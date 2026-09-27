"""Web tools. Results are external and unverified; each gets a citation id (w1, w2…) unique in the conversation."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.tools.base import Tool, ToolContext, ToolResult
from app.core.errors import AppError
from app.integrations.web.base import WebResult
from app.services import linkedin, records, web_research


def _cite(ctx: ToolContext, results: list[WebResult], title: str) -> ToolResult:
    if not results:
        return ToolResult(summary="The web search returned nothing.", ui={"kind": "web", "title": title, "rows": []})
    lines, rows = [], []
    for r in results:
        n = 1 + sum(1 for v in ctx.working_set.refs.values() if v["type"] == "web")
        ref = f"w{n}"
        ctx.working_set.refs[ref] = {"type": "web", "id": r.url, "name": r.title[:80]}
        date = f", {r.published[:10]}" if r.published else ""
        lines.append(f"[{ref}] {r.title} ({r.domain}{date}): {r.content[:600]}")
        rows.append(
            {
                "ref": ref,
                "title": r.title,
                "url": r.url,
                "domain": r.domain,
                "snippet": r.content[:220],
                "published": r.published,
            }
        )
    return ToolResult(
        summary="External web results (unverified; cite as [wN]):\n<web_data>\n" + "\n".join(lines) + "\n</web_data>",
        ui={"kind": "web", "title": title, "rows": rows},
    )


async def _run(ctx: ToolContext, fn) -> ToolResult:
    try:
        return await fn()
    except AppError as exc:  # not set up, budget used, or nothing to research: tell the model plainly
        return ToolResult(summary=exc.message, ok=False)


class WebSearch(BaseModel):
    query: str = Field(
        min_length=2, max_length=300, description="Public search terms only: names, topics. Never private CRM details."
    )
    news: bool = Field(False, description="Search recent news instead of the general web")
    recent: Literal["day", "week", "month", "year"] | None = None
    country: str | None = Field(
        None,
        max_length=40,
        description="Prefer results from this country, lowercase English name (e.g. 'india'). "
        "Default to the organisation's market for prospect searches.",
    )


async def web_search(ctx: ToolContext, a: WebSearch) -> ToolResult:
    async def go():
        results, _ = await web_research.search(
            ctx.tenant.session,
            ctx.tenant.organization_id,
            ctx.tenant.user_id,
            a.query,
            topic="news" if a.news else "general",
            time_range=a.recent,
            country=a.country,
        )
        return _cite(ctx, results, f"Web: {a.query}")

    return await _run(ctx, go)


class ResearchRecord(BaseModel):
    ref: str = Field(description="Company ref (e.g. c1) or lead ref (e.g. l2)")


async def research_company(ctx: ToolContext, a: ResearchRecord) -> ToolResult:
    company = await records.companies(ctx.tenant).get(ctx.working_set.resolve("company", a.ref))

    async def go():
        results, _ = await web_research.gather(
            ctx.tenant.session, ctx.tenant.organization_id, ctx.tenant.user_id, web_research.company_queries(company)
        )
        return _cite(ctx, results, f"Web research: {company.name}")

    return await _run(ctx, go)


async def research_lead(ctx: ToolContext, a: ResearchRecord) -> ToolResult:
    lead = await records.leads(ctx.tenant).get(ctx.working_set.resolve("lead", a.ref))

    async def go():
        results, _ = await web_research.gather(
            ctx.tenant.session, ctx.tenant.organization_id, ctx.tenant.user_id, web_research.lead_queries(lead)
        )
        return _cite(ctx, results, f"Web research: {lead.company_name}")

    return await _run(ctx, go)


class FindLinkedIn(BaseModel):
    ref: str = Field(description="Company (c1), contact (p1) or lead (l1) ref")


async def find_linkedin(ctx: ToolContext, a: FindLinkedIn) -> ToolResult:
    entry = ctx.working_set.refs.get(a.ref.strip().lower())
    if not entry or entry["type"] not in ("company", "contact", "lead"):
        return ToolResult(summary="Unknown record. Search for the company, contact or lead first.", ok=False)
    kind = entry["type"]

    async def go():
        if kind == "company":
            c = await records.companies(ctx.tenant).get(uuid.UUID(entry["id"]))
            want, query = "company", linkedin.query_for("company", c.name, city=c.city)
        elif kind == "contact":
            p = await records.contacts(ctx.tenant).get(uuid.UUID(entry["id"]))
            company = p.company.name if p.company else None
            want, query = "person", linkedin.query_for("person", p.full_name, company=company, title=p.job_title)
        else:
            lead = await records.leads(ctx.tenant).get(uuid.UUID(entry["id"]))
            want = linkedin.person_or_company(lead.name, lead.company_name)
            query = linkedin.query_for(want, lead.name, company=lead.company_name, title=lead.job_title)
        found = await linkedin.lookup(ctx.tenant.session, ctx.tenant.organization_id, ctx.tenant.user_id, want, query)
        rows = [{"ref": f"li{i + 1}", "title": c.title, "url": c.url, "domain": "linkedin.com",
                 "snippet": c.snippet, "published": None} for i, c in enumerate(found)]
        if not found:
            return ToolResult(summary=f"No public LinkedIn {want} page found for “{query}”.",
                              ui={"kind": "web", "title": "LinkedIn", "rows": []})
        lines = [f"- {c.url} — {c.title}: {c.snippet[:160]}" for c in found]
        return ToolResult(
            summary="Public LinkedIn pages (unverified; confirm with the user before saving with save_linkedin_url):\n"
            + "\n".join(lines),
            ui={"kind": "web", "title": "LinkedIn", "rows": rows},
        )

    return await _run(ctx, go)


WEB_TOOLS: list[Tool] = [
    Tool(
        "web_search",
        "web",
        "Search the public web or recent news. Results are external and unverified.",
        WebSearch,
        web_search,
    ),
    Tool(
        "research_company",
        "web",
        "Web research on a CRM company: what it does and recent news.",
        ResearchRecord,
        research_company,
    ),
    Tool(
        "research_lead",
        "web",
        "Web research on a lead's company (company-level, not the person).",
        ResearchRecord,
        research_lead,
    ),
    Tool(
        "find_linkedin",
        "web",
        "Find the public LinkedIn page of a CRM company, contact or lead (linkedin.com only). "
        "Returns candidates to confirm; save one with save_linkedin_url.",
        FindLinkedIn,
        find_linkedin,
    ),
]
