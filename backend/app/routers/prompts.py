from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import PromptTemplate, Provider
from ..services import openai_compat
from ..site import get_setting

router = APIRouter(prefix="/api/prompts", tags=["prompts"], dependencies=[Depends(current_user)])


class PromptIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: Literal["image", "chat"] = "image"
    content: str = ""
    negative: str = ""
    icon: str = Field("", max_length=16)


def prompt_out(p: PromptTemplate) -> dict:
    return {"id": p.id, "title": p.title, "category": p.category, "content": p.content, "negative": p.negative, "icon": p.icon or ""}


ENHANCE_SYSTEM = {
    "image": (
        "你是专业的 AI 绘画提示词工程师。把用户的想法扩写成一段高质量的图像生成提示词："
        "补充主体细节、环境、构图、光线、色彩、风格与画质描述，保持用户原意，不要添加用户没有暗示的主体。"
        "输出与用户输入相同的语言，只输出提示词本身，不要解释、不要引号、不要分点。"
    ),
    "video": (
        "你是专业的 AI 视频提示词工程师。把用户的想法扩写成一段视频生成提示词："
        "描述主体与动作、镜头运动（推拉摇移、跟拍等）、场景、光线氛围与节奏，控制在 120 字以内。"
        "输出与用户输入相同的语言，只输出提示词本身，不要解释。"
    ),
    "chat": (
        "你是提示词优化专家。把用户的需求改写成结构清晰、目标明确、包含必要背景与输出格式要求的提示词。"
        "只输出改写后的提示词本身。"
    ),
}


class EnhanceIn(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    kind: Literal["image", "video", "chat"] = "image"


@router.post("/enhance")
async def enhance_prompt(body: EnhanceIn, db: Session = Depends(get_db)):
    """使用对话模型优化 / 扩写提示词。"""
    pid, model = get_setting(db, "enhance_provider_id"), get_setting(db, "enhance_model")
    if not (pid and model):
        pid, model = get_setting(db, "default_chat_provider_id"), get_setting(db, "default_chat_model")
    provider = db.get(Provider, pid) if pid else None
    if provider is None or provider.kind != "openai" or not model:
        raise HTTPException(status_code=400, detail="请先在系统设置中配置「提示词优化模型」或默认对话模型")
    try:
        text = await openai_compat.chat_complete(provider, model, [
            {"role": "system", "content": ENHANCE_SYSTEM[body.kind]},
            {"role": "user", "content": body.prompt},
        ])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"优化失败：{exc}") from exc
    # 去掉推理模型可能输出的 <think> 段落
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return {"prompt": text.strip().strip('"“”')}


@router.get("")
def list_prompts(category: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PromptTemplate)
    if category:
        q = q.filter(PromptTemplate.category == category)
    return [prompt_out(p) for p in q.order_by(PromptTemplate.id.desc()).all()]


@router.post("")
def create_prompt(body: PromptIn, db: Session = Depends(get_db)):
    p = PromptTemplate(**body.model_dump())
    db.add(p)
    db.commit()
    return prompt_out(p)


@router.put("/{pid}")
def update_prompt(pid: int, body: PromptIn, db: Session = Depends(get_db)):
    p = db.get(PromptTemplate, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="提示词不存在")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return prompt_out(p)


@router.delete("/{pid}")
def delete_prompt(pid: int, db: Session = Depends(get_db)):
    p = db.get(PromptTemplate, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="提示词不存在")
    db.delete(p)
    db.commit()
    return {"ok": True}
