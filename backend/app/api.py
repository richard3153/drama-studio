"""API 路由（M1：系统状态 / 项目 / 角色+定妆照 / 任务与 SSE）。"""
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func

from .adapters.comfyui_adapter import ComfyUIAdapter
from .adapters.ollama_adapter import OllamaAdapter
from .config import COMFYUI_URL
from .config import ASSETS_ROOT
from .db import (AssetImage, Character, CharacterAppearance, Episode, Project, Prop,
                 PromptTemplate, Scene,
                 SessionLocal, Shot, StashCandidate, TaskRecord, init_db, task_to_dict)
from .services.prompt_templates import STAGES
from .scheduler import queue as task_queue
from .scheduler.vram import comfy_free_vram_gb, registry
from .services.asset_service import (generate_asset, generate_portrait,
                                     generate_portrait_composed, refine_asset)
from .services import asset_service, pipeline_service, script_service, shot_service, voice_service
from .services.script_service import MOVING_CAMERA, build_candidate_prompts
from .style_presets import (STYLE_PRESETS, assemble_character_prompt,
                            assemble_prop_prompt, assemble_scene_prompt)

router = APIRouter(prefix="/api")


# ---------- 系统状态 ----------

@router.get("/system")
async def system():
    reg = registry()
    info: dict = {"models": reg.get("models", {}), "defaults": reg.get("defaults", {})}
    try:
        stats = await ComfyUIAdapter().system_stats()
        d = stats["devices"][0]
        info["comfyui"] = {"url": COMFYUI_URL, "up": True,
                           "vram_total_gb": round(d["vram_total"] / 1024**3, 2),
                           "vram_free_gb": round(d["vram_free"] / 1024**3, 2)}
    except Exception as e:
        info["comfyui"] = {"url": COMFYUI_URL, "up": False, "error": str(e)}
    try:
        info["ollama"] = {"up": True, "models": await OllamaAdapter().list_models()}
    except Exception:
        info["ollama"] = {"up": False, "models": []}
    return info


# ---------- 项目 ----------

class ProjectIn(BaseModel):
    name: str
    description: str = ""
    aspect_ratio: str = "9:16"   # 全局画幅：16:9/21:9/4:3/1:1/3:4/9:16


@router.post("/projects")
def create_project(body: ProjectIn):
    from .aspect import normalize_aspect
    with SessionLocal() as db:
        p = Project(name=body.name, description=body.description,
                    aspect_ratio=normalize_aspect(body.aspect_ratio))
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"id": p.id, "name": p.name, "description": p.description,
                "aspect_ratio": p.aspect_ratio}


@router.get("/style-presets")
def style_presets():
    return {k: {"label": v["label"], "category": v["category"],
                "style_lock": v["style_lock"], "motion_hint": v["motion_hint"]}
            for k, v in STYLE_PRESETS.items()}


@router.get("/style-genres")
def style_genres():
    """题材词库列表（红果爆款反向解析）：key + 中文名 + 典型场景，供前端题材下拉。"""
    from .style_vocab import GENRE_LABELS, GENRE_VOCAB
    return {k: {"label": GENRE_LABELS.get(k, k),
                "sample_setting": (GENRE_VOCAB[k].get("setting") or [""])[0]}
            for k in GENRE_VOCAB}


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    style_preset: str | None = None
    lifelike: int | None = None        # 活人感提示词机制 1/0
    lifelike_full: int | None = None   # 全量瑕疵（含五官不完美）1/0
    auto_polish: int | None = None     # 初图 10% 微调 1/0（按资产类型分级生效）
    grid_storyboard: int | None = None # 宫格故事板（仅动漫风格建议开）
    aspect_ratio: str | None = None    # 全局画幅：16:9/21:9/4:3/1:1/3:4/9:16
    genre: str | None = None           # 题材锁（红果爆款题材词库 key，""=不挂题材词库）
    transition_bridge: int | None = None  # 转场镜开关：场景切换边界双帧 i2v 生成过渡镜
    transition_fx: str | None = None   # 成片兜底转场：''=不加 / fadeblack / fadewhite


@router.put("/projects/{pid}")
def update_project(pid: int, body: ProjectUpdate):
    from .aspect import normalize_aspect
    from .style_vocab import GENRE_VOCAB
    if body.style_preset and body.style_preset not in STYLE_PRESETS:
        raise HTTPException(400, "未知风格预设")
    if body.genre and body.genre not in GENRE_VOCAB:
        raise HTTPException(400, "未知题材词库 key")
    if body.transition_fx and body.transition_fx not in ("fadeblack", "fadewhite"):
        raise HTTPException(400, "兜底转场仅支持 fadeblack/fadewhite")
    with SessionLocal() as db:
        p = db.get(Project, pid)
        if not p:
            raise HTTPException(404, "项目不存在")
        if body.name is not None:
            p.name = body.name
        if body.description is not None:
            p.description = body.description
        if body.style_preset is not None:
            p.style_preset = body.style_preset
        if body.lifelike is not None:
            p.lifelike = body.lifelike
        if body.lifelike_full is not None:
            p.lifelike_full = body.lifelike_full
        if body.auto_polish is not None:
            p.auto_polish = body.auto_polish
        if body.grid_storyboard is not None:
            p.grid_storyboard = body.grid_storyboard
        if body.aspect_ratio is not None:
            p.aspect_ratio = normalize_aspect(body.aspect_ratio)
        if body.genre is not None:
            p.genre = body.genre
        if body.transition_bridge is not None:
            p.transition_bridge = body.transition_bridge
        if body.transition_fx is not None:
            p.transition_fx = body.transition_fx
        db.commit()
        reassembled = 0
        # 【#85 根治】全局风格锁/活人感变更后，存量实体的 base_prompt 还是旧风格文本
        # （旧图均为 anime_2d 词块开头）。若不同步重算，角色通道（直接用 base_prompt）
        # 与无槽位资产会继续按旧锁出图，用户看到"改了锁但画风没变"。
        # 这里对有槽位的实体按新锁重新组装；手工改过 base_prompt 的（无槽位）不动。
        if body.style_preset is not None or body.lifelike is not None or body.lifelike_full is not None:
            lifelike = bool(p.lifelike)
            lifelike_full = bool(getattr(p, "lifelike_full", 0))
            for etype, model in (("character", Character), ("scene", Scene), ("prop", Prop)):
                for row in db.scalars(select(model).where(model.project_id == pid)).all():
                    slots = json.loads(getattr(row, "prompt_json", "{}") or "{}")
                    if not slots:
                        continue
                    if etype == "character":
                        row.base_prompt = assemble_character_prompt(
                            slots, p.style_preset, "sheet", lifelike, lifelike_full)
                    elif etype == "scene":
                        row.base_prompt = assemble_scene_prompt(
                            slots, p.style_preset, lifelike, fallback_subject=row.name)
                    else:
                        row.base_prompt = assemble_prop_prompt(
                            slots, p.style_preset, lifelike, fallback_subject=row.name)
                    reassembled += 1
            db.commit()
        return {"id": p.id, "name": p.name, "style_preset": p.style_preset,
                "genre": getattr(p, "genre", ""),
                "transition_bridge": getattr(p, "transition_bridge", 0),
                "transition_fx": getattr(p, "transition_fx", ""),
                "lifelike": p.lifelike, "lifelike_full": p.lifelike_full,
                "auto_polish": p.auto_polish, "grid_storyboard": p.grid_storyboard,
                "aspect_ratio": p.aspect_ratio, "reassembled_prompts": reassembled}


@router.get("/projects")
def list_projects():
    with SessionLocal() as db:
        rows = db.scalars(select(Project).order_by(Project.id.desc())).all()
        return [{"id": p.id, "name": p.name, "description": p.description,
                 "style_preset": p.style_preset,
                 "genre": getattr(p, "genre", ""),
                 "transition_bridge": getattr(p, "transition_bridge", 0),
                 "transition_fx": getattr(p, "transition_fx", ""),
                 "lifelike": p.lifelike, "lifelike_full": p.lifelike_full,
                 "auto_polish": p.auto_polish, "grid_storyboard": p.grid_storyboard,
                 "aspect_ratio": p.aspect_ratio,
                 "created_at": str(p.created_at)} for p in rows]


@router.delete("/projects/{pid}")
def delete_project(pid: int):
    """删除项目：级联清库（角色/场景/道具/暂存/集/镜/资产图/外观/项目级模板/任务记录）+ 删磁盘资产目录。

    有 pending/running 任务引用该项目时拒绝删除，避免 worker 写库时踩空。
    """
    from .config import ASSETS_ROOT
    with SessionLocal() as db:
        p = db.get(Project, pid)
        if not p:
            raise HTTPException(404, "项目不存在")
        # 运行中的任务检查：TaskRecord 无 project_id 列，通过 params_json 匹配
        busy = 0
        for t in db.scalars(select(TaskRecord).where(
                TaskRecord.status.in_(("pending", "running")))).all():
            try:
                if json.loads(t.params_json or "{}").get("project_id") == pid:
                    busy += 1
            except Exception:
                pass
        if busy:
            raise HTTPException(409, f"该项目还有 {busy} 个进行中的任务，等任务结束或取消后再删除")

        # 顺序无关的子表（无下级引用）
        for model in (AssetImage, CharacterAppearance, StashCandidate, PromptTemplate):
            for row in db.scalars(select(model).where(model.project_id == pid)).all():
                db.delete(row)
        # 任务记录按 params 匹配清理
        for t in db.scalars(select(TaskRecord)).all():
            try:
                if json.loads(t.params_json or "{}").get("project_id") == pid:
                    db.delete(t)
            except Exception:
                pass
        # shots → episodes
        for s in db.scalars(select(Shot).where(Shot.project_id == pid)).all():
            db.delete(s)
        for e in db.scalars(select(Episode).where(Episode.project_id == pid)).all():
            db.delete(e)
        # characters / scenes / props
        for model in (Character, Scene, Prop):
            for row in db.scalars(select(model).where(model.project_id == pid)).all():
                db.delete(row)
        db.delete(p)
        db.commit()

    # 磁盘资产目录整体删除（图片/视频产物都在这里）
    import shutil
    asset_dir = Path(ASSETS_ROOT) / str(pid)
    removed = 0
    if asset_dir.exists():
        shutil.rmtree(asset_dir, ignore_errors=True)
        removed = 1
    return {"deleted": pid, "assets_dir_removed": removed}


# ---------- 角色 + 定妆照 ----------

class CharacterIn(BaseModel):
    name: str
    description: str = ""
    base_prompt: str
    prefer_tier: str | None = None      # low/mid/high，None=自动按显存选
    width: int | None = None
    height: int | None = None


@router.post("/projects/{pid}/characters")
async def create_character(pid: int, body: CharacterIn):
    with SessionLocal() as db:
        if not db.get(Project, pid):
            raise HTTPException(404, "项目不存在")
        ch = Character(project_id=pid, name=body.name,
                       description=body.description, base_prompt=body.base_prompt)
        # 音色跨集锁定：新角色自动分配一个项目内未被占用、性别匹配的音色
        ch.voice = voice_service.pick_free_voice(db, pid, body.description) or ""
        db.add(ch)
        db.commit()
        db.refresh(ch)
        project = db.get(Project, pid)
        params = {"project_id": pid, "character_id": ch.id,
                  "base_prompt": body.base_prompt,
                  "prefer_tier": body.prefer_tier,
                  "width": body.width, "height": body.height,
                  "style_preset": project.style_preset,
                  "auto_polish": bool(project.auto_polish)}
        t = task_queue.create_task(db, "portrait", params)
        db.commit()
        task_id = t.id
        resp = {"character_id": ch.id, "task_id": task_id}
    # 锁外启动异步执行
    task_queue.spawn_bg(_run_bg(task_id))
    return resp


async def _run_portrait(task_id: int):
    await _run_task(task_id)


async def _run_bg(task_id: int):
    """统一执行入口：登记 task_id → 执行协程，供暂停/取消端点定位（含排队等锁者）。"""
    task_queue.register_runner(task_id, asyncio.current_task())
    await _run_task(task_id)


async def _run_task(task_id: int):
    """通用任务执行器：按 type 分发到 service。"""
    with SessionLocal() as db:
        t = db.get(TaskRecord, task_id)
        params = json.loads(t.params_json)
        fn = {
            "portrait": lambda: generate_portrait(db, t, params),
            "asset": lambda: generate_asset(db, t, params),
            "asset_compose": lambda: generate_portrait_composed(db, t, params),
            "rebuild_slots": lambda: script_service.rebuild_slots(db, t, params),
            "ref_redraw": lambda: asset_service.generate_from_reference(db, t, params),
            "upscale": lambda: asset_service.upscale_asset(db, t, params),
            "polish": lambda: refine_asset(db, t, params),
            "scene_anchor": lambda: asset_service.auto_scene_anchors(db, t, params),
            "outline": lambda: script_service.generate_outline(db, t, params),
            "continue_outline": lambda: script_service.continue_outline(db, t, params),
            "script": lambda: script_service.write_episode_script(db, t, params),
            "breakdown": lambda: script_service.breakdown_episode(db, t, params),
            "refine": lambda: script_service.refine_text(db, t, params),
            "shot_frame": lambda: shot_service.generate_shot_frame(db, t, params),
            "shot_video": lambda: shot_service.generate_shot_video(db, t, params),
            "shot_talk": lambda: shot_service.generate_shot_talk(db, t, params),
            "shot_chain": lambda: shot_service.chain_shot_frame(db, t, params),
            "shot_extend": lambda: shot_service.extend_shot_video(db, t, params),
            "grid9": lambda: shot_service.generate_grid_storyboard(db, t, params),
            "tts": lambda: voice_service.tts_episode(db, t, params),
            "stitch": lambda: asyncio.to_thread(voice_service.export_final, db, t, params),
            "batch_frames": lambda: pipeline_service.batch_frames(db, t, params),
            "batch_transitions": lambda: pipeline_service.batch_transitions(db, t, params),
            "batch_videos": lambda: pipeline_service.batch_videos(db, t, params),
            "rechain_from": lambda: pipeline_service.rechain_from(db, t, params),
            "full_pipeline": lambda: pipeline_service.full_pipeline(db, t, params),
            "export_jianying": lambda: asyncio.to_thread(pipeline_service.export_jianying, db, t, params),
            "export_fcpxml": lambda: asyncio.to_thread(pipeline_service.export_fcpxml, db, t, params),
        }.get(t.type)
        if fn is None:
            raise RuntimeError(f"未知任务类型 {t.type}")
        await task_queue.run_task(db, t, fn)


@router.get("/characters")
def list_characters(project_id: int):
    with SessionLocal() as db:
        rows = db.scalars(select(Character).where(Character.project_id == project_id)
                          .order_by(Character.id)).all()
        return [{"id": c.id, "name": c.name, "voice": getattr(c, "voice", "") or ""}
                for c in rows]


@router.get("/characters/{cid}")
def get_character(cid: int):
    with SessionLocal() as db:
        ch = db.get(Character, cid)
        if not ch:
            raise HTTPException(404, "角色不存在")
        imgs = db.scalars(select(AssetImage).where(AssetImage.character_id == cid)).all()
        return {"id": ch.id, "name": ch.name, "description": ch.description,
                "base_prompt": ch.base_prompt,
                "face_lock_path": getattr(ch, "face_lock_path", "") or "",
                "images": [{"id": i.id, "kind": i.kind, "path": i.file_path} for i in imgs]}


class FaceLockIn(BaseModel):
    path: str = ""                   # 参考图绝对路径；空串=解除锁定（回到自动择优）


@router.post("/characters/{cid}/face-lock")
def set_face_lock(cid: int, body: FaceLockIn):
    """角色级默认脸锁：钉死该角色所有镜头 IPAdapter 参考用的那张图（100% 一致性）。

    path 传空解除锁定，回到自动择优（特写优先→分辨率大优先→版本新优先）。
    锁定路径不存在时 400（防锁死到失效图）。
    """
    with SessionLocal() as db:
        ch = db.get(Character, cid)
        if not ch:
            raise HTTPException(404, "角色不存在")
        p = (body.path or "").strip()
        if p and not Path(p).exists():
            raise HTTPException(400, f"参考图不存在：{p}")
        ch.face_lock_path = p
        db.commit()
        return {"id": ch.id, "face_lock_path": ch.face_lock_path}


@router.get("/assets/{aid}/file")
def asset_file(aid: int):
    with SessionLocal() as db:
        img = db.get(AssetImage, aid)
        if not img:
            raise HTTPException(404)
    p = Path(img.file_path)
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(p)


@router.get("/asset-file-by-path")
def asset_file_by_path(path: str):
    """按绝对路径取项目资产图（场景锚点缩略图用；仅限 data/projects 目录内，防路径穿越）。"""
    p = Path(path).resolve()
    if ASSETS_ROOT.resolve() not in p.parents:
        raise HTTPException(400, "路径越界")
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(p)


# ---------- 任务 ----------

@router.get("/tasks")
def list_tasks(limit: int = 50):
    with SessionLocal() as db:
        rows = db.scalars(select(TaskRecord).order_by(TaskRecord.id.desc()).limit(limit)).all()
        return [task_to_dict(t) for t in rows]


@router.post("/tasks/{tid}/retry")
async def retry_task(tid: int):
    """重试失败任务（显存/服务中断等可恢复失败）。"""
    with SessionLocal() as db:
        t = db.get(TaskRecord, tid)
        if not t:
            raise HTTPException(404, "任务不存在")
        if t.status in ("running", "pending"):
            raise HTTPException(400, f"任务状态 {t.status} 不可重试")
        t.status = "pending"
        t.error = ""
        t.progress = 0.0
        db.commit()
    at = task_queue.spawn_bg(_run_bg(tid))
    task_queue.register_runner(tid, at)
    return {"task_id": tid, "status": "requeued"}


@router.post("/tasks/{tid}/pause")
def pause_task(tid: int):
    """暂停任务：仅排队中（pending / 等锁）可暂停；GPU 推理中只能取消。"""
    with SessionLocal() as db:
        t = db.get(TaskRecord, tid)
        if not t:
            raise HTTPException(404, "任务不存在")
        if t.status == "pending":
            t.status = "paused"
            db.commit()
        elif t.status == "running" and (t.stage or "") == "":
            # 尚在等锁、未进 GPU 推理（stage 为空）：先落库 paused 再取消协程——
            # 顺序反了会有竞态：CancelledError 收尾读到旧快照 running 会覆写成 cancelled
            db.rollback()
            t.status = "paused"
            t.stage = "等待 GPU 空闲，已暂停"
            db.commit()
            task_queue.cancel_running(tid)
        else:
            raise HTTPException(400, f"任务状态 {t.status} 不支持暂停（推理中的任务只能取消）")
        return {"task_id": tid, "status": t.status}


@router.post("/tasks/{tid}/resume")
async def resume_task(tid: int):
    """继续已暂停的任务（重新排队派发）。"""
    with SessionLocal() as db:
        t = db.get(TaskRecord, tid)
        if not t:
            raise HTTPException(404, "任务不存在")
        if t.status != "paused":
            raise HTTPException(400, f"任务状态 {t.status} 不是暂停态")
        t.status = "pending"
        db.commit()
    at = task_queue.spawn_bg(_run_bg(tid))
    task_queue.register_runner(tid, at)
    return {"task_id": tid, "status": "pending"}


@router.post("/tasks/{tid}/cancel")
def cancel_task(tid: int):
    """取消任务：排队/暂停直接改状态；运行中取消其执行协程（CancelledError 收尾）。"""
    with SessionLocal() as db:
        t = db.get(TaskRecord, tid)
        if not t:
            raise HTTPException(404, "任务不存在")
        if t.status in ("done", "failed", "cancelled"):
            raise HTTPException(400, f"任务已结束（{t.status}），无需取消")
        if t.status in ("pending", "paused"):
            t.status = "cancelled"
            t.error = "手动取消"
            db.commit()
            return {"task_id": tid, "status": "cancelled"}
        # running：取消协程，run_task 的 CancelledError 分支负责收尾标 cancelled
        if not task_queue.cancel_running(tid):
            raise HTTPException(400, "任务没有在运行的协程可取消")
        return {"task_id": tid, "status": "cancelling"}


@router.get("/tasks/stream")
async def task_stream():
    q = task_queue.subscribe()

    async def gen():
        try:
            # 重连回放（#79）：页面重开时只靠 SSE 增量推送，正在跑的任务不会出现，
            # 任务栏一直显示"空闲"直到下一个事件。连接建立时先回放
            # 进行中/排队中/暂停的任务快照，前端 onmessage 会自然并入列表。
            with SessionLocal() as db:
                rows = db.scalars(select(TaskRecord).where(
                    TaskRecord.status.in_(("running", "pending", "paused"))
                ).order_by(TaskRecord.id.desc()).limit(30)).all()
            for t in rows:
                yield f"data: {json.dumps({'event': 'task_update', 'task': task_to_dict(t)}, ensure_ascii=False, default=str)}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            task_queue.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


# ---------- P1 剧本：大纲 / 分集 / 拆解 / 精修 ----------

class OutlineIn(BaseModel):
    idea: str
    num_episodes: int = 3
    genre: str = ""


@router.post("/projects/{pid}/outline")
async def generate_outline(pid: int, body: OutlineIn):
    with SessionLocal() as db:
        if not db.get(Project, pid):
            raise HTTPException(404, "项目不存在")
        params = {"project_id": pid, "idea": body.idea,
                  "num_episodes": body.num_episodes, "genre": body.genre}
        t = task_queue.create_task(db, "outline", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


class ContinueOutlineIn(BaseModel):
    idea: str = ""
    add_episodes: int = 10
    genre: str = ""


@router.post("/projects/{pid}/outline/continue")
async def continue_outline(pid: int, body: ContinueOutlineIn):
    """续写分集：保留已有分集，从下一集继续生成 add 集并逐集 AI 写剧本"""
    with SessionLocal() as db:
        if not db.get(Project, pid):
            raise HTTPException(404, "项目不存在")
        params = {"project_id": pid, "idea": body.idea,
                  "add_episodes": body.add_episodes, "genre": body.genre}
        t = task_queue.create_task(db, "continue_outline", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


class EpisodeIn(BaseModel):
    idx: int = 1
    title: str = ""
    outline: str = ""
    script_text: str = ""


@router.post("/projects/{pid}/episodes")
def add_episode(pid: int, body: EpisodeIn):
    with SessionLocal() as db:
        ep = Episode(project_id=pid, idx=body.idx, title=body.title,
                     outline=body.outline, script_text=body.script_text,
                     status="script" if body.script_text else "draft")
        db.add(ep)
        db.commit()
        db.refresh(ep)
        return {"id": ep.id, "idx": ep.idx, "title": ep.title}


@router.get("/projects/{pid}/episodes")
def list_episodes(pid: int):
    with SessionLocal() as db:
        rows = db.scalars(select(Episode).where(Episode.project_id == pid)
                          .order_by(Episode.idx)).all()
        return [{"id": e.id, "idx": e.idx, "title": e.title, "outline": e.outline,
                 "script_text": e.script_text, "status": e.status} for e in rows]


class EpisodeUpdate(BaseModel):
    title: str | None = None
    outline: str | None = None
    script_text: str | None = None


@router.put("/episodes/{eid}")
def update_episode(eid: int, body: EpisodeUpdate):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "分集不存在")
        if body.title is not None:
            ep.title = body.title
        if body.outline is not None:
            ep.outline = body.outline
        if body.script_text is not None:
            ep.script_text = body.script_text
            ep.status = "script"
        db.commit()
        return {"id": ep.id, "status": ep.status}


@router.post("/episodes/{eid}/write-script")
async def write_script(eid: int, model: str | None = None):
    with SessionLocal() as db:
        if not db.get(Episode, eid):
            raise HTTPException(404, "分集不存在")
        t = task_queue.create_task(db, "script", {"episode_id": eid, "model": model})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


@router.post("/episodes/{eid}/breakdown")
async def breakdown(eid: int, model: str | None = None):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep or not ep.script_text:
            raise HTTPException(400, "分集不存在或剧本正文为空")
        t = task_queue.create_task(db, "breakdown", {"episode_id": eid, "model": model})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


@router.get("/episodes/{eid}/breakdown")
def get_breakdown(eid: int):
    """拆解状态查询（前端轮询依赖）：
    - 本集有 pending/running 的拆解任务 → 如实返回 running（前端继续等待新结果，
      决不能提前返回旧 done，否则"重新拆解"看起来像没反应）；
    - 无进行中任务 → 返回最近 done（known_assets 按当前资产库实时过滤：资产删除后
      「资产库复用 N」自动同步）或最近 failed（展示失败原因）。
    """
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        pid = ep.project_id if ep else None
        rows = db.scalars(select(TaskRecord)
                          .where(TaskRecord.type == "breakdown")
                          .order_by(TaskRecord.id.desc())).all()
        mine = [t for t in rows if json.loads(t.params_json or "{}").get("episode_id") == eid]
        # 1) 有进行中的拆解 → running
        active = next((t for t in mine if t.status in ("pending", "running")), None)
        if active is not None:
            return {"task_id": active.id, "status": active.status,
                    "result": {}, "error": ""}
        # 2) 无进行中 → 最近 done（实时过滤资产），否则最近 failed
        pick = next((t for t in mine if t.status == "done"), None)
        if pick is None:
            pick = next((t for t in mine if t.status == "failed"), None)
        if pick is not None:
            t = pick
            result = json.loads(t.result_json or "{}")
            live = {
                "characters": {c.name for c in db.scalars(select(Character).where(Character.project_id == pid))},
                "scenes": {s.name for s in db.scalars(select(Scene).where(Scene.project_id == pid))},
                "props": {p.name for p in db.scalars(select(Prop).where(Prop.project_id == pid))},
            }
            ka = result.get("known_assets") or {}
            ka = {k: [n for n in (ka.get(k) or []) if n in live.get(k, set())]
                  for k in ("characters", "scenes", "props")}
            result["known_assets"] = ka
            return {"task_id": t.id, "status": t.status,
                    "result": result, "error": t.error}
        return {"task_id": None, "status": "none", "result": {}, "error": ""}


class RefineIn(BaseModel):
    text: str
    action: str = "polish"       # polish / continue


@router.post("/refine")
async def refine(body: RefineIn):
    with SessionLocal() as db:
        t = task_queue.create_task(db, "refine",
                                   {"text": body.text, "action": body.action})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


# ---------- 候选确认（Jellyfish 范式）：拆解结果 → 正式资产 + 批量生图 ----------

class CandidateList(BaseModel):
    """拆解候选（M2.2 槽位化）：slots 非空时 base_prompt 由代码组装；否则直接用 base_prompt。"""
    name: str
    description: str = ""
    slots: dict = {}
    base_prompt: str = ""
    portrait_mode: str = "sheet"     # 仅角色：sheet=三视图 / single=单人 / board=角色板
    gen_mode: str = "auto"           # 仅角色：auto/compose(A)/board(B)/layout(C)/sheet


class ConfirmIn(BaseModel):
    characters: list[CandidateList] = []
    scenes: list[CandidateList] = []
    props: list[CandidateList] = []
    generate_images: bool = True
    prefer_tier: str | None = None


def _portrait_dims(mode: str | None) -> tuple[int, int]:
    """【硬性要求】角色资产必须三视图：一律 16:9 横幅（1344x768），单人竖版通道已废弃。"""
    return (1344, 768)


@router.post("/projects/{pid}/confirm-candidates")
async def confirm_candidates(pid: int, body: ConfirmIn):
    """确认拆解候选：槽位 → 代码组装提示词 → 写入资产表 → 可选批量生图（串行队列）。
    跨集脸不变原则：同名同类型资产已存在时跳过（角色脸部锁定，服饰变化走角色板变体）。"""
    created: dict = {"character_ids": [], "scene_ids": [], "prop_ids": [],
                     "task_ids": [], "skipped_dup": []}
    with SessionLocal() as db:
        project = db.get(Project, pid)
        if not project:
            raise HTTPException(404, "项目不存在")
        preset = project.style_preset
        lifelike = bool(project.lifelike)
        lifelike_full = bool(getattr(project, "lifelike_full", 0))
        auto_polish = bool(project.auto_polish)

        def _dup_check(table, name):
            row = db.scalars(select(table).where(table.project_id == pid,
                                                 table.name == name)).first()
            return row is not None

        for c in body.characters:
            if _dup_check(Character, c.name):
                created["skipped_dup"].append(f"角色:{c.name}")
                continue
            # 【硬性要求】角色资产必须三视图：候选携带的 portrait_mode 一律归一 sheet
            prompt = (assemble_character_prompt(c.slots, preset, "sheet",
                                               lifelike, lifelike_full)
                      if c.slots else c.base_prompt)
            row = Character(project_id=pid, name=c.name, description=c.description,
                            base_prompt=prompt,
                            prompt_json=json.dumps(c.slots, ensure_ascii=False),
                            portrait_mode="sheet",
                            gen_mode=c.gen_mode or "auto")
            # 音色跨集锁定：新角色自动分配未占用音色；同名角色已被 _dup_check 复用（继承已锁音色）
            _slots = c.slots if isinstance(c.slots, dict) else {}
            _desc = f"{c.description} {_slots.get('identity', '')}"
            row.voice = voice_service.pick_free_voice(db, pid, _desc) or ""
            db.add(row)
            db.commit()
            db.refresh(row)
            created["character_ids"].append(row.id)
        for s in body.scenes:
            if _dup_check(Scene, s.name):
                created["skipped_dup"].append(f"场景:{s.name}")
                continue
            prompt = (assemble_scene_prompt(s.slots, preset, lifelike, fallback_subject=s.name)
                      if s.slots else s.base_prompt)
            row = Scene(project_id=pid, name=s.name, description=s.description,
                        base_prompt=prompt,
                        prompt_json=json.dumps(s.slots, ensure_ascii=False))
            db.add(row)
            db.commit()
            db.refresh(row)
            created["scene_ids"].append(row.id)
            # LLM 漏 space 槽位时自动补一次槽位重铸（本地 LLM 反推）
            if s.slots and not (s.slots.get("space") or "").strip():
                task_queue.create_task(db, "rebuild_slots",
                                       {"entity_type": "scene", "entity_id": row.id})
        for p in body.props:
            if _dup_check(Prop, p.name):
                created["skipped_dup"].append(f"道具:{p.name}")
                continue
            prompt = (assemble_prop_prompt(p.slots, preset, lifelike, fallback_subject=p.name)
                      if p.slots else p.base_prompt)
            row = Prop(project_id=pid, name=p.name, description=p.description,
                       base_prompt=prompt,
                       prompt_json=json.dumps(p.slots, ensure_ascii=False))
            db.add(row)
            db.commit()
            db.refresh(row)
            created["prop_ids"].append(row.id)
            # LLM 漏 subject 槽位时，自动补一次槽位重铸（本地 LLM 反推英文主体词）
            if p.slots and not (p.slots.get("subject") or "").strip():
                task_queue.create_task(db, "rebuild_slots",
                                       {"entity_type": "prop", "entity_id": row.id})

        if body.generate_images:
            jobs = ([("portrait", "character", i) for i in created["character_ids"]]
                    + [("scene", "scene", i) for i in created["scene_ids"]]
                    + [("prop", "prop", i) for i in created["prop_ids"]])
            for role, etype, eid in jobs:
                table = {"character": Character, "scene": Scene, "prop": Prop}[etype]
                entity = db.get(table, eid)
                if etype == "character":
                    width, height = _portrait_dims(entity.portrait_mode)
                    type_, params = _character_task_params(db, pid, entity, preset,
                                                           lifelike, lifelike_full,
                                                           auto_polish, body.prefer_tier,
                                                           width, height)
                else:
                    from .aspect import asset_dims
                    width, height = asset_dims(getattr(project_row, "aspect_ratio", None)
                                               if (project_row := db.get(Project, pid)) else None)
                    type_ = "asset"
                    params = {"project_id": pid, "role": role, "entity_type": etype,
                              "entity_id": eid, "base_prompt": entity.base_prompt,
                              "prefer_tier": body.prefer_tier,
                              "width": width, "height": height,
                              "auto_polish": auto_polish,
                              "style_preset": preset}
                t = task_queue.create_task(db, type_, params)
                created["task_ids"].append(t.id)
    # 全部入队后再统一启动（heavy 锁保证串行）
    for tid in created["task_ids"]:
        task_queue.spawn_bg(_run_bg(tid))
    return created


# ---------- 候选暂存区（跨集资产复用 / 脸不变原则） ----------

class StashItem(BaseModel):
    entity_type: str                     # character / scene / prop
    name: str
    description: str = ""
    slots: dict = {}
    portrait_mode: str = "sheet"


class StashIn(BaseModel):
    episode_id: int | None = None
    items: list[StashItem] = []


@router.post("/projects/{pid}/stash")
def stash_candidates(pid: int, body: StashIn):
    """拆解候选 → 暂存区（本集不确认，留给后续集或剧本变化后处理）。"""
    with SessionLocal() as db:
        if not db.get(Project, pid):
            raise HTTPException(404, "项目不存在")
        ids = []
        for it in body.items:
            # 【硬性要求】角色候选一律三视图：portrait_mode 入库前归一 sheet
            row = StashCandidate(project_id=pid, episode_id=body.episode_id,
                                 entity_type=it.entity_type, name=it.name,
                                 description=it.description,
                                 slots_json=json.dumps(it.slots, ensure_ascii=False),
                                 portrait_mode="sheet" if it.entity_type == "character"
                                 else it.portrait_mode)
            db.add(row)
            db.commit()
            db.refresh(row)
            ids.append(row.id)
        return {"stashed": len(ids), "ids": ids}


@router.get("/projects/{pid}/stash")
def list_stash(pid: int):
    with SessionLocal() as db:
        rows = db.scalars(select(StashCandidate)
                          .where(StashCandidate.project_id == pid)
                          .order_by(StashCandidate.id.desc())).all()
        return [{"id": r.id, "entity_type": r.entity_type, "name": r.name,
                 "description": r.description,
                 "slots": json.loads(r.slots_json or "{}"),
                 "portrait_mode": r.portrait_mode,
                 "episode_id": r.episode_id, "created_at": str(r.created_at)}
                for r in rows]


@router.delete("/stash/{sid}")
def delete_stash(sid: int):
    with SessionLocal() as db:
        row = db.get(StashCandidate, sid)
        if not row:
            raise HTTPException(404, "暂存候选不存在")
        db.delete(row)
        db.commit()
        return {"deleted": sid}


class StashConfirmIn(BaseModel):
    ids: list[int]
    generate_images: bool = True
    prefer_tier: str | None = None


@router.post("/projects/{pid}/stash/confirm")
async def stash_confirm(pid: int, body: StashConfirmIn):
    """暂存区候选 → 正式资产（复用 confirm 逻辑；同名跳过=脸不变原则）。"""
    with SessionLocal() as db:
        rows = [db.get(StashCandidate, i) for i in body.ids]
        rows = [r for r in rows if r and r.project_id == pid]
        payload = ConfirmIn(
            characters=[CandidateList(
                name=r.name, description=r.description,
                slots=json.loads(r.slots_json or "{}"), portrait_mode=r.portrait_mode)
                for r in rows if r.entity_type == "character"],
            scenes=[CandidateList(name=r.name, description=r.description,
                                  slots=json.loads(r.slots_json or "{}"))
                    for r in rows if r.entity_type == "scene"],
            props=[CandidateList(name=r.name, description=r.description,
                                 slots=json.loads(r.slots_json or "{}"))
                   for r in rows if r.entity_type == "prop"],
            generate_images=body.generate_images, prefer_tier=body.prefer_tier)
        for r in rows:   # 已入库的暂存项移除
            db.delete(r)
        db.commit()
    result = await confirm_candidates(pid, payload)
    return result


# ---------- 项目资产总览 ----------

@router.get("/projects/{pid}/assets")
def project_assets(pid: int):
    with SessionLocal() as db:
        chars = db.scalars(select(Character).where(Character.project_id == pid)).all()
        scenes = db.scalars(select(Scene).where(Scene.project_id == pid)).all()
        props = db.scalars(select(Prop).where(Prop.project_id == pid)).all()
        imgs = db.scalars(select(AssetImage).where(AssetImage.project_id == pid)).all()
        img_by_entity: dict = {}
        for i in imgs:
            meta = json.loads(i.meta_json or "{}")
            key = (meta.get("entity_type"), meta.get("entity_id"), i.kind)
            img_by_entity.setdefault(key, []).append(i)
        def _render_count(rows):
            """真实渲染次数（不把复用/衍生物计进去）：
            - refined_from/upscaled_from/from_reference = 微调/超分/重绘衍生图，不计
            - compose 拼版（sheet+face_ref 同 seed）= 一次渲染，按 seed 去重
            - 普通渲染一图一次；新数据有 render_session 标记，按标记去重
            """
            sessions = set()
            for i in rows:
                meta = json.loads(i.meta_json or "{}")
                if any(k in meta for k in ("refined_from", "upscaled_from", "from_reference")):
                    continue
                if meta.get("render_session"):
                    sessions.add(meta["render_session"])
                elif meta.get("compose"):
                    sessions.add(f"compose:{meta.get('seed')}")
                else:
                    sessions.add(f"img:{i.id}")
            return len(sessions)
        return {
            "characters": [{"id": c.id, "name": c.name, "description": c.description,
                            "base_prompt": c.base_prompt,
                            "slots": json.loads(c.prompt_json or "{}"),
                            "portrait_mode": c.portrait_mode,
                            "has_prompt": bool((c.base_prompt or "").strip()) or bool(json.loads(c.prompt_json or "{}")),
                            "image_ids": [i.id for i in img_by_entity.get(("character", c.id, "base_look"), [])],
                            "render_count": _render_count(img_by_entity.get(("character", c.id, "base_look"), []))}
                           for c in chars],
            "scenes": [{"id": s.id, "name": s.name, "description": s.description,
                        "base_prompt": s.base_prompt,
                        "slots": json.loads(s.prompt_json or "{}"),
                        "has_prompt": bool((s.base_prompt or "").strip()) or bool(json.loads(s.prompt_json or "{}")),
                        "anchor_path": getattr(s, "anchor_path", "") or "",
                        "anchor_image_id": next((i.id for i in img_by_entity.get(("scene", s.id, "scene"), [])
                                                 if i.file_path == getattr(s, "anchor_path", "")), None),
                        "image_ids": [i.id for i in img_by_entity.get(("scene", s.id, "scene"), [])],
                        "render_count": _render_count(img_by_entity.get(("scene", s.id, "scene"), []))}
                       for s in scenes],
            "props": [{"id": p.id, "name": p.name, "description": p.description,
                       "base_prompt": p.base_prompt,
                       "slots": json.loads(p.prompt_json or "{}"),
                       "has_prompt": bool((p.base_prompt or "").strip()) or bool(json.loads(p.prompt_json or "{}")),
                       "image_ids": [i.id for i in img_by_entity.get(("prop", p.id, "prop"), [])],
                       "render_count": _render_count(img_by_entity.get(("prop", p.id, "prop"), []))}
                      for p in props],
            "total_images": len(imgs),
        }


@router.delete("/entities/{etype}/{eid}")
def delete_entity(etype: str, eid: int):
    """删除资产（角色/场景/道具）：级联删除其全部生成图（文件+记录）、角色造型变体，
    并解除镜头首帧/尾帧/视频对已删文件的引用，防止后续进程错误调用。"""
    if etype not in ENTITY_TABLES:
        raise HTTPException(400, "实体类型错误")
    with SessionLocal() as db:
        entity = db.get(ENTITY_TABLES[etype], eid)
        if not entity:
            raise HTTPException(404, "资产不存在")
        # 该实体的全部生成图（meta_json 里 entity_type/entity_id 匹配 + character_id 兜底）
        imgs = db.scalars(select(AssetImage).where(AssetImage.project_id == entity.project_id)).all()
        del_paths: list[str] = []
        for i in imgs:
            meta = json.loads(i.meta_json or "{}")
            own = (meta.get("entity_type") == etype and meta.get("entity_id") == eid)
            if etype == "character" and i.character_id == eid:
                own = True
            if own:
                del_paths.append(str(i.file_path))
                db.delete(i)
        # 角色造型变体级联
        if etype == "character":
            for a in db.scalars(select(CharacterAppearance).where(
                    CharacterAppearance.character_id == eid)):
                db.delete(a)
        # 镜头引用解除（按已删文件路径匹配）
        cleared = 0
        for s in db.scalars(select(Shot).where(Shot.project_id == entity.project_id)):
            touched = False
            if s.first_frame_path and str(s.first_frame_path).replace("\\", "/") in [p.replace("\\", "/") for p in del_paths]:
                s.first_frame_path = ""; touched = True
            if s.end_frame_path and str(s.end_frame_path).replace("\\", "/") in [p.replace("\\", "/") for p in del_paths]:
                s.end_frame_path = ""; touched = True
            if s.video_path and str(s.video_path).replace("\\", "/") in [p.replace("\\", "/") for p in del_paths]:
                s.video_path = ""; touched = True
            if touched:
                if not s.first_frame_path:
                    s.status = "planned" if s.status in ("first_ready", "end_ready", "video_ready") else s.status
                cleared += 1
        db.delete(entity)
        db.commit()
        # DB 提交成功后再删物理文件
        for p in del_paths:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        return {"deleted": eid, "type": etype, "images_removed": len(del_paths),
                "shots_cleared": cleared}


@router.delete("/asset-images/{image_id}")
def delete_asset_image(image_id: int):
    """删除单张历史版本（文件+记录）。若被镜头首帧/尾帧/视频或造型脸参考引用，
    引用自动置空并回退状态，防止后续进程（IPA/首帧/宫格）错误调用已删图。"""
    with SessionLocal() as db:
        img = db.get(AssetImage, image_id)
        if not img:
            raise HTTPException(404, "图片不存在")
        path = str(img.file_path).replace("\\", "/")
        cleared = {"shots": 0, "appearances": 0}
        # 镜头引用清理（首帧/尾帧/视频按路径匹配）
        shots = db.scalars(select(Shot).where(
            (Shot.first_frame_path == img.file_path)
            | (Shot.end_frame_path == img.file_path)
            | (Shot.video_path == img.file_path))).all()
        for s in shots:
            if s.first_frame_path == img.file_path:
                s.first_frame_path = ""
            if s.end_frame_path == img.file_path:
                s.end_frame_path = ""
            if s.video_path == img.file_path:
                s.video_path = ""
            if not s.first_frame_path:
                s.status = "planned" if s.status in ("first_ready", "end_ready", "video_ready") else s.status
            elif not s.end_frame_path and s.status == "video_ready":
                s.status = "first_ready"
            cleared["shots"] += 1
        # 造型变体脸参考引用清理
        apps = db.scalars(select(CharacterAppearance).where(
            CharacterAppearance.face_ref_path == img.file_path)).all()
        for a in apps:
            a.face_ref_path = ""
            cleared["appearances"] += 1
        db.delete(img)
        db.commit()
        # 文件删除放最后（DB 提交成功才动文件；缺文件不阻塞记录删除）
        try:
            Path(img.file_path).unlink(missing_ok=True)
        except Exception:
            pass
        return {"deleted": image_id, "cleared": cleared}


# ---------- 资产编辑 / 重新渲染（手动调整闭环） ----------

class EntityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    base_prompt: str | None = None
    slots: dict | None = None            # 结构化槽位（提供时自动重组 base_prompt）
    portrait_mode: str | None = None     # 仅角色：sheet / single / board
    gen_mode: str | None = None          # 仅角色：auto/compose/board/layout/sheet


ENTITY_TABLES = {"character": Character, "scene": Scene, "prop": Prop}


@router.put("/entities/{etype}/{eid}")
def update_entity(etype: str, eid: int, body: EntityUpdate):
    if etype not in ENTITY_TABLES:
        raise HTTPException(400, "实体类型错误")
    with SessionLocal() as db:
        row = db.get(ENTITY_TABLES[etype], eid)
        if not row:
            raise HTTPException(404, "实体不存在")
        if body.name is not None:
            row.name = body.name
        if body.description is not None:
            row.description = body.description
        preset = row.style_preset if hasattr(row, "style_preset") else None
        if body.slots is not None:
            row.prompt_json = json.dumps(body.slots, ensure_ascii=False)
            # 槽位变更 → 按公式重组提示词（风格锁 + 活人感 + 组装器）
            project = db.get(Project, row.project_id)
            preset = project.style_preset if project else "anime_2d"
            lifelike = bool(project.lifelike) if project else True
            lifelike_full = bool(getattr(project, "lifelike_full", 0)) if project else False
            if etype == "character":
                # 【硬性要求】角色资产必须三视图：请求携带的 portrait_mode 一律归一 sheet
                mode = "sheet"
                row.portrait_mode = mode
                row.base_prompt = assemble_character_prompt(body.slots, preset, mode,
                                                            lifelike, lifelike_full)
            elif etype == "scene":
                row.base_prompt = assemble_scene_prompt(body.slots, preset, lifelike,
                                                        fallback_subject=row.name)
            elif etype == "prop":
                row.base_prompt = assemble_prop_prompt(body.slots, preset, lifelike,
                                                       fallback_subject=row.name)
        elif body.base_prompt is not None:
            row.base_prompt = body.base_prompt
        if body.portrait_mode is not None and etype == "character" and body.slots is None:
            row.portrait_mode = "sheet"   # 【硬性要求】改版式请求一律落 sheet
        if body.gen_mode is not None and etype == "character":
            if body.gen_mode not in CHAR_GEN_MODES:
                raise HTTPException(400, "未知角色生成方式")
            row.gen_mode = body.gen_mode
        db.commit()
        return {"id": row.id, "name": row.name, "base_prompt": row.base_prompt,
                "slots": json.loads(row.prompt_json or "{}"),
                "portrait_mode": getattr(row, "portrait_mode", None),
                "gen_mode": getattr(row, "gen_mode", "auto")}


class AnchorIn(BaseModel):
    asset_image_id: int | None = None
    path: str | None = None


@router.post("/scenes/{sid}/set-anchor")
def set_scene_anchor(sid: int, body: AnchorIn):
    """场景锚定图（缩略图法）：后续该场景的所有镜头首帧生成会注入此图锁环境一致。"""
    with SessionLocal() as db:
        s = db.get(Scene, sid)
        if not s:
            raise HTTPException(404, "场景不存在")
        if body.asset_image_id:
            img = db.get(AssetImage, body.asset_image_id)
            if not img or not Path(img.file_path).exists():
                raise HTTPException(404, "参考图不存在")
            s.anchor_path = img.file_path
        elif body.path and Path(body.path).exists():
            s.anchor_path = body.path
        else:
            raise HTTPException(400, "需要 asset_image_id 或有效 path")
        db.commit()
        return {"id": s.id, "name": s.name, "anchor_path": s.anchor_path}


@router.post("/scenes/{sid}/clear-anchor")
def clear_scene_anchor(sid: int):
    with SessionLocal() as db:
        s = db.get(Scene, sid)
        if not s:
            raise HTTPException(404, "场景不存在")
        s.anchor_path = ""
        db.commit()
        return {"id": s.id, "anchor_path": ""}


@router.post("/projects/{pid}/auto-scene-anchors")
async def auto_scene_anchors(pid: int):
    """一键补齐场景锚图：无锚场景自动生成 45° iso 等距剖面布局全景图并设为锚点。

    已有锚图的场景跳过；已有 iso 布局图的直接设锚（不重复渲染）。
    防重复：同项目已有 scene_anchor 任务在跑/排队时拒绝重复发起。
    """
    with SessionLocal() as db:
        if not db.get(Project, pid):
            raise HTTPException(404, "项目不存在")
        dup = next((t for t in db.scalars(select(TaskRecord).where(
            TaskRecord.type == "scene_anchor",
            TaskRecord.status.in_(("running", "pending")))).all()
            if json.loads(t.params_json or "{}").get("project_id") == pid), None)
        if dup:
            raise HTTPException(400, f"场景锚图任务 #{dup.id} 已在进行中，勿重复发起")
        t = task_queue.create_task(db, "scene_anchor", {"project_id": pid})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "scene_anchor"}


@router.post("/entities/{etype}/{eid}/rebuild-slots")
async def rebuild_slots(etype: str, eid: int):
    """旧资产槽位重铸：本地 LLM 按方法论模板从「名称+描述」反推结构化槽位。"""
    if etype not in ENTITY_TABLES:
        raise HTTPException(400, "实体类型错误")
    with SessionLocal() as db:
        row = db.get(ENTITY_TABLES[etype], eid)
        if not row:
            raise HTTPException(404, "实体不存在")
        params = {"entity_type": etype, "entity_id": eid, "project_id": row.project_id,
                  "name": row.name, "description": row.description}
        t = task_queue.create_task(db, "rebuild_slots", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


class RegenerateIn(BaseModel):
    project_id: int
    entity_type: str            # character / scene / prop
    entity_id: int
    model_key: str | None = None    # 手动指定模型（优先于 prefer_tier）
    prefer_tier: str | None = None  # low/mid/high
    width: int | None = None
    height: int | None = None
    iso_layout: bool = False        # 场景专用：生成 45° 等距空间布局全景图（场景缩略图/锚点候选）


ROLE_BY_ENTITY = {"character": "portrait", "scene": "scene", "prop": "prop"}

# 角色生成方式（决策 1）：auto=按风格自动 / compose=程序合成A / board=角色板B / layout=版式模型C / sheet=单张多视图
CHAR_GEN_MODES = ("auto", "compose", "board", "layout", "sheet")


def _character_task_params(db, pid, entity, preset, lifelike, lifelike_full,
                           auto_polish, tier, w, h, model_key=None):
    """按角色 gen_mode 分派生成任务类型与参数（方案 A/B/C 与动漫单张多视图）。"""
    import json as _json
    from .style_presets import style_family
    slots = _json.loads(getattr(entity, "prompt_json", "{}") or "{}")
    gm = getattr(entity, "gen_mode", "auto") or "auto"
    if gm in ("auto", "sheet"):
        # 【默认通道 2026-11-21】Qwen-Image 整张版式（实测赵总：左特写+正/侧/背三视图
        # 一次成型，纯侧/纯背转向正确，服装跨视图一致，信息栏+色卡自带）——
        # SDXL 单张必崩、compose img2img 转向弱，Qwen 版式/多视图服从度最强。
        # compose（SDXL 三视角拼版）保留为 gen_mode=compose 显式兜底通道。
        gm = "layout" if slots else "sheet"
    base = {"project_id": pid, "role": "portrait", "entity_type": "character",
            "entity_id": entity.id, "entity_name": entity.name,
            "style_preset": preset,
            "lifelike": lifelike, "lifelike_full": lifelike_full,
            "auto_polish": auto_polish}
    if gm == "compose" and slots:
        base.update({"task_type": "asset_compose", "slots": slots,
                     "prefer_tier": tier, "model_key": model_key})
        return "asset_compose", base
    if gm == "layout":
        # 版式模型整张多视图：默认 Qwen-Image（版式/多视图/中文小字渲染能力最强，
        # 实测 SDXL 整张版式必崩、compose img2img 转向弱）——8G 显存 offload 可跑。
        # 信息栏文字注入真实角色名（实测不注入时 Qwen 自由发挥伪文字）。
        caption = f', caption strip shows the Chinese text "{entity.name}" in small neat font'
        base.update({"task_type": "asset", "base_prompt": entity.base_prompt + caption,
                     "portrait_mode": "sheet", "prefer_tier": tier,
                     "model_key": model_key or "img_qwen_image",
                     "entity_name": entity.name})
        return "asset", base
    # 【硬性要求】角色资产必须三视图：gm single/board 通道废弃，一律 sheet
    mode = "sheet"
    base.update({"task_type": "asset", "base_prompt": entity.base_prompt,
                 "portrait_mode": mode, "prefer_tier": tier, "model_key": model_key,
                 "entity_name": entity.name,
                 "width": w, "height": h})
    return "asset", base


@router.post("/entities/{etype}/{eid}/from-reference")
async def gen_from_reference(etype: str, eid: int, body: dict):
    """真实参考图 → img2img 风格化重绘（实物类资产专用）。
    body: {project_id, image_url | ref_path, strength?, base_prompt?}"""
    if etype not in ("scene", "prop"):
        raise HTTPException(400, "参考图重绘仅支持场景/道具")
    with SessionLocal() as db:
        t = task_queue.create_task(db, "ref_redraw",
                                   {"entity_type": etype, "entity_id": eid, **body})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "ref_redraw"}


@router.post("/regenerate")
async def regenerate(body: RegenerateIn):
    """对单个资产重新渲染：使用实体当前 base_prompt + 指定模型档位，生成新版本。"""
    if body.entity_type not in ENTITY_TABLES:
        raise HTTPException(400, "实体类型错误")
    with SessionLocal() as db:
        entity = db.get(ENTITY_TABLES[body.entity_type], body.entity_id)
        if not entity:
            raise HTTPException(404, "实体不存在")
        project = db.get(Project, body.project_id)
        preset = project.style_preset if project else "anime_2d"
        lifelike = bool(project.lifelike) if project else True
        lifelike_full = bool(project.lifelike_full) if project else False
        auto_polish = bool(project.auto_polish) if project else False
        width, height = body.width, body.height
        if (width is None or height is None) and body.entity_type == "character":
            if width is None and height is None:
                width, height = _portrait_dims("sheet")
        # 槽位存在时按当前风格锁+活人感重组装（保证每次渲染词块一致）
        slots = json.loads(getattr(entity, "prompt_json", "{}") or "{}")
        if slots:
            if body.entity_type == "character":
                prompt = assemble_character_prompt(slots, preset, "sheet",
                                                   lifelike, lifelike_full)
            elif body.entity_type == "scene":
                prompt = assemble_scene_prompt(slots, preset, lifelike,
                                               fallback_subject=entity.name)
            else:
                prompt = assemble_prop_prompt(slots, preset, lifelike,
                                              fallback_subject=entity.name)
            # 重组结果回写 base_prompt：否则库里/store 里的仍是旧风格锁文本，
            # 角色 layout 通道与前端提示词框会继续拿旧 2D 词（#85 假象来源之一）
            if entity.base_prompt != prompt:
                entity.base_prompt = prompt
                db.commit()
        else:
            prompt = entity.base_prompt
        if body.iso_layout and body.entity_type == "scene":
            # 场景缩略图法：45° 等距剖面布局全景图，展示完整空间结构（用户参照 iso diorama 风格）
            prompt = (f"isometric cutaway diorama, 45-degree elevated dollhouse view of the complete space, "
                      f"entire layout visible in one frame, walls, furniture and prop placement clearly arranged, "
                      f"miniature 3D model style, soft studio lighting, plain dark background. Scene: {prompt}")
        if body.entity_type == "character":
            type_, params = _character_task_params(db, body.project_id, entity, preset,
                                                   lifelike, lifelike_full, auto_polish,
                                                   body.prefer_tier, width, height,
                                                   body.model_key)
            if type_ == "asset":
                params["base_prompt"] = prompt
        else:
            type_ = "asset"
            params = {"project_id": body.project_id,
                      "role": ROLE_BY_ENTITY[body.entity_type],
                      "entity_type": body.entity_type, "entity_id": body.entity_id,
                      "base_prompt": prompt,
                      "model_key": body.model_key, "prefer_tier": body.prefer_tier,
                      "width": width, "height": height, "auto_polish": auto_polish,
                      "style_preset": preset}
        t = task_queue.create_task(db, type_, params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": type_}


class RefineIn(BaseModel):
    asset_id: int                    # 源 AssetImage id（取最新版本即可）
    strength: float = 0.12           # 10% 幅度微调（0.10-0.15）
    project_id: int | None = None


@router.post("/refine-image")
async def refine_image(body: RefineIn):
    """对单张已生成图片做 10% img2img 微调：修复塑料感、补自然质感，构图与身份不变。"""
    with SessionLocal() as db:
        src = db.get(AssetImage, body.asset_id)
        if not src:
            raise HTTPException(404, "图片不存在")
        role = {"base_look": "portrait", "scene": "scene", "prop": "prop"}.get(src.kind, "portrait")
        params = {"project_id": src.project_id, "asset_id": src.id, "role": role,
                  "strength": max(0.08, min(0.2, float(body.strength)))}
        t = task_queue.create_task(db, "polish", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


class UpscaleIn(BaseModel):
    asset_id: int                    # 源 AssetImage id
    model: str | None = None         # 超分模型（默认按风格族自动选）


@router.post("/upscale-image")
async def upscale_image(body: UpscaleIn):
    """像素级超分放大（零 UNet 纯后处理，显存 <1GB、秒级）：
    写实族=4xNomos8kSCHAT-L，动漫族=4x-ESRGAN，通用=RealESRGAN_x2plus。"""
    with SessionLocal() as db:
        src = db.get(AssetImage, body.asset_id)
        if not src:
            raise HTTPException(404, "图片不存在")
        params = {"project_id": src.project_id, "asset_id": src.id,
                  "model": body.model}
        t = task_queue.create_task(db, "upscale", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id}


# ---------- 镜头卡 / 故事板（M3 基础） ----------

def _shot_dict(s: Shot, scene_anchor: str | None = None) -> dict:
    return {
        "id": s.id, "idx": s.idx, "scene_no": s.scene_no, "scene_name": s.scene_name,
        "int_ext": s.int_ext, "tod": s.tod, "duration": s.duration,
        "shot_size": s.shot_size, "camera_move": s.camera_move,
        "camera_speed": s.camera_speed, "camera_dir": s.camera_dir,
        "framing_start": s.framing_start, "framing_end": s.framing_end,
        "camera_angle": s.camera_angle, "focal_length": s.focal_length,
        "focus_transition": s.focus_transition, "blocking": s.blocking,
        "transition_in": getattr(s, "transition_in", ""),
        "beat": getattr(s, "beat", ""),
        "character_path": s.character_path, "subject_action": s.subject_action,
        "light": s.light, "composition": s.composition,
        "characters": json.loads(s.characters_json or "[]"),
        "props": json.loads(s.props_json or "[]"),
        "motion": json.loads(getattr(s, "motion_json", "") or "{}"),
        "dialogue": s.dialogue, "sfx": s.sfx,
        "image_prompt": s.image_prompt, "end_frame_prompt": s.end_frame_prompt,
        "video_prompt": s.video_prompt, "needs_end_frame": s.needs_end_frame,
        "first_frame_path": s.first_frame_path, "end_frame_path": s.end_frame_path,
        "video_path": s.video_path, "status": s.status,
        # 场景锚定图（缩略图法）：该镜首帧生成时会注入此图锁环境一致
        "scene_anchor_path": scene_anchor or "",
        "framing_start_key": s.framing_start,
        # M2.6：动作拍点 / 氛围 / 视效 / 轴线与承接 / 模板
        "action_beats": json.loads(s.action_beats_json or "[]"),
        "atmosphere": s.atmosphere,
        "mood_tags": json.loads(s.mood_tags_json or "[]"),
        "vfx_type": s.vfx_type, "vfx_note": s.vfx_note,
        "key_frame_prompt": s.key_frame_prompt,
        "prompt_template_id": s.prompt_template_id,
        "screen_direction": s.screen_direction,
        "composition_anchor": s.composition_anchor,
        "prev_summary": s.prev_summary, "next_goal": s.next_goal,
        "continuity_guidance": s.continuity_guidance,
        "ref_overrides": json.loads(getattr(s, "ref_overrides_json", "") or "{}"),
    }


@router.get("/episodes/{eid}/shots")
def list_shots(eid: int):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        rows = db.scalars(select(Shot).where(Shot.episode_id == eid)
                          .order_by(Shot.idx)).all()
        # 场景名 → 锚定图（缩略图法）：镜头卡片直接展示参考图清单
        anchors = {}
        for sc in db.scalars(select(Scene).where(Scene.project_id == ep.project_id)).all():
            if getattr(sc, "anchor_path", ""):
                anchors[sc.name] = sc.anchor_path
        return [_shot_dict(r, anchors.get((r.scene_name or "").strip())) for r in rows]


class ShotUpdate(BaseModel):
    dialogue: str | None = None    # 台词（「角色名（语气）：台词」，说话镜/配音共用）
    ref_overrides: dict | None = None   # 手动指定参考 {"角色名": path, "__scene__": path}，空值=清除
    motion: dict | None = None     # 运动动作控制 {posture,gesture,expression,gaze,intensity,secondary}
    camera_move: str | None = None
    camera_speed: str | None = None
    camera_dir: str | None = None
    framing_start: str | None = None
    framing_end: str | None = None
    camera_angle: str | None = None
    focal_length: str | None = None
    focus_transition: str | None = None
    blocking: str | None = None
    character_path: str | None = None
    subject_action: str | None = None
    end_action: str | None = None
    needs_end_frame: int | None = None
    image_prompt: str | None = None
    end_frame_prompt: str | None = None
    video_prompt: str | None = None
    key_frame_prompt: str | None = None
    atmosphere: str | None = None
    vfx_type: str | None = None
    vfx_note: str | None = None
    action_beats: list[dict] | None = None
    screen_direction: str | None = None
    continuity_guidance: str | None = None
    transition_in: str | None = None   # 与上镜的转场方式：''/hard_cut/match_cut/whip_pan/object_pass/light_flash/dissolve


@router.patch("/shots/{sid}")
def update_shot(sid: int, body: ShotUpdate):
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        for k, v in body.model_dump(exclude_none=True).items():
            if k == "action_beats":
                s.action_beats_json = json.dumps(v, ensure_ascii=False)
            elif k == "ref_overrides":
                cur = json.loads(getattr(s, "ref_overrides_json", "") or "{}")
                for ok, ov in v.items():      # 值为空串/null → 清除该覆盖，回落自动选
                    if ov:
                        cur[ok] = ov
                    else:
                        cur.pop(ok, None)
                s.ref_overrides_json = json.dumps(cur, ensure_ascii=False)
            elif k == "motion":
                # 运动动作控制：字段白名单 + 值裁剪，防任意键/超长文本进提示词
                cur = json.loads(getattr(s, "motion_json", "") or "{}")
                for mk in ("posture", "gesture", "expression", "gaze",
                           "intensity", "secondary"):
                    mv = (v.get(mk) or "").strip()
                    if mv:
                        cur[mk] = mv[:200]
                    else:
                        cur.pop(mk, None)
                s.motion_json = json.dumps(cur, ensure_ascii=False)
            elif hasattr(s, k):
                setattr(s, k, v)
        if body.needs_end_frame is None and (body.camera_move or body.character_path):
            move = s.camera_move or "固定"
            s.needs_end_frame = 1 if (move in MOVING_CAMERA or s.character_path) else 0
        db.commit()
        return _shot_dict(s)


@router.get("/shots/{sid}/refs")
def shot_refs(sid: int):
    """镜头参考溯源：本镜首帧/视频生成时实际引用的资产图 + 全部候选（调整窗口用）。

    - 角色：按 characters_json 顺序，used=face_ref>base_look（或镜头级手动指定），
      candidates=该角色资产库全部单人图（新→旧）；
    - 场景：used=Scene.anchor_path（或手动指定），candidates=项目 scene 资产；
    - 道具：仅提示词级引用（不挂图），如实标注。
    """
    from .db import Character
    from .services.shot_service import _ref_overrides, _face_candidates, _scene_anchor
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        ov = _ref_overrides(s)
        names = json.loads(s.characters_json or "[]")
        chars = {c.name: c for c in db.scalars(select(Character).where(
            Character.project_id == s.project_id)).all()}
        chars_out = []
        for n in names:
            c = chars.get(n)
            cid = c.id if c else None
            cands = []
            used_path, used_kind, source = "", "", ""
            if cid:
                cands = [{"path": p, "kind": "face_ref"} for p in _face_candidates(db, cid)]
                # 与生成链路同源：override > 角色级脸锁 > 自动择优第一张
                lock = getattr(c, "face_lock_path", "") or ""
                if ov.get(n) and Path(ov[n]).exists():
                    used_path, used_kind, source = ov[n], "override", "manual"
                elif lock and Path(lock).exists():
                    used_path, used_kind, source = lock, "face_lock", "locked"
                elif cands:
                    used_path, used_kind, source = cands[0]["path"], cands[0]["kind"], "auto"
            chars_out.append({"name": n, "character_id": cid, "used_path": used_path,
                              "used_kind": used_kind, "source": source,
                              "candidates": cands})
        # 场景：与生成链路同源（_scene_anchor 三级回退）；source 区分手动/锚点/自动回退
        scene_used, scene_src = "", ""
        if ov.get("__scene__") and Path(ov["__scene__"]).exists():
            scene_used, scene_src = ov["__scene__"], "manual"
        else:
            auto_scene = _scene_anchor(db, s)
            if auto_scene:
                scene_used = auto_scene
                sc = db.scalars(select(Scene).where(
                    Scene.project_id == s.project_id,
                    Scene.name == (s.scene_name or "").strip())).first()
                scene_src = ("anchor" if sc and sc.anchor_path
                             and Path(sc.anchor_path).exists()
                             and sc.anchor_path == auto_scene else "auto")
        scene_cands = [{"path": r.file_path, "kind": r.kind} for r in
                       db.scalars(select(AssetImage).where(
                           AssetImage.project_id == s.project_id,
                           AssetImage.kind == "scene")
                           .order_by(AssetImage.id.desc())).all()
                       if Path(r.file_path).exists()]
        # 道具：首帧链路只走提示词，不用图（如实标注）
        props_out = []
        for pn in json.loads(s.props_json or "[]"):
            cnt = db.scalar(select(func.count()).select_from(AssetImage).where(
                AssetImage.project_id == s.project_id,
                AssetImage.kind == "prop",
                AssetImage.prompt.like(f"%{pn}%")))
            props_out.append({"name": pn, "asset_count": cnt or 0,
                              "usage": "prompt_only"})
        return {"shot_id": s.id, "idx": s.idx, "characters": chars_out,
                "scene": {"name": s.scene_name, "used_path": scene_used,
                          "source": scene_src, "candidates": scene_cands},
                "props": props_out}


@router.post("/episodes/{eid}/rebuild-prompts")
def rebuild_episode_prompts(eid: int):
    """不重跑 LLM，按当前模板/运镜/拍点就地重组装全部镜头提示词。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        p = db.get(Project, ep.project_id)
        n = script_service.reassemble_episode_prompts(
            db, eid, ep.project_id, p.style_preset or "anime_2d",
            bool(p.lifelike), bool(p.lifelike_full))
        return {"ok": True, "shots": n}


# ---------- 镜头生成（M3：首帧 / 尾帧 / 视频 / 宫格） ----------

class ShotGenBody(BaseModel):
    frame_type: str = "first"      # first | end
    prefer_tier: str | None = None
    duration: int | None = None
    ipa_weight: float | None = None  # IPAdapter 锁脸强度（0.55/0.70/0.85 三档）
    model_key: str | None = None     # 显式指定生成模型（如 vid_h3_turbo 提速档）


@router.post("/shots/{sid}/frame")
async def gen_shot_frame(sid: int, body: ShotGenBody | None = None):
    b = body or ShotGenBody()
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        t = TaskRecord(type="shot_frame", status="pending",
                       params_json=json.dumps({"shot_id": sid, "frame_type": b.frame_type,
                                               "ipa_weight": b.ipa_weight},
                                              ensure_ascii=False))
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    task_queue.spawn_bg(_run_bg(tid))
    return {"task_id": tid, "task_type": "shot_frame"}


@router.post("/shots/{sid}/video")
async def gen_shot_video_api(sid: int, body: ShotGenBody | None = None):
    b = body or ShotGenBody()
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        t = TaskRecord(type="shot_video", status="pending",
                       params_json=json.dumps({"shot_id": sid, "prefer_tier": b.prefer_tier,
                                               "duration": b.duration,
                                               "model_key": b.model_key}, ensure_ascii=False))
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    task_queue.spawn_bg(_run_bg(tid))
    return {"task_id": tid, "task_type": "shot_video"}


@router.post("/shots/{sid}/talk")
async def gen_shot_talk_api(sid: int, body: ShotGenBody | None = None):
    """音频驱动说话镜（InfiniteTalk）：首帧+台词配音 → 口型跟音频的说话视频。"""
    b = body or ShotGenBody()
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        if not (s.dialogue or "").strip():
            raise HTTPException(400, "本镜没有台词，先在镜头卡里填写台词再生成说话镜头")
        t = TaskRecord(type="shot_talk", status="pending",
                       params_json=json.dumps({"shot_id": sid}, ensure_ascii=False))
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    task_queue.spawn_bg(_run_bg(tid))
    return {"task_id": tid, "task_type": "shot_talk"}


@router.post("/shots/{sid}/grid")
async def gen_shot_grid(sid: int, body: ShotGenBody | None = None):
    b = body or ShotGenBody()
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        t = TaskRecord(type="grid9", status="pending",
                       params_json=json.dumps({"shot_id": sid, "ipa_weight": b.ipa_weight},
                                              ensure_ascii=False))
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    task_queue.spawn_bg(_run_bg(tid))
    return {"task_id": tid, "task_type": "grid9"}


class ChainNextBody(BaseModel):
    strength: float | None = None     # 接力重绘幅度 0.2-0.5，默认 0.35


@router.post("/shots/{sid}/chain-next")
async def chain_next_frame(sid: int, body: ChainNextBody | None = None):
    """镜头接力：本镜末帧（尾帧优先，否则视频末帧）→ 下一镜首帧 img2img，
    构图光影连贯，人物位置自然衔接。"""
    b = body or ChainNextBody()
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        t = TaskRecord(type="shot_chain", status="pending",
                       params_json=json.dumps({"shot_id": sid, "strength": b.strength},
                                              ensure_ascii=False))
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    task_queue.spawn_bg(_run_bg(tid))
    return {"task_id": tid, "task_type": "shot_chain"}


class ExtendBody(BaseModel):
    seconds: int = 3                  # 续写时长（方言层按模型上限收口）


@router.post("/shots/{sid}/extend-video")
async def extend_shot_video_api(sid: int, body: ExtendBody | None = None):
    """镜内续写：本镜视频末帧 → 续写一段 i2v → ffmpeg 拼接，单镜时长不够时用。"""
    b = body or ExtendBody()
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404, "镜头不存在")
        t = TaskRecord(type="shot_extend", status="pending",
                       params_json=json.dumps({"shot_id": sid, "seconds": b.seconds,
                                               "prefer_tier": None}, ensure_ascii=False))
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    task_queue.spawn_bg(_run_bg(tid))
    return {"task_id": tid, "task_type": "shot_extend"}


class GridPickBody(BaseModel):
    cell_path: str


@router.post("/shots/{sid}/pick-grid-cell")
async def pick_grid_cell(sid: int, body: GridPickBody):
    with SessionLocal() as db:
        return await shot_service.pick_grid_cell(db, None, {"shot_id": sid, "cell_path": body.cell_path})


@router.get("/shots/{sid}/frame-file")
def shot_frame_file(sid: int, which: str = "first"):
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404)
    p = Path(s.end_frame_path or "") if which == "end" else Path(s.first_frame_path or "")
    if not p or not p.exists():
        raise HTTPException(404, "帧图尚未生成")
    return FileResponse(p)


@router.get("/shots/{sid}/video-file")
def shot_video_file(sid: int):
    with SessionLocal() as db:
        s = db.get(Shot, sid)
        if not s:
            raise HTTPException(404)
    p = Path(s.video_path or "")
    if not p or not p.exists():
        raise HTTPException(404, "视频尚未生成")
    return FileResponse(p, media_type="video/mp4")


@router.get("/shots/{sid}/grid")
def shot_grid_meta(sid: int):
    """返回该镜最近一次九宫格的单元格列表（前端刷新后仍能选格）。

    宫格仅支持动漫/国潮/3D 族；写实等其他风格下不返回历史宫格，
    避免风格切换后旧资产继续出现在新风格分镜卡上。
    """
    from .style_presets import style_family
    with SessionLocal() as db:
        shot = db.get(Shot, sid)
        if not shot:
            raise HTTPException(404, "镜头不存在")
        fam = style_family(
            (db.get(Project, shot.project_id).style_preset if db.get(Project, shot.project_id) else "") or "")
        if fam not in ("anime", "paint", "3d"):
            return {"grid_path": "", "cells": []}
        rows = db.scalars(select(AssetImage).where(
            AssetImage.kind == "grid9").order_by(AssetImage.id.desc())).all()
        for r in rows:
            meta = json.loads(r.meta_json or "{}")
            if meta.get("shot_id") == sid:
                return {"grid_path": r.file_path, "cells": meta.get("cells", [])}
    return {"grid_path": "", "cells": []}


@router.get("/shots/{sid}/cell-file")
def shot_cell_file(sid: int, i: int = 0):
    with SessionLocal() as db:
        from .style_presets import style_family
        shot = db.get(Shot, sid)
        if not shot:
            raise HTTPException(404, "镜头不存在")
        fam = style_family(
            (db.get(Project, shot.project_id).style_preset if db.get(Project, shot.project_id) else "") or "")
        if fam not in ("anime", "paint", "3d"):
            raise HTTPException(404, "当前风格不支持宫格")
        rows = db.scalars(select(AssetImage).where(
            AssetImage.kind == "grid9").order_by(AssetImage.id.desc())).all()
        for r in rows:
            meta = json.loads(r.meta_json or "{}")
            if meta.get("shot_id") == sid:
                cells = meta.get("cells", [])
                if 0 <= i < len(cells) and Path(cells[i]).exists():
                    return FileResponse(cells[i])
    raise HTTPException(404, "宫格尚未生成")


@router.get("/dialects")
def list_dialects():
    from .services.dialects import MAX_SECONDS
    return [{"family": k, "max_seconds": v} for k, v in MAX_SECONDS.items()]


# ---------- 配音与成片（edge-tts + concat + SRT/NVENC 烧字幕） ----------

class VoiceIn(BaseModel):
    voice: str


@router.get("/voice-presets")
def voice_presets():
    return voice_service.VOICE_MENU


@router.get("/projects/{pid}/voice-availability")
def voice_availability(pid: int):
    """音色占用表：{voice: 占用者名}（角色 + 旁白）。前端下拉禁用已占用项。"""
    with SessionLocal() as db:
        return voice_service.taken_voices(db, pid)


class NarratorVoiceIn(VoiceIn):
    pass


@router.post("/projects/{pid}/narrator-voice")
async def set_narrator_voice(pid: int, body: VoiceIn):
    """锁定旁白/无前缀台词音色（空 = 未设置，配音会要求先设置）。音色不可与角色重复。"""
    with SessionLocal() as db:
        p = db.get(Project, pid)
        if not p:
            raise HTTPException(404, "项目不存在")
        if body.voice:
            clash = voice_service.taken_voices(db, pid).get(body.voice)
            if clash and clash != "旁白":
                raise HTTPException(400, f"音色已被角色「{clash}」使用，请换一个")
        p.narrator_voice = body.voice
        db.commit()
        return {"project_id": pid, "narrator_voice": p.narrator_voice}


@router.get("/projects/{pid}/narrator-voice")
def get_narrator_voice(pid: int):
    with SessionLocal() as db:
        p = db.get(Project, pid)
        if not p:
            raise HTTPException(404, "项目不存在")
        return {"project_id": pid, "narrator_voice": getattr(p, "narrator_voice", "") or ""}


@router.get("/voice-preview-file")
async def voice_preview_file(voice: str, pid: int = 1):
    """试听音色：GET 直接返回样音 mp3（无缓存则现生成，同音色缓存复用）。"""
    if not voice:
        raise HTTPException(400, "请先选择音色")
    try:
        f = await voice_service.voice_preview(voice, pid)
    except Exception as e:
        raise HTTPException(502, f"试听生成失败：{e}")
    return FileResponse(f, media_type="audio/mpeg")


@router.post("/characters/{cid}/voice")
async def set_character_voice(cid: int, body: VoiceIn):
    """设置角色配音音色（空 = 未设置）。音色唯一 + 必须与角色性别匹配。"""
    with SessionLocal() as db:
        ch = db.get(Character, cid)
        if not ch:
            raise HTTPException(404, "角色不存在")
        if body.voice:
            clash = voice_service.taken_voices(db, ch.project_id,
                                               exclude_character_id=ch.id).get(body.voice)
            if clash:
                raise HTTPException(400, f"音色已被「{clash}」使用，每个角色/旁白音色必须唯一")
            # 性别匹配：女角色禁用男声、男角色禁用女声（描述判不出性别时不强判）
            desc = f"{ch.description or ''} {getattr(ch, 'prompt_json', '') or ''}"
            g = voice_service.guess_gender(desc)
            vg = voice_service.VOICE_GENDER.get(body.voice)
            if g and vg and g != vg:
                want = "女声" if g == "f" else "男声"
                raise HTTPException(400, f"角色「{ch.name}」按描述应为{want}，请选对应性别的音色（性别不对就先改角色描述）")
        ch.voice = body.voice
        db.commit()
        return {"id": ch.id, "name": ch.name, "voice": ch.voice}


@router.post("/episodes/{eid}/tts")
async def episode_tts(eid: int):
    """本集全部台词批量 TTS（edge-tts 在线，零显存）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        t = task_queue.create_task(db, "tts", {"episode_id": eid,
                                               "project_id": ep.project_id})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "tts"}


@router.post("/episodes/{eid}/export-final")
async def episode_export_final(eid: int):
    """成片合成：逐镜无损拼接 → 台词混音 → SRT → NVENC 烧字幕。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        t = task_queue.create_task(db, "stitch", {"episode_id": eid,
                                                  "project_id": ep.project_id})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "stitch"}


class BatchIn(BaseModel):
    ipa_weight: float | None = None
    duration: int | None = None
    chain: bool = True              # 批量首帧链式接力（上镜末帧→下镜首帧）
    from_idx: int | None = None     # 向后重链起始镜号
    model_key: str | None = None    # 视频模型显式指定（如 vid_h3_turbo 提速档；缺省走全局默认）


@router.post("/episodes/{eid}/batch-frames")
async def episode_batch_frames(eid: int, body: BatchIn = None):
    """批量首帧：跳过已有首帧的镜头（幂等断点续跑）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        params = {"episode_id": eid, "project_id": ep.project_id,
                  "ipa_weight": body.ipa_weight if body else None,
                  "chain": body.chain if body else True}
        t = task_queue.create_task(db, "batch_frames", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "batch_frames"}


@router.post("/episodes/{eid}/batch-videos")
async def episode_batch_videos(eid: int, body: BatchIn = None):
    """批量视频：有首帧缺视频的镜头逐个 i2v（缺尾帧自动补）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        params = {"episode_id": eid, "project_id": ep.project_id,
                  "ipa_weight": body.ipa_weight if body else None,
                  "duration": body.duration if body else None,
                  "model_key": body.model_key if body else None}
        t = task_queue.create_task(db, "batch_videos", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "batch_videos"}


@router.post("/episodes/{eid}/batch-transitions")
async def episode_batch_transitions(eid: int):
    """批量转场镜（方案二可选开关）：场景切换边界 → 上镜末帧+下镜首帧双帧 i2v 过渡镜。
    幂等：已有产物跳过；单边缺产物（上镜缺视频/尾帧、下镜缺首帧）跳过并记录原因。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        dup = next((t for t in db.scalars(select(TaskRecord).where(
            TaskRecord.type == "batch_transitions",
            TaskRecord.status.in_(("running", "pending")))).all()
            if json.loads(t.params_json or "{}").get("episode_id") == eid), None)
        if dup:
            raise HTTPException(400, f"该集已有转场镜任务在跑（任务 #{dup.id}）")
        t = task_queue.create_task(db, "batch_transitions",
                                   {"episode_id": eid, "project_id": ep.project_id})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "batch_transitions"}


@router.post("/episodes/{eid}/rechain-from")
async def episode_rechain_from(eid: int, body: BatchIn = None):
    """向后重链：以 from_idx-1 镜为锚点，从 from_idx 镜起逐镜 末帧→接力首帧→视频 连锁重生成。
    断链即停，修复后可从断点镜再链。全链重刷传 from_idx=1（第 1 镜也会重生成）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        # 防重复：同集已有重链在跑/排队时拒绝重复发起（避免多条链互相碾压产物）。
        # 参数在 Python 侧精确解析（LIKE '%"episode_id": 1%' 会误伤集 11/12…）
        dup = next((t for t in db.scalars(select(TaskRecord).where(
            TaskRecord.type == "rechain_from",
            TaskRecord.status.in_(("running", "pending")))).all()
            if json.loads(t.params_json or "{}").get("episode_id") == eid), None)
        if dup:
            raise HTTPException(400, f"该集已有重链任务在跑（任务 #{dup.id}），"
                                     "可在底部「队列详情」里取消后再发")
        from_idx = (body.from_idx if body and body.from_idx else 1)
        params = {"episode_id": eid, "project_id": ep.project_id,
                  "ipa_weight": body.ipa_weight if body else None,
                  "duration": body.duration if body else None,
                  "model_key": body.model_key if body else None,
                  "from_idx": from_idx}
        t = task_queue.create_task(db, "rechain_from", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "rechain_from", "from_idx": from_idx}


@router.post("/episodes/{eid}/full-pipeline")
async def episode_full_pipeline(eid: int, body: BatchIn = None):
    """一键全流程：缺首帧 → 缺视频（自动补尾帧）→ TTS → 成片合成。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        params = {"episode_id": eid, "project_id": ep.project_id,
                  "ipa_weight": body.ipa_weight if body else None,
                  "duration": body.duration if body else None,
                  "model_key": body.model_key if body else None}
        t = task_queue.create_task(db, "full_pipeline", params)
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "full_pipeline"}


@router.post("/episodes/{eid}/export-jianying")
async def episode_export_jianying(eid: int):
    """导出剪映草稿 draft_content.json（视频轨+台词文本轨）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        t = task_queue.create_task(db, "export_jianying",
                                   {"episode_id": eid, "project_id": ep.project_id})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "export_jianying"}


@router.post("/episodes/{eid}/export-fcpxml")
async def episode_export_fcpxml(eid: int):
    """导出 FCPXML 1.8（Premiere/达芬奇/FCPX 可导入）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        t = task_queue.create_task(db, "export_fcpxml",
                                   {"episode_id": eid, "project_id": ep.project_id})
    task_queue.spawn_bg(_run_bg(t.id))
    return {"task_id": t.id, "task_type": "export_fcpxml"}


@router.get("/episodes/{eid}/export-files")
def episode_export_files(eid: int):
    """导出文件清单（剪映草稿/FCPXML 下载链接）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        export_dir = voice_service.ASSETS_ROOT / str(ep.project_id) / "export"
        files = {}
        jy = export_dir / f"jianying_ep{eid}_draft_content.json"
        fx = export_dir / f"ep{eid}.fcpxml"
        files["jianying"] = f"/api/episodes/{eid}/jianying-file" if jy.exists() else ""
        files["fcpxml"] = f"/api/episodes/{eid}/fcpxml-file" if fx.exists() else ""
        return files


@router.get("/episodes/{eid}/jianying-file")
def episode_jianying_file(eid: int):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        f = voice_service.ASSETS_ROOT / str(ep.project_id) / "export" / f"jianying_ep{eid}_draft_content.json"
    if f.exists():
        return FileResponse(f, media_type="application/json", filename=f"ep{eid}_draft_content.json")
    raise HTTPException(404, "剪映草稿尚未导出")


@router.get("/episodes/{eid}/fcpxml-file")
def episode_fcpxml_file(eid: int):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        f = voice_service.ASSETS_ROOT / str(ep.project_id) / "export" / f"ep{eid}.fcpxml"
    if f.exists():
        return FileResponse(f, media_type="application/xml", filename=f"ep{eid}.fcpxml")
    raise HTTPException(404, "FCPXML 尚未导出")


@router.get("/episodes/{eid}/export-status")
def episode_export_status(eid: int):
    """成片/字幕文件现状（前端刷新用）。"""
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        export_dir = voice_service.ASSETS_ROOT / str(ep.project_id) / "export"
        final = export_dir / f"final_ep{eid}.mp4"
        srt = export_dir / f"final_ep{eid}.srt"
        return {"final_ready": final.exists(),
                "final_file": f"/api/episodes/{eid}/final-file" if final.exists() else "",
                "srt_ready": srt.exists(),
                "srt_file": f"/api/episodes/{eid}/srt-file" if srt.exists() else ""}


@router.get("/episodes/{eid}/final-file")
def episode_final_file(eid: int):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        f = voice_service.ASSETS_ROOT / str(ep.project_id) / "export" / f"final_ep{eid}.mp4"
    if f.exists():
        return FileResponse(f, media_type="video/mp4")
    raise HTTPException(404, "成片尚未生成")


@router.get("/episodes/{eid}/srt-file")
def episode_srt_file(eid: int):
    with SessionLocal() as db:
        ep = db.get(Episode, eid)
        if not ep:
            raise HTTPException(404, "剧集不存在")
        f = voice_service.ASSETS_ROOT / str(ep.project_id) / "export" / f"final_ep{eid}.srt"
    if f.exists():
        return FileResponse(f, media_type="text/plain", filename=f"ep{eid}.srt")
    raise HTTPException(404, "字幕尚未生成")


# ---------- 提示词模板（M2.6，Jellyfish 表同构） ----------

def _tpl_dict(t) -> dict:
    return {"id": t.id, "project_id": t.project_id, "stage": t.stage, "name": t.name,
            "content": t.content, "variables": json.loads(t.variables_json or "[]"),
            "is_default": t.is_default, "is_system": t.is_system,
            "stage_label": STAGES.get(t.stage, t.stage)}


@router.get("/prompt-templates")
def list_prompt_templates(project_id: int | None = None):
    with SessionLocal() as db:
        q = select(PromptTemplate)
        if project_id is not None:
            q = q.where((PromptTemplate.project_id == project_id) |
                        (PromptTemplate.project_id.is_(None)))
        else:
            q = q.where(PromptTemplate.project_id.is_(None))
        return [_tpl_dict(t) for t in db.scalars(q.order_by(PromptTemplate.stage,
                                                           PromptTemplate.id)).all()]


@router.get("/prompt-templates/stages")
def prompt_template_stages():
    return [{"stage": k, "label": v} for k, v in STAGES.items()]


class TemplateUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    is_default: int | None = None


@router.put("/prompt-templates/{tid}")
def update_prompt_template(tid: int, body: TemplateUpdate):
    from .services.prompt_templates import _vars_of
    with SessionLocal() as db:
        t = db.get(PromptTemplate, tid)
        if not t:
            raise HTTPException(404, "模板不存在")
        if t.is_system and (body.content is not None or body.name is not None):
            raise HTTPException(400, "系统预置模板只读，请先「复制为自定义」再改")
        if body.name is not None:
            t.name = body.name
        if body.content is not None:
            t.content = body.content
            t.variables_json = json.dumps(sorted(_vars_of(body.content)), ensure_ascii=False)
        if body.is_default is not None:
            if body.is_default:
                # 同 scope 同 stage 只能有一条默认
                for other in db.scalars(select(PromptTemplate).where(
                        PromptTemplate.stage == t.stage,
                        PromptTemplate.project_id == t.project_id)).all():
                    other.is_default = 1 if other.id == t.id else 0
            else:
                t.is_default = 0
        db.commit()
        return _tpl_dict(t)


class TemplateCreate(BaseModel):
    project_id: int
    stage: str
    name: str
    content: str
    is_default: int = 0


@router.post("/prompt-templates")
def create_prompt_template(body: TemplateCreate):
    from .services.prompt_templates import STAGES as _S, _vars_of
    if body.stage not in _S:
        raise HTTPException(400, "未知 stage")
    with SessionLocal() as db:
        t = PromptTemplate(project_id=body.project_id, stage=body.stage, name=body.name,
                           content=body.content,
                           variables_json=json.dumps(sorted(_vars_of(body.content)),
                                                     ensure_ascii=False),
                           is_default=body.is_default, is_system=0)
        db.add(t)
        db.commit()
        db.refresh(t)
        return _tpl_dict(t)


@router.delete("/prompt-templates/{tid}")
def delete_prompt_template(tid: int):
    with SessionLocal() as db:
        t = db.get(PromptTemplate, tid)
        if not t:
            raise HTTPException(404, "模板不存在")
        if t.is_system:
            raise HTTPException(400, "系统预置模板不可删除，只能改内容或另建自定义模板")
        db.delete(t)
        db.commit()
        return {"ok": True}


# ---------- 自强化提示词库（#90：Qwen-Image / MiniMax H3 实战词块统计） ----------

@router.get("/prompt-bank")
def prompt_bank_view():
    """词库全量视图：按 family 分组，weight=kept-1.5*failed 降序，含拉黑标记。"""
    from .services.prompt_bank import snapshot
    return snapshot()


class BankChunkIn(BaseModel):
    family: str                     # qwen_image | minimax_h3 | sdxl | flux2_klein
    kind: str = "image"             # image | video
    action: str = "add"             # add | remove
    text: str = ""
    key: str = ""                   # remove 时的词块 key


@router.post("/prompt-bank/chunk")
def prompt_bank_chunk(body: BankChunkIn):
    """手动增删词块（add 默认 kept=1 视为人工已验证；remove 按 key 删除）。"""
    from .services.prompt_bank import add_chunk, remove_chunk
    if body.action == "remove":
        ok = remove_chunk(body.family, body.key)
    else:
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(400, "text 不能为空")
        ok = add_chunk(body.family, text, body.kind)
    if not ok:
        raise HTTPException(400, "操作失败（重复词块 / 池已满 / key 不存在）")
    return {"ok": True}


@router.post("/prompt-bank/harvest")
def prompt_bank_harvest():
    """提炼入库：扫描现存成功产物提示词（资产图/镜头视频），高频短语自动进词库。
    图片源 → qwen_image（场景/道具/角色图提示词）；视频源 → minimax_h3（镜头 video_prompt）。"""
    from .services.prompt_bank import harvest
    from .services.model_vocab import MODEL_PROMPT_VOCAB
    docs_img, docs_vid = [], []
    with SessionLocal() as db:
        for a in db.scalars(select(AssetImage).where(AssetImage.kind.in_(
                ("scene", "prop", "portrait", "character")))).all():
            if a.prompt and a.file_path and Path(a.file_path).exists():
                docs_img.append(a.prompt)
        for s in db.scalars(select(Shot).where(Shot.video_path != "")).all():
            if s.video_prompt and s.video_path and Path(s.video_path).exists():
                docs_vid.append(s.video_prompt)

    def _phrases(fams):
        out = set()
        for f in fams:
            for v in MODEL_PROMPT_VOCAB.get(f, {}).values():
                out.update(p.strip().lower() for p in str(v).split(",") if p.strip())
        return out

    # 跨族禁用：视频族方言词不进 Qwen 图片库；图像族 + wan 系方言词不进 H3 视频库
    img_fams = ("sdxl", "flux2_klein", "qwen_image")
    vid_fams = ("minimax_h3", "wan", "infinitalk")
    added_img = harvest(docs_img, "qwen_image", "image", forbid_extra=_phrases(vid_fams))
    added_vid = harvest(docs_vid, "minimax_h3", "video",
                        forbid_extra=_phrases(img_fams + ("wan", "infinitalk")))
    return {"sources": {"image": len(docs_img), "video": len(docs_vid)},
            "added": {"qwen_image": added_img, "minimax_h3": added_vid}}


# 允许 uvicorn 启动时建表
init_db()

