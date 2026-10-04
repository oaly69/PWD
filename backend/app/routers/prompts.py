from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import PromptTemplate

router = APIRouter(prefix="/api/prompts", tags=["prompts"], dependencies=[Depends(current_user)])


class PromptIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    category: Literal["image", "chat"] = "image"
    content: str = ""
    negative: str = ""


def prompt_out(p: PromptTemplate) -> dict:
    return {"id": p.id, "title": p.title, "category": p.category, "content": p.content, "negative": p.negative}


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
