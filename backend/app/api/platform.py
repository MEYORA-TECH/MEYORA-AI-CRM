"""Platform admin: the whole installation. Only users with is_platform_admin get in."""

import uuid
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import Forbidden, ValidationFailed
from app.database.session import get_session
from app.integrations.google.oauth import redirect_uri
from app.models import User
from app.schemas.common import InputModel, OutputModel
from app.services import api_keys, platform, platform_overview
from app.services.platform import Change

router = APIRouter(prefix="/platform", tags=["platform"])
Source = Literal["saved", "server"] | None
Provider = Literal["groq", "openrouter", "gemini", "tavily"]


async def platform_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_platform_admin:
        raise Forbidden("Only platform admins can open this.")
    return user


# --- Overview (dashboard) --------------------------------------------------------------


class DayTokens(OutputModel):
    day: date
    tokens: int


class ProviderTokens(OutputModel):
    provider: str
    tokens: int


class WorkspaceRow(OutputModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    members: int
    companies: int
    contacts: int
    leads: int
    deals_open: int
    ai_tokens_today: int
    ai_tokens_30d: int
    web_searches_month: int
    mailboxes: int
    last_activity_at: datetime | None


class RecentUser(OutputModel):
    email: str
    full_name: str
    created_at: datetime
    last_login_at: datetime | None


class Health(OutputModel):
    google_ready: bool
    sign_in_live: bool
    gmail_live: bool
    shared_keys: dict[str, bool]


class OverviewOut(OutputModel):
    generated_at: datetime
    environment: str
    db_latency_ms: int
    workspaces: int
    users: int
    active_users_7d: int
    new_users_30d: int
    ai_tokens_today: int
    ai_tokens_30d: int
    ai_daily_quota_per_user: int
    web_searches_month: int
    web_monthly_limit_per_workspace: int
    mailboxes: int
    jobs: dict[str, int]
    failed_jobs_24h: int
    daily_tokens: list[DayTokens]
    providers: list[ProviderTokens]
    workspace_list: list[WorkspaceRow]
    recent_users: list[RecentUser]
    health: Health


@router.get("/overview", response_model=OverviewOut)
async def overview(
    tz: str = Query("Asia/Kolkata", max_length=64),
    _: User = Depends(platform_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailed("Unknown time zone") from exc
    return await platform_overview.build(session, tz, datetime.now(zone).date())


# --- Settings: Google & Gmail, shared keys -------------------------------------------------


class GoogleOut(OutputModel):
    client_id: str | None
    client_id_source: Source
    secret_set: bool
    secret_last4: str | None
    secret_source: Source
    sign_in_switch: bool
    sign_in_source: Source
    gmail_switch: bool
    gmail_source: Source
    ready: bool  # client ID and secret both present
    sign_in_live: bool
    gmail_live: bool
    redirect_uris: dict[str, str]
    javascript_origin: str


class SharedKeyOut(OutputModel):
    provider: Provider
    label: str
    used_for: str
    get_key_url: str
    source: Source
    last4: str | None


class SettingsOut(OutputModel):
    google: GoogleOut
    keys: list[SharedKeyOut]


def _switch(key: str, env: bool) -> bool:
    value = platform.saved(key)
    return env if value is None else value == "true"


def _settings_out() -> SettingsOut:
    s = get_settings()
    secret = platform.google_client_secret()
    env_secret = s.google_client_secret.get_secret_value() if s.google_client_secret else ""
    keys = []
    for p in platform.SHARED_KEY_PROVIDERS:
        spec = api_keys.PROVIDERS[p]
        value = platform.shared_key(p)
        env_value = getattr(s, f"{p}_api_key", None)
        keys.append(SharedKeyOut(
            provider=p, label=spec.label, used_for=spec.used_for, get_key_url=spec.get_key_url,
            source=platform.source(f"shared_key_{p}", env_value.get_secret_value() if env_value else None),
            last4=value[-4:] if value else None,
        ))
    return SettingsOut(
        google=GoogleOut(
            client_id=platform.google_client_id() or None,
            client_id_source=platform.source("google_client_id", s.google_client_id),
            secret_set=bool(secret),
            secret_last4=secret[-4:] if secret else None,
            secret_source=platform.source("google_client_secret", env_secret),
            sign_in_switch=_switch("google_auth_enabled", s.google_auth_enabled),
            sign_in_source=platform.source("google_auth_enabled", s.google_auth_enabled),
            gmail_switch=_switch("gmail_enabled", s.gmail_enabled),
            gmail_source=platform.source("gmail_enabled", s.gmail_enabled),
            ready=platform.google_ready(),
            sign_in_live=platform.google_auth_enabled(),
            gmail_live=platform.gmail_enabled(),
            redirect_uris={"sign_in": redirect_uri("login"), "gmail": redirect_uri("gmail")},
            javascript_origin=s.public_url.rstrip("/"),
        ),
        keys=keys,
    )


@router.get("/settings", response_model=SettingsOut)
async def get_platform_settings(_: User = Depends(platform_admin)):
    await platform.refresh(force=True)
    return _settings_out()


class GoogleIn(InputModel):
    """Only the fields sent are changed. null clears a saved value (back to the server's)."""

    client_id: str | None = Field(None, max_length=200)
    client_secret: str | None = Field(None, max_length=200)
    sign_in_enabled: bool | None = None
    gmail_enabled: bool | None = None


@router.put("/google", response_model=SettingsOut)
async def update_google(
    body: GoogleIn, user: User = Depends(platform_admin), session: AsyncSession = Depends(get_session)
):
    sent = body.model_fields_set
    changes: list[Change] = []
    if "client_id" in sent:
        cid = (body.client_id or "").strip()
        if cid and not cid.endswith(".apps.googleusercontent.com"):
            raise ValidationFailed("A Google OAuth client ID ends with “.apps.googleusercontent.com”.")
        changes.append(Change("google_client_id", cid or None))
    if "client_secret" in sent:
        secret = (body.client_secret or "").strip()
        if secret and (len(secret) < 20 or any(c.isspace() for c in secret)):
            raise ValidationFailed("That doesn't look like a Google OAuth client secret.")
        changes.append(Change("google_client_secret", secret or None))
    for field, key in (("sign_in_enabled", "google_auth_enabled"), ("gmail_enabled", "gmail_enabled")):
        if field in sent:
            value = getattr(body, field)
            changes.append(Change(key, None if value is None else ("true" if value else "false")))
    if changes:
        await platform.apply(session, changes, user.id)
    return _settings_out()


class KeyIn(InputModel):
    value: str = Field(min_length=16, max_length=400)


@router.put("/keys/{provider}", response_model=SettingsOut)
async def set_shared_key(
    provider: Provider, body: KeyIn, user: User = Depends(platform_admin), session: AsyncSession = Depends(get_session)
):
    spec = api_keys.PROVIDERS[provider]
    value = body.value.strip()
    if spec.prefix and not value.startswith(spec.prefix):
        raise ValidationFailed(f"{spec.label} keys start with “{spec.prefix}”.")
    if await api_keys.check(provider, value) is False:
        raise ValidationFailed(f"{spec.label} rejected this key. Check it was copied in full and is still active.")
    await platform.apply(session, [Change(f"shared_key_{provider}", value)], user.id)
    return _settings_out()


@router.delete("/keys/{provider}", status_code=204)
async def remove_shared_key(
    provider: Provider, user: User = Depends(platform_admin), session: AsyncSession = Depends(get_session)
) -> Response:
    await platform.apply(session, [Change(f"shared_key_{provider}", None)], user.id)
    return Response(status_code=204)

