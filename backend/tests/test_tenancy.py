"""Tenant isolation, checked at the API layer and directly against row-level security."""

import uuid

from sqlalchemy import text

from app.database.session import SessionLocal, set_tenant


async def test_other_org_cannot_see_or_touch_records(owner, other_org):
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()

    assert (await other_org.get(f"/api/companies/{company['id']}")).status_code == 404
    assert (await other_org.patch(f"/api/companies/{company['id']}", {"name": "Hacked"})).status_code == 404
    assert (await other_org.delete(f"/api/companies/{company['id']}")).status_code == 404
    assert (await other_org.get("/api/companies")).json()["total"] == 0
    assert (await other_org.get(f"/api/timeline/companies/{company['id']}")).status_code == 404

    still = await owner.get(f"/api/companies/{company['id']}")
    assert still.json()["name"] == "ABC Manufacturing"


async def test_cannot_link_records_across_orgs(owner, other_org):
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()

    resp = await other_org.post("/api/contacts", {"first_name": "Ravi", "company_id": company["id"]})
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0]["field"] == "company_id"

    resp = await other_org.post("/api/companies", {"name": "X", "owner_id": owner.user_id})
    assert resp.status_code == 422

    stage_id = (await owner.get("/api/pipelines")).json()[0]["stages"][0]["id"]
    resp = await other_org.post("/api/deals", {"name": "Steal", "stage_id": stage_id})
    assert resp.status_code == 404


async def test_rls_blocks_rows_even_without_app_filters(owner, other_org):
    await owner.post("/api/companies", {"name": "ABC Manufacturing"})
    await other_org.post("/api/companies", {"name": "Globex Subsidiary"})

    count = text("SELECT count(*) FROM companies")  # no WHERE clause at all

    async with SessionLocal() as session:
        assert await session.scalar(count) == 0  # no tenant set: fail closed

    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        assert await session.scalar(count) == 1
        names = (await session.execute(text("SELECT name FROM companies"))).scalars().all()
        assert names == ["ABC Manufacturing"]

    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(other_org.org_id))
        assert await session.scalar(count) == 1


async def test_rls_blocks_cross_tenant_insert(owner, other_org):
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(other_org.org_id))
        try:
            await session.execute(
                text("INSERT INTO companies (organization_id, name, status) VALUES (:org, 'Injected', 'prospect')"),
                {"org": owner.org_id},
            )
            await session.commit()
            inserted = True
        except Exception as exc:  # row-level security violation
            inserted = False
            assert "row-level security" in str(exc)
    assert not inserted


async def test_tenant_setting_does_not_leak_between_transactions(owner):
    await owner.post("/api/companies", {"name": "ABC Manufacturing"})
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        assert await session.scalar(text("SELECT count(*) FROM companies")) == 1
        await session.commit()
        session.info.pop("organization_id")
        # The next transaction on the same session starts without a tenant.
        assert await session.scalar(text("SELECT count(*) FROM companies")) == 0
