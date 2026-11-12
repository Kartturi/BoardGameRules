"""Asynchronous module contracts (Protocols) defining architectural boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from boardgamerules.domain.manual import FetchedRulebook, GameManual, PendingPdfManual
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.domain.user import SavedUserEntry, UserProfile


# CONCEPT: [System Design] Asynchronous I/O for High-Concurrency LLM Workloads
# Unlike traditional CRUD apps (where DB queries take ~3ms), AI/RAG workloads wait 2-8 seconds
# on external LLM generation, embedding APIs, and vector searches. Using async def contracts
# allows a single GCP Cloud Run container's event loop to serve hundreds of concurrent users
# waiting on I/O without blocking OS threads or spinning up costly extra containers, and
# enables parallel I/O fan-out via asyncio.gather().
#
# CONCEPT: [Design Pattern] Structural Subtyping (Ports & Adapters / Hexagonal Architecture)
# Using typing.Protocol defines "ports" in the inner domain layer without importing concrete
# drivers (MongoDB, Qdrant, GCS, Gemini). Any adapter class that implements matching method
# signatures satisfies the contract automatically without needing class inheritance.
#
# CONCEPT: [Design Pattern] Runtime-Checkable Protocols (@runtime_checkable)
# By default, typing.Protocol only exists for static type checkers (PyCharm, mypy) and fails
# if used with isinstance() at runtime. Decorating with @runtime_checkable allows runtime
# isinstance(obj, Protocol) checks by verifying that the required method names exist on obj,
# while static type checkers still enforce full parameter, return, and async coroutine types.
#
# CONCEPT: [Design Pattern] Interface Segregation Principle (ISP)
# Instead of forcing every service to depend on a single giant database interface, we split
# persistence into 4 focused repository protocols (User, GameManual, PendingPdf, UserHistory).
# The Batch PDF Job only needs PendingPdfRepository + GameManualRepository, keeping mocks tiny.
@runtime_checkable
class UserRepository(Protocol):
    async def save_user(self, user: UserProfile) -> None: ...

    async def get_user_by_id(self, user_id: str) -> UserProfile | None: ...

    async def get_user_by_google_sub(self, google_sub: str) -> UserProfile | None: ...


@runtime_checkable
class GameManualRepository(Protocol):
    async def save_manual(self, manual: GameManual) -> None: ...

    async def get_active_manual(self, game_id: str) -> GameManual | None: ...

    async def get_manual_by_bgg_id(
        self,
        bgg_id: int,
        edition: str = "standard",
    ) -> GameManual | None: ...

    async def get_manual_by_sha256(self, content_sha256: str) -> GameManual | None: ...

    async def list_manuals(self) -> tuple[GameManual, ...]: ...


@runtime_checkable
class PendingPdfRepository(Protocol):
    async def save_pending_pdf(self, pending_pdf: PendingPdfManual) -> None: ...

    async def list_pending_pdfs(self) -> tuple[PendingPdfManual, ...]: ...

    async def get_pending_pdf_by_key(self, file_key: str) -> PendingPdfManual | None: ...


@runtime_checkable
class UserHistoryRepository(Protocol):
    async def save_history_entry(self, entry: SavedUserEntry) -> None: ...

    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]: ...


# CONCEPT: [Design Pattern] Composite Interface Facade
# Combining the 4 segregated repository protocols into a single composite NoSqlRepository
# protocol lets the DI container pass one unified database adapter when needed, while
# individual consumers still type-hint only the narrow sub-protocol they require.
@runtime_checkable
class NoSqlRepository(
    UserRepository,
    GameManualRepository,
    PendingPdfRepository,
    UserHistoryRepository,
    Protocol,
):
    pass


# CONCEPT: [AI Engineering] Retrieval-Augmented Generation (RAG) Vector Port
# Decouples the vector store (Qdrant) from the rest of the application. The RAG port only
# indexes, searches, and deletes RuleChunks scoped by canonical game_id metadata filters.
@runtime_checkable
class RagEngine(Protocol):
    async def index_chunks(self, chunks: Sequence[RuleChunk]) -> None: ...

    async def search_chunks(
        self,
        game_id: str,
        query: str,
        top_k: int = 5,
    ) -> tuple[RuleChunk, ...]: ...

    async def delete_game_chunks(self, game_id: str) -> None: ...


@runtime_checkable
class RulebookFetcher(Protocol):
    async def fetch_rulebook(self, game_title: str) -> FetchedRulebook: ...


@runtime_checkable
class AiRuleGenerator(Protocol):
    async def generate_fallback_rules(self, game_title: str) -> str: ...

    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> str: ...

    async def answer_question(
        self,
        game_title: str,
        question: str,
        chunks: Sequence[RuleChunk],
    ) -> str: ...


# CONCEPT: [System Design] Cloud-Agnostic Blob Storage Abstraction
# Cloud Run containers have ephemeral filesystems. Abstracting PDF file operations behind
# PdfStorage lets local development use a local directory while GCP Cloud Run Jobs use a
# Google Cloud Storage (GCS) bucket with zero changes to the batch ingestion logic.
@runtime_checkable
class PdfStorage(Protocol):
    async def list_unprocessed_keys(self) -> tuple[str, ...]: ...

    async def read_pdf_bytes(self, file_key: str) -> bytes: ...

    async def move_to_processed(self, file_key: str) -> None: ...

    async def move_to_failed(self, file_key: str) -> None: ...
