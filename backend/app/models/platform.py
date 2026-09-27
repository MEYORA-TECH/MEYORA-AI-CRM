"""Installation-wide settings that platform admins change in the app (not tied to a workspace)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformSetting(Base):
    """One saved value. Secret values are AES-GCM encrypted. Not RLS: it belongs to no workspace;
    only platform-admin endpoints read or write it."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(default=False, server_default="false")
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"), onupdate=text("now()"))
