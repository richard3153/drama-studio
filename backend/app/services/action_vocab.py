"""打斗/动作提示词库（#76，#77 按社区方法论扩充）：

扩充来源（2026-11 搜索沉淀）：
- carat.im Fight Video Prompts：动作动词要具体（spinning back kick/upper-cut/grappling）、
  冲击物理（shockwaves on contact/distorted air/momentum shift）、环境互动
  （sparks flying/shattering glass/cracking concrete）
- faxianai Istanbul Noir Fight：因果链硬规则 wind-up → strike path → contact →
  body reaction → shift in center of gravity；禁假打（no fake hits/no reactions
  without contact/no weightless flying）
- awesomevideoprompts Parametric Fight：IMPACT=2-frame hold + brightness spike +
  micro shake；MOTION=hair/fabric 二级延迟；RHYTHM=快交换+micro pauses+1-2 个
  slow-motion beats；HERO MOMENT=慢入→狠击→短暂定格→强剪影
- 设计要点：
- 打击（strike）：重量感三要素——发力预判（weight shifted into the strike）→
  命中反馈（visible impact and recoil）→ 受击响应（staggers back）。
  I2V 只认"运动因果链"，单给"激烈打斗"只会出慢动作挥手。
- 追逐（chase）：动量词（momentum follow-through）+ 变向（direction changes）。
- 与 MOTION_STABILITY 兼容：no jitter 是全局约束，impact shake 是命中瞬间的
  具体事件词——具体词覆盖泛化词，实测不冲突。
- 平台安全：负面词挡 excessive gore / blood splatter（红果审核红线）+ 假打/无重力飞。
"""
from __future__ import annotations

# 关键词表：刻意不用单字（"打"会误中 打电话/打听），全部用动作短语级词
_STRIKE_WORDS = (
    "挥拳", "出拳", "一拳", "拳头", "打斗", "打架", "搏斗", "格斗", "扭打",
    "推搡", "耳光", "掌掴", "扇向", "踢向", "一脚踢", "踹", "肘击", "膝撞",
    "摔向", "摔倒", "撞飞", "撞向", "击中", "命中", "挡开", "格挡", "挥刀",
    "拔刀", "刀光", "刺向", "捅向", "开枪", "枪声", "枪口", "射击", "中弹",
    "瞄准", "上膛", "勒住", "掐住", "拽住衣", "扑向",
    "punch", "kicks", "kick ", "slap", "fight", "combat", "brawl", "wrestle",
    "slash", "stab", "sword", "blade", "knife", "gun ", "gun,", "shoot",
    "firearm", "explosion", "explode", "struck", "strikes", "impact of the",
    "elbow strike", "knee strike", "tackle", "chokes", "grabs",
    "fist", "swings", "swing at", "swung", "punches", "uppercut", "haymaker",
    "left hook", "right hook", "straight punch", "spin", "spinning back kick",
    "side kick", "elbow strike", "knee strike", "low kick", "clinch",
    "wrist control", "wind-up", "brawl", "jabs",
)
_CHASE_WORDS = (
    "追逐", "追赶", "奔逃", "逃跑", "逃向", "夺路", "闪避", "躲开", "扑倒",
    "追向", "猛冲", "冲向", "跃过", "翻越",
    "chase", "chasing", "flee", "runs from", "running from", "sprint",
    "dodge", "dives", "leaps over", "sprints", "rushes toward",
)


def detect_action(*texts: str) -> str:
    """动作镜识别：命中打击词返回 'strike'，命中追逐词返回 'chase'，否则 ''。
    打击优先（一个镜里既有打又有追，按打击编排更安全）。"""
    blob = " ".join(t or "" for t in texts).lower()
    if not blob.strip():
        return ""
    if any(w in blob for w in _STRIKE_WORDS):
        return "strike"
    if any(w in blob for w in _CHASE_WORDS):
        return "chase"
    return ""


# ---------- 方言词（kind: image=静帧动态姿态 / video=动作编排 / negative=安全负面） ----------

ACTION_VOCAB = {
    "strike": {
        "image": ("dynamic mid-strike action pose, weight shifted into the strike, "
                  "clenched fists, tensed muscles, cloth and hair whipping with the motion, "
                  "rim light defining the silhouette"),
        # 动量链（因果链硬规则）：发力预判 → 运行路径 → 接触 → 受击反应 → 重心转移；
        # 冲击物理：2 帧定格+亮度尖峰+微震；环境互动：尘土/碎屑/玻璃/火花；
        # 节奏：快交换 + micro pauses + 1 个慢放重击节拍（不全程慢动作）
        "video": ("fast-paced fight choreography with clear cause and effect, "
                  "wind-up then strike path then contact, the strike lands with visible "
                  "impact and recoil, the opponent staggers back with weight shifting "
                  "to the trailing foot, dust and debris kick up around the feet, "
                  "brief impact shake and a flicker of brightness on the hit, "
                  "cloth and hair react a beat behind the body, "
                  "one short slow-motion beat on the heaviest blow, "
                  "follow-through after each strike"),
        "negative": ("frozen static pose, sluggish slow motion, excessive gore, "
                     "blood splatter, weightless floating motion, fake no-contact swings"),
    },
    "chase": {
        "image": ("dynamic running action pose, body leaning into motion, "
                  "momentum clearly visible, cloth and hair trailing behind"),
        "video": ("fast-paced chase choreography, rapid direction changes, "
                  "obstacles vaulted mid-stride, momentum follow-through, "
                  "urgent breathless pacing, splashes and grit kicked up by each step"),
        "negative": ("frozen static pose, sluggish slow motion, excessive gore, "
                     "blood splatter, weightless floating motion"),
    },
}


def action_tokens(level: str, kind: str) -> str:
    return ACTION_VOCAB.get(level, {}).get(kind, "")
