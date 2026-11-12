"""NoSQL persistence adapters and document mappers for BoardGameRules."""

from boardgamerules.db.in_memory import (
    InMemoryGameManualRepository,
    InMemoryNoSqlRepository,
    InMemoryPendingPdfRepository,
    InMemoryUserHistoryRepository,
    InMemoryUserRepository,
)
from boardgamerules.db.mappers import (
    ensure_utc_datetime,
    history_entry_from_document,
    history_entry_to_document,
    manual_from_document,
    manual_to_document,
    pending_pdf_from_document,
    pending_pdf_to_document,
    user_from_document,
    user_to_document,
)
from boardgamerules.db.mongo import (
    MongoGameManualRepository,
    MongoNoSqlRepository,
    MongoPendingPdfRepository,
    MongoUserHistoryRepository,
    MongoUserRepository,
)

__all__ = [
    "InMemoryGameManualRepository",
    "InMemoryNoSqlRepository",
    "InMemoryPendingPdfRepository",
    "InMemoryUserHistoryRepository",
    "InMemoryUserRepository",
    "MongoGameManualRepository",
    "MongoNoSqlRepository",
    "MongoPendingPdfRepository",
    "MongoUserHistoryRepository",
    "MongoUserRepository",
    "ensure_utc_datetime",
    "history_entry_from_document",
    "history_entry_to_document",
    "manual_from_document",
    "manual_to_document",
    "pending_pdf_from_document",
    "pending_pdf_to_document",
    "user_from_document",
    "user_to_document",
]
