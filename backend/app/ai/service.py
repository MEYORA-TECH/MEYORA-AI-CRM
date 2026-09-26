"""One chat turn, end to end: quota → conversation → context → agent → persistence."""

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any, Literal

from sqlalchemy import func, select

from app.ai import registry
from app.ai.agent import TurnRecord, estimate_tokens, run_turn
from app.ai.prompts import select_tools, system_prompt
from app.ai.providers.base import ChatMessage
from app.ai.tools.base import ToolContext, WorkingSet
from app.auth.deps import RequestMeta, TenantContext
from app.auth.permissions import permissions_for
from app.core.config import get_settings
from app.core.errors import NotFound
from app.core.logging import get_logger
from app.database.session import SessionLocal, set_tenant
from app.models import AIConversation, AIMessage, AIUsageLog, Membership, Organization, User
from app.services import records

log = get_logger("ai.service")

PageType = Literal["company", "contact", "lead", "deal"]
HISTORY_MESSAGES = 12


@dataclass
class ChatRequest:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    meta: RequestMeta
    message: str
    conversation_id: uuid.UUID | None
    page_type: PageType | None
    page_id: uuid.UUID | None
    timezone: str


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def tokens_used_today(session, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
    start = datetime.combine(datetime.now(UTC).date(), time.min, UTC)
    used = await session.scalar(
        select(func.coalesce(func.sum(AIUsageLog.prompt_tokens + AIUsageLog.completion_tokens), 0)).where(
            AIUsageLog.organization_id == organization_id,
            AIUsageLog.user_id == user_id,
            AIUsageLog.created_at >= start,
        )
    )
    return int(used or 0)


async def get_conversation(ctx: TenantContext, conversation_id: uuid.UUID) -> AIConversation:
    conv = await ctx.session.scalar(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.organization_id == ctx.organization_id,
            AIConversation.user_id == ctx.user_id,  # conversations are private to their author
            AIConversation.deleted_at.is_(None),
        )
    )
    if conv is None:
        raise NotFound("Conversation")
    return conv


async def _history(ctx: TenantContext, conv: AIConversation) -> list[ChatMessage]:
    """Recent user/assistant text only. Old tool payloads are not replayed: the working set keeps the refs."""
    rows = list(
        await ctx.session.scalars(
            select(AIMessage)
            .where(
                AIMessage.conversation_id == conv.id,
                AIMessage.role.in_(["user", "assistant"]),
                AIMessage.content.is_not(None),
            )
            .order_by(AIMessage.created_at.desc())
            .limit(HISTORY_MESSAGES)
        )
    )
    return [ChatMessage(role=m.role, content=m.content) for m in reversed(rows)]  # type: ignore[arg-type]


async def _page_note(
    ctx: TenantContext, ws: WorkingSet, page_type: PageType | None, page_id: uuid.UUID | None
) -> str | None:
    if not page_type or not page_id:
        return None
    repo = {"company": records.companies, "contact": records.contacts, "lead": records.leads, "deal": records.deals}[
        page_type
    ]
    try:
        obj = await repo(ctx).get(page_id)
    except NotFound:
        return None
    name = obj.full_name if page_type == "contact" else obj.name
    ref = ws.ref_for(page_type, obj.id, name)
    return f"The user is looking at {page_type} {ref} ({name}). 'This', 'it' or 'them' likely refers to it."


def _fit(
    system: list[ChatMessage], history: list[ChatMessage], current: list[ChatMessage], tool_tokens: int, budget: int
) -> list[ChatMessage]:
    """Drop the oldest history until the prompt fits the per-request budget."""
    while history and estimate_tokens(system + history + current) + tool_tokens > budget:
        history = history[2:] if len(history) > 1 else []
    return system + history + current


async def chat_stream(req: ChatRequest) -> AsyncIterator[str]:
    settings = get_settings()
    async with SessionLocal() as session:
        await set_tenant(session, req.organization_id)
        user = await session.get(User, req.user_id)
        membership = await session.scalar(
            select(Membership).where(
                Membership.organization_id == req.organization_id, Membership.user_id == req.user_id
            )
        )
        org = await session.get(Organization, req.organization_id)
        if user is None or membership is None or org is None:
            yield sse("error", {"message": "You no longer have access to this workspace."})
            return
        ctx = TenantContext(
            session=session,
            user=user,
            organization_id=req.organization_id,
            role=membership.role,
            meta=req.meta,
            permissions=permissions_for(membership.role),
        )

        if not registry.is_configured():
            yield sse(
                "error",
                {
                    "message": "The assistant isn't set up yet. An admin needs to add an AI provider key.",
                    "code": "not_configured",
                },
            )
            return

        used = await tokens_used_today(session, req.organization_id, req.user_id)
        if used >= settings.ai_daily_token_quota:
            yield sse(
                "error", {"message": "You've used today's AI allowance. It resets at midnight UTC.", "code": "quota"}
            )
            return

        if req.conversation_id:
            try:
                conv = await get_conversation(ctx, req.conversation_id)
            except NotFound:
                yield sse("error", {"message": "That conversation doesn't exist.", "code": "not_found"})
                return
        else:
            conv = AIConversation(organization_id=req.organization_id, user_id=req.user_id, title=_title(req.message))
            session.add(conv)
            await session.flush()

        session.add(
            AIMessage(organization_id=req.organization_id, conversation_id=conv.id, role="user", content=req.message)
        )
        conv.last_message_at = datetime.now(UTC)
        await session.commit()
        yield sse("conversation", {"id": str(conv.id), "title": conv.title})

        ws = WorkingSet.load(conv.state)
        tools = select_tools(req.message, req.page_type)
        tool_tokens = sum(len(json.dumps(t.spec().parameters)) + len(t.description) for t in tools) // 4
        system = [
            ChatMessage(
                role="system",
                content=system_prompt(
                    org=org.name,
                    user=user.full_name,
                    role=membership.role,
                    tz=req.timezone,
                    currency=org.default_currency,
                ),
            )
        ]
        note = await _page_note(ctx, ws, req.page_type, req.page_id)
        current = ([ChatMessage(role="system", content=note)] if note else []) + [
            ChatMessage(role="user", content=req.message)
        ]
        history = (await _history(ctx, conv))[:-1]  # the message just saved is `current`
        messages = _fit(system, history, current, tool_tokens, settings.ai_request_token_budget)

        try:
            candidates = registry.route("crm", prefer=conv.provider)
        except registry.NoProviderAvailable as exc:
            yield sse("error", {"message": str(exc), "code": "not_configured"})
            return

        record = TurnRecord()
        tool_ctx = ToolContext(tenant=ctx, working_set=ws, timezone=req.timezone)
        try:
            async for event in run_turn(
                candidates=candidates,
                messages=messages,
                tools=tools,
                tool_ctx=tool_ctx,
                record=record,
                max_model_calls=settings.ai_max_model_calls,
            ):
                yield sse(event["type"], {k: v for k, v in event.items() if k != "type"})
        except Exception:  # never leave the stream hanging on a bug
            log.exception("ai_turn_failed", conversation_id=str(conv.id))
            await session.rollback()
            await session.refresh(conv)  # rollback expires loaded objects
            record.error = "Something went wrong while answering."
            yield sse("error", {"message": record.error})

        assistant_id = await _persist(session, req, conv, ws, record)
        total = sum(c.usage.prompt_tokens + c.usage.completion_tokens for c in record.calls)
        yield sse(
            "done",
            {
                "message_id": str(assistant_id) if assistant_id else None,
                "tokens": total,
                "provider": record.provider.label if record.provider else None,
                "used_today": used + total,
                "quota": settings.ai_daily_token_quota,
            },
        )


async def _persist(
    session, req: ChatRequest, conv: AIConversation, ws: WorkingSet, record: TurnRecord
) -> uuid.UUID | None:
    org_id = req.organization_id
    for m in record.tool_messages:
        session.add(
            AIMessage(
                organization_id=org_id,
                conversation_id=conv.id,
                role=m["role"],
                content=m.get("content"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
                tool_name=m.get("tool_name"),
                ui=m.get("ui"),
            )
        )
    assistant_id = None
    if record.text:
        usage = record.calls[-1].usage if record.calls else None
        msg = AIMessage(
            organization_id=org_id,
            conversation_id=conv.id,
            role="assistant",
            content=record.text,
            provider=record.provider.id if record.provider else None,
            model=record.provider.chat_model if record.provider else None,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )
        session.add(msg)
        await session.flush()
        assistant_id = msg.id
    for call in record.calls:
        session.add(
            AIUsageLog(
                organization_id=org_id,
                request_id=req.meta.request_id,
                user_id=req.user_id,
                conversation_id=conv.id,
                provider=call.provider,
                model=call.model,
                purpose="chat",
                latency_ms=call.latency_ms,
                prompt_tokens=call.usage.prompt_tokens,
                completion_tokens=call.usage.completion_tokens,
                tool_calls=call.tool_calls,
                status=call.status,
                error=call.error,
            )
        )
        log.info(
            "ai_call",
            provider=call.provider,
            model=call.model,
            latency_ms=call.latency_ms,
            prompt_tokens=call.usage.prompt_tokens,
            completion_tokens=call.usage.completion_tokens,
            tools=call.tool_calls,
            status=call.status,
            conversation_id=str(conv.id),
        )
    if record.provider and not conv.provider:
        conv.provider, conv.model = record.provider.id, record.provider.chat_model
    conv.state = ws.dump()
    conv.last_message_at = datetime.now(UTC)
    await session.commit()
    return assistant_id


def _title(message: str) -> str:
    text = " ".join(message.split())
    return text if len(text) <= 60 else text[:57].rstrip() + "…"
