from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import COOKIE_NAME, decode_session_token
from .site import is_installed


def require_installed(db: Session = Depends(get_db)) -> None:
    if not is_installed(db):
        raise HTTPException(status_code=409, detail="系统尚未安装，请先完成安装向导")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if not is_installed(db):
        raise HTTPException(status_code=409, detail="系统尚未安装，请先完成安装向导")
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    payload = decode_session_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    user = db.get(User, int(payload["sub"]))
    if user is None or user.token_version != payload.get("ver"):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user
