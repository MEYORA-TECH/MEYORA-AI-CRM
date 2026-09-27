"""Tenant-owned CRM tables. All are protected by row-level security."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CrmRecord, TenantOwned, Timestamps, UUIDPk, str_enum
from app.models.enums import (
    ActivityStatus,
    ActivityType,
    ActorType,
    CompanyStatus,
    DealStatus,
    LeadStatus,
    StageKind,
    TaskPriority,
    TaskStatus,
)

LIVE = text("deleted_at IS NULL")


def _user_fk(**kw) -> Any:
    return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), **kw)


def _ref_fk(table: str) -> Any:
    return mapped_column(ForeignKey(f"{table}.id", ondelete="SET NULL"), index=True)


def _trgm(name: str, column: str) -> Index:
    return Index(name, column, postgresql_using="gin", postgresql_ops={column: "gin_trgm_ops"})


def _tags(table: str) -> Index:
    return Index(f"ix_{table}_tags", "tags", postgresql_using="gin")


class Company(CrmRecord, Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_org_live_updated", "organization_id", "updated_at", postgresql_where=LIVE),
        _trgm("ix_companies_name_trgm", "name"),
        _tags("companies"),
    )

    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CompanyStatus] = mapped_column(
        str_enum(CompanyStatus, "company_status"), default=CompanyStatus.PROSPECT
    )
    owner_id: Mapped[uuid.UUID | None] = _user_fk(index=True)


class Contact(CrmRecord, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_org_live_updated", "organization_id", "updated_at", postgresql_where=LIVE),
        Index("ix_contacts_org_email", "organization_id", text("lower(email)")),
        _trgm("ix_contacts_first_name_trgm", "first_name"),
        _trgm("ix_contacts_last_name_trgm", "last_name"),
        _tags("contacts"),
    )

    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    job_title: Mapped[str | None] = mapped_column(String(200))
    company_id: Mapped[uuid.UUID | None] = _ref_fk("companies")
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = _user_fk(index=True)

    company: Mapped[Company | None] = relationship(lazy="raise")

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p)


class Lead(CrmRecord, Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_org_status", "organization_id", "status", postgresql_where=LIVE),
        _trgm("ix_leads_name_trgm", "name"),
        _trgm("ix_leads_company_name_trgm", "company_name"),
        _tags("leads"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
    )

    name: Mapped[str] = mapped_column(String(200))
    company_name: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(120))
    industry: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[LeadStatus] = mapped_column(str_enum(LeadStatus, "lead_status"), default=LeadStatus.NEW)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = _user_fk(index=True)
    converted_at: Mapped[datetime | None]
    converted_company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    converted_contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    converted_deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL", use_alter=True)
    )


class Pipeline(UUIDPk, Timestamps, TenantOwned, Base):
    __tablename__ = "pipelines"

    name: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(default=False, server_default="false")

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="pipeline",
        order_by="PipelineStage.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PipelineStage(UUIDPk, Timestamps, TenantOwned, Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (CheckConstraint("probability BETWEEN 0 AND 100", name="probability_range"),)

    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    probability: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[StageKind] = mapped_column(str_enum(StageKind, "stage_kind"), default=StageKind.OPEN)
    color: Mapped[str] = mapped_column(String(20), default="slate")

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages", lazy="raise")


class Deal(CrmRecord, Base):
    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_org_status", "organization_id", "status", postgresql_where=LIVE),
        Index("ix_deals_org_stage", "organization_id", "stage_id", postgresql_where=LIVE),
        Index("ix_deals_org_close", "organization_id", "expected_close_date", postgresql_where=LIVE),
        _trgm("ix_deals_name_trgm", "name"),
        _tags("deals"),
        CheckConstraint("probability BETWEEN 0 AND 100", name="probability_range"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[uuid.UUID | None] = _ref_fk("companies")
    contact_id: Mapped[uuid.UUID | None] = _ref_fk("contacts")
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    owner_id: Mapped[uuid.UUID | None] = _user_fk(index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal(0), server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id", ondelete="RESTRICT"))
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id", ondelete="RESTRICT"))
    status: Mapped[DealStatus] = mapped_column(str_enum(DealStatus, "deal_status"), default=DealStatus.OPEN)
    probability: Mapped[int] = mapped_column(Integer, default=0)
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[datetime | None]
    source: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company | None] = relationship(lazy="raise")


class _Related:
    """Optional links from an activity, task or note to the CRM records it concerns."""

    company_id: Mapped[uuid.UUID | None] = _ref_fk("companies")
    contact_id: Mapped[uuid.UUID | None] = _ref_fk("contacts")
    lead_id: Mapped[uuid.UUID | None] = _ref_fk("leads")
    deal_id: Mapped[uuid.UUID | None] = _ref_fk("deals")


class Activity(UUIDPk, Timestamps, TenantOwned, _Related, Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_org_occurred", "organization_id", "occurred_at"),)

    type: Mapped[ActivityType] = mapped_column(str_enum(ActivityType, "activity_type"))
    status: Mapped[ActivityStatus] = mapped_column(
        str_enum(ActivityStatus, "activity_status"), default=ActivityStatus.COMPLETED
    )
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime]
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(300))
    actor_id: Mapped[uuid.UUID | None] = _user_fk()
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")


class Task(UUIDPk, Timestamps, TenantOwned, _Related, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_org_status_due", "organization_id", "status", "due_at"),
        Index("ix_tasks_org_assignee", "organization_id", "assignee_id", "status"),
    )

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(str_enum(TaskStatus, "task_status"), default=TaskStatus.TODO)
    priority: Mapped[TaskPriority] = mapped_column(str_enum(TaskPriority, "task_priority"), default=TaskPriority.MEDIUM)
    due_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    assignee_id: Mapped[uuid.UUID | None] = _user_fk()
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class Note(UUIDPk, Timestamps, TenantOwned, _Related, Base):
    __tablename__ = "notes"

    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = _user_fk()
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)


class AuditLog(UUIDPk, TenantOwned, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_entity", "organization_id", "entity_type", "entity_id"),
    )

    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk()
    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "actor_type"), default=ActorType.USER)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None]
    changes: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(64))


# Every table listed here gets ENABLE + FORCE ROW LEVEL SECURITY in migrations.
RLS_TABLES = [
    t.__tablename__ for t in (Company, Contact, Lead, Pipeline, PipelineStage, Deal, Activity, Task, Note, AuditLog)
] + [
    "ai_conversations",
    "ai_messages",
    "ai_usage_logs",
    "ai_memories",
    "knowledge_chunks",
    "ai_conversation_summaries",
    "mail_accounts",
    "email_threads",
    "email_messages",
    "web_search_cache",
    "web_search_logs",
    "research_briefs",
    "ai_actions",
    "organization_api_keys",
]
