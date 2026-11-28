"""本地音效库（SFX Library）：BGM / 场景音 / 人声 / 动作音，供成片分轨混音。

数据：`data/sfx_library/index.json`（id → 元数据 + mp3 直链 + 本地文件名）+ `media/`。
抓取：`tools/fetch_pixabay_sfx.py`（Pixabay 免版税音效，逐条抓详情取直链再下音频）。

分轨归类（track）按元数据关键词自动判断，不依赖站点分类：
  bgm   —— 音乐/氛围/气息（可循环铺底）
  amb   —— 环境声音（雨/风/海/林/城市/人群，铺场景底噪）
  voice —— 人声反应（笑/喊/哭/气喘/群众杂声）
  sfx   —— 动作与打击（whoosh / 撞击 / 爆炸 / 玻璃 / 刀剑，贴动作点）
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "data" / "sfx_library"
INDEX = LIB / "index.json"
MEDIA = LIB / "media"
# 代理文件（128k mp3）：原码保留不动，代理只用于浏览器试听/预览，省带宽省解码。
# 合成混音始终走原码（resolve/audio_path 默认返回 MEDIA 下的原文件）。
PROXY = LIB / "media_proxy"

TRACK_NAMES = {"bgm": "BGM 音乐", "amb": "场景环境音", "voice": "人声反应", "sfx": "动作打击音"}

# 关键词优先级：amb 强词（自然/场所/ambience）→ voice → sfx → bgm → 兜底 sfx
# 注意 bgm 里不能放 ambient（环境音的英文描述几乎都写 “ambient sound”，会整片错判成 BGM）
_KW = {
    "voice": ["voice", "vocal", "laugh", "scream", "shout", "whisper", "cry", "sob", "baby",
              "applause", "crowd", "cheer", "gasp", "breath", "sigh", "groan", "giggle",
              "talking", "walla", "murmur", "chatter",
              "人声", "笑", "喊", "哭", "尖叫", "群众", "掌声", "喘息", "叹气", "台词"],
    "sfx": ["whoosh", "swoosh", "swish", "transition", "impact", "hit", "punch", "slap",
            "explosion", "blast", "boom", "crash", "glass", "slam", "sword", "gun", "shot",
            "magic", "spell", "zap", "riser", "stinger", "footstep", "knock", "door",
            "打击", "撞击", "爆炸", "玻璃", "刀剑", "转场", "特效", "法术", "枪", "脚步"],
    "bgm": ["music", "musical", "soundtrack", "score", "drone", "cinematic",
            "trailer", "epic", "suspense", "tension", "horror", "romantic", "piano", "guitar",
            "orchestra", "percussion", "drum", "beat", "loop", "jingle",
            "音乐", "配乐", "钢琴", "鼓", "古风", "武侠", "史诗", "悬疑", "恐怖", "浪漫",
            "战斗", "燃"],
}
_AMB = ["rain", "rainfall", "thunder", "wind", "storm", "ocean", "wave", "sea", "river",
        "water", "forest", "bird", "cricket", "fire", "fireplace", "city", "traffic",
        "street", "market", "restaurant", "office", "classroom", "room tone", "ambience",
        "ambient sound", "crowd", "snow", "jungle", "cave", "subway", "station",
        "airport", "hospital", "school", "library", "mall", "elevator", "parking",
        "highway", "construction", "factory", "kitchen", "cafe", "club", "stadium",
        "church", "temple", "beach", "boat", "harbor", "farm", "insect", "frog",
        "雨", "雷", "风", "海", "水", "森林", "鸟", "火", "城市", "街道",
        "市场", "环境"]

# 人声强词：必须压过 amb（人群底噪里也全是 crowd，不先判人声的话「人群闲聊/笑/掌声」
# 会被整片归成环境音，导致 voice 轨几乎为空）。只放不会和自然环境撞车的词。
_VOICE_STRONG = ["talk", "chatter", "walla", "murmur", "whisper", "laugh", "giggle",
                 "scream", "shout", "yell", "cry", "sob", "gasp", "applause", "clap",
                 "cheer", "sigh", "groan", "moan", "cough", "sneeze", "yawn", "snore",
                 "argue", "voice", "vocal", "baby", "speech", "conversation",
                 "说", "笑", "喊", "哭", "尖叫", "掌声", "耳语", "人声", "闲聊"]

_cache: dict = {"mtime": 0.0, "rows": []}


def track_of(rec: dict) -> str:
    manual = str(rec.get("track") or "").strip()
    if manual in TRACK_NAMES:      # 人工纠正优先（写入 index 的 track 字段）
        return manual
    text = " ".join([str(rec.get("name") or ""), str(rec.get("desc") or ""),
                     " ".join(str(t) for t in (rec.get("tags") or [])),
                     " ".join(str(t) for t in (rec.get("keywords") or []))]).lower()
    if any(k in text for k in _VOICE_STRONG):
        return "voice"          # 明确的人声反应/群杂，优先于环境
    if any(k in text for k in _AMB):
        return "amb"
    for tr in ("voice", "sfx", "bgm"):
        if any(k.lower() in text for k in _KW[tr]):
            return tr
    return "sfx"   # 兜底：音效库默认按动作音用


def rows() -> list[dict]:
    if not INDEX.exists():
        return []
    mtime = INDEX.stat().st_mtime
    if _cache["rows"] and _cache["mtime"] == mtime:
        return _cache["rows"]
    try:
        raw = json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for k, it in (raw.items() if isinstance(raw, dict) else []):
        f = it.get("file") or ""
        p = MEDIA / f if f else None
        size = p.stat().st_size if (p and p.exists()) else (it.get("size") or 0)
        out.append({
            "id": str(it.get("id") or k),
            "name": it.get("name") or "",
            "desc": (it.get("desc") or "")[:160],
            "duration": it.get("duration"),
            "author": it.get("author") or "",
            "tags": [str(t) for t in (it.get("tags") or [])][:6],
            "track": track_of(it),
            "file": f,
            "ext": it.get("ext") or (p.suffix if p else ""),
            "size": size,
            "downloaded": bool(p and p.exists() and size > 512),
        })
    _cache.update(mtime=mtime, rows=out)
    return out


def stats() -> dict:
    rs = rows()
    per = {k: 0 for k in TRACK_NAMES}
    for r in rs:
        per[r["track"]] = per.get(r["track"], 0) + 1
    return {
        "total": len(rs),
        "downloaded": sum(1 for r in rs if r["downloaded"]),
        "bytes": sum(r["size"] for r in rs),
        "tracks": [{"key": k, "name": v, "count": per.get(k, 0)} for k, v in TRACK_NAMES.items()],
    }


def query(q: str = "", track: str = "", page: int = 1, size: int = 20,
          max_dur: float = 0) -> dict:
    rs = rows()
    q = (q or "").strip().lower()
    if q:
        rs = [r for r in rs if q in r["name"].lower() or q in r["desc"].lower()
              or q in r["author"].lower() or any(q in t.lower() for t in r["tags"])
              or q in r["id"]]
    if track:
        rs = [r for r in rs if r["track"] == track]
    if max_dur:
        rs = [r for r in rs if (r["duration"] or 999) <= max_dur]
    rs = sorted(rs, key=lambda r: (-1 if r["downloaded"] else 0, -(r["duration"] or 0)))
    total = len(rs)
    size = max(1, min(100, int(size or 20)))
    pages = max(1, (total + size - 1) // size)
    page = max(1, min(pages, int(page or 1)))
    start = (page - 1) * size
    return {"total": total, "page": page, "pages": pages, "size": size,
            "stats": stats(), "items": rs[start:start + size]}


def find(sid: str) -> dict | None:
    sid = str(sid or "").strip()
    return next((r for r in rows() if r["id"] == sid), None)


def audio_path(sid: str, quality: str = "orig") -> Path | None:
    """quality='proxy' 时优先返回 128k 代理（没有则回退原码）；'orig' 返回下载到的原文件。"""
    r = find(sid)
    if not r or not r["downloaded"]:
        return None
    orig = MEDIA / r["file"]
    if quality == "proxy":
        pp = PROXY / f"{r['id']}.mp3"
        try:
            if pp.exists() and pp.stat().st_size > 512 and \
                    pp.stat().st_mtime >= orig.stat().st_mtime:
                return pp
        except OSError:
            pass
    return orig


def proxy_stats() -> dict:
    """代理覆盖率（供设置页与工具输出用）。"""
    rs = [r for r in rows() if r["downloaded"]]
    ready = 0
    pbytes = 0
    for r in rs:
        pp = PROXY / f"{r['id']}.mp3"
        try:
            if pp.exists() and pp.stat().st_size > 512:
                ready += 1
                pbytes += pp.stat().st_size
        except OSError:
            pass
    return {"total": len(rs), "ready": ready, "bytes": pbytes, "missing": len(rs) - ready}


def set_track(sid: str, track: str) -> dict:
    """人工纠正分轨（写回 index.json 的 track 字段；track="" 则恢复自动归类）。原子写。"""
    sid = str(sid or "").strip()
    if track and track not in TRACK_NAMES:
        return {"ok": False, "error": f"track 只能是 {'/'.join(TRACK_NAMES)}"}
    if not INDEX.exists():
        return {"ok": False, "error": "音效库为空"}
    raw = json.loads(INDEX.read_text(encoding="utf-8"))
    rec = raw.get(sid) if isinstance(raw, dict) else None
    if not rec:
        return {"ok": False, "error": f"音效 {sid} 不存在"}
    if track:
        rec["track"] = track
    else:
        rec.pop("track", None)
    tmp = INDEX.with_name(f".{INDEX.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)
    _cache["mtime"] = 0.0
    return {"ok": True, "id": sid, "track": track_of(rec), "manual": bool(track)}


def resolve(ref: str) -> Path | None:
    """把「音效库 id」或「本地绝对路径」解析成实际音频文件（混音用）。"""
    ref = (ref or "").strip()
    if not ref:
        return None
    p = Path(ref)
    if p.is_absolute() and p.exists():
        return p
    return audio_path(ref)
