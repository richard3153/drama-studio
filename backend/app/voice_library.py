"""本地音色库（Local Voice Library）。

把公开试听样本（积木全景音色库 voice.jimu.chat，1248 款真实录音）抓成本地参考音频库：
- `data/voice_library/index.json`：元数据（名称 / 编号 / 性别 / 分类 / 情绪 / 标签 / relPath）
- `data/voice_library/media/*.wav|*.mp3`：原声样本（约 1GB，不进 git）
- 抓取脚本：`tools/fetch_jimu_library.py`

用途：本地 zero-shot TTS（GPT-SoVITS / CosyVoice 等）需要「参考音频」，这份库就是候选池。
面板「后台配置 → 音色源 → 本地音色库」分页浏览、播放原声、把挑中的加入配音清单
（加入时 voice 填参考音频的绝对路径，provider=local）。
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LIB = DATA_DIR / "voice_library"
INDEX = LIB / "index.json"
MEDIA = LIB / "media"

GENDER_MAP = {"male": "m", "female": "f"}   # elder / child 性别不确定 → 空（配音不做性别强判）

_cache: dict = {"mtime": 0.0, "rows": []}


def rows() -> list[dict]:
    """索引行（带下载状态），按文件 mtime 缓存。"""
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
    for it in raw if isinstance(raw, list) else []:
        rel = it.get("relPath") or ""
        fname = Path(rel).name
        p = MEDIA / fname
        out.append({
            "code": it.get("code") or "",
            "name": it.get("name") or "",
            "gender": GENDER_MAP.get(it.get("gender") or "", ""),
            "genderName": it.get("genderName") or "",
            "category": it.get("category") or "",
            "categoryName": it.get("categoryName") or "",
            "emotionName": it.get("emotionName") or "",
            "tags": it.get("tags") or [],
            "sampleText": it.get("sampleText") or "",
            "file": fname,
            "ext": p.suffix.lower(),
            "size": p.stat().st_size if p.exists() else 0,
            "downloaded": p.exists() and p.stat().st_size > 1024,
        })
    _cache.update(mtime=mtime, rows=out)
    return out


def stats() -> dict:
    rs = rows()
    cats = {}
    for r in rs:
        cats[r["categoryName"]] = cats.get(r["categoryName"], 0) + 1
    return {
        "total": len(rs),
        "downloaded": sum(1 for r in rs if r["downloaded"]),
        "bytes": sum(r["size"] for r in rs),
        "categories": [{"key": k, "name": k, "count": v} for k, v in cats.items()],
        "file": str(INDEX),
    }


def query(q: str = "", gender: str = "", category: str = "",
          page: int = 1, size: int = 20) -> dict:
    rs = rows()
    q = (q or "").strip().lower()
    if q:
        rs = [r for r in rs if q in r["name"].lower() or q in r["code"].lower()
              or q in (r["categoryName"] or "").lower() or q in (r["genderName"] or "").lower()
              or any(q in str(t).lower() for t in r["tags"])
              or q in (r["sampleText"] or "").lower()]
    if gender:
        rs = [r for r in rs if r["gender"] == gender]
    if category:
        rs = [r for r in rs if r["category"] == category or r["categoryName"] == category]
    total = len(rs)
    size = max(1, min(100, int(size or 20)))
    pages = max(1, (total + size - 1) // size)
    page = max(1, min(pages, int(page or 1)))
    start = (page - 1) * size
    return {"total": total, "page": page, "pages": pages, "size": size,
            "stats": stats(), "items": rs[start:start + size]}


def find(code: str) -> dict | None:
    code = (code or "").strip().upper()
    return next((r for r in rows() if r["code"].upper() == code), None)


def audio_path(code: str) -> Path | None:
    r = find(code)
    if not r or not r["downloaded"]:
        return None
    return MEDIA / r["file"]


def add_to_sources(code: str, group: str | None = None) -> dict:
    """把库里的一条加入配音清单（provider=local，voice=参考音频绝对路径）。"""
    from . import voice_sources
    r = find(code)
    if not r:
        raise ValueError(f"音色库中没有编号 {code}")
    if not r["downloaded"]:
        raise ValueError(f"{r['code']} 的音频还没下载完（{r['file']}）")
    path = MEDIA / r["file"]
    label = f"{r['name'] or r['code']}（{r['code']}）"
    grp = group or f"积木音色库 · {r['categoryName'] or '未分类'}"
    voice_sources.add_item(grp, label, str(path), r["gender"], provider="local")
    return voice_sources.public()


def add_batch(codes: list[str]) -> dict:
    """批量加入（前端「批量加入本页」用）：逐条加，重复/缺失不阻塞，返回统计与失败原因。"""
    added, skipped, failed = 0, 0, []
    for code in [c for c in (codes or []) if c][:200]:
        try:
            add_to_sources(code)
            added += 1
        except ValueError as e:
            msg = str(e)
            if "已存在" in msg:
                skipped += 1
            else:
                failed.append(f"{code}: {msg}")
        except Exception as e:
            failed.append(f"{code}: {type(e).__name__} {e}")
    return {"added": added, "skipped": skipped, "failed": failed[:10], "state": voice_sources_public()}


def voice_sources_public() -> dict:
    from . import voice_sources
    return voice_sources.public()
