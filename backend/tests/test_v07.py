"""v0.7：短片项目（剧本 → 角色 → 分镜 → 关键帧 / 视频 / 配音 → 成片）。"""
import io
import json
import math
import shutil
import struct
import subprocess
import time
import wave

import pytest
from PIL import Image

from app.services import openai_compat, storyboard


def _png(color=(200, 80, 60), size=(320, 200)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def _wav(seconds=1.0):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(i / 8))) for i in range(int(16000 * seconds))))
    return buf.getvalue()


def _wait_all(c, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if not c.get("/api/tasks?status=active").json():
            return
        time.sleep(0.1)
    raise AssertionError("tasks timeout")


ELEMENTS = [{"kind": "character", "name": "小橘", "description": "一只橘猫", "prompt": "橘色短毛猫，绿色眼睛"},
            {"kind": "scene", "name": "窗台", "description": "午后窗台", "prompt": "阳光洒落的木质窗台"}]
SHOTS = [
    {"title": "开场", "description": "小橘趴在窗台上晒太阳", "camera": "远景，缓慢推近", "dialogue": "旁白：这是小橘的午后。",
     "duration": 2, "elements": ["小橘", "窗台"], "image_prompt": "橘猫趴在窗台", "video_prompt": "猫尾巴轻轻摆动"},
    {"title": "转折", "description": "一只蝴蝶飞过", "camera": "特写", "dialogue": "", "duration": 1.5, "elements": ["小橘"],
     "image_prompt": "蝴蝶飞过猫的鼻尖", "video_prompt": "蝴蝶飞过"},
]


def test_extract_json_array():
    assert storyboard.extract_json_array('<think>嗯</think>好的：\n```json\n[{"a": 1},]\n```') == [{"a": 1}]
    assert storyboard.extract_json_array('结果 [{"b": 2}] 完') == [{"b": 2}]
    with pytest.raises(openai_compat.ProviderError):
        storyboard.extract_json_array("没有 JSON")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 FFmpeg")
def test_project_pipeline(installed, monkeypatch):
    async def fake_complete(provider, model, messages, **params):
        system = messages[0]["content"]
        if "编剧" in system:
            return "第一场 窗台 午后\n小橘趴在窗台上。\n旁白：这是小橘的午后。"
        if "美术指导" in system:
            return json.dumps(ELEMENTS, ensure_ascii=False)
        assert "小橘" in system  # 分镜时带上已有角色
        return "```json\n" + json.dumps(SHOTS, ensure_ascii=False) + "\n```"

    seen = {"image": [], "video": [], "tts": []}

    async def fake_images(provider, model, prompt, params, refs=None):
        seen["image"].append((prompt, params.get("size"), len(refs or [])))
        return [(_png(), "image/png")]

    async def fake_video(provider, model, prompt, params, reference, on_progress):
        seen["video"].append((prompt, params.get("seconds"), reference is not None))
        out = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "1",
                              "-pix_fmt", "yuv420p", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"], capture_output=True, check=True)
        return [(out.stdout, "video/mp4")]

    async def fake_speech(provider, model, text, params):
        seen["tts"].append(text)
        return _wav(2.5), "audio/wav"

    monkeypatch.setattr(openai_compat, "chat_complete", fake_complete)
    monkeypatch.setattr(openai_compat, "generate_images", fake_images)
    monkeypatch.setattr(openai_compat, "generate_video", fake_video)
    monkeypatch.setattr(openai_compat, "speech", fake_speech)
    c = installed
    p = c.get("/api/providers").json()[0]
    c.put(f"/api/providers/{p['id']}", json={**p, "api_key": None, "video_models": ["video-model"], "tts_models": ["tts-model"]})

    proj = c.post("/api/projects", json={"name": "小橘的午后", "aspect": "16:9", "style": "温暖胶片质感"}).json()
    pid = proj["id"]
    assert proj["settings"]["image_size"] == "1536x1024" and proj["settings"]["board_id"]
    c.patch(f"/api/projects/{pid}", json={"settings": {"video_provider_id": p["id"], "video_model": "video-model",
                                                         "tts_provider_id": p["id"], "tts_model": "tts-model", "use_refs": True}})
    assert c.post(f"/api/projects/{pid}/ai/storyboard", json={}).status_code == 400  # 没有剧本
    script = c.post(f"/api/projects/{pid}/ai/script", json={"synopsis": "一只猫的午后"}).json()["script"]
    assert "旁白" in script
    r = c.post(f"/api/projects/{pid}/ai/elements").json()
    assert r["added"] == 2 and {e["name"] for e in r["project"]["elements"]} == {"小橘", "窗台"}
    assert c.post(f"/api/projects/{pid}/ai/elements").json()["added"] == 0  # 同名跳过

    proj = c.post(f"/api/projects/{pid}/ai/storyboard", json={"replace": True}).json()
    shots = proj["shots"]
    assert len(shots) == 2 and len(shots[0]["element_ids"]) == 2

    # 角色参考图
    cat = next(e for e in proj["elements"] if e["name"] == "小橘")
    c.post(f"/api/projects/{pid}/elements/{cat['id']}/generate")
    _wait_all(c)
    proj = c.get(f"/api/projects/{pid}").json()
    assert next(e for e in proj["elements"] if e["name"] == "小橘")["ref"]["kind"] == "image"
    assert "角色设定图" in seen["image"][-1][0]

    # 批量生成关键帧：提示词包含角色外观与统一风格，并带上角色参考图
    r = c.post(f"/api/projects/{pid}/generate", json={"slot": "keyframe"}).json()
    assert r["created"] == 2
    _wait_all(c)
    prompt, size, nrefs = seen["image"][-2]
    assert "橘色短毛猫" in prompt and "温暖胶片质感" in prompt and size == "1536x1024" and nrefs == 1
    proj = c.get(f"/api/projects/{pid}").json()
    assert all(s["keyframe"] for s in proj["shots"])
    assert c.post(f"/api/projects/{pid}/generate", json={"slot": "keyframe"}).json()["created"] == 0  # 只补缺

    # 第一个镜头生成视频（以关键帧为首帧），配音只为有台词的镜头生成
    c.post(f"/api/projects/{pid}/generate", json={"slot": "video", "shot_ids": [shots[0]["id"]]})
    assert c.post(f"/api/projects/{pid}/generate", json={"slot": "audio"}).json()["created"] == 1
    _wait_all(c)
    assert seen["video"][0][2] is True and seen["tts"] == ["这是小橘的午后。"]
    proj = c.get(f"/api/projects/{pid}").json()
    assert proj["shots"][0]["video"] and proj["shots"][0]["audio"] and not proj["shots"][1]["audio"]

    # 调整顺序、导出分镜
    c.post(f"/api/projects/{pid}/shots/reorder", json={"ids": [shots[1]["id"], shots[0]["id"]]})
    assert [s["id"] for s in c.get(f"/api/projects/{pid}").json()["shots"]] == [shots[1]["id"], shots[0]["id"]]
    md = c.get(f"/api/projects/{pid}/export.md").text
    assert "| 1 | 一只蝴蝶飞过 |" in md

    # 合成成片
    c.post(f"/api/projects/{pid}/render")
    _wait_all(c, 120)
    proj = c.get(f"/api/projects/{pid}").json()
    assert proj["render_task"]["status"] == "succeeded", proj["render_task"]
    out = proj["output"]
    assert out["kind"] == "video"
    data = c.get(out["url"]).content
    tmp = io.BytesIO(data)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", "-"],
                           input=tmp.getvalue(), capture_output=True, check=True)
    info = json.loads(probe.stdout)
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio", "subtitle"}
    # 1.5 秒（无配音）+ max(2 秒, 2.5 秒配音 + 0.3) ≈ 4.3 秒
    assert 4.0 < float(info["format"]["duration"]) < 4.8
    srt = c.get(f"/api/projects/{pid}/subtitles.srt").text
    assert "00:00:01,500 --> 00:00:04,300" in srt and "旁白：这是小橘的午后。" in srt
    # 生成的作品都归入项目作品集
    board = proj["settings"]["board_id"]
    assert c.get(f"/api/assets?board_id={board}").json()["total"] >= 6

    # 删除项目后作品保留
    c.delete(f"/api/projects/{pid}")
    assert c.get(out["url"]).status_code == 200


def test_project_isolation(installed):
    c = installed
    pid = c.post("/api/projects", json={"name": "私人项目"}).json()["id"]
    c.post("/api/users", json={"username": "bob", "password": "password123"})
    c.post("/api/auth/logout")
    c.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    assert c.get("/api/projects").json() == []
    assert c.get(f"/api/projects/{pid}").status_code == 404
    assert c.post(f"/api/projects/{pid}/render").status_code in (400, 404)
