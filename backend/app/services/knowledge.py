"""知识库：文档入库（提取 → 切分 → 向量化）与检索。

配置了向量模型时使用向量相似度检索；否则使用基于字词重叠的关键词检索（无需任何模型）。
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
from collections import Counter
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from ..db import new_session
from ..models import KbChunk, KbDocument, KnowledgeBase, Provider
from . import openai_compat
from .documents import extract_text, split_text

log = logging.getLogger("pwd.knowledge")
_sem = asyncio.Semaphore(2)
_jobs: set[asyncio.Task] = set()


def _tokens(text: str) -> list[str]:
    """英文按单词、中文按相邻二字切分，用于关键词检索。"""
    text = text.lower()
    words = re.findall(r"[a-z0-9_]{2,}", text)
    cjk = re.findall(r"[一-鿿]+", text)
    grams = [seg[i:i + 2] for seg in cjk for i in range(max(1, len(seg) - 1))]
    return words + grams


def _vec(blob: bytes | None) -> np.ndarray | None:
    return np.frombuffer(blob, dtype=np.float32) if blob else None


def submit_document(doc_id: int, data: bytes) -> None:
    task = asyncio.get_running_loop().create_task(_index(doc_id, data))
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)


async def _index(doc_id: int, data: bytes) -> None:
    async with _sem:
        with new_session() as db:
            doc = db.get(KbDocument, doc_id)
            if doc is None:
                return
            kb = db.get(KnowledgeBase, doc.kb_id)
            try:
                doc.status = "processing"
                db.commit()
                text = await asyncio.to_thread(extract_text, doc.filename, data)
                chunks = split_text(text)
                vectors: list[list[float]] | None = None
                provider = db.get(Provider, kb.embedding_provider_id) if kb and kb.embedding_provider_id else None
                if provider is not None and kb.embedding_model:
                    vectors = await openai_compat.embeddings(provider, kb.embedding_model, [f"{doc.filename}\n{c}" for c in chunks])
                db.query(KbChunk).filter(KbChunk.doc_id == doc.id).delete()
                for i, chunk in enumerate(chunks):
                    emb = np.asarray(vectors[i], dtype=np.float32).tobytes() if vectors else None
                    db.add(KbChunk(kb_id=doc.kb_id, doc_id=doc.id, idx=i, text=chunk, embedding=emb))
                doc.chars = len(text)
                doc.chunk_count = len(chunks)
                doc.status = "ready"
                doc.error = ""
            except Exception as exc:  # noqa: BLE001
                log.warning("文档 %s 入库失败：%s", doc_id, exc)
                doc.status = "failed"
                doc.error = str(exc) or exc.__class__.__name__
            db.commit()


async def search(db: Session, kb_ids: list[int], query: str, top_k: int = 6) -> list[dict[str, Any]]:
    """在多个知识库中检索，返回按相关度排序的片段。"""
    results: list[dict[str, Any]] = []
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all() if kb_ids else []
    q_tokens = Counter(_tokens(query))
    for kb in kbs:
        rows = (
            db.query(KbChunk, KbDocument.filename)
            .join(KbDocument, KbDocument.id == KbChunk.doc_id)
            .filter(KbChunk.kb_id == kb.id, KbDocument.status == "ready")
            .all()
        )
        if not rows:
            continue
        provider = db.get(Provider, kb.embedding_provider_id) if kb.embedding_provider_id else None
        scored: list[tuple[float, Any, str]] = []
        if provider is not None and kb.embedding_model and rows[0][0].embedding:
            qv = np.asarray((await openai_compat.embeddings(provider, kb.embedding_model, [query]))[0], dtype=np.float32)
            mat = np.stack([_vec(c.embedding) for c, _ in rows])
            sims = mat @ qv / (np.linalg.norm(mat, axis=1) * (np.linalg.norm(qv) or 1) + 1e-8)
            scored = [(float(sims[i]), c, fn) for i, (c, fn) in enumerate(rows)]
            scored = [x for x in scored if x[0] >= 0.2]
        else:
            # 关键词检索：简化的 BM25
            n = len(rows)
            docs_tokens = [Counter(_tokens(c.text)) for c, _ in rows]
            df: Counter = Counter()
            for toks in docs_tokens:
                df.update(set(toks))
            avg = sum(sum(t.values()) for t in docs_tokens) / n or 1
            for (c, fn), toks in zip(rows, docs_tokens):
                length = sum(toks.values()) or 1
                score = 0.0
                for term in q_tokens:
                    tf = toks.get(term, 0)
                    if not tf:
                        continue
                    idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                    score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
                if score > 0:
                    scored.append((score, c, fn))
            top = max((s for s, _, _ in scored), default=0) or 1
            scored = [(s / top * 0.9, c, fn) for s, c, fn in scored]  # 归一化，便于与向量结果合并
        for score, c, fn in scored:
            results.append({
                "kb_id": kb.id, "kb_name": kb.name, "doc_id": c.doc_id, "filename": fn, "idx": c.idx,
                "text": c.text, "score": round(score, 4),
            })
    results.sort(key=lambda r: -r["score"])
    return results[:top_k]


def format_context(results: list[dict[str, Any]], start: int = 1) -> str:
    return "\n\n".join(f"[{i}] 来源：{r['filename']}\n{r['text']}" for i, r in enumerate(results, start))
