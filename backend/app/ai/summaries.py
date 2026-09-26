"""Rolling conversation summaries, so long chats don't resend their whole history."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import complete
from app.ai.providers.base import ChatMessage
from app.jobs.queue import enqueue
from app.models import AIConversation, AIConversationSummary, AIMessage

KEEP_RECENT = 6  # always sent verbatim
SUMMARISE_AFTER = 12  # unsummarised messages before a new summary is made

SYSTEM = """Update the running summary of a CRM assistant conversation. Keep: what the user wants, records discussed (by name), facts found, decisions and open questions. Drop pleasantries. Plain prose, at most 150 words. Only use what is in the text."""


async def summary_for(session: AsyncSession, conversation_id: uuid.UUID) -> AIConversationSummary | None:
    return await session.scalar(
        select(AIConversationSummary).where(AIConversationSummary.conversation_id == conversation_id)
    )


def _text_messages(conversation_id: uuid.UUID, after: datetime | None):
    stmt = select(AIMessage).where(
        AIMessage.conversation_id == conversation_id,
        AIMessage.role.in_(["user", "assistant"]),
        AIMessage.content.is_not(None),
    )
    return stmt.where(AIMessage.created_at > after) if after else stmt


async def maybe_enqueue(session: AsyncSession, conv: AIConversation) -> None:
    existing = await summary_for(session, conv.id)
    count = await session.scalar(
        select(func.count()).select_from(
            _text_messages(conv.id, existing.covered_until if existing else None).subquery()
        )
    )
    if (count or 0) > SUMMARISE_AFTER:
        await enqueue(
            session,
            "summarize_conversation",
            conv.organization_id,
            {"conversation_id": str(conv.id)},
            dedupe_key=str(conv.id),
        )


async def summarize(session: AsyncSession, organization_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
    conv = await session.get(AIConversation, conversation_id)
    if conv is None or conv.deleted_at is not None:
        return False
    current = await summary_for(session, conversation_id)
    rows = list(
        await session.scalars(
            _text_messages(conversation_id, current.covered_until if current else None).order_by(AIMessage.created_at)
        )
    )
    to_fold = rows[:-KEEP_RECENT]
    if not to_fold:
        return False
    transcript = "\n".join(f"{m.role}: {m.content[:1200]}" for m in to_fold)
    previous = current.summary if current else "(none yet)"
    result = await complete(
        session,
        organization_id,
        [
            ChatMessage(role="system", content=SYSTEM),
            ChatMessage(role="user", content=f"Summary so far:\n{previous}\n\nNew messages:\n{transcript}"),
        ],
        purpose="summary",
        user_id=conv.user_id,
    )
    text = result.text.strip()[:2000]
    if not text:
        return False
    if current is None:
        session.add(
            AIConversationSummary(
                organization_id=organization_id,
                conversation_id=conversation_id,
                summary=text,
                covered_until=to_fold[-1].created_at,
                message_count=len(to_fold),
            )
        )
    else:
        current.summary = text
        current.covered_until = to_fold[-1].created_at
        current.message_count += len(to_fold)
    return True
