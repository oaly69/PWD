from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db, new_session
from ..deps import current_user
from ..models import Asset, Conversation, KnowledgeBase, Message, Provider, User, utcnow
from ..services import failover, knowledge, openai_compat, policy, websearch
from ..services import tools as tools_svc
from ..services.media import downscale_for_llm, read_media, to_data_uri
from ..site import get_setting
from .assets import asset_out

router = APIRouter(prefix="/api/conversations", tags=["chat"])
FILE_LIMIT_MAX = 120_000

DEFAULT_CONTEXT = 30  # 默认携带的历史消息条数


def msg_out(m: Message, assets: dict[int, Asset]) -> dict[str, Any]:
    meta = m.meta or {}
    return {
        "id": m.id,
        "parent_id": m.parent_id,
        "role": m.role,
        "content": m.content,
        "reasoning": m.reasoning or "",
        "model": m.model or "",
        "provider_id": meta.get("provider_id"),
        "compare_group": meta.get("compare_group") or "",
        "error": meta.get("error") or "",
        "served_by": meta.get("served_by") or "",
        "attachments": [asset_out(assets[i]) for i in (m.attachments or []) if i in assets],
        "files": [{"name": f.get("name", ""), "chars": f.get("chars", 0)} for f in meta.get("files") or []],
        "sources": meta.get("sources") or [],
        "tools": [
            {**{k: t.get(k) for k in ("name", "label", "args", "result")}, "assets": [asset_out(assets[i]) for i in t.get("asset_ids") or [] if i in assets]}
            for t in meta.get("tools") or []
        ],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ---------------------------------------------------------------- 消息树


class Tree:
    """对话消息树：按父消息分组，计算当前分支路径。"""

    def __init__(self, messages: list[Message]):
        self.by_id = {m.id: m for m in messages}
        self.children: dict[int | None, list[Message]] = {}
        for m in sorted(messages, key=lambda x: x.id):
            parent = m.parent_id if m.parent_id in self.by_id else None
            self.children.setdefault(parent, []).append(m)

    def latest_leaf(self, start: int | None) -> int | None:
        """沿着最新的子消息一路向下，返回分支末端。"""
        node = start
        while self.children.get(node):
            node = self.children[node][-1].id
        return node

    def path(self, leaf: int | None) -> list[Message]:
        if leaf not in self.by_id:
            leaf = self.latest_leaf(None)
        out: list[Message] = []
        seen: set[int] = set()
        while leaf is not None and leaf in self.by_id and leaf not in seen:
            seen.add(leaf)
            m = self.by_id[leaf]
            out.append(m)
            leaf = m.parent_id
        return out[::-1]

    def path_to(self, mid: int | None) -> list[Message]:
        """从根到指定消息（含）的路径；None 表示空路径。"""
        return self.path(mid) if mid in self.by_id else []

    def siblings(self, m: Message) -> list[Message]:
        parent = m.parent_id if m.parent_id in self.by_id else None
        return self.children.get(parent, [])

    def subtree(self, mid: int) -> list[int]:
        ids, stack = [], [mid]
        while stack:
            cur = stack.pop()
            ids.append(cur)
            stack.extend(c.id for c in self.children.get(cur, []))
        return ids


def active_path(c: Conversation) -> list[Message]:
    return Tree(list(c.messages)).path(c.current_leaf_id)


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
        tree = Tree(list(c.messages))
        path = tree.path(c.current_leaf_id)
        ids = {i for m in c.messages for i in (m.attachments or [])}
        ids |= {i for m in c.messages for t in ((m.meta or {}).get("tools") or []) for i in t.get("asset_ids") or []}
        assets = {a.id: a for a in db.query(Asset).filter(Asset.id.in_(ids)).all()} if ids else {}
        out = []
        for m in path:
            item = msg_out(m, assets)
            sib = tree.siblings(m)
            item["siblings"] = [s.id for s in sib]
            group = (m.meta or {}).get("compare_group")
            if group:
                item["alternatives"] = [msg_out(s, assets) for s in sib if (s.meta or {}).get("compare_group") == group]
            out.append(item)
        data["messages"] = out
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


def _message(c: Conversation, mid: int) -> Message:
    for m in c.messages:
        if m.id == mid:
            return m
    raise HTTPException(status_code=404, detail="消息不存在")


def _remove_subtree(db: Session, c: Conversation, mid: int) -> None:
    tree = Tree(list(c.messages))
    doomed = set(tree.subtree(mid))
    target = tree.by_id[mid]
    if c.current_leaf_id in doomed or c.current_leaf_id not in tree.by_id:
        rest = Tree([m for m in c.messages if m.id not in doomed])
        parent = target.parent_id if target.parent_id in rest.by_id else None
        c.current_leaf_id = rest.latest_leaf(parent)
    db.query(Message).filter(Message.id.in_(doomed)).delete(synchronize_session=False)
    db.expire(c, ["messages"])


@router.delete("/{cid}/messages/{mid}")
def delete_message(cid: int, mid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """删除消息及其后续的整个分支。"""
    c = _get(db, cid, user)
    _message(c, mid)
    _remove_subtree(db, c, mid)
    db.commit()
    return {"ok": True}


class MessagePatch(BaseModel):
    content: str
    truncate: bool = False  # 为 True 时删除该消息之后的所有消息


@router.patch("/{cid}/messages/{mid}")
def edit_message(cid: int, mid: int, body: MessagePatch, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    m = _message(c, mid)
    m.content = body.content
    if body.truncate:
        for child in Tree(list(c.messages)).children.get(mid, []):
            _remove_subtree(db, c, child.id)
        c.current_leaf_id = mid
    db.commit()
    return {"ok": True}


class BranchIn(BaseModel):
    message_id: int


@router.post("/{cid}/branch")
def switch_branch(cid: int, body: BranchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """切换到某条消息所在的分支（自动定位到该分支最新的末端）。"""
    c = _get(db, cid, user)
    _message(c, body.message_id)
    c.current_leaf_id = Tree(list(c.messages)).latest_leaf(body.message_id)
    db.commit()
    return conv_out(c, db, with_messages=True)


@router.get("/{cid}/export", response_class=PlainTextResponse)
def export_conversation(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    lines = [f"# {c.title}", ""]
    if c.system_prompt.strip():
        lines += ["> **角色设定**", ">", *[f"> {ln}" for ln in c.system_prompt.splitlines()], ""]
    for m in active_path(c):
        who = "🧑 我" if m.role == "user" else f"🤖 {m.model or c.model or '助手'}"
        lines += [f"### {who}", "", m.content, ""]
    filename = quote(f"{c.title}.md")
    return PlainTextResponse(
        "\n".join(lines), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


class FileIn(BaseModel):
    name: str = Field(..., max_length=255)
    text: str = Field(..., max_length=FILE_LIMIT_MAX)


class ModelRef(BaseModel):
    provider_id: int
    model: str = Field(..., min_length=1)


class SendIn(BaseModel):
    content: str = ""
    attachments: list[int] = Field(default_factory=list, max_length=10)
    # 为 True 时不新增用户消息，为 parent_id（或当前分支最后一条用户消息）重新生成一个回答分支
    regenerate: bool = False
    # 新消息挂在哪条消息下面：-1 表示当前分支末端；null 表示作为新的第一条消息（编辑首条消息）
    parent_id: int | None = -1
    # 多模型对比：同时请求多个模型，回答并列展示；为空时使用对话设置的模型
    models: list[ModelRef] = Field(default_factory=list, max_length=4)
    # 文档附件：前端先调用 /api/files/extract 提取文字，随消息一起发送
    files: list[FileIn] = Field(default_factory=list, max_length=5)


RAG_PROMPT = (
    "以下是根据用户问题检索到的参考资料。回答时优先依据资料内容，并在引用处用 [编号] 标注来源；"
    "资料与问题无关时忽略它们，不要编造资料中没有的信息。\n\n"
)
MAX_TOOL_ROUNDS = 5
FILE_LIMIT = 100_000  # 单个文档随消息发送的最大字符数


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_history(db: Session, c: Conversation, path: list[Message]) -> list[dict[str, Any]]:
    params = c.params or {}
    context = int(params.get("context_count") or DEFAULT_CONTEXT)
    history: list[dict[str, Any]] = []
    if c.system_prompt.strip():
        history.append({"role": "system", "content": c.system_prompt})
    usable = [m for m in path if m.role == "user" or m.content]  # 跳过生成失败的空回答
    for m in usable[-context:]:
        text = m.content
        files = (m.meta or {}).get("files") if m.role == "user" else None
        if files:
            blocks = "\n\n".join(f'<file name="{f.get("name", "")}">\n{f.get("text", "")}\n</file>' for f in files)
            text = f"{blocks}\n\n{m.content}" if m.content else blocks
        if m.role == "user" and m.attachments:
            parts: list[dict[str, Any]] = []
            if text:
                parts.append({"type": "text", "text": text})
            for aid in m.attachments:
                a = db.get(Asset, aid)
                if a is None or a.kind != "image":
                    continue
                data, mime = downscale_for_llm(read_media(a.filename), a.mime)
                parts.append({"type": "image_url", "image_url": {"url": to_data_uri(data, mime)}})
            history.append({"role": "user", "content": parts or text})
        else:
            history.append({"role": m.role, "content": text})
    return history


def _chat_provider(db: Session, provider_id: int | None) -> Provider:
    provider = db.get(Provider, provider_id) if provider_id else None
    if provider is None or provider.kind != "openai":
        raise HTTPException(status_code=400, detail="请先为对话选择一个 OpenAI 兼容的模型服务")
    if not provider.enabled:
        raise HTTPException(status_code=400, detail=f"模型服务「{provider.name}」已停用")
    return provider


@router.post("/{cid}/messages")
async def send_message(cid: int, body: SendIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get(db, cid, user)
    targets = [(_chat_provider(db, r.provider_id), r.model) for r in body.models]
    if not targets:
        if not c.model:
            raise HTTPException(status_code=400, detail="请先为对话选择模型")
        targets = [(_chat_provider(db, c.provider_id), c.model)]
    for provider, model in targets:
        policy.check_access(db, user, "chat", provider.id, model)
    policy.check_quota(db, user, "chat", len(targets))

    tree = Tree(list(c.messages))
    if body.regenerate:
        if body.parent_id not in (-1, None):
            anchor = tree.by_id.get(body.parent_id)
        else:
            anchor = next((m for m in reversed(tree.path(c.current_leaf_id)) if m.role == "user"), None)
        if anchor is None or anchor.role != "user":
            raise HTTPException(status_code=400, detail="没有可重新生成的消息")
        parent = anchor
    else:
        if not body.content.strip() and not body.attachments and not body.files:
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        if body.attachments:
            owned = db.query(Asset.id).filter(Asset.id.in_(body.attachments), Asset.user_id == user.id).count()
            if owned != len(set(body.attachments)):
                raise HTTPException(status_code=400, detail="附件不存在")
        if body.parent_id == -1:
            parent_id = c.current_leaf_id if c.current_leaf_id in tree.by_id else tree.latest_leaf(None)
        else:
            parent_id = body.parent_id
            if parent_id is not None and parent_id not in tree.by_id:
                raise HTTPException(status_code=400, detail="父消息不存在")
        files = [{"name": f.name, "chars": len(f.text), "text": f.text[:FILE_LIMIT]} for f in body.files]
        parent = Message(conversation_id=c.id, parent_id=parent_id, role="user", content=body.content, attachments=body.attachments,
                         meta={"files": files} if files else {})
        db.add(parent)
        if c.title == "新对话":
            first = body.content.strip().splitlines()[0] if body.content.strip() else (files[0]["name"] if files else "图片对话")
            c.title = first[:30]
        db.flush()

    history = _build_history(db, c, [*tree.path_to(parent.parent_id), parent])
    group = uuid.uuid4().hex[:12] if len(targets) > 1 else ""
    replies: list[Message] = []
    for provider, model in targets:
        meta = {"provider_id": provider.id}
        if group:
            meta["compare_group"] = group
        reply = Message(conversation_id=c.id, parent_id=parent.id, role="assistant", content="", model=model, meta=meta)
        db.add(reply)
        replies.append(reply)
    db.flush()
    c.current_leaf_id = replies[0].id
    c.updated_at = utcnow()
    db.commit()

    params = dict(c.params or {})
    uid = user.id
    query = parent.content.strip() or " ".join(f["name"] for f in (parent.meta or {}).get("files") or [])
    # 知识库、联网搜索与工具（均为对话级设置）
    kb_ids = [k.id for k in db.query(KnowledgeBase).filter(
        KnowledgeBase.id.in_([int(x) for x in params.get("kb_ids") or []]), KnowledgeBase.user_id == uid).all()]
    use_web = bool(params.get("web_search")) and websearch.configured(db)
    tool_specs, tool_route = await tools_svc.build_specs(db, [str(t) for t in params.get("tools") or []])
    prompt_chars = "".join(
        h["content"] if isinstance(h["content"], str) else "".join(p.get("text", "") for p in h["content"])
        for h in history
    )
    # 每个目标模型的候选服务（故障切换），在请求的数据库会话关闭前确定
    jobs = [
        (i, failover.candidates(db, provider, model, "chat"), model, reply.id)
        for i, ((provider, model), reply) in enumerate(zip(targets, replies))
    ]
    head = {
        "start": True,
        "user_message_id": parent.id,
        "compare_group": group,
        "replies": [{"i": i, "id": mid, "model": model, "provider_id": cands[0].id} for i, cands, model, mid in jobs],
    }

    def save_reply(mid: int, content: str, reasoning: str, error: str = "", served: Provider | None = None,
                   usage: dict[str, Any] | None = None, sources: list | None = None, tool_log: list | None = None) -> None:
        with new_session() as s:
            msg = s.get(Message, mid)
            if msg is None:
                return
            msg.content = content
            msg.reasoning = reasoning
            meta = dict(msg.meta or {})
            if error:
                meta["error"] = error
            if served is not None and served.id != meta.get("provider_id"):
                meta["served_by"] = served.name  # 发生了故障切换
            if sources:
                meta["sources"] = sources
            if tool_log:
                meta["tools"] = tool_log
            msg.meta = meta
            if served is not None and (content or reasoning):
                if usage and (usage.get("prompt_tokens") or usage.get("completion_tokens")):
                    policy.record_usage(s, uid, "chat", served.id, msg.model, 1,
                                        int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))
                else:
                    policy.record_usage(s, uid, "chat", served.id, msg.model, 1, policy.estimate_tokens(prompt_chars),
                                        policy.estimate_tokens(content + reasoning), estimated=True)
            conv = s.get(Conversation, cid)
            if conv:
                conv.updated_at = utcnow()
            s.commit()

    async def gather_context() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """检索知识库与联网搜索，返回（注入上下文后的消息，来源列表，提示信息）。"""
        sources: list[dict[str, Any]] = []
        blocks: list[str] = []
        notices: list[str] = []
        if kb_ids and query:
            try:
                with new_session() as s:
                    results = await knowledge.search(s, kb_ids, query)
                if results:
                    blocks.append(knowledge.format_context(results, len(sources) + 1))
                    sources += [{"type": "kb", "title": r["filename"], "kb": r["kb_name"], "snippet": r["text"][:300]} for r in results]
            except Exception as exc:  # noqa: BLE001
                notices.append(f"知识库检索失败：{exc}")
        if use_web and query:
            try:
                with new_session() as s:
                    results = await websearch.search(s, query)
                if results:
                    blocks.append(websearch.format_context(results, len(sources) + 1))
                    sources += [{"type": "web", "title": r["title"], "url": r["url"], "snippet": r["snippet"][:300]} for r in results]
            except Exception as exc:  # noqa: BLE001
                notices.append(f"联网搜索失败：{exc}")
        msgs = list(history)
        if blocks:
            msgs.insert(len(msgs) - 1, {"role": "system", "content": RAG_PROMPT + "\n\n".join(blocks)})
        return msgs, sources, notices

    async def stream():
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def worker(i: int, cands: list[Provider], model: str, mid: int, base_msgs: list, sources: list) -> None:
            content: list[str] = []
            reasoning: list[str] = []
            usage: dict[str, int] = {}
            tool_log: list[dict[str, Any]] = []
            all_sources = list(sources)
            served: Provider | None = None
            finished = False
            msgs = list(base_msgs)
            idx = 0  # 当前使用的候选服务
            try:
                for round_no in range(MAX_TOOL_ROUNDS + 1):
                    calls: list[dict[str, Any]] = []
                    round_text: list[str] = []
                    extra = {"tools": tool_specs} if tool_specs and round_no < MAX_TOOL_ROUNDS else {}
                    if content and round_no:
                        content.append("\n\n")
                    while True:
                        served = cands[idx]
                        produced = False
                        try:
                            async for kind, delta in openai_compat.chat_stream(served, model, msgs, params, **extra):
                                if kind == "usage":
                                    for k in ("prompt_tokens", "completion_tokens"):
                                        usage[k] = usage.get(k, 0) + int(delta.get(k) or 0)
                                    continue
                                if kind == "tool_calls":
                                    calls = delta
                                    continue
                                produced = True
                                if kind == "content":
                                    content.append(delta)
                                    round_text.append(delta)
                                    await queue.put({"i": i, "delta": delta})
                                else:
                                    reasoning.append(delta)
                                    await queue.put({"i": i, "reasoning": delta})
                            break
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:  # noqa: BLE001
                            # 还没输出任何内容且是可重试的错误时，切换到下一个提供同名模型的服务
                            if not produced and round_no == 0 and idx + 1 < len(cands) and failover.retryable(exc):
                                idx += 1
                                await queue.put({"i": i, "failover": cands[idx].name, "reason": str(exc)[:200]})
                                continue
                            raise
                    if not calls:
                        break
                    msgs.append({"role": "assistant", "content": "".join(round_text) or None, "tool_calls": calls})
                    for call in calls:
                        name = call["function"]["name"]
                        args = call["function"].get("arguments") or "{}"
                        label = tools_svc.label_of(name, tool_route)
                        await queue.put({"i": i, "tool": {"id": call.get("id"), "name": name, "label": label, "args": args[:500]}})
                        res = await tools_svc.execute(name, args, tool_route, uid, kb_ids)
                        entry = {"name": name, "label": label, "args": args[:2000], "result": res["text"][:4000], "asset_ids": res.get("asset_ids") or []}
                        tool_log.append(entry)
                        all_sources += res.get("sources") or []
                        msgs.append({"role": "tool", "tool_call_id": call.get("id") or name, "content": res["text"]})
                        assets_out = []
                        if entry["asset_ids"]:
                            with new_session() as s:
                                assets_out = [asset_out(a) for a in s.query(Asset).filter(Asset.id.in_(entry["asset_ids"])).all()]
                        await queue.put({"i": i, "tool_done": {"id": call.get("id"), "name": name, "label": label,
                                                               "result": entry["result"][:500], "assets": assets_out,
                                                               "sources": res.get("sources") or []}})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                finished = True
                err = str(exc) or exc.__class__.__name__
                save_reply(mid, "".join(content), "".join(reasoning), err, served, usage, all_sources, tool_log)
                await queue.put({"i": i, "error": err, "message_id": mid})
            else:
                finished = True
                save_reply(mid, "".join(content), "".join(reasoning), "", served, usage, all_sources, tool_log)
                await queue.put({"i": i, "done": True, "message_id": mid})
            finally:
                # 客户端中途断开（点击“停止”）时也保留已生成的部分内容
                if not finished:
                    save_reply(mid, "".join(content), "".join(reasoning), "", served, usage, all_sources, tool_log)

        workers: list[asyncio.Task] = []
        try:
            yield _sse(head)
            if (kb_ids or use_web) and query:
                yield _sse({"status": "searching", "kb": bool(kb_ids), "web": use_web})
            msgs, sources, notices = await gather_context()
            if sources or notices:
                yield _sse({"sources": sources, "notices": notices})
            workers = [asyncio.create_task(worker(*job, msgs, sources)) for job in jobs]
            remaining = len(workers)
            while remaining:
                event = await queue.get()
                if event.get("done") or "error" in event:
                    remaining -= 1
                yield _sse(event)
        finally:
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{cid}/title")
async def auto_title(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """让模型根据对话内容生成简短标题。"""
    c = _get(db, cid, user)
    provider = db.get(Provider, c.provider_id) if c.provider_id else None
    if provider is None or not c.model or not c.messages:
        raise HTTPException(status_code=400, detail="对话为空或未选择模型")
    policy.check_access(db, user, "chat", provider.id, c.model)
    snippet = "\n".join(f"{m.role}: {m.content[:300]}" for m in active_path(c)[:4])
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
