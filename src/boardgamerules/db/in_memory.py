"""In-memory NoSQL repository adapters for fast unit testing and local zero-DB execution."""

from __future__ import annotations

from boardgamerules.domain.enums import ManualStatus, PendingPdfStatus
from boardgamerules.domain.exceptions import StorageOperationError
from boardgamerules.domain.manual import GameManual, PendingPdfManual
from boardgamerules.domain.user import SavedUserEntry, UserProfile


# CONCEPT: [Design Pattern] In-Memory Fake Repository
# Unlike brittle unittest.mock patches that assert how a database driver was called, an
# in-memory Fake implements the real repository contract (including uniqueness constraints,
# sorting, and auto-superseding) so service and API tests run in microseconds without Docker.
class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, UserProfile] = {}

    async def save_user(self, user: UserProfile) -> None:
        existing_by_sub = await self.get_user_by_google_sub(user.google_sub)
        if existing_by_sub is not None and existing_by_sub.user_id != user.user_id:
            raise StorageOperationError(
                f"google_sub '{user.google_sub}' is already linked to another user_id."
            )
        self._users[user.user_id] = user

    async def get_user_by_id(self, user_id: str) -> UserProfile | None:
        return self._users.get(user_id)

    async def get_user_by_google_sub(self, google_sub: str) -> UserProfile | None:
        return next(
            (user for user in self._users.values() if user.google_sub == google_sub),
            None,
        )


# CONCEPT: [System Design] Single-Active-Record Invariant (Auto-Superseding)
# When a new READY manual is saved for a (game_id, edition), any previously READY manual
# for that same game and edition (such as an earlier Tier-3 AI fallback) is automatically
# transitioned to SUPERSEDED so queries never return stale unverified rules.
class InMemoryGameManualRepository:
    def __init__(self) -> None:
        self._manuals: dict[str, GameManual] = {}

    async def save_manual(self, manual: GameManual) -> None:
        if manual.status == ManualStatus.READY:
            for existing_id, existing in list(self._manuals.items()):
                if (
                    existing_id != manual.manual_id
                    and existing.game_id == manual.game_id
                    and existing.edition == manual.edition
                    and existing.status == ManualStatus.READY
                ):
                    self._manuals[existing_id] = existing.mark_superseded()
        self._manuals[manual.manual_id] = manual

    async def get_active_manual(self, game_id: str) -> GameManual | None:
        candidates = [
            manual
            for manual in self._manuals.values()
            if manual.game_id == game_id and manual.status == ManualStatus.READY
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda m: (m.is_verified, m.indexed_at), reverse=True)
        return candidates[0]

    async def get_manual_by_bgg_id(
        self,
        bgg_id: int,
        edition: str = "standard",
    ) -> GameManual | None:
        candidates = [
            manual
            for manual in self._manuals.values()
            if manual.bgg_id == bgg_id
            and manual.edition == edition
            and manual.status == ManualStatus.READY
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda m: m.indexed_at, reverse=True)
        return candidates[0]

    async def get_manual_by_sha256(self, content_sha256: str) -> GameManual | None:
        return next(
            (
                manual
                for manual in self._manuals.values()
                if manual.content_sha256 == content_sha256 and manual.status == ManualStatus.READY
            ),
            None,
        )

    async def list_manuals(self) -> tuple[GameManual, ...]:
        ready_manuals = [
            manual for manual in self._manuals.values() if manual.status == ManualStatus.READY
        ]
        ready_manuals.sort(key=lambda m: (m.game_title.lower(), m.edition.lower()))
        return tuple(ready_manuals)


class InMemoryPendingPdfRepository:
    def __init__(self) -> None:
        self._pending_pdfs: dict[str, PendingPdfManual] = {}

    async def save_pending_pdf(self, pending_pdf: PendingPdfManual) -> None:
        existing_by_key = await self.get_pending_pdf_by_key(pending_pdf.file_key)
        if existing_by_key is not None and existing_by_key.pending_id != pending_pdf.pending_id:
            raise StorageOperationError(
                f"file_key '{pending_pdf.file_key}' is already registered under another pending_id."
            )
        self._pending_pdfs[pending_pdf.pending_id] = pending_pdf

    async def list_pending_pdfs(self) -> tuple[PendingPdfManual, ...]:
        pending = [
            item for item in self._pending_pdfs.values() if item.status == PendingPdfStatus.PENDING
        ]
        pending.sort(key=lambda item: (item.created_at, item.pending_id))
        return tuple(pending)

    async def get_pending_pdf_by_key(self, file_key: str) -> PendingPdfManual | None:
        return next(
            (item for item in self._pending_pdfs.values() if item.file_key == file_key),
            None,
        )


class InMemoryUserHistoryRepository:
    def __init__(self) -> None:
        self._entries: dict[str, SavedUserEntry] = {}

    async def save_history_entry(self, entry: SavedUserEntry) -> None:
        self._entries[entry.entry_id] = entry

    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]:
        user_entries = [entry for entry in self._entries.values() if entry.user_id == user_id]
        user_entries.sort(key=lambda e: (e.created_at, e.entry_id), reverse=True)
        return tuple(user_entries)


class InMemoryNoSqlRepository(
    InMemoryUserRepository,
    InMemoryGameManualRepository,
    InMemoryPendingPdfRepository,
    InMemoryUserHistoryRepository,
):
    def __init__(self) -> None:
        InMemoryUserRepository.__init__(self)
        InMemoryGameManualRepository.__init__(self)
        InMemoryPendingPdfRepository.__init__(self)
        InMemoryUserHistoryRepository.__init__(self)
