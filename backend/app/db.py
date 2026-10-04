from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> None:
    """创建数据库引擎并建表。测试中可传入独立的数据库地址。"""
    global engine, SessionLocal
    settings.ensure_dirs()
    url = url or f"sqlite:///{settings.db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 简单的 PRAGMA
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    from . import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    assert SessionLocal is not None, "数据库未初始化"
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def new_session() -> Session:
    assert SessionLocal is not None, "数据库未初始化"
    return SessionLocal()
