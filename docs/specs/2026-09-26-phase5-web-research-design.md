# Phase 5 — Web research

Date: 2026-09-26 · Builds on the provider pool and privacy guardrail.

## Principles

- Web information is **external and unverified**. It is always labelled
  "Web" with its source link, kept apart from CRM facts, and never written
  into CRM records or memory without a person choosing to.
- **No server-side URL fetching.** Search and page extraction go through
  the search provider (Tavily), so Meyora has no SSRF surface.
- **Free-tier budget:** Tavily basic search costs 1 credit. Results are
  cached per organization for 24 h; a monthly organization cap and a daily
  per-user cap stop one person using up the month.
- Queries carry public names only (company name, website domain, industry,
  city), never notes, emails or deal details.

## Units

| Unit | Responsibility |
|---|---|
| `integrations/web/base.py` | `WebSearchProvider` interface, `WebResult` |
| `integrations/web/tavily.py` | Tavily search (Bearer auth), mocked transport in tests |
| `services/web_research.py` | Cached, budgeted search; company/lead research query plans; research briefs |
| AI tools | `web_search`, `research_company`, `research_lead` return numbered sources [W1]… |
| Registry | Optional Gemini (`GEMINI_API_KEY`) as a `public_only` provider via its OpenAI-compatible endpoint |

## Research briefs

`POST /api/research/{companies|leads}/{id}` runs the query plan, then asks a
model for a structured brief (what they do, recent news, signals, possible
talking points) citing [n] sources. The prompt contains only public inputs
(name, website, industry, city + web results), so it is routed as `public`:
Gemini free when configured, otherwise Groq. Briefs are stored with their
sources and model, shown on a "Web research" tab, and can be saved as a
note on request.

## Data (RLS)

- `web_search_cache`: query hash, provider, params, results, created_at.
- `web_search_logs`: user, query, provider, cached, created_at (budget).
- `research_briefs`: entity type/id, content (markdown), sources, model,
  provider, created_by, created_at.

## Testing

Fake Tavily transport: result parsing and citations, cache hits spend no
credit, monthly and daily caps, research tools in chat, briefs routed to a
public-only provider while CRM chat never is, org isolation.
