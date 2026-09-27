"""API keys an organisation brings for AI providers and web search.

The server's own keys (from the environment) still work as a fallback, so a new
organisation can use Meyora before adding keys. An organisation's key always wins.
Values are AES-GCM encrypted at rest and never returned to the browser: only the
last four characters are shown.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import TenantContext
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.errors import NotFound, ValidationFailed
from app.core.logging import get_logger
from app.models import OrganizationApiKey
from app.services.audit import audit

log = get_logger(__name__)
transport: httpx.AsyncBaseTransport | None = None  # tests inject a mock
CACHE_SECONDS = 60


@dataclass(frozen=True)
class KeySpec:
    provider: str
    label: str
    used_for: str
    get_key_url: str
    settings_field: str
    prefix: str | None = None


PROVIDERS: dict[str, KeySpec] = {
    s.provider: s
    for s in (
        KeySpec("groq", "Groq", "The assistant: chat, proposed actions, memory and summaries",
                "https://console.groq.com/keys", "groq_api_key", "gsk_"),
        KeySpec("openrouter", "OpenRouter", "A backup model for the assistant when Groq is busy",
                "https://openrouter.ai/settings/keys", "openrouter_api_key", "sk-or-"),
        KeySpec("gemini", "Google Gemini", "Summaries of public web research (never sees your CRM data)",
                "https://aistudio.google.com/apikey", "gemini_api_key"),
        KeySpec("tavily", "Tavily", "Web search for company and lead research",
                "https://app.tavily.com/home", "tavily_api_key", "tvly-"),
    )
}

# organization_id → (expires_at, {provider: plaintext key})
_cache: dict[uuid.UUID, tuple[float, dict[str, str]]] = {}


def _spec(provider: str) -> KeySpec:
    if provider not in PROVIDERS:
        raise NotFound("Provider")
    return PROVIDERS[provider]


def server_key(provider: str) -> str:
    value = getattr(get_settings(), PROVIDERS[provider].settings_field, None)
    return value.get_secret_value().strip() if value else ""


async def load(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, str]:
    """The organisation's own keys, decrypted. Needs the session's tenant set (RLS)."""
    hit = _cache.get(organization_id)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    rows = await session.scalars(
        select(OrganizationApiKey).where(OrganizationApiKey.organization_id == organization_id)
    )
    keys: dict[str, str] = {}
    for row in rows:
        try:
            keys[row.provider] = decrypt(row.encrypted_value)
        except Exception:  # a rotated ENCRYPTION_KEY makes old values unreadable; treat as unset
            log.warning("api_key_undecryptable", provider=row.provider, organization_id=str(organization_id))
    _cache[organization_id] = (time.monotonic() + CACHE_SECONDS, keys)
    return keys


def invalidate(organization_id: uuid.UUID) -> None:
    _cache.pop(organization_id, None)


async def resolve(session: AsyncSession, organization_id: uuid.UUID, provider: str) -> str:
    return (await load(session, organization_id)).get(provider) or server_key(provider)


async def check(provider: str, value: str) -> bool | None:
    """Ask the provider whether the key works. True / False, or None if it couldn't be checked."""
    requests = {
        "groq": ("GET", "https://api.groq.com/openai/v1/models", None),
        "openrouter": ("GET", "https://openrouter.ai/api/v1/key", None),
        "gemini": ("GET", "https://generativelanguage.googleapis.com/v1beta/openai/models", None),
        "tavily": ("GET", "https://api.tavily.com/usage", None),
    }
    method, url, body = requests[provider]
    try:
        async with httpx.AsyncClient(timeout=12, transport=transport) as client:
            resp = await client.request(method, url, json=body, headers={"Authorization": f"Bearer {value}"})
    except httpx.HTTPError:
        return None
    if resp.status_code in (401, 403):
        return False
    return True if resp.status_code < 300 else None


def _describe(spec: KeySpec, row: OrganizationApiKey | None) -> dict:
    has_server = bool(server_key(spec.provider))
    return {
        "provider": spec.provider,
        "label": spec.label,
        "used_for": spec.used_for,
        "get_key_url": spec.get_key_url,
        "source": "organization" if row else ("server" if has_server else None),
        "last4": row.last4 if row else None,
        "verified_at": row.verified_at if row else None,
        "updated_at": row.updated_at if row else None,
        "updated_by_id": row.updated_by_id if row else None,
    }


async def _rows(ctx: TenantContext) -> dict[str, OrganizationApiKey]:
    rows = await ctx.session.scalars(
        select(OrganizationApiKey).where(OrganizationApiKey.organization_id == ctx.organization_id)
    )
    return {r.provider: r for r in rows}


async def list_keys(ctx: TenantContext) -> list[dict]:
    rows = await _rows(ctx)
    return [_describe(spec, rows.get(p)) for p, spec in PROVIDERS.items()]


async def set_key(ctx: TenantContext, provider: str, value: str) -> dict:
    spec = _spec(provider)
    value = value.strip()
    if len(value) < 16 or any(c.isspace() for c in value):
        raise ValidationFailed(f"That doesn't look like a {spec.label} API key.")
    if spec.prefix and not value.startswith(spec.prefix):
        raise ValidationFailed(f"{spec.label} keys start with “{spec.prefix}”.")
    works = await check(provider, value)
    if works is False:
        raise ValidationFailed(f"{spec.label} rejected this key. Check it was copied in full and is still active.")

    rows = await _rows(ctx)
    row = rows.get(provider)
    old_last4 = row.last4 if row else None
    if row is None:
        row = OrganizationApiKey(organization_id=ctx.organization_id, provider=provider)
        ctx.session.add(row)
    row.encrypted_value = encrypt(value)
    row.last4 = value[-4:]
    row.updated_by_id = ctx.user_id
    row.verified_at = datetime.now(UTC) if works else None
    row.updated_at = datetime.now(UTC)
    await ctx.session.flush()
    # The key itself never goes into the audit log.
    audit(ctx, "api_key.update", entity_type="api_key", entity_id=row.id,
          changes={"provider": {"old": None, "new": provider}, "key": {"old": old_last4 and f"…{old_last4}",
                                                                      "new": f"…{row.last4}"}})
    invalidate(ctx.organization_id)
    return _describe(spec, row)


async def remove_key(ctx: TenantContext, provider: str) -> None:
    spec = _spec(provider)
    row = (await _rows(ctx)).get(provider)
    if row is None:
        raise NotFound(f"{spec.label} key")
    audit(ctx, "api_key.remove", entity_type="api_key", entity_id=row.id,
          changes={"provider": {"old": provider, "new": None}})
    await ctx.session.delete(row)
    await ctx.session.flush()
    invalidate(ctx.organization_id)
