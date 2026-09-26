"""Decide whether an email belongs in the CRM, and which records it concerns."""

import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Contact

# Personal mailbox domains say nothing about which company someone works for.
FREE_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "rediffmail.com",
    "zoho.com",
    "yandex.com",
}


@dataclass
class Match:
    contact_ids: list[uuid.UUID] = field(default_factory=list)
    company_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def relevant(self) -> bool:
        return bool(self.contact_ids or self.company_ids)


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower().strip()


def company_domains(company: Company) -> set[str]:
    domains = set()
    if company.email and "@" in company.email:
        domains.add(domain_of(company.email))
    if company.website:
        host = urlparse(company.website if "//" in company.website else f"//{company.website}").hostname or ""
        if host:
            domains.add(host.lower().removeprefix("www."))
    return domains - FREE_DOMAINS


async def match(session: AsyncSession, organization_id: uuid.UUID, emails: list[str], *, own_email: str) -> Match:
    """Contacts by exact address; companies by domain (and through their contacts)."""
    emails = sorted({e.lower() for e in emails if e and e.lower() != own_email.lower()})
    if not emails:
        return Match()
    contacts = list(
        await session.scalars(
            select(Contact).where(
                Contact.organization_id == organization_id,
                Contact.deleted_at.is_(None),
                func.lower(Contact.email).in_(emails),
            )
        )
    )
    domains = {domain_of(e) for e in emails} - FREE_DOMAINS - {domain_of(own_email)}
    companies: list[Company] = []
    if domains:
        candidates = await session.scalars(
            select(Company).where(
                Company.organization_id == organization_id,
                Company.deleted_at.is_(None),
                or_(
                    *[Company.email.ilike(f"%@{d}") for d in domains],
                    *[Company.website.ilike(f"%{d}%") for d in domains],
                ),
            )
        )
        companies = [c for c in candidates if company_domains(c) & domains]
    company_ids = {c.id for c in companies} | {c.company_id for c in contacts if c.company_id}
    return Match(contact_ids=[c.id for c in contacts], company_ids=sorted(company_ids))
