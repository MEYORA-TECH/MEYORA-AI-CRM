import uuid
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.auth.deps import RequestMeta, TenantContext
from app.models import AuditLog
from app.models.enums import ActorType


def apply_changes(obj: Any, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Set attributes on `obj` and return {field: {"old", "new"}} for fields that changed."""
    changes: dict[str, dict[str, Any]] = {}
    for key, new in data.items():
        old = getattr(obj, key)
        if old != new:
            changes[key] = {"old": old, "new": new}
            setattr(obj, key, new)
    return changes


def snapshot(obj: Any, fields: list[str]) -> dict[str, dict[str, Any]]:
    return {f: {"old": None, "new": getattr(obj, f)} for f in fields if getattr(obj, f) is not None}


def add_audit(
    session,
    *,
    organization_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None,
    meta: RequestMeta | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
    actor_type: ActorType = ActorType.USER,
) -> None:
    session.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=jsonable_encoder(changes or {}),
            ip=meta.ip if meta else None,
            user_agent=meta.user_agent if meta else None,
            request_id=meta.request_id if meta else None,
        )
    )


def audit(
    ctx: TenantContext,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    add_audit(
        ctx.session,
        organization_id=ctx.organization_id,
        action=action,
        actor_user_id=ctx.user_id,
        meta=ctx.meta,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
    )
