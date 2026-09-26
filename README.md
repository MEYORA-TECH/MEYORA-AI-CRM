# Meyora

An AI-native CRM. This repository holds Phase 1: the CRM foundation the AI layer is built on.
Design and platform decisions: [`docs/specs/2026-09-25-meyora-platform-and-phase1-design.md`](docs/specs/2026-09-25-meyora-platform-and-phase1-design.md).

| Part | Stack |
|---|---|
| `backend/` | FastAPI · async SQLAlchemy · Alembic · PostgreSQL 16 + pgvector (row-level security) |
| `frontend/` | React 18 · TypeScript · Vite · Tailwind CSS v4 · TanStack Query/Table · Radix · Motion |

## Run it locally

Requirements: Docker Desktop, Python 3.12, Node 20+.

```bash
cp .env.example .env            # then set passwords and JWT_SECRET
docker compose up -d db         # Postgres + pgvector; creates the non-superuser `meyora` role

cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt    # macOS/Linux: .venv/bin/pip
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:app --port 8000

cd ../frontend
npm install
npm run dev                      # http://localhost:5173, proxies /api to :8000
```

API docs (development only): http://localhost:8000/api/docs

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest      # uses TEST_DATABASE_URL (meyora_test)
cd ../frontend
npm run typecheck && npm run build
```

## Regenerating frontend API types

After changing backend schemas:

```bash
cd backend && .venv/Scripts/python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi.json','w'), indent=1)"
cd ../frontend && npm run gen:api
```

## How tenant isolation works

Every tenant-owned table carries `organization_id`. Repositories filter on it explicitly, and
Postgres row-level security (`ENABLE` + `FORCE`) enforces it again: each transaction starts with
`set_config('app.org_id', …, true)`, and with no organization set, queries return nothing. The app
connects as a non-superuser role, so policies always apply. Cross-record references are validated
against the caller's organization before insert.

## AI assistant, memory and background jobs

- **AI provider:** add a free `GROQ_API_KEY` to `.env` and restart the API. Without a key the
  assistant says it isn't set up; nothing is faked. More providers: `AI_EXTRA_PROVIDERS` (JSON),
  each tagged `trusted` or `public_only` — CRM data only ever goes to `trusted` ones.
- **Embeddings** run locally (FastEmbed, `BAAI/bge-small-en-v1.5`, ~200 MB RAM). The model
  downloads from Hugging Face on first use.
- **Jobs** (indexing, memory extraction, summaries) run in a worker inside the API process.
  Jobs that need a model wait until a provider is configured.
- **Existing data** created before the knowledge index: `.venv/Scripts/python -m app.ai.backfill`.
