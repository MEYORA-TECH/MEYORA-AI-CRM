"""Email tools. They read stored email only; content is untrusted third-party text."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.ai.tools.base import MAX_ROWS, Tool, ToolContext, ToolInputError, ToolResult
from app.models import EmailMessage, EmailThread
from app.services.crud import like_pattern

PREFIX_THREAD = "e"


def _thread_ref(ctx: ToolContext, thread: EmailThread) -> str:
    sid = str(thread.id)
    for ref, v in ctx.working_set.refs.items():
        if v["id"] == sid:
            return ref
    n = 1 + sum(1 for r in ctx.working_set.refs if r.startswith(PREFIX_THREAD) and r[1:].isdigit())
    ref = f"{PREFIX_THREAD}{n}"
    ctx.working_set.refs[ref] = {"type": "email_thread", "id": sid, "name": thread.subject[:80]}
    return ref


class SearchEmails(BaseModel):
    query: str | None = Field(None, description="Words in the subject, body or sender")
    contact_ref: str | None = None
    company_ref: str | None = None
    since_days: int = Field(90, ge=1, le=730)
    limit: int = Field(MAX_ROWS, ge=1, le=MAX_ROWS)


async def search_emails(ctx: ToolContext, a: SearchEmails) -> ToolResult:
    s = ctx.tenant.session
    stmt = select(EmailThread).where(
        EmailThread.organization_id == ctx.tenant.organization_id,
        EmailThread.last_message_at >= datetime.now(UTC) - timedelta(days=a.since_days),
    )
    if a.contact_ref:
        stmt = stmt.where(EmailThread.contact_ids.any(ctx.working_set.resolve("contact", a.contact_ref)))
    if a.company_ref:
        stmt = stmt.where(EmailThread.company_ids.any(ctx.working_set.resolve("company", a.company_ref)))
    if a.query:
        pattern = like_pattern(a.query)
        stmt = stmt.where(
            or_(
                EmailThread.subject.ilike(pattern, escape="\\"),
                EmailThread.id.in_(
                    select(EmailMessage.thread_id).where(
                        EmailMessage.organization_id == ctx.tenant.organization_id,
                        or_(
                            EmailMessage.body_text.ilike(pattern, escape="\\"),
                            EmailMessage.from_email.ilike(pattern, escape="\\"),
                        ),
                    )
                ),
            )
        )
    total = await s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    threads = list(await s.scalars(stmt.order_by(EmailThread.last_message_at.desc()).limit(a.limit)))
    lines, rows = [], []
    for t in threads:
        ref = _thread_ref(ctx, t)
        who = ", ".join(p.get("name") or p["email"] for p in t.participants[:3])
        lines.append(
            f'{ref}: "{t.subject}" · {t.message_count} message(s) · last {t.last_message_at:%Y-%m-%d} · with {who} · {t.snippet[:120]}'
        )
        rows.append(
            {
                "id": str(t.id),
                "title": t.subject,
                "subtitle": f"{t.last_message_at:%d %b} · {who}",
                "href": f"/emails/{t.id}",
            }
        )
    return ToolResult(
        summary="\n".join([f"{total} email thread(s)", *lines]),
        ui={"kind": "records", "entity": "email", "title": "Emails", "total": total, "rows": rows},
    )


class GetThread(BaseModel):
    ref: str = Field(description="Thread ref from search_emails (e.g. e1)")


async def get_email_thread(ctx: ToolContext, a: GetThread) -> ToolResult:
    entry = ctx.working_set.refs.get(a.ref.strip().lower())
    if not entry or entry["type"] != "email_thread":
        raise ToolInputError(f"Unknown email thread '{a.ref}'. Use search_emails first.")
    s = ctx.tenant.session
    thread = await s.scalar(
        select(EmailThread).where(
            EmailThread.id == entry["id"], EmailThread.organization_id == ctx.tenant.organization_id
        )
    )
    if thread is None:
        raise ToolInputError("That email thread no longer exists.")
    messages = list(
        await s.scalars(
            select(EmailMessage)
            .where(EmailMessage.thread_id == thread.id)
            .order_by(EmailMessage.sent_at.desc())
            .limit(8)
        )
    )
    parts = [f'Thread "{thread.subject}" ({thread.message_count} messages, newest first):']
    for m in messages:
        who = "us" if m.direction == "outbound" else (m.from_name or m.from_email)
        parts.append(
            f"--- {m.sent_at:%Y-%m-%d %H:%M} from {who} ({m.direction}) ---\n{m.body_text[:1500] or m.snippet}"
        )
    return ToolResult(
        summary="\n".join(parts),
        ui={
            "kind": "records",
            "entity": "email",
            "title": "Email thread",
            "total": 1,
            "rows": [
                {
                    "id": str(thread.id),
                    "title": thread.subject,
                    "subtitle": f"{thread.message_count} messages",
                    "href": f"/emails/{thread.id}",
                }
            ],
        },
    )


EMAIL_TOOLS: list[Tool] = [
    Tool(
        "search_emails",
        "emails",
        "Find synced email threads by words, contact or company.",
        SearchEmails,
        search_emails,
    ),
    Tool("get_email_thread", "emails", "Read the latest messages of one email thread.", GetThread, get_email_thread),
]
