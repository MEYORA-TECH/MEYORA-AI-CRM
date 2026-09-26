import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, MetaData, String, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Fetch server-generated values (created_at, updated_at) via RETURNING so they
    # are never lazily loaded later, which async sessions cannot do.
    __mapper_args__ = {"eager_defaults": True}
    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: ARRAY(String),
        datetime: DateTime(timezone=True),
    }


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Store enums as varchar + CHECK so adding a value needs no type migration."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        create_constraint=True,
        values_callable=lambda e: [m.value for m in e],
    )


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TenantOwned:
    """Marker + column for tables protected by row-level security."""

    __rls__ = True

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)


class SoftDelete:
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class CrmRecord(UUIDPk, Timestamps, TenantOwned, SoftDelete):
    tags: Mapped[list[str]] = mapped_column(default=list, server_default="{}")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
