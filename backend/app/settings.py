"""后台配置：可视化面板的配置源（data/settings.yaml）。

设计取舍：
- 这份文件是"运行时配置"，不进 git（.gitignore 已覆盖 backend/data/*）；
- 模型选择不直接改写 models.yaml（那份带大量中文注释、记录着实测数据，
  yaml.dump 会把注释全丢掉），而是由 pick_model / shot_service 在选档前读这里的覆盖值；
- 服务地址与路径在进程启动最早期写进 os.environ，config.py 用 get(..., 默认值)
  读，所以改完"重启后端生效"；ComfyUI 启动参数（注意力后端）改完要重启 ComfyUI。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.yaml"

# 默认值按本机现状给出：与 config.py / models.yaml 的默认保持一致，
# 这样面板首次打开时显示的就是"当前真实在跑的值"，不会因为缺项显示成空。
DEFAULTS: dict[str, Any] = {
    "server": {
        "comfyui_url": "http://127.0.0.1:8188",
        "comfyui_dir": r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI",
        "extra_model_paths": r"D:\Comfy-Desktop\extra_paths.yaml",
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "qwen3.5:4b",
    },
    "models": {
        "default_image": "img_qwen_image",
        "ref_image_photo": "img_realvisxl",
        "ref_image_anime": "img_animaginexl",
        "default_video": "vid_wan21_480p",
        "ref_video": "vid_h3_turbo",
        "talk_video": "vid_talk_infinitetalk",
    },
    "lora": {
        "dir": r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI\models\loras",
        "video_step_lora": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
        "enable_video_step_lora": True,
    },
    "accel": {
        "attention": "pytorch",   # pytorch | sage
        # 只在"关掉步数蒸馏 LoRA"时才用的采样步数：蒸馏 LoRA 旁路后 4 步必糊，
        # 抬到 20 步（16-24 区间实测可用）。开着蒸馏时工作流自带 4 步，这个值不参与。
        "video_steps": 20,
    },
}

# 允许写入的键（白名单；避免前端误传把 yaml 写坏）
_ALLOWED = {
    "server": {"comfyui_url", "comfyui_dir", "extra_model_paths", "ollama_url", "ollama_model"},
    "models": {"default_image", "ref_image_photo", "ref_image_anime",
               "default_video", "ref_video", "talk_video"},
    "lora": {"dir", "video_step_lora", "enable_video_step_lora"},
    "accel": {"attention", "video_steps"},
}


def _deep_merge(base: dict, patch: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))   # 深拷贝
    if SETTINGS_FILE.exists():
        try:
            raw = yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                cfg = _deep_merge(cfg, raw)
        except Exception:
            pass
    return cfg


def _to_bool(v) -> bool:
    """把面板/接口可能传的 "false"/"0"/"" 也当假——bool("false") 是 True，
    不处理会把"关掉蒸馏 LoRA"这种开关点成开的。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() not in ("", "0", "false", "no", "off", "none")


def save(patch: dict) -> dict:
    """合并写入（白名单过滤 + 类型纠正），返回保存后的完整配置。"""
    cur = load()
    clean: dict[str, dict] = {}
    for grp, vals in (patch or {}).items():
        if grp not in _ALLOWED or not isinstance(vals, dict):
            continue
        for k, v in vals.items():
            if k not in _ALLOWED[grp]:
                continue
            if isinstance(DEFAULTS[grp][k], bool):
                v = _to_bool(v)
            elif isinstance(DEFAULTS[grp][k], int) and not isinstance(v, str):
                try:
                    v = int(v)
                except Exception:
                    continue
            elif isinstance(DEFAULTS[grp][k], int) and isinstance(v, str):
                try:
                    v = int(v.strip())
                except Exception:
                    continue
            elif grp == "models" and not isinstance(v, str):
                # 模型档必须是"档位名"字符串：传 dict/list 时 str() 会存成
                # "{'x': 1}" 这种垃圾键，pick_model 直接找不到档、整条链路崩。
                continue
            elif not isinstance(v, str):
                v = str(v)
            if grp == "accel" and k == "video_steps":
                v = max(1, min(80, int(v)))          # 采样步数兜底夹到可用区间
            if grp == "accel" and k == "attention":
                v = str(v).strip().lower()
                if v not in ("pytorch", "sage"):
                    continue                          # 只认这两个，别把启动参数写歪
            clean.setdefault(grp, {})[k] = v.strip() if isinstance(v, str) else v
    cfg = _deep_merge(cur, clean)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        "# Drama Studio 运行时配置（前端「后台配置」面板读写；不进 git）\n"
        + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return cfg


def get(group: str, key: str, default=None):
    return (load().get(group) or {}).get(key, default)


def model_overrides() -> dict:
    """role → model_key 覆盖（pick_model 用）。

    只覆盖"主链路"角色：portrait/scene/prop/image_edit 统一跟 default_image 走，
    video 跟 default_video 走。参考链路（首帧锁脸/转场双帧/口型）是显式点名，
    不经过这里，避免互相串味。
    """
    m = load().get("models") or {}
    img = (m.get("default_image") or "").strip()
    vid = (m.get("default_video") or "").strip()
    out = {}
    if img:
        for role in ("portrait", "scene", "prop", "image_edit", "grid9"):
            out[role] = img
    if vid:
        out["video"] = vid
    return out


def bootstrap() -> None:
    """进程最早期把服务地址/路径写进环境变量（config.py 之后读到的就是新值）。

    只用 setdefault：外部显式设置的 DRAMA_* 环境变量优先级更高，不被面板覆盖。
    """
    srv = load().get("server") or {}
    mapping = {
        "DRAMA_COMFYUI_URL": srv.get("comfyui_url"),
        "DRAMA_COMFYUI_DIR": srv.get("comfyui_dir"),
        "DRAMA_EXTRA_MODEL_PATHS": srv.get("extra_model_paths"),
        "DRAMA_OLLAMA_URL": srv.get("ollama_url"),
    }
    for k, v in mapping.items():
        if v:
            os.environ.setdefault(k, str(v))
    acc = load().get("accel") or {}
    if str(acc.get("attention") or "").lower() == "sage":
        os.environ.setdefault("DRAMA_USE_SAGE_ATTENTION", "1")
