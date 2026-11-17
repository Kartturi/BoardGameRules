"""Asynchronous module contracts (Abstract Base Classes) defining architectural boundaries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

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
# CONCEPT: [Design Pattern] Explicit Abstract Base Class (ABC) Ports (Hexagonal Architecture)
# Defining abstract base classes in the inner domain layer without importing concrete drivers
# (MongoDB, Qdrant, GCS, Gemini) makes every adapter's contract immediately visible on its
# class definition line (e.g., `class QdrantRagEngine(RagEngine):`) and fails fast at
# instantiation time if any required @abstractmethod is missing.
#
# CONCEPT: [Design Pattern] Interface Segregation Principle (ISP)
# Instead of forcing every service to depend on a single giant database interface, we split
# persistence into 4 focused repository interfaces (User, GameManual, PendingPdf, UserHistory).
# The Batch PDF Job only needs PendingPdfRepository + GameManualRepository, keeping mocks tiny.
class UserRepository(ABC):
    @abstractmethod
    async def save_user(self, user: UserProfile) -> None: ...

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> UserProfile | None: ...

    @abstractmethod
    async def get_user_by_google_sub(self, google_sub: str) -> UserProfile | None: ...


class GameManualRepository(ABC):
    @abstractmethod
    async def save_manual(self, manual: GameManual) -> None: ...

    @abstractmethod
    async def get_active_manual(self, game_id: str) -> GameManual | None: ...

    @abstractmethod
    async def get_manual_by_bgg_id(
        self,
        bgg_id: int,
        edition: str = "standard",
    ) -> GameManual | None: ...

    @abstractmethod
    async def get_manual_by_sha256(self, content_sha256: str) -> GameManual | None: ...

    @abstractmethod
    async def list_manuals(self) -> tuple[GameManual, ...]: ...


class PendingPdfRepository(ABC):
    @abstractmethod
    async def save_pending_pdf(self, pending_pdf: PendingPdfManual) -> None: ...

    @abstractmethod
    async def list_pending_pdfs(self) -> tuple[PendingPdfManual, ...]: ...

    @abstractmethod
    async def get_pending_pdf_by_key(self, file_key: str) -> PendingPdfManual | None: ...


class UserHistoryRepository(ABC):
    @abstractmethod
    async def save_history_entry(self, entry: SavedUserEntry) -> None: ...

    @abstractmethod
    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]: ...


# CONCEPT: [Design Pattern] Composite Interface Facade
# Combining the 4 segregated repository interfaces into a single composite NoSqlRepository
# interface lets the DI container pass one unified database adapter when needed, while
# individual consumers still type-hint only the narrow sub-interface they require.
class NoSqlRepository(
    UserRepository,
    GameManualRepository,
    PendingPdfRepository,
    UserHistoryRepository,
    ABC,
):
    pass


# CONCEPT: [AI Engineering] Retrieval-Augmented Generation (RAG) Vector Port
# Decouples the vector store (Qdrant) from the rest of the application. The RAG port only
# indexes, searches, and deletes RuleChunks scoped by canonical game_id metadata filters.
class RagEngine(ABC):
    @abstractmethod
    async def index_chunks(self, chunks: Sequence[RuleChunk]) -> None: ...

    @abstractmethod
    async def search_chunks(
        self,
        game_id: str,
        query: str,
        top_k: int = 5,
    ) -> tuple[RuleChunk, ...]: ...

    @abstractmethod
    async def delete_game_chunks(self, game_id: str) -> None: ...


class RulebookFetcher(ABC):
    @abstractmethod
    async def fetch_rulebook(self, game_title: str) -> FetchedRulebook: ...


class AiRuleGenerator(ABC):
    @abstractmethod
    async def generate_fallback_rules(self, game_title: str) -> str: ...

    @abstractmethod
    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> str: ...

    @abstractmethod
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
class PdfStorage(ABC):
    @abstractmethod
    async def list_unprocessed_keys(self) -> tuple[str, ...]: ...

    @abstractmethod
    async def read_pdf_bytes(self, file_key: str) -> bytes: ...

    @abstractmethod
    async def move_to_processed(self, file_key: str) -> None: ...

    @abstractmethod
    async def move_to_failed(self, file_key: str) -> None: ...
