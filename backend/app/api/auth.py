import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, request_meta, token_payload
from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthorized
from app.database.session import get_session
from app.models import User
from app.schemas.auth import (
    AcceptInvitationIn,
    LoginIn,
    MeOut,
    RegisterIn,
    SwitchOrganizationIn,
    TokenOut,
)
from app.services import auth as auth_service
from app.services import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "meyora_rt"
COOKIE_PATH = "/api/auth"


def _require_xhr(request: Request) -> None:
    # Cookie-authenticated endpoints need a header a cross-site form cannot send.
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise Forbidden("Missing X-Requested-With header")


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)


async def _token_response(session, response, user, tokens) -> TokenOut:
    _set_refresh_cookie(response, tokens.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    me = await auth_service.build_me(session, user, tokens.organization_id)
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in, me=me)


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(data: RegisterIn, request: Request, response: Response,
                   session: AsyncSession = Depends(get_session)):
    meta = request_meta(request)
    await rate_limit.hit(f"register:{meta.ip}", limit=10, window_seconds=3600)
    user, tokens = await auth_service.register(session, data, meta)
    return await _token_response(session, response, user, tokens)


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    meta = request_meta(request)
    await rate_limit.hit(f"login:{meta.ip}:{data.email.lower()}",
                         limit=settings.login_rate_limit, window_seconds=settings.login_rate_window_seconds)
    user, tokens = await auth_service.login(session, data.email, data.password, meta)
    return await _token_response(session, response, user, tokens)


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    _require_xhr(request)
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise Unauthorized("Session expired. Please sign in again.")
    meta = request_meta(request)
    await rate_limit.hit(f"refresh:{meta.ip}", limit=120, window_seconds=900)
    user, tokens = await auth_service.refresh(session, raw, meta)
    return await _token_response(session, response, user, tokens)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    _require_xhr(request)
    await auth_service.logout(session, request.cookies.get(REFRESH_COOKIE))
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
async def me(payload: dict = Depends(token_payload), user: User = Depends(get_current_user),
             session: AsyncSession = Depends(get_session)):
    org = payload.get("org")
    return await auth_service.build_me(session, user, uuid.UUID(org) if org else None)


@router.post("/switch-organization", response_model=TokenOut)
async def switch_organization(data: SwitchOrganizationIn, request: Request, response: Response,
                              user: User = Depends(get_current_user),
                              session: AsyncSession = Depends(get_session)):
    _require_xhr(request)
    tokens = await auth_service.switch_organization(
        session, user, data.organization_id, request.cookies.get(REFRESH_COOKIE), request_meta(request)
    )
    return await _token_response(session, response, user, tokens)


@router.post("/accept-invitation", response_model=TokenOut)
async def accept_invitation(data: AcceptInvitationIn, request: Request, response: Response,
                            user: User = Depends(get_current_user),
                            session: AsyncSession = Depends(get_session)):
    _require_xhr(request)
    tokens = await auth_service.accept_invitation(
        session, user, data.token, request_meta(request), request.cookies.get(REFRESH_COOKIE)
    )
    return await _token_response(session, response, user, tokens)
