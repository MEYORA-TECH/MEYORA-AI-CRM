"""The agent loop: model → tools → model, streamed as events.

Provider failover happens only before the first token of a turn, so one answer
never mixes two models. Tool arguments are validated before anything runs.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.ai.providers.base import (
    ChatMessage,
    Completion,
    ProviderError,
    ProviderRateLimited,
    ProviderToolCallInvalid,
    TextDelta,
    ToolCall,
    Usage,
)
from app.ai.registry import ProviderEntry
from app.ai.tools.base import Tool, ToolContext
from app.core.logging import get_logger

log = get_logger("ai.agent")

# Short provider waits (e.g. Groq "retry in 4s") are absorbed instead of failing the answer.
MAX_SHORT_WAITS = 2
MAX_WAIT_SECONDS = 35.0  # Groq free tier: 8K tokens/minute; one multi-step answer can need a pause
# The provider sometimes rejects the model's own tool call (missing argument); one retry usually fixes it.
MAX_TOOL_CALL_RETRIES = 1


@dataclass
class ModelCall:
    provider: str
    model: str
    latency_ms: int
    usage: Usage
    tool_calls: list[str]
    status: str = "ok"
    error: str | None = None


@dataclass
class TurnRecord:
    """Everything the service persists after a turn."""

    provider: ProviderEntry | None = None
    text: str = ""
    tool_messages: list[dict[str, Any]] = field(default_factory=list)  # assistant tool_calls + tool results, in order
    calls: list[ModelCall] = field(default_factory=list)
    error: str | None = None


def estimate_tokens(messages: list[ChatMessage]) -> int:
    """Rough (chars/4) estimate used only for budgeting; real usage comes back from the provider."""
    chars = sum(len(m.content or "") + sum(len(c.arguments) + len(c.name) for c in m.tool_calls) for m in messages)
    return chars // 4 + 4 * len(messages)


async def run_turn(
    *,
    candidates: list[ProviderEntry],
    messages: list[ChatMessage],
    tools: list[Tool],
    tool_ctx: ToolContext,
    record: TurnRecord,
    max_model_calls: int,
    max_output_tokens: int = 1024,
) -> AsyncIterator[dict[str, Any]]:
    specs = [t.spec() for t in tools]
    by_name = {t.name: t for t in tools}
    streamed_any = False

    for call_no in range(max_model_calls):
        last_call = call_no == max_model_calls - 1
        completion: Completion | None = None

        # Try providers in order until one starts answering.
        pool = [record.provider] if record.provider else candidates
        for entry in pool:
            failure: ProviderError | None = None
            hint: ChatMessage | None = None
            waits = tool_retries = 0
            while True:
                started = time.perf_counter()
                call_streamed = False
                try:
                    async for event in entry.provider.stream_chat(
                        model=entry.chat_model,
                        messages=messages + [hint] if hint else messages,
                        tools=specs,
                        tool_choice="none" if last_call else "auto",
                        max_tokens=max_output_tokens,
                    ):
                        if isinstance(event, TextDelta):
                            streamed_any = call_streamed = True
                            yield {"type": "token", "text": event.text}
                        else:
                            completion = event
                    failure = None
                    break
                except ProviderError as exc:
                    failure = exc
                    record.calls.append(
                        ModelCall(
                            provider=entry.id,
                            model=entry.chat_model,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            usage=Usage(),
                            tool_calls=[],
                            status="rate_limited" if isinstance(exc, ProviderRateLimited) else "error",
                            error=exc.message[:300],
                        )
                    )
                    log.warning("ai_provider_failed", provider=entry.id, status=exc.status, error=exc.message)
                    if (
                        isinstance(exc, ProviderToolCallInvalid)
                        and not call_streamed
                        and tool_retries < MAX_TOOL_CALL_RETRIES
                    ):
                        tool_retries += 1
                        hint = ChatMessage(
                            role="system",
                            content=f"Your last tool call was rejected: {exc.detail[:200]}. "
                            "Call the tool again with every required argument filled in.",
                        )
                        continue
                    # Free tiers limit tokens per minute; a short pause mid-answer is better than failing it.
                    wait = exc.retry_after if isinstance(exc, ProviderRateLimited) else None
                    # Only wait if there's nobody better: a pinned provider mid-answer, or the last candidate.
                    no_alternative = record.provider is not None or entry is pool[-1]
                    if (
                        wait is not None
                        and wait <= MAX_WAIT_SECONDS
                        and no_alternative
                        and not call_streamed
                        and waits < MAX_SHORT_WAITS
                    ):
                        waits += 1
                        yield {
                            "type": "status",
                            "message": f"Waiting {int(wait) + 1}s for the AI provider's free-tier limit…",
                        }
                        await asyncio.sleep(wait + 0.5)
                        continue
                    break

            if failure is None:
                record.provider = entry
                record.calls.append(
                    ModelCall(
                        provider=entry.id,
                        model=entry.chat_model,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        usage=completion.usage if completion else Usage(),
                        tool_calls=[c.name for c in (completion.tool_calls if completion else [])],
                    )
                )
                break
            if streamed_any or record.provider is not None:
                record.error = failure.message
                yield {"type": "error", "message": failure.message}
                return
            # nothing shown yet: fail over to the next allowed provider

        if completion is None:
            record.error = record.calls[-1].error if record.calls else "No AI provider is available."
            yield {"type": "error", "message": record.error}
            return

        if not completion.tool_calls:
            record.text = completion.text
            return

        # The model asked for tools: record the request, run them, feed results back.
        calls = completion.tool_calls[:6]
        messages.append(ChatMessage(role="assistant", content=completion.text or None, tool_calls=calls))
        record.tool_messages.append(
            {"role": "assistant", "content": completion.text or None, "tool_calls": [c.__dict__ for c in calls]}
        )
        for call in calls:
            yield {"type": "tool_start", "id": call.id, "name": call.name}

        # Tools share the request's DB session, so they run one after another.
        for call in calls:
            summary, ui, ok = await _run_tool(by_name, call, tool_ctx)
            wrapped = f'<crm_data tool="{call.name}">\n{summary}\n</crm_data>'
            messages.append(ChatMessage(role="tool", content=wrapped, tool_call_id=call.id, name=call.name))
            record.tool_messages.append(
                {"role": "tool", "tool_call_id": call.id, "tool_name": call.name, "content": summary, "ui": ui}
            )
            yield {"type": "tool_result", "id": call.id, "name": call.name, "ok": ok, "ui": ui}

    record.text = ""


async def _run_tool(by_name: dict[str, Tool], call: ToolCall, ctx: ToolContext) -> tuple[str, Any, bool]:
    tool = by_name.get(call.name)
    if tool is None:
        return f"Unknown tool {call.name}.", None, False
    result = await tool.run(ctx, call.arguments)
    return result.summary, result.ui, result.ok
