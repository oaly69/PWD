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
}

PUBLIC_KEYS = {"site_name", "installed"}
EDITABLE_KEYS = set(DEFAULTS) - {"installed"}


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
