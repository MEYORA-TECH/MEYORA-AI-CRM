# Deploying Meyora: Vercel + Azure Container Apps + Neon

The setup for the internal testing phase (up to ~5 users, a $100 Azure credit):

```
app.meyora.in  →  Vercel (React build, free)
api.meyora.in  →  Azure Container Apps (FastAPI, 0.5 vCPU / 1 GiB, min 0 / max 1)
                    ├── Neon Postgres (data; not on Azure, so it survives any move)
                    └── Groq / Tavily / Google (outside services)
```

Nothing here is Azure-specific: the API is a standard Docker image and the data lives in Neon.
To move hosts later, run the same image elsewhere with the same environment variables and
point `api.meyora.in` at it.

## Before you start

- **Keep these two values forever.** Copy `ENCRYPTION_KEY` and `JWT_SECRET` from your current `.env`.
  A different `ENCRYPTION_KEY` makes every saved API key, the Google secret and Gmail tokens unreadable.
- **Pick the region next to the database.** Every query is a round trip; from India to Neon's US East we
  measured ~550 ms per query. Either:
  - keep the current Neon (AWS US East, Ohio) and use Azure region **East US 2**, or
  - create a new Neon project in **AWS Singapore**, run `scripts.setup_database` and the import again,
    and use Azure region **Southeast Asia** (fast for India too).
- Both domains must be **subdomains of meyora.in**. The sign-in cookie is `SameSite=Strict`, so it only
  travels between `app.meyora.in` and `api.meyora.in`, not between `*.vercel.app` and `*.azurecontainerapps.io`.

## 1. Database (once, and after every new migration)

From your machine, with the Neon owner URLs in `.env`:

```bash
cd backend
python -m scripts.setup_database
```

This runs the migrations as the owner and prints/saves `NEON_APP_DATABASE_URL`, the restricted login the
app uses (it can't change tables or bypass row-level security). The container never runs migrations itself.

## 2. The API image

Push the repository to GitHub. The workflow `.github/workflows/backend-image.yml` builds the image and
publishes it to GitHub Container Registry as `ghcr.io/<owner>/<repo>/meyora-api:latest` (free, unlike Azure
Container Registry). The embedding model is baked into the image.

If the package is private, create a GitHub token with `read:packages` for Azure to pull with.

## 3. Azure Container Apps

1. **Container Apps environment** in the region chosen above. When asked for Log Analytics, set a
   **daily cap** (e.g. 0.1 GB) and **30-day retention**, or it can quietly use credit.
2. **Container app**
   - Image: `ghcr.io/<owner>/<repo>/meyora-api:latest` (registry `ghcr.io`, your GitHub user + token if private)
   - CPU / memory: **0.5 vCPU / 1 GiB**
   - Scale: **min 0, max 1** (HTTP scaling). Set **min 1** while importing data or during long test sessions.
   - Ingress: **external**, target port **8000**, HTTPS only
3. **Secrets** (Container app → Secrets), then reference them from environment variables (`secretref:`):
   `database-url`, `encryption-key`, `jwt-secret`, and any AI keys you keep on the server.
4. **Environment variables**: everything in [`backend/.env.production.example`](../../backend/.env.production.example).
   The important ones:

   | Variable | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | secretref: the `NEON_APP_DATABASE_URL` value |
   | `DB_STATEMENT_CACHE_SIZE` | `0` |
   | `ENCRYPTION_KEY`, `JWT_SECRET` | secretref: the values from your current `.env` |
   | `PUBLIC_URL` | `https://app.meyora.in` |
   | `API_PUBLIC_URL` | `https://api.meyora.in` |
   | `CORS_ORIGINS` | `["https://app.meyora.in"]` |
   | `EMBEDDING_WARMUP` | `true` |

   The app refuses to start in production if `ENCRYPTION_KEY` is missing, `JWT_SECRET` is short,
   `PUBLIC_URL` isn't https, or `CORS_ORIGINS` still says localhost. The logs say exactly which.
5. **Health probes**: liveness and readiness on `GET /api/health` (it doesn't touch the database, so probes
   never keep Neon awake). Startup probe: same path, allow ~60 s. `GET /api/health/db` checks the database.
6. **Custom domain** `api.meyora.in` with a free managed certificate (add the CNAME and TXT records it shows).

## 4. Vercel (web app)

1. New project from the repository, **root directory `frontend`** (it reads `frontend/vercel.json`).
2. Environment variable (Production): `VITE_API_URL=https://api.meyora.in`.
3. Domain: `app.meyora.in`.

`vercel.json` sends every app route to `index.html` (so links like `/leads/123` work) and adds security headers.

## 5. After the first deploy

- **Platform admin**: from your machine, `cd backend && DATABASE_URL=<app URL> DB_STATEMENT_CACHE_SIZE=0 python -m scripts.platform_admin grant you@example.com`
  (already done for meyoratech@gmail.com on the current Neon).
- **Google sign-in / Gmail**: in Google Cloud, add the redirect URIs shown on **Platform → Google & Gmail**
  (they will read `https://api.meyora.in/api/...`) and `https://app.meyora.in` as an origin.
- Check `https://api.meyora.in/api/health/db`, sign in at `https://app.meyora.in`, open the dashboard.

## How it behaves with scale-to-zero

- After ~5 minutes without requests the API scales to 0 and stops using compute.
- The first request after that starts a container (a few seconds; the model is already in the image and
  loads in the background).
- Background work (Gmail sync, AI indexing, summaries) pauses while at 0 and resumes on the next start;
  queued jobs wait in the database, nothing is lost.
- While running, the job worker sleeps until the next job is due (up to 10 minutes) instead of polling,
  so Neon can suspend too.

## Cost guards

- No Azure Container Registry (images come from GitHub).
- Log Analytics daily cap set in step 3.1.
- Set a **budget alert** in Azure Cost Management (e.g. at $20 and $50).
