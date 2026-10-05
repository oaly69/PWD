from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db, new_session
from ..deps import current_user
from ..models import Asset, Conversation, Message, Provider, User, utcnow
from ..services import openai_compat
from ..services.media import downscale_for_llm, read_media, to_data_uri
from ..site import get_setting
from .assets import asset_out

router = APIRouter(prefix="/api/conversations", tags=["chat"])

DEFAULT_CONTEXT = 30  # 默认携带的历史消息条数


def msg_out(m: Message, assets: dict[int, Asset]) -> dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "reasoning": m.reasoning or "",
        "model": m.model or "",
        "attachments": [asset_out(assets[i]) for i in (m.attachments or []) if i in assets],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def conv_out(c: Conversation, db: Session | None = None, with_messages: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": c.id,
        "title": c.title,
        "icon": c.icon or "",
        "pinned": bool(c.pinned),
        "provider_id": c.provider_id,
        "model": c.model,
        "system_prompt": c.system_prompt,
        "params": c.params or {},
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if with_messages and db is not None:
        ids = {i for m in c.messages for i in (m.attachments or [])}
        assets = {a.id: a for a in db.query(Asset).filter(Asset.id.in_(ids)).all()} if ids else {}
        data["messages"] = [msg_out(m, assets) for m in c.messages]
    return data


def _get(db: Session, cid: int, user: User) -> Conversation:
    c = db.get(Conversation, cid)
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    return c


class ConversationIn(BaseModel):
    title: str | None = Field(None, max_length=255)
    icon: str | None = Field(None, max_length=16)
    pinned: bool | None = None
    provider_id: int | None = None
    model: str | None = None
    system_prompt: str | None = None
    params: dict[str, Any] | None = None


@router.get("")
def list_conversations(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = db.query(Conversation).filter(Conversation.user_id == user.id)
    if q:
        like = f"%{q}%"
        matched = db.query(Message.conversation_id).join(Conversation).filter(Conversation.user_id == user.id, Message.content.like(like))
        query = query.filter(or_(Conversation.title.like(like), Conversation.id.in_(matched)))
    rows = query.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(500).all()
    return [conv_out(c) for c in rows]


@router.post("")
def create_conversation(body: ConversationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = Conversation(
        user_id=user.id,
        title=body.title or "新对话",
        icon=body.icon or "",
        provider_id=body.provider_id if body.provider_id is not None else get_setting(db, "default_chat_provider_id"),
        model=body.model if body.model is not None else (get_setting(db, "default_chat_model") or ""),
        system_prompt=body.system_prompt if body.system_prompt is not None else (get_setting(db, "default_system_prompt") or ""),
        params=body.params or {},
    )
    db.add(c)
    db.commit()
    return conv_out(c, db, with_messages=True)


@router.get("/{cid}")
def get_conversation(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return conv_out(_get(db, cid, user), db, with_messages=True)


@router.patch("/{cid}")
def update_conversation(cid: int, body: ConversationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    for field in ("title", "icon", "pinned", "provider_id", "model", "system_prompt", "params"):
        value = getattr(body, field)
        if value is not None:
            setattr(c, field, value)
    db.commit()
    return conv_out(c)


@router.delete("/{cid}")
def delete_conversation(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_get(db, cid, user))
    db.commit()
    return {"ok": True}


@router.delete("/{cid}/messages/{mid}")
def delete_message(cid: int, mid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _get(db, cid, user)
    m = db.get(Message, mid)
    if m is None or m.conversation_id != cid:
        raise HTTPException(status_code=404, detail="消息不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}


class MessagePatch(BaseModel):
    content: str
    truncate: bool = False  # 为 True 时删除该消息之后的所有消息（编辑后重新发送）


@router.patch("/{cid}/messages/{mid}")
def edit_message(cid: int, mid: int, body: MessagePatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    m = db.get(Message, mid)
    if m is None or m.conversation_id != cid:
        raise HTTPException(status_code=404, detail="消息不存在")
    m.content = body.content
    if body.truncate:
        for other in list(c.messages):
            if other.id > mid:
                db.delete(other)
    db.commit()
    return {"ok": True}


@router.get("/{cid}/export", response_class=PlainTextResponse)
def export_conversation(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    lines = [f"# {c.title}", ""]
    if c.system_prompt.strip():
        lines += ["> **角色设定**", ">", *[f"> {ln}" for ln in c.system_prompt.splitlines()], ""]
    for m in c.messages:
        who = "🧑 我" if m.role == "user" else f"🤖 {m.model or c.model or '助手'}"
        lines += [f"### {who}", "", m.content, ""]
    filename = quote(f"{c.title}.md")
    return PlainTextResponse(
        "\n".join(lines), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


class SendIn(BaseModel):
    content: str = ""
    attachments: list[int] = Field(default_factory=list, max_length=10)
    regenerate: bool = False  # 为 True 时不新增用户消息，基于现有历史重新生成


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_history(db: Session, c: Conversation) -> list[dict[str, Any]]:
    params = c.params or {}
    context = int(params.get("context_count") or DEFAULT_CONTEXT)
    history: list[dict[str, Any]] = []
    if c.system_prompt.strip():
        history.append({"role": "system", "content": c.system_prompt})
    for m in c.messages[-context:]:
        if m.role == "user" and m.attachments:
            parts: list[dict[str, Any]] = []
            if m.content:
                parts.append({"type": "text", "text": m.content})
            for aid in m.attachments:
                a = db.get(Asset, aid)
                if a is None or a.kind != "image":
                    continue
                data, mime = downscale_for_llm(read_media(a.filename), a.mime)
                parts.append({"type": "image_url", "image_url": {"url": to_data_uri(data, mime)}})
            history.append({"role": "user", "content": parts or m.content})
        else:
            history.append({"role": m.role, "content": m.content})
    return history


@router.post("/{cid}/messages")
async def send_message(cid: int, body: SendIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    provider = db.get(Provider, c.provider_id) if c.provider_id else None
    if provider is None or provider.kind != "openai":
        raise HTTPException(status_code=400, detail="请先为对话选择一个 OpenAI 兼容的模型服务")
    if not c.model:
        raise HTTPException(status_code=400, detail="请先为对话选择模型")

    if body.regenerate:
        while c.messages and c.messages[-1].role == "assistant":
            db.delete(c.messages[-1])
            c.messages.pop()
    else:
        if not body.content.strip() and not body.attachments:
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        if body.attachments:
            owned = db.query(Asset.id).filter(Asset.id.in_(body.attachments), Asset.user_id == user.id).count()
            if owned != len(set(body.attachments)):
                raise HTTPException(status_code=400, detail="附件不存在")
        db.add(Message(conversation_id=c.id, role="user", content=body.content, attachments=body.attachments))
        if c.title == "新对话":
            first = body.content.strip().splitlines()[0] if body.content.strip() else "图片对话"
            c.title = first[:30]
    c.updated_at = utcnow()
    db.commit()
    db.refresh(c)

    history = _build_history(db, c)
    if not any(h["role"] == "user" for h in history):
        raise HTTPException(status_code=400, detail="没有可发送的消息")
    params = dict(c.params or {})
    model = c.model

    def save_reply(content: str, reasoning: str) -> int | None:
        if not content and not reasoning:
            return None
        with new_session() as s:
            msg = Message(conversation_id=cid, role="assistant", content=content, reasoning=reasoning, model=model)
            s.add(msg)
            conv = s.get(Conversation, cid)
            if conv:
                conv.updated_at = utcnow()
            s.commit()
            return msg.id

    async def stream():
        content: list[str] = []
        reasoning: list[str] = []
        saved = False
        try:
            async for kind, delta in openai_compat.chat_stream(provider, model, history, params):
                (content if kind == "content" else reasoning).append(delta)
                yield _sse({"delta": delta} if kind == "content" else {"reasoning": delta})
        except Exception as exc:  # noqa: BLE001
            saved = True
            mid = save_reply("".join(content), "".join(reasoning))
            yield _sse({"error": str(exc) or exc.__class__.__name__, "message_id": mid})
        else:
            saved = True
            yield _sse({"done": True, "message_id": save_reply("".join(content), "".join(reasoning))})
        finally:
            # 客户端中途断开（点击“停止”）时也保留已生成的部分内容
            if not saved:
                save_reply("".join(content), "".join(reasoning))

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{cid}/title")
async def auto_title(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """让模型根据对话内容生成简短标题。"""
    c = _get(db, cid, user)
    provider = db.get(Provider, c.provider_id) if c.provider_id else None
    if provider is None or not c.model or not c.messages:
        raise HTTPException(status_code=400, detail="对话为空或未选择模型")
    snippet = "\n".join(f"{m.role}: {m.content[:300]}" for m in c.messages[:4])
    try:
        title = await openai_compat.chat_complete(provider, c.model, [
            {"role": "system", "content": "根据对话内容生成一个不超过 15 个字的中文标题，只输出标题本身，不要标点和引号。"},
            {"role": "user", "content": snippet},
        ], max_tokens=40)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    title = title.strip().strip('"“”《》').splitlines()[0][:40] if title.strip() else c.title
    c.title = title
    db.commit()
    return {"title": title}
