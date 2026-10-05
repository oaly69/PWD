"""v0.9：批量生成、UTC+8 时间。"""
import asyncio
import time
from datetime import datetime, timedelta, timezone

from app import timeutil
from app.services import openai_compat

from .test_features import PNG, _wait
from .test_v05 import _login


def _wait_all(c, batch_id):
    for _ in range(300):
        rows = c.get(f"/api/task-batches/{batch_id}").json()
        if all(t["status"] not in ("pending", "running") for t in rows):
            return rows
        time.sleep(0.03)
    raise AssertionError("batch did not finish")


def test_batch_image_generation(installed, monkeypatch):
    seen = []

    async def fake_gen(provider, model, prompt, params, references):
        seen.append((prompt, params["size"], params["n"]))
        return [(PNG, "image/png")] * params["n"]

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    r = c.post("/api/generate/image/batch", json={"prompts": ["一只猫", "  ", "一只狗", "一只兔子"], "size": "512x512", "n": 2})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [t["prompt"] for t in data["tasks"]] == ["一只兔子", "一只狗", "一只猫"]
    assert data["tasks"][0]["params"]["batch_index"] == 3 and data["tasks"][0]["params"]["batch_total"] == 3
    rows = _wait_all(c, data["batch_id"])
    assert all(t["status"] == "succeeded" and len(t["assets"]) == 2 for t in rows)
    assert sorted(seen) == sorted([("一只猫", "512x512", 2), ("一只狗", "512x512", 2), ("一只兔子", "512x512", 2)])
    listed = c.get("/api/tasks", params={"batch": data["batch_id"]}).json()
    assert len(listed) == 3
    assert c.get("/api/task-batches/nope").status_code == 404
    assert c.post("/api/generate/image/batch", json={"prompts": [" "]}).status_code == 400
    assert c.post("/api/generate/image/batch", json={"prompts": ["x"] * 51}).status_code == 422
    assert c.post("/api/generate/tts/batch", json={"prompts": ["x"]}).status_code == 422


def test_batch_cancel(installed, monkeypatch):
    async def slow_gen(provider, model, prompt, params, references):
        await asyncio.sleep(30)
        return [(PNG, "image/png")]

    monkeypatch.setattr(openai_compat, "generate_images", slow_gen)
    c = installed
    data = c.post("/api/generate/image/batch", json={"prompts": ["a", "b", "c"]}).json()
    r = c.post(f"/api/task-batches/{data['batch_id']}/cancel").json()
    assert r["cancelled"] == 3
    rows = _wait_all(c, data["batch_id"])
    assert {t["status"] for t in rows} == {"cancelled"}


def test_batch_respects_quota(installed, monkeypatch):
    async def fake_gen(provider, model, prompt, params, references):
        return [(PNG, "image/png")]

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    g = c.post("/api/groups", json={"name": "体验组", "kinds": ["image"], "quotas": {"image_daily": 3}}).json()
    c.post("/api/users", json={"username": "bob", "password": "password123", "group_id": g["id"]})
    _login(c, "bob", "password123")
    r = c.post("/api/generate/image/batch", json={"prompts": ["a", "b"], "n": 2})
    assert r.status_code == 429 or r.status_code == 403, r.text
    assert "额度" in r.json()["detail"]
    ok = c.post("/api/generate/image/batch", json={"prompts": ["a", "b", "c"]})
    assert ok.status_code == 200


def test_times_are_utc8(installed, monkeypatch):
    async def fake_gen(provider, model, prompt, params, references):
        return [(PNG, "image/png")]

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    t = _wait(c, c.post("/api/generate/image", json={"prompt": "x"}).json()["id"])
    assert t["created_at"].endswith("+08:00") and t["finished_at"].endswith("+08:00")
    created = datetime.fromisoformat(t["created_at"])
    assert abs((created - datetime.now(timezone.utc)).total_seconds()) < 60
    assert c.get("/api/conversations").status_code == 200
    stats = c.get("/api/stats").json()
    assert stats["daily"][-1]["date"] == timeutil.now().date().isoformat() and stats["daily"][-1]["count"] == 1


def test_timeutil():
    assert timeutil.iso(None) is None
    assert timeutil.iso(datetime(2026, 1, 1, 16, 30)) == "2026-01-02T00:30:00+08:00"
    start = timeutil.day_start()
    local = start.astimezone(timeutil.TZ)
    assert (local.hour, local.minute) == (0, 0) and local.date() == timeutil.now().date()
    assert timeutil.day_start(1) == start - timedelta(days=1)
