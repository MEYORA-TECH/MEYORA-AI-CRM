"""Knowledge index: semantic search over the CRM's free text.

Indexed: notes, activity logs, and the descriptions of companies, contacts,
leads and deals. Chunks are replaced only when their text changes.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed, embed_one, embedder
from app.models import Activity, Company, Contact, Deal, EmailMessage, KnowledgeChunk, Lead, Note

INDEXED = {
    "note": Note,
    "activity": Activity,
    "company": Company,
    "contact": Contact,
    "lead": Lead,
    "deal": Deal,
    "email": EmailMessage,
}
CHUNK_CHARS = 900
OVERLAP = 120


@dataclass
class Source:
    title: str
    text: str
    occurred_at: datetime | None
    links: dict[str, uuid.UUID | None]


def _source(kind: str, obj) -> Source | None:
    if getattr(obj, "deleted_at", None) is not None:
        return None
    if kind == "note":
        return Source("Note", obj.body, obj.created_at, _links(obj))
    if kind == "email":
        if not obj.body_text:
            return None
        who = obj.from_name or obj.from_email
        return Source(
            f"Email: {obj.subject} (from {who})",
            obj.body_text,
            obj.sent_at,
            {
                "company_id": obj.company_ids[0] if obj.company_ids else None,
                "contact_id": obj.contact_ids[0] if obj.contact_ids else None,
            },
        )
    if kind == "activity":
        body = "\n".join(filter(None, [obj.body, f"Outcome: {obj.outcome}" if obj.outcome else None]))
        if not body:
            return None  # a subject alone is already searchable by name
        return Source(f"{obj.type.replace('_', ' ').title()}: {obj.subject}", body, obj.occurred_at, _links(obj))
    if not obj.description:
        return None
    if kind == "company":
        return Source(f"Company: {obj.name}", obj.description, obj.updated_at, {"company_id": obj.id})
    if kind == "contact":
        return Source(
            f"Contact: {obj.full_name}",
            obj.description,
            obj.updated_at,
            {"contact_id": obj.id, "company_id": obj.company_id},
        )
    if kind == "lead":
        return Source(f"Lead: {obj.name}", obj.description, obj.updated_at, {"lead_id": obj.id})
    return Source(
        f"Deal: {obj.name}",
        obj.description,
        obj.updated_at,
        {"deal_id": obj.id, "company_id": obj.company_id, "contact_id": obj.contact_id},
    )


def _links(obj) -> dict[str, uuid.UUID | None]:
    return {k: getattr(obj, k, None) for k in ("company_id", "contact_id", "lead_id", "deal_id")}


def chunk(text: str) -> list[str]:
    text = " ".join(text.split())
    if len(text) <= CHUNK_CHARS:
        return [text] if text else []
    parts, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):  # prefer to cut at a sentence or word boundary
            cut = max(text.rfind(". ", start, end), text.rfind(" ", start, end))
            end = cut + 1 if cut > start + CHUNK_CHARS // 2 else end
        parts.append(text[start:end].strip())
        start = end - OVERLAP if end < len(text) else end
    return parts


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def index_record(session: AsyncSession, organization_id: uuid.UUID, kind: str, record_id: uuid.UUID) -> int:
    """(Re)index one record. Returns the number of chunks embedded."""
    model = INDEXED[kind]
    obj = await session.scalar(select(model).where(model.id == record_id, model.organization_id == organization_id))
    source = _source(kind, obj) if obj is not None else None
    existing = list(
        await session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.source_type == kind, KnowledgeChunk.source_id == record_id)
            .order_by(KnowledgeChunk.chunk_no)
        )
    )
    pieces = chunk(source.text) if source else []
    embed_model = embedder().model
    if [c.content_hash for c in existing] == [_hash(p) for p in pieces] and all(
        c.embedding_model == embed_model for c in existing
    ):
        return 0  # unchanged

    await session.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.source_type == kind, KnowledgeChunk.source_id == record_id)
    )
    if not pieces:
        return 0
    vectors = await embed([f"{source.title}\n{p}" for p in pieces])
    for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
        session.add(
            KnowledgeChunk(
                organization_id=organization_id,
                source_type=kind,
                source_id=record_id,
                chunk_no=i,
                title=source.title[:300],
                content=piece,
                content_hash=_hash(piece),
                occurred_at=source.occurred_at,
                embedding=vector,
                embedding_model=embed_model,
                **source.links,
            )
        )
    return len(pieces)


@dataclass
class Hit:
    chunk: KnowledgeChunk
    similarity: float


async def search(
    session: AsyncSession,
    organization_id: uuid.UUID,
    query: str,
    *,
    link: tuple[str, uuid.UUID] | None = None,
    limit: int = 6,
    min_similarity: float = 0.3,
) -> list[Hit]:
    vector = await embed_one(query)
    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    stmt = (
        select(KnowledgeChunk, (1 - distance).label("similarity"))
        .where(KnowledgeChunk.organization_id == organization_id, KnowledgeChunk.embedding_model == embedder().model)
        .order_by(distance)
        .limit(limit)
    )
    if link:
        field, value = link
        stmt = stmt.where(getattr(KnowledgeChunk, field) == value)
    rows = (await session.execute(stmt)).all()
    return [Hit(c, float(sim)) for c, sim in rows if sim >= min_similarity]
