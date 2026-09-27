import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.database.session import SessionLocal, set_tenant


async def _stages(account) -> dict[str, str]:
    pipeline = (await account.get("/api/pipelines")).json()[0]
    return {s["name"]: s["id"] for s in pipeline["stages"]}


async def test_company_crud_search_sort_and_pagination(owner):
    for name, city in [("ABC Manufacturing", "Chennai"), ("Beta Logistics", "Pune"), ("Gamma Steel", "Chennai")]:
        assert (await owner.post("/api/companies", {"name": name, "city": city, "tags": ["Mfg", "mfg"]})).status_code == 201

    page = (await owner.get("/api/companies", params={"q": "manu"})).json()
    assert page["total"] == 1 and page["items"][0]["name"] == "ABC Manufacturing"
    assert page["items"][0]["tags"] == ["mfg"]

    sorted_page = (await owner.get("/api/companies", params={"sort": "name", "page_size": 2})).json()
    assert [c["name"] for c in sorted_page["items"]] == ["ABC Manufacturing", "Beta Logistics"]
    assert sorted_page["total"] == 3
    page2 = (await owner.get("/api/companies", params={"sort": "name", "page_size": 2, "page": 2})).json()
    assert [c["name"] for c in page2["items"]] == ["Gamma Steel"]

    assert (await owner.get("/api/companies", params={"sort": "password"})).status_code == 422
    assert (await owner.get("/api/companies", params={"q": "%"})).json()["total"] == 0


async def test_update_records_audit_changes(owner):
    company = (await owner.post("/api/companies", {"name": "ABC"})).json()
    await owner.patch(f"/api/companies/{company['id']}", {"city": "Chennai", "name": "ABC"})
    logs = (await owner.get("/api/organization/audit-logs", params={"entity_id": company["id"]})).json()
    actions = [log["action"] for log in logs["items"]]
    assert actions == ["company.update", "company.create"]
    assert logs["items"][0]["changes"] == {"city": {"old": None, "new": "Chennai"}}


async def test_lead_conversion(owner):
    lead = (await owner.post("/api/leads", {
        "name": "Ravi Kumar", "company_name": "ABC Manufacturing", "email": "ravi@abc.in",
        "industry": "Manufacturing", "source": "Referral", "tags": ["hot"],
    })).json()
    stages = await _stages(owner)

    resp = await owner.post(f"/api/leads/{lead['id']}/convert", {
        "deal_amount": 300000, "stage_id": stages["Discovery"],
    })
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["lead"]["status"] == "converted"

    contact = (await owner.get(f"/api/contacts/{result['contact_id']}")).json()
    assert (contact["first_name"], contact["last_name"]) == ("Ravi", "Kumar")
    assert contact["company"]["name"] == "ABC Manufacturing"

    deal = (await owner.get(f"/api/deals/{result['deal_id']}")).json()
    assert deal["amount"] == 300000
    assert deal["currency"] == "INR"
    assert deal["stage_id"] == stages["Discovery"]
    assert deal["probability"] == 35
    assert deal["lead_id"] == lead["id"]

    again = await owner.post(f"/api/leads/{lead['id']}/convert", {})
    assert again.status_code == 409

    # Status "converted" can only be reached through the convert action.
    other = (await owner.post("/api/leads", {"name": "Someone"})).json()
    assert (await owner.patch(f"/api/leads/{other['id']}", {"status": "converted"})).status_code == 422


async def test_conversion_reuses_existing_company_and_contact(owner):
    company = (await owner.post("/api/companies", {"name": "Flow Well Castings"})).json()
    contact = (await owner.post("/api/contacts", {"first_name": "Anand", "email": "anand@flowwell.in", "company_id": company["id"]})).json()
    lead = (await owner.post("/api/leads", {"name": "Anand R", "company_name": "flow well castings", "email": "Anand@flowwell.in"})).json()
    result = (await owner.post(f"/api/leads/{lead['id']}/convert", {"create_deal": False})).json()
    assert (result["company_id"], result["contact_id"]) == (company["id"], contact["id"])
    assert (await owner.get("/api/companies")).json()["total"] == 1
    assert (await owner.get("/api/contacts")).json()["total"] == 1

    # A company-only lead (imported prospect) links the company and creates no contact.
    only = (await owner.post("/api/leads", {"name": "Flow Well Castings", "company_name": "Flow Well Castings"})).json()
    result = (await owner.post(f"/api/leads/{only['id']}/convert", {})).json()
    assert result["company_id"] == company["id"] and result["contact_id"] is None and result["deal_id"]
    assert (await owner.get("/api/contacts")).json()["total"] == 1


async def test_deal_stage_changes(owner):
    stages = await _stages(owner)
    deal = (await owner.post("/api/deals", {"name": "Fleet tracking", "amount": 150000})).json()
    assert deal["stage_id"] == stages["Lead"]
    assert deal["status"] == "open" and deal["probability"] == 10

    won = (await owner.post(f"/api/deals/{deal['id']}/move", {"stage_id": stages["Won"]})).json()
    assert won["status"] == "won" and won["probability"] == 100 and won["closed_at"]

    reopened = (await owner.patch(f"/api/deals/{deal['id']}", {"stage_id": stages["Proposal"], "probability": 60})).json()
    assert reopened["status"] == "open" and reopened["probability"] == 60 and reopened["closed_at"] is None

    timeline = (await owner.get(f"/api/timeline/deals/{deal['id']}")).json()
    subjects = [i["title"] for i in timeline if i["type"] == "stage_change"]
    assert subjects == ["Stage changed to Proposal", "Stage changed to Won", "Deal created in Lead"]

    board = (await owner.get("/api/deals/board")).json()
    proposal = next(c for c in board["columns"] if c["name"] == "Proposal")
    assert proposal["count"] == 1 and proposal["total_amount"] == 150000


async def test_stage_with_deals_cannot_be_removed(owner):
    pipeline = (await owner.get("/api/pipelines")).json()[0]
    await owner.post("/api/deals", {"name": "D", "stage_id": pipeline["stages"][0]["id"]})
    kept = [{k: s[k] for k in ("id", "name", "probability", "kind", "color")} for s in pipeline["stages"][1:]]
    resp = await owner.patch(f"/api/pipelines/{pipeline['id']}", {"stages": kept})
    assert resp.status_code == 409


async def test_tasks_filters_and_completion(owner):
    now = datetime.now(UTC)
    overdue = (await owner.post("/api/tasks", {"title": "Call Ravi", "due_at": (now - timedelta(days=2)).isoformat()})).json()
    await owner.post("/api/tasks", {"title": "Send proposal", "due_at": (now + timedelta(days=5)).isoformat()})
    assert overdue["assignee_id"] == owner.user_id

    listed = (await owner.get("/api/tasks", params={"due": "overdue", "assignee": "me"})).json()
    assert [t["title"] for t in listed["items"]] == ["Call Ravi"]

    done = (await owner.patch(f"/api/tasks/{overdue['id']}", {"status": "completed"})).json()
    assert done["completed_at"]
    assert (await owner.get("/api/tasks", params={"due": "overdue"})).json()["total"] == 0
    reopened = (await owner.patch(f"/api/tasks/{overdue['id']}", {"status": "todo"})).json()
    assert reopened["completed_at"] is None


async def test_notes_only_editable_by_author_or_manager(owner):
    from tests.conftest import invite_and_join

    member = await invite_and_join(owner, "member")
    company = (await owner.post("/api/companies", {"name": "ABC"})).json()
    note = (await owner.post("/api/notes", {"body": "Prefers private deployment", "company_id": company["id"]})).json()
    assert (await member.patch(f"/api/notes/{note['id']}", {"body": "changed"})).status_code == 403
    assert (await owner.patch(f"/api/notes/{note['id']}", {"body": "Prefers on-prem"})).status_code == 200

    timeline = (await owner.get(f"/api/timeline/companies/{company['id']}")).json()
    assert timeline[0]["kind"] == "note" and timeline[0]["body"] == "Prefers on-prem"


async def test_dashboard_reflects_real_data(owner):
    stages = await _stages(owner)
    await owner.post("/api/leads", {"name": "L1"})
    await owner.post("/api/leads", {"name": "L2", "status": "qualified"})
    await owner.post("/api/deals", {"name": "Open deal", "amount": 100000, "stage_id": stages["Proposal"]})
    won = (await owner.post("/api/deals", {"name": "Won deal", "amount": 50000})).json()
    await owner.post(f"/api/deals/{won['id']}/move", {"stage_id": stages["Won"]})
    await owner.post("/api/deals", {"name": "USD deal", "amount": 999, "currency": "USD"})
    await owner.post("/api/tasks", {"title": "Today", "due_at": datetime.now(UTC).isoformat()})

    d = (await owner.get("/api/dashboard", params={"tz": "UTC"})).json()
    assert d["leads"]["total"] == 2 and d["leads"]["qualified"] == 1
    p = d["pipeline"]
    assert p["open_deals"] == 2 and p["won_deals"] == 1
    assert p["pipeline_value"] == 100000
    assert p["weighted_value"] == 55000
    assert p["revenue_total"] == 50000 and p["revenue_this_month"] == 50000
    assert p["other_currency_deals"] == 1
    assert d["tasks"]["due_today"] == 1
    assert d["insights"]["funnel"]["new"] == 1 and d["insights"]["funnel"]["qualified"] == 1
    assert len(d["insights"]["weeks"]) == 8

    assert (await owner.get("/api/dashboard", params={"tz": "Mars/Base"})).status_code == 422


async def test_manual_system_activities_are_rejected(owner):
    resp = await owner.post("/api/activities", {"type": "stage_change", "subject": "Fake"})
    assert resp.status_code == 422
    ok = await owner.post("/api/activities", {"type": "call", "subject": "Intro call", "duration_minutes": 20})
    assert ok.status_code == 201 and ok.json()["status"] == "completed"
    planned = await owner.post("/api/activities", {
        "type": "meeting", "subject": "Demo", "occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    })
    assert planned.json()["status"] == "planned"


async def test_dashboard_insights_for_prospecting(owner):
    abc = (await owner.post("/api/companies", {"name": "ABC Castings", "city": "Chennai", "industry": "Foundry"})).json()
    await owner.post("/api/companies", {"name": "Hosur Gears", "city": "Hosur", "industry": "Auto Components",
                                        "email": "info@hosurgears.in"})
    await owner.post("/api/companies", {"name": "Guindy Estate", "city": "Chennai", "tags": ["Outreach partner"]})
    await owner.post("/api/contacts", {"first_name": "Anand", "company_id": abc["id"], "tags": ["Decision maker"]})

    top = (await owner.post("/api/leads", {"name": "Top lead", "company_name": "ABC Castings", "score": 94,
                                           "custom_fields": {"Priority": "High"}, "email": "a@abc.in"})).json()
    called = (await owner.post("/api/leads", {"name": "Called lead", "score": 91})).json()
    await owner.post("/api/leads", {"name": "Mid lead", "score": 75})
    await owner.post("/api/leads", {"name": "Qualified lead", "score": 60, "status": "qualified"})
    await owner.post("/api/activities", {"type": "call", "subject": "Intro", "lead_id": called["id"]})
    await owner.post("/api/activities", {"type": "email", "subject": "Follow-up", "lead_id": called["id"]})
    await owner.post("/api/deals", {"name": "Quiet deal", "amount": 100000})

    i = (await owner.get("/api/dashboard", params={"tz": "Asia/Kolkata"})).json()["insights"]
    assert i["funnel"]["new"] == 3 and i["funnel"]["qualified"] == 1
    assert i["fit"] == {"top": 2, "high": 0, "medium": 1, "low": 1}
    assert i["coverage"] == {"companies": 2, "partners": 1, "with_contacts": 1, "with_decision_maker": 1, "with_email": 1}
    assert i["cities"][0] == {"label": "Chennai", "count": 1} or {"label": "Chennai", "count": 1} in i["cities"]
    assert {b["label"] for b in i["industries"]} == {"Foundry", "Auto Components"}
    # Contacted today, so not in "contact next"; best fit first.
    assert [c["name"] for c in i["contact_next"]] == ["Top lead", "Mid lead"] and i["to_contact"] == 2
    assert i["contact_next"][0]["priority"] == "High" and i["contact_next"][0]["has_email"] is True
    this_week = i["weeks"][-1]
    assert (this_week["calls"], this_week["emails"]) == (1, 1) and len(i["weeks"]) == 8
    assert i["stale_deals"] == 0 and i["stale_days"] == 14  # just opened: not stale yet
    assert top["id"] == i["contact_next"][0]["id"]

    # Three weeks old with nothing since: now it needs attention.
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        await session.execute(text("UPDATE deals SET created_at = now() - interval '21 days'"))
        await session.execute(text("UPDATE activities SET occurred_at = now() - interval '21 days' WHERE deal_id IS NOT NULL"))
        await session.commit()
    i = (await owner.get("/api/dashboard", params={"tz": "Asia/Kolkata"})).json()["insights"]
    assert i["stale_deals"] == 1
