"""Non-streaming model calls for background work (summaries, memory extraction)."""

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import registry
from app.ai.providers.base import ChatMessage, Completion, ProviderError, TextDelta
from app.jobs.queue import JobDeferred
from app.models import AIUsageLog


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    fallback: bool  # answered by a lower-priority provider


async def complete(
    session: AsyncSession,
    organization_id: uuid.UUID,
    messages: list[ChatMessage],
    *,
    purpose: str,
    user_id: uuid.UUID | None = None,
    json_mode: bool = False,
    max_tokens: int = 600,
) -> LLMResult:
    """Run one fast-model call on CRM data, logging usage. Defers the job if no provider can take it."""
    try:
        candidates = registry.route("crm")
    except registry.NoProviderAvailable as exc:
        raise JobDeferred("no AI provider configured") from exc

    last_error: ProviderError | None = None
    for i, entry in enumerate(candidates):
        model = entry.model_for("fast")
        started = time.perf_counter()
        try:
            parts, final = [], None
            async for ev in entry.provider.stream_chat(
                model=model, messages=messages, tools=[], max_tokens=max_tokens, temperature=0.1, json_mode=json_mode
            ):
                if isinstance(ev, TextDelta):
                    parts.append(ev.text)
                elif isinstance(ev, Completion):
                    final = ev
            usage = final.usage if final else None
            session.add(
                AIUsageLog(
                    organization_id=organization_id,
                    user_id=user_id,
                    provider=entry.id,
                    model=model,
                    purpose=purpose,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                )
            )
            return LLMResult(
                text=(final.text if final else "".join(parts)), provider=entry.id, model=model, fallback=i > 0
            )
        except ProviderError as exc:
            last_error = exc
            session.add(
                AIUsageLog(
                    organization_id=organization_id,
                    user_id=user_id,
                    provider=entry.id,
                    model=model,
                    purpose=purpose,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    status="error",
                    error=exc.message[:300],
                )
            )
    # Every provider refused (usually rate limits): try again later rather than failing the job.
    raise JobDeferred(f"providers unavailable: {last_error.message if last_error else 'unknown'}")


def parse_json(text: str) -> dict[str, Any]:
    """Models sometimes wrap JSON in prose or code fences; take the outermost object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model output is not a JSON object")
    return value
