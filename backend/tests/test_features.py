import io
import sqlite3
import time
import zipfile

from PIL import Image

from app.routers.providers import classify_models
from app.services import comfyui, openai_compat


def make_png(color=(109, 93, 252), size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


PNG = make_png()


def _wait(c, task_id):
    for _ in range(200):
        t = c.get(f"/api/tasks/{task_id}").json()
        if t["status"] not in ("pending", "running"):
            return t
        time.sleep(0.03)
    raise AssertionError("task did not finish")


# ------------------------------------------------------------------ 模型服务


def test_provider_crud_keeps_key(installed):
    c = installed
    p = c.post("/api/providers", json={
        "name": "B", "base_url": "http://b/v1/", "api_key": "abcdefghijk",
        "chat_models": ["m1", "m1", " "], "video_models": ["sora-2"], "tts_models": ["tts-1"],
    }).json()
    assert p["base_url"] == "http://b/v1"
    assert p["chat_models"] == ["m1"] and p["video_models"] == ["sora-2"] and p["tts_models"] == ["tts-1"]
    p2 = c.put(f"/api/providers/{p['id']}", json={"name": "B2", "base_url": "http://b/v1", "chat_models": ["m2"]}).json()
    assert p2["has_key"] is True and p2["name"] == "B2"
    assert c.delete(f"/api/providers/{p['id']}").status_code == 200


def test_comfyui_workflow_kinds(installed):
    wf = installed.get("/api/providers/comfyui/example").json()["workflows"]
    workflows = {**wf, "视频": wf["SDXL 文生图"]}
    p = installed.post("/api/providers", json={
        "name": "C", "kind": "comfyui", "base_url": "http://c:8188",
        "extra": {"workflows": workflows, "workflow_kinds": {"视频": "video"}},
    }).json()
    assert p["image_models"] == ["SDXL 文生图"]
    assert p["video_models"] == ["视频"]


def test_classify_models():
    out = classify_models(["gpt-4o", "gpt-image-1", "sora-2", "tts-1", "text-embedding-3-small",
                           "Qwen/Qwen2.5-VL-72B-Instruct", "Kwai-Kolors/Kolors", "Wan-AI/Wan2.2-T2V-A14B"])
    assert out["chat"] == ["gpt-4o", "Qwen/Qwen2.5-VL-72B-Instruct"]
    assert out["image"] == ["gpt-image-1", "Kwai-Kolors/Kolors"]
    assert out["video"] == ["sora-2", "Wan-AI/Wan2.2-T2V-A14B"]
    assert out["tts"] == ["tts-1"]
    assert out["other"] == ["text-embedding-3-small"]


def test_fill_workflow():
    values = comfyui.build_values("a cat", {"size": "512x768", "seed": 7, "negative_prompt": "bad"})
    graph = comfyui.fill_workflow(comfyui.EXAMPLE_WORKFLOW, values)
    assert graph["5"]["inputs"]["width"] == 512 and graph["5"]["inputs"]["height"] == 768
    assert graph["3"]["inputs"]["seed"] == 7
    assert graph["6"]["inputs"]["text"] == "a cat"
    assert graph["7"]["inputs"]["text"] == "bad"


# ------------------------------------------------------------------ 对话


def test_chat_stream_with_reasoning(installed, monkeypatch):
    async def fake_stream(provider, model, messages, params):
        assert messages[-1] == {"role": "user", "content": "你好"}
        assert params == {"temperature": 0.3}
        yield "reasoning", "先想想"
        for part in ("你", "好！"):
            yield "content", part

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    c = installed
    conv = c.post("/api/conversations", json={"params": {"temperature": 0.3}}).json()
    assert conv["model"] == "chat-model"
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"content": "你好"})
    assert '"reasoning": "先想想"' in r.text and '"delta": "你"' in r.text and '"done": true' in r.text
    detail = c.get(f"/api/conversations/{conv['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    reply = detail["messages"][1]
    assert reply["content"] == "你好！" and reply["reasoning"] == "先想想" and reply["model"] == "chat-model"
    assert detail["title"] == "你好"
    # 重新生成会替换最后一条助手回复
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"regenerate": True})
    assert '"done": true' in r.text
    assert len(c.get(f"/api/conversations/{conv['id']}").json()["messages"]) == 2


def test_chat_multimodal_edit_export_search(installed, monkeypatch):
    seen = {}

    async def fake_stream(provider, model, messages, params):
        seen["messages"] = messages
        yield "content", "看到了"

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    c = installed
    asset = c.post("/api/assets/upload", files={"file": ("cat.png", PNG, "image/png")}).json()
    conv = c.post("/api/conversations", json={"system_prompt": "你是助手"}).json()
    cid = conv["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"content": "这是什么", "attachments": [asset["id"]]})
    user_msg = seen["messages"][-1]
    assert seen["messages"][0] == {"role": "system", "content": "你是助手"}
    assert user_msg["content"][0] == {"type": "text", "text": "这是什么"}
    assert user_msg["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    detail = c.get(f"/api/conversations/{cid}").json()
    assert detail["messages"][0]["attachments"][0]["id"] == asset["id"]

    # 编辑第一条消息并截断后续消息
    first = detail["messages"][0]["id"]
    assert c.patch(f"/api/conversations/{cid}/messages/{first}", json={"content": "改过的问题", "truncate": True}).status_code == 200
    detail = c.get(f"/api/conversations/{cid}").json()
    assert len(detail["messages"]) == 1 and detail["messages"][0]["content"] == "改过的问题"

    # 置顶与搜索
    c.patch(f"/api/conversations/{cid}", json={"pinned": True})
    other = c.post("/api/conversations", json={}).json()
    convs = c.get("/api/conversations").json()
    assert convs[0]["id"] == cid and convs[0]["pinned"] is True
    assert [x["id"] for x in c.get("/api/conversations", params={"q": "改过"}).json()] == [cid]
    assert other["id"] in [x["id"] for x in convs]

    md = c.get(f"/api/conversations/{cid}/export")
    assert md.status_code == 200 and "改过的问题" in md.text and "角色设定" in md.text


def test_prompt_enhance(installed, monkeypatch):
    async def fake_complete(provider, model, messages, **params):
        assert model == "chat-model" and "绘画" in messages[0]["content"]
        return "<think>嗯</think>一只橘猫，午后阳光，胶片质感"

    monkeypatch.setattr(openai_compat, "chat_complete", fake_complete)
    r = installed.post("/api/prompts/enhance", json={"prompt": "橘猫", "kind": "image"})
    assert r.json()["prompt"] == "一只橘猫，午后阳光，胶片质感"


# ------------------------------------------------------------------ 生成任务


def test_image_generation_with_reference(installed, monkeypatch):
    async def fake_gen(provider, model, prompt, params, references):
        assert params["size"] == "512x512" and params["style"] == "电影感"
        assert prompt == "a cat，电影剧照" and params["negative_prompt"] == "模糊, 卡通"
        assert references == [(PNG, "image/png")]
        return [(make_png((1, 2, 3), (80, 60)), "image/png"), (PNG, "image/png")]

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    ref = c.post("/api/assets/upload", files={"file": ("ref.png", PNG, "image/png")}).json()
    task = c.post("/api/generate/image", json={
        "prompt": "a cat", "size": "512x512", "n": 2, "style": "电影感", "style_prompt": "电影剧照",
        "style_negative": "卡通", "negative_prompt": "模糊", "reference_asset_ids": [ref["id"]],
    }).json()
    t = _wait(c, task["id"])
    assert t["status"] == "succeeded" and t["progress"] == 100, t
    assert t["prompt"] == "a cat"  # 记录中保留原始提示词
    assert len(t["assets"]) == 2
    a = t["assets"][0]
    assert (a["width"], a["height"]) == (80, 60)
    assert a["params"]["reference_asset_ids"] == [ref["id"]]
    assert c.get(a["url"]).content.startswith(b"\x89PNG")
    thumb = c.get(a["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"

    assets = c.get("/api/assets", params={"source": "generated"}).json()
    assert assets["total"] == 2
    assert c.get("/api/assets/models").json() == ["image-model"]
    ids = [x["id"] for x in assets["items"]]
    assert c.post("/api/assets/batch", json={"ids": ids, "action": "favorite"}).json()["count"] == 2
    assert c.get("/api/assets", params={"favorite": True}).json()["total"] == 2
    z = c.get("/api/assets-zip", params={"ids": ",".join(map(str, ids))})
    assert len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 2
    assert c.post("/api/assets/batch", json={"ids": ids, "action": "delete"}).json()["count"] == 2
    assert c.get("/api/stats").json()["images"] == 1


def test_reference_must_be_image(installed):
    audio = installed.post("/api/assets/upload", files={"file": ("a.mp3", b"ID3", "audio/mpeg")}).json()
    r = installed.post("/api/generate/image", json={"prompt": "x", "reference_asset_ids": [audio["id"]]})
    assert r.status_code == 400


def test_video_and_tts_tasks(installed, monkeypatch):
    c = installed
    c.put("/api/providers/1", json={
        "name": "Mock", "base_url": "http://mock/v1", "chat_models": ["chat-model"], "image_models": ["image-model"],
        "video_models": ["sora-2"], "tts_models": ["tts-1"],
    })

    async def fake_video(provider, model, prompt, params, reference, on_progress):
        assert params["seconds"] == 4 and reference is None
        await on_progress(50, "video_123")
        return [(b"\x00\x00\x00\x18ftypmp42", "video/mp4")]

    async def fake_speech(provider, model, text, params):
        assert params["voice"] == "alloy" and text == "你好"
        return b"ID3audio", "audio/mpeg"

    monkeypatch.setattr(openai_compat, "generate_video", fake_video)
    monkeypatch.setattr(openai_compat, "speech", fake_speech)

    v = c.post("/api/generate/video", json={"provider_id": 1, "model": "sora-2", "prompt": "海浪", "seconds": 4}).json()
    s = c.post("/api/generate/tts", json={"provider_id": 1, "model": "tts-1", "prompt": "你好", "voice": "alloy"}).json()
    tv, ts = _wait(c, v["id"]), _wait(c, s["id"])
    assert tv["status"] == "succeeded" and tv["assets"][0]["kind"] == "video" and tv["assets"][0]["thumb_url"] is None
    assert ts["status"] == "succeeded" and ts["assets"][0]["kind"] == "audio"
    assert c.get("/api/tasks", params={"kind": "video"}).json()[0]["id"] == v["id"]
    stats = c.get("/api/stats").json()
    assert stats["videos"] == 1 and stats["audios"] == 1 and len(stats["daily"]) == 14


def test_task_failure_retry_and_cancel(installed, monkeypatch):
    calls = {"n": 0}

    async def fake_gen(provider, model, prompt, params, references):
        calls["n"] += 1
        if calls["n"] == 1:
            raise openai_compat.ProviderError("额度不足")
        import asyncio

        await asyncio.sleep(5)
        return [(PNG, "image/png")]

    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    task = c.post("/api/images/generate", json={"prompt": "x"}).json()
    t = _wait(c, task["id"])
    assert t["status"] == "failed" and "额度不足" in t["error"]

    retry = c.post(f"/api/tasks/{t['id']}/retry").json()
    assert retry["prompt"] == "x"
    for _ in range(100):
        if c.get(f"/api/tasks/{retry['id']}").json()["status"] == "running":
            break
        time.sleep(0.02)
    assert c.get("/api/tasks", params={"status": "active"}).json()[0]["id"] == retry["id"]
    assert c.post(f"/api/tasks/{retry['id']}/cancel").status_code == 200
    assert _wait(c, retry["id"])["status"] == "cancelled"


# ------------------------------------------------------------------ 作品与其他


def test_upload_and_media_traversal(installed):
    c = installed
    r = c.post("/api/assets/upload", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["source"] == "upload" and r.json()["width"] == 64
    assert c.post("/api/assets/upload", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    assert c.get("/media/%2e%2e/test.db").status_code == 404
    assert c.get("/thumbs/%2e%2e/test.db").status_code == 404
    c.post("/api/auth/logout")
    assert c.get(r.json()["url"]).status_code == 401


def test_prompts_seeded_and_crud(installed):
    c = installed
    roles = c.get("/api/prompts", params={"category": "chat"}).json()
    assert len(roles) >= 3 and all(r["icon"] for r in roles)
    p = c.post("/api/prompts", json={"title": "赛博", "content": "cyberpunk", "icon": "🌃"}).json()
    assert p["icon"] == "🌃"
    assert c.put(f"/api/prompts/{p['id']}", json={"title": "新", "content": "x"}).json()["title"] == "新"
    assert c.delete(f"/api/prompts/{p['id']}").status_code == 200


def test_backup(installed):
    c = installed
    c.post("/api/assets/upload", files={"file": ("a.png", PNG, "image/png")})
    r = c.get("/api/system/backup")
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "pwd.db" in names and any(n.startswith("media/") for n in names)


def test_migration_adds_columns_to_v01_database(tmp_path, monkeypatch):
    """模拟 v0.1 的旧库：缺少新字段时启动应自动补齐，且旧数据可读。"""
    from app import db
    from app.config import settings

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE providers (id INTEGER PRIMARY KEY, name VARCHAR(64), kind VARCHAR(32), base_url VARCHAR(512),
            api_key TEXT, enabled BOOLEAN, chat_models JSON, image_models JSON, extra JSON, created_at DATETIME);
        INSERT INTO providers VALUES (1, 'old', 'openai', 'http://x/v1', '', 1, '["c"]', '["i"]', '{}', '2026-01-01 00:00:00');
        CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER, role VARCHAR(16), content TEXT, created_at DATETIME);
    """)
    conn.close()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db.init_engine(f"sqlite:///{path}")
    cols = {r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(providers)")}
    assert {"video_models", "tts_models"} <= cols
    from app.models import Provider

    with db.new_session() as s:
        p = s.get(Provider, 1)
        assert p.video_models == [] and p.chat_models == ["c"]


def test_provider_test_draft_uses_saved_key(installed, monkeypatch):
    seen = {}

    async def fake_list(provider):
        seen["key"] = provider.api_key
        return ["gpt-4o", "gpt-image-1"]

    monkeypatch.setattr(openai_compat, "list_models", fake_list)
    r = installed.post("/api/providers/test-draft", json={"id": 1, "base_url": "http://mock/v1"}).json()
    assert r["ok"] and seen["key"] == "sk-test-123456"
    assert r["classified"]["image"] == ["gpt-image-1"]
    r = installed.post("/api/providers/test-draft", json={"base_url": "http://x/v1", "api_key": "new"}).json()
    assert seen["key"] == "new"


def test_upgraded_instance_gets_builtin_prompts_once(installed):
    from app import db
    from app.models import PromptTemplate
    from app.seed import seed_if_upgraded
    from app.site import set_setting

    with db.new_session() as s:
        s.query(PromptTemplate).delete()
        set_setting(s, "builtin_seeded", False)
        s.commit()
        seed_if_upgraded(s)
        n = s.query(PromptTemplate).count()
        assert n >= 10
        seed_if_upgraded(s)
        assert s.query(PromptTemplate).count() == n
