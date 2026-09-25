from tests.conftest import XHR, register


async def test_register_creates_owner_with_default_pipeline(client, owner):
    assert owner.me["role"] == "owner"
    assert "org:delete" in owner.me["permissions"]
    assert owner.refresh_cookie

    pipelines = (await owner.get("/api/pipelines")).json()
    assert len(pipelines) == 1
    assert [s["name"] for s in pipelines[0]["stages"]] == [
        "Lead", "Qualified", "Discovery", "Proposal", "Negotiation", "Won", "Lost",
    ]


async def test_duplicate_email_is_rejected(client, owner):
    resp = await client.post("/api/auth/register", json={
        "email": owner.email.upper(), "password": "another-long-password",
        "full_name": "Copy", "organization_name": "Copy Co",
    })
    assert resp.status_code == 409


async def test_register_requires_org_or_invite(client):
    resp = await client.post("/api/auth/register", json={
        "email": "a@example.com", "password": "long-enough-password", "full_name": "A",
    })
    assert resp.status_code == 422


async def test_short_password_rejected(client):
    resp = await client.post("/api/auth/register", json={
        "email": "a@example.com", "password": "short", "full_name": "A", "organization_name": "X",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_login_success_and_failure(client, owner):
    bad = await client.post("/api/auth/login", json={"email": owner.email, "password": "wrong-password"})
    assert bad.status_code == 401
    unknown = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x" * 12})
    assert unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]

    ok = await client.post("/api/auth/login", json={"email": owner.email, "password": "correct-horse-battery"})
    assert ok.status_code == 200
    assert ok.json()["me"]["current_organization_id"] == owner.org_id


async def test_protected_endpoint_requires_token(client):
    resp = await client.get("/api/companies")
    assert resp.status_code == 401
    resp = await client.get("/api/companies", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_refresh_rotates_and_detects_reuse(client, owner):
    first = owner.refresh_cookie
    cookie = {"Cookie": f"meyora_rt={first}"}

    rotated = await client.post("/api/auth/refresh", headers={**XHR, **cookie})
    assert rotated.status_code == 200
    second = rotated.cookies.get("meyora_rt")
    assert second and second != first

    # Replaying the old token revokes the whole family, including the new token.
    replay = await client.post("/api/auth/refresh", headers={**XHR, **cookie})
    assert replay.status_code == 401
    after = await client.post("/api/auth/refresh", headers={**XHR, "Cookie": f"meyora_rt={second}"})
    assert after.status_code == 401


async def test_refresh_requires_csrf_header(client, owner):
    resp = await client.post("/api/auth/refresh", headers={"Cookie": f"meyora_rt={owner.refresh_cookie}"})
    assert resp.status_code == 403


async def test_logout_revokes_refresh_token(client, owner):
    cookie = {"Cookie": f"meyora_rt={owner.refresh_cookie}"}
    out = await client.post("/api/auth/logout", headers={**XHR, **cookie})
    assert out.status_code == 204
    again = await client.post("/api/auth/refresh", headers={**XHR, **cookie})
    assert again.status_code == 401


async def test_switch_organization(client, owner):
    from tests.conftest import invite_and_join

    second_org_owner = await register(client, org="Second Org")
    joined = await invite_and_join(second_org_owner, "member")
    # The invited user now belongs to Second Org only; invite them to Acme too.
    resp = await owner.post("/api/organization/invitations", {"email": joined.email, "role": "manager"})
    token = resp.json()["token"]
    accepted = await joined.post("/api/auth/accept-invitation", {"token": token})
    assert accepted.status_code == 200
    me = accepted.json()["me"]
    assert me["current_organization_id"] == owner.org_id
    assert me["role"] == "manager"
    assert len(me["memberships"]) == 2

    switched = await joined.post("/api/auth/switch-organization", {"organization_id": second_org_owner.org_id})
    assert switched.status_code == 200
    assert switched.json()["me"]["role"] == "member"
