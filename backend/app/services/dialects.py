"""模型方言层（源码级借鉴 Toonflow providerPrompt / huobao video-prompts）。

同一个镜头，不同视频模型吃的提示词"方言"不一样：时长上限、是否认负面词、
是否认首尾帧、是否认多参考图、对运镜措辞的偏好。模板产出的是"内容层"，
这里再按目标模型包一层"模型层"，避免一套词喂所有模型。

已内置三族（都是本地/离线可跑的）：
- wan22：Wan2.2 i2v，英文、单镜连续、最多 5s（81 帧@16fps）、无内建负面词（靠模板 negative）
- minimax_h3：Hailuo/MiniMax H3 参考链，认运镜短语，最长 10s
- seedance：Seedance 系，吃"镜头/节拍"结构，最多 15s
- generic：兜底，只做长度与格式规整
"""
from __future__ import annotations

MAX_SECONDS = {"wan22": 5, "minimax_h3": 10, "seedance": 15, "generic": 10}

# 每族惯用运镜措辞（同样的意图，换模型要换词）
CAMERA_WORDS = {
    "wan22": {"push": "dolly in", "pull": "dolly out", "pan": "pan", "orbit": "orbit"},
    "minimax_h3": {"push": "camera pushes in", "pull": "camera pulls back",
                   "pan": "camera pans", "orbit": "camera circles around"},
    "seedance": {"push": "push-in shot", "pull": "pull-out shot", "pan": "panning shot",
                 "orbit": "orbit shot"},
    "generic": {"push": "push in", "pull": "pull back", "pan": "pan", "orbit": "orbit"},
}

TAIL = {
    "wan22": ("single continuous take, no cuts, consistent identity and wardrobe, "
              "natural motion, stable framing"),
    "minimax_h3": ("one continuous shot, stable camera, no scene change, "
                   "keep character identity and costume consistent"),
    "seedance": ("single shot, continuous action, consistent character identity"),
    "generic": ("single continuous shot, consistent character"),
}


def clamp_duration(seconds: float, family: str) -> int:
    cap = MAX_SECONDS.get(family, 10)
    try:
        v = int(round(float(seconds)))
    except Exception:
        v = cap
    return max(1, min(cap, v))


def wrap_video_prompt(prompt: str, family: str, seconds: float,
                      has_end_frame: bool = False) -> str:
    """在内容层提示词外面包一层模型方言：时长收敛 + 术语替换 + 收尾约束。"""
    p = (prompt or "").strip()
    cap = clamp_duration(seconds, family)
    if has_end_frame:
        p = p.replace("dolly in", CAMERA_WORDS[family]["push"])
        p = p.replace("dolly out", CAMERA_WORDS[family]["pull"])
    tail = TAIL.get(family, TAIL["generic"])
    prefix = ""
    if family == "seedance":
        prefix = f"[{cap}s] "
    return ", ".join(x for x in (prefix + p if prefix else p, tail) if x)


def negative_for(family: str, base: str = "") -> str:
    """方言层负面词：wan 系不认自然语言负面，尽量短标签；seedance 认句子。"""
    if family in ("wan22", "minimax_h3"):
        core = "static, blurry, watermark, text, deformed limbs, flicker, jump cut"
        return ", ".join(x for x in (core, base) if x)
    return base
