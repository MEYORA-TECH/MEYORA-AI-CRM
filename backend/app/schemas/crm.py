"""Request/response schemas for CRM records.

Pattern per entity: `<X>Fields` holds every writable field as optional,
`<X>Create` makes the required ones mandatory, `<X>Update` is a partial update
(applied with `exclude_unset`), and `<X>Out` is the response.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import EmailStr, Field

from app.models.enums import (
    ActivityStatus,
    ActivityType,
    CompanyStatus,
    DealStatus,
    LeadStatus,
    TaskPriority,
    TaskStatus,
)
from app.schemas.common import (
    Currency,
    InputModel,
    LongText,
    Money,
    Name,
    OutputModel,
    Phone,
    ShortText,
    TaggedInput,
    Url,
)


class RecordOut(OutputModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaggedOut(RecordOut):
    tags: list[str]
    custom_fields: dict[str, Any]


# --- Companies -------------------------------------------------------------


class CompanyFields(TaggedInput):
    name: Name | None = None
    industry: ShortText | None = None
    website: Url | None = None
    phone: Phone | None = None
    email: EmailStr | None = None
    address: ShortText | None = None
    city: ShortText | None = None
    state: ShortText | None = None
    country: ShortText | None = None
    employee_count: int | None = Field(default=None, ge=0, le=10_000_000)
    annual_revenue: Money | None = Field(default=None, ge=0)
    description: LongText | None = None
    status: CompanyStatus | None = None
    owner_id: uuid.UUID | None = None


class CompanyCreate(CompanyFields):
    name: Name


class CompanyUpdate(CompanyFields):
    pass


class CompanyOut(TaggedOut):
    name: str
    industry: str | None
    website: str | None
    phone: str | None
    email: str | None
    address: str | None
    city: str | None
    state: str | None
    country: str | None
    employee_count: int | None
    annual_revenue: Money | None
    description: str | None
    status: CompanyStatus
    owner_id: uuid.UUID | None


class CompanyRef(OutputModel):
    id: uuid.UUID
    name: str


# --- Contacts --------------------------------------------------------------


class ContactFields(TaggedInput):
    first_name: Name | None = None
    last_name: ShortText | None = None
    job_title: ShortText | None = None
    company_id: uuid.UUID | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    linkedin_url: Url | None = None
    address: ShortText | None = None
    city: ShortText | None = None
    state: ShortText | None = None
    country: ShortText | None = None
    description: LongText | None = None
    owner_id: uuid.UUID | None = None


class ContactCreate(ContactFields):
    first_name: Name


class ContactUpdate(ContactFields):
    pass


class ContactOut(TaggedOut):
    first_name: str
    last_name: str | None
    full_name: str
    job_title: str | None
    company_id: uuid.UUID | None
    company: CompanyRef | None = None
    email: str | None
    phone: str | None
    linkedin_url: str | None
    address: str | None
    city: str | None
    state: str | None
    country: str | None
    description: str | None
    owner_id: uuid.UUID | None


# --- Leads -----------------------------------------------------------------


class LeadFields(TaggedInput):
    name: Name | None = None
    company_name: ShortText | None = None
    job_title: ShortText | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    source: ShortText | None = None
    industry: ShortText | None = None
    status: LeadStatus | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    description: LongText | None = None
    owner_id: uuid.UUID | None = None


class LeadCreate(LeadFields):
    name: Name


class LeadUpdate(LeadFields):
    pass


class LeadOut(TaggedOut):
    name: str
    company_name: str | None
    job_title: str | None
    email: str | None
    phone: str | None
    source: str | None
    industry: str | None
    status: LeadStatus
    score: int
    description: str | None
    owner_id: uuid.UUID | None
    converted_at: datetime | None
    converted_company_id: uuid.UUID | None
    converted_contact_id: uuid.UUID | None
    converted_deal_id: uuid.UUID | None


class LeadConvertIn(InputModel):
    # Company: link an existing one, or create one from the lead (default).
    company_id: uuid.UUID | None = None
    create_company: bool = True
    create_contact: bool = True
    create_deal: bool = True
    deal_name: Name | None = None
    deal_amount: Money | None = Field(default=None, ge=0)
    deal_currency: Currency | None = None
    pipeline_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None


class LeadConvertOut(OutputModel):
    lead: LeadOut
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    deal_id: uuid.UUID | None


# --- Deals -----------------------------------------------------------------


class DealFields(TaggedInput):
    name: Name | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    amount: Money | None = Field(default=None, ge=0, le=10**15)
    currency: Currency | None = None
    pipeline_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    source: ShortText | None = None
    description: LongText | None = None


class DealCreate(DealFields):
    name: Name


class DealUpdate(DealFields):
    pass


class DealMoveIn(InputModel):
    stage_id: uuid.UUID


class DealOut(TaggedOut):
    name: str
    company_id: uuid.UUID | None
    company: CompanyRef | None = None
    contact_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    amount: Money
    currency: str
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    status: DealStatus
    probability: int
    expected_close_date: date | None
    closed_at: datetime | None
    source: str | None
    description: str | None


class BoardColumn(OutputModel):
    stage_id: uuid.UUID
    name: str
    kind: str
    color: str
    probability: int
    count: int
    total_amount: Money
    deals: list[DealOut]


class BoardOut(OutputModel):
    pipeline_id: uuid.UUID
    columns: list[BoardColumn]


# --- Links shared by activities, tasks and notes ---------------------------


class RelatedFields(InputModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None


class RelatedOut(OutputModel):
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    deal_id: uuid.UUID | None


# --- Activities ------------------------------------------------------------


class ActivityFields(RelatedFields):
    type: ActivityType | None = None
    status: ActivityStatus | None = None
    subject: Name | None = None
    body: LongText | None = None
    occurred_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    outcome: ShortText | None = None


class ActivityCreate(ActivityFields):
    type: ActivityType
    subject: Name


class ActivityUpdate(ActivityFields):
    pass


class ActivityOut(RecordOut, RelatedOut):
    type: ActivityType
    status: ActivityStatus
    subject: str
    body: str | None
    occurred_at: datetime
    duration_minutes: int | None
    outcome: str | None
    actor_id: uuid.UUID | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")


# --- Tasks -----------------------------------------------------------------


class TaskFields(RelatedFields):
    title: Name | None = None
    description: LongText | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    assignee_id: uuid.UUID | None = None


class TaskCreate(TaskFields):
    title: Name


class TaskUpdate(TaskFields):
    pass


class TaskOut(RecordOut, RelatedOut):
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    completed_at: datetime | None
    assignee_id: uuid.UUID | None
    created_by_id: uuid.UUID | None


# --- Notes -----------------------------------------------------------------


class NoteCreate(RelatedFields):
    body: LongText = Field(min_length=1)
    task_id: uuid.UUID | None = None


class NoteUpdate(InputModel):
    body: LongText = Field(min_length=1)


class NoteOut(RecordOut, RelatedOut):
    body: str
    author_id: uuid.UUID | None
    task_id: uuid.UUID | None


# --- Timeline --------------------------------------------------------------


class TimelineItem(OutputModel):
    kind: str  # activity | task | note
    id: uuid.UUID
    at: datetime
    title: str
    body: str | None
    type: str | None
    status: str | None
    actor_id: uuid.UUID | None
