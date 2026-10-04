from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Provider
from ..security import mask_secret
from ..services import comfyui, openai_compat
from ..services.openai_compat import ProviderError

router = APIRouter(prefix="/api/providers", tags=["providers"], dependencies=[Depends(current_user)])


class ProviderIn(BaseModel):
    name: str = Field("默认服务", max_length=64)
    kind: Literal["openai", "comfyui"] = "openai"
    base_url: str = Field(..., max_length=512)
    api_key: str | None = None  # 更新时为 None 表示保持不变
    enabled: bool = True
    chat_models: list[str] = []
    image_models: list[str] = []
    extra: dict[str, Any] = {}


def _clean_models(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in seen:
            seen.append(item)
    return seen


def apply_provider(provider: Provider, body: ProviderIn) -> None:
    provider.name = body.name.strip() or "未命名服务"
    provider.kind = body.kind
    provider.base_url = body.base_url.strip().rstrip("/")
    if body.api_key is not None:
        provider.api_key = body.api_key.strip()
    elif provider.api_key is None:
        provider.api_key = ""
    provider.enabled = body.enabled
    provider.chat_models = _clean_models(body.chat_models) if body.kind == "openai" else []
    provider.image_models = _clean_models(body.image_models)
    provider.extra = body.extra or {}
    if body.kind == "comfyui":
        workflows = provider.extra.get("workflows") or {}
        if not isinstance(workflows, dict):
            raise HTTPException(status_code=422, detail="workflows 必须是 {名称: 工作流 JSON} 的对象")
        provider.image_models = list(workflows.keys())


def provider_out(p: Provider) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "base_url": p.base_url,
        "api_key_masked": mask_secret(p.api_key or ""),
        "has_key": bool(p.api_key),
        "enabled": p.enabled,
        "chat_models": p.chat_models or [],
        "image_models": p.image_models or [],
        "extra": p.extra or {},
    }


async def test_provider_connection(provider: Provider) -> dict[str, Any]:
    try:
        if provider.kind == "comfyui":
            stats = await comfyui.check(provider)
            return {"ok": True, "message": "ComfyUI 连接成功", "detail": stats.get("system", {})}
        models = await openai_compat.list_models(provider)
        return {"ok": True, "message": f"连接成功，发现 {len(models)} 个模型", "models": models}
    except ProviderError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 - 网络错误等
        return {"ok": False, "message": f"连接失败：{exc.__class__.__name__}: {exc}"}


def _get(db: Session, provider_id: int) -> Provider:
    p = db.get(Provider, provider_id)
    if p is None:
        raise HTTPException(status_code=404, detail="模型服务不存在")
    return p


@router.get("")
def list_providers(db: Session = Depends(get_db)):
    return [provider_out(p) for p in db.query(Provider).order_by(Provider.id).all()]


@router.get("/comfyui/example")
def comfyui_example():
    return {"workflows": {"SDXL 文生图": comfyui.EXAMPLE_WORKFLOW}}


@router.post("")
def create_provider(body: ProviderIn, db: Session = Depends(get_db)):
    p = Provider()
    apply_provider(p, body)
    db.add(p)
    db.commit()
    return provider_out(p)


@router.put("/{provider_id}")
def update_provider(provider_id: int, body: ProviderIn, db: Session = Depends(get_db)):
    p = _get(db, provider_id)
    apply_provider(p, body)
    db.commit()
    return provider_out(p)


@router.delete("/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, provider_id))
    db.commit()
    return {"ok": True}


@router.post("/{provider_id}/test")
async def test_provider(provider_id: int, db: Session = Depends(get_db)):
    return await test_provider_connection(_get(db, provider_id))


@router.get("/{provider_id}/remote-models")
async def remote_models(provider_id: int, db: Session = Depends(get_db)):
    p = _get(db, provider_id)
    if p.kind != "openai":
        raise HTTPException(status_code=400, detail="仅 OpenAI 兼容服务支持拉取模型列表")
    try:
        return {"models": await openai_compat.list_models(p)}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"连接失败：{exc}") from exc
