"""Engine, sessions and the tenant context that drives row-level security.

Every transaction begins with `set_config('app.org_id', <org>, true)`, taken
from `session.info["organization_id"]`. The setting is transaction-local, so it
cannot leak to another request through the connection pool, and it also works
behind a transaction-mode pooler. With no organization set, the RLS policies
match nothing (fail closed).
"""

import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.metrics import instrument

_SET_ORG = text("SELECT set_config('app.org_id', :org_id, true)")

settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    # No ping on every checkout (a full round trip, ~0.5s to a distant database);
    # connections idle for a while are checked in _ping_if_idle instead.
    pool_pre_ping=False,
    pool_size=5,
    max_overflow=5,
    connect_args={"statement_cache_size": settings.db_statement_cache_size},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
instrument(engine.sync_engine)

PING_IF_IDLE_FOR = 30.0  # seconds; hosted Postgres (Neon) closes connections when it suspends


@event.listens_for(engine.sync_engine, "checkout")
def _ping_if_idle(dbapi_connection, record, _proxy) -> None:
    last_used = record.info.get("last_used")
    if last_used is None or time.monotonic() - last_used < PING_IF_IDLE_FOR:
        return
    try:
        alive = engine.dialect.do_ping(dbapi_connection)
    except Exception as exc:
        raise DisconnectionError() from exc  # the pool retries with a fresh connection
    if not alive:
        raise DisconnectionError()


@event.listens_for(engine.sync_engine, "checkin")
def _mark_used(_dbapi_connection, record) -> None:
    record.info["last_used"] = time.monotonic()


@event.listens_for(Session, "after_begin")
def _apply_tenant(session: Session, _transaction, connection) -> None:
    # The request's auth query sets the tenant itself (see auth.deps.get_tenant), saving a round trip.
    if session.info.pop("tenant_set_by_first_query", False):
        return
    org_id = session.info.get("organization_id")
    connection.execute(_SET_ORG, {"org_id": str(org_id) if org_id else ""})


async def set_tenant(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Bind the session to an organization, including the transaction already open."""
    session.info["organization_id"] = organization_id
    if session.in_transaction():
        await session.execute(_SET_ORG, {"org_id": str(organization_id)})


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
