"""Phase 6: AI actions are proposals until a person confirms them."""

import base64
import json
import uuid

import httpx
from sqlalchemy import select, text, update

from app.ai.providers.base import Completion, ToolCall, Usage
from app.database.session import SessionLocal, set_tenant
from app.integrations.gmail.send import SEND_SCOPE
from app.integrations.google import oauth
from app.models import AIAction, AuditLog, Task
from tests.conftest import XHR, invite_and_join
from tests.test_ai import ScriptedProvider, chat, entry, text_turn, tool_turn
from tests.test_gmail import _crm, connect_gmail


def proposals(events):
    return [d["ui"] for k, d in events if k == "tool_result" and d.get("ui", {}) and d["ui"].get("kind") == "action"]


async def _count(owner, sql):
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        return await session.scalar(text(sql))


async def confirm(account, action_id, edits=None):
    return await account.client.post(f"/api/ai/actions/{action_id}/confirm", json={"edits": edits} if edits else {},
                                     headers={**account.headers, **XHR})


async def test_proposal_writes_nothing_until_confirmed(owner, use_pool):
    await owner.post("/api/deals", {"name": "ABC fleet deal", "amount": 300000})
    provider = ScriptedProvider("groq", [
        tool_turn("search_deals", {}),
        tool_turn("create_task", {"title": "Follow up on ABC fleet deal", "due": "2026-10-06", "priority": "high", "about_ref": "d1"}),
        text_turn("I've proposed a follow-up task; confirm it to create it."),
    ])
    use_pool(entry(provider))
    events = await chat(owner, "Create a follow-up task for the ABC deal next Tuesday")
    [card] = proposals(events)
    assert card["status"] == "proposed" and card["ref"] == "a1" and card["title"] == "Create task"
    assert {c["field"] for c in card["changes"]} >= {"Title", "Due", "Priority", "For"}
    assert card["target"]["label"] == "ABC fleet deal"
    assert "NOT done yet" in provider.requests[2]["messages"][-1].content
    assert await _count(owner, "SELECT count(*) FROM tasks") == 0

    resp = await confirm(owner, card["id"])
    body = resp.json()
    assert resp.status_code == 200 and body["status"] == "executed", body
    assert await _count(owner, "SELECT count(*) FROM tasks") == 1
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))
        task = await session.scalar(select(Task))
        assert task.deal_id and task.priority == "high" and task.assignee_id == uuid.UUID(owner.user_id)
        audit = await session.scalar(select(AuditLog).where(AuditLog.action == "task.create"))
        assert audit.actor_type == "ai" and audit.actor_user_id == uuid.UUID(owner.user_id)
    assert body["result"]["href"].startswith("/tasks/")

    again = await confirm(owner, card["id"])
    assert again.status_code == 409

    # The conversation remembers what happened; the next turn sees it.
    conv_id = events[0][1]["id"]
    follow = ScriptedProvider("groq", [text_turn("It's done.")])
    use_pool(entry(follow))
    await chat(owner, "did that work?", conversation_id=conv_id)
    assert any(m.role == "system" and "a1" in (m.content or "") and "confirmed and done" in m.content
               for m in follow.requests[0]["messages"])


async def test_reject_and_messages_show_live_status(owner, use_pool):
    await owner.post("/api/leads", {"name": "Meera", "company_name": "Beta Logistics"})
    use_pool(entry(ScriptedProvider("groq", [
        tool_turn("search_leads", {}), tool_turn("update_lead", {"lead_ref": "l1", "status": "qualified", "score": 80}),
        text_turn("Proposed."),
    ])))
    events = await chat(owner, "Mark Meera as qualified with score 80")
    [card] = proposals(events)
    assert card["changes"] == [{"field": "Status", "old": "new", "new": "qualified"}, {"field": "Score", "old": 0, "new": 80}]
    rejected = await owner.client.post(f"/api/ai/actions/{card['id']}/reject", headers={**owner.headers, **XHR})
    assert rejected.json()["status"] == "rejected"
    lead = (await owner.get("/api/leads")).json()["items"][0]
    assert lead["status"] == "new" and lead["score"] == 0
    msgs = (await owner.get(f"/api/ai/conversations/{events[0][1]['id']}/messages")).json()
    shown = next(m["ui"] for m in msgs if m["ui"] and m["ui"].get("kind") == "action")
    assert shown["status"] == "rejected"


async def test_stale_target_is_refused_and_expiry(owner, use_pool):
    deal = (await owner.post("/api/deals", {"name": "Big deal", "amount": 100000})).json()
    use_pool(entry(ScriptedProvider("groq", [
        tool_turn("search_deals", {}), tool_turn("update_deal", {"deal_ref": "d1", "stage": "Proposal", "amount": 150000}),
        text_turn("Proposed."),
        tool_turn("update_deal", {"deal_ref": "d1", "stage": "Negotiation"}), text_turn("Proposed again."),
    ])))
    events = await chat(owner, "Move Big deal to Proposal at 1.5 lakh")
    [card] = proposals(events)
    assert card["changes"][0] == {"field": "Stage", "old": "Lead", "new": "Proposal"}

    await owner.patch(f"/api/deals/{deal['id']}", {"description": "edited by a person meanwhile"})
    stale = (await confirm(owner, card["id"])).json()
    assert stale["status"] == "failed" and "changed after" in stale["error"]
    assert (await owner.get(f"/api/deals/{deal['id']}")).json()["amount"] == 100000

    events = await chat(owner, "then move it to Negotiation", conversation_id=events[0][1]["id"])
    [card2] = proposals(events)
    assert card2["ref"] == "a2"
    async with SessionLocal() as session:
        await set_tenant(session, uuid.UUID(owner.org_id))  # RLS: updates need a tenant too
        await session.execute(update(AIAction).where(AIAction.id == uuid.UUID(card2["id"])).values(expires_at=text("now() - interval '1 minute'")))
        await session.commit()
    expired = (await confirm(owner, card2["id"])).json()
    assert expired["status"] == "expired"


async def test_confirm_all_runs_each_independently(owner, use_pool):
    for name in ("Deal A", "Deal B"):
        await owner.post("/api/deals", {"name": name})
    two_calls = [Completion(text="", usage=Usage(10, 10), finish_reason="tool_calls", tool_calls=[
        ToolCall("c1", "create_task", '{"title": "Call about Deal A", "about_ref": "d1"}'),
        ToolCall("c2", "create_task", '{"title": "Call about Deal B", "about_ref": "d2"}'),
    ])]
    use_pool(entry(ScriptedProvider("groq", [tool_turn("search_deals", {}), two_calls, text_turn("Proposed two tasks.")])))
    events = await chat(owner, "Create follow-up tasks for all my open deals")
    cards = proposals(events)
    assert [c["ref"] for c in cards] == ["a1", "a2"]
    resp = await owner.client.post("/api/ai/actions/confirm-all", json={"ids": [c["id"] for c in cards]},
                                   headers={**owner.headers, **XHR})
    assert [a["status"] for a in resp.json()] == ["executed", "executed"]
    assert await _count(owner, "SELECT count(*) FROM tasks") == 2


async def test_only_the_requester_can_confirm_and_permissions_apply(owner, use_pool):
    await owner.post("/api/leads", {"name": "Someone"})
    use_pool(entry(ScriptedProvider("groq", [tool_turn("search_leads", {}), tool_turn("add_note", {"about_ref": "l1", "body": "Called, interested."}), text_turn("ok")])))
    [card] = proposals(await chat(owner, "Add a note to that lead: called, interested"))
    colleague = await invite_and_join(owner, "admin")
    assert (await confirm(colleague, card["id"])).status_code == 403
    assert (await confirm(owner, card["id"])).json()["status"] == "executed"


async def test_invalid_proposals_are_explained_to_the_model(owner, use_pool):
    await owner.post("/api/deals", {"name": "Deal X"})
    provider = ScriptedProvider("groq", [
        tool_turn("search_deals", {}), tool_turn("update_deal", {"deal_ref": "d1", "stage": "Signed"}), text_turn("That stage doesn't exist."),
    ])
    use_pool(entry(provider))
    events = await chat(owner, "move Deal X to Signed")
    result = [d for k, d in events if k == "tool_result"][1]
    assert not result["ok"]
    assert "No stage called 'Signed'" in provider.requests[2]["messages"][-1].content
    assert await _count(owner, "SELECT count(*) FROM ai_actions") == 0


async def test_draft_email_is_editable_and_sent_through_gmail(owner, use_pool, google, monkeypatch):
    await _crm(owner)
    google.scope += " " + SEND_SCOPE
    await connect_gmail(owner, google)

    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages/send"):
            sent["mime"] = base64.urlsafe_b64decode(json.loads(request.content)["raw"]).decode()
            google.add_message("sent-1", sender="olivia@acme.test", to="ravi@abc.in", subject="Next steps",
                               body="Hi Ravi, edited text.")
            return httpx.Response(200, json={"id": "sent-1", "threadId": "t-sent-1"})
        return google.handler(request)

    monkeypatch.setattr(oauth, "transport", httpx.MockTransport(handler))
    use_pool(entry(ScriptedProvider("groq", [
        tool_turn("search_contacts", {"query": "Ravi"}),
        tool_turn("draft_email", {"to_ref": "p1", "subject": "Next steps", "body": "Hi Ravi, here are the next steps. Olivia"}),
        text_turn("Here's a draft for you to review."),
    ])))
    [card] = proposals(await chat(owner, "Draft an email to Ravi about next steps"))
    assert card["variant"] == "email" and card["email"]["can_send"] is True and card["email"]["to"] == ["ravi@abc.in"]
    assert await _count(owner, "SELECT count(*) FROM email_messages WHERE direction = 'outbound'") == 0

    done = (await confirm(owner, card["id"], {"body": "Hi Ravi, edited text."})).json()
    assert done["status"] == "executed", done
    assert "Hi Ravi, edited text." in sent["mime"] and "To: ravi@abc.in" in sent["mime"]
    assert done["result"]["href"].startswith("/emails/")
    assert await _count(owner, "SELECT count(*) FROM email_messages WHERE direction = 'outbound'") == 1


async def test_email_without_mailbox_cannot_be_sent(owner, use_pool):
    await owner.post("/api/contacts", {"first_name": "Ravi", "email": "ravi@abc.in"})
    use_pool(entry(ScriptedProvider("groq", [
        tool_turn("search_contacts", {}), tool_turn("draft_email", {"to_ref": "p1", "subject": "Hi", "body": "Hello Ravi, checking in."}),
        text_turn("Draft ready."),
    ])))
    [card] = proposals(await chat(owner, "Draft an email to Ravi"))
    assert card["email"]["can_send"] is False
    failed = (await confirm(owner, card["id"])).json()
    assert failed["status"] == "failed" and "Connect your Gmail" in failed["error"]
