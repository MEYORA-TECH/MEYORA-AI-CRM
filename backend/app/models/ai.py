"""AI conversations, messages and usage. Tenant-owned (RLS) and private to their user."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDelete, TenantOwned, Timestamps, UUIDPk


class AIConversation(UUIDPk, Timestamps, TenantOwned, SoftDelete, Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index(
            "ix_ai_conversations_user_recent",
            "organization_id",
            "user_id",
            "last_message_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    # Pinned at the first answer so a conversation never silently changes model mid-way.
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(120))
    # Working set: entities the conversation is about, so "all of them" resolves without re-searching.
    state: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    last_message_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AIMessage(UUIDPk, TenantOwned, Base):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_conversation", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("clock_timestamp()"))
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[list[Any] | None] = mapped_column(JSONB)
    tool_call_id: Mapped[str | None] = mapped_column(String(100))
    tool_name: Mapped[str | None] = mapped_column(String(80))
    # What the UI renders for a tool result (rows with links); never sent to the model.
    ui: Mapped[dict[str, Any] | None]
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)


class AIUsageLog(UUIDPk, TenantOwned, Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (Index("ix_ai_usage_user_day", "organization_id", "user_id", "created_at"),)

    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    request_id: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_conversations.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(String(30), default="chat")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[list[Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | error | rate_limited
    error: Mapped[str | None] = mapped_column(String(300))
