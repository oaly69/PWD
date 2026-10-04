"""OpenAI 兼容接口客户端：模型列表、流式对话、图像生成。"""
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..models import Provider

TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=15.0)


class ProviderError(RuntimeError):
    pass


def _base(provider: Provider) -> str:
    return provider.base_url.rstrip("/")


def _headers(provider: Provider) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    extra_headers = (provider.extra or {}).get("headers") or {}
    if isinstance(extra_headers, dict):
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    return headers


def _error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            return str(err.get("message") or err)
        return str(err)
    except ValueError:
        return resp.text[:500]


async def list_models(provider: Provider) -> list[str]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{_base(provider)}/models", headers=_headers(provider))
    if resp.status_code >= 400:
        raise ProviderError(f"获取模型列表失败（HTTP {resp.status_code}）：{_error_text(resp)}")
    data = resp.json()
    items = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
    names: list[str] = []
    for item in items or []:
        if isinstance(item, dict):
            name = item.get("id") or item.get("name") or item.get("model")
        else:
            name = str(item)
        if name:
            names.append(str(name))
    return sorted(set(names))


async def chat_stream(
    provider: Provider,
    model: str,
    messages: list[dict[str, str]],
    params: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """逐段产出模型回复文本。"""
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    for key in ("temperature", "top_p", "max_tokens"):
        if params and params.get(key) is not None:
            body[key] = params[key]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST", f"{_base(provider)}/chat/completions", headers=_headers(provider), json=body
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                raise ProviderError(f"对话请求失败（HTTP {resp.status_code}）：{_error_text(resp)}")
            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                # 部分服务忽略 stream 参数，直接返回完整 JSON
                await resp.aread()
                data = resp.json()
                text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                if text:
                    yield text
                return
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise ProviderError(str(chunk["error"]))
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield text


async def generate_images(
    provider: Provider, model: str, prompt: str, params: dict[str, Any]
) -> list[tuple[bytes, str]]:
    """调用 /images/generations，返回 [(图片字节, mime)]。"""
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if params.get("size"):
        body["size"] = params["size"]
    if params.get("n"):
        body["n"] = int(params["n"])
    if params.get("negative_prompt"):
        body["negative_prompt"] = params["negative_prompt"]
    if params.get("seed") not in (None, ""):
        body["seed"] = int(params["seed"])
    extra_body = params.get("extra_body")
    if isinstance(extra_body, dict):
        body.update(extra_body)

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        resp = await client.post(f"{_base(provider)}/images/generations", headers=_headers(provider), json=body)
        if resp.status_code >= 400:
            raise ProviderError(f"图像生成失败（HTTP {resp.status_code}）：{_error_text(resp)}")
        data = resp.json()
        items = data.get("data") or data.get("images") or []
        results: list[tuple[bytes, str]] = []
        for item in items:
            if isinstance(item, str):
                item = {"url": item}
            if item.get("b64_json"):
                results.append((base64.b64decode(item["b64_json"]), "image/png"))
            elif item.get("url"):
                url = item["url"]
                if url.startswith("data:"):
                    header, _, b64 = url.partition(",")
                    mime = header[5:].split(";")[0] or "image/png"
                    results.append((base64.b64decode(b64), mime))
                else:
                    img = await client.get(url)
                    if img.status_code >= 400:
                        raise ProviderError(f"下载生成结果失败（HTTP {img.status_code}）")
                    mime = img.headers.get("content-type", "image/png").split(";")[0]
                    results.append((img.content, mime))
    if not results:
        raise ProviderError("服务未返回任何图片")
    return results
