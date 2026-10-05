from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import VERSION, settings
from .. import db as dbmod
from ..db import get_db
from ..deps import current_user, require_admin
from ..models import Asset, Conversation, Message, PromptTemplate, Provider, Task, User, utcnow
from ..site import ADMIN_KEYS, EDITABLE_KEYS, PUBLIC_KEYS, SECRET_KEYS, all_settings, set_setting
from ..services.audit import audit

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@router.get("/site")
def site_info(db: Session = Depends(get_db)):
    data = all_settings(db)
    return {k: data[k] for k in PUBLIC_KEYS} | {"version": VERSION}


def _settings_out(db: Session, admin: bool = True) -> dict[str, Any]:
    data = all_settings(db)
    out = {k: v for k, v in data.items() if k in EDITABLE_KEYS and k not in SECRET_KEYS and (admin or k not in ADMIN_KEYS)}
    if admin:
        for k in SECRET_KEYS:
            out[f"{k}_set"] = bool(data.get(k))
    from ..services import websearch

    out["search_available"] = websearch.configured(db)
    out["stt_available"] = bool(data.get("stt_provider_id") and data.get("stt_model"))
    return out


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _settings_out(db, user.is_admin)


@router.put("/settings")
def update_settings(body: dict[str, Any], request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    unknown = set(body) - EDITABLE_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"不支持的设置项：{', '.join(sorted(unknown))}")
    if "site_name" in body and not str(body["site_name"] or "").strip():
        raise HTTPException(status_code=422, detail="站点名称不能为空")
    for key, value in body.items():
        if key in SECRET_KEYS and not value:
            continue  # 留空表示保持不变
        set_setting(db, key, value)
    audit(db, user, "settings.update", detail=", ".join(sorted(body)), request=request)
    db.commit()
    return _settings_out(db)


def _dir_size(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """当前用户的统计；管理员额外返回全站概况（site）。"""
    mine = Asset.user_id == user.id
    by_kind = dict(db.query(Asset.kind, func.count(Asset.id)).filter(mine).group_by(Asset.kind).all())
    since = utcnow() - timedelta(days=13)
    daily_rows = (
        db.query(func.date(Asset.created_at), func.count(Asset.id))
        .filter(mine, Asset.created_at >= since, Asset.source == "generated")
        .group_by(func.date(Asset.created_at))
        .all()
    )
    daily_map = {str(d): n for d, n in daily_rows}
    today = utcnow().date()
    daily = [
        {"date": (today - timedelta(days=i)).isoformat(), "count": daily_map.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(13, -1, -1)
    ]
    data = {
        "providers": db.query(Provider).filter(Provider.enabled.is_(True)).count(),
        "conversations": db.query(Conversation).filter(Conversation.user_id == user.id).count(),
        "assets": db.query(Asset).filter(mine).count(),
        "images": by_kind.get("image", 0),
        "videos": by_kind.get("video", 0),
        "audios": by_kind.get("audio", 0),
        "favorites": db.query(Asset).filter(mine, Asset.favorite.is_(True)).count(),
        "prompts": db.query(PromptTemplate).filter(PromptTemplate.user_id == user.id).count(),
        "tasks_running": db.query(Task).filter(Task.user_id == user.id, Task.status.in_(["pending", "running"])).count(),
        "tasks_failed": db.query(Task).filter(Task.user_id == user.id, Task.status == "failed").count(),
        "storage_bytes": db.query(func.coalesce(func.sum(Asset.size), 0)).filter(mine).scalar(),
        "daily": daily,
    }
    if user.is_admin:
        data["site"] = {
            "users": db.query(User).count(),
            "pending_users": db.query(User).filter(User.status == "pending").count(),
            "assets": db.query(Asset).count(),
            "messages": db.query(Message).count(),
            "storage_bytes": _dir_size(settings.media_dir),
        }
    return data


@router.get("/system/backup")
def backup(background: BackgroundTasks, request: Request, include_media: bool = True,
           db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """导出完整备份：数据库快照 + 会话密钥 +（可选）全部媒体文件。"""
    audit(db, user, "system.backup", detail="含媒体文件" if include_media else "仅数据库", request=request)
    db.commit()
    tmpdir = tempfile.mkdtemp(prefix="pwd-backup-")
    db_copy = os.path.join(tmpdir, "pwd.db")
    src = sqlite3.connect(dbmod.engine.url.database or str(settings.db_path))
    dst = sqlite3.connect(db_copy)
    with dst:
        src.backup(dst)  # 在线一致性快照
    src.close()
    dst.close()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = os.path.join(tmpdir, f"pwd-backup-{stamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_copy, "pwd.db")
        if settings.secret_file.exists():
            zf.write(settings.secret_file, ".secret_key")
        if include_media and settings.media_dir.exists():
            for root, _dirs, files in os.walk(settings.media_dir):
                for f in files:
                    full = os.path.join(root, f)
                    zf.write(full, os.path.join("media", os.path.relpath(full, settings.media_dir)), compress_type=zipfile.ZIP_STORED)

    def cleanup() -> None:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    background.add_task(cleanup)
    return FileResponse(zip_path, media_type="application/zip", filename=os.path.basename(zip_path))
