"""显存感知选档：读 models.yaml + ComfyUI /system_stats，挑能跑的最高质量档。"""
import functools

import httpx
import yaml

from ..config import COMFYUI_URL, MODELS_YAML


def load_registry() -> dict:
    with open(MODELS_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=8)
def _registry_cached(mtime: float) -> dict:
    return load_registry()


def registry() -> dict:
    return load_registry()


async def comfy_free_vram_gb() -> float:
    """经 ComfyUI 查询空闲显存（比 nvidia-smi 更贴近 torch 实际可用量）。"""
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{COMFYUI_URL}/system_stats")
        r.raise_for_status()
        return r.json()["devices"][0]["vram_free"] / 1024**3


async def pick_model(role: str, prefer_tier: str | None = None,
                     model_key: str | None = None,
                     style_family: str | None = None,
                     allowed_families: set | frozenset | None = None) -> tuple[str, dict]:
    """按 role 选模型。
    - 显式 model_key：用户手动指定，直接使用（不做显存判断，调度器串行兜底）
    - style_family：风格族（photo/anime/3d/paint），风格锁与底模强绑定（避免写实风格落到动漫底模）
    - prefer_tier：指定档位（若该档位模型存在）
    - allowed_families：只在该集合内选（用于排除"没有对应工作流模板"的家族，
      避免选中后加载模板直接报错——实测 flux2_klein 选中但 char_portrait_flux2.json 不存在）
    - 默认：显存足够者中质量档最高；全都放不下则取最小显存者
    返回 (model_key, model_info)。"""
    reg = registry()
    candidates = {k: v for k, v in reg["models"].items() if role in v.get("role", [])}
    if not candidates:
        raise RuntimeError(f"registry 中没有 role={role} 的模型")

    if model_key:
        if model_key not in candidates:
            raise RuntimeError(f"模型 {model_key} 不支持 role={role}")
        return model_key, candidates[model_key]

    # 全局底模（defaults.default_models，2026-11-24 拍板：图片=Qwen-Image / 视频=MiniMax H3）：
    # 未显式指定 model_key 且未指定 prefer_tier 时直取。辅助链路（首帧 IPA/宫格/微调）
    # 显式传 prefer_tier="low" 走 SDXL，不受此表影响；显式 prefer_tier 视为用户点名档位。
    default_key = (reg.get("defaults", {}).get("default_models") or {}).get(role)
    if not prefer_tier and default_key and default_key in candidates:
        return default_key, candidates[default_key]

    if allowed_families:
        supported = {k: v for k, v in candidates.items()
                     if v.get("family") in allowed_families}
        if supported:
            candidates = supported

    if style_family:
        styled = {k: v for k, v in candidates.items()
                  if style_family in (v.get("styles") or [])}
        if styled:
            candidates = styled


    free = await comfy_free_vram_gb()
    margin = reg.get("scheduler", {}).get("vram_safety_margin_gb", 0.5)
    usable = free - margin

    tier_rank = {"low": 0, "mid": 1, "high": 2}
    fits = {k: v for k, v in candidates.items() if v["vram_gb"] <= usable}
    if prefer_tier:
        tier_models = {k: v for k, v in candidates.items()
                       if v.get("tier") == prefer_tier}
        if tier_models:
            fits = tier_models
    if fits:
        key = max(fits, key=lambda k: tier_rank.get(fits[k].get("tier", "low"), 0))
        return key, fits[key]
    # 全都放不下：显存最省者（由调度器等待/卸载后重试）
    key = min(candidates, key=lambda k: candidates[k]["vram_gb"])
    return key, candidates[key]
