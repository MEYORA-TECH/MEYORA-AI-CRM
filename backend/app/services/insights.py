"""Prospecting insights for the dashboard, in a single round trip.

Every figure comes from one SQL statement: Postgres builds each section as JSON, so
the dashboard stays fast even against a distant database. Row-level security still
applies (the session's tenant is set); the explicit organisation filter is the first layer.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.dashboard import Insights

STALE_DAYS = 14  # a lead or deal with no completed activity for this long needs attention
WEEKS = 8

# Imported associations and industrial estates carry this tag: outreach partners, not sales targets.
_PARTNER = "('|' || lower(array_to_string(tags, '|')) || '|') LIKE '%|outreach partner|%'"
_DECIDER = "('|' || lower(array_to_string(k.tags, '|')) || '|') LIKE '%|decision maker|%'"

_SQL = text(f"""
WITH
  leads_live AS (
    SELECT * FROM leads WHERE organization_id = :org AND deleted_at IS NULL
  ),
  companies_live AS (
    SELECT c.*, {_PARTNER} AS partner FROM companies c WHERE organization_id = :org AND deleted_at IS NULL
  ),
  contact_stats AS (
    SELECT k.company_id,
           count(*) AS contacts,
           count(*) FILTER (WHERE {_DECIDER}) AS deciders,
           count(*) FILTER (WHERE k.email IS NOT NULL) AS emails
    FROM contacts k
    WHERE k.organization_id = :org AND k.deleted_at IS NULL AND k.company_id IS NOT NULL
    GROUP BY k.company_id
  ),
  lead_last AS (
    SELECT lead_id, max(occurred_at) AS at FROM activities
    WHERE organization_id = :org AND status = 'completed' AND lead_id IS NOT NULL
    GROUP BY lead_id
  ),
  to_contact AS (
    SELECT l.*, ll.at AS last_contact_at
    FROM leads_live l LEFT JOIN lead_last ll ON ll.lead_id = l.id
    WHERE l.status IN ('new', 'contacted') AND (ll.at IS NULL OR ll.at < :stale)
  )
SELECT
  (SELECT coalesce(json_object_agg(status, n), '{{}}') FROM
     (SELECT status, count(*) AS n FROM leads_live GROUP BY status) s) AS funnel,
  (SELECT json_build_object(
      'top', count(*) FILTER (WHERE score >= 90),
      'high', count(*) FILTER (WHERE score >= 80 AND score < 90),
      'medium', count(*) FILTER (WHERE score >= 70 AND score < 80),
      'low', count(*) FILTER (WHERE score < 70))
   FROM leads_live WHERE status IN ('new', 'contacted', 'qualified')) AS fit,
  (SELECT json_build_object(
      'companies', count(*) FILTER (WHERE NOT c.partner),
      'partners', count(*) FILTER (WHERE c.partner),
      'with_contacts', count(*) FILTER (WHERE NOT c.partner AND coalesce(cs.contacts, 0) > 0),
      'with_decision_maker', count(*) FILTER (WHERE NOT c.partner AND coalesce(cs.deciders, 0) > 0),
      'with_email', count(*) FILTER (WHERE NOT c.partner AND (c.email IS NOT NULL OR coalesce(cs.emails, 0) > 0)))
   FROM companies_live c LEFT JOIN contact_stats cs ON cs.company_id = c.id) AS coverage,
  (SELECT coalesce(json_agg(x), '[]') FROM
     (SELECT coalesce(city, 'Unknown') AS label, count(*) AS count FROM companies_live
      WHERE NOT partner GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 6) x) AS cities,
  (SELECT coalesce(json_agg(x), '[]') FROM
     (SELECT coalesce(industry, 'Unknown') AS label, count(*) AS count FROM companies_live
      WHERE NOT partner GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 6) x) AS industries,
  (SELECT coalesce(json_agg(x ORDER BY x.week_start), '[]') FROM
     (SELECT date_trunc('week', occurred_at AT TIME ZONE :tz)::date AS week_start,
             count(*) FILTER (WHERE type = 'call') AS calls,
             count(*) FILTER (WHERE type = 'email') AS emails,
             count(*) FILTER (WHERE type = 'meeting') AS meetings,
             count(*) FILTER (WHERE type = 'linkedin') AS linkedin,
             count(*) FILTER (WHERE type NOT IN ('call', 'email', 'meeting', 'linkedin')) AS other
      FROM activities
      WHERE organization_id = :org AND status = 'completed'
        AND type NOT IN ('stage_change', 'system') AND occurred_at >= :since
      GROUP BY 1) x) AS weeks,
  (SELECT coalesce(json_agg(x), '[]') FROM
     (SELECT id, name, company_name, score, status, industry,
             custom_fields ->> 'Priority' AS priority,
             email IS NOT NULL AS has_email, phone IS NOT NULL AS has_phone, last_contact_at
      FROM to_contact ORDER BY score DESC, created_at LIMIT 8) x) AS contact_next,
  (SELECT count(*) FROM to_contact) AS to_contact,
  (SELECT count(*) FROM deals d
   WHERE d.organization_id = :org AND d.deleted_at IS NULL AND d.status = 'open'
     AND d.created_at < :stale  -- a deal opened this week isn't stale
     AND NOT EXISTS (SELECT 1 FROM activities a WHERE a.deal_id = d.id AND a.status = 'completed'
                     AND a.occurred_at >= :stale)) AS stale_deals
""")


async def build(session: AsyncSession, organization_id, tz_name: str, week_start: date) -> Insights:
    """`week_start` is the Monday of the current week in the viewer's time zone."""
    now = datetime.now(UTC)
    first_week = week_start - timedelta(weeks=WEEKS - 1)
    row = (
        await session.execute(
            _SQL,
            {
                "org": organization_id,
                "tz": tz_name,
                "stale": now - timedelta(days=STALE_DAYS),
                # a day early so the first week's Monday is covered in any time zone
                "since": datetime.combine(first_week - timedelta(days=1), datetime.min.time(), UTC),
            },
        )
    ).one()

    # Fill weeks with no activity, so the chart always has WEEKS bars.
    by_week = {date.fromisoformat(str(w["week_start"])): w for w in row.weeks}
    weeks = [
        by_week.get(first_week + timedelta(weeks=i))
        or {
            "week_start": first_week + timedelta(weeks=i),
            "calls": 0, "emails": 0, "meetings": 0, "linkedin": 0, "other": 0,
        }
        for i in range(WEEKS)
    ]
    return Insights.model_validate(
        {
            "funnel": row.funnel,
            "fit": row.fit,
            "coverage": row.coverage,
            "cities": row.cities,
            "industries": row.industries,
            "weeks": weeks,
            "contact_next": row.contact_next,
            "to_contact": row.to_contact,
            "stale_deals": row.stale_deals,
            "stale_days": STALE_DAYS,
        }
    )
