"""SQLite + SQLAlchemy 初始化与 ORM 模型（M1 最小集，后续阶段扩展）。"""
import json
from datetime import datetime

from sqlalchemy import (Integer, String, Text, Float, DateTime, ForeignKey,
                        create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def now():
    return datetime.now()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    style_preset: Mapped[str] = mapped_column(String(40), default="anime_2d")  # 风格锁
    lifelike: Mapped[int] = mapped_column(Integer, default=1)      # 活人感提示词机制
    lifelike_full: Mapped[int] = mapped_column(Integer, default=0) # 全量瑕疵（含五官不完美，仅建议分镜用）
    auto_polish: Mapped[int] = mapped_column(Integer, default=1)   # 初图 10% 微调（按资产类型分级生效）
    grid_storyboard: Mapped[int] = mapped_column(Integer, default=1)  # 宫格故事板（仅动漫风格默认开）
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16")  # 全局画幅 16:9/21:9/4:3/1:1/3:4/9:16
    narrator_voice: Mapped[str] = mapped_column(String(80), default="")  # 旁白/无前缀台词音色（成片页锁定）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Character(Base):
    """角色：BaseLook 定妆照 + 衣橱（M1 先建主体）。prompt_json=结构化槽位。"""
    __tablename__ = "characters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    base_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_json: Mapped[str] = mapped_column(Text, default="{}")   # 槽位 {identity,appearance,hair,clothing,expression,palette}
    portrait_mode: Mapped[str] = mapped_column(String(20), default="sheet")  # sheet=三视图 / single=单人 / board=角色板
    gen_mode: Mapped[str] = mapped_column(String(24), default="auto")  # auto / compose(程序合成A) / board(角色板B) / layout(版式模型C)
    voice: Mapped[str] = mapped_column(String(80), default="")  # edge-tts 音色名（成片配音用；空=按性别自动分配）
    face_lock_path: Mapped[str] = mapped_column(Text, default="")  # 角色级默认脸锁：钉死 IPAdapter 参考版本（空=自动择优）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Scene(Base):
    """场景资产（BigBanana：概念图统一光影风格，跨镜头复用）。"""
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    base_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_json: Mapped[str] = mapped_column(Text, default="{}")   # 槽位 {space,era,elements,light,mood}
    anchor_path: Mapped[str] = mapped_column(Text, default="")     # 场景锚定图（缩略图法：镜头首帧注入此图锁环境一致性）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Prop(Base):
    """道具资产（可复用：独立提示词 + 参考图）。"""
    __tablename__ = "props"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    base_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_json: Mapped[str] = mapped_column(Text, default="{}")   # 槽位 {subject,purpose,era,details,material}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StashCandidate(Base):
    """候选暂存区（跨集资产复用）：拆解候选先暂存，后续集确认入库。
    脸不变原则：同名角色入库时跳过（脸部锁定），服饰/妆造变化走角色板变体。"""
    __tablename__ = "stash_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(20))          # character/scene/prop
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    slots_json: Mapped[str] = mapped_column(Text, default="{}")
    portrait_mode: Mapped[str] = mapped_column(String(20), default="sheet")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Episode(Base):
    """分集剧本（P1）：outline→script_text→breakdown。"""
    __tablename__ = "episodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=1)               # 第几集
    title: Mapped[str] = mapped_column(String(300), default="")
    outline: Mapped[str] = mapped_column(Text, default="")             # 本集大纲/梗概
    script_text: Mapped[str] = mapped_column(Text, default="")         # 剧本正文
    status: Mapped[str] = mapped_column(String(30), default="draft")   # draft/script/broken_down
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AssetImage(Base):
    """生成的/导入的图片资产。kind: base_look / wardrobe / scene / prop / grid9 ..."""
    __tablename__ = "asset_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    character_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id"),
                                                     nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    prompt: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Shot(Base):
    """镜头卡（故事板数据层）：一条=一个可生成单元，喂首帧/尾帧/视频。
    动态字段（计划 A/B/C 落地）：运镜向量、人物轨迹、起落幅、焦点变化、needs_end_frame。
    M2.6 源码级增强：动作拍点、氛围、视效、模板绑定、轴线/承接字段（Jellyfish ShotDetail 同构）。"""
    __tablename__ = "shots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=1)               # 本集内序号
    scene_no: Mapped[str] = mapped_column(String(20), default="")
    scene_name: Mapped[str] = mapped_column(String(200), default="")
    int_ext: Mapped[str] = mapped_column(String(10), default="")       # 内/外
    tod: Mapped[str] = mapped_column(String(10), default="")           # 日/夜
    duration: Mapped[int] = mapped_column(Integer, default=4)
    shot_size: Mapped[str] = mapped_column(String(20), default="中景")
    # —— 运镜向量 ——
    camera_move: Mapped[str] = mapped_column(String(40), default="固定")  # 固定/推/拉/横摇/移/跟/升降/环绕/手持
    camera_speed: Mapped[str] = mapped_column(String(20), default="normal")  # slow/normal/fast/whip
    camera_dir: Mapped[str] = mapped_column(String(24), default="")     # left/right/up/down/in/out
    framing_start: Mapped[str] = mapped_column(String(40), default="")  # 起幅景别
    framing_end: Mapped[str] = mapped_column(String(40), default="")    # 落幅景别
    camera_angle: Mapped[str] = mapped_column(String(40), default="")   # 平视/俯拍/仰拍/过肩/POV/航拍
    focal_length: Mapped[str] = mapped_column(String(20), default="")
    focus_transition: Mapped[str] = mapped_column(String(24), default="none")  # none/rack-focus/pull-focus/follow-focus
    blocking: Mapped[str] = mapped_column(Text, default="")             # 人物画面占位关系
    character_path: Mapped[str] = mapped_column(Text, default="")       # 人物活动轨迹（起→终）
    subject_action: Mapped[str] = mapped_column(Text, default="")
    light: Mapped[str] = mapped_column(Text, default="")
    composition: Mapped[str] = mapped_column(Text, default="")
    characters_json: Mapped[str] = mapped_column(Text, default="[]")
    props_json: Mapped[str] = mapped_column(Text, default="[]")
    dialogue: Mapped[str] = mapped_column(Text, default="")
    sfx: Mapped[str] = mapped_column(Text, default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")          # 首帧图提示词
    end_frame_prompt: Mapped[str] = mapped_column(Text, default="")      # 尾帧图提示词
    video_prompt: Mapped[str] = mapped_column(Text, default="")          # 视频（运动）提示词
    needs_end_frame: Mapped[int] = mapped_column(Integer, default=0)     # 位移/运镜镜=1
    # —— M2.6 新增（对齐 Jellyfish ShotDetail）——
    action_beats_json: Mapped[str] = mapped_column(Text, default="[]")   # [{text,phase}] 动作拍点
    atmosphere: Mapped[str] = mapped_column(Text, default="")
    mood_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    vfx_type: Mapped[str] = mapped_column(String(30), default="none")
    vfx_note: Mapped[str] = mapped_column(Text, default="")
    key_frame_prompt: Mapped[str] = mapped_column(Text, default="")      # 关键帧（峰值）提示词
    prompt_template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screen_direction: Mapped[str] = mapped_column(String(24), default="")
    composition_anchor: Mapped[str] = mapped_column(Text, default="")
    prev_summary: Mapped[str] = mapped_column(Text, default="")
    next_goal: Mapped[str] = mapped_column(Text, default="")
    continuity_guidance: Mapped[str] = mapped_column(Text, default="")
    ref_overrides_json: Mapped[str] = mapped_column(Text, default="{}")  # 手动指定参考：{"角色名": path, "__scene__": path}
    first_frame_path: Mapped[str] = mapped_column(Text, default="")
    end_frame_path: Mapped[str] = mapped_column(Text, default="")
    video_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="planned")   # planned/first_ready/end_ready/video_ready
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PromptTemplate(Base):
    """可编辑提示词模板（Jellyfish prompt_templates 表同构）。
    stage: asset_character/asset_scene/asset_prop/shot_first_frame/shot_end_frame/shot_video
    is_system=1 不允许删除；同 stage 至多一条 is_default。"""
    __tablename__ = "prompt_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # None=全局
    stage: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    variables_json: Mapped[str] = mapped_column(Text, default="[]")
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CharacterAppearance(Base):
    """角色造型变体（waoowaoo CharacterAppearance 同构）：脸锁死，服饰/妆造/饰品按集可换。
    face_lock=1 表示该变体必须复用同一张脸参考图（跨集一致性）。"""
    __tablename__ = "character_appearances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), index=True)
    episode_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")      # 造型名：如"雨夜便装"
    costume: Mapped[str] = mapped_column(Text, default="")
    makeup: Mapped[str] = mapped_column(Text, default="")
    accessories: Mapped[str] = mapped_column(Text, default="")
    hair: Mapped[str] = mapped_column(Text, default="")
    face_lock: Mapped[int] = mapped_column(Integer, default=1)
    face_ref_path: Mapped[str] = mapped_column(String(500), default="")
    ref_images_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class TaskRecord(Base):
    """统一异步任务（Jellyfish 范式）：状态机 pending→running→done/failed/cancelled。"""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(60), index=True)          # portrait / video / tts ...
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(200), default="")        # 当前阶段描述
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    model_key: Mapped[str] = mapped_column(String(120), default="")    # 实际使用的模型档位
    vram_gb: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def init_db():
    Base.metadata.create_all(engine)
    _migrate()


def _migrate():
    """轻量迁移：老库缺列时自动 ALTER TABLE ADD COLUMN。"""
    import sqlalchemy
    additions = {
        "projects": [
            ("style_preset", "VARCHAR(40) DEFAULT 'anime_2d'"),
            ("lifelike", "INTEGER DEFAULT 1"),
            ("lifelike_full", "INTEGER DEFAULT 0"),
            ("auto_polish", "INTEGER DEFAULT 1"),
            ("grid_storyboard", "INTEGER DEFAULT 1"),
            ("aspect_ratio", "VARCHAR(10) DEFAULT '9:16'"),
            ("narrator_voice", "VARCHAR(80) DEFAULT ''"),
        ],
        "characters": [
            ("prompt_json", "TEXT DEFAULT '{}'"),
            ("portrait_mode", "VARCHAR(20) DEFAULT 'sheet'"),
            ("gen_mode", "VARCHAR(24) DEFAULT 'auto'"),
            ("voice", "VARCHAR(80) DEFAULT ''"),
            ("face_lock_path", "TEXT DEFAULT ''"),   # 角色级默认脸锁：钉死 IPAdapter 参考版本，100% 一致性
        ],
        "scenes": [("prompt_json", "TEXT DEFAULT '{}'"),
                   ("anchor_path", "TEXT DEFAULT ''")],
        "props": [("prompt_json", "TEXT DEFAULT '{}'")],
        "shots": [
            ("action_beats_json", "TEXT DEFAULT '[]'"),
            ("atmosphere", "TEXT DEFAULT ''"),
            ("mood_tags_json", "TEXT DEFAULT '[]'"),
            ("vfx_type", "VARCHAR(30) DEFAULT 'none'"),
            ("vfx_note", "TEXT DEFAULT ''"),
            ("key_frame_prompt", "TEXT DEFAULT ''"),
            ("prompt_template_id", "INTEGER"),
            ("screen_direction", "VARCHAR(24) DEFAULT ''"),
            ("composition_anchor", "TEXT DEFAULT ''"),
            ("prev_summary", "TEXT DEFAULT ''"),
            ("next_goal", "TEXT DEFAULT ''"),
            ("continuity_guidance", "TEXT DEFAULT ''"),
            ("ref_overrides_json", "TEXT DEFAULT '{}'"),
        ],
    }
    with engine.connect() as conn:
        for table, cols in additions.items():
            existing = {row[1] for row in conn.execute(
                sqlalchemy.text(f"PRAGMA table_info({table})"))}
            for col, ddl in cols:
                if col not in existing:
                    conn.execute(sqlalchemy.text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        conn.commit()


def task_desc(type_: str, params: dict) -> str:
    """任务一句话中文描述（任务队列详细列表用）。"""
    p = params or {}
    eid = p.get("episode_id")
    ep = f"第{eid}集" if eid else ""
    try:
        n = int(p.get("num_episodes") or 0)
    except (TypeError, ValueError):
        n = 0
    from_ = p.get("from_idx")
    m = {
        "outline": lambda: f"生成分集大纲（{n or '?'} 集）",
        "continue_outline": lambda: f"续写分集大纲（{ep or '追加 10 集'}）",
        "script": lambda: f"写{ep}剧本",
        "breakdown": lambda: f"{ep}分镜拆解",
        "refine": lambda: "润色文本",
        "rebuild_slots": lambda: "重建资产槽位",
        "portrait": lambda: f"角色「{p.get('entity_name', '')}」定妆照（Qwen 整张版式）",
        "asset": lambda: f"生成资产（{p.get('entity_type', '')}）",
        "asset_compose": lambda: f"角色「{p.get('entity_name', '')}」三视图拼版",
        "ref_redraw": lambda: "实物参考图重绘",
        "upscale": lambda: "图片超分放大",
        "polish": lambda: "资产微调重生成",
        "shot_frame": lambda: f"镜头 #{p.get('shot_id', '?')} {p.get('frame_type', 'first')} 帧",
        "shot_video": lambda: f"镜头 #{p.get('shot_id', '?')} i2v 视频",
        "shot_talk": lambda: f"镜头 #{p.get('shot_id', '?')} 口型说话（InfiniteTalk，耗时较长）",
        "shot_chain": lambda: f"末帧接力首帧（承上一镜）",
        "shot_extend": lambda: f"镜头 #{p.get('shot_id', '?')} 镜内延长",
        "grid9": lambda: "九宫格故事板",
        "scene_anchor": lambda: "场景锚图补齐（45° iso 布局图→设锚）",
        "tts": lambda: f"{ep}台词配音（edge-tts）",
        "stitch": lambda: f"{ep}成片合成（拼接/混音/烧字幕）",
        "batch_frames": lambda: f"{ep}批量首帧（链式接力）",
        "batch_videos": lambda: f"{ep}批量视频",
        "rechain_from": lambda: f"{ep}向后重链（从 s{from_ or 1} 起）",
        "full_pipeline": lambda: f"{ep}一键全流程（首帧→视频→配音→成片）",
        "export_jianying": lambda: f"{ep}导出剪映草稿",
        "export_fcpxml": lambda: f"{ep}导出 FCPXML",
    }
    fn = m.get(type_)
    return fn() if fn else type_


def task_to_dict(t: TaskRecord) -> dict:
    return {
        "id": t.id, "type": t.type, "status": t.status, "progress": t.progress,
        "stage": t.stage, "desc": task_desc(t.type, json.loads(t.params_json or "{}")),
        "params": json.loads(t.params_json or "{}"),
        "result": json.loads(t.result_json or "{}"), "error": t.error,
        "model_key": t.model_key, "vram_gb": t.vram_gb,
        "created_at": str(t.created_at),
    }
