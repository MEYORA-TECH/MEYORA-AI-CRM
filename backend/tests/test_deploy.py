"""Deployment behaviour: production safety checks, split domains, and an idle worker that lets the database sleep."""

import asyncio
import time
import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.database.session import SessionLocal
from app.integrations.google import oauth
from app.jobs import queue
from app.jobs.worker import worker_loop

PROD = {
    "app_env": "production",
    "database_url": "postgresql+asyncpg://u:p@db.example/app",
    "jwt_secret": "x" * 40,
    "encryption_key": "A" * 43 + "=",
    "cors_origins": ["https://app.meyora.in"],
    "public_url": "https://app.meyora.in",
    "_env_file": None,
}


def test_production_refuses_unsafe_settings():
    ok = Settings(**PROD)
    assert ok.cookie_secure is True  # forced on in production
    for broken, message in [
        ({"encryption_key": None}, "ENCRYPTION_KEY"),
        ({"jwt_secret": "short"}, "JWT_SECRET"),
        ({"cors_origins": ["http://localhost:5173"]}, "CORS_ORIGINS"),
        ({"public_url": "http://app.meyora.in"}, "PUBLIC_URL"),
    ]:
        with pytest.raises(ValidationError, match=message):
            Settings(**{**PROD, **broken})


def test_google_redirects_go_to_the_api_domain(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "public_url", "https://app.meyora.in")
    monkeypatch.setattr(s, "api_public_url", "https://api.meyora.in/")
    assert oauth.redirect_uri("login") == "https://api.meyora.in/api/auth/google/callback"
    assert oauth.redirect_uri("gmail") == "https://api.meyora.in/api/integrations/gmail/callback"
    monkeypatch.setattr(s, "api_public_url", None)  # one domain: the API lives under the app's /api
    assert oauth.redirect_uri("login") == "https://app.meyora.in/api/auth/google/callback"


async def test_health_does_not_need_the_database(client):
    resp = await client.get("/api/health")
    assert resp.json() == {"status": "ok"}
    assert 'db;desc="0 queries"' in resp.headers["server-timing"]  # probes never wake the database
    assert (await client.get("/api/health/db")).json()["database"] == "ok"


async def test_idle_worker_sleeps_but_wakes_when_work_is_queued(owner, monkeypatch):
    ran = asyncio.Event()

    async def ping(session, org_id, payload):
        ran.set()

    monkeypatch.setitem(queue.HANDLERS, "test_ping", ping)
    monkeypatch.setattr(get_settings(), "jobs_idle_max_seconds", 600.0)
    assert await queue.seconds_until_next_job() is None  # nothing queued: sleep the full idle time

    stop = asyncio.Event()
    loop = asyncio.create_task(worker_loop(stop))
    try:
        await asyncio.sleep(0.3)  # the worker is now in its 10-minute idle sleep
        started = time.perf_counter()
        async with SessionLocal() as session:
            await queue.enqueue(session, "test_ping", uuid.UUID(owner.org_id), {})
            await session.commit()  # the commit wakes it
        await asyncio.wait_for(ran.wait(), timeout=5)
        assert time.perf_counter() - started < 3
    finally:
        stop.set()
        await asyncio.wait_for(loop, timeout=5)


async def test_next_job_time_is_known(owner):
    from datetime import timedelta

    async with SessionLocal() as session:
        await queue.enqueue(session, "test_later", uuid.UUID(owner.org_id), {}, delay=timedelta(minutes=5))
        await session.commit()
    due = await queue.seconds_until_next_job()
    assert due is not None and 280 < due <= 300
