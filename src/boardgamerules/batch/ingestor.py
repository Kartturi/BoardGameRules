"""Batch PDF rulebook ingestion coordinator with SHA-256 deduplication and dead-letter isolation."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath

from boardgamerules.domain.contracts import (
    GameManualRepository,
    PdfStorage,
    PendingPdfRepository,
    RagEngine,
)
from boardgamerules.domain.enums import ManualSource, ManualStatus
from boardgamerules.domain.exceptions import StorageOperationError
from boardgamerules.domain.manual import GameManual, PendingPdfManual
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.domain.validators import compute_pdf_sha256, normalize_game_id
from boardgamerules.rag.chunker import ChunkingConfig, chunk_rulebook_pages
from boardgamerules.rag.pdf_extractor import PdfTextExtractor, PyMuPdfTextExtractor

_DEFAULT_EXTRACTOR = PyMuPdfTextExtractor()
_DEFAULT_CHUNKING_CONFIG = ChunkingConfig()
logger = logging.getLogger(__name__)


# CONCEPT: [Design Pattern] Gateway & Repository (Injected Interfaces)
# PdfBatchIngestor does not talk to your hard drive, Qdrant, or MongoDB directly. Instead,
# those tools are passed in through BatchIngestionDependencies: PdfStorage and RagEngine are
# Gateways (wrappers around external tools like folders and Qdrant), while PendingPdfRepository
# and GameManualRepository are Repositories (wrappers for saving and loading database records).
# Because the ingestor only calls methods like self._storage.list_unprocessed_keys(), we can
# swap local folders for cloud storage or MongoDB for an in-memory test database without
# changing the ingestor code.
@dataclass(frozen=True)
class BatchIngestionDependencies:
    storage: PdfStorage
    pending_repo: PendingPdfRepository
    manual_repo: GameManualRepository
    rag_engine: RagEngine
    pdf_extractor: PdfTextExtractor = _DEFAULT_EXTRACTOR
    chunking_config: ChunkingConfig = _DEFAULT_CHUNKING_CONFIG


@dataclass(frozen=True)
class BatchIngestionResult:
    processed_keys: tuple[str, ...] = ()
    skipped_duplicate_keys: tuple[str, ...] = ()
    failed_keys: tuple[tuple[str, str], ...] = ()


# CONCEPT: [AI Engineering] Data Ingestion Pipeline (Extract -> Chunk -> Embed -> Index)
# "Ingestion" (taking in and digesting data) turns a raw PDF rulebook dropped in incoming/
# into searchable database records: read the PDF bytes, pull out each page's text, split it
# into overlapping RuleChunks, store their vector embeddings in Qdrant, and save the
# GameManual as READY in the database.
#
# CONCEPT: [System Design] Dead-Letter Folder (Isolating Broken Files)
# One broken or unreadable PDF must not stop the batch job from processing the other PDFs in
# incoming/. When a single file fails, we move it into failed/ (a "dead-letter" folder) and
# save the error message in the database, then continue with the remaining files.
class PdfBatchIngestor:
    def __init__(self, dependencies: BatchIngestionDependencies) -> None:
        self._storage = dependencies.storage
        self._pending_repo = dependencies.pending_repo
        self._manual_repo = dependencies.manual_repo
        self._rag_engine = dependencies.rag_engine
        self._pdf_extractor = dependencies.pdf_extractor
        self._chunking_config = dependencies.chunking_config

    async def run_once(self) -> BatchIngestionResult:
        incoming_keys = await self._storage.list_unprocessed_keys()
        logger.info(
            "Scanned incoming PDF directory",
            extra={"incoming_count": len(incoming_keys)},
        )
        tracker = _BatchRunTracker()

        for file_key in incoming_keys:
            await self._process_pdf(file_key, tracker)

        return tracker.to_result()

    async def _process_pdf(self, file_key: str, tracker: _BatchRunTracker) -> None:
        logger.info("Processing PDF manual", extra={"file_key": file_key})
        pending = await self._get_or_create_pending_pdf(file_key)
        processing_pdf = pending.mark_processing()
        await self._pending_repo.save_pending_pdf(processing_pdf)

        try:
            was_duplicate = await self._ingest_pdf(processing_pdf)
        except Exception as exc:
            logger.exception(
                "PDF ingestion failed; moving file to failed directory",
                extra={"file_key": file_key, "error_type": type(exc).__name__},
            )
            await self._mark_pdf_failed(processing_pdf, str(exc), tracker)
            return

        if was_duplicate:
            tracker.skipped_duplicate_keys.append(file_key)
        else:
            tracker.processed_keys.append(file_key)

    async def _get_or_create_pending_pdf(self, file_key: str) -> PendingPdfManual:
        existing = await self._pending_repo.get_pending_pdf_by_key(file_key)
        if existing is not None:
            return existing

        return PendingPdfManual(
            pending_id=f"pdf-{uuid.uuid4().hex[:12]}",
            file_key=file_key,
            game_title=_game_title_from_filename(file_key),
        )

    async def _ingest_pdf(self, pending: PendingPdfManual) -> bool:
        game_id = normalize_game_id(pending.game_title)
        pdf_bytes = await self._storage.read_pdf_bytes(pending.file_key)
        content_sha256 = compute_pdf_sha256(pdf_bytes)
        pending_with_hash = replace(pending, content_sha256=content_sha256)

        if await self._is_already_indexed(content_sha256):
            logger.info(
                "Skipping duplicate PDF manual already indexed",
                extra={"file_key": pending.file_key, "game_id": game_id},
            )
            await self._mark_pdf_completed(pending_with_hash)
            return True

        chunks = self._extract_chunks(game_id, pdf_bytes)
        await self._replace_chunks_in_qdrant(game_id, chunks)
        await self._save_ready_manual(pending_with_hash, game_id)
        await self._mark_pdf_completed(pending_with_hash)
        logger.info(
            "Indexed PDF manual into Qdrant",
            extra={
                "file_key": pending.file_key,
                "game_id": game_id,
                "chunk_count": len(chunks),
            },
        )
        return False

    async def _is_already_indexed(self, content_sha256: str) -> bool:
        existing_manual = await self._manual_repo.get_manual_by_sha256(content_sha256)
        return existing_manual is not None

    def _extract_chunks(self, game_id: str, pdf_bytes: bytes) -> tuple[RuleChunk, ...]:
        pages = self._pdf_extractor.extract_pages(pdf_bytes)
        return chunk_rulebook_pages(
            game_id=game_id,
            pages=pages,
            config=self._chunking_config,
        )

    async def _replace_chunks_in_qdrant(
        self,
        game_id: str,
        chunks: Sequence[RuleChunk],
    ) -> None:
        await self._rag_engine.delete_game_chunks(game_id)
        await self._rag_engine.index_chunks(chunks)

    async def _save_ready_manual(self, pending: PendingPdfManual, game_id: str) -> None:
        manual = GameManual(
            manual_id=f"manual-{game_id}-{uuid.uuid4().hex[:8]}",
            game_id=game_id,
            game_title=pending.game_title,
            source=ManualSource.MANUAL_PDF,
            edition=pending.edition,
            status=ManualStatus.READY,
            source_url_or_path=pending.file_key,
            content_sha256=pending.content_sha256,
        )
        await self._manual_repo.save_manual(manual)

    async def _mark_pdf_completed(self, pending: PendingPdfManual) -> None:
        await self._storage.move_to_processed(pending.file_key)
        await self._pending_repo.save_pending_pdf(pending.mark_completed())

    async def _mark_pdf_failed(
        self,
        pending: PendingPdfManual,
        error_message: str,
        tracker: _BatchRunTracker,
    ) -> None:
        final_error = error_message
        try:
            await self._storage.move_to_failed(pending.file_key)
        except StorageOperationError as move_exc:
            final_error = f"{error_message} (move_to_failed also failed: {move_exc})"

        await self._pending_repo.save_pending_pdf(pending.mark_failed(final_error))
        tracker.failed_keys.append((pending.file_key, final_error))


# CONCEPT: [Design Pattern] Collecting Parameter Pattern
# Instead of passing three separate lists (processed, duplicates, failed) into every helper
# function, we create one _BatchRunTracker and pass it through the loop to collect results.
# When the loop finishes, to_result() converts those lists into a read-only BatchIngestionResult.
@dataclass
class _BatchRunTracker:
    processed_keys: list[str] = field(default_factory=list)
    skipped_duplicate_keys: list[str] = field(default_factory=list)
    failed_keys: list[tuple[str, str]] = field(default_factory=list)

    def to_result(self) -> BatchIngestionResult:
        return BatchIngestionResult(
            processed_keys=tuple(self.processed_keys),
            skipped_duplicate_keys=tuple(self.skipped_duplicate_keys),
            failed_keys=tuple(self.failed_keys),
        )


def _game_title_from_filename(file_key: str) -> str:
    stem = PurePosixPath(file_key).stem
    cleaned = stem.replace("_", " ").replace("-", " ").strip()
    return cleaned if cleaned else "Untitled Rulebook"
