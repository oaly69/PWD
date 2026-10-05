from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Asset, User
from ..services.media import delete_media, ensure_thumb, image_size, media_path, save_media

router = APIRouter(tags=["assets"])

MAX_UPLOAD = 100 * 1024 * 1024
ALLOWED_PREFIX = ("image/", "video/", "audio/")


def asset_out(a: Asset) -> dict[str, Any]:
    task = a.task
    return {
        "id": a.id,
        "kind": a.kind,
        "source": a.source,
        "url": f"/media/{a.filename}",
        "thumb_url": f"/thumbs/{a.filename}" if a.kind == "image" else None,
        "mime": a.mime,
        "size": a.size,
        "width": a.width or 0,
        "height": a.height or 0,
        "prompt": a.prompt,
        "model": a.model,
        "favorite": a.favorite,
        "task_id": a.task_id,
        "params": (task.params or {}) if task else {},
        "provider_id": task.provider_id if task else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/api/assets")
def list_assets(
    kind: str | None = None,
    favorite: bool | None = None,
    source: str | None = None,
    model: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 40,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(Asset).filter(Asset.user_id == user.id)
    if kind:
        query = query.filter(Asset.kind == kind)
    if favorite is not None:
        query = query.filter(Asset.favorite == favorite)
    if source:
        query = query.filter(Asset.source == source)
    if model:
        query = query.filter(Asset.model == model)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Asset.prompt.like(like), Asset.model.like(like)))
    total = query.count()
    rows = query.order_by(Asset.id.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 200)).all()
    return {"total": total, "items": [asset_out(a) for a in rows]}


@router.get("/api/assets/models")
def asset_models(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Asset.model).filter(Asset.user_id == user.id, Asset.model != "").distinct().all()
    return sorted(r[0] for r in rows)


@router.get("/api/assets/{asset_id}")
def get_asset(asset_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return asset_out(_get(db, asset_id, user))


@router.post("/api/assets/upload")
async def upload_asset(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    mime = (file.content_type or "").split(";")[0]
    if not mime.startswith(ALLOWED_PREFIX):
        raise HTTPException(status_code=400, detail="仅支持图片、视频、音频文件")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件超过 100MB 限制")
    filename = save_media(data, mime)
    kind = mime.split("/")[0]
    w, h = image_size(data) if kind == "image" else (0, 0)
    a = Asset(user_id=user.id, kind=kind, source="upload", filename=filename, mime=mime, size=len(data), width=w, height=h, prompt=file.filename or "")
    db.add(a)
    db.commit()
    return asset_out(a)


class AssetPatch(BaseModel):
    favorite: bool | None = None
    prompt: str | None = None


def _get(db: Session, asset_id: int, user: User) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="作品不存在")
    return a


@router.patch("/api/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _get(db, asset_id, user)
    if body.favorite is not None:
        a.favorite = body.favorite
    if body.prompt is not None:
        a.prompt = body.prompt
    db.commit()
    return asset_out(a)


@router.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = _get(db, asset_id, user)
    delete_media(a.filename)
    db.delete(a)
    db.commit()
    return {"ok": True}


class BatchIn(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=500)
    action: str  # delete / favorite / unfavorite


@router.post("/api/assets/batch")
def batch_assets(body: BatchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Asset).filter(Asset.id.in_(body.ids), Asset.user_id == user.id).all()
    for a in rows:
        if body.action == "delete":
            delete_media(a.filename)
            db.delete(a)
        elif body.action in ("favorite", "unfavorite"):
            a.favorite = body.action == "favorite"
        else:
            raise HTTPException(status_code=422, detail="不支持的操作")
    db.commit()
    return {"ok": True, "count": len(rows)}


@router.get("/api/assets-zip")
def download_zip(ids: str, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """把多个作品打包为 zip 下载，ids 为逗号分隔的作品 ID。写入临时文件，避免大文件占用内存。"""
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:500]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids 格式错误") from exc
    rows = db.query(Asset).filter(Asset.id.in_(id_list), Asset.user_id == user.id).all()
    fd, tmp = tempfile.mkstemp(prefix="pwd-assets-", suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        for a in rows:
            path = media_path(a.filename)
            if path.is_file():
                zf.write(path, f"pwd-{a.id}{path.suffix}")
    background.add_task(os.remove, tmp)
    return FileResponse(tmp, media_type="application/zip", filename="pwd-assets.zip")


def _owns_file(db: Session, user: User, path: str) -> bool:
    return db.query(Asset.id).filter(Asset.filename == path, Asset.user_id == user.id).first() is not None


@router.get("/media/{path:path}")
def media(path: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not _owns_file(db, user, path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return _serve_media(path)


def _serve_media(path: str):
    try:
        target = media_path(path)
    except ValueError:
        target = None
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/thumbs/{path:path}")
def thumb(path: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not _owns_file(db, user, path):
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        target = ensure_thumb(path)
    except ValueError:
        target = None
    if target is None:
        # 无法生成缩略图时回退到原图
        return _serve_media(path)
    return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable"})
