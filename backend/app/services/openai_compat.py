"""OpenAI 兼容接口客户端：模型列表、流式对话、图像生成 / 编辑、语音合成、视频生成。"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

from ..models import Provider

TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=15.0)

ProgressCallback = Callable[[int, str], Awaitable[None]]


class ProviderError(RuntimeError):
    pass


def _base(provider: Provider) -> str:
    return provider.base_url.rstrip("/")


def _headers(provider: Provider, json_body: bool = True) -> dict[str, str]:
    headers = {"Content-Type": "application/json"} if json_body else {}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    extra_headers = (provider.extra or {}).get("headers") or {}
    if isinstance(extra_headers, dict):
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    return headers


def _error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error", data) if isinstance(data, dict) else data
        if isinstance(err, dict):
            return str(err.get("message") or err.get("msg") or err)
        return str(err)
    except ValueError:
        return resp.text[:500]


def _raise(resp: httpx.Response, action: str) -> None:
    if resp.status_code >= 400:
        raise ProviderError(f"{action}失败（HTTP {resp.status_code}）：{_error_text(resp)}")


# ---------------------------------------------------------------- 模型列表


async def list_models(provider: Provider) -> list[str]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{_base(provider)}/models", headers=_headers(provider))
    _raise(resp, "获取模型列表")
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


# ---------------------------------------------------------------- 对话


async def chat_stream(
    provider: Provider,
    model: str,
    messages: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, str]]:
    """逐段产出 (类型, 文本)，类型为 content（回复）或 reasoning（思考过程）。"""
    body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    for key in ("temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty"):
        if params and params.get(key) is not None:
            body[key] = params[key]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream(
            "POST", f"{_base(provider)}/chat/completions", headers=_headers(provider), json=body
        ) as resp:
            if resp.status_code >= 400:
                await resp.aread()
                _raise(resp, "对话请求")
            if "text/event-stream" not in resp.headers.get("content-type", ""):
                # 部分服务忽略 stream 参数，直接返回完整 JSON
                await resp.aread()
                msg = (resp.json().get("choices") or [{}])[0].get("message", {})
                if msg.get("reasoning_content"):
                    yield "reasoning", msg["reasoning_content"]
                if msg.get("content"):
                    yield "content", msg["content"]
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
                    err = chunk["error"]
                    raise ProviderError(err.get("message") if isinstance(err, dict) else str(err))
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if reasoning:
                        yield "reasoning", reasoning
                    if delta.get("content"):
                        yield "content", delta["content"]


async def chat_complete(provider: Provider, model: str, messages: list[dict[str, Any]], **params: Any) -> str:
    parts: list[str] = []
    async for kind, text in chat_stream(provider, model, messages, params):
        if kind == "content":
            parts.append(text)
    return "".join(parts).strip()


# ---------------------------------------------------------------- 图像


async def _collect_images(client: httpx.AsyncClient, data: dict[str, Any]) -> list[tuple[bytes, str]]:
    items = data.get("data") or data.get("images") or []
    results: list[tuple[bytes, str]] = []
    for item in items:
        if isinstance(item, str):
            item = {"url": item}
        if item.get("b64_json"):
            results.append((base64.b64decode(item["b64_json"]), "image/png"))
        elif item.get("url"):
            results.append(await _download(client, item["url"]))
    if not results:
        raise ProviderError("服务未返回任何图片")
    return results


async def _download(client: httpx.AsyncClient, url: str) -> tuple[bytes, str]:
    if url.startswith("data:"):
        header, _, b64 = url.partition(",")
        return base64.b64decode(b64), header[5:].split(";")[0] or "image/png"
    resp = await client.get(url, timeout=httpx.Timeout(300.0))
    if resp.status_code >= 400:
        raise ProviderError(f"下载生成结果失败（HTTP {resp.status_code}）")
    return resp.content, resp.headers.get("content-type", "application/octet-stream").split(";")[0]


def _image_body(model: str, prompt: str, params: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if params.get("size"):
        body["size"] = params["size"]
    if params.get("n"):
        body["n"] = int(params["n"])
    if params.get("negative_prompt"):
        body["negative_prompt"] = params["negative_prompt"]
    if params.get("seed") not in (None, ""):
        body["seed"] = int(params["seed"])
    return body


async def generate_images(
    provider: Provider,
    model: str,
    prompt: str,
    params: dict[str, Any],
    references: list[tuple[bytes, str]] | None = None,
) -> list[tuple[bytes, str]]:
    """文生图 / 图生图，返回 [(图片字节, mime)]。

    有参考图时根据服务配置 extra.image_edit_mode 选择：
      - edits：调用 /images/edits（multipart，OpenAI gpt-image-1 等）
      - field：在 /images/generations 请求体中附带 image 字段（硅基流动 Kolors / Qwen-Image-Edit 等）
    """
    body = _image_body(model, prompt, params)
    extra_body = params.get("extra_body")
    mode = (provider.extra or {}).get("image_edit_mode") or "edits"

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        if references and mode == "edits":
            form = {k: str(v) for k, v in body.items()}
            if isinstance(extra_body, dict):
                form.update({k: v if isinstance(v, str) else json.dumps(v) for k, v in extra_body.items()})
            field = "image[]" if len(references) > 1 else "image"
            files = [(field, (f"ref{i}.png", data, mime)) for i, (data, mime) in enumerate(references)]
            resp = await client.post(
                f"{_base(provider)}/images/edits", headers=_headers(provider, json_body=False), data=form, files=files
            )
            _raise(resp, "图像编辑")
        else:
            if references:
                from .media import to_data_uri

                body["image"] = to_data_uri(*references[0])
            if isinstance(extra_body, dict):
                body.update(extra_body)
            resp = await client.post(f"{_base(provider)}/images/generations", headers=_headers(provider), json=body)
            _raise(resp, "图像生成")
        return await _collect_images(client, resp.json())


# ---------------------------------------------------------------- 语音合成


async def speech(provider: Provider, model: str, text: str, params: dict[str, Any]) -> tuple[bytes, str]:
    fmt = params.get("format") or "mp3"
    body: dict[str, Any] = {"model": model, "input": text, "response_format": fmt}
    if params.get("voice"):
        body["voice"] = params["voice"]
    if params.get("speed"):
        body["speed"] = float(params["speed"])
    if params.get("instructions"):
        body["instructions"] = params["instructions"]
    if isinstance(params.get("extra_body"), dict):
        body.update(params["extra_body"])
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{_base(provider)}/audio/speech", headers=_headers(provider), json=body)
    _raise(resp, "语音合成")
    mime = resp.headers.get("content-type", "").split(";")[0]
    if not mime.startswith("audio/"):
        mime = {"mp3": "audio/mpeg", "wav": "audio/wav", "opus": "audio/ogg", "aac": "audio/aac", "flac": "audio/flac"}.get(fmt, "audio/mpeg")
    return resp.content, mime


# ---------------------------------------------------------------- 视频生成


async def generate_video(
    provider: Provider,
    model: str,
    prompt: str,
    params: dict[str, Any],
    reference: tuple[bytes, str] | None,
    on_progress: ProgressCallback,
    timeout: float = 3600,
) -> list[tuple[bytes, str]]:
    """异步视频生成。extra.video_api 选择接口风格：

      - openai：OpenAI Sora 风格 POST /videos → GET /videos/{id} → GET /videos/{id}/content
      - siliconflow：POST /video/submit → POST /video/status
    """
    api = (provider.extra or {}).get("video_api") or "openai"
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        if api == "siliconflow":
            return await _video_siliconflow(client, provider, model, prompt, params, reference, on_progress, deadline)
        return await _video_openai(client, provider, model, prompt, params, reference, on_progress, deadline)


async def _video_openai(client, provider, model, prompt, params, reference, on_progress, deadline):
    form: dict[str, str] = {"model": model, "prompt": prompt}
    if params.get("size"):
        form["size"] = str(params["size"])
    if params.get("seconds"):
        form["seconds"] = str(params["seconds"])
    if isinstance(params.get("extra_body"), dict):
        form.update({k: str(v) for k, v in params["extra_body"].items()})
    files = [("input_reference", ("reference.png", reference[0], reference[1]))] if reference else None
    resp = await client.post(
        f"{_base(provider)}/videos", headers=_headers(provider, json_body=False), data=form, files=files
    )
    _raise(resp, "提交视频任务")
    job = resp.json()
    job_id = job.get("id")
    if not job_id:
        raise ProviderError(f"服务未返回任务 ID：{str(job)[:300]}")
    await on_progress(int(job.get("progress") or 0), job_id)
    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        r = await client.get(f"{_base(provider)}/videos/{job_id}", headers=_headers(provider))
        _raise(r, "查询视频任务")
        job = r.json()
        status = job.get("status")
        await on_progress(int(job.get("progress") or 0), job_id)
        if status == "completed":
            c = await client.get(f"{_base(provider)}/videos/{job_id}/content", headers=_headers(provider))
            _raise(c, "下载视频")
            return [(c.content, c.headers.get("content-type", "video/mp4").split(";")[0] or "video/mp4")]
        if status in ("failed", "cancelled", "expired"):
            err = job.get("error") or {}
            raise ProviderError(f"视频生成失败：{err.get('message') if isinstance(err, dict) else err or status}")
    raise ProviderError("等待视频生成超时")


async def _video_siliconflow(client, provider, model, prompt, params, reference, on_progress, deadline):
    body: dict[str, Any] = {"model": model, "prompt": prompt}
    if params.get("size"):
        body["image_size"] = params["size"]
    if params.get("negative_prompt"):
        body["negative_prompt"] = params["negative_prompt"]
    if params.get("seed") not in (None, ""):
        body["seed"] = int(params["seed"])
    if reference:
        from .media import to_data_uri

        body["image"] = to_data_uri(*reference)
    if isinstance(params.get("extra_body"), dict):
        body.update(params["extra_body"])
    resp = await client.post(f"{_base(provider)}/video/submit", headers=_headers(provider), json=body)
    _raise(resp, "提交视频任务")
    request_id = resp.json().get("requestId") or resp.json().get("request_id")
    if not request_id:
        raise ProviderError(f"服务未返回任务 ID：{resp.text[:300]}")
    await on_progress(0, request_id)
    started = time.monotonic()
    while time.monotonic() < deadline:
        await asyncio.sleep(5)
        r = await client.post(f"{_base(provider)}/video/status", headers=_headers(provider), json={"requestId": request_id})
        _raise(r, "查询视频任务")
        data = r.json()
        status = data.get("status")
        if status == "Succeed":
            videos = (data.get("results") or {}).get("videos") or []
            if not videos:
                raise ProviderError("服务未返回视频")
            return [await _download(client, v["url"]) for v in videos]
        if status == "Failed":
            raise ProviderError(f"视频生成失败：{data.get('reason') or '未知原因'}")
        # 该接口不返回进度，按耗时估算一个平滑进度
        await on_progress(min(95, int((time.monotonic() - started) / 3)), request_id)
    raise ProviderError("等待视频生成超时")
