"""Synced email, read from the database only; Gmail is never called from here."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import exists, func, or_, select

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.errors import NotFound
from app.models import EmailMessage, EmailThread
from app.schemas.common import OutputModel, Page
from app.services.crud import ListQuery, like_pattern, list_query

router = APIRouter(prefix="/emails", tags=["emails"])
read = require(Perm.CRM_READ)


class ThreadOut(OutputModel):
    id: uuid.UUID
    subject: str
    snippet: str
    participants: list[dict[str, Any]]
    contact_ids: list[uuid.UUID]
    company_ids: list[uuid.UUID]
    message_count: int
    last_message_at: datetime


class MessageOut(OutputModel):
    id: uuid.UUID
    direction: str
    from_email: str
    from_name: str | None
    to: list[dict[str, Any]]
    cc: list[dict[str, Any]]
    subject: str
    body_text: str
    has_attachments: bool
    sent_at: datetime


class ThreadDetail(ThreadOut):
    messages: list[MessageOut]


@router.get("/threads", response_model=Page[ThreadOut])
async def list_threads(
    q: ListQuery = Depends(list_query),
    contact_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    ctx: TenantContext = Depends(read),
):
    stmt = select(EmailThread).where(EmailThread.organization_id == ctx.organization_id)
    if contact_id:
        stmt = stmt.where(EmailThread.contact_ids.any(contact_id))
    if company_id:
        stmt = stmt.where(EmailThread.company_ids.any(company_id))
    if q.q:
        pattern = like_pattern(q.q)
        stmt = stmt.where(
            or_(
                EmailThread.subject.ilike(pattern, escape="\\"),
                exists().where(
                    EmailMessage.thread_id == EmailThread.id,
                    or_(
                        EmailMessage.body_text.ilike(pattern, escape="\\"),
                        EmailMessage.from_email.ilike(pattern, escape="\\"),
                    ),
                ),
            )
        )
    total = await ctx.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await ctx.session.scalars(
        stmt.order_by(EmailThread.last_message_at.desc()).limit(q.page_size).offset((q.page - 1) * q.page_size)
    )
    return Page[ThreadOut](
        items=[ThreadOut.model_validate(r) for r in rows], total=total, page=q.page, page_size=q.page_size
    )


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(thread_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    thread = await ctx.session.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.organization_id == ctx.organization_id)
    )
    if thread is None:
        raise NotFound("Email thread")
    messages = await ctx.session.scalars(
        select(EmailMessage).where(EmailMessage.thread_id == thread.id).order_by(EmailMessage.sent_at)
    )
    return ThreadDetail(
        **ThreadOut.model_validate(thread).model_dump(), messages=[MessageOut.model_validate(m) for m in messages]
    )
