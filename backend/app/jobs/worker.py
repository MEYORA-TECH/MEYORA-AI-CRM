"""In-process worker loop, started with the app. One loop per instance is enough on the free tier."""

import asyncio
import contextlib

from app.core.logging import get_logger
from app.jobs import handlers  # noqa: F401  (registers job handlers)
from app.jobs.queue import run_one
from app.services import platform  # noqa: E402

log = get_logger("jobs.worker")

IDLE_SECONDS = 3.0


async def worker_loop(stop: asyncio.Event) -> None:
    log.info("job_worker_started")
    while not stop.is_set():
        try:
            await platform.refresh()  # Gmail sync reads the Google credentials
            ran = await run_one()
        except Exception:  # database hiccup: back off, keep the loop alive
            log.exception("job_worker_error")
            ran = False
        if not ran:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=IDLE_SECONDS)
    log.info("job_worker_stopped")
