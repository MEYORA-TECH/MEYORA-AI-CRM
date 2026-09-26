import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.config import get_settings
from app.core.errors import NotFound
from app.models import ResearchBrief
from app.schemas.common import OutputModel
from app.services import records, web_research
from app.services.audit import audit

router = APIRouter(tags=["research"])
Kind = Literal["companies", "leads"]
ENTITY_TYPE = {"companies": "company", "leads": "lead"}


class BriefOut(OutputModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    content: str
    sources: list[dict[str, Any]]
    provider: str
    model: str
    created_by_id: uuid.UUID | None
    created_at: datetime


class WebStatus(OutputModel):
    enabled: bool
    used_this_month: int
    monthly_limit: int


async def _entity(ctx: TenantContext, kind: Kind, entity_id: uuid.UUID):
    repo = records.companies if kind == "companies" else records.leads
    return await repo(ctx).get(entity_id)


@router.get("/web/status", response_model=WebStatus)
async def web_status(ctx: TenantContext = Depends(require(Perm.CRM_READ))):
    return WebStatus(
        enabled=web_research.is_enabled(),
        used_this_month=await web_research.usage(ctx.session, ctx.organization_id),
        monthly_limit=get_settings().web_search_monthly_limit,
    )


@router.get("/research/{kind}/{entity_id}", response_model=list[BriefOut])
async def list_briefs(kind: Kind, entity_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_READ))):
    await _entity(ctx, kind, entity_id)
    rows = await ctx.session.scalars(
        select(ResearchBrief)
        .where(
            ResearchBrief.organization_id == ctx.organization_id,
            ResearchBrief.entity_type == ENTITY_TYPE[kind],
            ResearchBrief.entity_id == entity_id,
        )
        .order_by(ResearchBrief.created_at.desc())
        .limit(5)
    )
    return list(rows)


@router.post("/research/{kind}/{entity_id}", response_model=BriefOut, status_code=201)
async def create_brief(kind: Kind, entity_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    entity = await _entity(ctx, kind, entity_id)
    entity_type = ENTITY_TYPE[kind]
    brief = await web_research.create_brief(ctx.session, ctx.organization_id, ctx.user_id, entity_type, entity)
    audit(
        ctx,
        "research.brief",
        entity_type=entity_type,
        entity_id=entity_id,
        changes={"sources": {"old": None, "new": len(brief.sources)}},
    )
    await ctx.session.commit()
    return brief


@router.post("/research/briefs/{brief_id}/save-note", status_code=201)
async def save_brief_as_note(brief_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    """A person decides this web research belongs in the CRM; it becomes a note with its sources."""
    brief = await ctx.session.scalar(
        select(ResearchBrief).where(ResearchBrief.id == brief_id, ResearchBrief.organization_id == ctx.organization_id)
    )
    if brief is None:
        raise NotFound("Research brief")
    sources = "\n".join(f"[{s['n']}] {s['title']} — {s['url']}" for s in brief.sources)
    body = f"Web research ({brief.created_at:%d %b %Y}, unverified)\n\n{brief.content}\n\nSources:\n{sources}"
    link = {"company_id": brief.entity_id} if brief.entity_type == "company" else {"lead_id": brief.entity_id}
    # Not mined for memories: web claims stay labelled as web research, not durable facts.
    note = await records.create_note(ctx, {"body": body[:20_000], **link}, extract_memories=False)
    await ctx.session.commit()
    return {"note_id": str(note.id)}
