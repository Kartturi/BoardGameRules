"""Unit tests for InMemoryNoSqlRepository across all 4 collections."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from boardgamerules.db import InMemoryNoSqlRepository
from boardgamerules.domain import (
    GameManual,
    ManualSource,
    ManualStatus,
    NoSqlRepository,
    PendingPdfManual,
    SavedEntryType,
    SavedUserEntry,
    StorageOperationError,
    UserProfile,
    compute_pdf_sha256,
)


def test_should_save_and_lookup_user_by_id_and_google_sub(
    sample_user: UserProfile,
) -> None:
    repo = InMemoryNoSqlRepository()

    async def _run() -> tuple[UserProfile | None, UserProfile | None, UserProfile | None]:
        await repo.save_user(sample_user)
        return (
            await repo.get_user_by_id(sample_user.user_id),
            await repo.get_user_by_google_sub(sample_user.google_sub),
            await repo.get_user_by_id("unknown-id"),
        )

    by_id, by_sub, missing = asyncio.run(_run())

    assert isinstance(repo, NoSqlRepository)
    assert by_id == sample_user
    assert by_sub == sample_user
    assert missing is None


def test_should_raise_storage_error_when_duplicate_google_sub_is_saved_for_different_user(
    sample_user: UserProfile,
) -> None:
    repo = InMemoryNoSqlRepository()
    conflicting_user = UserProfile(
        user_id="user-999",
        google_sub=sample_user.google_sub,
        email="other@example.com",
        display_name="Other",
    )

    async def _run() -> None:
        await repo.save_user(sample_user)
        await repo.save_user(conflicting_user)

    with pytest.raises(StorageOperationError, match="google_sub"):
        asyncio.run(_run())


def test_should_auto_supersede_prior_ready_manual_when_new_ready_manual_is_saved() -> None:
    repo = InMemoryNoSqlRepository()
    digest = compute_pdf_sha256(b"%PDF-1.7 official catan manual")
    ai_manual = GameManual(
        manual_id="man-ai-catan",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.AI_GENERATED,
        indexed_at=datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC),
    )
    pdf_manual = GameManual(
        manual_id="man-pdf-catan",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.MANUAL_PDF,
        bgg_id=13,
        content_sha256=digest,
        indexed_at=datetime(2026, 11, 12, 11, 0, 0, tzinfo=UTC),
    )

    async def _run() -> tuple[
        GameManual | None,
        GameManual | None,
        GameManual | None,
        tuple[GameManual, ...],
    ]:
        await repo.save_manual(ai_manual)
        await repo.save_manual(pdf_manual)
        return (
            await repo.get_active_manual("catan"),
            await repo.get_manual_by_bgg_id(13),
            await repo.get_manual_by_sha256(digest),
            await repo.list_manuals(),
        )

    active, by_bgg, by_sha, all_ready = asyncio.run(_run())

    assert active == pdf_manual
    assert by_bgg == pdf_manual
    assert by_sha == pdf_manual
    assert all_ready == (pdf_manual,)
    assert repo._manuals["man-ai-catan"].status == ManualStatus.SUPERSEDED


def test_should_return_only_pending_pdfs_in_fifo_order() -> None:
    repo = InMemoryNoSqlRepository()
    older = PendingPdfManual(
        pending_id="p-older",
        file_key="incoming/older.pdf",
        game_title="Carcassonne",
        created_at=datetime(2026, 11, 12, 9, 0, 0, tzinfo=UTC),
    )
    newer = PendingPdfManual(
        pending_id="p-newer",
        file_key="incoming/newer.pdf",
        game_title="Azul",
        created_at=datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC),
    )
    completed = PendingPdfManual(
        pending_id="p-done",
        file_key="incoming/done.pdf",
        game_title="Catan",
        created_at=datetime(2026, 11, 12, 8, 0, 0, tzinfo=UTC),
    ).mark_completed()

    async def _run() -> tuple[tuple[PendingPdfManual, ...], PendingPdfManual | None]:
        await repo.save_pending_pdf(newer)
        await repo.save_pending_pdf(older)
        await repo.save_pending_pdf(completed)
        return (
            await repo.list_pending_pdfs(),
            await repo.get_pending_pdf_by_key("incoming/done.pdf"),
        )

    pending_queue, by_key = asyncio.run(_run())

    assert pending_queue == (older, newer)
    assert by_key == completed


def test_should_raise_storage_error_when_duplicate_file_key_is_saved_with_different_id(
    sample_pending_pdf: PendingPdfManual,
) -> None:
    repo = InMemoryNoSqlRepository()
    duplicate_key_pdf = PendingPdfManual(
        pending_id="pending-other",
        file_key=sample_pending_pdf.file_key,
        game_title="Catan 2",
    )

    async def _run() -> None:
        await repo.save_pending_pdf(sample_pending_pdf)
        await repo.save_pending_pdf(duplicate_key_pdf)

    with pytest.raises(StorageOperationError, match="file_key"):
        asyncio.run(_run())


def test_should_list_user_history_ordered_from_newest_to_oldest() -> None:
    repo = InMemoryNoSqlRepository()
    first = SavedUserEntry(
        entry_id="e-1",
        user_id="user-1",
        game_id="catan",
        game_title="Catan",
        entry_type=SavedEntryType.QUICK_RECAP,
        prompt_or_heading="Quick Recap",
        content_markdown="Recap 1",
        source=ManualSource.MANUAL_PDF,
        created_at=datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC),
    )
    second = SavedUserEntry(
        entry_id="e-2",
        user_id="user-1",
        game_id="azul",
        game_title="Azul",
        entry_type=SavedEntryType.QA_ANSWER,
        prompt_or_heading="How do floor tiles score?",
        content_markdown="Negative points at the end of the round.",
        source=ManualSource.MANUAL_PDF,
        created_at=datetime(2026, 11, 12, 11, 0, 0, tzinfo=UTC),
    )
    other_user_entry = SavedUserEntry(
        entry_id="e-3",
        user_id="user-2",
        game_id="catan",
        game_title="Catan",
        entry_type=SavedEntryType.FULL_RULES,
        prompt_or_heading="Rules",
        content_markdown="Full rules",
        source=ManualSource.AI_GENERATED,
        created_at=datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC),
    )

    async def _run() -> tuple[SavedUserEntry, ...]:
        await repo.save_history_entry(first)
        await repo.save_history_entry(second)
        await repo.save_history_entry(other_user_entry)
        return await repo.list_user_history("user-1")

    history = asyncio.run(_run())

    assert history == (second, first)
