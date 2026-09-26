"""Read-only CRM tools. They go through the same tenant-scoped repositories as the UI."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.ai.tools.base import MAX_ROWS, Tool, ToolContext, ToolResult, rows_ui
from app.models import Activity, Company, Contact, Deal, Lead, Organization, PipelineStage, Task
from app.models.enums import DealStatus, LeadStatus, TaskStatus
from app.services import records, timeline
from app.services.crud import like_pattern


def _money(amount, currency: str) -> str:
    value = float(amount or 0)
    if currency == "INR":
        if value >= 1e7:
            return f"₹{value / 1e7:.1f}Cr"
        if value >= 1e5:
            return f"₹{value / 1e5:.1f}L"
        return f"₹{value:,.0f}"
    return f"{currency} {value:,.0f}"


def _ago(ts: datetime | None) -> str:
    if ts is None:
        return "never"
    days = (datetime.now(UTC) - ts).days
    return "today" if days <= 0 else f"{days}d ago"


def _ilike_any(q: str | None, *cols):
    return [or_(*[c.ilike(like_pattern(q), escape="\\") for c in cols])] if q else []


def _last_activity(field):
    """Correlated subquery: newest completed activity for a record."""
    return (
        select(func.max(Activity.occurred_at))
        .where(getattr(Activity, field) == field_owner(field).id, Activity.status == "completed")
        .correlate(field_owner(field))
        .scalar_subquery()
    )


def field_owner(field):
    return {"company_id": Company, "contact_id": Contact, "lead_id": Lead, "deal_id": Deal}[field]


async def _timeline_lines(ctx: ToolContext, field, entity_id, limit=6) -> list[str]:
    items = await timeline.for_entity(ctx.tenant, field, entity_id, limit=limit)
    return [
        f"- {i.at:%Y-%m-%d} {i.kind}{'/' + i.type if i.type else ''}: {i.title}"
        + (f" — {i.body[:160]}" if i.body else "")
        for i in items
    ]


# --- Companies ---------------------------------------------------------------


class SearchCompanies(BaseModel):
    query: str | None = Field(None, description="Name, email, website, city or industry text")
    industry: str | None = None
    city: str | None = None
    status: Literal["prospect", "active", "customer", "churned", "inactive"] | None = None
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_companies(ctx: ToolContext, a: SearchCompanies) -> ToolResult:
    repo = records.companies(ctx.tenant)
    stmt = repo.base()
    for cond in _ilike_any(a.query, Company.name, Company.email, Company.website, Company.city, Company.industry):
        stmt = stmt.where(cond)
    if a.industry:
        stmt = stmt.where(Company.industry.ilike(like_pattern(a.industry), escape="\\"))
    if a.city:
        stmt = stmt.where(Company.city.ilike(like_pattern(a.city), escape="\\"))
    if a.status:
        stmt = stmt.where(Company.status == a.status)
    total = await ctx.tenant.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(await ctx.tenant.session.scalars(stmt.order_by(Company.updated_at.desc()).limit(a.limit)))

    lines, ui_rows = [], []
    for c in rows:
        ref = ctx.working_set.ref_for("company", c.id, c.name)
        lines.append(f"{ref}: {c.name} · {c.industry or '-'} · {c.city or '-'} · {c.status}")
        ui_rows.append(
            {
                "id": str(c.id),
                "title": c.name,
                "subtitle": " · ".join(filter(None, [c.industry, c.city])),
                "badge": c.status,
            }
        )
    head = f"{total} compan{'y' if total == 1 else 'ies'} found" + (
        f", showing {len(rows)}" if total > len(rows) else ""
    )
    return ToolResult(summary="\n".join([head, *lines]), ui=rows_ui("company", ui_rows, total, "Companies"))


class GetRecord(BaseModel):
    ref: str = Field(description="Short ref from a search result (e.g. c1) or an ID")


async def get_company(ctx: ToolContext, a: GetRecord) -> ToolResult:
    cid = ctx.working_set.resolve("company", a.ref)
    c = await records.companies(ctx.tenant).get(cid)
    s = ctx.tenant.session
    contacts = await s.scalar(
        select(func.count(Contact.id)).where(Contact.company_id == cid, Contact.deleted_at.is_(None))
    )
    open_deals = list(
        await s.scalars(
            records.deals(ctx.tenant).base().where(Deal.company_id == cid, Deal.status == DealStatus.OPEN).limit(5)
        )
    )
    ref = ctx.working_set.ref_for("company", c.id, c.name)
    deal_lines = [
        f"  {ctx.working_set.ref_for('deal', d.id, d.name)}: {d.name} {_money(d.amount, d.currency)} ({d.probability}%)"
        for d in open_deals
    ]
    lines = [
        f"{ref}: {c.name} — status {c.status}, industry {c.industry or '-'}, {c.city or '-'}, {c.country or '-'}",
        f"website {c.website or '-'} · employees {c.employee_count or '-'} · contacts {contacts}",
        f"description: {(c.description or '-')[:400]}",
        f"open deals ({len(open_deals)}):",
        *deal_lines,
        "recent history:",
        *(await _timeline_lines(ctx, "company_id", cid)),
    ]
    return ToolResult(
        summary="\n".join(lines),
        ui=rows_ui(
            "company",
            [{"id": str(c.id), "title": c.name, "subtitle": c.industry or "", "badge": c.status}],
            1,
            "Company",
        ),
    )


# --- Contacts ----------------------------------------------------------------


class SearchContacts(BaseModel):
    query: str | None = Field(None, description="Name, email, phone or job title text")
    company_ref: str | None = Field(None, description="Only contacts at this company (ref or ID)")
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_contacts(ctx: ToolContext, a: SearchContacts) -> ToolResult:
    repo = records.contacts(ctx.tenant)
    stmt = repo.base()
    for cond in _ilike_any(
        a.query, Contact.first_name, Contact.last_name, Contact.email, Contact.phone, Contact.job_title
    ):
        stmt = stmt.where(cond)
    if a.company_ref:
        stmt = stmt.where(Contact.company_id == ctx.working_set.resolve("company", a.company_ref))
    total = await ctx.tenant.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    last = _last_activity("contact_id").label("last_at")
    rows = (
        await ctx.tenant.session.execute(stmt.add_columns(last).order_by(Contact.updated_at.desc()).limit(a.limit))
    ).all()
    lines, ui_rows = [], []
    for c, last_at in rows:
        ref = ctx.working_set.ref_for("contact", c.id, c.full_name)
        company = c.company.name if c.company else "-"
        lines.append(
            f"{ref}: {c.full_name} · {c.job_title or '-'} at {company} · {c.email or '-'} · last contact {_ago(last_at)}"
        )
        ui_rows.append(
            {
                "id": str(c.id),
                "title": c.full_name,
                "subtitle": " · ".join(filter(None, [c.job_title, company if c.company else None])),
            }
        )
    return ToolResult(
        summary="\n".join([f"{total} contact(s) found", *lines]), ui=rows_ui("contact", ui_rows, total, "Contacts")
    )


async def get_contact(ctx: ToolContext, a: GetRecord) -> ToolResult:
    cid = ctx.working_set.resolve("contact", a.ref)
    c = await records.contacts(ctx.tenant).get(cid)
    ref = ctx.working_set.ref_for("contact", c.id, c.full_name)
    company = (
        f"{ctx.working_set.ref_for('company', c.company.id, c.company.name)} {c.company.name}" if c.company else "-"
    )
    lines = [
        f"{ref}: {c.full_name} — {c.job_title or '-'} at {company}",
        f"email {c.email or '-'} · phone {c.phone or '-'} · {c.city or '-'}",
        f"background: {(c.description or '-')[:400]}",
        "recent history:",
        *(await _timeline_lines(ctx, "contact_id", cid, limit=8)),
    ]
    return ToolResult(
        summary="\n".join(lines),
        ui=rows_ui("contact", [{"id": str(c.id), "title": c.full_name, "subtitle": c.job_title or ""}], 1, "Contact"),
    )


# --- Leads -------------------------------------------------------------------


class SearchLeads(BaseModel):
    query: str | None = Field(None, description="Name, company, email, industry or source text")
    statuses: list[Literal["new", "contacted", "qualified", "unqualified", "converted", "lost"]] | None = None
    min_score: int | None = Field(None, ge=0, le=100)
    not_contacted_days: int | None = Field(
        None, ge=1, le=365, description="Only leads with no completed activity in this many days"
    )
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_leads(ctx: ToolContext, a: SearchLeads) -> ToolResult:
    stmt = records.leads(ctx.tenant).base()
    for cond in _ilike_any(a.query, Lead.name, Lead.company_name, Lead.email, Lead.industry, Lead.source):
        stmt = stmt.where(cond)
    if a.statuses:
        stmt = stmt.where(Lead.status.in_(a.statuses))
    if a.min_score is not None:
        stmt = stmt.where(Lead.score >= a.min_score)
    last = _last_activity("lead_id")
    if a.not_contacted_days:
        cutoff = datetime.now(UTC) - timedelta(days=a.not_contacted_days)
        stmt = stmt.where(or_(last.is_(None), last < cutoff))
    total = await ctx.tenant.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await ctx.tenant.session.execute(
            stmt.add_columns(last.label("last_at")).order_by(Lead.score.desc(), Lead.created_at.desc()).limit(a.limit)
        )
    ).all()
    lines, ui_rows = [], []
    for lead, last_at in rows:
        ref = ctx.working_set.ref_for("lead", lead.id, lead.name)
        lines.append(
            f"{ref}: {lead.name} · {lead.company_name or '-'} · {lead.status} · score {lead.score} · source {lead.source or '-'} · last contact {_ago(last_at)}"
        )
        ui_rows.append(
            {
                "id": str(lead.id),
                "title": lead.name,
                "subtitle": " · ".join(filter(None, [lead.company_name, lead.source])),
                "badge": lead.status,
            }
        )
    return ToolResult(
        summary="\n".join([f"{total} lead(s) found", *lines]), ui=rows_ui("lead", ui_rows, total, "Leads")
    )


async def get_lead(ctx: ToolContext, a: GetRecord) -> ToolResult:
    lid = ctx.working_set.resolve("lead", a.ref)
    lead = await records.leads(ctx.tenant).get(lid)
    ref = ctx.working_set.ref_for("lead", lead.id, lead.name)
    lines = [
        f"{ref}: {lead.name} — {lead.job_title or '-'} at {lead.company_name or '-'} · status {lead.status} · score {lead.score}",
        f"email {lead.email or '-'} · phone {lead.phone or '-'} · industry {lead.industry or '-'} · source {lead.source or '-'}",
        f"notes: {(lead.description or '-')[:400]}",
        "recent history:",
        *(await _timeline_lines(ctx, "lead_id", lid)),
    ]
    return ToolResult(
        summary="\n".join(lines),
        ui=rows_ui(
            "lead",
            [{"id": str(lead.id), "title": lead.name, "subtitle": lead.company_name or "", "badge": lead.status}],
            1,
            "Lead",
        ),
    )


# --- Deals -------------------------------------------------------------------


class SearchDeals(BaseModel):
    query: str | None = Field(None, description="Deal name or source text")
    statuses: list[Literal["open", "won", "lost"]] | None = Field(None, description="Default: all")
    stage: str | None = Field(None, description="Stage name, e.g. Proposal")
    company_ref: str | None = None
    company_industry: str | None = Field(None, description="Only deals whose company is in this industry")
    closing_from: date | None = None
    closing_to: date | None = None
    inactive_days: int | None = Field(
        None, ge=1, le=365, description="Only deals with no completed activity in this many days"
    )
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_deals(ctx: ToolContext, a: SearchDeals) -> ToolResult:
    s = ctx.tenant.session
    stmt = records.deals(ctx.tenant).base()
    for cond in _ilike_any(a.query, Deal.name, Deal.source):
        stmt = stmt.where(cond)
    if a.statuses:
        stmt = stmt.where(Deal.status.in_(a.statuses))
    if a.stage:
        stmt = stmt.join(PipelineStage, PipelineStage.id == Deal.stage_id).where(
            PipelineStage.name.ilike(a.stage.strip())
        )
    if a.company_ref:
        stmt = stmt.where(Deal.company_id == ctx.working_set.resolve("company", a.company_ref))
    if a.company_industry:
        stmt = stmt.join(Company, Company.id == Deal.company_id).where(
            Company.industry.ilike(like_pattern(a.company_industry), escape="\\")
        )
    if a.closing_from:
        stmt = stmt.where(Deal.expected_close_date >= a.closing_from)
    if a.closing_to:
        stmt = stmt.where(Deal.expected_close_date <= a.closing_to)
    last = _last_activity("deal_id")
    if a.inactive_days:
        stmt = stmt.where(or_(last.is_(None), last < datetime.now(UTC) - timedelta(days=a.inactive_days)))

    total = await s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await s.execute(stmt.add_columns(last.label("last_at")).order_by(Deal.amount.desc()).limit(a.limit))).all()
    stage_names = dict(
        (
            await s.execute(
                select(PipelineStage.id, PipelineStage.name).where(
                    PipelineStage.organization_id == ctx.tenant.organization_id
                )
            )
        ).all()
    )
    lines, ui_rows = [], []
    for d, last_at in rows:
        ref = ctx.working_set.ref_for("deal", d.id, d.name)
        company = d.company.name if d.company else "-"
        close = d.expected_close_date.isoformat() if d.expected_close_date else "-"
        lines.append(
            f"{ref}: {d.name} · {company} · {_money(d.amount, d.currency)} · {stage_names.get(d.stage_id, '?')} ({d.probability}%) · {d.status} · close {close} · last activity {_ago(last_at)}"
        )
        ui_rows.append(
            {
                "id": str(d.id),
                "title": d.name,
                "subtitle": f"{company} · {stage_names.get(d.stage_id, '')}",
                "value": _money(d.amount, d.currency),
                "badge": d.status,
            }
        )
    return ToolResult(
        summary="\n".join([f"{total} deal(s) found", *lines]), ui=rows_ui("deal", ui_rows, total, "Deals")
    )


async def get_deal(ctx: ToolContext, a: GetRecord) -> ToolResult:
    did = ctx.working_set.resolve("deal", a.ref)
    d = await records.deals(ctx.tenant).get(did)
    stage = await ctx.tenant.session.get(PipelineStage, d.stage_id)
    ref = ctx.working_set.ref_for("deal", d.id, d.name)
    company = (
        f"{ctx.working_set.ref_for('company', d.company.id, d.company.name)} {d.company.name}" if d.company else "-"
    )
    lines = [
        f"{ref}: {d.name} — {_money(d.amount, d.currency)} · stage {stage.name if stage else '?'} ({d.probability}%) · {d.status}",
        f"company {company} · expected close {d.expected_close_date or '-'} · source {d.source or '-'} · created {d.created_at:%Y-%m-%d}",
        f"description: {(d.description or '-')[:400]}",
        "recent history:",
        *(await _timeline_lines(ctx, "deal_id", did, limit=8)),
    ]
    return ToolResult(
        summary="\n".join(lines),
        ui=rows_ui(
            "deal",
            [
                {
                    "id": str(d.id),
                    "title": d.name,
                    "subtitle": d.company.name if d.company else "",
                    "value": _money(d.amount, d.currency),
                    "badge": d.status,
                }
            ],
            1,
            "Deal",
        ),
    )


# --- Tasks & activities --------------------------------------------------------


class SearchTasks(BaseModel):
    due: Literal["overdue", "today", "upcoming", "any"] = "any"
    assignee: Literal["me", "anyone"] = "me"
    include_completed: bool = False
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_tasks(ctx: ToolContext, a: SearchTasks) -> ToolResult:
    stmt = records.tasks(ctx.tenant).base()
    open_ = Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
    if not a.include_completed:
        stmt = stmt.where(open_)
    if a.assignee == "me":
        stmt = stmt.where(Task.assignee_id == ctx.tenant.user_id)
    now = datetime.now(UTC)
    zone = ZoneInfo(ctx.timezone)
    start = datetime.combine(now.astimezone(zone).date(), time.min, zone).astimezone(UTC)
    end = start + timedelta(days=1)
    if a.due == "overdue":
        stmt = stmt.where(open_, Task.due_at < now)
    elif a.due == "today":
        stmt = stmt.where(Task.due_at >= start, Task.due_at < end)
    elif a.due == "upcoming":
        stmt = stmt.where(Task.due_at >= end)
    total = await ctx.tenant.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(await ctx.tenant.session.scalars(stmt.order_by(Task.due_at.asc().nulls_last()).limit(a.limit)))
    lines, ui_rows = [], []
    for t in rows:
        ref = ctx.working_set.ref_for("task", t.id, t.title)
        due = t.due_at.astimezone(zone).strftime("%Y-%m-%d %H:%M") if t.due_at else "no due date"
        lines.append(f"{ref}: {t.title} · {t.priority} · {t.status} · due {due}")
        ui_rows.append({"id": str(t.id), "title": t.title, "subtitle": f"Due {due}", "badge": t.priority})
    return ToolResult(summary="\n".join([f"{total} task(s)", *lines]), ui=rows_ui("task", ui_rows, total, "Tasks"))


class SearchActivities(BaseModel):
    types: list[Literal["call", "meeting", "email", "note", "follow_up", "stage_change", "system"]] | None = None
    since_days: int = Field(14, ge=1, le=365)
    company_ref: str | None = None
    contact_ref: str | None = None
    deal_ref: str | None = None
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_activities(ctx: ToolContext, a: SearchActivities) -> ToolResult:
    stmt = (
        records.activities(ctx.tenant)
        .base()
        .where(Activity.occurred_at >= datetime.now(UTC) - timedelta(days=a.since_days))
    )
    if a.types:
        stmt = stmt.where(Activity.type.in_(a.types))
    for kind, field, value in (
        ("company", "company_id", a.company_ref),
        ("contact", "contact_id", a.contact_ref),
        ("deal", "deal_id", a.deal_ref),
    ):
        if value:
            stmt = stmt.where(getattr(Activity, field) == ctx.working_set.resolve(kind, value))
    total = await ctx.tenant.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(await ctx.tenant.session.scalars(stmt.order_by(Activity.occurred_at.desc()).limit(a.limit)))
    lines = [
        f"- {x.occurred_at:%Y-%m-%d} {x.type} ({x.status}): {x.subject}" + (f" — {x.body[:140]}" if x.body else "")
        for x in rows
    ]
    ui_rows = [{"id": str(x.id), "title": x.subject, "subtitle": f"{x.type} · {x.occurred_at:%d %b}"} for x in rows]
    return ToolResult(
        summary="\n".join([f"{total} activit{'y' if total == 1 else 'ies'} in the last {a.since_days} days", *lines]),
        ui=rows_ui("activity", ui_rows, total, "Activities"),
    )


# --- Pipeline summary ------------------------------------------------------------


class NoArgs(BaseModel):
    pass


async def pipeline_summary(ctx: ToolContext, _: NoArgs) -> ToolResult:
    s = ctx.tenant.session
    org = ctx.tenant.organization_id
    currency = (await s.get(Organization, org)).default_currency
    # Amounts only add up within one currency, so totals use the organization's default.
    live = (Deal.organization_id == org, Deal.deleted_at.is_(None), Deal.currency == currency)
    by_stage = (
        await s.execute(
            select(
                PipelineStage.name, PipelineStage.position, func.count(Deal.id), func.coalesce(func.sum(Deal.amount), 0)
            )
            .join(Deal, Deal.stage_id == PipelineStage.id)
            .where(*live, Deal.status == DealStatus.OPEN)
            .group_by(PipelineStage.name, PipelineStage.position)
            .order_by(PipelineStage.position)
        )
    ).all()
    won_month = await s.scalar(
        select(func.coalesce(func.sum(Deal.amount), 0)).where(
            *live,
            Deal.status == DealStatus.WON,
            Deal.closed_at >= datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0),
        )
    )
    leads_new = await s.scalar(
        select(func.count(Lead.id)).where(
            Lead.organization_id == org, Lead.deleted_at.is_(None), Lead.status == LeadStatus.NEW
        )
    )
    overdue = await s.scalar(
        select(func.count(Task.id)).where(
            Task.organization_id == org,
            Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
            Task.due_at < datetime.now(UTC),
        )
    )
    lines = [f"open pipeline by stage ({currency} deals only):"]
    lines += [f"- {name}: {count} deal(s), {_money(total, currency)}" for name, _, count, total in by_stage] or [
        "- no open deals"
    ]
    lines += [
        f"won this month: {_money(won_month, currency)}",
        f"new leads awaiting qualification: {leads_new}",
        f"overdue tasks (everyone): {overdue}",
    ]
    return ToolResult(summary="\n".join(lines))


TOOLS: list[Tool] = [
    Tool(
        "search_companies",
        "companies",
        "Find companies by text, industry, city or status.",
        SearchCompanies,
        search_companies,
    ),
    Tool(
        "get_company",
        "companies",
        "Full details of one company: open deals and recent history.",
        GetRecord,
        get_company,
    ),
    Tool(
        "search_contacts",
        "contacts",
        "Find contacts by text or company; includes last contact date.",
        SearchContacts,
        search_contacts,
    ),
    Tool(
        "get_contact",
        "contacts",
        "One contact with recent history (calls, meetings, notes, tasks).",
        GetRecord,
        get_contact,
    ),
    Tool(
        "search_leads",
        "leads",
        "Find leads by text, status, score, or not contacted in N days.",
        SearchLeads,
        search_leads,
    ),
    Tool("get_lead", "leads", "One lead with notes and history.", GetRecord, get_lead),
    Tool(
        "search_deals",
        "deals",
        "Find deals by stage, status, company, industry, close date, or inactivity.",
        SearchDeals,
        search_deals,
    ),
    Tool("get_deal", "deals", "One deal with stage, amount and recent history.", GetRecord, get_deal),
    Tool(
        "search_tasks",
        "tasks",
        "List tasks: overdue, due today or upcoming; mine or everyone's.",
        SearchTasks,
        search_tasks,
    ),
    Tool(
        "search_activities",
        "activities",
        "Recent calls, meetings, emails and notes, optionally for one record.",
        SearchActivities,
        search_activities,
    ),
    Tool(
        "pipeline_summary",
        "deals",
        "Totals: open pipeline by stage, won this month, new leads, overdue tasks.",
        NoArgs,
        pipeline_summary,
    ),
]

BY_NAME = {t.name: t for t in TOOLS}
