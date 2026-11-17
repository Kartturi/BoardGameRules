"""Vector embedding contract, Gemini async adapter, and deterministic test embedder."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from itertools import batched
from typing import Any

from boardgamerules.domain.exceptions import DomainValidationError, RagIngestionError
from boardgamerules.domain.validators import require_non_blank

_DEFAULT_GEMINI_EMBEDDING_MODEL = "text-embedding-004"
_MAX_GEMINI_BATCH_SIZE = 100
_WORD_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


# CONCEPT: [AI Engineering] Vector Embeddings (Translating Text Meaning into Coordinates)
# An "embedding" is a list of floating-point numbers (e.g., 768 numbers between -1.0 and 1.0)
# that represents the meaning of a text as a point in multi-dimensional space ("embedding"
# the text into a coordinate space). Texts with similar meaning get placed at nearby
# coordinates even when they share zero keywords, allowing Qdrant to find relevant rules by
# measuring distance (Cosine Similarity) between a player's question vector and rule vectors.
#
# CONCEPT: [AI Engineering] Asymmetric Task-Type Embeddings (Document vs. Query)
# Modern embedding models optimize vector representations differently for long rulebook
# passages being indexed (RETRIEVAL_DOCUMENT) versus short user questions (RETRIEVAL_QUERY).
# Separating embed_documents and embed_query preserves this distinction at the contract boundary.
class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...

    @abstractmethod
    async def embed_query(self, query: str) -> tuple[float, ...]: ...


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        client: Any,
        model: str = _DEFAULT_GEMINI_EMBEDDING_MODEL,
        max_batch_size: int = _MAX_GEMINI_BATCH_SIZE,
    ) -> None:
        require_non_blank(model, "model")
        if max_batch_size < 1 or max_batch_size > _MAX_GEMINI_BATCH_SIZE:
            raise DomainValidationError(
                f"max_batch_size must be between 1 and {_MAX_GEMINI_BATCH_SIZE}."
            )
        self._client = client
        self._model = model
        self._max_batch_size = max_batch_size

    async def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        for text in texts:
            require_non_blank(text, "text")

        vectors: list[tuple[float, ...]] = []
        for batch in batched(texts, self._max_batch_size, strict=False):
            batch_vectors = await self._embed_batch(list(batch), task_type="RETRIEVAL_DOCUMENT")
            vectors.extend(batch_vectors)
        return tuple(vectors)

    async def embed_query(self, query: str) -> tuple[float, ...]:
        require_non_blank(query, "query")
        vectors = await self._embed_batch([query], task_type="RETRIEVAL_QUERY")
        return vectors[0]

    async def _embed_batch(
        self,
        texts: list[str],
        task_type: str,
    ) -> list[tuple[float, ...]]:
        try:
            response = await self._client.aio.models.embed_content(
                model=self._model,
                contents=texts,
                config={"task_type": task_type},
            )
            return [tuple(float(val) for val in item.values) for item in response.embeddings]
        except Exception as exc:
            raise RagIngestionError(
                f"Failed to generate embeddings with model '{self._model}': {exc}"
            ) from exc


class DeterministicEmbeddingProvider(EmbeddingProvider):
    def __init__(self, vector_size: int = 64) -> None:
        if vector_size < 2:
            raise DomainValidationError("vector_size must be >= 2.")
        self._vector_size = vector_size

    async def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        for text in texts:
            require_non_blank(text, "text")
        return tuple(self._vectorize(text) for text in texts)

    async def embed_query(self, query: str) -> tuple[float, ...]:
        require_non_blank(query, "query")
        return self._vectorize(query)

    def _vectorize(self, text: str) -> tuple[float, ...]:
        buckets = [0.0] * self._vector_size
        for token in _extract_word_tokens(text):
            bucket_index, sign = _hash_token_to_bucket(token, self._vector_size)
            buckets[bucket_index] += sign
        return _normalize_to_unit_vector(buckets)


def _extract_word_tokens(text: str) -> list[str]:
    lowered = text.strip().lower()
    return _WORD_TOKEN_PATTERN.findall(lowered) or [lowered]


def _hash_token_to_bucket(token: str, vector_size: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    bucket_index = int.from_bytes(digest[:4], "big") % vector_size
    sign = 1.0 if (digest[4] % 2 == 0) else -1.0
    return bucket_index, sign


def _normalize_to_unit_vector(buckets: list[float]) -> tuple[float, ...]:
    length = math.sqrt(sum(val * val for val in buckets))
    if length == 0.0:
        buckets[0] = 1.0
        return tuple(buckets)
    return tuple(val / length for val in buckets)
