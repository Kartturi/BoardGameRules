"""Asynchronous MongoDB repository adapters using PyMongo's native AsyncDatabase."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from boardgamerules.db.mappers import (
    history_entry_from_document,
    history_entry_to_document,
    manual_from_document,
    manual_to_document,
    pending_pdf_from_document,
    pending_pdf_to_document,
    user_from_document,
    user_to_document,
)
from boardgamerules.domain.enums import ManualStatus, PendingPdfStatus
from boardgamerules.domain.exceptions import DomainValidationError, StorageOperationError
from boardgamerules.domain.manual import GameManual, PendingPdfManual
from boardgamerules.domain.user import SavedUserEntry, UserProfile


# CONCEPT: [System Design] NoSQL Operator Injection Prevention
# In MongoDB, passing a dict like {"$ne": None} as a filter value executes a query operator
# instead of a literal equality check (CWE-943). Enforcing strict scalar types (str/int) at
# the repository query boundary blocks operator injection even if upstream validation is bypassed.
def _require_str_scalar(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must be a non-empty string.")
    return value


def _require_int_scalar(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DomainValidationError(f"{field_name} must be a positive integer.")
    return value


# CONCEPT: [System Design] Exception Translation at Infrastructure Boundary
# Catching low-level driver exceptions (PyMongoError) and re-raising a domain exception
# (StorageOperationError) prevents database driver details from leaking into business logic.
@asynccontextmanager
async def _translate_mongo_errors(operation: str) -> AsyncIterator[None]:
    try:
        yield
    except PyMongoError as exc:
        raise StorageOperationError(f"MongoDB operation '{operation}' failed: {exc}") from exc


class MongoUserRepository:
    def __init__(self, collection: AsyncCollection[dict[str, Any]]) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> None:
        async with _translate_mongo_errors("ensure_user_indexes"):
            await self._collection.create_index(
                [("google_sub", ASCENDING)],
                unique=True,
                name="idx_users_google_sub_unique",
            )

    async def save_user(self, user: UserProfile) -> None:
        doc = user_to_document(user)
        async with _translate_mongo_errors("save_user"):
            await self._collection.replace_one({"_id": user.user_id}, doc, upsert=True)

    async def get_user_by_id(self, user_id: str) -> UserProfile | None:
        safe_id = _require_str_scalar(user_id, "user_id")
        async with _translate_mongo_errors("get_user_by_id"):
            doc = await self._collection.find_one({"_id": safe_id})
        return user_from_document(doc) if doc is not None else None

    async def get_user_by_google_sub(self, google_sub: str) -> UserProfile | None:
        safe_sub = _require_str_scalar(google_sub, "google_sub")
        async with _translate_mongo_errors("get_user_by_google_sub"):
            doc = await self._collection.find_one({"google_sub": safe_sub})
        return user_from_document(doc) if doc is not None else None


class MongoGameManualRepository:
    def __init__(self, collection: AsyncCollection[dict[str, Any]]) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> None:
        async with _translate_mongo_errors("ensure_manual_indexes"):
            await self._collection.create_index(
                [("game_id", ASCENDING), ("status", ASCENDING), ("indexed_at", DESCENDING)],
                name="idx_manuals_game_status_indexed",
            )
            await self._collection.create_index(
                [("bgg_id", ASCENDING), ("edition", ASCENDING), ("status", ASCENDING)],
                name="idx_manuals_bgg_edition_status",
            )
            await self._collection.create_index(
                [("content_sha256", ASCENDING), ("status", ASCENDING)],
                name="idx_manuals_sha256_status",
            )

    async def save_manual(self, manual: GameManual) -> None:
        doc = manual_to_document(manual)
        async with _translate_mongo_errors("save_manual"):
            if manual.status == ManualStatus.READY:
                await self._collection.update_many(
                    {
                        "_id": {"$ne": manual.manual_id},
                        "game_id": manual.game_id,
                        "edition": manual.edition,
                        "status": ManualStatus.READY.value,
                    },
                    {"$set": {"status": ManualStatus.SUPERSEDED.value}},
                )
            await self._collection.replace_one({"_id": manual.manual_id}, doc, upsert=True)

    async def get_active_manual(self, game_id: str) -> GameManual | None:
        safe_game_id = _require_str_scalar(game_id, "game_id")
        async with _translate_mongo_errors("get_active_manual"):
            cursor = self._collection.find(
                {"game_id": safe_game_id, "status": ManualStatus.READY.value}
            )
            docs = await cursor.to_list(length=None)
        if not docs:
            return None
        manuals = [manual_from_document(doc) for doc in docs]
        manuals.sort(key=lambda m: (m.is_verified, m.indexed_at), reverse=True)
        return manuals[0]

    async def get_manual_by_bgg_id(
        self,
        bgg_id: int,
        edition: str = "standard",
    ) -> GameManual | None:
        safe_bgg_id = _require_int_scalar(bgg_id, "bgg_id")
        safe_edition = _require_str_scalar(edition, "edition")
        async with _translate_mongo_errors("get_manual_by_bgg_id"):
            doc = await self._collection.find_one(
                {
                    "bgg_id": safe_bgg_id,
                    "edition": safe_edition,
                    "status": ManualStatus.READY.value,
                },
                sort=[("indexed_at", DESCENDING)],
            )
        return manual_from_document(doc) if doc is not None else None

    async def get_manual_by_sha256(self, content_sha256: str) -> GameManual | None:
        safe_sha = _require_str_scalar(content_sha256, "content_sha256")
        async with _translate_mongo_errors("get_manual_by_sha256"):
            doc = await self._collection.find_one(
                {
                    "content_sha256": safe_sha,
                    "status": ManualStatus.READY.value,
                }
            )
        return manual_from_document(doc) if doc is not None else None

    async def list_manuals(self) -> tuple[GameManual, ...]:
        async with _translate_mongo_errors("list_manuals"):
            cursor = self._collection.find(
                {"status": ManualStatus.READY.value},
                sort=[("game_title", ASCENDING), ("edition", ASCENDING)],
            )
            docs = await cursor.to_list(length=None)
        return tuple(manual_from_document(doc) for doc in docs)


class MongoPendingPdfRepository:
    def __init__(self, collection: AsyncCollection[dict[str, Any]]) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> None:
        async with _translate_mongo_errors("ensure_pending_pdf_indexes"):
            await self._collection.create_index(
                [("file_key", ASCENDING)],
                unique=True,
                name="idx_pending_pdfs_file_key_unique",
            )
            await self._collection.create_index(
                [("status", ASCENDING), ("created_at", ASCENDING)],
                name="idx_pending_pdfs_status_created",
            )

    async def save_pending_pdf(self, pending_pdf: PendingPdfManual) -> None:
        doc = pending_pdf_to_document(pending_pdf)
        async with _translate_mongo_errors("save_pending_pdf"):
            await self._collection.replace_one(
                {"_id": pending_pdf.pending_id},
                doc,
                upsert=True,
            )

    async def list_pending_pdfs(self) -> tuple[PendingPdfManual, ...]:
        async with _translate_mongo_errors("list_pending_pdfs"):
            cursor = self._collection.find(
                {"status": PendingPdfStatus.PENDING.value},
                sort=[("created_at", ASCENDING), ("_id", ASCENDING)],
            )
            docs = await cursor.to_list(length=None)
        return tuple(pending_pdf_from_document(doc) for doc in docs)

    async def get_pending_pdf_by_key(self, file_key: str) -> PendingPdfManual | None:
        safe_key = _require_str_scalar(file_key, "file_key")
        async with _translate_mongo_errors("get_pending_pdf_by_key"):
            doc = await self._collection.find_one({"file_key": safe_key})
        return pending_pdf_from_document(doc) if doc is not None else None


class MongoUserHistoryRepository:
    def __init__(self, collection: AsyncCollection[dict[str, Any]]) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> None:
        async with _translate_mongo_errors("ensure_user_history_indexes"):
            await self._collection.create_index(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="idx_user_history_user_created",
            )

    async def save_history_entry(self, entry: SavedUserEntry) -> None:
        doc = history_entry_to_document(entry)
        async with _translate_mongo_errors("save_history_entry"):
            await self._collection.replace_one({"_id": entry.entry_id}, doc, upsert=True)

    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]:
        safe_user_id = _require_str_scalar(user_id, "user_id")
        async with _translate_mongo_errors("list_user_history"):
            cursor = self._collection.find(
                {"user_id": safe_user_id},
                sort=[("created_at", DESCENDING), ("_id", DESCENDING)],
            )
            docs = await cursor.to_list(length=None)
        return tuple(history_entry_from_document(doc) for doc in docs)


class MongoNoSqlRepository:
    def __init__(self, database: AsyncDatabase[dict[str, Any]]) -> None:
        self._users = MongoUserRepository(database["users"])
        self._manuals = MongoGameManualRepository(database["game_manuals"])
        self._pending_pdfs = MongoPendingPdfRepository(database["pending_pdfs"])
        self._history = MongoUserHistoryRepository(database["user_history"])

    async def ensure_indexes(self) -> None:
        await self._users.ensure_indexes()
        await self._manuals.ensure_indexes()
        await self._pending_pdfs.ensure_indexes()
        await self._history.ensure_indexes()

    async def save_user(self, user: UserProfile) -> None:
        await self._users.save_user(user)

    async def get_user_by_id(self, user_id: str) -> UserProfile | None:
        return await self._users.get_user_by_id(user_id)

    async def get_user_by_google_sub(self, google_sub: str) -> UserProfile | None:
        return await self._users.get_user_by_google_sub(google_sub)

    async def save_manual(self, manual: GameManual) -> None:
        await self._manuals.save_manual(manual)

    async def get_active_manual(self, game_id: str) -> GameManual | None:
        return await self._manuals.get_active_manual(game_id)

    async def get_manual_by_bgg_id(
        self,
        bgg_id: int,
        edition: str = "standard",
    ) -> GameManual | None:
        return await self._manuals.get_manual_by_bgg_id(bgg_id, edition)

    async def get_manual_by_sha256(self, content_sha256: str) -> GameManual | None:
        return await self._manuals.get_manual_by_sha256(content_sha256)

    async def list_manuals(self) -> tuple[GameManual, ...]:
        return await self._manuals.list_manuals()

    async def save_pending_pdf(self, pending_pdf: PendingPdfManual) -> None:
        await self._pending_pdfs.save_pending_pdf(pending_pdf)

    async def list_pending_pdfs(self) -> tuple[PendingPdfManual, ...]:
        return await self._pending_pdfs.list_pending_pdfs()

    async def get_pending_pdf_by_key(self, file_key: str) -> PendingPdfManual | None:
        return await self._pending_pdfs.get_pending_pdf_by_key(file_key)

    async def save_history_entry(self, entry: SavedUserEntry) -> None:
        await self._history.save_history_entry(entry)

    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]:
        return await self._history.list_user_history(user_id)
