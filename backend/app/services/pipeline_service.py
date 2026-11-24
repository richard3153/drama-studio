"""M4/M5 批量编排服务：一键把本集所有镜头推到成片。

核心原则（闭环）：
- 幂等：单镜已有产物（文件存在）直接跳过 → 任务中断后重跑等于断点续跑；
- 不中断：单镜失败记录进 failed 列表继续下一镜，最后汇总；
- 复用：直接 await 单镜生成函数（generate_shot_frame / generate_shot_video），
  它们不持 heavy 锁，锁由编排任务本身持有，天然 GPU 串行。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from ..db import Episode, Project, Shot, TaskRecord
from ..scheduler.queue import update_progress
from . import shot_service, voice_service


def _collect(db, eid: int):
    return db.scalars(select(Shot).where(Shot.episode_id == eid)
                      .order_by(Shot.idx)).all()


def _ok(p: str | None) -> bool:
    return bool(p) and Path(p).exists()


async def _run_step(db, t: TaskRecord, label: str, done: int, total: int, coro):
    """单镜子步骤执行：进度条按全局比例推进，失败不中断只记录。"""
    update_progress(db, t, done / max(total, 1), f"{label}（{done + 1}/{total}）")
    try:
        await coro
        return None
    except Exception as e:
        return f"{label}: {str(e)[:200]}"


def _has_chainable_src(s: Shot) -> bool:
    """该镜可作为接力源：有视频（可抽真实末帧）或已有显式尾帧。"""
    return _ok(s.video_path) or (s.needs_end_frame and _ok(s.end_frame_path))


def _same_scene(a: Shot, b: Shot) -> bool:
    """方案一：接力只在同场景相邻镜之间进行——跨场景边界背景本该变化，
    接力会把上一个场景的画面带进新场景，反而制造断裂。""" 
    return (a.scene_name or "") == (b.scene_name or "")


async def batch_frames(db, t: TaskRecord, params: dict) -> dict:
    """批量首帧（链式）：跳过已有首帧；缺首帧的镜若上一镜已有视频/尾帧，
    自动接力上一镜末帧 img2img 重绘（衔接+人物外观继承），否则独立生成。
    params: episode_id, ipa_weight?, chain?=True"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    use_chain = params.get("chain", True)
    todo = [s for s in shots if not _ok(s.first_frame_path)]
    update_progress(db, t, 0.02, f"批量首帧：待生成 {len(todo)}/{len(shots)} 镜")
    failed, chained, standalone = [], 0, 0
    prev_by_idx = {s.idx: s for s in shots}
    for i, sh in enumerate(todo):
        prev = prev_by_idx.get(sh.idx - 1)
        coro = None
        if (use_chain and prev is not None and _has_chainable_src(prev)
                and prev.idx == sh.idx - 1 and _same_scene(prev, sh)):
            coro = shot_service.chain_shot_frame(db, t, {"shot_id": prev.id})
            label = f"接力首帧 s{sh.idx}"
        if coro is not None:
            err = await _run_step(db, t, label, i, len(todo), coro)
            if err:
                # 接力失败退回独立生成（链断了不阻塞整体）
                err = await _run_step(db, t, f"首帧 s{sh.idx}", i, len(todo),
                                      shot_service.generate_shot_frame(
                                          db, t, {"shot_id": sh.id, "frame_type": "first",
                                                  "ipa_weight": params.get("ipa_weight", 0.7)}))
            else:
                chained += 1
        else:
            standalone += 1
            err = await _run_step(db, t, f"首帧 s{sh.idx}", i, len(todo),
                                  shot_service.generate_shot_frame(
                                      db, t, {"shot_id": sh.id, "frame_type": "first",
                                              "ipa_weight": params.get("ipa_weight", 0.7)}))
        if err:
            failed.append({"shot_idx": sh.idx, "error": err})
    update_progress(db, t, 1.0,
                    f"批量首帧完成：成功 {len(todo) - len(failed)}（接力 {chained}/独立 {standalone}），失败 {len(failed)}")
    return {"total": len(shots), "generated": len(todo) - len(failed),
            "chained": chained, "standalone": standalone,
            "skipped": len(shots) - len(todo), "failed": failed}


async def batch_end_frames(db, t: TaskRecord, params: dict) -> dict:
    """批量尾帧：只处理 needs_end_frame 且缺尾帧文件的镜头。"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    todo = [s for s in shots
            if s.needs_end_frame and not _ok(s.end_frame_path)]
    update_progress(db, t, 0.02, f"批量尾帧：待生成 {len(todo)} 镜")
    failed = []
    for i, sh in enumerate(todo):
        err = await _run_step(db, t, f"尾帧 s{sh.idx}", i, len(todo),
                              shot_service.generate_shot_frame(
                                  db, t, {"shot_id": sh.id, "frame_type": "end",
                                          "ipa_weight": params.get("ipa_weight", 0.7)}))
        if err:
            failed.append({"shot_idx": sh.idx, "error": err})
    update_progress(db, t, 1.0, f"批量尾帧完成：成功 {len(todo) - len(failed)}，失败 {len(failed)}")
    return {"generated": len(todo) - len(failed), "failed": failed}


async def batch_videos(db, t: TaskRecord, params: dict) -> dict:
    """批量视频：有首帧、缺视频的镜头逐个 i2v（needs_end_frame 缺尾帧的先补尾帧）。"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    todo = []
    end_todo = []
    for s in shots:
        if _ok(s.video_path) or not _ok(s.first_frame_path):
            continue
        if s.needs_end_frame and not _ok(s.end_frame_path):
            end_todo.append(s)
        todo.append(s)
    total_steps = len(end_todo) + len(todo)
    update_progress(db, t, 0.02, f"批量视频：补尾帧 {len(end_todo)}，出视频 {len(todo)}")
    failed = []
    step = 0
    for sh in end_todo:
        err = await _run_step(db, t, f"尾帧 s{sh.idx}", step, total_steps,
                              shot_service.generate_shot_frame(
                                  db, t, {"shot_id": sh.id, "frame_type": "end",
                                          "ipa_weight": params.get("ipa_weight", 0.7)}))
        step += 1
        if err:
            failed.append({"shot_idx": sh.idx, "error": err})
    for sh in todo:
        if not _ok(sh.first_frame_path):   # 补尾帧失败不影响视频（单帧 i2v 也能跑）
            continue
        err = await _run_step(db, t, f"视频 s{sh.idx}", step, total_steps,
                              shot_service.generate_shot_video(
                                  db, t, {"shot_id": sh.id,
                                          "duration": params.get("duration"),
                                          "model_key": params.get("model_key")}))
        step += 1
        if err:
            failed.append({"shot_idx": sh.idx, "error": err})
    update_progress(db, t, 1.0, f"批量视频完成：成功 {len(todo) - len(failed)}，失败 {len(failed)}")
    return {"videos": len(todo) - len(failed), "failed": failed}


async def batch_transitions(db, t: TaskRecord, params: dict) -> dict:
    """批量转场镜（方案二，可选开关）：场景切换边界 → 上镜末帧+下镜首帧双帧 i2v 生成
    1-2s 过渡镜。幂等：已有产物跳过；单边缺产物（A 无视频/尾帧、B 无首帧）跳过并记录。
    params: episode_id"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    if not shots:
        raise RuntimeError("本集没有镜头")
    pid = shots[0].project_id
    boundaries = [(a, b) for a, b in zip(shots, shots[1:])
                  if (a.scene_name or "") != (b.scene_name or "")]
    update_progress(db, t, 0.02, f"场景切换边界 {len(boundaries)} 处，检查产物")
    todo, skipped = [], []
    for a, b in boundaries:
        out_path = shot_service.transition_clip_path(pid, a.idx, b.idx)
        if out_path.exists():
            skipped.append({"from": a.idx, "to": b.idx, "reason": "已有转场镜"})
        elif not _has_chainable_src(a):
            skipped.append({"from": a.idx, "to": b.idx, "reason": "上镜缺视频/尾帧"})
        elif not _ok(b.first_frame_path):
            skipped.append({"from": a.idx, "to": b.idx, "reason": "下镜缺首帧"})
        else:
            todo.append((a, b))
    done, failed = [], []
    for i, (a, b) in enumerate(todo):
        err = await _run_step(db, t, f"转场镜 s{a.idx}→s{b.idx}", i, len(todo),
                              shot_service.generate_transition_clip(
                                  db, t, {"from_shot_id": a.id, "to_shot_id": b.id,
                                          "mechanism": (b.transition_in or "")}))
        if err:
            failed.append({"from": a.idx, "to": b.idx, "error": err})
        else:
            done.append({"from": a.idx, "to": b.idx})
    update_progress(db, t, 1.0,
                    f"转场镜完成：生成 {len(done)}，跳过 {len(skipped)}，失败 {len(failed)}")
    return {"boundaries": len(boundaries), "generated": done,
            "skipped": skipped, "failed": failed}


async def rechain_from(db, t: TaskRecord, params: dict) -> dict:
    """向后重链（衔接一致性主入口）：从 from_idx 镜开始，以上一镜现有视频/尾帧为源，
    逐镜 末帧→接力首帧→（缺尾帧先补）→i2v 视频，向后连锁重生成。
    链式依赖：某镜失败即断链停止（后续镜依赖其产物），修复后可从断点再链（闭环）。
    params: episode_id, from_idx(从该镜起重链), duration?"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    start_idx = int(params.get("from_idx") or 1)
    todo = [s for s in shots if s.idx >= start_idx]
    if not todo:
        raise RuntimeError(f"第 {start_idx - 1} 镜已是最后一镜，没有后续镜头可重链"
                           f"（锚点镜本身保持不动）")
    prev_by_idx = {s.idx: s for s in shots}
    prev = prev_by_idx.get(start_idx - 1)
    total_steps = len(todo) * 2
    step = 0
    failed, done = [], []
    for sh in todo:
        # 1) 接力首帧
        if prev is None:
            err = await _run_step(db, t, f"[重链] 首帧 s{sh.idx}", step, total_steps,
                                  shot_service.generate_shot_frame(
                                      db, t, {"shot_id": sh.id, "frame_type": "first",
                                              "ipa_weight": params.get("ipa_weight", 0.7)}))
        else:
            if not _has_chainable_src(prev):
                raise RuntimeError(f"上一镜 #{prev.idx} 没有视频也没有尾帧，无法接力；先补齐它再重链")
            if not _same_scene(prev, sh):
                # 跨场景边界：不接力（接力会把旧场景带进新场景），改独立生成走场景锚图
                err = await _run_step(db, t, f"[重链] 首帧 s{sh.idx}（跨场景独立）", step, total_steps,
                                      shot_service.generate_shot_frame(
                                          db, t, {"shot_id": sh.id, "frame_type": "first",
                                                  "ipa_weight": params.get("ipa_weight", 0.7)}))
            else:
                err = await _run_step(db, t, f"[重链] 接力首帧 s{sh.idx}（承 #{prev.idx}）", step, total_steps,
                                      shot_service.chain_shot_frame(db, t, {"shot_id": prev.id}))
        step += 1
        if err:
            failed.append({"shot_idx": sh.idx, "stage": "first_frame", "error": err})
            break
        # 2) 视频（needs_end_frame 缺尾帧先补）
        if sh.needs_end_frame and not _ok(sh.end_frame_path):
            err2 = await _run_step(db, t, f"[重链] 尾帧 s{sh.idx}", step, total_steps,
                                   shot_service.generate_shot_frame(
                                       db, t, {"shot_id": sh.id, "frame_type": "end",
                                               "ipa_weight": params.get("ipa_weight", 0.7)}))
            if err2:
                failed.append({"shot_idx": sh.idx, "stage": "end_frame", "error": err2})
        step += 1
        err3 = await _run_step(db, t, f"[重链] 视频 s{sh.idx}", step, total_steps,
                               shot_service.generate_shot_video(
                                   db, t, {"shot_id": sh.id, "duration": params.get("duration"),
                                           "model_key": params.get("model_key")}))
        if err3:
            failed.append({"shot_idx": sh.idx, "stage": "video", "error": err3})
            break
        done.append(sh.idx)
        prev = sh   # 链推进：下一镜以本镜新视频为源
    update_progress(db, t, 1.0,
                    f"向后重链完成：重链 {len(done)} 镜{('，断链于 s' + str(failed[0]['shot_idx']) + '，修复后可从该镜再链') if failed else ''}")
    return {"rechained": done, "stopped_at": failed[0]["shot_idx"] if failed else None,
            "failed": failed}


async def full_pipeline(db, t: TaskRecord, params: dict) -> dict:
    """一键全流程：缺的首帧 → 缺的视频 → TTS → 拼接混音烧字幕成片。"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    no_first = [s for s in shots if not _ok(s.first_frame_path)]
    no_video = [s for s in shots if _ok(s.first_frame_path) and not _ok(s.video_path)]
    proj = db.get(Project, shots[0].project_id) if shots else None
    want_bridge = bool(getattr(proj, "transition_bridge", 0)) if proj else False
    steps_total = len(no_first) + len(no_video) + (1 if want_bridge else 0) + 2  # +转场镜?+TTS +合成
    step = 0

    summary = {}
    prev_by_idx = {s.idx: s for s in shots}
    for sh in no_first:
        prev = prev_by_idx.get(sh.idx - 1)
        if (prev is not None and _has_chainable_src(prev) and _same_scene(prev, sh)):
            err = await _run_step(db, t, f"[全流程] 接力首帧 s{sh.idx}", step, steps_total,
                                  shot_service.chain_shot_frame(db, t, {"shot_id": prev.id}))
            if err:
                err = await _run_step(db, t, f"[全流程] 首帧 s{sh.idx}", step, steps_total,
                                      shot_service.generate_shot_frame(
                                          db, t, {"shot_id": sh.id, "frame_type": "first",
                                                  "ipa_weight": params.get("ipa_weight", 0.7)}))
        else:
            err = await _run_step(db, t, f"[全流程] 首帧 s{sh.idx}", step, steps_total,
                                  shot_service.generate_shot_frame(
                                      db, t, {"shot_id": sh.id, "frame_type": "first",
                                              "ipa_weight": params.get("ipa_weight", 0.7)}))
        step += 1
        if err:
            summary.setdefault("failed", []).append({"shot_idx": sh.idx, "error": err})

    for sh in no_video:
        if sh.needs_end_frame and not _ok(sh.end_frame_path):
            # 补尾帧失败不中断全流程（与 batch_videos 一致：单帧 i2v 也能跑）
            err_ef = await _run_step(db, t, f"[全流程] 尾帧 s{sh.idx}", step, steps_total,
                                     shot_service.generate_shot_frame(
                                         db, t, {"shot_id": sh.id, "frame_type": "end",
                                                 "ipa_weight": params.get("ipa_weight", 0.7)}))
            if err_ef:
                summary.setdefault("failed", []).append(
                    {"shot_idx": sh.idx, "stage": "end_frame", "error": err_ef})
        err = await _run_step(db, t, f"[全流程] 视频 s{sh.idx}", step, steps_total,
                              shot_service.generate_shot_video(
                                  db, t, {"shot_id": sh.id,
                                          "duration": params.get("duration"),
                                          "model_key": params.get("model_key")}))
        step += 1
        if err:
            summary.setdefault("failed", []).append({"shot_idx": sh.idx, "error": err})

    if want_bridge:
        update_progress(db, t, step / max(steps_total, 1), "[全流程] 生成转场镜（场景切换边界）")
        try:
            summary["transitions"] = await batch_transitions(db, t, params)
        except Exception as e:
            summary.setdefault("failed", []).append({"stage": "transitions", "error": str(e)[:200]})
        step += 1

    update_progress(db, t, step / max(steps_total, 1), "[全流程] 台词配音（edge-tts）")
    try:
        summary["tts"] = await voice_service.tts_episode(db, t, params)
    except Exception as e:
        summary.setdefault("failed", []).append({"stage": "tts", "error": str(e)[:200]})

    update_progress(db, t, (steps_total - 1) / steps_total, "[全流程] 合成成片")
    try:
        summary["export"] = await asyncio.to_thread(
            voice_service.export_final, db, t, params)
    except Exception as e:
        summary.setdefault("failed", []).append({"stage": "export", "error": str(e)[:200]})

    update_progress(db, t, 1.0, f"[全流程] 完成，失败 {len(summary.get('failed', []))} 项")
    return summary


# ---------- 导出：剪映草稿 / FCPXML ----------

def _seg_duration(p: Path, fallback: float) -> float:
    try:
        return voice_service._ffprobe_duration(p) or fallback
    except Exception:
        return fallback


def export_jianying(db, t: TaskRecord, params: dict) -> dict:
    """剪映草稿（draft_content.json 最小可用版）：视频轨按镜序 + 台词文本轨。"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    segs = [s for s in shots if _ok(s.video_path)]
    if not segs:
        raise RuntimeError("没有可用镜头视频，先去分镜页生成")

    videos, texts, v_segs, t_segs = [], [], [], []
    cursor_us = 0
    for s in segs:
        dur = _seg_duration(Path(s.video_path), float(s.duration or 5))
        dur_us = int(dur * 1_000_000)
        vid = {"id": f"vid_{s.id}", "path": Path(s.video_path).as_posix(),
               "duration": dur_us, "type": "video"}
        videos.append(vid)
        v_segs.append({
            "id": f"seg_v_{s.id}", "material_id": vid["id"],
            "target_timerange": {"start": cursor_us, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
        })
        # 文本轨：按镜内台词平分（带说话人名）
        lines = voice_service._parse_lines(s.dialogue or "")
        if lines:
            slot = dur / len(lines)
            for j, (who, _tone, line) in enumerate(lines):
                start = cursor_us + int(j * slot * 1_000_000)
                # slot 极短（0.2s 以下）时 span 会被减成负数 → 剪映导入报错，钳到 0.1s
                span = int(max(0.1, min(slot - 0.2, 4.0)) * 1_000_000)
                # 字幕只放台词本身，不带说话人名（与烧录字幕口径一致）
                text = line
                texts.append({"id": f"txt_{s.id}_{j}", "text": text,
                              "duration": span})
                t_segs.append({"id": f"seg_t_{s.id}_{j}", "material_id": f"txt_{s.id}_{j}",
                               "target_timerange": {"start": start, "duration": span}})
        cursor_us += dur_us

    draft = {
        "draft_id": f"drama_ep{eid}",
        "duration": cursor_us,
        "fps": 30,
        "canvas": {"width": 1080, "height": 1920},
        "materials": {"videos": videos, "texts": texts},
        "tracks": [
            {"type": "video", "segments": v_segs},
            {"type": "text", "segments": t_segs},
        ],
    }
    out = voice_service._proj_dir(params["project_id"]) / "export" / f"jianying_ep{eid}_draft_content.json"
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
    update_progress(db, t, 1.0, f"剪映草稿导出：{len(segs)} 段 / {cursor_us / 1e6:.1f}s")
    return {"file": str(out), "segments": len(segs), "duration_s": round(cursor_us / 1e6, 1)}


def export_fcpxml(db, t: TaskRecord, params: dict) -> dict:
    """FCPXML 1.8 资源库版：Premiere / DaVinci / FCPX 可导入。"""
    eid = params["episode_id"]
    shots = _collect(db, eid)
    segs = [s for s in shots if _ok(s.video_path)]
    if not segs:
        raise RuntimeError("没有可用镜头视频，先去分镜页生成")

    def ts(sec: float) -> str:
        return f"{int(round(sec * 100_000_000))}/100000000s"

    assets, spine = [], []
    cursor = 0.0
    for s in segs:
        dur = _seg_duration(Path(s.video_path), float(s.duration or 5))
        assets.append(f'  <asset id="a{s.id}" name="shot_{s.idx}" src="file://{Path(s.video_path).as_posix()}"'
                      f' start="0s" duration="{ts(dur)}" hasVideo="1" hasAudio="1" format="fmt"/>')
        spine.append(f'''    <asset-clip ref="a{s.id}" name="s{s.idx}" offset="{ts(cursor)}" start="0s" duration="{ts(dur)}">
      <note>{(s.dialogue or "").strip()[:120]}</note>
    </asset-clip>''')
        cursor += dur

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.8">
  <resources>
    <format id="fmt" frameDuration="1/30s" width="1080" height="1920"/>
{chr(10).join(assets)}
  </resources>
  <library>
    <event name="Drama Studio">
      <project name="ep{eid}">
        <spine>
{chr(10).join(spine)}
        </spine>
      </project>
    </event>
  </library>
</fcpxml>
'''
    out = voice_service._proj_dir(params["project_id"]) / "export" / f"ep{eid}.fcpxml"
    out.write_text(xml, encoding="utf-8")
    update_progress(db, t, 1.0, f"FCPXML 导出：{len(segs)} 段 / {cursor:.1f}s")
    return {"file": str(out), "segments": len(segs), "duration_s": round(cursor, 1)}
