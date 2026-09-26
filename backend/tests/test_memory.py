"""Phase 3: jobs, knowledge index, memory, summaries. Embeddings use the test HashEmbedder."""

import json
import uuid

from sqlalchemy import select, text

from app.ai import memory
from app.ai.providers.base import Completion, TextDelta, Usage
from app.database.session import SessionLocal, set_tenant
from app.jobs.queue import enqueue, run_pending
from app.models import AIConversationSummary, AIMemory, Job, KnowledgeChunk
from tests.conftest import invite_and_join
from tests.test_ai import ScriptedProvider, chat, entry, text_turn, tool_turn


def json_turn(payload: dict) -> list:
    body = json.dumps(payload)
    return [TextDelta(body), Completion(text=body, tool_calls=[], usage=Usage(300, 60), finish_reason="stop")]


async def _session(account):
    session = SessionLocal()
    await set_tenant(session, uuid.UUID(account.org_id))
    return session


async def _count(sql: str, account=None) -> int:
    async with SessionLocal() as session:
        if account:
            await set_tenant(session, uuid.UUID(account.org_id))
        return await session.scalar(text(sql))


# --- Job queue -------------------------------------------------------------------

async def test_jobs_dedupe_and_defer_without_provider(owner, use_pool):
    use_pool()  # no AI provider: LLM jobs must wait, not fail
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()
    note_body = "ABC Manufacturing prefers private deployment and wants on-premise servers."
    await owner.post("/api/notes", {"body": note_body, "company_id": company["id"]})

    async with SessionLocal() as session:
        jobs = {j.kind: j for j in await session.scalars(select(Job))}
    assert {"index_record", "extract_memories"} <= set(jobs)

    await run_pending()
    async with SessionLocal() as session:
        extract = await session.scalar(select(Job).where(Job.kind == "extract_memories"))
        assert extract.status == "queued" and extract.attempts == 0 and "no AI provider" in extract.error
        dedupe = await session.scalar(select(Job).where(Job.kind == "extract_memories"))
        await enqueue(session, "extract_memories", dedupe.organization_id, dedupe.payload, dedupe_key=dedupe.dedupe_key)
        await session.commit()
        assert len(list(await session.scalars(select(Job).where(Job.kind == "extract_memories")))) == 1


# --- Knowledge index ----------------------------------------------------------------

async def test_notes_are_indexed_updated_and_removed(owner):
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()
    note = (await owner.post("/api/notes", {"body": "Ravi asked about fleet tracking for forty trucks.", "company_id": company["id"]})).json()
    await run_pending()
    assert await _count("SELECT count(*) FROM knowledge_chunks", owner) == 1

    await owner.patch(f"/api/notes/{note['id']}", {"body": "Ravi now wants fleet tracking for sixty trucks."})
    await run_pending()
    async with await _session(owner) as session:
        chunk = await session.scalar(select(KnowledgeChunk))
        assert "sixty" in chunk.content and chunk.company_id == uuid.UUID(company["id"])

    await owner.delete(f"/api/notes/{note['id']}")
    await run_pending()
    assert await _count("SELECT count(*) FROM knowledge_chunks", owner) == 0


async def test_search_knowledge_tool_via_chat(owner, use_pool):
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()
    await owner.post("/api/notes", {"body": "Budget approved for fleet tracking rollout next quarter.", "company_id": company["id"]})
    await run_pending()
    provider = ScriptedProvider("groq", [tool_turn("search_knowledge", {"query": "fleet tracking budget"}), text_turn("Budget is approved.")])
    use_pool(entry(provider))
    events = await chat(owner, "What was said about the fleet tracking budget?")
    result = next(d for k, d in events if k == "tool_result")
    assert result["ok"] and result["ui"]["rows"][0]["href"] == f"/companies/{company['id']}"
    assert "Budget approved" in provider.requests[1]["messages"][-1].content


# --- Memories -------------------------------------------------------------------------

async def test_save_dedupes_and_supersede_hides_old(owner):
    async with await _session(owner) as session:
        org, user = uuid.UUID(owner.org_id), uuid.UUID(owner.user_id)
        first = await memory.save_memory(session, org, content="ABC budget is about 3 lakh rupees.", user_id=user)
        again = await memory.save_memory(session, org, content="ABC budget is about 3 lakh rupees.", user_id=user, importance=5)
        assert first.action == "created" and again.action == "merged" and again.memory.importance == 5
        newer = await memory.save_memory(session, org, content="ABC raised its budget to 5 lakh rupees.", user_id=user)
        assert await memory.supersede(session, [first.memory.id], newer.memory) == 1
        await session.commit()
        recalled = await memory.recall(session, org, user, "ABC budget lakh rupees", touch=False)
        assert [r.memory.content for r in recalled] == ["ABC raised its budget to 5 lakh rupees."]


async def test_recall_respects_personal_scope_and_tenants(owner, other_org):
    colleague = await invite_and_join(owner, "member")
    async with await _session(owner) as session:
        org = uuid.UUID(owner.org_id)
        await memory.save_memory(session, org, content="I prefer short weekly deployment summaries.", user_id=uuid.UUID(owner.user_id), user_scope=True)
        await memory.save_memory(session, org, content="ABC prefers private deployment on premise.", user_id=uuid.UUID(owner.user_id))
        await session.commit()
        # The test embedder matches words, so the query shares words with both memories.
        query = "prefer private deployment premise, short weekly deployment summaries"
        mine = await memory.recall(session, org, uuid.UUID(owner.user_id), query, touch=False)
        theirs = await memory.recall(session, org, uuid.UUID(colleague.user_id), query, touch=False)
    assert len(mine) == 2
    assert [r.memory.scope for r in theirs] == ["organization"]

    assert (await colleague.get("/api/memories")).json()["total"] == 1
    assert (await other_org.get("/api/memories")).json()["total"] == 0
    assert (await owner.get("/api/memories", params={"scope": "user"})).json()["total"] == 1


async def test_note_extraction_saves_links_and_supersedes(owner, use_pool):
    company = (await owner.post("/api/companies", {"name": "ABC Manufacturing"})).json()
    async with await _session(owner) as session:
        old = await memory.save_memory(session, uuid.UUID(owner.org_id), content="ABC Manufacturing wants a cloud deployment.",
                                       user_id=uuid.UUID(owner.user_id), links={"company_id": uuid.UUID(company["id"])})
        await session.commit()

    provider = ScriptedProvider("groq", [json_turn({"memories": [
        {"content": "ABC Manufacturing now wants a private on-premise deployment.", "type": "requirement",
         "about": "organization", "importance": 4, "confidence": 0.9, "replaces": [1]},
        {"content": "Ravi is the decision maker at ABC Manufacturing.", "type": "relationship", "importance": 4, "confidence": 0.4},
    ]})])
    use_pool(entry(provider))
    await owner.post("/api/notes", {"company_id": company["id"],
                                    "body": "Call with Ravi: they changed their mind, now private on-premise deployment. Ravi decides."})
    await run_pending()

    async with await _session(owner) as session:
        rows = {m.content: m for m in await session.scalars(select(AIMemory))}
    assert rows[old.memory.content].status == "superseded"
    onprem = rows["ABC Manufacturing now wants a private on-premise deployment."]
    # Labelled "organization" by the model, but it names the note's company, so it stays linked to it.
    assert onprem.scope == "company" and onprem.company_id == uuid.UUID(company["id"])
    assert onprem.source_type == "note" and onprem.created_by == "ai"
    ravi = rows["Ravi is the decision maker at ABC Manufacturing."]
    assert ravi.status == "pending_review" and ravi.company_id == uuid.UUID(company["id"])  # default link from the note

    approved = await owner.patch(f"/api/memories/{ravi.id}", {"status": "active"})
    assert approved.json()["status"] == "active"
    # The extractor only ever saw existing memories as data, inside the user message.
    assert "1. ABC Manufacturing wants a cloud deployment." in provider.requests[0]["messages"][1].content


async def test_chat_injects_memories_and_remember_tool(owner, use_pool):
    await owner.post("/api/memories", {"content": "Fleet deals need a site survey before a proposal."})
    provider = ScriptedProvider("groq", [
        text_turn("Plan a site survey first."),
        tool_turn("remember", {"content": "Partha prefers answers as bullet points.", "about_ref": "me", "type": "preference"}),
        text_turn("Noted."),
    ])
    use_pool(entry(provider))

    events = await chat(owner, "What do we need before sending a fleet proposal?")
    used = next(d for k, d in events if k == "memories")
    assert used["items"][0]["content"] == "Fleet deals need a site survey before a proposal."
    assert any("<memories>" in (m.content or "") for m in provider.requests[0]["messages"])

    events = await chat(owner, "Please remember that I prefer answers as bullet points")
    saved = next(d for k, d in events if k == "tool_result")
    assert saved["ui"]["kind"] == "memory" and saved["ui"]["scope"] == "user"
    personal = (await owner.get("/api/memories", params={"scope": "user"})).json()
    assert personal["items"][0]["content"] == "Partha prefers answers as bullet points."


async def test_long_conversations_get_summarised(owner, use_pool):
    provider = ScriptedProvider("groq", [text_turn(f"answer {i}") for i in range(8)])
    use_pool(entry(provider))
    conv_id = (await chat(owner, "question 0"))[0][1]["id"]
    for i in range(1, 7):
        await chat(owner, f"question {i}", conversation_id=conv_id)  # 14 messages in total

    summariser = ScriptedProvider("groq", [text_turn("User asked questions 0-3 about the pipeline.")])
    use_pool(entry(summariser))
    await run_pending()
    async with await _session(owner) as session:
        row = await session.scalar(select(AIConversationSummary))
        assert row.summary.startswith("User asked") and row.message_count == 8

    follow = ScriptedProvider("groq", [text_turn("ok")])
    use_pool(entry(follow))
    await chat(owner, "question 7", conversation_id=conv_id)
    sent = follow.requests[0]["messages"]
    assert any("Earlier in this conversation" in (m.content or "") for m in sent)
    replayed = [m.content for m in sent if m.role == "user"]
    assert "question 0" not in replayed and replayed[-1] == "question 7"


async def test_memory_tables_are_row_level_secured(owner):
    await owner.post("/api/memories", {"content": "Something durable about the business."})
    assert await _count("SELECT count(*) FROM ai_memories") == 0
    assert await _count("SELECT count(*) FROM ai_memories", owner) == 1


async def test_delete_memory_forgets_it(owner):
    mem = (await owner.post("/api/memories", {"content": "Temporary fact to forget."})).json()
    member = await invite_and_join(owner, "member")
    assert (await member.delete(f"/api/memories/{mem['id']}")).status_code == 403
    assert (await owner.delete(f"/api/memories/{mem['id']}")).status_code == 204
    async with await _session(owner) as session:
        assert await session.get(AIMemory, uuid.UUID(mem["id"])) is None
