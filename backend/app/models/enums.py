from enum import StrEnum


class CompanyStatus(StrEnum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    CUSTOMER = "customer"
    CHURNED = "churned"
    INACTIVE = "inactive"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    CONVERTED = "converted"
    LOST = "lost"


class StageKind(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class DealStatus(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class ActivityType(StrEnum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    NOTE = "note"
    TASK = "task"
    FOLLOW_UP = "follow_up"
    STAGE_CHANGE = "stage_change"
    SYSTEM = "system"


class ActivityStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ActorType(StrEnum):
    USER = "user"
    AI = "ai"
    SYSTEM = "system"
