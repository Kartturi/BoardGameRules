# Task 8: Rule Orchestrator ("Organisation Body")

## Objective
Implement the central orchestrator service that coordinates the 3-tier rule resolution pipeline (`RAG -> Internet API + RAG -> AI Fallback`).

## Requirements
- Resolve game rule requests in strict priority order:
  1. Check if the game manual is already indexed in the RAG system / NoSQL DB.
  2. If missing, invoke the Internet API Fetcher; if found, ingest into RAG and return.
  3. If internet fetch fails, invoke the AI Fallback module to generate the rules.
- Coordinate Quick Recap generation and specific rule Q&A against the active game.
- Allow users to save generated rules, recaps, and Q&A answers into their NoSQL user history.
- Add unit tests covering all 3 resolution paths and failure fallbacks.

---

## Technical Implementation Plan (Approved Design — Execute Step 5 Onwards)

> **Execution Notes for Implementation**:
> - Follow `AGENTS.md` strictly: **Stepdown Rule (`§1.9`)** (public classes/functions at top, private `_` helpers at bottom), **no `_and_` in function names (`§1.1`)**, **disambiguate shadowing imports (`§1.1`)**, **no meta-references in comments (`§1.5`)**, **centralized structured logging with zero PII/secrets (`§1.8`)**.
> - All unit tests must run **100% offline ($0.00 API cost)** via `uv run --offline pytest`.
> - After implementation, run `uv run --offline python scripts/collect_concepts.py`, `uv run --offline ruff check --fix .`, `uv run --offline ruff format .`, and `uv run --offline pytest`.
> - Then follow `skills/task-workflow/SKILL.md` Steps 6–9 (Stage 1 AI PR Review -> Stage 2 Human PR Review -> wait for explicit `pr approved` -> Stage 3 Post-Approval AI PR Review -> move to `tasks/done/`, merge, push).

### 1. Files to Create & Modify

1. **Create [`src/boardgamerules/rag/ingestion.py`](../src/boardgamerules/rag/ingestion.py)** — Shared async PDF-to-Qdrant ingestion helper used by both `RuleOrchestrator` and `PdfBatchIngestor`.
2. **Modify [`src/boardgamerules/rag/__init__.py`](../src/boardgamerules/rag/__init__.py)** — Export `PdfIngestionOptions` and `ingest_pdf_rulebook`.
3. **Modify [`src/boardgamerules/batch/ingestor.py`](../src/boardgamerules/batch/ingestor.py)** — Refactor `_ingest_pdf` to delegate extraction, chunking, and Qdrant replacement to `ingest_pdf_rulebook(...)` (removing duplicated `_extract_chunks` and `_replace_chunks_in_qdrant` methods). Keep all existing `tests/unit/test_pdf_batch_ingestor.py` passing without changing public `PdfBatchIngestor` signatures.
4. **Create [`src/boardgamerules/orchestrator/models.py`](../src/boardgamerules/orchestrator/models.py)** — Frozen dataclasses: `OrchestratorDependencies`, `ResolvedRules`, `SaveUserEntryRequest`.
5. **Create [`src/boardgamerules/orchestrator/service.py`](../src/boardgamerules/orchestrator/service.py)** — `RuleOrchestrator` implementing 3-tier resolution, Quick Recap, Q&A, and user history coordination.
6. **Create [`src/boardgamerules/orchestrator/__init__.py`](../src/boardgamerules/orchestrator/__init__.py)** — Export `OrchestratorDependencies`, `ResolvedRules`, `RuleOrchestrator`, `SaveUserEntryRequest`.
7. **Create [`tests/unit/test_rule_orchestrator.py`](../tests/unit/test_rule_orchestrator.py)** — Comprehensive offline unit test suite.

---

### 2. Detailed Module Specifications

#### A. `src/boardgamerules/rag/ingestion.py`
- Public API at top:
  ```python
  @dataclass(frozen=True)
  class PdfIngestionOptions:
      pdf_extractor: PdfTextExtractor = field(default_factory=PyMuPdfTextExtractor)
      chunking_config: ChunkingConfig = field(default_factory=ChunkingConfig)

  async def ingest_pdf_rulebook(
      game_id: str,
      pdf_bytes: bytes,
      rag_engine: RagEngine,
      options: PdfIngestionOptions | None = None,
  ) -> tuple[RuleChunk, ...]:
  ```
- Behavior:
  1. Validate `require_canonical_game_id(game_id)` and `if not pdf_bytes: raise DomainValidationError("pdf_bytes cannot be empty.")`.
  2. Resolve `active_options = options or PdfIngestionOptions()`.
  3. Offload CPU-bound PDF extraction and chunking off the asyncio event loop:
     `chunks = await asyncio.to_thread(_extract_chunks, game_id, pdf_bytes, active_options)`.
  4. Replace chunks in Qdrant:
     `await rag_engine.delete_game_chunks(game_id)`
     `await rag_engine.index_chunks(chunks)`
  5. Return `chunks`.
- Private helper at bottom:
  ```python
  def _extract_chunks(
      game_id: str,
      pdf_bytes: bytes,
      options: PdfIngestionOptions,
  ) -> tuple[RuleChunk, ...]:
      pages = options.pdf_extractor.extract_pages(pdf_bytes)
      return chunk_rulebook_pages(
          game_id=game_id,
          pages=pages,
          config=options.chunking_config,
      )
  ```

#### B. `src/boardgamerules/orchestrator/models.py`
- Pure immutable dataclasses (`@dataclass(frozen=True)`):
  ```python
  @dataclass(frozen=True)
  class OrchestratorDependencies:
      manual_repo: GameManualRepository
      history_repo: UserHistoryRepository
      rag_engine: RagEngine
      rulebook_fetcher: RulebookFetcher
      ai_generator: AiRuleGenerator
      pdf_extractor: PdfTextExtractor = field(default_factory=PyMuPdfTextExtractor)
      chunking_config: ChunkingConfig = field(default_factory=ChunkingConfig)


  @dataclass(frozen=True)
  class ResolvedRules:
      manual: GameManual
      from_cache: bool


  @dataclass(frozen=True)
  class SaveUserEntryRequest:
      user_id: str
      game_title: str
      entry_type: SavedEntryType
      prompt_or_heading: str
      content_markdown: str
      source: ManualSource
  ```
- Validation in `SaveUserEntryRequest.__post_init__`:
  - `require_non_blank` on `user_id`, `game_title`, `prompt_or_heading`, `content_markdown`.
  - Validate canonical slug derivation via `normalize_game_id(self.game_title)` (fails fast on symbol-only titles like `"!!!"`).
- Note: Do **not** include `fallback_rulebook` on `ResolvedRules` — `manual.summary_markdown` is the single consistent representation for Tier-3 rules across both cache misses and cache hits.

#### C. `src/boardgamerules/orchestrator/service.py`
- Include two educational `# CONCEPT:` tags written in plain, everyday English:
  1. `# CONCEPT: [Design Pattern] Facade & Chain of Responsibility (3-Tier Rule Resolution)` — on `RuleOrchestrator`.
  2. `# CONCEPT: [System Design] Single-Flight Per-Key Concurrency Lock` — on `_get_resolution_lock` or `resolve_rules`.
- Public class `RuleOrchestrator` at top:
  - `__init__(self, dependencies: OrchestratorDependencies) -> None`:
    - Store narrow interfaces (`_manual_repo`, `_history_repo`, `_rag_engine`, `_rulebook_fetcher`, `_ai_generator`, `_ingestion_options = PdfIngestionOptions(pdf_extractor=dependencies.pdf_extractor, chunking_config=dependencies.chunking_config)`).
    - Initialize `self._resolution_locks: dict[str, asyncio.Lock] = {}`.
  - `async def resolve_rules(self, game_title: str) -> ResolvedRules`:
    1. Validate and normalize up front: `clean_title = game_title.strip()` and `game_id = normalize_game_id(clean_title)` (fail fast with `DomainValidationError`; never fall back to Tier 3 on invalid input).
    2. **Fast Tier-1 check** before acquiring lock:
       `existing = await self._manual_repo.get_active_manual(game_id)`
       If `existing is not None`, log `INFO` (`game_id`, `source=existing.source.value`, `from_cache=True`) and return `ResolvedRules(manual=existing, from_cache=True)`.
    3. Acquire per-`game_id` lock: `async with self._get_resolution_lock(game_id):`
       - **Double-checked Tier-1 lookup** inside the lock (prevents duplicate Tier-2 fetches and Qdrant delete/index race conditions under concurrent requests).
       - **Tier 2 (`_try_resolve_via_internet`)**:
         - Call `fetched = await self._rulebook_fetcher.fetch_rulebook(clean_title)`.
         - Compute `content_sha256 = fetched.content_sha256` **once** (avoid double-hashing large PDFs).
         - Call `chunks = await ingest_pdf_rulebook(game_id, fetched.pdf_bytes, self._rag_engine, self._ingestion_options)`.
         - Build `GameManual(manual_id=f"manual-{game_id}-{uuid.uuid4().hex[:8]}", game_id=game_id, game_title=fetched.game_title.strip(), source=ManualSource.INTERNET_API, edition=fetched.edition, status=ManualStatus.READY, source_url_or_path=fetched.source_url, bgg_id=fetched.bgg_id, product_code=fetched.product_code, content_sha256=content_sha256)`.
         - Persist via `await self._manual_repo.save_manual(manual)`.
         - Log `INFO` (`game_id`, `source=manual.source.value`, `chunk_count=len(chunks)`, `from_cache=False`) and return `ResolvedRules(manual=manual, from_cache=False)`.
       - **Tier 2 -> Tier 3 Fallback Boundary**:
         - Catch `(RulebookNotFoundError, ExternalRuleFetchError, RagIngestionError) as exc`:
           - `should_cache_fallback = isinstance(exc, RulebookNotFoundError)`
           - Log `WARNING` (`"Tier-2 rulebook fetch or ingestion failed; falling back to AI generation"`, `extra={"game_id": game_id, "error_type": type(exc).__name__, "will_cache_fallback": should_cache_fallback}`).
           - **Do NOT catch `StorageOperationError`** (database outages must fail fast, not silently hallucinate AI rules).
         - Call `_resolve_via_ai_fallback(game_id, clean_title, persist=should_cache_fallback)`:
           - `fallback = await self._ai_generator.generate_fallback_rules(clean_title)`
           - Build `GameManual(manual_id=f"manual-{game_id}-{uuid.uuid4().hex[:8]}", game_id=game_id, game_title=clean_title, source=ManualSource.AI_GENERATED, status=ManualStatus.READY, summary_markdown=fallback.to_markdown())`.
           - If `persist` is True (`RulebookNotFoundError`): `await self._manual_repo.save_manual(manual)`.
           - If `persist` is False (transient `ExternalRuleFetchError` / `RagIngestionError`): do **not** save to MongoDB, so the next request retries Tier 2.
           - Do **not** index Tier-3 AI text into Qdrant (keep Qdrant strictly for verified PDF rulebooks).
           - Return `ResolvedRules(manual=manual, from_cache=False)`.
  - `async def generate_quick_recap(self, game_title: str, top_k: int = 8) -> QuickRecap`:
    1. Validate `_validate_top_k(top_k)` up front (`1 <= top_k <= 50`, rejecting `bool`).
    2. `resolved = await self.resolve_rules(game_title)`
    3. If `resolved.manual.is_verified`:
       - `chunks = await self._rag_engine.search_chunks(game_id=resolved.manual.game_id, query=_QUICK_RECAP_QUERY, top_k=top_k)`
       - If `not chunks`: log `WARNING` (`"Verified manual has no indexed chunks in Qdrant; generating ungrounded quick recap"`, `extra={"game_id": resolved.manual.game_id, "source": resolved.manual.source.value}`).
    4. Else: `chunks = ()`.
    5. Return `await self._ai_generator.generate_quick_recap(game_title=resolved.manual.game_title, chunks=chunks)`.
  - `async def ask_question(self, game_title: str, question: str, top_k: int = 5) -> RuleAnswer`:
    1. Validate `require_non_blank(question, "question")` and `_validate_top_k(top_k)` up front (fail fast before any resolution I/O).
    2. `resolved = await self.resolve_rules(game_title)`
    3. If `resolved.manual.is_verified`:
       - Try `return await answer_rulebook_question(self._rag_engine, self._ai_generator, RulebookQuestion(game_id=resolved.manual.game_id, game_title=resolved.manual.game_title, question=question, top_k=top_k, source=resolved.manual.source))`.
       - Except `ManualNotFoundError`: log `WARNING` (`"Verified manual has no indexed chunks in Qdrant; falling back to ungrounded AI answer"`, `extra={"game_id": resolved.manual.game_id, "question_length": len(question)}`) and fall through to ungrounded answer helper.
    4. Ungrounded fallback (`_answer_ungrounded_question(resolved.manual, question)`):
       - `generated = await self._ai_generator.answer_question(game_title=resolved.manual.game_title, question=question, chunks=())`
       - Return `RuleAnswer(game_id=resolved.manual.game_id, question=question, answer_markdown=generated.answer_text, citations=(), source=ManualSource.AI_GENERATED, found_in_rules=False)`.
  - `async def save_user_entry(self, request: SaveUserEntryRequest) -> SavedUserEntry`:
    - Build `SavedUserEntry(entry_id=f"entry-{uuid.uuid4().hex[:12]}", user_id=request.user_id.strip(), game_id=normalize_game_id(request.game_title), game_title=request.game_title.strip(), entry_type=request.entry_type, prompt_or_heading=request.prompt_or_heading.strip(), content_markdown=request.content_markdown.strip(), source=request.source)`.
    - Persist via `await self._history_repo.save_history_entry(entry)`.
    - Log `INFO` (`"Saved user history entry"`, `extra={"game_id": entry.game_id, "entry_type": entry.entry_type.value, "source": entry.source.value}`) — **never log `user_id` or `content_markdown`**.
    - Return `entry`.
  - `async def list_user_history(self, user_id: str) -> tuple[SavedUserEntry, ...]`:
    - Validate `require_non_blank(user_id, "user_id")`.
    - Return `await self._history_repo.list_user_history(user_id.strip())`.
- Private helpers & constants at bottom of `service.py` (Stepdown Rule):
  - `_MAX_TOP_K = 50`
  - `_QUICK_RECAP_QUERY = "game objective setup turn structure winning conditions key rules"`
  - `_validate_top_k(top_k: int) -> None`

---

### 3. Planned Offline Unit Tests (`tests/unit/test_rule_orchestrator.py`)

Use `InMemoryGameManualRepository`, `InMemoryUserHistoryRepository`, real `QdrantRagEngine` (`QdrantClient(":memory:")` + `DeterministicEmbeddingProvider`), and minimal async fake classes for `RulebookFetcher`, `AiRuleGenerator`, and `PdfTextExtractor`. All tests follow AAA pattern and `test_should_<expected>_when_<condition>` naming:

1. `test_should_return_cached_manual_without_calling_fetcher_or_ai_when_tier1_manual_exists`
2. `test_should_fetch_ingest_and_persist_internet_manual_when_tier1_misses`
3. `test_should_fallback_to_ai_and_cache_manual_when_tier2_raises_rulebook_not_found`
4. `test_should_fallback_to_ai_without_caching_when_tier2_raises_transient_fetch_or_ingestion_error` (parametrized over `ExternalRuleFetchError` and `RagIngestionError`, verifying `manual_repo.get_active_manual(game_id) is None` so next call retries Tier 2)
5. `test_should_deduplicate_concurrent_resolutions_for_same_game_using_single_flight_lock` (two `asyncio.gather` calls for the same uncached game trigger Tier-2 fetch exactly once)
6. `test_should_propagate_storage_error_without_falling_back_to_ai_when_manual_repo_fails`
7. `test_should_generate_grounded_quick_recap_from_rag_chunks_when_verified_manual_exists`
8. `test_should_generate_ungrounded_quick_recap_when_resolved_manual_is_ai_generated`
9. `test_should_generate_ungrounded_quick_recap_with_warning_when_verified_manual_has_no_qdrant_chunks`
10. `test_should_answer_grounded_question_with_citations_when_verified_manual_exists`
11. `test_should_answer_ungrounded_question_when_resolved_manual_is_ai_generated_or_qdrant_drifts`
12. `test_should_save_and_list_user_history_entries_for_rules_recaps_and_qa_answers`
13. `test_should_fail_fast_with_validation_error_when_inputs_or_top_k_are_invalid` (blank title, symbol-only title, blank question, `top_k=0`, `top_k=51`, `top_k=True`, blank `user_id`)
