"""模型提示词库（#73 建，#90 升级）：提示词生成前预判下游模型，按该模型听得懂的方言组词。

与 dialects.py 的分工（双层防御）：
- dialects.py = 生成期兜底：运行时才知道最终模型 → 包一层（时长收敛/负面词/收尾约束）
- model_vocab.py = 组装期方言：拆解/重组装时就按预判的下游模型组词，
  让提示词从出生就长在该模型的"母语"里，而不是生成时再包一层补丁
- prompt_bank.py = 自强化层（#90）：固定方言 + 按 kept/failed 统计动态排序的学习词块，
  两层在 model_tokens() 里融合——拆解出生的提示词自带经过实战验证的词块

模型习惯差异依据（实测 + 模型架构常识）：
- sdxl：双 CLIP 编码器，训练语料 tag 式；超过 ~75 token 的长自然语言句后半段被稀释
  → 偏好短标签链，构图/画质类词用逗号标签而不是从句（分镜首尾帧/宫格 IPA 链路专用）
- flux2_klein：多模态文本编码器，自然语言/空间关系/实物理解强（实测纸条文字一次成立）
  → 偏好自然语言描述，物理常识词有效；tag 堆砌无益（现为辅助通道）
- qwen_image：中英双语强，自然语言长描述优于 tag 堆砌，文字渲染强（三视图信息栏、
  UI 面板中文小字受益）→ #87 全局图片默认档，布局/文字类指令可直接写
- minimax_h3：qwen3vl 文本编码器，认运镜短语与动作分解式短语；BasicGuider cfg=1
  无负面输入——否定句无效（#84 教训同源），词库一律正向表述；原生音频生成，
  氛围音可写进提示词 → #87 全局视频默认档
- infinitalk：口型跟音频驱动，提示词只管表演状态；大动作词（走动/转身）
  会和口型约束打架 → 注入"微动作+口型同步"词，负面挡大动作
"""
from __future__ import annotations

# ---------- 预判：这条提示词将来喂给哪个模型 ----------

def predict_image_family(role: str, style_family: str = "",
                         portrait_mode: str = "") -> str:
    """镜像 asset_service 选模规则（#87 后 defaults.default_models 四角色全走 qwen_image）：
    - 三视图 sheet / 场景 / 道具（photo、3d 等任意风格族）→ qwen_image
    - 分镜首尾帧/宫格 → sdxl（IPA 锁脸链路依赖，显式 prefer 锁定，不受全局默认影响）"""
    if role == "portrait" and portrait_mode == "sheet":
        return "qwen_image"
    if role in ("scene", "prop"):
        return "qwen_image"
    return "sdxl"


def predict_video_family(model_key: str | None = None) -> str:
    """视频提示词组装期预判：#87 后全局默认 vid_h3_int8/vid_h3_turbo → minimax_h3；
    InfiniteTalk 说话镜按 model_key 特判（生成期已硬编码 vid_talk_infinitetalk）。"""
    if model_key and "talk" in model_key:
        return "infinitalk"
    return "minimax_h3"


# ---------- 方言词库：每族的正向附加词（负面词基础 NEGATIVE 已覆盖，不重复加） ----------
# H3 注意：cfg=1 无负面通道 → negative 一律留空且禁止写否定句进提示词

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
        # 自然语言长描述：主体→环境→构图→光线→材质→氛围 分层递进（不写 tag 堆砌）
        # 文字渲染类需求显式下指令（"信息栏小字"实测受益）；无负面通道依赖，负面词留基础链
        "image": ("crisp legible text rendering, precise layout following, "
                  "coherent natural-language scene description"),
        "negative": "",
    },
    # 视频族（组装期用于 video_prompt）
    "minimax_h3": {
        # H3 i2v：首帧已定主体/风格 → 提示词只管运动+镜头+氛围音；
        # 认运镜短语（camera pushes in 等）；动作分解式；音频描述可直接写
        "video": ("single continuous shot, smooth natural motion, "
                  "camera motion serves the action, "
                  "ambient sound matches the scene atmosphere"),
        "negative": "",   # cfg=1 无负面输入，否定句无效
    },
    "wan": {
        # 官方 I2V 公式：图已定主体/场景/风格 → 提示词只描述运动+镜头；
        # 一个片段一个动作（多动作必 morphing）；描述结果而非命令。
        "video": ("smooth continuous motion, natural physics, "
                  "actions unfold step by step, one clear action per clip"),
        "negative": "static, flicker, jump cut",   # dialects.negative_for 已有同源词，此处供组装层引用
    },
    "infinitalk": {
        "video": ("talking naturally, lip movements match speech, "
                  "subtle head movements, expressive facial micro-expressions"),
        "negative": "large body movement, walking, turning away",
    },
}


def model_tokens(family: str, kind: str) -> str:
    """固定方言 + 自强化词块（prompt_bank 按 kept/failed 动态排序）融合。
    bank 层损坏/为空时退化为纯固定方言——组装零风险。"""
    fixed = MODEL_PROMPT_VOCAB.get(family, {}).get(kind, "")
    try:
        from .prompt_bank import bank_tokens
        learned = bank_tokens(family, kind)
    except Exception:
        learned = ""
    return ", ".join(x for x in (fixed, learned) if x)


def model_negative(family: str, kind: str) -> str:
    return MODEL_PROMPT_VOCAB.get(family, {}).get("negative", "")


def image_dialect(family: str, role: str = "") -> str:
    """资产生成（family 在手）直接取图像方言正向词。
    Qwen 的"文字渲染/版式跟随"指令只给角色板/道具（有信息栏小字、券面文字）——
    场景图不需要文字，带上反而诱导画面冒出乱码小字（实测污染）。"""
    s = model_tokens(family, "image")
    if family == "qwen_image" and role == "scene":
        s = s.replace("crisp legible text rendering, precise layout following, ", "")
        s = s.replace("crisp legible text rendering, precise layout following", "")
    return s.strip(" ,")
