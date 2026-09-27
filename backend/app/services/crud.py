"""Tenant-scoped data access shared by every CRM entity.

Every query here filters on the caller's organization explicitly; RLS in the
database is the second layer, not the only one.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from fastapi import Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, RelationshipDirection, joinedload, selectinload

from app.auth.deps import TenantContext
from app.core.errors import NotFound, ValidationFailed
from app.jobs.queue import enqueue
from app.models import Company, Contact, Deal, Lead, Membership, Task
from app.services.audit import apply_changes, audit, snapshot

# Entities whose text feeds the knowledge index (see app/ai/knowledge.py).
INDEXED = {"company", "contact", "lead", "deal", "activity", "note"}

M = TypeVar("M")


@dataclass
class ListQuery:
    page: int
    page_size: int
    q: str | None
    sort: str | None


def list_query(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    sort: str | None = Query(None, max_length=50, pattern=r"^-?[a-z_]+$"),
) -> ListQuery:
    return ListQuery(page=page, page_size=page_size, q=(q or "").strip() or None, sort=sort)


def like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class Repo(Generic[M]):
    def __init__(
        self,
        ctx: TenantContext,
        model: type[M],
        *,
        entity: str,
        search: list[InstrumentedAttribute] | None = None,
        sorts: dict[str, Any] | None = None,
        default_sort: str = "-updated_at",
        load: list[str] | None = None,
    ):
        self.ctx = ctx
        self.model = model
        self.entity = entity
        self.search = search or []
        self.sorts = sorts or {}
        self.default_sort = default_sort
        self.soft = hasattr(model, "deleted_at")
        self.load = load or []

    def base(self) -> Select:
        stmt = select(self.model).where(self.model.organization_id == self.ctx.organization_id)
        for rel in self.load:
            attr = getattr(self.model, rel)
            # A single related record (a contact's company, a deal's stage) comes in the same query
            # via a join; collections need their own query so LIMIT still counts parent rows.
            many_to_one = attr.property.direction is RelationshipDirection.MANYTOONE
            stmt = stmt.options(joinedload(attr) if many_to_one else selectinload(attr))
        if self.soft:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    async def get(self, obj_id: uuid.UUID) -> M:
        obj = await self.ctx.session.scalar(self.base().where(self.model.id == obj_id))
        if obj is None:
            raise NotFound(self.entity.replace("_", " ").capitalize())
        return obj

    def _order(self, sort: str | None):
        key = sort or self.default_sort
        desc = key.startswith("-")
        name = key.lstrip("-")
        column = self.sorts.get(name) or (getattr(self.model, name) if name in ("created_at", "updated_at") else None)
        if column is None:
            raise ValidationFailed(f"Cannot sort by '{name}'", details=sorted(self.sorts))
        primary = column.desc().nulls_last() if desc else column.asc().nulls_last()
        return [primary, self.model.id]

    async def page(self, query: ListQuery, filters: list | None = None) -> tuple[list[M], int]:
        stmt = self.base()
        for condition in filters or []:
            stmt = stmt.where(condition)
        if query.q and self.search:
            pattern = like_pattern(query.q)
            stmt = stmt.where(or_(*[col.ilike(pattern, escape="\\") for col in self.search]))

        # The page and the total in one round trip: count(*) OVER () is computed before LIMIT.
        paged = (
            stmt.add_columns(func.count().over().label("_total"))
            .order_by(*self._order(query.sort))
            .limit(query.page_size)
            .offset((query.page - 1) * query.page_size)
        )
        rows = (await self.ctx.session.execute(paged)).all()
        if rows:
            return [r[0] for r in rows], rows[0][1]
        if query.page == 1:
            return [], 0
        # Past the last page: nothing to show, but the caller still needs the real total.
        total = await self.ctx.session.scalar(select(func.count()).select_from(stmt.subquery()))
        return [], total or 0

    async def create(self, data: dict[str, Any]) -> M:
        obj = self.model(organization_id=self.ctx.organization_id, **data)
        self.ctx.session.add(obj)
        await self.ctx.session.flush()
        await self._load_relations(obj)
        audit(
            self.ctx,
            f"{self.entity}.create",
            entity_type=self.entity,
            entity_id=obj.id,
            changes=snapshot(obj, list(data)),
        )
        await self._reindex(obj)
        return obj

    async def update(self, obj: M, data: dict[str, Any]) -> dict:
        changes = apply_changes(obj, data)
        if changes:
            await self.ctx.session.flush()
            await self._load_relations(obj)
            audit(self.ctx, f"{self.entity}.update", entity_type=self.entity, entity_id=obj.id, changes=changes)
            await self._reindex(obj)
        return changes

    async def _load_relations(self, obj: M) -> None:
        if self.load:
            await self.ctx.session.refresh(obj, attribute_names=self.load)

    async def delete(self, obj: M) -> None:
        if self.soft:
            obj.deleted_at = datetime.now(UTC)
        else:
            await self.ctx.session.delete(obj)
        await self.ctx.session.flush()
        audit(self.ctx, f"{self.entity}.delete", entity_type=self.entity, entity_id=obj.id)
        await self._reindex(obj)

    async def _reindex(self, obj: M) -> None:
        if self.entity in INDEXED:
            await enqueue(
                self.ctx.session,
                "index_record",
                self.ctx.organization_id,
                {"kind": self.entity, "id": str(obj.id)},
                dedupe_key=f"{self.entity}:{obj.id}",
            )


_REF_MODELS: dict[str, tuple[type, str]] = {
    "company_id": (Company, "Company"),
    "contact_id": (Contact, "Contact"),
    "lead_id": (Lead, "Lead"),
    "deal_id": (Deal, "Deal"),
    "task_id": (Task, "Task"),
}
_USER_REFS = ("owner_id", "assignee_id")


async def check_refs(ctx: TenantContext, data: dict[str, Any]) -> None:
    """Reject references to records outside the caller's organization.

    Foreign keys only prove a row exists somewhere; this proves it belongs to
    this organization (and, for CRM records, is not deleted).
    """
    errors: list[dict[str, str]] = []
    for field, (model, label) in _REF_MODELS.items():
        ref = data.get(field)
        if ref is None:
            continue
        stmt = select(func.count(model.id)).where(model.id == ref, model.organization_id == ctx.organization_id)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        if not await ctx.session.scalar(stmt):
            errors.append({"field": field, "message": f"{label} not found"})

    for field in _USER_REFS:
        ref = data.get(field)
        if ref is None:
            continue
        found = await ctx.session.scalar(
            select(func.count(Membership.id)).where(
                Membership.organization_id == ctx.organization_id, Membership.user_id == ref
            )
        )
        if not found:
            errors.append({"field": field, "message": "User is not a member of this organization"})

    if errors:
        raise ValidationFailed("Some linked records are invalid", details=errors)
