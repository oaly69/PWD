from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import current_user
from ..models import Asset
from ..services.tasks import save_media

router = APIRouter(tags=["assets"], dependencies=[Depends(current_user)])

MAX_UPLOAD = 50 * 1024 * 1024
ALLOWED_PREFIX = ("image/", "video/", "audio/")


def asset_out(a: Asset) -> dict[str, Any]:
    return {
        "id": a.id,
        "kind": a.kind,
        "source": a.source,
        "url": f"/media/{a.filename}",
        "mime": a.mime,
        "size": a.size,
        "prompt": a.prompt,
        "model": a.model,
        "favorite": a.favorite,
        "task_id": a.task_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/api/assets")
def list_assets(
    kind: str | None = None,
    favorite: bool | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 40,
    db: Session = Depends(get_db),
):
    query = db.query(Asset)
    if kind:
        query = query.filter(Asset.kind == kind)
    if favorite is not None:
        query = query.filter(Asset.favorite == favorite)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Asset.prompt.like(like), Asset.model.like(like)))
    total = query.count()
    rows = query.order_by(Asset.id.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 200)).all()
    return {"total": total, "items": [asset_out(a) for a in rows]}


@router.post("/api/assets/upload")
async def upload_asset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    mime = (file.content_type or "").split(";")[0]
    if not mime.startswith(ALLOWED_PREFIX):
        raise HTTPException(status_code=400, detail="仅支持图片、视频、音频文件")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="文件超过 50MB 限制")
    filename = save_media(data, mime)
    a = Asset(kind=mime.split("/")[0], source="upload", filename=filename, mime=mime, size=len(data), prompt=file.filename or "")
    db.add(a)
    db.commit()
    return asset_out(a)


class AssetPatch(BaseModel):
    favorite: bool | None = None
    prompt: str | None = None


@router.patch("/api/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    if body.favorite is not None:
        a.favorite = body.favorite
    if body.prompt is not None:
        a.prompt = body.prompt
    db.commit()
    return asset_out(a)


@router.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    path = (settings.media_dir / a.filename).resolve()
    if path.is_relative_to(settings.media_dir.resolve()) and path.is_file():
        path.unlink()
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/media/{path:path}")
def media(path: str):
    root = settings.media_dir.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, headers={"Cache-Control": "private, max-age=31536000, immutable"})
