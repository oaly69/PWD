from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_installed
from ..models import User
from ..security import COOKIE_NAME, SESSION_TTL, create_session_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 简单的登录失败限流：同一 IP 10 分钟内最多失败 10 次
_FAIL_WINDOW = 600
_FAIL_LIMIT = 10
_failures: dict[str, list[float]] = defaultdict(list)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True, samesite="lax", path="/",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login", dependencies=[Depends(require_installed)])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    now = time.time()
    _failures[ip] = [t for t in _failures[ip] if now - t < _FAIL_WINDOW]
    if len(_failures[ip]) >= _FAIL_LIMIT:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")

    user = db.query(User).filter(User.username == body.username.strip()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        _failures[ip].append(now)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    _failures.pop(ip, None)
    set_session_cookie(response, create_session_token(user.id, user.token_version))
    return {"ok": True, "username": user.username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/password")
def change_password(
    body: PasswordIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # 使其他会话失效
    db.commit()
    set_session_cookie(response, create_session_token(user.id, user.token_version))
    return {"ok": True}
