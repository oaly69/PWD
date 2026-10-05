"""v0.6：知识库、文档对话、联网搜索、工具调用、MCP、语音识别。"""
import io
import json
import time
import zipfile

from app.services import documents, mcp, openai_compat, websearch


def _events(text):
    return [json.loads(line[5:]) for line in text.splitlines() if line.startswith("data:")]


def _docx(paragraphs):
    body = "".join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def _pdf(text):
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref))
    return out.getvalue()


def test_extract_formats():
    assert "第二段" in documents.extract_text("a.docx", _docx(["第一段", "第二段"]))
    assert "Hello PDF" in documents.extract_text("a.pdf", _pdf("Hello PDF"))
    assert documents.extract_text("a.html", "<p>你好</p><script>x()</script>".encode()) == "你好"
    assert documents.extract_text("a.txt", "中文 GBK".encode("gb18030")) == "中文 GBK"
    try:
        documents.extract_text("a.exe", b"x")
        raise AssertionError
    except openai_compat.ProviderError:
        pass


def _wait_docs(c, kid):
    for _ in range(100):
        docs = c.get(f"/api/kb/{kid}/documents").json()
        if all(d["status"] in ("ready", "failed") for d in docs):
            return docs
        time.sleep(0.05)
    raise AssertionError("doc timeout")


DOC = "PWD 是一个个人 AIGC 创作平台。\n\n它支持图像生成、视频生成和语音合成。\n\n部署方式是 Docker，镜像发布在 GHCR。"


def test_kb_keyword_and_chat_rag(installed, monkeypatch):
    c = installed
    kb = c.post("/api/kb", json={"name": "产品手册"}).json()
    r = c.post(f"/api/kb/{kb['id']}/documents", files={"file": ("手册.md", DOC.encode(), "text/markdown")})
    assert r.status_code == 200
    docs = _wait_docs(c, kb["id"])
    assert docs[0]["status"] == "ready" and docs[0]["chunk_count"] >= 1
    hits = c.post(f"/api/kb/{kb['id']}/search", json={"query": "怎么部署 Docker"}).json()
    assert hits and "Docker" in hits[0]["text"]
    assert c.get("/api/kb").json()[0]["documents"] == 1

    seen = {}

    async def fake_stream(provider, model, messages, params):
        seen["messages"] = messages
        yield "content", "用 Docker 部署 [1]"

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    cid = c.post("/api/conversations", json={"params": {"kb_ids": [kb["id"]]}}).json()["id"]
    ev = _events(c.post(f"/api/conversations/{cid}/messages", json={"content": "如何部署 Docker？"}).text)
    assert any(e.get("status") == "searching" for e in ev)
    src = next(e for e in ev if "sources" in e)["sources"]
    assert src[0]["type"] == "kb" and src[0]["title"] == "手册.md"
    ctx = seen["messages"][-2]
    assert ctx["role"] == "system" and "参考资料" in ctx["content"] and "GHCR" in ctx["content"]
    assert seen["messages"][-1]["content"] == "如何部署 Docker？"
    msg = c.get(f"/api/conversations/{cid}").json()["messages"][-1]
    assert msg["sources"][0]["title"] == "手册.md"

    # 别人的知识库不可见、不可用
    c.post("/api/users", json={"username": "bob", "password": "password123"})
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    assert c.get("/api/kb").json() == []
    assert c.get(f"/api/kb/{kb['id']}/documents").status_code == 404
    cid2 = c.post("/api/conversations", json={"params": {"kb_ids": [kb["id"]]}}).json()["id"]
    ev = _events(c.post(f"/api/conversations/{cid2}/messages", json={"content": "如何部署 Docker？"}).text)
    assert not any("sources" in e for e in ev)


def test_kb_vector_search(installed, monkeypatch):
    def vec(text):
        v = [0.0] * 8
        for i, key in enumerate(["部署", "Docker", "图像", "视频", "语音", "平台", "GHCR", "创作"]):
            v[i] = float(text.count(key))
        return v or [0.0] * 8

    async def fake_embed(provider, model, texts, batch=32):
        return [vec(t) for t in texts]

    monkeypatch.setattr(openai_compat, "embeddings", fake_embed)
    c = installed
    p = c.get("/api/providers").json()[0]
    c.put(f"/api/providers/{p['id']}", json={**p, "api_key": None, "embedding_models": ["embed-1"]})
    assert c.post("/api/kb", json={"name": "x", "embedding_provider_id": p["id"], "embedding_model": "nope"}).status_code == 400
    kb = c.post("/api/kb", json={"name": "向量库", "embedding_provider_id": p["id"], "embedding_model": "embed-1"}).json()
    long_doc = "\n\n".join(["图像生成 视频生成 语音合成" * 30, "Docker 部署 GHCR 镜像" * 30])
    c.post(f"/api/kb/{kb['id']}/documents", files={"file": ("a.txt", long_doc.encode(), "text/plain")})
    assert _wait_docs(c, kb["id"])[0]["status"] == "ready"
    hits = c.post(f"/api/kb/{kb['id']}/search", json={"query": "Docker 部署"}).json()
    assert "Docker" in hits[0]["text"] and hits[0]["score"] > 0.5
    # 已有文档时不能更换向量模型
    r = c.patch(f"/api/kb/{kb['id']}", json={"name": "向量库", "embedding_provider_id": None})
    assert r.status_code == 400


def test_chat_with_file_and_web_search(installed, monkeypatch):
    seen = {}

    async def fake_stream(provider, model, messages, params):
        seen["messages"] = messages
        yield "content", "好的"

    async def fake_search(db, query, limit=None):
        seen["query"] = query
        return [{"title": "新闻", "url": "https://example.com/a", "snippet": "今天的新闻"}]

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    monkeypatch.setattr(websearch, "search", fake_search)
    c = installed
    r = c.post("/api/files/extract", files={"file": ("报告.docx", _docx(["季度收入增长 20%"]), "application/octet-stream")})
    f = r.json()
    assert f["name"] == "报告.docx" and "增长" in f["text"]
    cid = c.post("/api/conversations", json={"params": {"web_search": True}}).json()["id"]
    # 未配置搜索引擎时忽略联网开关
    c.post(f"/api/conversations/{cid}/messages", json={"content": "总结一下", "files": [{"name": f["name"], "text": f["text"]}]})
    user_msg = seen["messages"][-1]["content"]
    assert user_msg.startswith('<file name="报告.docx">') and user_msg.endswith("总结一下")
    assert "query" not in seen
    path = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert path[0]["files"] == [{"name": "报告.docx", "chars": len(f["text"])}] and "text" not in path[0]["files"][0]

    c.put("/api/settings", json={"search_engine": "searxng", "search_url": "http://searx:8080"})
    assert c.get("/api/settings").json()["search_available"] is True
    ev = _events(c.post(f"/api/conversations/{cid}/messages", json={"content": "今天有什么新闻"}).text)
    assert seen["query"] == "今天有什么新闻"
    assert next(e for e in ev if "sources" in e)["sources"][0]["url"] == "https://example.com/a"
    # 历史中的文档在后续轮次仍然带上
    assert seen["messages"][0]["content"].startswith('<file name="报告.docx">')


def test_tool_calling_generate_image(installed, monkeypatch):
    import base64

    rounds = []

    async def fake_stream(provider, model, messages, params, tools=None):
        rounds.append({"tools": [t["function"]["name"] for t in tools or []], "last": messages[-1]})
        if len(rounds) == 1:
            yield "content", "好的，我来画。"
            yield "tool_calls", [{"id": "call_1", "type": "function", "function": {"name": "generate_image", "arguments": json.dumps({"prompt": "一只猫"})}}]
        else:
            yield "content", "画好了！"

    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

    async def fake_gen(provider, model, prompt, params, refs=None):
        return [(png, "image/png")]

    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    monkeypatch.setattr(openai_compat, "generate_images", fake_gen)
    c = installed
    catalog = c.get("/api/tools").json()
    assert {t["id"] for t in catalog} >= {"generate_image", "knowledge_search"} and "web_search" not in {t["id"] for t in catalog}
    cid = c.post("/api/conversations", json={"params": {"tools": ["generate_image"]}}).json()["id"]
    ev = _events(c.post(f"/api/conversations/{cid}/messages", json={"content": "画一只猫"}).text)
    assert any(e.get("tool", {}).get("name") == "generate_image" for e in ev)
    done = next(e for e in ev if "tool_done" in e)["tool_done"]
    assert len(done["assets"]) == 1
    assert rounds[0]["tools"] == ["generate_image"]
    assert rounds[1]["last"]["role"] == "tool" and "已生成 1 张图片" in rounds[1]["last"]["content"]
    msg = c.get(f"/api/conversations/{cid}").json()["messages"][-1]
    assert msg["content"] == "好的，我来画。\n\n画好了！"
    assert msg["tools"][0]["name"] == "generate_image" and msg["tools"][0]["assets"][0]["kind"] == "image"


def test_mcp_tools(installed, monkeypatch):
    calls = []

    async def fake_list(server, use_cache=True):
        return [{"name": "get_weather", "description": "查询天气", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}}}]

    async def fake_call(server, name, arguments):
        calls.append((server["id"], name, arguments))
        return "晴，25 度"

    async def fake_stream(provider, model, messages, params, tools=None):
        if messages[-1]["role"] == "user":
            yield "tool_calls", [{"id": "c1", "type": "function", "function": {"name": tools[0]["function"]["name"], "arguments": '{"city": "杭州"}'}}]
        else:
            yield "content", f"天气：{messages[-1]['content']}"

    monkeypatch.setattr(mcp, "list_tools", fake_list)
    monkeypatch.setattr(mcp, "call_tool", fake_call)
    monkeypatch.setattr(openai_compat, "chat_stream", fake_stream)
    c = installed
    c.put("/api/settings", json={"mcp_servers": [{"id": "wx", "name": "天气", "url": "http://mcp/wx", "headers": {"Authorization": "Bearer x"}, "enabled": True}]})
    assert c.post("/api/tools/mcp/test", json={"url": "http://mcp/wx"}).json()["ok"]
    ids = [t["id"] for t in c.get("/api/tools").json()]
    assert "mcp:wx:get_weather" in ids
    cid = c.post("/api/conversations", json={"params": {"tools": ["mcp:wx:get_weather"]}}).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"content": "杭州天气"})
    assert calls == [("wx", "get_weather", {"city": "杭州"})]
    assert c.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"] == "天气：晴，25 度"
    # 普通用户读不到 MCP 配置（含请求头）
    c.post("/api/users", json={"username": "bob", "password": "password123"})
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    s = c.get("/api/settings").json()
    assert "mcp_servers" not in s and "search_api_key" not in s and "oidc_issuer" not in s
    assert c.post("/api/tools/mcp/test", json={"url": "http://mcp/wx"}).status_code == 403


def test_mcp_sse_parse():
    import httpx

    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
    resp = httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)
    assert mcp._parse(resp, 1)["result"] == {"tools": []}


def test_transcribe(installed, monkeypatch):
    async def fake_tr(provider, model, data, filename, mime, language=None):
        assert data == b"audio" and model == "whisper-1"
        return "你好世界"

    monkeypatch.setattr(openai_compat, "transcribe", fake_tr)
    c = installed
    files = {"file": ("a.webm", b"audio", "audio/webm")}
    assert c.post("/api/audio/transcribe", files=files).status_code == 400
    p = c.get("/api/providers").json()[0]
    c.put("/api/settings", json={"stt_provider_id": p["id"], "stt_model": "whisper-1"})
    assert c.get("/api/settings").json()["stt_available"] is True
    assert c.post("/api/audio/transcribe", files=files).json()["text"] == "你好世界"
