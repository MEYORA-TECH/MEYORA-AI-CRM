"""Provider-neutral chat types. Business logic only ever sees these."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text as produced by the model


@dataclass
class ChatMessage:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class TextDelta:
    text: str


@dataclass
class Completion:
    """Final event of a stream: what the model decided and what it cost."""

    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    finish_reason: str | None


ProviderEvent = TextDelta | Completion


class ProviderError(Exception):
    """The provider failed; safe to show `message` to users."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


class ProviderRateLimited(ProviderError):
    def __init__(self, retry_after: float | None):
        wait = f" Try again in about {int(retry_after) + 1}s." if retry_after else " Try again shortly."
        super().__init__(f"The AI provider's free-tier limit was reached.{wait}", status=429)
        self.retry_after = retry_after


class AIProvider(Protocol):
    id: str

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        max_tokens: int,
        temperature: float = 0.2,
        json_mode: bool = False,
        extra: dict[str, Any] | None = None,
        tool_choice: str = "auto",
    ) -> AsyncIterator[ProviderEvent]: ...
