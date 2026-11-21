"""风格词库（2026-11-22 新增）：按风格锁挂载领域提示词包。

方法论来源（网络搜索综合）：
- 动漫系：Danbooru 词系对动漫特化模型（Animagine/Illustrious 等）远比自然语句有效——
  cel shading / clean lineart / screentone / speed lines / flat colors 这类短标签，
  且必须配「禁摄影词」负面（photorealistic 会把动漫模型拉向中间态脏画风）。
- 仙侠/国风系：xianxia / flowing immortal robes / spiritual energy aura / cloud sea /
  glowing talisman runes——服饰飘逸感+灵气特效+山水意境三段式（AI Style Atlas /
  国风词库方法论：服饰具体、场景有氛围、风格定调）。
- 特效词库（VFX prompt formula）：特效=颜色+形状+粒子+动势四要素
  （glowing blue energy orb, sparks, pulsing light），氛围粒子（dust/petals/mist）
  是低成本高级感的关键。
- 3D 系：subsurface scattering / raytraced reflections / volumetric light。

结构：FAMILY_VOCAB（族级兜底，按 style_family）+ PRESET_VOCAB（风格级覆盖，
如 xianxia 属 paint 族但词库完全不同）。
每包四类：style（风格锚）/ atmosphere（氛围）/ fx（特效）/ negative（族专属负面）。
"""
from __future__ import annotations

FAMILY_VOCAB: dict[str, dict[str, list[str]]] = {
    "anime": {
        "style": ["anime screencap", "cel shading", "clean lineart", "flat colors",
                  "expressive eyes with highlights", "soft bloom on highlights"],
        "atmosphere": ["painted background", "stylized dramatic lighting"],
        "fx": ["speed lines on fast motion", "glowing particle effects",
               "light rays through openings"],
        "negative": ["photorealistic, photograph, realistic skin texture, 3d render"],
    },
    "3d": {
        "style": ["stylized 3D render", "soft global illumination", "PBR materials",
                  "subtle subsurface scattering"],
        "atmosphere": ["volumetric light", "soft ambient occlusion"],
        "fx": ["volumetric god rays", "floating dust particles", "soft glow effects"],
        "negative": ["flat 2d drawing, cel shading, ink sketch"],
    },
    "paint": {
        "style": ["painterly brushwork", "textured pigment", "expressive strokes"],
        "atmosphere": ["poetic negative space", "misty layered depth"],
        "fx": ["drifting petals", "drifting cloud wisps", "ink-wash gradients"],
        "negative": ["photograph, hyperrealistic photo texture"],
    },
    "photo": {
        # 写实族质感词已由 QUALITY_SUFFIX/lifelike 承担，这里只补氛围与特效词
        "style": [],
        "atmosphere": ["atmospheric haze", "natural volumetric light"],
        "fx": ["drifting dust particles in light beams", "subtle lens flare"],
        "negative": ["anime, cartoon, cel shading, illustration"],
    },
}

# 风格级覆盖（命中即整包替换族兜底）
PRESET_VOCAB: dict[str, dict[str, list[str]]] = {
    "xianxia": {
        "style": ["xianxia fantasy aesthetic", "flowing immortal robes with wide sleeves",
                  "ink-wash undertones", "ancient Chinese architecture details"],
        "atmosphere": ["sea of clouds and misty peaks", "ethereal immortal realm",
                      "moonlit pavilion glow"],
        "fx": ["spiritual energy aura", "glowing talisman runes",
               "sword qi light trails", "floating glowing petals",
               "drifting cloud wisps", "soft spirit-fire glow"],
        "negative": ["photorealistic photograph, modern clothing, western fantasy armor"],
    },
    "guofeng_ink": {
        "style": ["Chinese ink wash painting", "five shades of ink",
                  "flying-white brush strokes", "generous negative space"],
        "atmosphere": ["misty mountains and water", "minimal poetic composition"],
        "fx": ["ink splatter dynamics", "bleeding ink edges", "brush gradient washes"],
        "negative": ["photorealistic photograph, saturated neon colors"],
    },
    "gongbi": {
        "style": ["gongbi meticulous painting", "fine ink outlines",
                  "mineral pigment layering", "silk scroll texture"],
        "atmosphere": ["ornate decorative composition", "classical elegance"],
        "fx": ["gold leaf accents", "delicate pattern details"],
        "negative": ["photorealistic photograph, loose sketchy brushwork"],
    },
    "guochao": {
        "style": ["guochao illustration style", "bold flat shapes with traditional motifs",
                  "vibrant red-gold palette accents"],
        "atmosphere": ["festive graphic energy", "modern-traditional fusion"],
        "fx": ["stylized auspicious cloud patterns", "decorative light bursts"],
        "negative": ["photorealistic photograph"],
    },
    "cyberpunk": {
        "style": ["cyberpunk aesthetic", "neon-lit night city", "high-tech low-life details"],
        "atmosphere": ["wet asphalt reflections", "atmospheric fog with neon spill"],
        "fx": ["holographic UI overlays", "neon glow and rim light",
               "electric arcs", "drifting illuminated particles"],
        "negative": ["rural pastoral setting, soft pastel palette"],
    },
    "steampunk": {
        "style": ["steampunk aesthetic", "brass gears and riveted copper", "victorian machinery"],
        "atmosphere": ["coal haze and warm lamplight", "workshop clutter"],
        "fx": ["steam bursts", "glowing pressure gauges", "sparks from mechanisms"],
        "negative": ["sleek modern minimalism"],
    },
    "film_noir": {
        "style": ["film noir aesthetic", "high contrast black and white", "hard shadows"],
        "atmosphere": ["smoky haze", "venetian blind light slats", "rain-slicked streets"],
        "fx": ["cigarette smoke wisps", "dramatic chiaroscuro shadows"],
        "negative": ["bright cheerful palette, flat even lighting"],
    },
    "hk_retro": {
        "style": ["1990s Hong Kong film look", "anamorphic widescreen feel",
                  "teal-orange grade with warm tungsten"],
        "atmosphere": ["neon street signs in rain", "crowded urban night"],
        "fx": ["practical neon glow", "smoky bar haze"],
        "negative": ["modern minimalist interiors"],
    },
    "ghibli": {
        "style": ["whimsical hand-painted animation look", "painterly backgrounds",
                  "warm natural palette"],
        "atmosphere": ["gentle diffuse daylight", "lush lived-in nature"],
        "fx": ["floating pollen and petals", "soft wind-blown grass motion"],
        "negative": ["photorealistic photograph, harsh neon lighting"],
    },
    "manga_bw": {
        "style": ["black and white manga panel", "screentone dot shading",
                  "bold ink lines", "heavy ink blacks"],
        "atmosphere": ["high contrast dramatic framing"],
        "fx": ["radial speed lines", "impact frame flashes", "halftone gradients"],
        "negative": ["full color, photorealistic photograph"],
    },
    "korean_webtoon": {
        "style": ["webtoon color style", "clean semi-painterly rendering",
                  "soft gradient shading"],
        "atmosphere": ["trendy urban or romantic lighting"],
        "fx": ["soft bloom highlights", "sparkle accents on emotion beats"],
        "negative": ["rough sketch lines, photorealistic photograph"],
    },
    "chibi_q": {
        "style": ["chibi proportions, big head small body", "thick clean outlines",
                  "simple flat colors"],
        "atmosphere": ["cute rounded shapes", "playful bright palette"],
        "fx": ["sparkle and star accents", "bouncy motion smears"],
        "negative": ["realistic anatomy, photorealistic photograph"],
    },
    "pixel_art": {
        "style": ["16-bit pixel art", "visible pixel grid", "limited palette with dithering"],
        "atmosphere": ["retro console game aesthetic"],
        "fx": ["pixel sparkle effects", "parallax background layers"],
        "negative": ["smooth anti-aliased rendering, photorealistic photograph"],
    },
    "american_comic": {
        "style": ["western comic book art", "bold inking", "halftone print texture",
                  "dynamic foreshortening"],
        "atmosphere": ["high contrast action lighting"],
        "fx": ["impact bursts", "action motion lines"],
        "negative": ["soft anime pastel palette"],
    },
    "synthwave": {
        "style": ["synthwave aesthetic", "chrome gradients", "sunset grid horizon"],
        "atmosphere": ["retro-futuristic neon dusk"],
        "fx": ["glowing wireframe grid", "neon laser lines", "scanline shimmer"],
        "negative": ["natural daylight realism"],
    },
    "game_cg": {
        "style": ["AAA game cinematic CG", "raytraced reflections", "detailed material shaders"],
        "atmosphere": ["epic scale environment lighting", "volumetric fog"],
        "fx": ["volumetric god rays", "ember particles", "energy glow effects"],
        "negative": ["flat cel shading, rough sketch"],
    },
    "pixar_3d": {
        "style": ["family-friendly stylized 3D animation", "appealing rounded shapes",
                  "soft subsurface scattering skin"],
        "atmosphere": ["warm inviting key light", "clean appealing color harmony"],
        "fx": ["soft sparkle particles", "bouncy squash-stretch energy"],
        "negative": ["photorealistic photograph, gritty realism"],
    },
    "guofeng_3d": {
        "style": ["Chinese fantasy 3D render", "guofeng ornament detail",
                  "soft cel-leaning shading on 3D forms"],
        "atmosphere": ["immortal mountain vistas", "flowing silk and cloud mist"],
        "fx": ["spiritual energy ribbons", "glowing rune circles", "drifting petals"],
        "negative": ["photorealistic photograph"],
    },
    "disney_2d": {
        "style": ["classic hand-drawn feature animation look", "expressive squash-and-stretch shapes",
                  "rich painted backgrounds"],
        "atmosphere": ["storybook warm lighting"],
        "fx": ["magical sparkle trails", "exaggerated motion flourishes"],
        "negative": ["photorealistic photograph"],
    },
    "anime_soft": {
        "style": ["soft anime illustration", "delicate lineart", "pastel palette",
                  "light bloom"],
        "atmosphere": ["gentle warm glow", "airy soft focus background"],
        "fx": ["soft sparkle particles", "petals drifting"],
        "negative": ["hard noir shadows, photorealistic photograph"],
    },
    "anime_2d": {
        "style": ["modern TV anime style", "3-tone cel shading", "thin clean lineart"],
        "atmosphere": ["crisp highlights", "stylized directional lighting"],
        "fx": ["speed lines on fast motion", "glowing particle effects"],
        "negative": ["photorealistic photograph, realistic skin texture, 3d render"],
    },
    "ukiyoe": {
        "style": ["ukiyo-e woodblock print", "flat color planes with bold outlines",
                  "wood grain texture"],
        "atmosphere": ["stylized wave and cloud motifs"],
        "fx": ["stylized wind swirls", "carved line accents"],
        "negative": ["photorealistic photograph, 3d render"],
    },
    "thick_paint": {
        "style": ["thick impasto digital painting", "visible bold brushstrokes",
                  "rich layered colors"],
        "atmosphere": ["dramatic painterly light"],
        "fx": ["paint splatter energy", "palette-knife texture strokes"],
        "negative": ["flat vector shapes, photorealistic photograph"],
    },
    "watercolor": {
        "style": ["watercolor painting", "bleeding wet edges", "translucent washes",
                  "visible paper texture"],
        "atmosphere": ["soft organic edges", "airy light atmosphere"],
        "fx": ["color bloom accidents", "granulating pigment texture"],
        "negative": ["hard digital outlines, photorealistic photograph"],
    },
    "jp_fresh": {
        "style": ["fresh Japanese film look", "airy high-key exposure", "clean gentle palette"],
        "atmosphere": ["soft daylight windows", "breezy summer mood"],
        "fx": ["gentle lens flare", "dust motes in sunlight"],
        "negative": ["heavy noir shadows"],
    },
    "fashion_edito": {
        "style": ["high fashion editorial photography", "controlled studio styling",
                  "graphic composition"],
        "atmosphere": ["sculpted directional light"],
        "fx": ["subtle wind on fabric"],
        "negative": ["anime, cartoon, illustration"],
    },
    "documentary": {
        "style": ["documentary photography feel", "available-light realism",
                  "unposed candid framing"],
        "atmosphere": ["authentic location atmosphere"],
        "fx": ["natural ambient particles"],
        "negative": ["anime, cartoon, dramatic studio lighting"],
    },
    "cinematic_film": {
        "style": ["cinematic film still", "anamorphic widescreen framing",
                  "teal-orange color grading"],
        "atmosphere": ["motivated practical lighting", "atmospheric depth"],
        "fx": ["subtle anamorphic lens flare", "drifting dust in light beams"],
        "negative": ["flat tv drama lighting, anime"],
    },
    "shonen": {
        "style": ["shonen action anime style", "dynamic composition", "saturated colors",
                  "high contrast"],
        "atmosphere": ["intense battle energy"],
        "fx": ["radial speed lines", "impact sparks", "energy burst shockwaves"],
        "negative": ["photorealistic photograph"],
    },
}


def _pack(preset_key: str) -> dict[str, list[str]]:
    from .style_presets import style_family   # 延迟导入，避免与 style_presets 循环
    p = PRESET_VOCAB.get((preset_key or "").strip())
    if p:
        return p
    return FAMILY_VOCAB.get(style_family(preset_key), FAMILY_VOCAB["photo"])


def style_vocab_positive(preset_key: str, kinds: tuple = ("style", "atmosphere", "fx")) -> str:
    """风格词库正向 token 串。kinds 控制取哪几类：角色三视图只要 style（特效词
    会让设定图出现剑气/灵光，污染参考图），场景/镜头取全量。"""
    pack = _pack(preset_key)
    parts = []
    for k in kinds:
        parts.extend(x for x in pack.get(k, []) if x)
    return ", ".join(parts)


def style_vocab_negative(preset_key: str) -> str:
    """风格词库负面 token 串（防风格串味：动漫禁摄影词、写实禁动漫词等）。"""
    return ", ".join(x for x in _pack(preset_key).get("negative", []) if x)


# ============================================================
# 题材词库（GENRE_VOCAB，2026-11-22 新增）：红果短剧爆款反向解析。
# 与风格词库正交：风格锁管「画什么画风」，题材锁管「画面像不像这个题材的爆款」。
# 数据来源（网络搜索）：
# - 母题分布（电影界 2026-10 全平台统计）：复仇 1053 部 > 隐身份 526 > 豪门言情 520
#   > 奇幻超自然 425 > 强势女主 412 > 契约婚姻 345 > 再度逆袭 334 > 草根翻身 296；
# - 红果官方激励六大品类：玄幻仙侠/历史古代/都市玄幻/悬疑犯罪/都市种田/奇幻脑洞；
# - 800 部红果剧名高频词：重生/逆袭/闪婚/总裁/战神/神医/打脸/赘婿/团宠；
# - 光比公式（抖音 AI 短剧方法论）：甜宠 1-2:1 高调柔光 / 剧情 3:1 中调 /
#   悬疑复仇 6:1 低调侧逆光 / 权谋伦勃朗 10:1 三角光 / 惊悚剪影 16:1+；
# - 场景语言（竖店/横店基地实测）：总裁家黑白灰轻奢+真皮沙发+石纹墙、
#   豪门「亿级观感」双层楼梯别墅、灰姑娘低顶出租屋、年代厂区暖钨丝。
# 每包五类：setting（典型场景）/ wardrobe（服化道）/ mood（光比情绪）/
#           hooks（名场面视觉钩子）/ negative（题材反串味）。
# ============================================================
GENRE_VOCAB: dict[str, dict[str, list[str]]] = {
    # ---------- 男频 ----------
    "war_god": {  # 战神归来/隐身份强者（男频第一大母题）
        "setting": ["opulent banquet hall with chandelier", "corporate boardroom",
                    "underground fight club", "luxury hotel lobby"],
        "wardrobe": ["military-style long coat with insignia", "sharp tailored black suit",
                     "subtle medal ribbon and scar details"],
        "mood": ["low-key dramatic lighting with deep shadows", "hero reveal backlight",
                 "cold steel-blue grade with warm highlight accents"],
        "hooks": ["low-angle hero entrance stepping out of a black car",
                  "slow-motion crowd turning their heads in awe",
                  "insignia or ring close-up reveal", "former bullies frozen mid-sneer"],
        "negative": ["childish cartoonish props, playful bright pastel set dressing"],
    },
    "zhuixu": {  # 赘婿逆袭
        "setting": ["wealthy family mansion dining hall", "cramped in-laws living room",
                    "modern corporate office"],
        "wardrobe": ["worn grey hoodie (hidden identity phase)",
                     "transformation into tailored designer suit",
                     "cheap slippers contrast with luxury surroundings"],
        "mood": ["humiliating cool fluorescent tone shifting to triumphant warm backlight",
                 "medium contrast with strong single-source key"],
        "hooks": ["contract torn in half close-up", "family heirloom ring reveal",
                  "in-laws' shocked gasping reaction shots",
                  "luxury motorcade arriving at humble doorway"],
        "negative": ["openly heroic heroic costume, fantasy armor"],
    },
    "shenhao": {  # 神豪/都市异能
        "setting": ["penthouse with skyline view", "supercar showroom",
                    "luxury shopping mall atrium", "private jet cabin"],
        "wardrobe": ["designer streetwear with luxury watch",
                     "limited sneakers and statement accessories"],
        "mood": ["neon night reflections on wet streets", "high-contrast glamour lighting",
                 "rich gold-teal commercial grade"],
        "hooks": ["black metal credit card placed on table", "cash raining down",
                  "luxury goods macro beauty shots", "envious onlookers whispering"],
        "negative": ["shabby rundown environment, poor rural setting"],
    },
    "dushi_xuanhuan": {  # 都市玄幻/天师捉妖
        "setting": ["old taoist temple with incense smoke", "modern city night alley",
                    "haunted old apartment", "antique shop interior"],
        "wardrobe": ["taoist robe hem peeking under modern jacket",
                     "brass compass and cinnabar brush props"],
        "mood": ["cold blue night with golden talisman glow accents",
                 "flickering practical lights, uneasy green casts"],
        "hooks": ["glowing yellow talisman paper burning with spirit flame",
                  "evil aura wisps recoiling from light", "brass bell ringing close-up"],
        "negative": ["pastoral idyllic countryside, bright daylight cheerfulness"],
    },
    "xuanhuan_xianxia": {  # 玄幻仙侠（漫剧第一大品类，配合 xianxia 风格锁）
        "setting": ["immortal sect hall with floating platforms",
                    "thunder tribulation peak", "spirit beast forest",
                    "cultivation cave with glowing pools"],
        "wardrobe": ["sect disciple robes with jade belt", "elder robes with cloud patterns"],
        "mood": ["awe-inspiring vast scale lighting", "storm light before breakthrough"],
        "hooks": ["cultivation aura burst with ground-crack shockwave",
                  "giant spirit beast silhouette behind mist",
                  "lightning tribulation column from dark clouds",
                  "level-up light pillar enveloping the body"],
        "negative": ["modern city buildings, everyday casual clothing"],
    },
    "lishi_quanmou": {  # 历史权谋/家国
        "setting": ["imperial court hall with dragon pillars", "war military tent",
                    "candle-lit night study with maps"],
        "wardrobe": ["historical court robes with rank embroidery", "lamellar armor",
                     "scholar robe with hair crown"],
        "mood": ["Rembrandt triangle lighting at 10:1 contrast",
                 "candlelight pools in vast dark halls"],
        "hooks": ["imperial edict scroll unrolling close-up",
                  "chess pieces being placed as power metaphor",
                  "kneeling ministers rows in depth", "secret letter by candlelight"],
        "negative": ["modern furniture, contemporary clothing"],
    },
    "niandai": {  # 年代逆袭（80/90 年代）
        "setting": ["1980s state factory dormitory", "old street with bicycles",
                    "factory office with enamel mugs", "family home with checkered tablecloth"],
        "wardrobe": ["era-accurate worker jacket and padded coat",
                     "twin braids and plain cotton dress"],
        "mood": ["warm tungsten nostalgia grade", "sunlit dust in old rooms",
                 "faded film-color palette"],
        "hooks": ["bicycle streams on morning street", "black-and-white TV glow",
                  "grain ration tickets and enamel basin close-ups",
                  "family confrontation around dinner table"],
        "negative": ["smartphones, modern appliances, contemporary fashion"],
    },
    "xuanyi": {  # 悬疑犯罪
        "setting": ["interrogation room with single lamp", "rain-slick night alley",
                    "taped-off crime scene", "evidence-board covered wall"],
        "wardrobe": ["dark trench coat", "plain detective casual wear"],
        "mood": ["low-key 6:1 side backlight", "cold desaturated grade",
                 "hard chiaroscuro with deep blacks"],
        "hooks": ["flickering fluorescent lamp", "evidence bag close-up",
                  "silhouette standing in doorway", "rain streaks on window glass"],
        "negative": ["bright cheerful pastel palette, comedy props"],
    },
    "zhongtian": {  # 都市种田/乡村致富
        "setting": ["sunlit village farmland", "farmhouse courtyard with harvest",
                    "rural market stalls", "greenhouse rows"],
        "wardrobe": ["plain practical rural workwear", "straw hat and rolled sleeves"],
        "mood": ["golden-hour warm abundance", "fresh morning haze over fields"],
        "hooks": ["overflowing harvest baskets close-up", "chickens and livestock bustle",
                  "first money bundle counted at market", "villagers' amazed gathering"],
        "negative": ["neon cyberpunk city, luxury penthouse"],
    },
    # ---------- 女频 ----------
    "zongcai": {  # 霸总甜宠/闪婚契约（女频基本盘）
        "setting": ["glass-walled CEO office overlooking city", "luxury penthouse living room",
                    "grand wedding venue", "five-star hotel suite"],
        "wardrobe": ["haute couture three-piece suit", "elegant evening dress",
                     "silky slip dress and robe details"],
        "mood": ["bright soft high-key glamour at 1-2:1 light ratio",
                 "honey-warm romantic grade", "window sheer diffused daylight"],
        "hooks": ["wall-slam silhouette shadow", "marriage contract papers on desk",
                  "diamond ring sparkle close-up", "jealous rival reaction cutaway"],
        "negative": ["grimy slum environment, violent gore"],
    },
    "danvzhu": {  # 大女主复仇/打脸虐渣
        "setting": ["luxury banquet confrontation", "boardroom takeover scene",
                    "rooftop at dusk", "rain-soaked street outside mansion"],
        "wardrobe": ["sharp-shouldered power suit", "scarlet evening gown",
                     "red lipstick and minimal jewelry"],
        "mood": ["cold elegant grade with dramatic rim light",
                 "strong contrast confrontation lighting"],
        "hooks": ["slow-motion entrance with hair flip", "champagne glass set down sharply",
                  "exposed evidence on projector screen",
                  "former betrayers' faces draining of color"],
        "negative": ["damsel-in-distress helpless pose, frumpy plain wardrobe"],
    },
    "gongdou": {  # 宫斗重生
        "setting": ["imperial palace chamber with silk drapes", "throne hall",
                    "palace garden with plum blossoms", "cold-side palace courtyard"],
        "wardrobe": ["court concubine dress with gold hairpins", "phoenix embroidery details",
                     "formal audience robes"],
        "mood": ["candle-lit intrigue with deep red-gold palette",
                 "shaft of light through lattice window"],
        "hooks": ["poisoned tea ripple close-up", "kneeling palace maids in rows",
                  "phoenix hairpin glinting ominously",
                  "rebirth flashback desaturation contrast"],
        "negative": ["modern clothing, contemporary architecture"],
    },
    "mengbao": {  # 萌宝/团宠甜宠
        "setting": ["warm bright family home", "kindergarten classroom",
                    "sunny park playground", "cozy bakery cafe"],
        "wardrobe": ["matching family casual outfits", "adorable kids' designer clothes"],
        "mood": ["airy high-key daylight", "soft pastel warm grade"],
        "hooks": ["cute kid tugging parent's sleeve", "heart-warming family meal",
                  "surprise gift box reveal", "tiny matching accessories close-up"],
        "negative": ["dark horror atmosphere, violence"],
    },
    "qihuan_naodong": {  # 奇幻脑洞/系统流
        "setting": ["modern city overlaid with holographic interface",
                    "ordinary apartment with glowing system portal"],
        "wardrobe": ["everyday casual clothes with glowing tech accessory"],
        "mood": ["cyan-magenta system glow against ordinary lighting",
                 "semi-transparent UI reflections on face"],
        "hooks": ["floating translucent system panel with quest text",
                  "level-up golden glow sweep", "inventory pop-up cards in air",
                  "countdown timer hologram"],
        "negative": ["fully fantasy medieval world, no-system setting cues"],
    },
}

GENRE_LABELS: dict[str, str] = {
    "war_god": "战神归来/隐身份强者", "zhuixu": "赘婿逆袭", "shenhao": "神豪/都市异能",
    "dushi_xuanhuan": "都市玄幻/天师捉妖", "xuanhuan_xianxia": "玄幻仙侠",
    "lishi_quanmou": "历史权谋", "niandai": "年代逆袭", "xuanyi": "悬疑犯罪",
    "zhongtian": "种田致富", "zongcai": "霸总甜宠/闪婚", "danvzhu": "大女主复仇/打脸",
    "gongdou": "宫斗重生", "mengbao": "萌宝团宠", "qihuan_naodong": "奇幻脑洞/系统流",
}


def style_genre_positive(genre_key: str,
                         kinds: tuple = ("setting", "wardrobe", "mood", "hooks")) -> str:
    """题材词库正向 token 串。默认全量（setting+wardrobe+mood+hooks）；
    镜头层可按需收缩，如只要 mood+hooks。"""
    pack = GENRE_VOCAB.get((genre_key or "").strip())
    if not pack:
        return ""
    parts = []
    for k in kinds:
        parts.extend(x for x in pack.get(k, []) if x)
    return ", ".join(parts)


def style_genre_negative(genre_key: str) -> str:
    """题材词库负面 token 串（防题材串味：霸总剧禁贫民窟、种田剧禁赛博都市等）。"""
    pack = GENRE_VOCAB.get((genre_key or "").strip())
    if not pack:
        return ""
    return ", ".join(x for x in pack.get("negative", []) if x)


def combined_shot_vocab(preset_key: str, genre_key: str,
                        genre_kinds: tuple = ("mood", "hooks")) -> str:
    """风格词库 + 题材词库合并成镜头层 vocab 串（模板 {{ vocab }} 单变量注入）。
    题材默认只取 mood+hooks——setting/wardrobe 由场景图与角色图承担，
    镜头里重复写会让提示词臃肿稀释权重。"""
    parts = [style_vocab_positive(preset_key),
             style_genre_positive(genre_key, genre_kinds)]
    return ", ".join(x for x in parts if x)
