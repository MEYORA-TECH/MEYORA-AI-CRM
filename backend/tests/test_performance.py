"""Query budgets per page. Every query is a network round trip to the database, so these stay low."""

import re

import pytest


def queries(resp) -> int:
    return int(re.search(r'db;desc="(\d+) queries"', resp.headers["server-timing"]).group(1))


@pytest.fixture
async def filled(owner):
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()
    await owner.post("/api/contacts", {"first_name": "Ravi", "company_id": company["id"]})
    await owner.post("/api/leads", {"name": "Meera", "company_name": "Beta Logistics"})
    await owner.post("/api/deals", {"name": "ABC deal", "company_id": company["id"], "amount": 100000})
    await owner.post("/api/tasks", {"title": "Call Ravi", "company_id": company["id"]})
    return company


BUDGETS = {
    "/api/companies": 2,
    "/api/contacts": 2,  # company comes in the same query
    "/api/leads": 2,
    "/api/deals": 2,
    "/api/tasks?assignee=any": 2,
    "/api/organization": 2,
    "/api/dashboard": 11,
}


@pytest.mark.parametrize("path", list(BUDGETS))
async def test_pages_stay_within_their_query_budget(owner, filled, path):
    resp = await owner.get(path)
    assert resp.status_code == 200, resp.text
    assert queries(resp) <= BUDGETS[path], f"{path}: {queries(resp)} queries (budget {BUDGETS[path]})"


async def test_record_page_budget(owner, filled):
    resp = await owner.get(f"/api/companies/{filled['id']}")
    assert queries(resp) <= 2
