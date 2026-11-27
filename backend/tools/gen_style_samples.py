"""生成风格库示例缩略图（57 种风格 × 同一主体同一构图，只用本地 Qwen-Image）。

用途：`🎨 风格库` 每张卡片要有"这个风格长什么样"的示例图，而不是色块占位。
做法：同一段主体描述（年轻剑客 / 古宅烛光 / 半身），前面拼各风格的 style_lock，
每张 768×1024、22 步，出图后压成 384×512 的 jpg 存到 `backend/data/style_samples/<key>.jpg`，
由 `GET /api/style-samples/<key>` 提供给前端。已存在的图默认跳过（支持断点续跑）。

用法（在 backend 目录下、后端与 ComfyUI 都在跑时）：
    .venv/Scripts/python.exe tools/gen_style_samples.py            # 跳过已有
    .venv/Scripts/python.exe tools/gen_style_samples.py --force    # 全部重出
    .venv/Scripts/python.exe tools/gen_style_samples.py --only anime_2d,ghibli
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from PIL import Image  # noqa: E402

from app.adapters.comfyui_adapter import ComfyUIAdapter  # noqa: E402
from app.style_presets import STYLE_PRESETS  # noqa: E402

OUT_DIR = BACKEND / "data" / "style_samples"
WF = "char_portrait_qwen.json"

# 统一主体：短剧与漫剧都常见（古装剑客、半身中景、烛光庭院），换风格时差异全由 style_lock 决定。
SUBJECT = ("a young swordsman in ragged dark blue robes standing in a dim candle-lit "
           "ancient chinese courtyard, upper body medium shot, detailed expressive face, "
           "cinematic composition, atmospheric depth")
# 少数风格的主体本身就该换：等距 2.5D 是"小景模型"不是人像，套人像只会出一张打光怪的特写
SUBJECT_BY_KEY = {
    "iso_25d": ("isometric diorama of an ancient chinese courtyard house at dusk, miniature "
                "model look, tile roofs, stone steps, two tiny figures walking, "
                "45-degree top-down view, soft ambient light"),
}
THUMB = (384, 512)
BASE_SEED = 20261128


async def gen_one(comfy: ComfyUIAdapter, key: str, lock: str, seed: int) -> bool:
    wf = comfy.load_template(WF)
    overrides = {
        "positive_text": f"{lock}, {SUBJECT_BY_KEY.get(key, SUBJECT)}",
        "EmptyLatentImage.width": 768,
        "EmptyLatentImage.height": 1024,
        "KSampler.steps": 22,
        "KSampler.seed": seed,
        "TextEncodeQwenImage21.resolution": 1024,
    }
    wf = comfy.apply_overrides(wf, overrides)
    outs = await comfy.run(
        wf, filename_prefix=f"drama_studio/style_{key}",
        save_root=BACKEND / "data" / "downloads" / "style_samples",
        timeout=900,
    )
    if not outs:
        return False
    src = Path(outs[0])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB").resize(THUMB, Image.LANCZOS)
        im.save(OUT_DIR / f"{key}.jpg", "JPEG", quality=88, optimize=True)
    # 只留压好的 jpg，原始 png 从下载目录清掉
    try:
        src.unlink()
    except OSError:
        pass
    return True


async def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已有缩略图也重出")
    ap.add_argument("--only", default="", help="只出这几个 key（逗号分隔）")
    args = ap.parse_args(argv)

    only = {k.strip() for k in args.only.split(",") if k.strip()}
    todo = [(k, v) for k, v in STYLE_PRESETS.items() if not only or k in only]
    todo = [(k, v) for k, v in todo
            if args.force or not (OUT_DIR / f"{k}.jpg").exists()]
    print(f"[style] 待生成 {len(todo)} 张 / 风格库共 {len(STYLE_PRESETS)} 种", flush=True)
    if not todo:
        return 0

    comfy = ComfyUIAdapter()
    ok, failed = 0, []
    t0 = time.time()
    for i, (key, preset) in enumerate(todo, 1):
        seed = (BASE_SEED + i * 7919) % (2 ** 31 - 1)
        try:
            done = await gen_one(comfy, key, preset["style_lock"], seed)
        except Exception as e:  # noqa: BLE001
            print(f"[style] {i}/{len(todo)} {key} 失败：{e}", flush=True)
            done = False
            await asyncio.sleep(8)   # ComfyUI 可能被打崩，缓一下再看
        if done:
            ok += 1
            print(f"[style] {i}/{len(todo)} ok  {key}  ({time.time() - t0:.0f}s)", flush=True)
        else:
            failed.append(key)
            print(f"[style] {i}/{len(todo)} FAIL {key}", flush=True)
    if failed:
        print("[style] 失败清单：" + ",".join(failed), flush=True)
        print("[style] 可单独重跑：--only " + ",".join(failed), flush=True)
    print(f"[style] 完成：成功 {ok} / 失败 {len(failed)}，用时 {time.time() - t0:.0f}s", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
