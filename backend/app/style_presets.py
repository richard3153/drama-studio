"""项目级风格预设（分类组织，覆盖动漫/国风/摄影写实/插画/复古等）。
词源：方法论第三、四章 + 网络风格词库整理（AI 短剧常用画风全谱）。
每个预设：style_lock 注入所有提示词头部；motion_hint 供视频提示词参考；category 用于前端分组。"""
import re

STYLE_PRESETS = {
    # ---------- 动漫 / 卡通 ----------
    "anime_2d": {
        "category": "动漫卡通", "label": "二次元动漫",
        "style_lock": ("2D anime style, cel shading, clean sharp lineart, flat colors, "
                       "hard-edged shadows, expressive detailed eyes"),
        "motion_hint": "局部动态（头发飘动、衣角翻飞、眼神光），避免大幅全身运动",
    },
    "anime_soft": {
        "category": "动漫卡通", "label": "日系软萌动画",
        "style_lock": ("soft anime style, pastel color palette, gentle gradient shading, "
                       "rounded shapes, warm dreamy lighting"),
        "motion_hint": "软性微动态（呼吸、眨眼、发梢摆动），治愈节奏",
    },
    "ghibli": {
        "category": "动漫卡通", "label": "吉卜力手绘",
        "style_lock": ("Ghibli style hand-drawn animation, watercolor texture, soft warm palette, "
                       "dappled natural light, airy atmosphere"),
        "motion_hint": "风的流动、云的移动、光线缓变，节奏舒缓",
    },
    "manga_bw": {
        "category": "动漫卡通", "label": "黑白漫画",
        "style_lock": ("black and white manga style, bold ink linework, screentone shading, "
                       "high contrast, dramatic speed lines"),
        "motion_hint": "速度线、集中线强化动作，黑白对比切换",
    },
    "korean_webtoon": {
        "category": "动漫卡通", "label": "韩漫条漫",
        "style_lock": ("korean webtoon style, tall elegant figures, smooth clean lines, "
                       "porcelain skin, soft gradient coloring, glossy highlights"),
        "motion_hint": "都市恋爱感微动态（发丝光、侧脸转动、牵手特写）",
    },
    "american_comic": {
        "category": "动漫卡通", "label": "美漫英雄",
        "style_lock": ("american comic book style, bold inked linework, halftone dots, "
                       "dramatic lighting, exaggerated muscle structure, vibrant color grading"),
        "motion_hint": "强冲击动作（挥拳、跳跃、爆炸），分镜冲击感",
    },
    "chibi_q": {
        "category": "动漫卡通", "label": "Q版萌系",
        "style_lock": ("chibi style, big head small body, super deformed proportions, "
                       "kawaii rounded shapes, bright saturated colors, simple thick outlines"),
        "motion_hint": "夸张弹性小动作（跳跃、歪头、摆手），表情包式表演",
    },
    "disney_2d": {
        "category": "动漫卡通", "label": "迪士尼2D",
        "style_lock": ("Disney classic 2D animation style, smooth ink outlines, warm soft shading, "
                       "expressive eyes, storybook feel, musical-film color"),
        "motion_hint": "歌舞化肢体表演，弹性预备动作",
    },
    "pixar_3d": {
        "category": "动漫卡通", "label": "皮克斯3D",
        "style_lock": ("Pixar style 3D render, soft global illumination, exaggerated appealing shapes, "
                       "vivid colors, subsurface skin scattering"),
        "motion_hint": "弹性动画（预备动作、挤压拉伸），符合动画十二法则",
    },
    "guofeng_3d": {
        "category": "动漫卡通", "label": "3D国风动画",
        "style_lock": ("3D chinese animation style, oriental stylized characters, smooth glossy skin, "
                       "flowing ornate hanfu cloth simulation, glowing vfx, cinematic bloom"),
        "motion_hint": "衣袂飘飞、法术光效、发丝物理飘动",
    },
    # ---------- 国风 / 东方 ----------
    "guofeng_ink": {
        "category": "国风东方", "label": "水墨国风",
        "style_lock": ("Chinese ink painting style, xuan paper texture, ink wash gradients, "
                       "flying white brushwork, vast negative space"),
        "motion_hint": "泼墨气势、云雾流动，意境大于写实",
    },
    "gongbi": {
        "category": "国风东方", "label": "工笔重彩",
        "style_lock": ("chinese gongbi painting style, meticulous fine brushwork, mineral pigment "
                       "colors, silk scroll texture, elegant outlined details"),
        "motion_hint": "静态端庄、衣纹缓动，卷轴式场景推移",
    },
    "xianxia": {
        "category": "国风东方", "label": "古风仙侠",
        "style_lock": ("chinese xianxia fantasy style, sea of clouds and celestial mountains, "
                       "flowing immortal robes, glowing spiritual artifacts, ethereal bloom light"),
        "motion_hint": "御剑飞行、法术灵光、云海翻涌",
    },
    "guochao": {
        "category": "国风东方", "label": "国潮插画",
        "style_lock": ("chinese neo-traditional illustration, auspicious cloud and dragon motifs, "
                       "high saturation clashing colors, bold graphic shapes, modern poster design"),
        "motion_hint": "图形化平面动效（色块平移、纹样旋转）",
    },
    "ukiyoe": {
        "category": "国风东方", "label": "浮世绘",
        "style_lock": ("ukiyo-e woodblock print style, flat color planes, bold outlines, "
                       "wave and cloud patterns, aged paper texture, limited palette"),
        "motion_hint": "平面浪纹滚动、服饰图案流动",
    },
    # ---------- 摄影 / 写实 ----------
    "photoreal": {
        "category": "摄影写实", "label": "写实人像写真",
        "style_lock": ("photorealistic portrait photography, 85mm lens, shallow depth of field, "
                       "natural skin texture and pores, realistic hair strands, softbox lighting, "
                       "raw photo, film grain"),
        "motion_hint": "真实微表情与呼吸感，浅景深焦点转移",
    },
    "cinematic_film": {
        "category": "摄影写实", "label": "电影写实",
        "style_lock": ("cinematic film still, movie-grade lighting, anamorphic lens flare, "
                       "teal-orange color grading, dramatic rim light, 2.39:1 widescreen feel, "
                       "photorealistic detail"),
        "motion_hint": "电影运镜（推拉摇移）、光影氛围变化",
    },
    "hk_retro": {
        "category": "摄影写实", "label": "港风复古",
        "style_lock": ("1990s hong kong film style, retro film grain, faded warm tones, "
                       "green-yellow shadows, saturated reds, neon signs, nostalgic glamour"),
        "motion_hint": "胶片质感慢摇镜头、霓虹闪烁、雨夜反光",
    },
    "film_noir": {
        "category": "摄影写实", "label": "黑色电影",
        "style_lock": ("film noir, black and white, extreme chiaroscuro, venetian blind shadows, "
                       "high contrast, smoke haze, 1940s detective mood"),
        "motion_hint": "光影切割、烟雾流动、慢速追随镜头",
    },
    "jp_fresh": {
        "category": "摄影写实", "label": "日系清新",
        "style_lock": ("japanese fresh style photography, high brightness low contrast, "
                       "slightly cyan-green tint, transparent whites, airy backlit haze, "
                       "light film grain, healing mood"),
        "motion_hint": "逆光发丝光、慢门柔动、生活化小动作",
    },
    "fashion_edito": {
        "category": "摄影写实", "label": "时尚杂志大片",
        "style_lock": ("high fashion editorial photography, studio dramatic lighting, "
                       "glossy magazine retouch, bold styling, clean background, "
                       "confident posing, luxury color grading"),
        "motion_hint": "镜头围绕主体旋转、服装摆动、定点换姿",
    },
    "documentary": {
        "category": "摄影写实", "label": "纪实抓拍",
        "style_lock": ("documentary photography, candid unposed moments, natural available light, "
                       "photojournalism grain, authentic imperfections, muted color palette"),
        "motion_hint": "手持晃动跟拍、自然事件流",
    },
    # ---------- 插画 / 数字艺术 ----------
    "thick_paint": {
        "category": "插画数字", "label": "厚涂插画",
        "style_lock": ("digital thick painting style, visible brush strokes, canvas texture, "
                       "realistic soft lighting, rich color layers"),
        "motion_hint": "微动态（烛火摇曳、尘埃浮动、呼吸起伏），避免剧烈动作",
    },
    "watercolor": {
        "category": "插画数字", "label": "水彩绘本",
        "style_lock": ("children book watercolor illustration, soft wet-on-wet bleeds, "
                       "paper texture showing through, gentle pastel palette, handcrafted warmth"),
        "motion_hint": "水痕晕开、纸面平移、轻盈飘动",
    },
    "oil_painting": {
        "category": "插画数字", "label": "古典油画",
        "style_lock": ("classical oil painting, impasto brushwork, chiaroscuro lighting, "
                       "varnished canvas texture, old master composition, rich earthy palette"),
        "motion_hint": "光如烛火的缓变、庄重慢节奏",
    },
    "flat_vector": {
        "category": "插画数字", "label": "扁平插画",
        "style_lock": ("flat vector illustration, clean geometric shapes, solid color fills, "
                       "minimal shading, consistent stroke width, limited palette, modern infographic look"),
        "motion_hint": "图形化转场（色块滑入、图标动效）",
    },
    "game_cg": {
        "category": "插画数字", "label": "游戏CG",
        "style_lock": ("game CG style, unreal engine 5 render, photorealistic materials, "
                       "cinematic lighting, ray tracing"),
        "motion_hint": "剧烈环境互动、爆炸烟尘、动态模糊",
    },
    "fantasy_art": {
        "category": "插画数字", "label": "奇幻概念",
        "style_lock": ("epic fantasy concept art, volumetric god rays, intricate ornament design, "
                       "matte painting depth, dramatic scale contrast, artstation quality"),
        "motion_hint": "宏大场景运镜（升降、飞掠）、粒子特效",
    },
    # ---------- 复古 / 未来 ----------
    "cyberpunk": {
        "category": "复古未来", "label": "赛博朋克",
        "style_lock": ("cyberpunk style, neon lighting, cyan-magenta contrast, metallic textures, "
                       "rain-slick reflections, holographic signage, high contrast"),
        "motion_hint": "霓虹闪烁、数据流、雨夜反光",
    },
    "steampunk": {
        "category": "复古未来", "label": "蒸汽朋克",
        "style_lock": ("steampunk style, victorian machinery, brass gears and copper pipes, "
                       "leather and rivets, steam clouds, sepia warm palette"),
        "motion_hint": "齿轮转动、蒸汽喷发、机械缓动",
    },
    "synthwave": {
        "category": "复古未来", "label": "复古合成波",
        "style_lock": ("synthwave retro-futurism, neon sunset gradient, chrome grid horizon, "
                       "80s aesthetic, hot pink and electric blue, VHS scanlines"),
        "motion_hint": "网格地平线滚动、霓虹扫光、VHS 抖动",
    },
    "pixel_art": {
        "category": "复古未来", "label": "像素复古",
        "style_lock": ("16-bit pixel art, chunky visible pixels, limited color palette, "
                       "dithered shading, retro game sprite look"),
        "motion_hint": "逐帧跳切动作、屏幕滚动，游戏化运镜",
    },
    "low_poly": {
        "category": "复古未来", "label": "低多边形",
        "style_lock": ("low poly 3D art, faceted geometric shapes, flat vibrant colors, "
                       "isometric view, clean minimal composition"),
        "motion_hint": "等距视角平移、几何体缓旋",
    },
}

DEFAULT_PRESET = "anime_2d"

# ---------- 画面规格（第二章/第四章 + 参考图角色板） ----------

# 三视图（2026-11-21 定稿版式，用户指定）：宽横幅一体成图 ——
# 左半：面部近景大特写（五官细节+微表情）；右半：全身正/侧/背三视图从左到右并排；
# 底部：窄信息栏（小字姓名+身高+关键配色色块）。固定横版 16:9（1344x768）出图。
# 旧版只写 "three views plus face close-up"，底模画成服装陈列板/肢体拼贴（实测两例崩坏），
# 必须把"同一个人物、每个视图全身、版式分区、信息栏"全部写死。
CHAR_SHEET_SPEC = ("character model sheet of ONE single character on a wide horizontal canvas: "
                   "left half of the canvas = one large face close-up portrait showing facial "
                   "features and subtle expression in detail; right half = three full-body views "
                   "of the SAME character standing side by side from left to right (front view, "
                   "side view, back view), identical face, hairstyle and outfit in every view, "
                   "full body from head to feet in every view, standing straight, arms relaxed "
                   "at sides; along the bottom edge = one narrow caption strip with small neat "
                   "text showing the character's name and height, plus a row of color palette "
                   "swatches showing the key outfit colors; plain pure white background, "
                   "no shadow, no props in hand, no other characters")

# 写实底模专用：明确"同一个人被拍三次 + 一张面部特写"，否则模型画成服装残板/情绪板。
# moyin character-generator 范式：把视图数量写死（exactly three / one horizontal row），
# 实测不写数量时底模自由发挥成 2/3/4 格混出。
CHAR_SHEET_SPEC_PHOTO = ("the same person on a wide horizontal studio sheet: left half of the "
                         "canvas = one large photorealistic face close-up portrait with detailed "
                         "facial features and subtle expression; right half = the same person "
                         "photographed in exactly three full-body poses standing side by side "
                         "from left to right (front view, side profile, back view), identical "
                         "outfit and hairstyle in all three, full body from head to feet in "
                         "every view; along the bottom edge = one narrow caption strip with "
                         "small neat text showing the character's name and height, plus a row "
                         "of color palette swatches of the outfit colors; seamless plain "
                         "light-gray studio background, no clothing cutouts, no flat lay, "
                         "no moodboard collage")

CHAR_SHEET_NEG = ("flat lay, clothing cutout collage, moodboard, outfit grid, cropped feet, "
                  "cropped head, headless figure, disembodied body parts, floating limbs, "
                  "disconnected torso, different people in each view, watermark, gibberish text, "
                  "garbled letters, two views only, four views, five views, grid of poses, "
                  "duplicated panels, fashion catalog, wardrobe display, vertical portrait "
                  "orientation, square canvas")

# 方案 A（程序侧合成）：单视角出图规格 —— 每次只画一个方向，最后程序拼版
# 【防拼贴】实测底模会在单视角图里自由发挥出"特写+三视图"组合 → 前缀写死 one view，
# 配合 CHAR_VIEW_NEG 的 model sheet/collage 拦截双保险。
VIEW_SPEC = {
    "front": ("exactly one single view of one person, one figure only, no inset, no collage, "
              "full body photograph, entire body visible from head to feet, wide full-length "
              "framing, (front view:1.2), standing straight facing camera, arms relaxed at sides, "
              "solid plain light-gray studio backdrop"),
    "side": ("exactly one single view of one person, one figure only, no inset, no collage, "
             "full body photograph, entire body visible from head to feet, wide full-length "
             "framing, (side profile view:1.5), (facing left, 90 degree profile:1.3), "
             "standing straight, solid plain light-gray studio backdrop"),
    "back": ("exactly one single view of one person, one figure only, no inset, no collage, "
             "full body photograph, entire body visible from head to feet, wide full-length "
             "framing, (back view:1.5), (seen from behind, back of the head and body:1.3), "
             "standing straight, solid plain light-gray studio backdrop"),
}
CHAR_VIEW_NEG = ("headshot, portrait crop, bust shot, close-up, upper body only, "
                 "cropped legs, cropped feet, two people, multiple characters, text, watermark, "
                 "clothing cutout collage, flat lay, moodboard, "
                 "model sheet, character sheet, turnaround, multiple views, split panels, "
                 "split screen, collage, grid layout, inset closeup, contact sheet, "
                 "convenience store interior, shop shelves, street, room interior, "
                 "background scenery, props in background")
# 单人立绘
CHAR_SINGLE_SPEC = ("single character, full body, front facing, plain background, "
                    "no other characters, no text")
# 角色板（参考图提炼：主立绘+三视图+面部/妆造/饰品/服饰细节+表情集+Q版形象+配色卡）
CHAR_BOARD_SPEC = ("professional character design board layout: one large full-body main "
                   "illustration on the left, three views (front, side, back) top right, "
                   "face close-up with makeup details, four expression close-ups (neutral, "
                   "smiling, angry, surprised), hair and costume texture detail close-ups, "
                   "accessory close-ups, one chibi Q-version of the same character, "
                   "color palette swatch row, pure white background, clean sheet layout, "
                   "same character in every panel, no text, no other characters")

# 场景（空镜）规格 —— 借鉴 huobao final-prompt：无人物空镜，含背影/剪影/倒影/照片里的人都要剔除
SCENE_EMPTY_SPEC = ("empty scene with absolutely no people, no human figure, no back view of a person, "
                    "no silhouette, no reflection of a person, no portrait inside a frame or photo, "
                    "environment concept design, cinematic composition, "
                    "clear foreground-midground-background layers, high detail")

# 道具（白底单品）规格 —— 借鉴 huobao final-prompt：single product shot on pure white background
PROP_SPEC = ("single product shot, one isolated item, centered composition, "
             "seamless pure white studio background, soft top light with subtle contact shadow, "
             "macro material detail, no hands, no people, no other objects")

# 2026-11-22 强化（hyper-realism 方法论）：去掉泛化赞美词（masterpiece/8K 类只抬高饱和度
# 与塑料感），换成摄影机/材质语言——给模型"怎么拍"而不是"拍得好"。
QUALITY_SUFFIX = ("natural texture, authentic detail, subtle film grain, realistic fabric "
                  "weight, visible pores and flyaway hairs, natural color grade, "
                  "unretouched look, restrained rendering")

# ---------- 活人感机制（去 AI 塑料感） ----------
# 依据：生活化瑕疵 + 真实光影 + 非模板姿态 + 10%微调 + 规避过度渲染
STYLE_FAMILY = {
    "photoreal": "photo", "cinematic_film": "photo", "hk_retro": "photo",
    "film_noir": "photo", "jp_fresh": "photo", "fashion_edito": "photo",
    "documentary": "photo", "cyberpunk": "photo", "steampunk": "photo",
    "anime_2d": "anime", "anime_soft": "anime", "ghibli": "anime", "manga_bw": "anime",
    "korean_webtoon": "anime", "american_comic": "anime", "chibi_q": "anime",
    "disney_2d": "anime", "pixel_art": "anime",
    "pixar_3d": "3d", "guofeng_3d": "3d", "game_cg": "3d", "low_poly": "3d",
    "synthwave": "3d",
    "guofeng_ink": "paint", "gongbi": "paint", "xianxia": "paint", "guochao": "paint",
    "ukiyoe": "paint", "thick_paint": "paint", "watercolor": "paint",
    "oil_painting": "paint", "flat_vector": "paint", "fantasy_art": "paint",
}

IMPERFECTION = {
    "photo": ("natural skin texture with subtle pores and fine blemishes, "
              "slightly asymmetric facial features, a few stray hairs out of place, "
              "faint nasolabial and under-eye detail, tiny fabric wrinkles, "
              "slight uneven makeup, natural skin shine"),
    "anime": ("hand-drawn line weight variation, slight color bleeding at edges, "
              "subtle paper grain, imperfect brush edges, small proportion quirks"),
    "3d": ("subtle surface imperfections, micro scratches and wear, "
           "slight asymmetry in features, soft ambient occlusion, "
           "non-uniform material response"),
    "paint": ("visible brush texture, uneven pigment density, canvas grain, "
              "slightly imperfect outlines, hand-painted irregularities"),
}

# 身份安全版：只保留“质感层”瑕疵，不动五官与脸型（用于三视图/角色板，跨集一致优先）
IMPERFECTION_SAFE = {
    "photo": ("natural skin texture with visible pores, fine fabric wrinkles, "
              "slight uneven makeup, a few stray hairs"),
    "anime": "hand-drawn line weight variation, subtle paper grain",
    "3d": "subtle surface imperfections, soft ambient occlusion",
    "paint": "visible brush texture, canvas grain",
}

PHYSICAL_LIGHT = {
    "photo": ("physically plausible lighting: single dominant practical light source "
              "matching the location, realistic falloff, soft natural shadow edges, "
              "mixed color temperature between key and ambient, no studio rim light"),
    "anime": "lighting consistent with the location, soft ambient bounce, simple cast shadows",
    "3d": ("lighting consistent with the location, soft global illumination, "
           "believable shadow softness, no overdone rim glow"),
    "paint": "lighting consistent with the location, painterly light direction, soft value shifts",
}

NATURAL_POSE = ("captured mid-action, natural off-balance stance, asymmetric shoulders, "
                "relaxed irregular hand gestures, candid unposed moment, "
                "gaze slightly off-camera, believable body weight shift")

ANTI_OVER_RENDER_POS = ("unretouched photography feel, natural contrast, "
                        "restrained highlights, matte midtones, no plastic gloss")
ANTI_OVER_RENDER_NEG = ("over-sharpened, hdr halo, oversaturated, plastic skin, waxy skin, "
                        "airbrushed, poreless glass skin, beauty filter, instagram filter, "
                        "cgi plastic look, 3d render look, flawless doll face, dead glassy eyes, "
                        "glossy over-polished, perfect symmetry, "
                        "stiff symmetrical pose, mannequin posture, t-pose, "
                        "perfectly centered portrait")


def style_family(preset_key: str) -> str:
    return STYLE_FAMILY.get(preset_key, "anime")


# ---------- 风格锁按资产类型适配 ----------
# 实测坑：photoreal 的 style_lock 是人像摄影模板（85mm 人像、皮肤毛孔、发丝、
# 柔光箱打脸光），直接套在道具上时"勺子"这种弱主体词被人像词堆淹没，
# SDXL 直接产出人脸特写（道具墙"勺子→人脸"事故）。道具必须用静物摄影版，
# 场景必须用环境摄影版——人像专用词一律不得进入非角色资产。
_PORTRAIT_ONLY_RE = re.compile(
    r"portrait photography|skin texture and pores|realistic hair strands|softbox lighting", re.I)

PROP_PHOTO_LOCK = ("photorealistic product photography, 60mm macro lens, studio softbox lighting, "
                   "raw photo, film grain")
SCENE_PHOTO_LOCK = ("photorealistic environmental photography, wide angle lens, natural location "
                    "lighting, raw photo, film grain")


def style_lock_for(kind: str, preset_key: str) -> str:
    """按资产类型适配风格锁。kind: character / prop / scene / shot。
    角色与人像镜头沿用原 style_lock；道具/场景遇到人像专用词时替换为对应摄影版。
    非写实 preset 的 style_lock 不含人像专用词，原样返回（不受影响）。"""
    lock = get_style(preset_key)["style_lock"]
    if kind == "prop" and _PORTRAIT_ONLY_RE.search(lock):
        return PROP_PHOTO_LOCK
    if kind == "scene" and _PORTRAIT_ONLY_RE.search(lock):
        return SCENE_PHOTO_LOCK
    return lock


# ---------- 国家/地区形象（ethnicity）预设：value=槽位值（英文 token），label=前端显示 ----------

ETHNICITY_PRESETS = {
    "chinese": ("中国人", "East Asian Chinese ethnicity, Chinese facial features"),
    "korean": ("韩国人", "East Asian Korean ethnicity, Korean facial features"),
    "japanese": ("日本人", "East Asian Japanese ethnicity, Japanese facial features"),
    "american": ("美国人", "American, Caucasian facial features"),
    "european": ("欧洲人", "European, Caucasian facial features"),
    "african": ("非洲人", "African, Black facial features, dark skin tone"),
    "indian": ("印度人", "South Asian Indian ethnicity, Indian facial features, warm brown skin tone"),
    "southeast asian": ("东南亚人", "Southeast Asian ethnicity, Southeast Asian facial features"),
    "middle eastern": ("中东人", "Middle Eastern ethnicity, Middle Eastern facial features"),
    "latin": ("拉丁裔", "Latin American Hispanic ethnicity, Latino facial features"),
    "russian": ("俄罗斯人", "Slavic Eastern European ethnicity, Slavic facial features"),
}


def ethnicity_token(slots: dict) -> str:
    """槽位 ethnicity → 画面词块：预设值展开成完整外貌描述，自由文本原样用。"""
    v = (slots.get("ethnicity") or "").strip()
    if not v:
        return ""
    return ETHNICITY_PRESETS.get(v.lower(), (v, v))[1]


def lifelike_tokens(preset_key: str, *, human: bool = True, pose: bool = False,
                    consistent: bool = False) -> str:
    """组装活人感词块。
    consistent=True（三视图/角色板/定妆照）→ 只用身份安全版瑕疵，保证跨集五官稳定；
    human=False 为空镜（不加皮肤瑕疵）；pose=True 才加姿态词。"""
    fam = style_family(preset_key)
    parts = []
    if human:
        parts.append((IMPERFECTION_SAFE if consistent else IMPERFECTION)[fam])
    parts.append(PHYSICAL_LIGHT[fam])
    if human and pose and not consistent:
        parts.append(NATURAL_POSE)
    parts.append(ANTI_OVER_RENDER_POS)
    return ", ".join(parts)


def character_view_prompt(slots: dict, preset_key: str, view: str,
                          lifelike: bool = True, full_identity: bool = False) -> str:
    """方案 A 用：单视角（front/side/back）定妆图提示词。视角/构图规格放最前（权重最高）。"""
    s = get_style(preset_key)
    parts = [VIEW_SPEC[view], s["style_lock"]]
    eth = ethnicity_token(slots)
    for key in ("identity", "appearance", "face", "hair", "clothing", "makeup",
                "accessories", "expression", "pose"):
        v = _take(slots, key)
        if v:
            parts.append(v)
        if key == "identity" and eth:
            parts.append(eth)
    palette = _take(slots, "palette")
    if palette:
        parts.append(f"color palette: {palette}")
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=True, pose=False,
                                     consistent=not full_identity))
    parts.append(QUALITY_SUFFIX)
    return ", ".join(p for p in parts if p)


def assemble_end_frame_prompt(shot_slots: dict, preset_key: str, scene_concept: str,
                              char_looks: list[str], lifelike: bool = True,
                              full_identity: bool = False) -> str:
    """尾帧提示词：动作完成后的静止状态（位移/运镜镜必出，供双帧 i2v 收束）。"""
    s = get_style(preset_key)
    # 空镜尾帧（无角色入镜）：风格锁按场景适配，禁止人像专用词（同勺子错配）
    parts = [style_lock_for("scene", preset_key) if not char_looks else s["style_lock"]]
    if scene_concept:
        parts.append(_clean(scene_concept))
    parts.extend(_clean(x) for x in char_looks if x)
    end_action = _take(shot_slots, "end_action") or _take(shot_slots, "subject_action")
    if end_action:
        parts.append(f"final pose after the action: {_clean(end_action)}")
    size = _take(shot_slots, "framing_end") or _take(shot_slots, "shot_size")
    if size:
        parts.append(f"{size} shot")
    camera = _take(shot_slots, "camera")
    if camera:
        parts.append(f"camera: {camera}")
    light = _take(shot_slots, "light")
    if light:
        parts.append(light)
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=bool(char_looks),
                                     consistent=not full_identity))
    parts.append(QUALITY_SUFFIX)
    return ", ".join(p for p in parts if p)

# 道具三分类（第二章：核心叙事/角色连接/环境氛围）
PROP_CATEGORY_LABEL = {"core": "核心叙事道具", "bond": "角色连接道具", "ambient": "环境氛围道具"}


def _clean(v) -> str:
    """清洗 LLM 填的槽位值：剥掉“EN:”提示前缀与空白。"""
    s = str(v or "").strip()
    if s[:3].upper() == "EN:":
        s = s[3:].strip()
    return s


def _take(slots: dict, key: str) -> str:
    return _clean(slots.get(key))


def get_style(preset_key: str) -> dict:
    return STYLE_PRESETS.get(preset_key) or STYLE_PRESETS[DEFAULT_PRESET]


def assemble_character_prompt(slots: dict, preset_key: str, mode: str = "sheet",
                              lifelike: bool = True, full_identity: bool = False) -> str:
    """角色提示词组装（第二章九段式公式：风格定位→身份→身材→五官→发型→服装→饰品→
    配色→表情气质→姿态→画面规格）。活人感：单人立绘加自然姿态；三视图/角色板保持静态规范。
    full_identity=True 时连三视图也用全量瑕疵（仅用户显式开启）。

    【硬性要求 2026-11-21】角色资产必须三视图版式：mode 参数一律强制 "sheet"，
    无论调用方传 single/board——单人立绘与角色板通道已废弃，防止任何入口漏网。"""
    mode = "sheet"
    s = get_style(preset_key)
    parts = [s["style_lock"]]
    # 国家/地区形象：紧跟 identity 段（权重顺序第二位）
    eth = ethnicity_token(slots)
    for key in ("identity", "appearance", "face", "hair", "clothing", "makeup",
                "accessories"):
        v = _take(slots, key)
        if v:
            parts.append(v)
        if key == "identity" and eth:
            parts.append(eth)
    palette = _take(slots, "palette")
    if palette:
        parts.append(f"color palette: {palette}")
    expr = _take(slots, "expression")
    if expr:
        parts.append(f"expression: {expr}")
    pose = _take(slots, "pose")
    if pose:
        parts.append(f"usual posture: {pose}")
    if mode == "board":
        chibi = _take(slots, "chibi")
        if chibi:
            parts.append(f"chibi version: {chibi}")
        parts.append(CHAR_BOARD_SPEC)
    else:
        if mode == "sheet" and style_family(preset_key) == "photo":
            parts.append(CHAR_SHEET_SPEC_PHOTO)
        else:
            parts.append(CHAR_SHEET_SPEC if mode == "sheet" else CHAR_SINGLE_SPEC)
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=True,
                                     pose=(mode == "single"),
                                     consistent=(mode != "single") and not full_identity))
    parts.append(QUALITY_SUFFIX)
    return ", ".join(p for p in parts if p)


def assemble_scene_prompt(slots: dict, preset_key: str, lifelike: bool = True,
                          fallback_subject: str = "") -> str:
    """场景提示词组装（第二章公式）；空镜不加皮肤瑕疵，只加真实光影与去过度渲染。

    与道具同病同治：拆解 LLM 偶发漏掉 space 槽位时用场景名顶上，
    避免提示词没有空间主体词导致出图不对题。
    """
    s = get_style(preset_key)
    parts = [style_lock_for("scene", preset_key)]
    if not (slots.get("space") or "").strip() and fallback_subject:
        parts.append(fallback_subject.strip())
    for key in ("space", "era", "elements", "light"):
        v = _take(slots, key)
        if v:
            parts.append(v)
    mood = _take(slots, "mood")
    if mood:
        parts.append(f"mood: {mood}")
    parts.append(SCENE_EMPTY_SPEC)
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=False))
    parts.append(QUALITY_SUFFIX)
    return ", ".join(p for p in parts if p)


def assemble_prop_prompt(slots: dict, preset_key: str, lifelike: bool = True,
                         fallback_subject: str = "") -> str:
    """道具提示词组装（第二章道具三分类理论）。

    实测坑：本地 LLM 拆解偶发漏掉 subject 槽位，导致提示词里没有物品本体词，
    底模自由发挥出完全无关的物品（监控屏幕→皮球）。两层兜底：
    ① slots["subject"] 缺失时用 fallback_subject（道具名/描述）顶上；
    ② 中文名对 SDXL 无效但对 qwen_image 有效，且 rebuild-slots 会补英文槽位。
    """
    s = get_style(preset_key)
    category = _take(slots, "category") or "core"
    parts = [style_lock_for("prop", preset_key)]
    subject = _take(slots, "subject") or (fallback_subject or "").strip()
    if subject:
        parts.append(subject)
    purpose = _take(slots, "purpose")
    if purpose:
        parts.append(f"story function: {purpose}")
    for key in ("era", "details"):
        v = _take(slots, key)
        if v:
            parts.append(v)
    material = _take(slots, "material")
    if material:
        parts.append(f"material & color: {material}")
    if category == "bond":
        interaction = _take(slots, "interaction")
        parts.append(f"interaction: {interaction or 'held and used by its owner'}")
    if category == "ambient":
        parts.append("worn aged patina, shallow depth of field, background blurred, "
                     "blended into environment")
    parts.append(PROP_SPEC)
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=False))
    parts.append(QUALITY_SUFFIX)
    return ", ".join(p for p in parts if p)


def assemble_shot_prompt(shot_slots: dict, preset_key: str,
                         scene_concept: str, char_looks: list[str],
                         lifelike: bool = True, full_identity: bool = False) -> str:
    """分镜首帧提示词组装（第四章 6 模块公式 + 活人感机制）。"""
    s = get_style(preset_key)
    # 空镜（无角色入镜）：风格锁按场景适配，禁止人像专用词——
    # 无人画面带"皮肤毛孔/发丝/85mm 人像"词会让 SDXL 硬塞人或出油光材质
    parts = [style_lock_for("scene", preset_key) if not char_looks else s["style_lock"]]
    if scene_concept:
        parts.append(_clean(scene_concept))
    parts.extend(_clean(x) for x in char_looks if x)
    for key in ("subject_action", "light"):
        v = _take(shot_slots, key)
        if v:
            parts.append(v)
    size = _take(shot_slots, "shot_size")
    if size:
        parts.append(f"{size} shot")
    camera = _take(shot_slots, "camera")
    if camera:
        parts.append(f"camera: {camera}")
    comp = _take(shot_slots, "composition")
    if comp:
        parts.append(comp)
    if lifelike:
        # 分镜永远用全量瑕疵（这是"活人感"主战场）；full_identity 只影响角色定妆资产
        parts.append(lifelike_tokens(preset_key, human=bool(char_looks), pose=bool(char_looks)))
    parts.append(QUALITY_SUFFIX)
    return ", ".join(p for p in parts if p)
