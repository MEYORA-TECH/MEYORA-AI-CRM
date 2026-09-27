"""Organisation API keys: owner-managed, encrypted, used by the AI pool, invisible to the assistant."""

import ast
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, text

from app.ai import registry
from app.database.session import SessionLocal, set_tenant
from app.models import OrganizationApiKey
from app.services import api_keys
from tests.conftest import XHR, invite_and_join

GROQ_KEY = "gsk_test_" + "a" * 40 + "WXYZ"


@pytest.fixture
def providers(monkeypatch):
    """Fake provider APIs: keys ending in 'BAD' are rejected."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.headers.get("authorization", "").endswith("BAD"):
            return httpx.Response(401, json={"error": "invalid key"})
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(api_keys, "transport", httpx.MockTransport(handler))
    api_keys._cache.clear()
    registry._org_pools.clear()
    return seen


async def put_key(account, provider, value):
    return await account.client.put(f"/api/organization/api-keys/{provider}", json={"value": value},
                                    headers={**account.headers, **XHR})


async def test_owner_saves_a_checked_key_that_is_never_shown_again(owner, providers):
    resp = await put_key(owner, "groq", GROQ_KEY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "organization" and body["last4"] == "WXYZ" and body["verified_at"]
    assert GROQ_KEY not in resp.text
    assert providers == [("api.groq.com", f"Bearer {GROQ_KEY}")]

    listed = (await owner.get("/api/organization/api-keys")).json()
    assert {k["provider"] for k in listed} == {"groq", "openrouter", "gemini", "tavily"}
    assert GROQ_KEY not in str(listed)

    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        row = await session.scalar(select(OrganizationApiKey))
        assert row.encrypted_value.startswith("v1:") and GROQ_KEY not in row.encrypted_value
        audit = await session.scalar(text("SELECT changes::text FROM audit_logs WHERE action = 'api_key.update'"))
        assert "WXYZ" in audit and GROQ_KEY not in audit


async def test_rejected_or_malformed_keys_are_not_saved(owner, providers):
    bad = await put_key(owner, "groq", "gsk_" + "b" * 30 + "BAD")
    assert bad.status_code == 422 and "rejected this key" in bad.json()["error"]["message"]
    wrong_prefix = await put_key(owner, "tavily", "sk-" + "c" * 30)
    assert wrong_prefix.status_code == 422 and "tvly-" in wrong_prefix.json()["error"]["message"]
    assert all(k["source"] != "organization" for k in (await owner.get("/api/organization/api-keys")).json())


async def test_only_the_owner_can_manage_keys(owner, providers):
    admin = await invite_and_join(owner, "admin")
    assert (await admin.get("/api/organization/api-keys")).status_code == 403
    assert (await put_key(admin, "groq", GROQ_KEY)).status_code == 403


async def test_keys_stay_inside_their_organisation_and_feed_its_ai_pool(owner, other_org, providers):
    await put_key(owner, "groq", GROQ_KEY)
    other = (await other_org.get("/api/organization/api-keys")).json()
    assert next(k for k in other if k["provider"] == "groq")["source"] != "organization"

    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        pool = await registry.pool_for(session, uuid.UUID(owner.org_id))
        groq = next(p for p in pool if p.id == "groq")
        assert groq.provider._api_key == GROQ_KEY
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(other_org.org_id))
        assert all(getattr(p.provider, "_api_key", None) != GROQ_KEY
                   for p in await registry.pool_for(session, uuid.UUID(other_org.org_id)))

    assert (await owner.client.delete("/api/organization/api-keys/groq", headers={**owner.headers, **XHR})).status_code == 204
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        assert all(getattr(p.provider, "_api_key", None) != GROQ_KEY
                   for p in await registry.pool_for(session, uuid.UUID(owner.org_id)))


def test_the_assistant_has_no_way_to_reach_api_keys():
    """No AI tool, action, prompt or index may read or write the API keys table."""
    app = Path(__file__).resolve().parents[1] / "app"
    forbidden = {"api_keys", "OrganizationApiKey", "organization_api_keys"}
    for path in [*(app / "ai" / "tools").rglob("*.py"), *(app / "ai" / "actions").rglob("*.py"),
                 app / "ai" / "prompts.py", app / "ai" / "knowledge.py", app / "ai" / "memory.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {a.attr for a in ast.walk(tree) if isinstance(a, ast.Attribute)}
        names |= {al.name.split(".")[-1] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                  for al in n.names}
        names |= {n.module.split(".")[-1] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        strings = {c.value for c in ast.walk(tree) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        assert not (names & forbidden), f"{path.name} references API keys"
        assert not any(f in s for s in strings for f in forbidden), f"{path.name} mentions API keys"

    from app.services.crud import INDEXED
    assert "api_key" not in INDEXED


async def test_key_lookups_are_cached_so_ai_requests_stay_fast(owner, providers):
    """After the first load, getting an organisation's keys and provider pool costs no database query."""
    from sqlalchemy import event

    from app.database.session import engine

    await put_key(owner, "groq", GROQ_KEY)
    org_id = uuid.UUID(owner.org_id)
    statements = []

    def count(*_args):
        statements.append(1)

    async with SessionLocal() as session:
        await set_tenant(session, org_id)
        first = await registry.pool_for(session, org_id)
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        try:
            for _ in range(20):
                assert await registry.pool_for(session, org_id) is first  # same built pool, not rebuilt
                await api_keys.resolve(session, org_id, "tavily")
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert statements == []
