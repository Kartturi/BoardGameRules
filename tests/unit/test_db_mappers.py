"""Unit tests for BSON document mappers and UTC timestamp normalization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from boardgamerules.db import (
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
from boardgamerules.domain import (
    GameManual,
    ManualSource,
    PendingPdfManual,
    SavedEntryType,
    SavedUserEntry,
    UserProfile,
)


def test_should_normalize_naive_and_offset_datetimes_to_utc() -> None:
    naive_dt = datetime(2026, 11, 12, 12, 0, 0)
    plus_two_tz = timezone(timedelta(hours=2))
    offset_dt = datetime(2026, 11, 12, 14, 0, 0, tzinfo=plus_two_tz)

    normalized_naive = ensure_utc_datetime(naive_dt)
    normalized_offset = ensure_utc_datetime(offset_dt)

    assert normalized_naive == datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC)
    assert normalized_offset == datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC)


def test_should_round_trip_user_profile_with_naive_mongo_date(
    sample_user: UserProfile,
) -> None:
    doc = user_to_document(sample_user)
    doc["created_at"] = sample_user.created_at.replace(tzinfo=None)

    restored = user_from_document(doc)

    assert doc["_id"] == sample_user.user_id
    assert restored == sample_user


def test_should_round_trip_game_manual_preserving_enums_and_deduplication_fields(
    sample_manual: GameManual,
) -> None:
    doc = manual_to_document(sample_manual)
    doc["indexed_at"] = sample_manual.indexed_at.replace(tzinfo=None)

    restored = manual_from_document(doc)

    assert doc["_id"] == sample_manual.manual_id
    assert isinstance(restored.source, ManualSource)
    assert restored == sample_manual


def test_should_round_trip_pending_pdf_manual_with_completed_timestamp(
    sample_pending_pdf: PendingPdfManual,
) -> None:
    completed = sample_pending_pdf.mark_completed(
        processed_at=datetime(2026, 11, 12, 13, 0, 0, tzinfo=UTC)
    )
    doc = pending_pdf_to_document(completed)
    doc["created_at"] = completed.created_at.replace(tzinfo=None)
    doc["processed_at"] = completed.processed_at.replace(tzinfo=None)  # type: ignore[union-attr]

    restored = pending_pdf_from_document(doc)

    assert doc["_id"] == completed.pending_id
    assert restored == completed


def test_should_round_trip_saved_user_entry(fixed_utc_now: datetime) -> None:
    entry = SavedUserEntry(
        entry_id="hist-001",
        user_id="user-001",
        game_id="catan",
        game_title="Catan",
        entry_type=SavedEntryType.QA_ANSWER,
        prompt_or_heading="Can I build a settlement on an opponent's road?",
        content_markdown="No, unless it connects to your own road and obeys the distance rule.",
        source=ManualSource.MANUAL_PDF,
        created_at=fixed_utc_now,
    )
    doc = history_entry_to_document(entry)
    doc["created_at"] = fixed_utc_now.replace(tzinfo=None)

    restored = history_entry_from_document(doc)

    assert doc["_id"] == entry.entry_id
    assert restored == entry
