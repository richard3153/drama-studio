"""镜头生成服务（M3）：首帧 / 尾帧 / 双帧 i2v 视频 / 九宫格故事板。

分工（对齐 Jellyfish / ArcReel 的 stage 划分）：
- 首帧、尾帧：单图生成（SDXL 底模，按风格族选模型），走镜头卡里已组装好的提示词；
- 视频：Wan2.2 i2v 双帧链路（Q4 GGUF + 4 步 LoRA），首帧必给、尾帧按 needs_end_frame 决定；
- 九宫格：宫格候选构图，仅动漫族开放，裁单格可直接当首帧。
"""
from __future__ import annotations

import asyncio
import json
import math
import random
from pathlib import Path

from sqlalchemy import select

from ..adapters.comfyui_adapter import ComfyUIAdapter, ComfyUIError
from ..config import BASE_DIR
from ..db import AssetImage, Project, SessionLocal, Shot, TaskRecord
from ..scheduler.queue import update_progress
from ..scheduler.vram import pick_model, registry
from ..style_presets import ANTI_OVER_RENDER_NEG, style_family
from .dialects import clamp_duration, negative_for as dialect_negative, wrap_video_prompt
from .prompt_templates import neg_for

ASSETS_ROOT = BASE_DIR / "data" / "projects"

FRAME_WF = "scene_sdxl.json"     # 单图文生图（构图由提示词承载，SDXL 最省显存）
# 视频模板：低显存档默认 Wan2.1 480P fp8 + 4 步蒸馏（单模型，8G 实测 480x832x33 ≈108s）；
# Wan2.2 Q4 GGUF 双模型画质更好但 GGUF 权重在显存不足时要 CPU 反量化，实测 18 分钟/33 帧，只作高质离线档。
VIDEO_WF_BY_MODEL = {
    "vid_wan21_480p": "i2v_wan21_480p.json",
    "vid_wan22_flf_q4": "i2v_first_last.json",
}
VIDEO_WF = "i2v_wan21_480p.json"
GRID_WF = "grid_storyboard.json"
IPA_WF = "scene_ipadapter.json"      # SDXL IPAdapter 锁脸（easy ipadapterApply，PLUS 预设）
IPA_WF_DUAL = "scene_ipadapter_dual.json"  # 双人镜链式双 IPA（两张单人参考串接）
IPA_WEIGHT = 0.75                    # 2026-11-22 调优：0.7 身份偏弱（参考图治理后可承受更高权重）；>0.85 会开始重复主体

NEGATIVE = ("nsfw, lowres, bad anatomy, bad hands, text, watermark, "
            "signature, jpeg artifacts, worst quality, blurry, deformed, "
            + ANTI_OVER_RENDER_NEG)


def _res(project: Project | None) -> tuple[int, int]:
    """镜头帧分辨率：跟随项目全局画幅（IPA 通道压长边 ≤832，宽幅会把单人复制成多人）。"""
    from ..aspect import shot_dims
    aspect = getattr(project, "aspect_ratio", None) if project else None
    return shot_dims(aspect)


def _is_single_portrait(path: str, meta: dict | None = None) -> bool:
    """参考图必须是单人特写（face_ref / 单人立绘），不能是整张多视角版式。

    判定顺序（2026-11-22 治理：此前竖版硬判把 672x652 近正方形三视图裁脸图整批误拒，
    实际喂给 IPAdapter 的只剩 253px 拼版小图，身份信号弱 → 脸锁不住）：
    1. meta 明确标记单脸特写（source=sheet_crop / compose 拼版裁脸）→ 直接可用；
    2. 文件名含版式词且无特写 meta → 拒（整张版式当 IPA 参考会把版式一起学进去）；
    3. 宽高比兜底：只拒宽横版拼版（w > h*1.25）；竖版/近正方形单人图均可用。
    """
    p = Path(path)
    if not p.exists():
        return False
    m = meta or {}
    if m.get("source") == "sheet_crop" or m.get("compose"):
        return True
    if any(k in p.name.lower() for k in ("sheet", "view", "board", "refine", "grid")):
        return False
    try:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
        return w <= h * 1.25
    except Exception:
        return False


def _face_candidates(db, cid: int) -> list[str]:
    """一个角色的可用单人参考图，按「特写优先→分辨率大优先→版本新优先」排序。

    分辨率即身份信号强度：672px 裁脸图远胜 253px 拼版小图（放大后糊成色块）。
    """
    rows = db.scalars(select(AssetImage).where(
        AssetImage.character_id == cid).order_by(AssetImage.id.desc())).all()
    out: list[tuple[str, tuple]] = []
    for r in rows:
        if r.kind not in ("face_ref", "base_look"):
            continue
        try:
            meta = json.loads(r.meta_json or "{}")
        except Exception:
            meta = {}
        if not _is_single_portrait(r.file_path, meta):
            continue
        try:
            from PIL import Image
            with Image.open(r.file_path) as im:
                area = im.size[0] * im.size[1]
        except Exception:
            area = 0
        score = (0 if r.kind == "face_ref" else 1, -area, -r.id)
        out.append((r.file_path, score))
    out.sort(key=lambda x: x[1])
    return [p for p, _ in out]


def _ref_overrides(shot: Shot) -> dict:
    """镜头级参考覆盖：{"角色名": path, "__scene__": path}，路径不存在自动忽略回落自动选。"""
    try:
        d = json.loads(getattr(shot, "ref_overrides_json", "") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _char_ref_paths(db, shot: Shot, limit: int = 2) -> list[str]:
    """按镜头 characters_json 顺序收集每人的单人特写参考图。

    优先级（2026-11-22 治理）：镜头卡手动指定 ref_overrides_json
    > 角色级默认脸锁 Character.face_lock_path（溯源窗口「设为默认参考」钉死版本）
    > 自动择优（_face_candidates：特写优先→分辨率大优先→版本新优先）。
    """
    from ..db import Character
    names = json.loads(shot.characters_json or "[]") if isinstance(shot.characters_json, str) else (shot.characters_json or [])
    if not isinstance(names, list) or not names:
        return []
    overrides = _ref_overrides(shot)
    chars = db.scalars(select(Character).where(Character.project_id == shot.project_id)).all()
    by_name = {c.name: c for c in chars}
    out: list[str] = []
    for n in names:
        ov = overrides.get(n)
        if ov and Path(ov).exists():
            out.append(ov)
            if len(out) >= limit:
                break
            continue
        c = by_name.get(n)
        if not c:
            continue
        lock = getattr(c, "face_lock_path", "") or ""
        if lock and Path(lock).exists():
            out.append(lock)
            if len(out) >= limit:
                break
            continue
        cands = _face_candidates(db, c.id)
        if cands:
            out.append(cands[0])
        if len(out) >= limit:
            break
    return out


def _char_ref_path(db, shot: Shot) -> str | None:
    """单人参考（宫格用）：取第一个角色的。"""
    refs = _char_ref_paths(db, shot, limit=1)
    return refs[0] if refs else None


def _dual_ref_composite(ref_paths: list[str], w: int, h: int, save_root: Path, tag: str) -> str:
    """双人镜双参考拼接：两张单人竖图各缩放到目标画布尺寸，左右拼成一张双人格参考。

    IPA plus 对"双人格参考图"会自然学成"画面里有两个人"，比链式双 IPA 简单且不易串脸。
    拼接图缓存到 tmp，同一镜头反复生成不重复合成。
    """
    from PIL import Image as PImage
    out = save_root.parent / "tmp_ref" / f"{tag}_{w}x{h}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return str(out)
    ims = []
    for p in ref_paths[:2]:
        im = PImage.open(p).convert("RGB")
        im = im.resize((w, h), PImage.LANCZOS)
        ims.append(im)
    canvas = PImage.new("RGB", (w * len(ims), h))
    for i, im in enumerate(ims):
        canvas.paste(im, (i * w, 0))
    canvas.save(out)
    return str(out)


async def _img2img(comfy, model, prompt: str, negative: str, ref_path: str,
                   w: int, h: int, denoise: float, steps: int, cfg: float,
                   seed: int, save_root: Path, prefix: str, timeout: float = 900):
    wf = comfy.load_template("refine_img2img.json")
    ref_name = await comfy.upload_image(ref_path)
    overrides = {
        "positive_text": prompt,
        "negative_text": negative,
        "LoadImage.image": ref_name,
        "ImageScale.width": w,
        "ImageScale.height": h,
        "ImageScale.crop": "center",
        "KSampler.seed": seed,
        "KSampler.denoise": denoise,
        "KSampler.steps": steps,
        "KSampler.cfg": cfg,
    }
    if model.get("family") == "sdxl":
        overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
    wf = comfy.apply_overrides(wf, overrides)
    return await comfy.run(wf, filename_prefix=prefix, save_root=save_root, timeout=timeout)


async def _ipa_gen(comfy, model, prompt: str, negative: str, ref_path: str,
                   w: int, h: int, seed: int, steps: int, cfg: float,
                   weight: float, save_root: Path, prefix: str, timeout: float = 900,
                   multi: bool = False, real: bool = False, ref_path2: str | None = None,
                   weight2: float | None = None):
    """SDXL IPAdapter 文生图：参考图只锁身份（脸/发型/服装基调），构图由提示词决定。

    实测坑（都踩过）：
    - 别手接 IPAdapterAdvanced（本机版本出抽象色块），走 easy ipadapterApply + PLUS 预设；
    - 画布别用 1216x832 宽幅，IPA 会把一个角色复制成三个人；短片统一 480x832 竖版。
    """
    # 双人镜走链式双 IPA（两张单人参考各挂一个 easy ipadapterApply），
    # 不用双人格拼接图——实测拼接图会被 IPA 学成"角色设定板拼版"。
    if multi:
        wf = comfy.load_template(IPA_WF_DUAL)
        ref_name = await comfy.upload_image(ref_path)
        ref2_name = await comfy.upload_image(ref_path2)
        overrides = {
            "positive_text": prompt,
            "negative_text": negative,
            "LoadImage@0.image": ref_name,
            "LoadImage@1.image": ref2_name,
            "easy ipadapterApply@0.weight": weight,
            "easy ipadapterApply@1.weight": weight2 if weight2 is not None else weight,
            "EmptyLatentImage.width": w,
            "EmptyLatentImage.height": h,
            "KSampler.seed": seed,
            "KSampler.steps": steps,
            "KSampler.cfg": cfg,
        }
        if model.get("family") == "sdxl":
            overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
        wf = comfy.apply_overrides(wf, overrides)
        return await comfy.run(wf, filename_prefix=prefix, save_root=save_root, timeout=timeout)

    wf = comfy.load_template(IPA_WF)
    ref_name = await comfy.upload_image(ref_path)
    # IPA 权重偏高时底模容易在同一张里复制出第二个同样的人，负面里显式压掉；
    # 双人镜（multi）需要两个人，不能压 multiple people。
    if not multi:
        negative = (negative or "") + ", multiple people, duplicate character, cloned face, twin"
    negative = (negative or "") + ", character sheet, multiple views, sketch, rough lines"
    # 写实底模脸型变异治理（用户实测：RealVisXL 上脸型漂移）：负面里锁脸型一致性
    if model.get("family") == "sdxl" and real:
        negative += (", different face, inconsistent face, changing facial features, "
                     "distorted face, asymmetrical face, cross-eyed, doll face, "
                     "plastic skin, airbrushed skin, over-smoothed skin, beauty filter, "
                     "uncanny valley, waxy skin")
    overrides = {
        "positive_text": prompt,
        "negative_text": negative,
        "LoadImage.image": ref_name,
        "easy ipadapterApply.weight": weight,
        "EmptyLatentImage.width": w,
        "EmptyLatentImage.height": h,
        "KSampler.seed": seed,
        "KSampler.steps": steps,
        "KSampler.cfg": cfg,
    }
    if model.get("family") == "sdxl":
        overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
    wf = comfy.apply_overrides(wf, overrides)
    return await comfy.run(wf, filename_prefix=prefix, save_root=save_root, timeout=timeout)


def _motion_static_tokens(shot: Shot) -> str:
    """运动动作控制 → 首帧/尾帧静态姿态 token（运行时兜底，与 script_service 组装同源）。

    独立生成（不经 rebuild-prompts）时提示词可能落后于 motion_json 编辑，
    生成前补上：身体姿态+手部动作+表情状态+视线。
    """
    try:
        m = json.loads(getattr(shot, "motion_json", "") or "{}")
    except Exception:
        m = {}
    if not isinstance(m, dict):
        return ""
    parts = []
    if (m.get("posture") or "").strip():
        parts.append(f"body posture: {m['posture'].strip()}")
    if (m.get("gesture") or "").strip():
        parts.append(f"hand action: {m['gesture'].strip()}")
    if (m.get("expression") or "").strip():
        parts.append(f"facial state: {m['expression'].strip()}")
    if (m.get("gaze") or "").strip():
        parts.append(f"gaze: {m['gaze'].strip()}")
    return ", ".join(parts)


def _motion_video_tokens(shot: Shot) -> str:
    """运动动作控制 → 视频运动 token：幅度限定 + 次级联动 + 稳定性约束。"""
    try:
        m = json.loads(getattr(shot, "motion_json", "") or "{}")
    except Exception:
        m = {}
    if not isinstance(m, dict):
        return ""
    inten = {"subtle": "subtle, minimal amplitude", "natural": "natural amplitude",
             "strong": "broad, deliberate amplitude"}.get(m.get("intensity", ""), "")
    parts = [m[k].strip() for k in ("posture", "gesture", "expression", "gaze")
             if (m.get(k) or "").strip()]
    if inten:
        parts.append(f"action amplitude: {inten}")
    if (m.get("secondary") or "").strip():
        parts.append(f"secondary motion: {m['secondary'].strip()}")
    parts.append("smooth natural motion, stable framing, no jitter, no morphing, "
                 "feet do not slide")
    return ", ".join(x for x in parts if x)


def _vocab_positive(preset: str, genre: str = "") -> str:
    """风格词库 + 题材词库正向 token（anime cel 词系 / xianxia 仙侠词系 / 特效词系…
    + 红果爆款题材层：战神/赘婿/霸总/宫斗… 的 mood+hooks 名场面视觉）。"""
    from ..style_vocab import combined_shot_vocab
    return combined_shot_vocab(preset, genre)


def _shot_neg(stage: str, preset: str, extra: str = "", genre: str = "") -> str:
    """stage 负面基线 + 全局负面 + 风格词库负面 + 题材词库负面。

    风格串味治理：动漫模型必须禁摄影词（photorealistic 会拉出脏中间态），
    写实模型禁动漫词，词库按风格自动给出。
    题材串味治理：霸总剧禁贫民窟、种田剧禁赛博都市、悬疑禁明亮欢乐色等。
    """
    from ..style_vocab import style_vocab_negative, style_genre_negative
    parts = [neg_for(stage, extra), style_vocab_negative(preset),
             style_genre_negative(genre)]
    return ", ".join(x for x in parts if x)


def _scene_anchor(db, shot: Shot) -> str | None:
    """场景参考图三级回退（2026-11-22 治理：此前只认手动锚图，覆盖率≈0）：

    1. 镜头卡 ref_overrides_json 的 "__scene__"（溯源窗口手动指定，优先级最高）；
    2. Scene.anchor_path 手动锚图（资产页「设为锚点」）；
    3. 自动回退：该场景名下的 iso 45° 布局图优先（空间结构最完整，缩略图法本意），
       其次最新一张场景概念图——无需任何手动操作即生效。

    场景匹配：先精确名，后大小写/空白容错名（防拆解命名漂移导致锚图失联）。
    """
    from ..db import Scene, AssetImage
    ov = _ref_overrides(shot).get("__scene__")
    if ov and Path(ov).exists():
        return ov
    name = (getattr(shot, "scene_name", "") or "").strip()
    if not name:
        return None
    sc = db.scalars(select(Scene).where(
        Scene.project_id == shot.project_id,
        Scene.name == name)).first()
    if not sc:
        for cand in db.scalars(select(Scene).where(
                Scene.project_id == shot.project_id)).all():
            if (cand.name or "").strip().lower() == name.lower():
                sc = cand
                break
    if not sc:
        return None
    if getattr(sc, "anchor_path", "") and Path(sc.anchor_path).exists():
        return sc.anchor_path
    # 自动回退：meta.entity_id 挂在该场景名下的场景图（iso 布局图优先，最新优先）
    imgs = db.scalars(select(AssetImage).where(
        AssetImage.project_id == shot.project_id,
        AssetImage.kind == "scene").order_by(AssetImage.id.desc())).all()
    iso = plain = None
    for r in imgs:
        try:
            meta = json.loads(r.meta_json or "{}")
        except Exception:
            meta = {}
        if meta.get("entity_id") != sc.id:
            continue
        p = Path(r.file_path)
        if not p.exists():
            continue
        is_iso = bool(meta.get("iso_layout")) or "isometric" in (r.prompt or "").lower()
        if is_iso and iso is None:
            iso = r.file_path
        if plain is None:
            plain = r.file_path
    return iso or plain


async def _gen_frame(db, task, shot: Shot, project: Project, *, frame_type: str,
                     params: dict | None = None) -> Path:
    params = params or {}
    preset = (project.style_preset if project else "") or "anime_2d"
    genre = (getattr(project, "genre", "") if project else "") or ""
    fam = style_family(preset)
    model_key, model = await pick_model("scene", "low", style_family=fam,
                                        allowed_families=frozenset(("sdxl",)))
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    prompt = shot.end_frame_prompt if frame_type == "end" else shot.image_prompt
    if not prompt:
        raise RuntimeError(f"镜头 #{shot.idx} 的{'尾帧' if frame_type == 'end' else '首帧'}提示词为空，先点「重组装提示词」")
    # 生成时兜底承接：独立生成（无接力源）的同场景镜头也带上镜连续性提示，
    # 压"每个镜头都重新开始"的断裂感（接力 img2img 走 chain_shot_frame 自有承接词）
    if frame_type == "first":
        prev = db.scalars(select(Shot).where(
            Shot.episode_id == shot.episode_id,
            Shot.idx == shot.idx - 1)).first()
        if prev is not None and (prev.scene_name or "") == (shot.scene_name or "") \
                and "continuous" not in prompt:
            prompt = (prompt + ", continuous scene from the previous shot, same location, "
                      "consistent lighting and character appearance")
    # 运行时兜底：motion_json 里存了动作控制但提示词未含 → 生成前补上（编辑即时生效）
    mtok = _motion_static_tokens(shot)
    if mtok and mtok[:24].lower() not in prompt.lower():
        prompt = prompt + ", " + mtok
    # 运行时兜底：风格词库（按风格锁挂载的领域词）未进提示词时补上
    vtok = _vocab_positive(preset, genre)
    if vtok and vtok.split(",")[0].strip().lower() not in prompt.lower():
        prompt = prompt + ", " + vtok

    update_progress(db, task, 0.15, f"生成{ '尾帧' if frame_type=='end' else '首帧' }（{model_key}）")
    comfy = ComfyUIAdapter()
    w, h = _res(project)
    save_root = ASSETS_ROOT / str(shot.project_id) / "shots"
    neg = _shot_neg("shot_first_frame", preset, NEGATIVE, genre=genre)
    seed = random.randint(0, 2**31 - 1)
    prefix = f"drama_studio/p{shot.project_id}_s{shot.idx}_{frame_type}"

    # 一致性第一保险：SDXL IPAdapter 锁脸，默认开。
    # 有角色参考图就走 IPA（脸/发型/服装基调锁住，构图交给提示词）；
    # use_ref=0 的镜（纯空镜、群像、无人镜）才走纯文生图。
    refs = [] if params.get("use_ref") is False else _char_ref_paths(db, shot, limit=2)
    ipa_weight = float(params.get("ipa_weight") or IPA_WEIGHT)
    scene_ref = None if params.get("use_scene_ref") is False else _scene_anchor(db, shot)
    scene_ipa_w = float(params.get("scene_ipa_weight") or 0.4)
    real = fam == "photo"   # 写实底模需要额外锁脸负面（脸型变异治理）
    # 场景锁定优先（镜头卡开关）：直接以锚图为底图 img2img，环境还原度最高，
    # 代价是构图被锚图约束、无 IPA 锁脸（写实风格下脸可能漂移，用户权衡）。
    if params.get("scene_lock") and scene_ref:
        update_progress(db, task, 0.2,
                        f"场景锁定：锚图 img2img（denoise {params.get('scene_denoise', 0.45)}）")
        out = await _img2img(comfy, model, prompt, neg, scene_ref, w, h,
                             float(params.get("scene_denoise") or 0.45), 26, 6.0,
                             seed, save_root, prefix)
        if out:
            return out[0]
    if refs:
        multi = len(refs) >= 2
        if multi:
            ref = _dual_ref_composite(refs, w, h, save_root, f"p{shot.project_id}_s{shot.idx}")
            update_progress(db, task, 0.2,
                            f"IPAdapter 双人锁脸（{Path(refs[0]).name} + {Path(refs[1]).name}，weight {ipa_weight}）")
        else:
            ref = refs[0]
            update_progress(db, task, 0.2,
                            f"IPAdapter 锁脸（{Path(ref).name}，weight {ipa_weight}）"
                            + (f" + 场景锚图（weight {scene_ipa_w}）" if scene_ref else ""))
        try:
            # 单角色 + 场景锚图 → 双 IPA：槽0=角色脸，槽1=场景环境（独立低权重）
            use_dual = multi or bool(scene_ref)
            out = await _ipa_gen(comfy, model, prompt, neg, ref, w, h, seed, 26, 6.0,
                                 ipa_weight, save_root, prefix, multi=use_dual, real=real,
                                 ref_path2=(refs[1] if multi else scene_ref),
                                 weight2=(ipa_weight if multi else scene_ipa_w))
            if out:
                return out[0]
        except Exception as e:  # 锁脸失败不阻断出图，回落文生图
            update_progress(db, task, 0.25, f"IPAdapter 失败 → 回落文生图：{e}")
    elif scene_ref:
        # 纯空镜 + 场景锚图：单 IPA 挂锚图（锁环境风格与元素，构图交给提示词）
        update_progress(db, task, 0.2, f"IPAdapter 场景锚图（{Path(scene_ref).name}，weight {scene_ipa_w}）")
        try:
            out = await _ipa_gen(comfy, model, prompt, neg, scene_ref, w, h, seed, 26, 6.0,
                                 scene_ipa_w, save_root, prefix, real=real)
            if out:
                return out[0]
        except Exception as e:
            update_progress(db, task, 0.25, f"场景 IPA 失败 → 回落文生图：{e}")

    wf = comfy.load_template(FRAME_WF)
    overrides = {
        "positive_text": prompt,
        "negative_text": neg,
        "EmptyLatentImage.width": w,
        "EmptyLatentImage.height": h,
        "KSampler.seed": seed,
        "KSampler.steps": 26,
        "KSampler.cfg": 6.0,
    }
    if model.get("family") == "sdxl":
        overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
    wf = comfy.apply_overrides(wf, overrides)
    out = await comfy.run(wf, filename_prefix=prefix, save_root=save_root, timeout=900)
    if not out:
        raise ComfyUIError("首帧生成没有返回文件")
    return out[0]


async def generate_shot_frame(db, task, params: dict) -> dict:
    """params: shot_id, frame_type=first|end"""
    shot = db.get(Shot, params["shot_id"])
    if not shot:
        raise RuntimeError("镜头不存在")
    project = db.get(Project, shot.project_id)
    frame_type = params.get("frame_type", "first")
    path = await _gen_frame(db, task, shot, project, frame_type=frame_type, params=params)
    update_progress(db, task, 0.9, "写入镜头卡")
    if frame_type == "end":
        shot.end_frame_path = str(path)
    else:
        shot.first_frame_path = str(path)
        if not shot.video_path:
            shot.status = "first_ready"
    db.add(AssetImage(project_id=shot.project_id, kind=f"shot_{frame_type}",
                      file_path=str(path),
                      prompt=shot.end_frame_prompt if frame_type == "end" else shot.image_prompt,
                      meta_json=json.dumps({"shot_id": shot.id, "shot_idx": shot.idx},
                                           ensure_ascii=False)))
    db.commit()
    return {"shot_id": shot.id, "frame_type": frame_type, "path": str(path)}


async def generate_shot_video(db, task, params: dict) -> dict:
    """双帧 i2v：首帧必给，尾帧按 needs_end_frame。params: shot_id, duration?"""
    shot = db.get(Shot, params["shot_id"])
    if not shot:
        raise RuntimeError("镜头不存在")
    if not shot.first_frame_path or not Path(shot.first_frame_path).exists():
        raise RuntimeError("先出首帧再生成视频")

    project = db.get(Project, shot.project_id)
    model_key, model = await pick_model("video", params.get("prefer_tier"),
                                        params.get("model_key") or "vid_wan21_480p")
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]
    family = model.get("family", "wan22")
    wf_name = VIDEO_WF_BY_MODEL.get(model_key, VIDEO_WF)
    # 两套模板的采样键名不同：Wan2.2 双模型用两个 KSamplerAdvanced，Wan2.1 单段用 KSampler
    samp_prefix = "KSamplerAdvanced" if wf_name == "i2v_first_last.json" else "KSampler"

    fps = 16
    raw_duration = int(params.get("duration") or shot.duration or 5)
    duration = clamp_duration(raw_duration, family)      # 模型方言层收住时长上限
    length = max(17, min(121, int(round(duration * fps / 4.0)) * 4 + 1))
    # 单帧 i2v（无尾帧约束）超过约 3s 后 4 步蒸馏模型容易漂移、末帧跑飞（实测 65 帧末帧塌进货架），
    # 所以单帧模式封顶 49 帧；需要更长就走首尾帧双约束。
    has_end = bool(shot.needs_end_frame and shot.end_frame_path
                   and Path(shot.end_frame_path).exists())
    if not has_end:
        length = min(length, 49)
    prompt = wrap_video_prompt(shot.video_prompt, family, duration,
                               has_end_frame=bool(shot.needs_end_frame))
    # 运行时兜底：motion_json 动作控制 + 稳定性约束（编辑即时生效，旧提示词也补）
    preset = (project.style_preset if project else "") or "anime_2d"
    genre = (getattr(project, "genre", "") if project else "") or ""
    mtok = _motion_video_tokens(shot)
    if mtok and "no morphing" not in prompt:
        prompt = f"{prompt}, {mtok}"
    vtok = _vocab_positive(preset, genre)
    if vtok and vtok.split(",")[0].strip().lower() not in prompt.lower():
        prompt = f"{prompt}, {vtok}"

    update_progress(db, task, 0.1, f"上传首帧/尾帧（{model_key}，{duration}s / {length} 帧）")
    comfy = ComfyUIAdapter()
    wf = comfy.load_template(wf_name)
    start_name = await comfy.upload_image(shot.first_frame_path)

    seed = random.randint(0, 2**31 - 1)
    overrides = {
        "positive_text": prompt,
        "negative_text": dialect_negative(family, _shot_neg("shot_video", preset, genre=genre)),
        "LoadImage@0.image": start_name,
        f"{samp_prefix}.seed": seed,
        "WanFirstLastFrameToVideo.length": length,
        "CreateVideo.fps": fps,
    }
    if samp_prefix == "KSamplerAdvanced":
        overrides.pop("KSamplerAdvanced.seed", None)
        overrides["KSamplerAdvanced@0.noise_seed"] = seed
        overrides["KSamplerAdvanced@1.noise_seed"] = seed
    end_name = None
    if shot.needs_end_frame and shot.end_frame_path and Path(shot.end_frame_path).exists():
        end_name = await comfy.upload_image(shot.end_frame_path)
        overrides["LoadImage@1.image"] = end_name
    else:
        overrides["WanFirstLastFrameToVideo.end_image"] = None   # None = 摘掉该输入，退化为单帧 i2v

    w, h = _res(project)
    overrides["WanFirstLastFrameToVideo.width"] = w
    overrides["WanFirstLastFrameToVideo.height"] = h

    wf = comfy.apply_overrides(wf, overrides)
    update_progress(db, task, 0.3, f"{model_key} 推理中（8G 显存约 2-4 分钟/条）")
    save_root = ASSETS_ROOT / str(shot.project_id) / "shots"
    out = await comfy.run(wf, filename_prefix=f"drama_studio/p{shot.project_id}_s{shot.idx}_video",
                          save_root=save_root, timeout=2400)
    await comfy.free_memory()
    if not out:
        raise ComfyUIError("视频生成没有返回文件，检查 SaveVideo 节点")

    shot.video_path = str(out[0])
    shot.status = "video_ready"
    db.add(AssetImage(project_id=shot.project_id, kind="shot_video",
                      file_path=str(out[0]), prompt=prompt,
                      meta_json=json.dumps({"shot_id": shot.id, "fps": fps,
                                            "frames": length, "model_key": model_key,
                                            "end_frame": bool(end_name)}, ensure_ascii=False)))
    db.commit()
    update_progress(db, task, 1.0, "成片写入镜头卡")
    return {"shot_id": shot.id, "video_path": str(out[0]), "frames": length}


GRID_SHOTS = [
    "full body wide shot, center composition",
    "medium shot from waist up, slight low angle",
    "close-up on face, shallow depth of field",
    "over-the-shoulder shot from behind the subject",
    "side profile view, subject facing left",
    "high angle looking down",
    "low angle looking up, dramatic",
    "wide establishing shot with the subject small in frame",
    "three-quarter view, subject facing right",
]


async def generate_grid_storyboard(db, task, params: dict) -> dict:
    """九宫格候选构图（仅动漫/国潮/3D）：9 格逐张生成再拼联系表。

    为什么不一次性让底模画 "3x3 宫格"：SDXL 对面板布局服从度很差，实测会出多人叠影、
    脸和服装每格都不一样。逐格生成 + 同角色词 + 固定 seed 血统，再做 3x3 联系表，
    既保证一致性，每格本身也是可直接用的 480x832 首帧候选。
    """
    shot = db.get(Shot, params["shot_id"])
    if not shot:
        raise RuntimeError("镜头不存在")
    project = db.get(Project, shot.project_id)
    preset = (project.style_preset if project else "") or "anime_2d"
    genre = (getattr(project, "genre", "") if project else "") or ""
    if style_family(preset) not in ("anime", "paint", "3d"):
        raise RuntimeError("九宫格只对动漫/国潮/3D 风格开放（写实风格分辨率损耗大，建议关掉宫格）")
    if not shot.image_prompt:
        raise RuntimeError("镜头首帧提示词为空，先点「重组装提示词」")

    model_key, model = await pick_model("grid9", "low", style_family=style_family(preset),
                                        allowed_families=frozenset(("sdxl",)))
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    comfy = ComfyUIAdapter()
    wf = comfy.load_template(GRID_WF)
    save_root = ASSETS_ROOT / str(shot.project_id) / "shots"
    w, h = _res(project)
    base_seed = random.randint(0, 2**31 - 1)

    cells = []
    ref = None if params.get("use_ref") is False else _char_ref_path(db, shot)
    for i, spec in enumerate(GRID_SHOTS):
        update_progress(db, task, 0.1 + 0.08 * i, f"宫格 {i + 1}/9：{spec.split(',')[0]}")
        prompt_i = f"{shot.image_prompt}, {spec}"
        prefix = f"drama_studio/p{shot.project_id}_s{shot.idx}_g{i + 1}"
        out = None
        if ref:
            # 宫格也用 IPAdapter 锁脸：9 格构图不同、但必须是同一张脸
            try:
                out = await _ipa_gen(comfy, model, prompt_i,
                                     _shot_neg("shot_first_frame", preset, NEGATIVE, genre=genre), ref, w, h,
                                     base_seed + i, 22, 6.0,
                                     float(params.get("ipa_weight", 0.65)), save_root,
                                     prefix, timeout=600)
            except Exception:
                out = None
        if out:
            cells.append(str(out[0]))
            continue
        overrides = {
            "positive_text": prompt_i,
            "negative_text": _shot_neg("shot_first_frame", preset, NEGATIVE, genre=genre),
            "EmptyLatentImage.width": w,
            "EmptyLatentImage.height": h,
            "KSampler.seed": base_seed + i,
            "KSampler.steps": 22,
            "KSampler.cfg": 6.0,
        }
        if model.get("family") == "sdxl":
            overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
        wf_i = comfy.apply_overrides(comfy.load_template(GRID_WF), overrides)
        out = await comfy.run(wf_i, filename_prefix=prefix, save_root=save_root, timeout=600)
        if out:
            cells.append(str(out[0]))

    if not cells:
        raise ComfyUIError("宫格候选一张都没生成出来")

    update_progress(db, task, 0.85, "拼 3x3 联系表")
    from PIL import Image
    sheet = Image.new("RGB", (w * 3, h * 3), (24, 24, 24))
    for i, p in enumerate(cells[:9]):
        img = Image.open(p).convert("RGB").resize((w, h), Image.LANCZOS)
        sheet.paste(img, ((i % 3) * w, (i // 3) * h))
    sheet_path = save_root / f"p{shot.project_id}_s{shot.idx}_gridsheet.png"
    sheet.save(sheet_path)

    db.add(AssetImage(project_id=shot.project_id, kind="grid9", file_path=str(sheet_path),
                      prompt=shot.image_prompt,
                      meta_json=json.dumps({"shot_id": shot.id, "cells": cells},
                                           ensure_ascii=False)))
    db.commit()
    update_progress(db, task, 1.0, "宫格与 9 格候选写入资产库")
    return {"shot_id": shot.id, "grid_path": str(sheet_path), "cells": cells}


async def pick_grid_cell(db, task, params: dict) -> dict:
    """把某格宫格候选直接设为本镜首帧。params: shot_id, cell_path"""
    shot = db.get(Shot, params["shot_id"])
    if not shot:
        raise RuntimeError("镜头不存在")
    cell = params["cell_path"]
    if not Path(cell).exists():
        raise RuntimeError("宫格候选文件不存在")
    shot.first_frame_path = cell
    shot.status = "first_ready"
    db.commit()
    return {"shot_id": shot.id, "first_frame_path": cell}


# ---------- 视频续写 / 镜头接力（末帧驱动的连贯性） ----------
# 原理（对齐 FLF/续写范式）：视频生成模型只能看到首帧（或首尾帧），跨镜头/跨段的
# 画面一致性靠"上一段的真实末帧"作为下一段的起点来保证，而不是靠提示词重新想象。
# 两级应用：
# - 镜间接力：上镜尾帧/视频末帧 → 下镜首帧 img2img（denoise 低，保留构图光影，仅按
#   下镜提示词微调内容）——解决"每镜独立生成，镜头间构图光影跳变"；
# - 镜内续写：本镜视频末帧 → 再生成一段 i2v → ffmpeg 无损拼接——解决"单镜 5s 上限"。

import subprocess  # noqa: E402
from datetime import datetime  # noqa: E402
from ..config import FFMPEG  # noqa: E402


def _ffmpeg(args: list[str]) -> None:
    proc = subprocess.run([str(FFMPEG), "-y", "-loglevel", "error", *args],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {proc.stderr[-300:]}")


def _extract_last_frame(video_path: str, out_png: Path) -> Path:
    """取视频最后一帧（-sseof 从尾部回退 0.3s 保证落在末帧上）。"""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-sseof", "-0.3", "-i", video_path, "-frames:v", "1", "-update", "1",
             str(out_png)])
    if not out_png.exists() or out_png.stat().st_size == 0:
        raise RuntimeError(f"末帧提取失败：{video_path}")
    return out_png


def _chain_source_frame(db, shot: Shot, save_root: Path) -> tuple[str, str]:
    """接力源帧：优先显式尾帧（FLF 生成的落幅），否则从已生成视频提取真实末帧。"""
    if shot.needs_end_frame and shot.end_frame_path and Path(shot.end_frame_path).exists():
        return str(shot.end_frame_path), "end_frame"
    if shot.video_path and Path(shot.video_path).exists():
        png = save_root / f"p{shot.project_id}_s{shot.idx}_lastframe.png"
        _extract_last_frame(shot.video_path, png)
        return str(png), "video_last_frame"
    raise RuntimeError("上镜没有尾帧也没有视频，先点「尾帧」或「视频」再接力")


async def chain_shot_frame(db, task, params: dict) -> dict:
    """镜头接力：上镜末帧 → 下镜首帧 img2img（denoise 低，构图光影连贯）。

    params: {shot_id(上镜), strength?(0.2-0.5 默认 0.35)}
    下一镜 = 同集 idx+1。
    """
    src = db.get(Shot, params["shot_id"])
    if not src:
        raise RuntimeError("上镜不存在")
    dst = db.scalars(select(Shot).where(Shot.episode_id == src.episode_id,
                                        Shot.idx == src.idx + 1)).first()
    if not dst:
        raise RuntimeError("没有下一镜（本镜已是最后一镜）")
    if not dst.image_prompt:
        raise RuntimeError(f"镜头 #{dst.idx} 的首帧提示词为空，先「重组装提示词」")

    project = db.get(Project, src.project_id)
    preset = (project.style_preset if project else "") or "anime_2d"
    genre = (getattr(project, "genre", "") if project else "") or ""
    model_key, model = await pick_model("scene", "low", style_family=style_family(
        (project.style_preset if project else "") or "anime_2d"),
        allowed_families=frozenset(("sdxl",)))
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    save_root = ASSETS_ROOT / str(src.project_id) / "shots"
    update_progress(db, task, 0.2, "提取上镜末帧（尾帧 > 视频末帧）")
    src_frame, src_kind = _chain_source_frame(db, src, save_root)

    denoise = max(0.2, min(0.5, float(params.get("strength") or 0.35)))
    comfy = ComfyUIAdapter()
    w, h = _res(project)
    seed = random.randint(0, 2**31 - 1)
    # img2img 本身锁住构图/光影/人物位置，提示词只引导本镜的动作与景别变化
    prompt = (f"{dst.image_prompt}, continuous scene from previous shot, "
              f"seamless match cut, consistent lighting, location and character appearance")
    neg = _shot_neg("shot_first_frame", preset, NEGATIVE, genre=genre)
    update_progress(db, task, 0.4, f"末帧接力重绘（denoise {denoise}，承接 #{src.idx} → #{dst.idx}）")
    out = await _img2img(comfy, model, prompt, neg, src_frame, w, h, denoise,
                         26, 5.0, seed, save_root,
                         f"drama_studio/p{src.project_id}_s{dst.idx}_first_chain")
    await comfy.free_memory()
    if not out:
        raise ComfyUIError("接力首帧没有返回文件")

    update_progress(db, task, 0.9, "写入下一镜首帧")
    dst.first_frame_path = str(out[0])
    if not dst.video_path:
        dst.status = "first_ready"
    db.add(AssetImage(project_id=src.project_id, kind="shot_first",
                      file_path=str(out[0]), prompt=dst.image_prompt,
                      meta_json=json.dumps({"shot_id": dst.id, "shot_idx": dst.idx,
                                            "chain_from": src.id, "chain_source": src_kind,
                                            "denoise": denoise}, ensure_ascii=False)))
    db.commit()
    return {"src_shot": src.id, "dst_shot": dst.id, "dst_idx": dst.idx,
            "source": src_kind, "denoise": denoise, "path": str(out[0])}


async def extend_shot_video(db, task, params: dict) -> dict:
    """镜内续写：本镜视频末帧 → 再生成一段 i2v → ffmpeg 拼接（Wan 无原生续写，
    末帧接力是 ComfyUI 生态标准做法）。params: {shot_id, seconds?(默认 3)}"""
    shot = db.get(Shot, params["shot_id"])
    if not shot:
        raise RuntimeError("镜头不存在")
    if not shot.video_path or not Path(shot.video_path).exists():
        raise RuntimeError("先生成本镜视频再续写")

    project = db.get(Project, shot.project_id)
    model_key, model = await pick_model("video", params.get("prefer_tier"),
                                        params.get("model_key") or "vid_wan21_480p")
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]
    family = model.get("family", "wan22")
    wf_name = VIDEO_WF_BY_MODEL.get(model_key, VIDEO_WF)
    samp_prefix = "KSamplerAdvanced" if wf_name == "i2v_first_last.json" else "KSampler"

    fps = 16
    duration = clamp_duration(int(params.get("seconds") or 3), family)
    length = max(17, min(81, int(round(duration * fps / 4.0)) * 4 + 1))
    w, h = _res(project)
    save_root = ASSETS_ROOT / str(shot.project_id) / "shots"

    update_progress(db, task, 0.15, "提取视频末帧")
    last_png = _extract_last_frame(shot.video_path,
                                   save_root / f"p{shot.project_id}_s{shot.idx}_extend_seed.png")

    comfy = ComfyUIAdapter()
    wf = comfy.load_template(wf_name)
    start_name = await comfy.upload_image(str(last_png))
    # 续写段提示词：保持人物/场景/运镜基调，仅自然延续动作
    preset = (project.style_preset if project else "") or "anime_2d"
    genre = (getattr(project, "genre", "") if project else "") or ""
    prompt = wrap_video_prompt(shot.video_prompt, family, duration, has_end_frame=False)
    mtok = _motion_video_tokens(shot)
    if mtok and "no morphing" not in prompt:
        prompt = f"{prompt}, {mtok}"
    vtok = _vocab_positive(preset, genre)
    if vtok and vtok.split(",")[0].strip().lower() not in prompt.lower():
        prompt = f"{prompt}, {vtok}"
    seed = random.randint(0, 2**31 - 1)
    overrides = {
        "positive_text": prompt,
        "negative_text": dialect_negative(family, _shot_neg("shot_video", preset, genre=genre)),
        "LoadImage@0.image": start_name,
        f"{samp_prefix}.seed": seed,
        "WanFirstLastFrameToVideo.length": length,
        "WanFirstLastFrameToVideo.width": w,
        "WanFirstLastFrameToVideo.height": h,
        "CreateVideo.fps": fps,
    }
    if samp_prefix == "KSamplerAdvanced":
        overrides.pop(f"{samp_prefix}.seed", None)
        overrides["KSamplerAdvanced@0.noise_seed"] = seed
        overrides["KSamplerAdvanced@1.noise_seed"] = seed
    overrides["WanFirstLastFrameToVideo.end_image"] = None   # 单帧续写
    wf = comfy.apply_overrides(wf, overrides)
    update_progress(db, task, 0.4, f"{model_key} 续写推理（+{duration}s / {length} 帧）")
    out = await comfy.run(wf, filename_prefix=f"drama_studio/p{shot.project_id}_s{shot.idx}_ext",
                          save_root=save_root, timeout=2400)
    await comfy.free_memory()
    if not out:
        raise ComfyUIError("续写段没有返回文件，检查 SaveVideo 节点")

    update_progress(db, task, 0.8, "ffmpeg 无损拼接原片+续写段")
    merged = save_root / f"p{shot.project_id}_s{shot.idx}_video_ext{int(datetime.now().timestamp())}.mp4"
    # ComfyUI 自带 ffmpeg 是精简版（无 libx264）：同参数 mp4 走 concat demuxer
    # 无损 copy；万一两段参数不一致 copy 失败，回退内置 mpeg4 重编码。
    list_file = save_root / f"p{shot.project_id}_s{shot.idx}_concat.txt"
    list_file.write_text(f"file '{shot.video_path}'\nfile '{out[0]}'\n", encoding="utf-8")
    try:
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-c", "copy", str(merged)])
    except RuntimeError:
        update_progress(db, task, 0.82, "concat copy 失败（参数不一致）→ mpeg4 重编码")
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-c:v", "mpeg4", "-q:v", "3", "-an", str(merged)])
    list_file.unlink(missing_ok=True)

    prev = shot.video_path
    shot.video_path = str(merged)
    shot.status = "video_ready"
    db.add(AssetImage(project_id=shot.project_id, kind="shot_video",
                      file_path=str(merged), prompt=prompt,
                      meta_json=json.dumps({"shot_id": shot.id, "fps": fps,
                                            "extended_from": prev, "added_seconds": duration,
                                            "model_key": model_key}, ensure_ascii=False)))
    db.commit()
    update_progress(db, task, 1.0, "续写成片写入镜头卡")
    return {"shot_id": shot.id, "video_path": str(merged), "added_seconds": duration,
            "previous": prev}

# ---------- 音频驱动说话镜（InfiniteTalk，任务 #40 口型对齐） ----------

TALK_WF = "infinitetalk_talk.json"
TALK_FPS = 16.0
TALK_WINDOW = 49          # InfiniteTalk 单窗口帧数（4n+1），8G 显存 swap30 实测稳档
TALK_MAX_FRAMES = 337     # ≈21s 台词上限，防超长台词把 8G 卡成僵尸任务


async def generate_shot_talk(db, task, params: dict) -> dict:
    """音频驱动说话镜（Wan2.1 InfiniteTalk Single，用户拍板的口型对齐路线）：
    首帧 + 台词配音 → 口型/表情全程跟音频的说话视频。
    台词读 shot.dialogue（支持「角色名（语气）：台词」），多行逐句 TTS 后拼接，
    音色按 characters.voice 锁定值解析；音色没锁直接报错引导先锁。
    params: {shot_id, duration?(未用，时长由音频长度决定)}
    """
    shot = db.get(Shot, params["shot_id"])
    if not shot:
        raise RuntimeError("镜头不存在")
    if not shot.first_frame_path or not Path(shot.first_frame_path).exists():
        raise RuntimeError("先出首帧再生成说话镜头")
    if not (shot.dialogue or "").strip():
        raise RuntimeError("本镜没有台词，先在镜头卡里填台词（角色名（语气）：台词）")

    project = db.get(Project, shot.project_id)
    model_key, model = await pick_model("video", None, "vid_talk_infinitetalk")
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    # —— 台词 → 逐行 TTS（语气层）→ ffmpeg 拼接 ——
    from .voice_service import (_assign_voices, _ffprobe_duration, _parse_lines,
                                _tone_params, _tts_one)
    lines = _parse_lines(shot.dialogue)
    voices = _assign_voices(db, shot.project_id)
    narrator = getattr(project, "narrator_voice", "")
    missing = sorted({w for w, _, _ in lines if w and w != "旁白" and w not in voices})
    if not narrator and any(not w or w == "旁白" for w, _, _ in lines):
        missing.insert(0, "【旁白/无前缀台词】")
    if missing:
        raise RuntimeError("说话镜需要配音，以下说话人还没锁定音色：" + "、".join(missing))

    audio_dir = ASSETS_ROOT / str(shot.project_id) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    segs = []
    for seq, (who, tone, text) in enumerate(lines):
        voice = narrator if (not who or who == "旁白") else voices[who]
        rate, pitch = _tone_params(tone)
        seg = audio_dir / f"p{shot.project_id}_s{shot.idx}_talk{seq:02d}.mp3"
        update_progress(db, task, 0.05 + 0.12 * (seq + 1) / len(lines),
                        f"TTS 第 {seq + 1}/{len(lines)} 句（{who or '旁白'}·{tone or '平静'}）")
        await _tts_one(text, voice, seg, rate=rate, pitch=pitch)
        segs.append(seg)

    update_progress(db, task, 0.2, "拼接台词音频")
    talk_audio = audio_dir / f"p{shot.project_id}_s{shot.idx}_talk.mp3"
    silence = audio_dir / "_silence.mp3"
    if not silence.exists():
        _ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.35",
                 "-c:a", "libmp3lame", "-q:a", "6", str(silence)])
    if len(segs) == 1:
        segs[0].replace(talk_audio)
    else:
        list_file = audio_dir / f"p{shot.project_id}_s{shot.idx}_talkconcat.txt"
        parts = []
        for i, s in enumerate(segs):
            parts.append(f"file '{s}'")
            if i < len(segs) - 1:
                parts.append(f"file '{silence}'")
        list_file.write_text("\n".join(parts), encoding="utf-8")
        _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-c", "copy", str(talk_audio)])
        list_file.unlink(missing_ok=True)

    audio_sec = _ffprobe_duration(talk_audio)
    # 帧数对齐 4n+1（VAE 时间压缩因子 4）：至少一个窗口，按音频时长 +1s 余量
    frames = max(TALK_WINDOW, min(TALK_MAX_FRAMES,
                 int(math.ceil((audio_sec + 1.0) * TALK_FPS)) // 4 * 4 + 1))

    # —— InfiniteTalk 推理 ——
    update_progress(db, task, 0.3, f"上传首帧与配音（{audio_sec:.1f}s → {frames} 帧）")
    comfy = ComfyUIAdapter()
    start_name = await comfy.upload_image(shot.first_frame_path)
    audio_name = await comfy.upload_audio(talk_audio)
    w, h = _res(project)
    seed = random.randint(0, 2 ** 31 - 1)
    wf = comfy.load_template(TALK_WF)
    preset = (project.style_preset if project else "") or "anime_2d"
    genre = (getattr(project, "genre", "") if project else "") or ""
    prompt = shot.video_prompt or shot.image_prompt or "a person talking"
    mtok = _motion_video_tokens(shot)
    if mtok:
        prompt = f"{prompt}, {mtok}"
    vtok = _vocab_positive(preset, genre)
    if vtok and vtok.split(",")[0].strip().lower() not in prompt.lower():
        prompt = f"{prompt}, {vtok}"
    overrides = {
        "WanVideoTextEncode.positive_prompt":
            f"{prompt}, the character is speaking, natural talking expressions, "
            "lip movements match speech, consistent character appearance",
        "WanVideoTextEncode.negative_prompt": dialect_negative("wan22", _shot_neg("shot_video", preset, genre=genre)),
        "LoadImage@0.image": start_name,
        "LoadAudio.audio": audio_name,
        "MultiTalkWav2VecEmbeds.num_frames": frames,
        "WanVideoImageToVideoMultiTalk.width": w,
        "WanVideoImageToVideoMultiTalk.height": h,
        "WanVideoSampler.seed": seed,
        "CreateVideo.fps": 16,
    }
    wf = comfy.apply_overrides(wf, overrides)
    est_min = frames / TALK_WINDOW * 85     # 49 帧窗口实测约 80-85 分钟（swap30 + LoRA 运行时 patch，8G 极限档）
    update_progress(db, task, 0.4,
                    f"InfiniteTalk 推理中（{frames} 帧 ≈ {est_min:.0f} 分钟，口型跟音频；建议挂后台等）")
    save_root = ASSETS_ROOT / str(shot.project_id) / "shots"
    out = await comfy.run(wf, filename_prefix=f"drama_studio/p{shot.project_id}_s{shot.idx}_talk",
                          save_root=save_root, timeout=max(7200, est_min * 60 * 1.3))
    await comfy.free_memory()
    if not out:
        raise ComfyUIError("说话镜头没有返回文件，检查 SaveVideo 节点")

    shot.video_path = str(out[0])
    shot.status = "video_ready"
    db.add(AssetImage(project_id=shot.project_id, kind="shot_video",
                      file_path=str(out[0]), prompt=prompt,
                      meta_json=json.dumps({"shot_id": shot.id, "fps": 16,
                                            "frames": frames, "talk": True,
                                            "audio_sec": round(audio_sec, 2),
                                            "model_key": model_key,
                                            "dialogue": shot.dialogue}, ensure_ascii=False)))
    db.commit()
    update_progress(db, task, 1.0, "说话镜头成片写入镜头卡")
    return {"shot_id": shot.id, "video_path": str(out[0]), "frames": frames,
            "audio_sec": round(audio_sec, 2)}
