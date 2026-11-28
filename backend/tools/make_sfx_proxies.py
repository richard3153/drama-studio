"""为本地音效库生成 128k mp3 代理（保留原码不动，代理只给浏览器试听/预览用）。

用法（backend 目录）：
    .venv\\Scripts\\python.exe tools\\make_sfx_proxies.py                # 全量增量
    .venv\\Scripts\\python.exe tools\\make_sfx_proxies.py --limit 500    # 只做 500 条
    .venv\\Scripts\\python.exe tools\\make_sfx_proxies.py --workers 3

产物：data/sfx_library/media_proxy/<id>.mp3
规则：源文件更新过、或代理缺失/过小 → 重转；已是最新 → 跳过（可反复跑）。
合成混音仍用 media/ 下的原码（sfx_library.resolve / audio_path(quality="orig")）。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "data" / "sfx_library"
INDEX = LIB / "index.json"
MEDIA = LIB / "media"
PROXY = LIB / "media_proxy"
LOG = LIB / "_proxy.log"

# ffmpeg：优先 PATH，其次项目常用位置（与 voice_service 里的常量保持一致）
_CANDIDATES = [
    r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\custom_nodes\video2dlssnr\bin\ffmpeg.exe",
    "ffmpeg",
]


def ffmpeg() -> str:
    for c in _CANDIDATES:
        if Path(c).exists() or shutil.which(c):
            return c
    raise SystemExit("找不到 ffmpeg：把 ffmpeg 放进 PATH 或用项目内置路径")


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="生成本地音效库 128k 代理")
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少条（0=全部）")
    ap.add_argument("--workers", type=int, default=2, help="并行 ffmpeg 数（默认 2，吃 CPU 别开太大）")
    ap.add_argument("--bitrate", default="128k")
    args = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit("音效库为空：先跑 fetch_pixabay_sfx.py")

    raw = json.loads(INDEX.read_text(encoding="utf-8"))
    PROXY.mkdir(parents=True, exist_ok=True)
    # 清理上次异常中断留下的临时文件（以点开头 + .tmp.mp3），避免堆积
    for stale in PROXY.glob(".*.tmp.mp3"):
        stale.unlink(missing_ok=True)
    exe = ffmpeg()

    jobs = []
    for sid, rec in (raw.items() if isinstance(raw, dict) else []):
        f = rec.get("file") or ""
        src = MEDIA / f if f else None
        if not src or not src.exists() or src.stat().st_size < 512:
            continue
        dst = PROXY / f"{sid}.mp3"
        if dst.exists() and dst.stat().st_size > 512 and dst.stat().st_mtime >= src.stat().st_mtime:
            continue
        jobs.append((str(sid), src, dst))
    total = len(jobs) if not args.limit else min(len(jobs), args.limit)
    log(f"待转 {total} 条（缺口 {len(jobs)}），workers={args.workers}, bitrate={args.bitrate}")

    ok = fail = 0
    done = 0
    t0 = time.time()

    def one(job):
        sid, src, dst = job
        # 临时名必须保留 .mp3 后缀：ffmpeg 靠扩展名选封装格式，纯 .tmp 会报
        # "Unable to choose an output format"
        tmp = dst.with_name(f".{dst.stem}.{time.time_ns()}.tmp.mp3")
        cmd = [exe, "-y", "-v", "error", "-i", str(src),
               "-vn", "-ac", "2", "-ar", "44100", "-b:a", args.bitrate, str(tmp)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 512:
                tmp.unlink(missing_ok=True)
                return False, (r.stderr.decode("utf-8", "ignore")[:120] or "空输出")
            dst.unlink(missing_ok=True)
            tmp.replace(dst)
            return True, ""
        except Exception as e:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            return False, str(e)[:120]

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(one, j): j for j in jobs[:total]}
        for fu in cf.as_completed(futs):
            good, err = fu.result()
            done += 1
            if good:
                ok += 1
            else:
                fail += 1
                log(f"失败 {futs[fu][0]}: {err}")
            if done % 50 == 0 or done == total:
                mb = sum(p.stat().st_size for p in PROXY.glob("*.mp3")) / 1024 / 1024
                log(f"进度 {done}/{total} ok={ok} fail={fail} 代理共 {mb:.0f}MB "
                    f"({(time.time() - t0) / max(done, 1):.2f}s/条)")

    log(f"完成：本次转 {ok} 条，失败 {fail} 条，用时 {int(time.time() - t0)}s")


if __name__ == "__main__":
    sys.exit(main())
