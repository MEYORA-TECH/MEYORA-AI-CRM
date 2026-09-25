import uuid
from datetime import datetime

from app.schemas.common import Money, OutputModel
from app.schemas.crm import ActivityOut, CompanyOut, ContactOut, DealOut, TaskOut


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


class DashboardOut(OutputModel):
    currency: str
    generated_at: datetime
    leads: LeadStats
    pipeline: PipelineStats
    tasks: TaskStats
    my_tasks: list[TaskOut]
    upcoming_activities: list[ActivityOut]
    recent_activities: list[ActivityOut]
    recent_companies: list[CompanyOut]
    recent_contacts: list[ContactOut]
    recent_deals: list[DealOut]
