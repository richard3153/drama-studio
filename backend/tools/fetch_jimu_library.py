"""把积木全景音色库（voice.jimu.chat，1248 款）抓成本地音色参考库。

用途：本地 zero-shot TTS（GPT-SoVITS / CosyVoice 等）需要「参考音频」，这个脚本把
1248 条公开试听样本落到 backend/data/voice_library/media/，并保留 index.json 元数据，
面板「音色源 → 本地音色库」按索引分页浏览、播放原声、把选中的加入配音清单。

- 断点续传：已存在且大小 > 1KB 的文件跳过（可反复跑）
- 并发 8，失败重试 2 次；进度写 data/voice_library/_download.log
- 产物不进 git（backend/data/* 已忽略）

用法：
    .venv\\Scripts\\python.exe tools\\fetch_jimu_library.py
    .venv\\Scripts\\python.exe tools\\fetch_jimu_library.py --workers 12
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

BASE = "https://voice.jimu.chat/"
ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "data" / "voice_library"
MEDIA = LIB / "media"
INDEX = LIB / "index.json"
LOG = LIB / "_download.log"
INDEX_URL = BASE + "voices_index.json"
DETAILS_URL = BASE + "voices_details.json"

_lock = threading.Lock()


def log(msg: str) -> None:
    with _lock:
        print(msg, flush=True)
        try:
            with LOG.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
        except Exception:
            pass


def ensure_index(client: httpx.Client) -> list[dict]:
    LIB.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    if not INDEX.exists():
        log("下载音色索引 voices_index.json …")
        r = client.get(INDEX_URL, timeout=90)
        r.raise_for_status()
        INDEX.write_bytes(r.content)
    if not (LIB / "details.json").exists():
        try:
            r = client.get(DETAILS_URL, timeout=90)
            r.raise_for_status()
            (LIB / "details.json").write_bytes(r.content)
        except Exception as e:
            log(f"details.json 下载失败（不影响主流程）：{e}")
    return json.loads(INDEX.read_text(encoding="utf-8"))


def target_path(item: dict) -> Path:
    rel = item.get("relPath") or ""
    name = Path(rel).name or f"{item.get('id', 'voice')}.wav"
    return MEDIA / name


def fetch_one(client: httpx.Client, item: dict) -> tuple[str, str]:
    out = target_path(item)
    if out.exists() and out.stat().st_size > 1024:
        return ("skip", out.name)
    url = BASE + (item.get("relPath") or "")
    for attempt in range(3):
        try:
            r = client.get(url, timeout=120)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            body = r.content
            if len(body) < 1024:
                raise RuntimeError(f"文件过小 {len(body)}B")
            tmp = out.with_suffix(out.suffix + ".part")
            tmp.write_bytes(body)
            tmp.replace(out)
            return ("ok", out.name)
        except Exception as e:
            if attempt == 2:
                return ("fail", f"{out.name}: {type(e).__name__} {e}")
            time.sleep(1.5 * (attempt + 1))
    return ("fail", out.name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    headers = {"User-Agent": "Mozilla/5.0 (compatible; drama-studio/1.0)"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        items = ensure_index(client)
        log(f"索引 {len(items)} 条，开始下载到 {MEDIA}")
        done = {"ok": 0, "skip": 0, "fail": 0}
        fails: list[str] = []
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(fetch_one, client, it): it for it in items}
            for i, fut in enumerate(as_completed(futs), 1):
                status, name = fut.result()
                done[status] += 1
                if status == "fail":
                    fails.append(name)
                if i % 50 == 0 or i == len(items):
                    rate = i / max(time.time() - t0, 0.1)
                    log(f"进度 {i}/{len(items)}  新下载 {done['ok']}  跳过 {done['skip']}  "
                        f"失败 {done['fail']}  {rate:.1f} 条/s")
        log(f"完成：{done}  用时 {time.time() - t0:.0f}s")
        if fails:
            log("失败清单前 20 条：\n" + "\n".join(fails[:20]))
        total = sum(p.stat().st_size for p in MEDIA.glob("*") if p.is_file())
        log(f"本地音色库合计 {total / 1024 ** 2:.0f} MB，{len(list(MEDIA.glob('*')))} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
