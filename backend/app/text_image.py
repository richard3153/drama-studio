"""带文字道具的云端出图通道（GPT-Image 2.5）。

为什么单开一条通道：

GPT-Image 2.5（`gpt-image-2.5-flare` / `gpt-image-2.5-sunburst`）是 OpenAI 的**闭源
云模型**——官方只开 `/v1/images/generations`，没有任何可下载的本地权重，所以本机
ComfyUI 跑不了它，只能走 HTTP API（官方 key 或任意 OpenAI 兼容中转）。

它的不可替代性在于**字能写对**：令牌铭文、符箓榜文、契约账册、告示榜单这类
"画面主体就是文字"的道具，Qwen-Image / SDXL 只会画伪文字（实测手写标注全是乱码），
GPT-Image 能把给定的中文原样写进画面。所以道具生成按"是否带文字"分流：
带文字 → 本通道；不带 → 本地 ComfyUI（Qwen-Image）。

配置在 `data/settings.yaml` 的 `text_image` 段（前端「⚙️ 配置」可改）：
  base_url: https://api.openai.com/v1   # 或中转站，如 https://xxx/v1
  api_key:  sk-...                      # 或写 env:OPENAI_API_KEY 引用环境变量
  model:    gpt-image-2.5-flare         # flare=光影强 / sunburst=色彩艳
  size:     1536x1024                   # 官方推荐 1024x1024 / 1536x1024 / 1024x1536
  quality:  high                        # low / medium / high / xhigh / max
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import httpx

from .config import ASSETS_ROOT
from .settings import get

# —— 带文字道具的识别词（命中即判定"画面主体是文字"，需要云端准字通道）——
# 只收"文字本身就是物件"的类别：牌子、文书、票券、符箓、经卷、碑刻、账簿…
# 刻意不用单字（"字/刻/印/票/签"）：实测单字会把"签字笔""数字时钟""印刷机"这类
# 普通道具误判成带文字，白白走云端通道。所以用双字以上的专业词 + 描述型短语。
TEXT_PROP_WORDS = (
    "铭文", "刻字", "题字", "字迹", "字样", "带字", "有字",
    "匾额", "牌匾", "令牌", "腰牌", "木牌", "门牌", "招牌", "招贴",
    "符箓", "符纸", "符咒", "黄符", "灵符",
    "诏书", "圣旨", "榜文", "告示", "公文", "文书", "度牒", "通关文牒", "路引",
    "经卷", "经书", "秘籍", "功法卷", "卷轴", "手札", "书信", "密令", "遗嘱",
    "玉简", "竹简", "简牍", "木牍", "石刻",
    "契约", "地契", "房契", "契书", "账簿", "账册", "账本", "名录", "花名册",
    "票据", "兑换券", "银票", "票号", "票据簿",
    "印章", "官印", "玉玺", "印玺", "封条",
    "舆图", "地图", "阵图", "图谱", "碑刻", "石碑", "墓志",
    "牌位", "灵位", "谥册", "册封",
)
# 反例：自带这些词但其实是普通物件（先剔除再判定，避免误分流到云端烧钱）
TEXT_PROP_EXCLUDE = ("字典", "书桌", "书架", "文具", "签字笔", "标签纸", "印泥盒", "印刷机")
# 描述型触发："details 里写着刻着…" —— 比单字精确
TEXT_PROP_PATTERNS = ("刻着", "刻有", "写着", "写有", "印着", "印有", "题着", "题有",
                      "铭着", "铭刻", "镌刻", "上书", "字样", "带字", "刻满", "写满")


def _cfg() -> dict:
    return {
        "enabled": bool(get("text_image", "enabled", True)),
        "base_url": str(get("text_image", "base_url", "https://api.openai.com/v1") or "").rstrip("/"),
        "api_key": str(get("text_image", "api_key", "") or "").strip(),
        "model": str(get("text_image", "model", "gpt-image-2.5-flare") or "").strip(),
        "size": str(get("text_image", "size", "1536x1024") or "").strip(),
        "quality": str(get("text_image", "quality", "high") or "").strip(),
        "timeout_s": float(get("text_image", "timeout_s", 240) or 240),
    }


def api_key() -> str:
    """支持 `env:VAR` 引用环境变量，避免把 key 明文写进配置文件。"""
    raw = _cfg()["api_key"]
    if raw.lower().startswith("env:"):
        return os.environ.get(raw[4:].strip(), "").strip()
    return raw


def ready() -> dict:
    """是否具备调用条件（面板与任务前置检查共用）。"""
    c = _cfg()
    if not c["enabled"]:
        return {"ok": False, "reason": "配置里 text_image.enabled = false"}
    if not c["base_url"]:
        return {"ok": False, "reason": "未配置 base_url"}
    if not api_key():
        return {"ok": False,
                "reason": "未配置 API Key（⚙️ 配置 → GPT-Image 2.5：填 key，或写 env:OPENAI_API_KEY）"}
    return {"ok": True, "reason": "", "model": c["model"], "size": c["size"], "quality": c["quality"]}


def looks_textual(name: str = "", slots: dict | None = None) -> bool:
    """这个道具是不是"带文字"的（名字/用途/细节里出现牌榜契约类词）。"""
    text = " ".join([str(name or "")] + [str(v or "") for v in (slots or {}).values()])
    if any(w in text for w in TEXT_PROP_EXCLUDE):
        # 先把"签字笔/标签纸"这类反例整词剔除，再看还有没有真命中
        for w in TEXT_PROP_EXCLUDE:
            text = text.replace(w, "")
    return any(w in text for w in TEXT_PROP_WORDS) or any(p in text for p in TEXT_PROP_PATTERNS)


def text_prompt(base_prompt: str, slots: dict | None = None, name: str = "") -> str:
    """把道具提示词改写成"给云端模型看的出图指令"。

    云端模型不懂 SDXL 那套逗号词块（"item reference sheet, single object"），
    需要的是自然语言的拍摄说明：一张图、物品居中、留白、光线、以及**逐字写出**
    要出现的文字（这是它相比本地底模唯一的价值点）。
    """
    s = slots or {}
    subject = (s.get("subject") or name or "").strip()
    details = (s.get("details") or "").strip()
    material = (s.get("material") or "").strip()
    purpose = (s.get("purpose") or "").strip()
    body = "，".join(x for x in (subject, material, details) if x) or base_prompt
    text_content = (s.get("text_content") or "").strip()
    lines = [
        "一张中国古风短剧道具的产品图（正视图，单件物品，平放在干净的浅灰或米色背景上，"
        "四周留白，柔和的均匀棚拍光，写实质感，画面里不要出现人物和手）。",
        f"物件：{body}。",
    ]
    if purpose:
        lines.append(f"它的剧情功能是：{purpose}。")
    if text_content:
        lines.append(f"物品表面必须逐字写出这段中文：“{text_content}”，"
                     "笔画结构完全正确、可以逐字辨认，书法手写质感。")
    lines.append(
        "画面上必须有清晰、笔画正确、可以逐字辨认的**简体中文文字**（不要拉丁字母、不要乱码、不要伪字）；"
        "文字要自然融入材质（刻、印、写、烫），不要像后期贴上去的水印。")
    lines.append("不要画面边框、不要水印、不要说明文字块、不要重复物件。")
    return "\n".join(lines)


async def generate(prompt: str, project_id: int, prefix: str,
                   size: str | None = None, quality: str | None = None) -> list[Path]:
    """调云端出图并把图落到本地资产目录（返回路径列表）。"""
    st = ready()
    if not st["ok"]:
        raise RuntimeError("GPT-Image 2.5 不可用：" + st["reason"])
    c = _cfg()
    payload = {"model": c["model"], "prompt": prompt, "n": 1,
               "size": size or c["size"], "quality": quality or c["quality"]}
    url = c["base_url"] + "/images/generations"
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=c["timeout_s"]) as cli:
        r = await cli.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            # 中转站对 quality/size 的取值支持不一：降级重试一次（丢掉不被支持的字段）
            if r.status_code in (400, 422):
                payload.pop("quality", None)
                r = await cli.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            msg = ""
            try:
                msg = (r.json().get("error") or {}).get("message") or ""
            except Exception:
                msg = r.text[:200]
            raise RuntimeError(f"GPT-Image 调用失败（HTTP {r.status_code}）：{msg or '无错误信息'}")
        data = r.json()

    items = data.get("data") or []
    if not items:
        raise RuntimeError("GPT-Image 返回里没有图片（data 为空）")
    save_root = ASSETS_ROOT / str(project_id) / "assets"
    save_root.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, it in enumerate(items):
        b64 = it.get("b64_json")
        if b64:
            raw = base64.b64decode(b64)
        elif it.get("url"):
            async with httpx.AsyncClient(timeout=c["timeout_s"]) as cli:
                rr = await cli.get(it["url"])
                rr.raise_for_status()
                raw = rr.content
        else:
            continue
        ext = "png"
        if raw[:3] == b"\xff\xd8\xff":
            ext = "jpg"
        name = f"{re.sub(r'[^0-9A-Za-z_]', '', prefix)}_gpt{i + 1:05d}_.{ext}"
        path = save_root / name
        path.write_bytes(raw)
        saved.append(path)
    if not saved:
        raise RuntimeError("GPT-Image 返回的数据里既没有 b64_json 也没有 url")
    return saved
