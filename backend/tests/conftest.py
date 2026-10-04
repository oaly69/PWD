import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="pwd-test-")
os.environ["PWD_DATA_DIR"] = _TMP
os.environ.pop("PWD_INSTALL_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "install_token", "")
    db.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


ADMIN = {"admin_username": "admin", "admin_password": "password123"}


@pytest.fixture()
def installed(client):
    r = client.post("/api/install", json={**ADMIN, "site_name": "测试站", "provider": {
        "name": "Mock", "kind": "openai", "base_url": "http://mock/v1", "api_key": "sk-test-123456",
        "chat_models": ["chat-model"], "image_models": ["image-model"],
    }})
    assert r.status_code == 200, r.text
    return client
