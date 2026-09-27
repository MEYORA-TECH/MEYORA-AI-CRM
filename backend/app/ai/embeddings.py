"""Text embeddings behind one interface. Runs locally: no API key, no data leaves the server."""

import asyncio
import hashlib
import math
import re
import threading
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings

DIMENSIONS = 384


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedProvider:
    """bge-small-en-v1.5 via ONNX on CPU. Loaded on first use (~200 MB RAM, a few seconds)."""

    def __init__(self, model: str, cache_dir: str | None = None):
        self.model = model
        self.cache_dir = cache_dir
        self._engine = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._engine is None:
                from fastembed import TextEmbedding

                self._engine = TextEmbedding(self.model, threads=1, cache_dir=self.cache_dir)
        return self._engine

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._load().embed(texts, batch_size=16)]


class HashEmbedder:
    """Deterministic bag-of-words vectors. Test double only: similar wording → similar vectors."""

    model = "hash-bow-384"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * DIMENSIONS
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                if len(word) < 3:
                    continue
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                vec[h % DIMENSIONS] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


@lru_cache
def embedder() -> EmbeddingProvider:
    s = get_settings()
    if s.embedding_backend == "hash":
        return HashEmbedder()
    return FastEmbedProvider(s.embedding_model, s.embedding_cache_dir)


def warm_up() -> None:
    """Load the model now (call from a thread) so the first real request doesn't wait for it."""
    engine = embedder()
    if isinstance(engine, FastEmbedProvider):
        engine.embed(["warm up"])


async def embed(texts: list[str]) -> list[list[float]]:
    """CPU-bound; run off the event loop."""
    if not texts:
        return []
    return await asyncio.to_thread(embedder().embed, texts)


async def embed_one(text: str) -> list[float]:
    return (await embed([text]))[0]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
