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
import time
from datetime import datetime
from pathlib import Path

import edge_tts
from sqlalchemy import select

from .. import voice_sources
from ..config import FFMPEG
from ..db import Character, Episode, Project, Shot, TaskRecord
from ..scheduler.queue import update_progress

FFPROBE = FFMPEG.with_name("ffprobe.exe")
ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "projects"

# 音色清单已迁到 data/voice_sources.yaml（后台配置「音色源」选项卡可增删）：
# 内置 14 个 edge-tts 音色是默认种子（2026-11-21 用 edge_tts.list_voices() 实测，
# 旧菜单里 Xiaojian/Xiaoxuan/Yunfeng/Yunye 等在免费接口不存在、选了会失败，已剔除）；
# 自定义本地音色按 provider=local 走自建 HTTP TTS 服务。gender 标注 f/m：
# 角色音色必须与角色性别匹配（拆解描述猜性别 + 设置时强校验）。
def voice_menu() -> list[dict]:
    return voice_sources.menu()


def voice_gender(voice: str) -> str:
    return voice_sources.gender_map().get(voice, "")


def voice_key(voice: str) -> str:
    return voice_sources.key_map().get(voice, "")


NARRATOR_DEFAULT = "zh-CN-YunyangNeural"


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
    menu = voice_menu()
    female_groups = [grp for grp in menu if grp["group"].endswith("女") or "女" in grp["group"]]
    male_groups = [grp for grp in menu if grp not in female_groups]
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
    """单条 TTS：按音色条目的 provider 分派（edge 在线 / local 自建 HTTP 服务）。

    rate/pitch 只有 edge-tts 认；本地服务不传（不同引擎参数不通用，强传会被拒）。
    """
    if voice_sources.provider_for(voice) == "local":
        await _tts_local(text, voice, out_path)
        return
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await c.save(str(out_path))


async def _tts_local(text: str, voice: str, out_path: Path):
    """本地 TTS 服务出音频。支持两种协议：

    - gpt-sovits：POST {base}/tts，{text, text_lang, ref_audio_path=voice, media_type: mp3}
      （GPT-SoVITS api_v2 `api_v2.py` 的标准入参；voice 填参考音频文件名或 speaker）
    - openai：POST {base}/v1/audio/speech，{model, input, voice, response_format: mp3}
      （Kokoro-FastAPI / openedai-speech 等 OpenAI 兼容服务）

    产物落地仍用上层给定的 .mp3 路径（文件名是成片混音的约定，不可变）。
    """
    import httpx
    conf = voice_sources.local_conf()
    base, api, timeout = conf["url"].rstrip("/"), conf["api"], conf["timeout"]
    if not base:
        raise RuntimeError("本地音色源未配置服务地址（后台配置 → 音色源）")
    if not voice:
        raise RuntimeError("音色 id 为空")
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            if api == "openai":
                r = await c.post(f"{base}/v1/audio/speech", json={
                    "model": "tts-1", "input": text, "voice": voice,
                    "response_format": "mp3", "speed": 1.0})
            else:
                r = await c.post(f"{base}/tts", json={
                    "text": text, "text_lang": "zh", "ref_audio_path": voice,
                    "prompt_text": "", "prompt_lang": "zh",
                    "media_type": "mp3", "streaming_mode": False})
    except Exception as e:
        raise RuntimeError(f"本地 TTS 服务连不上 {base}（{api}）：{type(e).__name__}: {e}")
    body = getattr(r, "content", b"") or b""
    if r.status_code >= 400:
        raise RuntimeError(f"本地 TTS 服务返回 {r.status_code}：{body[:200].decode('utf-8', 'ignore')}")
    if len(body) < 1000:
        raise RuntimeError(f"本地 TTS 返回音频过短（{len(body)} 字节）——检查服务端是否就绪、"
                           f"音色「{voice}」是否在服务里登记")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(body)


def audio_media_type(path: Path) -> str:
    """按文件头判音频 MIME（本地服务的 mp3 声明可能不靠谱，试听接口别硬写 audio/mpeg）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except Exception:
        return "audio/mpeg"
    if head[:4] == b"RIFF":
        return "audio/wav"
    return "audio/mpeg"


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


def _video_probe(path: Path) -> dict:
    """探测视频宽高/帧率/编码（拼接前判参：wan 480x832@16fps 旧片 × H3 768x1344@24fps
    新片混拼时 concat demuxer 必坏，需走 concat filter 统一缩放重编码）。"""
    r = subprocess.run([str(FFPROBE), "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        st = json.loads(r.stdout)["streams"][0]
        num, den = st["r_frame_rate"].split("/")
        return {"w": int(st["width"]), "h": int(st["height"]),
                "fps": round(float(num) / float(den), 3), "codec": st.get("codec_name", "")}
    except Exception:
        return {"w": 0, "h": 0, "fps": 0.0, "codec": ""}


def _segments_uniform(segs: list) -> bool:
    """全段分辨率/帧率一致 → 可走 -c copy 无损快路。"""
    probes = [_video_probe(s["video"]) for s in segs]
    first = probes[0]
    return all(p["w"] == first["w"] and p["h"] == first["h"]
               and abs(p["fps"] - first["fps"]) < 0.01 for p in probes[1:])


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


def _make_fade_seg(a_video: Path, b_img: str, out_dir: Path, style: str,
                   a_idx: int, b_idx: int) -> Path | None:
    """兜底转场段（方案四）：A 末帧淡出 → B 首帧淡入（黑场/白闪），0.8s NVENC 编码。

    幂等：同边界产物已存在直接复用。失败抛异常由调用方吞掉退化硬切。
    """
    out = out_dir / f"transition_fade_{style}_s{a_idx}_s{b_idx}.mp4"
    if out.exists():
        return out
    out_dir.mkdir(parents=True, exist_ok=True)
    a_png = out_dir / f".tfade_{style}_s{a_idx}_s{b_idx}_a.png"
    _run_ff([str(FFMPEG), "-y", "-sseof", "-0.2", "-i", str(a_video),
             "-frames:v", "1", str(a_png)], "抽A末帧")
    color = "white" if style == "fadewhite" else "black"
    _run_ff([str(FFMPEG), "-y",
             "-loop", "1", "-t", "0.4", "-i", str(a_png),
             "-loop", "1", "-t", "0.4", "-i", str(b_img),
             "-filter_complex",
             f"[0:v]format=yuv420p,fade=t=out:st=0.2:d=0.2:color={color}[a];"
             f"[1:v]format=yuv420p,fade=t=in:st=0:d=0.3:color={color}[b];"
             f"[a][b]concat=n=2:v=1:a=0,setsar=1",
             "-r", "16", "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
             str(out)], "生成兜底转场段")
    a_png.unlink(missing_ok=True)
    return out if out.exists() else None


def export_final(db, t: TaskRecord, params: dict) -> dict:
    """成片合成：拼接 → 混音 → SRT → NVENC 烧字幕。全同步 ffmpeg，fn 内直接跑。"""
    update_progress(db, t, 0.02, "收集镜头")
    eid, pid = params["episode_id"], params["project_id"]
    shots = db.scalars(select(Shot).where(Shot.episode_id == eid)
                       .order_by(Shot.idx)).all()
    segs = []   # {idx, video, dur, lines:[(seq,text)], scene}
    skipped = []
    for sh in shots:
        if sh.video_path and Path(sh.video_path).exists():
            segs.append({"idx": sh.idx, "video": Path(sh.video_path),
                         "dur": _ffprobe_duration(Path(sh.video_path)),
                         "scene": sh.scene_name or "",
                         "first_frame": sh.first_frame_path or "",
                         "lines": _parse_lines(sh.dialogue or "")})
        elif (sh.dialogue or "").strip() or sh.video_path:
            skipped.append(sh.idx)
    if not segs:
        raise RuntimeError("本集没有任何可用镜头视频，先去分镜页生成镜头视频")
    total_dur = sum(s["dur"] for s in segs)

    # 转场插入（方案二/四）：场景切换边界优先用已生成的双帧转场镜；
    # 没有转场镜且项目配了兜底转场（fadeblack/fadewhite）→ 用 A 末帧淡出+B 首帧淡入
    # 生成插入段（0.8s，NVENC 编码）。插入段无台词无字幕，时长计入游标，配音起点自动后移。
    from .shot_service import transition_clip_path
    proj = db.get(Project, pid)
    fx = (getattr(proj, "transition_fx", "") or "").strip().lower() if proj else ""
    inserts = 0
    export_dir0 = _proj_dir(pid) / "export"
    i = 0
    while i < len(segs) - 1:
        a, b = segs[i], segs[i + 1]
        if (a["scene"] or "") == (b["scene"] or ""):
            i += 1
            continue
        bridge = transition_clip_path(pid, a["idx"], b["idx"])
        if bridge.exists():
            segs.insert(i + 1, {"idx": a["idx"], "video": bridge,
                                "dur": _ffprobe_duration(bridge) or 1.0,
                                "scene": "", "first_frame": "", "lines": []})
            inserts += 1
            i += 2   # 跳过刚插入的转场段（A→转场段→B）：转场段 scene="" 会被误判成新边界造成死循环
            continue
        elif fx in ("fadeblack", "fadewhite") and b.get("first_frame"):
            try:
                seg = _make_fade_seg(a["video"], b["first_frame"], export_dir0,
                                     fx, a["idx"], b["idx"])
                if seg:
                    segs.insert(i + 1, {"idx": a["idx"], "video": seg,
                                        "dur": _ffprobe_duration(seg) or 0.8,
                                        "scene": "", "first_frame": "", "lines": []})
                    inserts += 1
                    i += 2   # 同上：跳过插入段，防重复插入死循环
                    continue
            except Exception:
                pass   # 兜底段生成失败不阻塞成片，退化为硬切
        i += 1
    if inserts:
        update_progress(db, t, 0.06, f"插入转场段 {inserts} 处")

    export_dir = _proj_dir(pid) / "export"
    novoice = export_dir / f"final_ep{eid}_mute.mp4"
    final = export_dir / f"final_ep{eid}.mp4"
    srt_path = export_dir / f"final_ep{eid}.srt"

    # 1) 拼接：先探测各段参数。wan 旧片(480x832@16fps)与 H3 新片(768x1344@24fps)混拼时
    #    concat demuxer（copy 或重编码）都会因流参数不一致坏掉——走 concat filter
    #    统一 scale/pad 到首段分辨率 + fps 归一后 NVENC 重编码一次。
    #    全段一致才走 -c copy 无损快路。
    mixed_params = not _segments_uniform(segs)
    update_progress(db, t, 0.1, f"拼接 {len(segs)} 段" +
                    ("（混合分辨率/帧率，统一缩放重编码）" if mixed_params
                     else "（含转场段，重编码）" if inserts else "（无损 copy）"))
    lst = export_dir / "concat_list.txt"
    lst.write_text("".join(f"file '{s['video'].as_posix()}'\n" for s in segs),
                   encoding="utf-8")
    if mixed_params:
        base_w, base_h = _video_size(segs[0]["video"])
        base_fps = _video_probe(segs[0]["video"])["fps"] or 24.0
        chains = []
        for i, s in enumerate(segs):
            chains.append(
                f"[{i}:v]scale={base_w}:{base_h}:force_original_aspect_ratio=decrease,"
                f"pad={base_w}:{base_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"fps={base_fps},format=yuv420p[v{i}]")
        fc = ";".join(chains) + ";" + \
            "".join(f"[v{i}]" for i in range(len(segs))) + \
            f"concat=n={len(segs)}:v=1:a=0[vout]"
        _run_ff([str(FFMPEG), "-y"] +
                [x for s in segs for x in ("-i", str(s["video"]))] +
                ["-filter_complex", fc, "-map", "[vout]",
                 "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
                 "-pix_fmt", "yuv420p", "-an", str(novoice)], "拼接（混合参数，concat filter）")
    elif inserts:
        _run_ff([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "8M",
                 "-pix_fmt", "yuv420p", "-an", str(novoice)], "拼接（含转场段）")
    else:
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
    shot_starts: list[float] = []
    for s in segs:
        shot_starts.append(cursor)
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

    # 分轨：BGM 铺底（整集循环 + 首尾淡入淡出）+ 每镜动作音/环境音（贴镜头起点）。
    # 台词轨是上面 n 条 adelay 输入；这里追加的输入排在它们之后，索引按顺序算。
    vo_paths = _collect_vo_audio(segs, pid, eid, audio_dir)
    inputs: list[dict] = [{"path": p} for p in vo_paths]
    try:
        from ..audio_mix import load as _load_mix
        from .. import sfx_library as _sfx
        mixcfg = _load_mix(pid, eid)
    except Exception as e:
        # 分轨配置读不出来不该让整条成片链路失败，但必须留痕（否则用户以为挂了 BGM 却没混进去）
        print(f"[export_final] 音频分轨配置读取失败（{e}），本集按纯台词轨合成", flush=True)
        mixcfg, _sfx = {"bgm": {}, "shots": {}}, None

    bgm = (mixcfg.get("bgm") or {}) if isinstance(mixcfg, dict) else {}
    bgm_path = _sfx.resolve(bgm.get("ref")) if (_sfx and bgm.get("ref")) else None
    if bgm_path:
        idx = len(inputs) + 1
        inputs.append({"path": bgm_path, "loop": True})
        vol = float(bgm.get("volume") or 0.22)
        fi = max(min(float(bgm.get("fade_in") or 0.8), total_dur), 0.0)
        fo = max(min(float(bgm.get("fade_out") or 2.0), total_dur), 0.0)
        filters.append(
            f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol},"
            f"atrim=0:{total_dur:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fi},afade=t=out:st={max(total_dur - fo, 0):.3f}:d={fo}[bgm]")
        mix_inputs.append("[bgm]")

    if _sfx:
        for k, (s, st) in enumerate(zip(segs, shot_starts)):
            item = (mixcfg.get("shots") or {}).get(str(s["idx"])) or {}
            p = _sfx.resolve(item.get("ref")) if item.get("ref") else None
            if not p:
                continue
            idx = len(inputs) + 1
            inputs.append({"path": p})
            vol = float(item.get("volume") or 0.6)
            off = max(float(item.get("offset") or 0), 0.0)
            start = st + off
            name = f"fx{k}"
            filters.append(
                f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol},"
                f"adelay={int(start * 1000)}|{int(start * 1000)},"
                f"atrim=0:{start + s['dur']:.3f},asetpts=PTS-STARTPTS[{name}]")
            mix_inputs.append(f"[{name}]")

    if mix_inputs:
        head = ";".join(filters)
        fc = (head + ";" if head else "") + "".join(mix_inputs) + \
             f"amix=inputs={len(mix_inputs)}:duration=longest:normalize=0[mixout]"
        mixed = export_dir / f"final_ep{eid}_mix.mp4"
        cmd = [str(FFMPEG), "-y", "-i", str(novoice)]
        for it in inputs:
            if it.get("loop"):
                cmd += ["-stream_loop", "-1"]
            cmd += ["-i", str(it["path"])]
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[mixout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(mixed)]
        _run_ff(cmd, "音频分轨混音（台词" +
                (f" + BGM" if bgm_path else "") +
                (f" + {len(mix_inputs) - n - (1 if bgm_path else 0)} 条贴片音" if len(mix_inputs) > n + (1 if bgm_path else 0) else "") +
                "）")
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
