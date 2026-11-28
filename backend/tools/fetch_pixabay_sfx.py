"""Pixabay 音效抓取器（本地音效库，用于成片后期 BGM / 场景音 / 人声分轨）。

数据落盘：
  data/sfx_library/index.json   元数据（id / slug / 标题 / 标签 / 时长 / 作者 / 授权 / mp3 直链 / 本地文件 / 体积）
  data/sfx_library/media/<id>.<ext>
  data/sfx_library/_fetch.log   进度日志

抓取链路（每条）：列表页（20 条/页，含 id+slug）→ 详情页（JSON-LD 取 contentUrl + 元数据）→ CDN 下载音频。
Pixabay 站点对脚本请求有 Cloudflare 挑战，用 curl_cffi 的浏览器指纹 + 失败重试；音频 CDN 不限速。

用法：
  python tools/fetch_pixabay_sfx.py --kw whoosh --pages 3          # 单关键词探测
  python tools/fetch_pixabay_sfx.py --preset core --limit 3000     # 影视常用分类批量
  python tools/fetch_pixabay_sfx.py --all --limit 20000            # 全量扩充（慢，数小时级）
断点续传：index.json 里已有的 id 直接跳过；音频 >1KB 跳过下载。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

from curl_cffi import requests as cr

LIB = Path(__file__).resolve().parent.parent / "data" / "sfx_library"
INDEX = LIB / "index.json"
MEDIA = LIB / "media"
LOG = LIB / "_fetch.log"

SITE = "https://pixabay.com"
LIST_TPL = SITE + "/zh/sound-effects/search/{kw}/"
DETAIL_TPL = SITE + "/zh/sound-effects/{slug}-{sid}/"
UA_LANG = "zh-CN,zh;q=0.9"

ITEM_RE = re.compile(r'/zh/sound-effects/([a-z0-9\-]+?)-(\d{5,})/')
JSONLD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
DUR_RE = re.compile(r'"duration":"PT([0-9.]+)S?"')
TAG_RE = re.compile(r'<a[^>]+href="/zh/sound-effects/search/[^"]+"[^>]*>(.*?)</a>')

CORE_KW = [
    # 场景音（环境层）
    "rain", "thunder", "wind", "ocean", "waves", "forest", "birds", "fire", "crickets",
    "city", "traffic", "crowd", "market", "restaurant", "classroom", "office",
    "footsteps", "door", "knock", "sword", "horse", "car", "engine", "phone",
    # 转场 / 打击 / 动作层
    "whoosh", "transition", "impact", "punch", "hit", "explosion", "glass", "crash",
    "swish", "swoosh", "slam", "boom",
    # 人声层（群杂 / 反应）
    "laugh", "scream", "shout", "whisper", "cry", "baby", "applause", "gasp",
    "breath", "sigh", "groan",
    # 音乐 / 情绪层（BGM 候选，短片段与氛围）
    "ambient", "cinematic", "trailer", "epic", "suspense", "horror", "romantic",
    "action", "drone", "tension", "鼓", "钢琴", "古风", "武侠",
    "鼓点", "配乐", "战斗", "史诗",
]

# 精选建库用的扩展词组（--preset extended）：在 core 之外补足四轨的细粒度覆盖
EXTENDED_KW = [
    # 环境层（更细的时空/场所，长环境音，铺底与场景声）
    "morning", "night", "dawn", "dusk", "storm", "snow", "desert", "jungle", "river",
    "stream", "cave", "subway", "train", "station", "airport", "hospital", "school",
    "library", "mall", "elevator", "parking", "highway", "construction", "factory",
    "kitchen", "bar", "cafe", "club", "stadium", "church", "temple", "beach", "boat",
    "harbor", "farm", "dog", "cat", "wolf", "insects", "bees", "frogs",
    # 拟音 / 动作层（短促、可逐镜贴）
    "slap", "kick", "fall", "stab", "arrow", "bow", "gunshot", "gun", "reload",
    "ricochet", "blade", "armor", "whip", "magic", "spell", "laser", "robot",
    "alarm", "siren", "beep", "notification", "keyboard", "mouse", "camera",
    "shutter", "glitch", "typing", "paper", "page", "coin", "cash", "zipper",
    "bottle", "pour", "coffee", "dish", "chopsticks", "lock", "key", "chain",
    "bell", "doorbell", "stairs", "elevator-bell", "rain-window", "water", "wind-gust",
    # 人声层（群杂 / 反应 / 情绪）
    "chatter", "children", "playground", "cheer", "boo", "moan", "cough", "sneeze",
    "murmur", "kids", "argue", "whispering", "sarcastic", "scared", "angry-yell",
    # 音乐 / 情绪层（BGM 短曲与氛围铺底）
    "piano", "guitar", "strings", "cello", "flute", "erhu", "guzheng", "drums",
    "percussion", "bass", "lofi", "jazz", "techno", "sad", "happy", "funny", "cute",
    "mysterious", "calm", "peaceful", "hopeful", "dark", "angry", "wedding",
    "funeral", "victory", "fanfare", "cartoon", "adventure",
]

# 人声专补词包（--preset voice）：核心词包 / 扩展包里人声词占比低，Pixabay 人声素材存量也少，
# 单独一轮人群 / 儿童 / 耳语 / 情绪反应关键词，把 voice 轨补到可用量级。
VOICE_KW = [
    # 人群（议论 / 嘈杂底流 / 欢呼 / 掌声 / 抗议）
    "people", "people-talking", "crowd-talking", "crowd-laughing", "walla", "chatter",
    "audience", "clapping", "cheer", "boo", "protest", "party", "wedding",
    "restaurant-crowd", "market-crowd", "street-crowd", "office-chatter",
    # 儿童
    "children", "kids", "kids-playing", "toddler", "baby", "baby-laughing", "baby-crying",
    "playground", "kindergarten",
    # 耳语 / 低声 / 喃喃
    "whisper", "whispering", "murmur", "mumbling", "low-voice", "gibberish",
    # 情绪反应（笑 / 哭 / 喊 / 喘 / 咳）
    "laugh", "giggle", "man-laughing", "woman-laughing", "scream", "screaming", "shout",
    "yelling", "argue", "cry", "sobbing", "sigh", "gasp", "breath", "heavy-breath",
    "groan", "moan", "cough", "sneeze", "yawn", "snore",
    # 中文补充
    "人声", "人群", "儿童", "耳语", "低声", "群众", "欢呼", "掌声", "喧闹",
]

_write_lock = threading.Lock()
_state = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0, "start": time.time()}
_state_lock = threading.Lock()
_limiter_lock = threading.Lock()
_limiter_last = [0.0]
MIN_INTERVAL = 0.85  # 站点请求最小间隔（秒）：pixabay 的 Cloudflare 对突发很敏感


def pace() -> None:
    """全局限速：列表页与详情页共用一条最小间隔，避免触发 Cloudflare 挑战。"""
    with _limiter_lock:
        wait = MIN_INTERVAL - (time.time() - _limiter_last[0])
        if wait > 0:
            time.sleep(wait)
        _limiter_last[0] = time.time()


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_index() -> dict:
    if INDEX.exists():
        try:
            data = json.loads(INDEX.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_index(idx: dict) -> None:
    """原子写 + 合并磁盘上的人工字段。

    抓取进程每 20s 全量重写 index；如果它直接覆盖，面板里「点用途改轨」写进的
    track 字段会在下一次落盘时被抹掉。这里先读磁盘，把人工 track 盖回内存条目，
    并把磁盘上抓取进程还没见过的条目（例如手动追加）保留下来。
    """
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    try:
        disk = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    except Exception:
        disk = {}
    if isinstance(disk, dict):
        for k, it in list(idx.items()):
            d = disk.get(k)
            if isinstance(d, dict) and d.get("track") in ("bgm", "amb", "voice", "sfx"):
                merged = dict(it)
                merged["track"] = d["track"]
                idx[k] = merged
        for k, d in disk.items():
            if k not in idx and isinstance(d, dict) and d.get("file"):
                idx[k] = d
    tmp = INDEX.with_name(f".{INDEX.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(idx, ensure_ascii=False, indent=1))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, INDEX)


_tls = threading.local()
HOME = SITE + "/zh/sound-effects/"


def make_session() -> cr.Session | None:
    """新建一个能通过 Cloudflare 的 session（预热首页，失败就换指纹重来）。"""
    for i in range(4):
        s = cr.Session(impersonate="chrome")
        try:
            r = s.get(HOME, timeout=25, headers={"Accept-Language": UA_LANG})
            if r.status_code == 200 and "Just a moment" not in r.text:
                return s
        except Exception:
            pass
        time.sleep(2 + i * 3)
    return None


def get_session() -> cr.Session | None:
    """线程局部 session；被 CF 挑战后丢弃重建（挑战页会污染整条连接的信誉）。"""
    s = getattr(_tls, "s", None)
    if s is not None and getattr(_tls, "bad", False):
        _tls.s, _tls.bad = None, False
        s = None
    if s is None:
        s = make_session()
        _tls.s = s
    return s


def http_get(url: str, referer: str | None = None, tries: int = 4) -> str | None:
    for i in range(tries):
        s = get_session()
        if s is None:
            time.sleep(5 + i * 5)
            continue
        try:
            pace()
            hdr = {"Accept-Language": UA_LANG}
            if referer:
                hdr["Referer"] = referer
            r = s.get(url, timeout=35, headers=hdr)
            body = r.text or ""
            if r.status_code == 404:
                return None
            if r.status_code == 200 and len(body) > 20000 and "Just a moment" not in body:
                return body
            _tls.bad = True              # 403 / 挑战页：换 session，退避再来
            time.sleep(5 + i * 7)
        except Exception:
            _tls.bad = True
            time.sleep(3 + i * 6)
    return None


def list_ids(kw: str, pages: int, delay: float = 1.2) -> list[tuple[str, int]]:
    """抓关键词的列表页，返回 [(slug, id)]（按页顺序去重）。"""
    out: list[tuple[str, int]] = []
    seen: set[int] = set()
    for p in range(1, pages + 1):
        url = LIST_TPL.format(kw=quote(kw)) + ("" if p == 1 else f"?pagi={p}")
        h = http_get(url, referer=LIST_TPL.format(kw=quote(kw)))
        if not h:
            log(f"列表失败 kw={kw} pagi={p}")
            continue
        items = ITEM_RE.findall(h)
        for slug, sid in items:
            sid = int(sid)
            if sid in seen:
                continue
            seen.add(sid)
            out.append((slug, sid))
        time.sleep(delay)
    return out


def clean_text(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def parse_detail(h: str) -> dict | None:
    obj = None
    for b in JSONLD_RE.findall(h):
        try:
            d = json.loads(b)
        except Exception:
            continue
        stack = [d]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "contentUrl" in cur and str(cur.get("contentUrl", "")).startswith("http"):
                    obj = cur
                    break
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    if not obj:
        return None
    dur = DUR_RE.search(h)
    author = (obj.get("author") or {}).get("name") if isinstance(obj.get("author"), dict) else None
    raw_name = clean_text(obj.get("headline") or obj.get("name") or "")
    name = re.sub(r"\s*by\s+[^|]+?\s*\|\s*免版税音效$", "", raw_name).strip()
    name = re.sub(r"\s*\|\s*免版税音效$", "", name).strip()
    if name.endswith(" 音效"):
        name = name[:-3].strip()
    tags: list[str] = []
    for t in TAG_RE.findall(h):
        t = clean_text(t)
        if t and t not in tags:
            tags.append(t)
    return {
        "contentUrl": obj.get("contentUrl"),
        "headline": name,
        "description": clean_text(obj.get("description") or "")[:400],
        "duration": float(dur.group(1)) if dur else None,
        "author": author,
        "keywords": obj.get("keywords") or [],
        "tags": tags[:12],
        "datePublished": obj.get("datePublished"),
    }


def download(url: str, dest: Path) -> int:
    """音频走 CDN（不经 Cloudflare），失败重试 2 次。"""
    part = dest.with_suffix(dest.suffix + ".part")
    for i in range(3):
        try:
            s = get_session()
            if s is None:
                time.sleep(3)
                continue
            r = s.get(url, timeout=150, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 512:
                part.write_bytes(r.content)
                os.replace(part, dest)
                return len(r.content)
            time.sleep(2 + i * 3)
        except Exception:
            time.sleep(2 + i * 3)
    return 0


def ext_of(url: str, fallback: str = ".mp3") -> str:
    m = re.search(r"\.(mp3|wav|ogg|m4a)", url.split("?")[0], re.I)
    return ("." + m.group(1).lower()) if m else fallback


def process_one(slug: str, sid: int, idx: dict, meta_lock: threading.Lock) -> None:
    key = str(sid)
    if key in idx and idx[key].get("file"):
        with _state_lock:
            _state["skip"] += 1
        return
    url = DETAIL_TPL.format(slug=slug, sid=sid)
    h = http_get(url, referer=HOME)
    if not h:
        with _state_lock:
            _state["fail"] += 1
        return
    meta = parse_detail(h)
    if not meta or not meta["contentUrl"]:
        with _state_lock:
            _state["fail"] += 1
        return
    ext = ext_of(meta["contentUrl"])
    dest = MEDIA / f"{sid}{ext}"
    size = 0
    if not (dest.exists() and dest.stat().st_size > 1024):
        size = download(meta["contentUrl"], dest)
        if not size:
            with _state_lock:
                _state["fail"] += 1
            return
    else:
        size = dest.stat().st_size
    rec = {
        "id": sid,
        "slug": slug,
        "name": meta["headline"],
        "desc": meta["description"],
        "duration": meta["duration"],
        "author": meta["author"],
        "tags": meta["tags"],
        "keywords": meta["keywords"][:8] if isinstance(meta["keywords"], list) else [],
        "page": url,
        "mp3": meta["contentUrl"],
        "file": dest.name,
        "ext": ext,
        "size": size,
        "fetched": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with meta_lock:
        idx[key] = rec
    with _state_lock:
        _state["ok"] += 1
        _state["bytes"] += size


def main() -> None:
    ap = argparse.ArgumentParser(description="抓取 Pixabay 音效到本地音效库")
    ap.add_argument("--kw", action="append", default=[], help="关键词（可重复）")
    ap.add_argument("--preset", choices=["core", "extended", "voice", "all"], help="内置分类关键词组：core 影视常用 / extended 精细扩充 / voice 人声专补 / all 三组叠加")
    ap.add_argument("--pages", type=int, default=5, help="每个关键词抓多少页（20 条/页）")
    ap.add_argument("--limit", type=int, default=0, help="最多抓多少条有效音效（0=不限）")
    ap.add_argument("--workers", type=int, default=3, help="详情页并发（站点 CF 敏感，建议 2-4）")
    ap.add_argument("--delay", type=float, default=1.2, help="列表页间隔秒")
    args = ap.parse_args()

    kws = list(args.kw)
    if args.preset in ("core", "all"):
        kws += CORE_KW
    if args.preset in ("extended", "all"):
        kws += EXTENDED_KW
    if args.preset in ("voice", "all"):
        kws += VOICE_KW
    if not kws:
        print("需要 --kw 或 --preset core|extended|voice|all")
        sys.exit(2)

    MEDIA.mkdir(parents=True, exist_ok=True)
    idx = load_index()
    log(f"启动：关键词 {len(kws)} 个 × {args.pages} 页，已有 {len(idx)} 条，workers={args.workers}")

    targets: list[tuple[str, int]] = []
    for kw in kws:
        got = list_ids(kw, args.pages, args.delay)
        fresh = [(sl, i) for sl, i in got if str(i) not in idx]
        targets.extend(fresh)
        log(f"kw={kw} 列表 {len(got)} 条，新增候选 {len(fresh)}（累计 {len(targets)}）")
        if args.limit and len(targets) >= args.limit:
            targets = targets[: args.limit]
            break

    if args.limit:
        targets = targets[: args.limit]
    log(f"待抓 {len(targets)} 条")

    meta_lock = threading.Lock()
    last_save = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(process_one, sl, i, idx, meta_lock): i for sl, i in targets}
        done = 0
        for f in as_completed(futs):
            done += 1
            if time.time() - last_save > 20:
                with meta_lock:
                    save_index(idx)
                last_save = time.time()
                log(f"进度 {done}/{len(targets)} ok={_state['ok']} skip={_state['skip']} fail={_state['fail']} "
                    f"{_state['bytes']/1024/1024:.0f}MB")

    with meta_lock:
        save_index(idx)
    el = time.time() - _state["start"]
    log(f"完成：ok={_state['ok']} skip={_state['skip']} fail={_state['fail']} "
        f"{_state['bytes']/1024/1024:.1f}MB 用时 {el:.0f}s 库共 {len(idx)} 条")


if __name__ == "__main__":
    main()

