"""Vector embedding contract, Gemini async adapter, and deterministic test embedder."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from itertools import batched
from typing import Any

from boardgamerules.domain.exceptions import DomainValidationError, RagIngestionError
from boardgamerules.domain.validators import require_non_blank

_DEFAULT_GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
_DEFAULT_OUTPUT_DIMENSIONALITY = 768
_MAX_GEMINI_BATCH_SIZE = 100
_DEFAULT_MAX_RETRIES = 4
_DEFAULT_BASE_RETRY_SECONDS = 25.0
_RETRY_DELAY_PATTERN = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)
_WORD_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
logger = logging.getLogger(__name__)


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


# CONCEPT: [System Design] Rate-Limit Backoff & Retry (HTTP 429 Resource Exhausted)
# Cloud LLM and embedding APIs enforce strict per-minute token/chunk quotas (e.g., 100
# embedded chunks per minute on Google AI Studio's free tier). Catching 429 RESOURCE_EXHAUSTED
# responses, honoring the server's requested retry delay, and retrying automatically allows
# large multi-manual batch jobs to complete smoothly without dropping files into failed/.
class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        client: Any,
        model: str = _DEFAULT_GEMINI_EMBEDDING_MODEL,
        max_batch_size: int = _MAX_GEMINI_BATCH_SIZE,
        output_dimensionality: int = _DEFAULT_OUTPUT_DIMENSIONALITY,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        base_retry_seconds: float = _DEFAULT_BASE_RETRY_SECONDS,
    ) -> None:
        require_non_blank(model, "model")
        if max_batch_size < 1 or max_batch_size > _MAX_GEMINI_BATCH_SIZE:
            raise DomainValidationError(
                f"max_batch_size must be between 1 and {_MAX_GEMINI_BATCH_SIZE}."
            )
        if output_dimensionality < 2:
            raise DomainValidationError("output_dimensionality must be >= 2.")
        if max_retries < 0:
            raise DomainValidationError("max_retries cannot be negative.")
        self._client = client
        self._model = model
        self._max_batch_size = max_batch_size
        self._output_dimensionality = output_dimensionality
        self._max_retries = max_retries
        self._base_retry_seconds = base_retry_seconds

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
        for attempt in range(self._max_retries + 1):
            try:
                logger.debug(
                    "Requesting Gemini embeddings batch",
                    extra={
                        "model": self._model,
                        "task_type": task_type,
                        "batch_size": len(texts),
                    },
                )
                response = await self._client.aio.models.embed_content(
                    model=self._model,
                    contents=texts,
                    config={
                        "task_type": task_type,
                        "output_dimensionality": self._output_dimensionality,
                    },
                )
                return [tuple(float(val) for val in item.values) for item in response.embeddings]
            except Exception as exc:
                if _is_rate_limit_error(exc) and attempt < self._max_retries:
                    wait_seconds = _parse_retry_delay_seconds(str(exc), self._base_retry_seconds)
                    logger.warning(
                        "Gemini embedding rate limit hit; retrying after backoff",
                        extra={
                            "model": self._model,
                            "attempt": attempt + 1,
                            "wait_seconds": wait_seconds,
                        },
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                raise RagIngestionError(
                    f"Failed to generate embeddings with model '{self._model}': {exc}"
                ) from exc

        raise RagIngestionError(f"Exhausted retries for embedding model '{self._model}'.")


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


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "429" in message or "RESOURCE_EXHAUSTED" in message


def _parse_retry_delay_seconds(error_text: str, default_seconds: float) -> float:
    if default_seconds <= 0.0:
        return 0.0
    match = _RETRY_DELAY_PATTERN.search(error_text)
    if match is not None:
        return float(match.group(1)) + 1.0
    return default_seconds


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
