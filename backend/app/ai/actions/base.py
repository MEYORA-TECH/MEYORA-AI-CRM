"""Proposable actions: `prepare` validates and previews (writes nothing); `execute` runs after confirmation."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.ai.tools.base import ToolContext, ToolInputError
from app.auth.deps import TenantContext

HREF = {"company": "/companies", "contact": "/contacts", "lead": "/leads", "deal": "/deals", "task": "/tasks"}
LINKABLE = {"company": "company_id", "contact": "contact_id", "lead": "lead_id", "deal": "deal_id"}


@dataclass
class Proposal:
    title: str  # "Create task"
    summary: str  # one line, shown to the model and on the card
    payload: dict[str, Any]  # JSON-safe, fully resolved arguments for execute()
    changes: list[dict[str, Any]] = field(default_factory=list)  # [{field, old, new}]
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    target_version: str | None = None
    target_label: str | None = None
    kind: str = "crm"  # crm | email | linkedin
    email: dict[str, Any] | None = None  # draft for email actions (editable before sending)
    linkedin: dict[str, Any] | None = None  # draft for LinkedIn actions (sent by the user on LinkedIn)

    def card(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "changes": self.changes,
            "variant": self.kind,
            "email": self.email,
            "linkedin": self.linkedin,
            "target": {
                "type": self.target_type,
                "id": str(self.target_id) if self.target_id else None,
                "label": self.target_label,
                "href": f"{HREF[self.target_type]}/{self.target_id}"
                if self.target_type in HREF and self.target_id
                else None,
            },
        }


@dataclass
class Executed:
    summary: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None

    def as_dict(self) -> dict[str, Any]:
        href = f"{HREF[self.entity_type]}/{self.entity_id}" if self.entity_type in HREF and self.entity_id else None
        if self.entity_type == "email" and self.entity_id:
            href = f"/emails/{self.entity_id}"
        return {
            "summary": self.summary,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "href": href,
        }


@dataclass
class ActionSpec:
    name: str
    description: str
    args: type[BaseModel]
    prepare: Callable[[ToolContext, Any], Awaitable[Proposal]]
    execute: Callable[[TenantContext, dict[str, Any], dict[str, Any] | None], Awaitable[Executed]]
    # Current version of the target, to refuse actions on records changed since the proposal.
    version: Callable[[TenantContext, uuid.UUID], Awaitable[str | None]] | None = None


# --- Helpers shared by actions ---------------------------------------------------------


def resolve_about(ctx: ToolContext, ref: str | None) -> tuple[str, uuid.UUID, str] | None:
    """A company/contact/lead/deal ref → (type, id, name)."""
    if not ref:
        return None
    entry = ctx.working_set.refs.get(ref.strip().lower())
    if not entry or entry["type"] not in LINKABLE:
        raise ToolInputError(f"Unknown record '{ref}'. Search for it first so it has a ref.")
    return entry["type"], uuid.UUID(entry["id"]), entry["name"]


def parse_when(value: str | None, tz: str, *, default_hour: int = 10) -> datetime | None:
    """ISO date or datetime from the model → aware UTC datetime. A bare date means 10:00 local."""
    if not value:
        return None
    zone = ZoneInfo(tz)
    try:
        if len(value.strip()) == 10:
            d = date.fromisoformat(value.strip())
            return datetime.combine(d, time(default_hour), zone).astimezone(UTC)
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolInputError(f"'{value}' isn't a date. Use YYYY-MM-DD or an ISO date-time.") from exc
    return (dt if dt.tzinfo else dt.replace(tzinfo=zone)).astimezone(UTC)


def show_when(value: str | None, tz: str) -> str | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(ZoneInfo(tz)).strftime("%a %d %b %Y, %H:%M")


def change(field_: str, old: Any, new: Any) -> dict[str, Any]:
    return {"field": field_, "old": old, "new": new}


def version_of(obj) -> str | None:
    stamp = getattr(obj, "updated_at", None)
    return stamp.isoformat() if stamp else None
