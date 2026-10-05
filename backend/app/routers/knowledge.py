"""知识库、文档提取、工具目录、语音识别。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, require_admin
from ..models import KbChunk, KbDocument, KnowledgeBase, Provider, User
from ..services import knowledge, openai_compat, policy
from ..services import tools as tools_svc
from ..services.documents import SUPPORTED, extract_text
from ..services.openai_compat import ProviderError
from ..site import get_setting

router = APIRouter(prefix="/api", tags=["knowledge"])

MAX_DOC = 50 * 1024 * 1024


class KbIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field("", max_length=1000)
    embedding_provider_id: int | None = None
    embedding_model: str = ""


def _kb(db: Session, kid: int, user: User) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kid)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


def kb_out(db: Session, kb: KnowledgeBase) -> dict[str, Any]:
    docs = db.query(func.count(KbDocument.id), func.sum(KbDocument.chunk_count)).filter(KbDocument.kb_id == kb.id).one()
    provider = db.get(Provider, kb.embedding_provider_id) if kb.embedding_provider_id else None
    return {
        "id": kb.id, "name": kb.name, "description": kb.description,
        "embedding_provider_id": kb.embedding_provider_id, "embedding_model": kb.embedding_model,
        "embedding_label": f"{provider.name} · {kb.embedding_model}" if provider and kb.embedding_model else "",
        "documents": int(docs[0] or 0), "chunks": int(docs[1] or 0),
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


def doc_out(d: KbDocument) -> dict[str, Any]:
    return {
        "id": d.id, "kb_id": d.kb_id, "filename": d.filename, "size": d.size, "chars": d.chars, "status": d.status,
        "error": d.error, "chunk_count": d.chunk_count, "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _check_embedding(db: Session, body: KbIn) -> None:
    if not body.embedding_provider_id:
        body.embedding_model = ""
        return
    p = db.get(Provider, body.embedding_provider_id)
    if p is None or not p.enabled or body.embedding_model not in (p.embedding_models or []):
        raise HTTPException(status_code=400, detail="向量模型不可用")


@router.get("/kb")
def list_kbs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).order_by(KnowledgeBase.id.desc()).all()
    return [kb_out(db, kb) for kb in rows]


@router.post("/kb")
def create_kb(body: KbIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _check_embedding(db, body)
    kb = KnowledgeBase(user_id=user.id, name=body.name.strip(), description=body.description,
                       embedding_provider_id=body.embedding_provider_id or None, embedding_model=body.embedding_model)
    db.add(kb)
    db.commit()
    return kb_out(db, kb)


@router.patch("/kb/{kid}")
def update_kb(kid: int, body: KbIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = _kb(db, kid, user)
    _check_embedding(db, body)
    changed = (body.embedding_provider_id or None, body.embedding_model) != (kb.embedding_provider_id, kb.embedding_model)
    has_docs = db.query(KbDocument.id).filter(KbDocument.kb_id == kb.id).first() is not None
    if changed and has_docs:
        raise HTTPException(status_code=400, detail="已有文档的知识库不能更换向量模型，请新建知识库")
    kb.name = body.name.strip()
    kb.description = body.description
    kb.embedding_provider_id = body.embedding_provider_id or None
    kb.embedding_model = body.embedding_model
    db.commit()
    return kb_out(db, kb)


@router.delete("/kb/{kid}")
def delete_kb(kid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_kb(db, kid, user))
    db.commit()
    return {"ok": True}


@router.get("/kb/{kid}/documents")
def list_documents(kid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = _kb(db, kid, user)
    rows = db.query(KbDocument).filter(KbDocument.kb_id == kb.id).order_by(KbDocument.id.desc()).all()
    return [doc_out(d) for d in rows]


@router.post("/kb/{kid}/documents")
async def upload_document(kid: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = _kb(db, kid, user)
    data = await file.read(MAX_DOC + 1)
    if len(data) > MAX_DOC:
        raise HTTPException(status_code=413, detail="文档超过 50MB 限制")
    name = (file.filename or "未命名").rsplit("/", 1)[-1][:255]
    ext = name[name.rfind("."):].lower() if "." in name else ""
    if ext and ext not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"暂不支持 {ext} 格式")
    doc = KbDocument(kb_id=kb.id, filename=name, size=len(data), status="pending")
    db.add(doc)
    db.commit()
    knowledge.submit_document(doc.id, data)
    return doc_out(doc)


@router.delete("/kb/{kid}/documents/{did}")
def delete_document(kid: int, did: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = _kb(db, kid, user)
    doc = db.get(KbDocument, did)
    if doc is None or doc.kb_id != kb.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    db.query(KbChunk).filter(KbChunk.doc_id == doc.id).delete()
    db.delete(doc)
    db.commit()
    return {"ok": True}


class SearchIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(6, ge=1, le=20)


@router.post("/kb/{kid}/search")
async def search_kb(kid: int, body: SearchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    kb = _kb(db, kid, user)
    try:
        return await knowledge.search(db, [kb.id], body.query, body.top_k)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/files/extract")
async def extract_file(file: UploadFile = File(...), _user: User = Depends(current_user)):
    """提取文档文字，用于在对话中直接附带文档。"""
    import asyncio

    data = await file.read(MAX_DOC + 1)
    if len(data) > MAX_DOC:
        raise HTTPException(status_code=413, detail="文档超过 50MB 限制")
    name = (file.filename or "未命名").rsplit("/", 1)[-1][:255]
    try:
        text = await asyncio.to_thread(extract_text, name, data)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from .chat import FILE_LIMIT

    return {"name": name, "chars": len(text), "text": text[:FILE_LIMIT], "truncated": len(text) > FILE_LIMIT}


@router.get("/tools")
async def list_tools(db: Session = Depends(get_db), _user: User = Depends(current_user)):
    return await tools_svc.catalog(db)


@router.post("/audio/transcribe")
async def transcribe(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    pid, model = get_setting(db, "stt_provider_id"), get_setting(db, "stt_model")
    provider = db.get(Provider, pid) if pid else None
    if provider is None or not model or not provider.enabled:
        raise HTTPException(status_code=400, detail="管理员尚未配置语音识别模型")
    policy.check_access(db, user, "chat")
    data = await file.read(25 * 1024 * 1024 + 1)
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="录音过长")
    try:
        text = await openai_compat.transcribe(provider, model, data, file.filename or "audio.webm", file.content_type or "audio/webm")
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": text}


class McpTestIn(BaseModel):
    url: str = Field(..., max_length=1000)
    headers: dict[str, str] = Field(default_factory=dict)


@router.post("/tools/mcp/test")
async def test_mcp(body: McpTestIn, _admin: User = Depends(require_admin)):
    """测试 MCP 服务连接并列出其工具（管理员）。"""
    from ..services import mcp

    try:
        tools = await mcp.list_tools({"id": "_test", "url": body.url, "headers": body.headers}, use_cache=False)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"连接失败：{exc}"}
    return {"ok": True, "message": f"连接成功，发现 {len(tools)} 个工具", "tools": [{"name": t["name"], "description": t.get("description", "")} for t in tools]}
