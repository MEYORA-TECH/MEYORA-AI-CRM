"""Memories, the knowledge index, conversation summaries and background jobs."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.embeddings import DIMENSIONS
from app.models.base import Base, TenantOwned, Timestamps, UUIDPk


def _hnsw(name: str, table_col: str = "embedding") -> Index:
    return Index(name, table_col, postgresql_using="hnsw", postgresql_ops={table_col: "vector_cosine_ops"})


class AIMemory(UUIDPk, Timestamps, TenantOwned, Base):
    """A durable fact worth remembering, with where it came from."""

    __tablename__ = "ai_memories"
    __table_args__ = (
        Index("ix_ai_memories_org_status", "organization_id", "status"),
        Index("ix_ai_memories_org_hash", "organization_id", "content_hash"),
        _hnsw("ix_ai_memories_embedding"),
    )

    content: Mapped[str] = mapped_column(Text)
    memory_type: Mapped[str] = mapped_column(String(20), default="fact")
    scope: Mapped[str] = mapped_column(String(20), default="organization")
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")  # manual | chat | note | activity
    source_id: Mapped[uuid.UUID | None]
    source_model: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    importance: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | superseded | pending_review
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_memories.id", ondelete="SET NULL"))
    valid_from: Mapped[datetime] = mapped_column(server_default=text("now()"))
    valid_until: Mapped[datetime | None]
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    content_hash: Mapped[str] = mapped_column(String(64))
    access_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_accessed_at: Mapped[datetime | None]
    created_by: Mapped[str] = mapped_column(String(10), default="user")  # user | ai


class KnowledgeChunk(UUIDPk, TenantOwned, Base):
    """An embedded slice of CRM text (notes, call logs, descriptions) for semantic search."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_source", "organization_id", "source_type", "source_id"),
        _hnsw("ix_knowledge_embedding"),
    )

    source_type: Mapped[str] = mapped_column(String(20))  # note | activity | company | contact | lead | deal
    source_id: Mapped[uuid.UUID]
    chunk_no: Mapped[int] = mapped_column(Integer, default=0)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime | None]
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))
    embedding_model: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"), onupdate=text("now()"))


class AIConversationSummary(UUIDPk, TenantOwned, Base):
    __tablename__ = "ai_conversation_summaries"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)
    covered_until: Mapped[datetime]
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"), onupdate=text("now()"))


class Job(UUIDPk, Base):
    """Background work queue in Postgres (no Redis on the free tier). Not RLS: the worker spans tenants."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_ready", "run_after", postgresql_where=text("status = 'queued'")),
        Index("ix_jobs_dedupe", "kind", "dedupe_key", unique=True, postgresql_where=text("status = 'queued'")),
    )

    kind: Mapped[str] = mapped_column(String(40))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(12), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    run_after: Mapped[datetime] = mapped_column(server_default=text("now()"))
    locked_at: Mapped[datetime | None]
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
