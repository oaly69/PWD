import time

from app.services import comfyui, openai_compat

PNG = b"\x89PNG\r\n\x1a\nfake"


def test_provider_crud_keeps_key(installed):
    c = installed
    p = c.post("/api/providers", json={"name": "B", "base_url": "http://b/v1/", "api_key": "abcdefghijk", "chat_models": ["m1", "m1", " "]}).json()
    assert p["base_url"] == "http://b/v1"
    assert p["chat_models"] == ["m1"]
    p2 = c.put(f"/api/providers/{p['id']}", json={"name": "B2", "base_url": "http://b/v1", "chat_models": ["m2"]}).json()
    assert p2["has_key"] is True and p2["name"] == "B2"
    assert c.delete(f"/api/providers/{p['id']}").status_code == 200


def test_comfyui_provider_models_from_workflows(installed):
    wf = installed.get("/api/providers/comfyui/example").json()["workflows"]
    p = installed.post("/api/providers", json={"name": "C", "kind": "comfyui", "base_url": "http://c:8188", "extra": {"workflows": wf}}).json()
    assert p["image_models"] == list(wf.keys())


def test_fill_workflow():
    values = comfyui.build_values("a cat", {"size": "512x768", "seed": 7, "negative_prompt": "bad"})
    graph = comfyui.fill_workflow(comfyui.EXAMPLE_WORKFLOW, values)
    assert graph["5"]["inputs"]["width"] == 512 and graph["5"]["inputs"]["height"] == 768
    assert graph["3"]["inputs"]["seed"] == 7
    assert graph["6"]["inputs"]["text"] == "a cat"
    assert graph["7"]["inputs"]["text"] == "bad"


def test_chat_stream(installed, monkeypatch):
    async def fake_stream(provider, model, messages, params):
        assert messages[-1] == {"role": "user", "content": "你好"}
        for part in ("你", "好！"):
            yield part

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    c = installed
    conv = c.post("/api/conversations", json={}).json()
    assert conv["model"] == "chat-model"
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"content": "你好"})
    assert '"delta": "你"' in r.text and '"done": true' in r.text
    detail = c.get(f"/api/conversations/{conv['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "你好！"
    assert detail["title"] == "你好"
    # 重新生成会替换最后一条助手回复
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"regenerate": True})
    assert '"done": true' in r.text
    assert len(c.get(f"/api/conversations/{conv['id']}").json()["messages"]) == 2


def _wait(c, task_id):
    for _ in range(100):
        t = c.get(f"/api/tasks/{task_id}").json()
        if t["status"] in ("succeeded", "failed"):
            return t
        time.sleep(0.05)
    raise AssertionError("task did not finish")


def test_image_generation_and_assets(installed, monkeypatch):
    async def fake_gen(provider, model, prompt, params):
        assert params["size"] == "512x512"
        return [(PNG, "image/png"), (PNG, "image/png")]

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    task = c.post("/api/images/generate", json={"prompt": "a cat", "size": "512x512", "n": 2}).json()
    t = _wait(c, task["id"])
    assert t["status"] == "succeeded", t
    assert len(t["assets"]) == 2
    url = t["assets"][0]["url"]
    assert c.get(url).content == PNG
    assets = c.get("/api/assets").json()
    assert assets["total"] == 2
    aid = assets["items"][0]["id"]
    assert c.patch(f"/api/assets/{aid}", json={"favorite": True}).json()["favorite"] is True
    assert c.get("/api/assets", params={"favorite": True}).json()["total"] == 1
    assert c.delete(f"/api/assets/{aid}").status_code == 200
    assert c.get("/api/stats").json()["assets"] == 1


def test_image_generation_failure_recorded(installed, monkeypatch):
    async def fake_gen(provider, model, prompt, params):
        raise openai_compat.ProviderError("额度不足")

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    task = installed.post("/api/images/generate", json={"prompt": "x"}).json()
    t = _wait(installed, task["id"])
    assert t["status"] == "failed" and "额度不足" in t["error"]


def test_upload_and_media_traversal(installed):
    c = installed
    r = c.post("/api/assets/upload", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["source"] == "upload"
    assert c.post("/api/assets/upload", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    assert c.get("/media/%2e%2e/test.db").status_code == 404
    c.post("/api/auth/logout")
    assert c.get(r.json()["url"]).status_code == 401


def test_prompts_crud(installed):
    c = installed
    p = c.post("/api/prompts", json={"title": "赛博朋克", "content": "cyberpunk city"}).json()
    assert c.get("/api/prompts", params={"category": "image"}).json()[0]["title"] == "赛博朋克"
    assert c.put(f"/api/prompts/{p['id']}", json={"title": "新", "content": "x"}).json()["title"] == "新"
    assert c.delete(f"/api/prompts/{p['id']}").status_code == 200
