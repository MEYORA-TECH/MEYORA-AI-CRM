import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.auth.permissions import Role
from app.models.enums import ActorType
from app.schemas.auth import OrganizationOut, UserOut
from app.schemas.common import Currency, InputModel, Name, OutputModel


class OrganizationUpdate(InputModel):
    name: Name | None = None
    default_currency: Currency | None = None
    about: str | None = Field(None, max_length=2000)


class OrganizationDetailOut(OrganizationOut):
    about: str | None


class MemberOut(OutputModel):
    user: UserOut
    role: Role
    created_at: datetime


class RoleUpdate(InputModel):
    role: Role


class AuditLogOut(OutputModel):
    id: uuid.UUID
    created_at: datetime
    actor_user_id: uuid.UUID | None
    actor_type: ActorType
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    changes: dict[str, Any]
    ip: str | None
    request_id: str | None
