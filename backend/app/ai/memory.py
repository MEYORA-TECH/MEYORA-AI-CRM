"""Long-term memory: durable facts with provenance, deduplicated and scored for retrieval."""

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed_one, embedder
from app.ai.llm import complete, parse_json
from app.ai.providers.base import ChatMessage
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import AIMemory

log = get_logger("ai.memory")

MemoryType = Literal["fact", "preference", "requirement", "relationship", "decision"]
Scope = Literal["user", "organization", "company", "contact", "deal"]
TYPES = {"fact", "preference", "requirement", "relationship", "decision"}
LINK_FIELDS = ("company_id", "contact_id", "deal_id")
REVIEW_BELOW = 0.6


def normalize(content: str) -> str:
    return " ".join(content.split()).strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize(content).lower().encode()).hexdigest()


def scope_for(links: dict[str, uuid.UUID | None], user_scope: bool) -> Scope:
    if user_scope:
        return "user"
    for field, scope in (("deal_id", "deal"), ("contact_id", "contact"), ("company_id", "company")):
        if links.get(field):
            return scope  # type: ignore[return-value]
    return "organization"


@dataclass
class Saved:
    memory: AIMemory
    action: Literal["created", "merged"]


async def save_memory(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    content: str,
    memory_type: str = "fact",
    user_id: uuid.UUID | None,
    user_scope: bool = False,
    links: dict[str, uuid.UUID | None] | None = None,
    source_type: str = "manual",
    source_id: uuid.UUID | None = None,
    source_model: str | None = None,
    confidence: float = 1.0,
    importance: int = 3,
    created_by: str = "user",
) -> Saved:
    """Store a memory, or merge into a near-identical one about the same thing."""
    settings = get_settings()
    content = normalize(content)[:1000]
    links = {k: (links or {}).get(k) for k in LINK_FIELDS}
    scope = scope_for(links, user_scope)
    vector = await embed_one(content)

    duplicate = await _nearest(session, organization_id, vector, scope=scope, links=links, user_id=user_id)
    if duplicate and (
        duplicate[1] >= settings.memory_dedup_similarity or duplicate[0].content_hash == content_hash(content)
    ):
        mem = duplicate[0]
        mem.importance = max(mem.importance, importance)
        mem.confidence = max(mem.confidence, confidence)
        if mem.status == "pending_review" and confidence >= REVIEW_BELOW:
            mem.status = "active"
        return Saved(mem, "merged")

    mem = AIMemory(
        organization_id=organization_id,
        content=content,
        memory_type=memory_type if memory_type in TYPES else "fact",
        scope=scope,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        source_model=source_model,
        confidence=round(min(1.0, max(0.0, confidence)), 2),
        importance=min(5, max(1, importance)),
        status="active" if confidence >= REVIEW_BELOW else "pending_review",
        embedding=vector,
        embedding_model=embedder().model,
        content_hash=content_hash(content),
        created_by=created_by,
        **links,
    )
    session.add(mem)
    await session.flush()
    return Saved(mem, "created")


async def _nearest(session, organization_id, vector, *, scope, links, user_id) -> tuple[AIMemory, float] | None:
    distance = AIMemory.embedding.cosine_distance(vector)
    stmt = select(AIMemory, (1 - distance).label("sim")).where(
        AIMemory.organization_id == organization_id,
        AIMemory.status != "superseded",
        AIMemory.scope == scope,
        AIMemory.embedding_model == embedder().model,
    )
    for field in LINK_FIELDS:
        col = getattr(AIMemory, field)
        stmt = stmt.where(col == links[field]) if links[field] else stmt.where(col.is_(None))
    if scope == "user":
        stmt = stmt.where(AIMemory.user_id == user_id)
    row = (await session.execute(stmt.order_by(distance).limit(1))).first()
    return (row[0], float(row[1])) if row else None


async def supersede(session: AsyncSession, old_ids: list[uuid.UUID], new: AIMemory) -> int:
    if not old_ids:
        return 0
    result = await session.execute(
        update(AIMemory)
        .where(AIMemory.id.in_(old_ids), AIMemory.organization_id == new.organization_id, AIMemory.id != new.id)
        .values(status="superseded", superseded_by_id=new.id, valid_until=datetime.now(UTC))
    )
    return result.rowcount or 0


# --- Retrieval ------------------------------------------------------------------


@dataclass
class Recalled:
    memory: AIMemory
    similarity: float
    score: float


def visible_to(user_id: uuid.UUID):
    """User-scope memories belong to one person; everything else is shared with the organization."""
    return or_(AIMemory.scope != "user", AIMemory.user_id == user_id)


async def recall(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    *,
    focus: dict[str, set[uuid.UUID]] | None = None,
    limit: int = 6,
    touch: bool = True,
) -> list[Recalled]:
    """Most useful active memories for this question: similarity, importance, recency, and focus on current records."""
    settings = get_settings()
    vector = await embed_one(query)
    distance = AIMemory.embedding.cosine_distance(vector)
    rows = (
        await session.execute(
            select(AIMemory, (1 - distance).label("sim"))
            .where(
                AIMemory.organization_id == organization_id,
                AIMemory.status == "active",
                visible_to(user_id),
                AIMemory.embedding_model == embedder().model,
            )
            .order_by(distance)
            .limit(30)
        )
    ).all()

    now = datetime.now(UTC)
    focus = focus or {}
    scored = []
    for mem, sim in rows:
        sim = float(sim)
        linked = any(getattr(mem, f) in ids for f, ids in focus.items() if ids)
        if sim < settings.memory_min_similarity and not linked:
            continue
        age_days = max(0.0, (now - mem.valid_from).total_seconds() / 86400)
        score = 0.6 * sim + 0.2 * (mem.importance / 5) + 0.1 * math.exp(-age_days / 180) + (0.1 if linked else 0.0)
        scored.append(Recalled(mem, sim, round(score, 4)))
    scored.sort(key=lambda r: r.score, reverse=True)
    top = scored[:limit]
    if touch and top:
        await session.execute(
            update(AIMemory)
            .where(AIMemory.id.in_([r.memory.id for r in top]))
            .values(access_count=AIMemory.access_count + 1, last_accessed_at=now)
        )
    return top


# --- Extraction ----------------------------------------------------------------

EXTRACT_SYSTEM = """You maintain the long-term memory of a CRM. From the text, extract durable facts that will still matter weeks from now: customer requirements, preferences, decision makers and relationships, budgets, commitments, decisions.

Rules:
- Only facts stated in the text. No guesses, no advice, nothing about the assistant.
- Skip questions, greetings, requests, and details the CRM already stores as fields (emails, phone numbers, deal stages or amounts already recorded).
- Each memory is one standalone sentence that names its subject, e.g. "ABC Manufacturing prefers private (on-premise) deployment."
- "about": a record ref from the list, "organization" for company-wide knowledge, or "me" for the speaker's personal preferences.
- If a new fact contradicts or updates an existing memory, list that memory's number in "replaces".
- At most 5. Return {"memories": []} when nothing qualifies.

Return JSON only: {"memories": [{"content": str, "type": "fact|preference|requirement|relationship|decision", "about": str, "importance": 1-5, "confidence": 0-1, "replaces": [int]}]}"""


@dataclass
class Extracted:
    saved: list[Saved]
    superseded: int


async def extract(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    text: str,
    speaker: str,
    refs: dict[str, dict[str, str]],
    default_links: dict[str, uuid.UUID | None],
    source_type: str,
    source_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> Extracted:
    """Ask the fast model for memories in `text`, then save, merge and supersede."""
    # Memories about the same records are candidates for updating even when worded differently.
    focus = {f: {v} for f, v in default_links.items() if v and f in LINK_FIELDS}
    existing = (
        [r.memory for r in await recall(session, organization_id, user_id, text, focus=focus, limit=5, touch=False)]
        if user_id
        else []
    )
    numbered = "\n".join(f"{i + 1}. {m.content}" for i, m in enumerate(existing)) or "(none)"
    known = (
        "\n".join(
            f"{ref}: {v['name']} ({v['type']})"
            for ref, v in refs.items()
            if v["type"] in ("company", "contact", "deal")
        )
        or "(none)"
    )
    result = await complete(
        session,
        organization_id,
        [
            ChatMessage(role="system", content=EXTRACT_SYSTEM),
            ChatMessage(
                role="user",
                content=f"Existing memories:\n{numbered}\n\nKnown records:\n{known}\n\nText from {speaker}:\n<<<\n{text[:4000]}\n>>>",
            ),
        ],
        purpose="memory_extract",
        user_id=user_id,
        json_mode=True,
        max_tokens=500,
    )
    try:
        items = parse_json(result.text).get("memories") or []
    except ValueError:
        log.warning("memory_extract_unparseable", source_type=source_type)
        return Extracted([], 0)

    saved: list[Saved] = []
    superseded = 0
    for item in items[:5]:
        if not isinstance(item, dict) or not str(item.get("content", "")).strip():
            continue
        about = str(item.get("about") or "").strip().lower()
        links, user_scope = dict(default_links), about == "me"
        if about in refs and refs[about]["type"] in ("company", "contact", "deal"):
            links = {f: None for f in LINK_FIELDS} | {f"{refs[about]['type']}_id": uuid.UUID(refs[about]["id"])}
        elif about == "organization":
            links = {f: None for f in LINK_FIELDS}
        confidence = _number(item.get("confidence"), 0.7)
        if result.fallback:
            confidence -= 0.15  # weaker model answered: make a human look before trusting it
        s = await save_memory(
            session,
            organization_id,
            content=str(item["content"]),
            memory_type=str(item.get("type") or "fact"),
            user_id=user_id,
            user_scope=user_scope,
            links=links,
            source_type=source_type,
            source_id=source_id,
            source_model=result.model,
            confidence=confidence,
            importance=int(_number(item.get("importance"), 3)),
            created_by="ai",
        )
        saved.append(s)
        replaces = [
            existing[n - 1].id for n in item.get("replaces") or [] if isinstance(n, int) and 0 < n <= len(existing)
        ]
        superseded += await supersede(session, replaces, s.memory)
    return Extracted(saved, superseded)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
