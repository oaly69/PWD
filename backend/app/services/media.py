"""媒体文件读写：保存生成结果、读取作品、生成缩略图。"""
from __future__ import annotations

import base64
import io
import logging
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from ..config import settings

log = logging.getLogger("pwd.media")

THUMB_SIZE = 512

_EXT_FIX = {".jpe": ".jpg", ".jpeg": ".jpg"}


# 部分系统的 mimetypes 不认识这些类型，显式指定扩展名
_MIME_EXT = {
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
    "audio/ogg": ".ogg", "audio/opus": ".opus", "audio/aac": ".aac", "audio/flac": ".flac", "audio/webm": ".webm",
    "audio/mp4": ".m4a", "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov", "image/webp": ".webp",
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
}


def _ext(mime: str) -> str:
    mime = (mime or "").split(";")[0].strip().lower()
    ext = _MIME_EXT.get(mime) or mimetypes.guess_extension(mime) or ".bin"
    return _EXT_FIX.get(ext, ext)


def media_path(filename: str) -> Path:
    root = settings.media_dir.resolve()
    target = (root / filename).resolve()
    if not target.is_relative_to(root):
        raise ValueError("非法路径")
    return target


def local_media(filename: str) -> Path:
    """返回本地文件路径；启用对象存储且本地缓存缺失时先从对象存储下载。"""
    path = media_path(filename)
    if not path.is_file():
        from . import storage

        storage.fetch_to(filename, path)
    return path


def thumbs_dir() -> Path:
    return settings.data_dir / "thumbs"


def image_size(data: bytes) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return img.size
    except Exception:  # noqa: BLE001 - 非图片或损坏
        return 0, 0


def save_media(data: bytes, mime: str) -> str:
    """保存文件到 media 目录，返回相对文件名（按月份分目录）。"""
    sub = datetime.now().strftime("%Y%m")
    folder = settings.media_dir / sub
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{_ext(mime)}"
    (folder / name).write_bytes(data)
    from . import storage

    storage.upload_later(f"{sub}/{name}", folder / name, mime)
    return f"{sub}/{name}"


def delete_media(filename: str) -> None:
    for path in (media_path(filename), thumb_path(filename)):
        try:
            if path.is_file():
                path.unlink()
        except (OSError, ValueError):
            pass
    from . import storage

    storage.delete_later(filename)


def thumb_path(filename: str) -> Path:
    root = thumbs_dir().resolve()
    target = (root / f"{filename}.webp").resolve()
    if not target.is_relative_to(root):
        raise ValueError("非法路径")
    return target


def ensure_thumb(filename: str) -> Path | None:
    """返回缩略图路径，不存在时即时生成；非图片返回 None。"""
    target = thumb_path(filename)
    if target.is_file():
        return target
    src = local_media(filename)
    if not src.is_file():
        return None
    try:
        from PIL import Image, ImageOps

        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((THUMB_SIZE, THUMB_SIZE * 2))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            target.parent.mkdir(parents=True, exist_ok=True)
            img.save(target, "WEBP", quality=82)
        return target
    except Exception as exc:  # noqa: BLE001
        log.debug("生成缩略图失败 %s: %s", filename, exc)
        return None


def read_media(filename: str) -> bytes:
    return local_media(filename).read_bytes()


def to_data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def downscale_for_llm(data: bytes, mime: str, max_side: int = 1536) -> tuple[bytes, str]:
    """发送给多模态模型前压缩过大的图片，减少请求体积。"""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            if max(img.size) <= max_side and len(data) < 3 * 1024 * 1024:
                return data, mime
            img.thumbnail((max_side, max_side))
            out = io.BytesIO()
            img.convert("RGB").save(out, "JPEG", quality=88)
            return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001
        return data, mime
