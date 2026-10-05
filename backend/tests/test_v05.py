"""v0.5：用户组权限、用量配额、故障切换、两步验证、单点登录、操作日志。"""
import time

from app.security import totp_now
from app.services import oidc, openai_compat


def _login(c, username, password, **extra):
    c.post("/api/auth/logout")
    return c.post("/api/auth/login", json={"username": username, "password": password, **extra})


def _as_admin(c):
    assert _login(c, "admin", "password123").json()["ok"]


def _wait(c, tid):
    for _ in range(100):
        t = c.get(f"/api/tasks/{tid}").json()
        if t["status"] not in ("pending", "running"):
            return t
        time.sleep(0.05)
    raise AssertionError("task timeout")


def _png():
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, "PNG")
    return out.getvalue()


def test_group_permissions_and_quota(installed, monkeypatch):
    async def fake_stream(provider, model, messages, params):
        yield "content", "你好呀"
        yield "usage", {"prompt_tokens": 10, "completion_tokens": 5}

    async def fake_gen(provider, model, prompt, params, refs=None):
        return [(_png(), "image/png")] * int(params.get("n") or 1)

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    pid = c.get("/api/providers").json()[0]["id"]
    c.put(f"/api/providers/{pid}", json={**c.get("/api/providers").json()[0], "api_key": None, "chat_models": ["chat-model", "chat-pro"]})
    g = c.post("/api/groups", json={
        "name": "体验组", "kinds": ["chat", "image"], "models": {"chat": [f"{pid}::chat-model"]},
        "quotas": {"chat_daily": 2, "image_daily": 3},
    }).json()
    assert g["kinds"] == ["chat", "image"]
    uid = c.post("/api/users", json={"username": "bob", "password": "password123", "group_id": g["id"]}).json()["id"]
    assert [x["group_id"] for x in c.get("/api/users").json() if x["id"] == uid] == [g["id"]]

    _login(c, "bob", "password123")
    p = c.get("/api/providers").json()[0]
    assert p["chat_models"] == ["chat-model"] and p["image_models"] == ["image-model"] and p["video_models"] == []
    cid = c.post("/api/conversations", json={}).json()["id"]
    # 白名单外的模型、没有权限的能力
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "x", "models": [{"provider_id": pid, "model": "chat-pro"}]})
    assert r.status_code == 403
    assert c.post("/api/generate/video", json={"prompt": "x", "provider_id": pid, "model": "image-model"}).status_code == 403
    # 对话配额：每天 2 条
    for _ in range(2):
        assert '"done": true' in c.post(f"/api/conversations/{cid}/messages", json={"content": "嗨"}).text
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "嗨"})
    assert r.status_code == 429 and "额度" in r.json()["detail"]
    me = c.get("/api/usage/me").json()
    assert me["usage"]["today"]["chat"] == 2 and me["usage"]["tokens_month"] == 30 and me["quotas"]["chat_daily"] == 2
    # 图像配额按张数：已用 2 张，再要 2 张超出
    t = _wait(c, c.post("/api/generate/image", json={"prompt": "猫", "n": 2}).json()["id"])
    assert t["status"] == "succeeded"
    assert c.post("/api/generate/image", json={"prompt": "猫", "n": 2}).status_code == 429
    assert c.get("/api/usage/report").status_code == 403

    _as_admin(c)
    report = c.get("/api/usage/report").json()
    bob = next(u for u in report["users"] if u["username"] == "bob")
    assert bob["chat"] == 2 and bob["image"] == 2 and bob["tokens"] == 30
    # 管理员不受限制；删除用户组后 bob 不再受限
    c.delete(f"/api/groups/{g['id']}")
    _login(c, "bob", "password123")
    assert c.get("/api/providers").json()[0]["video_models"] == []  # 服务本身没有视频模型
    assert c.get("/api/usage/me").json()["group"] is None


def test_failover_chat_and_task(installed, monkeypatch):
    calls = []

    async def fake_stream(provider, model, messages, params):
        calls.append(provider.name)
        if provider.name == "Mock":
            raise openai_compat.ProviderError("上游繁忙", 503)
        yield "content", f"来自 {provider.name}"

    async def fake_gen(provider, model, prompt, params, refs=None):
        calls.append(provider.name)
        if provider.name == "Mock":
            raise openai_compat.ProviderError("限流", 429)
        return [(_png(), "image/png")]

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    c.post("/api/providers", json={"name": "备用A", "base_url": "http://a/v1", "chat_models": ["chat-model"], "image_models": ["image-model"], "extra": {"priority": 1}})
    c.post("/api/providers", json={"name": "备用B", "base_url": "http://b/v1", "chat_models": ["chat-model"], "extra": {"priority": 5}})
    cid = c.post("/api/conversations", json={}).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "hi"})
    assert '"failover": "备用B"' in r.text and '"done": true' in r.text
    assert calls == ["Mock", "备用B"]
    msg = c.get(f"/api/conversations/{cid}").json()["messages"][-1]
    assert msg["content"] == "来自 备用B" and msg["served_by"] == "备用B"

    t = _wait(c, c.post("/api/generate/image", json={"prompt": "猫"}).json()["id"])
    assert t["status"] == "succeeded" and t["params"]["served_by"] == "备用A"

    # 关闭故障切换后直接失败
    c.put("/api/settings", json={"failover_enabled": False})
    t = _wait(c, c.post("/api/generate/image", json={"prompt": "猫"}).json()["id"])
    assert t["status"] == "failed" and "限流" in t["error"]

    # 不可重试的错误（如 400）不切换
    async def bad_request(provider, model, messages, params):
        raise openai_compat.ProviderError("参数错误", 400)
        yield  # noqa

    c.put("/api/settings", json={"failover_enabled": True})
    monkeypatch.setattr(openai_compat, "chat_stream", bad_request)
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "hi"})
    assert "failover" not in r.text and "参数错误" in r.text


def test_two_factor_login(installed):
    c = installed
    setup = c.post("/api/auth/2fa/setup").json()
    assert setup["uri"].startswith("otpauth://totp/")
    assert c.post("/api/auth/2fa/enable", json={"secret": setup["secret"], "code": "000000"}).status_code == 400
    assert c.post("/api/auth/2fa/enable", json={"secret": setup["secret"], "code": totp_now(setup["secret"])}).json()["ok"]
    assert c.get("/api/auth/me").json()["totp_enabled"]
    r = _login(c, "admin", "password123")
    assert r.json() == {"ok": False, "need_totp": True}
    assert c.get("/api/auth/me").status_code == 401  # 未发放会话
    assert _login(c, "admin", "password123", code="123456").status_code == 401
    assert _login(c, "admin", "password123", code=totp_now(setup["secret"])).json()["ok"]
    # 管理员可为用户重置两步验证
    me_id = c.get("/api/auth/me").json()["id"]
    c.post("/api/users", json={"username": "bob", "password": "password123"})
    bob = next(u for u in c.get("/api/users").json() if u["username"] == "bob")
    c.patch(f"/api/users/{bob['id']}", json={"reset_2fa": True})
    assert c.post("/api/auth/2fa/disable", json={"password": "wrong"}).status_code == 400
    assert c.post("/api/auth/2fa/disable", json={"password": "password123"}).json()["ok"]
    assert _login(c, "admin", "password123").json()["ok"] and me_id


def test_oidc_login_flow(installed, monkeypatch):
    c = installed
    assert c.get("/api/auth/oidc/login", follow_redirects=False).status_code == 404
    c.put("/api/settings", json={
        "oidc_enabled": True, "oidc_issuer": "https://idp.example.com", "oidc_client_id": "pwd", "oidc_client_secret": "s3cret",
        "register_need_approval": False, "public_url": "https://pwd.example.com",
    })
    settings = c.get("/api/settings").json()
    assert "oidc_client_secret" not in settings and settings["oidc_client_secret_set"] is True
    assert c.get("/api/site").json()["oidc_enabled"] is True

    seen = {}

    async def fake_discover(issuer):
        return {"authorization_endpoint": "https://idp.example.com/auth", "token_endpoint": "https://idp.example.com/token",
                "userinfo_endpoint": "https://idp.example.com/userinfo"}

    async def fake_exchange(conf, code, redirect_uri, client_id, secret):
        seen.update(code=code, redirect=redirect_uri, secret=secret)
        return {"access_token": "at"}

    async def fake_userinfo(conf, tokens):
        return {"sub": "u-1", "preferred_username": "carol", "email": "carol@example.com"}

    monkeypatch.setattr(oidc, "discover", fake_discover)
    monkeypatch.setattr(oidc, "exchange", fake_exchange)
    monkeypatch.setattr(oidc, "userinfo", fake_userinfo)

    c.post("/api/auth/logout")
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://idp.example.com/auth?")
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["redirect_uri"] == ["https://pwd.example.com/api/auth/oidc/callback"]
    # state 不匹配
    r = c.get("/api/auth/oidc/callback", params={"code": "abc", "state": "wrong"}, follow_redirects=False)
    assert "sso_error" in r.headers["location"]
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = c.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/" and seen["secret"] == "s3cret"
    me = c.get("/api/auth/me").json()
    assert me["username"] == "carol" and me["oidc_linked"] and not me["is_admin"]
    # 再次登录复用同一账号
    c.post("/api/auth/logout")
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    c.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert c.get("/api/auth/me").json()["id"] == me["id"]

    # 关闭自动创建 + 管理员绑定自己的账号
    _as_admin(c)
    c.put("/api/settings", json={"oidc_auto_create": False})

    async def admin_info(conf, tokens):
        return {"sub": "admin-sub", "preferred_username": "boss"}

    monkeypatch.setattr(oidc, "userinfo", admin_info)
    r = c.get("/api/auth/oidc/login", params={"link": True}, follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = c.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "/settings?sso=linked"
    c.post("/api/auth/logout")
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    c.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert c.get("/api/auth/me").json()["username"] == "admin"


def test_audit_log(installed):
    c = installed
    _login(c, "admin", "wrong")
    _as_admin(c)
    c.post("/api/users", json={"username": "bob", "password": "password123"})
    c.put("/api/settings", json={"site_name": "新名字"})
    logs = c.get("/api/audit").json()
    actions = [i["action"] for i in logs["items"]]
    assert {"auth.login_failed", "auth.login", "user.create", "settings.update"} <= set(actions)
    assert logs["items"][0]["label"] == "修改系统设置"
    assert c.get("/api/audit", params={"action": "user.create"}).json()["items"][0]["target"] == "bob"
    _login(c, "bob", "password123")
    assert c.get("/api/audit").status_code == 403
