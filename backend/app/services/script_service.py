"""P1 剧本服务（M2.2 方法论重构，源自 4 篇方法论）：

- 大纲：高概念公式（熟悉设定+颠覆性反差）+ 每集强钩子（第三章）
- 剧本：影视标准格式（第一章）：场号题头[内/外][日/夜] + △可视化动作 + 紧凑对白
  + 【音效】【字幕】 + (V.O.)/(O.S.)，禁止心理描写
- 拆解：规则解析剧本（零 LLM，稳）→ 分场景拆镜（第一章导演切镜 8 原则）
  → 资产库强制引用（消灭二次理解）→ 代码模板组装提示词（第二/四章公式，LLM 只填槽位）
- 全程温度 0.3 + 内容级校验
"""
import json
import re
from pathlib import Path

from sqlalchemy import select

from ..adapters.ollama_adapter import OllamaAdapter, _strip_think
from ..style_presets import (_clean, QUALITY_SUFFIX, assemble_character_prompt,
                             assemble_end_frame_prompt, assemble_prop_prompt,
                             assemble_scene_prompt, assemble_shot_prompt, get_style,
                             style_lock_for, lifelike_tokens)

LLM_TEMP = 0.3

# ---------- 结构化槽位 schema（LLM 只填这些，不再自由发挥提示词） ----------

CANDIDATE_SCHEMA = {
    "characters": [{
        "name": "角色名", "description": "身份定位+性格反差点（中文）",
        "identity": "性别,年龄段,职业/身份（英文填写）",
        "appearance": "身高参照+体型+年龄感（英文填写，如 tall and slim, looks younger than actual age）",
        "face": "脸型+五官特征+记忆点（英文填写，如 oval face, sharp brows, mole under left eye）",
        "hair": "发型+发色（英文填写）",
        "clothing": "按上身-下装-鞋三段描述（英文填写，如 olive open coat over black tank top; dark pleated skirt; black boots）",
        "makeup": "妆造特点（英文填写，无则空串）",
        "accessories": "1-2个标志性配件（英文填写，无则空串，宁缺勿多）",
        "expression": "常见表情与气质（英文填写，写成五官动作如 lips pressed, gaze lowered）",
        "pose": "常态姿态（英文填写，如 hands in pockets, slight forward lean）",
        "chibi": "Q版形象特点（英文填写，无则空串）",
        "palette": "主色+辅助色（英文填写，如 olive green with black accents）",
    }],
    "scenes": [{
        "name": "场景名", "description": "功能说明（中文）",
        "space": "空间类型+主要结构与物件（英文填写）",
        "era": "时代与风格（英文填写）",
        "elements": "关键陈设元素（英文填写）",
        "light": "光源,时段,色调（英文填写）",
        "mood": "氛围情绪（英文填写）",
    }],
    "props": [{
        "name": "道具名", "description": "叙事功能（中文）",
        "category": "core=核心叙事道具 / bond=角色连接道具 / ambient=环境氛围道具",
        "subject": "物品本体（英文填写）",
        "purpose": "剧情功能（英文填写）",
        "era": "时代标签（英文填写）",
        "details": "形状,纹理,铭刻细节（英文填写）",
        "material": "材质与色彩（英文填写）",
        "interaction": "与角色的交互方式（英文，如手指紧扣扳手；bond类必填）",
    }],
}

SHOT_SCHEMA = {
    "shots": [{
        "duration": 4, "shot_size": "远景/全景/中景/近景/特写",
        "camera": "固定/缓推/拉/横摇/移/跟/升降/环绕/手持（中文）",
        "camera_move": "固定|推|拉|横摇|竖摇|移|跟|升降|环绕|手持",
        "camera_speed": "slow|normal|fast|whip",
        "camera_dir": "left|right|up|down|in|out（无位移则空串）",
        "framing_start": "起幅景别（中文，如全景）",
        "framing_end": "落幅景别（中文，如近景；固定镜头可与起幅相同）",
        "camera_angle": "平视|俯拍|仰拍|过肩|POV|航拍|斜角",
        "focal_length": "24mm/35mm/50mm/85mm（可空）",
        "focus_transition": "none|rack-focus|pull-focus|follow-focus",
        "blocking": "人物在画面中的位置关系（英文，如 man at frame left, woman at frame right）",
        "character_path": "人物活动轨迹（英文，如 from left edge walks to the counter then turns back to camera；无位移则空串）",
        "end_action": "动作结束时的姿态（英文，供尾帧使用）",
        "characters": ["入镜角色名，必须引用资产清单或新增候选"],
        "props": ["道具名"],
        "dialogue": "该镜头台词原文（无则空串）", "sfx": "【音效】内容（无则空串）",
        "subject_action": "谁在做什么，客观具体可视觉化（英文，禁止抽象形容词）",
        "light": "本镜头光影（英文）",
        "composition": "构图与角度，如过肩/仰视（英文）",
    }],
    "new_characters": [], "new_scenes": [], "new_props": [],
}

# 判定“这个镜头必须出尾帧”的运镜集合（位移型）
MOVING_CAMERA = {"推", "拉", "横摇", "竖摇", "移", "跟", "升降", "环绕", "手持"}

# 景别/角度中→英（v2v/i2v 模型只认英文，避免中文残留）
SHOT_SIZE_EN = {"远景": "extreme wide shot", "全景": "wide shot", "中景": "medium shot",
                "近景": "close shot", "特写": "close-up", "大特写": "extreme close-up",
                "中近景": "medium close-up"}
ANGLE_EN = {"平视": "eye level", "俯拍": "high angle", "仰拍": "low angle",
            "过肩": "over-the-shoulder", "斜角": "dutch angle", "航拍": "aerial view",
            "POV": "POV", "主观": "POV"}


def _en_size(v: str) -> str:
    return SHOT_SIZE_EN.get((v or "").strip(), (v or "").strip())


def _en_angle(v: str) -> str:
    return ANGLE_EN.get((v or "").strip(), (v or "").strip())


def _extract_json(text: str) -> dict:
    text = _strip_think(text).strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM 输出中未找到 JSON 对象")
    return json.loads(text[start:end + 1])


def _flatten_slots(entity: dict) -> str:
    """槽位 → 英文外貌/概念短句（用于镜头提示词的角色外貌引用）。"""
    keys = ("identity", "appearance", "hair", "clothing", "expression")
    return ", ".join(v for k in keys if (v := _clean(entity.get(k))))


def _look_of(slots: dict, base_prompt: str = "") -> str:
    """角色外貌取词：槽位优先，槽位为空则回落到角色基础设定词。

    实测教训：角色槽位没补全时，镜头提示词里角色段直接消失，底模会给你一张空镜。
    所以这里必须有兜底，并把 base_prompt 截断成可读片段（去掉画风/版式词）。"""
    look = _flatten_slots(slots or {})
    if look:
        return look
    bp = (base_prompt or "").strip()
    if not bp:
        return ""
    cut = bp.split(", character reference sheet")[0]
    parts = [x.strip() for x in cut.split(",")]
    # 去掉纯画风/版式词，只保留人物描述
    skip = ("style", "render", "reference sheet", "concept art", "character design",
            "8k", "highres", "masterpiece", "game cg", "unreal")
    keep = [x for x in parts if x and not any(s in x.lower() for s in skip)]
    return ", ".join(keep[:6])


def _multi_layout_hint(names: list[str], looks: list[str]) -> str:
    """双人/多人同框的分列布局词。

    实测：链式双 IPA 已把两张脸都锁住，但提示词没有布局词时底模只画一个人
    （构图语义单主体）。加上分列词后双人才有明确的空间锚点：
    第一人=左（对应 IPA 参考图 A），第二人=右（参考图 B），顺序与 _char_ref_paths 一致。
    布局词必须是英文（底模不认中文角色名），用各自外貌短语的前几个词指代。
    """
    n = len(looks)
    if n <= 1:
        return ""

    def _tag(look: str) -> str:
        # 取外貌短语的前几个实词做指代（剔除冠词/介词收尾），如 "young woman" / "grey hooded hoodie"
        stops = {"with", "in", "on", "the", "a", "an", "of", "and", "wearing", "holding"}
        words = [w for w in (look or "").replace(",", " ").split() if w]
        out = []
        for w in words:
            if w.lower() in stops:
                if out:
                    break
                continue
            out.append(w)
            if len(out) >= 3:
                break
        return " ".join(out) or "character"

    if n == 2:
        return (f", two characters in the same frame, {_tag(looks[0])} positioned on the left, "
                f"{_tag(looks[1])} positioned on the right, both clearly visible, "
                "two-shot composition, clear separation between the two, no overlapping")
    return ", multiple characters in the same frame, standing apart, clear separation between characters"


async def _chat_json(prompt: str, system: str, *, model: str = "qwen3.5:4b",
                     retries: int = 2, on_stage=None) -> dict:
    ollama = OllamaAdapter()
    last_err = None
    for attempt in range(retries + 1):
        try:
            raw = await ollama.chat(prompt, system=system, model=model,
                                    json_mode=True, temperature=LLM_TEMP)
            return _extract_json(raw)
        except Exception as e:
            last_err = e
            if on_stage:
                on_stage(f"JSON 解析失败（第 {attempt + 1} 次），重试")
    raise RuntimeError(f"LLM 结构化输出失败: {last_err}")


# ---------- 1. 大纲（第三章：高概念 + 强钩子） ----------

async def generate_outline(db, task, params: dict) -> dict:
    """一句话/大纲 → 高概念 + 人物小传 + 分集大纲。params: {project_id, idea, num_episodes, genre?}

    数量硬保证（实测：qwen 4B 对"共 N 集"只给一半，60 集更不可能单次生成）：
    按 6 集/批循环生成，每批带已有分集摘要做上下文防重复，直到凑满 N 或连续补不齐。
    """
    from ..scheduler.queue import update_progress
    from ..db import Episode

    n = max(1, min(int(params.get("num_episodes") or 3), 60))
    update_progress(db, task, 0.05, "调用本地 LLM 生成高概念与分集大纲")
    # idea 空时回落到项目一句话描述（前端已自动带入，这里兜底防其他入口漏传）
    idea = (params.get("idea") or "").strip()
    if not idea:
        from ..db import Project
        p = db.get(Project, params.get("project_id"))
        idea = (getattr(p, "description", "") or "").strip()
    if not idea:
        raise RuntimeError("缺少创意输入：请在大纲输入框填写一句话描述或大纲")
    system = (
        "你是资深短剧策划。第一步用高概念公式提炼卖点：熟悉设定 + 颠覆性反差 = 高概念。"
        "第二步按三幕剧逻辑拆分集：每集解决一个具体矛盾（小反转），结尾设强钩子。"
        '输出 JSON：{"high_concept":"一句话卖点","characters":[{"name":"","brief":"身份+性格反差+欲望"}],'
        '"episodes":[{"idx":1,"title":"","summary":"150-300字梗概","hook":"本集结尾钩子一句话"}]}'
        "episodes 数组必须恰好包含要求的集数，一集都不能少。"
    )
    prompt = (
        f"题材/风格：{params.get('genre') or '不限'}\n"
        f"全剧共 {n} 集，每集 1-2 分钟竖屏短剧。\n"
        f"创意/大纲：{idea}\n请输出 JSON。"
    )

    # 首批：高概念 + 人物小传 + 第一批分集
    first = await _chat_json(prompt, system, on_stage=lambda m: update_progress(db, task, 0.1, m))
    high_concept = str(first.get("high_concept", ""))
    chars_brief = first.get("characters", [])
    batch_eps = first.get("episodes", [])
    all_eps: list[dict] = []
    seen_titles: set[str] = set()
    for e in batch_eps:
        t = str(e.get("title", "")).strip()
        if e.get("summary") and t and t not in seen_titles:
            seen_titles.add(t)
            all_eps.append({"title": t, "summary": str(e.get("summary", "")),
                            "hook": str(e.get("hook", ""))})

    # 补齐循环：每批 6 集，带最近分集摘要做上下文，LLM 偷懒就继续催
    BATCH = 6
    rounds = 0
    while len(all_eps) < n and rounds < 12:
        rounds += 1
        start = len(all_eps) + 1
        want = min(n - len(all_eps), BATCH)
        update_progress(db, task, 0.1 + 0.8 * (len(all_eps) / max(n, 1)),
                        f"分集 {len(all_eps) + 1}-{len(all_eps) + want}/{n}（第 {rounds} 轮补齐）")
        ctx = "已有分集（严禁重复，剧情线顺延）:\n" + "\n".join(
            f"- 第{i + 1}集《{e['title']}》: {e['summary'][:70]}"
            for i, e in enumerate(all_eps[-6:]))
        p2 = (
            f"题材/风格：{params.get('genre') or '不限'}\n"
            f"全剧共 {n} 集；高概念：{high_concept}\n{ctx}\n\n"
            f"请继续创作第 {start} 集到第 {start + want - 1} 集，"
            f"共 {want} 集（episodes 数组必须恰好 {want} 个元素，idx 从 {start} 开始连续编号）。"
            "每集推进一个新矛盾，钩子强度递进。只输出 JSON。"
        )
        data = await _chat_json(p2, system)
        got = 0
        for e in data.get("episodes", []):
            t = str(e.get("title", "")).strip()
            if e.get("summary") and t and t not in seen_titles:
                seen_titles.add(t)
                all_eps.append({"title": t, "summary": str(e.get("summary", "")),
                                "hook": str(e.get("hook", ""))})
                got += 1
        if got == 0:   # 一轮颗粒无收：LLM 卡死，放弃避免死循环
            break

    # 落库（idx 统一重排 1..k，防止 LLM 乱编 idx）
    # 重生成 = 整体覆盖：先清本项目旧分集与镜头（大纲重走即流程重走，与重拆覆盖镜头同一闭环哲学）
    from ..db import Shot
    pid = params["project_id"]
    for s in db.scalars(select(Shot).join(
            Episode, Shot.episode_id == Episode.id).where(Episode.project_id == pid)).all():
        db.delete(s)
    for e in db.scalars(select(Episode).where(Episode.project_id == pid)).all():
        db.delete(e)
    db.commit()
    created = []
    for i, e in enumerate(all_eps[:n]):
        summary, hook = e["summary"], e["hook"]
        ep = Episode(project_id=params["project_id"], idx=i + 1,
                     title=e["title"][:300],
                     outline=(summary + (f"\n【钩子】{hook}" if hook else "")),
                     status="outline")
        db.add(ep)
        db.commit()
        db.refresh(ep)
        created.append({"id": ep.id, "idx": ep.idx, "title": ep.title,
                        "summary": summary, "hook": hook})
    if len(created) < n:
        note = f"（要求 {n} 集，模型 {rounds} 轮后产出 {len(created)} 集——可在分集列表查看，重新生成会覆盖）"
        update_progress(db, task, 1.0, f"大纲完成 {len(created)} 集{note}")
    else:
        update_progress(db, task, 1.0, f"大纲完成 {len(created)}/{n} 集")
    return {"high_concept": high_concept,
            "characters_brief": chars_brief,
            "episodes": created}


async def continue_outline(db, task, params: dict) -> dict:
    """续写分集：保留已有分集，从第 N+1 集继续生成 add 集，并逐集 AI 写剧本。
    params: {project_id, add_episodes?=10, genre?, model?}
    与 generate_outline（重建式）不同：只追加不清理，idx 接续已有分集。
    """
    from ..scheduler.queue import update_progress
    from ..db import Episode, Project

    pid = params["project_id"]
    add = max(1, min(int(params.get("add_episodes") or 10), 60))
    existing = db.scalars(select(Episode).where(Episode.project_id == pid)
                          .order_by(Episode.idx)).all()
    if not existing:
        raise RuntimeError("暂无分集，请先用「生成分集大纲」创建，再续写")
    if len(existing) + add > 60:
        add = 60 - len(existing)
        if add <= 0:
            raise RuntimeError("已达 60 集上限，无法续写")
    start_idx = existing[-1].idx + 1

    idea = (params.get("idea") or "").strip()
    if not idea:
        p = db.get(Project, pid)
        idea = (getattr(p, "description", "") or "").strip()
    if not idea:
        raise RuntimeError("缺少创意输入：项目一句话描述为空，请在续写时传入 idea")

    system = (
        "你是资深短剧策划。按三幕剧逻辑拆分集：每集解决一个具体矛盾（小反转），结尾设强钩子。"
        '输出 JSON：{"episodes":[{"idx":1,"title":"","summary":"150-300字梗概","hook":"本集结尾钩子一句话"}]}'
        "episodes 数组必须恰好包含要求的集数，一集都不能少，严禁与已有分集重复。"
    )
    all_new: list[dict] = []
    seen_titles = {e.title.strip() for e in existing if e.title}
    recent = [f"- 第{e.idx}集《{e.title}》: {(e.outline or '')[:70]}" for e in existing]
    BATCH = 6
    rounds = 0
    while len(all_new) < add and rounds < 12:
        rounds += 1
        want = min(add - len(all_new), BATCH)
        idx_from = start_idx + len(all_new)
        update_progress(db, task, 0.05 + 0.6 * (len(all_new) / add),
                        f"续写分集 {idx_from}-{idx_from + want - 1}（第 {rounds} 轮）")
        ctx = "已有分集（剧情线顺延）:\n" + "\n".join(recent[-6:])
        p2 = (
            f"题材/风格：{params.get('genre') or '不限'}\n"
            f"全剧创意：{idea}\n{ctx}\n\n"
            f"请继续创作第 {idx_from} 集到第 {idx_from + want - 1} 集，"
            f"共 {want} 集（episodes 数组必须恰好 {want} 个元素，idx 从 {idx_from} 开始连续编号）。"
            "每集推进一个新矛盾，钩子强度递进。只输出 JSON。"
        )
        data = await _chat_json(p2, system)
        got = 0
        for e in data.get("episodes", []):
            t = str(e.get("title", "")).strip()
            if e.get("summary") and t and t not in seen_titles:
                seen_titles.add(t)
                cur_idx = start_idx + len(all_new)
                all_new.append({"title": t, "summary": str(e.get("summary", "")),
                                "hook": str(e.get("hook", ""))})
                recent.append(f"- 第{cur_idx}集《{t}》: {str(e.get('summary', ''))[:70]}")
                got += 1
        if got == 0:   # 一轮颗粒无收：LLM 卡死，放弃避免死循环
            break
        # 每批立即落库：中断不丢已完成批次
        base = start_idx + len(all_new) - got
        for j, e in enumerate(all_new[-got:]):
            db.add(Episode(project_id=pid, idx=base + j,
                           title=e["title"][:300],
                           outline=(e["summary"] + (f"\n【钩子】{e['hook']}" if e["hook"] else "")),
                           status="outline"))
        db.commit()

    new_eps = db.scalars(select(Episode).where(Episode.project_id == pid)
                         .order_by(Episode.idx)).all()[-len(all_new):]
    # 逐集 AI 写剧本（单集失败不炸任务，保留 status=outline 可单独重写）
    created, failed = [], []
    for i, ep in enumerate(new_eps):
        update_progress(db, task, 0.7 + 0.28 * i / max(len(new_eps), 1),
                        f"写第 {ep.idx} 集剧本（{i + 1}/{len(new_eps)}）")
        try:
            prompt = f"本集标题：{ep.title}\n本集大纲：\n{ep.outline}\n\n请写本集完整剧本。"
            text = await OllamaAdapter().chat(prompt, system=SCRIPT_FORMAT_SYSTEM,
                                              model=params.get("model") or "qwen3.5:4b",
                                              temperature=LLM_TEMP)
            ep.script_text = text
            ep.status = "script"
            db.commit()
            created.append({"id": ep.id, "idx": ep.idx, "title": ep.title})
        except Exception as exc:
            db.rollback()
            failed.append({"idx": ep.idx, "error": str(exc)[:200]})
    update_progress(db, task, 1.0,
                    f"续写完成：新增 {len(new_eps)} 集（第 {start_idx}-{start_idx + len(new_eps) - 1} 集），"
                    f"剧本 {len(created)}/{len(new_eps)} 集" + ("，失败集可单独点「AI 写本集剧本」重试" if failed else ""))
    return {"added_episodes": len(new_eps), "start_idx": start_idx,
            "scripts_done": len(created), "scripts_failed": failed,
            "episodes": created}


# ---------- 2. 剧本（第一章：影视标准格式） ----------

SCRIPT_FORMAT_SYSTEM = (
    "你是拥有20年经验的短剧编剧。根据分集大纲写完整剧本，严格遵循以下影视标准格式，"
    "不要输出任何解释或 JSON：\n"
    "1. 场景题头行：场号-场景名[内/外][日/夜]，如：1-1 废弃仓库[内][夜]；"
    "场号 = 本集第几场戏，同一地点同一时间段的连续内容只写一个题头，"
    "仅在场景切换（地点变化或时间跳跃）时新增题头，一集 2-4 个场景，严禁每个节拍都开新场。\n"
    "2. 动作行以△开头：只写可视化动作/表情/环境，严禁心理描写（如“他心里想”），"
    "必须转换为动作或表情。\n"
    "3. 对白紧凑格式：角色名:(情绪/动作)台词内容。\n"
    "4. 重要音效用【音效】标注，屏幕文字用【字幕】标注。\n"
    "5. 画外音标(O.S.)，内心独白标(V.O.)。\n"
    "2分钟竖屏短剧约 800-1200 字，2-4 个场景，结尾必须留强钩子。直接输出剧本文本。"
)


async def write_episode_script(db, task, params: dict) -> dict:
    """分集大纲 → 本集剧本正文（标准格式）。params: {episode_id, model?}"""
    from ..scheduler.queue import update_progress
    from ..db import Episode

    ep = db.get(Episode, params["episode_id"])
    update_progress(db, task, 0.2, "按影视标准格式写剧本")
    prompt = f"本集标题：{ep.title}\n本集大纲：\n{ep.outline}\n\n请写本集完整剧本。"
    text = await OllamaAdapter().chat(prompt, system=SCRIPT_FORMAT_SYSTEM,
                                      model=params.get("model") or "qwen3.5:4b",
                                      temperature=LLM_TEMP)
    ep.script_text = text
    ep.status = "script"
    db.commit()
    return {"episode_id": ep.id, "script_length": len(text),
            "scenes_found": len(parse_script(text))}



class _SceneStub:
    """新拆出的场景（尚未入库）的最小占位对象。"""

    def __init__(self, d: dict):
        self.prompt_json = json.dumps(d, ensure_ascii=False)
        self.base_prompt = ""


def _scene_concept_for(scene_name: str, scenes_rows: dict) -> str:
    """场景概念解析：精确名 > 包含关系 > base_prompt > 原场景名。
    老资产 slots 为空时直接用已生成的英文 base_prompt，避免中文场景名进提示词。"""
    if not scene_name:
        return ""
    row = scenes_rows.get(scene_name)
    if row is None:
        for name, r in scenes_rows.items():
            if name and (name in scene_name or scene_name in name):
                row = r
                break
    if row is None:
        return "" if not re.search(r"[A-Za-z]", scene_name or "") else scene_name
    slots = json.loads(getattr(row, "prompt_json", "{}") or "{}")
    concept = _slots_concept(slots)
    if concept:
        return concept
    base = getattr(row, "base_prompt", "") or ""
    if base:
        return base
    # 没匹配到资产且场景名是纯中文：丢掉（中文 token 对 CLIP 是噪声）
    return "" if not re.search(r"[A-Za-z]", scene_name or "") else scene_name


# ---------- 3. 规则解析剧本（零 LLM，第一章格式） ----------

_SCENE_RE = re.compile(
    r"^\s*(\d+\s*[-－]\s*\d+|[一二三四五六七八九十]+)\s*[、.．]?\s*"
    r"(.+?)\s*[\[【［]\s*(内|外)\s*[\]】］]\s*[\[【［]\s*(日|夜|晨|黄昏|傍晚|凌晨)\s*[\]】］]\s*$")
_SFX_RE = re.compile(r"^【音效】\s*(.+)$")
_SUB_RE = re.compile(r"^【字幕】\s*(.+)$")
_ACTION_RE = re.compile(r"^△\s*(.+)$")
_DIALOG_RE = re.compile(
    r"^([^\s:：（(]{1,12})\s*(?:[（(]([^:：（)]{0,20})[)）])?\s*[:：]\s*"
    r"(?:[（(](.+?)[)）]\s*)?(.+)$")


def parse_script(text: str) -> list[dict]:
    """标准格式剧本 → 结构化场景块（规则解析，不依赖 LLM）。"""
    scenes: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\((V\.O\.|O\.S\.)\)\s*", "", line)   # 画外音/独白前缀剥离
        m = _SCENE_RE.match(line)
        if m:
            cur = {"no": m.group(1).replace("－", "-").replace(" ", ""),
                   "name": m.group(2).strip(), "int_ext": m.group(3),
                   "tod": m.group(4), "blocks": []}
            scenes.append(cur)
            continue
        if cur is None:
            continue
        if m := _SFX_RE.match(line):
            cur["blocks"].append({"type": "sfx", "text": m.group(1)})
        elif m := _SUB_RE.match(line):
            cur["blocks"].append({"type": "subtitle", "text": m.group(1)})
        elif m := _ACTION_RE.match(line):
            cur["blocks"].append({"type": "action", "text": m.group(1)})
        elif m := _DIALOG_RE.match(line):
            cur["blocks"].append({"type": "dialogue", "speaker": m.group(1),
                                  "emotion": (m.group(2) or m.group(3) or "").strip(),
                                  "text": (m.group(4) or "").strip()})
        else:
            cur["blocks"].append({"type": "action", "text": line})
    # 合并连续同名同时空场景（LLM 有时把每个节拍都开新场）
    merged: list[dict] = []
    for sc in scenes:
        if merged and (sc["name"], sc["int_ext"], sc["tod"]) == \
                (merged[-1]["name"], merged[-1]["int_ext"], merged[-1]["tod"]):
            merged[-1]["blocks"].extend(sc["blocks"])
        else:
            merged.append(sc)
    return merged


def _scene_script_text(scene: dict) -> str:
    out = [f"{scene['no']}-{scene['name']}[{scene['int_ext']}][{scene['tod']}]"]
    for b in scene["blocks"]:
        if b["type"] == "dialogue":
            emo = f"({b['emotion']})" if b.get("emotion") else ""
            out.append(f"{b['speaker']}{emo}:{b['text']}")
        elif b["type"] == "sfx":
            out.append(f"【音效】{b['text']}")
        elif b["type"] == "subtitle":
            out.append(f"【字幕】{b['text']}")
        else:
            out.append(f"△{b['text']}")
    return "\n".join(out)


# ---------- 4. 拆解（分场景 + 资产强制引用 + 代码组装提示词） ----------

CUTTING_RULES = (
    "切镜原则（20年经验导演，必须遵守）：\n"
    "1. 情绪显著转变处切镜，情绪积累用2-3个镜头铺垫\n"
    "2. 复杂动作拆“准备→执行→结果”多个镜头\n"
    "3. 人物增减/位置关系/主导关系变化时切新镜\n"
    "4. 场景或时间切换必须新镜，转场可用1-2s专用镜头\n"
    "5. 对话遵循视线乒乓：说话者→聆听者交替切镜\n"
    "6. 景别/角度/运镜有意义变化即新镜\n"
    "7. 特效/关键道具独占镜头并给足时长\n"
    "8. 每镜头3-8秒；景别循序渐进（远→全→中→近→特），不要跳切"
)


def _load_asset_lists(db, project_id: int) -> dict:
    """已确认资产清单（拆解必须引用，消灭二次理解）。"""
    from ..db import Character, Prop, Scene
    chars = db.scalars(select(Character)
                       .where(Character.project_id == project_id)).all()
    scenes = db.scalars(select(Scene)
                        .where(Scene.project_id == project_id)).all()
    props = db.scalars(select(Prop)
                       .where(Prop.project_id == project_id)).all()
    return {
        "characters": [{"name": c.name, "look": _flatten_slots(
            json.loads(c.prompt_json or "{}")) or c.base_prompt[:120]} for c in chars],
        "scenes": [{"name": s.name,
                    "concept": _slots_concept(json.loads(s.prompt_json or "{}")) or s.base_prompt[:120]}
                   for s in scenes],
        "props": [{"name": p.name} for p in props],
    }


_PROP_STOPWORDS = {"black", "white", "large", "small", "modern", "metal", "metallic",
                   "wooden", "plastic", "digital", "glass", "with", "and", "the", "of",
                   "blue", "light", "screen", "standard", "matte", "silver", "finish",
                   "transparent", "projection", "pattern", "motion", "facial", "expression",
                   "repetitive", "avatar", "figure"}


def _match_prop_names(texts: list[str], props_db: dict) -> list[str]:
    """props_json 为空时的兜底：用道具 subject 槽位英文词在动作/走位文本里做词边界匹配。

    拆解产出的动作文本是英文而道具名是中文，中文名永远匹配不上——
    所以从道具槽位 subject 提英文关键词（≥3 字母，去通用材质/颜色词），
    如「全息投影」→ holographic/mannequin、「签字笔」→ pen/ballpoint。
    只用 subject 槽位（details/purpose 里的 blue/light/screen 等通用词会全局误匹配）。
    """
    blob = " ".join(t or "" for t in texts).lower()
    if not blob.strip():
        return []
    hits: list[str] = []
    for n, row in props_db.items():
        slots = json.loads(getattr(row, "prompt_json", "{}") or "{}")
        kws = [w for w in re.findall(r"[a-zA-Z]{3,}", (slots.get("subject") or "").lower())
               if w not in _PROP_STOPWORDS]
        if any(re.search(rf"\b{re.escape(k)}\b", blob) for k in kws):
            hits.append(n)
    return hits


def _prop_tokens_for(prop_names: list[str] | None, props_rows: dict) -> str:
    """镜头引用道具 → 英文 token + 角色-道具互动整合词。

    此前 props_json 只存在镜头卡里、从未进提示词——角色与道具结合差的根因。
    token 来源：道具槽位 subject/details/material（interaction 槽位若有则带上互动方式）；
    未确认入库的道具名跳过（噪声不入）。
    """
    toks, interacts = [], []
    for n in prop_names or []:
        if not (n or "").strip():
            continue
        row = props_rows.get(n)
        if row is None:
            for name, r in props_rows.items():
                if name and (name in n or n in name):
                    row = r
                    break
        if row is None:
            continue
        slots = json.loads(getattr(row, "prompt_json", "{}") or "{}")
        t = _clean(", ".join(v for k in ("subject", "details", "material")
                             if (v := _clean(slots.get(k)))))
        if not t:
            t = _clean(getattr(row, "base_prompt", "") or "")
        if t and re.search(r"[A-Za-z]", t):
            toks.append(t)
        it = _clean(slots.get("interaction") or "")
        if it and re.search(r"[A-Za-z]", it):
            interacts.append(it)
    if not toks:
        return ""
    out = "props in scene: " + "; ".join(toks)
    if interacts:
        out += ", " + "; ".join(interacts)
    out += (", characters naturally holding and using the props, "
            "props and characters integrated in one coherent scene")
    return out


def _slots_concept(slots: dict) -> str:
    return ", ".join(v for k in ("space", "era", "elements", "light", "mood")
                     if (v := _clean(slots.get(k))))


def _entity_concept(entity_row, fallback_name: str) -> str:
    slots = json.loads(entity_row.prompt_json or "{}") if entity_row else {}
    return _slots_concept(slots)


async def _breakdown_scene(scene: dict, assets: dict, project_name: str,
                           model: str) -> dict:
    """单场景 → 镜头 JSON + 本场景新增实体候选（槽位化）。"""
    asset_lines = (
        "【已确认角色资产（镜头 characters 只能引用以下名字或列入 new_characters）】\n" +
        ("\n".join(f"- {c['name']}: {c['look']}" for c in assets["characters"]) or "（无）") +
        "\n【已确认场景资产（scene 字段必须引用以下名字）】\n" +
        ("\n".join(f"- {s['name']}: {s['concept'][:80]}" for s in assets["scenes"]) or "（无）") +
        "\n【已确认道具资产（props 引用以下名字或列入 new_props）】\n" +
        ("\n".join(f"- {p['name']}" for p in assets["props"]) or "（无）")
    )
    schema = json.dumps({**SHOT_SCHEMA, "new_characters": CANDIDATE_SCHEMA["characters"],
                         "new_scenes": CANDIDATE_SCHEMA["scenes"],
                         "new_props": CANDIDATE_SCHEMA["props"]}, ensure_ascii=False)
    system = (
        f"你是拥有20年资历的影视导演与分镜设计师，为短剧《{project_name}》拆解分镜。\n"
        f"{CUTTING_RULES}\n"
        "输出 JSON，结构严格遵守：\n" + schema +
        "\n要求：\n"
        "- characters/scene/props 只能引用资产清单中的名字；清单没有的新实体放入 new_*（同样格式）\n"
        "- new_props 只列核心叙事道具（推动剧情的信物/武器）与角色连接道具（与人物强绑定的随身物），"
        "并给 category=core/bond；货架、门窗等环境陈设一律不列（它们属于场景槽位 elements）\n"
        "- scene 字段填该镜头所在场景名；\n"
        "- subject_action/light/composition 用英文、客观具体、可视觉化，禁止抽象形容词（帅气/霸气）\n"
        "- dialogue 用中文台词原文；多句台词每行一句，格式「角色名（语气）：台词」，"
        "语气从【平静/低语/紧张/急促/愤怒/悲伤/惊喜/温柔/迟疑/兴奋/冷峻】中按剧情选一个，"
        "如「小安（低语）：欢迎光临」；旁白行不用前缀直接写；shot_size/camera 用中文\n"
        "- 运镜编排（硬性要求，禁止全片固定）：每场至少 2 个移动镜头（推/拉/横摇/移/跟/手持/升降/环绕）；"
        "禁止连续 3 个镜头使用相同的 camera_move+camera_speed 组合。运镜要贴合叙事："
        "开场定场镜用缓推或拉（交代空间）；角色有位移时优先跟/移/手持；对话正反打用固定或缓推+过肩；"
        "情绪强调用慢速推近（camera_speed=slow, camera_dir=in）；紧张/动作段落用 fast 或 whip\n"
        "- camera_speed 按情绪分配，不要全部 slow：日常对话 normal、氛围铺垫 slow、冲突/追逐 fast\n"
        "- 只输出 JSON"
    )
    prompt = (f"剧本场景：\n{_scene_script_text(scene)}\n\n{asset_lines}\n\n"
              f"请为该场景输出分镜 JSON。")
    data = await _chat_json(prompt, system, model=model)
    for k, default in (("shots", []), ("new_characters", []),
                       ("new_scenes", []), ("new_props", [])):
        if not isinstance(data.get(k), list):
            data[k] = default
    return data


_CAMERA_MOVE_EN2CN = {
    "fixed": "固定", "static": "固定", "push": "推", "push in": "推", "dolly in": "推",
    "pull": "拉", "pull back": "拉", "dolly out": "拉", "pan": "横摇", "pan left": "横摇",
    "pan right": "横摇", "tilt": "竖摇", "tilt up": "竖摇", "tilt_up": "竖摇",
    "tilt down": "竖摇", "tilt_down": "竖摇", "move": "移", "truck": "移",
    "tracking": "移", "follow": "跟", "tracking shot": "跟", "crane": "升降",
    "crane up": "升降", "orbit": "环绕", "handheld": "手持",
}


def _normalize_camera_values(shots: list[dict]) -> None:
    """运镜值域归一：LLM 偶发输出英文（fixed/push/follow…）映射回中文枚举，
    否则前端下拉与视频提示词的运镜映射双双失配。"""
    for s in shots:
        mv = (s.get("camera_move") or "").strip()
        low = mv.lower()
        if low in _CAMERA_MOVE_EN2CN:
            s["camera_move"] = _CAMERA_MOVE_EN2CN[low]
        elif mv and mv not in ("固定", "推", "拉", "横摇", "竖摇", "移", "跟", "升降", "环绕", "手持"):
            s["camera_move"] = "固定"
        sp = (s.get("camera_speed") or "").strip().lower()
        if sp not in ("slow", "normal", "fast", "whip"):
            s["camera_speed"] = "normal"


def _diversify_cameras(shots: list[dict]) -> None:
    """运镜多样性兜底：LLM 偷懒全填"固定/慢"时按叙事启发式重排。

    规则（与拆解指令同源）：
    - 首镜 = 缓推 in（定场交代空间）
    - 有 character_path 的镜 = 跟（人物位移必须镜头跟走）
    - 末镜 = 拉 out（收场）
    - 其余固定镜按序轮换 推/横摇/竖摇（打连续重复）
    - speed：角色位移镜 normal，固定镜 slow/normal 交替
    仅当整场移动镜占比 < 1/3 时才介入（尊重 LLM 已有的合理编排）。
    """
    moves = [s.get("camera_move") or "固定" for s in shots]
    if sum(m != "固定" for m in moves) >= max(1, len(shots) // 3):
        return
    n = len(shots)
    rot = ["推", "横摇", "固定", "竖摇"]
    ri = 0
    for i, s in enumerate(shots):
        path = (s.get("character_path") or "").strip()
        if i == 0:
            s["camera_move"], s["camera_dir"], s["camera_speed"] = "推", "in", "slow"
        elif i == n - 1 and n >= 3:
            s["camera_move"], s["camera_dir"], s["camera_speed"] = "拉", "out", "normal"
        elif path:
            s["camera_move"], s["camera_dir"], s["camera_speed"] = "跟", "", "normal"
        else:
            s["camera_move"] = rot[ri % len(rot)]
            ri += 1
            s["camera_dir"] = ""
            s["camera_speed"] = "slow" if s["camera_move"] in ("推", "竖摇") else "normal"
        if s["camera_move"] in ("推", "拉"):
            s["framing_start"] = s.get("framing_start") or s.get("shot_size", "")
            s["framing_end"] = "近景" if s["camera_move"] == "推" else "全景"


def _validate_scene_result(data: dict, assets: dict) -> list[str]:
    """内容级校验：只检查提示词槽位完整性；未知实体由 _promote_unknown 自动晋升。"""
    problems = []
    for i, shot in enumerate(data.get("shots", [])):
        if not shot.get("subject_action"):
            problems.append(f"镜头{i + 1}缺 subject_action")
    return problems


def _promote_unknown(data: dict, assets: dict, scene_name: str = "") -> list[str]:
    """实体晋升（第二章道具三分类 + 核心叙事阈值）：
    - 未知角色/场景 → 自动晋升候选占位
    - LLM 已声明的道具：core/bond 保留；ambient（环境氛围）不独立生成，记入 prop_notes
    - 镜头引用但未声明的道具：出现 ≥2 次才晋升（核心叙事阈值），否则视为环境陈设跳过
    """
    warns = []
    notes = data.setdefault("_prop_notes", {"merged_ambient": [], "skipped": []})
    if scene_name:
        known_scenes = ({s["name"] for s in assets["scenes"]}
                        | {s.get("name", "") for s in data.get("new_scenes", [])})
        if scene_name not in known_scenes:
            data.setdefault("new_scenes", []).append(
                {"name": scene_name, "description": "剧本新场景（拆解自动发现，需补全槽位）"})
            warns.append(f"新场景“{scene_name}”自动进入候选")
    known_chars = ({c["name"] for c in assets["characters"]}
                   | {c.get("name", "") for c in data.get("new_characters", [])})
    for shot in data.get("shots", []):
        for cname in shot.get("characters", []):
            if cname not in known_chars:
                data.setdefault("new_characters", []).append(
                    {"name": cname, "description": "剧本新角色（拆解自动发现，需补全槽位）"})
                known_chars.add(cname)
                warns.append(f"新角色“{cname}”自动进入候选")
    known_props = ({p["name"] for p in assets["props"]}
                   | {p.get("name", "") for p in data.get("new_props", [])})
    # LLM 声明的环境氛围道具 → 并入场景，不独立生成
    kept_props = []
    for p in data.get("new_props", []):
        if (p.get("category") or "core") == "ambient":
            notes["merged_ambient"].append(p.get("name", ""))
            warns.append(f"环境氛围道具“{p.get('name')}”并入场景底板")
        else:
            kept_props.append(p)
    data["new_props"] = kept_props
    # 镜头引用但未声明的道具：出现次数阈值
    ref_count: dict[str, int] = {}
    for shot in data.get("shots", []):
        for pname in shot.get("props", []):
            ref_count[pname] = ref_count.get(pname, 0) + 1
    for pname, cnt in ref_count.items():
        if pname in known_props:
            continue
        if cnt >= 2:
            data.setdefault("new_props", []).append(
                {"name": pname, "description": f"剧本关键道具（出现{cnt}次，自动晋升）",
                 "category": "core"})
            known_props.add(pname)
            warns.append(f"新道具“{pname}”出现{cnt}次，自动晋升核心候选")
        else:
            notes["skipped"].append(pname)
    return warns


async def breakdown_episode(db, task, params: dict) -> dict:
    """剧本正文 → 分场景拆镜 + 候选实体（槽位化）+ 组装好的每镜头提示词。"""
    from ..scheduler.queue import update_progress
    from ..db import Episode, Project

    ep = db.get(Episode, params["episode_id"])
    project = db.get(Project, ep.project_id)
    preset = project.style_preset if project else "anime_2d"
    model = params.get("model") or "qwen3.5:4b"

    update_progress(db, task, 0.05, "规则解析剧本场景块（零 LLM）")
    scenes = parse_script(ep.script_text)
    if not scenes:
        raise RuntimeError("未解析到任何场景题头（应形如“1-1 仓库[内][夜]”）。"
                           "请在剧本页检查格式或重写剧本。")
    assets = _load_asset_lists(db, ep.project_id)

    all_shots: list[dict] = []
    new_chars, new_scenes, new_props = [], [], []
    prop_notes = {"merged_ambient": [], "skipped": []}
    for si, scene in enumerate(scenes):
        update_progress(db, task, 0.1 + 0.8 * si / max(len(scenes), 1),
                        f"拆解场景 {si + 1}/{len(scenes)}：{scene['name']}")
        data = await _breakdown_scene(scene, assets, project.name if project else "", model)
        _promote_unknown(data, assets, scene["name"])
        problems = _validate_scene_result(data, assets)
        if problems:
            data = await _breakdown_scene(scene, assets, project.name if project else "", model)
            _promote_unknown(data, assets, scene["name"])
            problems2 = _validate_scene_result(data, assets)
            if problems2:  # 兜底：仍缺槽位则填占位值，不中断整个拆解
                for i, shot in enumerate(data["shots"]):
                    if not shot.get("subject_action"):
                        shot["subject_action"] = "cinematic shot of the scene"
        _normalize_camera_values(data["shots"])
        _diversify_cameras(data["shots"])
        for shot in data["shots"]:
            move = (shot.get("camera_move") or "固定").strip()
            path = (shot.get("character_path") or "").strip()
            # 决策：位移/运镜镜自动出尾帧，纯对话镜不出
            needs_end = 1 if (move in MOVING_CAMERA or path) else 0
            all_shots.append({
                "idx": len(all_shots) + 1,
                "scene_no": scene["no"], "scene_name": scene["name"],
                "int_ext": scene["int_ext"], "tod": scene["tod"],
                "duration": int(shot.get("duration") or 4),
                "shot_size": shot.get("shot_size", "中景"),
                "camera": shot.get("camera", "固定"),
                "camera_move": move,
                "camera_speed": shot.get("camera_speed", "normal"),
                "camera_dir": shot.get("camera_dir", ""),
                "framing_start": shot.get("framing_start", shot.get("shot_size", "")),
                "framing_end": shot.get("framing_end", shot.get("shot_size", "")),
                "camera_angle": shot.get("camera_angle", ""),
                "focal_length": shot.get("focal_length", ""),
                "focus_transition": shot.get("focus_transition", "none"),
                "blocking": shot.get("blocking", ""),
                "character_path": path,
                "end_action": shot.get("end_action", ""),
                "action": shot.get("subject_action", ""),
                "characters": shot.get("characters", []),
                "props": shot.get("props", []),
                "dialogue": shot.get("dialogue", ""),
                "sfx": shot.get("sfx", ""),
                "needs_end_frame": needs_end,
                "image_slots": {"subject_action": shot.get("subject_action", ""),
                                "end_action": shot.get("end_action", ""),
                                "light": shot.get("light", ""),
                                "shot_size": shot.get("shot_size", ""),
                                "framing_end": shot.get("framing_end", ""),
                                "camera": shot.get("camera", ""),
                                "composition": shot.get("composition", "")},
            })
        new_chars += [c for c in data.get("new_characters", []) if c.get("name")]
        new_scenes += [s for s in data.get("new_scenes", []) if s.get("name")]
        new_props += [p for p in data.get("new_props", []) if p.get("name")]
        notes = data.get("_prop_notes", {})
        prop_notes["merged_ambient"] += notes.get("merged_ambient", [])
        prop_notes["skipped"] += notes.get("skipped", [])

    update_progress(db, task, 0.95, "组装每镜头首帧/尾帧/视频提示词（风格锁+运动向量+活人感）")
    lip = bool(project.lifelike) if project else True
    lfull = bool(getattr(project, "lifelike_full", 0)) if project else False
    _assemble_shot_prompts(db, ep.project_id, preset, all_shots, new_chars, new_scenes,
                           lifelike=lip, lifelike_full=lfull)
    persist_shots(db, ep.id, ep.project_id, all_shots)

    ep.status = "broken_down"
    db.commit()
    prop_notes = {k: sorted(set(v)) for k, v in prop_notes.items()}
    return {
        "style_preset": preset,
        "scenes": [{"no": s["no"], "name": s["name"], "int_ext": s["int_ext"],
                    "tod": s["tod"],
                    "shot_count": sum(1 for sh in all_shots
                                      if sh["scene_no"] == s["no"])} for s in scenes],
        "shots": all_shots,
        "candidates": {"characters": _dedup(new_chars), "scenes": _dedup(new_scenes),
                       "props": _dedup(new_props)},
        "prop_notes": prop_notes,
        "known_assets": {k: [x["name"] for x in v] for k, v in assets.items()},
    }


def _dedup(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        if it.get("name") and it["name"] not in seen:
            seen.add(it["name"])
            out.append(it)
    return out


def _assemble_shot_prompts(db, project_id: int, preset: str, shots: list[dict],
                           new_chars: list[dict], new_scenes: list[dict],
                           lifelike: bool = True, lifelike_full: bool = False):
    """每镜头首帧/尾帧/视频提示词组装（M2.6 源码级增强版）。

    流程（借鉴 Jellyfish shot_video_prompt_pack + ArcReel 模板引擎）：
    1. 先做镜头连续性计算（动作拍点 / 屏幕朝向 / 前后承接）；
    2. 每个 stage 取可编辑模板（项目默认 > 全局默认 > 内置），变量由代码算好注入；
    3. 模板缺失/写坏时回退到原代码组装函数，保证链路不断。
    """
    from ..db import Character, Prop, Scene
    from .continuity import apply_continuity, beats_text, pick_beat, split_beats
    from .prompt_templates import render, resolve

    chars = {c.name: json.loads(c.prompt_json or "{}")
             for c in db.scalars(select(Character)
                                 .where(Character.project_id == project_id)).all()}
    scenes_db = {s.name: s for s in db.scalars(select(Scene)
                 .where(Scene.project_id == project_id)).all()}
    props_db = {p.name: p for p in db.scalars(select(Prop)
                .where(Prop.project_id == project_id)).all()}
    base_looks = {c.name: (c.base_prompt or "")
                  for c in db.scalars(select(Character)
                                      .where(Character.project_id == project_id)).all()}
    for c in new_chars:
        chars.setdefault(c["name"], c)
    for s in new_scenes:
        if s.get("name"):
            scenes_db.setdefault(s["name"], _SceneStub(s))

    s = get_style(preset)

    # 0) 连续性预计算：动作拍点 + 屏幕朝向 + 承接关系（就地写入 shots）
    for shot in shots:
        shot["action_beats"] = split_beats(shot.get("action", ""))
        shot.setdefault("atmosphere", "")
    apply_continuity(shots)

    tpl_ff, tid_ff = resolve(db, project_id, "shot_first_frame")
    tpl_ef, tid_ef = resolve(db, project_id, "shot_end_frame")
    tpl_vd, tid_vd = resolve(db, project_id, "shot_video")

    for shot in shots:
        scene_concept = _scene_concept_for(shot["scene_name"], scenes_db)
        char_looks = [_look_of(chars.get(n, {}), base_looks.get(n, '')) for n in shot["characters"]]
        char_looks = [x for x in char_looks if x]
        beats = shot["action_beats"]

        slots_en = dict(shot["image_slots"])
        slots_en["shot_size"] = _en_size(slots_en.get("shot_size", ""))
        slots_en["framing_end"] = _en_size(slots_en.get("framing_end", ""))

        common = {
            # 空镜（无角色入镜）按场景适配风格锁，禁止人像专用词进入无人画面
            "style_lock": s["style_lock"] if char_looks else style_lock_for("scene", preset),
            "scene": _clean(scene_concept),
            "characters": (", ".join(_clean(x) for x in char_looks)
                           + _multi_layout_hint(shot.get("characters"), char_looks)),
            "props": _prop_tokens_for(
                shot.get("props") or _match_prop_names(
                    [shot.get("action", ""), shot.get("blocking", "")], props_db),
                props_db),
            "lifelike": lifelike_tokens(preset, human=True, pose=False,
                                        consistent=not lifelike_full) if lifelike else "",
            "quality": QUALITY_SUFFIX,
        }

        # 1) 首帧：动作起拍（trigger），构图/景别/光影
        vars_ff = dict(common)
        vars_ff.update({
            "action": _clean(pick_beat(beats, "trigger") or slots_en.get("subject_action", "")),
            "atmosphere": _clean(shot.get("atmosphere", "")),
            "prev": _clean(shot.get("prev_summary", "")),
            "framing": _en_size(slots_en.get("shot_size", "")),
            "angle": _en_angle(shot.get("camera_angle", "")),
            "light": _clean(slots_en.get("light", "")),
            "composition": _clean(", ".join(x for x in [
                slots_en.get("composition", ""), shot.get("composition_anchor", "")] if x)),
        })
        rendered = render(tpl_ff, vars_ff)
        shot["image_prompt"] = rendered if len(rendered) > 20 else assemble_shot_prompt(
            slots_en, preset, scene_concept, char_looks, lifelike, lifelike_full)
        shot["prompt_template_id"] = tid_ff

        # 2) 尾帧：动作收束（aftermath）
        if shot.get("needs_end_frame"):
            vars_ef = dict(common)
            vars_ef.update({
                "end_action": _clean(pick_beat(beats, "aftermath") or slots_en.get("end_action", "")),
                "prev": _clean(shot.get("prev_summary", "")),
                "framing_end": _en_size(slots_en.get("framing_end", "")),
                "composition": _clean(slots_en.get("composition", "")),
            })
            rendered = render(tpl_ef, vars_ef)
            shot["end_frame_prompt"] = rendered if len(rendered) > 20 else assemble_end_frame_prompt(
                slots_en, preset, scene_concept, char_looks, lifelike, lifelike_full)
        else:
            shot["end_frame_prompt"] = ""

        # 3) 关键帧：动作峰值（peak），供宫格故事板/补帧使用
        vars_kf = dict(common)
        vars_kf.update({
            "action": _clean(pick_beat(beats, "peak") or slots_en.get("subject_action", "")),
            "atmosphere": _clean(shot.get("atmosphere", "")),
            "prev": _clean(shot.get("prev_summary", "")),
            "framing": _en_size(slots_en.get("shot_size", "")),
            "angle": _en_angle(shot.get("camera_angle", "")),
            "light": _clean(slots_en.get("light", "")),
            "composition": _clean(slots_en.get("composition", "")),
        })
        shot["key_frame_prompt"] = render(tpl_ff, vars_kf)

        # 4) 视频：三拍时间轴 + 运镜向量 + 站位 + 连续性
        motion = []
        if shot.get("camera_move") and shot["camera_move"] != "固定":
            d = {"推": "dolly in / push in", "拉": "dolly out / pull back",
                 "横摇": "pan", "竖摇": "tilt", "移": "truck / track sideways",
                 "跟": "follow the subject", "升降": "crane up-down",
                 "环绕": "orbit around the subject", "手持": "handheld follow"}.get(
                shot["camera_move"], shot["camera_move"])
            direction = {"left": "to the left", "right": "to the right", "up": "upward",
                         "down": "downward", "in": "closer", "out": "wider"}.get(
                shot.get("camera_dir", ""), "")
            speed = {"slow": "slow and steady", "normal": "normal pace",
                     "fast": "fast", "whip": "whip-fast"}.get(shot.get("camera_speed", ""), "")
            seg = f"{d} {direction} {speed}".strip()
            if shot.get("framing_start") and shot.get("framing_end"):
                seg += f", from {_en_size(shot['framing_start'])} to {_en_size(shot['framing_end'])}"
            motion.append(seg)

        vars_vd = dict(common)
        vars_vd.update({
            "beats": beats_text(beats, shot.get("duration", 4)),
            "camera": ", ".join(motion),
            "blocking": _clean(shot.get("blocking", "")),
            "character_path": _clean(shot.get("character_path", "")),
            "focus": shot.get("focus_transition", "") if shot.get("focus_transition") != "none" else "",
            "prev": _clean(shot.get("prev_summary", "")),
            "continuity": _clean(shot.get("continuity_guidance", "")),
            "duration": shot.get("duration", 4),
        })
        rendered = render(tpl_vd, vars_vd)
        if len(rendered) > 20:
            shot["video_prompt"] = rendered
        else:
            shot["video_prompt"] = ", ".join(x for x in [
                s["style_lock"] if char_looks else style_lock_for("scene", preset), scene_concept,
                _clean(shot["image_slots"].get("subject_action")),
                ", ".join(motion), _en_size(shot["shot_size"]),
                _en_angle(shot.get("camera_angle", "")), s["motion_hint"]] if x)
        shot["video_template_id"] = tid_vd


def persist_shots(db, episode_id: int, project_id: int, shots: list[dict]):
    """镜头卡落库（故事板数据层）：重建本集 shots（重拆即覆盖，保留已生成首尾帧路径）。"""
    from ..db import Shot
    old = db.scalars(select(Shot).where(Shot.episode_id == episode_id)).all()
    keep = {(o.idx): o for o in old}
    for o in old:
        db.delete(o)
    db.flush()
    for sh in shots:
        row = Shot(
            project_id=project_id, episode_id=episode_id, idx=sh["idx"],
            scene_no=sh["scene_no"], scene_name=sh["scene_name"],
            int_ext=sh["int_ext"], tod=sh["tod"], duration=sh["duration"],
            shot_size=sh["shot_size"], camera_move=sh.get("camera_move", "固定"),
            camera_speed=sh.get("camera_speed", "normal"),
            camera_dir=sh.get("camera_dir", ""),
            framing_start=sh.get("framing_start", ""), framing_end=sh.get("framing_end", ""),
            camera_angle=sh.get("camera_angle", ""), focal_length=sh.get("focal_length", ""),
            focus_transition=sh.get("focus_transition", "none"),
            blocking=sh.get("blocking", ""), character_path=sh.get("character_path", ""),
            subject_action=sh.get("action", ""), light=sh.get("image_slots", {}).get("light", ""),
            composition=sh.get("image_slots", {}).get("composition", ""),
            characters_json=json.dumps(sh.get("characters", []), ensure_ascii=False),
            props_json=json.dumps(sh.get("props", []), ensure_ascii=False),
            dialogue=sh.get("dialogue", ""), sfx=sh.get("sfx", ""),
            image_prompt=sh.get("image_prompt", ""),
            end_frame_prompt=sh.get("end_frame_prompt", ""),
            video_prompt=sh.get("video_prompt", ""),
            key_frame_prompt=sh.get("key_frame_prompt", ""),
            action_beats_json=json.dumps(sh.get("action_beats", []), ensure_ascii=False),
            atmosphere=sh.get("atmosphere", ""),
            mood_tags_json=json.dumps(sh.get("mood_tags", []), ensure_ascii=False),
            vfx_type=sh.get("vfx_type", "none"), vfx_note=sh.get("vfx_note", ""),
            screen_direction=sh.get("screen_direction", ""),
            composition_anchor=sh.get("composition_anchor", ""),
            prev_summary=sh.get("prev_summary", ""), next_goal=sh.get("next_goal", ""),
            continuity_guidance=sh.get("continuity_guidance", ""),
            needs_end_frame=int(sh.get("needs_end_frame", 0)))
        # 闭环保护：同序号镜头已生成过首帧/尾帧/视频 → 继承成果引用与状态。
        # 重拆是"回退重走流程"，不是丢弃已生成的产物；提示词变了用户可手动重新生成。
        prev = keep.get(sh["idx"])
        if prev is not None:
            if prev.first_frame_path and Path(prev.first_frame_path).exists():
                row.first_frame_path = prev.first_frame_path
            if prev.end_frame_path and Path(prev.end_frame_path).exists():
                row.end_frame_path = prev.end_frame_path
            if prev.video_path and Path(prev.video_path).exists():
                row.video_path = prev.video_path
            if row.first_frame_path:
                row.status = "video_ready" if row.video_path else "first_ready"
        db.add(row)
    db.commit()


# ---------- 6. 就地重组装提示词（不重跑 LLM，改模板/改运镜后秒级生效） ----------

def reassemble_episode_prompts(db, episode_id: int, project_id: int, preset: str,
                               lifelike: bool = True, lifelike_full: bool = False) -> int:
    """从已有镜头卡重建首帧/尾帧/关键帧/视频提示词（零 LLM 调用）。

    改提示词模板、改运镜向量、勾尾帧之后，用这个接口让结果立刻重算，
    不必再等一次 2 分钟的拆解——这是压住随机性的关键操作。
    """
    from ..db import Character, Prop, Scene, Shot
    from .continuity import apply_continuity, beats_text, pick_beat, split_beats
    from .prompt_templates import render, resolve

    rows = db.scalars(select(Shot).where(Shot.episode_id == episode_id)
                      .order_by(Shot.idx)).all()
    if not rows:
        return 0
    chars = {c.name: json.loads(c.prompt_json or "{}")
             for c in db.scalars(select(Character)
                                 .where(Character.project_id == project_id)).all()}
    scenes_db = {s.name: s for s in db.scalars(select(Scene)
                 .where(Scene.project_id == project_id)).all()}
    props_db = {p.name: p for p in db.scalars(select(Prop)
                .where(Prop.project_id == project_id)).all()}
    base_looks = {c.name: (c.base_prompt or "")
                  for c in db.scalars(select(Character)
                                      .where(Character.project_id == project_id)).all()}
    s = get_style(preset)

    # 用行数据重建可计算的镜头字典，跑一次连续性与拍点
    dicts = []
    for r in rows:
        dicts.append({
            "row": r, "idx": r.idx, "scene_name": r.scene_name,
            "action": r.subject_action, "blocking": r.blocking,
            "character_path": r.character_path, "duration": r.duration,
            "characters": json.loads(r.characters_json or "[]"),
            "props": json.loads(r.props_json or "[]"),
            "image_slots": {"subject_action": r.subject_action, "light": r.light,
                            "composition": r.composition, "shot_size": r.shot_size,
                            "framing_end": r.framing_end},
        })
    for d in dicts:
        d["action_beats"] = split_beats(d["action"])
    apply_continuity(dicts)

    tpl_ff, tid_ff = resolve(db, project_id, "shot_first_frame")
    tpl_ef, _ = resolve(db, project_id, "shot_end_frame")
    tpl_vd, _ = resolve(db, project_id, "shot_video")

    for d in dicts:
        r = d["row"]
        # 单镜头可挂自己的模板（特殊镜头：开场、定格、空镜等），未挂则回落到项目默认
        tpl_ff_shot, tid_x = (resolve(db, project_id, "shot_first_frame", r.prompt_template_id)
                              if getattr(r, "prompt_template_id", None) else (tpl_ff, tid_ff))
        scene_concept = _scene_concept_for(d["scene_name"], scenes_db)
        char_looks = [_look_of(chars.get(n, {}), base_looks.get(n, '')) for n in d["characters"]]
        char_looks = [x for x in char_looks if x]
        common = {
            # 空镜（无角色入镜）按场景适配风格锁，禁止人像专用词进入无人画面
            "style_lock": s["style_lock"] if char_looks else style_lock_for("scene", preset),
            "scene": _clean(scene_concept),
            "characters": (", ".join(_clean(x) for x in char_looks)
                           + _multi_layout_hint(d.get("characters"), char_looks)),
            "props": _prop_tokens_for(
                d.get("props") or _match_prop_names(
                    [d.get("action", ""), d.get("blocking", "")], props_db),
                props_db),
            "lifelike": lifelike_tokens(preset, human=True, pose=False,
                                        consistent=not lifelike_full) if lifelike else "",
            "quality": QUALITY_SUFFIX,
        }
        v = dict(common)
        v.update({
            "action": _clean(pick_beat(d["action_beats"], "trigger") or d["action"]),
            "atmosphere": _clean(r.atmosphere), "framing": _en_size(r.shot_size),
            "prev": _clean(d.get("prev_summary", "")),
            "angle": _en_angle(r.camera_angle), "light": _clean(r.light),
            "composition": _clean(", ".join(x for x in [
                r.composition, d.get("composition_anchor", "")] if x)),
        })
        r.image_prompt = render(tpl_ff_shot, v)
        r.prompt_template_id = tid_x
        v2 = dict(common)
        v2.update({"end_action": _clean(pick_beat(d["action_beats"], "aftermath") or d["action"]),
                   "prev": _clean(d.get("prev_summary", "")),
                   "framing_end": _en_size(r.framing_end or r.shot_size),
                   "composition": _clean(r.composition)})
        r.end_frame_prompt = render(tpl_ef, v2) if r.needs_end_frame else ""
        v3 = dict(common)
        v3.update({
            "action": _clean(pick_beat(d["action_beats"], "peak") or d["action"]),
            "atmosphere": _clean(r.atmosphere),
            "prev": _clean(d.get("prev_summary", "")),
            "framing": _en_size(r.shot_size), "angle": _en_angle(r.camera_angle),
            "light": _clean(r.light), "composition": _clean(r.composition),
        })
        r.key_frame_prompt = render(tpl_ff, v3)

        motion = []
        if r.camera_move and r.camera_move != "固定":
            mv = {"推": "dolly in / push in", "拉": "dolly out / pull back",
                  "横摇": "pan", "竖摇": "tilt", "移": "truck / track sideways",
                  "跟": "follow the subject", "升降": "crane up-down",
                  "环绕": "orbit around the subject", "手持": "handheld follow"}.get(
                r.camera_move, r.camera_move)
            dr = {"left": "to the left", "right": "to the right", "up": "upward",
                  "down": "downward", "in": "closer", "out": "wider"}.get(r.camera_dir, "")
            sp = {"slow": "slow and steady", "normal": "normal pace",
                  "fast": "fast", "whip": "whip-fast"}.get(r.camera_speed, "")
            seg = f"{mv} {dr} {sp}".strip()
            if r.framing_start and r.framing_end:
                seg += f", from {_en_size(r.framing_start)} to {_en_size(r.framing_end)}"
            motion.append(seg)
        v4 = dict(common)
        v4.update({
            "beats": beats_text(d["action_beats"], r.duration),
            "camera": ", ".join(motion), "blocking": _clean(r.blocking),
            "character_path": _clean(r.character_path),
            "focus": r.focus_transition if r.focus_transition != "none" else "",
            "prev": _clean(d.get("prev_summary", "")),
            "continuity": _clean(d.get("continuity_guidance", "")),
            "duration": r.duration,
        })
        r.video_prompt = render(tpl_vd, v4)

        r.action_beats_json = json.dumps(d["action_beats"], ensure_ascii=False)
        r.screen_direction = d.get("screen_direction", "")
        r.composition_anchor = d.get("composition_anchor", "")
        r.prev_summary = d.get("prev_summary", "")
        r.next_goal = d.get("next_goal", "")
        r.continuity_guidance = d.get("continuity_guidance", "")
        # 注意：prompt_template_id 已在上方按"单镜自定义 > 默认"写为 tid_x，
        # 此处不得再用 tid_ff 无条件覆盖（否则单镜特殊模板被重组操作抹掉）。
    db.commit()
    return len(dicts)


# ---------- 5. 候选 → 正式资产提示词组装（供 api.confirm_candidates 调用） ----------

def build_candidate_prompts(preset: str, cands: dict) -> dict:
    """槽位 → base_prompt（代码组装，LLM 不再自由发挥）。"""
    return {
        "characters": [(c, assemble_character_prompt(c, preset,
                                                     c.get("portrait_mode", "sheet")))
                       for c in cands.get("characters", [])],
        "scenes": [(s, assemble_scene_prompt(s, preset, fallback_subject=s.get("name", "")))
                   for s in cands.get("scenes", [])],
        "props": [(p, assemble_prop_prompt(p, preset, fallback_subject=p.get("name", "")))
                  for p in cands.get("props", [])],
    }


SLOT_FIELDS = {
    "character": ("identity", "ethnicity", "appearance", "face", "hair", "clothing", "makeup",
                  "accessories", "expression", "pose", "chibi", "palette"),
    "scene": ("space", "era", "elements", "light", "mood"),
    "prop": ("category", "subject", "purpose", "era", "details", "material", "interaction"),
}

SLOT_GUIDE = {
    "character": ("按第二章九段式角色公式：identity=性别,年龄段,职业/身份；"
                  "ethnicity=国家/地区形象，必须从固定枚举中按角色背景选一个（有就写，没有则空串）："
                  "chinese/korean/japanese/american/european/african/indian/southeast asian/"
                  "middle eastern/latin/russian，如韩国财阀→korean、印度程序员→indian；"
                  "appearance=身高参照,体型,年龄感"
                  "（要具体，如接近180cm/比同龄人矮半个头）；face=脸型+五官+记忆点（痣/疤/耳洞等区分标志）；"
                  "hair=发型发色；clothing=按上身-下装-鞋三段描述（基础着装要具体到款式，如风衣/制服/机能服/军靴）；"
                  "makeup=妆造；accessories=1-2个标志性配件（宁缺勿多，配件是辨识度关键）；expression=常见表情"
                  "（写成五官动作：嘴角微翘/眉头微皱/眼神冷淡，禁止抽象词如帅气/冷酷）；pose=常态姿态（双手插兜/抱臂/"
                  "站姿笔直）；chibi=Q版形象特点；palette=主色+辅助色（如黑金/白蓝）。"
                  "信息聚焦：每个角色保留1-2个核心设计重点；抽象形容词一律转成可视觉化的五官或服饰符号。"
                  "全部用英文短语填写，禁止整句、禁止中文、无信息则空串。"
                  "禁止用 figure/silhouette 等模糊主体词，身份必须写明性别与年龄。"),
    "scene": ("按第二章场景公式：space=空间类型+主要结构与物件；era=时代与风格；"
              "elements=关键陈设元素（前景/中景/远景层次）；light=光源,时段,色调；mood=氛围情绪。英文短语。"),
    "prop": ("按第二章道具公式：category=core/bond/ambient；subject=物品本体；"
             "purpose=剧情功能；era=时代标签；details=形状,纹理,铭刻；material=材质与色彩；"
             "interaction=与角色的交互方式（core/bond 必填）。英文短语。"),
}


def _strip_unspecified(slots: dict) -> dict:
    """清掉 LLM 的占位词段（"unspecified bottom" / "none" / "n/a"）。

    实测：重铸时 LLM 对未知信息会填 "color unspecified, style unspecified"，
    原样进提示词既稀释权重又教坏底模。按逗号分段剔除，保留有效段。
    """
    out = {}
    for k, v in slots.items():
        if not isinstance(v, str):
            out[k] = v
            continue
        segs = [s.strip() for s in v.split(",")
                if s.strip() and "unspecified" not in s.lower()
                and s.lower() not in ("none", "n/a", "not specified", "unknown")]
        if segs:
            out[k] = ", ".join(segs)
    return out


async def rebuild_slots(db, task, params: dict):
    """旧资产槽位重铸：从「名称+描述」按方法论模板反推结构化槽位（本地 LLM）。"""
    from ..db import Character, Scene, Prop, Project
    from ..scheduler.queue import update_progress

    etype = params["entity_type"]
    table = {"character": Character, "scene": Scene, "prop": Prop}[etype]
    row = db.get(table, params["entity_id"])
    if not row:
        raise RuntimeError("实体不存在")
    project = db.get(Project, row.project_id)
    preset = project.style_preset if project else "anime_2d"

    fields = SLOT_FIELDS[etype]
    schema = ",\n".join(f'    "{f}": "英文短语（无信息填空串）"' for f in fields)
    system = ("你是影视美术指导，负责把一句资产描述拆成结构化设计槽位。"
              "只输出 JSON，键为 slots，值是英文字段；不得编造描述里没有的关键设定。")
    prompt = (f"资产类型：{etype}\n名称：{params['name']}\n描述：{params['description']}\n\n"
              f"填写规则：{SLOT_GUIDE[etype]}\n\n"
              f"输出 JSON：\n{{\n  \"slots\": {{\n{schema}\n  }}\n}}")
    update_progress(db, task, 0.1, "调用本地 LLM 反推槽位")
    data = await _chat_json(prompt, system)
    slots = data.get("slots") or {}
    slots = {k: _clean(v) for k, v in slots.items() if k in fields and v}
    slots = _strip_unspecified(slots)

    row.prompt_json = json.dumps(slots, ensure_ascii=False)
    lifelike = bool(project.lifelike) if project else True
    lfull = bool(getattr(project, "lifelike_full", 0)) if project else False
    if etype == "character":
        # 【硬性要求】角色资产必须三视图：重建槽位时归一 portrait_mode 并按 sheet 重组
        row.portrait_mode = "sheet"
        row.base_prompt = assemble_character_prompt(slots, preset, "sheet",
                                                    lifelike, lfull)
    elif etype == "scene":
        # LLM 再漏 space 时回退场景名，保证提示词永远有空间主体词
        if not (slots.get("space") or "").strip():
            slots.setdefault("space", row.name or "")
            row.prompt_json = json.dumps(slots, ensure_ascii=False)
        row.base_prompt = assemble_scene_prompt(slots, preset, lifelike,
                                                fallback_subject=row.name)
    else:
        # LLM 再漏 subject 时回退道具名，保证提示词永远有物品本体词
        if etype == "prop" and not (slots.get("subject") or "").strip():
            slots.setdefault("subject", row.name or "")
            row.prompt_json = json.dumps(slots, ensure_ascii=False)
        row.base_prompt = assemble_prop_prompt(slots, preset, lifelike,
                                               fallback_subject=row.name)
    db.commit()
    update_progress(db, task, 1.0, "槽位重铸完成")
    return {"entity_type": etype, "entity_id": row.id, "slots": slots,
            "base_prompt": row.base_prompt}


async def refine_text(db, task, params: dict) -> dict:
    """续写/润色。params: {text, action: 'polish'|'continue', model?} → {text}"""
    action = params.get("action", "polish")
    system = ("你是短剧编剧编辑。" + ("润色给定剧本文本，保持标准剧本格式与人物。" if action == "polish"
              else "续写给定剧本文本约300字，保持标准剧本格式与风格连贯。") + "直接输出文本。")
    text = await OllamaAdapter().chat(params["text"], system=system,
                                      model=params.get("model") or "qwen3.5:4b",
                                      temperature=LLM_TEMP)
    return {"text": text}

