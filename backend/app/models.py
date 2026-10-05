from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Setting(Base):
    """键值形式的站点配置（站点名称、是否已安装、默认模型等）。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # active 正常 / pending 待审核 / disabled 已禁用
    status: Mapped[str] = mapped_column(String(16), default="active")
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def role(self) -> str:
        return "admin" if self.is_admin else "user"


class Provider(Base):
    """模型服务商。

    kind:
      - openai   任何 OpenAI 兼容接口（OpenAI / DeepSeek / 硅基流动 / OpenRouter / Ollama ...）
      - comfyui  本地或远程 ComfyUI，使用 API 格式工作流
    """

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32), default="openai")
    base_url: Mapped[str] = mapped_column(String(512))
    api_key: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 文本模型与图像模型列表（用户可手动维护，也可从 /models 拉取）
    chat_models: Mapped[list] = mapped_column(JSON, default=list)
    image_models: Mapped[list] = mapped_column(JSON, default=list)
    video_models: Mapped[list] = mapped_column(JSON, default=list)
    tts_models: Mapped[list] = mapped_column(JSON, default=list)
    # 额外配置：ComfyUI 工作流、额外请求头等
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), nullable=True)
    model: Mapped[str] = mapped_column(String(255), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    # 当前显示的分支末端消息（对话是一棵消息树，编辑 / 重新生成会产生分支）
    current_leaf_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 模型参数：temperature / top_p / max_tokens / context_count
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")  # 推理模型的思考过程
    attachments: Mapped[list] = mapped_column(JSON, default=list)  # 附件作品 ID 列表
    model: Mapped[str] = mapped_column(String(255), default="")
    # provider_id / compare_group（多模型对比批次）/ error（生成失败原因）
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Task(Base):
    """异步生成任务（图像 / 视频 / 语音），后台执行，前端轮询状态。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="image")  # image / video / tts
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/succeeded/failed/cancelled
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id", ondelete="SET NULL"), nullable=True)
    model: Mapped[str] = mapped_column(String(255), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")  # 远端异步任务 ID
    progress: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assets: Mapped[list[Asset]] = relationship(back_populates="task")


class Asset(Base):
    """作品库中的文件（生成结果或上传素材）。"""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="image")
    source: Mapped[str] = mapped_column(String(16), default="generated")  # generated / upload
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(64), default="image/png")
    size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    prompt: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    board_id: Mapped[int | None] = mapped_column(ForeignKey("boards.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task | None] = relationship(back_populates="assets")


class Board(Base):
    """作品集：把作品按项目 / 主题归类。"""

    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromptTemplate(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 为空表示公共模板（内置或管理员共享），所有用户可见
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    group: Mapped[str] = mapped_column(String(32), default="")  # 分组，用于筛选
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), default="image")  # chat（对话角色）/ image / video
    icon: Mapped[str] = mapped_column(String(16), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    negative: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
