"""Google OAuth 2.0 / OpenID Connect, done by hand with httpx (no SDK).

Every redirect carries a single-use state (CSRF), a PKCE verifier (code
interception) and a nonce (ID-token replay). ID tokens are verified against
Google's published keys.
"""

import base64
import hashlib
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import OAuthState
from app.services import platform

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}

Purpose = Literal["login", "gmail"]
SCOPES: dict[Purpose, list[str]] = {
    "login": ["openid", "email", "profile"],
    "gmail": [
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",  # only used when the user presses Send on a draft
    ],
}
CALLBACK_PATH: dict[Purpose, str] = {"login": "/api/auth/google/callback", "gmail": "/api/integrations/gmail/callback"}
STATE_TTL = timedelta(minutes=10)

# Tests swap this for httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None
_jwks: dict[str, Any] = {"keys": None, "fetched": 0.0}


class GoogleError(AppError):
    status_code = 400
    code = "google_error"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20, transport=transport)


def redirect_uri(purpose: Purpose) -> str:
    return get_settings().api_url + CALLBACK_PATH[purpose]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


async def begin(
    session: AsyncSession,
    purpose: Purpose,
    *,
    user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    login_hint: str | None = None,
) -> str:
    """Store a pending handshake and return the Google URL to send the browser to."""
    if not platform.google_ready():
        raise GoogleError("Google isn't set up yet. A platform admin can add it in Platform admin → Google & Gmail.")
    state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(16)
    session.add(
        OAuthState(
            state_hash=_hash(state),
            purpose=purpose,
            code_verifier=verifier,
            nonce=nonce,
            user_id=user_id,
            organization_id=organization_id,
            expires_at=datetime.now(UTC) + STATE_TTL,
        )
    )
    params = {
        "client_id": platform.google_client_id(),
        "redirect_uri": redirect_uri(purpose),
        "response_type": "code",
        "scope": " ".join(SCOPES[purpose]),
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    }
    if purpose == "gmail":
        # Offline access + consent so Google returns a refresh token for background sync.
        params |= {"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"}
    else:
        params["prompt"] = "select_account"
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


async def consume_state(session: AsyncSession, raw_state: str | None, purpose: Purpose) -> OAuthState:
    """Single use, unexpired, and for the flow that started it; anything else is rejected."""
    if not raw_state:
        raise GoogleError("The sign-in link is missing its security check. Please try again.")
    row = await session.scalar(select(OAuthState).where(OAuthState.state_hash == _hash(raw_state)).with_for_update())
    if row is None or row.used_at is not None or row.purpose != purpose or row.expires_at < datetime.now(UTC):
        raise GoogleError("This Google sign-in has expired or was already used. Please try again.")
    row.used_at = datetime.now(UTC)
    return row


async def exchange_code(code: str, state: OAuthState) -> dict[str, Any]:
    async with _client() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": platform.google_client_id(),
                "client_secret": platform.google_client_secret(),
                "redirect_uri": redirect_uri(state.purpose),  # type: ignore[arg-type]
                "grant_type": "authorization_code",
                "code_verifier": state.code_verifier,
            },
        )
    if resp.status_code != 200:
        raise GoogleError("Google didn't accept the sign-in. Please try again.")
    return resp.json()


async def _signing_key(kid: str):
    if _jwks["keys"] is None or time.time() - _jwks["fetched"] > 3600 or kid not in _jwks["keys"]:
        async with _client() as client:
            resp = await client.get(CERTS_URL)
        resp.raise_for_status()
        _jwks["keys"] = {k["kid"]: jwt.PyJWK(k).key for k in resp.json()["keys"]}
        _jwks["fetched"] = time.time()
    key = _jwks["keys"].get(kid)
    if key is None:
        raise GoogleError("Couldn't verify Google's response.")
    return key


async def verify_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    try:
        kid = jwt.get_unverified_header(id_token)["kid"]
        claims = jwt.decode(
            id_token,
            await _signing_key(kid),
            algorithms=["RS256"],
            audience=platform.google_client_id(),
            options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            leeway=30,
        )
    except (jwt.PyJWTError, KeyError) as exc:
        raise GoogleError("Couldn't verify Google's response.") from exc
    if claims.get("iss") not in ISSUERS or claims.get("nonce") != nonce:
        raise GoogleError("Couldn't verify Google's response.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise GoogleError("Your Google account's email address isn't verified.")
    return claims


async def refresh_access_token(refresh_token: str) -> str:
    async with _client() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": platform.google_client_id(),
                "client_secret": platform.google_client_secret(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code in (400, 401):
        raise GoogleRevoked()
    resp.raise_for_status()
    return resp.json()["access_token"]


class GoogleRevoked(Exception):
    """The refresh token no longer works (revoked, expired after 7 days in Testing mode, or password change)."""


async def revoke(token: str) -> None:
    async with _client() as client:
        await client.post(REVOKE_URL, data={"token": token})
