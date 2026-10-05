"""后台任务执行器：在进程内用 asyncio 执行生成任务，并把结果写入作品库。"""
from __future__ import annotations

import asyncio
import logging

from ..db import new_session
from ..models import Asset, Provider, Task, utcnow
from . import comfyui, failover, imageops, openai_compat, policy
from .media import image_size, read_media, save_media
from .openai_compat import ProviderError

log = logging.getLogger("pwd.tasks")

# 不同类型任务各自的并发上限：视频任务耗时长，不应阻塞图像任务
CONCURRENCY = {"image": 3, "video": 2, "tts": 3}
_semaphores: dict[str, asyncio.Semaphore] = {}
_running: dict[int, asyncio.Task] = {}

ACTIVE = ("pending", "running")


def _sem(kind: str) -> asyncio.Semaphore:
    if kind not in _semaphores:
        _semaphores[kind] = asyncio.Semaphore(CONCURRENCY.get(kind, 2))
    return _semaphores[kind]


def recover_interrupted() -> None:
    """服务重启时，把仍处于运行状态的任务标记为失败。"""
    with new_session() as db:
        for task in db.query(Task).filter(Task.status.in_(ACTIVE)).all():
            task.status = "failed"
            task.error = "服务重启，任务被中断"
            task.finished_at = utcnow()
        db.commit()


def submit(task_id: int) -> None:
    t = asyncio.get_running_loop().create_task(_run(task_id))
    _running[task_id] = t
    t.add_done_callback(lambda _t: _running.pop(task_id, None))


def cancel(task_id: int) -> bool:
    t = _running.get(task_id)
    if t is None:
        return False
    t.cancel()
    return True


def _load_references(db, ids: list[int] | None) -> list[tuple[bytes, str]]:
    refs: list[tuple[bytes, str]] = []
    for aid in ids or []:
        asset = db.get(Asset, int(aid))
        if asset is None:
            raise ProviderError(f"参考素材 #{aid} 不存在")
        refs.append((read_media(asset.filename), asset.mime))
    return refs


def effective_prompt(task: Task) -> tuple[str, dict]:
    """把风格预设合并进提示词与反向提示词（任务记录中保留用户原始输入）。"""
    params = dict(task.params or {})
    prompt = task.prompt
    if params.get("style_prompt"):
        prompt = f"{prompt.rstrip('，,。. ')}，{params['style_prompt']}"
    if params.get("style_negative"):
        neg = params.get("negative_prompt", "").strip()
        params["negative_prompt"] = f"{neg}, {params['style_negative']}" if neg else params["style_negative"]
    return prompt, params


REMBG_PROMPT = "Remove the background completely and keep only the main subject with clean edges, transparent background."


async def _execute_op(db, task: Task, provider: Provider | None, prompt: str, params: dict, on_progress) -> list[tuple[bytes, str]]:
    """作品二次编辑：局部重绘 / 扩图 / 放大 / 去背景。"""
    op = params["op"]
    src = db.get(Asset, int(params.get("source_asset_id") or 0))
    if src is None or src.kind != "image":
        raise ProviderError("原图不存在或已被删除")
    data = read_media(src.filename)

    if op == "upscale":
        scale = float(params.get("scale") or 2)
        if provider is None:
            return [(imageops.upscale_local(data, scale), "image/png")]
        if provider.kind == "comfyui":
            w, h = imageops.image_dims(data)
            overrides = {"width": round(w * scale), "height": round(h * scale), "scale": scale}
            return await comfyui.generate(provider, task.model, prompt, params, None, on_progress, uploads={"image": (data, src.mime)}, overrides=overrides)
        raise ProviderError("OpenAI 兼容接口没有通用的放大接口，请选择「本地放大」或 ComfyUI 放大工作流")

    if provider is None:
        raise ProviderError("模型服务不存在或已被删除")

    if op == "rembg":
        if provider.kind == "comfyui":
            return await comfyui.generate(provider, task.model, prompt, params, None, on_progress, uploads={"image": (data, src.mime)})
        extra = dict(params.get("extra_body") or {})
        if "gpt-image" in task.model:
            extra.setdefault("background", "transparent")
        return await openai_compat.edit_image(provider, task.model, prompt or REMBG_PROMPT, {**params, "extra_body": extra}, imageops.prepare_png(data))

    if op in ("inpaint", "outpaint"):
        if op == "inpaint":
            if not params.get("mask_file"):
                raise ProviderError("缺少蒙版")
            base = data
            mask = imageops.normalize_mask(read_media(params["mask_file"]), imageops.image_dims(data))
        else:
            e = params.get("expand") or {}
            base, mask = imageops.outpaint_canvas(data, *(int(e.get(k) or 0) for k in ("left", "top", "right", "bottom")))
        prep = imageops.prepare_inpaint(base, mask)
        if provider.kind == "comfyui":
            uploads = {"image": (prep["image_alpha"], "image/png"), "mask": (prep["mask"], "image/png")}
            w, h = imageops.image_dims(base)
            return await comfyui.generate(provider, task.model, prompt, params, None, on_progress, uploads=uploads, overrides={"width": w, "height": h})
        return await openai_compat.edit_image(
            provider, task.model, prompt, params, prep["image"], mask=prep["openai_mask"], mask_white=prep["mask"]
        )
    raise ProviderError(f"未知的编辑操作：{op}")


async def _execute(db, task: Task, provider: Provider | None) -> list[tuple[bytes, str]]:
    prompt, params = effective_prompt(task)

    async def on_progress(progress: int, external_id: str = "") -> None:
        changed = False
        if progress != task.progress:
            task.progress = progress
            changed = True
        if external_id and external_id != task.external_id:
            task.external_id = external_id
            changed = True
        if changed:
            db.commit()

    if params.get("op"):
        return await _execute_op(db, task, provider, prompt, params, on_progress)
    assert provider is not None
    refs = _load_references(db, params.get("reference_asset_ids"))
    if provider.kind == "comfyui":
        if task.kind == "tts":
            raise ProviderError("ComfyUI 暂不支持语音合成")
        return await comfyui.generate(provider, task.model, prompt, params, refs, on_progress)
    if task.kind == "image":
        return await openai_compat.generate_images(provider, task.model, prompt, params, refs)
    if task.kind == "video":
        return await openai_compat.generate_video(
            provider, task.model, prompt, params, refs[0] if refs else None, on_progress
        )
    if task.kind == "tts":
        return [await openai_compat.speech(provider, task.model, task.prompt, params)]
    raise ProviderError(f"未知任务类型：{task.kind}")


async def _execute_with_failover(db, task: Task, provider: Provider | None) -> tuple[list[tuple[bytes, str]], Provider | None]:
    """执行任务；可重试的错误（网络、限流、5xx）自动切换到提供同名模型的其他服务。"""
    if provider is None:
        return await _execute(db, task, None), None
    kind = "image" if (task.params or {}).get("op") else task.kind
    cands = failover.candidates(db, provider, task.model, kind)
    for n, cand in enumerate(cands):
        try:
            outputs = await _execute(db, task, cand)
        except Exception as exc:
            if n + 1 < len(cands) and failover.retryable(exc):
                log.info("task %s: %s 失败（%s），切换到 %s", task.id, cand.name, exc, cands[n + 1].name)
                continue
            raise
        if cand.id != provider.id:
            task.params = {**(task.params or {}), "served_by": cand.name}
        return outputs, cand
    raise ProviderError("没有可用的模型服务")


async def _run(task_id: int) -> None:
    with new_session() as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        try:
            async with _sem(task.kind):
                provider = db.get(Provider, task.provider_id) if task.provider_id else None
                task.status = "running"
                db.commit()
                if provider is None and not (task.params or {}).get("op"):
                    raise ProviderError("模型服务不存在或已被删除")
                outputs, served = await _execute_with_failover(db, task, provider)
                for data, mime in outputs:
                    filename = save_media(data, mime)
                    kind = mime.split("/")[0] if mime.split("/")[0] in ("image", "video", "audio") else task.kind
                    w, h = image_size(data) if kind == "image" else (0, 0)
                    db.add(Asset(
                        user_id=task.user_id, kind=kind, source="generated", filename=filename, mime=mime, size=len(data),
                        width=w, height=h, prompt=task.prompt, model=task.model, task_id=task.id,
                    ))
                if served is not None:  # 本地放大不计入用量
                    policy.record_usage(db, task.user_id, task.kind, served.id, task.model, max(1, len(outputs)))
                task.status = "succeeded"
                task.progress = 100
        except asyncio.CancelledError:
            task.status = "cancelled"
            task.error = "已取消"
        except Exception as exc:  # noqa: BLE001 - 任何错误都记录到任务上
            log.warning("task %s failed: %s", task_id, exc)
            task.status = "failed"
            task.error = str(exc) or exc.__class__.__name__
        task.finished_at = utcnow()
        db.commit()
