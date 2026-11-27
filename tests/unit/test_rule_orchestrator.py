"""Comprehensive offline unit tests for RuleOrchestrator ($0.00 token cost)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from qdrant_client import AsyncQdrantClient

from boardgamerules.db.in_memory import (
    InMemoryGameManualRepository,
    InMemoryUserHistoryRepository,
)
from boardgamerules.domain.ai import GeneratedRuleAnswer, GeneratedRulebook, QuickRecap
from boardgamerules.domain.contracts import AiRuleGenerator, RulebookFetcher
from boardgamerules.domain.enums import ManualSource, ManualStatus, SavedEntryType
from boardgamerules.domain.exceptions import (
    DomainValidationError,
    ExternalRuleFetchError,
    RagIngestionError,
    RulebookNotFoundError,
    StorageOperationError,
)
from boardgamerules.domain.manual import FetchedRulebook, GameManual
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.orchestrator.models import (
    OrchestratorDependencies,
    SaveUserEntryRequest,
)
from boardgamerules.orchestrator.service import RuleOrchestrator
from boardgamerules.rag.chunker import ChunkingConfig
from boardgamerules.rag.embeddings import DeterministicEmbeddingProvider
from boardgamerules.rag.pdf_extractor import PdfPageText, PdfTextExtractor
from boardgamerules.rag.qdrant_engine import QdrantRagEngine


class _FakePdfTextExtractor(PdfTextExtractor):
    def __init__(self, pages: Sequence[PdfPageText] | None = None) -> None:
        self.pages = tuple(
            pages
            or (
                PdfPageText(page_number=1, text="1. Setup\nPlace board in center."),
                PdfPageText(page_number=2, text="2. Turn Structure\nRoll dice and trade."),
            )
        )

    def extract_pages(self, pdf_bytes: bytes) -> tuple[PdfPageText, ...]:
        if not pdf_bytes:
            raise DomainValidationError("pdf_bytes cannot be empty.")
        return self.pages


class _FakeRulebookFetcher(RulebookFetcher):
    def __init__(
        self,
        rulebooks: dict[str, FetchedRulebook] | None = None,
        exception_to_raise: Exception | None = None,
    ) -> None:
        self.rulebooks = rulebooks or {}
        self.exception_to_raise = exception_to_raise
        self.call_count = 0
        self.last_title: str | None = None

    async def fetch_rulebook(self, game_title: str) -> FetchedRulebook:
        self.call_count += 1
        self.last_title = game_title
        if self.exception_to_raise is not None:
            raise self.exception_to_raise
        if game_title in self.rulebooks:
            return self.rulebooks[game_title]
        raise RulebookNotFoundError(game_title)


class _FakeAiRuleGenerator(AiRuleGenerator):
    def __init__(self) -> None:
        self.fallback_call_count = 0
        self.recap_call_count = 0
        self.qa_call_count = 0
        self.last_recap_chunks: Sequence[RuleChunk] = ()
        self.last_qa_chunks: Sequence[RuleChunk] = ()

    async def generate_fallback_rules(self, game_title: str) -> GeneratedRulebook:
        self.fallback_call_count += 1
        return GeneratedRulebook(
            game_title=game_title,
            overview=f"Overview of {game_title}",
            setup_steps=("Step 1: Setup board", "Step 2: Deal cards"),
            turn_structure=("Action 1: Play card", "Action 2: Draw card"),
            winning_condition="First to 10 victory points wins.",
            key_rules=("Rule 1: No trading with bank",),
        )

    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> QuickRecap:
        self.recap_call_count += 1
        self.last_recap_chunks = chunks
        is_grounded = bool(chunks)
        cited_ids = tuple(c.chunk_id for c in chunks[:1]) if is_grounded else ()
        return QuickRecap(
            game_title=game_title,
            goal=f"Reach goal in {game_title}",
            turn_summary=("Roll and move",),
            setup_highlights=("Place tokens",),
            key_rules_to_remember=("Watch out for thief",),
            is_grounded=is_grounded,
            cited_chunk_ids=cited_ids,
        )

    async def answer_question(
        self,
        game_title: str,
        question: str,
        chunks: Sequence[RuleChunk],
    ) -> GeneratedRuleAnswer:
        self.qa_call_count += 1
        self.last_qa_chunks = chunks
        is_grounded = bool(chunks)
        cited_ids = tuple(c.chunk_id for c in chunks[:1]) if is_grounded else ()
        return GeneratedRuleAnswer(
            answer_text=f"Answer for {question} in {game_title}",
            found_in_rules=is_grounded,
            cited_chunk_ids=cited_ids,
            is_grounded=is_grounded,
        )


class _FailingGameManualRepository(InMemoryGameManualRepository):
    async def get_active_manual(self, game_id: str) -> GameManual | None:
        raise StorageOperationError("Database connection lost.")

    async def save_manual(self, manual: GameManual) -> None:
        raise StorageOperationError("Database write failed.")


@pytest.fixture
def memory_rag_engine() -> QdrantRagEngine:
    client = AsyncQdrantClient(location=":memory:")
    embedder = DeterministicEmbeddingProvider(vector_size=32)
    return QdrantRagEngine(
        client=client,
        embedder=embedder,
        collection_name="test_orchestrator_rules",
        vector_size=32,
    )


@pytest.fixture
def base_dependencies(memory_rag_engine: QdrantRagEngine) -> OrchestratorDependencies:
    return OrchestratorDependencies(
        manual_repo=InMemoryGameManualRepository(),
        history_repo=InMemoryUserHistoryRepository(),
        rag_engine=memory_rag_engine,
        rulebook_fetcher=_FakeRulebookFetcher(),
        ai_generator=_FakeAiRuleGenerator(),
        pdf_extractor=_FakePdfTextExtractor(),
        chunking_config=ChunkingConfig(),
    )


@pytest.mark.anyio
async def test_should_return_cached_manual_without_calling_fetcher_or_ai_when_tier1_manual_exists(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    existing_manual = GameManual(
        manual_id="manual-catan-001",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.MANUAL_PDF,
        status=ManualStatus.READY,
        summary_markdown="# Catan Rules",
    )
    await base_dependencies.manual_repo.save_manual(existing_manual)
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    resolved = await orchestrator.resolve_rules("Catan")

    # Assert
    assert resolved.from_cache is True
    assert resolved.manual == existing_manual
    assert base_dependencies.rulebook_fetcher.call_count == 0  # type: ignore[attr-defined]
    assert base_dependencies.ai_generator.fallback_call_count == 0  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_should_fetch_ingest_and_persist_internet_manual_when_tier1_misses(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    sample_pdf = b"%PDF-1.4 sample pdf content for Wingspan"
    fetched = FetchedRulebook(
        game_title="Wingspan",
        source_url="https://stonemaiergames.com/wingspan.pdf",
        pdf_bytes=sample_pdf,
        edition="second",
        bgg_id=266192,
        product_code="STM900",
    )
    fetcher = _FakeRulebookFetcher(rulebooks={"Wingspan": fetched})
    deps = OrchestratorDependencies(
        manual_repo=base_dependencies.manual_repo,
        history_repo=base_dependencies.history_repo,
        rag_engine=base_dependencies.rag_engine,
        rulebook_fetcher=fetcher,
        ai_generator=base_dependencies.ai_generator,
        pdf_extractor=base_dependencies.pdf_extractor,
        chunking_config=base_dependencies.chunking_config,
    )
    orchestrator = RuleOrchestrator(deps)

    # Act
    resolved = await orchestrator.resolve_rules("Wingspan")

    # Assert
    assert resolved.from_cache is False
    assert resolved.manual.game_id == "wingspan"
    assert resolved.manual.game_title == "Wingspan"
    assert resolved.manual.source == ManualSource.INTERNET_API
    assert resolved.manual.edition == "second"
    assert resolved.manual.bgg_id == 266192
    assert resolved.manual.product_code == "STM900"
    assert resolved.manual.source_url_or_path == "https://stonemaiergames.com/wingspan.pdf"
    assert resolved.manual.is_verified is True

    # Verify persisted in MongoDB
    saved = await deps.manual_repo.get_active_manual("wingspan")
    assert saved is not None
    assert saved.manual_id == resolved.manual.manual_id

    # Verify chunks ingested into Qdrant
    chunks = await deps.rag_engine.search_chunks(game_id="wingspan", query="Setup", top_k=5)
    assert len(chunks) > 0


@pytest.mark.anyio
async def test_should_fallback_to_ai_and_cache_manual_when_tier2_raises_rulebook_not_found(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    resolved = await orchestrator.resolve_rules("Unknown Game 123")

    # Assert
    assert resolved.from_cache is False
    assert resolved.manual.game_id == "unknown-game-123"
    assert resolved.manual.source == ManualSource.AI_GENERATED
    assert resolved.manual.is_verified is False
    assert "Overview of Unknown Game 123" in resolved.manual.summary_markdown
    assert base_dependencies.ai_generator.fallback_call_count == 1  # type: ignore[attr-defined]

    # Conclusive 404 must be cached in MongoDB
    persisted = await base_dependencies.manual_repo.get_active_manual("unknown-game-123")
    assert persisted is not None
    assert persisted.manual_id == resolved.manual.manual_id

    # Verify next call hits Tier 1 cache
    second_resolved = await orchestrator.resolve_rules("Unknown Game 123")
    assert second_resolved.from_cache is True
    assert base_dependencies.ai_generator.fallback_call_count == 1  # type: ignore[attr-defined]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "transient_error",
    [
        ExternalRuleFetchError("Network timeout connecting to publisher."),
        RagIngestionError("Corrupt PDF bytes could not be parsed."),
    ],
)
async def test_should_fallback_to_ai_without_caching_on_transient_fetch_or_ingestion_error(
    base_dependencies: OrchestratorDependencies,
    transient_error: Exception,
) -> None:
    # Arrange
    fetcher = _FakeRulebookFetcher(exception_to_raise=transient_error)
    deps = OrchestratorDependencies(
        manual_repo=base_dependencies.manual_repo,
        history_repo=base_dependencies.history_repo,
        rag_engine=base_dependencies.rag_engine,
        rulebook_fetcher=fetcher,
        ai_generator=base_dependencies.ai_generator,
        pdf_extractor=base_dependencies.pdf_extractor,
        chunking_config=base_dependencies.chunking_config,
    )
    orchestrator = RuleOrchestrator(deps)

    # Act
    resolved = await orchestrator.resolve_rules("Carcassonne")

    # Assert
    assert resolved.from_cache is False
    assert resolved.manual.source == ManualSource.AI_GENERATED

    # Transient error must NOT be cached in MongoDB so future requests can retry Tier 2
    cached = await deps.manual_repo.get_active_manual("carcassonne")
    assert cached is None


@pytest.mark.anyio
async def test_should_deduplicate_concurrent_resolutions_for_same_game_using_single_flight_lock(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    class _SlowFetcher(RulebookFetcher):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_rulebook(self, game_title: str) -> FetchedRulebook:
            self.calls += 1
            await asyncio.sleep(0.05)
            return FetchedRulebook(
                game_title=game_title,
                source_url="https://example.com/rules.pdf",
                pdf_bytes=b"%PDF-1.4 dummy",
            )

    slow_fetcher = _SlowFetcher()
    deps = OrchestratorDependencies(
        manual_repo=base_dependencies.manual_repo,
        history_repo=base_dependencies.history_repo,
        rag_engine=base_dependencies.rag_engine,
        rulebook_fetcher=slow_fetcher,
        ai_generator=base_dependencies.ai_generator,
        pdf_extractor=base_dependencies.pdf_extractor,
        chunking_config=base_dependencies.chunking_config,
    )
    orchestrator = RuleOrchestrator(deps)

    # Act - run 3 simultaneous resolution requests for the exact same uncached game
    results = await asyncio.gather(
        orchestrator.resolve_rules("Azul"),
        orchestrator.resolve_rules("Azul"),
        orchestrator.resolve_rules("Azul"),
    )

    # Assert
    assert slow_fetcher.calls == 1
    assert len(results) == 3
    # Exactly one executed fetch (from_cache=False), others caught the cache inside the lock
    cache_flags = [r.from_cache for r in results]
    assert cache_flags.count(False) == 1
    assert cache_flags.count(True) == 2


@pytest.mark.anyio
async def test_should_propagate_storage_error_without_falling_back_to_ai_when_manual_repo_fails(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    deps = OrchestratorDependencies(
        manual_repo=_FailingGameManualRepository(),
        history_repo=base_dependencies.history_repo,
        rag_engine=base_dependencies.rag_engine,
        rulebook_fetcher=base_dependencies.rulebook_fetcher,
        ai_generator=base_dependencies.ai_generator,
        pdf_extractor=base_dependencies.pdf_extractor,
        chunking_config=base_dependencies.chunking_config,
    )
    orchestrator = RuleOrchestrator(deps)

    # Act & Assert - database crash must fail fast and not hallucinate AI rules
    with pytest.raises(StorageOperationError, match="Database connection lost"):
        await orchestrator.resolve_rules("Catan")


@pytest.mark.anyio
async def test_should_generate_grounded_quick_recap_from_rag_chunks_when_verified_manual_exists(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    existing_manual = GameManual(
        manual_id="manual-ticket-to-ride-01",
        game_id="ticket-to-ride",
        game_title="Ticket to Ride",
        source=ManualSource.MANUAL_PDF,
        status=ManualStatus.READY,
    )
    await base_dependencies.manual_repo.save_manual(existing_manual)
    await base_dependencies.rag_engine.index_chunks(
        (
            RuleChunk(
                chunk_id="chunk-ttr-001",
                game_id="ticket-to-ride",
                text="Collect train cards to claim routes across North America.",
                page_number=1,
                section_title="Objective",
            ),
        )
    )
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    recap = await orchestrator.generate_quick_recap("Ticket to Ride", top_k=5)

    # Assert
    assert recap.is_grounded is True
    assert "chunk-ttr-001" in recap.cited_chunk_ids
    assert len(base_dependencies.ai_generator.last_recap_chunks) == 1  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_should_generate_ungrounded_quick_recap_when_resolved_manual_is_ai_generated(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    ai_manual = GameManual(
        manual_id="manual-custom-game-01",
        game_id="custom-game",
        game_title="Custom Game",
        source=ManualSource.AI_GENERATED,
        status=ManualStatus.READY,
        summary_markdown="# Custom Game",
    )
    await base_dependencies.manual_repo.save_manual(ai_manual)
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    recap = await orchestrator.generate_quick_recap("Custom Game")

    # Assert
    assert recap.is_grounded is False
    assert recap.cited_chunk_ids == ()
    assert base_dependencies.ai_generator.last_recap_chunks == ()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_should_warn_and_generate_ungrounded_recap_when_verified_manual_lacks_chunks(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    # Verified in MongoDB, but Qdrant has 0 chunks for this game
    verified_manual = GameManual(
        manual_id="manual-splendor-01",
        game_id="splendor",
        game_title="Splendor",
        source=ManualSource.MANUAL_PDF,
        status=ManualStatus.READY,
    )
    await base_dependencies.manual_repo.save_manual(verified_manual)
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    recap = await orchestrator.generate_quick_recap("Splendor")

    # Assert - gracefully produces ungrounded recap instead of crashing
    assert recap.is_grounded is False
    assert base_dependencies.ai_generator.last_recap_chunks == ()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_should_answer_grounded_question_with_citations_when_verified_manual_exists(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    manual = GameManual(
        manual_id="manual-dune-01",
        game_id="dune-imperium",
        game_title="Dune: Imperium",
        source=ManualSource.MANUAL_PDF,
        status=ManualStatus.READY,
    )
    await base_dependencies.manual_repo.save_manual(manual)
    await base_dependencies.rag_engine.index_chunks(
        (
            RuleChunk(
                chunk_id="chunk-dune-p4",
                game_id="dune-imperium",
                text="Water is required to deploy troops into the deep desert.",
                page_number=4,
                section_title="Deployment",
            ),
        )
    )
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    answer = await orchestrator.ask_question("Dune: Imperium", "How do I deploy troops?")

    # Assert
    assert answer.found_in_rules is True
    assert answer.is_verified is True
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk_id == "chunk-dune-p4"


@pytest.mark.anyio
async def test_should_answer_ungrounded_question_when_manual_is_ai_generated_or_drifts(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    ai_manual = GameManual(
        manual_id="manual-space-alert-01",
        game_id="space-alert",
        game_title="Space Alert",
        source=ManualSource.AI_GENERATED,
        status=ManualStatus.READY,
        summary_markdown="# Space Alert",
    )
    await base_dependencies.manual_repo.save_manual(ai_manual)
    orchestrator = RuleOrchestrator(base_dependencies)

    # Act
    answer = await orchestrator.ask_question("Space Alert", "How long is a phase?")

    # Assert
    assert answer.found_in_rules is False
    assert answer.is_verified is False
    assert answer.citations == ()
    assert "Space Alert" in answer.answer_markdown


@pytest.mark.anyio
async def test_should_save_and_list_user_history_entries_for_rules_recaps_and_qa_answers(
    base_dependencies: OrchestratorDependencies,
) -> None:
    # Arrange
    orchestrator = RuleOrchestrator(base_dependencies)
    request1 = SaveUserEntryRequest(
        user_id="user_alice",
        game_title="Pandemic",
        entry_type=SavedEntryType.FULL_RULES,
        prompt_or_heading="Rules for Pandemic",
        content_markdown="# Pandemic Rules Summary",
        source=ManualSource.MANUAL_PDF,
    )
    request2 = SaveUserEntryRequest(
        user_id="user_alice",
        game_title="Pandemic",
        entry_type=SavedEntryType.QA_ANSWER,
        prompt_or_heading="How does an outbreak occur?",
        content_markdown="When a city exceeds 3 disease cubes.",
        source=ManualSource.MANUAL_PDF,
    )

    # Act
    saved1 = await orchestrator.save_user_entry(request1)
    saved2 = await orchestrator.save_user_entry(request2)
    history = await orchestrator.list_user_history("user_alice")

    # Assert
    assert saved1.game_id == "pandemic"
    assert saved1.entry_type == SavedEntryType.FULL_RULES
    assert saved2.entry_type == SavedEntryType.QA_ANSWER
    assert len(history) == 2
    history_ids = {h.entry_id for h in history}
    assert saved1.entry_id in history_ids
    assert saved2.entry_id in history_ids
    # list_user_history is sorted latest first (reverse=True by created_at)
    assert history[0].entry_id == saved2.entry_id
    assert history[1].entry_id == saved1.entry_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("game_title", "question", "top_k", "user_id"),
    [
        ("", "How to play?", 5, "u1"),
        ("   ", "How to play?", 5, "u1"),
        ("!@#$%", "How to play?", 5, "u1"),
        ("Catan", "", 5, "u1"),
        ("Catan", "   ", 5, "u1"),
        ("Catan", "How to play?", 0, "u1"),
        ("Catan", "How to play?", 51, "u1"),
        ("Catan", "How to play?", True, "u1"),
        ("Catan", "How to play?", 5, ""),
        ("Catan", "How to play?", 5, "   "),
    ],
)
async def test_should_fail_fast_with_validation_error_when_inputs_or_top_k_are_invalid(
    base_dependencies: OrchestratorDependencies,
    game_title: str,
    question: str,
    top_k: int,
    user_id: str,
) -> None:
    orchestrator = RuleOrchestrator(base_dependencies)

    # Test resolve_rules validation
    if not game_title.strip() or game_title == "!@#$%":
        with pytest.raises(DomainValidationError):
            await orchestrator.resolve_rules(game_title)

    # Test ask_question validation
    if not question.strip() or not (1 <= top_k <= 50 and not isinstance(top_k, bool)):
        with pytest.raises(DomainValidationError):
            await orchestrator.ask_question("Catan", question=question, top_k=top_k)

    # Test generate_quick_recap validation
    if not (1 <= top_k <= 50 and not isinstance(top_k, bool)):
        with pytest.raises(DomainValidationError):
            await orchestrator.generate_quick_recap("Catan", top_k=top_k)

    # Test list_user_history validation
    if not user_id.strip():
        with pytest.raises(DomainValidationError):
            await orchestrator.list_user_history(user_id)
