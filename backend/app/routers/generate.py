from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Asset, Provider, Task
from ..services import tasks as task_runner
from ..site import get_setting
from .assets import asset_out

router = APIRouter(prefix="/api", tags=["generate"], dependencies=[Depends(current_user)])

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


def _create_task(db: Session, kind: str, body: GenerateIn) -> Task:
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
    for aid in body.reference_asset_ids:
        ref = db.get(Asset, aid)
        if ref is None or ref.kind != "image":
            raise HTTPException(status_code=400, detail=f"参考图 #{aid} 不存在或不是图片")
    params = body.model_dump(exclude={"provider_id", "model", "prompt"}, exclude_none=True, exclude_defaults=False)
    if kind != "image":
        params.pop("n", None)
    task = Task(kind=kind, status="pending", provider_id=provider.id, model=model, prompt=body.prompt, params=params)
    db.add(task)
    db.commit()
    task_runner.submit(task.id)
    return task


@router.post("/generate/{kind}")
async def generate(kind: Kind, body: GenerateIn, db: Session = Depends(get_db)):
    return task_out(_create_task(db, kind, body))


@router.post("/images/generate")
async def generate_image(body: GenerateIn, db: Session = Depends(get_db)):
    """兼容旧版接口。"""
    return task_out(_create_task(db, "image", body))


@router.get("/tasks")
def list_tasks(
    kind: str | None = None,
    status: str | None = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Task)
    if kind:
        q = q.filter(Task.kind == kind)
    if status == "active":
        q = q.filter(Task.status.in_(task_runner.ACTIVE))
    elif status:
        q = q.filter(Task.status == status)
    rows = q.order_by(Task.id.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 100)).all()
    return [task_out(t) for t in rows]


def _get(db: Session, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return t


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    return task_out(_get(db, task_id))


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    t = _get(db, task_id)
    if t.status not in task_runner.ACTIVE:
        raise HTTPException(status_code=400, detail="任务已结束")
    if not task_runner.cancel(task_id):
        t.status = "cancelled"
        t.error = "已取消"
        db.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: int, db: Session = Depends(get_db)):
    t = _get(db, task_id)
    if t.status in task_runner.ACTIVE:
        raise HTTPException(status_code=400, detail="任务进行中")
    new = Task(kind=t.kind, status="pending", provider_id=t.provider_id, model=t.model, prompt=t.prompt, params=dict(t.params or {}))
    db.add(new)
    db.commit()
    task_runner.submit(new.id)
    return task_out(new)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除任务记录（已生成的作品保留在作品库中）。"""
    t = _get(db, task_id)
    if t.status in task_runner.ACTIVE:
        raise HTTPException(status_code=400, detail="任务进行中，无法删除")
    db.delete(t)
    db.commit()
    return {"ok": True}
