"""用户管理（仅管理员）。"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import Asset, Conversation, Task, User
from ..security import hash_password
from ..services.media import delete_media

router = APIRouter(prefix="/api/users", tags=["users"])

USERNAME_PATTERN = r"^[A-Za-z0-9_\-一-龥]+$"


def user_out(u: User, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "is_admin": u.is_admin,
        "status": u.status,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }
    if stats is not None:
        data.update(stats)
    return data


def _active_admins(db: Session) -> int:
    return db.query(User).filter(User.is_admin.is_(True), User.status == "active").count()


@router.get("")
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    convs = dict(db.query(Conversation.user_id, func.count(Conversation.id)).group_by(Conversation.user_id).all())
    assets = {uid: (n, size or 0) for uid, n, size in db.query(Asset.user_id, func.count(Asset.id), func.sum(Asset.size)).group_by(Asset.user_id).all()}
    tasks = dict(db.query(Task.user_id, func.count(Task.id)).group_by(Task.user_id).all())
    out = []
    for u in db.query(User).order_by(User.id).all():
        n_assets, size = assets.get(u.id, (0, 0))
        out.append(user_out(u, {"conversations": convs.get(u.id, 0), "assets": n_assets, "tasks": tasks.get(u.id, 0), "storage_bytes": size}))
    return out


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["admin", "user"] = "user"


@router.post("")
def create_user(body: UserCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username.strip()).first():
        raise HTTPException(status_code=409, detail="用户名已被占用")
    u = User(username=body.username.strip(), password_hash=hash_password(body.password), is_admin=body.role == "admin", status="active")
    db.add(u)
    db.commit()
    return user_out(u)


class UserPatch(BaseModel):
    role: Literal["admin", "user"] | None = None
    status: Literal["active", "pending", "disabled"] | None = None
    password: str | None = Field(None, min_length=8, max_length=128)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    losing_admin = u.is_admin and u.status == "active" and (
        (body.role is not None and body.role != "admin") or (body.status is not None and body.status != "active")
    )
    if losing_admin:
        if u.id == admin.id:
            raise HTTPException(status_code=400, detail="不能取消自己的管理员权限或禁用自己")
        if _active_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="至少需要保留一个可用的管理员")
    if body.role is not None:
        u.is_admin = body.role == "admin"
    if body.status is not None:
        if body.status != u.status:
            u.token_version += 1  # 状态变化时让已登录的会话失效
        u.status = body.status
    if body.password:
        u.password_hash = hash_password(body.password)
        u.token_version += 1
    db.commit()
    return user_out(u)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """删除用户及其全部数据（对话、任务、作品文件、个人提示词）。"""
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    if u.is_admin and _active_admins(db) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一个可用的管理员")
    for a in db.query(Asset).filter(Asset.user_id == u.id).all():
        delete_media(a.filename)
    db.delete(u)  # 依赖外键 ON DELETE CASCADE 删除关联数据
    db.commit()
    return {"ok": True}
