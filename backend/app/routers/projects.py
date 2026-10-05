"""短片项目：剧本、角色与场景、分镜、批量生成与成片导出。"""
from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Asset, Board, Project, ProjectElement, Provider, Shot, Task, User, utcnow
from ..services import policy, storyboard
from ..services import tasks as task_runner
from ..services.openai_compat import ProviderError
from ..site import get_setting
from ..timeutil import iso
from .assets import asset_out

router = APIRouter(prefix="/api/projects", tags=["projects"])

KINDS = ("chat", "image", "video", "tts")
DEFAULT_SIZES = {
    "16:9": ("1536x1024", "1280x720"), "9:16": ("1024x1536", "720x1280"), "1:1": ("1024x1024", "1024x1024"),
    "4:3": ("1536x1152", "1024x768"), "3:4": ("1152x1536", "768x1024"),
}


# ---------------------------------------------------------------- 输出


def _task_states(db: Session, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    return {t.id: {"id": t.id, "status": t.status, "progress": t.progress or 0, "error": t.error}
            for t in db.query(Task).filter(Task.id.in_(ids)).all()}


def project_out(db: Session, p: Project, detail: bool = False) -> dict[str, Any]:
    settings = dict(p.settings or {})
    settings.pop("srt", None)
    shots_q = db.query(Shot).filter(Shot.project_id == p.id)
    data: dict[str, Any] = {
        "id": p.id, "name": p.name, "synopsis": p.synopsis, "style": p.style, "aspect": p.aspect, "settings": settings,
        "shot_count": shots_q.count(), "has_srt": bool((p.settings or {}).get("srt")),
        "created_at": iso(p.created_at),
        "updated_at": iso(p.updated_at),
    }
    asset_ids: set[int] = set()
    shots = shots_q.order_by(Shot.idx, Shot.id).all() if detail else []
    elements = db.query(ProjectElement).filter(ProjectElement.project_id == p.id).order_by(ProjectElement.id).all() if detail else []
    cover = next((s.keyframe_asset_id for s in shots_q.order_by(Shot.idx, Shot.id).all() if s.keyframe_asset_id), None)
    for s in shots:
        asset_ids |= {x for x in (s.keyframe_asset_id, s.video_asset_id, s.audio_asset_id) if x}
    asset_ids |= {e.ref_asset_id for e in elements if e.ref_asset_id}
    asset_ids |= {x for x in (p.output_asset_id, cover) if x}
    assets = {a.id: asset_out(a) for a in db.query(Asset).filter(Asset.id.in_(asset_ids)).all()} if asset_ids else {}
    data["cover"] = assets.get(cover)
    data["output"] = assets.get(p.output_asset_id) if p.output_asset_id else None
    if not detail:
        return data
    task_ids = [t for s in shots for t in (s.tasks or {}).values()] + [e.task_id for e in elements if e.task_id]
    render_id = (p.settings or {}).get("render_task_id")
    if render_id:
        task_ids.append(render_id)
    states = _task_states(db, [int(t) for t in task_ids if t])
    data["script"] = p.script
    data["render_task"] = states.get(render_id) if render_id else None
    data["elements"] = [
        {"id": e.id, "kind": e.kind, "name": e.name, "description": e.description, "prompt": e.prompt,
         "ref": assets.get(e.ref_asset_id), "task": states.get(e.task_id) if e.task_id else None}
        for e in elements
    ]
    data["shots"] = [
        {
            "id": s.id, "idx": s.idx, "title": s.title, "description": s.description, "camera": s.camera,
            "dialogue": s.dialogue, "duration": s.duration, "element_ids": s.element_ids or [],
            "image_prompt": s.image_prompt, "video_prompt": s.video_prompt,
            "keyframe": assets.get(s.keyframe_asset_id), "video": assets.get(s.video_asset_id), "audio": assets.get(s.audio_asset_id),
            "tasks": {k: states.get(int(v)) for k, v in (s.tasks or {}).items() if v and states.get(int(v))},
        }
        for s in shots
    ]
    return data


def _get(db: Session, pid: int, user: User) -> Project:
    p = db.get(Project, pid)
    if p is None or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="项目不存在")
    return p


def _touch(p: Project) -> None:
    p.updated_at = utcnow()


# ---------------------------------------------------------------- 项目


class ProjectIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    synopsis: str | None = Field(None, max_length=20000)
    script: str | None = Field(None, max_length=200000)
    style: str | None = Field(None, max_length=2000)
    aspect: Literal["16:9", "9:16", "1:1", "4:3", "3:4"] | None = None
    settings: dict[str, Any] | None = None


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Project).filter(Project.user_id == user.id).order_by(Project.updated_at.desc()).all()
    return [project_out(db, p) for p in rows]


@router.post("")
def create_project(body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    aspect = body.aspect or "16:9"
    settings: dict[str, Any] = {"subtitles": True}
    for kind in KINDS:
        settings[f"{kind}_provider_id"] = get_setting(db, f"default_{kind}_provider_id")
        settings[f"{kind}_model"] = get_setting(db, f"default_{kind}_model") or ""
    settings["image_size"], settings["video_size"] = DEFAULT_SIZES[aspect]
    settings.update(body.settings or {})
    p = Project(user_id=user.id, name=(body.name or "未命名短片").strip(), synopsis=body.synopsis or "",
                script=body.script or "", style=body.style or "", aspect=aspect, settings=settings)
    db.add(p)
    db.flush()
    board = Board(user_id=user.id, name=f"短片·{p.name}"[:64])
    db.add(board)
    db.flush()
    p.settings = {**settings, "board_id": board.id}
    db.commit()
    return project_out(db, p, detail=True)


@router.get("/{pid}")
def get_project(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return project_out(db, _get(db, pid, user), detail=True)


@router.patch("/{pid}")
def update_project(pid: int, body: ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    for field in ("name", "synopsis", "script", "style", "aspect"):
        value = getattr(body, field)
        if value is not None:
            setattr(p, field, value.strip() if field == "name" else value)
    if body.settings is not None:
        allowed = {f"{k}_{x}" for k in KINDS for x in ("provider_id", "model")} | {"image_size", "video_size", "voice", "use_refs", "subtitles", "minutes"}
        p.settings = {**(p.settings or {}), **{k: v for k, v in body.settings.items() if k in allowed}}
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


@router.delete("/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """删除项目；已生成的作品保留在作品库（项目作品集中）。"""
    db.delete(_get(db, pid, user))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- AI 编剧


def _model(db: Session, p: Project, user: User, kind: str) -> tuple[Provider, str]:
    st = p.settings or {}
    pid = st.get(f"{kind}_provider_id") or get_setting(db, f"default_{kind}_provider_id")
    model = st.get(f"{kind}_model") or get_setting(db, f"default_{kind}_model") or ""
    provider = db.get(Provider, pid) if pid else None
    label = {"chat": "对话", "image": "图像", "video": "视频", "tts": "语音"}[kind]
    if provider is None or not provider.enabled or not model:
        raise HTTPException(status_code=400, detail=f"请先在项目设置中选择{label}模型")
    policy.check_access(db, user, kind, provider.id, model)
    return provider, model


class ScriptIn(BaseModel):
    synopsis: str = Field(..., min_length=1, max_length=20000)
    minutes: float = Field(1.0, ge=0.25, le=10)


@router.post("/{pid}/ai/script")
async def ai_script(pid: int, body: ScriptIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    provider, model = _model(db, p, user, "chat")
    policy.check_quota(db, user, "chat")
    try:
        script = await storyboard.write_script(provider, model, body.synopsis, body.minutes)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    policy.record_usage(db, user.id, "chat", provider.id, model, 1, policy.estimate_tokens(body.synopsis), policy.estimate_tokens(script), estimated=True)
    p.synopsis = body.synopsis
    p.script = script
    _touch(p)
    db.commit()
    return {"script": script}


@router.post("/{pid}/ai/elements")
async def ai_elements(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """从剧本中提取角色与场景（已存在同名的跳过）。"""
    p = _get(db, pid, user)
    if not p.script.strip():
        raise HTTPException(status_code=400, detail="请先填写剧本")
    provider, model = _model(db, p, user, "chat")
    policy.check_quota(db, user, "chat")
    try:
        items = await storyboard.extract_elements(provider, model, p.script)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    policy.record_usage(db, user.id, "chat", provider.id, model, 1, policy.estimate_tokens(p.script), 500, estimated=True)
    existing = {e.name for e in db.query(ProjectElement).filter(ProjectElement.project_id == p.id).all()}
    added = 0
    for it in items:
        if it["name"] in existing:
            continue
        db.add(ProjectElement(project_id=p.id, **it))
        existing.add(it["name"])
        added += 1
    _touch(p)
    db.commit()
    return {"added": added, "project": project_out(db, p, detail=True)}


class StoryboardIn(BaseModel):
    replace: bool = True
    max_shots: int = Field(16, ge=1, le=60)


@router.post("/{pid}/ai/storyboard")
async def ai_storyboard(pid: int, body: StoryboardIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    if not p.script.strip():
        raise HTTPException(status_code=400, detail="请先填写剧本")
    provider, model = _model(db, p, user, "chat")
    policy.check_quota(db, user, "chat")
    elements = db.query(ProjectElement).filter(ProjectElement.project_id == p.id).all()
    try:
        shots = await storyboard.split_shots(provider, model, p.script, [e.name for e in elements], body.max_shots)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    policy.record_usage(db, user.id, "chat", provider.id, model, 1, policy.estimate_tokens(p.script), 800, estimated=True)
    by_name = {e.name: e.id for e in elements}
    if body.replace:
        db.query(Shot).filter(Shot.project_id == p.id).delete()
        start = 0
    else:
        start = (db.query(Shot).filter(Shot.project_id == p.id).count())
    for i, s in enumerate(shots):
        names = s.pop("elements")
        db.add(Shot(project_id=p.id, idx=start + i, element_ids=[by_name[n] for n in names if n in by_name], **s))
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


# ---------------------------------------------------------------- 角色与场景


class ElementIn(BaseModel):
    kind: Literal["character", "scene", "prop"] = "character"
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field("", max_length=2000)
    prompt: str = Field("", max_length=4000)
    ref_asset_id: int | None = None


def _element(db: Session, p: Project, eid: int) -> ProjectElement:
    e = db.get(ProjectElement, eid)
    if e is None or e.project_id != p.id:
        raise HTTPException(status_code=404, detail="角色或场景不存在")
    return e


def _own_asset(db: Session, user: User, aid: int | None, kind: str | None = None) -> int | None:
    if not aid:
        return None
    a = db.get(Asset, aid)
    if a is None or a.user_id != user.id or (kind and a.kind != kind):
        raise HTTPException(status_code=400, detail="作品不存在")
    return a.id


@router.post("/{pid}/elements")
def create_element(pid: int, body: ElementIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    data = body.model_dump()
    data["ref_asset_id"] = _own_asset(db, user, body.ref_asset_id, "image")
    db.add(ProjectElement(project_id=p.id, **data))
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


@router.patch("/{pid}/elements/{eid}")
def update_element(pid: int, eid: int, body: ElementIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    e = _element(db, p, eid)
    for k, v in body.model_dump().items():
        setattr(e, k, _own_asset(db, user, v, "image") if k == "ref_asset_id" else v)
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


@router.delete("/{pid}/elements/{eid}")
def delete_element(pid: int, eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    e = _element(db, p, eid)
    for s in db.query(Shot).filter(Shot.project_id == p.id).all():
        if e.id in (s.element_ids or []):
            s.element_ids = [x for x in s.element_ids if x != e.id]
    db.delete(e)
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


def _submit(db: Session, user: User, kind: str, provider: Provider, model: str, prompt: str, params: dict[str, Any]) -> Task:
    policy.check_quota(db, user, kind)
    task = Task(user_id=user.id, kind=kind, status="pending", provider_id=provider.id, model=model, prompt=prompt, params=params)
    db.add(task)
    db.flush()
    return task


@router.post("/{pid}/elements/{eid}/generate")
async def generate_element(pid: int, eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """为角色 / 场景生成参考图（角色为全身设定图，场景为空镜）。"""
    p = _get(db, pid, user)
    e = _element(db, p, eid)
    provider, model = _model(db, p, user, "image")
    if e.kind == "character":
        prompt = f"角色设定图，{e.name}，{e.prompt or e.description}，全身站立，正面，纯色背景，清晰的面部与服装细节"
        size = "1024x1024"
    else:
        prompt = f"{e.prompt or e.description}，空镜，无人物"
        size = (p.settings or {}).get("image_size") or "1536x1024"
    if p.style:
        prompt += f"，{p.style}"
    task = _submit(db, user, "image", provider, model, prompt, {"n": 1, "size": size, "element_id": e.id, "project_id": p.id,
                                                                  "board_id": (p.settings or {}).get("board_id")})
    e.task_id = task.id
    db.commit()
    task_runner.submit(task.id)
    return project_out(db, p, detail=True)


# ---------------------------------------------------------------- 分镜


class ShotIn(BaseModel):
    title: str = Field("", max_length=128)
    description: str = Field("", max_length=4000)
    camera: str = Field("", max_length=255)
    dialogue: str = Field("", max_length=2000)
    duration: float = Field(4.0, ge=1, le=60)
    element_ids: list[int] = Field(default_factory=list)
    image_prompt: str = Field("", max_length=4000)
    video_prompt: str = Field("", max_length=4000)
    keyframe_asset_id: int | None = None
    video_asset_id: int | None = None
    audio_asset_id: int | None = None
    after_id: int | None = None  # 新建时插入到该镜头之后


def _shot(db: Session, p: Project, sid: int) -> Shot:
    s = db.get(Shot, sid)
    if s is None or s.project_id != p.id:
        raise HTTPException(status_code=404, detail="镜头不存在")
    return s


def _renumber(db: Session, p: Project, ordered: list[Shot]) -> None:
    for i, s in enumerate(ordered):
        s.idx = i


def _apply_shot(db: Session, user: User, p: Project, s: Shot, body: ShotIn) -> None:
    valid = {e.id for e in db.query(ProjectElement).filter(ProjectElement.project_id == p.id).all()}
    for k in ("title", "description", "camera", "dialogue", "duration", "image_prompt", "video_prompt"):
        setattr(s, k, getattr(body, k))
    s.element_ids = [x for x in body.element_ids if x in valid]
    s.keyframe_asset_id = _own_asset(db, user, body.keyframe_asset_id, "image")
    s.video_asset_id = _own_asset(db, user, body.video_asset_id, "video")
    s.audio_asset_id = _own_asset(db, user, body.audio_asset_id, "audio")


@router.post("/{pid}/shots")
def create_shot(pid: int, body: ShotIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    ordered = db.query(Shot).filter(Shot.project_id == p.id).order_by(Shot.idx, Shot.id).all()
    s = Shot(project_id=p.id)
    _apply_shot(db, user, p, s, body)
    db.add(s)
    pos = len(ordered)
    if body.after_id is not None:
        pos = next((i + 1 for i, x in enumerate(ordered) if x.id == body.after_id), len(ordered))
    ordered.insert(pos, s)
    _renumber(db, p, ordered)
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


@router.put("/{pid}/shots/{sid}")
def update_shot(pid: int, sid: int, body: ShotIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    _apply_shot(db, user, p, _shot(db, p, sid), body)
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


@router.delete("/{pid}/shots/{sid}")
def delete_shot(pid: int, sid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    db.delete(_shot(db, p, sid))
    db.flush()
    _renumber(db, p, db.query(Shot).filter(Shot.project_id == p.id).order_by(Shot.idx, Shot.id).all())
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


class ReorderIn(BaseModel):
    ids: list[int]


@router.post("/{pid}/shots/reorder")
def reorder_shots(pid: int, body: ReorderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    shots = {s.id: s for s in db.query(Shot).filter(Shot.project_id == p.id).all()}
    if set(body.ids) != set(shots):
        raise HTTPException(status_code=400, detail="镜头列表不匹配")
    _renumber(db, p, [shots[i] for i in body.ids])
    _touch(p)
    db.commit()
    return project_out(db, p, detail=True)


Slot = Literal["keyframe", "video", "audio"]


def _shot_prompt(db: Session, p: Project, s: Shot) -> tuple[str, list[int]]:
    """组合关键帧提示词：镜头画面 + 出场角色 / 场景的外观描述 + 统一风格；返回提示词与参考图。"""
    els = {e.id: e for e in db.query(ProjectElement).filter(ProjectElement.id.in_(s.element_ids or [])).all()}
    parts = [s.image_prompt or s.description]
    refs: list[int] = []
    for eid in s.element_ids or []:
        e = els.get(eid)
        if e is None:
            continue
        if e.prompt or e.description:
            parts.append(f"{e.name}：{e.prompt or e.description}")
        if e.ref_asset_id and e.kind == "character":
            refs.append(e.ref_asset_id)
    if s.camera:
        parts.append(s.camera)
    if p.style:
        parts.append(p.style)
    return "，".join(x.strip("，。 ") for x in parts if x and x.strip()), refs[:4]


def _generate_slot(db: Session, user: User, p: Project, s: Shot, slot: str) -> Task | None:
    st = p.settings or {}
    base = {"project_id": p.id, "shot_id": s.id, "slot": slot, "board_id": st.get("board_id")}
    if slot == "keyframe":
        provider, model = _model(db, p, user, "image")
        prompt, refs = _shot_prompt(db, p, s)
        if not prompt:
            raise HTTPException(status_code=400, detail=f"镜头 {s.idx + 1} 缺少画面描述")
        params = {**base, "n": 1, "size": st.get("image_size") or DEFAULT_SIZES[p.aspect][0]}
        if refs and st.get("use_refs"):
            params["reference_asset_ids"] = refs
        task = _submit(db, user, "image", provider, model, prompt, params)
    elif slot == "video":
        provider, model = _model(db, p, user, "video")
        prompt = "，".join(x for x in (s.video_prompt or s.description, s.camera, p.style) if x)
        if not prompt:
            raise HTTPException(status_code=400, detail=f"镜头 {s.idx + 1} 缺少画面描述")
        params = {**base, "size": st.get("video_size") or DEFAULT_SIZES[p.aspect][1], "seconds": int(round(s.duration))}
        if s.keyframe_asset_id:
            params["reference_asset_ids"] = [s.keyframe_asset_id]  # 以关键帧作为首帧
        task = _submit(db, user, "video", provider, model, prompt, params)
    else:
        if not s.dialogue.strip():
            return None
        provider, model = _model(db, p, user, "tts")
        text = s.dialogue.split("：", 1)[1] if s.dialogue.startswith(("旁白：", "旁白:")) else s.dialogue
        params = {**base, "format": "mp3"}
        if st.get("voice"):
            params["voice"] = st["voice"]
        task = _submit(db, user, "tts", provider, model, text.strip(), params)
    s.tasks = {**(s.tasks or {}), slot: task.id}
    return task


class GenerateIn(BaseModel):
    slot: Slot
    shot_ids: list[int] | None = None  # 为空表示全部镜头
    only_missing: bool = True  # 只生成还没有结果的镜头


@router.post("/{pid}/generate")
async def generate(pid: int, body: GenerateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    shots = db.query(Shot).filter(Shot.project_id == p.id).order_by(Shot.idx, Shot.id).all()
    if body.shot_ids is not None:
        shots = [s for s in shots if s.id in set(body.shot_ids)]
    active = {t.id for t in db.query(Task.id).filter(Task.user_id == user.id, Task.status.in_(task_runner.ACTIVE)).all()}
    created: list[Task] = []
    for s in shots:
        if (s.tasks or {}).get(body.slot) in active:
            continue  # 正在生成
        if body.only_missing and getattr(s, f"{body.slot}_asset_id"):
            continue
        task = _generate_slot(db, user, p, s, body.slot)
        if task is not None:
            created.append(task)
    _touch(p)
    db.commit()
    for t in created:
        task_runner.submit(t.id)
    return {"created": len(created), "project": project_out(db, p, detail=True)}


@router.post("/{pid}/render")
async def render_project(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.render import ffmpeg_available

    p = _get(db, pid, user)
    if not ffmpeg_available():
        raise HTTPException(status_code=400, detail="服务器未安装 FFmpeg，无法合成成片（官方 Docker 镜像已内置）")
    if not db.query(Shot).filter(Shot.project_id == p.id, (Shot.keyframe_asset_id.isnot(None)) | (Shot.video_asset_id.isnot(None))).first():
        raise HTTPException(status_code=400, detail="还没有可用的镜头：请先生成关键帧或视频")
    task = Task(user_id=user.id, kind="render", status="pending", provider_id=None, model="FFmpeg", prompt=f"成片：{p.name}",
                params={"project_id": p.id, "board_id": (p.settings or {}).get("board_id")})
    db.add(task)
    db.flush()
    p.settings = {**(p.settings or {}), "render_task_id": task.id}
    _touch(p)
    db.commit()
    task_runner.submit(task.id)
    return project_out(db, p, detail=True)


@router.get("/{pid}/subtitles.srt", response_class=PlainTextResponse)
def subtitles(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _get(db, pid, user)
    srt = (p.settings or {}).get("srt") or ""
    if not srt:
        from ..services.render import build_srt

        t, items = 0.0, []
        for s in db.query(Shot).filter(Shot.project_id == p.id).order_by(Shot.idx, Shot.id).all():
            items.append((t, t + s.duration, s.dialogue))
            t += s.duration
        srt = build_srt(items)
    return PlainTextResponse(srt, media_type="application/x-subrip; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(p.name)}.srt"})


@router.get("/{pid}/export.md", response_class=PlainTextResponse)
def export_storyboard(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """导出分镜脚本（Markdown 表格）。"""
    p = _get(db, pid, user)
    rows = db.query(Shot).filter(Shot.project_id == p.id).order_by(Shot.idx, Shot.id).all()
    els = {e.id: e.name for e in db.query(ProjectElement).filter(ProjectElement.project_id == p.id).all()}
    esc = lambda x: (x or "").replace("|", "\\|").replace("\n", "<br>")  # noqa: E731
    lines = [f"# {p.name}", "", p.synopsis, "", "| # | 画面 | 景别 / 运镜 | 台词 / 旁白 | 时长 | 出场 |", "|---|---|---|---|---|---|"]
    for i, s in enumerate(rows, 1):
        lines.append(f"| {i} | {esc(s.description)} | {esc(s.camera)} | {esc(s.dialogue)} | {s.duration:g}s | {'、'.join(els.get(x, '') for x in s.element_ids or [])} |")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(p.name)}.md"})
