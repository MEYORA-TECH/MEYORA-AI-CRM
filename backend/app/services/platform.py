"""Installation-wide settings: Google sign-in and Gmail, and the shared AI / web keys.

Platform admins change these in the app. A saved value wins; anything not saved falls
back to the server's environment (.env), so a fresh install works exactly as before.

Saved values are cached in memory and re-read at most every CACHE_SECONDS, so reading a
setting never costs a query; saving clears the cache immediately in this process.
Fallbacks are resolved at read time, so changing the environment (or a test patching
settings) takes effect without touching the cache.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.logging import get_logger
from app.models import PlatformSetting

log = get_logger(__name__)
CACHE_SECONDS = 30

SHARED_KEY_PROVIDERS = ("groq", "openrouter", "gemini", "tavily")
_SECRET_KEYS = {"google_client_secret", *(f"shared_key_{p}" for p in SHARED_KEY_PROVIDERS)}
_KNOWN = {"google_client_id", "google_auth_enabled", "gmail_enabled", *_SECRET_KEYS}

_saved: dict[str, str] = {}
_loaded_at = float("-inf")
_lock = asyncio.Lock()


async def refresh(force: bool = False) -> None:
    """Re-read saved settings if the cache is older than CACHE_SECONDS."""
    global _saved, _loaded_at
    if not force and time.monotonic() - _loaded_at < CACHE_SECONDS:
        return
    async with _lock:
        if not force and time.monotonic() - _loaded_at < CACHE_SECONDS:
            return
        from app.database.session import SessionLocal  # avoid an import cycle at startup

        try:
            async with SessionLocal() as session:
                rows = (await session.scalars(select(PlatformSetting))).all()
            values: dict[str, str] = {}
            for row in rows:
                try:
                    values[row.key] = decrypt(row.value) if row.is_secret else row.value
                except Exception:  # a rotated ENCRYPTION_KEY: treat as not saved
                    log.warning("platform_setting_undecryptable", key=row.key)
            _saved = values
        except Exception:
            log.exception("platform_settings_unavailable")  # keep serving the last known values
        _loaded_at = time.monotonic()


def reset_cache() -> None:
    global _saved, _loaded_at
    _saved, _loaded_at = {}, float("-inf")


def saved(key: str) -> str | None:
    return _saved.get(key)


def _secret_env(value) -> str:
    return value.get_secret_value().strip() if value else ""


def _flag(key: str, default: bool) -> bool:
    value = saved(key)
    return default if value is None else value == "true"


# --- Effective values (saved, else environment) -------------------------------------


def google_client_id() -> str:
    return saved("google_client_id") or (get_settings().google_client_id or "")


def google_client_secret() -> str:
    return saved("google_client_secret") or _secret_env(get_settings().google_client_secret)


def google_ready() -> bool:
    return bool(google_client_id() and google_client_secret())


def google_auth_enabled() -> bool:
    """Sign in with Google is offered: switched on and credentials present."""
    return _flag("google_auth_enabled", get_settings().google_auth_enabled) and google_ready()


def gmail_enabled() -> bool:
    return _flag("gmail_enabled", get_settings().gmail_enabled) and google_ready()


def shared_key(provider: str) -> str:
    """The key every workspace without its own uses for this provider."""
    return saved(f"shared_key_{provider}") or _secret_env(getattr(get_settings(), f"{provider}_api_key", None))


def source(key: str, env_value) -> str | None:
    """Where a setting's value comes from: 'saved', 'server' (environment) or None."""
    if saved(key) is not None:
        return "saved"
    return "server" if env_value not in (None, "", False) else None


# --- Changes (platform admins only; callers check that) ------------------------------


@dataclass
class Change:
    key: str
    value: str | None  # None removes the saved value, falling back to the environment


async def apply(session, changes: list[Change], user_id: uuid.UUID) -> None:
    for c in changes:
        assert c.key in _KNOWN, c.key
        if c.value is None:
            await session.execute(delete(PlatformSetting).where(PlatformSetting.key == c.key))
            continue
        secret = c.key in _SECRET_KEYS
        stored = encrypt(c.value) if secret else c.value
        stmt = insert(PlatformSetting).values(key=c.key, value=stored, is_secret=secret, updated_by_id=user_id)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[PlatformSetting.key],
                set_={
                    "value": stmt.excluded.value,
                    "is_secret": secret,
                    "updated_by_id": user_id,
                    "updated_at": _now(),
                },
            )
        )
    await session.commit()
    # The key never goes to the log, only which setting changed and who changed it.
    log.info("platform_settings_changed", keys=[c.key for c in changes], by=str(user_id))
    await refresh(force=True)
    _invalidate_dependents()


def _now():
    from sqlalchemy import func

    return func.now()


def _invalidate_dependents() -> None:
    from app.ai import registry

    registry.invalidate()
