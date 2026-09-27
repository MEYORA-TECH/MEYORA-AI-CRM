"""Settings → API keys. Owner only; values go in, never come back out."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import Field

from app.auth.deps import TenantContext, require
from app.auth.permissions import Perm
from app.schemas.common import InputModel, OutputModel
from app.services import api_keys

router = APIRouter(prefix="/organization/api-keys", tags=["organization"])
Provider = Literal["groq", "openrouter", "gemini", "tavily"]


class ApiKeyOut(OutputModel):
    provider: Provider
    label: str
    used_for: str
    get_key_url: str
    source: Literal["organization", "server"] | None
    last4: str | None
    verified_at: datetime | None
    updated_at: datetime | None
    updated_by_id: uuid.UUID | None


class ApiKeyIn(InputModel):
    value: str = Field(min_length=16, max_length=400)


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(ctx: TenantContext = Depends(require(Perm.ORG_SECRETS))):
    return await api_keys.list_keys(ctx)


@router.put("/{provider}", response_model=ApiKeyOut)
async def set_key(provider: Provider, body: ApiKeyIn, ctx: TenantContext = Depends(require(Perm.ORG_SECRETS))):
    out = await api_keys.set_key(ctx, provider, body.value)
    await ctx.session.commit()
    return out


@router.delete("/{provider}", status_code=204)
async def remove_key(provider: Provider, ctx: TenantContext = Depends(require(Perm.ORG_SECRETS))):
    await api_keys.remove_key(ctx, provider)
    await ctx.session.commit()
    return Response(status_code=204)
