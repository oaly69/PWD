"""S3 兼容对象存储（可选）。

启用方式：设置环境变量 PWD_S3_ENDPOINT、PWD_S3_BUCKET、PWD_S3_ACCESS_KEY、PWD_S3_SECRET_KEY
（可选 PWD_S3_REGION、PWD_S3_PREFIX、PWD_S3_ADDRESSING=path|virtual、PWD_S3_CACHE_DAYS）。

工作方式：媒体文件先写入本地 media 目录，再在后台上传到对象存储；本地文件作为缓存，
超过 PWD_S3_CACHE_DAYS 天未访问且已确认上传的文件会被清理，之后访问时再从对象存储下载回来。
作品访问仍经过应用鉴权，存储桶无需公开。签名为 AWS Signature V4，不依赖 boto3。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from ..config import settings

log = logging.getLogger("pwd.storage")
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="s3-upload")
_pending: set[str] = set()
_lock = threading.Lock()
_transport: httpx.BaseTransport | None = None  # 测试时注入


def enabled() -> bool:
    return bool(settings.s3_endpoint and settings.s3_bucket)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign(method: str, url: str, headers: dict[str, str], payload_hash: str, access_key: str, secret_key: str,
         region: str, now: datetime | None = None) -> dict[str, str]:
    """返回加上 x-amz-date、x-amz-content-sha256 与 Authorization 的请求头（AWS Signature V4）。"""
    now = now or datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    parsed = urlparse(url)
    out = {k.lower(): str(v).strip() for k, v in headers.items()}
    out["host"] = parsed.netloc
    out["x-amz-date"] = amz_date
    out["x-amz-content-sha256"] = payload_hash
    signed = sorted(out)
    canonical_headers = "".join(f"{k}:{out[k]}\n" for k in signed)
    query = "&".join(sorted(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in
                            (p.split("=", 1) if "=" in p else (p, "") for p in parsed.query.split("&") if p)))
    canonical = "\n".join([method, parsed.path or "/", query, canonical_headers, ";".join(signed), payload_hash])
    scope = f"{datestamp}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), datestamp), region), "s3"), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(signed)}, Signature={signature}"
    )
    return out


def _url(filename: str) -> str:
    key = quote(f"{settings.s3_prefix}{filename}", safe="/-_.~")
    endpoint = urlparse(settings.s3_endpoint)
    if settings.s3_addressing == "virtual":
        return f"{endpoint.scheme}://{settings.s3_bucket}.{endpoint.netloc}/{key}"
    return f"{settings.s3_endpoint}/{quote(settings.s3_bucket)}/{key}"


def _request(method: str, filename: str, body: bytes = b"", headers: dict[str, str] | None = None) -> httpx.Response:
    url = _url(filename)
    payload = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
    signed = sign(method, url, headers or {}, payload, settings.s3_access_key, settings.s3_secret_key, settings.s3_region)
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=300, write=300, pool=10), transport=_transport) as client:
        return client.request(method, url, content=body or None, headers=signed)


def put(filename: str, data: bytes, mime: str = "application/octet-stream") -> None:
    resp = _request("PUT", filename, data, {"content-type": mime})
    if resp.status_code >= 300:
        raise RuntimeError(f"上传到对象存储失败（HTTP {resp.status_code}）：{resp.text[:200]}")


def get(filename: str) -> bytes | None:
    resp = _request("GET", filename)
    if resp.status_code == 404:
        return None
    if resp.status_code >= 300:
        raise RuntimeError(f"从对象存储读取失败（HTTP {resp.status_code}）")
    return resp.content


def exists(filename: str) -> bool:
    return _request("HEAD", filename).status_code == 200


def delete(filename: str) -> None:
    _request("DELETE", filename)


# ---------------------------------------------------------------- 与本地缓存配合


def upload_later(filename: str, path: Path, mime: str) -> None:
    """后台上传（不阻塞请求）。"""
    if not enabled():
        return
    with _lock:
        _pending.add(filename)

    def job() -> None:
        try:
            for attempt in range(3):
                try:
                    put(filename, path.read_bytes(), mime)
                    return
                except Exception as exc:  # noqa: BLE001
                    log.warning("上传 %s 失败（第 %d 次）：%s", filename, attempt + 1, exc)
                    time.sleep(2 * (attempt + 1))
        finally:
            with _lock:
                _pending.discard(filename)

    _pool.submit(job)


def fetch_to(filename: str, path: Path) -> bool:
    """本地缓存缺失时从对象存储下载。"""
    if not enabled():
        return False
    try:
        data = get(filename)
    except Exception as exc:  # noqa: BLE001
        log.warning("下载 %s 失败：%s", filename, exc)
        return False
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def delete_later(filename: str) -> None:
    if enabled():
        _pool.submit(lambda: _safe(delete, filename))


def _safe(fn, *args) -> Any:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        log.warning("对象存储操作失败：%s", exc)
        return None


def evict_cache(max_age_days: float | None = None) -> int:
    """清理超过保留天数、且已确认在对象存储中的本地文件，返回清理数量。"""
    days = settings.s3_cache_days if max_age_days is None else max_age_days
    if not enabled() or days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    root = settings.media_dir
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix == ".part":
            continue
        st = path.stat()
        if max(st.st_atime, st.st_mtime) > cutoff:
            continue
        name = path.relative_to(root).as_posix()
        with _lock:
            if name in _pending:
                continue
        if _safe(exists, name):
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def sync_all() -> dict[str, int]:
    """把本地已有但对象存储中没有的文件全部上传（启用对象存储前的存量数据迁移）。"""
    import mimetypes

    uploaded = skipped = failed = 0
    root = settings.media_dir
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix == ".part":
            continue
        name = path.relative_to(root).as_posix()
        if _safe(exists, name):
            skipped += 1
            continue
        try:
            put(name, path.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream")
            uploaded += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("同步 %s 失败：%s", name, exc)
            failed += 1
    return {"uploaded": uploaded, "skipped": skipped, "failed": failed}


def status() -> dict[str, Any]:
    if not enabled():
        return {"backend": "local"}
    with _lock:
        pending = len(_pending)
    return {
        "backend": "s3", "endpoint": settings.s3_endpoint, "bucket": settings.s3_bucket, "prefix": settings.s3_prefix,
        "region": settings.s3_region, "cache_days": settings.s3_cache_days, "pending_uploads": pending,
    }
