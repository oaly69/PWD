"""管理员：用户组、用量报表、操作日志；以及当前用户的用量与配额。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_admin
from ..models import AuditLog, User, UserGroup
from ..services import policy
from ..services.audit import ACTION_LABEL, audit
from ..timeutil import iso

router = APIRouter(prefix="/api", tags=["admin"])


class GroupIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field("", max_length=500)
    kinds: list[str] = Field(default_factory=lambda: list(policy.KINDS))
    models: dict[str, list[str]] = Field(default_factory=dict)
    quotas: dict[str, int] = Field(default_factory=dict)


def group_out(g: UserGroup, members: int = 0) -> dict[str, Any]:
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "kinds": g.kinds or [],
        "models": g.models if isinstance(g.models, dict) else {},
        "quotas": g.quotas or {},
        "members": members,
    }


def _apply(g: UserGroup, body: GroupIn) -> None:
    unknown = set(body.kinds) - set(policy.KINDS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知的能力：{', '.join(unknown)}")
    allowed_quota = {*policy.QUOTA_KEYS, "tokens_monthly"}
    g.name = body.name.strip()
    g.description = body.description
    g.kinds = [k for k in policy.KINDS if k in body.kinds]
    g.models = {k: list(dict.fromkeys(v)) for k, v in body.models.items() if k in policy.KINDS and v}
    g.quotas = {k: max(0, int(v)) for k, v in body.quotas.items() if k in allowed_quota and v}


@router.get("/groups", dependencies=[Depends(require_admin)])
def list_groups(db: Session = Depends(get_db)):
    counts: dict[int, int] = {}
    for (gid,) in db.query(User.group_id).filter(User.group_id.isnot(None)).all():
        counts[gid] = counts.get(gid, 0) + 1
    return [group_out(g, counts.get(g.id, 0)) for g in db.query(UserGroup).order_by(UserGroup.id).all()]


@router.post("/groups")
def create_group(body: GroupIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(UserGroup).filter(UserGroup.name == body.name.strip()).first():
        raise HTTPException(status_code=409, detail="用户组名称已存在")
    g = UserGroup()
    _apply(g, body)
    db.add(g)
    audit(db, admin, "group.create", g.name, request=request)
    db.commit()
    return group_out(g)


@router.put("/groups/{gid}")
def update_group(gid: int, body: GroupIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    g = db.get(UserGroup, gid)
    if g is None:
        raise HTTPException(status_code=404, detail="用户组不存在")
    dup = db.query(UserGroup).filter(UserGroup.name == body.name.strip(), UserGroup.id != gid).first()
    if dup:
        raise HTTPException(status_code=409, detail="用户组名称已存在")
    _apply(g, body)
    audit(db, admin, "group.update", g.name, request=request)
    db.commit()
    return group_out(g, db.query(User).filter(User.group_id == gid).count())


@router.delete("/groups/{gid}")
def delete_group(gid: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """删除用户组，组内用户变为不受限制。"""
    g = db.get(UserGroup, gid)
    if g is None:
        raise HTTPException(status_code=404, detail="用户组不存在")
    db.query(User).filter(User.group_id == gid).update({User.group_id: None})
    from ..site import get_setting, set_setting

    if get_setting(db, "default_group_id") == gid:
        set_setting(db, "default_group_id", None)
    audit(db, admin, "group.delete", g.name, request=request)
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.get("/usage/me")
def my_usage(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return policy.quota_status(db, user)


@router.get("/usage/report", dependencies=[Depends(require_admin)])
def usage_report(days: int = 30, db: Session = Depends(get_db)):
    return policy.usage_report(db, min(max(days, 1), 365))


@router.get("/audit", dependencies=[Depends(require_admin)])
def audit_logs(
    action: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if q:
        like = f"%{q}%"
        query = query.filter((AuditLog.username.like(like)) | (AuditLog.target.like(like)) | (AuditLog.ip.like(like)))
    total = query.count()
    rows = query.order_by(AuditLog.id.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 200)).all()
    return {
        "total": total,
        "actions": ACTION_LABEL,
        "items": [
            {
                "id": r.id, "user_id": r.user_id, "username": r.username, "action": r.action,
                "label": ACTION_LABEL.get(r.action, r.action), "target": r.target, "detail": r.detail, "ip": r.ip,
                "created_at": iso(r.created_at),
            }
            for r in rows
        ],
    }
