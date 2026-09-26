"""Changes the assistant has proposed, and what happened to them."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, UUIDPk


class AIAction(UUIDPk, TenantOwned, Base):
    __tablename__ = "ai_actions"
    __table_args__ = (Index("ix_ai_actions_conversation", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    ref: Mapped[str] = mapped_column(String(10))  # a1, a2… within the conversation
    tool: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    target_type: Mapped[str | None] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID | None]
    target_version: Mapped[str | None] = mapped_column(String(40))  # updated_at when proposed
    status: Mapped[str] = mapped_column(String(12), default="proposed", server_default="proposed")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    expires_at: Mapped[datetime]
    decided_at: Mapped[datetime | None]
