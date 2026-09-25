from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import RateLimited
from app.database.session import SessionLocal

# Fixed window counter in Postgres: shared across instances and survives restarts,
# which an in-memory limiter on a free-tier host would not.
_HIT = text(
    """
    INSERT INTO rate_limit_buckets (key, window_start, count) VALUES (:key, :now, 1)
    ON CONFLICT (key) DO UPDATE SET
      count = CASE WHEN rate_limit_buckets.window_start < :cutoff
                   THEN 1 ELSE rate_limit_buckets.count + 1 END,
      window_start = CASE WHEN rate_limit_buckets.window_start < :cutoff
                          THEN :now ELSE rate_limit_buckets.window_start END
    RETURNING count
    """
)


async def hit(key: str, *, limit: int, window_seconds: int) -> None:
    """Count one attempt; raise RateLimited once `limit` is exceeded within the window."""
    if not get_settings().rate_limit_enabled:
        return
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=window_seconds)
    # Separate session so the attempt is recorded even if the caller's work fails.
    async with SessionLocal() as session:
        count = await session.scalar(_HIT, {"key": key[:300], "now": now, "cutoff": cutoff})
        await session.commit()
    if count is not None and count > limit:
        raise RateLimited("Too many attempts. Please wait a few minutes and try again.")
