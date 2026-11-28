"""音色源（Voice Source）本地配置：data/voice_sources.yaml。

为什么单独一个文件（而不是塞进 settings.yaml）：
- 音色清单是"列表 + 每个条目的元数据（性别 / provider / voice id）"，settings.yaml 的
  白名单保存逻辑只按标量处理，塞进去会把条目 str() 成一坨垃圾；
- 这份文件要能被面板"逐条增删"，独立成文更好读好改，也不进 git（backend/data/* 已忽略）。

两级 provider：
- 全局 `provider`：edge（默认，走 edge-tts 在线免费接口）| local_http（走本机/自建 TTS 服务）；
- 条目 `provider`：edge | local，覆盖全局（内置 14 个 edge 音色永远走 edge，不受全局切换影响）。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FILE = DATA_DIR / "voice_sources.yaml"

# 内置清单（2026-11-21 用 edge_tts.list_voices() 实测的中文音色全集 14 个；
# edge-tts 免费接口里 Xiaojian/Xiaoxuan/Yunfeng/Yunye 等并不存在，已剔除）
BUILTIN_GROUPS = [
    {"group": "普通话女声", "items": [
        {"key": "xiaoxiao", "label": "晓晓 · 温暖通用（女）", "voice": "zh-CN-XiaoxiaoNeural", "gender": "f"},
        {"key": "xiaoyi",   "label": "晓伊 · 年轻少女感（女）", "voice": "zh-CN-XiaoyiNeural", "gender": "f"},
    ]},
    {"group": "普通话男声", "items": [
        {"key": "yunjian",  "label": "云健 · 沉稳磁性（成熟男性）", "voice": "zh-CN-YunjianNeural", "gender": "m"},
        {"key": "yunxi",    "label": "云希 · 阳光青年（男主常用）", "voice": "zh-CN-YunxiNeural", "gender": "m"},
        {"key": "yunyang",  "label": "云扬 · 专业旁白/新闻（男）", "voice": "zh-CN-YunyangNeural", "gender": "m"},
        {"key": "yunxia",   "label": "云夏 · 少年音（男）", "voice": "zh-CN-YunxiaNeural", "gender": "m"},
    ]},
    {"group": "方言与地区 · 女", "items": [
        {"key": "shaanxi",    "label": "晓妮 · 陕西话女声", "voice": "zh-CN-shaanxi-XiaoniNeural", "gender": "f"},
        {"key": "dongbei",    "label": "晓北 · 东北话女声", "voice": "zh-CN-liaoning-XiaobeiNeural", "gender": "f"},
        {"key": "cantonesef", "label": "曉曼 · 粤语女声（香港）", "voice": "zh-HK-HiuMaanNeural", "gender": "f"},
        {"key": "cantonesef2", "label": "曉佳 · 粤语女声（书卷感）", "voice": "zh-HK-HiuGaaiNeural", "gender": "f"},
        {"key": "taiwanf",  "label": "曉臻 · 台湾腔女声", "voice": "zh-TW-HsiaoChenNeural", "gender": "f"},
        {"key": "taiwanf2", "label": "曉瑜 · 台湾腔女声（清新）", "voice": "zh-TW-HsiaoYuNeural", "gender": "f"},
    ]},
    {"group": "方言与地区 · 男", "items": [
        {"key": "cantonesem", "label": "雲龍 · 粤语男声（香港）", "voice": "zh-HK-WanLungNeural", "gender": "m"},
        {"key": "taiwanm",  "label": "雲哲 · 台湾腔男声", "voice": "zh-TW-YunJheNeural", "gender": "m"},
    ]},
]

DEFAULTS: dict[str, Any] = {
    "provider": "edge",                       # edge | local_http
    "local": {
        "url": "http://127.0.0.1:9880",
        "api": "gpt-sovits",                  # gpt-sovits | openai
        "timeout": 60,
    },
    "groups": BUILTIN_GROUPS,
}

_LOCAL_API = ("gpt-sovits", "openai")
_PROVIDERS = ("edge", "local_http")


def _builtin_voice_keys() -> dict[str, str]:
    return {i["voice"]: i.get("provider", "edge")
            for g in BUILTIN_GROUPS for i in g["items"]}


def _ensure() -> None:
    if FILE.exists():
        return
    FILE.parent.mkdir(parents=True, exist_ok=True)
    _write(DEFAULTS)


def _write(data: dict) -> None:
    FILE.write_text(
        "# Drama Studio 音色源本地配置（后台配置「音色源」选项卡读写；不进 git）\n"
        "# provider: edge = edge-tts 在线免费接口；local_http = 本机/自建 TTS 服务\n"
        "# 条目 provider: edge | local（内置 edge 音色固定走 edge，不受全局切换影响）\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def _deep_merge(base: dict, patch: dict) -> dict:
    import json
    out = json.loads(json.dumps(base))
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    _ensure()
    try:
        raw = yaml.safe_load(FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        raw = {}
    cfg = _deep_merge(DEFAULTS, raw if isinstance(raw, dict) else {})
    # 条目统一补齐 provider 字段，避免前端每条都要判空
    for g in cfg.get("groups") or []:
        for it in g.get("items") or []:
            it.setdefault("provider", "edge")
    return cfg


def menu() -> list[dict]:
    """给前端的下拉菜单结构：[{group, items:[{key,label,voice,gender,provider}]}]"""
    return load().get("groups") or []


def gender_map() -> dict[str, str]:
    return {i["voice"]: i.get("gender", "") for g in menu() for i in g.get("items") or []}


def key_map() -> dict[str, str]:
    return {i["voice"]: i.get("key", "") for g in menu() for i in g.get("items") or []}


def provider_for(voice: str) -> str:
    """该音色走哪个通道：条目级 provider 优先，其次全局 provider。

    返回 edge / local —— 全局 local_http 时，内置 edge 音色仍按条目 provider=edge 走在线。
    """
    cfg = load()
    for g in cfg.get("groups") or []:
        for it in g.get("items") or []:
            if it.get("voice") == voice:
                p = (it.get("provider") or "").strip().lower()
                return "edge" if p == "edge" else "local"
    return "local" if (cfg.get("provider") or "").strip() == "local_http" else "edge"


def local_conf() -> dict:
    loc = load().get("local") or {}
    return {
        "url": str(loc.get("url") or "").rstrip("/"),
        "api": str(loc.get("api") or "gpt-sovits"),
        "timeout": int(loc.get("timeout") or 60),
    }


def public() -> dict:
    cfg = load()
    groups = cfg.get("groups") or []
    return {
        "file": str(FILE),
        "provider": cfg.get("provider") or "edge",
        "local": cfg.get("local") or {},
        "groups": groups,
        "count": sum(len(g.get("items") or []) for g in groups),
        "builtin_keys": sorted({i["key"] for g in BUILTIN_GROUPS for i in g["items"]}),
    }


def set_source(provider: str | None = None, local: dict | None = None) -> dict:
    cfg = load()
    if provider is not None:
        p = str(provider).strip().lower()
        if p not in _PROVIDERS:
            raise ValueError("provider 只支持 edge / local_http")
        cfg["provider"] = p
    if local:
        loc = cfg.setdefault("local", {})
        if local.get("url") is not None:
            url = str(local["url"]).strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError("本地服务地址必须以 http:// 或 https:// 开头")
            loc["url"] = url.rstrip("/")
        if local.get("api") is not None:
            api = str(local["api"]).strip().lower()
            if api not in _LOCAL_API:
                raise ValueError("本地协议只支持 gpt-sovits / openai")
            loc["api"] = api
        if local.get("timeout") is not None:
            try:
                loc["timeout"] = max(5, min(600, int(local["timeout"])))
            except Exception:
                raise ValueError("超时必须是 5-600 的整数秒")
    _write(cfg)
    return public()


def add_item(group: str, label: str, voice: str, gender: str,
             provider: str = "local") -> dict:
    cfg = load()
    group = (group or "本地音色").strip() or "本地音色"
    label = (label or "").strip()
    voice = (voice or "").strip()
    gender = (gender or "").strip().lower()
    if not label:
        raise ValueError("显示名不能为空")
    if not voice:
        raise ValueError("voice id 不能为空（本地服务里登记的音色名/参考音频名）")
    if gender not in ("f", "m"):
        raise ValueError("性别只能选 男声 / 女声（配音性别要强匹配）")
    if provider not in ("local", "edge"):
        raise ValueError("条目 provider 只支持 local / edge")
    all_voices = {i["voice"] for g in cfg.get("groups") or [] for i in g.get("items") or []}
    if voice in all_voices:
        raise ValueError(f"voice id「{voice}」已存在，换一个")
    key = "local_" + "".join(ch if ch.isalnum() else "_" for ch in voice.lower())[:32]
    keys = {i.get("key") for g in cfg.get("groups") or [] for i in g.get("items") or []}
    base, n = key, 2
    while key in keys:
        key, n = f"{base}_{n}", n + 1
    grp = next((g for g in cfg.get("groups") or [] if g.get("group") == group), None)
    if grp is None:
        grp = {"group": group, "items": []}
        cfg.setdefault("groups", []).append(grp)
    grp.setdefault("items", []).append(
        {"key": key, "label": label, "voice": voice, "gender": gender, "provider": provider})
    _write(cfg)
    return public()


def remove_item(key: str) -> dict:
    builtin_keys = {i["key"] for g in BUILTIN_GROUPS for i in g["items"]}
    if key in builtin_keys:
        raise ValueError("内置 edge 音色不允许删除（要停用它请切换全局音色源为本地）")
    cfg = load()
    hit = False
    for g in cfg.get("groups") or []:
        items = g.get("items") or []
        kept = [i for i in items if i.get("key") != key]
        if len(kept) != len(items):
            hit = True
            g["items"] = kept
    if not hit:
        raise ValueError(f"没有 key 为「{key}」的音色")
    # 空的自定义分组一并清掉，避免面板里堆空行
    cfg["groups"] = [g for g in cfg.get("groups") or []
                     if g.get("items") or g.get("group") in {b["group"] for b in BUILTIN_GROUPS}]
    _write(cfg)
    return public()


def probe(url: str | None = None, api: str | None = None, timeout: int = 8) -> dict:
    """探测本地 TTS 服务：可达性 + 尝试列音色（openai 兼容 /v1/voices、gpt-sovits /voices）。"""
    import httpx
    conf = local_conf()
    url = (url or conf["url"]).rstrip("/")
    api = (api or conf["api"])
    t0 = time.time()
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(url)
            reachable = r.status_code < 500
            voices: list[str] = []
            for path in (["/v1/voices", "/voices"] if api == "openai" else ["/voices"]):
                try:
                    rr = c.get(url + path)
                    if rr.status_code == 200:
                        data = rr.json()
                        rows = data.get("data") if isinstance(data, dict) else data
                        if isinstance(rows, list):
                            voices = [str(x.get("id") or x.get("name") or x)
                                      if isinstance(x, dict) else str(x) for x in rows][:40]
                        if voices:
                            break
                except Exception:
                    continue
            return {"ok": True, "reachable": reachable, "status": r.status_code,
                    "url": url, "api": api, "voices": voices,
                    "ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "reachable": False, "url": url, "api": api,
                "error": f"{type(e).__name__}: {e}", "ms": round((time.time() - t0) * 1000)}
