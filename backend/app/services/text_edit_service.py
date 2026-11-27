"""图片文字局部微调（inpaint）：在**已生成的图**上只重画文字所在区域。

设计前提（用户明确要求）：
  · 不再用云端 GPT-Image 2.5 出整图——那样画风/构图/光影全会变，等于重画；
  · 只在原图的文字框内部重绘，框外的纸纹、折痕、朱印、边缘光照一字不动；
  · 全程本地 ComfyUI（Qwen-Image 2.1 + mask 局部重绘），零 token、零云端调用。

实现要点（实测踩过的坑）：
  1. VAEEncodeForInpaint 对 16 通道的 Qwen VAE 不成立——mask 区会被填成灰块、
     采样不生效（第一次试跑整块灰）。正确路子是 VAEEncode 原图 +
     SetLatentNoiseMask(框选 mask) + KSampler denoise≈0.88：
     框外 latent 原样保留，框内加噪重画。
  2. mask 必须是"白=重画、黑=保留"，且要羽化（默认 12px @1024），
     否则接缝是一条硬边。
  3. 提示词写成中文指令式（"把这块的竖排毛笔字写成「青云宗令牌」"），
     实测 Qwen-Image 在框内能把 5 个中文字全写对。
"""
from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy.orm import Session

from ..adapters.comfyui_adapter import ComfyUIAdapter
from ..db import AssetImage, TaskRecord
from ..config import ASSETS_ROOT

NEG = ("blurry text, gibberish characters, garbled lettering, misspelled characters, "
       "extra text, watermark, lowres, deformed")

# 第 2 轮起追加的"擦旧字"指令：模型会保留原有笔画残影（实测「券」字被反复保留、
# 越画越叠），必须先明说擦掉再写，光提高 denoise 不够。
_ERASE_ZH = "；蒙版内原有的字形必须完全擦除，只按上面这几个字重新书写，不得保留任何旧笔画、叠字或残影"
_ERASE_EN = ("; erase the old lettering inside the mask completely before writing, "
             "then draw only the new letters, no ghost strokes or double lettering")

# 缺省文字框（归一化）：按资产类型给"文字最常出现的位置"。
# 刻意避开右下朱印与右侧边框——框压到印章会把印章重画淡（实测）。
DEFAULT_BOX = {"x": 0.335, "y": 0.195, "w": 0.30, "h": 0.545}
DEFAULT_BOX_BY_KIND = {
    # 道具设计图：牌面/券面文字多在主体中部竖向区域（沿用旧默认）
    "prop": DEFAULT_BOX,
    # 场景设计图：文字多在门额/牌匾/招牌，落在画面中上偏中的横块
    "scene": {"x": 0.26, "y": 0.22, "w": 0.48, "h": 0.26},
    # 角色设计图：文字是面板旁的手写标注与底部信息行（通栏窄条，别框到立绘和脸）
    "character": {"x": 0.04, "y": 0.86, "w": 0.92, "h": 0.11},
}


def _default_box_for(kind: str) -> dict:
    return dict(DEFAULT_BOX_BY_KIND.get(kind or "prop", DEFAULT_BOX))


def _clamp_box(box: dict | None, kind: str = "prop") -> dict:
    """归一化框（0-1），越界/太小都收回来——mask 太小等于没重画，太大等于重画整图。"""
    b = _default_box_for(kind)
    for k in ("x", "y", "w", "h"):
        try:
            if box and box.get(k) is not None:
                b[k] = float(box[k])
        except (TypeError, ValueError):
            pass
    b["w"] = max(0.05, min(0.95, b["w"]))
    b["h"] = max(0.05, min(0.95, b["h"]))
    b["x"] = max(0.0, min(1.0 - b["w"], b["x"]))
    b["y"] = max(0.0, min(1.0 - b["h"], b["y"]))
    return b


def make_mask(src: Path, box: dict | None, out_path: Path,
              feather_px: int | None = None) -> Path:
    """按归一化框生成羽化 mask（白=重画区，黑=保留），尺寸与原图一致。"""
    b = _clamp_box(box)
    with Image.open(src) as im:
        W, H = im.size
    box_px = (int(b["x"] * W), int(b["y"] * H),
              int((b["x"] + b["w"]) * W), int((b["y"] + b["h"]) * H))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rectangle(box_px, fill=255)
    if feather_px is None:
        # 羽化按图短边走：768 宽 → 9px，1024 → 12px，羽化过大会把字抹平
        feather_px = max(4, int(min(W, H) / 85))
    m = m.filter(ImageFilter.GaussianBlur(feather_px))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.convert("RGB").save(out_path)
    return out_path


# 按资产类型给"这个字写在哪"的语境补充：模型需要知道载体，否则会把字画成浮空贴图
_KIND_ZH = {
    "prop": "文字写在物件本体表面，随载体弧度与透视贴合",
    "scene": "文字写在门额 / 牌匾 / 招牌 / 墙面标识上，透视与所在平面一致",
    "character": "文字是设计图纸上的手写标注与信息行，小小一行，笔迹与图纸手写风格一致",
}
_KIND_EN = {
    "prop": "the lettering sits on the object surface, following its curvature and perspective",
    "scene": "the lettering is painted on a plaque, signboard or wall sign, aligned to that plane",
    "character": "the lettering is a small hand-written annotation on the design sheet",
}


def build_prompt(text: str, extra: str = "", lang: str = "zh", kind: str = "prop") -> str:
    """局部改字的指令式提示词（中文载体写毛笔/印刷体，英文载体写印刷大写字母）。

    2026-11-28：从"只服务道具牌面"扩到角色设计图标注 / 场景牌匾，并按语言分流——
    之前英文招牌也吃"中文毛笔字"指令，模型会把英文画成伪汉字。
    """
    t = (text or "").strip()
    if lang == "en":
        head = (f'rewrite only the lettering inside the masked area as "{t}", '
                "clean printed capital letters, correct spelling, evenly spaced on one line, "
                "letter by letter legible, " + _KIND_EN.get(kind, _KIND_EN["prop"]) + "; "
                "keep the original surface texture, wear, stains, frame and lighting exactly "
                "as they are, everything outside the mask unchanged, no extra text")
    else:
        head = (f"把画面中文字所在区域的字，改写为「{t}」，"
                "中文毛笔字或印刷体，字形准确、笔画清晰、逐字可读，字距与排版自然；"
                + _KIND_ZH.get(kind, _KIND_ZH["prop"]) + "；"
                "文字所在材质（纸面/牌面/布面/墙面/金属面）的纹理、折痕、做旧痕迹、朱印、"
                "边框与光照保持原样，画面其余部分完全不变，不要新增任何多余文字")
    return f"{head}。{extra}" if extra else head


async def _inpaint_once(comfy, db, task, *, src: Path, src_name: str, mask_path: Path,
                        prompt: str, denoise: float, seed: int, pid: int,
                        entity_id, tag: str) -> Path:
    """单轮：上传原图 → 生成 mask → Qwen 局部重绘 → 返回产物路径。"""
    mask_name = await comfy.upload_image(mask_path, subfolder="drama_studio_mask")
    wf = comfy.load_template("prop_text_inpaint.json")
    wf = comfy.apply_overrides(wf, {
        "LoadImage.image": src_name,
        "LoadImageMask.image": mask_name,
        "KSampler.seed": seed,
        "KSampler.denoise": denoise,
        "positive_text": prompt,
        "negative_text": NEG,
    })
    files = await comfy.run(
        wf,
        filename_prefix=f"drama_studio/p{pid}_text{entity_id if entity_id is not None else ''}"
                        f"{'_' + tag if tag else ''}",
        save_root=Path(ASSETS_ROOT) / str(pid) / "assets",
        timeout=900,
        on_stage=lambda m: print(f"[task {task.id}] {m}"),
    )
    if not files:
        raise RuntimeError("ComfyUI 没有返回产物")
    return Path(files[0])


async def run_text_edit(db: Session, task: TaskRecord, params: dict) -> dict:
    """任务入口：读源图 → 生成 mask → 本地 Qwen 局部重绘 → 落库新版本。

    2026-11-28 增加**自动迭代**（`auto_loop`）：每画完一轮就用本地 OCR 读一遍框内的字，
    与目标文字比对；不过就按"读得最差的那一块"重新框选（面积逐步减小到上一轮的 85% 以内），
    再画一轮，直到读对或用完轮次。判定口径与缩框规则见 `text_judge`。
    """
    import asyncio

    from ..scheduler.queue import update_progress
    from . import text_judge, text_ocr

    src0 = Path(params["source_path"])
    if not src0.exists():
        raise RuntimeError(f"源图不存在：{src0}")
    pid = int(params["project_id"])
    text = (params.get("text") or "").strip()
    if not text:
        raise RuntimeError("没填要写的文字内容")
    kind = params.get("kind") or "prop"
    # 资产 kind 是 base_look / scene / prop → 归一到提示词语境的三类
    kind_tag = ("character" if kind == "base_look" else kind) if kind in (
        "base_look", "scene", "prop") else "prop"
    lang = (params.get("lang") or "").strip().lower()
    if lang not in ("zh", "en"):
        from ..text_prop import detect_lang
        lang = detect_lang(text)

    auto = bool(params.get("auto_loop", True))
    max_rounds = int(params.get("max_rounds") or 3)
    max_rounds = max(1, min(6, max_rounds))
    box0 = _clamp_box(params.get("box"), kind_tag)
    base_denoise = float(params.get("denoise") or 0.88)
    base_denoise = max(0.55, min(0.96, base_denoise))  # <0.55 字写不实，>0.98 框内纹理全重画
    base_seed = int(params.get("seed") or random.randint(0, 2 ** 31 - 1))
    prompt = build_prompt(text, params.get("extra_prompt") or "", lang=lang, kind=kind_tag)

    with Image.open(src0) as im:
        img_w, img_h = im.size

    comfy = ComfyUIAdapter()
    src = src0
    src_name = await comfy.upload_image(src0)
    cur_box = box0
    rounds: list[dict] = []
    final_file: Path | None = None
    final_box = box0
    final_denoise = base_denoise
    final_prompt = prompt
    ok = False
    all_outs: list[Path] = []
    # 落库的不是"最后一轮"而是"最好的一轮"：Qwen 对某些字有顽固惯性（「牌」反复画成
    # 券/黎），第 3 轮常常是「券」+ 叠笔残影，比第 1 轮还糊。按 (命中率, OCR 置信度)
    # 选最佳，避免越迭代越差。
    best = {"key": (-1.0, -1.0), "file": None, "box": box0,
            "denoise": base_denoise, "prompt": prompt}
    stagnant = 0
    col_box = dict(box0)      # 最近一次的"整段框"，逐字修复时以它为基准定位错字
    single_char: str | None = None   # 非空表示本轮只重写这一个字

    for r in range(1, max_rounds + 1):
        mask_path = (Path(ASSETS_ROOT) / str(pid) / "masks"
                     / f"text_mask_{int(datetime.now().timestamp() * 1000)}_r{r}.png")
        make_mask(src, cur_box, mask_path)
        denoise = max(0.55, min(0.95, base_denoise + 0.05 * (r - 1)))
        if single_char:
            # 单字轮：提示词只描述这一个字，避免模型在窄框里再猜整串
            prompt_r = build_prompt(single_char, params.get("extra_prompt") or "",
                                    lang=lang, kind=kind_tag)
        else:
            prompt_r = prompt
        if r > 1:
            prompt_r = prompt_r + (_ERASE_EN if lang == "en" else _ERASE_ZH)
        stage = (f"第 {r}/{max_rounds} 轮局部重绘（{kind_tag} 框 "
                 f"{cur_box['w'] * 100:.0f}%×{cur_box['h'] * 100:.0f}%，{lang}）"
                 if max_rounds > 1 or auto else "本地 Qwen-Image 局部重绘中（只动文字框）")
        update_progress(db, task, 0.05 + 0.9 * (r - 1) / max_rounds, stage)
        out = await _inpaint_once(
            comfy, db, task, src=src, src_name=src_name, mask_path=mask_path,
            prompt=prompt_r, denoise=denoise, seed=(base_seed + (r - 1) * 7919) % (2 ** 31 - 1),
            pid=pid, entity_id=params.get("entity_id"),
            tag=f"r{r}" if max_rounds > 1 else "",
        )
        all_outs.append(out)

        verdict = None
        items = None
        if auto:
            items = await asyncio.to_thread(text_ocr.read_region, out, cur_box)
            verdict = text_judge.judge(text, items, lang=lang,
                                       min_hit=params.get("min_hit"))
            verdict["round"] = r
            verdict["box"] = dict(cur_box)
            rounds.append(verdict)
            key = (float(verdict["hit"]), float(verdict["best_score"]))
            if key > best["key"]:
                best = {"key": key, "file": out, "box": dict(cur_box),
                        "denoise": denoise, "prompt": prompt_r, "round": r}
                stagnant = 0
            else:
                stagnant += 1
            update_progress(db, task, 0.05 + 0.9 * r / max_rounds,
                            f"第 {r}/{max_rounds} 轮完成：命中 {verdict['hit'] * 100:.0f}%"
                            f"（{verdict['reason']}）{'，已达标' if verdict['ok'] else ''}")
            ok = ok or verdict["ok"]
        else:
            best = {"key": (0.0, 0.0), "file": out, "box": dict(cur_box),
                    "denoise": denoise, "prompt": prompt_r}

        final_file, final_box, final_denoise, final_prompt = (
            best["file"], best["box"], best["denoise"], best["prompt"])
        stop_reason = None
        if (auto and len(rounds) >= 2
                and not rounds[-1].get("observed") and not rounds[-2].get("observed")):
            stop_reason = "连续两轮框内读不出字（强光/极小字/笔迹太草），停止迭代"
        elif auto and stagnant >= 2:
            stop_reason = "连续两轮命中率不再提升（模型对这几个字有顽固惯性），停止迭代"
        if ok or not auto or r >= max_rounds or stop_reason:
            if stop_reason:
                update_progress(db, task, 0.95, stop_reason)
            break

        # 重新框选：目标字占满框时不缩（缩了会切字留残影），只换种子/强度重试；
        # 目标字只占框一部分时，才收缩到目标所在的那一块。
        nxt = text_judge.focus_box(cur_box, items, text, lang, img_w, img_h)
        # 能定位到"具体写错了哪个字"且整串 ≥3 个字时，改为**只重写这一个字**：框收窄到
        # 该字所在的一段（约整段高度的 1/n），提示词也只给这一个字。整段重写常出现
        # "改对一个、又写坏另一个"（实测「青云宗令牌」第 1 轮「牌」对了、「青」却成「胃」）。
        bad = text_judge.locate_bad(items, text, lang) if auto else None
        if bad and bad["n"] >= 3:
            single_char = bad["char"]
            nxt = text_judge.char_box(col_box, bad["k"], bad["n"],
                                      vertical=col_box["h"] >= col_box["w"])
        else:
            single_char = None
            col_box = dict(nxt)
        same = text_judge.same_box(cur_box, nxt)
        if same and stagnant >= 1:
            update_progress(db, task, 0.95, "框已到最小范围且命中率无变化，停止迭代（建议换词或人工微调）")
            break
        # 下一轮仍从**原始图**重画（不是在上轮产物上再叠一遍）：叠着改会把上轮的错字/
        # 残笔一起留在框内，越迭代越糊（实测第 3 轮出「牌」+「券」底的叠字）。
        cur_box = nxt

    await comfy.free_memory()

    # 中间轮产物不入库，物理删除（否则 assets 目录会堆一堆废版本）
    for f in all_outs:
        if f != final_file:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass

    saved = []
    if final_file is not None:
        img = None
        # 重绘可能返回多张（ComfyUI 批量），第一张之外的一并删掉
        meta_rounds = [{"round": v.get("round"), "box": v.get("box"), "hit": v.get("hit"),
                        "extra": v.get("extra"), "score": v.get("best_score"),
                        "observed": v.get("observed"), "reason": v.get("reason")}
                       for v in rounds]
        img = AssetImage(
            project_id=pid,
            character_id=params.get("character_id"),
            kind=kind,
            file_path=str(final_file),
            prompt=final_prompt,
            meta_json=json.dumps({
                "model_key": "qwen_image_2.1",
                "workflow": "prop_text_inpaint.json",
                "op": "text_inpaint",
                "parent_asset_id": params.get("asset_id"),
                "source_path": str(src0),
                "entity_type": params.get("entity_type", "prop"),
                "entity_id": params.get("entity_id"),
                "text": text,
                "lang": lang,
                "surface_kind": kind_tag,
                "box": final_box,
                "denoise": final_denoise,
                "seed": base_seed,
                "local_only": True,
                "auto_iter": {
                    "enabled": bool(auto),
                    "rounds_done": len(rounds),
                    "max_rounds": max_rounds,
                    "final_ok": bool(ok),
                    "best_round": best.get("round") if auto else None,
                    "detail": meta_rounds,
                },
            }, ensure_ascii=False),
        )
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": kind})

    if not rounds:
        done_text = "局部改字完成"
    elif ok:
        done_text = f"局部改字完成（自动迭代达标，取第 {best.get('round')} 轮结果）"
    else:
        done_text = (f"局部改字完成（{len(rounds)} 轮均未达标，取最佳的第 {best.get('round')} 轮，"
                     f"框 {final_box['w']*100:.0f}%×{final_box['h']*100:.0f}%，建议人工微调）")
    update_progress(db, task, 1.0, done_text)
    return {"assets": saved, "model_key": "qwen_image_2.1", "local_only": True,
            "lang": lang, "surface_kind": kind_tag, "auto_iter": {
                "enabled": bool(auto), "rounds": rounds, "final_ok": bool(ok),
                "best_round": best.get("round") if auto else None,
                "final_box": final_box, "ocr_available": text_ocr.available()}}
