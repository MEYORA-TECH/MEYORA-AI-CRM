"""Streaming client for any OpenAI-compatible chat API (Groq, OpenRouter, Meta Model API, …)."""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.ai.providers.base import (
    ChatMessage,
    Completion,
    ProviderError,
    ProviderEvent,
    ProviderRateLimited,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)


def _to_wire(m: ChatMessage) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": m.role, "content": m.content or ""}
    if m.tool_calls:
        msg["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in m.tool_calls
        ]
    if m.tool_call_id:
        msg["tool_call_id"] = m.tool_call_id
    if m.name and m.role == "tool":
        msg["name"] = m.name
    return msg


_DURATION = re.compile(r"^(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s?)?$")


def _seconds(value: str) -> float | None:
    """Parse "12", "7.66s" or "2m59.56s" (Groq's reset-header format)."""
    match = _DURATION.match(value.strip())
    if not match or not any(match.groups()):
        return None
    minutes, seconds = match.groups()
    return float(minutes or 0) * 60 + float(seconds or 0)


def _retry_after(resp: httpx.Response) -> float | None:
    for key in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        if value := resp.headers.get(key):
            parsed = _seconds(value)
            if parsed is not None:
                return parsed
    return None


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        id: str,
        base_url: str,
        api_key: str,
        extra_body: dict[str, Any] | None = None,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.id = id
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._extra_body = extra_body or {}
        self._timeout = timeout
        self._transport = transport

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        max_tokens: int,
        temperature: float = 0.2,
    ) -> AsyncIterator[ProviderEvent]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [_to_wire(m) for m in messages],
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream_options": {"include_usage": True},
            **self._extra_body,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"
            body["parallel_tool_calls"] = True

        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        usage = Usage()
        finish: str | None = None

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                ) as resp:
                    if resp.status_code == 429:
                        raise ProviderRateLimited(_retry_after(resp))
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode(errors="replace")[:300]
                        raise ProviderError(
                            f"The AI provider returned an error ({resp.status_code}).", status=resp.status_code
                        ) from RuntimeError(detail)

                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        raw_usage = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage")
                        if raw_usage:
                            usage = Usage(
                                prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
                                completion_tokens=int(raw_usage.get("completion_tokens") or 0),
                            )
                        for choice in chunk.get("choices") or []:
                            delta = choice.get("delta") or {}
                            if delta.get("content"):
                                text_parts.append(delta["content"])
                                yield TextDelta(delta["content"])
                            for tc in delta.get("tool_calls") or []:
                                slot = calls.setdefault(
                                    int(tc.get("index", 0)), {"id": "", "name": "", "arguments": ""}
                                )
                                slot["id"] = tc.get("id") or slot["id"]
                                fn = tc.get("function") or {}
                                slot["name"] += fn.get("name") or ""
                                slot["arguments"] += fn.get("arguments") or ""
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
            except httpx.TimeoutException as exc:
                raise ProviderError("The AI provider took too long to respond.") from exc
            except httpx.TransportError as exc:
                raise ProviderError("Couldn't reach the AI provider.") from exc

        tool_calls = [
            ToolCall(id=c["id"] or f"call_{i}", name=c["name"], arguments=c["arguments"] or "{}")
            for i, c in sorted(calls.items())
            if c["name"]
        ]
        yield Completion(text="".join(text_parts), tool_calls=tool_calls, usage=usage, finish_reason=finish)
