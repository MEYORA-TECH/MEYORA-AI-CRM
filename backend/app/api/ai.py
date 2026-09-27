import uuid
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import exists, func, select

from app.ai import registry
from app.ai.actions import service as actions_service
from app.ai.service import ChatRequest, chat_stream, get_conversation, tokens_used_today
from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models import AIAction, AIConversation, AIMessage
from app.schemas.common import InputModel, OutputModel, Page
from app.services.crud import ListQuery, like_pattern, list_query

router = APIRouter(prefix="/ai", tags=["ai"])
use_ai = require(Perm.CRM_READ)


class PageContext(InputModel):
    type: Literal["company", "contact", "lead", "deal"]
    id: uuid.UUID


class ChatIn(InputModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    page: PageContext | None = None
    timezone: str = Field("Asia/Kolkata", max_length=64)


class ConversationOut(OutputModel):
    id: uuid.UUID
    title: str
    provider: str | None
    model: str | None
    created_at: datetime
    last_message_at: datetime


class ConversationUpdate(InputModel):
    title: str = Field(min_length=1, max_length=200)


class MessageOut(OutputModel):
    id: uuid.UUID
    role: str
    content: str | None
    tool_name: str | None
    tool_call_id: str | None
    ui: dict[str, Any] | None
    provider: str | None
    created_at: datetime


class StatusOut(OutputModel):
    configured: bool
    providers: list[str]
    used_today: int
    quota: int


@router.get("/status", response_model=StatusOut)
async def ai_status(ctx: TenantContext = Depends(use_ai)):
    providers = await registry.pool_for(ctx.session, ctx.organization_id)
    return StatusOut(
        configured=registry.is_configured(providers),
        providers=[p.label for p in providers if p.privacy == "trusted"],
        used_today=await tokens_used_today(ctx.session, ctx.organization_id, ctx.user_id),
        quota=get_settings().ai_daily_token_quota,
    )


@router.post("/chat")
async def chat(body: ChatIn, ctx: TenantContext = Depends(use_ai)):
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailed("Unknown time zone") from exc
    if body.conversation_id:
        await get_conversation(ctx, body.conversation_id)  # 404 before streaming starts
    req = ChatRequest(
        user_id=ctx.user_id,
        organization_id=ctx.organization_id,
        meta=ctx.meta,
        message=body.message.strip(),
        conversation_id=body.conversation_id,
        page_type=body.page.type if body.page else None,
        page_id=body.page.id if body.page else None,
        timezone=body.timezone,
    )
    # The stream opens its own DB session; the request's session closes with the handler.
    await ctx.session.close()
    return StreamingResponse(
        chat_stream(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _mine(ctx: TenantContext):
    return select(AIConversation).where(
        AIConversation.organization_id == ctx.organization_id,
        AIConversation.user_id == ctx.user_id,
        AIConversation.deleted_at.is_(None),
    )


@router.get("/conversations", response_model=Page[ConversationOut])
async def list_conversations(q: ListQuery = Depends(list_query), ctx: TenantContext = Depends(use_ai)):
    stmt = _mine(ctx)
    if q.q:
        pattern = like_pattern(q.q)
        stmt = stmt.where(
            AIConversation.title.ilike(pattern, escape="\\")
            | exists().where(
                AIMessage.conversation_id == AIConversation.id,
                AIMessage.role.in_(["user", "assistant"]),
                AIMessage.content.ilike(pattern, escape="\\"),
            )
        )
    total = await ctx.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await ctx.session.scalars(
        stmt.order_by(AIConversation.last_message_at.desc()).limit(q.page_size).offset((q.page - 1) * q.page_size)
    )
    return Page[ConversationOut](
        items=[ConversationOut.model_validate(r) for r in rows], total=total, page=q.page, page_size=q.page_size
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def conversation_messages(conversation_id: uuid.UUID, ctx: TenantContext = Depends(use_ai)):
    conv = await get_conversation(ctx, conversation_id)
    rows = await ctx.session.scalars(
        select(AIMessage)
        .where(AIMessage.conversation_id == conv.id, AIMessage.organization_id == ctx.organization_id)
        .order_by(AIMessage.created_at)
        .limit(400)
    )
    rows = [m for m in rows if m.role != "assistant" or m.content]  # tool-request turns carry no text
    # Action cards show their live status (confirmed later, expired, …), not the status at proposal time.
    action_ids = [uuid.UUID(m.ui["id"]) for m in rows if m.ui and m.ui.get("kind") == "action"]
    actions = (
        {str(a.id): a for a in await ctx.session.scalars(select(AIAction).where(AIAction.id.in_(action_ids)))}
        if action_ids
        else {}
    )
    out = []
    for m in rows:
        item = MessageOut.model_validate(m)
        if m.ui and m.ui.get("kind") == "action" and (a := actions.get(m.ui["id"])):
            item.ui = {**m.ui, **_action_state(a)}
        out.append(item)
    return out


def _action_state(a: AIAction) -> dict[str, Any]:
    return {"status": a.status, "result": a.result, "error": a.error, "expires_at": a.expires_at.isoformat()}


class ActionOut(OutputModel):
    id: uuid.UUID
    ref: str
    tool: str
    status: str
    preview: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    expires_at: datetime
    decided_at: datetime | None


class ConfirmIn(InputModel):
    # Email drafts can be edited on the card before sending.
    edits: dict[str, Any] | None = None


class ConfirmAllIn(InputModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=20)


@router.post("/actions/{action_id}/confirm", response_model=ActionOut)
async def confirm_action(
    action_id: uuid.UUID, body: ConfirmIn | None = None, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))
):
    edits = body.edits if body else None
    if edits is not None:
        # Only the fields a person can edit on a card: an email draft, or a LinkedIn draft's text.
        edits = {k: v for k, v in edits.items() if k in ("to", "subject", "body", "text")}
    return await actions_service.confirm(ctx, action_id, edits)


@router.post("/actions/{action_id}/reject", response_model=ActionOut)
async def reject_action(action_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    return await actions_service.reject(ctx, action_id)


@router.post("/actions/confirm-all", response_model=list[ActionOut])
async def confirm_all(body: ConfirmAllIn, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    """Confirm several proposals in order. Each succeeds or fails on its own."""
    return [await actions_service.confirm(ctx, action_id) for action_id in body.ids]


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, ctx: TenantContext = Depends(use_ai)
):
    conv = await get_conversation(ctx, conversation_id)
    conv.title = body.title.strip()
    await ctx.session.commit()
    return conv


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, ctx: TenantContext = Depends(use_ai)):
    conv = await get_conversation(ctx, conversation_id)
    conv.deleted_at = func.now()
    await ctx.session.commit()
    return Response(status_code=204)
