"""The assistant follows the conversation, knows the business, and ranks prospects by fit."""

from app.ai.prompts import select_tools, system_prompt
from tests.test_ai import ScriptedProvider, chat, entry, text_turn, tool_turn
from tests.test_web import web  # noqa: F401  (fixture)


def names(tools):
    return {t.name for t in tools}


def test_follow_ups_keep_the_tools_the_conversation_was_using():
    follow_up = "ok then search for a company where around only 10-100 employees work"
    assert "web_search" not in names(select_tools(follow_up, None))
    assert "web_search" in names(select_tools(follow_up, None, {"web_search"}))
    # Memory stays opt-in even if it was used recently.
    assert "remember" not in names(select_tools("and the next one?", None, {"remember"}))


def test_the_business_profile_and_honesty_rules_reach_the_prompt():
    prompt = system_prompt(org="Meyora", user="Olivia", role="owner", tz="Asia/Kolkata", currency="INR",
                           about="We build ERP systems for Tamil Nadu manufacturers.")
    assert "About Meyora" in prompt and "Tamil Nadu manufacturers" in prompt
    assert "Follow-ups continue the current task" in prompt
    assert "Never claim a company is" in prompt
    assert "About" not in system_prompt(org="Acme", user="O", role="owner", tz="UTC", currency="INR").split("How you work")[0]


async def test_company_search_ranks_by_fit_and_leaves_out_outreach_partners(owner, use_pool):
    for name, fit, tags, size in [
        ("Low Fit Mills", 60, ["Manufacturing SME"], "51–200"),
        ("Top Fit Castings", 94, ["Chennai Manufacturing SME", "High priority"], "51–200"),
        ("Ambattur Industrial Manufacturers Association", 99, ["Association", "Outreach partner"], None),
        ("Mid Fit Engineering", 82, ["High priority"], "201–500"),
    ]:
        company = (await owner.post("/api/companies", {
            "name": name, "tags": tags, "custom_fields": {"Fit score": fit, **({"Company size": size} if size else {})},
        })).json()
        if name == "Top Fit Castings":
            await owner.post("/api/contacts", {"first_name": "Anand", "company_id": company["id"], "tags": ["Decision maker"]})

    provider = ScriptedProvider("groq", [
        tool_turn("search_companies", {"limit": 3}),
        tool_turn("search_companies", {"size": "51-200", "min_fit": 80}),
        tool_turn("search_companies", {"include_partners": True, "limit": 1}),
        text_turn("Here are the best fits."),
    ])
    use_pool(entry(provider))
    await chat(owner, "fetch 3 companies we should contact")

    first = provider.requests[1]["messages"][-1].content
    lines = [line for line in first.splitlines() if line.startswith(("c1", "c2", "c3"))]
    assert "Top Fit Castings" in lines[0] and "fit 94" in lines[0] and "1 decision maker" in lines[0]
    assert "Mid Fit Engineering" in lines[1] and "Low Fit Mills" in lines[2]
    assert "Association" not in first and "3 companies found" in first

    sized = provider.requests[2]["messages"][-1].content
    assert "1 company found" in sized and "Top Fit Castings" in sized  # hyphen matches the stored en dash
    partners = provider.requests[3]["messages"][-1].content
    assert "Ambattur Industrial Manufacturers Association" in partners


async def test_a_web_follow_up_stays_on_the_web_and_can_aim_at_india(owner, use_pool, web):  # noqa: F811
    provider = ScriptedProvider("groq", [
        tool_turn("web_search", {"query": "Chennai manufacturers needing ERP", "country": "india"}),
        text_turn("**From the web** Nothing specific [w1]."),
        tool_turn("web_search", {"query": "Chennai manufacturers 10-100 employees", "country": "India"}),
        text_turn("**From the web** Found a few [w3]."),
    ])
    use_pool(entry(provider))
    events = await chat(owner, "web search for companies that might need an ERP")
    conv_id = events[0][1]["id"]
    await chat(owner, "ok then search for a company where around only 10-100 employees work", conversation_id=conv_id)

    assert "web_search" in provider.requests[2]["tools"]  # offered on the follow-up, which names no topic
    assert [r["body"].get("country") for r in web.requests] == ["india", "india"]
