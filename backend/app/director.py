"""导演台元数据（2026-11-27 对齐 RunningHub RHTV 无限画布的可视化控件）。

RHTV 把"靠提示词碰运气"的地方都做成了按钮/预设：
  · 摄像机控制按钮 —— 景别 / 机位 / 运镜 / 速度 / 焦段 / 焦点 / 转场，点一下即写入
  · 风格库 —— 分类 + 搜索 + 卡片网格，一键套用到项目（不用背长提示词）
  · 预设 —— 运镜/风格组合预设（固定机位、跟随镜头、机械臂环绕…）
  · 人物调节 —— 面部控制 / 姿态调整 / 形象设定 / 妆容调节，分区微调不改整张
这里把这些枚举集中成一份元数据，前端直接渲染成按钮和卡片。

关键约束：每个按钮都必须能落到 shots 表的真实字段上（不能是装饰），
value 一律用 script_service 已认的英文/中文 key，避免再起一套编码。
"""
from .services.script_service import ANGLE_EN, LENS_EN, SHOT_SIZE_EN
from .style_presets import (STYLE_HIDDEN, STYLE_PRESETS, is_style_hidden,
                            style_family, style_sample_path, visible_presets)

# ---------- 摄像机控制 ----------
# 景别：取自 SHOT_SIZE_EN（已带"可见构图后果"锚点，前端只做展示与选择）
SHOT_SIZES = [
    {"v": "远景", "zh": "远景", "hint": "人在环境中很小，环境主导", "group": "景别"},
    {"v": "全景", "zh": "全景", "hint": "全身入画，留出空间余量", "group": "景别"},
    {"v": "中景", "zh": "中景", "hint": "腰部以上，看得清体态", "group": "景别"},
    {"v": "中近景", "zh": "中近景", "hint": "胸部以上，表情清楚", "group": "景别"},
    {"v": "近景", "zh": "近景", "hint": "胸脸占满画面", "group": "景别"},
    {"v": "特写", "zh": "特写", "hint": "脸占满画面，微表情可见", "group": "景别"},
    {"v": "大特写", "zh": "大特写", "hint": "单一细节，浅景深", "group": "景别"},
]

ANGLES = [
    {"v": "平视", "zh": "平视", "hint": "自然的人眼高度", "group": "机位"},
    {"v": "俯拍", "zh": "高角俯拍", "hint": "被观察、无助感", "group": "机位"},
    {"v": "仰拍", "zh": "低角仰拍", "hint": "压迫感、主体强势", "group": "机位"},
    {"v": "过肩", "zh": "过肩", "hint": "观众站在角色身后", "group": "机位"},
    {"v": "斜角", "zh": "倾斜斜角", "hint": "地平线歪 20°，不安", "group": "机位"},
    {"v": "航拍", "zh": "航拍俯瞰", "hint": "正上方，地理关系清楚", "group": "机位"},
    {"v": "POV", "zh": "第一人称POV", "hint": "主观视角，环境贴脸", "group": "机位"},
]

MOVES = [
    {"v": "固定", "zh": "固定机位", "dir": "", "hint": "三脚架静观，靠人物动"},
    {"v": "推", "zh": "推进", "dir": "in", "hint": "逼近主体，情绪收紧"},
    {"v": "拉", "zh": "拉远", "dir": "out", "hint": "退开交代环境"},
    {"v": "横摇", "zh": "横摇", "dir": "left", "hint": "左右扫过，揭示空间"},
    {"v": "竖摇", "zh": "竖摇", "dir": "up", "hint": "上下扫，从脚到脸"},
    {"v": "移", "zh": "平移", "dir": "right", "hint": "轨道平移，保持距离"},
    {"v": "跟", "zh": "跟随", "dir": "in", "hint": "跟着人物走，代入感强"},
    {"v": "升降", "zh": "升降", "dir": "down", "hint": "机位上下，改高低关系"},
    {"v": "环绕", "zh": "环绕", "dir": "", "hint": "绕主体转，空间立体"},
    {"v": "手持", "zh": "手持", "dir": "", "hint": "微抖纪实，紧张真实"},
]

SPEEDS = [
    {"v": "slow", "zh": "慢", "hint": "压抑/凝视/仪式感"},
    {"v": "normal", "zh": "常速", "hint": "默认"},
    {"v": "fast", "zh": "快", "hint": "追逃/冲突"},
    {"v": "whip", "zh": "甩镜", "hint": "暴力切换，配 whip_pan"},
]

LENSES = [
    {"v": "", "zh": "不限", "hint": ""},
    {"v": "24mm", "zh": "24mm 广角", "hint": "空间扩张，边缘畸变"},
    {"v": "35mm", "zh": "35mm", "hint": "自然纪实"},
    {"v": "50mm", "zh": "50mm", "hint": "接近人眼"},
    {"v": "85mm", "zh": "85mm 中长焦", "hint": "压缩背景，脸更好看"},
    {"v": "135mm", "zh": "135mm 长焦", "hint": "强压缩，主体剥离"},
]

FOCUSES = [
    {"v": "none", "zh": "无", "hint": ""},
    {"v": "rack-focus", "zh": "焦点转移", "hint": "从前景拉到主体"},
    {"v": "pull-focus", "zh": "拉焦", "hint": "主体转环境"},
    {"v": "follow-focus", "zh": "跟焦", "hint": "跟住移动主体"},
]

TRANSITIONS = [
    {"v": "", "zh": "默认", "hint": "按场景边界自动"},
    {"v": "hard_cut", "zh": "硬切", "hint": "最常用"},
    {"v": "match_cut", "zh": "相似剪辑", "hint": "形状/动作对位"},
    {"v": "whip_pan", "zh": "甩镜过渡", "hint": "快速摇出摇入"},
    {"v": "object_pass", "zh": "物体遮挡", "hint": "前景物扫过换场"},
    {"v": "light_flash", "zh": "闪白/闪光", "hint": "爆闪切"},
    {"v": "dissolve", "zh": "叠化", "hint": "时间流逝"},
]

# ---------- 镜头预设（RHTV 式"一键专业运镜"） ----------
# 每条 = 一组能直接写进 shots 的字段（+ 可选的光影/氛围建议词）。
SHOT_PRESETS = [
    {"id": "static_observe", "zh": "固定静观", "desc": "三脚架不动，全靠人物表演",
     "shot_size": "中景", "camera_angle": "平视", "camera_move": "固定", "camera_speed": "slow"},
    {"id": "push_in_close", "zh": "缓推特写", "desc": "慢慢逼近脸，情绪收紧",
     "shot_size": "特写", "camera_angle": "平视", "camera_move": "推", "camera_speed": "slow",
     "focal_length": "85mm"},
    {"id": "pull_out_wide", "zh": "拉远交代", "desc": "从人物退开，把环境交出来",
     "shot_size": "全景", "camera_angle": "平视", "camera_move": "拉", "camera_speed": "normal",
     "focal_length": "35mm"},
    {"id": "orbit_hero", "zh": "环绕主角", "desc": "绕人转一圈，立体感最强",
     "shot_size": "中景", "camera_angle": "平视", "camera_move": "环绕", "camera_speed": "slow"},
    {"id": "follow_walk", "zh": "跟随行走", "desc": "跟着人走，代入感",
     "shot_size": "中近景", "camera_angle": "平视", "camera_move": "跟", "camera_speed": "normal",
     "character_path": "walks steadily forward, camera tracks alongside"},
    {"id": "handheld_doc", "zh": "手持纪实", "desc": "微抖真实感，紧张/混乱",
     "shot_size": "中景", "camera_angle": "平视", "camera_move": "手持", "camera_speed": "normal"},
    {"id": "ots_dialogue", "zh": "过肩对话", "desc": "两人戏标配，观众站背后",
     "shot_size": "中近景", "camera_angle": "过肩", "camera_move": "固定", "camera_speed": "slow",
     "focal_length": "50mm"},
    {"id": "low_pressure", "zh": "低角压迫", "desc": "仰拍 + 广角，主角压人一头",
     "shot_size": "中景", "camera_angle": "仰拍", "camera_move": "推", "camera_speed": "slow",
     "focal_length": "24mm"},
    {"id": "high_vulnerable", "zh": "高角俯瞰", "desc": "俯拍，人物显得渺小无助",
     "shot_size": "全景", "camera_angle": "俯拍", "camera_move": "升降", "camera_speed": "slow",
     "focal_length": "35mm"},
    {"id": "aerial_establish", "zh": "航拍全景", "desc": "开场交代地理关系",
     "shot_size": "远景", "camera_angle": "航拍", "camera_move": "移", "camera_speed": "slow"},
    {"id": "whip_transition", "zh": "甩镜转场", "desc": "暴力切换，换场不拖泥带水",
     "shot_size": "中景", "camera_angle": "平视", "camera_move": "横摇", "camera_speed": "whip",
     "transition_in": "whip_pan"},
    {"id": "dutch_unease", "zh": "倾斜不安", "desc": "斜角 + 手持，心神不宁",
     "shot_size": "中近景", "camera_angle": "斜角", "camera_move": "手持", "camera_speed": "slow"},
    {"id": "rack_reveal", "zh": "焦点转移揭示", "desc": "先前景后主体，信息延迟给",
     "shot_size": "中近景", "camera_angle": "平视", "camera_move": "固定", "camera_speed": "slow",
     "focal_length": "85mm", "focus_transition": "rack-focus"},
]

# ---------- 风格库 ----------
def style_library() -> dict:
    """STYLE_PRESETS → 前端风格库（分类 + 卡片 + 示例缩略图）。

    只列 AI 短剧 / AI 漫剧用得上的风格（STYLE_HIDDEN 里的暂不显示，数据仍在）；
    每张卡片的 `thumb` 指向生成的示例图（同一主体同一构图，差异全在风格上），
    图还没生成时 thumb=None，前端退回分类渐变块。
    """
    groups: dict[str, list] = {}
    for key, s in STYLE_PRESETS.items():
        if is_style_hidden(key):
            continue
        has_thumb = style_sample_path(key) is not None
        groups.setdefault(s.get("category", "其他"), []).append({
            "key": key,
            "label": s.get("label", key),
            "family": style_family(key),
            "sample": (s.get("style_lock") or "")[:96],
            "motion": s.get("motion_hint", ""),
            "thumb": f"/api/style-samples/{key}.jpg" if has_thumb else None,
        })
    return {"groups": [{"name": k, "items": v} for k, v in groups.items()],
            "total": len(visible_presets()),
            "hidden_total": len(STYLE_HIDDEN),
            "hidden_note": "另 " + str(len(STYLE_HIDDEN))
                           + " 种（像素/体素/纸张肌理/设计示意类）暂不适用短剧漫剧，未在列表显示"}


# ---------- 人物调节（RHTV「人物调节」：面部/姿态/形象/妆容，分区微调） ----------
# 每 chip = {zh 前端显示, en 写入槽位的英文词}。value 直接进 characters 的槽位，
# 所以必须是能进 SDXL/Qwen 提示词的描述性英文，不是抽象形容词。
CHARACTER_ADJUST = [
    {"slot": "face", "zh": "面部", "hint": "五官骨相", "chips": [
        {"zh": "清瘦棱角", "en": "lean angular face, defined jawline"},
        {"zh": "圆润亲和", "en": "soft rounded face, friendly features"},
        {"zh": "眉骨高挺", "en": "prominent brow ridge, deep-set eyes"},
        {"zh": "眼窝深邃", "en": "deep eye sockets, hooded eyes"},
        {"zh": "薄唇冷感", "en": "thin lips, composed cold mouth"},
        {"zh": "少年感", "en": "youthful soft cheeks, clean jaw"},
    ]},
    {"slot": "expression", "zh": "表情基调", "hint": "定妆照的情绪底色", "chips": [
        {"zh": "沉静内敛", "en": "calm restrained expression, steady gaze"},
        {"zh": "阴郁压抑", "en": "brooding heavy expression, lowered brow"},
        {"zh": "倔强不服", "en": "stubborn defiant expression, chin slightly up"},
        {"zh": "温和无害", "en": "gentle harmless expression, soft eyes"},
        {"zh": "机警戒备", "en": "alert guarded expression, narrowed eyes"},
        {"zh": "疲惫麻木", "en": "tired numb expression, dull eyes"},
    ]},
    {"slot": "hair", "zh": "发型", "hint": "剪裁与束法", "chips": [
        {"zh": "凌乱短碎发", "en": "messy short chopped hair"},
        {"zh": "高马尾束发", "en": "high tied ponytail"},
        {"zh": "半束长发", "en": "half-tied long hair"},
        {"zh": "低盘髻", "en": "low coiled bun"},
        {"zh": "散发披肩", "en": "loose shoulder-length hair"},
        {"zh": "板寸", "en": "buzz cut"},
    ]},
    {"slot": "makeup", "zh": "妆容", "hint": "妆面与皮肤状态", "chips": [
        {"zh": "素颜无妆", "en": "no makeup, bare natural skin"},
        {"zh": "苍白病态", "en": "pale sickly complexion"},
        {"zh": "唇色暗红", "en": "dark red lips"},
        {"zh": "眼下乌青", "en": "dark circles under the eyes"},
        {"zh": "烟熏眼影", "en": "smoky eye shadow"},
        {"zh": "汗湿油光", "en": "sweaty sheen on the skin"},
    ]},
    {"slot": "appearance", "zh": "体型", "hint": "身材骨架", "chips": [
        {"zh": "清瘦单薄", "en": "thin lean build"},
        {"zh": "精瘦结实", "en": "wiry muscular build"},
        {"zh": "宽肩厚背", "en": "broad shoulders, heavy back"},
        {"zh": "少年纤细", "en": "slim adolescent build"},
        {"zh": "高挑挺拔", "en": "tall upright build"},
    ]},
    {"slot": "pose", "zh": "姿态", "hint": "定妆站姿", "chips": [
        {"zh": "垂手站立", "en": "standing straight, arms at sides"},
        {"zh": "抱臂而立", "en": "standing with arms crossed"},
        {"zh": "单手负后", "en": "one hand behind the back"},
        {"zh": "微微含胸", "en": "slightly hunched shoulders"},
        {"zh": "昂首直立", "en": "chin up, upright proud posture"},
        {"zh": "倚靠斜站", "en": "leaning against a wall"},
    ]},
    {"slot": "clothing", "zh": "服装质感", "hint": "面料与磨损", "chips": [
        {"zh": "粗麻布衣", "en": "coarse linen cloth"},
        {"zh": "洗旧棉袍", "en": "washed-out worn cotton robe"},
        {"zh": "破口补丁", "en": "patched tears, frayed edges"},
        {"zh": "暗纹锦缎", "en": "damask brocade with subtle patterns"},
        {"zh": "皮质护甲", "en": "leather armor plates"},
        {"zh": "素白内衬", "en": "plain white inner lining"},
    ]},
    {"slot": "accessories", "zh": "随身饰物", "hint": "腰间/腕上", "chips": [
        {"zh": "腰间布袋", "en": "cloth pouch at the waist"},
        {"zh": "旧木牌", "en": "worn wooden token"},
        {"zh": "束发木簪", "en": "wooden hairpin"},
        {"zh": "护腕布条", "en": "cloth wrist wraps"},
        {"zh": "玉坠", "en": "jade pendant"},
        {"zh": "草绳腰带", "en": "straw rope belt"},
    ]},
]


def meta() -> dict:
    from .light_grades import LIGHT_GRADES, GROUPS
    return {
        "camera": {
            "shot_size": SHOT_SIZES, "angle": ANGLES, "move": MOVES,
            "speed": SPEEDS, "lens": LENSES, "focus": FOCUSES,
            "transition": TRANSITIONS,
        },
        # 反向词表给前端做"当前值是否被模型认识"的校验提示
        "known": {"shot_size": list(SHOT_SIZE_EN), "angle": list(ANGLE_EN),
                  "lens": list(LENS_EN)},
        "presets": SHOT_PRESETS,
        "styles": style_library(),
        "character_adjust": CHARACTER_ADJUST,
        # 光影/色彩滤镜（RHTV 节点底部预设条）：纯提示词词块，本地模型执行，不耗 token
        "light_grades": LIGHT_GRADES,
        "light_grade_groups": GROUPS,
    }
