"""Unit tests for MongoNoSqlRepository verifying index creation, CRUD, and error translation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from boardgamerules.db import MongoNoSqlRepository
from boardgamerules.domain import (
    DomainValidationError,
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


class _FakeAsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        if length is None:
            return list(self._docs)
        return list(self._docs[:length])


class _FakeAsyncCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.indexes: list[tuple[list[tuple[str, int]], bool, str | None]] = []
        self.should_fail: bool = False

    def _check_fail(self) -> None:
        if self.should_fail:
            raise PyMongoError("Simulated MongoDB connection failure")

    async def create_index(
        self,
        keys: list[tuple[str, int]],
        unique: bool = False,
        name: str | None = None,
    ) -> str:
        self._check_fail()
        self.indexes.append((keys, unique, name))
        return name or "idx"

    async def replace_one(
        self,
        filter_doc: dict[str, Any],
        replacement: dict[str, Any],
        upsert: bool = False,
    ) -> None:
        self._check_fail()
        doc_id = str(filter_doc["_id"])
        if doc_id in self.docs or upsert:
            self.docs[doc_id] = dict(replacement)

    async def update_many(
        self,
        filter_doc: dict[str, Any],
        update_doc: dict[str, Any],
    ) -> None:
        self._check_fail()
        excluded_id = filter_doc.get("_id", {}).get("$ne")
        for doc_id, doc in self.docs.items():
            if doc_id == excluded_id:
                continue
            if (
                doc.get("game_id") == filter_doc.get("game_id")
                and doc.get("edition") == filter_doc.get("edition")
                and doc.get("status") == filter_doc.get("status")
            ):
                doc.update(update_doc.get("$set", {}))

    async def find_one(
        self,
        filter_doc: dict[str, Any],
        sort: list[tuple[str, int]] | None = None,
    ) -> dict[str, Any] | None:
        self._check_fail()
        matches = self._matching_docs(filter_doc, sort=sort)
        return matches[0] if matches else None

    def find(
        self,
        filter_doc: dict[str, Any],
        sort: list[tuple[str, int]] | None = None,
    ) -> _FakeAsyncCursor:
        self._check_fail()
        return _FakeAsyncCursor(self._matching_docs(filter_doc, sort=sort))

    def _matching_docs(
        self,
        filter_doc: dict[str, Any],
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        matched = [
            dict(doc)
            for doc in self.docs.values()
            if all(doc.get(k) == v for k, v in filter_doc.items())
        ]
        if sort:
            for field_name, direction in reversed(sort):
                matched.sort(
                    key=lambda d, f=field_name: d.get(f),
                    reverse=(direction == DESCENDING),
                )
        return matched


class _FakeAsyncDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeAsyncCollection] = {
            "users": _FakeAsyncCollection(),
            "game_manuals": _FakeAsyncCollection(),
            "pending_pdfs": _FakeAsyncCollection(),
            "user_history": _FakeAsyncCollection(),
        }

    def __getitem__(self, name: str) -> _FakeAsyncCollection:
        return self.collections[name]


def test_should_ensure_indexes_and_perform_crud_across_mongo_collections(
    sample_user: UserProfile,
    sample_pending_pdf: PendingPdfManual,
) -> None:
    fake_db = _FakeAsyncDatabase()
    repo = MongoNoSqlRepository(fake_db)  # type: ignore[arg-type]
    digest = compute_pdf_sha256(b"%PDF-1.7 catan")
    ai_manual = GameManual(
        manual_id="man-ai",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.AI_GENERATED,
        indexed_at=datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC),
    )
    official_manual = GameManual(
        manual_id="man-official",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.MANUAL_PDF,
        bgg_id=13,
        content_sha256=digest,
        indexed_at=datetime(2026, 11, 12, 11, 0, 0, tzinfo=UTC),
    )
    history_entry = SavedUserEntry(
        entry_id="hist-1",
        user_id=sample_user.user_id,
        game_id="catan",
        game_title="Catan",
        entry_type=SavedEntryType.QUICK_RECAP,
        prompt_or_heading="Quick Recap",
        content_markdown="Summary",
        source=ManualSource.MANUAL_PDF,
    )

    async def _run() -> None:
        await repo.ensure_indexes()
        await repo.save_user(sample_user)
        await repo.save_manual(ai_manual)
        await repo.save_manual(official_manual)
        await repo.save_pending_pdf(sample_pending_pdf)
        await repo.save_history_entry(history_entry)

        assert await repo.get_user_by_id(sample_user.user_id) == sample_user
        assert await repo.get_user_by_google_sub(sample_user.google_sub) == sample_user
        assert await repo.get_active_manual("catan") == official_manual
        assert await repo.get_manual_by_bgg_id(13) == official_manual
        assert await repo.get_manual_by_sha256(digest) == official_manual
        assert await repo.list_manuals() == (official_manual,)
        assert await repo.list_pending_pdfs() == (sample_pending_pdf,)
        assert await repo.get_pending_pdf_by_key(sample_pending_pdf.file_key) == sample_pending_pdf
        assert await repo.list_user_history(sample_user.user_id) == (history_entry,)

    asyncio.run(_run())

    assert isinstance(repo, NoSqlRepository)
    assert len(fake_db["users"].indexes) == 1
    assert len(fake_db["game_manuals"].indexes) == 3
    assert len(fake_db["pending_pdfs"].indexes) == 2
    assert len(fake_db["user_history"].indexes) == 1
    assert fake_db["game_manuals"].docs["man-ai"]["status"] == ManualStatus.SUPERSEDED.value
    assert fake_db["users"].indexes[0][0] == [("google_sub", ASCENDING)]


def test_should_translate_pymongo_error_into_storage_operation_error(
    sample_user: UserProfile,
) -> None:
    fake_db = _FakeAsyncDatabase()
    fake_db["users"].should_fail = True
    repo = MongoNoSqlRepository(fake_db)  # type: ignore[arg-type]

    with pytest.raises(StorageOperationError, match="MongoDB operation 'save_user' failed"):
        asyncio.run(repo.save_user(sample_user))


def test_should_reject_nosql_operator_injection_payloads_in_mongo_queries() -> None:
    fake_db = _FakeAsyncDatabase()
    repo = MongoNoSqlRepository(fake_db)  # type: ignore[arg-type]

    with pytest.raises(DomainValidationError, match="google_sub"):
        asyncio.run(repo.get_user_by_google_sub({"$ne": None}))  # type: ignore[arg-type]

    with pytest.raises(DomainValidationError, match="bgg_id"):
        asyncio.run(repo.get_manual_by_bgg_id({"$gt": 0}))  # type: ignore[arg-type]
