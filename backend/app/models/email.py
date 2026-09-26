"""OAuth handshakes, connected mailboxes and synced (CRM-related) email."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, Timestamps, UUIDPk


class OAuthState(UUIDPk, Base):
    """A pending OAuth redirect. Global (no RLS): the callback arrives before we know the tenant."""

    __tablename__ = "oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20))  # login | gmail
    code_verifier: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class MailAccount(UUIDPk, Timestamps, TenantOwned, Base):
    __tablename__ = "mail_accounts"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "email_address"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="gmail")
    email_address: Mapped[str] = mapped_column(String(320))
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(default=list, server_default="{}")
    history_id: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="connected", server_default="connected")
    last_sync_at: Mapped[datetime | None]
    next_sync_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(String(500))
    messages_synced: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


_ids = lambda: mapped_column(ARRAY(UUID(as_uuid=True)), default=list, server_default="{}")  # noqa: E731


class EmailThread(UUIDPk, Timestamps, TenantOwned, Base):
    __tablename__ = "email_threads"
    __table_args__ = (
        UniqueConstraint("account_id", "provider_thread_id"),
        Index("ix_email_threads_org_recent", "organization_id", "last_message_at"),
        Index("ix_email_threads_contacts", "contact_ids", postgresql_using="gin"),
        Index("ix_email_threads_companies", "company_ids", postgresql_using="gin"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mail_accounts.id", ondelete="CASCADE"))
    provider_thread_id: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(500), default="")
    snippet: Mapped[str] = mapped_column(String(500), default="")
    participants: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    contact_ids: Mapped[list[uuid.UUID]] = _ids()
    company_ids: Mapped[list[uuid.UUID]] = _ids()
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime]


class EmailMessage(UUIDPk, TenantOwned, Base):
    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "provider_message_id"),
        Index("ix_email_messages_thread", "thread_id", "sent_at"),
        Index("ix_email_messages_contacts", "contact_ids", postgresql_using="gin"),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_threads.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mail_accounts.id", ondelete="CASCADE"))
    provider_message_id: Mapped[str] = mapped_column(String(100))
    rfc_message_id: Mapped[str | None] = mapped_column(String(500))
    direction: Mapped[str] = mapped_column(String(10))  # inbound | outbound
    from_email: Mapped[str] = mapped_column(String(320))
    from_name: Mapped[str | None] = mapped_column(String(300))
    to: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    cc: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    subject: Mapped[str] = mapped_column(String(500), default="")
    snippet: Mapped[str] = mapped_column(String(500), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[list[str]] = mapped_column(default=list, server_default="{}")
    has_attachments: Mapped[bool] = mapped_column(default=False, server_default="false")
    contact_ids: Mapped[list[uuid.UUID]] = _ids()
    company_ids: Mapped[list[uuid.UUID]] = _ids()
    sent_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
