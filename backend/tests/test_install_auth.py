from app.config import settings

from .conftest import ADMIN


def test_status_before_install(client):
    r = client.get("/api/install/status")
    assert r.json()["installed"] is False
    # 未安装时业务接口返回 409
    assert client.get("/api/providers").status_code == 409


def test_install_sets_defaults_and_logs_in(installed):
    c = installed
    assert c.get("/api/install/status").json()["installed"] is True
    assert c.get("/api/auth/me").json()["username"] == "admin"
    s = c.get("/api/settings").json()
    assert s["site_name"] == "测试站"
    assert s["default_chat_model"] == "chat-model"
    assert s["default_image_model"] == "image-model"
    providers = c.get("/api/providers").json()
    assert providers[0]["api_key_masked"] == "sk-****3456"
    assert "api_key" not in providers[0]


def test_cannot_install_twice(installed):
    r = installed.post("/api/install", json=ADMIN)
    assert r.status_code == 409


def test_install_token_required(client, monkeypatch):
    monkeypatch.setattr(settings, "install_token", "secret-token")
    assert client.get("/api/install/status").json()["need_token"] is True
    assert client.post("/api/install", json=ADMIN).status_code == 403
    r = client.post("/api/install", json={**ADMIN, "install_token": "secret-token"})
    assert r.status_code == 200


def test_login_logout_and_password(installed):
    c = installed
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "password123"}).status_code == 200
    old_cookie = c.cookies.get("pwd_session")
    r = c.post("/api/auth/password", json={"old_password": "password123", "new_password": "newpassword1"})
    assert r.status_code == 200
    # 修改密码后旧会话失效
    c.cookies.set("pwd_session", old_cookie)
    assert c.get("/api/auth/me").status_code == 401


def test_settings_reject_unknown_keys(installed):
    assert installed.put("/api/settings", json={"installed": False}).status_code == 422
    r = installed.put("/api/settings", json={"site_name": "新名字"})
    assert r.json()["site_name"] == "新名字"
    assert installed.get("/api/site").json()["site_name"] == "新名字"
