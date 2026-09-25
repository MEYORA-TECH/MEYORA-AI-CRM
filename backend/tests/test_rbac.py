from tests.conftest import invite_and_join


async def test_member_can_edit_but_not_delete(owner):
    member = await invite_and_join(owner, "member")
    assert member.me["role"] == "member"

    company = (await owner.post("/api/companies", {"name": "ABC"})).json()
    assert (await member.get(f"/api/companies/{company['id']}")).status_code == 200
    assert (await member.patch(f"/api/companies/{company['id']}", {"city": "Chennai"})).status_code == 200
    assert (await member.delete(f"/api/companies/{company['id']}")).status_code == 403

    manager = await invite_and_join(owner, "manager")
    assert (await manager.delete(f"/api/companies/{company['id']}")).status_code == 204
    assert (await owner.get(f"/api/companies/{company['id']}")).status_code == 404


async def test_member_cannot_manage_members_or_pipelines(owner):
    member = await invite_and_join(owner, "member")
    resp = await member.post("/api/organization/invitations", {"email": "x@example.com", "role": "member"})
    assert resp.status_code == 403
    pipeline_id = (await member.get("/api/pipelines")).json()[0]["id"]
    assert (await member.patch(f"/api/pipelines/{pipeline_id}", {"name": "Mine"})).status_code == 403
    assert (await member.get("/api/organization/audit-logs")).status_code == 403
    assert (await member.get("/api/organization/members")).status_code == 200


async def test_admin_cannot_touch_owner(owner):
    admin = await invite_and_join(owner, "admin")
    assert (await admin.patch(f"/api/organization/members/{owner.user_id}", {"role": "member"})).status_code == 403
    resp = await admin.post("/api/organization/invitations", {"email": "boss@example.com", "role": "owner"})
    assert resp.status_code == 403


async def test_last_owner_cannot_be_demoted_or_leave(owner):
    resp = await owner.patch(f"/api/organization/members/{owner.user_id}", {"role": "admin"})
    assert resp.status_code == 409
    assert (await owner.delete(f"/api/organization/members/{owner.user_id}")).status_code == 409


async def test_removed_member_loses_access_immediately(owner):
    member = await invite_and_join(owner, "member")
    assert (await member.get("/api/companies")).status_code == 200
    assert (await owner.delete(f"/api/organization/members/{member.user_id}")).status_code == 204
    assert (await member.get("/api/companies")).status_code == 403


async def test_invitation_is_single_use_and_email_bound(client, owner):
    from tests.conftest import register

    resp = await owner.post("/api/organization/invitations", {"email": "invitee@example.com", "role": "member"})
    token = resp.json()["token"]

    wrong = await client.post("/api/auth/register", json={
        "email": "someone-else@example.com", "password": "long-enough-password",
        "full_name": "Wrong", "invite_token": token,
    })
    assert wrong.status_code == 403

    await register(client, invite_token=token, email="invitee@example.com")
    reuse = await client.post("/api/auth/register", json={
        "email": "invitee2@example.com", "password": "long-enough-password",
        "full_name": "Again", "invite_token": token,
    })
    assert reuse.status_code == 422
