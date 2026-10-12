"""v0.10：生成数量补齐。"""
import asyncio
import base64
import json

import httpx

from app.models import Provider
from app.services import openai_compat

from .test_features import PNG


def _client_factory(handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return factory


def test_generate_images_fills_missing(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body)
        # 模拟忽略 n 的服务：每次只返回 1 张
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    monkeypatch.setattr(openai_compat.httpx, "AsyncClient", _client_factory(handler))
    p = Provider(name="x", kind="openai", base_url="http://mock/v1", api_key="k")
    imgs = asyncio.run(openai_compat.generate_images(p, "m", "cat", {"n": 3, "seed": 10}))
    assert len(imgs) == 3
    assert calls[0]["n"] == 3 and len(calls) == 3
    assert sorted(c["seed"] for c in calls[1:]) == [11, 12]


def test_generate_images_respects_full_batch(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}] * body["n"]})

    monkeypatch.setattr(openai_compat.httpx, "AsyncClient", _client_factory(handler))
    p = Provider(name="x", kind="openai", base_url="http://mock/v1", api_key="k")
    assert len(asyncio.run(openai_compat.generate_images(p, "m", "cat", {"n": 4}))) == 4
    assert len(calls) == 1


def _ark_handler(calls, *, reject_body_params=False):
    state = {"polls": 0}

    def handler(request: httpx.Request):
        url = str(request.url)
        if request.method == "POST" and url.endswith("/contents/generations/tasks"):
            body = json.loads(request.content)
            calls.append(body)
            if reject_body_params and "resolution" in body:
                return httpx.Response(400, json={"error": {"message": "unknown field resolution"}})
            return httpx.Response(200, json={"id": "cgt-1"})
        if request.method == "GET" and url.endswith("/contents/generations/tasks/cgt-1"):
            state["polls"] += 1
            if state["polls"] < 2:
                return httpx.Response(200, json={"id": "cgt-1", "status": "running"})
            return httpx.Response(200, json={"id": "cgt-1", "status": "succeeded", "content": {"video_url": "https://tos.example/v.mp4"}})
        if url == "https://tos.example/v.mp4":
            return httpx.Response(200, content=b"\x00\x00\x00\x18ftypmp42", headers={"content-type": "application/octet-stream"})
        return httpx.Response(404)

    return handler


async def _no_sleep(_s):
    return None


def test_seedance_video(monkeypatch):
    calls, progress = [], []
    monkeypatch.setattr(openai_compat.httpx, "AsyncClient", _client_factory(_ark_handler(calls)))
    monkeypatch.setattr(openai_compat.asyncio, "sleep", _no_sleep)
    # 按旧预设保存为 openai 风格的方舟服务也自动识别为 ark
    p = Provider(name="方舟", kind="openai", base_url="https://ark.cn-beijing.volces.com/api/v3", api_key="k", extra={"video_api": "openai"})
    assert openai_compat.video_api_of(p) == "ark"

    async def on_progress(pct, job_id):
        progress.append(job_id)

    out = asyncio.run(openai_compat.generate_video(
        p, "doubao-seedance-1-0-pro-250528", "猫在窗台", {"size": "1280x720", "seconds": 5, "seed": 7}, (PNG, "image/png"), on_progress,
    ))
    assert out[0][1] == "video/mp4" and out[0][0].startswith(b"\x00\x00\x00\x18ftyp")
    body = calls[0]
    assert body["model"] == "doubao-seedance-1-0-pro-250528"
    assert (body["resolution"], body["ratio"], body["duration"], body["seed"]) == ("720p", "adaptive", 5, 7)
    assert body["content"][0] == {"type": "text", "text": "猫在窗台"}
    assert body["content"][1]["role"] == "first_frame" and body["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert progress and set(progress) == {"cgt-1"}


def test_seedance_text_command_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(openai_compat.httpx, "AsyncClient", _client_factory(_ark_handler(calls, reject_body_params=True)))
    monkeypatch.setattr(openai_compat.asyncio, "sleep", _no_sleep)
    p = Provider(name="方舟", kind="openai", base_url="https://ark.cn-beijing.volces.com/api/v3", api_key="k", extra={"video_api": "ark"})

    async def on_progress(pct, job_id):
        return None

    asyncio.run(openai_compat.generate_video(p, "m", "海浪", {"size": "720x1280", "seconds": 10, "extra_body": {"camera_fixed": True}}, None, on_progress))
    assert len(calls) == 2
    assert calls[1]["content"][0]["text"] == "海浪 --resolution 720p --ratio 9:16 --duration 10 --camerafixed true"
    assert "resolution" not in calls[1] and "camera_fixed" not in calls[1]


def test_ark_size():
    assert openai_compat._ark_size("1920x1080") == ("1080p", "16:9")
    assert openai_compat._ark_size("864x480") == ("480p", "16:9")
    assert openai_compat._ark_size("1024x1024") == ("1080p", "1:1")
    assert openai_compat._ark_size("bad") == (None, None)
