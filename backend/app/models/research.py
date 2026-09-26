"""Web search cache, budget log, and saved research briefs."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, UUIDPk


class WebSearchCache(UUIDPk, TenantOwned, Base):
    __tablename__ = "web_search_cache"
    __table_args__ = (Index("ix_web_cache_lookup", "organization_id", "query_hash", "created_at"),)

    query_hash: Mapped[str] = mapped_column(String(64))
    query: Mapped[str] = mapped_column(String(500))
    provider: Mapped[str] = mapped_column(String(20))
    results: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class WebSearchLog(UUIDPk, TenantOwned, Base):
    __tablename__ = "web_search_logs"
    __table_args__ = (Index("ix_web_logs_budget", "organization_id", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    query: Mapped[str] = mapped_column(String(500))
    provider: Mapped[str] = mapped_column(String(20))
    cached: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ResearchBrief(UUIDPk, TenantOwned, Base):
    __tablename__ = "research_briefs"
    __table_args__ = (Index("ix_research_entity", "organization_id", "entity_type", "entity_id", "created_at"),)

    entity_type: Mapped[str] = mapped_column(String(20))  # company | lead
    entity_id: Mapped[uuid.UUID]
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(120))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
