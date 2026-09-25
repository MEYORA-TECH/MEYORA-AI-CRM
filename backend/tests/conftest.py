"""Tests run against a real Postgres (the `meyora_test` database) so RLS is exercised."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values

_ROOT = Path(__file__).resolve().parents[2]
_env = {**dotenv_values(_ROOT / ".env"), **os.environ}
TEST_DB = _env.get("TEST_DATABASE_URL")
if not TEST_DB:
    raise RuntimeError("Set TEST_DATABASE_URL (see .env.example)")

os.environ.update(
    DATABASE_URL=TEST_DB,
    APP_ENV="test",
    RATE_LIMIT_ENABLED="false",
    JWT_SECRET=_env.get("JWT_SECRET") or "test-secret-" + "x" * 40,
)


def pytest_configure(config):
    backend = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        env={**os.environ, "ALEMBIC_DATABASE_URL": TEST_DB},
        check=True,
    )


import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

XHR = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(autouse=True)
async def _clean_db():
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class Account:
    def __init__(self, client: httpx.AsyncClient, body: dict):
        self.client = client
        self.token = body["access_token"]
        self.me = body["me"]
        self.refresh_cookie: str | None = None

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def org_id(self) -> str:
        return self.me["current_organization_id"]

    @property
    def user_id(self) -> str:
        return self.me["id"]

    async def get(self, url, **kw):
        return await self.client.get(url, headers=self.headers, **kw)

    async def post(self, url, json=None, **kw):
        return await self.client.post(url, json=json, headers={**self.headers, **XHR}, **kw)

    async def patch(self, url, json=None, **kw):
        return await self.client.patch(url, json=json, headers=self.headers, **kw)

    async def delete(self, url, **kw):
        return await self.client.delete(url, headers=self.headers, **kw)


async def register(client, *, org: str | None = "Acme Traders", invite_token: str | None = None,
                   email: str | None = None, name: str = "Test User") -> Account:
    body = {
        "email": email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        "password": "correct-horse-battery",
        "full_name": name,
    }
    if invite_token:
        body["invite_token"] = invite_token
    else:
        body["organization_name"] = org
    resp = await client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    account = Account(client, resp.json())
    account.refresh_cookie = resp.cookies.get("meyora_rt")
    account.email = body["email"]
    return account


@pytest.fixture
async def owner(client) -> Account:
    return await register(client, org="Acme Traders", name="Olivia Owner")


@pytest.fixture
async def other_org(client) -> Account:
    return await register(client, org="Globex Industries", name="Gary Globex")


async def invite_and_join(owner: Account, role: str, name: str = "Invited Person") -> Account:
    email = f"{role}-{uuid.uuid4().hex[:6]}@example.com"
    resp = await owner.post("/api/organization/invitations", {"email": email, "role": role})
    assert resp.status_code == 201, resp.text
    return await register(owner.client, invite_token=resp.json()["token"], email=email, name=name)
