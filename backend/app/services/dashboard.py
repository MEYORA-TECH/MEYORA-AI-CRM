"""Dashboard figures, computed entirely in SQL from live CRM data."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, select, true

from app.auth.deps import TenantContext
from app.models import Activity, Deal, Lead, Organization, Task
from app.models.enums import ActivityStatus, DealStatus, LeadStatus, TaskStatus
from app.schemas.crm import ActivityOut, TaskOut
from app.schemas.dashboard import DashboardOut, LeadStats, PipelineStats, StageSummary, TaskStats
from app.services import insights, pipelines

_OPEN_TASK = Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])


async def build(ctx: TenantContext, tz_name: str) -> DashboardOut:
    s = ctx.session
    org_id = ctx.organization_id
    tz = ZoneInfo(tz_name)
    now = datetime.now(UTC)
    local_today = now.astimezone(tz).date()
    day_start = datetime.combine(local_today, time.min, tz).astimezone(UTC)
    day_end = day_start + timedelta(days=1)
    month_start = datetime.combine(local_today.replace(day=1), time.min, tz).astimezone(UTC)
    thirty_days_ago = now - timedelta(days=30)

    # All headline figures in one round trip: four single-row subqueries side by side.
    currency_q = select(func.coalesce(Organization.default_currency, "INR")).where(Organization.id == org_id)
    org_currency = currency_q.scalar_subquery()
    live_lead = and_(Lead.organization_id == org_id, Lead.deleted_at.is_(None))
    leads_q = select(
        func.count(Lead.id).label("l_total"),
        func.count(Lead.id).filter(Lead.created_at >= thirty_days_ago).label("l_recent"),
        func.count(Lead.id).filter(Lead.status == LeadStatus.NEW).label("l_new"),
        func.count(Lead.id).filter(Lead.status == LeadStatus.QUALIFIED).label("l_qualified"),
        func.count(Lead.id).filter(Lead.status == LeadStatus.CONVERTED).label("l_converted"),
    ).where(live_lead)

    live_deal = and_(Deal.organization_id == org_id, Deal.deleted_at.is_(None))
    in_currency = Deal.currency == org_currency
    zero = Decimal(0)
    deals_q = select(
        func.count(Deal.id).filter(Deal.status == DealStatus.OPEN).label("d_open"),
        func.count(Deal.id).filter(Deal.status == DealStatus.WON).label("d_won"),
        func.count(Deal.id).filter(Deal.status == DealStatus.LOST).label("d_lost"),
        func.coalesce(func.sum(Deal.amount).filter(Deal.status == DealStatus.OPEN, in_currency), zero).label("d_value"),
        func.coalesce(
            func.sum(Deal.amount * Deal.probability / 100).filter(Deal.status == DealStatus.OPEN, in_currency), zero
        ).label("d_weighted"),
        func.coalesce(
            func.sum(Deal.amount).filter(Deal.status == DealStatus.WON, in_currency), zero
        ).label("d_revenue"),
        func.coalesce(
            func.sum(Deal.amount).filter(
                Deal.status == DealStatus.WON, in_currency, Deal.closed_at >= month_start
            ),
            zero,
        ).label("d_revenue_month"),
        func.count(Deal.id).filter(~in_currency).label("d_other_currency"),
        func.count(Deal.id).filter(
            Deal.status == DealStatus.OPEN,
            Deal.expected_close_date >= local_today.replace(day=1),
            Deal.expected_close_date < (local_today.replace(day=28) + timedelta(days=4)).replace(day=1),
        ).label("d_closing"),
    ).where(live_deal)

    tasks_q = select(
        func.count(Task.id).filter(Task.due_at >= day_start, Task.due_at < day_end).label("t_today"),
        func.count(Task.id).filter(Task.due_at < now).label("t_overdue"),
        func.count(Task.id).label("t_open"),
    ).where(Task.organization_id == org_id, Task.assignee_id == ctx.user_id, _OPEN_TASK)

    lq, dq, tq = leads_q.subquery(), deals_q.subquery(), tasks_q.subquery()
    figures = (
        await s.execute(
            select(currency_q.scalar_subquery().label("currency"), *lq.c, *dq.c, *tq.c)
            # each side is exactly one row, so joining on TRUE just puts them side by side
            .select_from(lq.join(dq, true()).join(tq, true()))
        )
    ).one()
    currency = figures.currency or "INR"

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

    insight = await insights.build(s, org_id, tz_name, local_today - timedelta(days=local_today.weekday()))

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
            total=figures.l_total,
            new_last_30_days=figures.l_recent,
            new_status=figures.l_new,
            qualified=figures.l_qualified,
            converted=figures.l_converted,
        ),
        pipeline=PipelineStats(
            open_deals=figures.d_open,
            won_deals=figures.d_won,
            lost_deals=figures.d_lost,
            pipeline_value=figures.d_value,
            weighted_value=figures.d_weighted,
            revenue_total=figures.d_revenue,
            revenue_this_month=figures.d_revenue_month,
            other_currency_deals=figures.d_other_currency,
            closing_this_month=figures.d_closing,
            stages=stages,
        ),
        tasks=TaskStats(due_today=figures.t_today, overdue=figures.t_overdue, open=figures.t_open),
        my_tasks=[TaskOut.model_validate(t) for t in due_today],
        upcoming_activities=[ActivityOut.model_validate(a) for a in upcoming],
        insights=insight,
    )
