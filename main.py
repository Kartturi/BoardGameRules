"""Manual demo script to query indexed board game rulebooks in Qdrant."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from boardgamerules.domain import normalize_game_id
from boardgamerules.logging_config import configure_logging
from boardgamerules.rag import (
    QdrantRagEngine,
    RagSettings,
    create_embedding_provider_from_settings,
    create_qdrant_client_from_settings,
)

DEFAULT_GAME_ID = "6c-scythe-rulebook"
DEFAULT_QUESTION = "How is the game setup for a 3 player game?"
DEFAULT_TOP_K = 3


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search indexed board game rules in Qdrant.")
    parser.add_argument(
        "--game-id",
        default=DEFAULT_GAME_ID,
        help="Game ID or title to query (default: 6c-scythe-rulebook).",
    )
    parser.add_argument(
        "--question",
        default=DEFAULT_QUESTION,
        help="Rule question to search for.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Number of top matching rulebook chunks to return.",
    )
    return parser.parse_args(argv)


async def run_query_demo(game_id_or_title: str, question: str, top_k: int) -> None:
    game_id = normalize_game_id(game_id_or_title)
    settings = RagSettings.from_env()
    embedder = create_embedding_provider_from_settings(settings)
    qdrant_client = create_qdrant_client_from_settings(settings)

    try:
        rag_engine = QdrantRagEngine(
            client=qdrant_client,
            embedder=embedder,
            collection_name=settings.qdrant_collection_name,
            vector_size=settings.qdrant_vector_size,
        )
        matches = await rag_engine.search_chunks(
            game_id=game_id,
            query=question,
            top_k=top_k,
        )

        print(f"Game ID:  {game_id}")
        print(f"Question: {question}")
        print(
            f"Matches:  {len(matches)} chunk(s) retrieved from "
            f"'{settings.qdrant_collection_name}'\n"
        )

        for rank, chunk in enumerate(matches, start=1):
            print(
                f"--- Match #{rank} (Page {chunk.page_number} | Section: {chunk.section_title}) ---"
            )
            print(f"{chunk.text}\n")
    finally:
        await qdrant_client.close()


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging()
    args = parse_args(argv)
    asyncio.run(
        run_query_demo(
            game_id_or_title=args.game_id,
            question=args.question,
            top_k=args.top_k,
        )
    )


if __name__ == "__main__":
    main()
