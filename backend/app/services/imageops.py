"""图像编辑的本地预处理：蒙版、扩图画布、本地放大。

蒙版约定：前端提交的蒙版为与原图同尺寸的灰度图，白色 = 需要重绘的区域。
不同后端需要的格式不同：
  - OpenAI /images/edits：RGBA 蒙版，透明（alpha=0）处为重绘区域
  - ComfyUI LoadImage：MASK 输出 = 1 - alpha，因此把原图重绘区域设为透明即可；
    同时提供白色=重绘区域的独立蒙版图，供 LoadImageMask 节点使用
"""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageFilter, ImageOps

from .openai_compat import ProviderError

MAX_SIDE = 8192
OVERLAP = 24  # 扩图时向原图内部延伸的重绘带宽度，让接缝更自然


def _open(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ProviderError("无法读取图片") from exc
    return ImageOps.exif_transpose(img)


def _png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def decode_data_uri(uri: str) -> bytes:
    if not uri.startswith("data:") or "," not in uri:
        raise ProviderError("蒙版格式错误")
    try:
        return base64.b64decode(uri.split(",", 1)[1])
    except ValueError as exc:
        raise ProviderError("蒙版格式错误") from exc


def normalize_mask(mask_data: bytes, size: tuple[int, int]) -> Image.Image:
    """转成与原图同尺寸的二值灰度蒙版（白 = 重绘）。透明背景的画笔图层同样适用。"""
    m = _open(mask_data)
    if m.mode in ("RGBA", "LA") or "transparency" in m.info:
        m = m.convert("RGBA").getchannel("A")
    else:
        m = m.convert("L")
    if m.size != size:
        m = m.resize(size, Image.Resampling.NEAREST)
    m = m.point(lambda v: 255 if v >= 128 else 0)
    if not m.getbbox():
        raise ProviderError("蒙版为空，请先涂抹需要重绘的区域")
    return m


def prepare_inpaint(image_data: bytes, mask: Image.Image) -> dict[str, bytes]:
    """返回各后端需要的图片：image（原图 PNG）、image_alpha（重绘区透明）、mask（白=重绘）、openai_mask。"""
    img = _open(image_data).convert("RGBA")
    inv = ImageOps.invert(mask)
    alpha_img = img.copy()
    alpha_img.putalpha(inv)
    openai_mask = Image.new("RGBA", img.size, (0, 0, 0, 255))
    openai_mask.putalpha(inv)
    return {
        "image": _png(img.convert("RGB")),
        "image_alpha": _png(alpha_img),
        "mask": _png(mask),
        "openai_mask": _png(openai_mask),
    }


def outpaint_canvas(image_data: bytes, left: int, top: int, right: int, bottom: int) -> tuple[bytes, Image.Image]:
    """把原图放到扩展后的画布上，返回（画布 PNG，蒙版）。扩展区用边缘像素拉伸填充，比纯色更利于模型衔接。"""
    img = _open(image_data).convert("RGB")
    w, h = img.size
    nw, nh = w + left + right, h + top + bottom
    if nw == w and nh == h:
        raise ProviderError("请设置扩展的方向和大小")
    if max(nw, nh) > MAX_SIDE:
        raise ProviderError(f"扩图后尺寸不能超过 {MAX_SIDE} 像素")
    canvas = img.resize((nw, nh), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(32))
    canvas.paste(img, (left, top))
    mask = Image.new("L", (nw, nh), 255)
    keep = (
        left + (OVERLAP if left else 0),
        top + (OVERLAP if top else 0),
        left + w - (OVERLAP if right else 0),
        top + h - (OVERLAP if bottom else 0),
    )
    mask.paste(0, keep)
    return _png(canvas), mask


def upscale_local(image_data: bytes, scale: float) -> bytes:
    """本地放大（Lanczos + 轻度锐化）。不依赖模型，速度快，适合快速得到大尺寸图片。"""
    img = _open(image_data)
    w, h = img.size
    nw, nh = round(w * scale), round(h * scale)
    if max(nw, nh) > MAX_SIDE:
        raise ProviderError(f"放大后尺寸不能超过 {MAX_SIDE} 像素")
    mode = "RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB"
    out = img.convert(mode).resize((nw, nh), Image.Resampling.LANCZOS)
    out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    return _png(out)


def prepare_png(image_data: bytes) -> bytes:
    """统一转成 PNG（部分编辑接口只接受 PNG）。"""
    return _png(_open(image_data).convert("RGBA"))


def image_dims(image_data: bytes) -> tuple[int, int]:
    return _open(image_data).size
