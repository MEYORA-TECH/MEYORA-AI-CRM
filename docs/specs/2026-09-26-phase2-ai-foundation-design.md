# Phase 2 — AI Foundation

Date: 2026-09-26 · Builds on §3 of the platform spec (provider pool, privacy
guardrail, free-tier economics, context budget, drift safeguards).

## Scope

Provider abstraction + Groq, streaming AI chat, conversation history, and
**read-only** CRM tools. Write tools (create/update with confirmation) are
Phase 6; memory and summaries are Phase 3.

## Backend (`app/ai/`)

| Unit | Responsibility |
|---|---|
| `providers/base.py` | Neutral types: `ChatMessage`, `ToolSpec`, `StreamEvent`; `AIProvider` protocol; `ProviderRateLimited` / `ProviderError` |
| `providers/openai_compat.py` | One implementation for every OpenAI-compatible API (Groq, OpenRouter, Meta Model API, Gemini's compat endpoint, Ollama). Streams SSE, accumulates tool-call deltas, reads usage and rate-limit headers |
| `registry.py` | Provider pool from settings. Each entry: id, base URL, key env var, chat/fast model, privacy class (`trusted` / `public_only`), context limit, enabled environments. `route(purpose, data_class)` returns candidates in priority order and **never** returns a `public_only` provider for `crm` data |
| `budget.py` | Per-request token budget from the model's configured context: system + tools, page card, recent turns, reserved output. Estimation is chars/4 with a margin; real usage from the provider is logged |
| `tools/` | Registry of read tools with Pydantic arguments, a group, and a handler returning `{summary for the model, rows for the UI, entity refs}`. Results are capped (≤10 rows) and compact |
| `tool_select.py` | Picks tool groups by keywords + the current page; falls back to all read tools |
| `agent.py` | Loop: max 3 model calls per turn; executes tool calls (parallel allowed), validates args, streams events |
| `service.py` | Conversation lifecycle, quota check, provider failover **at turn start only**, persistence, usage logging |

### Data (all tenant-owned, RLS; conversations private to their user)

- `ai_conversations` — user_id, title, provider, model (pinned at first
  turn), `state` jsonb (working set of entity refs), last_message_at,
  deleted_at.
- `ai_messages` — conversation_id, role (user/assistant/tool), content,
  tool_calls jsonb, tool_call_id, tool_name, `ui` jsonb (rows to render),
  provider, model, prompt/completion tokens.
- `ai_usage_logs` — request_id, user_id, conversation_id, provider, model,
  purpose, latency_ms, prompt/completion tokens, tool calls, status, error.

### API

- `POST /api/ai/chat` → `text/event-stream`. Events: `conversation`,
  `tool_start`, `tool_result`, `token`, `done` (usage), `error`.
- `GET/PATCH/DELETE /api/ai/conversations[/{id}]`, `GET …/{id}/messages`,
  search with `q`.
- `GET /api/ai/status` — whether AI is configured, today's usage vs quota.

### Rules

- CRM data only reaches `trusted` providers (tested).
- Tool results are wrapped as data; instructions inside them are ignored.
- Per-user daily token quota (default 60k) from `ai_usage_logs`; 429 with
  a clear message when exhausted.
- No AI answers are hard-coded; if no provider is configured the UI says
  so and the chat is disabled.

## Frontend

- **AI panel**: right-side glass drawer (topbar spark button, Ctrl+J), aware
  of the page's record. **Assistant page** with conversation history
  (rename, delete, search).
- Streaming markdown, tool indicators ("Searching deals…"), tool results
  rendered as linked record lists with a `CRM` source chip, suggested
  prompts, usage/quota line.

## Testing

Provider stream parsing (mocked HTTP transport), guardrail routing, tool
tenant isolation, agent loop with a scripted provider (test double only),
SSE endpoint, quota enforcement, conversation privacy between users.
