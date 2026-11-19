"""Unit tests for vector embedding providers and batching."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from boardgamerules.domain import DomainValidationError, RagIngestionError
from boardgamerules.rag import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
)


@dataclass(frozen=True)
class _FakeEmbeddingItem:
    values: list[float]


@dataclass(frozen=True)
class _FakeEmbedResponse:
    embeddings: list[_FakeEmbeddingItem]


class _FakeAioModels:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[tuple[str, list[str], dict[str, Any] | None]] = []

    async def embed_content(
        self,
        *,
        model: str,
        contents: Sequence[str],
        config: dict[str, Any] | None = None,
    ) -> _FakeEmbedResponse:
        if self.should_fail:
            raise RuntimeError("Simulated Gemini API quota error")
        batch = list(contents)
        self.calls.append((model, batch, config))
        return _FakeEmbedResponse(
            embeddings=[_FakeEmbeddingItem(values=[float(i + 1), 0.5]) for i in range(len(batch))]
        )


class _FakeAioNamespace:
    def __init__(self, models: _FakeAioModels) -> None:
        self.models = models


class _FakeGenAiClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.aio_models = _FakeAioModels(should_fail=should_fail)
        self.aio = _FakeAioNamespace(self.aio_models)


def test_should_batch_document_embeddings_and_use_asymmetric_task_types_in_gemini_provider() -> (
    None
):
    fake_client = _FakeGenAiClient()
    provider = GeminiEmbeddingProvider(client=fake_client, max_batch_size=2)

    async def _run() -> tuple[tuple[tuple[float, ...], ...], tuple[float, ...]]:
        doc_vectors = await provider.embed_documents(["Chunk 1", "Chunk 2", "Chunk 3"])
        query_vector = await provider.embed_query("How do I win?")
        return doc_vectors, query_vector

    doc_vectors, query_vector = asyncio.run(_run())

    assert isinstance(provider, EmbeddingProvider)
    assert len(doc_vectors) == 3
    assert len(query_vector) == 2
    assert len(fake_client.aio_models.calls) == 3
    assert fake_client.aio_models.calls[0][1] == ["Chunk 1", "Chunk 2"]
    assert fake_client.aio_models.calls[0][2] == {
        "task_type": "RETRIEVAL_DOCUMENT",
        "output_dimensionality": 768,
    }
    assert fake_client.aio_models.calls[1][1] == ["Chunk 3"]
    assert fake_client.aio_models.calls[2][1] == ["How do I win?"]
    assert fake_client.aio_models.calls[2][2] == {
        "task_type": "RETRIEVAL_QUERY",
        "output_dimensionality": 768,
    }


def test_should_translate_gemini_provider_errors_into_rag_ingestion_error() -> None:
    fake_client = _FakeGenAiClient(should_fail=True)
    provider = GeminiEmbeddingProvider(client=fake_client, max_retries=0)

    with pytest.raises(RagIngestionError, match="Failed to generate embeddings"):
        asyncio.run(provider.embed_query("How many cards?"))


def test_should_retry_automatically_on_429_resource_exhausted_in_gemini_provider() -> None:
    # Arrange
    attempts = 0

    class _RateLimitedAioModels(_FakeAioModels):
        async def embed_content(
            self,
            *,
            model: str,
            contents: Sequence[str],
            config: dict[str, Any] | None = None,
        ) -> _FakeEmbedResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 0.01s.")
            return await super().embed_content(model=model, contents=contents, config=config)

    fake_client = _FakeGenAiClient()
    fake_client.aio_models = _RateLimitedAioModels()
    fake_client.aio = _FakeAioNamespace(fake_client.aio_models)
    provider = GeminiEmbeddingProvider(
        client=fake_client,
        max_retries=2,
        base_retry_seconds=0.0,
    )

    # Act
    vector = asyncio.run(provider.embed_query("How do I win?"))

    # Assert
    assert attempts == 2
    assert len(vector) == 2


def test_should_produce_normalized_deterministic_vectors_in_test_embedding_provider() -> None:
    provider = DeterministicEmbeddingProvider(vector_size=16)

    async def _run() -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        docs = await provider.embed_documents(
            [
                "Roll dice to collect wood and brick resources.",
                "Play a knight card to move the robber.",
            ]
        )
        query = await provider.embed_query("Roll dice for wood resources")
        return docs[0], docs[1], query

    vec_wood, vec_knight, vec_query = asyncio.run(_run())

    norm = math.sqrt(sum(v * v for v in vec_wood))
    sim_wood = sum(a * b for a, b in zip(vec_wood, vec_query, strict=True))
    sim_knight = sum(a * b for a, b in zip(vec_knight, vec_query, strict=True))

    assert isinstance(provider, EmbeddingProvider)
    assert len(vec_wood) == 16
    assert math.isclose(norm, 1.0, rel_tol=1e-5)
    assert sim_wood > sim_knight

    with pytest.raises(DomainValidationError, match="query"):
        asyncio.run(provider.embed_query("   "))
