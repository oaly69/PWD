"""轻量级数据库迁移。

`Base.metadata.create_all` 只会创建缺失的表，不会给已有表补字段。
这里按「表.字段 → DDL」逐项检查并补齐，保证旧版本部署的数据库在升级镜像后可直接使用。
新增字段时只需在 COLUMNS 中追加一行；需要回填的数据写在 DATA_MIGRATIONS（必须可重复执行）。
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
    # v0.3 多用户
    ("users", "status", "VARCHAR(16) DEFAULT 'active'"),
    ("users", "last_login_at", "DATETIME"),
    ("conversations", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("tasks", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("assets", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("prompts", "user_id", "INTEGER REFERENCES users(id) ON DELETE CASCADE"),
    ("prompts", "group", "VARCHAR(32) DEFAULT ''"),
    ("prompts", "builtin", "BOOLEAN DEFAULT 0"),
]

# 数据迁移：单用户时代的数据归属到最早的管理员；提示词保持为空（即公共模板）
DATA_MIGRATIONS = [
    "UPDATE conversations SET user_id = (SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1) WHERE user_id IS NULL",
    "UPDATE tasks SET user_id = (SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1) WHERE user_id IS NULL",
    "UPDATE assets SET user_id = (SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1) WHERE user_id IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_assets_filename ON assets (filename)",
    "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_tasks_user_id ON tasks (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_assets_user_id ON assets (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_prompts_user_id ON prompts (user_id)",
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
        for sql in DATA_MIGRATIONS:
            conn.execute(text(sql))
