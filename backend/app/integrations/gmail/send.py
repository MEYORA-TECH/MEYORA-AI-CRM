"""Send one email through the user's Gmail, then store it like any synced outbound message."""

import base64
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.integrations.gmail.client import BASE, GmailClient
from app.integrations.gmail.parse import add_body, parse
from app.integrations.gmail.sync import _store
from app.integrations.google import oauth
from app.models import EmailMessage, MailAccount
from app.services import email_matching

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class SendError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


async def send(
    session: AsyncSession,
    account: MailAccount,
    *,
    to: list[str],
    subject: str,
    body: str,
    sender_name: str | None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
) -> EmailMessage:
    if account.status != "connected" or not account.refresh_token_encrypted:
        raise SendError("Your Gmail isn't connected. Reconnect it in Settings > Email.")
    if SEND_SCOPE not in (account.scopes or []):
        raise SendError("Gmail was connected without permission to send. Reconnect it in Settings > Email.")
    try:
        access = await oauth.refresh_access_token(decrypt(account.refresh_token_encrypted))
    except oauth.GoogleRevoked as exc:
        account.status = "reconnect_required"
        raise SendError("Google access expired. Reconnect Gmail in Settings > Email.") from exc

    mime = MimeMessage()
    mime["From"] = formataddr((sender_name or "", account.email_address))
    mime["To"] = ", ".join(to)
    mime["Subject"] = subject
    if in_reply_to:
        mime["In-Reply-To"] = in_reply_to
        mime["References"] = in_reply_to
    mime.set_content(body)
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

    async with httpx.AsyncClient(timeout=30, transport=oauth.transport) as client:
        resp = await client.post(
            f"{BASE}/messages/send",
            json={"raw": raw, **({"threadId": thread_id} if thread_id else {})},
            headers={"Authorization": f"Bearer {access}"},
        )
    if resp.status_code >= 400:
        raise SendError(f"Gmail refused to send the email ({resp.status_code}).")
    sent_id = resp.json()["id"]

    # Store what Gmail actually sent, through the same path as synced mail.
    full = await GmailClient(access).message(sent_id, full=True)
    parsed = add_body(parse(full), full)
    found = await email_matching.match(
        session, account.organization_id, [a.email for a in parsed.participants], own_email=account.email_address
    )
    await _store(session, account, parsed, found)
    account.messages_synced += 1
    stored = await session.scalar(
        select(EmailMessage).where(EmailMessage.account_id == account.id, EmailMessage.provider_message_id == sent_id)
    )
    return stored
