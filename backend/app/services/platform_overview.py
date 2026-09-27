"""Numbers for the Platform admin dashboard: the whole installation at a glance.

Workspace data is protected by row-level security, and this does not bypass it: each
workspace's totals are read with that workspace set as the tenant, one statement per
workspace. Only counts and sums leave this module, never records.
"""

import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import set_tenant
from app.services import platform

MAX_WORKSPACES = 200
DAYS = 14

# Tables without RLS: organisations, users, memberships, jobs.
_GLOBAL = text("""
SELECT
  (SELECT count(*) FROM organizations) AS workspaces,
  (SELECT count(*) FROM users) AS users,
  (SELECT count(*) FROM users WHERE last_login_at >= now() - interval '7 days') AS active_7d,
  (SELECT count(*) FROM users WHERE created_at >= now() - interval '30 days') AS new_30d,
  (SELECT coalesce(json_agg(x), '[]') FROM
     (SELECT o.id, o.name, o.created_at,
             (SELECT count(*) FROM memberships m WHERE m.organization_id = o.id) AS members
      FROM organizations o ORDER BY o.created_at LIMIT :cap) x) AS orgs,
  (SELECT coalesce(json_object_agg(status, n), '{}') FROM
     (SELECT status, count(*) AS n FROM jobs GROUP BY status) j) AS jobs,
  (SELECT count(*) FROM jobs WHERE status = 'failed' AND created_at >= now() - interval '1 day') AS failed_24h,
  (SELECT coalesce(json_agg(x), '[]') FROM
     (SELECT email, full_name, created_at, last_login_at FROM users ORDER BY created_at DESC LIMIT 6) x) AS recent_users
""")

# Runs once per workspace, with that workspace as the tenant.
_WORKSPACE = text("""
SELECT
  (SELECT count(*) FROM companies WHERE organization_id = :org AND deleted_at IS NULL) AS companies,
  (SELECT count(*) FROM contacts WHERE organization_id = :org AND deleted_at IS NULL) AS contacts,
  (SELECT count(*) FROM leads WHERE organization_id = :org AND deleted_at IS NULL) AS leads,
  (SELECT count(*) FROM deals WHERE organization_id = :org AND deleted_at IS NULL AND status = 'open') AS deals_open,
  (SELECT coalesce(sum(prompt_tokens + completion_tokens), 0) FROM ai_usage_logs
    WHERE organization_id = :org AND created_at >= :today) AS tokens_today,
  (SELECT coalesce(sum(prompt_tokens + completion_tokens), 0) FROM ai_usage_logs
    WHERE organization_id = :org AND created_at >= :since30) AS tokens_30d,
  (SELECT coalesce(json_object_agg(provider, t), '{}') FROM
     (SELECT provider, sum(prompt_tokens + completion_tokens) AS t FROM ai_usage_logs
      WHERE organization_id = :org AND created_at >= :since30 GROUP BY provider) p) AS providers,
  (SELECT coalesce(json_object_agg(d, t), '{}') FROM
     (SELECT (created_at AT TIME ZONE :tz)::date AS d, sum(prompt_tokens + completion_tokens) AS t FROM ai_usage_logs
      WHERE organization_id = :org AND created_at >= :since_days GROUP BY 1) x) AS daily,
  (SELECT count(*) FROM web_search_logs
    WHERE organization_id = :org AND NOT cached AND created_at >= :month) AS web_month,
  (SELECT count(*) FROM mail_accounts WHERE organization_id = :org) AS mailboxes,
  (SELECT max(created_at) FROM audit_logs WHERE organization_id = :org) AS last_activity_at
""")


async def build(session: AsyncSession, tz_name: str, local_today: date) -> dict[str, Any]:
    now = datetime.now(UTC)
    started = time.perf_counter()
    g = (await session.execute(_GLOBAL, {"cap": MAX_WORKSPACES})).one()
    db_latency_ms = round((time.perf_counter() - started) * 1000)

    params = {
        "tz": tz_name,
        "today": now - timedelta(hours=24),
        "since30": now - timedelta(days=30),
        "since_days": now - timedelta(days=DAYS + 1),
        "month": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    }
    rows, providers, daily = [], {}, {}
    for org in g.orgs:
        await set_tenant(session, org["id"])
        w = (await session.execute(_WORKSPACE, {**params, "org": org["id"]})).one()
        for p, t in w.providers.items():
            providers[p] = providers.get(p, 0) + int(t)
        for d, t in w.daily.items():
            daily[d] = daily.get(d, 0) + int(t)
        rows.append({
            **org, "companies": w.companies, "contacts": w.contacts, "leads": w.leads, "deals_open": w.deals_open,
            "ai_tokens_today": w.tokens_today, "ai_tokens_30d": w.tokens_30d, "web_searches_month": w.web_month,
            "mailboxes": w.mailboxes, "last_activity_at": w.last_activity_at,
        })
    session.info["organization_id"] = None  # leave no tenant behind on this session
    await session.execute(text("SELECT set_config('app.org_id', '', true)"))

    s = get_settings()
    days = [local_today - timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    return {
        "generated_at": now,
        "environment": s.app_env,
        "db_latency_ms": db_latency_ms,
        "workspaces": g.workspaces,
        "users": g.users,
        "active_users_7d": g.active_7d,
        "new_users_30d": g.new_30d,
        "ai_tokens_today": sum(r["ai_tokens_today"] for r in rows),
        "ai_tokens_30d": sum(r["ai_tokens_30d"] for r in rows),
        "ai_daily_quota_per_user": s.ai_daily_token_quota,
        "web_searches_month": sum(r["web_searches_month"] for r in rows),
        "web_monthly_limit_per_workspace": s.web_search_monthly_limit,
        "mailboxes": sum(r["mailboxes"] for r in rows),
        "jobs": g.jobs,
        "failed_jobs_24h": g.failed_24h,
        "daily_tokens": [{"day": d, "tokens": daily.get(d.isoformat(), 0)} for d in days],
        "providers": sorted(({"provider": p, "tokens": t} for p, t in providers.items()), key=lambda x: -x["tokens"]),
        "workspace_list": sorted(rows, key=lambda r: -r["ai_tokens_30d"]),
        "recent_users": g.recent_users,
        "health": {
            "google_ready": platform.google_ready(),
            "sign_in_live": platform.google_auth_enabled(),
            "gmail_live": platform.gmail_enabled(),
            "shared_keys": {p: bool(platform.shared_key(p)) for p in platform.SHARED_KEY_PROVIDERS},
        },
    }
