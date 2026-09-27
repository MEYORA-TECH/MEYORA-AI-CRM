import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger
from app.database.metrics import DbStats, current

log = get_logger("http")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # The API only serves JSON; nothing should ever execute from it.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID, logs one line per request, and sets security headers."""

    def __init__(self, app, *, hsts: bool):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        if len(request_id) > 64:
            request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        stats = DbStats()
        token = current.set(stats)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            current.reset(token)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        # Visible in the browser's network panel (Timing tab).
        response.headers["Server-Timing"] = (
            f'db;desc="{stats.queries} queries";dur={stats.ms:.1f}, total;dur={elapsed_ms}'
        )

        response.headers["X-Request-ID"] = request_id
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if self.hsts:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=elapsed_ms,
            db_queries=stats.queries,
            db_ms=round(stats.ms, 1),
        )
        return response
