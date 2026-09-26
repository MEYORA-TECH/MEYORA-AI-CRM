"""Dashboard figures, computed entirely in SQL from live CRM data."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, select

from app.auth.deps import TenantContext
from app.models import Activity, Company, Contact, Deal, Lead, Organization, Task
from app.models.enums import ActivityStatus, DealStatus, LeadStatus, TaskStatus
from app.schemas.crm import ActivityOut, CompanyOut, ContactOut, DealOut, TaskOut
from app.schemas.dashboard import DashboardOut, LeadStats, PipelineStats, StageSummary, TaskStats
from app.services import pipelines, records

_OPEN_TASK = Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])


async def build(ctx: TenantContext, tz_name: str) -> DashboardOut:
    s = ctx.session
    org_id = ctx.organization_id
    org = await s.get(Organization, org_id)
    currency = org.default_currency if org else "INR"

    tz = ZoneInfo(tz_name)
    now = datetime.now(UTC)
    local_today = now.astimezone(tz).date()
    day_start = datetime.combine(local_today, time.min, tz).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    month_start = datetime.combine(local_today.replace(day=1), time.min, tz).astimezone(UTC)
    thirty_days_ago = now - timedelta(days=30)

    live_lead = and_(Lead.organization_id == org_id, Lead.deleted_at.is_(None))
    lead_row = (
        await s.execute(
            select(
                func.count(Lead.id),
                func.count(Lead.id).filter(Lead.created_at >= thirty_days_ago),
                func.count(Lead.id).filter(Lead.status == LeadStatus.NEW),
                func.count(Lead.id).filter(Lead.status == LeadStatus.QUALIFIED),
                func.count(Lead.id).filter(Lead.status == LeadStatus.CONVERTED),
            ).where(live_lead)
        )
    ).one()

    live_deal = and_(Deal.organization_id == org_id, Deal.deleted_at.is_(None))
    in_currency = Deal.currency == currency
    zero = Decimal(0)
    deal_row = (
        await s.execute(
            select(
                func.count(Deal.id).filter(Deal.status == DealStatus.OPEN),
                func.count(Deal.id).filter(Deal.status == DealStatus.WON),
                func.count(Deal.id).filter(Deal.status == DealStatus.LOST),
                func.coalesce(func.sum(Deal.amount).filter(Deal.status == DealStatus.OPEN, in_currency), zero),
                func.coalesce(
                    func.sum(Deal.amount * Deal.probability / 100).filter(Deal.status == DealStatus.OPEN, in_currency),
                    zero,
                ),
                func.coalesce(func.sum(Deal.amount).filter(Deal.status == DealStatus.WON, in_currency), zero),
                func.coalesce(
                    func.sum(Deal.amount).filter(
                        Deal.status == DealStatus.WON, in_currency, Deal.closed_at >= month_start
                    ),
                    zero,
                ),
                func.count(Deal.id).filter(~in_currency),
                func.count(Deal.id).filter(
                    Deal.status == DealStatus.OPEN,
                    Deal.expected_close_date >= local_today.replace(day=1),
                    Deal.expected_close_date < (local_today.replace(day=28) + timedelta(days=4)).replace(day=1),
                ),
            ).where(live_deal)
        )
    ).one()

    task_row = (
        await s.execute(
            select(
                func.count(Task.id).filter(Task.due_at >= day_start, Task.due_at < day_end),
                func.count(Task.id).filter(Task.due_at < now),
                func.count(Task.id),
            ).where(Task.organization_id == org_id, Task.assignee_id == ctx.user_id, _OPEN_TASK)
        )
    ).one()

    due_today = await s.scalars(
        select(Task)
        .where(Task.organization_id == org_id, Task.assignee_id == ctx.user_id, _OPEN_TASK, Task.due_at < day_end)
        .order_by(Task.due_at.asc().nulls_last())
        .limit(8)
    )

    upcoming = await s.scalars(
        select(Activity)
        .where(
            Activity.organization_id == org_id, Activity.status == ActivityStatus.PLANNED, Activity.occurred_at >= now
        )
        .order_by(Activity.occurred_at.asc())
        .limit(6)
    )
    recent_activity = await s.scalars(
        select(Activity)
        .where(
            Activity.organization_id == org_id, Activity.status == ActivityStatus.COMPLETED, Activity.occurred_at <= now
        )
        .order_by(Activity.occurred_at.desc())
        .limit(8)
    )

    recent_companies = await s.scalars(records.companies(ctx).base().order_by(Company.created_at.desc()).limit(5))
    recent_contacts = await s.scalars(records.contacts(ctx).base().order_by(Contact.created_at.desc()).limit(5))
    recent_deals = await s.scalars(records.deals(ctx).base().order_by(Deal.created_at.desc()).limit(5))

    stages: list[StageSummary] = []
    pipeline_list = await pipelines.list_pipelines(ctx)
    if pipeline_list:
        default = pipeline_list[0]
        per_stage = {
            row.stage_id: row
            for row in (
                await s.execute(
                    select(
                        Deal.stage_id,
                        func.count(Deal.id).label("count"),
                        func.coalesce(func.sum(case((in_currency, Deal.amount), else_=zero)), zero).label("amount"),
                    )
                    .where(live_deal, Deal.pipeline_id == default.id)
                    .group_by(Deal.stage_id)
                )
            ).all()
        }
        stages = [
            StageSummary(
                stage_id=st.id,
                name=st.name,
                kind=st.kind,
                color=st.color,
                count=per_stage[st.id].count if st.id in per_stage else 0,
                amount=per_stage[st.id].amount if st.id in per_stage else zero,
            )
            for st in default.stages
        ]

    return DashboardOut(
        currency=currency,
        generated_at=now,
        leads=LeadStats(
            total=lead_row[0],
            new_last_30_days=lead_row[1],
            new_status=lead_row[2],
            qualified=lead_row[3],
            converted=lead_row[4],
        ),
        pipeline=PipelineStats(
            open_deals=deal_row[0],
            won_deals=deal_row[1],
            lost_deals=deal_row[2],
            pipeline_value=deal_row[3],
            weighted_value=deal_row[4],
            revenue_total=deal_row[5],
            revenue_this_month=deal_row[6],
            other_currency_deals=deal_row[7],
            closing_this_month=deal_row[8],
            stages=stages,
        ),
        tasks=TaskStats(due_today=task_row[0], overdue=task_row[1], open=task_row[2]),
        my_tasks=[TaskOut.model_validate(t) for t in due_today],
        upcoming_activities=[ActivityOut.model_validate(a) for a in upcoming],
        recent_activities=[ActivityOut.model_validate(a) for a in recent_activity],
        recent_companies=[CompanyOut.model_validate(c) for c in recent_companies],
        recent_contacts=[ContactOut.model_validate(c) for c in recent_contacts],
        recent_deals=[DealOut.model_validate(d) for d in recent_deals],
    )
