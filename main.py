"""Manual smoke-test entry point for the RAG Engine & Vector Store."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pymupdf
from qdrant_client import AsyncQdrantClient

from boardgamerules.domain import normalize_game_id
from boardgamerules.rag import (
    DeterministicEmbeddingProvider,
    PyMuPdfTextExtractor,
    QdrantRagEngine,
    RagSettings,
    chunk_rulebook_pages,
    create_qdrant_client_from_settings,
)

INCOMING_DIR = Path("data/rulebooks/incoming")
SAMPLE_PDF_PATH = INCOMING_DIR / "catan.pdf"


def ensure_sample_rulebook_pdf(target_path: Path = SAMPLE_PDF_PATH) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing_pdfs = sorted(target_path.parent.glob("*.pdf"))
    if existing_pdfs:
        return existing_pdfs[0]

    sample_pages = (
        (
            "# Game Setup\n\n"
            "Each player selects a color and takes 5 settlements, 4 cities, and 15 roads. "
            "Place 2 settlements and 2 roads on the board during initial setup."
        ),
        (
            "# Turn Overview\n\n"
            "On your turn, roll both dice for resource production, trade resources with "
            "other players or the bank, and build roads, settlements, cities, or buy "
            "development cards."
        ),
        (
            "# Rolling a 7 and the Robber\n\n"
            "When a 7 is rolled, no one receives resources. Any player holding more than "
            "7 resource cards must discard half (rounded down). Then move the Robber to "
            "any terrain hex and steal 1 random resource from an adjacent player."
        ),
    )

    with pymupdf.open() as doc:
        for page_text in sample_pages:
            page = doc.new_page()
            page.insert_textbox(pymupdf.Rect(50, 50, 540, 750), page_text, fontsize=12)
        doc.save(target_path)

    return target_path


async def _connect_qdrant_or_fallback(
    settings: RagSettings,
) -> tuple[AsyncQdrantClient, str]:
    client = create_qdrant_client_from_settings(settings)
    if settings.qdrant_url == ":memory:":
        return client, ":memory:"
    try:
        await client.get_collections()
        return client, settings.qdrant_url
    except Exception:
        await client.close()
        return AsyncQdrantClient(location=":memory:"), ":memory: (Docker Qdrant not running)"


async def run_demo() -> None:
    pdf_path = ensure_sample_rulebook_pdf()
    game_title = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    game_id = normalize_game_id(game_title)

    print(f"1. Reading rulebook PDF: {pdf_path} (game_id='{game_id}')")
    extractor = PyMuPdfTextExtractor()
    pages = extractor.extract_pages(pdf_path.read_bytes())
    print(f"   Extracted {len(pages)} non-blank page(s).")

    chunks = chunk_rulebook_pages(game_id=game_id, pages=pages)
    print(f"2. Chunked into {len(chunks)} section-aware RuleChunk(s):")
    for chunk in chunks:
        print(f"   - [{chunk.chunk_id}] p.{chunk.page_number} ({chunk.section_title})")

    settings = RagSettings.from_env()
    client, active_location = await _connect_qdrant_or_fallback(settings)
    print(f"3. Connected to Qdrant at: {active_location}")

    try:
        engine = QdrantRagEngine(
            client=client,
            embedder=DeterministicEmbeddingProvider(vector_size=64),
            collection_name="demo_rulebook_chunks",
            vector_size=64,
        )
        await engine.index_chunks(chunks)
        print(f"   Indexed {len(chunks)} chunk(s) into collection 'demo_rulebook_chunks'.")

        query = "What happens when a 7 is rolled and the robber moves?"
        results = await engine.search_chunks(game_id=game_id, query=query, top_k=2)
        print(f"\n4. Query: '{query}'")
        for rank, match in enumerate(results, start=1):
            print(
                f"   Match #{rank} (p.{match.page_number} | {match.section_title}):\n"
                f"   {match.text}\n"
            )
    finally:
        await client.close()


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
