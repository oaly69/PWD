"""OIDC 单点登录客户端（授权码模式）。

身份信息通过 userinfo 接口获取（令牌直接由 token 接口经 HTTPS 返回，无需本地校验 id_token 签名）。
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx

from .openai_compat import ProviderError

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
TIMEOUT = httpx.Timeout(15.0)


async def discover(issuer: str) -> dict[str, Any]:
    issuer = issuer.rstrip("/")
    hit = _cache.get(issuer)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        r = await client.get(f"{issuer}/.well-known/openid-configuration")
    if r.status_code >= 400:
        raise ProviderError(f"获取 OIDC 配置失败（HTTP {r.status_code}），请检查 Issuer 地址")
    conf = r.json()
    for key in ("authorization_endpoint", "token_endpoint"):
        if not conf.get(key):
            raise ProviderError(f"OIDC 配置缺少 {key}")
    _cache[issuer] = (time.time(), conf)
    return conf


def authorize_url(conf: dict[str, Any], client_id: str, redirect_uri: str, state: str, scopes: str, nonce: str) -> str:
    query = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes or "openid profile email",
        "state": state,
        "nonce": nonce,
    })
    sep = "&" if "?" in conf["authorization_endpoint"] else "?"
    return f"{conf['authorization_endpoint']}{sep}{query}"


async def exchange(conf: dict[str, Any], code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict[str, Any]:
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client_id}
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(conf["token_endpoint"], data=data, headers={"Accept": "application/json"})
    if r.status_code >= 400:
        raise ProviderError(f"换取令牌失败（HTTP {r.status_code}）：{r.text[:200]}")
    return r.json()


async def userinfo(conf: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    endpoint = conf.get("userinfo_endpoint")
    if not endpoint or not tokens.get("access_token"):
        raise ProviderError("OIDC 服务未提供 userinfo 接口")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(endpoint, headers={"Authorization": f"Bearer {tokens['access_token']}"})
    if r.status_code >= 400:
        raise ProviderError(f"获取用户信息失败（HTTP {r.status_code}）")
    info = r.json()
    if not info.get("sub"):
        raise ProviderError("用户信息缺少 sub")
    return info
