"""Platform admin: installation settings and the overview, for platform admins only."""

import uuid

import httpx
import pytest
from sqlalchemy import text, update

from app.ai import registry
from app.database.session import SessionLocal
from app.models import User
from app.services import api_keys
from tests.conftest import XHR
from tests.test_ai import ScriptedProvider, chat, entry, text_turn

CLIENT_ID = "1234-abc.apps.googleusercontent.com"
SECRET = "GOCSPX-test-secret-value-9876"


async def make_admin(account):
    async with SessionLocal() as session:
        await session.execute(update(User).where(User.id == uuid.UUID(account.user_id)).values(is_platform_admin=True))
        await session.commit()


async def put(account, path, body):
    return await account.client.put(path, json=body, headers={**account.headers, **XHR})


async def test_only_platform_admins_get_in(owner):
    # A workspace owner is not a platform admin.
    for path in ("/api/platform/overview", "/api/platform/settings"):
        assert (await owner.get(path)).status_code == 403
    assert (await put(owner, "/api/platform/google", {"sign_in_enabled": True})).status_code == 403
    assert (await owner.get("/api/auth/me")).json()["is_platform_admin"] is False
    await make_admin(owner)
    assert (await owner.get("/api/auth/me")).json()["is_platform_admin"] is True
    assert (await owner.get("/api/platform/settings")).status_code == 200


async def test_google_can_be_set_up_and_switched_from_the_app(owner):
    await make_admin(owner)
    assert (await owner.client.get("/api/auth/providers")).json()["google"] is False

    bad = await put(owner, "/api/platform/google", {"client_id": "not-a-client-id"})
    assert bad.status_code == 422
    # The switch alone isn't enough: without credentials sign-in stays off.
    out = (await put(owner, "/api/platform/google", {"sign_in_enabled": True})).json()["google"]
    assert out["sign_in_switch"] is True and out["sign_in_live"] is False and out["ready"] is False

    resp = await put(owner, "/api/platform/google", {"client_id": CLIENT_ID, "client_secret": SECRET, "gmail_enabled": True})
    assert resp.status_code == 200, resp.text
    g = resp.json()["google"]
    assert g["ready"] and g["sign_in_live"] and g["gmail_live"] and g["secret_last4"] == "9876"
    assert SECRET not in resp.text
    assert g["redirect_uris"]["sign_in"].endswith("/api/auth/google/callback")
    assert (await owner.client.get("/api/auth/providers")).json() == {"password": True, "google": True, "gmail": True}

    async with SessionLocal() as session:
        stored = await session.scalar(text("SELECT value FROM platform_settings WHERE key = 'google_client_secret'"))
        assert stored.startswith("v1:") and SECRET not in stored

    # Clearing a saved value falls back to the server's environment (empty in tests): off again.
    g = (await put(owner, "/api/platform/google", {"client_secret": None})).json()["google"]
    assert g["secret_set"] is False and g["sign_in_live"] is False


@pytest.fixture
def key_check(monkeypatch):
    monkeypatch.setattr(api_keys, "transport", httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []})))


async def test_shared_keys_feed_every_workspace(owner, other_org, key_check):
    await make_admin(owner)
    key = "gsk_shared_" + "k" * 40
    resp = await put(owner, "/api/platform/keys/groq", {"value": key})
    assert resp.status_code == 200 and key not in resp.text
    groq = next(k for k in resp.json()["keys"] if k["provider"] == "groq")
    assert groq["source"] == "saved" and groq["last4"] == "kkkk"
    assert next(p for p in registry.pool() if p.id == "groq").provider._api_key == key
    # Workspaces without their own key now show the shared one as available.
    other_keys = (await other_org.get("/api/organization/api-keys")).json()
    assert next(k for k in other_keys if k["provider"] == "groq")["source"] == "server"

    gone = await owner.client.delete("/api/platform/keys/groq", headers={**owner.headers, **XHR})
    assert gone.status_code == 204
    assert all(p.id != "groq" for p in registry.pool())


async def test_overview_counts_each_workspace_separately(owner, other_org, use_pool):
    await make_admin(owner)
    for name in ("A1", "A2", "A3"):
        await owner.post("/api/companies", {"name": name})
    await other_org.post("/api/companies", {"name": "G1"})
    await other_org.post("/api/leads", {"name": "Lead G"})
    use_pool(entry(ScriptedProvider("groq", [text_turn("hi")])))
    await chat(other_org, "hello")

    o = (await owner.get("/api/platform/overview", params={"tz": "Asia/Kolkata"})).json()
    assert o["workspaces"] == 2 and o["users"] == 2
    rows = {r["name"]: r for r in o["workspace_list"]}
    assert rows["Acme Traders"]["companies"] == 3 and rows["Acme Traders"]["leads"] == 0
    assert rows["Globex Industries"]["companies"] == 1 and rows["Globex Industries"]["leads"] == 1
    assert rows["Globex Industries"]["ai_tokens_30d"] == 940 and o["ai_tokens_30d"] == 940
    assert o["providers"] == [{"provider": "groq", "tokens": 940}]
    assert len(o["daily_tokens"]) == 14 and o["daily_tokens"][-1]["tokens"] == 940
    assert o["health"]["google_ready"] is False
    # Nothing leaks: the admin's own workspace still sees only its own records.
    assert (await owner.get("/api/companies")).json()["total"] == 3
