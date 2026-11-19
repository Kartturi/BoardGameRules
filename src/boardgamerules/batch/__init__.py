"""Batch PDF rulebook ingestion job and storage adapters."""

from boardgamerules.batch.cli import main, parse_batch_cli_args, run_batch_once
from boardgamerules.batch.ingestor import (
    BatchIngestionDependencies,
    BatchIngestionResult,
    PdfBatchIngestor,
)
from boardgamerules.batch.storage import LocalPdfStorage

__all__ = [
    "BatchIngestionDependencies",
    "BatchIngestionResult",
    "LocalPdfStorage",
    "PdfBatchIngestor",
    "main",
    "parse_batch_cli_args",
    "run_batch_once",
]
