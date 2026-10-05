from __future__ import annotations

import hmac
import threading

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import VERSION, settings
from ..db import get_db
from ..models import Provider, User, utcnow
from ..security import create_session_token, hash_password
from ..seed import seed_defaults
from ..site import is_installed, set_setting
from .auth import set_session_cookie
from .providers import ProviderIn, apply_provider, test_provider_connection

router = APIRouter(prefix="/api/install", tags=["install"])
_lock = threading.Lock()


class InstallIn(BaseModel):
    site_name: str = Field("PWD 创作台", max_length=64)
    admin_username: str = Field(..., min_length=2, max_length=64)
    admin_password: str = Field(..., min_length=8, max_length=128)
    install_token: str = ""
    provider: ProviderIn | None = None


def _check_token(token: str) -> None:
    if settings.install_token and not hmac.compare_digest(token.strip(), settings.install_token):
        raise HTTPException(status_code=403, detail="安装令牌不正确")


@router.get("/status")
def install_status(db: Session = Depends(get_db)):
    return {
        "installed": is_installed(db),
        "need_token": bool(settings.install_token),
        "version": VERSION,
        "data_dir": str(settings.data_dir),
    }


class TestIn(BaseModel):
    install_token: str = ""
    provider: ProviderIn


@router.post("/test-provider")
async def install_test_provider(body: TestIn, db: Session = Depends(get_db)):
    if is_installed(db):
        raise HTTPException(status_code=409, detail="系统已安装")
    _check_token(body.install_token)
    tmp = Provider()
    apply_provider(tmp, body.provider)
    return await test_provider_connection(tmp)


@router.post("")
def do_install(body: InstallIn, response: Response, db: Session = Depends(get_db)):
    with _lock:
        if is_installed(db):
            raise HTTPException(status_code=409, detail="系统已安装，无法重复安装")
        _check_token(body.install_token)

        user = User(username=body.admin_username.strip(), password_hash=hash_password(body.admin_password), is_admin=True, status="active", last_login_at=utcnow())
        db.add(user)
        set_setting(db, "site_name", body.site_name.strip() or "PWD 创作台")

        if body.provider and body.provider.base_url.strip():
            provider = Provider()
            apply_provider(provider, body.provider)
            db.add(provider)
            db.flush()
            if provider.chat_models:
                set_setting(db, "default_chat_provider_id", provider.id)
                set_setting(db, "default_chat_model", provider.chat_models[0])
            for kind, models in (("image", provider.image_models), ("video", provider.video_models), ("tts", provider.tts_models)):
                if models:
                    set_setting(db, f"default_{kind}_provider_id", provider.id)
                    set_setting(db, f"default_{kind}_model", models[0])
            if provider.stt_models:
                set_setting(db, "stt_provider_id", provider.id)
                set_setting(db, "stt_model", provider.stt_models[0])

        seed_defaults(db)
        set_setting(db, "installed", True)
        db.commit()

    set_session_cookie(response, create_session_token(user.id, user.token_version))
    return {"ok": True, "username": user.username}
