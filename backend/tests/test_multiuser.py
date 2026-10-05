import io

from PIL import Image

from app.services import openai_compat

from .conftest import ADMIN


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 10, 10)).save(buf, "PNG")
    return buf.getvalue()


def login(c, username, password):
    c.cookies.clear()
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


def make_user(c, username="alice", password="alicepass1", role="user"):
    r = c.post("/api/users", json={"username": username, "password": password, "role": role})
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_creates_user_and_data_is_isolated(installed, monkeypatch):
    c = installed
    make_user(c)
    # 管理员的数据
    admin_conv = c.post("/api/conversations", json={"title": "管理员的对话"}).json()
    admin_asset = c.post("/api/assets/upload", files={"file": ("a.png", png(), "image/png")}).json()
    admin_prompt = c.post("/api/prompts", json={"title": "管理员私有", "content": "x"}).json()
    shared_prompt = c.post("/api/prompts", json={"title": "共享给大家", "content": "y", "shared": True}).json()
    assert admin_prompt["shared"] is False and shared_prompt["shared"] is True

    login(c, "alice", "alicepass1")
    me = c.get("/api/auth/me").json()
    assert me["role"] == "user" and me["is_admin"] is False
    assert c.get("/api/conversations").json() == []
    assert c.get(f"/api/conversations/{admin_conv['id']}").status_code == 404
    assert c.get("/api/assets").json()["total"] == 0
    assert c.get(admin_asset["url"]).status_code == 404
    assert c.get(admin_asset["thumb_url"]).status_code == 404
    assert c.patch(f"/api/assets/{admin_asset['id']}", json={"favorite": True}).status_code == 404
    titles = {p["title"] for p in c.get("/api/prompts").json()}
    assert "共享给大家" in titles and "管理员私有" not in titles
    # 公共模板不能被普通用户修改或删除
    assert c.put(f"/api/prompts/{shared_prompt['id']}", json={"title": "改", "content": "z"}).status_code == 403
    assert c.delete(f"/api/prompts/{shared_prompt['id']}").status_code == 403
    # 普通用户自建模板始终是私有的
    mine = c.post("/api/prompts", json={"title": "alice 的", "content": "z", "shared": True}).json()
    assert mine["shared"] is False

    # 自己的数据正常可用，且不能引用别人的作品
    conv = c.post("/api/conversations", json={}).json()
    assert conv["model"] == "chat-model"
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hi", "attachments": [admin_asset["id"]]})
    assert r.status_code == 400
    r = c.post("/api/generate/image", json={"prompt": "x", "reference_asset_ids": [admin_asset["id"]]})
    assert r.status_code == 400
    own = c.post("/api/assets/upload", files={"file": ("b.png", png(), "image/png")}).json()
    assert c.get(own["url"]).status_code == 200
    stats = c.get("/api/stats").json()
    assert stats["assets"] == 1 and "site" not in stats

    login(c, "admin", ADMIN["admin_password"])
    assert c.get("/api/assets").json()["total"] == 1
    assert c.get("/api/stats").json()["site"]["users"] == 2


def test_non_admin_forbidden_from_admin_apis(installed):
    c = installed
    make_user(c)
    login(c, "alice", "alicepass1")
    providers = c.get("/api/providers").json()
    assert providers[0]["chat_models"] == ["chat-model"]
    assert "base_url" not in providers[0] and "api_key_masked" not in providers[0]
    for method, url, body in [
        ("post", "/api/providers", {"base_url": "http://x"}),
        ("put", "/api/providers/1", {"base_url": "http://x"}),
        ("delete", "/api/providers/1", None),
        ("post", "/api/providers/1/test", None),
        ("post", "/api/providers/test-draft", {"base_url": "http://x"}),
        ("put", "/api/settings", {"site_name": "x"}),
        ("get", "/api/system/backup", None),
        ("get", "/api/users", None),
        ("post", "/api/users", {"username": "bob", "password": "bobpass12"}),
    ]:
        kwargs = {"json": body} if body is not None else {}
        assert getattr(c, method)(url, **kwargs).status_code == 403, url
    # 读取设置（用于默认模型）仍然允许
    assert c.get("/api/settings").status_code == 200


def test_registration_flow(installed):
    c = installed
    assert c.get("/api/site").json()["allow_register"] is False
    c.cookies.clear()
    assert c.post("/api/auth/register", json={"username": "bob", "password": "bobpass12"}).status_code == 403

    login(c, "admin", ADMIN["admin_password"])
    c.put("/api/settings", json={"allow_register": True, "register_need_approval": True})
    c.cookies.clear()
    r = c.post("/api/auth/register", json={"username": "bob", "password": "bobpass12"})
    assert r.json()["status"] == "pending"
    assert c.post("/api/auth/register", json={"username": "bob", "password": "bobpass12"}).status_code == 409
    assert c.post("/api/auth/register", json={"username": "a b", "password": "bobpass12"}).status_code == 422
    r = c.post("/api/auth/login", json={"username": "bob", "password": "bobpass12"})
    assert r.status_code == 403 and "审核" in r.json()["detail"]

    login(c, "admin", ADMIN["admin_password"])
    bob = next(u for u in c.get("/api/users").json() if u["username"] == "bob")
    assert bob["status"] == "pending"
    c.patch(f"/api/users/{bob['id']}", json={"status": "active"})
    c.put("/api/settings", json={"register_need_approval": False})
    c.cookies.clear()
    r = c.post("/api/auth/register", json={"username": "carol", "password": "carolpass1"})
    assert r.json()["status"] == "active"
    assert c.get("/api/auth/me").json()["username"] == "carol"  # 免审核注册后直接登录
    login(c, "bob", "bobpass12")


def test_disable_reset_and_admin_guards(installed):
    c = installed
    alice = make_user(c)
    login(c, "alice", "alicepass1")
    alice_cookie = c.cookies.get("pwd_session")

    login(c, "admin", ADMIN["admin_password"])
    admin_id = c.get("/api/auth/me").json()["id"]
    # 禁用后已登录会话立即失效
    c.patch(f"/api/users/{alice['id']}", json={"status": "disabled"})
    admin_cookie = c.cookies.get("pwd_session")
    c.cookies.set("pwd_session", alice_cookie)
    assert c.get("/api/auth/me").status_code == 401
    c.cookies.set("pwd_session", admin_cookie)
    r = c.post("/api/auth/login", json={"username": "alice", "password": "alicepass1"})
    assert r.status_code == 403
    login(c, "admin", ADMIN["admin_password"])

    # 重置密码
    c.patch(f"/api/users/{alice['id']}", json={"status": "active", "password": "newalice123"})
    login(c, "alice", "newalice123")
    login(c, "admin", ADMIN["admin_password"])

    # 不能降级 / 禁用 / 删除自己，至少保留一个管理员
    assert c.patch(f"/api/users/{admin_id}", json={"role": "user"}).status_code == 400
    assert c.patch(f"/api/users/{admin_id}", json={"status": "disabled"}).status_code == 400
    assert c.delete(f"/api/users/{admin_id}").status_code == 400
    # 提升为管理员后可以降级原管理员
    c.patch(f"/api/users/{alice['id']}", json={"role": "admin"})
    login(c, "alice", "newalice123")
    assert c.patch(f"/api/users/{admin_id}", json={"role": "user"}).status_code == 200


def test_delete_user_removes_data_and_files(installed, monkeypatch):
    from app.config import settings

    c = installed
    alice = make_user(c)
    login(c, "alice", "alicepass1")
    asset = c.post("/api/assets/upload", files={"file": ("a.png", png(), "image/png")}).json()
    c.post("/api/conversations", json={})
    c.post("/api/prompts", json={"title": "alice", "content": "x"})
    path = settings.media_dir / asset["url"].removeprefix("/media/")
    assert path.exists()

    login(c, "admin", ADMIN["admin_password"])
    users = {u["username"]: u for u in c.get("/api/users").json()}
    assert users["alice"]["assets"] == 1 and users["alice"]["conversations"] == 1
    assert c.delete(f"/api/users/{alice['id']}").status_code == 200
    assert not path.exists()
    from app import db
    from app.models import Asset, Conversation, PromptTemplate

    with db.new_session() as s:
        assert s.query(Asset).filter_by(user_id=alice["id"]).count() == 0
        assert s.query(Conversation).filter_by(user_id=alice["id"]).count() == 0
        assert s.query(PromptTemplate).filter_by(user_id=alice["id"]).count() == 0


def test_all_api_routes_require_login(client):
    """除公开接口外，所有 /api 路由在未登录时都必须拒绝访问。"""
    client.post("/api/install", json=ADMIN)
    client.cookies.clear()
    public = {"/api/health", "/api/site", "/api/install/status", "/api/install", "/api/install/test-provider",
              "/api/auth/login", "/api/auth/logout", "/api/auth/register", "/api/openapi.json", "/api/docs",
              "/api/docs/oauth2-redirect"}
    checked = 0
    schema = client.get("/api/openapi.json").json()
    for path, ops in schema["paths"].items():
        if path in public:
            continue
        url = path.replace("{path}", "x.png")
        for key in ("{cid}", "{mid}", "{pid}", "{kind}", "{task_id}", "{asset_id}", "{provider_id}", "{user_id}"):
            url = url.replace(key, "image" if key == "{kind}" else "1")
        for method in ops:
            r = client.request(method.upper(), url, json={})
            assert r.status_code in (401, 403), f"{method} {url} -> {r.status_code}"
            checked += 1
    assert checked > 40


def test_legacy_rows_assigned_to_admin(tmp_path, monkeypatch):
    """模拟 v0.2 数据库：对话 / 作品没有 user_id，迁移后归属第一个管理员。"""
    import sqlite3

    from app import db
    from app.config import settings

    path = tmp_path / "v02.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) UNIQUE, password_hash VARCHAR(255),
            is_admin BOOLEAN, token_version INTEGER, created_at DATETIME);
        INSERT INTO users VALUES (1, 'admin', 'x', 1, 0, '2026-01-01');
        CREATE TABLE conversations (id INTEGER PRIMARY KEY, title VARCHAR(255), provider_id INTEGER, model VARCHAR(255),
            system_prompt TEXT, created_at DATETIME, updated_at DATETIME);
        INSERT INTO conversations (id, title, model, system_prompt) VALUES (1, '旧对话', '', '');
        CREATE TABLE assets (id INTEGER PRIMARY KEY, kind VARCHAR(16), source VARCHAR(16), filename VARCHAR(255),
            mime VARCHAR(64), size INTEGER, prompt TEXT, model VARCHAR(255), favorite BOOLEAN, task_id INTEGER, created_at DATETIME);
        INSERT INTO assets (id, kind, source, filename, mime, size, prompt, model, favorite) VALUES (1, 'image', 'generated', 'a.png', 'image/png', 1, '', '', 0);
    """)
    conn.close()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db.init_engine(f"sqlite:///{path}")
    con = sqlite3.connect(path)
    assert con.execute("SELECT user_id FROM conversations").fetchone()[0] == 1
    assert con.execute("SELECT user_id FROM assets").fetchone()[0] == 1
    assert con.execute("SELECT status FROM users").fetchone()[0] == "active"
