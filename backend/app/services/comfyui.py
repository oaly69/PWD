"""ComfyUI 客户端：提交 API 格式工作流，轮询结果并下载输出图片。

工作流存放在 provider.extra["workflows"] 中，形如 {"工作流名称": {...API JSON...}}，
工作流名称即为模型名称（可同时用于图像与视频，取决于工作流的输出节点）。可用占位符：
  {{prompt}} {{negative_prompt}} {{seed}} {{width}} {{height}} {{steps}} {{batch_size}}
  {{image}}  参考图（自动上传到 ComfyUI 的 input 目录后替换为文件名，配合 LoadImage 节点）
当某个字符串值恰好等于数字类占位符时，会被替换为数字。
输出支持 SaveImage（images）以及 VideoHelperSuite 等节点的 gifs / videos 输出。
"""
from __future__ import annotations

import asyncio
import copy
import json
import mimetypes
import random
import time
import uuid
from typing import Any

import httpx

from ..models import Provider
from .openai_compat import ProviderError

NUMERIC_KEYS = {"seed", "width", "height", "steps", "batch_size"}

EXAMPLE_WORKFLOW: dict[str, Any] = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": "{{seed}}", "steps": "{{steps}}", "cfg": 7, "sampler_name": "euler",
            "scheduler": "normal", "denoise": 1,
            "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0],
        },
    },
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": "{{batch_size}}"},
    },
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{prompt}}", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}", "clip": ["4", 1]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "PWD", "images": ["8", 0]}},
}


def fill_workflow(workflow: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            for key in NUMERIC_KEYS:
                if node == f"{{{{{key}}}}}":
                    return values[key]
            for key, val in values.items():
                node = node.replace(f"{{{{{key}}}}}", str(val))
            return node
        return node

    return walk(copy.deepcopy(workflow))


def _base(provider: Provider) -> str:
    return provider.base_url.rstrip("/")


def _headers(provider: Provider) -> dict[str, str]:
    return {"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {}


def build_values(prompt: str, params: dict[str, Any]) -> dict[str, Any]:
    width, height = 1024, 1024
    size = str(params.get("size") or "")
    if "x" in size:
        try:
            width, height = (int(v) for v in size.lower().split("x", 1))
        except ValueError:
            pass
    seed = params.get("seed")
    return {
        "prompt": prompt,
        "negative_prompt": params.get("negative_prompt") or "",
        "seed": int(seed) if seed not in (None, "") else random.randint(0, 2**31 - 1),
        "width": width,
        "height": height,
        "steps": int(params.get("steps") or 25),
        "batch_size": int(params.get("n") or 1),
    }


async def generate(
    provider: Provider,
    model: str,
    prompt: str,
    params: dict[str, Any],
    references: list[tuple[bytes, str]] | None = None,
    on_progress=None,
    timeout: float = 3600,
) -> list[tuple[bytes, str]]:
    workflows = (provider.extra or {}).get("workflows") or {}
    workflow = workflows.get(model)
    if not isinstance(workflow, dict) or not workflow:
        raise ProviderError(f"未找到名为「{model}」的 ComfyUI 工作流，请在模型服务中配置")
    values = build_values(prompt, params)

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        values["image"] = ""
        if references:
            data, mime = references[0]
            up = await client.post(
                f"{_base(provider)}/upload/image",
                files={"image": (f"pwd_{uuid.uuid4().hex[:8]}.png", data, mime)},
                data={"overwrite": "true"},
                headers=_headers(provider),
            )
            if up.status_code >= 400:
                raise ProviderError(f"上传参考图到 ComfyUI 失败（HTTP {up.status_code}）")
            info = up.json()
            values["image"] = f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]
        elif _uses_placeholder(workflow, "image"):
            raise ProviderError("该工作流需要参考图（包含 {{image}} 占位符），请先选择参考图")
        graph = fill_workflow(workflow, values)
        resp = await client.post(
            f"{_base(provider)}/prompt",
            json={"prompt": graph, "client_id": uuid.uuid4().hex},
            headers=_headers(provider),
        )
        if resp.status_code >= 400:
            raise ProviderError(f"提交 ComfyUI 工作流失败（HTTP {resp.status_code}）：{resp.text[:500]}")
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise ProviderError(f"ComfyUI 未返回 prompt_id：{resp.text[:300]}")

        if on_progress:
            await on_progress(0, prompt_id)
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        history: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            await asyncio.sleep(2)
            if on_progress:
                await on_progress(min(95, int((time.monotonic() - started) / 2)), prompt_id)
            r = await client.get(f"{_base(provider)}/history/{prompt_id}", headers=_headers(provider))
            if r.status_code == 200:
                data = r.json()
                if prompt_id in data:
                    history = data[prompt_id]
                    status = history.get("status") or {}
                    if status.get("status_str") == "error":
                        raise ProviderError(f"ComfyUI 执行失败：{status.get('messages')}")
                    if status.get("completed", True):
                        break
        if history is None:
            raise ProviderError("等待 ComfyUI 结果超时")

        results: list[tuple[bytes, str]] = []
        for output in (history.get("outputs") or {}).values():
            files = (output.get("images") or []) + (output.get("gifs") or []) + (output.get("videos") or []) + (output.get("audio") or [])
            for img in files:
                if not isinstance(img, dict) or img.get("type") == "temp" or not img.get("filename"):
                    continue
                r = await client.get(
                    f"{_base(provider)}/view",
                    params={"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")},
                    headers=_headers(provider),
                )
                if r.status_code >= 400:
                    raise ProviderError(f"下载 ComfyUI 输出失败（HTTP {r.status_code}）")
                mime = r.headers.get("content-type", "").split(";")[0]
                if not mime or mime == "application/octet-stream":
                    mime = mimetypes.guess_type(img["filename"])[0] or "application/octet-stream"
                results.append((r.content, mime))
    if not results:
        raise ProviderError("ComfyUI 工作流没有输出文件（请确认包含 SaveImage 或视频保存节点）")
    return results


def _uses_placeholder(workflow: Any, key: str) -> bool:
    return f"{{{{{key}}}}}" in json.dumps(workflow, ensure_ascii=False)


async def check(provider: Provider) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        r = await client.get(f"{_base(provider)}/system_stats", headers=_headers(provider))
    if r.status_code >= 400:
        raise ProviderError(f"连接 ComfyUI 失败（HTTP {r.status_code}）")
    return r.json()
