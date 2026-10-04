"""轻量级数据库迁移。

`Base.metadata.create_all` 只会创建缺失的表，不会给已有表补字段。
这里按「表.字段 → DDL」逐项检查并补齐，保证旧版本部署的数据库在升级镜像后可直接使用。
新增字段时只需在 COLUMNS 中追加一行。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger("pwd.migrate")

# (表名, 字段名, SQLite 字段定义)
COLUMNS: list[tuple[str, str, str]] = [
    # v0.2
    ("providers", "video_models", "JSON DEFAULT '[]'"),
    ("providers", "tts_models", "JSON DEFAULT '[]'"),
    ("conversations", "pinned", "BOOLEAN DEFAULT 0"),
    ("conversations", "params", "JSON DEFAULT '{}'"),
    ("conversations", "icon", "VARCHAR(16) DEFAULT ''"),
    ("messages", "reasoning", "TEXT DEFAULT ''"),
    ("messages", "attachments", "JSON DEFAULT '[]'"),
    ("messages", "model", "VARCHAR(255) DEFAULT ''"),
    ("tasks", "external_id", "VARCHAR(255) DEFAULT ''"),
    ("tasks", "progress", "INTEGER DEFAULT 0"),
    ("assets", "width", "INTEGER DEFAULT 0"),
    ("assets", "height", "INTEGER DEFAULT 0"),
    ("prompts", "icon", "VARCHAR(16) DEFAULT ''"),
]


def run(engine: Engine) -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in COLUMNS:
            if table not in tables:
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if column not in existing:
                log.info("迁移：%s 增加字段 %s", table, column)
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
