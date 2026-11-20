"""全局配置：路径、服务地址。

全部支持环境变量覆盖，默认值按 Windows + ComfyUI Desktop 布局给出；
其他机器只需设置 DRAMA_COMFYUI_INPUT_DIR / DRAMA_FFMPEG（或把 ffmpeg 放进 PATH）。
"""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # backend/
BACKEND_DIR = BASE_DIR
DATA_DIR = BASE_DIR / "data"
WORKFLOW_DIR = BASE_DIR / "workflows"
DB_PATH = DATA_DIR / "drama_studio.sqlite3"
MODELS_YAML = DATA_DIR / "models.yaml"

COMFYUI_URL = os.environ.get("DRAMA_COMFYUI_URL", "http://127.0.0.1:8188")
# ComfyUI input 共享目录（LoadAudio 音频直写 fallback 用；与启动参数 --input-directory 一致）
COMFYUI_INPUT_DIR = os.environ.get(
    "DRAMA_COMFYUI_INPUT_DIR",
    r"D:\Comfy-Desktop\ComfyUI-Shared\input")
OLLAMA_URL = os.environ.get("DRAMA_OLLAMA_URL", "http://127.0.0.1:11434")

# ffmpeg：优先环境变量 → PATH → ComfyUI Desktop 自带那份（视频续写提末帧/拼接用）
_FFMPEG_FALLBACK = Path(r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
                        r"\custom_nodes\video2dlssnr\bin\ffmpeg.exe")
_ffmpeg = os.environ.get("DRAMA_FFMPEG")
FFMPEG = Path(_ffmpeg) if _ffmpeg else (
    Path(shutil.which("ffmpeg")) if shutil.which("ffmpeg")
    else _FFMPEG_FALLBACK)

# 项目资产根目录
ASSETS_ROOT = DATA_DIR / "projects"

DATA_DIR.mkdir(exist_ok=True)
ASSETS_ROOT.mkdir(exist_ok=True)
