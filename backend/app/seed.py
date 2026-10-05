"""内置模板：对话角色、图像提示词、视频提示词。

模板数据存放在 seed_data/{chat,image,video}.json，每条包含 icon / title / group / content（图像可含 negative）。
内置模板 user_id 为空（公共）且 builtin=True。数据版本号记录在设置项 builtin_seed_version 中，
升级时只补充缺少的模板，不会覆盖或恢复用户已删除的模板。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from .models import PromptTemplate, User

SEED_VERSION = 2
DATA_DIR = Path(__file__).resolve().parent / "seed_data"
CATEGORIES = ("chat", "image", "video")

# v0.2 安装时写入的示例标题（当时没有 builtin 标记，升级时据此识别）
LEGACY_BUILTIN_TITLES = {
    ("chat", "文案策划"), ("chat", "分镜编剧"), ("chat", "绘画提示词专家"), ("chat", "中英翻译"), ("chat", "头脑风暴"),
    ("image", "赛博朋克城市"), ("image", "国风山水"), ("image", "人像写真"), ("image", "3D 可爱角色"), ("image", "美食摄影"),
}


@lru_cache
def builtin_templates() -> dict[str, list[dict]]:
    return {c: json.loads((DATA_DIR / f"{c}.json").read_text(encoding="utf-8")) for c in CATEGORIES}


def _add_builtins(db: Session, skip: set[tuple[str, str]] | None = None) -> int:
    skip = skip or set()
    n = 0
    for category, items in builtin_templates().items():
        for it in items:
            if (category, it["title"]) in skip:
                continue
            db.add(PromptTemplate(
                user_id=None, builtin=True, category=category, title=it["title"], icon=it.get("icon", ""),
                group=it.get("group", ""), content=it["content"], negative=it.get("negative", ""),
            ))
            n += 1
    return n


def seed_defaults(db: Session) -> None:
    """全新安装时写入全部内置模板。"""
    from .site import set_setting

    _add_builtins(db)
    set_setting(db, "builtin_seed_version", SEED_VERSION)
    set_setting(db, "builtin_seeded", True)


def seed_if_upgraded(db: Session) -> None:
    """旧版本升级：整理历史模板归属并补充新增的内置模板（每个版本只执行一次）。"""
    from .site import get_setting, is_installed, set_setting

    if not is_installed(db):
        return
    version = get_setting(db, "builtin_seed_version") or 0
    if version >= SEED_VERSION:
        return
    admin = db.query(User).filter(User.is_admin.is_(True)).order_by(User.id).first()
    for p in db.query(PromptTemplate).filter(PromptTemplate.user_id.is_(None), PromptTemplate.builtin.is_(False)).all():
        if (p.category, p.title) in LEGACY_BUILTIN_TITLES:
            db.delete(p)  # 旧版示例由新版内置模板替代
        elif admin is not None:
            p.user_id = admin.id  # 单用户时代自建的模板归管理员私有
    db.flush()
    existing = {(p.category, p.title) for p in db.query(PromptTemplate).filter(PromptTemplate.builtin.is_(True)).all()}
    _add_builtins(db, skip=existing)
    set_setting(db, "builtin_seed_version", SEED_VERSION)
    set_setting(db, "builtin_seeded", True)
    db.commit()
