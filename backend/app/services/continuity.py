"""镜头连续性服务（源码级借鉴 Jellyfish action_beats.py / shot_video_prompt_pack.py）。

三件事：
1. 动作节拍推断：把 subject_action 拆成 trigger / peak / aftermath 三拍，首帧取 trigger，
   尾帧取 aftermath，视频按三拍写时间分段——这是压住 i2v 随机性的核心；
2. 屏幕朝向（180° 轴线）：同一场景连续镜头的左右朝向要一致，翻轴要显式提示；
3. 前后镜头承接：上一镜动作结果 / 下一镜目标，避免"每个镜头都重新开始"。
"""
from __future__ import annotations

import re

BEAT_SPLIT = re.compile(r"[，,。；;、]|然后|接着|随即|之后|随后"
                        r"|\band then\b|\bthen\b|\bafter that\b|\bwhile\b|\bas\b|\band\b")
TRIGGER_KW = ("听到", "看到", "看见", "发现", "察觉", "突然", "骤然", "刚", "开始",
              "推门", "转头", "回头", "响起", "打开", "拿起")
PEAK_KW = ("脱手", "下坠", "落地", "捂住", "蹲下", "扑", "冲", "举起", "挥", "对峙",
           "爆发", "僵住", "抓", "撞", "喊", "跑", "扔", "撕", "砸")
AFTERMATH_KW = ("呼吸急促", "喘", "停留", "停住", "站定", "蹲着", "倒在", "保持",
                "恢复", "看向", "余韵", "收束", "沉默", "转身离开")

PHASES = ("trigger", "peak", "aftermath")


def _hits(text: str, kws: tuple[str, ...]) -> int:
    return sum(1 for k in kws if k in text)


def infer_phase(text: str, index: int, total: int) -> str:
    """关键词优先，位置兜底（Jellyfish infer_action_beat_phase 同序）。"""
    t = (text or "").strip()
    if not t:
        return "peak"
    if _hits(t, AFTERMATH_KW):
        return "aftermath"
    if _hits(t, TRIGGER_KW):
        return "trigger"
    if _hits(t, PEAK_KW):
        return "peak"
    if index == 0:
        return "trigger"
    if total >= 3 and index == total - 1:
        return "aftermath"
    return "peak"


def split_beats(action: str) -> list[dict]:
    """动作串 → 节拍列表 [{text, phase}]，最多 4 拍，短句合并。"""
    parts = [p.strip() for p in BEAT_SPLIT.split(action or "") if p and p.strip()]
    # 太碎的合并（单拍短于 4 字）
    merged: list[str] = []
    for p in parts:
        if merged and len(p) < 4:
            merged[-1] += "，" + p
        else:
            merged.append(p)
    # 悬空结尾（介词/连词/冠词/形容词）与下一拍合并，避免 "with stiff" 这类断句
    dangling = ("with", "and", "of", "to", "in", "into", "at", "from", "on", "for",
                "the", "a", "an", "his", "her", "their", "its", "stiff", "slowly", "suddenly")
    fixed: list[str] = []
    for p in merged:
        if fixed and (fixed[-1].rstrip().split(" ")[-1].lower().strip(",.") in dangling):
            fixed[-1] += ", " + p
        else:
            fixed.append(p)
    merged = fixed[:4]
    total = len(merged)
    return [{"text": t, "phase": infer_phase(t, i, total)} for i, t in enumerate(merged)]


def pick_beat(beats: list[dict], phase: str) -> str:
    for b in beats:
        if b["phase"] == phase:
            return b["text"]
    return beats[-1]["text"] if beats else ""


def beats_text(beats: list[dict], duration: int) -> str:
    """视频用：带秒区间的分拍描述，按文本长度分配时长（给 i2v 明确时间轴）。"""
    if not beats:
        return ""
    dur = max(2, int(duration or 4))
    weights = [max(4, len(re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9 ]", "", b["text"]))) for b in beats]
    total_w = sum(weights) or 1
    out, cursor = [], 0.0
    for i, b in enumerate(beats):
        seg = dur * weights[i] / total_w
        start, end = cursor, min(dur, cursor + seg)
        cursor = end
        s_show = f"{round(start, 1):g}"
        e_show = f"{round(end, 1):g}"
        out.append(f"[{s_show}s-{e_show}s] {b['text']}")
    return "; ".join(out)


_LR_EN = re.compile(r"(frame left|screen left|on the left|at the left|left edge|"
                    r"frame right|screen right|on the right|at the right|right edge)", re.I)
_TOWARD_EN = re.compile(r"(walks?|runs?|moves?|steps?|crosses?|toward|towards|approaches)", re.I)


def infer_screen_direction(*texts: str) -> str:
    """从 blocking / 轨迹 / 动作推断屏幕朝向（中英混排都能认），供跨镜头轴线连续性使用。"""
    blob = " ".join(t or "" for t in texts)
    left = blob.count("左") + len(re.findall(r"\bleft\b", blob, re.I))
    right = blob.count("右") + len(re.findall(r"\bright\b", blob, re.I))
    toward = any(k in blob for k in ("走向", "冲", "跑", "推门")) or bool(_TOWARD_EN.search(blob))
    if left and not right:
        return "left_to_right" if toward else "facing_left"
    if right and not left:
        return "right_to_left" if toward else "facing_right"
    return ""


DIR_EN = {"left_to_right": "moves from frame left toward frame right",
          "right_to_left": "moves from frame right toward frame left",
          "facing_left": "body and gaze toward frame left",
          "facing_right": "body and gaze toward frame right"}


def apply_continuity(shots: list[dict]) -> None:
    """就地补全 continuity_guidance / prev_summary / next_goal / screen_direction。
    规则：同场景相邻镜头，若朝向相反则显式提示「保持同一侧站位，勿翻轴」；
    跨场景不约束。文案用英文（i2v 模型只认英文，中文会变成噪声 token）。"""
    prev = None
    for i, sh in enumerate(shots):
        sh["screen_direction"] = sh.get("screen_direction") or infer_screen_direction(
            sh.get("blocking", ""), sh.get("action", ""), sh.get("character_path", ""))
        prev_summary = ""
        guidance = ""
        if prev is not None and prev.get("scene_name") == sh.get("scene_name"):
            # 承接摘要只进英文 token：上一镜动作若为中文（CLIP/Wan 噪声）就只保留通用承接短语
            act = (prev.get("action") or "").strip()
            en_act = act if act and all(ord(c) < 128 for c in act) else ""
            prev_summary = ("continuous scene from the previous shot"
                            + (f" ({en_act[:60]})" if en_act else "")
                            + ", same location, consistent environment, "
                              "lighting and character appearance")
            pd, cd = prev.get("screen_direction", ""), sh.get("screen_direction", "")
            if pd and cd and pd != cd:
                guidance = ("axis warning: keep each subject on its own side of the frame, "
                            f"do not cross the 180-degree line; subject {DIR_EN.get(cd, '')}")
            elif cd:
                guidance = (f"same staging and lighting as previous shot; "
                            f"subject {DIR_EN.get(cd, '')}")
        sh["prev_summary"] = prev_summary if prev_summary else ""
        sh["next_goal"] = (f"sets up next shot: {shots[i+1].get('action', '')[:60]}"
                           if i + 1 < len(shots) and shots[i+1].get("scene_name") == sh.get("scene_name")
                           else "")
        sh["continuity_guidance"] = guidance
        sh["composition_anchor"] = sh.get("composition_anchor") or (
            "rule of thirds, leave negative space in the gaze direction"
            if sh.get("screen_direction") else "")
        prev = sh
