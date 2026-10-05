"""文档文本提取与切分。支持 txt / md / csv / json / html / pdf / docx / pptx / xlsx 等常见格式。"""
from __future__ import annotations

import html
import io
import json
import re
import zipfile
from xml.etree import ElementTree

from .openai_compat import ProviderError

MAX_CHARS = 2_000_000  # 单个文档最多提取的字符数
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp",
            ".h", ".sql", ".yaml", ".yml", ".toml", ".ini", ".xml", ".srt", ".vtt", ".tex", ".rst", ".sh", ".css", ".vue"}
SUPPORTED = sorted(TEXT_EXT | {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".json", ".epub"})


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def _xml_text(xml: bytes, para_tag: str) -> str:
    """提取 OOXML 中的文字：按段落标签换行。"""
    root = ElementTree.fromstring(xml)
    out: list[str] = []
    for para in root.iter():
        if para.tag.endswith(para_tag):
            out.append("".join(t.text or "" for t in para.iter() if t.tag.endswith("}t")))
    return "\n".join(x for x in out if x.strip())


def _docx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return _xml_text(z.read("word/document.xml"), "}p")


def _pptx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        slides = sorted(
            (n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
            key=lambda n: int(re.findall(r"\d+", n)[-1]),
        )
        return "\n\n".join(f"## 第 {i + 1} 页\n{_xml_text(z.read(n), '}p')}" for i, n in enumerate(slides))


def _xlsx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter() if t.tag.endswith("}t")) for si in root if si.tag.endswith("}si")]
        lines: list[str] = []
        for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
            root = ElementTree.fromstring(z.read(name))
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                cells = []
                for c in row:
                    v = next((x.text for x in c.iter() if x.tag.endswith("}v") or x.tag.endswith("}t")), "") or ""
                    if c.get("t") == "s" and v.isdigit() and int(v) < len(shared):
                        v = shared[int(v)]
                    cells.append(v)
                if any(cells):
                    lines.append(" | ".join(cells))
        return "\n".join(lines)


def _epub(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        parts = [n for n in z.namelist() if n.endswith((".xhtml", ".html", ".htm"))]
        return "\n\n".join(_strip_html(_decode(z.read(n))) for n in sorted(parts))


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - 个别页面解析失败时跳过
            pages.append("")
        if sum(len(p) for p in pages) > MAX_CHARS:
            break
    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        raise ProviderError("PDF 中没有可提取的文字（可能是扫描件，需要先 OCR）")
    return text


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    ext = name[name.rfind("."):] if "." in name else ""
    try:
        if ext == ".pdf":
            text = _pdf(data)
        elif ext == ".docx":
            text = _docx(data)
        elif ext == ".pptx":
            text = _pptx(data)
        elif ext == ".xlsx":
            text = _xlsx(data)
        elif ext == ".epub":
            text = _epub(data)
        elif ext in (".html", ".htm"):
            text = _strip_html(_decode(data))
        elif ext == ".json":
            raw = _decode(data)
            try:
                text = json.dumps(json.loads(raw), ensure_ascii=False, indent=1)
            except ValueError:
                text = raw
        elif ext in TEXT_EXT or not ext:
            text = _decode(data)
        else:
            raise ProviderError(f"暂不支持 {ext} 格式，支持：{'、'.join(SUPPORTED)}")
    except ProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"解析文档失败：{exc}") from exc
    text = re.sub(r"[ \t　]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    if not text:
        raise ProviderError("文档中没有可提取的文字")
    return text[:MAX_CHARS]


def split_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """按段落合并成约 size 字符的片段，过长段落按句子再切，片段之间保留少量重叠。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        if len(p) <= size:
            pieces.append(p)
            continue
        sentences = re.split(r"(?<=[。！？!?；;.\n])", p)
        buf = ""
        for s in sentences:
            while len(s) > size:  # 没有标点的超长内容硬切
                pieces.append((buf + s[: size - len(buf)]).strip())
                s, buf = s[size - len(buf):], ""
            if len(buf) + len(s) > size and buf:
                pieces.append(buf.strip())
                buf = ""
            buf += s
        if buf.strip():
            pieces.append(buf.strip())
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if buf and len(buf) + len(piece) + 2 > size:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = f"{tail}\n{piece}" if tail else piece
        else:
            buf = f"{buf}\n\n{piece}" if buf else piece
    if buf.strip():
        chunks.append(buf)
    return chunks
