# Phase 6 — AI actions with confirmation

Date: 2026-09-26 · Brief rule 12: destructive or externally visible AI actions
need confirmation. Meyora goes further: **every** AI write is a proposal until
a person confirms it.

## Flow

1. The model calls a write tool (e.g. `create_task`). Arguments are validated
   and references resolved, but nothing is written. An `ai_actions` row is
   stored with a human-readable preview (target, field changes old → new).
2. The chat shows an action card: **Confirm** / **Cancel**; several proposals
   from one turn get **Confirm all**. The model is told the action is
   awaiting confirmation and must not claim it is done.
3. On confirm, the action runs through the same services and permission
   checks as the UI, as the confirming user, with audit entries marked
   `actor_type = ai`. If the target changed since the proposal, the action is
   refused ("changed since it was proposed"). Proposals expire after 30 min.
   Confirming twice is a 409.
4. The outcome is written into the conversation as an event, so the next
   turn knows what actually happened.

No delete actions in this phase.

## Actions

`create_task`, `update_task`, `log_activity`, `add_note`, `create_lead`,
`update_lead`, `update_deal` (stage by name, amount, close date,
probability), `update_contact`, `draft_email`.

**Email:** `draft_email` proposes to / subject / body (reply threading when a
thread ref is given). The card lets the user edit before pressing **Send**.
Sending uses Gmail (`gmail.send` scope, requested when connecting); the sent
message is stored as outbound mail on the thread. Without a connected
mailbox the card offers copy and "open in mail app" instead of Send.

## Data

`ai_actions` (RLS): conversation, user, tool, args, preview, target
type/id, target version (updated_at at proposal), status
(proposed / executed / rejected / failed / expired), result, error,
expires_at, decided_at.

## Testing

Proposal writes nothing; confirm executes with audit `actor_type=ai`;
reject; expiry; stale target refused; double confirm; batch confirm;
permission re-check at execution; outcome event reaches the next turn;
email send via fake Gmail stores the outbound message; other users can't
confirm someone else's action.
