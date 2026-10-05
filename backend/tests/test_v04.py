"""v0.4：对话分支、多模型对比。"""
import json

from app.services import openai_compat


def _events(text: str) -> list[dict]:
    return [json.loads(line[5:]) for line in text.splitlines() if line.startswith("data:")]


def _fake(monkeypatch, fail_model: str | None = None):
    calls = []

    async def fake_stream(provider, model, messages, params):
        calls.append((model, [m["content"] for m in messages]))
        if model == fail_model:
            yield "content", "半截"
            raise openai_compat.ProviderError("额度不足")
        yield "content", f"{model} 回答 {len(calls)}"

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    return calls


def test_branching_edit_regenerate_switch(installed, monkeypatch):
    calls = _fake(monkeypatch)
    c = installed
    cid = c.post("/api/conversations", json={}).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"content": "问题一"})
    c.post(f"/api/conversations/{cid}/messages", json={"content": "问题二"})
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert [m["content"] for m in path] == ["问题一", "chat-model 回答 1", "问题二", "chat-model 回答 2"]
    q2 = path[2]

    # 编辑「问题二」：作为同级分支重新发送，历史里只包含之前的消息
    c.post(f"/api/conversations/{cid}/messages", json={"content": "问题二（改）", "parent_id": q2["parent_id"]})
    assert calls[-1][1] == ["问题一", "chat-model 回答 1", "问题二（改）"]
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert path[2]["content"] == "问题二（改）" and path[2]["siblings"] == [q2["id"], path[2]["id"]]

    # 对「问题一」重新生成：从中间分叉，不影响原分支
    c.post(f"/api/conversations/{cid}/messages", json={"regenerate": True, "parent_id": path[0]["id"]})
    assert calls[-1][1] == ["问题一"]
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert len(path) == 2 and len(path[1]["siblings"]) == 2

    # 切回原来的第一个回答 → 自动定位到该分支最新的末端
    first_answer = path[1]["siblings"][0]
    path = c.post(f"/api/conversations/{cid}/branch", json={"message_id": first_answer}).json()["messages"]
    assert [m["content"] for m in path][-1] == "chat-model 回答 3"

    # 删除「问题二（改）」分支后回到原来的「问题二」
    c.delete(f"/api/conversations/{cid}/messages/{path[2]['id']}")
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert path[2]["content"] == "问题二" and path[2]["siblings"] == [q2["id"]]

    # 编辑第一条消息（parent_id=null）产生新的根
    c.post(f"/api/conversations/{cid}/messages", json={"content": "全新开头", "parent_id": None})
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert path[0]["content"] == "全新开头" and len(path[0]["siblings"]) == 2 and len(path) == 2
    md = c.get(f"/api/conversations/{cid}/export").text
    assert "全新开头" in md and "问题二" not in md


def test_compare_models(installed, monkeypatch):
    calls = _fake(monkeypatch, fail_model="bad-model")
    c = installed
    pid = c.get("/api/providers").json()[0]["id"]
    cid = c.post("/api/conversations", json={}).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={
        "content": "比一比",
        "models": [{"provider_id": pid, "model": "chat-model"}, {"provider_id": pid, "model": "bad-model"}],
    })
    events = _events(r.text)
    head = events[0]
    assert head["start"] and head["compare_group"] and len(head["replies"]) == 2
    assert any(e.get("error") == "额度不足" and e["i"] == 1 for e in events)
    assert any(e.get("done") and e["i"] == 0 for e in events)
    assert len(calls) == 2
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    alts = path[1]["alternatives"]
    assert [a["model"] for a in alts] == ["chat-model", "bad-model"]
    assert alts[1]["error"] == "额度不足" and alts[1]["content"] == "半截"
    # 失败的空回答不进入后续上下文；选用第二个回答继续对话
    c.post(f"/api/conversations/{cid}/branch", json={"message_id": alts[1]["id"]})
    c.post(f"/api/conversations/{cid}/messages", json={"content": "继续"})
    assert calls[-1][1] == ["比一比", "半截", "继续"]


def test_compare_rejects_foreign_or_disabled_provider(installed, monkeypatch):
    _fake(monkeypatch)
    c = installed
    cid = c.post("/api/conversations", json={}).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "x", "models": [{"provider_id": 999, "model": "m"}]})
    assert r.status_code == 400
    p = c.get("/api/providers").json()[0]
    c.put(f"/api/providers/{p['id']}", json={**p, "api_key": None, "enabled": False})
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "x", "models": [{"provider_id": p["id"], "model": "m"}]})
    assert r.status_code == 400 and "停用" in r.json()["detail"]


# ------------------------------------------------------------------ 图像编辑

import base64  # noqa: E402
import io  # noqa: E402
import time  # noqa: E402

from PIL import Image  # noqa: E402


def _png(size=(64, 48), color=(200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def _upload(c, data=None):
    r = c.post("/api/assets/upload", files={"file": ("a.png", data or _png(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()


def _wait(c, tid):
    for _ in range(100):
        t = c.get(f"/api/tasks/{tid}").json()
        if t["status"] not in ("pending", "running"):
            return t
        time.sleep(0.05)
    raise AssertionError("task timeout")


def _mask_uri(size=(64, 48), box=(10, 10, 30, 30)) -> str:
    m = Image.new("L", size, 0)
    m.paste(255, box)
    out = io.BytesIO()
    m.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def test_local_upscale(installed):
    c = installed
    a = _upload(c)
    t = c.post("/api/images/edit", json={"op": "upscale", "source_asset_id": a["id"], "scale": 2}).json()
    assert t["model"] == "本地放大" and t["provider_id"] is None
    t = _wait(c, t["id"])
    assert t["status"] == "succeeded", t["error"]
    assert (t["assets"][0]["width"], t["assets"][0]["height"]) == (128, 96)
    # 重试同样可用
    t2 = _wait(c, c.post(f"/api/tasks/{t['id']}/retry").json()["id"])
    assert t2["status"] == "succeeded"


def test_inpaint_openai_sends_mask(installed, monkeypatch):
    seen = {}

    async def fake_edit(provider, model, prompt, params, image, mask=None, mask_white=None):
        seen.update(prompt=prompt, image=Image.open(io.BytesIO(image)), mask=Image.open(io.BytesIO(mask)), white=mask_white)
        return [(_png((64, 48), (0, 0, 255)), "image/png")]

    monkeypatch.setattr(openai_compat, "edit_image", fake_edit)
    c = installed
    a = _upload(c)
    pid = c.get("/api/providers").json()[0]["id"]
    body = {"op": "inpaint", "source_asset_id": a["id"], "provider_id": pid, "model": "image-model", "prompt": "一只猫"}
    assert c.post("/api/images/edit", json=body).status_code == 400  # 缺蒙版
    empty = _mask_uri(box=(0, 0, 0, 0))
    assert c.post("/api/images/edit", json={**body, "mask": empty}).status_code == 400
    t = _wait(c, c.post("/api/images/edit", json={**body, "mask": _mask_uri()}).json()["id"])
    assert t["status"] == "succeeded", t["error"]
    assert seen["prompt"] == "一只猫" and seen["image"].size == (64, 48)
    # OpenAI 蒙版：涂抹区域透明，其余不透明
    assert seen["mask"].mode == "RGBA" and seen["mask"].getpixel((15, 15))[3] == 0 and seen["mask"].getpixel((50, 40))[3] == 255
    assert t["params"]["op"] == "inpaint" and "mask" not in t["params"]


def test_outpaint_and_rembg_comfyui(installed, monkeypatch):
    from app.services import comfyui

    seen = []

    async def fake_comfy(provider, model, prompt, params, references=None, on_progress=None, timeout=3600, uploads=None, overrides=None):
        seen.append({"uploads": uploads, "overrides": overrides, "model": model})
        return [(_png(), "image/png")]

    monkeypatch.setattr(comfyui, "generate", fake_comfy)
    c = installed
    pid = c.post("/api/providers", json={"name": "Comfy", "kind": "comfyui", "base_url": "http://comfy:8188", "image_models": ["SDXL 局部重绘"],
                                         "extra": {"workflows": {"SDXL 局部重绘": {"1": {}}}}}).json()["id"]
    a = _upload(c)
    t = _wait(c, c.post("/api/images/edit", json={"op": "outpaint", "source_asset_id": a["id"], "provider_id": pid, "model": "SDXL 局部重绘",
                                                   "expand": {"left": 16, "right": 16}}).json()["id"])
    assert t["status"] == "succeeded", t["error"]
    up = seen[-1]["uploads"]
    img = Image.open(io.BytesIO(up["image"][0]))
    mask = Image.open(io.BytesIO(up["mask"][0]))
    assert img.size == (96, 48) and seen[-1]["overrides"] == {"width": 96, "height": 48}
    # 扩展区为重绘区（透明 / 白色），原图中心保持不变
    assert img.getpixel((2, 20))[3] == 0 and img.getpixel((48, 24))[3] == 255
    assert mask.getpixel((2, 20)) == 255 and mask.getpixel((48, 24)) == 0
    t = _wait(c, c.post("/api/images/edit", json={"op": "rembg", "source_asset_id": a["id"], "provider_id": pid, "model": "SDXL 局部重绘"}).json()["id"])
    assert t["status"] == "succeeded" and t["prompt"] == "去除背景"
    t = _wait(c, c.post("/api/images/edit", json={"op": "upscale", "source_asset_id": a["id"], "provider_id": pid, "model": "SDXL 局部重绘", "scale": 3}).json()["id"])
    assert seen[-1]["overrides"]["width"] == 192


def test_edit_requires_owner(installed):
    c = installed
    a = _upload(c)
    c.post("/api/users", json={"username": "bob", "password": "password123", "role": "user"})
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    r = c.post("/api/images/edit", json={"op": "upscale", "source_asset_id": a["id"]})
    assert r.status_code == 404


def test_boards(installed):
    c = installed
    a1, a2, a3 = _upload(c), _upload(c), _upload(c)
    b = c.post("/api/boards", json={"name": "秋季海报"}).json()
    assert b["count"] == 0
    assert c.post("/api/assets/batch", json={"ids": [a1["id"], a2["id"]], "action": "move", "board_id": b["id"]}).json()["count"] == 2
    boards = c.get("/api/boards").json()
    assert boards[0]["count"] == 2 and len(boards[0]["covers"]) == 2
    assert c.get(f"/api/assets?board_id={b['id']}").json()["total"] == 2
    assert [x["id"] for x in c.get("/api/assets?board_id=0").json()["items"]] == [a3["id"]]
    assert c.patch(f"/api/assets/{a1['id']}", json={"board_id": 0}).json()["board_id"] is None
    assert c.patch(f"/api/boards/{b['id']}", json={"name": "冬季"}).json()["name"] == "冬季"
    # 别人的作品集不可用
    c.post("/api/users", json={"username": "bob", "password": "password123", "role": "user"})
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    mine = _upload(c)
    assert c.get("/api/boards").json() == []
    assert c.patch(f"/api/assets/{mine['id']}", json={"board_id": b["id"]}).status_code == 404
    assert c.delete(f"/api/boards/{b['id']}").status_code == 404
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    # 删除作品集不删除作品
    c.delete(f"/api/boards/{b['id']}")
    assert c.get(f"/api/assets/{a2['id']}").json()["board_id"] is None
