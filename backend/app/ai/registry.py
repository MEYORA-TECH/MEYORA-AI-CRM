"""The provider pool and the privacy guardrail.

Every AI request declares what it carries:
  - "crm":    organization data (records, emails, notes). Only `trusted` providers.
  - "public": nothing private (e.g. summarising a public web page). Any provider.

`route()` is the only way to obtain a provider, so the guardrail cannot be bypassed.
"""

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from app.ai.providers.base import AIProvider
from app.ai.providers.openai_compat import OpenAICompatibleProvider
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

DataClass = Literal["crm", "public"]
Privacy = Literal["trusted", "public_only"]
Purpose = Literal["chat", "fast"]


@dataclass
class ProviderEntry:
    id: str
    label: str
    privacy: Privacy
    chat_model: str
    fast_model: str
    context_window: int
    provider: AIProvider
    priority: int = 100
    # Request options for background work (e.g. less reasoning so JSON fits the output limit).
    background_extra: dict[str, Any] = field(default_factory=dict)
    environments: set[str] = field(default_factory=lambda: {"development", "test", "production"})

    def model_for(self, purpose: Purpose) -> str:
        return self.chat_model if purpose == "chat" else self.fast_model


class NoProviderAvailable(Exception):
    pass


def _secret(value) -> str:
    return value.get_secret_value().strip() if value else ""


def _build_pool() -> list[ProviderEntry]:
    s = get_settings()
    pool: list[ProviderEntry] = []

    if groq_key := _secret(s.groq_api_key):
        pool.append(
            ProviderEntry(
                id="groq",
                label="Groq",
                privacy="trusted",
                priority=10,
                chat_model=s.groq_chat_model,
                fast_model=s.groq_fast_model,
                context_window=131_072,
                background_extra={"reasoning_effort": "low"},  # gpt-oss reasons before answering
                provider=OpenAICompatibleProvider(
                    id="groq", base_url="https://api.groq.com/openai/v1", api_key=groq_key
                ),
            )
        )

    if (openrouter_key := _secret(s.openrouter_api_key)) and s.openrouter_chat_model:
        # Only providers that don't collect prompts, so CRM data may use it.
        pool.append(
            ProviderEntry(
                id="openrouter",
                label="OpenRouter",
                privacy="trusted",
                priority=20,
                chat_model=s.openrouter_chat_model,
                fast_model=s.openrouter_chat_model,
                context_window=32_768,
                provider=OpenAICompatibleProvider(
                    id="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_key,
                    extra_body={"provider": {"data_collection": "deny"}},
                ),
            )
        )

    for raw in json.loads(s.ai_extra_providers or "[]"):
        pool.append(_from_config(raw))

    return sorted((p for p in pool if s.app_env in p.environments), key=lambda p: p.priority)


def _from_config(raw: dict[str, Any]) -> ProviderEntry:
    key = os.environ.get(raw["api_key_env"], "")
    if raw.get("privacy") not in ("trusted", "public_only"):
        raise ValueError(f"Provider {raw.get('id')}: privacy must be 'trusted' or 'public_only'")
    return ProviderEntry(
        id=raw["id"],
        label=raw.get("label", raw["id"]),
        privacy=raw["privacy"],
        chat_model=raw["chat_model"],
        fast_model=raw.get("fast_model", raw["chat_model"]),
        context_window=int(raw.get("context_window", 32_768)),
        priority=int(raw.get("priority", 100)),
        environments=set(raw.get("environments", ["development", "test", "production"])),
        provider=OpenAICompatibleProvider(
            id=raw["id"], base_url=raw["base_url"], api_key=key, extra_body=raw.get("extra_body")
        ),
    )


@lru_cache
def pool() -> list[ProviderEntry]:
    entries = _build_pool()
    log.info("ai_provider_pool", providers=[(p.id, p.privacy) for p in entries])
    return entries


def route(
    data_class: DataClass, *, prefer: str | None = None, entries: list[ProviderEntry] | None = None
) -> list[ProviderEntry]:
    """Candidates allowed for this data, best first. `prefer` pins a conversation's provider."""
    allowed = [
        p for p in (entries if entries is not None else pool()) if data_class == "public" or p.privacy == "trusted"
    ]
    if prefer:
        allowed.sort(key=lambda p: (p.id != prefer, p.priority))
    if not allowed:
        raise NoProviderAvailable("No AI provider is configured for this kind of request.")
    return allowed


def is_configured() -> bool:
    return any(p.privacy == "trusted" for p in pool())
