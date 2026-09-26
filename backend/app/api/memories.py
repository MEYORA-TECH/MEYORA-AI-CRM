import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field
from sqlalchemy import func, select

from app.ai import memory
from app.ai.embeddings import embed_one, embedder
from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.errors import Forbidden, NotFound
from app.models import AIMemory
from app.schemas.common import InputModel, OutputModel, Page
from app.services.audit import audit
from app.services.crud import ListQuery, check_refs, list_query

router = APIRouter(prefix="/memories", tags=["memories"])

MemoryType = Literal["fact", "preference", "requirement", "relationship", "decision"]


class MemoryOut(OutputModel):
    id: uuid.UUID
    content: str
    memory_type: str
    scope: str
    user_id: uuid.UUID | None
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    source_type: str
    source_id: uuid.UUID | None
    source_model: str | None
    confidence: float
    importance: int
    status: str
    superseded_by_id: uuid.UUID | None
    created_by: str
    access_count: int
    created_at: datetime
    updated_at: datetime


class MemoryCreate(InputModel):
    content: str = Field(min_length=5, max_length=1000)
    memory_type: MemoryType = "fact"
    importance: int = Field(3, ge=1, le=5)
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    personal: bool = Field(False, description="Only visible to you")


class MemoryUpdate(InputModel):
    content: str | None = Field(None, min_length=5, max_length=1000)
    memory_type: MemoryType | None = None
    importance: int | None = Field(None, ge=1, le=5)
    status: Literal["active"] | None = Field(None, description="Approve a memory waiting for review")


async def _get(ctx: TenantContext, memory_id: uuid.UUID) -> AIMemory:
    mem = await ctx.session.scalar(
        select(AIMemory).where(
            AIMemory.id == memory_id, AIMemory.organization_id == ctx.organization_id, memory.visible_to(ctx.user_id)
        )
    )
    if mem is None:
        raise NotFound("Memory")
    return mem


def _can_change(ctx: TenantContext, mem: AIMemory) -> None:
    # Like notes: anyone can add; changing a teammate's memory needs Manager rights.
    if mem.user_id != ctx.user_id and not ctx.can(Perm.CRM_DELETE):
        raise Forbidden("Only the person who saved this memory or a manager can change it")


@router.get("", response_model=Page[MemoryOut])
async def list_memories(
    q: ListQuery = Depends(list_query),
    scope: Literal["user", "organization", "company", "contact", "deal"] | None = None,
    status: Literal["active", "superseded", "pending_review"] | None = Query(None),
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    ctx: TenantContext = Depends(require(Perm.CRM_READ)),
):
    stmt = select(AIMemory).where(AIMemory.organization_id == ctx.organization_id, memory.visible_to(ctx.user_id))
    if scope:
        stmt = stmt.where(AIMemory.scope == scope)
    stmt = stmt.where(AIMemory.status == status) if status else stmt.where(AIMemory.status != "superseded")
    for col, value in (
        (AIMemory.company_id, company_id),
        (AIMemory.contact_id, contact_id),
        (AIMemory.deal_id, deal_id),
    ):
        if value:
            stmt = stmt.where(col == value)
    total = await ctx.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if q.q:  # meaning-based search, closest first
        order = [AIMemory.embedding.cosine_distance(await embed_one(q.q))]
        stmt = stmt.where(AIMemory.embedding_model == embedder().model)
    else:
        order = [AIMemory.importance.desc(), AIMemory.updated_at.desc()]
    rows = await ctx.session.scalars(stmt.order_by(*order).limit(q.page_size).offset((q.page - 1) * q.page_size))
    return Page[MemoryOut](
        items=[MemoryOut.model_validate(r) for r in rows], total=total, page=q.page, page_size=q.page_size
    )


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(body: MemoryCreate, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    links = {"company_id": body.company_id, "contact_id": body.contact_id, "deal_id": body.deal_id}
    await check_refs(ctx, links)
    saved = await memory.save_memory(
        ctx.session,
        ctx.organization_id,
        content=body.content,
        memory_type=body.memory_type,
        user_id=ctx.user_id,
        user_scope=body.personal,
        links=links,
        source_type="manual",
        importance=body.importance,
    )
    audit(
        ctx,
        f"memory.{'create' if saved.action == 'created' else 'merge'}",
        entity_type="memory",
        entity_id=saved.memory.id,
        changes={"content": {"old": None, "new": saved.memory.content}},
    )
    await ctx.session.commit()
    return saved.memory


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: uuid.UUID, body: MemoryUpdate, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))
):
    mem = await _get(ctx, memory_id)
    changes: dict = {}
    if body.content is not None and memory.normalize(body.content) != mem.content:
        _can_change(ctx, mem)
        content = memory.normalize(body.content)
        changes["content"] = {"old": mem.content, "new": content}
        mem.content, mem.content_hash = content, memory.content_hash(content)
        mem.embedding, mem.embedding_model = await embed_one(content), embedder().model
        mem.created_by, mem.confidence = "user", 1.0  # a person has now vouched for it
    if body.memory_type and body.memory_type != mem.memory_type:
        changes["memory_type"] = {"old": mem.memory_type, "new": body.memory_type}
        mem.memory_type = body.memory_type
    if body.importance is not None and body.importance != mem.importance:
        changes["importance"] = {"old": mem.importance, "new": body.importance}
        mem.importance = body.importance
    if body.status == "active" and mem.status == "pending_review":
        changes["status"] = {"old": mem.status, "new": "active"}
        mem.status, mem.confidence = "active", max(mem.confidence, 0.9)
    if changes:
        audit(ctx, "memory.update", entity_type="memory", entity_id=mem.id, changes=changes)
        await ctx.session.commit()
    return mem


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    mem = await _get(ctx, memory_id)
    _can_change(ctx, mem)
    # Hard delete: forgetting means forgetting.
    await ctx.session.delete(mem)
    audit(ctx, "memory.delete", entity_type="memory", entity_id=memory_id)  # no content kept
    await ctx.session.commit()
    return Response(status_code=204)
