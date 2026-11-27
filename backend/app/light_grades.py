"""光影 / 色彩滤镜预设（对齐 RunningHub RHTV 图片 / 视频节点底部的预设条）。

RHTV 的做法是把"打光 + 调色"这类最难用文字描述的活儿做成可点的预设，
点完自动带出一串专业光影参数，保证一串镜头视觉风格一致。

这里的落地前提（用户明确要求）：**不消耗任何 token、不调云端资源**。
所以没有走"云端滤镜 API / LUT 上传"那套，而是：
  · 每个预设 = 一组写在提示词里的英文光影/色彩词块（本地底模听得懂的"光源+方向+
    色温+对比+调色"描述）；
  · 点选即写库字段 → 零 LLM 整集重组装（和导演台同一套链路），不重新拆解；
  · 生成仍走本地 Qwen-Image / SDXL / MiniMax H3，不产生任何 API 调用。

三级作用域（越靠内越优先）：
  shot.light_grade（单镜覆盖） >  project.light_grade（全片默认） >  ""（自动，按 tod/light 走）

只进图片侧提示词（首帧 / 尾帧 / 关键帧）：视频由首帧承载画面，
I2V 提示词里塞调色词会让 H3 每帧重新"想"颜色，反而闪烁。
"""
from __future__ import annotations

# group 只用于前端分组展示；tokens 是真正进提示词的部分。
LIGHT_GRADES = [
    # ---------- 光线 ----------
    {"v": "golden_hour", "zh": "黄金时刻", "group": "光线",
     "hint": "低角度暖阳、长影、皮肤暖金——情绪上扬、回忆感",
     "tokens": "warm golden hour sunlight, low sun angle, long soft shadows, "
               "amber rim light on hair and shoulders, honey-toned highlights"},
    {"v": "blue_hour", "zh": "蓝调时刻", "group": "光线",
     "hint": "暮色冷蓝 + 远处暖灯点，安静、离别、悬而未决",
     "tokens": "blue hour twilight, deep cool blue ambient light, distant warm lamps "
               "as tiny highlights, low contrast shadows, melancholic mood"},
    {"v": "overcast", "zh": "阴天柔光", "group": "光线",
     "hint": "无直射光、几乎无影、灰蓝低对比——压抑、写实",
     "tokens": "overcast diffuse daylight, no direct sun, very soft shadowless light, "
               "grey-blue desaturated palette, muted contrast"},
    {"v": "candle", "zh": "烛火暖光", "group": "光线",
     "hint": "橙黄跳动光源贴脸、暗部极深——密室、密谋、温情",
     "tokens": "candlelight illumination, flickering warm orange source near the face, "
               "deep dark falloff, warm skin tones against near-black background"},
    {"v": "moonlight", "zh": "月光冷调", "group": "光线",
     "hint": "青蓝月光、硬边阴影——夜行、清冷、仙侠",
     "tokens": "cool moonlight, cyan-blue directional light from upper left, "
               "hard-edged shadows, silver highlights, night atmosphere"},
    {"v": "neon", "zh": "霓虹夜", "group": "光线",
     "hint": "品红/青色霓虹、湿地反光——赛博、都市、夜店",
     "tokens": "neon night lighting, magenta and cyan rim lights, wet reflective surfaces, "
               "colorful light streaks, high contrast night scene"},
    {"v": "hardnoon", "zh": "正午硬光", "group": "光线",
     "hint": "顶光直打、短硬影、高对比——焦灼、对峙、荒原",
     "tokens": "harsh midday sun overhead, hard short shadows under nose and chin, "
               "high contrast, blown warm highlights, dusty air"},
    {"v": "softbox", "zh": "柔光棚拍", "group": "光线",
     "hint": "均匀柔光、干净无影——产品感、亮相、审美优先",
     "tokens": "soft studio softbox lighting, even wrap-around light, clean shadowless "
               "background, gentle specular highlights, commercial look"},
    {"v": "backlight", "zh": "逆光剪影", "group": "光线",
     "hint": "强逆光成剪影 + 轮廓光 + 雾气——神秘、登场、史诗",
     "tokens": "strong backlight, subject as dark silhouette rimmed by glowing edge light, "
               "volumetric haze, sun flare, dramatic reversed contrast"},
    {"v": "underlight", "zh": "底光诡异", "group": "光线",
     "hint": "光从下方打、面部阴影反转——恐怖、反派、压迫",
     "tokens": "low-key underlighting from below the face, inverted facial shadows, "
               "sickly cool green tint, deep black background, unsettling mood"},
    {"v": "window_beam", "zh": "窗棂光柱", "group": "光线",
     "hint": "斜射光柱 + 尘埃 + 条纹影——古宅、静室、时间感",
     "tokens": "diagonal window light beam, visible dust motes in the shaft, "
               "barred shadow pattern across the floor and wall, warm afternoon tone"},
    {"v": "fog", "zh": "薄雾漫射", "group": "光线",
     "hint": "雾气 + 光晕 + 空气透视——山野、清晨、空灵",
     "tokens": "thin mist, volumetric light scattering, glowing halation around light sources, "
               "aerial perspective with pale distant layers, ethereal mood"},

    # ---------- 色彩 ----------
    {"v": "teal_orange", "zh": "青橙电影调", "group": "色彩",
     "hint": "暗部压青、肤色压橙——大片标配，冷暖对撞",
     "tokens": "teal and orange color grading, cyan-shifted shadows, warm orange skin tones, "
               "cinematic color contrast, filmic rolloff"},
    {"v": "bleach", "zh": "漂白高对比", "group": "色彩",
     "hint": "低饱和 + 抬黑 + 强对比——战争、纪实、冷硬",
     "tokens": "bleach bypass look, desaturated colors, crushed blacks, high contrast, "
               "gritty textured highlights, harsh realistic tone"},
    {"v": "film_low", "zh": "胶片低饱和", "group": "色彩",
     "hint": "柔和高光 + 轻颗粒 + 低饱和——文艺、回忆、生活流",
     "tokens": "muted film stock colors, soft rolled-off highlights, subtle grain, "
               "slightly faded blacks, nostalgic analog color science"},
    {"v": "vivid", "zh": "国潮高饱和", "group": "色彩",
     "hint": "高饱和朱红/金/翠 + 清透高光——喜庆、燃、宣传感",
     "tokens": "vivid saturated palette, rich vermilion red and gold accents, "
               "jade green touches, crisp clean highlights, poster-like color punch"},
    {"v": "bw", "zh": "黑白水墨", "group": "色彩",
     "hint": "纯单色 + 强明暗层次——庄重、回忆、风格化",
     "tokens": "black and white monochrome, strong tonal separation, ink-wash gradation, "
               "deep blacks and clean whites, no color at all"},
    {"v": "pastel", "zh": "奶油柔粉", "group": "色彩",
     "hint": "低对比粉调 + 柔光——甜宠、少女、日常",
     "tokens": "creamy pastel palette, soft pink and peach tones, lifted shadows, "
               "low contrast, dreamy gentle highlights"},
]

GRADE_BY_KEY = {g["v"]: g for g in LIGHT_GRADES}
GROUPS = ["光线", "色彩"]

# 短版词（分镜首帧/尾帧模板只给光位 ~12 词预算，见 prompt_templates.shot_first_frame）。
# 长版 tokens 有 8-14 词，整段塞进短模板会把 77 token 预算挤爆、画面内容反而丢，
# 所以每条另备 3-5 词的高信息量版本：只保留"什么光 + 什么调"。
SHORT = {
    "golden_hour": "golden hour warm light",
    "blue_hour": "blue hour cool ambient",
    "overcast": "overcast flat soft light",
    "candle": "candlelit warm glow",
    "moonlight": "cool moonlight silver rim",
    "neon": "neon magenta cyan",
    "hardnoon": "harsh overhead sun",
    "softbox": "soft even studio light",
    "backlight": "backlit silhouette glowing rim",
    "underlight": "underlight sickly green",
    "window_beam": "diagonal window light beam",
    "fog": "thin mist volumetric glow",
    "teal_orange": "teal shadows warm orange",
    "bleach": "bleach bypass crushed blacks",
    "film_low": "muted film grain",
    "vivid": "vivid red gold saturated",
    "bw": "black and white monochrome",
    "pastel": "creamy pastel pink",
}


def grade_tokens(key: str) -> str:
    """取预设的提示词词块（未知 key 返回空串，绝不猜）。"""
    g = GRADE_BY_KEY.get((key or "").strip())
    return g["tokens"] if g else ""


def grade_short(key: str) -> str:
    """取短版词块（分镜短模板用）。"""
    return SHORT.get((key or "").strip(), "")


def meta() -> dict:
    """前端渲染用：预设 + 分组（结构对齐 director.meta 的其它组）。"""
    return {"light_grades": LIGHT_GRADES, "light_grade_groups": GROUPS}


def apply_grade(light_text: str, grade_key: str) -> str:
    """把光影预设词块并进已有 light 描述（已有内容保留在前，预设补在后面）。

    设计取舍：预设不是"覆盖"导演写的具体光位，而是补足色温/对比/调色层。
    已有 light 里若已写了同一件事（如 "golden hour"），仍然拼上去——同一个词重复
    一次在 CLIP 里只是轻微加权，不会把画面带偏，反而更稳。
    """
    tok = grade_tokens(grade_key)
    base = (light_text or "").strip().rstrip(",.")
    if not tok:
        return base
    return f"{base}, {tok}" if base else tok
