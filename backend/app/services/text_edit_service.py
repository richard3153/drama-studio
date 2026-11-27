"""图片文字局部微调（inpaint）：在**已生成的图**上只重画文字所在区域。

设计前提（用户明确要求）：
  · 不再用云端 GPT-Image 2.5 出整图——那样画风/构图/光影全会变，等于重画；
  · 只在原图的文字框内部重绘，框外的纸纹、折痕、朱印、边缘光照一字不动；
  · 全程本地 ComfyUI（Qwen-Image 2.1 + mask 局部重绘），零 token、零云端调用。

实现要点（实测踩过的坑）：
  1. VAEEncodeForInpaint 对 16 通道的 Qwen VAE 不成立——mask 区会被填成灰块、
     采样不生效（第一次试跑整块灰）。正确路子是 VAEEncode 原图 +
     SetLatentNoiseMask(框选 mask) + KSampler denoise≈0.88：
     框外 latent 原样保留，框内加噪重画。
  2. mask 必须是"白=重画、黑=保留"，且要羽化（默认 12px @1024），
     否则接缝是一条硬边。
  3. 提示词写成中文指令式（"把这块的竖排毛笔字写成「青云宗令牌」"），
     实测 Qwen-Image 在框内能把 5 个中文字全写对。
"""
from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy.orm import Session

from ..adapters.comfyui_adapter import ComfyUIAdapter
from ..db import AssetImage, TaskRecord
from ..config import ASSETS_ROOT

NEG = ("blurry text, gibberish characters, garbled lettering, misspelled characters, "
       "extra text, watermark, lowres, deformed")

# 缺省文字框（归一化）：竖排五字常见位置的中上段。
# 刻意避开右下朱印与右侧边框——框压到印章会把印章重画淡（实测）。
DEFAULT_BOX = {"x": 0.335, "y": 0.195, "w": 0.30, "h": 0.545}


def _clamp_box(box: dict | None) -> dict:
    """归一化框（0-1），越界/太小都收回来——mask 太小等于没重画，太大等于重画整图。"""
    b = dict(DEFAULT_BOX)
    for k in ("x", "y", "w", "h"):
        try:
            if box and box.get(k) is not None:
                b[k] = float(box[k])
        except (TypeError, ValueError):
            pass
    b["w"] = max(0.05, min(0.95, b["w"]))
    b["h"] = max(0.05, min(0.95, b["h"]))
    b["x"] = max(0.0, min(1.0 - b["w"], b["x"]))
    b["y"] = max(0.0, min(1.0 - b["h"], b["y"]))
    return b


def make_mask(src: Path, box: dict | None, out_path: Path,
              feather_px: int | None = None) -> Path:
    """按归一化框生成羽化 mask（白=重画区，黑=保留），尺寸与原图一致。"""
    b = _clamp_box(box)
    with Image.open(src) as im:
        W, H = im.size
    box_px = (int(b["x"] * W), int(b["y"] * H),
              int((b["x"] + b["w"]) * W), int((b["y"] + b["h"]) * H))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rectangle(box_px, fill=255)
    if feather_px is None:
        # 羽化按图短边走：768 宽 → 9px，1024 → 12px，羽化过大会把字抹平
        feather_px = max(4, int(min(W, H) / 85))
    m = m.filter(ImageFilter.GaussianBlur(feather_px))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.convert("RGB").save(out_path)
    return out_path


def build_prompt(text: str, extra: str = "") -> str:
    """中文指令式提示词：说清"哪块、写成什么、其余别动"。"""
    t = (text or "").strip()
    head = (f"把画面中文字所在区域的字，改写为「{t}」，"
            "中文毛笔字或印刷体，字形准确、笔画清晰、逐字可读，字距与排版自然；"
            "文字所在纸面/布面/牌面的纹理、折痕、做旧痕迹、朱印、边框与光照保持原样，"
            "画面其余部分完全不变，不要新增任何多余文字")
    return f"{head}。{extra}" if extra else head


async def run_text_edit(db: Session, task: TaskRecord, params: dict) -> dict:
    """任务入口：读源图 → 生成 mask → 本地 Qwen 局部重绘 → 落库新版本。"""
    from ..scheduler.queue import update_progress

    src = Path(params["source_path"])
    if not src.exists():
        raise RuntimeError(f"源图不存在：{src}")
    pid = int(params["project_id"])
    text = (params.get("text") or "").strip()
    if not text:
        raise RuntimeError("没填要写的文字内容")

    box = _clamp_box(params.get("box"))
    mask_path = Path(ASSETS_ROOT) / str(pid) / "masks" / f"text_mask_{int(datetime.now().timestamp()*1000)}.png"
    make_mask(src, box, mask_path)
    update_progress(db, task, 0.08, f"局部蒙版已生成（框 {box['w']*100:.0f}%×{box['h']*100:.0f}%）")

    comfy = ComfyUIAdapter()
    src_name = await comfy.upload_image(src)
    mask_name = await comfy.upload_image(mask_path, subfolder="drama_studio_mask")

    wf = comfy.load_template("prop_text_inpaint.json")
    seed = int(params.get("seed") or random.randint(0, 2 ** 31 - 1))
    denoise = float(params.get("denoise") or 0.88)
    denoise = max(0.55, min(0.98, denoise))   # <0.55 字写不实，>0.98 框内纹理全重画
    prompt = build_prompt(text, params.get("extra_prompt") or "")
    wf = comfy.apply_overrides(wf, {
        "LoadImage.image": src_name,
        "LoadImageMask.image": mask_name,
        "KSampler.seed": seed,
        "KSampler.denoise": denoise,
        "positive_text": prompt,
        "negative_text": NEG,
    })
    update_progress(db, task, 0.15, "本地 Qwen-Image 局部重绘中（只动文字框）")
    files = await comfy.run(
        wf,
        filename_prefix=f"drama_studio/p{pid}_text{params.get('entity_id', '')}",
        save_root=Path(ASSETS_ROOT) / str(pid) / "assets",
        timeout=900,
        on_stage=lambda m: print(f"[task {task.id}] {m}"),
    )
    await comfy.free_memory()

    kind = params.get("kind") or "prop"
    saved = []
    for f in files:
        img = AssetImage(
            project_id=pid,
            character_id=params.get("character_id"),
            kind=kind,
            file_path=str(f),
            prompt=prompt,
            meta_json=json.dumps({
                "model_key": "qwen_image_2.1",
                "workflow": "prop_text_inpaint.json",
                "op": "text_inpaint",
                "parent_asset_id": params.get("asset_id"),
                "source_path": str(src),
                "entity_type": params.get("entity_type", "prop"),
                "entity_id": params.get("entity_id"),
                "text": text,
                "box": box,
                "denoise": denoise,
                "seed": seed,
                "local_only": True,
            }, ensure_ascii=False),
        )
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": kind})
    update_progress(db, task, 1.0, "局部改字完成")
    return {"assets": saved, "model_key": "qwen_image_2.1", "local_only": True}
