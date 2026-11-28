"""成片音频分轨编排（BGM / 场景音 / 动作音 / 台词四轨）。

存储：`data/projects/<pid>/audio_mix/ep<eid>.json`（不进 git，随项目目录走）
{
  "bgm":  {"ref": "<音效库 id 或绝对路径>", "volume": 0.22, "fade_in": 1.0, "fade_out": 2.0},
  "shots": {"3": {"ref": "<音效库 id>", "volume": 0.6, "offset": 0.0}}
}
台词轨不在这里——它由配音模块按镜头台词自动排布。这里只管三条"贴片轨"：
BGM 铺底（整集循环、结尾淡出）、每镜动作音（贴镜头起点）、以及可选的场景环境音（同样按镜挂）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
PROJECTS = DATA / "projects"


def _path(pid: int, eid: int) -> Path:
    return PROJECTS / str(pid) / "audio_mix" / f"ep{eid}.json"


def load(pid: int, eid: int) -> dict:
    p = _path(pid, eid)
    if not p.exists():
        return {"bgm": {}, "shots": {}}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        # 坏文件（历史非原子写被强杀 / 手工改坏）：不能静默当空配置，留证据再重建
        import shutil, time as _t
        bak = p.with_name(f"{p.name}.corrupt-{int(_t.time())}")
        try:
            shutil.copy2(p, bak)
        except Exception:
            pass
        print(f"[audio_mix] {p} 解析失败（{e}），已备份到 {bak.name}，按空配置继续", flush=True)
        return {"bgm": {}, "shots": {}}
    if not isinstance(d, dict):
        return {"bgm": {}, "shots": {}}
    d.setdefault("bgm", {})
    d.setdefault("shots", {})
    return d


def save(pid: int, eid: int, cfg: dict) -> dict:
    cfg = {"bgm": cfg.get("bgm") or {}, "shots": cfg.get("shots") or {}}
    p = _path(pid, eid)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 原子写：先写 .tmp 再 os.replace。直接覆盖原文件时，若进程在「截断→写入」之间被强杀
    # （重启后端、抓取脚本被 kill 等），会留下 0 字节/全 \x00 的坏文件，编排配置静默丢失。
    # tmp 名带 pid+线程号：两次并发 PUT（BGM 与贴片音）写同一个 .json.tmp 会互相截断。
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, ensure_ascii=False, indent=1))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return cfg


def set_bgm(pid: int, eid: int, ref: str, volume: float | None = 0.22,
            fade_in: float | None = None, fade_out: float | None = None) -> dict:
    """改 BGM。volume/fade 传 None 表示「沿用已保存的值」。

    前端只调音量时不会带 fade 字段，若这里无脑取默认值，每拖一次滑杆就把之前设好的
    淡入淡出重置回 0.8/2.0（配置静默被冲掉）。
    """
    cfg = load(pid, eid)
    old = cfg.get("bgm") or {}
    cfg["bgm"] = {
        "ref": ref or "",
        "volume": old.get("volume", 0.22) if volume is None else volume,
        "fade_in": old.get("fade_in", 0.8) if fade_in is None else fade_in,
        "fade_out": old.get("fade_out", 2.0) if fade_out is None else fade_out,
    }
    return save(pid, eid, cfg)


def set_shot(pid: int, eid: int, idx: int, ref: str, volume: float | None = 0.6,
             offset: float | None = None) -> dict:
    cfg = load(pid, eid)
    shots = cfg["shots"]
    if not ref:
        shots.pop(str(idx), None)
    else:
        old = shots.get(str(idx)) or {}
        shots[str(idx)] = {
            "ref": ref,
            "volume": old.get("volume", 0.6) if volume is None else volume,
            "offset": old.get("offset", 0.0) if offset is None else offset,
        }
    return save(pid, eid, cfg)


def summary(pid: int, eid: int) -> dict:
    """给前端用的摘要：带上解析后的文件名/是否存在，避免前端自己拼路径。"""
    from . import sfx_library as sfx
    cfg = load(pid, eid)
    bgm = cfg.get("bgm") or {}
    bgm_path = sfx.resolve(bgm.get("ref")) if bgm.get("ref") else None
    shots = []
    for k, v in (cfg.get("shots") or {}).items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue                      # 坏 key（手工改坏/旧版本残留）不能让 GET 直接 500
        p = sfx.resolve(v.get("ref"))
        shots.append({"idx": idx, "ref": v.get("ref"), "volume": v.get("volume"),
                      "offset": v.get("offset", 0),
                      "name": (sfx.find(v.get("ref")) or {}).get("name") or (Path(p).name if p else ""),
                      "ok": bool(p)})
    shots.sort(key=lambda x: x["idx"])
    bgm_name = ""
    if bgm.get("ref"):
        bgm_name = (sfx.find(bgm.get("ref")) or {}).get("name") or (Path(bgm_path).name if bgm_path else "")
    return {
        "bgm": dict(bgm, ok=bool(bgm_path), name=bgm_name),
        "shots": shots,
        "file": str(_path(pid, eid)),
    }
