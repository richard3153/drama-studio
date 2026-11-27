"""ComfyUI 进程守护：进程崩溃/被系统杀掉后，后端自己把它拉起来。

为什么要有这个（2026-11-26 现场）：ComfyUI 在 8G 卡上跑 H3 长采样时被
`access violation reading 0x…`（comfy_aimdo host_buffer.truncate）打死，
进程表里 python 数归零、8188 拒绝连接；后端所有后续任务（首帧/IPAdapter、
视频）全部报 "All connection attempts failed" 并中断，用户看到的只有
「已中断」，根因（ComfyUI 根本不在）没人知道。
原方案靠计划任务 ComfyUI-Watchdog 每 2 分钟跑 run_comfyui.vbs，但该 vbs 的
`sh.Run` 在本机起不来子进程（boot 日志 22:22 之后从未更新），等于形同虚设。

策略：
- 每 interval 秒看一次 8188 是否可连（秒级开销，不碰 GPU）；
- 不可连时先数 ComfyUI 进程：>0 说明正在启动（冷启动实测 7-14 分钟），等它；
- 进程也没有 → 查冷却时间（启动日志文件时间戳），冷却期内不重复拉起，
  冷却结束仍不在才 Popen 启动，并追加到 backend/_comfy_boot.log；
- 所有状态写 data/.comfy_supervisor.json，供 /api/health 与前端展示。
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from ..config import (BASE_DIR, COMFYUI_DIR, COMFYUI_PYTHON,
                      COMFYUI_URL, DATA_DIR, EXTRA_MODEL_PATHS)

STATE_FILE = DATA_DIR / ".comfy_supervisor.json"
BOOT_COOLDOWN = 900.0          # 冷启动 7-14 分钟，冷却期内不重复拉起
_PWSH = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_GROUP = 0x00000200
_BOOT_LOG = BASE_DIR / "_comfy_boot.log"
_BOOT_ERR = BASE_DIR / "_comfy_boot_err.log"

# 内存态：最近一次判定结果与时间，供 /api/health 快照
_state = {"comfy": "unknown", "checked_at": 0.0, "restarts": 0}


def _host_port() -> tuple[str, int]:
    u = urlparse(COMFYUI_URL)
    return u.hostname or "127.0.0.1", u.port or 8188


def port_open(timeout: float = 8.0) -> bool:
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def listen_present() -> bool:
    """8188 是否仍处于 LISTEN（有进程占着端口）。

    意义：WAN 采样时 ComfyUI 主循环被占满，accept/HTTP 会暂时不回包，
    port_open 就会判"不通"；但只要端口还在 LISTEN，就说明进程活着、
    只是忙——绝不能当"进程不在"去重复拉起（会把采样打断、history 截断）。
    """
    _, port = _host_port()
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=_CREATE_NO_WINDOW)
    except Exception:
        return False
    return any(f":{port} " in line and "LISTENING" in line.upper()
               for line in (out.stdout or "").splitlines())


def proc_count() -> int:
    """数 ComfyUI 的 python 进程；-1 表示查不到（此时按"可能在启动"处理，不乱拉）。"""
    cmd = ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' }).Count")
    try:
        out = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-Command", cmd],
                             capture_output=True, text=True, timeout=30,
                             creationflags=_CREATE_NO_WINDOW)
        return int((out.stdout or "").strip() or 0)
    except Exception:
        return -1


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(**kv):
    st = _read_state()
    st.update(kv)
    try:
        STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _boot_age() -> float:
    """距上一次启动尝试 / 日志最后写入的时间（秒）。"""
    last = max(float(_read_state().get("last_start") or 0),
               _BOOT_LOG.stat().st_mtime if _BOOT_LOG.exists() else 0.0)
    return time.time() - last if last else 1e9


def _launch_spec() -> tuple[Path, Path, list[str]]:
    """拉起前按后台配置现算启动参数（cwd, python, args）。

    为什么不在导入期算：config.COMPYUI_LAUNCH_ARGS 是进程启动时求值的常量，
    面板把注意力后端改成 sage 之后，旧实现即便点了「重启 ComfyUI」，
    新进程仍以旧参数（pytorch）起来——配置写着 sage 但没生效，还看不出原因。
    现在每次拉起都读 settings：改完注意力/安装目录/extra_paths，点重启即生效。
    """
    try:
        from .. import settings as _S
        srv = _S.load().get("server") or {}
        acc = _S.load().get("accel") or {}
    except Exception:
        srv, acc = {}, {}
    comfy_dir = Path(str(srv.get("comfyui_dir") or COMFYUI_DIR))
    python = Path(str(COMFYUI_PYTHON))
    if comfy_dir != Path(COMFYUI_DIR):      # 面板换了安装目录 → python 跟着换
        python = comfy_dir / "ComfyUI" / ".venv" / "Scripts" / "python.exe"
    extra = str(srv.get("extra_model_paths") or EXTRA_MODEL_PATHS)
    args = ["-u", "-s", r"ComfyUI\main.py", "--enable-manager",
            "--extra-model-paths-config", extra,
            "--user-directory", str(comfy_dir / "ComfyUI" / "user")]
    if str(acc.get("attention") or "").lower() == "sage":
        args.append("--use-sage-attention")
    return comfy_dir, python, args


def _start() -> bool:
    comfy_dir, python, args = _launch_spec()
    if not python.exists():
        print(f"[comfy-supervisor] 启动失败：找不到 {python}")
        return False
    _BOOT_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        fout = open(_BOOT_LOG, "ab")
        ferr = open(_BOOT_ERR, "ab")
        p = subprocess.Popen(
            [str(python), *args],
            cwd=str(comfy_dir), stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW | _CREATE_NEW_GROUP)
        _write_state(last_start=time.time(), pid=p.pid)
        print(f"[comfy-supervisor] ComfyUI 进程不在，已拉起 pid={p.pid}（冷启动约 7-14 分钟）"
              f" args={' '.join(args)}")
        return True
    except Exception as e:
        print(f"[comfy-supervisor] 拉起失败：{e}")
        return False


def ensure(force: bool = False) -> str:
    """一次巡检：up / starting / cooldown / started / start-failed。"""
    if port_open():
        _state.update(comfy="up", checked_at=time.time())
        return "up"
    if listen_present():
        # 端口还在监听：进程活着，只是在采样/加载中不回包，等它，别再拉一个。
        _state.update(comfy="starting", checked_at=time.time())
        return "starting"
    n = proc_count()
    if n > 0:
        _state.update(comfy="starting", checked_at=time.time())
        return "starting"
    if n < 0:
        _state.update(comfy="unknown", checked_at=time.time())
        return "unknown"
    age = _boot_age()
    if not force and age < BOOT_COOLDOWN:
        _state.update(comfy="cooldown", checked_at=time.time())
        return "cooldown"
    ok = _start()
    _state.update(comfy="starting" if ok else "down", checked_at=time.time(),
                  restarts=int(_state.get("restarts", 0)) + (1 if ok else 0))
    return "started" if ok else "start-failed"


def _comfy_pids() -> list[int]:
    cmd = ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
           "Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' } | "
           "Select-Object -ExpandProperty ProcessId) -join ','")
    try:
        out = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-Command", cmd],
                             capture_output=True, text=True, timeout=30,
                             creationflags=_CREATE_NO_WINDOW)
        return [int(x) for x in (out.stdout or "").strip().split(",") if x.strip().isdigit()]
    except Exception:
        return []


def restart() -> bool:
    """按最新启动参数重启 ComfyUI（改注意力后端/路径后面板用；调用方负责先判队列空闲）。"""
    pids = _comfy_pids()
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, timeout=15,
                           creationflags=_CREATE_NO_WINDOW)
        except Exception:
            pass
    time.sleep(3)
    _write_state(last_start=0)
    ok = _start()
    _state.update(comfy="starting" if ok else "down", checked_at=time.time())
    return ok


def snapshot() -> dict:
    return {
        "state": _state["comfy"],
        "checked_at": _state["checked_at"],
        "restarts": _state["restarts"],
        "boot_age_s": round(_boot_age(), 1) if port_open() is False else 0,
    }


async def supervisor_loop(interval: float = 60.0):
    """后端启动即挂载：ComfyUI 掉了就自己续上，不再依赖 (已失效的) vbs 计划任务。"""
    await asyncio.sleep(5)
    while True:
        try:
            r = await asyncio.to_thread(ensure)
            if r == "started":
                print("[comfy-supervisor] 已重启 ComfyUI，端口就绪前任务请稍后再点「继续」")
        except Exception as e:
            print(f"[comfy-supervisor] 巡检异常：{e}")
        await asyncio.sleep(interval)
