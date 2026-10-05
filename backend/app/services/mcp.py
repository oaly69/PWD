"""MCP（Model Context Protocol）客户端：Streamable HTTP 传输，支持 tools/list 与 tools/call。

每次调用建立一个短会话（initialize → 请求），实现简单、无需维护长连接。
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import VERSION
from .openai_compat import ProviderError

PROTOCOL = "2025-06-18"
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_tools_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _parse(resp: httpx.Response, req_id: int) -> dict[str, Any]:
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("id") == req_id:
                    return msg
        raise ProviderError("MCP 服务未返回结果")
    return resp.json()


class Session:
    def __init__(self, server: dict[str, Any]):
        self.url = server["url"]
        self.headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        self.headers.update({str(k): str(v) for k, v in (server.get("headers") or {}).items()})
        self.client = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True)
        self.next_id = 0

    async def __aenter__(self) -> "Session":
        await self.request("initialize", {
            "protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "PWD", "version": VERSION},
        })
        await self.notify("notifications/initialized")
        return self

    async def __aexit__(self, *exc) -> None:
        sid = self.headers.get("Mcp-Session-Id")
        if sid:
            try:
                await self.client.delete(self.url, headers=self.headers)
            except httpx.HTTPError:
                pass
        await self.client.aclose()

    async def notify(self, method: str) -> None:
        await self.client.post(self.url, headers=self.headers, json={"jsonrpc": "2.0", "method": method})

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.next_id += 1
        body = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        resp = await self.client.post(self.url, headers=self.headers, json=body)
        if resp.status_code >= 400:
            raise ProviderError(f"MCP 请求 {method} 失败（HTTP {resp.status_code}）：{resp.text[:200]}", resp.status_code)
        if resp.headers.get("mcp-session-id"):
            self.headers["Mcp-Session-Id"] = resp.headers["mcp-session-id"]
        msg = _parse(resp, self.next_id)
        if msg.get("error"):
            err = msg["error"]
            raise ProviderError(f"MCP 错误：{err.get('message') if isinstance(err, dict) else err}")
        return msg.get("result")


async def list_tools(server: dict[str, Any], use_cache: bool = True) -> list[dict[str, Any]]:
    key = f"{server.get('id')}|{server.get('url')}"
    hit = _tools_cache.get(key)
    if use_cache and hit and time.time() - hit[0] < 300:
        return hit[1]
    async with Session(server) as s:
        result = await s.request("tools/list")
    tools = [t for t in (result or {}).get("tools", []) if t.get("name")]
    _tools_cache[key] = (time.time(), tools)
    return tools


async def call_tool(server: dict[str, Any], name: str, arguments: dict[str, Any]) -> str:
    async with Session(server) as s:
        result = await s.request("tools/call", {"name": name, "arguments": arguments})
    parts = []
    for item in (result or {}).get("content", []):
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
        elif item.get("type") == "resource":
            res = item.get("resource") or {}
            parts.append(res.get("text") or res.get("uri", ""))
        else:
            parts.append(f"[{item.get('type')}]")
    if (result or {}).get("structuredContent") and not parts:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    text = "\n".join(p for p in parts if p)
    if (result or {}).get("isError"):
        return f"工具执行出错：{text}"
    return text or "（工具没有返回内容）"
