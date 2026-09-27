"""Propose, confirm and reject AI actions."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.ai.actions.base import ActionSpec
from app.ai.actions.crm_actions import CRM_ACTIONS
from app.ai.actions.email_action import EMAIL_ACTIONS
from app.ai.actions.linkedin_actions import LINKEDIN_ACTIONS
from app.ai.tools.base import Tool, ToolContext, ToolResult
from app.auth.deps import TenantContext
from app.auth.permissions import Perm
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.logging import get_logger
from app.models import AIAction, AIMessage
from app.services.audit import audit

log = get_logger("ai.actions")
SPECS: dict[str, ActionSpec] = {a.name: a for a in CRM_ACTIONS + EMAIL_ACTIONS + LINKEDIN_ACTIONS}
EXPIRES_AFTER = timedelta(minutes=30)


async def propose(ctx: ToolContext, spec: ActionSpec, args) -> ToolResult:
    if not ctx.tenant.can(Perm.CRM_WRITE):
        return ToolResult(summary="You don't have permission to change records, so I can't propose this.", ok=False)
    proposal = await spec.prepare(ctx, args)
    session = ctx.tenant.session
    count = (
        await session.scalar(select(func.count(AIAction.id)).where(AIAction.conversation_id == ctx.conversation_id))
        if ctx.conversation_id
        else 0
    )
    action = AIAction(
        organization_id=ctx.tenant.organization_id,
        conversation_id=ctx.conversation_id,
        user_id=ctx.tenant.user_id,
        ref=f"a{(count or 0) + 1}",
        tool=spec.name,
        args=proposal.payload,
        preview=proposal.card(),
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        target_version=proposal.target_version,
        expires_at=datetime.now(UTC) + EXPIRES_AFTER,
    )
    session.add(action)
    await session.flush()
    return ToolResult(
        summary=f"Proposed {action.ref}: {proposal.summary}. NOT done yet: it waits for the user to confirm in the app.",
        ui={**proposal.card(), "kind": "action", "id": str(action.id), "ref": action.ref, "status": "proposed"},
    )


def action_tools() -> list[Tool]:
    def make(spec: ActionSpec) -> Tool:
        async def handler(ctx: ToolContext, args) -> ToolResult:
            return await propose(ctx, spec, args)

        return Tool(spec.name, "actions", spec.description, spec.args, handler)

    return [make(s) for s in SPECS.values()]


async def _get(ctx: TenantContext, action_id: uuid.UUID) -> AIAction:
    action = await ctx.session.scalar(
        select(AIAction)
        .where(AIAction.id == action_id, AIAction.organization_id == ctx.organization_id)
        .with_for_update()
    )
    if action is None:
        raise NotFound("Action")
    if action.user_id != ctx.user_id:
        raise Forbidden("Only the person who asked for this action can confirm it")
    return action


def _event(action: AIAction, text: str) -> AIMessage | None:
    if action.conversation_id is None:
        return None
    return AIMessage(
        organization_id=action.organization_id,
        conversation_id=action.conversation_id,
        role="event",
        content=f"Action {action.ref} ({action.preview.get('title')}): {text}",
    )


async def confirm(ctx: TenantContext, action_id: uuid.UUID, edits: dict[str, Any] | None = None) -> AIAction:
    action = await _get(ctx, action_id)
    if action.status != "proposed":
        raise Conflict(f"This action was already {action.status}.")
    now = datetime.now(UTC)
    action.decided_at = now
    if action.expires_at < now:
        action.status, action.error = "expired", "Proposal expired; ask the assistant again."
    else:
        spec = SPECS[action.tool]
        try:
            if spec.version and action.target_id and action.target_version:
                current = await spec.version(ctx, action.target_id)
                if current != action.target_version:
                    raise Conflict(
                        "This record changed after the assistant proposed the change. Ask again to get an up-to-date proposal."
                    )
            ctx.actor_type = "ai"  # audit entries from the services below are marked as AI actions
            # A savepoint: if the action fails, only its own writes are undone, not the status update.
            async with ctx.session.begin_nested():
                done = await spec.execute(ctx, action.args, edits)
            action.status, action.result = "executed", done.as_dict()
        except AppError as exc:
            action.status, action.error = "failed", exc.message[:300]
        finally:
            ctx.actor_type = "user"

    audit(
        ctx,
        f"ai_action.{action.status}",
        entity_type=action.target_type,
        entity_id=action.target_id,
        changes={
            "tool": {"old": None, "new": action.tool},
            "summary": {"old": None, "new": action.preview.get("summary")},
        },
    )
    text = {
        "executed": f"confirmed and done. {(action.result or {}).get('summary', '')}",
        "failed": f"confirmed but failed: {action.error}",
        "expired": "expired before it was confirmed; nothing was changed.",
    }[action.status]
    if event := _event(action, text):
        ctx.session.add(event)
    log.info("ai_action", tool=action.tool, status=action.status, action_id=str(action.id))
    await ctx.session.commit()
    return action


async def reject(ctx: TenantContext, action_id: uuid.UUID) -> AIAction:
    action = await _get(ctx, action_id)
    if action.status != "proposed":
        raise Conflict(f"This action was already {action.status}.")
    action.status, action.decided_at = "rejected", datetime.now(UTC)
    if event := _event(action, "declined by the user; nothing was changed."):
        ctx.session.add(event)
    audit(
        ctx,
        "ai_action.rejected",
        entity_type=action.target_type,
        entity_id=action.target_id,
        changes={"tool": {"old": None, "new": action.tool}},
    )
    await ctx.session.commit()
    return action
