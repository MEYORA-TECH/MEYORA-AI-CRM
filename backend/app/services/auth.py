import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequestMeta
from app.auth.permissions import Role, permissions_for
from app.auth.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, Unauthorized, ValidationFailed
from app.database.session import set_tenant
from app.models import Invitation, Membership, Organization, RefreshToken, User
from app.schemas.auth import MembershipOut, MeOut, OrganizationOut, RegisterIn
from app.services.audit import add_audit
from app.services.pipelines import build_default_pipeline


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    organization_id: uuid.UUID | None


def _now() -> datetime:
    return datetime.now(UTC)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    return f"{base}-{secrets.token_hex(3)}"


async def _find_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(func.lower(User.email) == email.lower()))


async def memberships_of(session: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    rows = await session.scalars(
        select(Membership).where(Membership.user_id == user_id).order_by(Membership.created_at)
    )
    return list(rows)


async def build_me(session: AsyncSession, user: User, organization_id: uuid.UUID | None) -> MeOut:
    memberships = await memberships_of(session, user.id)
    current = next((m for m in memberships if m.organization_id == organization_id), None)
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_platform_admin=user.is_platform_admin,
        memberships=[
            MembershipOut(organization=OrganizationOut.model_validate(m.organization), role=m.role) for m in memberships
        ],
        current_organization_id=current.organization_id if current else None,
        role=current.role if current else None,
        permissions=sorted(permissions_for(current.role)) if current else [],
    )


async def issue_tokens(
    session: AsyncSession,
    user: User,
    organization_id: uuid.UUID | None,
    meta: RequestMeta,
    *,
    family_id: uuid.UUID | None = None,
) -> tuple[IssuedTokens, RefreshToken]:
    settings = get_settings()
    raw = new_opaque_token()
    record = RefreshToken(
        user_id=user.id,
        organization_id=organization_id,
        token_hash=hash_token(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=_now() + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=meta.user_agent,
        ip=meta.ip,
    )
    session.add(record)
    await session.flush()
    tokens = IssuedTokens(
        access_token=create_access_token(user.id, organization_id),
        refresh_token=raw,
        expires_in=settings.access_token_ttl_minutes * 60,
        organization_id=organization_id,
    )
    return tokens, record


async def _accept_invitation(session: AsyncSession, user: User, raw_token: str, meta: RequestMeta) -> Membership:
    invitation = await session.scalar(select(Invitation).where(Invitation.token_hash == hash_token(raw_token)))
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at < _now()
    ):
        raise ValidationFailed("This invitation is invalid or has expired")
    if invitation.email.lower() != user.email.lower():
        raise Forbidden("This invitation was sent to a different email address")

    existing = await session.scalar(
        select(Membership).where(
            Membership.organization_id == invitation.organization_id,
            Membership.user_id == user.id,
        )
    )
    if existing:
        raise Conflict("You are already a member of this organization")

    invitation.accepted_at = _now()
    membership = Membership(organization_id=invitation.organization_id, user_id=user.id, role=invitation.role)
    session.add(membership)
    await session.flush()
    await set_tenant(session, invitation.organization_id)
    add_audit(
        session,
        organization_id=invitation.organization_id,
        action="member.join",
        actor_user_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        changes={"role": {"old": None, "new": invitation.role}},
    )
    return membership


async def create_workspace(session: AsyncSession, user: User, name: str, meta: RequestMeta) -> uuid.UUID:
    """A new organization owned by `user`, with the default pipeline."""
    org = Organization(name=name, slug=_slugify(name))
    session.add(org)
    await session.flush()
    session.add(Membership(organization_id=org.id, user_id=user.id, role=Role.OWNER))
    await set_tenant(session, org.id)
    session.add(build_default_pipeline(org.id))
    add_audit(
        session,
        organization_id=org.id,
        action="organization.create",
        actor_user_id=user.id,
        meta=meta,
        entity_type="organization",
        entity_id=org.id,
    )
    return org.id


async def sign_in_with_google(session: AsyncSession, claims: dict, meta: RequestMeta) -> tuple[User, IssuedTokens]:
    """Google identity → Meyora account: by Google ID, else by verified email (linked), else a new account."""
    user = await session.scalar(select(User).where(User.google_sub == claims["sub"]))
    if user is None:
        user = await _find_user_by_email(session, claims["email"])
        if user is not None:
            user.google_sub = claims["sub"]  # Google verified this address, so it's the same person
    created = user is None
    if created:
        user = User(
            email=claims["email"].lower(),
            full_name=claims.get("name") or claims["email"].split("@")[0],
            avatar_url=claims.get("picture"),
            google_sub=claims["sub"],
        )
        session.add(user)
        await session.flush()
    if not user.is_active:
        raise Unauthorized("This account is disabled.")

    memberships = await memberships_of(session, user.id)
    if memberships:
        org_id = memberships[0].organization_id
    else:
        first = (claims.get("given_name") or user.full_name.split(" ")[0]).strip()
        org_id = await create_workspace(session, user, f"{first}'s workspace", meta)
    user.last_login_at = _now()
    tokens, _ = await issue_tokens(session, user, org_id, meta)
    await set_tenant(session, org_id)
    add_audit(
        session,
        organization_id=org_id,
        action="auth.login",
        actor_user_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=user.id,
        changes={"method": {"old": None, "new": "google"}},
    )
    await session.commit()
    return user, tokens


async def register(session: AsyncSession, data: RegisterIn, meta: RequestMeta) -> tuple[User, IssuedTokens]:
    if bool(data.organization_name) == bool(data.invite_token):
        raise ValidationFailed("Provide either an organization name or an invitation")
    if await _find_user_by_email(session, data.email):
        raise Conflict("An account with this email already exists")

    user = User(email=data.email.lower(), full_name=data.full_name, password_hash=hash_password(data.password))
    session.add(user)
    await session.flush()

    if data.invite_token:
        membership = await _accept_invitation(session, user, data.invite_token, meta)
        org_id = membership.organization_id
    else:
        org_id = await create_workspace(session, user, data.organization_name, meta)

    user.last_login_at = _now()
    tokens, _ = await issue_tokens(session, user, org_id, meta)
    await session.commit()
    return user, tokens


async def login(session: AsyncSession, email: str, password: str, meta: RequestMeta) -> tuple[User, IssuedTokens]:
    user = await _find_user_by_email(session, email)
    if not verify_password(password, user.password_hash if user else None) or not user:
        raise Unauthorized("Incorrect email or password")
    if not user.is_active:
        raise Unauthorized("Incorrect email or password")

    memberships = await memberships_of(session, user.id)
    org_id = memberships[0].organization_id if memberships else None
    user.last_login_at = _now()
    tokens, _ = await issue_tokens(session, user, org_id, meta)
    if org_id:
        await set_tenant(session, org_id)
        add_audit(
            session,
            organization_id=org_id,
            action="auth.login",
            actor_user_id=user.id,
            meta=meta,
            entity_type="user",
            entity_id=user.id,
        )
    await session.commit()
    return user, tokens


async def refresh(session: AsyncSession, raw_token: str, meta: RequestMeta) -> tuple[User, IssuedTokens]:
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
    )
    if record is None:
        raise Unauthorized("Session expired. Please sign in again.")

    if record.revoked_at is not None:
        # A rotated token was replayed: assume theft and end the whole session family.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == record.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await session.commit()
        raise Unauthorized("Session expired. Please sign in again.")

    if record.expires_at < _now():
        raise Unauthorized("Session expired. Please sign in again.")

    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Session expired. Please sign in again.")

    # Keep the organization only if the user is still a member.
    org_id = record.organization_id
    memberships = await memberships_of(session, user.id)
    if org_id not in {m.organization_id for m in memberships}:
        org_id = memberships[0].organization_id if memberships else None

    tokens, new_record = await issue_tokens(session, user, org_id, meta, family_id=record.family_id)
    record.revoked_at = _now()
    record.replaced_by_id = new_record.id
    await session.commit()
    return user, tokens


async def logout(session: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    record = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if record is not None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == record.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await session.commit()


async def switch_organization(
    session: AsyncSession, user: User, organization_id: uuid.UUID, raw_refresh: str | None, meta: RequestMeta
) -> IssuedTokens:
    member = await session.scalar(
        select(Membership).where(Membership.organization_id == organization_id, Membership.user_id == user.id)
    )
    if member is None:
        raise Forbidden("You are not a member of this organization")
    await logout(session, raw_refresh)
    tokens, _ = await issue_tokens(session, user, organization_id, meta)
    await session.commit()
    return tokens


async def accept_invitation(
    session: AsyncSession, user: User, raw_token: str, meta: RequestMeta, raw_refresh: str | None
) -> IssuedTokens:
    membership = await _accept_invitation(session, user, raw_token, meta)
    await logout(session, raw_refresh)
    tokens, _ = await issue_tokens(session, user, membership.organization_id, meta)
    await session.commit()
    return tokens
