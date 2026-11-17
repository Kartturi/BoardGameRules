"""Unit tests for QdrantRagEngine using Qdrant's embedded in-memory mode."""

from __future__ import annotations

import asyncio

import pytest
from qdrant_client import AsyncQdrantClient

from boardgamerules.domain import (
    DomainValidationError,
    RagEngine,
    RagIngestionError,
    RuleChunk,
    StorageOperationError,
)
from boardgamerules.rag import DeterministicEmbeddingProvider, QdrantRagEngine


def test_should_index_search_and_delete_chunks_with_game_isolation_in_qdrant_rag_engine() -> None:
    embedder = DeterministicEmbeddingProvider(vector_size=32)
    catan_setup = RuleChunk(
        chunk_id="catan-p1-c0001",
        game_id="catan",
        text="Each player starts with two settlements and two roads on the board.",
        page_number=1,
        section_title="Setup",
    )
    catan_trading = RuleChunk(
        chunk_id="catan-p4-c0002",
        game_id="catan",
        text="Players may trade resource cards with the bank at a 4:1 ratio.",
        page_number=4,
        section_title="Trading",
    )
    azul_setup = RuleChunk(
        chunk_id="azul-p1-c0001",
        game_id="azul",
        text="Each player starts with a player board and places a scoring marker on zero.",
        page_number=1,
        section_title="Setup",
    )

    async def _run() -> tuple[
        tuple[RuleChunk, ...],
        tuple[RuleChunk, ...],
        tuple[RuleChunk, ...],
        tuple[RuleChunk, ...],
    ]:
        client = AsyncQdrantClient(location=":memory:")
        try:
            engine = QdrantRagEngine(
                client=client,
                embedder=embedder,
                collection_name="test_rules",
                vector_size=32,
            )
            assert isinstance(engine, RagEngine)

            empty_before_init = await engine.search_chunks("catan", "settlements")
            await engine.index_chunks((catan_setup, catan_trading, azul_setup))

            catan_results = await engine.search_chunks(
                game_id="catan",
                query="starts with two settlements and two roads",
                top_k=2,
            )
            await engine.delete_game_chunks("catan")
            catan_after_delete = await engine.search_chunks("catan", "settlements")
            azul_after_delete = await engine.search_chunks("azul", "scoring marker")
            return empty_before_init, catan_results, catan_after_delete, azul_after_delete
        finally:
            await client.close()

    empty_before, catan_hits, catan_deleted, azul_remaining = asyncio.run(_run())

    assert empty_before == ()
    assert len(catan_hits) == 2
    assert catan_hits[0] == catan_setup
    assert all(chunk.game_id == "catan" for chunk in catan_hits)
    assert catan_deleted == ()
    assert azul_remaining == (azul_setup,)


def test_should_upsert_deterministically_without_duplicating_chunks_on_reindex() -> None:
    embedder = DeterministicEmbeddingProvider(vector_size=16)
    original = RuleChunk(
        chunk_id="catan-p1-c0001",
        game_id="catan",
        text="Original rule text about settlements.",
        page_number=1,
        section_title="Setup",
    )
    updated = RuleChunk(
        chunk_id="catan-p1-c0001",
        game_id="catan",
        text="Updated rule text about settlements.",
        page_number=1,
        section_title="Setup",
    )

    async def _run() -> tuple[RuleChunk, ...]:
        client = AsyncQdrantClient(location=":memory:")
        try:
            engine = QdrantRagEngine(client=client, embedder=embedder, vector_size=16)
            await engine.index_chunks((original,))
            await engine.index_chunks((updated,))
            return await engine.search_chunks("catan", "settlements", top_k=5)
        finally:
            await client.close()

    results = asyncio.run(_run())

    assert results == (updated,)


def test_should_validate_inputs_and_translate_qdrant_driver_errors() -> None:
    embedder = DeterministicEmbeddingProvider(vector_size=16)

    class _FailingQdrantClient:
        async def collection_exists(self, collection_name: str) -> bool:
            raise RuntimeError("Simulated Qdrant network outage")

    failing_engine = QdrantRagEngine(
        client=_FailingQdrantClient(),  # type: ignore[arg-type]
        embedder=embedder,
        vector_size=16,
    )
    chunk = RuleChunk(chunk_id="c-1", game_id="catan", text="Rule text")

    with pytest.raises(DomainValidationError, match="canonical normalized slug"):
        asyncio.run(failing_engine.search_chunks("Invalid Slug!", "query"))

    with pytest.raises(DomainValidationError, match="top_k"):
        asyncio.run(failing_engine.search_chunks("catan", "query", top_k=0))

    with pytest.raises(RagIngestionError, match="Qdrant indexing failed"):
        asyncio.run(failing_engine.index_chunks((chunk,)))

    with pytest.raises(StorageOperationError, match="Qdrant search failed"):
        asyncio.run(failing_engine.search_chunks("catan", "query"))
