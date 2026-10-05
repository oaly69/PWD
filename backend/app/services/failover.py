"""故障切换：请求失败（网络错误、429 限流、5xx）时，自动改用提供同名模型的其他服务。

候选顺序：用户选择的服务优先，其余按服务的 extra.priority 从高到低。
"""
from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from ..models import Provider
from ..site import get_setting
from .openai_compat import ProviderError

FIELD = {"chat": "chat_models", "image": "image_models", "video": "video_models", "tts": "tts_models"}


def priority(p: Provider) -> int:
    try:
        return int((p.extra or {}).get("priority") or 0)
    except (TypeError, ValueError):
        return 0


def candidates(db: Session, provider: Provider, model: str, kind: str) -> list[Provider]:
    if not get_setting(db, "failover_enabled"):
        return [provider]
    field = FIELD.get(kind)
    others = [
        p for p in db.query(Provider).filter(Provider.enabled.is_(True), Provider.id != provider.id).all()
        if field and p.kind == provider.kind and model in (getattr(p, field) or [])
    ]
    others.sort(key=lambda p: (-priority(p), p.id))
    return [provider, *others]


def retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, ProviderError):
        status = getattr(exc, "status", None)
        return status is not None and (status == 429 or status >= 500)
    return False
