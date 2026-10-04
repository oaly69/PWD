from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Provider, Task
from ..services import tasks as task_runner
from ..site import get_setting
from .assets import asset_out

router = APIRouter(prefix="/api", tags=["images"], dependencies=[Depends(current_user)])


class ImageGenIn(BaseModel):
    provider_id: int | None = None
    model: str | None = None
    prompt: str = Field(..., min_length=1, max_length=8000)
    negative_prompt: str = ""
    size: str = "1024x1024"
    n: int = Field(1, ge=1, le=8)
    seed: int | None = None
    steps: int | None = Field(None, ge=1, le=200)
    extra_body: dict[str, Any] | None = None


def task_out(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "kind": t.kind,
        "status": t.status,
        "provider_id": t.provider_id,
        "model": t.model,
        "prompt": t.prompt,
        "params": t.params or {},
        "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "assets": [asset_out(a) for a in t.assets],
    }


@router.post("/images/generate")
async def generate(body: ImageGenIn, db: Session = Depends(get_db)):
    provider_id = body.provider_id or get_setting(db, "default_image_provider_id")
    model = body.model or get_setting(db, "default_image_model") or ""
    provider = db.get(Provider, provider_id) if provider_id else None
    if provider is None:
        raise HTTPException(status_code=400, detail="请先选择图像模型服务")
    if not provider.enabled:
        raise HTTPException(status_code=400, detail="该模型服务已停用")
    if not model:
        raise HTTPException(status_code=400, detail="请先选择图像模型")
    params = body.model_dump(exclude={"provider_id", "model", "prompt"}, exclude_none=True)
    task = Task(kind="image", status="pending", provider_id=provider.id, model=model, prompt=body.prompt, params=params)
    db.add(task)
    db.commit()
    task_runner.submit(task.id)
    return task_out(task)


@router.get("/tasks")
def list_tasks(kind: str | None = None, limit: int = 30, offset: int = 0, db: Session = Depends(get_db)):
    q = db.query(Task)
    if kind:
        q = q.filter(Task.kind == kind)
    rows = q.order_by(Task.id.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 100)).all()
    return [task_out(t) for t in rows]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_out(t)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除任务记录（已生成的作品保留在作品库中）。"""
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status in ("pending", "running"):
        raise HTTPException(status_code=400, detail="任务进行中，无法删除")
    db.delete(t)
    db.commit()
    return {"ok": True}
