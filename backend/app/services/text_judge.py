"""改字判定 + 下一轮重绘框计算（自动迭代的核心）。

一轮 inpaint 之后发生什么，全看这里：
  1. `judge()`   —— 把 OCR 读到的字与目标文字比对，给出"过/不过"和命中率；
  2. `focus_box()` —— 不过就重新框选：优先框住"读得最差的那一块字"，并把面积压到
     上一轮的 85% 以内（用户要的"重绘范围逐步减小"），到像素下限就停，避免越缩越糊。

判定口径（刻意现实，不追求 100%）：
  · 中文按**字符命中率**：目标里 75% 的字被读出来即算过（毛笔字 + 做旧底很难全对）；
  · 英文按**单词命中率**：80%；
  · 另设"杂质"上限：框内读出的字里，不属于目标的比例 > 45% 视为框太大/周围还有乱字，
    即使命中率够也不算过 —— 这种情况交给 focus_box 缩框解决；
  · 尺寸标注（300 / 507.68 / 620×840）不是文字内容，判定前剔除。
"""
from __future__ import annotations

import re

_DIGIT_ONLY = re.compile(r"^[\s\d.,:：/×xX%+\-±()（）]*$")
_PUNCT = re.compile(r"[^\w\u4e00-\u9fff]", re.UNICODE)
_WORD = re.compile(r"[a-z0-9]+")


def _norm(s: str) -> str:
    return _PUNCT.sub("", (s or "").lower())


def _meaningful(items: list[dict]) -> list[dict]:
    return [it for it in items if not _DIGIT_ONLY.match(it.get("text") or "")]


def judge(target: str, items: list[dict] | None, lang: str = "zh",
          min_hit: float | None = None, max_extra: float = 0.45) -> dict:
    """比对 OCR 结果与目标文字。

    返回 {ok, hit, extra, best_score, observed, reason}
      reason: ok / no_text（框内没读出字）/ low_hit / noisy（周围杂字太多）/ low_conf
    """
    target = (target or "").strip()
    if not target:
        return {"ok": False, "hit": 0.0, "extra": 0.0, "best_score": 0.0,
                "observed": "", "reason": "no_target"}
    if items is None:
        # OCR 引擎不可用：无法判定，按"未验证"处理，交给轮次上限兜底
        return {"ok": False, "hit": 0.0, "extra": 0.0, "best_score": 0.0,
                "observed": "", "reason": "no_engine"}

    use = _meaningful(items)
    observed = "".join(it["text"] for it in use)
    best = max((float(it.get("score") or 0) for it in use), default=0.0)

    if lang == "en":
        tw = set(_WORD.findall(target.lower()))
        ow = set(_WORD.findall(observed.lower()))
        hit = len(tw & ow) / max(1, len(tw))
        extra = len([w for w in ow - tw if len(w) > 1]) / max(1, len(ow))
        th = 0.85 if min_hit is None else float(min_hit)
        ok_conf = 0.45
    else:
        tset = set(_norm(target))
        oset = set(_norm(observed))
        hit = len(tset & oset) / max(1, len(tset))
        extra = len([c for c in oset if c not in tset]) / max(1, len(oset))
        # 5 字牌匾错 1 字（「青云宗令黎」）就是不合格：短句要求全对，长句允许错 1 字
        if min_hit is not None:
            th = float(min_hit)
        else:
            th = 1.0 if len(tset) <= 4 else 0.9
        ok_conf = 0.40

    if not observed:
        reason = "no_text"
    elif best < ok_conf:
        reason = "low_conf"
    elif hit < th:
        reason = "low_hit"
    else:
        # 注意：框内读出别的标注（extra 高）不算失败——设计图本身就到处是标注，
        # 只要目标这几个字读清楚了就算达标（实测「灵石兑换券」hit=1.0 却被判 noisy，
        # 会白白多跑两轮）。extra 只作为报告字段，供缩框与人工判断参考。
        reason = "ok"

    return {"ok": reason == "ok", "hit": round(hit, 3), "extra": round(extra, 3),
            "best_score": round(best, 3), "observed": observed[:60], "reason": reason}


def focus_box(box: dict, items: list[dict] | None, target: str, lang: str,
              img_w: int, img_h: int, shrink: float = 0.82,
              area_cap: float = 0.85, min_px: int = 56) -> dict:
    """算下一轮的重绘框：框住读得最差的那块字，面积压到上一轮的 `area_cap` 以内。"""
    box = {k: float(box[k]) for k in ("x", "y", "w", "h")}
    tset = set(_norm(target))

    def cover(it: dict) -> float:
        cset = set(_norm(it.get("text") or ""))
        return len(cset & tset) / max(1, len(tset))

    cand = [it for it in (items or [])
            if not _DIGIT_ONLY.match(it.get("text") or "")
            and (it["bbox"]["w"] * it["bbox"]["h"]) > 0.0015]

    keep = False
    if cand:
        # 框住"目标字符最集中"的那一块（那就是目标字所在位置）；覆盖率为 0 的纯乱字块
        # 多半是旁边别的标注，聚焦过去会跑偏——这时宁可按中心收缩。
        best = max(cand, key=lambda it: (cover(it), it["bbox"]["w"] * it["bbox"]["h"]))
        cover_best = cover(best)
        fill = (best["bbox"]["w"] * best["bbox"]["h"]) / max(1e-9, box["w"] * box["h"])
        # 目标字本来就占满框（竖排五字顶到框边）→ 再缩只会切掉边缘的字、留下半截残影
        # （实测「青云宗令牌」缩到 26%×46% 时第五字被切，出来是「券」+ 叠笔）。这种情况
        # 保持原框，靠换 seed / 提高重绘强度 / 擦除提示再试。
        if cover_best >= 0.35 and fill < 0.55:
            b = dict(best["bbox"])
            pad_x, pad_y = b["w"] * 0.30, b["h"] * 0.30
            b = {"x": b["x"] - pad_x, "y": b["y"] - pad_y,
                 "w": b["w"] + 2 * pad_x, "h": b["h"] + 2 * pad_y}
            x0, y0 = max(b["x"], box["x"]), max(b["y"], box["y"])
            x1, y1 = min(b["x"] + b["w"], box["x"] + box["w"]), min(b["y"] + b["h"], box["y"] + box["h"])
            if x1 - x0 > 0.02 and y1 - y0 > 0.02:
                b = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
            else:
                b, keep = dict(box), True
        else:
            b, keep = dict(box), True
    else:
        # 框内读不出字（发光字/极小字/笔迹太潦草）：以中心收缩
        nw, nh = box["w"] * shrink, box["h"] * shrink
        b = {"x": box["x"] + (box["w"] - nw) / 2, "y": box["y"] + (box["h"] - nh) / 2,
             "w": nw, "h": nh}

    # 面积硬上限：这一轮不许比上一轮更大（"逐步减小"）。
    # keep=True（目标字占满框、不缩）时跳过，否则会被这条规则强行缩掉边缘字。
    cap = box["w"] * box["h"] * area_cap
    if not keep and b["w"] * b["h"] > cap > 0:
        k = (cap / (b["w"] * b["h"])) ** 0.5
        nw, nh = b["w"] * k, b["h"] * k
        b = {"x": b["x"] + (b["w"] - nw) / 2, "y": b["y"] + (b["h"] - nh) / 2,
             "w": nw, "h": nh}

    # 像素下限：短边 < min_px 模型写不出清晰中文字，缩到这个量级就收手
    mw = max(0.05, min_px / max(1, img_w))
    mh = max(0.05, min_px / max(1, img_h))
    if b["w"] < mw:
        b["x"] = b["x"] + (b["w"] - mw) / 2
        b["w"] = mw
    if b["h"] < mh:
        b["y"] = b["y"] + (b["h"] - mh) / 2
        b["h"] = mh

    # 收回画内
    b["w"] = max(0.05, min(0.95, b["w"]))
    b["h"] = max(0.05, min(0.95, b["h"]))
    b["x"] = max(0.0, min(1.0 - b["w"], b["x"]))
    b["y"] = max(0.0, min(1.0 - b["h"], b["y"]))
    return {k: round(v, 4) for k, v in b.items()}


def same_box(a: dict, b: dict, tol: float = 0.12) -> bool:
    """两框中心偏移 < tol、面积变化 < 15% 即视为"没变化"，继续循环没意义。"""
    ax, ay = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bx, by = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    d = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    area_a, area_b = a["w"] * a["h"], b["w"] * b["h"]
    return d < tol and (max(area_a, area_b) / max(1e-6, min(area_a, area_b))) < 1.15
