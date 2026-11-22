"""模型提示词库（#73）：提示词生成前预判下游模型，按该模型听得懂的方言组词。

与 dialects.py 的分工（双层防御）：
- dialects.py = 生成期兜底：运行时才知道最终模型 → 包一层（时长收敛/负面词/收尾约束）
- model_vocab.py = 组装期方言：拆解/重组装时就按预判的下游模型组词，
  让提示词从出生就长在该模型的"母语"里，而不是生成时再包一层补丁

模型习惯差异依据（实测 + 模型架构常识）：
- sdxl：双 CLIP 编码器，训练语料 tag 式；超过 ~75 token 的长自然语言句后半段被稀释
  → 偏好短标签链，构图/画质类词用逗号标签而不是从句
- flux2_klein：多模态文本编码器，自然语言/空间关系/实物理解强（实测纸条文字一次成立）
  → 偏好自然语言描述，物理常识词有效；tag 堆砌无益
- qwen_image：中英双语强，文字渲染强（三视图信息栏"姓名/身高小字"受益）
  → 布局/文字类指令可直接写，加"可读文字渲染"token
- wan 系（umt5 编码器，2.1/2.2 同族方言）：动作分解式短语（逗号分隔的时序动作）
  优于文学化长句；"single continuous take"防多镜头拼接；认短标签负面词
- infinitalk：口型跟音频驱动，提示词只管表演状态；大动作词（走动/转身）
  会和口型约束打架 → 注入"微动作+口型同步"词，负面挡大动作
"""
from __future__ import annotations

# ---------- 预判：这条提示词将来喂给哪个模型 ----------

def predict_image_family(role: str, style_family: str = "",
                         portrait_mode: str = "") -> str:
    """镜像 asset_service.pick_model 的选模规则（纯规则、零 LLM、零 IO）：
    - 三视图 sheet → qwen_image（#55 全量走 Qwen-Image）
    - 场景/道具 photo 族 → flux2_klein（#28 实物理解）
    - 其余（分镜首尾帧/角色板/非 photo 资产）→ sdxl（IPA 锁脸链路依赖）"""
    if role == "portrait" and portrait_mode == "sheet":
        return "qwen_image"
    if role in ("scene", "prop") and style_family == "photo":
        return "flux2_klein"
    return "sdxl"


def predict_video_family(model_key: str | None = None) -> str:
    """视频提示词组装期预判：默认 vid_wan21_480p（wan 系）；
    InfiniteTalk 说话镜按 model_key 特判（生成期已硬编码 vid_talk_infinitetalk）。"""
    if model_key and "talk" in model_key:
        return "infinitalk"
    return "wan"


# ---------- 方言词库：每族的正向附加词（负面词基础 NEGATIVE 已覆盖，不重复加） ----------

MODEL_PROMPT_VOCAB = {
    # 图像族（组装期用于首帧/尾帧/关键帧 + 资产生成）
    "sdxl": {
        "image": "sharp focus, coherent composition, clean edges",
        "negative": "",   # 基础 NEGATIVE 已含 jpeg artifacts/worst quality
    },
    "flux2_klein": {
        "image": "physically accurate materials, true-to-life proportions",
        "negative": "",   # flux2 对 CFG 负面词响应弱，堆词无益
    },
    "qwen_image": {
        "image": "crisp legible text rendering, precise layout following",
        "negative": "",
    },
    # 视频族（组装期用于 video_prompt）
    "wan": {
        "video": ("smooth continuous motion, natural physics, "
                  "actions unfold step by step"),
        "negative": "static, flicker, jump cut",   # dialects.negative_for 已有同源词，此处供组装层引用
    },
    "infinitalk": {
        "video": ("talking naturally, lip movements match speech, "
                  "subtle head movements, expressive facial micro-expressions"),
        "negative": "large body movement, walking, turning away",
    },
}


def model_tokens(family: str, kind: str) -> str:
    return MODEL_PROMPT_VOCAB.get(family, {}).get(kind, "")


def model_negative(family: str, kind: str) -> str:
    return MODEL_PROMPT_VOCAB.get(family, {}).get("negative", "")


def image_dialect(family: str) -> str:
    """资产生成（family 在手）直接取图像方言正向词。"""
    return model_tokens(family, "image")
