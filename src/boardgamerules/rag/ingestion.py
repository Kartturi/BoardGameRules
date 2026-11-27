"""Asynchronous PDF rulebook ingestion helper for extracting, chunking, and indexing in Qdrant."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from boardgamerules.domain.contracts import RagEngine
from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.domain.validators import require_canonical_game_id
from boardgamerules.rag.chunker import ChunkingConfig, chunk_rulebook_pages
from boardgamerules.rag.pdf_extractor import PdfTextExtractor, PyMuPdfTextExtractor


# CONCEPT: [AI Engineering] Asynchronous Worker Pipeline Offloading
# Extracting text from multi-page PDFs and chunking text with regexes is CPU-intensive.
# Running it in a background thread via asyncio.to_thread prevents blocking the main event loop,
# keeping async web services responsive while processing documents.
@dataclass(frozen=True)
class PdfIngestionOptions:
    pdf_extractor: PdfTextExtractor = field(default_factory=PyMuPdfTextExtractor)
    chunking_config: ChunkingConfig = field(default_factory=ChunkingConfig)


async def ingest_pdf_rulebook(
    game_id: str,
    pdf_bytes: bytes,
    rag_engine: RagEngine,
    options: PdfIngestionOptions | None = None,
) -> tuple[RuleChunk, ...]:
    require_canonical_game_id(game_id)
    if not pdf_bytes:
        raise DomainValidationError("pdf_bytes cannot be empty.")

    active_options = options or PdfIngestionOptions()
    chunks = await asyncio.to_thread(_extract_chunks, game_id, pdf_bytes, active_options)

    await rag_engine.delete_game_chunks(game_id)
    await rag_engine.index_chunks(chunks)
    return chunks


def _extract_chunks(
    game_id: str,
    pdf_bytes: bytes,
    options: PdfIngestionOptions,
) -> tuple[RuleChunk, ...]:
    pages = options.pdf_extractor.extract_pages(pdf_bytes)
    return chunk_rulebook_pages(
        game_id=game_id,
        pages=pages,
        config=options.chunking_config,
    )
