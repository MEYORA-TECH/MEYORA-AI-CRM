"""API keys an organisation brings for AI providers and web search. Values are encrypted at rest."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, Timestamps, UUIDPk


class OrganizationApiKey(UUIDPk, Timestamps, TenantOwned, Base):
    __tablename__ = "organization_api_keys"
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_org_api_keys_provider"),)

    provider: Mapped[str] = mapped_column(String(40))
    encrypted_value: Mapped[str] = mapped_column(Text)
    last4: Mapped[str] = mapped_column(String(4))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None]
