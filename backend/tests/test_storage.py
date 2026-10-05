"""对象存储：SigV4 签名与本地缓存 / 后台上传 / 按需下载。"""
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.services import storage


def test_sigv4_matches_aws_example():
    """AWS 官方文档「GET Object」示例的签名。"""
    headers = storage.sign(
        "GET", "https://examplebucket.s3.amazonaws.com/test.txt", {"range": "bytes=0-9"}, storage.EMPTY_SHA256,
        "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1",
        now=datetime(2013, 5, 24, tzinfo=timezone.utc),
    )
    assert headers["authorization"].endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in headers["authorization"]


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=ak/")
        key = request.url.path
        self.requests.append((request.method, key))
        if request.method == "PUT":
            self.objects[key] = request.content
            return httpx.Response(200)
        if request.method in ("GET", "HEAD"):
            if key not in self.objects:
                return httpx.Response(404)
            return httpx.Response(200, content=self.objects[key] if request.method == "GET" else b"")
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx.Response(204)
        return httpx.Response(405)


def _wait(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_s3_backed_media(installed, monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(storage, "_transport", httpx.MockTransport(fake.handler))
    for k, v in {"s3_endpoint": "http://minio:9000", "s3_bucket": "pwd", "s3_access_key": "ak", "s3_secret_key": "sk",
                 "s3_prefix": "media/", "s3_addressing": "path"}.items():
        monkeypatch.setattr(settings, k, v)
    c = installed
    assert c.get("/api/system/storage").json()["backend"] == "s3"
    a = c.post("/api/assets/upload", files={"file": ("a.txt.png", b"\x89PNG fake", "image/png")}).json()
    key = f"/pwd/media/{a['url'][len('/media/'):]}"
    assert _wait(lambda: key in fake.objects)
    assert fake.objects[key] == b"\x89PNG fake"

    # 本地缓存被清理后，访问时自动从对象存储下载
    local = settings.media_dir / a["url"][len("/media/"):]
    local.unlink()
    assert c.get(a["url"]).content == b"\x89PNG fake"
    assert local.is_file()

    # 过期缓存清理：只清理已确认上传的文件
    import os

    old = time.time() - 30 * 86400
    os.utime(local, (old, old))
    assert storage.evict_cache(7) == 1 and not local.exists()

    # 存量同步与删除
    extra = settings.media_dir / "202001" / "old.png"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"old")
    r = c.post("/api/system/storage/sync").json()
    assert r["uploaded"] == 1 and "/pwd/media/202001/old.png" in fake.objects
    c.delete(f"/api/assets/{a['id']}")
    assert _wait(lambda: key not in fake.objects)
