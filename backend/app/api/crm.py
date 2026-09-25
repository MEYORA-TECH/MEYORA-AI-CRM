import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.errors import Forbidden, ValidationFailed
from app.models import Activity, Company, Contact, Deal, Lead, Note, Task
from app.models.enums import (
    ActivityStatus,
    ActivityType,
    CompanyStatus,
    DealStatus,
    LeadStatus,
    TaskPriority,
    TaskStatus,
)
from app.schemas.common import Page
from app.schemas.crm import (
    ActivityCreate,
    ActivityOut,
    ActivityUpdate,
    BoardOut,
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    DealCreate,
    DealMoveIn,
    DealOut,
    DealUpdate,
    LeadConvertIn,
    LeadConvertOut,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TimelineItem,
)
from app.services import deals as deal_service
from app.services import leads as lead_service
from app.services import records, timeline
from app.services.crud import ListQuery, check_refs, list_query

read = require(Perm.CRM_READ)
write = require(Perm.CRM_WRITE)
delete = require(Perm.CRM_DELETE)

router = APIRouter()


def _payload(body, *, not_null: tuple[str, ...] = ()) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    bad = [f for f in not_null if f in data and data[f] is None]
    if bad:
        raise ValidationFailed("These fields cannot be empty", details=bad)
    for key in ("tags", "custom_fields"):
        if key in data and data[key] is None:
            data[key] = [] if key == "tags" else {}
    return data


def _page(model_out, items, total, q: ListQuery):
    return Page[model_out](
        items=[model_out.model_validate(i) for i in items], total=total, page=q.page, page_size=q.page_size
    )


def _tag_filter(model, tag: str | None) -> list:
    return [model.tags.any(tag.lower())] if tag else []


async def _done(ctx: TenantContext) -> None:
    await ctx.session.commit()


# --- Companies ---------------------------------------------------------------

companies = APIRouter(prefix="/companies", tags=["companies"])


@companies.get("", response_model=Page[CompanyOut])
async def list_companies(
    q: ListQuery = Depends(list_query),
    status: CompanyStatus | None = None,
    owner_id: uuid.UUID | None = None,
    industry: str | None = Query(None, max_length=120),
    tag: str | None = Query(None, max_length=50),
    ctx: TenantContext = Depends(read),
):
    f = _tag_filter(Company, tag)
    if status:
        f.append(Company.status == status)
    if owner_id:
        f.append(Company.owner_id == owner_id)
    if industry:
        f.append(func.lower(Company.industry) == industry.lower())
    items, total = await records.companies(ctx).page(q, f)
    return _page(CompanyOut, items, total, q)


@companies.post("", response_model=CompanyOut, status_code=201)
async def create_company(body: CompanyCreate, ctx: TenantContext = Depends(write)):
    data = _payload(body, not_null=("status",))
    data.setdefault("owner_id", ctx.user_id)
    await check_refs(ctx, data)
    obj = await records.companies(ctx).create(data)
    await _done(ctx)
    return obj


@companies.get("/{company_id}", response_model=CompanyOut)
async def get_company(company_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    return await records.companies(ctx).get(company_id)


@companies.patch("/{company_id}", response_model=CompanyOut)
async def update_company(company_id: uuid.UUID, body: CompanyUpdate, ctx: TenantContext = Depends(write)):
    repo = records.companies(ctx)
    obj = await repo.get(company_id)
    data = _payload(body, not_null=("name", "status"))
    await check_refs(ctx, data)
    await repo.update(obj, data)
    await _done(ctx)
    return obj


@companies.delete("/{company_id}", status_code=204)
async def delete_company(company_id: uuid.UUID, ctx: TenantContext = Depends(delete)):
    repo = records.companies(ctx)
    await repo.delete(await repo.get(company_id))
    await _done(ctx)
    return Response(status_code=204)


# --- Contacts ----------------------------------------------------------------

contacts = APIRouter(prefix="/contacts", tags=["contacts"])


@contacts.get("", response_model=Page[ContactOut])
async def list_contacts(
    q: ListQuery = Depends(list_query),
    company_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    tag: str | None = Query(None, max_length=50),
    ctx: TenantContext = Depends(read),
):
    f = _tag_filter(Contact, tag)
    if company_id:
        f.append(Contact.company_id == company_id)
    if owner_id:
        f.append(Contact.owner_id == owner_id)
    items, total = await records.contacts(ctx).page(q, f)
    return _page(ContactOut, items, total, q)


@contacts.post("", response_model=ContactOut, status_code=201)
async def create_contact(body: ContactCreate, ctx: TenantContext = Depends(write)):
    data = _payload(body)
    data.setdefault("owner_id", ctx.user_id)
    await check_refs(ctx, data)
    obj = await records.contacts(ctx).create(data)
    await _done(ctx)
    return obj


@contacts.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    return await records.contacts(ctx).get(contact_id)


@contacts.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: uuid.UUID, body: ContactUpdate, ctx: TenantContext = Depends(write)):
    repo = records.contacts(ctx)
    obj = await repo.get(contact_id)
    data = _payload(body, not_null=("first_name",))
    await check_refs(ctx, data)
    await repo.update(obj, data)
    await _done(ctx)
    return obj


@contacts.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, ctx: TenantContext = Depends(delete)):
    repo = records.contacts(ctx)
    await repo.delete(await repo.get(contact_id))
    await _done(ctx)
    return Response(status_code=204)


# --- Leads -------------------------------------------------------------------

leads = APIRouter(prefix="/leads", tags=["leads"])


@leads.get("", response_model=Page[LeadOut])
async def list_leads(
    q: ListQuery = Depends(list_query),
    status: list[LeadStatus] | None = Query(None),
    owner_id: uuid.UUID | None = None,
    source: str | None = Query(None, max_length=120),
    min_score: int | None = Query(None, ge=0, le=100),
    tag: str | None = Query(None, max_length=50),
    ctx: TenantContext = Depends(read),
):
    f = _tag_filter(Lead, tag)
    if status:
        f.append(Lead.status.in_(status))
    if owner_id:
        f.append(Lead.owner_id == owner_id)
    if source:
        f.append(func.lower(Lead.source) == source.lower())
    if min_score is not None:
        f.append(Lead.score >= min_score)
    items, total = await records.leads(ctx).page(q, f)
    return _page(LeadOut, items, total, q)


@leads.post("", response_model=LeadOut, status_code=201)
async def create_lead(body: LeadCreate, ctx: TenantContext = Depends(write)):
    data = _payload(body, not_null=("status", "score"))
    if data.get("status") == LeadStatus.CONVERTED:
        raise ValidationFailed("Use the convert action to convert a lead")
    data.setdefault("owner_id", ctx.user_id)
    await check_refs(ctx, data)
    obj = await records.leads(ctx).create(data)
    await _done(ctx)
    return obj


@leads.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    return await records.leads(ctx).get(lead_id)


@leads.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: uuid.UUID, body: LeadUpdate, ctx: TenantContext = Depends(write)):
    repo = records.leads(ctx)
    obj = await repo.get(lead_id)
    data = _payload(body, not_null=("name", "status", "score"))
    if "status" in data and (data["status"] == LeadStatus.CONVERTED) != (obj.status == LeadStatus.CONVERTED):
        raise ValidationFailed("Use the convert action to convert a lead")
    await check_refs(ctx, data)
    await repo.update(obj, data)
    await _done(ctx)
    return obj


@leads.post("/{lead_id}/convert", response_model=LeadConvertOut)
async def convert_lead(lead_id: uuid.UUID, body: LeadConvertIn, ctx: TenantContext = Depends(write)):
    lead = await records.leads(ctx).get(lead_id)
    lead, result = await lead_service.convert(ctx, lead, body)
    await _done(ctx)
    return LeadConvertOut(lead=LeadOut.model_validate(lead), **result)


@leads.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: uuid.UUID, ctx: TenantContext = Depends(delete)):
    repo = records.leads(ctx)
    await repo.delete(await repo.get(lead_id))
    await _done(ctx)
    return Response(status_code=204)


# --- Deals -------------------------------------------------------------------

deals = APIRouter(prefix="/deals", tags=["deals"])


@deals.get("", response_model=Page[DealOut])
async def list_deals(
    q: ListQuery = Depends(list_query),
    status: list[DealStatus] | None = Query(None),
    pipeline_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    closing_from: datetime | None = None,
    closing_to: datetime | None = None,
    tag: str | None = Query(None, max_length=50),
    ctx: TenantContext = Depends(read),
):
    f = _tag_filter(Deal, tag)
    if status:
        f.append(Deal.status.in_(status))
    for col, val in ((Deal.pipeline_id, pipeline_id), (Deal.stage_id, stage_id),
                     (Deal.owner_id, owner_id), (Deal.company_id, company_id),
                     (Deal.contact_id, contact_id)):
        if val:
            f.append(col == val)
    if closing_from:
        f.append(Deal.expected_close_date >= closing_from.date())
    if closing_to:
        f.append(Deal.expected_close_date <= closing_to.date())
    items, total = await records.deals(ctx).page(q, f)
    return _page(DealOut, items, total, q)


@deals.get("/board", response_model=BoardOut)
async def deal_board(pipeline_id: uuid.UUID | None = None, ctx: TenantContext = Depends(read)):
    return await deal_service.board(ctx, pipeline_id)


@deals.post("", response_model=DealOut, status_code=201)
async def create_deal(body: DealCreate, ctx: TenantContext = Depends(write)):
    deal = await deal_service.create_deal(ctx, _payload(body, not_null=("currency",)))
    await _done(ctx)
    return deal


@deals.get("/{deal_id}", response_model=DealOut)
async def get_deal(deal_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    return await records.deals(ctx).get(deal_id)


@deals.patch("/{deal_id}", response_model=DealOut)
async def update_deal(deal_id: uuid.UUID, body: DealUpdate, ctx: TenantContext = Depends(write)):
    deal = await records.deals(ctx).get(deal_id)
    data = _payload(body, not_null=("name", "amount", "currency", "pipeline_id", "stage_id", "probability"))
    await deal_service.update_deal(ctx, deal, data)
    await _done(ctx)
    return deal


@deals.post("/{deal_id}/move", response_model=DealOut)
async def move_deal(deal_id: uuid.UUID, body: DealMoveIn, ctx: TenantContext = Depends(write)):
    deal = await records.deals(ctx).get(deal_id)
    await deal_service.update_deal(ctx, deal, {"stage_id": body.stage_id})
    await _done(ctx)
    return deal


@deals.delete("/{deal_id}", status_code=204)
async def delete_deal(deal_id: uuid.UUID, ctx: TenantContext = Depends(delete)):
    repo = records.deals(ctx)
    await repo.delete(await repo.get(deal_id))
    await _done(ctx)
    return Response(status_code=204)


# --- Activities --------------------------------------------------------------

activities = APIRouter(prefix="/activities", tags=["activities"])


def _related_filters(model, company_id, contact_id, lead_id, deal_id) -> list:
    pairs = ((model.company_id, company_id), (model.contact_id, contact_id),
             (model.lead_id, lead_id), (model.deal_id, deal_id))
    return [col == val for col, val in pairs if val]


@activities.get("", response_model=Page[ActivityOut])
async def list_activities(
    q: ListQuery = Depends(list_query),
    type: list[ActivityType] | None = Query(None),
    status: ActivityStatus | None = None,
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    ctx: TenantContext = Depends(read),
):
    f = _related_filters(Activity, company_id, contact_id, lead_id, deal_id)
    if type:
        f.append(Activity.type.in_(type))
    if status:
        f.append(Activity.status == status)
    if occurred_from:
        f.append(Activity.occurred_at >= occurred_from)
    if occurred_to:
        f.append(Activity.occurred_at <= occurred_to)
    items, total = await records.activities(ctx).page(q, f)
    return _page(ActivityOut, items, total, q)


@activities.post("", response_model=ActivityOut, status_code=201)
async def create_activity(body: ActivityCreate, ctx: TenantContext = Depends(write)):
    data = _payload(body, not_null=("occurred_at",))
    if data.get("type") in (ActivityType.STAGE_CHANGE, ActivityType.SYSTEM):
        raise ValidationFailed("This activity type is recorded automatically")
    obj = await records.create_activity(ctx, data)
    await _done(ctx)
    return obj


@activities.get("/{activity_id}", response_model=ActivityOut)
async def get_activity(activity_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    return await records.activities(ctx).get(activity_id)


@activities.patch("/{activity_id}", response_model=ActivityOut)
async def update_activity(activity_id: uuid.UUID, body: ActivityUpdate, ctx: TenantContext = Depends(write)):
    repo = records.activities(ctx)
    obj = await repo.get(activity_id)
    data = _payload(body, not_null=("type", "status", "subject", "occurred_at"))
    if data.get("type") in (ActivityType.STAGE_CHANGE, ActivityType.SYSTEM):
        raise ValidationFailed("This activity type is recorded automatically")
    await check_refs(ctx, data)
    await repo.update(obj, data)
    await _done(ctx)
    return obj


@activities.delete("/{activity_id}", status_code=204)
async def delete_activity(activity_id: uuid.UUID, ctx: TenantContext = Depends(delete)):
    repo = records.activities(ctx)
    await repo.delete(await repo.get(activity_id))
    await _done(ctx)
    return Response(status_code=204)


# --- Tasks -------------------------------------------------------------------

tasks = APIRouter(prefix="/tasks", tags=["tasks"])


@tasks.get("", response_model=Page[TaskOut])
async def list_tasks(
    q: ListQuery = Depends(list_query),
    status: list[TaskStatus] | None = Query(None),
    priority: list[TaskPriority] | None = Query(None),
    assignee: Literal["me", "any"] | None = None,
    assignee_id: uuid.UUID | None = None,
    due: Literal["overdue", "today", "upcoming", "none"] | None = None,
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    tz: str = Query("Asia/Kolkata", max_length=64),
    ctx: TenantContext = Depends(read),
):
    f = _related_filters(Task, company_id, contact_id, lead_id, deal_id)
    if status:
        f.append(Task.status.in_(status))
    if priority:
        f.append(Task.priority.in_(priority))
    if assignee == "me":
        f.append(Task.assignee_id == ctx.user_id)
    elif assignee_id:
        f.append(Task.assignee_id == assignee_id)
    if due:
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationFailed("Unknown time zone") from exc
        now = datetime.now(UTC)
        start = datetime.combine(now.astimezone(zone).date(), time.min, zone).astimezone(UTC)
        end = start + timedelta(days=1)
        open_ = Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
        f += {
            "overdue": [open_, Task.due_at < now],
            "today": [Task.due_at >= start, Task.due_at < end],
            "upcoming": [open_, Task.due_at >= end],
            "none": [Task.due_at.is_(None)],
        }[due]
    items, total = await records.tasks(ctx).page(q, f)
    return _page(TaskOut, items, total, q)


@tasks.post("", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, ctx: TenantContext = Depends(write)):
    obj = await records.create_task(ctx, _payload(body, not_null=("status", "priority")))
    await _done(ctx)
    return obj


@tasks.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, ctx: TenantContext = Depends(read)):
    return await records.tasks(ctx).get(task_id)


@tasks.patch("/{task_id}", response_model=TaskOut)
async def update_task(task_id: uuid.UUID, body: TaskUpdate, ctx: TenantContext = Depends(write)):
    task = await records.tasks(ctx).get(task_id)
    await records.update_task(ctx, task, _payload(body, not_null=("title", "status", "priority")))
    await _done(ctx)
    return task


@tasks.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, ctx: TenantContext = Depends(write)):
    repo = records.tasks(ctx)
    task = await repo.get(task_id)
    if task.created_by_id != ctx.user_id and not ctx.can(Perm.CRM_DELETE):
        raise Forbidden("Only the creator or a manager can delete this task")
    await repo.delete(task)
    await _done(ctx)
    return Response(status_code=204)


# --- Notes -------------------------------------------------------------------

notes = APIRouter(prefix="/notes", tags=["notes"])


@notes.get("", response_model=Page[NoteOut])
async def list_notes(
    q: ListQuery = Depends(list_query),
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    ctx: TenantContext = Depends(read),
):
    f = _related_filters(Note, company_id, contact_id, lead_id, deal_id)
    if task_id:
        f.append(Note.task_id == task_id)
    items, total = await records.notes(ctx).page(q, f)
    return _page(NoteOut, items, total, q)


@notes.post("", response_model=NoteOut, status_code=201)
async def create_note(body: NoteCreate, ctx: TenantContext = Depends(write)):
    obj = await records.create_note(ctx, _payload(body))
    await _done(ctx)
    return obj


@notes.patch("/{note_id}", response_model=NoteOut)
async def update_note(note_id: uuid.UUID, body: NoteUpdate, ctx: TenantContext = Depends(write)):
    note = await records.notes(ctx).get(note_id)
    await records.update_note(ctx, note, body.body)
    await _done(ctx)
    return note


@notes.delete("/{note_id}", status_code=204)
async def delete_note(note_id: uuid.UUID, ctx: TenantContext = Depends(write)):
    note = await records.notes(ctx).get(note_id)
    await records.delete_note(ctx, note)
    await _done(ctx)
    return Response(status_code=204)


# --- Timeline ----------------------------------------------------------------

timeline_router = APIRouter(prefix="/timeline", tags=["timeline"])

_TIMELINE_REPOS = {
    "companies": ("company_id", records.companies),
    "contacts": ("contact_id", records.contacts),
    "leads": ("lead_id", records.leads),
    "deals": ("deal_id", records.deals),
}


@timeline_router.get("/{entity}/{entity_id}", response_model=list[TimelineItem])
async def entity_timeline(
    entity: Literal["companies", "contacts", "leads", "deals"],
    entity_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=200),
    ctx: TenantContext = Depends(read),
):
    field, repo = _TIMELINE_REPOS[entity]
    await repo(ctx).get(entity_id)  # 404 if missing or in another organization
    return await timeline.for_entity(ctx, field, entity_id, limit)


for sub in (companies, contacts, leads, deals, activities, tasks, notes, timeline_router):
    router.include_router(sub)
