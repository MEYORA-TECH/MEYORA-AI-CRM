"""Repository configuration per CRM entity, plus the small domain rules of each."""

from datetime import UTC, datetime
from typing import Any

from app.auth.deps import TenantContext
from app.auth.permissions import Perm
from app.core.errors import Forbidden
from app.jobs.queue import enqueue
from app.models import Activity, Company, Contact, Deal, Lead, Note, Task
from app.models.enums import ActivityStatus, TaskStatus
from app.services.crud import Repo, check_refs


def companies(ctx: TenantContext) -> Repo[Company]:
    return Repo(
        ctx,
        Company,
        entity="company",
        search=[Company.name, Company.email, Company.website, Company.city, Company.industry],
        sorts={
            "name": Company.name,
            "industry": Company.industry,
            "city": Company.city,
            "status": Company.status,
            "annual_revenue": Company.annual_revenue,
        },
    )


def contacts(ctx: TenantContext) -> Repo[Contact]:
    return Repo(
        ctx,
        Contact,
        entity="contact",
        load=["company"],
        search=[Contact.first_name, Contact.last_name, Contact.email, Contact.phone, Contact.job_title],
        sorts={
            "first_name": Contact.first_name,
            "last_name": Contact.last_name,
            "email": Contact.email,
            "job_title": Contact.job_title,
        },
    )


def leads(ctx: TenantContext) -> Repo[Lead]:
    return Repo(
        ctx,
        Lead,
        entity="lead",
        search=[Lead.name, Lead.company_name, Lead.email, Lead.phone, Lead.industry, Lead.source],
        sorts={
            "name": Lead.name,
            "company_name": Lead.company_name,
            "status": Lead.status,
            "score": Lead.score,
            "source": Lead.source,
        },
    )


def deals(ctx: TenantContext) -> Repo[Deal]:
    return Repo(
        ctx,
        Deal,
        entity="deal",
        load=["company"],
        search=[Deal.name, Deal.source],
        sorts={
            "name": Deal.name,
            "amount": Deal.amount,
            "expected_close_date": Deal.expected_close_date,
            "probability": Deal.probability,
            "status": Deal.status,
        },
    )


def activities(ctx: TenantContext) -> Repo[Activity]:
    return Repo(
        ctx,
        Activity,
        entity="activity",
        default_sort="-occurred_at",
        search=[Activity.subject, Activity.body],
        sorts={"occurred_at": Activity.occurred_at, "type": Activity.type, "status": Activity.status},
    )


def tasks(ctx: TenantContext) -> Repo[Task]:
    return Repo(
        ctx,
        Task,
        entity="task",
        default_sort="due_at",
        search=[Task.title, Task.description],
        sorts={"due_at": Task.due_at, "priority": Task.priority, "status": Task.status, "title": Task.title},
    )


def notes(ctx: TenantContext) -> Repo[Note]:
    return Repo(ctx, Note, entity="note", default_sort="-created_at", search=[Note.body])


# --- Activities --------------------------------------------------------------


async def create_activity(ctx: TenantContext, data: dict[str, Any]) -> Activity:
    await check_refs(ctx, data)
    data.setdefault("occurred_at", datetime.now(UTC))
    if data.get("status") is None:
        data["status"] = ActivityStatus.PLANNED if data["occurred_at"] > datetime.now(UTC) else ActivityStatus.COMPLETED
    return await activities(ctx).create({**data, "actor_id": ctx.user_id})


# --- Tasks -------------------------------------------------------------------


def _task_completion(task: Task | None, data: dict[str, Any]) -> None:
    status = data.get("status")
    if status is None:
        return
    was_done = task is not None and task.status == TaskStatus.COMPLETED
    if status == TaskStatus.COMPLETED and not was_done:
        data["completed_at"] = datetime.now(UTC)
    elif status != TaskStatus.COMPLETED:
        data["completed_at"] = None


async def create_task(ctx: TenantContext, data: dict[str, Any]) -> Task:
    data.setdefault("assignee_id", ctx.user_id)
    await check_refs(ctx, data)
    _task_completion(None, data)
    return await tasks(ctx).create({**data, "created_by_id": ctx.user_id})


async def update_task(ctx: TenantContext, task: Task, data: dict[str, Any]) -> Task:
    await check_refs(ctx, data)
    _task_completion(task, data)
    await tasks(ctx).update(task, data)
    return task


# --- Notes -------------------------------------------------------------------


def _check_note_owner(ctx: TenantContext, note: Note) -> None:
    # Anyone may add notes; editing someone else's note needs delete rights (Manager+).
    if note.author_id != ctx.user_id and not ctx.can(Perm.CRM_DELETE):
        raise Forbidden("Only the author or a manager can change this note")


async def create_note(ctx: TenantContext, data: dict[str, Any]) -> Note:
    await check_refs(ctx, data)
    note = await notes(ctx).create({**data, "author_id": ctx.user_id})
    if len(note.body.strip()) >= 40:  # notes are where requirements and preferences get written down
        await enqueue(
            ctx.session,
            "extract_memories",
            ctx.organization_id,
            {"source_type": "note", "source_id": str(note.id)},
            dedupe_key=f"note:{note.id}",
        )
    return note


async def update_note(ctx: TenantContext, note: Note, body: str) -> Note:
    _check_note_owner(ctx, note)
    await notes(ctx).update(note, {"body": body})
    return note


async def delete_note(ctx: TenantContext, note: Note) -> None:
    _check_note_owner(ctx, note)
    await notes(ctx).delete(note)
