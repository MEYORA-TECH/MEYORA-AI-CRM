"""Concurrent chats: every answer reaches the person who asked, and one conversation runs one turn at a time."""

import asyncio
import uuid

from sqlalchemy import text

from app.ai.providers.base import Completion, TextDelta, Usage
from app.database.session import SessionLocal, set_tenant
from tests.test_ai import chat, entry


class EchoProvider:
    """Answers each request with its own question, slowly, so concurrent turns interleave."""

    id = "groq"

    def __init__(self, delay: float = 0.05):
        self.delay = delay

    async def stream_chat(self, *, model, messages, tools, max_tokens, temperature=0.2, json_mode=False, extra=None,
                          tool_choice="auto"):
        question = next(m.content for m in reversed(messages) if m.role == "user")
        answer = f"Answer to: {question}"
        for word in answer.split(" "):
            await asyncio.sleep(self.delay)
            yield TextDelta(word + " ")
        yield Completion(text=answer, tool_calls=[], usage=Usage(10, 5), finish_reason="stop")


def streamed_text(events):
    return "".join(d["text"] for k, d in events if k == "token").strip()


async def test_concurrent_chats_never_cross(owner, other_org, use_pool):
    use_pool(entry(EchoProvider()))
    askers = [(owner, f"owner question {i}") for i in range(3)] + [(other_org, f"globex question {i}") for i in range(3)]
    results = await asyncio.gather(*(chat(account, q) for account, q in askers))

    for (account, question), events in zip(askers, results, strict=True):
        assert streamed_text(events) == f"Answer to: {question}"
        conv_id = events[0][1]["id"]
        saved = (await account.get(f"/api/ai/conversations/{conv_id}/messages")).json()
        assert [(m["role"], m["content"]) for m in saved] == [
            ("user", question), ("assistant", f"Answer to: {question}"),
        ]
    # Each workspace sees only its own three conversations.
    assert (await owner.get("/api/ai/conversations")).json()["total"] == 3
    assert (await other_org.get("/api/ai/conversations")).json()["total"] == 3


async def test_one_turn_at_a_time_per_conversation(owner, use_pool):
    use_pool(entry(EchoProvider(delay=0.01)))
    conv_id = (await chat(owner, "first"))[0][1]["id"]

    use_pool(entry(EchoProvider(delay=0.1)))
    slow = asyncio.create_task(chat(owner, "second, slow", conversation_id=conv_id))
    await asyncio.sleep(0.25)  # the slow turn has claimed the conversation
    clash = await chat(owner, "third, while busy", conversation_id=conv_id)
    assert clash[0][0] == "error" and clash[0][1]["code"] == "busy"
    assert streamed_text(await slow) == "Answer to: second, slow"

    # Released afterwards: the next message goes through.
    follow = await chat(owner, "fourth", conversation_id=conv_id)
    assert streamed_text(follow) == "Answer to: fourth"
    saved = (await owner.get(f"/api/ai/conversations/{conv_id}/messages")).json()
    assert [m["content"] for m in saved if m["role"] == "user"] == ["first", "second, slow", "fourth"]


async def test_a_stale_claim_expires(owner, use_pool):
    use_pool(entry(EchoProvider(delay=0)))
    conv_id = (await chat(owner, "hello"))[0][1]["id"]
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        # A turn that died long ago without releasing its claim.
        await session.execute(text("UPDATE ai_conversations SET busy_until = now() - interval '1 minute'"))
        await session.commit()
    events = await chat(owner, "still there?", conversation_id=conv_id)
    assert streamed_text(events) == "Answer to: still there?"
