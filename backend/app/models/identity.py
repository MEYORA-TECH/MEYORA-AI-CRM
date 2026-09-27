"""Global tables (no RLS): access is checked in application code."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.permissions import Role
from app.models.base import Base, Timestamps, UUIDPk, str_enum


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    default_currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    # What the organisation sells, to whom and where. Given to the assistant so it judges fit
    # and aims web research at the right market.
    about: Mapped[str | None] = mapped_column(Text)


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)

    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    last_login_at: Mapped[datetime | None]
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Runs the whole installation (Platform admin). Granted only from the server:
    # `python -m scripts.platform_admin grant <email>`, never through the app.
    is_platform_admin: Mapped[bool] = mapped_column(default=False, server_default="false")


class Membership(UUIDPk, Timestamps, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))

    organization: Mapped[Organization] = relationship(lazy="joined")
    user: Mapped[User] = relationship(lazy="joined")


class RefreshToken(UUIDPk, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by_id: Mapped[uuid.UUID | None]
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip: Mapped[str | None] = mapped_column(String(64))


class Invitation(UUIDPk, Timestamps, Base):
    __tablename__ = "invitations"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[Role] = mapped_column(str_enum(Role, "invitation_role"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]

    organization: Mapped[Organization] = relationship(lazy="joined")


class RateLimitBucket(Base):
    """Fixed-window counters, shared by every app instance."""

    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    window_start: Mapped[datetime]
    count: Mapped[int]
