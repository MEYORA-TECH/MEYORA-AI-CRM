"""Background job handlers. Each runs in its own session with the tenant already set."""

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import knowledge, memory, summaries
from app.jobs.queue import handler
from app.models import AIConversation, AIMessage, Note

# Questions and commands rarely contain durable facts; skipping them saves free-tier tokens.
_QUESTION = re.compile(
    r"^\s*(what|who|when|where|why|how|which|show|list|find|give|tell|can|could|is|are|do|does|summari[sz]e)\b", re.I
)


def worth_extracting(text: str) -> bool:
    text = text.strip()
    return len(text) >= 25 and not text.endswith("?") and not _QUESTION.match(text)


@handler("index_record")
async def index_record(session: AsyncSession, org_id: uuid.UUID, payload: dict[str, Any]) -> None:
    await knowledge.index_record(session, org_id, payload["kind"], uuid.UUID(payload["id"]))


@handler("summarize_conversation")
async def summarize_conversation(session: AsyncSession, org_id: uuid.UUID, payload: dict[str, Any]) -> None:
    await summaries.summarize(session, org_id, uuid.UUID(payload["conversation_id"]))


@handler("extract_memories")
async def extract_memories(session: AsyncSession, org_id: uuid.UUID, payload: dict[str, Any]) -> None:
    kind, source_id = payload["source_type"], uuid.UUID(payload["source_id"])
    if kind == "chat":
        msg = await session.get(AIMessage, source_id)
        if msg is None or msg.role != "user" or not msg.content:
            return
        conv = await session.get(AIConversation, msg.conversation_id)
        if conv is None:
            return
        refs = (conv.state or {}).get("refs", {})
        await memory.extract(
            session,
            org_id,
            text=msg.content,
            speaker="the user in a chat",
            refs=refs,
            default_links={},
            source_type="chat",
            source_id=msg.id,
            user_id=conv.user_id,
        )
    elif kind == "note":
        note = await session.scalar(select(Note).where(Note.id == source_id, Note.organization_id == org_id))
        if note is None:
            return
        links = {"company_id": note.company_id, "contact_id": note.contact_id, "deal_id": note.deal_id}
        await memory.extract(
            session,
            org_id,
            text=note.body,
            speaker="a CRM note written by a teammate",
            refs={},
            default_links=links,
            source_type="note",
            source_id=note.id,
            user_id=note.author_id,
        )
