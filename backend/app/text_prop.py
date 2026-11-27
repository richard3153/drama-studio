"""带文字道具的判定词表（纯本地，无任何云端调用）。

历史：这里曾经是一条 GPT-Image 2.5 云端整图通道。已按用户要求移除——
GPT-Image 2.5 是闭源 API 模型，**没有任何可下载的本地权重**（ComfyUI 里只有走
OpenAI API 的 Partner Node），而整图重渲又会换掉构图/纸纹/光影，不满足"只把字改对"。
现在带文字道具的链路是：

1. 本地底模出整图（Qwen-Image 2.1），`style_presets.assemble_prop_prompt` 把
   `text_content` 槽位里的中文塞进提示词（实测五字竖排一次写对）；
2. 字写错/写糊 → 资产卡「📝 改字」，在原图上框住文字区做 mask 局部重绘
   （`services/text_edit_service.py` + `workflows/prop_text_inpaint.json`）。

本文件只剩两件事：判断"这个道具是不是画面主体就是文字"，以及在没填
`text_content` 时用道具名兜底当要写的字。
"""
from __future__ import annotations

# —— 识别词（命中即判定"画面主体是文字"）——
# 只收"文字本身就是物件"的类别：牌子、文书、票券、符箓、经卷、碑刻、账簿…
# 刻意不用单字（"字/刻/印/票/签"）：实测单字会把"签字笔""数字时钟""印刷机"这类
# 普通道具误判成带文字。
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
# 反例：自带这些词但其实是普通物件（先剔除再判定）
TEXT_PROP_EXCLUDE = ("字典", "书桌", "书架", "文具", "签字笔", "标签纸", "印泥盒", "印刷机")
# 描述型触发："details 里写着刻着…" —— 比单字精确
TEXT_PROP_PATTERNS = ("刻着", "刻有", "写着", "写有", "印着", "印有", "题着", "题有",
                      "铭着", "铭刻", "镌刻", "上书", "字样", "带字", "刻满", "写满")


def looks_textual(name: str = "", slots: dict | None = None) -> bool:
    """这个道具是不是"带文字"的（名字/用途/细节里出现牌榜契约类词）。"""
    text = " ".join([str(name or "")] + [str(v or "") for v in (slots or {}).values()])
    if any(w in text for w in TEXT_PROP_EXCLUDE):
        for w in TEXT_PROP_EXCLUDE:
            text = text.replace(w, "")
    return any(w in text for w in TEXT_PROP_WORDS) or any(p in text for p in TEXT_PROP_PATTERNS)


def surface_text(name: str = "", slots: dict | None = None) -> str:
    """要写在道具表面上的字：优先 text_content 槽位，否则用道具名兜底（≤12 字）。"""
    s = slots or {}
    explicit = str(s.get("text_content") or s.get("text") or "").strip()
    if explicit:
        return explicit
    n = str(name or "").strip()
    if n and len(n) <= 12 and looks_textual(n, s):
        return n
    return ""
