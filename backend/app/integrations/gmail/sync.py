"""Gmail → database sync. Only CRM-related mail is stored; only new mail is downloaded.

First run: messages from the last N days (capped). Afterwards: Gmail's history
API returns just the ids added since the stored history id, so a quiet mailbox
costs one small request per interval. For each new id we fetch headers first
and download the full message only if it involves a CRM contact or company.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import decrypt
from app.core.logging import get_logger
from app.integrations.gmail.client import GmailClient, HistoryExpired
from app.integrations.gmail.parse import add_body, parse
from app.integrations.google.oauth import GoogleRevoked, refresh_access_token
from app.jobs.queue import enqueue
from app.models import EmailMessage, EmailThread, MailAccount
from app.services import email_matching

log = get_logger("gmail.sync")
SKIP_QUERY = "-in:spam -in:trash -category:promotions -category:social"


@dataclass
class SyncResult:
    seen: int = 0
    stored: int = 0
    skipped_unrelated: int = 0


async def sync_account(session: AsyncSession, organization_id: uuid.UUID, account_id: uuid.UUID) -> SyncResult | None:
    settings = get_settings()
    account = await session.scalar(
        select(MailAccount).where(MailAccount.id == account_id, MailAccount.organization_id == organization_id)
    )
    if account is None or account.status != "connected" or not account.refresh_token_encrypted:
        return None  # disconnected: the self-scheduling chain stops here

    try:
        access = await refresh_access_token(decrypt(account.refresh_token_encrypted))
    except GoogleRevoked:
        account.status = "reconnect_required"
        account.last_error = "Google access expired or was revoked. Reconnect Gmail to resume syncing."
        return None

    gmail = GmailClient(access)
    profile = await gmail.profile()  # read the history id *before* listing, so nothing slips between
    if account.history_id:
        try:
            ids = await gmail.added_since(account.history_id)
        except HistoryExpired:
            log.info("gmail_history_expired", account_id=str(account.id))
            ids = await gmail.list_message_ids(f"newer_than:7d {SKIP_QUERY}", settings.gmail_initial_sync_max_messages)
    else:
        ids = await gmail.list_message_ids(
            f"newer_than:{settings.gmail_initial_sync_days}d {SKIP_QUERY}", settings.gmail_initial_sync_max_messages
        )

    known = (
        set(
            await session.scalars(
                select(EmailMessage.provider_message_id).where(
                    EmailMessage.account_id == account.id, EmailMessage.provider_message_id.in_(ids)
                )
            )
        )
        if ids
        else set()
    )

    result = SyncResult()
    for message_id in ids:
        if message_id in known:
            continue
        result.seen += 1
        meta = parse(await gmail.message(message_id, full=False))
        if "SPAM" in meta.labels or "TRASH" in meta.labels:
            continue
        found = await email_matching.match(
            session, organization_id, [a.email for a in meta.participants], own_email=account.email_address
        )
        if not found.relevant:
            result.skipped_unrelated += 1
            continue
        full = add_body(meta, await gmail.message(message_id, full=True))
        await _store(session, account, full, found)
        result.stored += 1

    account.history_id = str(profile.get("historyId") or account.history_id or "")
    account.last_sync_at = datetime.now(UTC)
    account.next_sync_at = account.last_sync_at + timedelta(minutes=settings.gmail_sync_interval_minutes)
    account.messages_synced += result.stored
    account.last_error = None
    log.info(
        "gmail_synced",
        account_id=str(account.id),
        seen=result.seen,
        stored=result.stored,
        skipped=result.skipped_unrelated,
    )
    return result


async def _store(session: AsyncSession, account: MailAccount, p, found: email_matching.Match) -> None:
    thread = await session.scalar(
        select(EmailThread).where(EmailThread.account_id == account.id, EmailThread.provider_thread_id == p.thread_id)
    )
    if thread is None:
        thread = EmailThread(
            organization_id=account.organization_id,
            account_id=account.id,
            provider_thread_id=p.thread_id,
            subject=p.subject,
            snippet=p.snippet,
            participants=[],
            contact_ids=[],
            company_ids=[],
            message_count=0,
            last_message_at=p.sent_at,
        )
        session.add(thread)
    people = {x["email"]: x for x in thread.participants}
    for a in p.participants:
        people.setdefault(a.email, a.as_dict())
    thread.participants = list(people.values())
    thread.contact_ids = sorted(set(thread.contact_ids) | set(found.contact_ids))
    thread.company_ids = sorted(set(thread.company_ids) | set(found.company_ids))
    thread.message_count += 1
    if p.sent_at >= thread.last_message_at:
        thread.last_message_at, thread.snippet = p.sent_at, p.snippet
    await session.flush()

    message = EmailMessage(
        organization_id=account.organization_id,
        thread_id=thread.id,
        account_id=account.id,
        provider_message_id=p.id,
        rfc_message_id=p.rfc_message_id,
        direction="outbound" if p.from_.email == account.email_address.lower() else "inbound",
        from_email=p.from_.email,
        from_name=p.from_.name,
        to=[a.as_dict() for a in p.to],
        cc=[a.as_dict() for a in p.cc],
        subject=p.subject,
        snippet=p.snippet,
        body_text=p.body_text,
        labels=p.labels,
        has_attachments=p.has_attachments,
        contact_ids=found.contact_ids,
        company_ids=found.company_ids,
        sent_at=p.sent_at,
    )
    session.add(message)
    await session.flush()
    # Make the email searchable by meaning, like notes and call logs.
    await enqueue(
        session,
        "index_record",
        account.organization_id,
        {"kind": "email", "id": str(message.id)},
        dedupe_key=f"email:{message.id}",
    )


async def schedule_next(session: AsyncSession, account: MailAccount, *, now: bool = False) -> None:
    """Each sync queues the next one: one pending sync per mailbox, no cron needed."""
    delay = timedelta() if now else timedelta(minutes=get_settings().gmail_sync_interval_minutes)
    if now:  # "Sync now": pull an already-waiting sync forward instead of queueing a second one
        await session.execute(
            text(
                "UPDATE jobs SET run_after = now() WHERE kind = 'gmail_sync' AND dedupe_key = :k AND status = 'queued'"
            ),
            {"k": f"gmail:{account.id}"},
        )
    await enqueue(
        session,
        "gmail_sync",
        account.organization_id,
        {"account_id": str(account.id)},
        dedupe_key=f"gmail:{account.id}",
        delay=delay,
    )
