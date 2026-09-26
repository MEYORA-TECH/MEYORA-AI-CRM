import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.database.session import get_session, set_tenant
from app.integrations.gmail import sync
from app.integrations.google import oauth as google_oauth
from app.models import MailAccount
from app.schemas.common import OutputModel
from app.services.audit import add_audit, audit

router = APIRouter(prefix="/integrations/gmail", tags=["integrations"])
log = get_logger("integrations.gmail")


class MailAccountOut(OutputModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email_address: str
    status: str
    last_sync_at: datetime | None
    next_sync_at: datetime | None
    last_error: str | None
    messages_synced: int
    created_at: datetime


class GmailStatus(OutputModel):
    enabled: bool
    accounts: list[MailAccountOut]


def _enabled() -> bool:
    s = get_settings()
    return s.gmail_enabled and s.google_ready


def _back(path: str) -> str:
    return get_settings().public_url.rstrip("/") + path


@router.get("", response_model=GmailStatus)
async def gmail_status(ctx: TenantContext = Depends(require(Perm.CRM_READ))):
    rows = await ctx.session.scalars(
        select(MailAccount).where(MailAccount.organization_id == ctx.organization_id).order_by(MailAccount.created_at)
    )
    return GmailStatus(enabled=_enabled(), accounts=[MailAccountOut.model_validate(r) for r in rows])


@router.post("/connect")
async def gmail_connect(ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    if not _enabled():
        raise ValidationFailed("Gmail isn't enabled on this server.")
    url = await google_oauth.begin(
        ctx.session, "gmail", user_id=ctx.user_id, organization_id=ctx.organization_id, login_hint=ctx.user.email
    )
    await ctx.session.commit()
    return {"url": url}


@router.get("/callback")
async def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not _enabled():
        return RedirectResponse(_back("/settings?tab=email&gmail=disabled"), status_code=303)
    if error or not code:
        return RedirectResponse(_back("/settings?tab=email&gmail=cancelled"), status_code=303)
    try:
        pending = await google_oauth.consume_state(session, state, "gmail")
        await session.commit()
        tokens = await google_oauth.exchange_code(code, pending)
        claims = await google_oauth.verify_id_token(tokens.get("id_token", ""), pending.nonce)
        granted = set((tokens.get("scope") or "").split())
        if "https://www.googleapis.com/auth/gmail.readonly" not in granted:
            raise google_oauth.GoogleError("Gmail access wasn't granted.")
        if not tokens.get("refresh_token"):
            raise google_oauth.GoogleError("Google didn't return offline access.")
    except google_oauth.GoogleError as exc:
        log.warning("gmail_connect_failed", reason=exc.message)
        return RedirectResponse(_back("/settings?tab=email&gmail=failed"), status_code=303)

    await set_tenant(session, pending.organization_id)
    address = claims["email"].lower()
    account = await session.scalar(
        select(MailAccount).where(
            MailAccount.organization_id == pending.organization_id,
            MailAccount.provider == "gmail",
            MailAccount.email_address == address,
        )
    )
    if account is not None and account.user_id != pending.user_id:
        return RedirectResponse(_back("/settings?tab=email&gmail=taken"), status_code=303)
    if account is None:
        account = MailAccount(organization_id=pending.organization_id, user_id=pending.user_id, email_address=address)
        session.add(account)
    account.refresh_token_encrypted = encrypt(tokens["refresh_token"])
    account.scopes = sorted(granted)
    account.status, account.last_error = "connected", None
    await session.flush()
    await sync.schedule_next(session, account, now=True)
    add_audit(
        session,
        organization_id=pending.organization_id,
        action="gmail.connect",
        actor_user_id=pending.user_id,
        meta=None,
        entity_type="mail_account",
        entity_id=account.id,
        changes={"email": {"old": None, "new": address}},
    )
    await session.commit()
    return RedirectResponse(_back("/settings?tab=email&gmail=connected"), status_code=303)


async def _own_account(ctx: TenantContext, account_id: uuid.UUID) -> MailAccount:
    account = await ctx.session.scalar(
        select(MailAccount).where(MailAccount.id == account_id, MailAccount.organization_id == ctx.organization_id)
    )
    if account is None:
        raise NotFound("Mailbox")
    if account.user_id != ctx.user_id and not ctx.can(Perm.MEMBERS_MANAGE):
        raise Forbidden("Only the mailbox owner or an admin can do this")
    return account


@router.post("/{account_id}/sync", response_model=MailAccountOut)
async def gmail_sync_now(account_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    account = await _own_account(ctx, account_id)
    if account.status != "connected":
        raise ValidationFailed("Reconnect this mailbox first.")
    await sync.schedule_next(ctx.session, account, now=True)
    await ctx.session.commit()
    return account


@router.delete("/{account_id}", status_code=204)
async def gmail_disconnect(account_id: uuid.UUID, ctx: TenantContext = Depends(require(Perm.CRM_WRITE))):
    account = await _own_account(ctx, account_id)
    if account.refresh_token_encrypted:
        try:
            await google_oauth.revoke(decrypt(account.refresh_token_encrypted))
        except Exception:  # still forget it locally even if Google can't be reached
            log.warning("gmail_revoke_failed", account_id=str(account.id))
    account.refresh_token_encrypted = None
    account.status = "disconnected"
    audit(ctx, "gmail.disconnect", entity_type="mail_account", entity_id=account.id)
    await ctx.session.commit()
    return Response(status_code=204)
