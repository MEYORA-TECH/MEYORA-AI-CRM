"""LinkedIn within LinkedIn's rules: public page lookup, drafts the user sends, and outreach tracking."""

import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.integrations.web import tavily
from app.services import linkedin
from tests.test_actions import confirm, proposals
from tests.test_ai import ScriptedProvider, chat, entry, text_turn, tool_turn


def test_urls_are_recognised_and_made_canonical():
    assert linkedin.normalize("https://in.linkedin.com/company/vgs-and-co?trk=x") == (
        "company", "https://www.linkedin.com/company/vgs-and-co")
    assert linkedin.normalize("http://www.linkedin.com/in/ravi-kumar-12/") == (
        "person", "https://www.linkedin.com/in/ravi-kumar-12")
    assert linkedin.normalize("https://example.com/in/ravi") is None
    with pytest.raises(Exception, match="company page"):
        linkedin.require("https://www.linkedin.com/in/ravi", "company")


@pytest.fixture
def linkedin_web(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"results": [
            {"title": "Flow Well Castings | LinkedIn", "url": "https://in.linkedin.com/company/flow-well-castings",
             "content": "Foundry in Coimbatore. 51-200 employees."},
            {"title": "Flow Well Castings - duplicate", "url": "https://www.linkedin.com/company/flow-well-castings/about/",
             "content": "About"},
            {"title": "Ravi Kumar - Director - Flow Well | LinkedIn", "url": "https://in.linkedin.com/in/ravi-kumar-12",
             "content": "Director at Flow Well Castings"},
            {"title": "A post", "url": "https://www.linkedin.com/posts/flow-well_update-123", "content": "Post"},
        ]})

    monkeypatch.setattr(get_settings(), "tavily_api_key", SecretStr("tvly-test"))
    monkeypatch.setattr(tavily, "transport", httpx.MockTransport(handler))
    return seen


async def test_lookup_finds_public_pages_on_linkedin_only(owner, linkedin_web):
    company = (await owner.post("/api/companies", {"name": "Flow Well Castings", "city": "Coimbatore"})).json()
    found = (await owner.get(f"/api/linkedin/lookup/companies/{company['id']}")).json()
    assert linkedin_web[0]["include_domains"] == ["linkedin.com"]
    assert found["kind"] == "company" and found["query"] == "Flow Well Castings Coimbatore"
    assert [c["url"] for c in found["candidates"]] == ["https://www.linkedin.com/company/flow-well-castings"]
    assert found["candidates"][0]["title"] == "Flow Well Castings"

    contact = (await owner.post("/api/contacts", {"first_name": "Ravi", "last_name": "Kumar",
                                                  "company_id": company["id"], "job_title": "Director"})).json()
    people = (await owner.get(f"/api/linkedin/lookup/contacts/{contact['id']}")).json()
    assert people["kind"] == "person" and people["query"] == "Ravi Kumar Flow Well Castings Director"
    assert [c["url"] for c in people["candidates"]] == ["https://www.linkedin.com/in/ravi-kumar-12"]


async def test_drafts_are_sent_by_the_user_and_logged_as_linkedin_outreach(owner, use_pool):
    lead = (await owner.post("/api/leads", {"name": "Ravi Kumar", "company_name": "Flow Well Castings",
                                            "linkedin_url": "https://www.linkedin.com/in/ravi-kumar-12"})).json()
    too_long = "x" * 301
    provider = ScriptedProvider("groq", [
        tool_turn("search_leads", {}),
        tool_turn("draft_linkedin_message", {"to_ref": "l1", "kind": "connection_note", "text": too_long}),
        tool_turn("draft_linkedin_message", {"to_ref": "l1", "kind": "connection_note",
                                             "text": "Hi Ravi, I help foundries track orders and QC. Happy to connect."}),
        text_turn("Here's a connection note for you to send."),
    ])
    use_pool(entry(provider))
    events = await chat(owner, "draft a linkedin connection request to Ravi")
    assert "at most 300 characters" in provider.requests[2]["messages"][-1].content
    [card] = proposals(events)
    assert card["variant"] == "linkedin" and card["linkedin"]["limit"] == 300
    assert card["linkedin"]["profile_url"] == "https://www.linkedin.com/in/ravi-kumar-12"
    assert (await owner.get("/api/activities")).json()["total"] == 0  # nothing is logged until they confirm

    done = (await confirm(owner, card["id"], {"text": "Hi Ravi, edited note."})).json()
    assert done["status"] == "executed", done
    [act] = (await owner.get("/api/activities", params={"lead_id": lead["id"]})).json()["items"]
    assert act["type"] == "linkedin" and act["body"] == "Hi Ravi, edited note."
    assert act["subject"] == "LinkedIn connection request to Ravi Kumar"

    insights = (await owner.get("/api/dashboard", params={"tz": "Asia/Kolkata"})).json()["insights"]
    assert insights["weeks"][-1]["linkedin"] == 1
    assert all(c["id"] != lead["id"] for c in insights["contact_next"])  # contacted now


async def test_saving_a_page_checks_it_is_the_right_kind(owner, use_pool):
    await owner.post("/api/companies", {"name": "Flow Well Castings"})
    provider = ScriptedProvider("groq", [
        tool_turn("search_companies", {}),
        tool_turn("save_linkedin_url", {"ref": "c1", "url": "https://www.linkedin.com/in/someone"}),
        tool_turn("save_linkedin_url", {"ref": "c1", "url": "https://in.linkedin.com/company/flow-well-castings?x=1"}),
        text_turn("Proposed."),
    ])
    use_pool(entry(provider))
    events = await chat(owner, "save the linkedin page for Flow Well")
    assert "needs a company page" in provider.requests[2]["messages"][-1].content
    [card] = proposals(events)
    assert card["changes"] == [{"field": "LinkedIn", "old": None,
                                "new": "https://www.linkedin.com/company/flow-well-castings"}]
    assert (await confirm(owner, card["id"])).json()["status"] == "executed"
    saved = (await owner.get("/api/companies")).json()["items"][0]
    assert saved["linkedin_url"] == "https://www.linkedin.com/company/flow-well-castings"


async def test_linkedin_activities_and_converted_leads(owner):
    ok = await owner.post("/api/activities", {"type": "linkedin", "subject": "Connection request to Anand"})
    assert ok.status_code == 201 and ok.json()["status"] == "completed"
    lead = (await owner.post("/api/leads", {"name": "Anand R", "company_name": "JAK Industries",
                                            "linkedin_url": "https://www.linkedin.com/in/anand-r"})).json()
    result = (await owner.post(f"/api/leads/{lead['id']}/convert", {"create_deal": False})).json()
    contact = (await owner.get(f"/api/contacts/{result['contact_id']}")).json()
    assert contact["linkedin_url"] == "https://www.linkedin.com/in/anand-r"
