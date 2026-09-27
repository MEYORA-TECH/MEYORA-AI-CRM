"""Per-request database counters, reported in the Server-Timing header and the request log."""

import time
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class DbStats:
    queries: int = 0
    ms: float = 0.0


# The middleware puts a fresh DbStats here; tasks spawned for the request share the same object.
current: ContextVar[DbStats | None] = ContextVar("db_stats", default=None)


def instrument(engine: Engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _start(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_started", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _end(conn, cursor, statement, parameters, context, executemany):
        started = conn.info["query_started"].pop()
        if stats := current.get():
            stats.queries += 1
            stats.ms += (time.perf_counter() - started) * 1000
