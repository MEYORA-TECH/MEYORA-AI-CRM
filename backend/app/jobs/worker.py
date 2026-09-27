"""In-process worker loop, started with the app. One loop per instance is enough on the free tier."""

import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger
from app.jobs import handlers  # noqa: F401  (registers job handlers)
from app.jobs.queue import run_one, seconds_until_next_job, wakeup
from app.services import platform

log = get_logger("jobs.worker")

IDLE_SECONDS = 3.0


async def worker_loop(stop: asyncio.Event) -> None:
    """Run jobs as they come due. When idle it sleeps until the next job is due (at most
    jobs_idle_max_seconds), waking at once when this process queues new work, so an idle
    app doesn't poll the database and a serverless database can suspend."""
    log.info("job_worker_started")
    idle_max = get_settings().jobs_idle_max_seconds
    while not stop.is_set():
        try:
            await platform.refresh()  # Gmail sync reads the Google credentials
            if await run_one():
                continue
            due = await seconds_until_next_job()
        except Exception:  # database hiccup: back off, keep the loop alive
            log.exception("job_worker_error")
            due = IDLE_SECONDS
        wait = idle_max if due is None else min(max(due, 0.2), idle_max)
        await _sleep(stop, wait)
    log.info("job_worker_stopped")


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    """Sleep until `seconds` pass, new work is queued, or the app stops."""
    wakeup.clear()
    waits = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(wakeup.wait())]
    try:
        await asyncio.wait(waits, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for w in waits:
            w.cancel()
