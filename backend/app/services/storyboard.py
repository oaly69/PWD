"""短片项目的 AI 编剧能力：写剧本、提取角色与场景、拆分镜头。输出要求为 JSON，解析时尽量容错。"""
from __future__ import annotations

import json
import re
from typing import Any

from ..models import Provider
from . import openai_compat
from .openai_compat import ProviderError

SCRIPT_SYSTEM = """你是一名资深短片编剧。根据用户提供的故事梗概，写一个适合 AI 视频制作的短片剧本：
- 时长约 {minutes} 分钟，分为若干场景，每个场景注明地点与时间；
- 画面描写具体、可视化，人物动作清晰，避免大量心理描写；
- 对白简洁口语化，旁白用「旁白：」开头；
- 直接输出剧本正文，不要额外解释。"""

ELEMENTS_SYSTEM = """你是一名影视美术指导。阅读剧本，提取其中的主要角色和场景，为每一项写出可直接用于 AI 绘画的外观描述，保证多个镜头中形象一致。
只输出 JSON 数组，不要任何解释，格式：
[{"kind": "character", "name": "角色名", "description": "身份与性格（一句话）", "prompt": "外貌、年龄、发型、服装、体态等具体外观描述"},
 {"kind": "scene", "name": "场景名", "description": "场景说明", "prompt": "环境、陈设、光线、色调等具体描述"}]
角色不超过 6 个，场景不超过 6 个。"""

STORYBOARD_SYSTEM = """你是一名分镜师。把剧本拆分为适合 AI 生成视频的镜头序列，每个镜头 3～8 秒，镜头总数不超过 {max_shots} 个。
已有角色与场景（出场时请在 elements 中引用名称）：{elements}
只输出 JSON 数组，不要任何解释，每个镜头格式：
{{"title": "镜头标题", "description": "画面内容（中文，具体可视化）", "camera": "景别与运镜，如：中景，缓慢推近",
  "dialogue": "该镜头的台词或旁白，没有则为空字符串", "duration": 5, "elements": ["出场角色或场景名称"],
  "image_prompt": "用于生成关键帧的画面提示词（主体、动作、构图、光线、氛围）", "video_prompt": "用于图生视频的动态描述（人物动作与镜头运动）"}}"""


def extract_json_array(text: str) -> list[dict[str, Any]]:
    """从模型输出中取出 JSON 数组（兼容 ```json 代码块、前后多余文字、<think> 段落）。"""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    candidates = [m.group(1)] if m else []
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except ValueError:
            # 常见问题：尾随逗号
            try:
                data = json.loads(re.sub(r",\s*([\]}])", r"\1", cand))
            except ValueError:
                continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    raise ProviderError("模型没有返回有效的 JSON，请重试或换一个对话模型")


async def _complete(provider: Provider, model: str, system: str, user: str) -> str:
    return await openai_compat.chat_complete(provider, model, [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.7)


async def write_script(provider: Provider, model: str, synopsis: str, minutes: float = 1.0) -> str:
    text = await _complete(provider, model, SCRIPT_SYSTEM.format(minutes=minutes), f"故事梗概：\n{synopsis}")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


async def extract_elements(provider: Provider, model: str, script: str) -> list[dict[str, Any]]:
    items = extract_json_array(await _complete(provider, model, ELEMENTS_SYSTEM, f"剧本：\n{script[:20000]}"))
    out = []
    for it in items:
        name = str(it.get("name") or "").strip()[:64]
        if not name:
            continue
        kind = it.get("kind") if it.get("kind") in ("character", "scene", "prop") else "character"
        out.append({"kind": kind, "name": name, "description": str(it.get("description") or "")[:1000],
                    "prompt": str(it.get("prompt") or "")[:2000]})
    return out


async def split_shots(provider: Provider, model: str, script: str, element_names: list[str], max_shots: int = 24) -> list[dict[str, Any]]:
    system = STORYBOARD_SYSTEM.format(max_shots=max_shots, elements="、".join(element_names) or "（无）")
    items = extract_json_array(await _complete(provider, model, system, f"剧本：\n{script[:20000]}"))
    shots = []
    for it in items[:max_shots]:
        try:
            duration = float(it.get("duration") or 5)
        except (TypeError, ValueError):
            duration = 5.0
        shots.append({
            "title": str(it.get("title") or "")[:128],
            "description": str(it.get("description") or "")[:2000],
            "camera": str(it.get("camera") or "")[:255],
            "dialogue": str(it.get("dialogue") or "")[:1000],
            "duration": max(1.0, min(20.0, duration)),
            "elements": [str(x) for x in (it.get("elements") or []) if isinstance(x, (str, int))],
            "image_prompt": str(it.get("image_prompt") or "")[:2000],
            "video_prompt": str(it.get("video_prompt") or "")[:2000],
        })
    if not shots:
        raise ProviderError("没有拆分出任何镜头，请检查剧本内容")
    return shots
