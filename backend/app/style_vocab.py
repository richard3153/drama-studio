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
