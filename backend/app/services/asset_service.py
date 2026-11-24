"""P2 资产服务：资产图生成 + 初图 10% 微调（img2img）、活人感负面约束、低显存串行。"""
import json
import random
from datetime import datetime
from pathlib import Path

from ..adapters.comfyui_adapter import ComfyUIAdapter
from ..config import ASSETS_ROOT
from ..db import AssetImage, Project
from ..scheduler.vram import pick_model, registry
from ..style_presets import (ANTI_OVER_RENDER_NEG, CHAR_SHEET_NEG, CHAR_VIEW_NEG,
                             QUALITY_SUFFIX, QUALITY_SUFFIX_ENV, character_view_prompt,
                             style_family)

# 角色/场景/道具的“中性”正向尾巴（不再堆砌 masterpiece/8k，规避过度渲染）
POSITIVE_SUFFIX = {
    "portrait": ("character reference sheet, full body, clean plain background, "
                 "consistent art style"),
    "scene": ("concept art, environment design, consistent art style, unoccupied space"),
    "prop": ("item reference sheet, single object, clean plain background"),
}
NEGATIVE = (
    "nsfw, lowres, bad anatomy, bad hands, text, watermark, "
    "signature, jpeg artifacts, worst quality, blurry, deformed, " + ANTI_OVER_RENDER_NEG
)

# 场景/道具专用负向：人形排除必须走负向（SDXL 对正向 "no people" 几乎无响应，
# 反而会因 people 这个词把人拽进画面）。这一层是 #84「废弃矿洞出少女」的根治手段。
NEGATIVE_ENV = NEGATIVE + (
    ", people, person, persons, human, human figure, man, woman, child, girl, boy, "
    "crowd, group of people, character, characters, anime girl, anime boy, "
    "face, facial closeup, portrait, headshot, silhouette, back view, "
    "hands, arms, legs, body, standing figure, sitting figure, cosplay"
)

KIND_BY_ROLE = {"portrait": "base_look", "scene": "scene", "prop": "prop"}

# family → role → 模板名
FAMILY_TEMPLATE = {
    "sdxl": {
        "portrait": "char_portrait.json",
        "scene": "scene_sdxl.json",
        "prop": "prop_sdxl.json",
    },
    "qwen_image": {
        "portrait": "char_portrait_qwen.json",
        "scene": "char_portrait_qwen.json",
        "prop": "char_portrait_qwen.json",
    },
    "flux2_klein": {
        "portrait": "char_portrait_flux2.json",
        "scene": "char_portrait_flux2.json",
        "prop": "char_portrait_flux2.json",
    },
}

# 微调（img2img）默认幅度 10%（denoise 0.10-0.15 区间）
DEFAULT_POLISH_STRENGTH = 0.12

# 真实参考图重绘默认幅度：0.5 是平衡点——太低（<0.35）等于没换风格，
# 太高（>0.65）结构和文字会漂（键帽/屏幕文字必须靠低 denoise 保真）
REF_REDRAW_STRENGTH = 0.5

# 超分放大模型（本地 ComfyUI upscale_models 目录实测在位）：
# 写实照片族用 Nomos8k（照片级细节），动漫/插画族用 4x-ESRGAN，通用兜底 RealESRGAN_x2plus
UPSCALE_MODEL_REAL = "4xNomos8kSCHAT-L.pth"
UPSCALE_MODEL_ANIME = "4x-ESRGAN.pth"
UPSCALE_MODEL_DEFAULT = "RealESRGAN_x2plus.pth"
UPSCALE_MAX_SIDE = 4096          # 4x 后超限则 PIL 缩回，防前端加载/存储爆炸


def _refs_root(project_id: int) -> Path:
    return ASSETS_ROOT / str(project_id) / "refs"


async def download_reference(project_id: int, image_url: str) -> Path:
    """下载外部参考图到项目 refs 目录，返回本地路径。"""
    import httpx
    root = _refs_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    suffix = ".png"
    lower = image_url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if lower.endswith(ext):
            suffix = ext
            break
    dest = root / f"ref{random.randint(0, 2**31 - 1)}{suffix}"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.get(image_url)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


async def generate_from_reference(db, task, params: dict) -> dict:
    """真实参考图 → img2img 风格化重绘。

    适用：现实中真实存在的物品/场景（便利店、保温瓶、键盘、手机……）。
    文生图画这类实物会文字乱码、结构失真（实测键帽全乱）；真实照片做底图
    走 denoise≈0.5 的 img2img，结构、比例、屏幕/键帽文字全部保真，只换画风。
    params: {project_id, entity_type, entity_id, image_url | ref_path, strength?, base_prompt?}
    """
    from ..scheduler.queue import update_progress
    from ..db import Scene, Prop

    etype = params["entity_type"]
    eid = params["entity_id"]
    # 提示词来源：显式传入 > 实体当前 base_prompt（风格锁+主体已在里面）
    prompt = params.get("base_prompt")
    if not prompt:
        row = (db.get(Prop, eid) if etype == "prop" else db.get(Scene, eid))
        if row is None:
            raise RuntimeError("实体不存在")
        prompt = row.base_prompt
    if not prompt:
        raise RuntimeError("实体提示词为空，先完成资产生成")

    # 参考图：URL 下载或本地路径
    ref_path = params.get("ref_path")
    if not ref_path and params.get("image_url"):
        ref_path = await download_reference(params["project_id"], params["image_url"])
    if not ref_path or not Path(ref_path).exists():
        raise RuntimeError("缺少参考图（image_url 或 ref_path）")

    strength = float(params.get("strength") or REF_REDRAW_STRENGTH)
    # 重绘统一走 SDXL 写实低档（refine_img2img.json 是 CheckpointLoaderSimple 模板）
    model_key, model = await pick_model("scene", "low", allowed_families={"sdxl"})
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    comfy = ComfyUIAdapter()
    wf = comfy.load_template("refine_img2img.json")
    update_progress(db, task, 0.1, "上传参考图")
    img_name = await comfy.upload_image(str(ref_path))
    try:
        from PIL import Image
        with Image.open(ref_path) as im:
            sw, sh = im.size
    except Exception:
        sw, sh = 1024, 1024
    overrides = {
        "CheckpointLoaderSimple.ckpt_name": model["weight"],
        "LoadImage.image": img_name,
        "ImageScale.width": sw,
        "ImageScale.height": sh,
        "ImageScale.crop": "disabled",
        "positive_text": prompt,
        "negative_text": NEGATIVE,
        "KSampler.denoise": strength,
        "KSampler.seed": random.randint(0, 2**31 - 1),
    }
    wf = comfy.apply_overrides(wf, overrides)
    update_progress(db, task, 0.3, f"参考图重绘（denoise {strength}，{model_key}）")
    save_root = ASSETS_ROOT / str(params["project_id"]) / "assets"
    files = await comfy.run(wf,
                            filename_prefix=f"drama_studio/p{params['project_id']}_{etype}{eid}_ref",
                            save_root=save_root, timeout=900)
    await comfy.free_memory()

    saved = []
    role_kind = {"scene": "scene", "prop": "prop"}.get(etype, "base_look")
    for f in files:
        img = AssetImage(project_id=params["project_id"], kind=role_kind,
                         character_id=None, file_path=str(f),
                         prompt=prompt,
                         meta_json=json.dumps({"entity_type": etype, "entity_id": eid,
                                               "from_reference": str(ref_path),
                                               "redraw_strength": strength,
                                               "model_key": model_key},
                                              ensure_ascii=False))
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": role_kind})
    return {"assets": saved, "reference": str(ref_path), "strength": strength}


async def upscale_asset(db, task, params: dict) -> dict:
    """对已生成图片做像素级超分放大（不动构图/身份/seed，纯后处理）。

    零 UNet：只加载 <320MB 的 ESRGAN 系放大器，显存占用 <1GB，几秒出图，
    与扩散生成完全串行也不抢档位。params: {asset_id, model?, project_id?}
    """
    from ..scheduler.queue import update_progress
    from PIL import Image

    src = db.get(AssetImage, params["asset_id"])
    if not src or not Path(src.file_path).exists():
        raise RuntimeError("源图不存在")

    # 按源图风格族选放大器（可显式覆盖）
    model_name = params.get("model")
    if not model_name:
        fam = "realistic"
        try:
            meta = json.loads(src.meta_json or "{}")
            preset = meta.get("style_preset") or ""
            if not preset:
                project = db.get(Project, src.project_id)
                preset = project.style_preset if project else ""
            from ..style_presets import style_family
            fam = style_family(preset)
        except Exception:
            pass
        model_name = (UPSCALE_MODEL_REAL if fam == "realistic"
                      else UPSCALE_MODEL_ANIME if fam == "anime"
                      else UPSCALE_MODEL_DEFAULT)
    task.model_key = f"upscale:{model_name}"
    task.vram_gb = 1

    comfy = ComfyUIAdapter()
    wf = comfy.load_template("upscale_image.json")
    update_progress(db, task, 0.1, "上传源图到 ComfyUI")
    img_name = await comfy.upload_image(src.file_path)
    wf = comfy.apply_overrides(wf, {
        "LoadImage.image": img_name,
        "UpscaleModelLoader.model_name": model_name,
    })
    update_progress(db, task, 0.4, f"超分放大（{model_name}，无 UNet 纯后处理）")
    save_root = ASSETS_ROOT / str(src.project_id) / "assets"
    files = await comfy.run(wf,
                            filename_prefix=f"drama_studio/p{src.project_id}_upscale{src.id}",
                            save_root=save_root, timeout=300)
    await comfy.free_memory()

    saved = []
    # 衍生图必须继承源图的实体归属（entity_type/entity_id），
    # 否则 /projects/{pid}/assets 的 img_by_entity 归不到资产下 → 前端历史版本永远看不到
    _src_meta = json.loads(src.meta_json or "{}")
    _ety = _src_meta.get("entity_type") or ("character" if src.character_id else None)
    _eid = _src_meta.get("entity_id") or src.character_id
    for f in files:
        # 4x 后超限缩回（LANCZOS，画质损失可忽略），防前端/存储问题
        try:
            with Image.open(f) as im:
                w, h = im.size
            if max(w, h) > UPSCALE_MAX_SIDE:
                scale = UPSCALE_MAX_SIDE / max(w, h)
                with Image.open(f) as im:
                    im.resize((int(w * scale), int(h * scale)), Image.LANCZOS).save(f)
        except Exception:
            pass
        img = AssetImage(project_id=src.project_id, kind=src.kind,
                         character_id=src.character_id, file_path=str(f),
                         prompt=src.prompt,
                         meta_json=json.dumps({"upscaled_from": src.id,
                                               "upscale_model": model_name,
                                               **({"entity_type": _ety, "entity_id": _eid} if _ety else {})},
                                              ensure_ascii=False))
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": img.kind})
    return {"assets": saved, "upscale_model": model_name}


def _supported_families(role: str) -> frozenset:
    """该 role 实际有工作流模板的家族集合（按磁盘文件校验，不是按声明）。

    pick_model 据此排除"注册了但模板文件缺失"的家族（实测 flux2_klein 被兜底选中后
    加载 char_portrait_flux2.json 直接报"模板不存在"，整批任务失败）。
    """
    wf_dir = Path(__file__).resolve().parent.parent.parent / "workflows"
    ok = set()
    for fam, m in FAMILY_TEMPLATE.items():
        name = m.get(role)
        if name and (wf_dir / name).exists():
            ok.add(fam)
    return frozenset(ok)


async def generate_asset(db, task, params: dict) -> dict:
    """通用资产图生成。params: {project_id, role, base_prompt, entity_id, entity_type,
    prefer_tier?, width?, height?}"""
    reg = registry()
    role = params["role"]                     # portrait / scene / prop
    # 【守卫】空提示词直接拒绝：拆解自动发现的角色（槽位未补全、base_prompt 空）
    # 一旦放行，提示词只剩风格填充词 → SDXL 出乱线稿垃圾图，浪费 GPU 且误导用户。
    if not (params.get("base_prompt") or "").strip():
        raise RuntimeError(
            f"资产的主体提示词为空（拆解自动发现的候选，槽位尚未补全）："
            f"{params.get('entity_type', '')} #{params.get('entity_id', '')}。"
            f"请先在资产编辑器补全槽位/描述后再渲染")
    if role == "portrait":
        # 【硬性要求 2026-11-21】角色资产必须三视图 sheet 版式：入口统一归一，
        # 单人立绘(single)/角色板(board)通道废弃——任何调用方传什么都以 sheet 出图。
        params["portrait_mode"] = "sheet"
        # 三视图 sheet = 宽横幅版式（16:9，1344x768）。
        # 兜底修正：此前默认 832x1216 竖版，横幅三视图会被压成竖条崩版。
        w = int(params.get("width") or 1344)
        h = int(params.get("height") or 768)
    else:
        # 场景/道具跟随项目全局画幅（角色定妆照固定竖版不参与）
        from ..aspect import asset_dims
        project = db.get(Project, params.get("project_id"))
        w, h = asset_dims(project.aspect_ratio if project else None)

    # 自动选档已由 models.yaml defaults.default_models 承担（2026-11-24 全局拍板：
    # 图片=Qwen-Image）。此前的 photo→flux2 / 3d→qwen 自动规则删除——用户显式传
    # model_key/prefer_tier 时仍走各自通道（如首帧 IPA 锁 SDXL、微调锁 low）。
    prefer = params.get("prefer_tier")

    model_key, model = await pick_model(role, prefer,
                                        params.get("model_key"),
                                        style_family=style_family(params.get("style_preset") or ""),
                                        allowed_families=_supported_families(role))
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    family = model.get("family", "sdxl")
    template_name = FAMILY_TEMPLATE.get(family, {}).get(role)
    if not template_name:
        raise RuntimeError(f"family={family} role={role} 尚无模板")

    comfy = ComfyUIAdapter()
    wf = comfy.load_template(template_name)
    suffix = POSITIVE_SUFFIX[role]
    # 场景/道具：负向提示换 NEGATIVE_ENV（人形硬排除），画质尾词换无皮肤/发丝版
    negative = NEGATIVE_ENV if role in ("scene", "prop") else NEGATIVE
    quality = QUALITY_SUFFIX_ENV if role in ("scene", "prop") else QUALITY_SUFFIX
    if role == "portrait":
        # 【硬性要求】sheet 三视图专属词块：信息栏需画姓名/身高小字，全局 NEG 的裸
        # "text" 会压制它 → 剔除裸 text（watermark/乱码拦截仍在 NEG 与 CHAR_SHEET_NEG 里）。
        neg_parts = [p.strip() for p in NEGATIVE.split(",") if p.strip() and p.strip() != "text"]
        negative = ", ".join(neg_parts) + f", {CHAR_SHEET_NEG}"
    from .model_vocab import image_dialect   # 模型方言词库（family 已知 → 直接取该族母语词）
    prompt = ", ".join(x for x in (params['base_prompt'], suffix, quality,
                                   image_dialect(family)) if x)
    overrides = {
        "positive_text": prompt,
        "negative_text": negative,
        "EmptyLatentImage.width": w,
        "EmptyLatentImage.height": h,
        "KSampler.seed": random.randint(0, 2**31 - 1),
    }
    # 一次渲染任务 = 一个 render_session（compose 多图归一次计数；前端「渲染 N 次」按此去重）
    render_session = f"{task.id}-{int(datetime.now().timestamp() * 1000)}"
    if family == "sdxl":
        overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
    elif family == "flux2_klein":
        overrides["UNETLoader.unet_name"] = model["weight"]
    wf = comfy.apply_overrides(wf, overrides)

    def on_stage(msg):
        print(f"[task {task.id}] {msg}")

    from ..scheduler.queue import update_progress
    update_progress(db, task, 0.05, f"选档 {model_key}（{model['vram_gb']}GB）")
    save_root = ASSETS_ROOT / str(params["project_id"]) / "assets"
    files = await comfy.run(wf, filename_prefix=f"drama_studio/p{params['project_id']}_{role}{params.get('entity_id','')}",
                            save_root=save_root, timeout=600, on_stage=on_stage)
    update_progress(db, task, 0.9, "生成完成，写入资产库")
    await comfy.free_memory()

    kind = KIND_BY_ROLE[role]
    saved = []
    for f in files:
        img = AssetImage(project_id=params["project_id"], kind=kind,
                         character_id=params.get("entity_id") if role == "portrait" else None,
                         file_path=str(f), prompt=prompt,
                         meta_json=json.dumps({"model_key": model_key, "workflow": template_name,
                                               "entity_type": params.get("entity_type", ""),
                                               "entity_id": params.get("entity_id"),
                                               "render_session": render_session},
                                              ensure_ascii=False))
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": kind})

    # 三视图 sheet（一次成图）自动裁 face_ref：新版式左半就是面部特写，
    # 裁左半区域即可作为 IPA 锁脸参考（此前 sheet 模式不产 face_ref，锁脸链路断）。
    if role == "portrait" and params.get("portrait_mode") == "sheet" and files:
        try:
            from PIL import Image
            eid = params.get("entity_id")
            with Image.open(files[0]) as im:
                iw, ih = im.size
                face = im.convert("RGB").crop((0, 0, int(iw * 0.5), int(ih * 0.85)))
            face_path = Path(files[0]).with_name(
                f"p{params['project_id']}_portrait{eid}_sheetface_{files[0].stem.rsplit('_', 1)[-1]}.png")
            face_path.parent.mkdir(parents=True, exist_ok=True)
            face.save(face_path)
            fimg = AssetImage(project_id=params["project_id"], kind="face_ref",
                              character_id=eid, file_path=str(face_path), prompt=prompt,
                              meta_json=json.dumps({"source": "sheet_crop", "sheet": str(files[0]),
                                                    "entity_type": "character", "entity_id": eid},
                                                   ensure_ascii=False))
            db.add(fimg)
            db.commit()
            saved.append({"asset_id": fimg.id, "file_path": str(face_path), "kind": "face_ref"})
        except Exception as e:   # 裁脸失败不阻断主产物
            print(f"[sheet face_ref] crop failed: {e}")

    # 初图 10% 微调（自动，分级生效：角色板/三视图 OFF，场景/道具/单人立绘 ON）
    if params.get("auto_polish") and not (
            role == "portrait" and params.get("portrait_mode") in ("sheet", "board")):
        import asyncio
        from ..scheduler.queue import create_task
        for item in saved:
            p = {"project_id": params["project_id"], "asset_id": item["asset_id"],
                 "role": role, "entity_type": params.get("entity_type", ""),
                 "entity_id": params.get("entity_id"),
                 "style_preset": params.get("style_preset", ""),
                 "strength": DEFAULT_POLISH_STRENGTH}
            t = create_task(db, "polish", p)
            asyncio.create_task(_run_polish_task(t.id))
    return {"assets": saved, "model_key": model_key}


async def _run_polish_task(task_id: int):
    """自动微调任务执行器：独立会话 + heavy 锁（与生图串行，低显存安全）。"""
    import asyncio
    from ..db import SessionLocal, TaskRecord
    from ..scheduler import queue as task_queue

    await asyncio.sleep(0.2)
    with SessionLocal() as db:
        t = db.get(TaskRecord, task_id)
        if not t or t.status != "pending":
            return
        params = json.loads(t.params_json or "{}")
        await task_queue.run_task(db, t, lambda: refine_asset(db, t, params))


def _cjk_font(size: int = 40):
    """信息栏中文字体：按平台探测 truetype，全部失败回退默认（中文会变方框但不出错）。"""
    from PIL import ImageFont
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
              "/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


async def generate_portrait_composed(db, task, params: dict) -> dict:
    """方案 A：正/侧/背三次单视角出图（同 seed）→ PIL 横向拼三视图 + 面部参考裁切。
    params: project_id/entity_id/slots/style_preset/prefer_tier/model_key/lifelike/lifelike_full"""
    from ..scheduler.queue import update_progress
    import asyncio

    slots = params.get("slots") or {}
    preset = params.get("style_preset") or "anime_2d"
    lifelike = params.get("lifelike", True)
    full = params.get("lifelike_full", False)

    model_key, model = await pick_model("portrait", params.get("prefer_tier"),
                                        params.get("model_key"),
                                        style_family=style_family(preset),
                                        allowed_families=_supported_families("portrait"))
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]
    family = model.get("family", "sdxl")
    template_name = FAMILY_TEMPLATE.get(family, {}).get("portrait", "char_portrait.json")

    seed = random.randint(0, 2**31 - 1)      # 三视角同 seed，尽量稳住五官
    w, h = (640, 960)
    comfy = ComfyUIAdapter()
    save_root = ASSETS_ROOT / str(params["project_id"]) / "assets"
    files: list[Path] = []

    for i, view in enumerate(("front", "side", "back")):
        update_progress(db, task, 0.05 + i * 0.25, f"生成 {view} 视角（{i + 1}/3）")
        prompt = character_view_prompt(slots, preset, view, lifelike, full)
        overrides = {
            "positive_text": prompt,
            "negative_text": f"{NEGATIVE}, {CHAR_VIEW_NEG}",
            "EmptyLatentImage.width": w,
            "EmptyLatentImage.height": h,
            "KSampler.seed": seed,
        }
        if family == "sdxl":
            overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
        elif family == "flux2_klein":
            overrides["UNETLoader.unet_name"] = model["weight"]
        elif family == "qwen_image":
            # Qwen-Image 走 UNETLoader（diffusion_models 目录）；weight 随注册表可换
            overrides["UNETLoader.unet_name"] = model["weight"]

        wf = comfy.load_template(template_name)

        if view in ("side", "back") and files:
            # 决策 A1 扩展（2026-11-21）：side/back 都不再独立采样——同 seed 独立采样
            # 实测服装漂移（赵总 front 西装 vs side 夹克）。以正面图为条件 img2img 重绘：
            # 服装/身份/体型随条件图锁定，姿势转向靠视角 prompt + denoise 驱动。
            # 参数实测：denoise 0.55 + cfg 5.0 会把写实背面漂成插画 → 0.5/2.5。
            view_cn = "侧面" if view == "side" else "背面"
            update_progress(db, task, 0.3 if view == "side" else 0.55,
                            f"{view_cn}视角：以正面图为条件 img2img 重绘")
            wf = comfy.load_template("refine_img2img.json")
            front_name = await comfy.upload_image(str(files[0]))
            overrides = {
                "positive_text": prompt,
                "negative_text": f"{NEGATIVE}, {CHAR_VIEW_NEG}",
                "LoadImage.image": front_name,
                "ImageScale.width": w,
                "ImageScale.height": h,
                "ImageScale.crop": "center",
                # 实测：denoise 0.55 + cfg 5.0 会把写实背面漂成插画（林小满/赵总两例）
                # → 0.5 保背面服从度，cfg 2.5 贴 RealVisXL 写实推荐区间压风格漂移。
                "KSampler.seed": seed,
                "KSampler.denoise": 0.5,
                "KSampler.steps": 28,
                "KSampler.cfg": 2.5,
            }
            if family == "sdxl":
                overrides["CheckpointLoaderSimple.ckpt_name"] = model["weight"]
            else:
                # refine_img2img.json 是 SDXL img2img 模板（CheckpointLoaderSimple），
                # 主模型为 flux2 等非 sdxl 家族时，背面 img2img 临时换 sdxl 低档执行
                skey, smodel = await pick_model("portrait", "low", allowed_families={"sdxl"})
                overrides["CheckpointLoaderSimple.ckpt_name"] = smodel["weight"]
            wf = comfy.apply_overrides(wf, overrides)
            out = await comfy.run(wf,
                                  filename_prefix=f"drama_studio/p{params['project_id']}_view_{view}",
                                  save_root=save_root, timeout=600)
            files.extend(out)
            continue

        wf = comfy.apply_overrides(wf, overrides)
        out = await comfy.run(wf,
                              filename_prefix=f"drama_studio/p{params['project_id']}_view_{view}",
                              save_root=save_root, timeout=600)
        files.extend(out)

    update_progress(db, task, 0.85, "PIL 拼版：左面部特写 + 三视图 + 底部信息栏")
    from PIL import Image, ImageDraw
    panels = [Image.open(f).convert("RGB") for f in files[:3]]
    # 定稿版式（与 CHAR_SHEET_SPEC 一致，程序保证不崩版）：
    # 左半 = 面部特写放大；右半 = 正/侧/背三视图并排；底部 = 信息栏（角色名·国家形象 + 配色色块）
    PH = 864                                   # 主体区高
    pw = int(PH * 2 / 3)                       # 单视图面板宽（2:3 出图比例）
    panels = [p.resize((pw, PH), Image.LANCZOS) for p in panels]
    strip_h = 96
    W, H = pw * 4, PH + strip_h
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    # 左半：正面图上部中央裁切 → cover 放大填满左区
    front = panels[0]
    fw, fh = front.size
    face = front.crop((int(fw * 0.25), 0, int(fw * 0.75), int(fh * 0.42)))
    scale = max(pw / face.width, PH / face.height)
    face = face.resize((max(int(face.width * scale), pw) + 1,
                        max(int(face.height * scale), PH) + 1), Image.LANCZOS)
    fx, fy = (face.width - pw) // 2, (face.height - PH) // 2
    sheet.paste(face.crop((fx, fy, fx + pw, fy + PH)), (0, 0))
    # 右半：三视图从左到右（正/侧/背）
    for i, p in enumerate(panels):
        sheet.paste(p, (pw + i * pw, 0))
    # 底部信息栏：角色名 · 国家形象（中文）+ 服装主色色块
    draw = ImageDraw.Draw(sheet)
    name = params.get("entity_name") or ""
    eth_label = ""
    eth_v = (slots.get("ethnicity") or "").strip().lower()
    if eth_v:
        from ..style_presets import ETHNICITY_PRESETS
        eth_label = ETHNICITY_PRESETS.get(eth_v, (eth_v, ""))[0]
    label = " · ".join(x for x in (name, eth_label) if x)
    draw.text((16, PH + 28), label, fill=(40, 40, 40), font=_cjk_font(40))
    # 色块：从正面图下半（服装区）取平均色 + 明暗两个变体
    base = front.crop((0, int(fh * 0.55), fw, fh)).resize((1, 1)).getpixel((0, 0))[:3]
    lighter = tuple(min(255, c + 45) for c in base)
    darker = tuple(max(0, c - 45) for c in base)
    sx = W - 200
    for c in (base, lighter, darker):
        draw.rectangle((sx, PH + 24, sx + 48, PH + 72), fill=c, outline=(210, 210, 210))
        sx += 56
    # 实测坑：输出文件名曾是固定 sheet_composed.png/face_ref.png —— 多角色共用
    # 同一物理文件互相覆盖（后生成的角色覆盖先前的，且旧 AssetImage 行指向的
    # 内容悄然变化）。文件名必须带角色 id + seed 唯一化。
    eid = params.get("entity_id")
    sheet_path = (ASSETS_ROOT / str(params["project_id"]) / "assets"
                  / f"p{params['project_id']}_portrait{eid}_sheet_{seed}.png")
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(sheet_path)

    # 面部参考：从正面图裁上部中央区域
    front = panels[0]
    fw, fh = front.size
    face = front.crop((int(fw * 0.28), 0, int(fw * 0.72), int(fh * 0.32)))
    face_path = sheet_path.with_name(f"p{params['project_id']}_portrait{eid}_face_{seed}.png")
    face.save(face_path)

    update_progress(db, task, 0.95, "写入资产库")
    await comfy.free_memory()
    saved = []
    for path, kind in ((sheet_path, "base_look"), (face_path, "face_ref")):
        img = AssetImage(project_id=params["project_id"], kind=kind,
                         character_id=eid, file_path=str(path),
                         prompt=character_view_prompt(slots, preset, "front", lifelike, full),
                         meta_json=json.dumps({"compose": "A", "views": ["front", "side", "back"],
                                               "entity_type": "character", "entity_id": eid,
                                               "seed": seed, "model_key": model_key},
                                              ensure_ascii=False))
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": kind})

    if params.get("auto_polish"):
        # 决策 3：三视图/角色板默认不自动微调（怕改坏版式与五官），仅保留手动「✨微调10%」
        pass
    return {"assets": saved, "model_key": model_key, "compose": "A"}


async def refine_asset(db, task, params: dict) -> dict:
    """初图 → img2img 低幅度微调（默认 denoise 0.12），修复塑料感/增加自然质感。"""
    from ..scheduler.queue import update_progress
    src = db.get(AssetImage, params["asset_id"])
    if not src:
        raise RuntimeError("源图不存在")
    strength = float(params.get("strength") or DEFAULT_POLISH_STRENGTH)
    role = params.get("role", "portrait")

    # 微调统一走 SDXL 低档模型（潜空间一致、显存最省），按风格族选底模。
    # refine_img2img.json 是 SDXL img2img 模板，必须锁死 sdxl 族：
    # 实测 flux2_klein 源图的 polish 把 flux2 权重塞进 CheckpointLoaderSimple → 400
    preset = params.get("style_preset") or ""
    if not preset:
        project = db.get(Project, src.project_id)
        preset = project.style_preset if project else ""
    model_key, model = await pick_model("portrait", "low",
                                        style_family=style_family(preset),
                                        allowed_families={"sdxl"})
    task.model_key = model_key
    task.vram_gb = model["vram_gb"]

    comfy = ComfyUIAdapter()
    wf = comfy.load_template("refine_img2img.json")
    update_progress(db, task, 0.1, "上传初图到 ComfyUI")
    img_name = await comfy.upload_image(src.file_path)
    base_prompt = src.prompt.split(", character reference sheet")[0]
    try:
        from PIL import Image
        with Image.open(src.file_path) as im:
            sw, sh = im.size
    except Exception:
        sw, sh = 832, 1216
    overrides = {
        "CheckpointLoaderSimple.ckpt_name": model["weight"],
        "LoadImage.image": img_name,
        "ImageScale.width": sw,          # 微调保持原图尺寸，不裁不加边
        "ImageScale.height": sh,
        "ImageScale.crop": "disabled",
        "positive_text": f"{base_prompt}, subtle natural texture, film-like grain, "
                         f"unretouched detail, keep composition and identity unchanged",
        "negative_text": NEGATIVE,
        "KSampler.denoise": strength,
        "KSampler.seed": random.randint(0, 2**31 - 1),
    }
    wf = comfy.apply_overrides(wf, overrides)
    update_progress(db, task, 0.3, f"img2img 微调（denoise {strength}）")
    save_root = ASSETS_ROOT / str(src.project_id) / "assets"
    files = await comfy.run(wf,
                            filename_prefix=f"drama_studio/p{src.project_id}_refine{src.id}",
                            save_root=save_root, timeout=600)
    await comfy.free_memory()

    saved = []
    # 衍生图必须继承源图的实体归属（同 upscale：否则历史版本归不到资产下）
    _src_meta = json.loads(src.meta_json or "{}")
    _ety = _src_meta.get("entity_type") or ("character" if src.character_id else None)
    _eid = _src_meta.get("entity_id") or src.character_id
    for f in files:
        img = AssetImage(project_id=src.project_id, kind=src.kind,
                         character_id=src.character_id, file_path=str(f),
                         prompt=src.prompt,
                         meta_json=json.dumps({"polish_strength": strength,
                                               "refined_from": src.id,
                                               "model_key": model_key,
                                               **({"entity_type": _ety, "entity_id": _eid} if _ety else {})},
                                              ensure_ascii=False))
        db.add(img)
        db.commit()
        db.refresh(img)
        saved.append({"asset_id": img.id, "file_path": img.file_path, "kind": img.kind})
    return {"assets": saved, "strength": strength}


async def generate_portrait(db, task, params: dict) -> dict:
    """兼容 M1 接口：角色定妆照。"""
    params = dict(params)
    params["role"] = "portrait"
    params.setdefault("entity_type", "character")
    params["entity_id"] = params.get("character_id") or params.get("entity_id")
    return await generate_asset(db, task, params)


def _scene_iso_image(db, project_id: int, scene_id: int) -> str | None:
    """找场景名下最新的 iso 45° 布局图（meta.iso_layout 或提示词含 isometric）。"""
    from sqlalchemy import select as _select
    from ..db import AssetImage as _AI
    rows = db.scalars(_select(_AI).where(
        _AI.project_id == project_id,
        _AI.kind == "scene").order_by(_AI.id.desc())).all()
    for r in rows:
        try:
            meta = json.loads(r.meta_json or "{}")
        except Exception:
            meta = {}
        if meta.get("entity_id") != scene_id:
            continue
        if not Path(r.file_path).exists():
            continue
        if bool(meta.get("iso_layout")) or "isometric" in (r.prompt or "").lower():
            return r.file_path
    return None


async def auto_scene_anchors(db, task, params: dict) -> dict:
    """一键补齐场景锚图（缩略图法落地）。

    对项目每个场景：已有锚图→跳过；已有 iso 布局图→直接设锚；
    两者皆无→生成 45° 等距剖面布局全景图（iso diorama，完整空间结构）
    并设为 Scene.anchor_path。生成复用 generate_asset 渲染链路（kind=scene 入库）。
    """
    from sqlalchemy import select
    from ..db import Scene
    from ..scheduler.queue import update_progress
    from ..style_presets import assemble_scene_prompt

    pid = params["project_id"]
    project = db.get(Project, pid)
    preset = (project.style_preset if project else "") or "anime_2d"
    lifelike = bool(project.lifelike) if project else True
    scenes = db.scalars(select(Scene).where(Scene.project_id == pid)).all()
    anchored, skipped = [], []
    total = len(scenes)
    for i, sc in enumerate(scenes):
        update_progress(db, task, 0.05 + 0.9 * i / max(total, 1),
                        f"场景 {i + 1}/{total}：{sc.name}")
        if sc.anchor_path and Path(sc.anchor_path).exists():
            skipped.append(sc.name)
            continue
        iso = _scene_iso_image(db, pid, sc.id)
        if not iso:
            # 生成 45° iso 布局全景图（与资产页 iso_layout 出图同一提示词结构）
            slots = json.loads(sc.prompt_json or "{}")
            base = (assemble_scene_prompt(slots, preset, lifelike,
                                          fallback_subject=sc.name)
                    if slots else (sc.base_prompt or sc.name))
            iso_prompt = (
                "isometric cutaway diorama, 45-degree elevated dollhouse view of the complete space, "
                "entire layout visible in one frame, walls, furniture and prop placement clearly arranged, "
                f"miniature 3D model style, soft studio lighting, plain dark background. Scene: {base}")
            await generate_asset(db, task, {
                "project_id": pid, "role": "scene", "entity_type": "scene",
                "entity_id": sc.id, "base_prompt": iso_prompt,
                "style_preset": preset})
            iso = _scene_iso_image(db, pid, sc.id)
        if iso:
            sc.anchor_path = iso
            db.commit()
            anchored.append(sc.name)
        else:
            skipped.append(sc.name)
    update_progress(db, task, 1.0,
                    f"场景锚图完成：{len(anchored)} 个设锚，{len(skipped)} 个已有/跳过")
    return {"anchored": anchored, "skipped": skipped}
