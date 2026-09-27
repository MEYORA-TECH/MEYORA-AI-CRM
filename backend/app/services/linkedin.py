"""LinkedIn, within LinkedIn's rules.

LinkedIn's API gives regular developers no access to messages or other people's profiles,
so Meyora doesn't sync anything from LinkedIn. It does two things instead:
- finds a company's or person's *public* LinkedIn page through web search (linkedin.com only),
  for the user to confirm, and
- drafts connection notes and messages that the user sends on LinkedIn themselves
  (see app/ai/actions/linkedin_actions.py), then logs them as LinkedIn activities.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailed
from app.services import web_research

Kind = Literal["company", "person"]

CONNECTION_NOTE_LIMIT = 300  # LinkedIn's limit for a note on a connection request
MESSAGE_LIMIT = 2000

_URL = re.compile(
    r"^https?://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/(?P<section>in|company|school|showcase)/(?P<slug>[^/?#\s]+)",
    re.IGNORECASE,
)


def normalize(url: str) -> tuple[Kind, str] | None:
    """A LinkedIn profile or page URL in one canonical form, or None if it isn't one."""
    m = _URL.match((url or "").strip())
    if not m:
        return None
    section = m["section"].lower()
    kind: Kind = "person" if section == "in" else "company"
    return kind, f"https://www.linkedin.com/{section}/{m['slug']}"


def require(url: str, kind: Kind) -> str:
    """Validate a URL the user or the assistant wants to save; returns the canonical form."""
    parsed = normalize(url)
    if parsed is None:
        raise ValidationFailed("That isn't a LinkedIn profile or company page link.")
    if parsed[0] != kind:
        want = (
            "a person's profile (linkedin.com/in/…)" if kind == "person" else "a company page (linkedin.com/company/…)"
        )
        raise ValidationFailed(f"This record needs {want}.")
    return parsed[1]


@dataclass
class Candidate:
    url: str
    title: str
    snippet: str


def query_for(kind: Kind, name: str, *, company: str | None = None, city: str | None = None,
              title: str | None = None) -> str:
    parts = [name]
    if kind == "person":
        parts += [company or "", title or ""]
    else:
        parts += [city or ""]
    return " ".join(p for p in parts if p).strip()


async def lookup(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    kind: Kind,
    query: str,
) -> list[Candidate]:
    """Public LinkedIn pages matching `query` (one web search credit; cached for a day)."""
    results, _ = await web_research.search(
        session, organization_id, user_id, query, max_results=8, include_domains=["linkedin.com"],
    )
    seen: set[str] = set()
    out: list[Candidate] = []
    for r in results:
        parsed = normalize(r.url)
        if parsed is None or parsed[0] != kind or parsed[1] in seen:
            continue
        seen.add(parsed[1])
        title = re.sub(r"\s*[|·-]\s*LinkedIn\s*$", "", r.title or "").strip()
        out.append(Candidate(url=parsed[1], title=title or parsed[1], snippet=(r.content or "")[:240]))
    return out[:5]


def person_or_company(lead_name: str, company_name: str | None) -> Kind:
    """A lead named after its company (an imported prospect) is looked up as a company."""
    return "company" if company_name and lead_name.strip().lower() == company_name.strip().lower() else "person"
