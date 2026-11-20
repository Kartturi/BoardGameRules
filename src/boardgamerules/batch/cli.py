"""Stateless CLI entry point for single-run (Cloud Run Jobs) or polling batch PDF ingestion."""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from pymongo import AsyncMongoClient
from qdrant_client import AsyncQdrantClient

from boardgamerules.batch.ingestor import (
    BatchIngestionDependencies,
    BatchIngestionResult,
    PdfBatchIngestor,
)
from boardgamerules.batch.storage import LocalPdfStorage
from boardgamerules.db.in_memory import InMemoryNoSqlRepository
from boardgamerules.db.mongo import MongoNoSqlRepository
from boardgamerules.domain.contracts import NoSqlRepository
from boardgamerules.env_loader import PROJECT_ROOT
from boardgamerules.logging_config import configure_logging
from boardgamerules.rag.config import (
    RagSettings,
    create_embedding_provider_from_settings,
    create_qdrant_client_from_settings,
)
from boardgamerules.rag.qdrant_engine import QdrantRagEngine

_DEFAULT_RULEBOOKS_DIR = PROJECT_ROOT / "data" / "rulebooks"
logger = logging.getLogger(__name__)


def parse_batch_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest PDF rulebooks from incoming/ into Qdrant and NoSQL storage."
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=_DEFAULT_RULEBOOKS_DIR,
        help="Base rulebooks directory containing incoming/, processed/, and failed/.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.0,
        help="If > 0, poll incoming/ every N seconds instead of exiting after one pass.",
    )
    return parser.parse_args(argv)


async def run_batch_once(
    base_dir: Path = _DEFAULT_RULEBOOKS_DIR,
    settings: RagSettings | None = None,
) -> BatchIngestionResult:
    resolved_settings = settings or RagSettings.from_env()
    qdrant_client = create_qdrant_client_from_settings(resolved_settings)
    try:
        async with open_database(resolved_settings) as database:
            rag_engine = _create_rag_engine(resolved_settings, qdrant_client)
            ingestor = _create_ingestor(base_dir, database, rag_engine)
            return await ingestor.run_once()
    finally:
        await qdrant_client.close()


def _create_rag_engine(
    settings: RagSettings,
    qdrant_client: AsyncQdrantClient,
) -> QdrantRagEngine:
    return QdrantRagEngine(
        client=qdrant_client,
        embedder=create_embedding_provider_from_settings(settings),
        collection_name=settings.qdrant_collection_name,
        vector_size=settings.qdrant_vector_size,
    )


def _create_ingestor(
    base_dir: Path,
    database: NoSqlRepository,
    rag_engine: QdrantRagEngine,
) -> PdfBatchIngestor:
    return PdfBatchIngestor(
        BatchIngestionDependencies(
            storage=LocalPdfStorage(base_dir=base_dir),
            pending_repo=database,
            manual_repo=database,
            rag_engine=rag_engine,
        )
    )


@asynccontextmanager
async def open_database(settings: RagSettings) -> AsyncIterator[NoSqlRepository]:
    if not settings.mongodb_uri or not settings.mongodb_database:
        logger.info("Using in-memory NoSQL repository (MONGODB_URI not configured)")
        yield InMemoryNoSqlRepository()
        return

    logger.info(
        "Connecting to MongoDB repository",
        extra={"mongodb_database": settings.mongodb_database},
    )
    mongo_client: AsyncMongoClient[dict[str, object]] = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )
    try:
        repository = MongoNoSqlRepository(mongo_client[settings.mongodb_database])
        await repository.ensure_indexes()
        yield repository
    finally:
        await mongo_client.close()


async def run_batch_worker(
    base_dir: Path,
    poll_interval: float,
) -> BatchIngestionResult:
    logger.info(
        "Starting PDF batch worker",
        extra={"base_dir": str(base_dir), "poll_interval_seconds": poll_interval},
    )
    while True:
        result = await run_batch_once(base_dir=base_dir)
        _log_batch_result(result)
        if poll_interval <= 0.0:
            return result
        await asyncio.sleep(poll_interval)


def _log_batch_result(result: BatchIngestionResult) -> None:
    logger.info(
        "Batch ingestion pass completed",
        extra={
            "processed_count": len(result.processed_keys),
            "duplicates_skipped_count": len(result.skipped_duplicate_keys),
            "failed_count": len(result.failed_keys),
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = parse_batch_cli_args(argv)
    asyncio.run(run_batch_worker(base_dir=args.base_dir, poll_interval=args.poll_interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
