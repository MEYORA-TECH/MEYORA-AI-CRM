from datetime import UTC, datetime

from app.auth.deps import TenantContext
from app.core.errors import Conflict, ValidationFailed
from app.models import Activity, Lead
from app.models.enums import ActivityType, LeadStatus
from app.schemas.crm import LeadConvertIn
from app.services import deals, records
from app.services.audit import audit
from app.services.crud import check_refs


def _split_name(name: str) -> tuple[str, str | None]:
    first, _, last = name.strip().partition(" ")
    return first, (last.strip() or None)


async def convert(ctx: TenantContext, lead: Lead, opts: LeadConvertIn) -> tuple[Lead, dict]:
    """Turn a lead into company + contact + deal in one transaction."""
    if lead.status == LeadStatus.CONVERTED:
        raise Conflict("This lead has already been converted")
    if not (opts.company_id or opts.create_company or opts.create_contact or opts.create_deal):
        raise ValidationFailed("Nothing to create")

    company_id = opts.company_id
    if company_id:
        await check_refs(ctx, {"company_id": company_id})
    elif opts.create_company and lead.company_name:
        company = await records.companies(ctx).create({
            "name": lead.company_name,
            "industry": lead.industry,
            "owner_id": lead.owner_id,
            "tags": list(lead.tags),
        })
        company_id = company.id

    contact_id = None
    if opts.create_contact:
        first, last = _split_name(lead.name)
        contact = await records.contacts(ctx).create({
            "first_name": first,
            "last_name": last,
            "job_title": lead.job_title,
            "email": lead.email,
            "phone": lead.phone,
            "company_id": company_id,
            "owner_id": lead.owner_id,
            "description": lead.description,
            "tags": list(lead.tags),
        })
        contact_id = contact.id

    deal_id = None
    if opts.create_deal:
        deal_data = {
            "name": opts.deal_name or f"{lead.company_name or lead.name} deal",
            "company_id": company_id,
            "contact_id": contact_id,
            "lead_id": lead.id,
            "owner_id": lead.owner_id or ctx.user_id,
            "source": lead.source,
            "pipeline_id": opts.pipeline_id,
            "stage_id": opts.stage_id,
        }
        if opts.deal_amount is not None:
            deal_data["amount"] = opts.deal_amount
        if opts.deal_currency:
            deal_data["currency"] = opts.deal_currency
        deal = await deals.create_deal(ctx, deal_data)
        deal_id = deal.id

    now = datetime.now(UTC)
    lead.status = LeadStatus.CONVERTED
    lead.converted_at = now
    lead.converted_company_id = company_id
    lead.converted_contact_id = contact_id
    lead.converted_deal_id = deal_id
    ctx.session.add(Activity(
        organization_id=ctx.organization_id,
        type=ActivityType.SYSTEM,
        subject=f"Lead {lead.name} converted",
        occurred_at=now,
        actor_id=ctx.user_id,
        lead_id=lead.id,
        company_id=company_id,
        contact_id=contact_id,
        deal_id=deal_id,
    ))
    await ctx.session.flush()
    result = {"company_id": company_id, "contact_id": contact_id, "deal_id": deal_id}
    audit(ctx, "lead.convert", entity_type="lead", entity_id=lead.id,
          changes={k: {"old": None, "new": v} for k, v in result.items() if v})
    return lead, result
