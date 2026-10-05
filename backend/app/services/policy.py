"""用户组权限、用量配额与用量记录。管理员不受权限与配额限制。"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import User, UsageLog, UserGroup

KINDS = ("chat", "image", "video", "tts")
KIND_LABEL = {"chat": "对话", "image": "图像生成", "video": "视频生成", "tts": "语音合成"}
QUOTA_KEYS = {"chat_daily": "chat", "image_daily": "image", "video_daily": "video", "tts_daily": "tts"}


def group_of(db: Session, user: User) -> UserGroup | None:
    if user.is_admin or not user.group_id:
        return None
    return db.get(UserGroup, user.group_id)


def _allowed(group: UserGroup, kind: str) -> list[str]:
    models = group.models if isinstance(group.models, dict) else {}
    return list(models.get(kind) or [])


def can_use(group: UserGroup | None, kind: str, provider_id: int | None = None, model: str | None = None) -> bool:
    if group is None:
        return True
    if kind not in (group.kinds or []):
        return False
    allowed = _allowed(group, kind)
    if not allowed or provider_id is None or model is None:
        return True
    return f"{provider_id}::{model}" in allowed


def filter_models(group: UserGroup | None, provider_id: int, kind: str, models: list[str]) -> list[str]:
    if group is None:
        return models
    if kind not in (group.kinds or []):
        return []
    allowed = _allowed(group, kind)
    if not allowed:
        return models
    return [m for m in models if f"{provider_id}::{m}" in allowed]


def check_access(db: Session, user: User, kind: str, provider_id: int | None = None, model: str | None = None) -> None:
    group = group_of(db, user)
    if group is None:
        return
    if kind not in (group.kinds or []):
        raise HTTPException(status_code=403, detail=f"你所在的用户组「{group.name}」没有{KIND_LABEL.get(kind, kind)}权限")
    if not can_use(group, kind, provider_id, model):
        raise HTTPException(status_code=403, detail=f"你所在的用户组「{group.name}」不能使用模型「{model}」")


def _local_day_start() -> datetime:
    return timeutil.day_start()


def _local_month_start() -> datetime:
    return timeutil.month_start()


def usage_summary(db: Session, user_id: int) -> dict[str, Any]:
    """今日各能力用量与本月 Token 用量。"""
    day = _local_day_start()
    rows = (
        db.query(UsageLog.kind, func.sum(UsageLog.units))
        .filter(UsageLog.user_id == user_id, UsageLog.created_at >= day)
        .group_by(UsageLog.kind)
        .all()
    )
    today = {k: 0 for k in KINDS} | {k: int(n or 0) for k, n in rows}
    tokens = (
        db.query(func.sum(UsageLog.prompt_tokens + UsageLog.completion_tokens))
        .filter(UsageLog.user_id == user_id, UsageLog.created_at >= _local_month_start())
        .scalar()
    )
    return {"today": today, "tokens_month": int(tokens or 0)}


def quota_status(db: Session, user: User) -> dict[str, Any]:
    group = group_of(db, user)
    usage = usage_summary(db, user.id)
    quotas = {k: int(v) for k, v in ((group.quotas or {}) if group else {}).items() if v}
    return {
        "group": {"id": group.id, "name": group.name, "kinds": group.kinds} if group else None,
        "usage": usage,
        "quotas": quotas,
    }


def check_quota(db: Session, user: User, kind: str, amount: int = 1) -> None:
    group = group_of(db, user)
    if group is None:
        return
    quotas = group.quotas or {}
    usage = usage_summary(db, user.id)
    key = f"{kind}_daily"
    limit = int(quotas.get(key) or 0)
    if limit and usage["today"].get(kind, 0) + amount > limit:
        raise HTTPException(
            status_code=429,
            detail=f"今日{KIND_LABEL.get(kind, kind)}额度已用完（{usage['today'].get(kind, 0)}/{limit}），明天再来吧",
        )
    if kind == "chat":
        tlimit = int(quotas.get("tokens_monthly") or 0)
        if tlimit and usage["tokens_month"] >= tlimit:
            raise HTTPException(status_code=429, detail=f"本月 Token 额度已用完（{usage['tokens_month']}/{tlimit}）")


def estimate_tokens(text: str) -> int:
    """粗略估算：中文约 1 字 1 token，英文约 4 字符 1 token。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return cjk + math.ceil((len(text) - cjk) / 4)


def record_usage(
    db: Session,
    user_id: int | None,
    kind: str,
    provider_id: int | None,
    model: str,
    units: int = 1,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated: bool = False,
) -> None:
    db.add(UsageLog(
        user_id=user_id, kind=kind, provider_id=provider_id, model=model or "", units=units,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, estimated=estimated,
    ))


def usage_report(db: Session, days: int = 30) -> dict[str, Any]:
    """管理员用量报表：每日趋势、按用户、按模型汇总。"""
    since = _local_day_start() - timedelta(days=days - 1)
    base = db.query(UsageLog).filter(UsageLog.created_at >= since)
    tokens = func.sum(UsageLog.prompt_tokens + UsageLog.completion_tokens)
    daily = (
        base.with_entities(func.date(UsageLog.created_at, timeutil.SQLITE_OFFSET), UsageLog.kind, func.sum(UsageLog.units), tokens)
        .group_by(func.date(UsageLog.created_at, timeutil.SQLITE_OFFSET), UsageLog.kind)
        .all()
    )
    by_user = (
        base.with_entities(UsageLog.user_id, UsageLog.kind, func.sum(UsageLog.units), tokens)
        .group_by(UsageLog.user_id, UsageLog.kind)
        .all()
    )
    by_model = (
        base.with_entities(UsageLog.kind, UsageLog.model, func.sum(UsageLog.units), tokens)
        .group_by(UsageLog.kind, UsageLog.model)
        .order_by(func.sum(UsageLog.units).desc())
        .limit(50)
        .all()
    )
    users = {u.id: u.username for u in db.query(User.id, User.username).all()}
    per_user: dict[int, dict[str, Any]] = {}
    for uid, kind, units, tok in by_user:
        row = per_user.setdefault(uid or 0, {"user_id": uid, "username": users.get(uid, "已删除用户"), "tokens": 0} | {k: 0 for k in KINDS})
        row[kind] = int(units or 0)
        row["tokens"] += int(tok or 0)
    return {
        "days": days,
        "daily": [{"date": str(d), "kind": k, "units": int(u or 0), "tokens": int(t or 0)} for d, k, u, t in daily],
        "users": sorted(per_user.values(), key=lambda r: -(r["chat"] + r["image"] + r["video"] + r["tts"])),
        "models": [{"kind": k, "model": m, "units": int(u or 0), "tokens": int(t or 0)} for k, m, u, t in by_model],
    }
