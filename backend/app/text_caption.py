"""Ideogram 4 结构化 caption 构建（纯本地规则，不调 LLM、不碰云端）。

实测结论（2026-11-28，本机 8G 卡，ideogram4 fp8 双模型 + qwen3vl_8b int8 编码器）：
Ideogram 4 的权重是**按 structured JSON caption 训练的**。喂自然语言 prompt（哪怕只有
"a red apple on a wooden table"）会稳定输出灰底占位图「Image blocked by safety filter」；
换成官方 caption 结构立刻正常出图，英文文字（"QING YUN SECT TOKEN"）逐字母准确、
浮雕质感和载体材质都跟得住。bf16 / int8 编码器结果一致，所以这与编码器无关，是
prompt 形态问题——英文文字档必须走 JSON caption。

caption 结构（与 KJNodes 的 Ideogram4PromptBuilderKJ 输出完全一致）：

    {
      "high_level_description": "...",
      "style_description": {"aesthetics": ..., "lighting": ..., "photo": ...},
      "compositional_deconstruction": {
        "background": "...",
        "elements": [
          {"type": "obj",  "bbox": [ymin, xmin, ymax, xmax], "desc": "..."},
          {"type": "text", "bbox": [...], "text": "要写的英文原文", "desc": "..."}
        ]
      }
    }

bbox 用 0-1000 归一网格，轴向是 Ideogram 的 [ymin, xmin, ymax, xmax]。

两条硬经验（各踩过一次）：
1) obj 的 desc 里**不能**再出现要写的字。槽位 details 里常见的
   "carved capital letters QING YUN SECT TOKEN" 会让模型把文字画两遍（重叠错位）。
2) obj 的 desc 要短、只写主体/材质/环境。风格词、剧情词、"story function" 这类
   长句会把构图顶歪（实测塞满风格词后木牌被画成 45° 侧立、文字被裁）。
"""
from __future__ import annotations

import json
import re


def _strip_text(token: str, s: str) -> str:
    """把"要写的字"从描述里剔掉，避免模型重复画第二遍文字。"""
    if not token or not s:
        return s
    token = token.strip()
    # 连同紧挨着的前缀词（carved capital letters / reading / the text …）一起删，
    # 避免剩下半句像 "carved capital," 这样的残词继续暗示"要刻字"
    prefix = (r"(?:\s*(?:reading|reads|saying|says|carved|engraved|printed|written|"
              r"lettered|capital|text|letters?|characters?|the words|the text))*")
    pat = re.compile(r"[,，]?\s*" + prefix + r"\s*" + re.escape(token), re.IGNORECASE)
    return pat.sub("", s)


def _clean(parts: list[str]) -> str:
    segs = []
    for p in parts:
        for s in str(p or "").split(","):
            s = s.strip(" .，、")
            if s and s not in segs:
                segs.append(s)
    # 压到 ~180 字符，caption 越长文字版式的预算越紧
    out, total = [], 0
    for s in segs:
        if total + len(s) > 180:
            break
        out.append(s)
        total += len(s) + 2
    return ", ".join(out)


def build_caption(subject: str, surface: str, width: int, height: int,
                  details: str = "", material: str = "", era: str = "",
                  aesthetics: str = "") -> str:
    """道具槽位 + 要写的英文文字 → Ideogram 4 caption 字符串（compact JSON）。"""
    subject = (subject or "").strip()
    details = _strip_text(surface, (details or "").strip())
    obj_desc = _clean([subject, era, material, details])
    if not obj_desc:
        obj_desc = "the prop itself"
    obj_desc += ", no lettering on the object other than the specified text"

    if int(height) >= int(width):
        # 竖版画幅：文字区给成**宽块**（横向单词逐行堆叠）。踩过坑：窄高块会被理解成
        # 单列竖排长串，"QING YUN SECT TOKEN" 一行塞不下 → 掉字母（SEC/KEN）并混入中文伪字
        text_box = [300, 230, 620, 770]
        rows = ("bold carved capital letters, four stacked horizontal lines, one word per line, "
                "high contrast, large and perfectly legible, spelled exactly as given")
    else:
        # 横版画幅：宽扁块（自左向右横排，匾额/横幅适用）
        text_box = [360, 200, 640, 800]
        rows = ("bold carved capital letters, horizontal line, high contrast, "
                "large and perfectly legible, spelled exactly as given")

    caption = {
        "high_level_description": (f"front-facing product photo of {obj_desc.split(',')[0]}, "
                                   "single object, centered, straight-on view"),
        "style_description": {
            "aesthetics": aesthetics or "clean commercial product shot, realistic materials",
            "lighting": "soft even studio light, no harsh shadows",
            "photo": "85mm, f/4, sharp focus on the object",
        },
        "compositional_deconstruction": {
            "background": "plain uncluttered studio backdrop matching the object, no lettering",
            "elements": [
                {"type": "obj", "bbox": [60, 60, 940, 940], "desc": obj_desc},
                {"type": "text", "bbox": text_box, "text": surface,
                 "desc": (rows + ", the only text on the object, "
                          "no other characters of any other language")},
            ],
        },
    }
    return json.dumps(caption, ensure_ascii=False, separators=(",", ":"))
