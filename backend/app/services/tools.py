"""对话中可供模型调用的工具：内置工具（生图、联网搜索、知识库检索）与管理员配置的 MCP 服务工具。"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..db import new_session
from ..models import Asset, Provider, Task, User
from ..site import get_setting
from . import knowledge, mcp, policy, websearch
from .openai_compat import ProviderError

BUILTIN: dict[str, dict[str, Any]] = {
    "generate_image": {
        "label": "生成图片",
        "description": "根据文字描述生成图片。当用户要求画图、生成图片、配图、设计海报时调用。返回生成结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "详细的画面描述，包含主体、场景、风格、光线、构图等"},
                "size": {"type": "string", "description": "图片尺寸，例如 1024x1024、1536x1024（横图）、1024x1536（竖图）"},
            },
            "required": ["prompt"],
        },
    },
    "web_search": {
        "label": "联网搜索",
        "description": "搜索互联网获取最新信息。当问题涉及新闻、实时数据、最新版本或你不确定的事实时调用。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "搜索关键词"}},
            "required": ["query"],
        },
    },
    "knowledge_search": {
        "label": "检索知识库",
        "description": "在用户为当前对话选择的知识库中检索相关资料。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "检索内容"}},
            "required": ["query"],
        },
    },
}


def mcp_servers(db: Session) -> list[dict[str, Any]]:
    return [s for s in (get_setting(db, "mcp_servers") or []) if isinstance(s, dict) and s.get("enabled", True) and s.get("url")]


def _fn_name(server_id: str, tool: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"mcp_{server_id}_{tool}")[:64]


async def catalog(db: Session) -> list[dict[str, Any]]:
    """可用工具列表（供前端选择）。MCP 服务不可达时跳过并返回错误信息。"""
    items: list[dict[str, Any]] = [
        {"id": k, "label": v["label"], "description": v["description"], "source": "builtin"}
        for k, v in BUILTIN.items()
        if k != "web_search" or websearch.configured(db)
    ]
    for server in mcp_servers(db):
        try:
            tools = await asyncio.wait_for(mcp.list_tools(server), timeout=15)
        except Exception as exc:  # noqa: BLE001
            items.append({"id": f"mcp:{server['id']}", "label": server.get("name") or server["id"], "source": "mcp",
                          "server": server.get("name"), "error": str(exc)[:200]})
            continue
        for t in tools:
            items.append({
                "id": f"mcp:{server['id']}:{t['name']}", "label": t.get("title") or t["name"],
                "description": (t.get("description") or "")[:300], "source": "mcp", "server": server.get("name") or server["id"],
            })
    return items


async def build_specs(db: Session, selected: list[str]) -> tuple[list[dict[str, Any]], dict[str, tuple[str, Any]]]:
    """把选择的工具转换为 OpenAI tools 参数，返回（specs，函数名 → 执行目标）。"""
    specs: list[dict[str, Any]] = []
    route: dict[str, tuple[str, Any]] = {}
    for tid in selected:
        if tid in BUILTIN:
            if tid == "web_search" and not websearch.configured(db):
                continue
            b = BUILTIN[tid]
            specs.append({"type": "function", "function": {"name": tid, "description": b["description"], "parameters": b["parameters"]}})
            route[tid] = ("builtin", tid)
    wanted = {t.split(":", 2)[1] for t in selected if t.startswith("mcp:")}
    for server in mcp_servers(db):
        if server["id"] not in wanted:
            continue
        try:
            tools = await asyncio.wait_for(mcp.list_tools(server), timeout=15)
        except Exception:  # noqa: BLE001 - 不可达的服务跳过
            continue
        for t in tools:
            tid = f"mcp:{server['id']}:{t['name']}"
            if tid not in selected and f"mcp:{server['id']}" not in selected:
                continue
            name = _fn_name(server["id"], t["name"])
            schema = t.get("inputSchema") or {"type": "object", "properties": {}}
            specs.append({"type": "function", "function": {"name": name, "description": (t.get("description") or t["name"])[:1000], "parameters": schema}})
            route[name] = ("mcp", (server, t["name"]))
    return specs, route


def label_of(name: str, route: dict[str, tuple[str, Any]]) -> str:
    """工具的展示名称：内置工具用中文名，MCP 工具用「服务名 · 工具名」。"""
    if name in BUILTIN:
        return BUILTIN[name]["label"]
    target = route.get(name)
    if target and target[0] == "mcp":
        server, tool = target[1]
        return f"{server.get('name') or server['id']} · {tool}"
    return name


async def _generate_image(user_id: int, args: dict[str, Any]) -> dict[str, Any]:
    from . import tasks as task_runner

    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"text": "缺少 prompt 参数"}
    with new_session() as db:
        user = db.get(User, user_id)
        pid, model = get_setting(db, "default_image_provider_id"), get_setting(db, "default_image_model")
        provider = db.get(Provider, pid) if pid else None
        if user is None or provider is None or not model or not provider.enabled:
            return {"text": "管理员尚未配置默认图像模型，无法生成图片"}
        try:
            policy.check_access(db, user, "image", provider.id, model)
            policy.check_quota(db, user, "image", 1)
        except Exception as exc:  # noqa: BLE001
            return {"text": f"无法生成图片：{getattr(exc, 'detail', exc)}"}
        params: dict[str, Any] = {"n": 1, "negative_prompt": ""}
        size = str(args.get("size") or "")
        if re.fullmatch(r"\d{3,4}x\d{3,4}", size):
            params["size"] = size
        task = Task(user_id=user_id, kind="image", status="pending", provider_id=provider.id, model=model, prompt=prompt, params=params)
        db.add(task)
        db.commit()
        tid = task.id
    task_runner.submit(tid)
    for _ in range(600):  # 最长等待 10 分钟
        await asyncio.sleep(1)
        with new_session() as db:
            t = db.get(Task, tid)
            if t.status in ("pending", "running"):
                continue
            if t.status != "succeeded":
                return {"text": f"图片生成失败：{t.error}"}
            assets = db.query(Asset).filter(Asset.task_id == tid).all()
            return {"text": f"已生成 {len(assets)} 张图片并展示给用户（提示词：{prompt}）。", "asset_ids": [a.id for a in assets]}
    return {"text": "图片生成超时，可在任务中心查看结果"}


async def execute(name: str, raw_args: str, route: dict[str, tuple[str, Any]], user_id: int, kb_ids: list[int]) -> dict[str, Any]:
    """执行一次工具调用，返回 {"text": 给模型的结果, "asset_ids"?: [...], "sources"?: [...]}"""
    try:
        args = json.loads(raw_args or "{}") if isinstance(raw_args, str) else dict(raw_args or {})
    except ValueError:
        return {"text": "工具参数不是合法的 JSON"}
    target = route.get(name)
    if target is None:
        return {"text": f"未知工具：{name}"}
    kind, ref = target
    try:
        if kind == "mcp":
            server, tool = ref
            text = await asyncio.wait_for(mcp.call_tool(server, tool, args), timeout=120)
            return {"text": text[:20000]}
        if ref == "generate_image":
            return await _generate_image(user_id, args)
        if ref == "web_search":
            with new_session() as db:
                results = await websearch.search(db, str(args.get("query") or ""))
            sources = [{"type": "web", "title": r["title"], "url": r["url"], "snippet": r["snippet"][:300]} for r in results]
            return {"text": websearch.format_context(results) or "没有搜索到结果", "sources": sources}
        if ref == "knowledge_search":
            if not kb_ids:
                return {"text": "当前对话没有选择知识库"}
            with new_session() as db:
                results = await knowledge.search(db, kb_ids, str(args.get("query") or ""))
            sources = [{"type": "kb", "title": r["filename"], "kb": r["kb_name"], "snippet": r["text"][:300]} for r in results]
            return {"text": knowledge.format_context(results) or "知识库中没有找到相关内容", "sources": sources}
    except ProviderError as exc:
        return {"text": f"工具执行失败：{exc}"}
    except asyncio.TimeoutError:
        return {"text": "工具执行超时"}
    return {"text": f"未知工具：{name}"}
