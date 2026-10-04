from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import VERSION
from ..db import get_db
from ..deps import current_user
from ..models import Asset, Conversation, Provider, Task
from ..site import EDITABLE_KEYS, PUBLIC_KEYS, all_settings, set_setting

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@router.get("/site")
def site_info(db: Session = Depends(get_db)):
    data = all_settings(db)
    return {k: data[k] for k in PUBLIC_KEYS} | {"version": VERSION}


@router.get("/settings", dependencies=[Depends(current_user)])
def get_settings(db: Session = Depends(get_db)):
    data = all_settings(db)
    return {k: v for k, v in data.items() if k in EDITABLE_KEYS}


@router.put("/settings", dependencies=[Depends(current_user)])
def update_settings(body: dict[str, Any], db: Session = Depends(get_db)):
    unknown = set(body) - EDITABLE_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"不支持的设置项：{', '.join(sorted(unknown))}")
    for key, value in body.items():
        set_setting(db, key, value)
    db.commit()
    data = all_settings(db)
    return {k: v for k, v in data.items() if k in EDITABLE_KEYS}


@router.get("/stats", dependencies=[Depends(current_user)])
def stats(db: Session = Depends(get_db)):
    return {
        "providers": db.query(Provider).count(),
        "conversations": db.query(Conversation).count(),
        "assets": db.query(Asset).count(),
        "favorites": db.query(Asset).filter(Asset.favorite.is_(True)).count(),
        "tasks_running": db.query(Task).filter(Task.status.in_(["pending", "running"])).count(),
        "tasks_failed": db.query(Task).filter(Task.status == "failed").count(),
    }
