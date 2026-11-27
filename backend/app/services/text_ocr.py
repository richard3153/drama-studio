"""本地 OCR 读字（RapidOCR / PP-OCRv4 ONNX）——给「改字自动迭代」提供判定信号。

为什么选它而不是视觉大模型：
  · 本机 Ollama 只有纯文本权重（qwen3.5 / qwen3），没有视觉模型；拉一个 3B VL 会和
    常驻的 ComfyUI 抢 8G 显存，还要多等 10–30 秒/次；
  · RapidOCR 是 CPU 即可跑的离线 OCR（依赖约 40MB + 内置中文模型，不落 hf 下载），
    整图约 2–3 秒，零 token、零显存占用；
  · 它读得出「字对不对」这件事——这正是自动迭代需要的唯一信号。

**为什么不裁小图单独 OCR**（实测教训）：把框内区域裁出来再 OCR，竖排大字的边缘笔画被
裁断、行文上下文丢失，识别率断崖下跌（「灵石兑换券」整图读对，裁框后只剩「石兑」）。
所以统一**先整图 OCR，再按框（外扩 25%）过滤文本块**——det 阶段看到完整版面，
判定又只算框附近的字，两头都不吃亏。
"""
from __future__ import annotations

import threading
from pathlib import Path

_ENGINE = None
_ENGINE_TRIED = False
_LOCK = threading.Lock()

_MIN_SCORE = 0.30


def available() -> bool:
    return get_engine() is not None


def get_engine():
    """懒加载 OCR 引擎；首次约 1–2 秒（模型加载），失败只试一次。"""
    global _ENGINE, _ENGINE_TRIED
    if _ENGINE_TRIED:
        return _ENGINE
    with _LOCK:
        if not _ENGINE_TRIED:
            try:
                from rapidocr_onnxruntime import RapidOCR
                _ENGINE = RapidOCR()
            except Exception as e:  # noqa: BLE001
                print(f"[text_ocr] OCR 引擎不可用：{e}")
                _ENGINE = None
            _ENGINE_TRIED = True
    return _ENGINE


def _overlap_ratio(bb: dict, region: dict) -> float:
    x0 = max(bb["x"], region["x"])
    y0 = max(bb["y"], region["y"])
    x1 = min(bb["x"] + bb["w"], region["x"] + region["w"])
    y1 = min(bb["y"] + bb["h"], region["y"] + region["h"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area = max(1e-9, bb["w"] * bb["h"])
    return inter / area


def read_region(image_path: str | Path, box: dict | None = None,
                pad: float = 0.25, min_cover: float = 0.45,
                min_score: float = _MIN_SCORE) -> list[dict] | None:
    """整图 OCR，再按 `box`（外扩 pad 倍）过滤文本块。

    返回 [{"text", "score", "bbox": {x,y,w,h}}]（bbox 为整图归一化坐标）；
    读不到字返回 []，引擎不可用返回 None。
    """
    eng = get_engine()
    if eng is None:
        return None

    import numpy as np
    from PIL import Image

    with Image.open(image_path) as im:
        im = im.convert("RGB")
        W, H = im.size
        short = max(1, min(W, H))
        scale = min(2.0, 640.0 / short) if short < 640 else 1.0
        if scale > 1.05:
            im = im.resize((int(W * scale), int(H * scale)), Image.LANCZOS)

    try:
        res, _ = eng(np.asarray(im))
    except Exception as e:  # noqa: BLE001
        print(f"[text_ocr] OCR 调用失败：{e}")
        return []

    out: list[dict] = []
    for it in (res or []):
        try:
            pts, txt, sc = it[0], (it[1] or "").strip(), float(it[2])
        except (IndexError, TypeError, ValueError):
            continue
        if not txt or sc < min_score:
            continue
        xs = [float(p[0]) / scale for p in pts]
        ys = [float(p[1]) / scale for p in pts]
        out.append({
            "text": txt,
            "score": round(sc, 4),
            "bbox": {"x": max(0.0, min(xs) / W), "y": max(0.0, min(ys) / H),
                     "w": max(0.0, (max(xs) - min(xs)) / W),
                     "h": max(0.0, (max(ys) - min(ys)) / H)},
        })

    if not box:
        return out

    region = {
        "x": max(0.0, float(box["x"]) - float(box["w"]) * pad),
        "y": max(0.0, float(box["y"]) - float(box["h"]) * pad),
        "w": min(1.0, float(box["w"]) * (1 + 2 * pad)),
        "h": min(1.0, float(box["h"]) * (1 + 2 * pad)),
    }
    return [it for it in out if _overlap_ratio(it["bbox"], region) >= min_cover]
