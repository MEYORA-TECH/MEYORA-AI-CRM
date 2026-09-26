"""Knowledge search and explicit memories."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.ai import knowledge, memory
from app.ai.tools.base import Tool, ToolContext, ToolInputError, ToolResult

_HREF = {"company_id": "/companies", "contact_id": "/contacts", "lead_id": "/leads", "deal_id": "/deals"}


def _href(chunk) -> str | None:
    for field in ("deal_id", "contact_id", "company_id", "lead_id"):
        if getattr(chunk, field):
            return f"{_HREF[field]}/{getattr(chunk, field)}"
    own = {"company": "/companies", "contact": "/contacts", "lead": "/leads", "deal": "/deals"}.get(chunk.source_type)
    return f"{own}/{chunk.source_id}" if own else None


def _link_for_ref(ctx: ToolContext, ref: str | None) -> tuple[str, uuid.UUID] | None:
    if not ref:
        return None
    entry = ctx.working_set.refs.get(ref.strip().lower())
    if not entry:
        raise ToolInputError(f"Unknown reference '{ref}'. Search for the record first.")
    if entry["type"] not in ("company", "contact", "lead", "deal"):
        raise ToolInputError(f"{ref} can't have notes attached.")
    return f"{entry['type']}_id", uuid.UUID(entry["id"])


class SearchKnowledge(BaseModel):
    query: str = Field(description="What to look for, in plain words (meaning-based search)")
    about_ref: str | None = Field(None, description="Only notes and activity linked to this record")


async def search_knowledge(ctx: ToolContext, a: SearchKnowledge) -> ToolResult:
    hits = await knowledge.search(
        ctx.tenant.session, ctx.tenant.organization_id, a.query, link=_link_for_ref(ctx, a.about_ref)
    )
    if not hits:
        return ToolResult(
            summary="No matching notes or activity logs.",
            ui={"kind": "records", "entity": "note", "title": "Notes & activity", "total": 0, "rows": []},
        )
    lines, rows = [], []
    for h in hits:
        c = h.chunk
        when = c.occurred_at.strftime("%Y-%m-%d") if c.occurred_at else "undated"
        lines.append(f"- [{c.title} · {when}] {c.content[:500]}")
        rows.append(
            {
                "id": str(c.id),
                "title": c.title,
                "subtitle": f"{when} · {c.content[:90]}…" if len(c.content) > 90 else f"{when} · {c.content}",
                "href": _href(c),
            }
        )
    return ToolResult(
        summary=f"{len(hits)} relevant passage(s):\n" + "\n".join(lines),
        ui={"kind": "records", "entity": "note", "title": "Notes & activity", "total": len(hits), "rows": rows},
    )


class Remember(BaseModel):
    content: str = Field(min_length=5, max_length=500, description="One standalone sentence naming its subject")
    about_ref: str | None = Field(None, description="Record ref it is about, or 'me' for the user's own preference")
    type: Literal["fact", "preference", "requirement", "relationship", "decision"] = "fact"
    importance: int = Field(3, ge=1, le=5)


async def remember(ctx: ToolContext, a: Remember) -> ToolResult:
    user_scope = (a.about_ref or "").strip().lower() == "me"
    links: dict[str, uuid.UUID | None] = {}
    if a.about_ref and not user_scope:
        field, value = _link_for_ref(ctx, a.about_ref)
        if field == "lead_id":
            raise ToolInputError(
                "Memories attach to companies, contacts or deals. Convert the lead first, or save it org-wide."
            )
        links = {field: value}
    saved = await memory.save_memory(
        ctx.tenant.session,
        ctx.tenant.organization_id,
        content=a.content,
        memory_type=a.type,
        user_id=ctx.tenant.user_id,
        user_scope=user_scope,
        links=links,
        source_type="chat",
        confidence=0.95,
        importance=a.importance,
        created_by="ai",
    )
    verb = "Already remembered" if saved.action == "merged" else "Remembered"
    return ToolResult(
        summary=f"{verb}: {saved.memory.content}",
        ui={
            "kind": "memory",
            "action": saved.action,
            "id": str(saved.memory.id),
            "content": saved.memory.content,
            "scope": saved.memory.scope,
        },
    )


MEMORY_TOOLS: list[Tool] = [
    Tool(
        "search_knowledge",
        "knowledge",
        "Meaning-based search of notes, call and meeting logs, and record descriptions.",
        SearchKnowledge,
        search_knowledge,
    ),
    Tool(
        "remember",
        "memory",
        "Save a durable fact to long-term memory. Only when the user explicitly asks you to remember something.",
        Remember,
        remember,
    ),
]
