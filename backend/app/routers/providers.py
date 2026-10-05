from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_admin
from ..models import User
from ..models import Provider
from ..security import mask_secret
from ..services import comfyui, openai_compat, policy
from ..services.audit import audit
from ..services.openai_compat import ProviderError

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderIn(BaseModel):
    name: str = Field("默认服务", max_length=64)
    kind: Literal["openai", "comfyui"] = "openai"
    base_url: str = Field(..., max_length=512)
    api_key: str | None = None  # 更新时为 None 表示保持不变
    enabled: bool = True
    chat_models: list[str] = []
    image_models: list[str] = []
    video_models: list[str] = []
    tts_models: list[str] = []
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
    provider.video_models = _clean_models(body.video_models)
    provider.tts_models = _clean_models(body.tts_models) if body.kind == "openai" else []
    provider.extra = body.extra or {}
    if body.kind == "comfyui":
        workflows = provider.extra.get("workflows") or {}
        if not isinstance(workflows, dict):
            raise HTTPException(status_code=422, detail="workflows 必须是 {名称: 工作流 JSON} 的对象")
        # extra.workflow_kinds 标记每个工作流用于图像还是视频，默认图像
        kinds = provider.extra.get("workflow_kinds") or {}
        provider.image_models = [n for n in workflows if kinds.get(n, "image") == "image"]
        provider.video_models = [n for n in workflows if kinds.get(n) == "video"]


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
        "video_models": p.video_models or [],
        "tts_models": p.tts_models or [],
        "extra": p.extra or {},
    }


async def test_provider_connection(provider: Provider) -> dict[str, Any]:
    try:
        if provider.kind == "comfyui":
            stats = await comfyui.check(provider)
            return {"ok": True, "message": "ComfyUI 连接成功", "detail": stats.get("system", {})}
        models = await openai_compat.list_models(provider)
        return {"ok": True, "message": f"连接成功，发现 {len(models)} 个模型", "models": models, "classified": classify_models(models)}
    except ProviderError as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 - 网络错误等
        return {"ok": False, "message": f"连接失败：{exc.__class__.__name__}: {exc}"}


_IMAGE_HINTS = ("image", "dall-e", "flux", "kolors", "stable-diffusion", "sdxl", "sd3", "imagen", "midjourney",
                "seedream", "cogview", "hidream", "recraft", "ideogram", "qwen-image", "janus", "wanx")
_VIDEO_HINTS = ("video", "sora", "veo", "kling", "wan2", "wan-", "hunyuanvideo", "seedance", "hailuo", "cogvideo",
                "runway", "pika", "vidu", "ltx")
_TTS_HINTS = ("tts", "speech", "cosyvoice", "fish-speech", "fishaudio", "indextts", "moss-tts", "voice")
_SKIP_HINTS = ("embed", "rerank", "whisper", "asr", "moderation", "sensevoice", "bge-", "transcribe")


def classify_models(models: list[str]) -> dict[str, list[str]]:
    """按名称特征把模型粗略归类为 文本 / 图像 / 视频 / 语音，供前端一键勾选。"""
    out: dict[str, list[str]] = {"chat": [], "image": [], "video": [], "tts": [], "other": []}
    for m in models:
        low = m.lower()
        if any(h in low for h in _SKIP_HINTS):
            out["other"].append(m)
        elif any(h in low for h in _VIDEO_HINTS):
            out["video"].append(m)
        elif any(h in low for h in _TTS_HINTS):
            out["tts"].append(m)
        elif any(h in low for h in _IMAGE_HINTS) and "vl" not in low.split("-") and "vision" not in low:
            out["image"].append(m)
        else:
            out["chat"].append(m)
    return out


def _get(db: Session, provider_id: int) -> Provider:
    p = db.get(Provider, provider_id)
    if p is None:
        raise HTTPException(status_code=404, detail="模型服务不存在")
    return p


def provider_public(p: Provider, group=None) -> dict[str, Any]:
    """普通用户可见的信息：只包含选择模型所需的字段（按用户组过滤），不暴露地址、Key 与工作流。"""
    extra = p.extra or {}
    return {
        "id": p.id,
        "name": p.name,
        "kind": p.kind,
        "enabled": p.enabled,
        "chat_models": policy.filter_models(group, p.id, "chat", p.chat_models or []),
        "image_models": policy.filter_models(group, p.id, "image", p.image_models or []),
        "video_models": policy.filter_models(group, p.id, "video", p.video_models or []),
        "tts_models": policy.filter_models(group, p.id, "tts", p.tts_models or []),
        "extra": {k: extra[k] for k in ("image_edit_mode", "video_api") if k in extra},
    }


@router.get("")
def list_providers(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Provider).order_by(Provider.id).all()
    if user.is_admin:
        return [provider_out(p) for p in rows]
    group = policy.group_of(db, user)
    return [provider_public(p, group) for p in rows if p.enabled]


@router.get("/comfyui/example", dependencies=[Depends(require_admin)])
def comfyui_example():
    return {"workflows": {
        "SDXL 文生图": comfyui.EXAMPLE_WORKFLOW,
        "SDXL 局部重绘": comfyui.EXAMPLE_INPAINT,
        "4x 高清放大": comfyui.EXAMPLE_UPSCALE,
    }}


class DraftTestIn(ProviderIn):
    id: int | None = None  # 编辑已有服务且未填写新 Key 时，沿用已保存的 Key


@router.post("/test-draft", dependencies=[Depends(require_admin)])
async def test_draft(body: DraftTestIn, db: Session = Depends(get_db)):
    """测试尚未保存的配置（用于表单中的“测试连接 / 获取模型”）。"""
    tmp = Provider()
    if body.id and body.api_key is None:
        saved = db.get(Provider, body.id)
        tmp.api_key = saved.api_key if saved else ""
    apply_provider(tmp, body)
    return await test_provider_connection(tmp)


@router.post("")
def create_provider(body: ProviderIn, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    p = Provider()
    apply_provider(p, body)
    db.add(p)
    audit(db, admin, "provider.create", p.name, p.base_url, request)
    db.commit()
    return provider_out(p)


@router.put("/{provider_id}")
def update_provider(provider_id: int, body: ProviderIn, request: Request, db: Session = Depends(get_db),
                    admin: User = Depends(require_admin)):
    p = _get(db, provider_id)
    apply_provider(p, body)
    audit(db, admin, "provider.update", p.name, "更换了 API Key" if body.api_key else "", request)
    db.commit()
    return provider_out(p)


@router.delete("/{provider_id}")
def delete_provider(provider_id: int, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    p = _get(db, provider_id)
    audit(db, admin, "provider.delete", p.name, p.base_url, request)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{provider_id}/test", dependencies=[Depends(require_admin)])
async def test_provider(provider_id: int, db: Session = Depends(get_db)):
    return await test_provider_connection(_get(db, provider_id))


@router.get("/{provider_id}/remote-models", dependencies=[Depends(require_admin)])
async def remote_models(provider_id: int, db: Session = Depends(get_db)):
    p = _get(db, provider_id)
    if p.kind != "openai":
        raise HTTPException(status_code=400, detail="仅 OpenAI 兼容服务支持拉取模型列表")
    try:
        models = await openai_compat.list_models(p)
        return {"models": models, "classified": classify_models(models)}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"连接失败：{exc}") from exc
