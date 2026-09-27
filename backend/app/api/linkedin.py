"""Find a record's public LinkedIn page (web search limited to linkedin.com)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.schemas.common import OutputModel
from app.services import linkedin, records

router = APIRouter(prefix="/linkedin", tags=["linkedin"])


class CandidateOut(OutputModel):
    url: str
    title: str
    snippet: str


class LookupOut(OutputModel):
    kind: Literal["company", "person"]
    query: str
    candidates: list[CandidateOut]


@router.get("/lookup/{entity}/{entity_id}", response_model=LookupOut)
async def lookup(
    entity: Literal["companies", "contacts", "leads"],
    entity_id: uuid.UUID,
    ctx: TenantContext = Depends(require(Perm.CRM_WRITE)),  # it spends a web search credit
):
    if entity == "companies":
        c = await records.companies(ctx).get(entity_id)
        kind, query = "company", linkedin.query_for("company", c.name, city=c.city)
    elif entity == "contacts":
        p = await records.contacts(ctx).get(entity_id)
        kind = "person"
        company = p.company.name if p.company else None
        query = linkedin.query_for("person", p.full_name, company=company, title=p.job_title)
    else:
        lead = await records.leads(ctx).get(entity_id)
        kind = linkedin.person_or_company(lead.name, lead.company_name)
        query = linkedin.query_for(kind, lead.name, company=lead.company_name, title=lead.job_title)
    found = await linkedin.lookup(ctx.session, ctx.organization_id, ctx.user_id, kind, query)
    await ctx.session.commit()  # keep the search log and cache
    return LookupOut(kind=kind, query=query, candidates=[CandidateOut(**c.__dict__) for c in found])
