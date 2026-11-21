"""可编辑提示词模板引擎（源码级借鉴 ArcReel prompt_templates/engine.py + Jellyfish PromptTemplate 表）。

设计要点（照搬源码里的硬规矩）：
1. 模板按 stage 分类（asset_character / asset_scene / asset_prop / shot_first_frame /
   shot_end_frame / shot_video），前端可改，系统预置模板 is_system=True 不允许删除；
2. 同一 stage 至多一条 is_default；
3. 模板只写措辞，变量由代码计算好后注入（避免 LLM 自由发挥导致随机性）；
4. 渲染走 Jinja2 沙箱，未定义变量渲染为空，渲染后清理多余逗号与空白；
5. 每个 stage 配一条负面提示词基线（Jellyfish DEFAULT_VIDEO_NEGATIVE_PROMPT 同类）。
"""
from __future__ import annotations

import json
import re

from jinja2 import Environment, StrictUndefined, BaseLoader
from jinja2.sandbox import SandboxedEnvironment

_env: Environment = SandboxedEnvironment(loader=BaseLoader(), undefined=StrictUndefined,
                                        autoescape=False, trim_blocks=True,
                                        lstrip_blocks=True)

STAGES = {
    "asset_character": "角色资产图",
    "asset_scene": "场景资产图",
    "asset_prop": "道具资产图",
    "shot_first_frame": "镜头首帧",
    "shot_end_frame": "镜头尾帧",
    "shot_video": "镜头视频",
}

# 负面基线（按 stage）：Jellyfish 原文「不要新增无关人物；不要改变角色身份、服装颜色和场景地点」
NEG_BASE = {
    "shot_first_frame": ("extra people, new characters, changed identity, different costume color, "
                         "changed location, text, watermark, deformed limbs, extra fingers"),
    "shot_end_frame": ("extra people, new characters, changed identity, different costume color, "
                       "changed location, text, watermark, deformed limbs"),
    "shot_video": ("extra people, identity change, costume color change, location change, "
                   "text, watermark, limb distortion, camera jump cut, flickering, "
                   "morphing, warping faces, sliding feet, sudden speed changes, "
                   "duplicated limbs, jittery motion"),
    "asset_scene": ("people, person, human figure, silhouette, reflection of a person, "
                    "portrait in a frame, hands, text, watermark"),
    "asset_prop": ("people, hands, fingers, model, busy background, pattern background, "
                   "text, watermark"),
    "asset_character": ("two people, multiple characters, text, watermark, deformed hands, "
                        "extra limbs"),
}

SYSTEM_TEMPLATES: dict[str, tuple[str, str]] = {
    "shot_first_frame": (
        "镜头首帧（默认）",
        "{{ style_lock }}{% if vocab %}, {{ vocab }}{% endif %}{% if scene %}, {{ scene }}{% endif %}"
        "{% if characters %}, {{ characters }}{% endif %}"
        "{% if props %}, {{ props }}{% endif %}"
        "{% if action %}, {{ action }}{% endif %}"
        "{% if motion %}, {{ motion }}{% endif %}"
        "{% if atmosphere %}, atmosphere: {{ atmosphere }}{% endif %}"
        "{% if prev %}, {{ prev }}{% endif %}"
        "{% if framing %}, {{ framing }}{% endif %}"
        "{% if angle %}, {{ angle }}{% endif %}"
        "{% if lens %}, {{ lens }}{% endif %}"
        "{% if light %}, lighting: {{ light }}{% endif %}"
        "{% if composition %}, {{ composition }}{% endif %}"
        "{% if lifelike %}, {{ lifelike }}{% endif %}"
        "{% if quality %}, {{ quality }}{% endif %}",
    ),
    "shot_end_frame": (
        "镜头尾帧（默认）",
        "{{ style_lock }}{% if vocab %}, {{ vocab }}{% endif %}{% if scene %}, {{ scene }}{% endif %}"
        "{% if characters %}, {{ characters }}{% endif %}"
        "{% if props %}, {{ props }}{% endif %}"
        "{% if end_action %}, final pose after the action: {{ end_action }}{% endif %}"
        "{% if motion %}, {{ motion }}{% endif %}"
        "{% if prev %}, {{ prev }}{% endif %}"
        "{% if framing_end %}, {{ framing_end }}{% endif %}"
        "{% if composition %}, {{ composition }}{% endif %}"
        "{% if lifelike %}, {{ lifelike }}{% endif %}"
        "{% if quality %}, {{ quality }}{% endif %}",
    ),
    "shot_video": (
        "镜头视频（默认：I2V 公式——图定义实体，文只管运动）",
        "{{ style_lock }}{% if vocab %}, {{ vocab }}{% endif %}{% if scene %}, {{ scene }}{% endif %}"
        "{% if beats %}, action beats: {{ beats }}{% endif %}"
        "{% if motion_cues %}, subject motion: {{ motion_cues }}{% endif %}"
        "{% if camera %}, camera: {{ camera }}{% endif %}"
        "{% if motion_constraints %}, {{ motion_constraints }}{% endif %}"
        "{% if blocking %}, blocking: {{ blocking }}{% endif %}"
        "{% if character_path %}, character movement: {{ character_path }}{% endif %}"
        "{% if focus %}, focus: {{ focus }}{% endif %}"
        "{% if prev %}, {{ prev }}{% endif %}"
        "{% if continuity %}, continuity: {{ continuity }}{% endif %}"
        "{% if duration %}, {{ duration }}s single continuous take{% endif %}"
        "{% if lifelike %}, {{ lifelike }}{% endif %}"
        "{% if quality %}, {{ quality }}{% endif %}",
    ),
    "asset_character": (
        "角色资产图（默认）",
        "{{ style_lock }}{% if spec %}, {{ spec }}{% endif %}"
        "{% if identity %}, {{ identity }}{% endif %}"
        "{% if appearance %}, {{ appearance }}{% endif %}"
        "{% if hair %}, {{ hair }}{% endif %}"
        "{% if clothing %}, {{ clothing }}{% endif %}"
        "{% if accessories %}, accessories: {{ accessories }}{% endif %}"
        "{% if expression %}, {{ expression }}{% endif %}"
        "{% if palette %}, color palette: {{ palette }}{% endif %}"
        "{% if lifelike %}, {{ lifelike }}{% endif %}"
        "{% if quality %}, {{ quality }}{% endif %}",
    ),
    "asset_scene": (
        "场景资产图（默认，强制空镜）",
        "{{ style_lock }}{% if space %}, {{ space }}{% endif %}"
        "{% if era %}, {{ era }}{% endif %}"
        "{% if elements %}, {{ elements }}{% endif %}"
        "{% if light %}, {{ light }}{% endif %}"
        "{% if mood %}, mood: {{ mood }}{% endif %}"
        "{% if empty_spec %}, {{ empty_spec }}{% endif %}"
        "{% if lifelike %}, {{ lifelike }}{% endif %}"
        "{% if quality %}, {{ quality }}{% endif %}",
    ),
    "asset_prop": (
        "道具资产图（默认，白底单品）",
        "{{ style_lock }}{% if subject %}, {{ subject }}{% endif %}"
        "{% if purpose %}, story function: {{ purpose }}{% endif %}"
        "{% if era %}, {{ era }}{% endif %}"
        "{% if details %}, {{ details }}{% endif %}"
        "{% if material %}, material & color: {{ material }}{% endif %}"
        "{% if prop_spec %}, {{ prop_spec }}{% endif %}"
        "{% if lifelike %}, {{ lifelike }}{% endif %}"
        "{% if quality %}, {{ quality }}{% endif %}",
    ),
}

_WS = re.compile(r"\s+")
_DUP_COMMA = re.compile(r",\s*,+")


def _tidy(text: str) -> str:
    """清理渲染结果：多余逗号、首尾逗号、连续空白。"""
    text = _DUP_COMMA.sub(",", text or "")
    text = _WS.sub(" ", text).strip()
    text = text.strip(", ").strip("，")
    return text


def render(content: str, variables: dict) -> str:
    """渲染模板；缺失变量渲染为空（Jellyfish `_render_template` 同款容错）。"""
    try:
        tmpl = _env.from_string(content)
        out = tmpl.render(**{k: (v if v is not None else "") for k, v in variables.items()})
        return _tidy(out)
    except Exception:
        # 模板写坏了不能让整条链路挂：回退到变量值顺序拼接
        return _tidy(", ".join(str(v) for v in variables.values() if v))


def neg_for(stage: str, extra: str = "") -> str:
    base = NEG_BASE.get(stage, "")
    return ", ".join(x for x in (base, extra) if x)


def seed_templates(db, project_id: int | None = None):
    """写入/同步系统预置模板（幂等）。系统模板只读，随代码版本覆盖，保证升级即生效。"""
    from ..db import PromptTemplate
    from sqlalchemy import select

    for stage, (name, content) in SYSTEM_TEMPLATES.items():
        existing = db.scalars(select(PromptTemplate).where(
            PromptTemplate.project_id == project_id,
            PromptTemplate.stage == stage,
            PromptTemplate.is_system == 1)).first()
        if existing:
            if existing.content != content:
                existing.content = content
                existing.variables_json = json.dumps(sorted(_vars_of(content)),
                                                    ensure_ascii=False)
            if not existing.is_default and not db.scalars(select(PromptTemplate).where(
                    PromptTemplate.stage == stage,
                    PromptTemplate.project_id == project_id,
                    PromptTemplate.is_default == 1)).first():
                existing.is_default = 1
            continue
        db.add(PromptTemplate(
            project_id=project_id, stage=stage, name=name, content=content,
            variables_json=json.dumps(sorted(_vars_of(content)), ensure_ascii=False),
            is_default=1, is_system=1))
    db.commit()


def _vars_of(content: str) -> set[str]:
    return set(re.findall(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)", content or ""))


def resolve(db, project_id: int, stage: str, template_id: int | None = None):
    """取模板：指定 id > 项目默认 > 全局默认 > 内置兜底。返回 (content, template_id)。"""
    from ..db import PromptTemplate
    from sqlalchemy import select

    if template_id:
        row = db.get(PromptTemplate, template_id)
        if row:
            return row.content, row.id
    for scope in (project_id, None):
        row = db.scalars(select(PromptTemplate).where(
            PromptTemplate.stage == stage,
            PromptTemplate.is_default == 1,
            PromptTemplate.project_id == scope)).first()
        if row:
            return row.content, row.id
    return SYSTEM_TEMPLATES.get(stage, ("", "{{ style_lock }}"))[1], None
