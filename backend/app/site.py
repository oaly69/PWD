"""站点级配置的读写（存储在 settings 表中）。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict[str, Any] = {
    "installed": False,
    "site_name": "PWD 创作台",
    "default_chat_provider_id": None,
    "default_chat_model": "",
    "default_image_provider_id": None,
    "default_image_model": "",
    "default_video_provider_id": None,
    "default_video_model": "",
    "default_tts_provider_id": None,
    "default_tts_model": "",
    "enhance_provider_id": None,
    "enhance_model": "",
    "default_system_prompt": "",
    "allow_register": False,  # 是否开放注册
    "register_need_approval": True,  # 注册后是否需要管理员审核
    "default_group_id": None,  # 新注册用户默认加入的用户组
    "failover_enabled": True,  # 请求失败时自动切换到提供同名模型的其他服务
    "public_url": "",  # 站点对外访问地址（用于单点登录回调），为空时根据请求自动推断
    # OIDC 单点登录（Authentik / Keycloak / Logto / Casdoor 等）
    "oidc_enabled": False,
    "oidc_issuer": "",
    "oidc_client_id": "",
    "oidc_client_secret": "",
    "oidc_scopes": "openid profile email",
    "oidc_button_text": "使用单点登录",
    "oidc_auto_create": True,  # 首次登录自动创建账号（是否需要审核沿用注册审核设置）
}

PUBLIC_KEYS = {"site_name", "installed", "allow_register", "oidc_enabled", "oidc_button_text"}
EDITABLE_KEYS = set(DEFAULTS) - {"installed"}
SECRET_KEYS = {"oidc_client_secret"}  # 读取设置时不返回明文


def get_setting(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key)
    return row.value


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def all_settings(db: Session) -> dict[str, Any]:
    data = dict(DEFAULTS)
    for row in db.query(Setting).all():
        data[row.key] = row.value
    return data


def is_installed(db: Session) -> bool:
    return bool(get_setting(db, "installed"))
