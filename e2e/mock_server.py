"""端到端测试用的模拟模型服务：OpenAI 兼容接口（对话 / 图像 / 视频 / 语音 / 向量 / 语音识别）、
SearXNG 搜索与 MCP 工具服务。返回固定或随机生成的内容，不依赖任何外部服务。"""
import asyncio, base64, io, json, math, random, shutil, subprocess
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image, ImageDraw, ImageFilter

app = FastAPI()
JOBS = {}

def art(w, h, seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    c1 = [rnd.randint(40, 255) for _ in range(3)]; c2 = [rnd.randint(0, 200) for _ in range(3)]
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    for _ in range(14):
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(w // 12, w // 4)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(rnd.randint(60, 255) for _ in range(3)))
    img = img.filter(ImageFilter.GaussianBlur(radius=w // 40))
    buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()

@app.get("/v1/models")
def models():
    ids = ["gpt-4o", "deepseek-reasoner", "gpt-image-1", "Kwai-Kolors/Kolors", "sora-2", "tts-1", "gpt-4o-mini-tts", "text-embedding-3-small", "whisper-1"]
    return {"data": [{"id": i} for i in ids]}

@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    last = body["messages"][-1]["content"]
    if isinstance(last, list):
        last = " ".join(p.get("text", "[图片]") if p["type"] == "text" else "[图片]" for p in last)
    reasoning = "用户想要一段创作内容，我先梳理主题、受众和语气，再组织结构。" if "reasoner" in body["model"] else ""
    if body["messages"][0]["role"] == "system" and "提示词工程师" in body["messages"][0]["content"]:
        text = f"{last}，午后柔和的阳光透过窗纱，暖色调，浅景深，胶片质感，细节丰富，电影级构图"
    else:
        text = f"好的！关于「{last}」，这里是一个示例回复：\n\n## 创意方案\n\n1. **主题**：秋日的第一杯咖啡\n2. **语气**：温暖、治愈\n\n```python\ndef hello():\n    print('Hello PWD')\n```\n\n> 小提示：可以继续追问细节。"
    tools = body.get("tools") or []
    if tools and body["messages"][-1]["role"] == "user":
        names = [t["function"]["name"] for t in tools]
        want = "generate_image" if "画" in str(last) and "generate_image" in names else next((n for n in names if n.startswith("mcp_")), None) if "天气" in str(last) else None
        if want:
            args = json.dumps({"prompt": "一只戴墨镜的橘猫"} if want == "generate_image" else {"city": "杭州"}, ensure_ascii=False)
            async def gen_tool():
                yield "data: " + json.dumps({"choices": [{"delta": {"content": "好的，我来处理。"}}]}) + "\n\n"
                yield "data: " + json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": want, "arguments": args[:5]}}]}}]}) + "\n\n"
                yield "data: " + json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[5:]}}]}, "finish_reason": "tool_calls"}]}) + "\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(gen_tool(), media_type="text/event-stream")
    if body["messages"][-1]["role"] == "tool":
        text = f"根据工具结果：{body['messages'][-1]['content'][:60]}"
    sys0 = str(body["messages"][0]["content"]) if body["messages"][0]["role"] == "system" else ""
    if "短片编剧" in sys0:
        text = "第一场 窗台 午后\n橘猫小橘趴在窗台上晒太阳，尾巴轻轻摆动。\n旁白：这是小橘最喜欢的午后。\n\n第二场 窗台 午后\n一只蓝色蝴蝶飞过，小橘抬起头。\n小橘：喵？"
    elif "美术指导" in sys0:
        text = json.dumps([{"kind": "character", "name": "小橘", "description": "一只慵懒的橘猫", "prompt": "橘色短毛猫，圆脸，绿色眼睛"},
                           {"kind": "scene", "name": "窗台", "description": "午后的窗台", "prompt": "木质窗台，纱帘，阳光斜照"}], ensure_ascii=False)
    elif "分镜师" in sys0:
        text = "```json\n" + json.dumps([
            {"title": "开场", "description": "小橘趴在窗台上晒太阳", "camera": "远景，缓慢推近", "dialogue": "旁白：这是小橘最喜欢的午后。", "duration": 3, "elements": ["小橘", "窗台"], "image_prompt": "橘猫趴在洒满阳光的窗台", "video_prompt": "尾巴轻轻摆动"},
            {"title": "蝴蝶", "description": "蓝色蝴蝶飞过", "camera": "特写", "dialogue": "", "duration": 2, "elements": ["窗台"], "image_prompt": "蓝色蝴蝶飞过窗台", "video_prompt": "蝴蝶飞过"},
            {"title": "抬头", "description": "小橘抬头看蝴蝶", "camera": "中景", "dialogue": "小橘：喵？", "duration": 2, "elements": ["小橘"], "image_prompt": "橘猫抬头", "video_prompt": "猫抬头"},
        ], ensure_ascii=False) + "\n```"
    ctx = next((m["content"] for m in body["messages"] if m["role"] == "system" and "参考资料" in str(m["content"])), "")
    if ctx:
        text = "根据资料，PWD 使用 Docker 部署 [1]。"
    if not body.get("stream"):
        return {"choices": [{"message": {"content": text}}]}
    async def gen():
        for ch in reasoning:
            yield "data: " + json.dumps({"choices": [{"delta": {"reasoning_content": ch}}]}) + "\n\n"
            await asyncio.sleep(0.004)
        for ch in text:
            yield "data: " + json.dumps({"choices": [{"delta": {"content": ch}}]}) + "\n\n"
            await asyncio.sleep(0.006)
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

def size_of(s):
    try:
        w, h = (int(x) for x in str(s or "1024x1024").split("x")); return w // 3, h // 3
    except ValueError:
        return 340, 340

@app.post("/v1/images/generations")
async def images(req: Request):
    body = await req.json()
    await asyncio.sleep(8 if "取消" in body["prompt"] else 1.2)
    w, h = size_of(body.get("size"))
    return {"data": [{"b64_json": base64.b64encode(art(w, h, random.random())).decode()} for _ in range(body.get("n", 1))]}

@app.post("/v1/images/edits")
async def edits(req: Request):
    form = await req.form()
    await asyncio.sleep(1.2)
    w, h = size_of(form.get("size"))
    return {"data": [{"b64_json": base64.b64encode(art(w, h, 7)).decode()} for _ in range(int(form.get("n", 1)))]}

@app.post("/v1/videos")
async def videos(req: Request):
    jid = f"video_{len(JOBS) + 1}"
    JOBS[jid] = 0
    return {"id": jid, "status": "queued", "progress": 0}

@app.get("/v1/videos/{jid}")
def video_status(jid: str):
    JOBS[jid] = min(100, JOBS[jid] + 50)
    return {"id": jid, "status": "completed" if JOBS[jid] >= 100 else "in_progress", "progress": JOBS[jid]}

_SAMPLE: bytes | None = None


def sample_video() -> bytes:
    """用 FFmpeg 生成 1 秒测试视频；没有 FFmpeg 时返回占位字节。"""
    global _SAMPLE
    if _SAMPLE is None:
        if shutil.which("ffmpeg"):
            _SAMPLE = subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25", "-t", "1",
                 "-pix_fmt", "yuv420p", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"],
                capture_output=True, check=True,
            ).stdout
        else:
            _SAMPLE = b"\x00" * 64
    return _SAMPLE


@app.get("/v1/videos/{jid}/content")
def video_content(jid: str):
    return Response(sample_video(), media_type="video/mp4")

@app.post("/v1/audio/speech")
async def speech(req: Request):
    import struct, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000)))
    return Response(buf.getvalue(), media_type="audio/wav")


@app.post("/v1/embeddings")
async def embeddings(req: Request):
    body = await req.json()
    keys = ["部署", "Docker", "图像", "视频", "语音", "平台", "GHCR", "创作"]
    return {"data": [{"index": i, "embedding": [float(t.count(k)) + 0.01 for k in keys]} for i, t in enumerate(body["input"])]}


@app.post("/v1/audio/transcriptions")
async def transcriptions(req: Request):
    await req.form()
    return {"text": "帮我写一首关于秋天的诗"}


@app.get("/search")
def searx(q: str, format: str = "json"):
    return {"results": [{"title": f"关于{q}的新闻", "url": "https://news.example.com/1", "content": "这是一条搜索结果摘要"}]}


@app.post("/mcp")
async def mcp(req: Request):
    from fastapi.responses import JSONResponse
    msg = await req.json()
    if "id" not in msg:
        return Response(status_code=202)
    if msg["method"] == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "mock"}}}, headers={"Mcp-Session-Id": "s1"})
    if msg["method"] == "tools/list":
        return {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [{"name": "get_weather", "description": "查询城市天气", "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}]}}
    if msg["method"] == "tools/call":
        city = msg["params"]["arguments"].get("city")
        return {"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": f"{city}：晴，25 度"}]}}
    return {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "not found"}}
