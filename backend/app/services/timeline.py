import uuid
from typing import Literal

from sqlalchemy import select

from app.auth.deps import TenantContext
from app.models import Activity, EmailMessage, Note, Task
from app.schemas.crm import TimelineItem

EntityField = Literal["company_id", "contact_id", "lead_id", "deal_id"]


async def for_entity(
    ctx: TenantContext, field: EntityField, entity_id: uuid.UUID, limit: int = 100
) -> list[TimelineItem]:
    """Activities, tasks and notes linked to one record, newest first."""
    org = ctx.organization_id
    s = ctx.session

    acts = await s.scalars(
        select(Activity)
        .where(Activity.organization_id == org, getattr(Activity, field) == entity_id)
        .order_by(Activity.occurred_at.desc())
        .limit(limit)
    )
    task_rows = await s.scalars(
        select(Task)
        .where(Task.organization_id == org, getattr(Task, field) == entity_id)
        .order_by(Task.created_at.desc())
        .limit(limit)
    )
    note_rows = await s.scalars(
        select(Note)
        .where(Note.organization_id == org, getattr(Note, field) == entity_id)
        .order_by(Note.created_at.desc())
        .limit(limit)
    )

    items = [
        TimelineItem(
            kind="activity",
            id=a.id,
            at=a.occurred_at,
            title=a.subject,
            body=a.body,
            type=a.type,
            status=a.status,
            actor_id=a.actor_id,
        )
        for a in acts
    ]
    items += [
        TimelineItem(
            kind="task",
            id=t.id,
            at=t.created_at,
            title=t.title,
            body=t.description,
            type=t.priority,
            status=t.status,
            actor_id=t.created_by_id,
        )
        for t in task_rows
    ]
    items += [
        TimelineItem(
            kind="note",
            id=n.id,
            at=n.created_at,
            title="Note",
            body=n.body,
            type=None,
            status=None,
            actor_id=n.author_id,
        )
        for n in note_rows
    ]
    if field in ("company_id", "contact_id"):
        column = EmailMessage.company_ids if field == "company_id" else EmailMessage.contact_ids
        mail = await s.scalars(
            select(EmailMessage)
            .where(EmailMessage.organization_id == org, column.any(entity_id))
            .order_by(EmailMessage.sent_at.desc())
            .limit(limit)
        )
        items += [
            TimelineItem(
                kind="email",
                id=m.thread_id,
                at=m.sent_at,
                title=m.subject,
                body=(m.snippet or m.body_text[:280]) or None,
                type="sent" if m.direction == "outbound" else "received",
                status=None,
                actor_id=None,
            )
            for m in mail
        ]
    items.sort(key=lambda i: i.at, reverse=True)
    return items[:limit]
