"""CRM write actions. Execution goes through the same services (and checks) as the UI."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.ai.actions.base import (
    LINKABLE,
    ActionSpec,
    Executed,
    Proposal,
    change,
    parse_when,
    resolve_about,
    show_when,
    version_of,
)
from app.ai.tools.base import ToolContext, ToolInputError
from app.auth.deps import TenantContext
from app.models import PipelineStage
from app.services import deals as deal_service
from app.services import records
from app.services.crud import check_refs


def _uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


# --- create_task -------------------------------------------------------------------------


class CreateTask(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    due: str | None = Field(None, description="YYYY-MM-DD or ISO date-time, in the user's time zone")
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    about_ref: str | None = Field(None, description="Company, contact, lead or deal ref this task is for")
    details: str | None = Field(None, max_length=2000)


async def prepare_create_task(ctx: ToolContext, a: CreateTask) -> Proposal:
    about = resolve_about(ctx, a.about_ref)
    due = parse_when(a.due, ctx.timezone)
    payload = {
        "title": a.title,
        "priority": a.priority,
        "description": a.details,
        "due_at": due.isoformat() if due else None,
    }
    if about:
        payload[LINKABLE[about[0]]] = str(about[1])
    shown_due = show_when(payload["due_at"], ctx.timezone)
    return Proposal(
        title="Create task",
        summary=f"Task “{a.title}”"
        + (f" due {shown_due}" if shown_due else "")
        + (f" for {about[2]}" if about else ""),
        payload=payload,
        changes=[
            c
            for c in [
                change("Title", None, a.title),
                change("Due", None, shown_due) if shown_due else None,
                change("Priority", None, a.priority),
                change("For", None, about[2]) if about else None,
            ]
            if c
        ],
        target_type=about[0] if about else None,
        target_id=about[1] if about else None,
        target_label=about[2] if about else None,
    )


async def execute_create_task(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    data = {k: v for k, v in p.items() if v is not None}
    for k in ("company_id", "contact_id", "lead_id", "deal_id"):
        if k in data:
            data[k] = uuid.UUID(data[k])
    if "due_at" in data:
        data["due_at"] = datetime.fromisoformat(data["due_at"])
    task = await records.create_task(ctx, data)
    return Executed(f"Created task “{task.title}”", "task", task.id)


# --- update_task -------------------------------------------------------------------------


class UpdateTask(BaseModel):
    task_ref: str
    status: Literal["todo", "in_progress", "completed", "cancelled"] | None = None
    due: str | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None


async def prepare_update_task(ctx: ToolContext, a: UpdateTask) -> Proposal:
    task = await records.tasks(ctx.tenant).get(ctx.working_set.resolve("task", a.task_ref))
    payload: dict[str, Any] = {"task_id": str(task.id)}
    changes = []
    if a.status and a.status != task.status:
        payload["status"] = a.status
        changes.append(change("Status", task.status, a.status))
    if a.priority and a.priority != task.priority:
        payload["priority"] = a.priority
        changes.append(change("Priority", task.priority, a.priority))
    if a.due:
        due = parse_when(a.due, ctx.timezone)
        payload["due_at"] = due.isoformat()
        changes.append(
            change(
                "Due",
                show_when(task.due_at.isoformat(), ctx.timezone) if task.due_at else None,
                show_when(payload["due_at"], ctx.timezone),
            )
        )
    if not changes:
        raise ToolInputError("That task already looks like that; nothing to change.")
    return Proposal(
        title="Update task",
        summary=f"Update task “{task.title}”",
        payload=payload,
        changes=changes,
        target_type="task",
        target_id=task.id,
        target_version=version_of(task),
        target_label=task.title,
    )


async def execute_update_task(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    task = await records.tasks(ctx).get(uuid.UUID(p["task_id"]))
    data = {k: v for k, v in p.items() if k != "task_id"}
    if "due_at" in data:
        data["due_at"] = datetime.fromisoformat(data["due_at"])
    await records.update_task(ctx, task, data)
    return Executed(f"Updated task “{task.title}”", "task", task.id)


async def task_version(ctx: TenantContext, target_id: uuid.UUID) -> str | None:
    return version_of(await records.tasks(ctx).get(target_id))


# --- log_activity --------------------------------------------------------------------------


class LogActivity(BaseModel):
    type: Literal["call", "meeting", "email", "note", "follow_up"]
    subject: str = Field(min_length=2, max_length=300)
    about_ref: str | None = None
    notes: str | None = Field(None, max_length=5000)
    when: str | None = Field(None, description="When it happened or is planned; default now")


async def prepare_log_activity(ctx: ToolContext, a: LogActivity) -> Proposal:
    about = resolve_about(ctx, a.about_ref)
    when = parse_when(a.when, ctx.timezone, default_hour=9)
    payload = {"type": a.type, "subject": a.subject, "body": a.notes, "occurred_at": when.isoformat() if when else None}
    if about:
        payload[LINKABLE[about[0]]] = str(about[1])
    return Proposal(
        title="Log activity",
        summary=f"Log {a.type.replace('_', ' ')} “{a.subject}”" + (f" on {about[2]}" if about else ""),
        payload=payload,
        changes=[
            c
            for c in [
                change("Type", None, a.type),
                change("Subject", None, a.subject),
                change("When", None, show_when(payload["occurred_at"], ctx.timezone)) if when else None,
            ]
            if c
        ],
        target_type=about[0] if about else None,
        target_id=about[1] if about else None,
        target_label=about[2] if about else None,
    )


async def execute_log_activity(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    data = {k: v for k, v in p.items() if v is not None}
    for k in ("company_id", "contact_id", "lead_id", "deal_id"):
        if k in data:
            data[k] = uuid.UUID(data[k])
    if "occurred_at" in data:
        data["occurred_at"] = datetime.fromisoformat(data["occurred_at"])
    act = await records.create_activity(ctx, data)
    return Executed(f"Logged {act.type.replace('_', ' ')} “{act.subject}”", None, act.id)


# --- add_note ------------------------------------------------------------------------------


class AddNote(BaseModel):
    about_ref: str
    body: str = Field(min_length=3, max_length=10_000)


async def prepare_add_note(ctx: ToolContext, a: AddNote) -> Proposal:
    about = resolve_about(ctx, a.about_ref)
    return Proposal(
        title="Add note",
        summary=f"Note on {about[2]}",
        payload={LINKABLE[about[0]]: str(about[1]), "body": a.body},
        changes=[change("Note", None, a.body[:300])],
        target_type=about[0],
        target_id=about[1],
        target_label=about[2],
    )


async def execute_add_note(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    data = {k: (uuid.UUID(v) if k.endswith("_id") else v) for k, v in p.items()}
    note = await records.create_note(ctx, data)
    return Executed("Added a note", None, note.id)


# --- create_lead / update_lead -------------------------------------------------------------


class CreateLead(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    company_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    source: str | None = Field(None, max_length=120)
    industry: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=5000)


async def prepare_create_lead(ctx: ToolContext, a: CreateLead) -> Proposal:
    payload = {
        "name": a.name,
        "company_name": a.company_name,
        "email": a.email,
        "phone": a.phone,
        "source": a.source,
        "industry": a.industry,
        "description": a.notes,
    }
    return Proposal(
        title="Create lead",
        summary=f"Lead {a.name}" + (f" at {a.company_name}" if a.company_name else ""),
        payload=payload,
        changes=[change(k.replace("_", " ").capitalize(), None, v) for k, v in payload.items() if v],
    )


async def execute_create_lead(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    lead = await records.leads(ctx).create({**{k: v for k, v in p.items() if v is not None}, "owner_id": ctx.user_id})
    return Executed(f"Created lead {lead.name}", "lead", lead.id)


class UpdateLead(BaseModel):
    lead_ref: str
    status: Literal["new", "contacted", "qualified", "unqualified", "lost"] | None = None
    score: int | None = Field(None, ge=0, le=100)


async def prepare_update_lead(ctx: ToolContext, a: UpdateLead) -> Proposal:
    lead = await records.leads(ctx.tenant).get(ctx.working_set.resolve("lead", a.lead_ref))
    if lead.status == "converted":
        raise ToolInputError("This lead is already converted.")
    payload: dict[str, Any] = {"lead_id": str(lead.id)}
    changes = []
    if a.status and a.status != lead.status:
        payload["status"] = a.status
        changes.append(change("Status", lead.status, a.status))
    if a.score is not None and a.score != lead.score:
        payload["score"] = a.score
        changes.append(change("Score", lead.score, a.score))
    if not changes:
        raise ToolInputError("Nothing to change on that lead.")
    return Proposal(
        title="Update lead",
        summary=f"Update lead {lead.name}",
        payload=payload,
        changes=changes,
        target_type="lead",
        target_id=lead.id,
        target_version=version_of(lead),
        target_label=lead.name,
    )


async def execute_update_lead(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    repo = records.leads(ctx)
    lead = await repo.get(uuid.UUID(p["lead_id"]))
    await repo.update(lead, {k: v for k, v in p.items() if k != "lead_id"})
    return Executed(f"Updated lead {lead.name}", "lead", lead.id)


async def lead_version(ctx: TenantContext, target_id: uuid.UUID) -> str | None:
    return version_of(await records.leads(ctx).get(target_id))


# --- update_deal ---------------------------------------------------------------------------


class UpdateDeal(BaseModel):
    deal_ref: str
    stage: str | None = Field(None, description="Stage name, e.g. Proposal, Won, Lost")
    amount: float | None = Field(None, ge=0)
    expected_close_date: date | None = None
    probability: int | None = Field(None, ge=0, le=100)


async def prepare_update_deal(ctx: ToolContext, a: UpdateDeal) -> Proposal:
    s = ctx.tenant.session
    deal = await records.deals(ctx.tenant).get(ctx.working_set.resolve("deal", a.deal_ref))
    current_stage = await s.get(PipelineStage, deal.stage_id)
    payload: dict[str, Any] = {"deal_id": str(deal.id)}
    changes = []
    if a.stage:
        stage = await s.scalar(
            select(PipelineStage).where(
                PipelineStage.pipeline_id == deal.pipeline_id,
                PipelineStage.organization_id == ctx.tenant.organization_id,
                PipelineStage.name.ilike(a.stage.strip()),
            )
        )
        if stage is None:
            names = ", ".join(
                x.name
                for x in await s.scalars(
                    select(PipelineStage)
                    .where(PipelineStage.pipeline_id == deal.pipeline_id)
                    .order_by(PipelineStage.position)
                )
            )
            raise ToolInputError(f"No stage called '{a.stage}'. Stages: {names}.")
        if stage.id != deal.stage_id:
            payload["stage_id"] = str(stage.id)
            changes.append(change("Stage", current_stage.name if current_stage else None, stage.name))
    if a.amount is not None and Decimal(str(a.amount)) != deal.amount:
        payload["amount"] = str(Decimal(str(a.amount)).quantize(Decimal("0.01")))
        changes.append(change("Amount", float(deal.amount), a.amount))
    if a.expected_close_date and a.expected_close_date != deal.expected_close_date:
        payload["expected_close_date"] = a.expected_close_date.isoformat()
        changes.append(
            change(
                "Expected close",
                deal.expected_close_date.isoformat() if deal.expected_close_date else None,
                a.expected_close_date.isoformat(),
            )
        )
    if a.probability is not None and a.probability != deal.probability:
        payload["probability"] = a.probability
        changes.append(change("Probability", deal.probability, a.probability))
    if not changes:
        raise ToolInputError("That deal already looks like that; nothing to change.")
    return Proposal(
        title="Update deal",
        summary=f"Update deal {deal.name}",
        payload=payload,
        changes=changes,
        target_type="deal",
        target_id=deal.id,
        target_version=version_of(deal),
        target_label=deal.name,
    )


async def execute_update_deal(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    deal = await records.deals(ctx).get(uuid.UUID(p["deal_id"]))
    data: dict[str, Any] = {}
    if "stage_id" in p:
        data["stage_id"] = uuid.UUID(p["stage_id"])
    if "amount" in p:
        data["amount"] = Decimal(p["amount"])
    if "expected_close_date" in p:
        data["expected_close_date"] = date.fromisoformat(p["expected_close_date"])
    if "probability" in p:
        data["probability"] = p["probability"]
    await deal_service.update_deal(ctx, deal, data)
    return Executed(f"Updated deal {deal.name}", "deal", deal.id)


async def deal_version(ctx: TenantContext, target_id: uuid.UUID) -> str | None:
    return version_of(await records.deals(ctx).get(target_id))


# --- update_contact ------------------------------------------------------------------------


class UpdateContact(BaseModel):
    contact_ref: str
    job_title: str | None = Field(None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    linkedin_url: str | None = Field(None, max_length=500)


async def prepare_update_contact(ctx: ToolContext, a: UpdateContact) -> Proposal:
    contact = await records.contacts(ctx.tenant).get(ctx.working_set.resolve("contact", a.contact_ref))
    payload: dict[str, Any] = {"contact_id": str(contact.id)}
    changes = []
    for field_, label in (
        ("job_title", "Job title"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("linkedin_url", "LinkedIn"),
    ):
        new = getattr(a, field_)
        if new is not None and new != getattr(contact, field_):
            payload[field_] = new
            changes.append(change(label, getattr(contact, field_), new))
    if not changes:
        raise ToolInputError("Nothing to change on that contact.")
    return Proposal(
        title="Update contact",
        summary=f"Update {contact.full_name}",
        payload=payload,
        changes=changes,
        target_type="contact",
        target_id=contact.id,
        target_version=version_of(contact),
        target_label=contact.full_name,
    )


async def execute_update_contact(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    repo = records.contacts(ctx)
    contact = await repo.get(uuid.UUID(p["contact_id"]))
    data = {k: v for k, v in p.items() if k != "contact_id"}
    await check_refs(ctx, data)
    await repo.update(contact, data)
    return Executed(f"Updated {contact.full_name}", "contact", contact.id)


async def contact_version(ctx: TenantContext, target_id: uuid.UUID) -> str | None:
    return version_of(await records.contacts(ctx).get(target_id))


CRM_ACTIONS: list[ActionSpec] = [
    ActionSpec(
        "create_task",
        "Propose a task (e.g. a follow-up). Applied only after the user confirms.",
        CreateTask,
        prepare_create_task,
        execute_create_task,
    ),
    ActionSpec(
        "update_task",
        "Propose changing a task's status, due date or priority.",
        UpdateTask,
        prepare_update_task,
        execute_update_task,
        task_version,
    ),
    ActionSpec(
        "log_activity",
        "Propose logging a call, meeting, email or follow-up on a record.",
        LogActivity,
        prepare_log_activity,
        execute_log_activity,
    ),
    ActionSpec(
        "add_note",
        "Propose adding a note to a company, contact, lead or deal.",
        AddNote,
        prepare_add_note,
        execute_add_note,
    ),
    ActionSpec("create_lead", "Propose creating a new lead.", CreateLead, prepare_create_lead, execute_create_lead),
    ActionSpec(
        "update_lead",
        "Propose changing a lead's status or score (conversion stays in the app).",
        UpdateLead,
        prepare_update_lead,
        execute_update_lead,
        lead_version,
    ),
    ActionSpec(
        "update_deal",
        "Propose moving a deal to another stage or changing its amount, close date or probability.",
        UpdateDeal,
        prepare_update_deal,
        execute_update_deal,
        deal_version,
    ),
    ActionSpec(
        "update_contact",
        "Propose updating a contact's job title, email, phone or LinkedIn.",
        UpdateContact,
        prepare_update_contact,
        execute_update_contact,
        contact_version,
    ),
]
