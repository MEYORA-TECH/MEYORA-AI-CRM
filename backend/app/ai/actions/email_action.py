"""Draft an email; send it only when the user presses Send (after optionally editing it)."""

import uuid
from typing import Any

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.ai.actions.base import ActionSpec, Executed, Proposal
from app.ai.tools.base import ToolContext, ToolInputError
from app.auth.deps import TenantContext
from app.core.errors import ValidationFailed
from app.integrations.gmail import send as gmail_send
from app.models import EmailMessage, EmailThread, MailAccount
from app.services import records


class DraftEmail(BaseModel):
    to_ref: str | None = Field(None, description="Contact ref to send to")
    to_email: EmailStr | None = Field(None, description="Address, if not a contact")
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(
        min_length=5, max_length=10_000, description="Plain text, ready to send, signed with the user's name"
    )
    reply_to_thread_ref: str | None = Field(None, description="Email thread ref (e.g. e1) when replying")


async def _mailbox(session, organization_id, user_id) -> MailAccount | None:
    return await session.scalar(
        select(MailAccount).where(
            MailAccount.organization_id == organization_id,
            MailAccount.user_id == user_id,
            MailAccount.status == "connected",
        )
    )


async def prepare_draft_email(ctx: ToolContext, a: DraftEmail) -> Proposal:
    to_email, label, contact_id = a.to_email, None, None
    if a.to_ref:
        contact = await records.contacts(ctx.tenant).get(ctx.working_set.resolve("contact", a.to_ref))
        if not contact.email:
            raise ToolInputError(f"{contact.full_name} has no email address in the CRM.")
        to_email, label, contact_id = contact.email, contact.full_name, contact.id
    if not to_email:
        raise ToolInputError("Say who the email is to (a contact ref or an address).")

    thread_payload: dict[str, Any] = {}
    if a.reply_to_thread_ref:
        entry = ctx.working_set.refs.get(a.reply_to_thread_ref.strip().lower())
        if not entry or entry["type"] != "email_thread":
            raise ToolInputError("Unknown email thread. Use search_emails first.")
        thread_payload["thread_id"] = entry["id"]

    account = await _mailbox(ctx.tenant.session, ctx.tenant.organization_id, ctx.tenant.user_id)
    email = {
        "to": [to_email],
        "subject": a.subject,
        "body": a.body,
        "can_send": bool(account and gmail_send.SEND_SCOPE in (account.scopes or [])),
        "from": account.email_address if account else None,
    }
    return Proposal(
        title="Send email",
        summary=f"Email to {label or to_email}: “{a.subject}”",
        payload={"to": [to_email], "subject": a.subject, "body": a.body, **thread_payload},
        target_type="contact" if contact_id else None,
        target_id=contact_id,
        target_label=label,
        kind="email",
        email=email,
    )


async def execute_draft_email(ctx: TenantContext, p: dict[str, Any], edits: dict[str, Any] | None) -> Executed:
    # The user may have edited the draft on the card; the edited version is what gets sent.
    final = {**p, **{k: v for k, v in (edits or {}).items() if k in ("to", "subject", "body") and v}}
    if not final["to"] or not final["subject"].strip() or not final["body"].strip():
        raise ValidationFailed("The email needs a recipient, a subject and a message.")
    account = await _mailbox(ctx.session, ctx.organization_id, ctx.user_id)
    if account is None:
        raise ValidationFailed("Connect your Gmail in Settings > Email to send from Meyora.")

    provider_thread, in_reply_to = None, None
    if p.get("thread_id"):
        thread = await ctx.session.scalar(
            select(EmailThread).where(
                EmailThread.id == uuid.UUID(p["thread_id"]), EmailThread.organization_id == ctx.organization_id
            )
        )
        if thread and thread.account_id == account.id:
            provider_thread = thread.provider_thread_id
            last = await ctx.session.scalar(
                select(EmailMessage)
                .where(EmailMessage.thread_id == thread.id)
                .order_by(EmailMessage.sent_at.desc())
                .limit(1)
            )
            in_reply_to = last.rfc_message_id if last else None
    try:
        sent = await gmail_send.send(
            ctx.session,
            account,
            to=final["to"],
            subject=final["subject"],
            body=final["body"],
            sender_name=ctx.user.full_name,
            thread_id=provider_thread,
            in_reply_to=in_reply_to,
        )
    except gmail_send.SendError as exc:
        raise ValidationFailed(exc.message) from exc
    return Executed(f"Sent “{final['subject']}” to {', '.join(final['to'])}", "email", sent.thread_id if sent else None)


EMAIL_ACTIONS = [
    ActionSpec(
        "draft_email",
        "Draft an email for the user to review. It is only sent when they press Send.",
        DraftEmail,
        prepare_draft_email,
        execute_draft_email,
    ),
]
