"""LinkedIn actions. Meyora can't send on LinkedIn (its API doesn't allow it), so:

- draft_linkedin_message proposes an editable draft; the user copies it, sends it on
  LinkedIn, then confirms "Log as sent", which records a LinkedIn activity.
- save_linkedin_url proposes saving a public LinkedIn page found with find_linkedin.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.actions.base import ActionSpec, Executed, Proposal, change
from app.ai.tools.base import ToolContext, ToolInputError
from app.auth.deps import TenantContext
from app.core.errors import ValidationFailed
from app.services import linkedin, records

KIND_LABEL = {"connection_note": "connection request", "message": "message", "inmail": "InMail"}


def _resolve(ctx: ToolContext, ref: str, allowed: tuple[str, ...]) -> tuple[str, uuid.UUID]:
    entry = ctx.working_set.refs.get((ref or "").strip().lower())
    if not entry or entry["type"] not in allowed:
        raise ToolInputError(f"Unknown {' or '.join(allowed)} '{ref}'. Search for it first so it has a ref.")
    return entry["type"], uuid.UUID(entry["id"])


# --- draft_linkedin_message ---------------------------------------------------------------


class DraftLinkedInMessage(BaseModel):
    to_ref: str = Field(description="Contact ref (p1) or lead ref (l1)")
    kind: Literal["connection_note", "message", "inmail"] = Field(
        description="connection_note: note on a connection request (300 characters max); "
        "message: to a 1st-degree connection; inmail: to someone outside the network"
    )
    text: str = Field(min_length=10, max_length=linkedin.MESSAGE_LIMIT)
    subject: str | None = Field(None, max_length=200, description="InMail only")


def _check_length(kind: str, text: str) -> None:
    if kind == "connection_note" and len(text) > linkedin.CONNECTION_NOTE_LIMIT:
        raise ToolInputError(
            f"A connection note can be at most {linkedin.CONNECTION_NOTE_LIMIT} characters; this one is {len(text)}. "
            "Shorten it."
        )


async def prepare_draft_linkedin(ctx: ToolContext, a: DraftLinkedInMessage) -> Proposal:
    kind, record_id = _resolve(ctx, a.to_ref, ("contact", "lead"))
    _check_length(a.kind, a.text.strip())
    if kind == "contact":
        record = await records.contacts(ctx.tenant).get(record_id)
        name, company_id = record.full_name, record.company_id
    else:
        record = await records.leads(ctx.tenant).get(record_id)
        name, company_id = record.name, None
    label = KIND_LABEL[a.kind]
    return Proposal(
        title=f"LinkedIn {label}",
        summary=f"LinkedIn {label} to {name}",
        payload={
            "target_type": kind, "target_id": str(record_id), "company_id": str(company_id) if company_id else None,
            "kind": a.kind, "text": a.text.strip(), "subject": a.subject, "name": name,
        },
        target_type=kind,
        target_id=record_id,
        target_label=name,
        kind="linkedin",
        linkedin={
            "kind": a.kind,
            "label": label,
            "text": a.text.strip(),
            "subject": a.subject,
            "limit": linkedin.CONNECTION_NOTE_LIMIT if a.kind == "connection_note" else linkedin.MESSAGE_LIMIT,
            "profile_url": record.linkedin_url,
            "recipient": name,
        },
    )


async def execute_draft_linkedin(ctx: TenantContext, p: dict[str, Any], edits: dict[str, Any] | None) -> Executed:
    text = ((edits or {}).get("text") or p["text"]).strip()
    if not text:
        raise ValidationFailed("The message is empty.")
    try:
        _check_length(p["kind"], text)
    except ToolInputError as exc:
        raise ValidationFailed(exc.message) from exc
    label = KIND_LABEL[p["kind"]]
    data: dict[str, Any] = {
        "type": "linkedin",
        "subject": f"LinkedIn {label} to {p['name']}"[:300],
        "body": (f"{p['subject']}\n\n" if p.get("subject") else "") + text,
        "occurred_at": datetime.now(UTC),
        f"{p['target_type']}_id": uuid.UUID(p["target_id"]),
    }
    if p.get("company_id"):
        data["company_id"] = uuid.UUID(p["company_id"])
    await records.create_activity(ctx, data)
    return Executed(f"Logged the LinkedIn {label} to {p['name']}", p["target_type"], uuid.UUID(p["target_id"]))


# --- save_linkedin_url ------------------------------------------------------------------------


class SaveLinkedInUrl(BaseModel):
    ref: str = Field(description="Company (c1), contact (p1) or lead (l1) ref")
    url: str = Field(max_length=500, description="The public LinkedIn page, e.g. from find_linkedin")


def _repo(ctx: TenantContext, kind: str):
    return {"company": records.companies, "contact": records.contacts, "lead": records.leads}[kind](ctx)


def _expected(kind: str, record) -> linkedin.Kind:
    if kind == "company":
        return "company"
    if kind == "lead":
        return linkedin.person_or_company(record.name, record.company_name)
    return "person"


def _name(kind: str, record) -> str:
    return record.full_name if kind == "contact" else record.name


async def prepare_save_linkedin(ctx: ToolContext, a: SaveLinkedInUrl) -> Proposal:
    kind, record_id = _resolve(ctx, a.ref, ("company", "contact", "lead"))
    record = await _repo(ctx.tenant, kind).get(record_id)
    try:
        url = linkedin.require(a.url, _expected(kind, record))
    except ValidationFailed as exc:
        raise ToolInputError(exc.message) from exc
    if url == record.linkedin_url:
        raise ToolInputError("That LinkedIn page is already saved on this record.")
    return Proposal(
        title="Save LinkedIn page",
        summary=f"Save LinkedIn for {_name(kind, record)}",
        payload={"kind": kind, "id": str(record_id), "url": url},
        changes=[change("LinkedIn", record.linkedin_url, url)],
        target_type=kind,
        target_id=record_id,
        target_label=_name(kind, record),
    )


async def execute_save_linkedin(ctx: TenantContext, p: dict[str, Any], _edits) -> Executed:
    repo = _repo(ctx, p["kind"])
    record = await repo.get(uuid.UUID(p["id"]))
    await repo.update(record, {"linkedin_url": linkedin.require(p["url"], _expected(p["kind"], record))})
    return Executed(f"Saved the LinkedIn page for {_name(p['kind'], record)}", p["kind"], record.id)


LINKEDIN_ACTIONS = [
    ActionSpec(
        "draft_linkedin_message",
        "Draft a LinkedIn connection note or message for the user to send on LinkedIn themselves. "
        "Confirming logs it as a LinkedIn activity.",
        DraftLinkedInMessage,
        prepare_draft_linkedin,
        execute_draft_linkedin,
    ),
    ActionSpec(
        "save_linkedin_url",
        "Propose saving a public LinkedIn page on a company, contact or lead.",
        SaveLinkedInUrl,
        prepare_save_linkedin,
        execute_save_linkedin,
    ),
]
