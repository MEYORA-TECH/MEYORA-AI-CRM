import uuid
from datetime import date, datetime

from app.schemas.common import Money, OutputModel
from app.schemas.crm import ActivityOut, TaskOut


class LeadStats(OutputModel):
    total: int
    new_last_30_days: int
    new_status: int
    qualified: int
    converted: int


class StageSummary(OutputModel):
    stage_id: uuid.UUID
    name: str
    kind: str
    color: str
    count: int
    amount: Money


class PipelineStats(OutputModel):
    open_deals: int
    won_deals: int
    lost_deals: int
    pipeline_value: Money
    weighted_value: Money
    revenue_total: Money
    revenue_this_month: Money
    closing_this_month: int
    # Amounts above only include deals in the organization's default currency.
    other_currency_deals: int
    stages: list[StageSummary]


class TaskStats(OutputModel):
    due_today: int
    overdue: int
    open: int


class LeadFunnel(OutputModel):
    new: int = 0
    contacted: int = 0
    qualified: int = 0
    unqualified: int = 0
    converted: int = 0
    lost: int = 0


class FitBands(OutputModel):
    """Open leads (new, contacted, qualified) by fit score: 90+, 80-89, 70-79, below 70."""

    top: int
    high: int
    medium: int
    low: int


class Coverage(OutputModel):
    """How reachable the prospect companies are. Outreach partners are counted separately."""

    companies: int
    partners: int
    with_contacts: int
    with_decision_maker: int
    with_email: int


class Bucket(OutputModel):
    label: str
    count: int


class WeekActivity(OutputModel):
    week_start: date
    calls: int
    emails: int
    meetings: int
    linkedin: int
    other: int


class ContactNext(OutputModel):
    id: uuid.UUID
    name: str
    company_name: str | None
    score: int
    status: str
    industry: str | None
    priority: str | None
    has_email: bool
    has_phone: bool
    last_contact_at: datetime | None


class Insights(OutputModel):
    funnel: LeadFunnel
    fit: FitBands
    coverage: Coverage
    cities: list[Bucket]
    industries: list[Bucket]
    weeks: list[WeekActivity]
    contact_next: list[ContactNext]
    to_contact: int  # open leads with no completed activity in `stale_days`
    stale_deals: int  # open deals with no completed activity in `stale_days`
    stale_days: int


class DashboardOut(OutputModel):
    currency: str
    generated_at: datetime
    leads: LeadStats
    pipeline: PipelineStats
    tasks: TaskStats
    my_tasks: list[TaskOut]
    upcoming_activities: list[ActivityOut]
    insights: Insights
