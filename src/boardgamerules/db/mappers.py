"""Pure document mappers between MongoDB BSON dictionaries and domain entities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from boardgamerules.domain.enums import (
    ManualSource,
    ManualStatus,
    PendingPdfStatus,
    SavedEntryType,
)
from boardgamerules.domain.manual import GameManual, PendingPdfManual
from boardgamerules.domain.user import SavedUserEntry, UserProfile


# CONCEPT: [System Design] UTC Timezone Normalization at Persistence Boundary
# MongoDB stores timestamps in UTC but deserializes BSON Date values as timezone-naive
# datetime objects by default. Attaching UTC at the mapper boundary guarantees domain
# entities always receive timezone-aware UTC timestamps.
def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# CONCEPT: [Design Pattern] Data Mapper Pattern (vs. Active Record / ODM)
# Unlike Active Record ODMs (like Beanie or MongoEngine) where domain models inherit from
# a database Document class and call `await model.save()`, a Data Mapper translates between
# pure domain dataclasses and raw MongoDB "_id" dicts. This keeps domain logic vendor-agnostic
# (easy to swap MongoDB for GCP Firestore or InMemory fakes) and testable without a DB.
def user_to_document(user: UserProfile) -> dict[str, Any]:
    return {
        "_id": user.user_id,
        "google_sub": user.google_sub,
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at,
    }


def user_from_document(doc: dict[str, Any]) -> UserProfile:
    return UserProfile(
        user_id=str(doc["_id"]),
        google_sub=str(doc["google_sub"]),
        email=str(doc["email"]),
        display_name=str(doc["display_name"]),
        created_at=ensure_utc_datetime(doc["created_at"]),
    )


def manual_to_document(manual: GameManual) -> dict[str, Any]:
    return {
        "_id": manual.manual_id,
        "game_id": manual.game_id,
        "game_title": manual.game_title,
        "source": manual.source.value,
        "edition": manual.edition,
        "status": manual.status.value,
        "summary_markdown": manual.summary_markdown,
        "source_url_or_path": manual.source_url_or_path,
        "bgg_id": manual.bgg_id,
        "product_code": manual.product_code,
        "content_sha256": manual.content_sha256,
        "indexed_at": manual.indexed_at,
    }


def manual_from_document(doc: dict[str, Any]) -> GameManual:
    return GameManual(
        manual_id=str(doc["_id"]),
        game_id=str(doc["game_id"]),
        game_title=str(doc["game_title"]),
        source=ManualSource(doc["source"]),
        edition=str(doc.get("edition", "standard")),
        status=ManualStatus(doc["status"]),
        summary_markdown=str(doc.get("summary_markdown", "")),
        source_url_or_path=doc.get("source_url_or_path"),
        bgg_id=doc.get("bgg_id"),
        product_code=doc.get("product_code"),
        content_sha256=doc.get("content_sha256"),
        indexed_at=ensure_utc_datetime(doc["indexed_at"]),
    )


def pending_pdf_to_document(pending_pdf: PendingPdfManual) -> dict[str, Any]:
    return {
        "_id": pending_pdf.pending_id,
        "file_key": pending_pdf.file_key,
        "game_title": pending_pdf.game_title,
        "edition": pending_pdf.edition,
        "content_sha256": pending_pdf.content_sha256,
        "status": pending_pdf.status.value,
        "error_message": pending_pdf.error_message,
        "created_at": pending_pdf.created_at,
        "processed_at": pending_pdf.processed_at,
    }


def pending_pdf_from_document(doc: dict[str, Any]) -> PendingPdfManual:
    processed_raw = doc.get("processed_at")
    return PendingPdfManual(
        pending_id=str(doc["_id"]),
        file_key=str(doc["file_key"]),
        game_title=str(doc["game_title"]),
        edition=str(doc.get("edition", "standard")),
        content_sha256=doc.get("content_sha256"),
        status=PendingPdfStatus(doc["status"]),
        error_message=doc.get("error_message"),
        created_at=ensure_utc_datetime(doc["created_at"]),
        processed_at=ensure_utc_datetime(processed_raw) if processed_raw is not None else None,
    )


def history_entry_to_document(entry: SavedUserEntry) -> dict[str, Any]:
    return {
        "_id": entry.entry_id,
        "user_id": entry.user_id,
        "game_id": entry.game_id,
        "game_title": entry.game_title,
        "entry_type": entry.entry_type.value,
        "prompt_or_heading": entry.prompt_or_heading,
        "content_markdown": entry.content_markdown,
        "source": entry.source.value,
        "created_at": entry.created_at,
    }


def history_entry_from_document(doc: dict[str, Any]) -> SavedUserEntry:
    return SavedUserEntry(
        entry_id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        game_id=str(doc["game_id"]),
        game_title=str(doc["game_title"]),
        entry_type=SavedEntryType(doc["entry_type"]),
        prompt_or_heading=str(doc["prompt_or_heading"]),
        content_markdown=str(doc["content_markdown"]),
        source=ManualSource(doc["source"]),
        created_at=ensure_utc_datetime(doc["created_at"]),
    )
