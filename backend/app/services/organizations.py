import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.auth.deps import TenantContext
from app.auth.permissions import ROLE_RANK, Role
from app.auth.security import hash_token, new_opaque_token
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import Invitation, Membership, Organization, User
from app.schemas.organizations import OrganizationUpdate
from app.services.audit import apply_changes, audit

INVITATION_TTL = timedelta(days=7)


async def get_organization(ctx: TenantContext) -> Organization:
    org = await ctx.session.get(Organization, ctx.organization_id)
    if org is None:
        raise NotFound("Organization")
    return org


async def update_organization(ctx: TenantContext, data: OrganizationUpdate) -> Organization:
    org = await get_organization(ctx)
    changes = apply_changes(org, data.model_dump(exclude_unset=True))
    if changes:
        audit(ctx, "organization.update", entity_type="organization", entity_id=org.id, changes=changes)
    return org


async def list_members(ctx: TenantContext) -> list[Membership]:
    rows = await ctx.session.scalars(
        select(Membership)
        .where(Membership.organization_id == ctx.organization_id)
        .join(User, User.id == Membership.user_id)
        .order_by(User.full_name)
    )
    return list(rows)


async def is_member(ctx: TenantContext, user_id: uuid.UUID) -> bool:
    found = await ctx.session.scalar(
        select(func.count(Membership.id)).where(
            Membership.organization_id == ctx.organization_id, Membership.user_id == user_id
        )
    )
    return bool(found)


async def _get_membership(ctx: TenantContext, user_id: uuid.UUID) -> Membership:
    membership = await ctx.session.scalar(
        select(Membership).where(Membership.organization_id == ctx.organization_id, Membership.user_id == user_id)
    )
    if membership is None:
        raise NotFound("Member")
    return membership


async def _owner_count(ctx: TenantContext) -> int:
    return (
        await ctx.session.scalar(
            select(func.count(Membership.id)).where(
                Membership.organization_id == ctx.organization_id, Membership.role == Role.OWNER
            )
        )
        or 0
    )


def _check_can_manage(ctx: TenantContext, target_role: Role, new_role: Role | None = None) -> None:
    # Only owners may touch owners or grant ownership; nobody can act above their own rank.
    if Role.OWNER in (target_role, new_role) and ctx.role != Role.OWNER:
        raise Forbidden("Only an owner can change owner access")
    if ROLE_RANK[target_role] > ROLE_RANK[ctx.role]:
        raise Forbidden()


async def change_role(ctx: TenantContext, user_id: uuid.UUID, role: Role) -> Membership:
    membership = await _get_membership(ctx, user_id)
    _check_can_manage(ctx, membership.role, role)
    if membership.role == Role.OWNER and role != Role.OWNER and await _owner_count(ctx) <= 1:
        raise Conflict("An organization must keep at least one owner")
    if membership.role != role:
        audit(
            ctx,
            "member.role_change",
            entity_type="user",
            entity_id=user_id,
            changes={"role": {"old": membership.role, "new": role}},
        )
        membership.role = role
    return membership


async def remove_member(ctx: TenantContext, user_id: uuid.UUID) -> None:
    membership = await _get_membership(ctx, user_id)
    if user_id != ctx.user_id:
        _check_can_manage(ctx, membership.role)
    if membership.role == Role.OWNER and await _owner_count(ctx) <= 1:
        raise Conflict("An organization must keep at least one owner")
    await ctx.session.delete(membership)
    audit(
        ctx,
        "member.remove",
        entity_type="user",
        entity_id=user_id,
        changes={"role": {"old": membership.role, "new": None}},
    )


async def list_invitations(ctx: TenantContext) -> list[Invitation]:
    rows = await ctx.session.scalars(
        select(Invitation)
        .where(
            Invitation.organization_id == ctx.organization_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(rows)


async def create_invitation(ctx: TenantContext, email: str, role: Role) -> tuple[Invitation, str]:
    _check_can_manage(ctx, role, role)
    already = await ctx.session.scalar(
        select(func.count(Membership.id))
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization_id, func.lower(User.email) == email.lower())
    )
    if already:
        raise Conflict("This person is already a member")

    raw = new_opaque_token()
    invitation = Invitation(
        organization_id=ctx.organization_id,
        email=email.lower(),
        role=role,
        token_hash=hash_token(raw),
        invited_by_id=ctx.user_id,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    ctx.session.add(invitation)
    await ctx.session.flush()
    audit(
        ctx,
        "member.invite",
        entity_type="invitation",
        entity_id=invitation.id,
        changes={"email": {"old": None, "new": invitation.email}, "role": {"old": None, "new": role}},
    )
    return invitation, raw


async def revoke_invitation(ctx: TenantContext, invitation_id: uuid.UUID) -> None:
    invitation = await ctx.session.scalar(
        select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == ctx.organization_id)
    )
    if invitation is None or invitation.accepted_at or invitation.revoked_at:
        raise NotFound("Invitation")
    invitation.revoked_at = datetime.now(UTC)
    audit(ctx, "member.invite_revoke", entity_type="invitation", entity_id=invitation.id)
