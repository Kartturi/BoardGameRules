"""Unit tests for the PdfBatchIngestor pipeline and CLI runner."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from qdrant_client import AsyncQdrantClient

from boardgamerules.batch import (
    BatchIngestionDependencies,
    LocalPdfStorage,
    PdfBatchIngestor,
    parse_batch_cli_args,
    run_batch_once,
)
from boardgamerules.db import InMemoryNoSqlRepository
from boardgamerules.domain import (
    GameManual,
    ManualSource,
    ManualStatus,
    PendingPdfStatus,
    RuleChunk,
)
from boardgamerules.rag import (
    DeterministicEmbeddingProvider,
    QdrantRagEngine,
    RagSettings,
)


def _create_sample_pdf_bytes(pages: tuple[str, ...]) -> bytes:
    with pymupdf.open() as doc:
        for page_text in pages:
            page = doc.new_page()
            page.insert_textbox(pymupdf.Rect(50, 50, 540, 750), page_text, fontsize=12)
        return doc.tobytes()


@pytest.mark.anyio
async def test_should_ingest_incoming_pdf_into_qdrant_mark_manual_ready_and_move_to_processed(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = LocalPdfStorage(base_dir=tmp_path)
    nosql_repo = InMemoryNoSqlRepository()
    qdrant_client = AsyncQdrantClient(location=":memory:")
    rag_engine = QdrantRagEngine(
        client=qdrant_client,
        embedder=DeterministicEmbeddingProvider(vector_size=32),
        vector_size=32,
    )
    pdf_bytes = _create_sample_pdf_bytes(
        (
            "# Setup\n\nEach player starts with 2 settlements and 2 roads.",
            "# Robber Rules\n\nRolling a 7 activates the robber and players discard over 7 cards.",
        )
    )
    (tmp_path / "incoming" / "The_Settlers_of_Catan.pdf").write_bytes(pdf_bytes)

    ingestor = PdfBatchIngestor(
        BatchIngestionDependencies(
            storage=storage,
            pending_repo=nosql_repo,
            manual_repo=nosql_repo,
            rag_engine=rag_engine,
        )
    )

    # Act
    result = await ingestor.run_once()

    # Assert
    assert result.processed_keys == ("incoming/The_Settlers_of_Catan.pdf",)
    assert result.skipped_duplicate_keys == ()
    assert result.failed_keys == ()
    assert (tmp_path / "processed" / "The_Settlers_of_Catan.pdf").is_file()
    assert not (tmp_path / "incoming" / "The_Settlers_of_Catan.pdf").exists()

    manual = await nosql_repo.get_active_manual("the-settlers-of-catan")
    assert manual is not None
    assert manual.source == ManualSource.MANUAL_PDF
    assert manual.status == ManualStatus.READY
    assert manual.content_sha256 is not None

    pending_record = await nosql_repo.get_pending_pdf_by_key("incoming/The_Settlers_of_Catan.pdf")
    assert pending_record is not None
    assert pending_record.status == PendingPdfStatus.COMPLETED
    assert pending_record.content_sha256 == manual.content_sha256

    chunks = await rag_engine.search_chunks(
        game_id="the-settlers-of-catan",
        query="What happens when rolling a 7 activates the robber?",
        top_k=2,
    )
    assert len(chunks) == 2
    assert chunks[0].page_number == 2
    await qdrant_client.close()


@pytest.mark.anyio
async def test_should_skip_reembedding_when_identical_sha256_manual_already_exists(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = LocalPdfStorage(base_dir=tmp_path)
    nosql_repo = InMemoryNoSqlRepository()
    qdrant_client = AsyncQdrantClient(location=":memory:")
    rag_engine = QdrantRagEngine(
        client=qdrant_client,
        embedder=DeterministicEmbeddingProvider(vector_size=32),
        vector_size=32,
    )
    pdf_bytes = _create_sample_pdf_bytes(("# Setup\n\nPlace the board in the center.",))
    (tmp_path / "incoming" / "catan.pdf").write_bytes(pdf_bytes)

    ingestor = PdfBatchIngestor(
        BatchIngestionDependencies(
            storage=storage,
            pending_repo=nosql_repo,
            manual_repo=nosql_repo,
            rag_engine=rag_engine,
        )
    )
    await ingestor.run_once()

    # Drop a second copy of the exact same PDF bytes under a new filename
    (tmp_path / "incoming" / "catan_duplicate_copy.pdf").write_bytes(pdf_bytes)

    # Act
    second_result = await ingestor.run_once()

    # Assert
    assert second_result.processed_keys == ()
    assert second_result.skipped_duplicate_keys == ("incoming/catan_duplicate_copy.pdf",)
    assert second_result.failed_keys == ()
    assert (tmp_path / "processed" / "catan_duplicate_copy.pdf").is_file()

    duplicate_pending = await nosql_repo.get_pending_pdf_by_key("incoming/catan_duplicate_copy.pdf")
    assert duplicate_pending is not None
    assert duplicate_pending.status == PendingPdfStatus.COMPLETED
    await qdrant_client.close()


@pytest.mark.anyio
async def test_should_move_corrupted_pdf_to_failed_and_continue_processing_valid_pdfs(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = LocalPdfStorage(base_dir=tmp_path)
    nosql_repo = InMemoryNoSqlRepository()
    qdrant_client = AsyncQdrantClient(location=":memory:")
    rag_engine = QdrantRagEngine(
        client=qdrant_client,
        embedder=DeterministicEmbeddingProvider(vector_size=32),
        vector_size=32,
    )
    (tmp_path / "incoming" / "01_corrupted.pdf").write_bytes(b"not-a-valid-pdf")
    (tmp_path / "incoming" / "02_carcassonne.pdf").write_bytes(
        _create_sample_pdf_bytes(("# Tile Placement\n\nDraw and place 1 land tile.",))
    )

    ingestor = PdfBatchIngestor(
        BatchIngestionDependencies(
            storage=storage,
            pending_repo=nosql_repo,
            manual_repo=nosql_repo,
            rag_engine=rag_engine,
        )
    )

    # Act
    result = await ingestor.run_once()

    # Assert
    assert result.processed_keys == ("incoming/02_carcassonne.pdf",)
    assert len(result.failed_keys) == 1
    assert result.failed_keys[0][0] == "incoming/01_corrupted.pdf"

    assert (tmp_path / "failed" / "01_corrupted.pdf").is_file()
    assert (tmp_path / "processed" / "02_carcassonne.pdf").is_file()

    corrupted_pending = await nosql_repo.get_pending_pdf_by_key("incoming/01_corrupted.pdf")
    assert corrupted_pending is not None
    assert corrupted_pending.status == PendingPdfStatus.FAILED
    assert corrupted_pending.error_message is not None
    await qdrant_client.close()


@pytest.mark.anyio
async def test_should_purge_old_chunks_when_new_pdf_supersedes_existing_manual(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = LocalPdfStorage(base_dir=tmp_path)
    nosql_repo = InMemoryNoSqlRepository()
    qdrant_client = AsyncQdrantClient(location=":memory:")
    rag_engine = QdrantRagEngine(
        client=qdrant_client,
        embedder=DeterministicEmbeddingProvider(vector_size=32),
        vector_size=32,
    )
    # Seed an old AI-generated manual with 3 chunks in Qdrant
    await nosql_repo.save_manual(
        GameManual(
            manual_id="manual-ai-old",
            game_id="catan",
            game_title="Catan",
            source=ManualSource.AI_GENERATED,
        )
    )
    await rag_engine.index_chunks(
        (
            RuleChunk(chunk_id="catan-old-1", game_id="catan", text="Old chunk 1"),
            RuleChunk(chunk_id="catan-old-2", game_id="catan", text="Old chunk 2"),
            RuleChunk(chunk_id="catan-old-3", game_id="catan", text="Old chunk 3"),
        )
    )

    # Drop a new official 1-page PDF for Catan
    (tmp_path / "incoming" / "Catan.pdf").write_bytes(
        _create_sample_pdf_bytes(("# Official Setup\n\nOfficial verified setup rules.",))
    )
    ingestor = PdfBatchIngestor(
        BatchIngestionDependencies(
            storage=storage,
            pending_repo=nosql_repo,
            manual_repo=nosql_repo,
            rag_engine=rag_engine,
        )
    )

    # Act
    await ingestor.run_once()

    # Assert: old chunks were deleted before new chunk was indexed
    chunks = await rag_engine.search_chunks(game_id="catan", query="Setup rules", top_k=10)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "catan-p1-c0001"
    await qdrant_client.close()


@pytest.mark.anyio
async def test_should_parse_cli_args_and_execute_run_batch_once(tmp_path: Path) -> None:
    # Arrange
    args = parse_batch_cli_args(["--base-dir", str(tmp_path), "--poll-interval", "0"])
    (tmp_path / "incoming").mkdir(parents=True, exist_ok=True)
    (tmp_path / "incoming" / "azul.pdf").write_bytes(
        _create_sample_pdf_bytes(("# Drafting Tiles\n\nPick all tiles of one color.",))
    )
    settings = RagSettings(
        qdrant_url=":memory:",
        qdrant_collection_name="cli_test_chunks",
        qdrant_vector_size=16,
        gemini_embedding_model="text-embedding-004",
    )

    # Act
    result = await run_batch_once(base_dir=args.base_dir, settings=settings)

    # Assert
    assert args.base_dir == tmp_path
    assert args.poll_interval == 0.0
    assert result.processed_keys == ("incoming/azul.pdf",)
    assert (tmp_path / "processed" / "azul.pdf").is_file()
