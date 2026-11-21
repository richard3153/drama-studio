"""配音与成片服务（决策拍板：edge-tts 在线 TTS + 拼接 + 配音混入 + SRT 字幕烧录）。

显存原则：TTS 走 edge-tts 在线（零显存，不与视频推理抢 GPU）；
拼接走 ffmpeg concat demuxer -c copy 无损（wan21 各段编码参数一致，实测可用）；
混音只重编码音频轨（aac），视频轨保持 copy；
字幕烧录必须重编码视频 → h264_nvenc 硬编（精简版 ffmpeg 无 libx264 但有 NVENC，4070 实测可用）。

闭环语义：本模块是纯下游聚合，不删除任何镜头产物；重合成幂等（同一输入重复执行结果一致）。
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import edge_tts
from sqlalchemy import select

from ..config import FFMPEG
from ..db import Character, Episode, Project, Shot, TaskRecord
from ..scheduler.queue import update_progress

FFPROBE = FFMPEG.with_name("ffprobe.exe")
ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "projects"

# 音色全量库（2026-11-21 用 edge_tts.list_voices() 实测的中文音色全集，14 个——
# 旧菜单里 Xiaojian/Xiaoxuan/Yunfeng/Yunye 等在 edge-tts 免费接口中不存在，选了会 TTS 失败，
# 已全部剔除。gender 标注 f/m：角色音色必须与角色性别匹配（拆解描述猜性别 + 设置时强校验）。
VOICE_MENU = [
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
        {"key": "shaanxi",  "label": "晓妮 · 陕西话女声", "voice": "zh-CN-shaanxi-XiaoniNeural", "gender": "f"},
        {"key": "dongbei",  "label": "晓北 · 东北话女声", "voice": "zh-CN-liaoning-XiaobeiNeural", "gender": "f"},
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
VOICE_GENDER = {i["voice"]: i["gender"] for g in VOICE_MENU for i in g["items"]}
NARRATOR_DEFAULT = "zh-CN-YunyangNeural"
# 兼容旧字段：音色名 → 菜单 key
VOICE_KEYS = {i["voice"]: i["key"] for g in VOICE_MENU for i in g["items"]}


def _proj_dir(pid: int) -> Path:
    d = ASSETS_ROOT / str(pid)
    (d / "audio").mkdir(parents=True, exist_ok=True)
    (d / "export").mkdir(parents=True, exist_ok=True)
    return d


def _assign_voices(db, project_id: int) -> dict[str, str]:
    """角色名 → 音色：只认 characters.voice 手动锁死的值，不再自动分配。"""
    chars = db.scalars(select(Character).where(Character.project_id == project_id)).all()
    return {c.name: c.voice for c in chars if getattr(c, "voice", "")}


def taken_voices(db, project_id: int, exclude_character_id: int | None = None) -> dict[str, str]:
    """项目内已占用的音色 → 占用者名（角色 + 旁白）。选新音色时必须避开。"""
    taken: dict[str, str] = {}
    proj = db.get(Project, project_id)
    nv = getattr(proj, "narrator_voice", "") if proj else ""
    if nv:
        taken[nv] = "旁白"
    chars = db.scalars(select(Character).where(Character.project_id == project_id)).all()
    for c in chars:
        v = getattr(c, "voice", "")
        if v and c.id != exclude_character_id:
            taken[v] = taken.get(v) or c.name
    return taken


def guess_gender(description: str) -> str | None:
    """从角色描述猜性别：f / m / None（猜不出不强判）。

    中英文双词表：拆解 LLM 的 identity 槽位常写 "female young adult" 这类英文。
    """
    d = (description or "").lower()
    # 英文用词边界匹配（避免 female 里的 male 子串误伤）
    import re
    is_f = bool(re.search(r'\b(female|woman|girl|lady|she)\b', d)) \
        or any(w in d for w in ("女", "她", "母", "姐", "妹", "妻", "婆", "娘", "妇", "姨", "奶"))
    is_m = bool(re.search(r'\b(male|man|boy|guy|he)\b', d)) \
        or any(w in d for w in ("男", "他", "父", "叔", "哥", "弟", "夫", "爷", "郎"))
    if is_f and not is_m:
        return "f"
    if is_m and not is_f:
        return "m"
    return None


def pick_free_voice(db, project_id: int, description: str = "") -> str | None:
    """给新角色自动分配一个未被占用、且与性别匹配的音色。

    性别优先：描述能判性别 → 只在该性别组内找（该组耗尽再换另一组兜底）；
    猜不出性别 → 女→男 顺序。全库耗尽返回 None（允许手动重复）。
    """
    taken = set(taken_voices(db, project_id))
    g = guess_gender(description)
    female_groups = [grp for grp in VOICE_MENU if grp["group"].endswith("女") or "女" in grp["group"]]
    male_groups = [grp for grp in VOICE_MENU if grp not in female_groups]
    ordered = (female_groups + male_groups) if g == "f" else (male_groups + female_groups)
    for item in [i for grp in ordered for i in grp["items"]]:
        if item["voice"] not in taken:
            return item["voice"]
    return None


def _missing_voices(db, project_id: int, dialogue_names: set[str]) -> list[str]:
    """校验：出现过的台词角色（或旁白）音色是否已锁死，返回缺失清单。"""
    from ..db import Project
    p = db.get(Project, project_id)
    chars = db.scalars(select(Character).where(Character.project_id == project_id)).all()
    assigned = {c.name: c.voice for c in chars if getattr(c, "voice", "")}
    missing = [n for n in sorted(dialogue_names) if n not in assigned]
    narrator_ok = bool(getattr(p, "narrator_voice", ""))
    if not narrator_ok:
        missing.insert(0, "【旁白/无前缀台词】")
    return missing


def _parse_lines(dialogue: str) -> list[tuple[str, str, str]]:
    """解析台词行 → (说话人, 语气, 台词)。

    支持格式：
    - 「角色名（语气）：台词」——语气标注（低语/急促/愤怒/悲伤…见 TONE_MAP）
    - 「角色名：台词」——语气默认平静
    - 无前缀行 → ("", "", text) 归旁白
    """
    out = []
    for raw in re.split(r"[\n；;]+", dialogue or ""):
        line = raw.strip().strip("。")
        if not line:
            continue
        m = re.match(r"^([^\u4e00-\u9fa5\w]{0,4})([\u4e00-\u9fa5\w]{1,8})"
                     r"(?:（([^）]{1,6})）)?[:：]\s*(.+)$", line)
        if m and len(m.group(2)) <= 6:
            out.append((m.group(2), (m.group(3) or "").strip(), m.group(4).strip()))
        else:
            out.append(("", "", line))
    return out


# 语气 → (语速, 音调)：映射到 edge-tts 的 rate/pitch，让同一音色说出不同情绪
TONE_MAP = {
    "": ("+0%", "+0Hz"), "平静": ("+0%", "+0Hz"),
    "低语": ("-12%", "-6Hz"), "紧张": ("-8%", "-4Hz"),
    "急促": ("+18%", "+0Hz"), "愤怒": ("+8%", "+12Hz"),
    "悲伤": ("-15%", "-10Hz"), "惊喜": ("+6%", "+16Hz"),
    "温柔": ("-6%", "-3Hz"), "迟疑": ("-20%", "-5Hz"),
    "兴奋": ("+10%", "+8Hz"), "冷峻": ("-8%", "-8Hz"),
}


def _tone_params(tone: str) -> tuple[str, str]:
    return TONE_MAP.get((tone or "").strip(), ("+0%", "+0Hz"))


async def _tts_one(text: str, voice: str, out_path: Path, rate: str = "+0%",
                   pitch: str = "+0Hz"):
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await c.save(str(out_path))


async def tts_episode(db, t: TaskRecord, params: dict) -> dict:
    """本集全部有台词镜头批量 TTS：audio/p{pid}_s{idx}_{seq}.mp3。

    音色必须已锁死（用户拍板）：角色看 characters.voice，旁白看 project.narrator_voice；
    缺哪个报哪个，不做自动兜底。
    """
    update_progress(db, t, 0.05, "收集台词")
    eid, pid = params["episode_id"], params["project_id"]
    from ..db import Project
    project = db.get(Project, pid)
    shots = db.scalars(select(Shot).where(Shot.episode_id == eid)
                       .order_by(Shot.idx)).all()
    voices = _assign_voices(db, pid)
    audio_dir = _proj_dir(pid) / "audio"
    # 清掉本集旧配音文件，避免残留孤儿音轨（重生成幂等）
    # 清掉本集旧配音文件，避免残留孤儿音轨（重生成幂等）。
    # 文件名必须带集号（e{eid}）：同项目各集镜头序号相同，不带集号会互相覆盖/误删
    for old in audio_dir.glob(f"p{pid}_e{eid}_s*_vo*.mp3"):
        old.unlink(missing_ok=True)

    jobs: list[tuple[Shot, int, str, str, str]] = []   # (shot, seq, tone, text, voice)
    missing = []
    for sh in shots:
        if not (sh.dialogue or "").strip():
            continue
        for seq, (who, tone, text) in enumerate(_parse_lines(sh.dialogue)):
            if who == "旁白":       # 旁白前缀行走 narrator_voice
                who = ""
            v = voices.get(who) if who else None
            if not v and who:
                missing.append(who)
                continue
            if not who and not getattr(project, "narrator_voice", ""):
                if "【旁白】" not in missing:
                    missing.append("【旁白】")
                continue
            jobs.append((sh, seq, tone, text, v or project.narrator_voice))
    if missing:
        raise RuntimeError("以下说话人还没有锁定音色，请先试听并选择：" +
                           "、".join(sorted(set(missing))))

    done = 0
    for sh, seq, tone, text, voice in jobs:
        out = audio_dir / f"p{pid}_e{eid}_s{sh.idx}_vo{seq}.mp3"
        rate, pitch = _tone_params(tone)
        await _tts_one(text, voice, out, rate=rate, pitch=pitch)
        done += 1
        update_progress(db, t, 0.05 + 0.9 * done / max(len(jobs), 1),
                        f"配音 {done}/{len(jobs)}：{text[:18]}")

    update_progress(db, t, 1.0, f"配音完成 {done} 条")
    return {"lines": done}


async def voice_preview(voice: str, pid: int) -> Path:
    """试听：生成一句样音返回文件路径（同音色缓存复用）。"""
    audio_dir = _proj_dir(pid) / "audio"
    safe = re.sub(r"[^A-Za-z0-9]", "_", voice)
    out = audio_dir / f"preview_{safe}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        return out
    await _tts_one("这是我的声音。深夜的街口，故事刚刚开始。", voice, out)
    return out


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run([str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _run_ff(args: list, stage_hint: str):
    """ffmpeg 调用统一包装：失败时把 stderr 尾部带进异常，避免黑盒。"""
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stderr or "")[-800:]
        raise RuntimeError(f"ffmpeg {stage_hint} 失败(rc={r.returncode}): {tail}")
    return r


def _srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _video_size(path: Path) -> tuple[int, int]:
    """探测视频宽高（字幕字号/边距按分辨率自适应的基准）。"""
    r = subprocess.run([str(FFPROBE), "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0:s=x", str(path)], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return (1280, 720)


def _subtitle_font_px(w: int, h: int) -> float:
    """字幕字号像素值（横屏贴画高 / 竖屏贴画宽）。"""
    return h * 0.038 if w >= h else w * 0.048


_CJK_RE = re.compile(r"[\u2e80-\u9fff\uff00-\uffef\u3000-\u303f]")


def _char_units(ch: str) -> float:
    """字符宽度估算：CJK 全角 ≈ 1 个字宽，西文 ≈ 0.55。"""
    return 1.0 if _CJK_RE.match(ch) else 0.55


def _split_subtitle_line(text: str, w: int, h: int) -> list[str]:
    """字幕单行硬约束：按成片宽度估算一行容量，超宽的台词切成多段顺序显示。

    容量 = 画面宽的 92% ÷ 字宽；分段优先在标点/空格处断，西文单词不拆字母。
    """
    if not (text or "").strip():
        return [text or ""]
    max_units = max(8.0, (w * 0.92) / _subtitle_font_px(w, h))
    # 切 token：CJK 单字一枚，西文连续串（单词+尾随标点）一枚
    tokens = re.findall(r"[A-Za-z0-9]+[\.,!?'’]*|.", text)
    lines, cur, cur_u = [], "", 0.0
    for tk in tokens:
        u = sum(_char_units(c) for c in tk)
        if cur and cur_u + u > max_units:
            lines.append(cur.strip())
            cur, cur_u = "", 0.0
        cur += tk
        cur_u += u
    if cur.strip():
        lines.append(cur.strip())
    return lines or [text]


def _subtitle_style(w: int, h: int) -> str:
    """按画幅算字幕样式：字号 = 画面高的 ~3.8%（横）/ 宽的 4.8%（竖），底部居中留安全边距。

    ffmpeg 把 SRT 转 ASS 时 PlayRes 固定 384x288，force_style 的 FontSize/MarginV
    都在 288 高的坐标系里，随视频高度线性放大 → 换算 px * 288 / h。
    WrapStyle=2 禁止 libass 自动折行（超宽已在 _split_subtitle_line 里分段）。
    """
    font_px = _subtitle_font_px(w, h)
    if w >= h:                                  # 横屏：字号贴视频高度
        margin_px = h * 0.045                   # 贴底但留出安全区
    else:                                       # 竖屏：位置略抬高避 UI 遮挡
        margin_px = h * 0.085
    font_size = max(8, round(font_px * 288 / h))
    margin_v = max(4, round(margin_px * 288 / h))
    return (f"FontName=Microsoft YaHei,FontSize={font_size},Alignment=2,MarginV={margin_v},"
            "WrapStyle=2,"
            "PrimaryColour=&H00FFFFFF&,OutlineColour=&H000000&,BackColour=&H80000000&,"
            "BorderStyle=1,Outline=1.1,Shadow=0,Spacing=0.4")


def export_final(db, t: TaskRecord, params: dict) -> dict:
    """成片合成：拼接 → 混音 → SRT → NVENC 烧字幕。全同步 ffmpeg，fn 内直接跑。"""
    update_progress(db, t, 0.02, "收集镜头")
    eid, pid = params["episode_id"], params["project_id"]
    shots = db.scalars(select(Shot).where(Shot.episode_id == eid)
                       .order_by(Shot.idx)).all()
    segs = []   # {idx, video, dur, lines:[(seq,text)]}
    skipped = []
    for sh in shots:
        if sh.video_path and Path(sh.video_path).exists():
            segs.append({"idx": sh.idx, "video": Path(sh.video_path),
                         "dur": _ffprobe_duration(Path(sh.video_path)),
                         "lines": _parse_lines(sh.dialogue or "")})
        elif (sh.dialogue or "").strip() or sh.video_path:
            skipped.append(sh.idx)
    if not segs:
        raise RuntimeError("本集没有任何可用镜头视频，先去分镜页生成镜头视频")
    total_dur = sum(s["dur"] for s in segs)

    export_dir = _proj_dir(pid) / "export"
    novoice = export_dir / f"final_ep{eid}_mute.mp4"
    final = export_dir / f"final_ep{eid}.mp4"
    srt_path = export_dir / f"final_ep{eid}.srt"

    # 1) 无损拼接（-c copy；文件名转义走 concat demuxer 清单文件）
    update_progress(db, t, 0.1, f"拼接 {len(segs)} 段（无损 copy）")
    lst = export_dir / "concat_list.txt"
    lst.write_text("".join(f"file '{s['video'].as_posix()}'\n" for s in segs),
                   encoding="utf-8")
    _run_ff([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", str(novoice)], "无损拼接")
    total_dur = _ffprobe_duration(novoice) or total_dur
    sub_w, sub_h = _video_size(novoice)   # 字幕单行容量基准（成片实际分辨率）

    # 2) 台词音频 + SRT：按镜头起点 adelay 混入；镜内多行平分时长
    # 配音文件必须已由「生成台词配音」产出（音色已锁死校验过），缺失直接报错而不是自动兜底
    update_progress(db, t, 0.35, "混入台词配音")
    audio_dir = _proj_dir(pid) / "audio"
    missing_audio = [f"s{s['idx']}#vo{j}" for s in segs for j in range(len(s["lines"]))
                     if not (audio_dir / f"p{pid}_e{eid}_s{s['idx']}_vo{j}.mp3").exists()]
    if missing_audio:
        raise RuntimeError("缺少配音文件（先点「生成台词配音」）：" + "、".join(missing_audio[:8]))
    filters, mix_inputs, cursor, srt_rows, n = [], [], 0.0, [], 0
    for s in segs:
        shot_end = cursor + s["dur"]
        cur_line = cursor + 0.15     # 台词从镜头起点略延后开始
        for j, (who, tone, text) in enumerate(s["lines"]):
            mp3 = audio_dir / f"p{pid}_e{eid}_s{s['idx']}_vo{j}.mp3"
            adur = _ffprobe_duration(mp3) or 2.0
            # 行开始按实际音频时长顺序排布（不再是镜内平分），越过镜尾则贴到镜尾
            start = min(cur_line, max(cursor, shot_end - adur))
            remain = max(shot_end - start, 0.5)
            filters.append(
                f"[{len(mix_inputs) + 1}:a]aresample=44100,"
                f"aformat=channel_layouts=stereo,"
                f"adelay={int(start * 1000)}|{int(start * 1000)},"
                f"atrim=0:{remain}[a{n}]")
            mix_inputs.append(f"[a{n}]")
            n += 1
            # 字幕只放台词本身，不带说话人名（说话人由配音音色区分）；
            # 单行硬约束：超宽台词按段长加权切成多段顺序显示（各段区间不重叠）
            chunks = _split_subtitle_line(text, sub_w, sub_h)
            span = min(start + adur, shot_end) - start
            if len(chunks) == 1:
                srt_rows.append((start, start + span, text))
            else:
                weights = [sum(_char_units(c) for c in ch) for ch in chunks]
                total_w = sum(weights) or 1
                cur = start
                for k, ch in enumerate(chunks):
                    end_k = start + span if k == len(chunks) - 1 \
                        else cur + span * weights[k] / total_w
                    srt_rows.append((cur, end_k, ch))
                    cur = end_k
            cur_line = start + adur + 0.35   # 行间 0.35s 呼吸间隔
        cursor += s["dur"]

    if n:
        fc = ";".join(filters) + ";" + "".join(mix_inputs) + \
             f"amix=inputs={n}:duration=longest:normalize=0[mixout]"
        mixed = export_dir / f"final_ep{eid}_vo.mp4"
        _run_ff([str(FFMPEG), "-y", "-i", str(novoice)] +
                [x for a in _collect_vo_audio(segs, pid, eid, audio_dir) for x in ("-i", str(a))] +
                ["-filter_complex", fc, "-map", "0:v", "-map", "[mixout]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(mixed)],
                "台词混音")
    else:
        mixed = novoice

    # 3) SRT
    update_progress(db, t, 0.7, f"写字幕 SRT（{len(srt_rows)} 行）")
    srt_path.write_text("".join(
        f"{i + 1}\n{_srt_ts(a)} --> {_srt_ts(b)}\n{text}\n\n"
        for i, (a, b, text) in enumerate(srt_rows)), encoding="utf-8")

    # 4) 烧字幕：NVENC 硬编重编码（无 libx264 的替代）；无台词时只拼不烧。
    #    字号/边距按成片分辨率自适应，底部居中（横竖屏各自基准，见 _subtitle_style）
    if srt_rows:
        update_progress(db, t, 0.85, "烧录字幕（h264_nvenc）")
        sub_arg = str(srt_path).replace("\\", "/").replace(":", "\\:")
        w, h = _video_size(mixed)
        style = _subtitle_style(w, h)
        _run_ff(
            [str(FFMPEG), "-y", "-i", str(mixed), "-vf",
             f"subtitles='{sub_arg}':force_style='{style}'", "-c:v", "h264_nvenc",
             "-preset", "p4", "-cq", "23", "-c:a", "copy", str(final)],
            "烧录字幕")
    else:
        final.write_bytes(mixed.read_bytes())

    update_progress(db, t, 1.0, f"成片完成 {_ffprobe_duration(final):.1f}s")
    return {"file": str(final), "srt": str(srt_path), "segments": len(segs),
            "subtitles": len(srt_rows), "skipped_shots": skipped,
            "duration": round(_ffprobe_duration(final), 2)}


def _collect_vo_audio(segs, pid, eid, audio_dir):
    out = []
    for s in segs:
        for j in range(len(s["lines"])):
            out.append(audio_dir / f"p{pid}_e{eid}_s{s['idx']}_vo{j}.mp3")
    return out
