"""Import Meyora's prospecting spreadsheets into a new "Meyora" organisation.

    python -m scripts.import_meyora_sheets --owner-email you@example.com \
        --workbook "MEYORA (1).xlsx" --new-leads MEYORA_ALL_165_COMPANIES.xlsx [--commit]

Without --commit it only prints what it would import. With --commit it creates
the organisation (default pipeline, INR), imports everything in one transaction
through the app's database role (so row-level security applies), queues AI
indexing, and prints a one-time owner invite link. The owner sets their own
password on that link.

Mapping
  Companies sheets → companies (prospect). Firmographics in columns, the rest
                     (Meyora ID, size band, LinkedIn, fit score, …) in custom fields.
                     Same-name rows are merged.
  Every prospect   → a lead (score = fit score) named after its best contact.
                     Associations / industrial estates are outreach partners, not leads.
  Contacts sheet   → contacts. Generic inboxes ("Company / Office") become the
                     company's email instead. "#ERROR!"/"—" phones are dropped.
  Research sheet,
  Notes column     → notes on the company and its lead, dated by research date.
  Empty sheets (Pipeline, Outreach, Interactions) and summaries are skipped.
"""

import argparse
import asyncio
import os
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import openpyxl
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
PLACEHOLDERS = {"", "—", "-", "–", "website", "linkedin", "#error!", "none", "n/a", "na", "public site masks mobile"}
PARTNER_SEGMENTS = {"Association", "Government"}
PRIORITY_TAG = {"Hot": "Hot", "High": "High priority", "Medium": "Medium priority", "Low": "Low priority"}

# Chennai's industrial suburbs roll up to Chennai; the rest are their own towns.
CITY_ALIASES = [
    (("sriperumbudur", "sipcot", "oragadam"), "Sriperumbudur"),
    (("coimbatore",), "Coimbatore"),
    (("tiruppur",), "Tiruppur"),
    (("hosur",), "Hosur"),
    (("kancheepuram",), "Kancheepuram"),
    (("tiruvallur",), "Tiruvallur"),
    (("vellore",), "Vellore"),
    (
        ("chennai", "ambattur", "guindy", "sidco", "anna nagar", "poonamallee", "gummidipoondi", "thirumudivakkam"),
        "Chennai",
    ),
]


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return None if text.lower() in PLACEHOLDERS else text


def clean_url(value: Any) -> str | None:
    text = clean(value)
    if not text or "." not in text or " " in text:
        return None
    return text if re.match(r"https?://", text) else f"https://{text}"


def clean_phone(value: Any) -> str | None:
    text = clean(value)
    return text if text and len(re.sub(r"\D", "", text)) >= 8 else None


def clean_email(value: Any) -> str | None:
    text = clean(value)
    return text.lower() if text and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text) else None


def city_of(location: str | None) -> str | None:
    low = (location or "").lower()
    # "Chennai / Sriperumbudur" → the first place named wins
    hits = [(low.find(k), city) for keys, city in CITY_ALIASES for k in keys if k in low]
    return min(hits)[1] if hits else None


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def name_key(name: str) -> str:
    base = re.sub(r"\b(pvt|private|ltd|limited|llp|co)\b\.?", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", base)


def split_name(full: str) -> tuple[str, str | None]:
    parts = full.split()
    return (parts[0], None) if len(parts) == 1 else (" ".join(parts[:-1]), parts[-1])


def read_sheet(path: Path, name: str) -> list[dict[str, Any]]:
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[name]
    rows = [r for r in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in r)]
    head = [h for h in rows[0] if h is not None]
    return [dict(zip(head, r, strict=False)) for r in rows[1:] if any(v not in (None, "", 0) for v in r[: len(head)])]


# --- Plan -------------------------------------------------------------------------


@dataclass
class Prospect:
    ids: list[str]
    name: str
    fields: dict[str, Any]
    custom: dict[str, Any]
    tags: list[str]
    fit: int
    source: str | None
    partner: bool
    research_date: date | None
    notes: list[tuple[date | None, str]] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)
    lead: dict[str, Any] | None = None


def _source(raw: Any) -> str | None:
    text = clean(raw)
    return re.sub(r"\s*\((LinkedIn)\)$", "", text) if text else None


def plan(workbook: Path, new_leads: Path) -> tuple[list[Prospect], dict[str, int]]:
    rows = read_sheet(workbook, "Companies") + read_sheet(new_leads, "NEW 66 LEADS")
    stats: dict[str, int] = defaultdict(int)
    stats["company rows"] = len(rows)
    by_key: dict[str, Prospect] = {}
    by_id: dict[str, Prospect] = {}

    for r in rows:
        name = clean(r["Company Name"])
        if not name:
            continue
        location = clean(r["Location"])
        city = city_of(location)
        segment = clean(r["ICP Segment"])
        priority = clean(r["Priority"])
        fit = int(float(r["Fit Score (0-100)"] or 0))
        linkedin = clean_url(r["LinkedIn URL"])
        tags = [t for t in (segment, PRIORITY_TAG.get(priority or "")) if t]
        partner = segment in PARTNER_SEGMENTS
        if partner:
            tags.append("Outreach partner")
        custom = {
            "Meyora ID": r["Company ID"],
            "Company size": clean(r["Company Size"]),
            "LinkedIn": linkedin,
            "Fit score": fit,
            "Priority": priority,
            "ICP segment": segment,
            "Tech / software clues": clean(r["Tech/Software Clues"]),
            "Source": _source(r["Source"]),
            "Research date": str(as_date(r["Research Date"]) or "") or None,
        }
        p = Prospect(
            ids=[r["Company ID"]],
            name=name,
            fields={
                "name": name,
                "industry": clean(r["Industry"]),
                "website": clean_url(r["Website"]),
                "address": location if location and location != city else None,
                "city": city,
                "state": "Tamil Nadu" if city else None,
                "country": "India",
                "description": clean(r["Business Description"]),
            },
            custom={k: v for k, v in custom.items() if v not in (None, "")},
            tags=tags,
            fit=fit,
            source=_source(r["Source"]),
            partner=partner,
            research_date=as_date(r["Research Date"]),
        )
        if note := clean(r["Notes"]):
            p.notes.append((p.research_date, f"**Research note**\n\n{note}"))

        key = name_key(name)
        if key in by_key:  # same company listed twice: keep the higher-fit row, merge the rest in
            stats["merged duplicates"] += 1
            kept = by_key[key]
            if p.fit > kept.fit:
                p.ids, p.notes = kept.ids + p.ids, kept.notes + p.notes
                for k, v in kept.fields.items():
                    p.fields[k] = p.fields.get(k) or v
                p.custom = {**kept.custom, **p.custom}
                kept = by_key[key] = p
            else:
                kept.ids += p.ids
                kept.notes += p.notes
                for k, v in p.fields.items():
                    kept.fields[k] = kept.fields.get(k) or v
                kept.custom = {**p.custom, **kept.custom}
            kept.custom["Meyora ID"] = ", ".join(kept.ids)
            for i in kept.ids:
                by_id[i] = kept
        else:
            by_key[key] = p
            by_id[r["Company ID"]] = p

    for c in read_sheet(workbook, "Contacts"):
        p = by_id.get(c["Company ID"])
        if p is None:
            stats["contacts with unknown company"] += 1
            continue
        who = clean(c["Contact Name / Contact Point"]) or ""
        email = clean_email(c["Email"])
        if who.lower().startswith("company"):  # a shared inbox, not a person
            if email and not p.fields.get("email"):
                p.fields["email"] = email
            elif email and email != p.fields.get("email"):
                others = p.custom.get("Other emails")
                p.custom["Other emails"] = f"{others}, {email}" if others else email
            stats["generic inboxes → company email"] += 1
            continue
        first, last = split_name(who)
        decision = clean(c.get("Decision Maker?"))
        p.contacts.append(
            {
                "first_name": first,
                "last_name": last,
                "job_title": clean(c["Job Title / Department"]),
                "email": email,
                "phone": clean_phone(c["Phone"]),
                "description": f"Source: {clean(c.get('Source / verification')) or 'spreadsheet'}",
                "tags": ["Decision maker"]
                if decision == "Yes"
                else ["Possible decision maker"]
                if decision == "Potential"
                else [],
                "custom_fields": {"Meyora ID": c["Contact ID"], "Decision maker?": decision},
            }
        )
        if clean(c["Phone"]) and not clean_phone(c["Phone"]):
            stats["unusable phone numbers dropped"] += 1

    for r in read_sheet(workbook, "Research"):
        p = by_id.get(r["Company ID"])
        if p is None:
            stats["research with unknown company"] += 1
            continue
        scores = " · ".join(
            f"{label} {int(float(r[col]))}/5"
            for label, col in (
                ("Pain", "Pain Severity (1-5)"),
                ("Urgency", "Urgency (1-5)"),
                ("Budget", "Budget Potential (1-5)"),
                ("Fit", "Strategic Fit (1-5)"),
            )
            if r.get(col) is not None
        )
        lines = [
            ("Problem / opportunity", clean(r["Problem / Opportunity"])),
            ("Current process", clean(r["Current Process"])),
            ("Possible Meyora solution", clean(r["Potential Meyora Solution"])),
            ("Evidence", clean(r["Evidence / Source"])),
            ("Scores", f"{scores} · Overall {r['Overall Opportunity Score']}" if scores else None),
            ("Caution", clean(r["Notes"])),
        ]
        body = "\n\n".join(["**Opportunity research**"] + [f"**{k}:** {v}" for k, v in lines if v])
        p.notes.append((as_date(r["Date"]) or p.research_date, body))
        if r.get("Overall Opportunity Score") is not None:
            p.custom["Opportunity score"] = int(float(r["Overall Opportunity Score"]))

    prospects = list(by_key.values())
    for p in prospects:
        if p.partner:
            continue
        people = sorted(p.contacts, key=lambda c: "Decision maker" not in c["tags"])
        best = people[0] if people else None
        p.lead = {
            "name": f"{best['first_name']} {best['last_name'] or ''}".strip() if best else p.name,
            "company_name": p.name,
            "job_title": best["job_title"] if best else None,
            "email": best["email"] if best else p.fields.get("email"),
            "phone": best["phone"] if best else None,
            "source": p.source,
            "industry": p.fields["industry"],
            "score": max(0, min(100, p.fit)),
            "description": "\n\n".join(x for x in (p.fields["description"], p.custom.get("Tech / software clues")) if x)
            or None,
            "tags": [t for t in p.tags if t != "Outreach partner"],
            "custom_fields": {
                k: p.custom[k] for k in ("Meyora ID", "ICP segment", "Priority", "Company size") if k in p.custom
            },
        }

    stats["companies"] = len(prospects)
    stats["outreach partners (no lead)"] = sum(p.partner for p in prospects)
    stats["leads"] = sum(p.lead is not None for p in prospects)
    stats["contacts"] = sum(len(p.contacts) for p in prospects)
    stats["notes"] = sum(len(p.notes) for p in prospects)
    return prospects, dict(stats)


# --- Write ------------------------------------------------------------------------


async def write(
    prospects: list[Prospect], stats: dict[str, int], org_name: str, owner_email: str, public_url: str
) -> str:
    from sqlalchemy import func, select

    from app.auth.permissions import Role
    from app.auth.security import hash_token, new_opaque_token
    from app.database.session import SessionLocal, engine, set_tenant
    from app.jobs.queue import enqueue
    from app.models import Company, Contact, Invitation, Lead, Note, Organization
    from app.models.enums import ActorType, CompanyStatus, LeadStatus
    from app.services.audit import add_audit
    from app.services.auth import _slugify
    from app.services.pipelines import build_default_pipeline

    async with SessionLocal() as session:
        existing = await session.scalar(select(func.count(Organization.id)).where(Organization.name == org_name))
        if existing:
            sys.exit(f'An organisation called "{org_name}" already exists; nothing was imported.')

        org = Organization(name=org_name, slug=_slugify(org_name), default_currency="INR")
        session.add(org)
        await session.flush()
        await set_tenant(session, org.id)
        session.add(build_default_pipeline(org.id))

        raw_token = new_opaque_token()
        session.add(
            Invitation(
                organization_id=org.id,
                email=owner_email.lower(),
                role=Role.OWNER,
                token_hash=hash_token(raw_token),
                invited_by_id=None,
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )

        indexed: list[tuple[str, uuid.UUID]] = []

        def at(d: date | None) -> datetime | None:
            return datetime(d.year, d.month, d.day, 10, tzinfo=UTC) if d else None

        for p in prospects:
            company = Company(
                organization_id=org.id, status=CompanyStatus.PROSPECT, tags=p.tags, custom_fields=p.custom, **p.fields
            )
            session.add(company)
            await session.flush()
            indexed.append(("company", company.id))
            for c in p.contacts:
                contact = Contact(organization_id=org.id, company_id=company.id, **c)
                session.add(contact)
                await session.flush()
                indexed.append(("contact", contact.id))
            lead_id = None
            if p.lead:
                lead = Lead(organization_id=org.id, status=LeadStatus.NEW, **p.lead)
                session.add(lead)
                await session.flush()
                lead_id = lead.id
                indexed.append(("lead", lead.id))
            for when, body in p.notes:
                note = Note(organization_id=org.id, company_id=company.id, lead_id=lead_id, body=body)
                if when:
                    note.created_at = note.updated_at = at(when)
                session.add(note)
                await session.flush()
                indexed.append(("note", note.id))

        for kind, record_id in indexed:  # so the assistant can find them by meaning
            await enqueue(
                session, "index_record", org.id, {"kind": kind, "id": str(record_id)}, dedupe_key=f"{kind}:{record_id}"
            )
        add_audit(
            session,
            organization_id=org.id,
            action="import.spreadsheets",
            actor_user_id=None,
            meta=None,
            actor_type=ActorType.SYSTEM,
            entity_type="organization",
            entity_id=org.id,
            changes={k: {"old": None, "new": v} for k, v in stats.items()},
        )
        await session.commit()
    await engine.dispose()
    return f"{public_url.rstrip('/')}/register?invite={raw_token}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--workbook", type=Path, required=True, help="The master CRM workbook (Companies/Contacts/Research)"
    )
    parser.add_argument("--new-leads", type=Path, required=True, help="The workbook with the 'NEW 66 LEADS' sheet")
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--org-name", default="Meyora")
    parser.add_argument("--env-file", type=Path, default=BACKEND.parent / ".env")
    parser.add_argument("--public-url", default=None, help="Where the web app runs (defaults to PUBLIC_URL)")
    parser.add_argument("--commit", action="store_true", help="Write to the database (default: dry run)")
    args = parser.parse_args()

    prospects, stats = plan(args.workbook, args.new_leads)
    print("Import plan:")
    for k, v in stats.items():
        print(f"  {k:<34} {v}")
    sample = next(p for p in prospects if p.contacts and len(p.notes) > 1)
    print(
        f"\nExample: {sample.name} ({', '.join(sample.ids)}) → {sample.fields['city']}, tags {sample.tags}, "
        f"lead '{sample.lead['name'] if sample.lead else '-'}' score {sample.fit}, "
        f"{len(sample.contacts)} contacts, {len(sample.notes)} notes"
    )
    if not args.commit:
        print("\nDry run only. Re-run with --commit to import.")
        return

    env = dotenv_values(args.env_file)
    app_url = env.get("NEON_APP_DATABASE_URL")
    if not app_url:
        sys.exit("NEON_APP_DATABASE_URL is missing; run scripts.setup_database first.")
    # Import through the app's role (not the owner) so row-level security applies to every insert.
    os.environ["DATABASE_URL"] = app_url
    os.environ["DB_STATEMENT_CACHE_SIZE"] = "0"  # Neon's pooler
    link = asyncio.run(
        write(
            prospects,
            stats,
            args.org_name,
            args.owner_email,
            args.public_url or env.get("PUBLIC_URL") or "http://localhost:5173",
        )
    )
    print(f'\nImported into "{args.org_name}". Owner invite (valid 7 days, open it once):\n{link}')


if __name__ == "__main__":
    main()
