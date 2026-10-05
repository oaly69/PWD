from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Asset, Provider, Task, User
from ..services import policy
from ..services import tasks as task_runner
from ..site import get_setting
from .assets import asset_out

router = APIRouter(prefix="/api", tags=["generate"])

Kind = Literal["image", "video", "tts"]
MODEL_FIELD = {"image": "image_models", "video": "video_models", "tts": "tts_models"}
KIND_LABEL = {"image": "图像", "video": "视频", "tts": "语音"}


class GenerateIn(BaseModel):
    provider_id: int | None = None
    model: str | None = None
    prompt: str = Field(..., min_length=1, max_length=20000)
    negative_prompt: str = ""
    size: str | None = None
    n: int = Field(1, ge=1, le=8)
    seed: int | None = None
    steps: int | None = Field(None, ge=1, le=200)
    seconds: int | None = Field(None, ge=1, le=60)  # 视频时长
    voice: str | None = None  # 语音
    speed: float | None = Field(None, ge=0.25, le=4)
    format: str | None = None
    instructions: str | None = None
    style: str | None = None  # 风格预设名称
    style_prompt: str | None = Field(None, max_length=2000)  # 执行时追加到提示词末尾
    style_negative: str | None = Field(None, max_length=2000)
    reference_asset_ids: list[int] = Field(default_factory=list, max_length=8)
    extra_body: dict[str, Any] | None = None


def task_out(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "kind": t.kind,
        "status": t.status,
        "progress": t.progress or 0,
        "provider_id": t.provider_id,
        "model": t.model,
        "prompt": t.prompt,
        "params": t.params or {},
        "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "assets": [asset_out(a) for a in t.assets],
    }


def _create_task(db: Session, kind: str, body: GenerateIn, user: User) -> Task:
    provider_id = body.provider_id or get_setting(db, f"default_{kind}_provider_id")
    model = body.model or get_setting(db, f"default_{kind}_model") or ""
    provider = db.get(Provider, provider_id) if provider_id else None
    if provider is None:
        raise HTTPException(status_code=400, detail=f"请先选择{KIND_LABEL[kind]}模型服务")
    if not provider.enabled:
        raise HTTPException(status_code=400, detail="该模型服务已停用")
    if not model:
        raise HTTPException(status_code=400, detail=f"请先选择{KIND_LABEL[kind]}模型")
    if kind == "tts" and provider.kind != "openai":
        raise HTTPException(status_code=400, detail="语音合成仅支持 OpenAI 兼容接口")
    policy.check_access(db, user, kind, provider.id, model)
    policy.check_quota(db, user, kind, body.n if kind == "image" else 1)
    for aid in body.reference_asset_ids:
        ref = db.get(Asset, aid)
        if ref is None or ref.kind != "image" or ref.user_id != user.id:
            raise HTTPException(status_code=400, detail=f"参考图 #{aid} 不存在或不是图片")
    params = body.model_dump(exclude={"provider_id", "model", "prompt"}, exclude_none=True, exclude_defaults=False)
    if kind != "image":
        params.pop("n", None)
    task = Task(user_id=user.id, kind=kind, status="pending", provider_id=provider.id, model=model, prompt=body.prompt, params=params)
    db.add(task)
    db.commit()
    task_runner.submit(task.id)
    return task


@router.post("/generate/{kind}")
async def generate(kind: Kind, body: GenerateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return task_out(_create_task(db, kind, body, user))


@router.post("/images/generate")
async def generate_image(body: GenerateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """兼容旧版接口。"""
    return task_out(_create_task(db, "image", body, user))


class ExpandIn(BaseModel):
    left: int = Field(0, ge=0, le=4096)
    top: int = Field(0, ge=0, le=4096)
    right: int = Field(0, ge=0, le=4096)
    bottom: int = Field(0, ge=0, le=4096)


class ImageEditIn(BaseModel):
    op: Literal["inpaint", "outpaint", "upscale", "rembg"]
    source_asset_id: int
    provider_id: int | None = None  # 放大时为空表示本地放大
    model: str | None = None
    prompt: str = Field("", max_length=20000)
    negative_prompt: str = ""
    mask: str | None = Field(None, max_length=30_000_000)  # data URI，白色 = 重绘区域
    expand: ExpandIn | None = None
    scale: float | None = Field(None, ge=1, le=8)
    n: int = Field(1, ge=1, le=4)
    seed: int | None = None
    steps: int | None = Field(None, ge=1, le=200)
    extra_body: dict[str, Any] | None = None


OP_LABEL = {"inpaint": "局部重绘", "outpaint": "扩图", "upscale": "高清放大", "rembg": "去除背景"}


@router.post("/images/edit")
async def edit_image(body: ImageEditIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """对作品进行二次编辑，结果作为新作品保存。"""
    from ..services import imageops
    from ..services.media import read_media, save_media

    src = db.get(Asset, body.source_asset_id)
    if src is None or src.kind != "image" or src.user_id != user.id:
        raise HTTPException(status_code=404, detail="原图不存在")
    local = body.op == "upscale" and not body.provider_id
    provider = None
    if not local:
        provider = db.get(Provider, body.provider_id) if body.provider_id else None
        if provider is None:
            raise HTTPException(status_code=400, detail="请选择模型")
        if not provider.enabled:
            raise HTTPException(status_code=400, detail="该模型服务已停用")
        if not body.model:
            raise HTTPException(status_code=400, detail="请选择模型")
        policy.check_access(db, user, "image", provider.id, body.model)
        policy.check_quota(db, user, "image", body.n)
    else:
        policy.check_access(db, user, "image")
    if body.op == "inpaint":
        if not body.prompt.strip():
            raise HTTPException(status_code=400, detail="请描述要在涂抹区域生成的内容")
        if not body.mask:
            raise HTTPException(status_code=400, detail="请先涂抹需要重绘的区域")
    if body.op == "outpaint" and not (body.expand and any(body.expand.model_dump().values())):
        raise HTTPException(status_code=400, detail="请设置扩展的方向和大小")

    params = body.model_dump(exclude={"provider_id", "model", "prompt", "mask"}, exclude_none=True)
    if body.mask:
        try:
            mask_bytes = imageops.decode_data_uri(body.mask)
            size = (src.width, src.height) if src.width and src.height else imageops.image_dims(read_media(src.filename))
            imageops.normalize_mask(mask_bytes, size)
        except imageops.ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        params["mask_file"] = save_media(mask_bytes, "image/png")
    if body.op == "upscale":
        params["scale"] = body.scale or 2
    prompt = body.prompt.strip() or (src.prompt if body.op == "outpaint" else "") or OP_LABEL[body.op]
    task = Task(
        user_id=user.id, kind="image", status="pending", provider_id=provider.id if provider else None,
        model=body.model or "本地放大", prompt=prompt, params=params,
    )
    db.add(task)
    db.commit()
    task_runner.submit(task.id)
    return task_out(task)


@router.get("/tasks")
def list_tasks(
    kind: str | None = None,
    status: str | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    q = db.query(Task).filter(Task.user_id == user.id)
    if kind:
        q = q.filter(Task.kind == kind)
    if status == "active":
        q = q.filter(Task.status.in_(task_runner.ACTIVE))
    elif status:
        q = q.filter(Task.status == status)
    rows = q.order_by(Task.id.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 100)).all()
    return [task_out(t) for t in rows]


def _get(db: Session, task_id: int, user: User) -> Task:
    t = db.get(Task, task_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return t


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return task_out(_get(db, task_id, user))


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _get(db, task_id, user)
    if t.status not in task_runner.ACTIVE:
        raise HTTPException(status_code=400, detail="任务已结束")
    if not task_runner.cancel(task_id):
        t.status = "cancelled"
        t.error = "已取消"
        db.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = _get(db, task_id, user)
    if t.status in task_runner.ACTIVE:
        raise HTTPException(status_code=400, detail="任务进行中")
    if t.provider_id:
        policy.check_access(db, user, t.kind, t.provider_id, t.model)
        policy.check_quota(db, user, t.kind, int((t.params or {}).get("n") or 1) if t.kind == "image" else 1)
    new = Task(user_id=user.id, kind=t.kind, status="pending", provider_id=t.provider_id, model=t.model, prompt=t.prompt, params=dict(t.params or {}))
    db.add(new)
    db.commit()
    task_runner.submit(new.id)
    return task_out(new)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """删除任务记录（已生成的作品保留在作品库中）。"""
    t = _get(db, task_id, user)
    if t.status in task_runner.ACTIVE:
        raise HTTPException(status_code=400, detail="任务进行中，无法删除")
    db.delete(t)
    db.commit()
    return {"ok": True}
