import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.errors import ValidationFailed
from app.models import AuditLog
from app.schemas.auth import InvitationCreate, InvitationCreated, InvitationOut, OrganizationOut
from app.schemas.common import Page
from app.schemas.dashboard import DashboardOut
from app.schemas.organizations import AuditLogOut, MemberOut, OrganizationUpdate, RoleUpdate
from app.schemas.pipelines import PipelineCreate, PipelineOut, PipelineUpdate
from app.services import dashboard as dashboard_service
from app.services import organizations as org_service
from app.services import pipelines as pipeline_service
from app.services.crud import ListQuery, list_query

router = APIRouter()

# --- Organization & members --------------------------------------------------

org = APIRouter(prefix="/organization", tags=["organization"])


@org.get("", response_model=OrganizationOut)
async def get_organization(ctx: TenantContext = Depends(require(Perm.CRM_READ))):
    return await org_service.get_organization(ctx)


@org.patch("", response_model=OrganizationOut)
async def update_organization(body: OrganizationUpdate, ctx: TenantContext = Depends(require(Perm.ORG_MANAGE))):
    result = await org_service.update_organization(ctx, body)
    await ctx.session.commit()
    return result


@org.get("/members", response_model=list[MemberOut])
async def list_members(ctx: TenantContext = Depends(require(Perm.MEMBERS_READ))):
    return await org_service.list_members(ctx)


@org.patch("/members/{user_id}", response_model=MemberOut)
async def change_role(user_id: uuid.UUID, body: RoleUpdate,
                      ctx: TenantContext = Depends(require(Perm.MEMBERS_MANAGE))):
    membership = await org_service.change_role(ctx, user_id, body.role)
    await ctx.session.commit()
    return membership


@org.delete("/members/{user_id}", status_code=204)
async def remove_member(user_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.MEMBERS_READ))):
    # Anyone may leave; removing someone else needs members:manage.
    if user_id != ctx.user_id:
        ctx.require(Perm.MEMBERS_MANAGE)
    await org_service.remove_member(ctx, user_id)
    await ctx.session.commit()
    return Response(status_code=204)


@org.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(ctx: TenantContext = Depends(require(Perm.MEMBERS_MANAGE))):
    return await org_service.list_invitations(ctx)


@org.post("/invitations", response_model=InvitationCreated, status_code=201)
async def create_invitation(body: InvitationCreate, ctx: TenantContext = Depends(require(Perm.MEMBERS_MANAGE))):
    invitation, token = await org_service.create_invitation(ctx, body.email, body.role)
    await ctx.session.commit()
    return InvitationCreated(**InvitationOut.model_validate(invitation).model_dump(), token=token)


@org.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.MEMBERS_MANAGE))):
    await org_service.revoke_invitation(ctx, invitation_id)
    await ctx.session.commit()
    return Response(status_code=204)


@org.get("/audit-logs", response_model=Page[AuditLogOut])
async def audit_logs(
    q: ListQuery = Depends(list_query),
    entity_type: str | None = Query(None, max_length=50),
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    ctx: TenantContext = Depends(require(Perm.AUDIT_READ)),
):
    stmt = select(AuditLog).where(AuditLog.organization_id == ctx.organization_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    total = await ctx.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await ctx.session.scalars(
        stmt.order_by(AuditLog.created_at.desc()).limit(q.page_size).offset((q.page - 1) * q.page_size)
    )
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r) for r in rows], total=total, page=q.page, page_size=q.page_size
    )


# --- Pipelines ---------------------------------------------------------------

pipelines = APIRouter(prefix="/pipelines", tags=["pipelines"])


@pipelines.get("", response_model=list[PipelineOut])
async def list_pipelines(ctx: TenantContext = Depends(require(Perm.CRM_READ))):
    return await pipeline_service.list_pipelines(ctx)


@pipelines.post("", response_model=PipelineOut, status_code=201)
async def create_pipeline(body: PipelineCreate, ctx: TenantContext = Depends(require(Perm.PIPELINES_MANAGE))):
    pipeline = await pipeline_service.create_pipeline(ctx, body)
    await ctx.session.commit()
    return await pipeline_service.get_pipeline(ctx, pipeline.id)


@pipelines.patch("/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline(pipeline_id: uuid.UUID, body: PipelineUpdate,
                          ctx: TenantContext = Depends(require(Perm.PIPELINES_MANAGE))):
    pipeline = await pipeline_service.update_pipeline(ctx, pipeline_id, body)
    await ctx.session.commit()
    return pipeline


@pipelines.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.PIPELINES_MANAGE))):
    await pipeline_service.delete_pipeline(ctx, pipeline_id)
    await ctx.session.commit()
    return Response(status_code=204)


# --- Dashboard ---------------------------------------------------------------

dashboard = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard.get("", response_model=DashboardOut)
async def get_dashboard(tz: str = Query("Asia/Kolkata", max_length=64),
                        ctx: TenantContext = Depends(require(Perm.CRM_READ))):
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailed("Unknown time zone") from exc
    return await dashboard_service.build(ctx, tz)


for sub in (org, pipelines, dashboard):
    router.include_router(sub)
