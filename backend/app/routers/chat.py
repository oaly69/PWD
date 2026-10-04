from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db, new_session
from ..deps import current_user
from ..models import Conversation, Message, Provider, utcnow
from ..services import openai_compat
from ..site import get_setting

router = APIRouter(prefix="/api/conversations", tags=["chat"], dependencies=[Depends(current_user)])

MAX_HISTORY = 50  # 每次请求携带的历史消息上限


def conv_out(c: Conversation, with_messages: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": c.id,
        "title": c.title,
        "provider_id": c.provider_id,
        "model": c.model,
        "system_prompt": c.system_prompt,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if with_messages:
        data["messages"] = [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in c.messages
        ]
    return data


def _get(db: Session, cid: int) -> Conversation:
    c = db.get(Conversation, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return c


class ConversationIn(BaseModel):
    title: str | None = Field(None, max_length=255)
    provider_id: int | None = None
    model: str | None = None
    system_prompt: str | None = None


@router.get("")
def list_conversations(db: Session = Depends(get_db)):
    rows = db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(200).all()
    return [conv_out(c) for c in rows]


@router.post("")
def create_conversation(body: ConversationIn, db: Session = Depends(get_db)):
    c = Conversation(
        title=body.title or "新对话",
        provider_id=body.provider_id if body.provider_id is not None else get_setting(db, "default_chat_provider_id"),
        model=body.model if body.model is not None else (get_setting(db, "default_chat_model") or ""),
        system_prompt=body.system_prompt if body.system_prompt is not None else (get_setting(db, "default_system_prompt") or ""),
    )
    db.add(c)
    db.commit()
    return conv_out(c, with_messages=True)


@router.get("/{cid}")
def get_conversation(cid: int, db: Session = Depends(get_db)):
    return conv_out(_get(db, cid), with_messages=True)


@router.patch("/{cid}")
def update_conversation(cid: int, body: ConversationIn, db: Session = Depends(get_db)):
    c = _get(db, cid)
    for field in ("title", "provider_id", "model", "system_prompt"):
        value = getattr(body, field)
        if value is not None:
            setattr(c, field, value)
    db.commit()
    return conv_out(c)


@router.delete("/{cid}")
def delete_conversation(cid: int, db: Session = Depends(get_db)):
    db.delete(_get(db, cid))
    db.commit()
    return {"ok": True}


@router.delete("/{cid}/messages/{mid}")
def delete_message(cid: int, mid: int, db: Session = Depends(get_db)):
    m = db.get(Message, mid)
    if m is None or m.conversation_id != cid:
        raise HTTPException(status_code=404, detail="消息不存在")
    db.delete(m)
    db.commit()
    return {"ok": True}


class SendIn(BaseModel):
    content: str = ""
    regenerate: bool = False  # 为 True 时不新增用户消息，基于现有历史重新生成
    temperature: float | None = None
    max_tokens: int | None = None


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{cid}/messages")
async def send_message(cid: int, body: SendIn, db: Session = Depends(get_db)):
    c = _get(db, cid)
    provider = db.get(Provider, c.provider_id) if c.provider_id else None
    if provider is None or provider.kind != "openai":
        raise HTTPException(status_code=400, detail="请先为对话选择一个 OpenAI 兼容的模型服务")
    if not c.model:
        raise HTTPException(status_code=400, detail="请先为对话选择模型")

    if body.regenerate:
        # 删除末尾的助手回复后重新生成
        while c.messages and c.messages[-1].role == "assistant":
            db.delete(c.messages[-1])
            c.messages.pop()
    else:
        if not body.content.strip():
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        db.add(Message(conversation_id=c.id, role="user", content=body.content))
        if c.title == "新对话":
            c.title = body.content.strip().splitlines()[0][:30] or "新对话"
    c.updated_at = utcnow()
    db.commit()
    db.refresh(c)

    history: list[dict[str, str]] = []
    if c.system_prompt.strip():
        history.append({"role": "system", "content": c.system_prompt})
    history += [{"role": m.role, "content": m.content} for m in c.messages[-MAX_HISTORY:]]
    if len(history) == (1 if c.system_prompt.strip() else 0):
        raise HTTPException(status_code=400, detail="没有可发送的消息")

    params = {"temperature": body.temperature, "max_tokens": body.max_tokens}
    model = c.model

    def save_reply(content: str) -> int | None:
        if not content:
            return None
        with new_session() as s:
            msg = Message(conversation_id=cid, role="assistant", content=content)
            s.add(msg)
            s.commit()
            return msg.id

    async def stream():
        parts: list[str] = []
        saved = False
        try:
            async for delta in openai_compat.chat_stream(provider, model, history, params):
                parts.append(delta)
                yield _sse({"delta": delta})
        except Exception as exc:  # noqa: BLE001
            saved = True
            yield _sse({"error": str(exc) or exc.__class__.__name__, "message_id": save_reply("".join(parts))})
        else:
            saved = True
            yield _sse({"done": True, "message_id": save_reply("".join(parts))})
        finally:
            # 客户端中途断开（点击“停止”）时也保留已生成的部分内容
            if not saved:
                save_reply("".join(parts))

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
