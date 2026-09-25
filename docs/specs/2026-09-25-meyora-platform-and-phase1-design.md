# Meyora AI CRM — Platform Decisions & Phase 1 Design

Date: 2026-09-25 · Status: approved in discussion

Meyora is a multi-tenant, AI-native CRM. The traditional CRM is the structure,
PostgreSQL is the truth, and an AI agent operates on top of it through tools.
The full product brief is split into seven phases; this document fixes the
platform-wide decisions and specifies Phase 1 (foundation). Later phases get
their own specs.

## 1. Hard constraints

- **Zero running cost for now.** Free-tier hosting, free-tier AI APIs, no own
  hardware/GPU.
- **Everyone in an organization sees and edits all CRM records.** Delete,
  pipeline configuration and member management require Manager or above.
  The permission layer must allow ownership rules later without rework.
- **Strict tenant isolation.** No request can read or write another
  organization's data.

## 2. Stack

| Layer | Choice |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS v4, Radix primitives (shadcn-style, restyled), TanStack Query + Table, React Router, Zustand, Motion, dnd-kit, cmdk, Recharts, React Hook Form + Zod, Sonner, Lucide |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic |
| Database | PostgreSQL 16 + pgvector + pg_trgm |
| Auth | Argon2 password hashing, short-lived JWT access token (memory only on the client), rotating refresh token in an httpOnly cookie with reuse detection |
| Background work | Postgres job table + in-process worker loop (no Redis; added from Phase 2 when needed) |
| Embeddings | FastEmbed, quantized `bge-small-en-v1.5` (384 dims), in-process, lazy-loaded; swappable via `EmbeddingProvider` |
| Logging | structlog JSON with request IDs |
| Tests | pytest + httpx against a real Postgres (Docker) |
| Local dev | Docker Compose (Postgres + pgvector); frontend via `npm run dev` |
| Hosting (target) | Neon (Postgres + pgvector), Render free web service (Docker), Vercel (frontend) |

## 3. AI platform decisions (implemented from Phase 2)

- **Provider abstraction.** One `OpenAICompatibleProvider` plus config entries.
  Business logic never imports a provider.
- **Provider pool** (config-driven), each entry tagged with a privacy class:

  | Priority | Provider | CRM data | Role |
  |---|---|---|---|
  | 1 | Groq free — gpt-oss-120b (chat), gpt-oss-20b (background), qwen3.8-27b (overflow) | allowed | primary |
  | 2 | OpenRouter free with no-training routing required | allowed | failover |
  | 3 | Gemini free | public only | web research |
  | 4 | OpenRouter free (any) | public only | research overflow |
  | dev | NVIDIA NIM, Alibaba Qwen trial, FreeLLMAPI | public only | local testing, excluded in production |
  | off | Cheap paid slot (DeepSeek-class model on a privacy-compliant host) | allowed | disabled until chosen |

- **Privacy guardrail.** Every AI request is tagged `crm` or `public`. The
  router refuses to send `crm` requests to a provider whose class is
  `public_only`. Enforced in code and covered by tests.
- **Free-tier economics.** Compute with SQL, narrate with the LLM only on
  request. Direct-render path (LLM picks the tool, UI renders the rows, no
  second narration call). Parallel tool calls, max ~3 loop iterations.
  Cached AI summaries invalidated by data changes. Per-user daily quotas and
  an admin usage meter. Rate-limit-aware scheduler reading provider headers.
  Bring-your-own-key per organization (encrypted).
- **Context window.** Per-request budget ~3–5k tokens on the free tier,
  derived from each model's configured limits. Sections: system + selected
  tool groups, page entity, conversation summary, recent turns, memories,
  retrieved context, reserved output. Tool results compacted with
  `result_ref` for paging. Conversation working set of entity IDs for
  follow-ups ("all of them").
- **Memory.** Three separate stores: conversation history, knowledge index
  (RAG chunks), memories (durable facts with scope, provenance, confidence,
  importance, status/supersession, validity). Explicit "remember" writes
  immediately; extraction runs as a background job; dedup by similarity;
  contradictions supersede, never delete. Users can view/edit/delete.

### 3.1 Context drift and contamination safeguards

Failover between models and mixing sources create two risks; both are
addressed by design:

1. **Model drift inside a conversation.** A conversation is pinned to the
   model that started it. Failover happens only at a turn boundary, never
   mid agent loop. Each stored assistant message records `provider` and
   `model`, and the UI shows when a fallback answered.
2. **Provider-format contamination.** History is stored in one neutral
   (OpenAI-style) format. Provider-specific reasoning/thinking content is
   never persisted or replayed to another model.
3. **Invalid actions from a weaker model.** Every tool call is validated
   against its Pydantic schema before execution; one repair retry, then a
   visible error. Writes still require confirmation where applicable.
4. **Memory contamination.** Memories are only extracted from grounded
   sources (user statements, CRM records, emails, documents), never from
   model speculation. Each memory stores the model and source that produced
   it; fallback-model extractions start at lower confidence and low-
   confidence memories wait for review.
5. **Tenant contamination.** All context is assembled per request from
   RLS-scoped queries. Every cache key includes `organization_id`. No
   cross-organization memory or summary is ever reused.
6. **Web contamination / prompt injection.** Web and email content is wrapped
   and labelled as untrusted data; instructions inside it are never
   followed. Web facts are shown as external and never written to CRM
   records or memories without user confirmation.

## 4. Phase 1 scope

Authentication, organizations & RBAC, tenant isolation, companies, contacts,
leads (with conversion), pipelines & deals (Kanban + list), activities &
unified timeline, tasks, notes, dashboard, audit log, the glass UI shell.
Google OAuth ships with Gmail in Phase 4 (same OAuth client and scopes).

### 4.1 Tenant isolation (two layers)

1. **Application layer.** Every repository query filters by
   `organization_id` from the authenticated context. Referenced IDs
   (company, contact, owner, stage…) are validated to belong to the same
   organization before insert/update — foreign keys alone do not prevent a
   cross-tenant reference.
2. **Database layer (RLS).** Every tenant-owned table has
   `ENABLE` + `FORCE ROW LEVEL SECURITY` with the policy
   `organization_id = NULLIF(current_setting('app.org_id', true), '')::uuid`.
   The app connects as a non-superuser role. The org ID is set with
   `set_config(..., true)` at the start of every transaction from
   `session.info`, so an unset context returns zero rows (fail closed).

Global tables without RLS (access checked in code): `organizations`,
`users`, `memberships`, `refresh_tokens`, `invitations`.

### 4.2 Roles and permissions

Roles: Owner, Admin, Manager, Member. Permissions are strings mapped from
roles in one module, checked through a `require(permission)` dependency.

| Permission | Member | Manager | Admin | Owner |
|---|---|---|---|---|
| `crm:read`, `crm:write` | ✓ | ✓ | ✓ | ✓ |
| `crm:delete` | | ✓ | ✓ | ✓ |
| `pipelines:manage` | | ✓ | ✓ | ✓ |
| `members:read` | ✓ | ✓ | ✓ | ✓ |
| `members:manage`, `org:manage`, `audit:read` | | | ✓ | ✓ |
| `org:delete`, transfer ownership | | | | ✓ |

Rules: the last Owner cannot be removed or demoted; Admins cannot grant or
change the Owner role.

### 4.3 Data model (all tables: UUID PK, `created_at`, `updated_at`)

Tenant-owned tables also carry `organization_id` (indexed, FK) and, for CRM
records, `deleted_at` (soft delete), `tags text[]` (GIN), and
`custom_fields jsonb`.

- **organizations** — name, slug (unique), default_currency (INR).
- **users** — email (unique, lower-cased), password_hash (nullable for future
  Google-only users), full_name, avatar_url, is_active, last_login_at.
- **memberships** — organization_id, user_id, role; unique (org, user).
- **refresh_tokens** — user_id, organization_id, token_hash (unique),
  family_id, expires_at, revoked_at, replaced_by_id, user_agent, ip.
- **invitations** — organization_id, email, role, token_hash, invited_by,
  expires_at, accepted_at.
- **companies** — name, industry, website, phone, email, address, city,
  state, country, employee_count, annual_revenue, description, status
  (prospect/active/customer/churned/inactive), owner_id.
- **contacts** — first_name, last_name, job_title, company_id, email, phone,
  linkedin_url, address, city, state, country, owner_id, description.
- **leads** — name, company_name, job_title, email, phone, source, industry,
  status (new/contacted/qualified/unqualified/converted/lost), score
  (0–100), owner_id, description, converted_at, converted_company_id,
  converted_contact_id, converted_deal_id.
- **pipelines** — name, is_default. **pipeline_stages** — pipeline_id, name,
  position, probability, kind (open/won/lost), color.
- **deals** — name, company_id, contact_id, owner_id, amount numeric(18,2),
  currency char(3), pipeline_id, stage_id, status (open/won/lost, derived
  from stage kind), probability, expected_close_date, source, description,
  closed_at, lead_id.
- **activities** — type (call/meeting/email/note/task/follow_up/
  stage_change/system), status (planned/completed/cancelled), subject, body,
  occurred_at, duration_minutes, outcome, actor_id, company_id, contact_id,
  lead_id, deal_id, metadata jsonb.
- **tasks** — title, description, status (todo/in_progress/completed/
  cancelled), priority (low/medium/high/urgent), due_at, completed_at,
  assignee_id, created_by_id, company_id, contact_id, lead_id, deal_id.
- **notes** — body, author_id, company_id, contact_id, lead_id, deal_id,
  task_id.
- **audit_logs** — actor_user_id, actor_type (user/ai/system), action,
  entity_type, entity_id, changes jsonb (old/new per field), ip,
  user_agent, request_id, created_at.

Indexes: `(organization_id, <frequent filter>)` composites, trigram GIN on
names/emails for search, GIN on tags. Extensions `vector` and `pg_trgm` are
enabled in the first migration so Phase 3 needs no infra change.

### 4.4 Domain rules

- **Lead conversion** (one transaction): optionally create or reuse a
  company, create a contact, optionally create a deal in a chosen
  pipeline/stage; mark the lead converted with links; log an activity and
  an audit entry. Converting twice returns 409.
- **Deal stage change**: status and `closed_at` follow the stage kind;
  probability defaults to the stage's value unless explicitly set; a
  `stage_change` activity and an audit entry record old → new.
- **Pipelines**: every organization gets a default pipeline on creation
  (Lead, Qualified, Discovery, Proposal, Negotiation, Won, Lost). A stage
  with deals cannot be deleted (409).
- **Tasks**: completing sets `completed_at`; reopening clears it.
- **Audit**: every create/update/delete, login, conversion, stage change,
  membership/role change. Changes store only the fields that changed.

### 4.5 API conventions

- REST under `/api`. List endpoints: `page`, `page_size` (≤100), `q`,
  entity filters, `sort` (whitelisted, `-field` for descending). Response
  `{items, total, page, page_size}`.
- Errors: `{"error": {"code", "message", "details"}}` with 400/401/403/404/
  409/422/429 used consistently.
- Auth: `POST /api/auth/register|login|refresh|logout|switch-organization`,
  `GET /api/auth/me`. Refresh cookie scoped to `/api/auth`, `SameSite=Strict`,
  `HttpOnly`, `Secure` in production; refresh also requires the
  `X-Requested-With` header (CSRF defense).
- Rate limiting on auth endpoints (in-memory per instance for Phase 1).

### 4.6 Frontend

- **Layout**: floating dark glass sidebar rail on the left (collapsed icons,
  expands with labels); frosted top bar with pill segmented sub-navigation,
  global search (⌘K), notifications, avatar; content on frosted cards over
  an ambient sage/mint gradient canvas.
- **Glassmorphism system**: surface tokens (`--glass-1/2/3` opacity steps,
  backdrop blur, hairline light borders, inner highlight, layered soft
  shadows). Dense data (tables, inputs) uses the most opaque step for
  legibility. Light and dark themes from day one. Respect
  `prefers-reduced-transparency` / `prefers-reduced-motion`.
- **Typography**: Plus Jakarta Sans, tabular numerals for money; INR
  formatting with lakh/crore grouping.
- **Pages**: login/register, dashboard, companies/contacts/leads (tables +
  detail pages with tabs + timeline), deals (Kanban + list + detail),
  activities, tasks, settings (organization, members, pipelines, audit).
- **AI affordance placeholders are not shipped in Phase 1** — no fake AI UI
  (Rule 1). The shell reserves the right-side AI panel slot and ⌘K "Ask AI"
  mode for Phase 2.
- API types generated from the FastAPI OpenAPI schema.

### 4.7 Testing

pytest against a real Postgres: auth flows (register, login, refresh
rotation, reuse detection, logout), RBAC denials, tenant isolation at both
layers (API 404 across orgs, raw RLS query returns nothing, cross-tenant
reference rejected), lead conversion, deal stage change side effects,
pagination/filter/sort. Frontend: typecheck + build in this phase.

## 5. Out of scope for Phase 1

AI features, Gmail/Google OAuth, documents, global semantic search, reports,
email sending, background jobs.
