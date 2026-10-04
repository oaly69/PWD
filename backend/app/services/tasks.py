"""后台任务执行器：在进程内用 asyncio 执行生成任务，并把结果写入作品库。"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from datetime import datetime

from ..config import settings
from ..db import new_session
from ..models import Asset, Provider, Task, utcnow
from . import comfyui, openai_compat

log = logging.getLogger("pwd.tasks")

MAX_CONCURRENCY = 2
_semaphore: asyncio.Semaphore | None = None
_running: set[asyncio.Task] = set()


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    return _semaphore


def save_media(data: bytes, mime: str) -> str:
    """保存文件到 media 目录，返回相对文件名（按月份分目录）。"""
    ext = mimetypes.guess_extension(mime) or ".bin"
    if ext == ".jpe":
        ext = ".jpg"
    sub = datetime.now().strftime("%Y%m")
    folder = settings.media_dir / sub
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    (folder / name).write_bytes(data)
    return f"{sub}/{name}"


def recover_interrupted() -> None:
    """服务重启时，把仍处于运行状态的任务标记为失败。"""
    with new_session() as db:
        for task in db.query(Task).filter(Task.status.in_(["pending", "running"])).all():
            task.status = "failed"
            task.error = "服务重启，任务被中断"
            task.finished_at = utcnow()
        db.commit()


def submit(task_id: int) -> None:
    t = asyncio.get_running_loop().create_task(_run(task_id))
    _running.add(t)
    t.add_done_callback(_running.discard)


async def _run(task_id: int) -> None:
    async with _sem():
        with new_session() as db:
            task = db.get(Task, task_id)
            if task is None:
                return
            provider = db.get(Provider, task.provider_id) if task.provider_id else None
            task.status = "running"
            db.commit()
            try:
                if provider is None:
                    raise openai_compat.ProviderError("模型服务不存在或已被删除")
                if provider.kind == "comfyui":
                    images = await comfyui.generate_images(provider, task.model, task.prompt, task.params or {})
                else:
                    images = await openai_compat.generate_images(provider, task.model, task.prompt, task.params or {})
                for data, mime in images:
                    filename = save_media(data, mime)
                    db.add(Asset(
                        kind="image", source="generated", filename=filename, mime=mime, size=len(data),
                        prompt=task.prompt, model=task.model, task_id=task.id,
                    ))
                task.status = "succeeded"
            except Exception as exc:  # noqa: BLE001 - 任何错误都记录到任务上
                log.warning("task %s failed: %s", task_id, exc)
                task.status = "failed"
                task.error = str(exc) or exc.__class__.__name__
            task.finished_at = utcnow()
            db.commit()
