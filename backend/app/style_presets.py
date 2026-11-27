"""项目级风格预设（分类组织，覆盖动漫/国风/摄影写实/插画/复古等）。
词源：方法论第三、四章 + 网络风格词库整理（AI 短剧常用画风全谱）。
每个预设：style_lock 注入所有提示词头部；motion_hint 供视频提示词参考；category 用于前端分组。"""
import re
from pathlib import Path

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
        # 2026-11-26 修复：原写死 "flowing ornate hanfu" 会顶掉角色卡里的服装槽位
        # （林越设定是"破旧短上衣+松裤+草鞋"的落魄修士，出图却成白衣仙侠），
        # 服装交给角色槽位决定，风格锁只保留"有布料物理"这一层。
        "style_lock": ("3D chinese animation style, oriental stylized characters, smooth stylized skin, "
                       "flowing cloth simulation, glowing vfx, cinematic bloom"),
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
        # 注意：不写画幅词（2.39:1/widescreen）——竖屏出图时模型会把宽银幕构图
        # letterbox 进竖画布，剩余空间被人物特写填满，产生上下拼接画面（#78）
        "style_lock": ("cinematic film still, movie-grade lighting, anamorphic lens flare, "
                       "teal-orange color grading, dramatic rim light, "
                       "shallow depth of field, photorealistic detail"),
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
    # ---------- 风格库扩充（2026-11-28，参照 liblib.art 生图模型库分类补齐）----------
    # 选型原则：只收"能被底模听懂"的画风锚词（材质/笔触/渲染方式），不收具体模型名；
    # 每个新风格都在 STYLE_FAMILY 登记族（决定质感尾词与负向），否则会落到 anime 兜底。
    "anime_thick": {
        "category": "动漫卡通", "label": "日系厚涂2.5D",
        "style_lock": ("japanese 2.5D thick-paint illustration, soft digital brushwork, "
                       "rich color gradients, glowing rim light, semi-realistic anime rendering"),
        "motion_hint": "光影缓移、发丝与衣料飘动，半写实质感",
    },
    "guoman": {
        "category": "动漫卡通", "label": "国漫新番",
        "style_lock": ("chinese donghua animation style, semi-realistic cel shading, "
                       "ornate chinese fantasy costume detail, glowing vfx particles, "
                       "cinematic bloom"),
        "motion_hint": "法术光效、衣袂翻飞，国漫式分镜节奏",
    },
    "anime_90s": {
        "category": "动漫卡通", "label": "90年代赛璐璐",
        "style_lock": ("1990s retro anime cel style, hand-painted cels, simple flat shading, "
                       "vintage film grain, muted nostalgic colors, VHS softness"),
        "motion_hint": "有限帧动画感、轻抖动，复古颗粒",
    },
    "illustrious": {
        "category": "动漫卡通", "label": "高精度二次元插画",
        "style_lock": ("highly detailed anime illustration, illustrator-grade rendering, "
                       "dramatic composition, intricate hair and fabric detail, "
                       "pastel-to-neon gradient lighting"),
        "motion_hint": "静态构图为主，光斑与粒子缓动",
    },
    "colored_pencil": {
        "category": "插画数字", "label": "彩铅手绘",
        "style_lock": ("colored pencil drawing, visible waxy pencil strokes, layered hatching, "
                       "paper grain, soft blended shading"),
        "motion_hint": "手绘逐帧感，轻微笔触抖动",
    },
    "charcoal": {
        "category": "插画数字", "label": "炭笔素描",
        "style_lock": ("charcoal sketch, rough expressive smudges, grainy paper texture, "
                       "high contrast darks, visible erasure marks"),
        "motion_hint": "单色高对比，光影像炭粉一样过渡",
    },
    "marker_sketch": {
        "category": "插画数字", "label": "马克笔草图",
        "style_lock": ("alcohol marker sketch, translucent overlapping strokes, "
                       "bold graphic color blocks, loose confident linework, sketchbook feel"),
        "motion_hint": "设计稿式快速运镜，色块平移",
    },
    "riso_print": {
        "category": "插画数字", "label": "孔版印刷",
        "style_lock": ("risograph print, limited two-tone ink, visible misregistration offset, "
                       "coarse halftone dot grain, flat bold shapes"),
        "motion_hint": "套色偏移抖动、网点闪烁",
    },
    "linocut": {
        "category": "插画数字", "label": "木刻版画",
        "style_lock": ("linocut relief print, carved bold gouge lines, high contrast black ink, "
                       "coarse paper texture, limited color block print"),
        "motion_hint": "刀刻线条硬切，画面高对比",
    },
    "paper_cut": {
        "category": "插画数字", "label": "剪纸拼贴",
        "style_lock": ("layered paper cut collage, hand-cut edges with soft drop shadow, "
                       "flat colored paper shapes, craft texture"),
        "motion_hint": "纸片分层位移、投影变化",
    },
    "gouache": {
        "category": "插画数字", "label": "不透明水彩绘本",
        "style_lock": ("opaque gouache illustration, matte flat paint layers, visible brush "
                       "edges, muted storybook palette, paper texture"),
        "motion_hint": "绘本翻页感，色块稳定不闪烁",
    },
    "blind_box": {
        "category": "潮玩3D", "label": "盲盒潮玩",
        "style_lock": ("designer toy blind-box style, vinyl figure with glossy finish, "
                       "chunky stylized proportions, collectible display lighting, "
                       "clean pastel backdrop"),
        "motion_hint": "手办转台旋转、灯光扫过表面",
    },
    "clay_stopmotion": {
        "category": "潮玩3D", "label": "黏土定格",
        "style_lock": ("stop-motion clay animation look, hand-sculpted plasticine texture, "
                       "fingerprints and tool marks, miniature set lighting"),
        "motion_hint": "逐格定格微动，手工质感抖动",
    },
    "plush_toy": {
        "category": "潮玩3D", "label": "毛绒玩偶",
        "style_lock": ("plush toy look, soft fuzzy fabric texture, embroidered details, "
                       "huggable rounded shapes, soft studio light"),
        "motion_hint": "柔软挤压回弹，绒毛微动",
    },
    "voxel": {
        "category": "潮玩3D", "label": "体素方块",
        "style_lock": ("voxel art, everything built from visible cubes, blocky stepped edges, "
                       "limited palette, isometric game camera"),
        "motion_hint": "方块拼合/拆解动画，等距视角",
    },
    "iso_25d": {
        "category": "潮玩3D", "label": "等距2.5D",
        "style_lock": ("isometric 2.5D render, three-quarter top-down camera, clean geometric "
                       "environment, soft ambient occlusion, mobile-game diorama look"),
        "motion_hint": "等距视角平移推近，剖面展开",
    },
    "mecha_hard": {
        "category": "潮玩3D", "label": "硬表面机甲",
        "style_lock": ("hard-surface mecha design, panel-lined armor, industrial greebles, "
                       "metallic scratch wear, cool rim lighting, precise mechanical detail"),
        "motion_hint": "机械关节展开、液压缓动",
    },
    "y2k_gloss": {
        "category": "复古未来", "label": "Y2K千禧高光",
        "style_lock": ("Y2K aesthetic, chrome gradients, translucent plastic, bubble gloss "
                       "highlights, star sparkle accents, early-2000s digital optimism"),
        "motion_hint": "高光扫过、闪片爆闪",
    },
    "vaporwave": {
        "category": "复古未来", "label": "蒸汽波",
        "style_lock": ("vaporwave aesthetic, pastel magenta and cyan gradients, marble statue "
                       "motifs, grid floor, glow bloom, retro VHS overlay"),
        "motion_hint": "网格地平线滚动、VHS 抖动",
    },
    "dark_gothic": {
        "category": "暗黑废土", "label": "暗黑哥特",
        "style_lock": ("dark gothic fantasy art, ornate black iron filigree, desaturated cold "
                       "palette, candle-lit gloom, cathedral scale"),
        "motion_hint": "烛火摇曳、阴影缓慢爬动",
    },
    "wasteland": {
        "category": "暗黑废土", "label": "废土末世",
        "style_lock": ("post-apocalyptic wasteland look, rusted metal and dust, bleached harsh "
                       "sunlight, scavenged jury-rigged gear, desolate horizon"),
        "motion_hint": "风沙弥漫、镜头手持感",
    },
    "blueprint": {
        "category": "设计工程", "label": "工程蓝图",
        "style_lock": ("technical blueprint drawing, white linework on cyan-blue paper, precise "
                       "construction lines, dimension ticks, grid background, engineering schematic"),
        "motion_hint": "线条逐笔绘制、标注依次出现",
    },
    "tech_wire": {
        "category": "设计工程", "label": "科技线框",
        "style_lock": ("tech wireframe render, glowing holographic line lattice, translucent "
                       "surfaces, scanning grid, cyan-amber accent glow"),
        "motion_hint": "线框扫描、结构逐层展开",
    },
    "glass_neon": {
        "category": "设计工程", "label": "玻璃拟态霓虹",
        "style_lock": ("glassmorphism render, frosted translucent surfaces, neon edge glow, "
                       "gradient light refraction, minimal futuristic UI mood"),
        "motion_hint": "折射光斑缓移、边缘霓虹呼吸",
    },
}

DEFAULT_PRESET = "anime_2d"

# ---------- 风格可见范围（2026-11-28）：风格库只列 AI 短剧 / AI 漫剧用得上的 ----------
# 判断口径：这个风格能不能直接当"一集几分钟、连拍十几镜、角色要复用"的片子底色。
# 用不上的照样保留文字说明 + 示例缩略图（backend/data/style_samples/<key>.jpg 全 57 张都出），
# 只是不在列表里显示；哪天要放出来，从这个集合里删掉 key 即可，前端不用改。
STYLE_HIDDEN = frozenset({
    # 插画数字里偏"单张作品"的：纸张/笔触肌理太强，同一角色多镜之间纹理与手绘线条
    # 每镜都重画一遍，接戏时脸和衣服细节对不上
    "flat_vector", "charcoal", "marker_sketch", "riso_print", "linocut", "paper_cut",
    # 复古未来里偏"平面设计/游戏画面"的：像素、低多边形、Y2K 光面、蒸汽波都是
    # 一张海报/一个封面成立，连成戏就散架
    "synthwave", "pixel_art", "low_poly", "y2k_gloss", "vaporwave",
    # 潮玩 3D 里的"物件/机甲"类：主体是手办、玩偶、体素、机甲，不承接人物表演
    # （clay_stopmotion / iso_25d 留着：黏土定格与等距小景漫剧能用）
    "blind_box", "plush_toy", "voxel", "mecha_hard",
    # 设计工程：蓝图、线框、玻璃拟态是工程示意图的语汇，不适合叙事画面
    "blueprint", "tech_wire", "glass_neon",
})

# 隐性风格的"为什么不显示"（前端 hover 提示用，按分类给一句话）
STYLE_HIDDEN_NOTE = {
    "插画数字": "纸张/笔触肌理每镜重画，角色接戏对不上，暂不适用",
    "复古未来": "像素/低多边形/Y2K 是封面语汇，连成戏会散架，暂不适用",
    "潮玩3D": "主体是手办/玩偶/机甲，不承接人物表演，暂不适用",
    "设计工程": "工程示意语汇，不适合叙事画面，暂不适用",
}


def is_style_hidden(preset_key: str) -> bool:
    """该风格当前是否不进风格库列表（数据与缩略图仍保留）。"""
    return preset_key in STYLE_HIDDEN


def visible_presets() -> dict:
    """风格库列表该显示的预设（保持 STYLE_PRESETS 原有顺序）。"""
    return {k: v for k, v in STYLE_PRESETS.items() if k not in STYLE_HIDDEN}


# ---------- 风格示例缩略图（tools/gen_style_samples.py 生成） ----------
STYLE_SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "style_samples"


def style_sample_path(preset_key: str) -> Path | None:
    """示例缩略图本地路径；没生成过/非法 key 返回 None（前端退回渐变色块）。"""
    if preset_key in STYLE_PRESETS:          # 白名单挡 ../ 穿越
        p = STYLE_SAMPLES_DIR / f"{preset_key}.jpg"
        if p.exists():
            return p
    return None


# ---------- 画面规格（第二章/第四章 + 参考图角色板） ----------

# 三视图（2026-11-21 定稿版式，用户指定）：宽横幅一体成图 ——
# 左半：面部近景大特写（五官细节+微表情）；右半：全身正/侧/背三视图从左到右并排；
# 底部：窄信息栏（小字姓名+身高+关键配色色块）。固定横版 16:9（1344x768）出图。
# 旧版只写 "three views plus face close-up"，底模画成服装陈列板/肢体拼贴（实测两例崩坏），
# 必须把"同一个人物、每个视图全身、版式分区、信息栏"全部写死。
# 人物设计图（2026-11-27 用户拍板：不要三视图/四视图排排站，改成概念设计稿）
# 版式参考 RunningHub 上那类「人物设计图」：中心一张全身立绘，四周环绕服装分层、
# 表情、材质、随身物件，手绘箭头 + 手写标注，米黄纸纹底。竖版 3:4。
CHAR_SHEET_SPEC = ("character design sheet of ONE single character, vertical concept-art board "
                   "on warm beige textured parchment: center = one large full-body illustration "
                   "of the character standing in the outfit, head to feet, occupying about half "
                   "the canvas height, calm pose; upper left = the outfit disassembled into flat "
                   "separate pieces (outer garment, inner layer, belt, footwear) laid out neatly; "
                   "upper right = three head close-ups of the SAME face with different "
                   "expressions (calm, frowning, surprised), identical hairstyle; lower left = "
                   "two material detail close-ups (coarse cloth weave, leather and metal "
                   "accessory sheen); lower right = the character's personal props laid out as "
                   "small objects; thin hand-drawn arrows connecting each detail to the matching "
                   "part of the main figure, small handwritten annotation labels beside every "
                   "element; a short row of four color swatches along the bottom; ink-and-wash "
                   "concept art rendering, consistent face, hairstyle and outfit across every "
                   "element, no other characters")

# 写实底模专用：设计稿语气换成"现场概念设定板 + 实拍质感"，
# 否则 SDXL 会把 parchment/ink 画成插画纸感。
CHAR_SHEET_SPEC_PHOTO = ("photorealistic character design board of ONE single person, vertical "
                         "concept layout on a warm grey studio backdrop: center = one large "
                         "full-length photograph of the person standing in full outfit, head to "
                         "feet, occupying about half the canvas height; upper left = the outfit "
                         "as flat separate pieces (jacket, shirt, trousers, shoes) neatly laid "
                         "out; upper right = three head close-ups of the SAME face with different "
                         "expressions (calm, frowning, surprised); lower left = two material "
                         "detail close-ups (fabric weave, leather and metal accessory); lower "
                         "right = the person's personal props as small objects; thin hand-drawn "
                         "arrows and small handwritten annotation labels beside each element; a "
                         "short row of four color swatches along the bottom; consistent identity "
                         "and outfit in every panel, no other people, no clothing catalog grid")

# 短版设计图版式（2026-11-27）：SDXL 同样吃 77 token 分块，版式规格放在 1800 字
# 长串末尾会被稀释成"单人立绘"（实测两版对比）。所以把版式写最前、只留 ~15 词。
CHAR_DESIGN_SPEC_SHORT = ("character design sheet, one large full-body figure in the center, "
                          "side panels of outfit pieces, expression heads and material "
                          "close-ups, warm parchment background, handwritten labels")

CHAR_SHEET_NEG = ("three view lineup, turnaround, orthogonal front side back views, "
                  "four views side by side, duplicate full-body figures of the same pose, "
                  "fashion catalog grid, lookbook spread, runway walk, moodboard, outfit grid, "
                  "cropped feet, cropped head, headless figure, disembodied body parts, floating "
                  "limbs, disconnected torso, different people in each panel, watermark, "
                  "gibberish text, garbled letters, empty white margin, square canvas")

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

# 场景设计图 / 道具设计图版式（2026-11-28 用户要求：对齐 RunningHub 无限画布 RHTV 的资产范式，
# 场景不再出"单张空镜照"、道具不再出"白底单品"，一律出概念设定板/设计稿）：
#   · 一张主图占中心 + 环绕侧面视图 / 顶视图 / 材质特写面板
#   · 手绘箭头 + 手写标注 + 尺寸线 + 底部色卡
#   · 米黄纸纹底（Qwen-Image 对 parchment/annotation 响应好，实测角色设计图已成立）
# SDXL 会把这种长版式稀释（77 token 分块），所以另留一个 ~15 词的短版兜底。
SCENE_DESIGN_SPEC = ("environment design sheet, one large main establishing view of the location "
                     "occupying the center, secondary panels around it showing the same space from "
                     "a second angle and a simple top-down floor plan sketch, close-up panels of "
                     "key material, lighting and set-dressing details, thin hand-drawn arrows "
                     "connecting each detail to its place in the main view, small handwritten "
                     "annotation labels beside the panels, a short row of color swatches at the "
                     "bottom, warm beige parchment concept-board background, unoccupied space, "
                     "consistent architecture and lighting across all panels")
SCENE_DESIGN_SPEC_SHORT = ("environment design sheet, main view centered, side panels of "
                           "another angle plus floor plan and material close-ups, handwritten "
                           "labels, parchment board, unoccupied space")

PROP_DESIGN_SPEC = ("prop design sheet, one large three-quarter view of the single item "
                    "centered and dominating the sheet, smaller panels around it showing the "
                    "same item in front view, side view and top view, close-up panels of surface "
                    "ornament, carving and material texture, thin dimension lines with "
                    "measurement ticks, small handwritten annotation labels beside each panel, "
                    "a short row of color swatches at the bottom, warm beige parchment "
                    "concept-board background, consistent shape and material in every panel")
PROP_DESIGN_SPEC_SHORT = ("prop design sheet, main three-quarter view centered, front side "
                          "and top view panels, material close-ups, dimension lines, handwritten "
                          "labels, parchment board")

# 设计图负向：拦"多物件重复/两套主角"和"衣物目录拼贴"。
# 注意不能把裸 text 放进来——设计图本来就要写标注（与角色设计图同一处理）。
DESIGN_SHEET_NEG = ("two different objects, duplicated main object, clone of the same item "
                    "twice, product catalog grid, clothing catalog, lookbook spread, "
                    "watermark, cropped dimension line, empty white margin, square canvas")

# 从提示词里剥掉设计图版式（分镜/镜头复用场景概念时用：
# 版式词进了首帧提示词会把镜头画成设定板）。
def strip_design_spec(text: str) -> str:
    t = text or ""
    for spec in (SCENE_DESIGN_SPEC, PROP_DESIGN_SPEC,
                 SCENE_DESIGN_SPEC_SHORT, PROP_DESIGN_SPEC_SHORT):
        t = t.replace(spec, "")
    return ", ".join(x.strip() for x in t.split(",") if x.strip())


# 场景（空镜）规格 —— 2026-11-23 改为"纯正向空场表述"：
# SDXL 对正向否定句（no people / no human figure）几乎不响应，反而会因 "people" 这个词
# 把人物拉进画面（实测「废弃矿洞」出成少女侧身像）。人形排除一律交给 NEGATIVE_ENV 负向词。
SCENE_EMPTY_SPEC = ("unoccupied interior space, empty set, environment concept art, "
                    "wide establishing shot, clear foreground-midground-background layers, "
                    "high detail")

# 道具（白底单品）规格 —— 同理只留正向：单品、居中、纯白底、柔光
PROP_SPEC = ("single product shot, one isolated item, centered composition, "
             "seamless pure white studio background, soft top light with subtle contact shadow, "
             "macro material detail")

# 2026-11-22 强化（hyper-realism 方法论）：去掉泛化赞美词（masterpiece/8K 类只抬高饱和度
# 与塑料感），换成摄影机/材质语言——给模型"怎么拍"而不是"拍得好"。
QUALITY_SUFFIX = ("natural texture, authentic detail, subtle film grain, realistic fabric "
                  "weight, visible pores and flyaway hairs, natural color grade, "
                  "unretouched look, restrained rendering")

# 无人像画质尾巴（场景/道具/空镜专用）：去掉了 pores and flyaway hairs / fabric weight
# ——皮肤毛孔+发丝是"这里有人"的最强诱导词，实测场景/道具出人形的主因之一。
QUALITY_SUFFIX_ENV = ("natural texture, authentic detail, subtle film grain, "
                      "natural color grade, unretouched look, restrained rendering")

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
    # 风格库扩充（2026-11-28）：不登记会落到 anime 兜底，质感尾词/负向会串味
    "anime_thick": "paint", "guoman": "anime", "anime_90s": "anime",
    "illustrious": "anime",
    "colored_pencil": "paint", "charcoal": "paint", "marker_sketch": "paint",
    "riso_print": "paint", "linocut": "paint", "paper_cut": "paint", "gouache": "paint",
    "blind_box": "3d", "clay_stopmotion": "3d", "plush_toy": "3d", "voxel": "3d",
    "iso_25d": "3d", "mecha_hard": "3d", "y2k_gloss": "3d", "vaporwave": "3d",
    "dark_gothic": "paint", "wasteland": "photo",
    "blueprint": "paint", "tech_wire": "3d", "glass_neon": "3d",
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


# ---------- 质感尾巴 / 去过度渲染词按族分支（2026-11-26 修复角色不一致） ----------
# 现场事故：项目风格锁是 guofeng_3d（3D 国风），但拼出的 prompt 同时含
#   ① 正向无条件注入的 "subtle film grain / realistic fabric weight / visible pores /
#      unretouched photography feel"（写实摄影词）
#   ② 负向无条件注入的 "cgi plastic look / 3d render look / plastic skin / waxy skin"
#   → 两套词把 3D 国风硬拽成写实电影风，s1 出"写实中年学者"、s2 出"不属于角色板的仙侠脸"。
# 修法：三条尾巴全部按风格族取值，3D/动漫/绘画族禁入写实摄影词，负向也禁"反 CGI"词，
# 反而把 "photographic realism / live-action photo" 加进它们的负向。
_QUALITY_BY_FAM = {
    "photo": QUALITY_SUFFIX,
    "3d": ("clean CG surface with subtle micro-imperfections, physically based shading, "
           "subsurface scattering on skin, soft global illumination, "
           "accurate material response, crisp silhouette, high detail"),
    "anime": ("clean line art, cel shading with soft gradation, consistent flat colors, "
              "crisp silhouette, high detail"),
    "paint": ("layered brushwork, pigment variation, canvas texture, painterly detail"),
}

# 无人画面版（场景/道具/空镜）：去掉一切"这里有人"的皮肤/发丝诱导词
_QUALITY_ENV_BY_FAM = {
    "photo": QUALITY_SUFFIX_ENV,
    "3d": ("clean CG surface, physically based shading, soft global illumination, "
           "accurate material response, crisp detail"),
    "anime": "clean line art, consistent flat colors, crisp detail",
    "paint": "layered brushwork, canvas texture, painterly detail",
}

_ANTI_POS_BY_FAM = {
    "photo": ANTI_OVER_RENDER_POS,
    "3d": ("consistent global illumination, believable specular response, "
           "restrained highlights, matte-to-glossy material contrast"),
    "anime": "consistent shading direction, restrained highlights, clean color separation",
    "paint": "consistent light direction, restrained highlights, painterly value structure",
}

_ANTI_NEG_BY_FAM = {
    "photo": ANTI_OVER_RENDER_NEG,
    "3d": ("over-sharpened, hdr halo, oversaturated, airbrushed, beauty filter, "
           "instagram filter, photographic realism, live-action photo, film grain noise, "
           "deformed face, asymmetric eyes, extra limbs, bad hands, blurry, low detail"),
    "anime": ("photographic realism, live-action photo, film grain noise, muddy colors, "
              "sketchy messy lines, deformed face, extra limbs, bad hands, blurry, low detail"),
    "paint": ("photographic realism, live-action photo, muddy colors, deformed face, "
              "extra limbs, bad hands, blurry, low detail"),
}


# 分镜镜头专用精简版（2026-11-27）：只留"材质/渲染色"锚点。
# 分镜首帧本来就 1900+ 字，画质尾巴再堆 7-8 段会把服装与动作词挤出注意力；
# 实测同一角色 13 镜出现 4 套不同衣服，画质词稀释是主因之一。
_SHOT_QUALITY_BY_FAM = {
    "photo": "natural texture, authentic detail, natural color grade",
    "3d": "clean CG surface, physically based shading, crisp silhouette",
    "anime": "clean line art, flat colors, crisp silhouette",
    "paint": "layered brushwork, painterly detail",
}


def quality_suffix(preset_key: str, human: bool = True, compact: bool = False) -> str:
    """按风格族取质感尾巴。human=False 用无人版（场景/道具/空镜）。
    compact=True 返回分镜镜头用精简版（分镜提示词已很长，画质词只留锚点）。"""
    if compact:
        return _SHOT_QUALITY_BY_FAM[style_family(preset_key)]
    return (_QUALITY_BY_FAM if human else _QUALITY_ENV_BY_FAM)[style_family(preset_key)]


def anti_over_render_neg(preset_key: str) -> str:
    """按风格族取"去过度渲染"负向词。3D/动漫族不得含 cgi/3d render 类词。"""
    return _ANTI_NEG_BY_FAM[style_family(preset_key)]


# ---------- 单时刻化（2026-11-26 修复首帧上下分格/双人复制） ----------
# 现场：s1 的 subject_action 是 "clutches it tightly to his chest before dropping it
# when he falls"——一句话里塞了"抓在胸口"和"跌倒掉落"两个时刻，SDXL 直接把画面画成
# 上下两格（两组同样的脸）。首帧只能是一个瞬间，动作演变交给 video_prompt。
_DUAL_MOMENT_RE = re.compile(
    r"\s*(?:,\s*)?(?:before|after|then|and then|until|later|afterwards)\s+", re.I)


def single_moment(text: str) -> str:
    """把"前一刻…然后…"的双动作描述截成单一瞬间（取第一段）。"""
    t = _clean(text or "")
    if not t:
        return t
    head = _DUAL_MOMENT_RE.split(t, maxsplit=1)[0].strip(" ,")
    return head or t


# ---------- 风格锁按资产类型适配 ----------
# 实测坑：photoreal 的 style_lock 是人像摄影模板（85mm 人像、皮肤毛孔、发丝、
# 柔光箱打脸光），直接套在道具上时"勺子"这种弱主体词被人像词堆淹没，
# SDXL 直接产出人脸特写（道具墙"勺子→人脸"事故）。道具必须用静物摄影版，
# 场景必须用环境摄影版——人像专用词一律不得进入非角色资产。
_PORTRAIT_ONLY_RE = re.compile(
    r"portrait photography|skin texture and pores|realistic hair strands|softbox lighting", re.I)

# ---------- 非角色资产的人像词语块剔除（2026-11-23 #84） ----------
# 事故：场景「2-1-青云界·废弃矿洞」出成二次元少女侧身像、道具「系统提示框」出成少女+悬浮框。
# 提示词主体词齐全、也带了空镜约束，真正的源头是风格锁里的人像词——
#   anime_2d: expressive detailed eyes（"在画眼睛"=画人）
#   guofeng_3d: oriental stylized characters / smooth glossy skin / hanfu cloth simulation
#   korean_webtoon: tall elegant figures, porcelain skin
#   pixar_3d: subsurface skin scattering；chibi_q: big head small body
# 这些词在角色上是对的，落到场景/道具上就把人形拽进画面。这里逐词块剔除，只留画风与光效。
_CHAR_WORD_RE = re.compile(
    r"(expressive|detailed)\s+(eyes?|faces?)|"
    r"(stylized\s+)?characters?|character design|"
    r"(smooth\s+)?glossy skin|porcelain skin|skin texture|skin pores?|"
    r"subsurface skin scattering|"
    r"hanfu|cloth simulation|costume|outfit|clothing|dress|"
    r"(tall\s+)?elegant figures?|big head small body|"
    r"facial features|beautiful face|handsome|"
    r"person|people|human|portrait|silhouette|hair strands?", re.I)

# 剔除人像词后，按"资产类型 + 风格族"补回画风锚词（防止锁变得没有画风倾向）
ENV_LOCK_TAIL = {
    "scene": {
        "photo": "environmental photography, wide establishing view, natural location lighting",
        "anime": "anime background art, cel-shaded environment painting, detailed background scenery",
        "3d": ("stylized 3D animation render, toon-shaded 3D environment, "
               "clean stylized geometry, carved ornament detail, physically based materials, "
               "volumetric lighting, set dressing"),
        "paint": "painterly environment painting, atmospheric perspective, visible brush texture",
    },
    "prop": {
        "photo": "product still life, macro material detail, natural location lighting",
        "anime": "anime object illustration, cel-shaded still object, thin clean lineart",
        "3d": ("stylized 3D animation asset, toon-shaded 3D object, clean stylized geometry, "
               "physically based materials, soft studio lighting"),
        "paint": "painterly object study, visible brush texture, even value shifts",
    },
}

PROP_PHOTO_LOCK = ("photorealistic product photography, 60mm macro lens, studio softbox lighting, "
                   "raw photo, film grain")
SCENE_PHOTO_LOCK = ("photorealistic environmental photography, wide angle lens, natural location "
                    "lighting, raw photo, film grain")


def _env_lock(lock_text: str) -> str:
    """逐词块剔除人像词（眼睛/皮肤/发丝/服饰/人物），保留画风与光效词块。"""
    keep = [c.strip() for c in lock_text.split(",")
            if c.strip() and not _CHAR_WORD_RE.search(c)]
    return ", ".join(keep)


# ---------- 分镜短锁（2026-11-27）：SDXL 单块只有 77 token，分镜提示词必须压进一块 ----------
# 事故：分镜首帧提示词 1867 字（约 380 token）被 ComfyUI 切成 5 个 77-token 块再平均，
# 每个概念权重只剩 1/5——服装/道具/场景全部失效，模型按底模先验自由编（一集换 4 套衣服）。
# 修法：分镜走"短模板"，画风只留定调锚点，其余交给角色外观+动作+场景主体。
SHOT_STYLE_SHORT = {
    "guofeng_3d": "3D chinese animation, guofeng stylized characters",
    "pixar_3d": "stylized 3D animation, rounded appealing shapes",
    "game_cg": "AAA game cinematic CG",
    "low_poly": "low-poly 3D render",
    "photoreal": "photorealistic photo",
    "cinematic_film": "cinematic film still",
    "film_noir": "black and white film noir",
    "documentary": "documentary photography",
    "anime_2d": "modern TV anime, 3-tone cel shading",
    "anime_soft": "soft anime illustration",
    "ghibli": "hand-drawn anime",
    "korean_webtoon": "korean webtoon art",
    "guofeng_ink": "chinese ink painting",
    "xianxia": "chinese fantasy illustration",
    # 风格库扩充（2026-11-28）：分镜只留一个定调锚，防止 77-token 块被画风词挤爆
    "anime_thick": "japanese 2.5D thick-paint anime",
    "guoman": "chinese donghua animation",
    "anime_90s": "1990s retro anime cel",
    "illustrious": "detailed anime illustration",
    "blind_box": "designer toy 3D render",
    "clay_stopmotion": "clay stop-motion look",
    "plush_toy": "plush toy 3D",
    "voxel": "voxel art",
    "iso_25d": "isometric 2.5D render",
    "mecha_hard": "hard-surface mecha CG",
    "y2k_gloss": "Y2K chrome gloss",
    "vaporwave": "vaporwave pastel",
    "dark_gothic": "dark gothic art",
    "wasteland": "post-apocalyptic wasteland",
    "blueprint": "technical blueprint",
    "tech_wire": "holographic wireframe",
    "glass_neon": "glassmorphism neon",
    "colored_pencil": "colored pencil drawing",
    "gouache": "gouache storybook illustration",
    "riso_print": "risograph print",
    "linocut": "linocut print",
    "charcoal": "charcoal sketch",
    "marker_sketch": "marker sketch",
    "paper_cut": "paper cut collage",
}


def shot_style_short(preset_key: str) -> str:
    """分镜短画风（≤3 块）。未登记的 preset 回落 style_lock 前三块。"""
    v = SHOT_STYLE_SHORT.get(preset_key)
    if v:
        return v
    lock = get_style(preset_key)["style_lock"]
    return ", ".join(c.strip() for c in lock.split(",")[:3] if c.strip())


def style_lock_for(kind: str, preset_key: str) -> str:
    """按资产类型适配风格锁。kind: character / prop / scene / shot。
    角色与人像镜头沿用原 style_lock；
    道具/场景：人像摄影锁换成静物/环境摄影版，并把所有人像/皮肤/服饰词块剔除，
    再补回该风格族的画风锚词（避免非角色资产被风格锁带出人物）。"""
    lock = get_style(preset_key)["style_lock"]
    if kind not in ("scene", "prop"):
        return lock
    if _PORTRAIT_ONLY_RE.search(lock):
        lock = PROP_PHOTO_LOCK if kind == "prop" else SCENE_PHOTO_LOCK
    fam = style_family(preset_key)
    return ", ".join(x for x in (_env_lock(lock), ENV_LOCK_TAIL[kind][fam]) if x)


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
    parts.append(_ANTI_POS_BY_FAM[fam])
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
    parts.append(quality_suffix(preset_key, human=True))
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
    parts.append(quality_suffix(preset_key, human=bool(char_looks)))
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


def _clip_n(v: str, n: int = 6) -> str:
    """截取前 n 个词：人物调节槽位要挤进短版设计图提示词，只留可执行的描述。"""
    words = _clean(v).replace(",", " , ").split()
    out = " ".join(words[:n]).replace(" , ", ", ").strip(" ,")
    return out


def get_style(preset_key: str) -> dict:
    return STYLE_PRESETS.get(preset_key) or STYLE_PRESETS[DEFAULT_PRESET]


def assemble_character_design_prompt(slots: dict, preset_key: str,
                                     lifelike: bool = True) -> str:
    """人物设计图版式的短组装（2026-11-27 版式改版专用）。

    为什么不是走九段式长串：SDXL 超过 77 token 会切成多块再池化平均，1200 字以上的
    九段式会让末尾的"设计图版式"退化成一张普通立绘（实测 1800 字那版完全没出面板）。
    所以顺序固定为「版式 → 风格 → 人 → 穿什么 → 细节」：
      design sheet spec(15 词) + style_short + identity/ethnicity + hair + clothing
      + 版式细节（色卡/材质）
    目标 55-70 词，落在一个 77-token 块内。
    """
    parts = [CHAR_DESIGN_SPEC_SHORT, shot_style_short(preset_key)]
    eth = ethnicity_token(slots)
    # 服装紧跟版式与身份：放到第三位，避免被发型/配色词稀释成"现代T恤"
    for key in ("identity", "clothing", "hair"):
        v = _take(slots, key)
        if v:
            parts.append(v)
        if key == "identity" and eth:
            parts.append(eth)
    # palette 不再注入：原设配色（青/绯）与"灰粗布"服装词冲突，
    # 实测会把粗布长衫染成青色/墨绿（2026-11-27）
    #
    # 人物调节（RHTV 面部/表情/妆容/体型/姿态/饰物）必须能落到图上：
    # 六槽各留前 6 词追加在尾部——他们在参考图里本就是"表情头 + 材质 + 随身物件"
    # 的信息来源，不给它们位置等于按钮点了不出效果。六槽全空时不占 token。
    for key, label in (("face", ""), ("expression", "expression: "),
                       ("makeup", "makeup: "), ("appearance", "build: "),
                       ("pose", "posture: "), ("accessories", "wearing ")):
        v = _clip_n(_take(slots, key), 6)
        if v:
            parts.append((label + v).strip())
    # 材质尾：原先硬编码"古代中国农夫装"只适配林越一个角色，
    # 其他角色/现代题材会被强行染成古装，改成通用布料质感
    parts.append("coarse cloth texture, fabric folds visible")
    return ", ".join(p for p in parts if p)


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
        # 设计图版式（sheet）不堆活人感长串：一张图里要塞立绘+细节+标注，
        # 20 段光照/瑕疵词会把"版式+服装"稀释掉（2026-11-27 实测：2165 字里
        # 服装词失效，出成别的衣服）。只留一条材质真实感。
        if mode == "sheet":
            parts.append("realistic material rendering, subtle surface texture")
        else:
            parts.append(lifelike_tokens(preset_key, human=True,
                                         pose=(mode == "single"),
                                         consistent=(mode != "single") and not full_identity))
    from .style_vocab import style_vocab_positive
    # 风格词库（只取 style 锚词）：特效/氛围词留给镜头，设定图保持干净版式
    parts.append(style_vocab_positive(preset_key, kinds=("style",)))
    parts.append(quality_suffix(preset_key, human=True, compact=(mode == "sheet")))
    return ", ".join(p for p in parts if p)


def assemble_scene_prompt(slots: dict, preset_key: str, lifelike: bool = True,
                          fallback_subject: str = "", design_sheet: bool = True) -> str:
    """场景提示词组装（第二章公式）；空镜不加皮肤瑕疵，只加真实光影与去过度渲染。

    2026-11-28 版式改版：场景资产从"单张空镜概念图"改为 **场景设计图**
    （对齐 RunningHub 无限画布 RHTV 的资产范式）：主视角 + 第二角度 + 平面草图 +
    材质/光影特写 + 手绘箭头与手写标注 + 色卡，米黄纸纹底。
    design_sheet=False 用于 iso 布局图等"单张成图"的兜底通道（版式会与
    isometric diorama 打架）。

    与道具同病同治：拆解 LLM 偶发漏掉 space 槽位时用场景名顶上，
    避免提示词没有空间主体词导致出图不对题。
    """
    s = get_style(preset_key)
    # 权重顺序：空间主体词前置（SDXL 前 75 token 权重最高），版式紧随其后，
    # 风格锁再次——主体弱、风格锁里的人像词靠前，就会出人（#84 事故）。
    head = []
    if not (slots.get("space") or "").strip() and fallback_subject:
        head.append(fallback_subject.strip())
    space = _take(slots, "space")
    if space:
        head.append(space)
    parts = head
    if design_sheet:
        parts.append(SCENE_DESIGN_SPEC)
    parts.append(style_lock_for("scene", preset_key))
    for key in ("era", "elements", "light"):
        v = _take(slots, key)
        if v:
            parts.append(v)
    mood = _take(slots, "mood")
    if mood:
        parts.append(f"mood: {mood}")
    # 场景里出现的牌匾/招牌/门额文字：把字写进提示词，生成时就争取写对，
    # 写不对再用资产卡「📝 改字」局部重绘（中文/英文都支持）。
    text_content = (_take(slots, "text_content") or _take(slots, "text") or "").strip()
    if text_content:
        parts.append(f'Chinese characters "{text_content}" written on a plaque, signboard '
                     'or door lintel in the scene, accurate strokes, correctly spelled, '
                     'no gibberish lettering')
    parts.append(SCENE_EMPTY_SPEC)
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=False))
    from .style_vocab import style_vocab_positive
    parts.append(style_vocab_positive(preset_key))   # 场景吃全量词库（含特效/氛围）
    parts.append(quality_suffix(preset_key, human=False))
    return ", ".join(p for p in parts if p)


def assemble_prop_prompt(slots: dict, preset_key: str, lifelike: bool = True,
                         fallback_subject: str = "", design_sheet: bool = True) -> str:
    """道具提示词组装（第二章道具三分类理论）。

    2026-11-28 版式改版：道具资产从"白底单品图"改为 **道具设计图**
    （对齐 RHTV）：三视图 + 材质/纹样特写 + 尺寸线 + 手写标注 + 色卡，米黄纸纹底。
    白底单品规格 PROP_SPEC 只在 design_sheet=False 的旧通道保留。

    实测坑：本地 LLM 拆解偶发漏掉 subject 槽位，导致提示词里没有物品本体词，
    底模自由发挥出完全无关的物品（监控屏幕→皮球）。两层兜底：
    ① slots["subject"] 缺失时用 fallback_subject（道具名/描述）顶上；
    ② 中文名对 SDXL 无效但对 qwen_image 有效，且 rebuild-slots 会补英文槽位。
    """
    s = get_style(preset_key)
    category = _take(slots, "category") or "core"
    subject = _take(slots, "subject") or (fallback_subject or "").strip()
    # 物品主体词前置（同场景：主体弱 → 风格锁/质感动词把人形拽进画面）
    head = [subject] if subject else []
    parts = head
    if design_sheet:
        parts.append(PROP_DESIGN_SPEC)
    parts.append(style_lock_for("prop", preset_key))
    purpose = _take(slots, "purpose")
    if purpose:
        parts.append(f"story function: {purpose}")
    for key in ("era", "details"):
        v = _take(slots, key)
        if v:
            parts.append(v)
    # 牌面/券面/铭文上的具体文字：必须把文字本身写进提示词。
    # 实测（项目2「灵石兑换券」1024×1024，Qwen-Image）：只要提示词明确给出
    # "四个竖排汉字 灵石兑换券"，五个字全部写对；不给文字内容时只能出伪字。
    # 这是本地底模/云端通道共用的"准字"关键，所以放在道具组装里而不是某个模型分支。
    # 设计图模式下这段字同时是"牌面文字 + 面板旁的手写标注"，措辞要照顾两处。
    text_content = (_take(slots, "text_content") or _take(slots, "text") or "").strip()
    if text_content:
        parts.append(
            f'Chinese characters "{text_content}" visibly rendered on the surface '
            'and repeated as a hand-written annotation label beside the panel, '
            'accurate strokes, correctly spelled, no gibberish lettering')
    material = _take(slots, "material")
    if material:
        parts.append(f"material & color: {material}")
    if category == "bond":
        interaction = _take(slots, "interaction")
        parts.append(f"interaction: {interaction or 'held and used by its owner'}")
    if category == "ambient" and not design_sheet:
        # 环境氛围道具在旧通道里要"虚化融进环境"；设计图模式必须主体清晰、居中可读，
        # 否则连轮廓都画不清（面板/标注全部失效）
        parts.append("worn aged patina, shallow depth of field, background blurred, "
                     "blended into environment")
    if not design_sheet:
        parts.append(PROP_SPEC)
    if lifelike:
        parts.append(lifelike_tokens(preset_key, human=False))
    from .style_vocab import style_vocab_positive
    parts.append(style_vocab_positive(preset_key, kinds=("style",)))
    parts.append(quality_suffix(preset_key, human=False))
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
            # 首帧只画一个瞬间："A before B" 会被画成上下两格同样的脸（2026-11-26 s1 现场）
            parts.append(single_moment(v) if key == "subject_action" else v)
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
    parts.append(quality_suffix(preset_key, human=bool(char_looks)))
    return ", ".join(p for p in parts if p)
