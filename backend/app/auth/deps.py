import uuid
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Perm, Role, permissions_for
from app.auth.security import decode_access_token
from app.core.errors import Forbidden, Unauthorized
from app.database.session import get_session, set_tenant
from app.models import Membership, User

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None
    request_id: str | None


@dataclass
class TenantContext:
    """Who is acting, in which organization, with what rights. Passed to every service."""

    session: AsyncSession
    user: User
    organization_id: uuid.UUID
    role: Role
    meta: RequestMeta
    permissions: frozenset[Perm] = field(default_factory=frozenset)

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def can(self, perm: Perm) -> bool:
        return perm in self.permissions

    def require(self, perm: Perm) -> None:
        if not self.can(perm):
            raise Forbidden()


def request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        request_id=getattr(request.state, "request_id", None),
    )


async def token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Not authenticated")
    try:
        return decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid or expired token") from exc


async def get_current_user(
    payload: dict = Depends(token_payload),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise Unauthorized("Invalid or expired token")
    return user


async def get_tenant(
    request: Request,
    payload: dict = Depends(token_payload),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    org_claim = payload.get("org")
    if not org_claim:
        raise Forbidden("Select an organization first")
    organization_id = uuid.UUID(org_claim)

    # Membership is re-checked on every request, so removing a member or
    # changing a role takes effect immediately, not when the token expires.
    membership = await session.scalar(
        select(Membership).where(Membership.organization_id == organization_id, Membership.user_id == user.id)
    )
    if membership is None:
        raise Forbidden("You are not a member of this organization")

    await set_tenant(session, organization_id)
    return TenantContext(
        session=session,
        user=user,
        organization_id=organization_id,
        role=membership.role,
        meta=request_meta(request),
        permissions=permissions_for(membership.role),
    )


def require(perm: Perm):
    async def _dep(ctx: TenantContext = Depends(get_tenant)) -> TenantContext:
        ctx.require(perm)
        return ctx

    return _dep
