"""联网搜索：SearXNG（自建，免费）、Tavily、博查（国内可用）。"""
from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..site import get_setting
from .openai_compat import ProviderError

TIMEOUT = httpx.Timeout(20.0)
ENGINES = {"searxng": "SearXNG", "tavily": "Tavily", "bocha": "博查"}


def configured(db: Session) -> bool:
    engine = get_setting(db, "search_engine")
    if engine == "searxng":
        return bool(get_setting(db, "search_url"))
    return engine in ENGINES and bool(get_setting(db, "search_api_key"))


async def search(db: Session, query: str, limit: int | None = None) -> list[dict[str, Any]]:
    engine = get_setting(db, "search_engine")
    url = (get_setting(db, "search_url") or "").rstrip("/")
    key = get_setting(db, "search_api_key") or ""
    limit = int(limit or get_setting(db, "search_max_results") or 5)
    query = query.strip()[:400]
    if not query:
        return []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        if engine == "searxng":
            if not url:
                raise ProviderError("未配置 SearXNG 地址")
            r = await client.get(f"{url}/search", params={"q": query, "format": "json"}, headers={"Accept": "application/json"})
            if r.status_code >= 400:
                raise ProviderError(f"SearXNG 搜索失败（HTTP {r.status_code}），请确认已在 settings.yml 中启用 json 格式")
            items = [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("content", "")} for i in r.json().get("results", [])]
        elif engine == "tavily":
            r = await client.post(
                url or "https://api.tavily.com/search", headers={"Authorization": f"Bearer {key}"},
                json={"query": query, "max_results": limit, "search_depth": "basic"},
            )
            if r.status_code >= 400:
                raise ProviderError(f"Tavily 搜索失败（HTTP {r.status_code}）：{r.text[:200]}")
            items = [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("content", "")} for i in r.json().get("results", [])]
        elif engine == "bocha":
            r = await client.post(
                url or "https://api.bochaai.com/v1/web-search", headers={"Authorization": f"Bearer {key}"},
                json={"query": query, "count": limit, "summary": True},
            )
            if r.status_code >= 400:
                raise ProviderError(f"博查搜索失败（HTTP {r.status_code}）：{r.text[:200]}")
            pages = ((r.json().get("data") or {}).get("webPages") or {}).get("value") or []
            items = [{"title": i.get("name", ""), "url": i.get("url", ""), "snippet": i.get("summary") or i.get("snippet", "")} for i in pages]
        else:
            raise ProviderError("管理员尚未配置联网搜索")
    return [i for i in items if i["url"]][:limit]


def format_context(results: list[dict[str, Any]], start: int = 1) -> str:
    return "\n\n".join(f"[{i}] {r['title']}（{r['url']}）\n{r['snippet']}" for i, r in enumerate(results, start))
