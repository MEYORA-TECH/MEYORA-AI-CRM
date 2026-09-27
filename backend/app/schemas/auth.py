import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.auth.permissions import Perm, Role
from app.schemas.common import InputModel, Name, OutputModel

Password = str


class RegisterIn(InputModel):
    email: EmailStr
    password: Password = Field(min_length=10, max_length=128)
    full_name: Name
    # Either create a new organization, or join one through an invitation.
    organization_name: Name | None = None
    invite_token: str | None = Field(default=None, max_length=200)


class LoginIn(InputModel):
    email: EmailStr
    password: Password = Field(min_length=1, max_length=128)


class SwitchOrganizationIn(InputModel):
    organization_id: uuid.UUID


class UserOut(OutputModel):
    id: uuid.UUID
    email: str
    full_name: str
    avatar_url: str | None


class OrganizationOut(OutputModel):
    id: uuid.UUID
    name: str
    slug: str
    default_currency: str


class MembershipOut(OutputModel):
    organization: OrganizationOut
    role: Role


class MeOut(UserOut):
    is_platform_admin: bool = False
    memberships: list[MembershipOut]
    current_organization_id: uuid.UUID | None
    role: Role | None
    permissions: list[Perm]


class TokenOut(OutputModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    me: MeOut


class InvitationCreate(InputModel):
    email: EmailStr
    role: Role = Role.MEMBER


class InvitationOut(OutputModel):
    id: uuid.UUID
    email: str
    role: Role
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationCreated(InvitationOut):
    # Shown once so an admin can share the link; only its hash is stored.
    token: str


class AcceptInvitationIn(InputModel):
    token: str = Field(max_length=200)
