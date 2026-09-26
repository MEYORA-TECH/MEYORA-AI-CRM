# Phase 3 — Context & Memory

Date: 2026-09-26 · Implements the context-window and memory plan agreed in
chat (platform spec §3). Three stores stay separate: conversation history,
knowledge index, memories.

## Units

| Unit | Responsibility |
|---|---|
| `ai/embeddings.py` | `EmbeddingProvider` interface; `FastEmbedProvider` (bge-small-en-v1.5, 384 dims, lazy-loaded, ~200 MB RAM) and a deterministic `HashEmbedder` used only in tests |
| `jobs/` | Postgres job table (`FOR UPDATE SKIP LOCKED`) + in-process worker started with the app. Jobs retry with backoff; LLM jobs wait while no provider is configured |
| `ai/knowledge.py` | Knowledge index: notes, activity bodies and record descriptions chunked and embedded into `knowledge_chunks`; re-indexed when the source changes (content hash) |
| `ai/memory.py` | Memories: create (explicit), extract (LLM, background), dedup (cosine ≥ 0.92 → update), supersede on contradiction, scored retrieval |
| `ai/summaries.py` | Rolling conversation summary with the fast model once > 12 unsummarised messages |
| `ai/context.py` | Assembles per-turn context within budget: summary, recent turns, top memories (≤ 6, ≤ 500 tokens) |

## Data (tenant-owned, RLS)

- `ai_memories`: content, memory_type (fact / preference / requirement /
  relationship / decision), scope (user / organization / company / contact /
  deal), user_id (for user scope and author), company_id, contact_id,
  deal_id, source_type, source_id, confidence, importance (1–5), status
  (active / superseded / pending_review), superseded_by_id, valid_from,
  valid_until, embedding vector(384), embedding_model, content_hash,
  access_count, last_accessed_at, created_by (user / ai).
- `knowledge_chunks`: source_type, source_id, company/contact/lead/deal ids,
  content, content_hash, embedding, embedding_model.
- `ai_conversation_summaries`: conversation_id, summary,
  covered_until (message timestamp), message_count.
- `jobs`: kind, payload, organization_id, status, attempts, run_after, error.

HNSW indexes (`vector_cosine_ops`) on both embedding columns.

## Retrieval score

`0.6·similarity + 0.2·importance/5 + 0.1·recency + 0.1·scope_match`, where
recency decays over 180 days and scope_match is 1 when the memory is linked
to the page record or a working-set entity. Minimum similarity 0.55.
User-scope memories are only visible to their user.

## Agent changes

- New tools: `search_knowledge` (semantic search over notes and call logs),
  `remember` (explicit memory; internal and editable, so no confirmation).
- Each turn gets relevant memories injected as labelled data, plus the
  conversation summary instead of old turns.
- Memories extracted only from the user's own statements and CRM content,
  never from the assistant's text. Extractions from a fallback provider
  start at lower confidence; confidence < 0.6 → pending_review.

## UI

- **Memory** page: search (semantic), filter by scope/status, edit, pin
  (importance 5), delete, approve pending.
- **AI memory** tab on company, contact and deal pages, with "Add memory".
- Chat shows "Remembered …" when the assistant saves a memory.

## Testing

Job queue claim/retry, knowledge indexing on note create/update, memory
dedup + supersede, scored retrieval incl. user-scope privacy and tenant
isolation, summary trigger, context budget, remember/search_knowledge tools.
