"""打斗/动作提示词库（#76）：动作镜自动识别 + 打击/追逐两类编排词注入。

背景：短剧爽点集中在前 10 集的高频冲突（战神/赘婿题材尤甚），但通用提示词
写不出"打得有来有回"——I2V 模型默认给慢速优雅动作，打击没有重量感。
本库对拆解产物的 subject_action/blocking/dialogue/sfx 做关键词识别，
命中后自动注入动作编排词（组装期 + 生成期双层，与 model_vocab 同构）。

设计要点：
- 打击（strike）：重量感三要素——发力预判（weight shifted into the strike）→
  命中反馈（visible impact and recoil）→ 受击响应（staggers back）。
  I2V 只认"运动因果链"，单给"激烈打斗"只会出慢动作挥手。
- 追逐（chase）：动量词（momentum follow-through）+ 变向（direction changes）。
- 与 MOTION_STABILITY 兼容：no jitter 是全局约束，impact shake 是命中瞬间的
  具体事件词——具体词覆盖泛化词，实测不冲突。
- 平台安全：负面词挡 excessive gore / blood splatter（红果审核红线）。
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
                  "clenched fists, tensed muscles, cloth and hair whipping with the motion"),
        "video": ("fast-paced fight choreography, the strike lands with visible impact "
                  "and recoil, the opponent staggers back, dust and debris kick up "
                  "around the feet, brief impact shake on the hit, follow-through "
                  "after each blow"),
        "negative": "frozen static pose, sluggish slow motion, excessive gore, blood splatter",
    },
    "chase": {
        "image": ("dynamic running action pose, body leaning into motion, "
                  "momentum clearly visible, cloth and hair trailing behind"),
        "video": ("fast-paced chase choreography, rapid direction changes, "
                  "obstacles vaulted mid-stride, momentum follow-through, "
                  "urgent breathless pacing"),
        "negative": "frozen static pose, sluggish slow motion, excessive gore, blood splatter",
    },
}


def action_tokens(level: str, kind: str) -> str:
    return ACTION_VOCAB.get(level, {}).get(kind, "")
