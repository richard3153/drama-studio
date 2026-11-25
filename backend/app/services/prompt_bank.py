"""自强化提示词库（#90）：在 model_vocab 固定方言之上叠加可学习词块层。

机制：
- 种子词块随代码内置（按 Qwen-Image / MiniMax H3 官方提示词习惯编写），
  首次读取落盘 backend/data/prompt_bank.json；
- 生成成功 → 产物提示词反查命中词块 kept+1；任务失败 → 命中词块 failed+1；
  权重 = kept - 1.5*failed，kept≥2 转正、failed≥3 且 kept=0 自动拉黑停用；
- harvest 提炼：扫描现存成功产物提示词，提取高频短语（过滤固定词库已有词块）
  自动入库——用户反复得到好结果的词块会自己"浮"到注入队列前面。
- 词块是"增量尾词"，只叠加不改写主体；主体语义由拆解槽位/镜头提示词承担。
"""
from __future__ import annotations

import json
import re
import threading
from collections import Counter
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent.parent / "data"
BANK_PATH = _DATA / "prompt_bank.json"
_LOCK = threading.Lock()

# 单 family 词块池上限：防止 harvest 无限膨胀稀释注入
MAX_CHUNKS_PER_FAMILY = 60
# 每次注入的词块条数上限（weight 排序取 top）
INJECT_TOP_K = 6
BLACKLIST_THRESHOLD = 3     # failed 达到且 kept=0 → 拉黑
PROMOTE_THRESHOLD = 2       # kept 达到 → 转正（从种子态毕业）

# ---------- 种子词块（首跑落盘；模型官方提示词习惯提炼） ----------

SEED_CHUNKS = {
    # 图片族：Qwen-Image（DiT + 双语文本编码器：自然语言长描述、文字渲染、版式跟随强）
    "qwen_image": [
        {"text": "coherent long-form natural language description, structured detail", "kind": "image"},
        {"text": "clean composition with clear foreground-background separation", "kind": "image"},
        {"text": "soft volumetric lighting with believable shadow falloff", "kind": "image"},
        {"text": "fine material texture detail, natural color grading", "kind": "image"},
        {"text": "harmonious unified art style across all elements", "kind": "image"},
        {"text": "accurate proportions and balanced framing", "kind": "image"},
        {"text": "readable in-image text, correctly spelled characters", "kind": "image"},
        {"text": "consistent perspective, grounded spatial relationships", "kind": "image"},
    ],
    # 视频族：MiniMax H3（qwen3vl 文本编码器：认运镜短语与动作分解；cfg=1 无负面输入，
    # 否定句无效——词库一律正向表述；H3 原生音频，氛围音可直接写进提示词）
    "minimax_h3": [
        {"text": "frame-to-frame continuity preserved, subject scale stable", "kind": "video"},
        {"text": "physically plausible dynamics, believable weight and momentum", "kind": "video"},
        {"text": "expressive facial performance, natural body movement", "kind": "video"},
        {"text": "camera movement motivated by subject action", "kind": "video"},
        {"text": "consistent character appearance and lighting throughout", "kind": "video"},
        {"text": "diegetic ambient audio: wind, footsteps, room tone", "kind": "video"},
        {"text": "clear depth: subject in foreground, environment recedes naturally", "kind": "video"},
        {"text": "subtle wind, cloth and hair secondary motion", "kind": "video"},
    ],
    # 其余族（辅助链路仍用）：给空种子，靠 harvest 自学
    "sdxl": [],
    "flux2_klein": [],
}

# 固定词库（model_vocab / style 画质锁 / 稳定性词）已覆盖的短语——harvest 跳过防重复注入
FIXED_PHRASES = {
    "crisp legible text rendering", "precise layout following", "sharp focus",
    "coherent composition", "clean edges", "physically accurate materials",
    "true-to-life proportions", "smooth natural motion", "stable framing",
    "no jitter", "no morphing", "smooth continuous motion", "natural physics",
    "one clear action per clip", "single continuous shot", "stable camera",
}

# 画质尾巴/摄影链关键词（style_presets.QUALITY_SUFFIX* 与图像方言的典型措辞）：
# 这些是固定组装链的一部分，不属于任何模型的"可学习方言"，提炼时一律拦截——
# 否则写实摄影词会随历史产物窜进 3D 国风图片库 / H3 视频库，造成风格漂移。
QUALITY_KEYWORDS = (
    "film grain", "color grad", "teal-orange", "unretouched", "pores", "flyaway",
    "depth of field", "lens flare", "cinematic film still", "restrained rendering",
    "authentic detail", "natural texture", "realistic fabric", "shallow focus",
)

# 剧情/UI 具象词：属内容层（本项目剧本设定），不是可迁移的模型方言，禁止入通用词库
CONTENT_BLOCK = (
    "quest", "inventory", "hologram", "tooltip", "pop-up", "level-up", "timer",
    "system", "dialog box", "health bar", " ui", "ui ", "button", "menu",
)

# 词性准入（模型方言必须是"运动/镜头/光影/材质"级指令，不能是名词堆砌的情节描述）：
# 视频短语须含至少一个运动/镜头/物理/氛围词根；图片短语须含构图/光线/材质/风格词根
VIDEO_ROOTS = (
    "camera", "shot", "move", "motion", "slide", "drift", "float", "step",
    "walk", "run", "turn", "push", "pull", "pan", "tilt", "zoom", "fade",
    "physical", "momentum", "weight", "foot", "feet", "continuous", "take", "cut",
    "pace", "rhythm", "breath", "dust", "wind", "rain", "fog", "smoke", "particle",
    "blocking", "framing", "ambien", "sound", "audio", "atmosphere", "depth",
    "foreground", "background", "perspective", "reflection",
)

# 视频库禁收光照描述：光由场景板/首帧锁死，写进 I2V 视频提示词会与具体场景打架
# （实测把"正午阳光"场景和提炼来的"室内荧光灯"词块同时塞进去，光效互相抵消）
VIDEO_LIGHT_BLOCK = (
    "light", "lighting", "shadow", "glow", "exposure", "color temperature",
    "rim light", "backlight", "highlight", "bloom",
)
IMAGE_ROOTS = (
    "light", "composition", "texture", "color", "colour", "material", "detail", "shadow",
    "perspective", "framing", "style", "render", "proportion", "layout", "depth",
    "atmosphere", "tone", "palette", "grading", "surface", "silhouette", "contrast",
    "focus", "geometry", "shading", "illumination", "ornament", "layer", "form",
    "highlight", "midtones", "reflection", "glow", "aura",
)


def _blank() -> dict:
    return {fam: {} for fam in SEED_CHUNKS}


def _seed_entry(c: dict) -> dict:
    return {"text": c["text"], "kind": c["kind"], "kept": 1, "failed": 0, "seed": True}


def _load() -> dict:
    """读取词库；不存在/损坏则用种子重建（种子 kept=1 视为已验证基线）。"""
    if BANK_PATH.exists():
        try:
            data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for fam, seedlist in SEED_CHUNKS.items():
                    pool = data.setdefault(fam, {})
                    have = {v.get("text", "").lower() for v in pool.values()}
                    for c in seedlist:
                        if c["text"].lower() not in have:
                            pool[f"seed_{c['kind']}_{len(pool)}"] = _seed_entry(c)
                return data
        except Exception:
            pass
    data = _blank()
    for fam, seedlist in SEED_CHUNKS.items():
        for c in seedlist:
            data[fam][f"seed_{c['kind']}_{len(data[fam])}"] = _seed_entry(c)
    _save(data)
    return data


def _save(data: dict):
    BANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = BANK_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(BANK_PATH)


def _weight(e: dict) -> float:
    return e.get("kept", 0) - 1.5 * e.get("failed", 0)


def _blacklisted(e: dict) -> bool:
    return (not e.get("seed")) and e.get("failed", 0) >= BLACKLIST_THRESHOLD \
        and e.get("kept", 0) == 0


def bank_tokens(family: str, kind: str, top_k: int = INJECT_TOP_K) -> str:
    """取该 family+kind 下权重为正的学习词块（weight 降序 top_k），逗号拼接。
    无学习词块 / 词库损坏 → 空串（组装方按空值跳过，零风险）。"""
    with _LOCK:
        data = _load()
    pool = data.get(family, {})
    # 排序：权重降序；权重相同时实战提炼块（h_/u_）优先于内置种子（seed_）——
    # 真实产物验证过的短语更贴合本机模型，种子只在学习层空/弱时才补位。
    ranked = sorted(
        ((k, e) for k, e in pool.items()
         if e.get("kind") == kind and not _blacklisted(e) and _weight(e) > 0),
        key=lambda kv: (_weight(kv[1]), not kv[0].startswith("seed_")), reverse=True)
    return ", ".join(e["text"] for _, e in ranked[:top_k])


def reinforce_from_prompt(family: str, prompt: str, ok: bool) -> dict:
    """生成收尾钩子：产物提示词反查命中词块并计数（成功 kept+1 / 失败 failed+1）。
    只统计真实注入进提示词的词块——没被采用的词块不受影响。"""
    if not prompt:
        return {}
    low = prompt.lower()
    with _LOCK:
        data = _load()
        pool = data.setdefault(family, {})
        touched = 0
        for e in pool.values():
            t = e.get("text", "").lower()
            if t and t in low:
                if ok:
                    e["kept"] = e.get("kept", 0) + 1
                    if e.get("kept", 0) >= PROMOTE_THRESHOLD:
                        e["seed"] = False   # 转正：进入正常权重生命周期（可被拉黑机制约束）
                else:
                    e["failed"] = e.get("failed", 0) + 1
                touched += 1
        _save(data)
    return {"family": family, "touched": touched}


_INFRA_ERRORS = ("Connect", "Timeout", "ReadError", "RemoteProtocol", "Transport", "Pool")


def reinforce_on_error(family: str, prompt: str, exc: BaseException) -> dict:
    """生成失败钩子（异常路径）：ComfyUI 连不上/排队超时等基础设施故障不计入词块失败——
    词块只对"模型/提示词质量"负责，网络与显存故障不该把好词块拉黑。"""
    if any(k in type(exc).__name__ for k in _INFRA_ERRORS):
        return {"family": family, "touched": 0, "skipped": "infrastructure"}
    return reinforce_from_prompt(family, prompt, ok=False)


def harvest(docs: list[str], family: str, kind: str, min_hits: int = 3,
            max_new: int = 12, forbid_extra=None) -> list[str]:
    """从成功产物提示词中提炼高频短语入库。
    docs: 提示词文本列表；短语=逗号分段、长度 6-120 字符、≥3 个英文词；
    forbid_extra: 调用方传入的跨族禁用短语（其他模型族方言词，防止图像词窜进视频库）；
    命中 ≥min_hits 才入库；已在固定词库/种子/黑名单的短语跳过。"""
    forbid = set(FIXED_PHRASES) | {f.lower() for f in (forbid_extra or ())}
    counter = Counter()
    for doc in docs:
        if not doc:
            continue
        for raw in re.split(r"[,，;；]", doc):
            t = raw.strip().lower()
            if not (6 <= len(t) <= 120) or len(t.split()) < 3:
                continue            # 1-2 词的碎片太弱，组合不出有效指令
            if re.search(r"\bno |without|nude|nsfw", t):
                continue
            # 模板标签剥离/碎片过滤：组装模板里的 "camera:" 前缀保留正文；
            # "action beats: [0s-4s] ..."、"4s single continuous take"、"from medium shot"
            # 是模板结构与时长碎片，不是可复用词块
            t = re.sub(r"^(camera|subject motion|blocking|focus|continuity):\s*", "", t)
            t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()   # 去尾部括号注释（模板残留）
            if (not t) or "[" in t or "]" in t or re.match(r"^\d+(\.\d+)?s\b", t) \
                    or t.startswith("from ") or "action beats" in t:
                continue
            if any(k in t for k in QUALITY_KEYWORDS):
                continue
            if any(c in t for c in CONTENT_BLOCK):
                continue
            # 词根用词边界匹配（避免 "chairs" 误命中 "hair" 这类子串假阳性）
            if kind == "video":
                if any(k in t for k in VIDEO_LIGHT_BLOCK):
                    continue        # 视频库禁收光照描述（光已由场景板/首帧锁死）
                if not any(re.search(rf"\b{r}", t) for r in VIDEO_ROOTS):
                    continue
            if kind == "image" and not any(re.search(rf"\b{r}", t) for r in IMAGE_ROOTS):
                continue
            if any(f in t for f in forbid):
                continue
            counter[t] += 1
    with _LOCK:
        data = _load()
        pool = data.setdefault(family, {})
        have = {v.get("text", "").lower() for v in pool.values()}
        added = []
        for text, n in counter.most_common():
            if len(added) >= max_new or len(pool) >= MAX_CHUNKS_PER_FAMILY:
                break
            if n < min_hits or text in have:
                continue
            pool[f"h_{kind}_{len(pool)}"] = {"text": text, "kind": kind,
                                             "kept": 1, "failed": 0, "seed": True}
            have.add(text)
            added.append(text)
        if added:
            _save(data)
    return added


def add_chunk(family: str, text: str, kind: str) -> bool:
    with _LOCK:
        data = _load()
        pool = data.setdefault(family, {})
        if len(pool) >= MAX_CHUNKS_PER_FAMILY:
            return False
        if any(v.get("text", "").lower() == text.lower() for v in pool.values()):
            return False
        pool[f"u_{kind}_{len(pool)}"] = {"text": text, "kind": kind,
                                         "kept": 1, "failed": 0, "seed": True}
        _save(data)
    return True


def remove_chunk(family: str, key: str) -> bool:
    with _LOCK:
        data = _load()
        pool = data.setdefault(family, {})
        if key in pool:
            del pool[key]
            _save(data)
            return True
    return False


def snapshot() -> dict:
    """全量词库 + 权重视图（API 展示用）。"""
    with _LOCK:
        data = _load()
    out = {}
    for fam, pool in data.items():
        items = []
        for k, e in pool.items():
            items.append({**e, "key": k, "weight": round(_weight(e), 2),
                          "blacklisted": _blacklisted(e)})
        items.sort(key=lambda e: e["weight"], reverse=True)
        out[fam] = items
    return out
