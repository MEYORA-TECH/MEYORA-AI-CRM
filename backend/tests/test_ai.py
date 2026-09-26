"""AI layer tests. `ScriptedProvider` is a test double; nothing here reaches a real model."""

import json
import uuid

import httpx
import pytest
from sqlalchemy import select, text

from app.ai import registry
from app.ai.providers.base import (
    ChatMessage,
    Completion,
    ProviderRateLimited,
    TextDelta,
    ToolCall,
    Usage,
)
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.ai.registry import ProviderEntry
from app.ai.tools.base import ToolContext, WorkingSet
from app.ai.tools.crm import BY_NAME
from app.auth.deps import RequestMeta, TenantContext
from app.auth.permissions import Role, permissions_for
from app.database.session import SessionLocal, set_tenant
from app.models import AIMessage, AIUsageLog, User
from tests.conftest import invite_and_join


class ScriptedProvider:
    """Replays a fixed list of turns: each turn is a list of events, or an exception to raise."""

    def __init__(self, id: str, turns: list):
        self.id = id
        self.turns = list(turns)
        self.requests: list[dict] = []

    async def stream_chat(self, *, model, messages, tools, max_tokens, temperature=0.2):
        self.requests.append({"messages": list(messages), "tools": [t.name for t in tools]})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        for event in turn:
            yield event


def text_turn(answer: str) -> list:
    return [TextDelta(answer), Completion(text=answer, tool_calls=[], usage=Usage(900, 40), finish_reason="stop")]


def tool_turn(name: str, args: dict) -> list:
    call = ToolCall(id=f"call_{uuid.uuid4().hex[:6]}", name=name, arguments=json.dumps(args))
    return [Completion(text="", tool_calls=[call], usage=Usage(800, 20), finish_reason="tool_calls")]


def entry(provider, privacy="trusted", priority=10) -> ProviderEntry:
    return ProviderEntry(id=provider.id, label=provider.id.title(), privacy=privacy, chat_model="m", fast_model="m",
                         context_window=131072, provider=provider, priority=priority)


@pytest.fixture
def use_pool(monkeypatch):
    def _set(*entries):
        monkeypatch.setattr(registry, "pool", lambda: list(entries))
    return _set


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def chat(account, message, **extra):
    resp = await account.client.post("/api/ai/chat", json={"message": message, "timezone": "UTC", **extra},
                                     headers=account.headers)
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


# --- Provider client -----------------------------------------------------------

def _sse_body(chunks: list[dict]) -> bytes:
    return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


async def test_openai_compatible_stream_parses_text_tools_and_usage():
    chunks = [
        {"choices": [{"delta": {"content": "Look"}}]},
        {"choices": [{"delta": {"content": "ing"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "search_deals", "arguments": "{\"sta"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ge\": \"Proposal\"}"}}]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "x_groq": {"usage": {"prompt_tokens": 321, "completion_tokens": 12}}},
    ]
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, content=_sse_body(chunks), headers={"content-type": "text/event-stream"})

    p = OpenAICompatibleProvider(id="t", base_url="https://x.test/v1", api_key="k", transport=httpx.MockTransport(handler))
    events = [e async for e in p.stream_chat(model="m", messages=[ChatMessage(role="user", content="hi")], tools=[], max_tokens=50)]

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Look", "ing"]
    done = events[-1]
    assert isinstance(done, Completion)
    assert done.tool_calls == [ToolCall(id="c1", name="search_deals", arguments='{"stage": "Proposal"}')]
    assert (done.usage.prompt_tokens, done.usage.completion_tokens) == (321, 12)
    assert seen["auth"] == "Bearer k" and seen["body"]["stream"] is True


async def test_rate_limit_becomes_provider_rate_limited():
    transport = httpx.MockTransport(lambda r: httpx.Response(429, headers={"retry-after": "7"}, json={"error": "slow down"}))
    p = OpenAICompatibleProvider(id="t", base_url="https://x.test/v1", api_key="k", transport=transport)
    with pytest.raises(ProviderRateLimited) as info:
        async for _ in p.stream_chat(model="m", messages=[], tools=[], max_tokens=10):
            pass
    assert info.value.retry_after == 7.0


# --- Privacy guardrail -------------------------------------------------------------

def test_crm_data_never_routes_to_public_only_providers():
    trusted = entry(ScriptedProvider("groq", []), priority=20)
    public = entry(ScriptedProvider("gemini-free", []), privacy="public_only", priority=1)
    assert [e.id for e in registry.route("crm", entries=[public, trusted])] == ["groq"]
    assert [e.id for e in registry.route("public", entries=[public, trusted])] == ["gemini-free", "groq"]
    with pytest.raises(registry.NoProviderAvailable):
        registry.route("crm", entries=[public])


# --- Tools respect tenancy -----------------------------------------------------------

async def _tool_ctx(session, account) -> ToolContext:
    await set_tenant(session, uuid.UUID(account.org_id))
    user = await session.get(User, uuid.UUID(account.user_id))
    tenant = TenantContext(session=session, user=user, organization_id=uuid.UUID(account.org_id), role=Role.OWNER,
                           meta=RequestMeta(None, None, None), permissions=permissions_for(Role.OWNER))
    return ToolContext(tenant=tenant, working_set=WorkingSet(), timezone="UTC")


async def test_tools_only_see_their_own_organization(owner, other_org):
    deal = (await owner.post("/api/deals", {"name": "Fleet tracking", "amount": 250000})).json()

    async with SessionLocal() as session:
        mine = await _tool_ctx(session, owner)
        found = await BY_NAME["search_deals"].run(mine, "{}")
        assert "1 deal(s) found" in found.summary and "d1: Fleet tracking" in found.summary
        assert mine.working_set.refs["d1"]["id"] == deal["id"]
        detail = await BY_NAME["get_deal"].run(mine, '{"ref": "d1"}')
        assert "₹2.5L" in detail.summary

    async with SessionLocal() as session:
        theirs = await _tool_ctx(session, other_org)
        assert "0 deal(s) found" in (await BY_NAME["search_deals"].run(theirs, "{}")).summary
        leaked = await BY_NAME["get_deal"].run(theirs, json.dumps({"ref": deal["id"]}))
        assert not leaked.ok and "not found" in leaked.summary.lower()


async def test_invalid_tool_arguments_are_rejected_not_run(owner):
    async with SessionLocal() as session:
        ctx = await _tool_ctx(session, owner)
        result = await BY_NAME["search_leads"].run(ctx, '{"min_score": 500}')
        assert not result.ok and "Invalid arguments" in result.summary


# --- Chat turns ---------------------------------------------------------------------

async def test_chat_turn_uses_tools_streams_and_persists(owner, use_pool):
    await owner.post("/api/deals", {"name": "ABC fleet deal", "amount": 300000})
    provider = ScriptedProvider("groq", [tool_turn("search_deals", {"statuses": ["open"]}), text_turn("You have one open deal worth ₹3L.")])
    use_pool(entry(provider))

    events = await chat(owner, "Which deals are open?")
    kinds = [k for k, _ in events]
    assert kinds[0] == "conversation" and kinds[-1] == "done"
    assert "tool_start" in kinds and "tool_result" in kinds
    tool_result = next(d for k, d in events if k == "tool_result")
    assert tool_result["ui"]["rows"][0]["title"] == "ABC fleet deal"
    assert "".join(d["text"] for k, d in events if k == "token") == "You have one open deal worth ₹3L."
    done = events[-1][1]
    assert done["tokens"] == 800 + 20 + 900 + 40

    # The second model call saw the tool result wrapped as data.
    second = provider.requests[1]["messages"]
    assert any(m.role == "tool" and "<crm_data" in (m.content or "") for m in second)
    assert "search_deals" in provider.requests[0]["tools"]

    conv_id = events[0][1]["id"]
    messages = (await owner.get(f"/api/ai/conversations/{conv_id}/messages")).json()
    assert [m["role"] for m in messages] == ["user", "tool", "assistant"]
    conv = (await owner.get("/api/ai/conversations")).json()["items"][0]
    assert conv["provider"] == "groq" and conv["title"] == "Which deals are open?"

    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        logs = list(await session.scalars(select(AIUsageLog)))
        assert len(logs) == 2 and logs[0].tool_calls == ["search_deals"]


async def test_follow_up_resolves_refs_from_the_working_set(owner, use_pool):
    await owner.post("/api/deals", {"name": "ABC fleet deal", "amount": 300000})
    provider = ScriptedProvider("groq", [
        tool_turn("search_deals", {}), text_turn("One deal."),
        tool_turn("get_deal", {"ref": "d1"}), text_turn("It is in Lead."),
    ])
    use_pool(entry(provider))
    first = await chat(owner, "List deals")
    conv_id = first[0][1]["id"]
    second = await chat(owner, "Tell me more about it", conversation_id=conv_id)
    detail = next(d for k, d in second if k == "tool_result")
    assert detail["ok"] and detail["ui"]["rows"][0]["title"] == "ABC fleet deal"
    # History carries the earlier exchange as plain text only.
    third_request = provider.requests[2]["messages"]
    assert [m.role for m in third_request if m.role != "system"] == ["user", "assistant", "user"]


async def test_fails_over_before_any_text_is_shown(owner, use_pool):
    busy = ScriptedProvider("groq", [ProviderRateLimited(12)])
    backup = ScriptedProvider("openrouter", [text_turn("Hello from the backup.")])
    use_pool(entry(busy, priority=10), entry(backup, priority=20))
    events = await chat(owner, "hello")
    assert events[-1][0] == "done" and events[-1][1]["provider"] == "Openrouter"
    assert not any(k == "error" for k, _ in events)


async def test_rate_limit_with_no_backup_reports_clearly(owner, use_pool):
    use_pool(entry(ScriptedProvider("groq", [ProviderRateLimited(30)])))
    events = await chat(owner, "hello")
    error = next(d for k, d in events if k == "error")
    assert "free-tier limit" in error["message"] and "31s" in error["message"]


async def test_not_configured_and_quota(owner, use_pool, monkeypatch):
    use_pool()
    events = await chat(owner, "hello")
    assert events[0] == ("error", {"message": events[0][1]["message"], "code": "not_configured"})

    use_pool(entry(ScriptedProvider("groq", [text_turn("hi")])))
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        session.add(AIUsageLog(organization_id=uuid.UUID(owner.org_id), user_id=uuid.UUID(owner.user_id),
                               provider="groq", model="m", prompt_tokens=10**6, completion_tokens=0))
        await session.commit()
    events = await chat(owner, "hello")
    assert events[0][1]["code"] == "quota"
    status = (await owner.get("/api/ai/status")).json()
    assert status["used_today"] >= 10**6 and status["configured"] is True


async def test_conversations_are_private_to_their_author(owner, use_pool):
    use_pool(entry(ScriptedProvider("groq", [text_turn("hi")])))
    conv_id = (await chat(owner, "private question"))[0][1]["id"]
    colleague = await invite_and_join(owner, "admin")
    assert (await colleague.get(f"/api/ai/conversations/{conv_id}/messages")).status_code == 404
    assert (await colleague.get("/api/ai/conversations")).json()["total"] == 0
    resp = await colleague.client.post("/api/ai/chat", json={"message": "x", "conversation_id": conv_id}, headers=colleague.headers)
    assert resp.status_code == 404


async def test_conversation_rename_search_delete(owner, use_pool):
    use_pool(entry(ScriptedProvider("groq", [text_turn("Fleet tracking came up twice.")])))
    conv_id = (await chat(owner, "what about fleet tracking?"))[0][1]["id"]
    assert (await owner.patch(f"/api/ai/conversations/{conv_id}", {"title": "Fleet notes"})).json()["title"] == "Fleet notes"
    assert (await owner.get("/api/ai/conversations", params={"q": "came up twice"})).json()["total"] == 1
    assert (await owner.delete(f"/api/ai/conversations/{conv_id}")).status_code == 204
    assert (await owner.get("/api/ai/conversations")).json()["total"] == 0


async def test_ai_tables_are_row_level_secured(owner, use_pool):
    use_pool(entry(ScriptedProvider("groq", [text_turn("hi")])))
    await chat(owner, "hello")
    async with SessionLocal() as session:
        assert await session.scalar(text("SELECT count(*) FROM ai_messages")) == 0  # no tenant set
        await set_tenant(session, uuid.UUID(owner.org_id))
        assert await session.scalar(select(text("count(*)")).select_from(AIMessage)) == 2
