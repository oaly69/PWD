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
