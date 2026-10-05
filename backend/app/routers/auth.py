from __future__ import annotations

import time
from collections import defaultdict

import re
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import STATUS_MESSAGE, current_user, require_installed
from ..models import User, UserGroup, utcnow
from ..security import (
    COOKIE_NAME, SESSION_TTL, create_session_token, decode_session_token, hash_password, load_payload, new_totp_secret,
    sign_payload, totp_uri, verify_password, verify_totp,
)
from ..services import oidc
from ..services.audit import audit
from ..site import get_setting

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 简单的登录失败限流：同一 IP 10 分钟内最多失败 10 次
_FAIL_WINDOW = 600
_FAIL_LIMIT = 10
_failures: dict[str, list[float]] = defaultdict(list)
_registers: dict[str, list[float]] = defaultdict(list)  # 同一 IP 每小时最多注册 5 次


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True, samesite="lax", path="/",
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class LoginIn(BaseModel):
    username: str
    password: str
    code: str | None = None  # 两步验证码


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
        audit(db, user, "auth.login_failed", detail="密码错误", request=request, username=body.username.strip())
        db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.totp_secret:
        if not body.code:
            return {"ok": False, "need_totp": True}
        if not verify_totp(user.totp_secret, body.code):
            _failures[ip].append(now)
            audit(db, user, "auth.login_failed", detail="两步验证码错误", request=request)
            db.commit()
            raise HTTPException(status_code=401, detail="验证码错误或已过期")
    _failures.pop(ip, None)
    if user.status != "active":
        raise HTTPException(status_code=403, detail=STATUS_MESSAGE.get(user.status, "账号不可用"))
    user.last_login_at = utcnow()
    audit(db, user, "auth.login", request=request)
    db.commit()
    set_session_cookie(response, create_session_token(user.id, user.token_version))
    return {"ok": True, "username": user.username}


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_\-\u4e00-\u9fa5]+$")
    password: str = Field(..., min_length=8, max_length=128)


@router.post("/register", dependencies=[Depends(require_installed)])
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_setting(db, "allow_register"):
        raise HTTPException(status_code=403, detail="当前站点未开放注册，请联系管理员")
    ip = _client_ip(request)
    now = time.time()
    _registers[ip] = [t for t in _registers[ip] if now - t < 3600]
    if len(_registers[ip]) >= 5:
        raise HTTPException(status_code=429, detail="注册过于频繁，请稍后再试")
    username = body.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="用户名已被占用")
    status = "pending" if get_setting(db, "register_need_approval") else "active"
    user = User(username=username, password_hash=hash_password(body.password), is_admin=False, status=status,
                group_id=_default_group(db))
    db.add(user)
    db.flush()
    audit(db, user, "auth.register", detail="待审核" if status == "pending" else "", request=request)
    db.commit()
    _registers[ip].append(now)
    if status == "active":
        user.last_login_at = utcnow()
        db.commit()
        set_session_cookie(response, create_session_token(user.id, user.token_version))
    return {"ok": True, "username": user.username, "status": status}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id, "username": user.username, "is_admin": user.is_admin, "role": user.role, "status": user.status,
        "totp_enabled": bool(user.totp_secret), "oidc_linked": bool(user.oidc_sub),
    }


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/password")
def change_password(
    body: PasswordIn, request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # 使其他会话失效
    audit(db, user, "auth.password", request=request)
    db.commit()
    set_session_cookie(response, create_session_token(user.id, user.token_version))
    return {"ok": True}


def _default_group(db: Session) -> int | None:
    gid = get_setting(db, "default_group_id")
    return gid if gid and db.get(UserGroup, gid) else None


# ---------------------------------------------------------------- 两步验证


@router.post("/2fa/setup")
def totp_setup(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """生成新的密钥（尚未生效，需用验证码确认后开启）。"""
    secret = new_totp_secret()
    return {"secret": secret, "uri": totp_uri(secret, user.username, get_setting(db, "site_name") or "PWD")}


class TotpEnableIn(BaseModel):
    secret: str = Field(..., min_length=16, max_length=64)
    code: str


@router.post("/2fa/enable")
def totp_enable(body: TotpEnableIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_totp(body.secret, body.code):
        raise HTTPException(status_code=400, detail="验证码不正确，请确认手机时间准确后重试")
    user.totp_secret = body.secret
    audit(db, user, "auth.2fa_enable", request=request)
    db.commit()
    return {"ok": True}


class TotpDisableIn(BaseModel):
    password: str


@router.post("/2fa/disable")
def totp_disable(body: TotpDisableIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="密码不正确")
    user.totp_secret = ""
    audit(db, user, "auth.2fa_disable", request=request)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- OIDC 单点登录

OIDC_COOKIE = "pwd_oidc"


def _oidc_settings(db: Session) -> dict:
    keys = ("oidc_enabled", "oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_scopes", "oidc_auto_create", "public_url")
    conf = {k: get_setting(db, k) for k in keys}
    if not conf["oidc_enabled"] or not conf["oidc_issuer"] or not conf["oidc_client_id"]:
        raise HTTPException(status_code=404, detail="未启用单点登录")
    return conf


def _redirect_uri(request: Request, public_url: str) -> str:
    base = (public_url or str(request.base_url)).rstrip("/")
    return f"{base}/api/auth/oidc/callback"


def _fail(msg: str) -> RedirectResponse:
    return RedirectResponse(f"/login?sso_error={quote(msg)}", status_code=302)


@router.get("/oidc/login", dependencies=[Depends(require_installed)])
async def oidc_login(request: Request, link: bool = False, db: Session = Depends(get_db)):
    conf = _oidc_settings(db)
    link_uid = None
    if link:
        payload = decode_session_token(request.cookies.get(COOKIE_NAME, ""))
        if not payload:
            raise HTTPException(status_code=401, detail="请先登录")
        link_uid = int(payload["sub"])
    try:
        meta = await oidc.discover(conf["oidc_issuer"])
    except Exception as exc:  # noqa: BLE001
        return _fail(f"单点登录暂不可用：{exc}")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(16)
    url = oidc.authorize_url(meta, conf["oidc_client_id"], _redirect_uri(request, conf["public_url"]), state, conf["oidc_scopes"], nonce)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(OIDC_COOKIE, sign_payload({"state": state, "link": link_uid}), max_age=600, httponly=True, samesite="lax", path="/")
    return resp


def _username_from(info: dict, db: Session) -> str:
    raw = info.get("preferred_username") or (info.get("email") or "").split("@")[0] or info.get("name") or "user"
    base = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fa5]", "", raw)[:28] or "user"
    if len(base) < 2:
        base = f"{base}_u"
    name, n = base, 1
    while db.query(User).filter(User.username == name).first():
        n += 1
        name = f"{base}{n}"
    return name


@router.get("/oidc/callback", dependencies=[Depends(require_installed)])
async def oidc_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    conf = _oidc_settings(db)
    saved = load_payload(request.cookies.get(OIDC_COOKIE, ""))
    if error:
        return _fail(f"登录被取消或失败：{error}")
    if not saved or not code or not secrets.compare_digest(str(saved.get("state", "")), state):
        return _fail("登录状态已失效，请重试")
    try:
        meta = await oidc.discover(conf["oidc_issuer"])
        tokens = await oidc.exchange(meta, code, _redirect_uri(request, conf["public_url"]), conf["oidc_client_id"], conf["oidc_client_secret"] or "")
        info = await oidc.userinfo(meta, tokens)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"单点登录失败：{exc}")
    sub = f"{conf['oidc_issuer'].rstrip('/')}|{info['sub']}"
    owner = db.query(User).filter(User.oidc_sub == sub).first()

    if saved.get("link"):
        user = db.get(User, int(saved["link"]))
        if user is None:
            return _fail("账号不存在")
        if owner is not None and owner.id != user.id:
            resp = RedirectResponse("/settings?sso=taken", status_code=302)
        else:
            user.oidc_sub = sub
            audit(db, user, "auth.oidc_link", detail=info.get("preferred_username") or info.get("email") or "", request=request)
            db.commit()
            resp = RedirectResponse("/settings?sso=linked", status_code=302)
        resp.delete_cookie(OIDC_COOKIE, path="/")
        return resp

    user = owner
    if user is None:
        if not conf["oidc_auto_create"]:
            return _fail("该单点登录账号尚未绑定，请先用密码登录后在「账号安全」中绑定")
        status = "pending" if get_setting(db, "register_need_approval") else "active"
        user = User(
            username=_username_from(info, db), password_hash=hash_password(secrets.token_urlsafe(32)), is_admin=False,
            status=status, oidc_sub=sub, group_id=_default_group(db),
        )
        db.add(user)
        db.flush()
        audit(db, user, "auth.register", detail="单点登录自动创建" + ("，待审核" if status == "pending" else ""), request=request)
        db.commit()
    if user.status != "active":
        resp = RedirectResponse("/login?sso=pending" if user.status == "pending" else f"/login?sso_error={quote(STATUS_MESSAGE.get(user.status, '账号不可用'))}", status_code=302)
        resp.delete_cookie(OIDC_COOKIE, path="/")
        return resp
    user.last_login_at = utcnow()
    audit(db, user, "auth.oidc_login", request=request)
    db.commit()
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(OIDC_COOKIE, path="/")
    set_session_cookie(resp, create_session_token(user.id, user.token_version))
    return resp


@router.post("/oidc/unlink")
def oidc_unlink(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user.oidc_sub = None
    audit(db, user, "auth.oidc_link", detail="解除绑定", request=request)
    db.commit()
    return {"ok": True}
