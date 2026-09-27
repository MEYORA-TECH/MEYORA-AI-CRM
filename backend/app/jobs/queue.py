"""A small job queue in Postgres.

Enqueue inside the same transaction as the data change, so a job exists if and
only if the change committed. Workers claim with FOR UPDATE SKIP LOCKED, so any
number of app instances can run them without double work.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.session import SessionLocal, set_tenant
from app.models import Job

log = get_logger("jobs")

MAX_ATTEMPTS = 5
Handler = Callable[[AsyncSession, uuid.UUID, dict[str, Any]], Awaitable[None]]
HANDLERS: dict[str, Handler] = {}


class JobDeferred(Exception):
    """Can't run yet (e.g. no AI provider configured). Retried later without using an attempt."""

    def __init__(self, reason: str, delay: timedelta = timedelta(minutes=15)):
        super().__init__(reason)
        self.delay = delay


def handler(kind: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


# Set after a transaction that queued jobs commits, so the worker starts at once instead of
# waiting out its idle sleep. (Set after commit: before it, the job isn't visible yet.)
wakeup = asyncio.Event()


@event.listens_for(Session, "after_commit")
def _wake_worker(session: Session) -> None:
    if session.info.pop("jobs_enqueued", False):
        wakeup.set()


@event.listens_for(Session, "after_rollback")
def _forget_enqueued(session: Session) -> None:
    session.info.pop("jobs_enqueued", None)


async def seconds_until_next_job() -> float | None:
    """When the next queued job becomes due (0 if one is due now), or None if none are queued."""
    async with SessionLocal() as session:
        due = await session.scalar(
            text("SELECT extract(epoch FROM min(run_after) - now()) FROM jobs WHERE status = 'queued'")
        )
    return None if due is None else max(0.0, float(due))


async def enqueue(
    session: AsyncSession,
    kind: str,
    organization_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
    delay: timedelta | None = None,
) -> None:
    """Queue a job. With a dedupe key, an identical job already waiting is not queued twice."""
    stmt = insert(Job).values(
        id=uuid.uuid4(),
        kind=kind,
        organization_id=organization_id,
        payload=payload,
        dedupe_key=dedupe_key,
        run_after=datetime.now(UTC) + (delay or timedelta()),
    )
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["kind", "dedupe_key"], index_where=text("status = 'queued'"))
    await session.execute(stmt)
    session.sync_session.info["jobs_enqueued"] = True


_CLAIM = text(
    """
    UPDATE jobs SET status = 'running', attempts = attempts + 1, locked_at = now()
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY run_after
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, kind, organization_id, payload, attempts
    """
)

# A worker that died mid-job leaves it "running"; hand it back after 10 minutes.
_RECLAIM = text(
    "UPDATE jobs SET status = 'queued' WHERE status = 'running' AND locked_at < now() - interval '10 minutes'"
)


async def run_one() -> bool:
    """Claim and run a single job. Returns False when nothing was ready."""
    async with SessionLocal() as session:
        await session.execute(_RECLAIM)
        row = (await session.execute(_CLAIM)).first()
        await session.commit()
    if row is None:
        return False

    job_id, kind, org_id, payload, attempts = row
    fn = HANDLERS.get(kind)
    status, run_after, error = "done", None, None
    try:
        if fn is None:
            raise RuntimeError(f"no handler for {kind}")
        async with SessionLocal() as session:
            await set_tenant(session, org_id)
            await fn(session, org_id, payload)
            await session.commit()
    except JobDeferred as exc:
        status, error = "queued", str(exc)[:500]
        run_after = datetime.now(UTC) + exc.delay
        attempts -= 1  # waiting isn't failing
    except Exception as exc:
        log.exception("job_failed", job_id=str(job_id), kind=kind, attempt=attempts)
        error = f"{type(exc).__name__}: {exc}"[:500]
        if attempts < MAX_ATTEMPTS:
            status, run_after = "queued", datetime.now(UTC) + timedelta(seconds=30 * 2**attempts)
        else:
            status = "failed"

    async with SessionLocal() as session:
        await session.execute(
            text(
                "UPDATE jobs SET status = :status, error = :error, attempts = :attempts, "
                "run_after = COALESCE(:run_after, run_after), locked_at = NULL WHERE id = :id"
            ),
            {"status": status, "error": error, "attempts": attempts, "run_after": run_after, "id": job_id},
        )
        # Keep the table small: finished jobs are only interesting for a day.
        await session.execute(text("DELETE FROM jobs WHERE status = 'done' AND created_at < now() - interval '1 day'"))
        await session.commit()
    log.info("job_finished", kind=kind, status=status, attempt=attempts)
    return True


async def run_pending(limit: int = 100) -> int:
    """Run ready jobs until none are left (used by tests and the worker loop)."""
    done = 0
    while done < limit and await run_one():
        done += 1
    return done
