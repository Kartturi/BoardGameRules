"""Unit tests verifying asynchronous Protocol contracts and structural subtyping."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from boardgamerules.domain import (
    AiRuleGenerator,
    FetchedRulebook,
    GameManual,
    GameManualRepository,
    NoSqlRepository,
    PdfStorage,
    PendingPdfManual,
    PendingPdfRepository,
    RagEngine,
    RulebookFetcher,
    RuleChunk,
    SavedUserEntry,
    UserHistoryRepository,
    UserProfile,
    UserRepository,
)


class _InMemoryNoSqlStub:
    def __init__(self) -> None:
        self.users: dict[str, UserProfile] = {}
        self.manuals: dict[str, GameManual] = {}
        self.pending_pdfs: dict[str, PendingPdfManual] = {}
        self.history: list[SavedUserEntry] = []

    async def save_user(self, user: UserProfile) -> None:
        self.users[user.user_id] = user

    async def get_user_by_id(self, user_id: str) -> UserProfile | None:
        return self.users.get(user_id)

    async def get_user_by_google_sub(self, google_sub: str) -> UserProfile | None:
        return next((u for u in self.users.values() if u.google_sub == google_sub), None)

    async def save_manual(self, manual: GameManual) -> None:
        self.manuals[manual.game_id] = manual

    async def get_active_manual(self, game_id: str) -> GameManual | None:
        return self.manuals.get(game_id)

    async def get_manual_by_bgg_id(
        self,
        bgg_id: int,
        edition: str = "standard",
    ) -> GameManual | None:
        return next(
            (m for m in self.manuals.values() if m.bgg_id == bgg_id and m.edition == edition),
            None,
        )

    async def get_manual_by_sha256(self, content_sha256: str) -> GameManual | None:
        return next(
            (m for m in self.manuals.values() if m.content_sha256 == content_sha256),
            None,
        )

    async def list_manuals(self) -> tuple[GameManual, ...]:
        return tuple(self.manuals.values())

    async def save_pending_pdf(self, pending_pdf: PendingPdfManual) -> None:
        self.pending_pdfs[pending_pdf.file_key] = pending_pdf

    async def list_pending_pdfs(self) -> tuple[PendingPdfManual, ...]:
        return tuple(self.pending_pdfs.values())

    async def get_pending_pdf_by_key(self, file_key: str) -> PendingPdfManual | None:
        return self.pending_pdfs.get(file_key)

    async def save_history_entry(self, entry: SavedUserEntry) -> None:
        self.history.append(entry)

    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]:
        return tuple(e for e in self.history if e.user_id == user_id)


class _StubRagEngine:
    async def index_chunks(self, chunks: Sequence[RuleChunk]) -> None:
        pass

    async def search_chunks(
        self,
        game_id: str,
        query: str,
        top_k: int = 5,
    ) -> tuple[RuleChunk, ...]:
        return ()

    async def delete_game_chunks(self, game_id: str) -> None:
        pass


class _StubRulebookFetcher:
    async def fetch_rulebook(self, game_title: str) -> FetchedRulebook:
        return FetchedRulebook(
            game_title=game_title,
            source_url="https://example.com/rules.pdf",
            pdf_bytes=b"%PDF-1.7",
        )


class _StubAiGenerator:
    async def generate_fallback_rules(self, game_title: str) -> str:
        return f"# Rules for {game_title}"

    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> str:
        return f"Quick recap for {game_title}"

    async def answer_question(
        self,
        game_title: str,
        question: str,
        chunks: Sequence[RuleChunk],
    ) -> str:
        return "42"


class _StubPdfStorage:
    async def list_unprocessed_keys(self) -> tuple[str, ...]:
        return ("incoming/catan.pdf",)

    async def read_pdf_bytes(self, file_key: str) -> bytes:
        return b"%PDF-1.7"

    async def move_to_processed(self, file_key: str) -> None:
        pass

    async def move_to_failed(self, file_key: str) -> None:
        pass


def test_should_satisfy_both_segregated_and_composite_nosql_protocols(
    sample_user: UserProfile,
    sample_manual: GameManual,
) -> None:
    repo = _InMemoryNoSqlStub()

    async def _exercise_repo() -> tuple[UserProfile | None, GameManual | None]:
        await repo.save_user(sample_user)
        await repo.save_manual(sample_manual)
        return (
            await repo.get_user_by_google_sub(sample_user.google_sub),
            await repo.get_active_manual(sample_manual.game_id),
        )

    fetched_user, fetched_manual = asyncio.run(_exercise_repo())

    assert isinstance(repo, UserRepository)
    assert isinstance(repo, GameManualRepository)
    assert isinstance(repo, PendingPdfRepository)
    assert isinstance(repo, UserHistoryRepository)
    assert isinstance(repo, NoSqlRepository)
    assert fetched_user == sample_user
    assert fetched_manual == sample_manual


def test_should_satisfy_rag_fetcher_ai_and_pdf_storage_protocols(
    sample_chunk: RuleChunk,
) -> None:
    rag = _StubRagEngine()
    fetcher = _StubRulebookFetcher()
    ai = _StubAiGenerator()
    storage = _StubPdfStorage()

    async def _exercise_modules() -> tuple[FetchedRulebook, str, tuple[str, ...]]:
        await rag.index_chunks((sample_chunk,))
        rulebook = await fetcher.fetch_rulebook("Catan")
        recap = await ai.generate_quick_recap("Catan", (sample_chunk,))
        keys = await storage.list_unprocessed_keys()
        return rulebook, recap, keys

    rulebook, recap, keys = asyncio.run(_exercise_modules())

    assert isinstance(rag, RagEngine)
    assert isinstance(fetcher, RulebookFetcher)
    assert isinstance(ai, AiRuleGenerator)
    assert isinstance(storage, PdfStorage)
    assert rulebook.game_title == "Catan"
    assert "Catan" in recap
    assert keys == ("incoming/catan.pdf",)
