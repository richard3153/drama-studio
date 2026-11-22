"""特效镜提示词库（#81）：特效镜自动识别 + 特效编排词注入，与 action_vocab 同构。

背景：shots 表有 vfx_type/vfx_note 字段，拆解可以标注，但此前从不进提示词——
纯死数据。短剧特效镜（金光护体/慢镜重击/雨夜对峙/闪回）是题材核心名场面，
但通用提示词只会画出一个普通站位。

设计要点：
- 识别双通道：①拆解显式标注（vfx_type/vfx_note）②关键词兜底扫描
  （subject_action/blocking/atmosphere/sfx/dialogue）。
- 允许多特效并存（雨夜+闪电），但封顶 2 个——特效词堆 3 个以上画面必糊。
- image 词只写"静帧能画出来的特效状态"（金光环绕/雨丝/光柱），video 词写
  "动态编排"（触发时机+环境反应+衰减），遵循 Wan I2V 原则：描述可见结果。
- 与环境互动挂钩：特效必须作用于环境（雨打湿肩头/金光照亮地面/风掀起衣摆），
  否则模型出"贴纸感"特效。
- 平台安全：不加血液类特效词（红果红线）；金光/神光类避免宗教符号。
"""
from __future__ import annotations

# 每类特效的触发关键词（短语级，防误中）。中文为主（拆解产物是中文）。
_VFX_WORDS: dict[str, tuple[str, ...]] = {
    "slow_motion": (
        "慢动作", "慢镜", "慢放", "放慢", "子弹时间", "时间放缓",
        "slow motion", "slow-motion", "bullet time", "slowmo",
    ),
    "time_freeze": (
        "时间静止", "时间冻结", "定格", "凝固", "瞬间静止",
        "time freeze", "frozen in time", "freeze frame", "stands still",
    ),
    "divine_glow": (
        "金光", "神光", "圣光", "金芒", "光芒万丈", "护体光", "灵光", "佛光",
        "golden light", "divine light", "holy glow", "radiant aura", "glowing aura",
    ),
    "energy_burst": (
        "气浪", "罡气", "气劲", "掌风", "拳风", "能量爆发", "冲击波", "气势爆发",
        "energy burst", "shockwave of power", "blasting energy", "air shockwave",
    ),
    "explosion_fire": (
        "爆炸", "火光", "烈焰", "燃烧", "火海", "起火", "爆开",
        "explosion", "explodes", "fireball", "blaze", "engulfed in fire",
    ),
    "lightning_storm": (
        "闪电", "雷鸣", "雷击", "惊雷", "雷电",
        "lightning", "thunder", "thunderbolt",
    ),
    "rain_storm": (
        "暴雨", "大雨", "雨夜", "淋雨", "雨中", "细雨",
        "heavy rain", "downpour", "in the rain", "rainstorm",
    ),
    "fog_smoke": (
        "浓雾", "烟雾", "迷雾", "烟尘", "云雾", "雾气",
        "thick fog", "smoke", "mist", "haze",
    ),
    "petals_snow": (
        "花瓣", "飘雪", "落雪", "樱花", "落叶", "漫天飞",
        "falling petals", "cherry blossom", "snow falling", "drifting petals",
    ),
    "light_rays": (
        "丁达尔", "光柱", "光束", "光线穿透", "耶稣光", "透过窗",
        "god rays", "volumetric light", "light beams", "crepuscular rays",
    ),
    "wind_gust": (
        "狂风", "风起", "风卷", "衣袂翻飞", "大风", "罡风",
        "strong wind", "wind gust", "cloak billowing",
    ),
    "shatter_debris": (
        "碎裂", "粉碎", "玻璃碎", "镜面碎", "崩裂", "炸裂",
        "shatter", "shattering glass", "cracking", "bursts into pieces",
    ),
    "water_splash": (
        "水花", "浪花", "溅起", "泼水", "落水", "水中",
        "water splash", "splashing water", "waves crash",
    ),
    "flashback_tone": (
        "回忆", "闪回", "往事", "记忆", "当年的", "回想",
        "flashback", "memory", "reminisce",
    ),
}

# 显式 vfx_type 值 → 词库 key（拆解 LLM 可能直接给英文枚举）
_VFX_TYPE_MAP = {
    "slow_motion": "slow_motion", "time_freeze": "time_freeze",
    "glow": "divine_glow", "divine_glow": "divine_glow",
    "energy": "energy_burst", "energy_burst": "energy_burst",
    "explosion": "explosion_fire", "fire": "explosion_fire",
    "lightning": "lightning_storm", "rain": "rain_storm",
    "fog": "fog_smoke", "smoke": "fog_smoke",
    "petals": "petals_snow", "snow": "petals_snow",
    "light_rays": "light_rays", "wind": "wind_gust",
    "shatter": "shatter_debris", "water": "water_splash",
    "flashback": "flashback_tone",
}

_MAX_KEYS = 2   # 特效词封顶：3 个以上特效叠一个镜，画面必糊

_VFX_ORDER = ("slow_motion", "time_freeze", "divine_glow", "energy_burst",
              "explosion_fire", "lightning_storm", "rain_storm", "fog_smoke",
              "petals_snow", "light_rays", "wind_gust", "shatter_debris",
              "water_splash", "flashback_tone")


def detect_vfx(vfx_type: str = "", vfx_note: str = "", *texts: str) -> list[str]:
    """特效镜识别：显式 vfx_type 优先，vfx_note 与正文关键词兜底。
    返回命中的特效 key 列表（封顶 2 个，按 _VFX_ORDER 稳定排序）。"""
    keys: list[str] = []
    vt = (vfx_type or "").strip().lower()
    if vt and vt != "none":
        mapped = _VFX_TYPE_MAP.get(vt)
        if mapped:
            keys.append(mapped)
    blob = " ".join(t or "" for t in ((vfx_note,) + texts)).lower()
    if blob.strip():
        for key in _VFX_ORDER:
            if key in keys:
                continue
            if len(keys) >= _MAX_KEYS:
                break
            if any(w in blob for w in _VFX_WORDS[key]):
                keys.append(key)
    # 稳定排序：同类输出顺序确定，提示词回归测试可断言
    keys = [k for k in _VFX_ORDER if k in keys]
    return keys[:_MAX_KEYS]


# ---------- 编排词（kind: image=静帧特效状态 / video=动态特效编排） ----------

VFX_VOCAB = {
    "slow_motion": {
        "image": "dynamic suspended-in-motion pose, cloth and hair mid-swing, airborne droplets and dust frozen around the subject",
        "video": "brief slow-motion beat at the peak of the action, cloth and hair drifting in slowed time, droplets and dust suspended mid-air, then time snaps back to full speed",
    },
    "time_freeze": {
        "image": "subject frozen mid-motion, surrounding elements suspended still, subtle glow outlining the subject",
        "video": "the world freezes around the subject mid-action, dust and droplets hang motionless in the air, camera slowly orbits the frozen moment",
    },
    "divine_glow": {
        "image": "golden radiant aura enveloping the subject, warm rim light on face and shoulders, ground lit by reflected golden glow",
        "video": "golden light builds around the subject, radiant glow flares outward and illuminates the surroundings, dust motes sparkle in the light",
    },
    "energy_burst": {
        "image": "visible shockwave ripple distorting the air around the subject, dust and loose debris blasted outward",
        "video": "an energy shockwave bursts outward from the subject, air visibly ripples, dust and loose papers blast away, nearby cloth and hair whip in the blast",
    },
    "explosion_fire": {
        "image": "fiery blast in the background, orange rim light on the subject, embers and smoke drifting",
        "video": "a blast flares in the background, orange firelight flickers across the subject, embers and thin smoke drift through the frame",
    },
    "lightning_storm": {
        "image": "a lightning bolt splitting the dark sky, harsh blue-white flash lighting the whole scene",
        "video": "lightning flashes and briefly silhouettes everything in blue-white, thunder-lit clouds flicker overhead, a second dimmer flash follows",
    },
    "rain_storm": {
        "image": "heavy rain streaks visible against the light, wet hair and soaked shoulders, raindrops bouncing off the ground",
        "video": "steady heavy rain falls through the whole shot, raindrops splash on shoulders and the wet ground, damp cloth clings and drips",
    },
    "fog_smoke": {
        "image": "low fog rolling across the ground, distant figures fading into haze, soft volumetric depth",
        "video": "fog drifts slowly across the frame, silhouettes emerge from and dissolve back into the haze, smoke curls upward",
    },
    "petals_snow": {
        "image": "petals drifting through the air, several in soft focus in the foreground, one landing on the subject's shoulder",
        "video": "petals drift and swirl gently through the frame, catching the light, a few land and slide off the subject's shoulder",
    },
    "light_rays": {
        "image": "volumetric light beams cutting through the window, dust motes glowing inside the light shafts",
        "video": "volumetric light shafts sweep slowly across the room, dust motes drift and sparkle inside the beams as they pass the subject",
    },
    "wind_gust": {
        "image": "strong wind, cloth and hair whipping hard to one side, loose papers and dust blown through the air",
        "video": "a gust surges through, cloth and hair whip sideways, loose papers and dust swirl across the frame and settle",
    },
    "shatter_debris": {
        "image": "glass shattering mid-air, sharp shards and glittering fragments suspended around the subject",
        "video": "the surface shatters outward, shards glitter as they fly and rain down, dust puffs out from the impact point",
    },
    "water_splash": {
        "image": "water splashing around the subject, droplets arcing mid-air, wet reflections on the ground",
        "video": "water splashes up around the subject, droplets arc and catch the light, ripples spread outward and settle",
    },
    "flashback_tone": {
        "image": "warm desaturated sepia tone, soft halation glow, hazy dreamlike softness, gentle vignette",
        "video": "warm faded sepia grade with soft halation, hazy dreamlike glow breathing gently, slow tender pacing like a memory",
    },
}


def vfx_tokens(keys: list[str], kind: str) -> str:
    """多特效编排词拼接（封顶 2，词库层已保证）。"""
    parts = [VFX_VOCAB[k][kind] for k in keys if k in VFX_VOCAB]
    return ", ".join(p for p in parts if p)
