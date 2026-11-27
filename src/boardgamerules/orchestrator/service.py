"""Central rule orchestrator coordinating the 3-tier rule resolution pipeline and user history."""

from __future__ import annotations

import asyncio
import logging
import uuid

from boardgamerules.domain.ai import QuickRecap
from boardgamerules.domain.contracts import (
    AiRuleGenerator,
    GameManualRepository,
    RagEngine,
    RulebookFetcher,
    UserHistoryRepository,
)
from boardgamerules.domain.enums import ManualSource, ManualStatus
from boardgamerules.domain.exceptions import (
    DomainValidationError,
    ExternalRuleFetchError,
    ManualNotFoundError,
    RagIngestionError,
    RulebookNotFoundError,
)
from boardgamerules.domain.manual import GameManual
from boardgamerules.domain.rag import RuleAnswer
from boardgamerules.domain.user import SavedUserEntry
from boardgamerules.domain.validators import normalize_game_id, require_non_blank
from boardgamerules.orchestrator.models import (
    OrchestratorDependencies,
    ResolvedRules,
    SaveUserEntryRequest,
)
from boardgamerules.rag.ingestion import PdfIngestionOptions, ingest_pdf_rulebook
from boardgamerules.rag.qa import RulebookQuestion, answer_rulebook_question

logger = logging.getLogger(__name__)


# CONCEPT: [Design Pattern] Facade & Chain of Responsibility (3-Tier Rule Resolution)
# RuleOrchestrator acts as a simplified entry-point (Facade) hiding multi-database, vector store,
# web search, and LLM complexity. It coordinates a Chain of Responsibility across three tiers:
# Tier 1 checks local cache (MongoDB/Qdrant); if missing, Tier 2 attempts online search and
# PDF ingestion; if unavailable, Tier 3 falls back to schema-constrained generative AI.
class RuleOrchestrator:
    def __init__(self, dependencies: OrchestratorDependencies) -> None:
        self._manual_repo: GameManualRepository = dependencies.manual_repo
        self._history_repo: UserHistoryRepository = dependencies.history_repo
        self._rag_engine: RagEngine = dependencies.rag_engine
        self._rulebook_fetcher: RulebookFetcher = dependencies.rulebook_fetcher
        self._ai_generator: AiRuleGenerator = dependencies.ai_generator
        self._ingestion_options = PdfIngestionOptions(
            pdf_extractor=dependencies.pdf_extractor,
            chunking_config=dependencies.chunking_config,
        )
        self._resolution_locks: dict[str, asyncio.Lock] = {}

    # CONCEPT: [System Design] Single-Flight Per-Key Concurrency Lock
    # When multiple concurrent requests demand the same uncached game rulebook simultaneously,
    # acquiring a per-game lock with double-checked caching ensures the system fetches, chunks,
    # and indexes the document only once instead of causing duplicate API calls or race conditions.
    async def resolve_rules(self, game_title: str) -> ResolvedRules:
        require_non_blank(game_title, "game_title")
        clean_title = game_title.strip()
        game_id = normalize_game_id(clean_title)

        existing = await self._manual_repo.get_active_manual(game_id)
        if existing is not None:
            logger.info(
                "Resolved game rules from cache",
                extra={"game_id": game_id, "source": existing.source.value, "from_cache": True},
            )
            return ResolvedRules(manual=existing, from_cache=True)

        async with self._get_resolution_lock(game_id):
            existing_locked = await self._manual_repo.get_active_manual(game_id)
            if existing_locked is not None:
                logger.info(
                    "Resolved game rules from cache after lock acquisition",
                    extra={
                        "game_id": game_id,
                        "source": existing_locked.source.value,
                        "from_cache": True,
                    },
                )
                return ResolvedRules(manual=existing_locked, from_cache=True)

            return await self._fetch_or_fallback_rules(game_id=game_id, clean_title=clean_title)

    async def generate_quick_recap(self, game_title: str, top_k: int = 8) -> QuickRecap:
        _validate_top_k(top_k)
        resolved = await self.resolve_rules(game_title)

        if resolved.manual.is_verified:
            chunks = await self._rag_engine.search_chunks(
                game_id=resolved.manual.game_id,
                query=_QUICK_RECAP_QUERY,
                top_k=top_k,
            )
            if not chunks:
                logger.warning(
                    "Verified manual has no indexed chunks in Qdrant; "
                    "generating ungrounded quick recap",
                    extra={
                        "game_id": resolved.manual.game_id,
                        "source": resolved.manual.source.value,
                    },
                )
        else:
            chunks = ()

        return await self._ai_generator.generate_quick_recap(
            game_title=resolved.manual.game_title,
            chunks=chunks,
        )

    async def ask_question(
        self,
        game_title: str,
        question: str,
        top_k: int = 5,
    ) -> RuleAnswer:
        require_non_blank(question, "question")
        _validate_top_k(top_k)
        resolved = await self.resolve_rules(game_title)

        if resolved.manual.is_verified:
            try:
                return await answer_rulebook_question(
                    rag_engine=self._rag_engine,
                    ai_generator=self._ai_generator,
                    query=RulebookQuestion(
                        game_id=resolved.manual.game_id,
                        game_title=resolved.manual.game_title,
                        question=question,
                        top_k=top_k,
                        source=resolved.manual.source,
                    ),
                )
            except ManualNotFoundError:
                logger.warning(
                    "Verified manual has no indexed chunks in Qdrant; "
                    "falling back to ungrounded AI answer",
                    extra={
                        "game_id": resolved.manual.game_id,
                        "question_length": len(question),
                    },
                )

        return await self._answer_ungrounded_question(resolved.manual, question)

    async def save_user_entry(self, request: SaveUserEntryRequest) -> SavedUserEntry:
        entry = SavedUserEntry(
            entry_id=f"entry-{uuid.uuid4().hex[:12]}",
            user_id=request.user_id.strip(),
            game_id=normalize_game_id(request.game_title),
            game_title=request.game_title.strip(),
            entry_type=request.entry_type,
            prompt_or_heading=request.prompt_or_heading.strip(),
            content_markdown=request.content_markdown.strip(),
            source=request.source,
        )
        await self._history_repo.save_history_entry(entry)
        logger.info(
            "Saved user history entry",
            extra={
                "game_id": entry.game_id,
                "entry_type": entry.entry_type.value,
                "source": entry.source.value,
            },
        )
        return entry

    async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]:
        require_non_blank(user_id, "user_id")
        return await self._history_repo.list_user_history(user_id.strip())

    def _get_resolution_lock(self, game_id: str) -> asyncio.Lock:
        lock = self._resolution_locks.get(game_id)
        if lock is None:
            lock = asyncio.Lock()
            self._resolution_locks[game_id] = lock
        return lock

    async def _fetch_or_fallback_rules(
        self,
        game_id: str,
        clean_title: str,
    ) -> ResolvedRules:
        try:
            return await self._fetch_internet_rules(game_id, clean_title)
        except (RulebookNotFoundError, ExternalRuleFetchError, RagIngestionError) as exc:
            should_cache = isinstance(exc, RulebookNotFoundError)
            logger.warning(
                "Tier-2 rulebook fetch or ingestion failed; falling back to AI generation",
                extra={
                    "game_id": game_id,
                    "error_type": type(exc).__name__,
                    "will_cache_fallback": should_cache,
                },
            )
            return await self._resolve_via_ai_fallback(
                game_id=game_id,
                game_title=clean_title,
                persist=should_cache,
            )

    async def _fetch_internet_rules(
        self,
        game_id: str,
        clean_title: str,
    ) -> ResolvedRules:
        fetched = await self._rulebook_fetcher.fetch_rulebook(clean_title)
        content_sha256 = fetched.content_sha256
        chunks = await ingest_pdf_rulebook(
            game_id=game_id,
            pdf_bytes=fetched.pdf_bytes,
            rag_engine=self._rag_engine,
            options=self._ingestion_options,
        )
        manual = GameManual(
            manual_id=f"manual-{game_id}-{uuid.uuid4().hex[:8]}",
            game_id=game_id,
            game_title=fetched.game_title.strip(),
            source=ManualSource.INTERNET_API,
            edition=fetched.edition,
            status=ManualStatus.READY,
            source_url_or_path=fetched.source_url,
            bgg_id=fetched.bgg_id,
            product_code=fetched.product_code,
            content_sha256=content_sha256,
        )
        await self._manual_repo.save_manual(manual)
        logger.info(
            "Resolved game rules via internet fetch and ingested into RAG",
            extra={
                "game_id": game_id,
                "source": manual.source.value,
                "chunk_count": len(chunks),
                "from_cache": False,
            },
        )
        return ResolvedRules(manual=manual, from_cache=False)

    async def _resolve_via_ai_fallback(
        self,
        game_id: str,
        game_title: str,
        persist: bool,
    ) -> ResolvedRules:
        fallback = await self._ai_generator.generate_fallback_rules(game_title)
        manual = GameManual(
            manual_id=f"manual-{game_id}-{uuid.uuid4().hex[:8]}",
            game_id=game_id,
            game_title=game_title,
            source=ManualSource.AI_GENERATED,
            status=ManualStatus.READY,
            summary_markdown=fallback.to_markdown(),
        )
        if persist:
            await self._manual_repo.save_manual(manual)

        logger.info(
            "Resolved game rules via AI fallback",
            extra={
                "game_id": game_id,
                "source": manual.source.value,
                "persisted": persist,
                "from_cache": False,
            },
        )
        return ResolvedRules(manual=manual, from_cache=False)

    async def _answer_ungrounded_question(
        self,
        manual: GameManual,
        question: str,
    ) -> RuleAnswer:
        generated = await self._ai_generator.answer_question(
            game_title=manual.game_title,
            question=question,
            chunks=(),
        )
        return RuleAnswer(
            game_id=manual.game_id,
            question=question,
            answer_markdown=generated.answer_text,
            citations=(),
            source=ManualSource.AI_GENERATED,
            found_in_rules=False,
        )


_MAX_TOP_K = 50
_QUICK_RECAP_QUERY = "game objective setup turn structure winning conditions key rules"


def _validate_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1 or top_k > _MAX_TOP_K:
        raise DomainValidationError(f"top_k must be an integer between 1 and {_MAX_TOP_K}.")
