"""Tool plumbing: definitions, compact results, and short entity refs.

Refs keep prompts small: instead of 36-character UUIDs the model sees `d3` or
`c1`. The mapping lives in the conversation's working set, so follow-ups like
"what about the second one?" resolve without searching again.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.providers.base import ToolSpec
from app.auth.deps import TenantContext
from app.core.errors import NotFound

PREFIX = {"company": "c", "contact": "p", "lead": "l", "deal": "d", "task": "t", "activity": "a"}
MAX_ROWS = 10


class ToolInputError(Exception):
    pass


@dataclass
class WorkingSet:
    """Entities this conversation has touched, keyed by short ref."""

    refs: dict[str, dict[str, str]] = field(default_factory=dict)  # ref -> {type, id, name}

    @classmethod
    def load(cls, state: dict[str, Any] | None) -> "WorkingSet":
        return cls(refs=dict((state or {}).get("refs", {})))

    def dump(self) -> dict[str, Any]:
        # Keep the most recent 60 refs; older ones can be found again by search.
        items = list(self.refs.items())[-60:]
        return {"refs": dict(items)}

    def ref_for(self, kind: str, obj_id: uuid.UUID, name: str) -> str:
        sid = str(obj_id)
        for ref, v in self.refs.items():
            if v["id"] == sid:
                v["name"] = name
                return ref
        n = 1 + sum(1 for r in self.refs if r.startswith(PREFIX[kind]) and r[len(PREFIX[kind]) :].isdigit())
        ref = f"{PREFIX[kind]}{n}"
        self.refs[ref] = {"type": kind, "id": sid, "name": name}
        return ref

    def resolve(self, kind: str, value: str) -> uuid.UUID:
        value = value.strip()
        entry = self.refs.get(value.lower())
        if entry:
            if entry["type"] != kind:
                raise ToolInputError(f"{value} is a {entry['type']}, not a {kind}")
            return uuid.UUID(entry["id"])
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise ToolInputError(f"Unknown {kind} reference '{value}'. Search for it first.") from exc


@dataclass
class ToolContext:
    tenant: TenantContext
    working_set: WorkingSet
    timezone: str
    conversation_id: uuid.UUID | None = None


@dataclass
class ToolResult:
    summary: str  # what the model reads: compact, plain text
    ui: dict[str, Any] | None = None  # what the user sees: linked rows
    ok: bool = True


Handler = Callable[[ToolContext, Any], Awaitable[ToolResult]]


@dataclass
class Tool:
    name: str
    group: str
    description: str
    args: type[BaseModel]
    handler: Handler

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=_compact_schema(self.args))

    async def run(self, ctx: ToolContext, raw_arguments: str) -> ToolResult:
        try:
            parsed = json.loads(raw_arguments or "{}")
            if not isinstance(parsed, dict):
                raise ValueError("arguments must be an object")
            args = self.args.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            return ToolResult(summary=f"Invalid arguments for {self.name}: {exc}. Fix them and try again.", ok=False)
        try:
            return await self.handler(ctx, args)
        except ToolInputError as exc:
            return ToolResult(summary=str(exc), ok=False)
        except NotFound as exc:  # includes records in other organizations: indistinguishable by design
            return ToolResult(summary=f"{exc.message}.", ok=False)


def _compact_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON Schema without titles: every token in a tool schema is paid on every call."""
    schema = model.model_json_schema()

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            node.pop("title", None)
            if "anyOf" in node:  # Optional[X] -> X; "null" costs tokens and models omit fields anyway
                non_null = [o for o in node["anyOf"] if o.get("type") != "null"]
                if len(non_null) == 1:
                    rest = {k: v for k, v in node.items() if k not in ("anyOf", "default")}
                    node = {**non_null[0], **rest}
            node.pop("default", None) if node.get("default") is None else None
            return {k: strip(v) for k, v in node.items()}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(schema)


def rows_ui(entity: str, rows: list[dict[str, Any]], total: int, title: str) -> dict[str, Any]:
    return {"kind": "records", "entity": entity, "title": title, "total": total, "rows": rows}
