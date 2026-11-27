# Task 7: AI Fallback & Quick Recap Generator Module

## Objective
Implement the AI module that generates game rules when no manual is found, creates short Quick Recaps, and synthesizes RAG Q&A answers.

## Requirements
- Define Pydantic v2 `BaseModel` schemas (`response_schema`) for structured Gemini outputs and map them into domain dataclasses.
- Generate structured rules for a requested board game using the LLM when both existing RAG and internet fetching fail.
- Generate a concise "Quick Recap" summary of a game's rules on demand.
- Generate grounded answers to user rule questions using retrieved RAG chunks.
- Add unit tests verifying prompt construction, response parsing, and source attribution (RAG-grounded vs AI-generated fallback).

---

## Technical Implementation Plan (Approved Design)

> **Status**: Design approved on branch `feat/task-007-ai-fallback-and-recap-generator` after Devil's Advocate review. Proceed directly to **Step 5 (Implement & Verify)** of `skills/task-workflow/SKILL.md`, keeping all rules in `AGENTS.md`.
> **Zero-Cost Testing Rule**: All automated tests MUST run 100% offline with fake/stub Gemini clients (`$0.00` API cost, zero real network calls).

### 1. Files to Create & Modify

**Create:**
- `src/boardgamerules/domain/ai.py` — Pure frozen domain dataclasses (`GeneratedRulebook`, `QuickRecap`, `GeneratedRuleAnswer`). Zero external imports (no `pydantic`, no `google-genai`, no `logging`).
- `src/boardgamerules/ai/__init__.py` — Public package exports (`__all__`).
- `src/boardgamerules/ai/config.py` — `AiSettings` dataclass + `from_env()`.
- `src/boardgamerules/ai/schemas.py` — Pydantic v2 `response_schema` models + pure anti-corruption mappers to domain dataclasses.
- `src/boardgamerules/ai/prompts.py` — Pure `PromptBundle` builders with XML escaping and chunk budget management.
- `src/boardgamerules/ai/generator.py` — `GeminiAiRuleGenerator(AiRuleGenerator)` + `create_gemini_ai_generator(settings)`.
- `tests/unit/test_ai_generator.py` — Comprehensive offline AAA unit tests.

**Modify:**
- `src/boardgamerules/domain/rag.py` — Add `found_in_rules: bool = True` and `is_verified` property to `RuleAnswer`.
- `src/boardgamerules/domain/contracts.py` — Update `AiRuleGenerator` return types to domain dataclasses (keep lean 1–3 arg signatures; do **not** add a `source` param).
- `src/boardgamerules/domain/__init__.py` — Export `GeneratedRulebook`, `QuickRecap`, `GeneratedRuleAnswer`.
- `src/boardgamerules/rag/qa.py` — Consume `GeneratedRuleAnswer`, populate `RuleAnswer.found_in_rules`, and ensure `citations=()` when `found_in_rules=False`.
- `tests/unit/test_contracts.py` — Update `_StubAiGenerator` for the new `AiRuleGenerator` return types.
- `tests/unit/test_rag_qa.py` — Update `_RecordingAiRuleGenerator` and add a test for `found_in_rules=False` -> empty `citations`.
- `pyproject.toml` — Explicitly add `"pydantic>=2.10.0"` to `[project].dependencies` (do not rely on transitive dependency).
- `.env.example` — Add `GEMINI_MODEL="gemini-2.5-flash"` under the Google Gemini section.
- `CONCEPTS.md` — Regenerate via `uv run --offline python scripts/collect_concepts.py`.

---

### 2. Domain Layer Specifications (`src/boardgamerules/domain/`)

#### 2.1 `src/boardgamerules/domain/ai.py`
All classes must be `@dataclass(frozen=True)`, validate inputs in `__post_init__` (using `require_non_blank` and raising `DomainValidationError`), and coerce sequence fields to `tuple(...)` via `object.__setattr__`.

1. **`GeneratedRulebook`**:
   - Fields:
     - `game_title: str` (non-blank)
     - `overview: str` (non-blank)
     - `setup_steps: tuple[str, ...]` (coerced to `tuple`, at least 1 item, every item non-blank)
     - `turn_structure: tuple[str, ...]` (coerced to `tuple`, at least 1 item, every item non-blank)
     - `winning_condition: str` (non-blank)
     - `key_rules: tuple[str, ...] = ()` (coerced to `tuple`, may be empty, every item non-blank)
     - `source: ManualSource = ManualSource.AI_GENERATED`
   - Property: `is_verified -> bool` returning `self.source != ManualSource.AI_GENERATED`.
   - Method: `to_markdown() -> str`:
     - Clean, pure Markdown (do **not** prepend a hardcoded AI warning banner — UI/frontend renders badges via `is_verified`/`source`).
     - Exact sections:
       - `# {game_title}`
       - `## Overview` + `{overview}`
       - `## Setup` + numbered list (`1. ...`, `2. ...`)
       - `## Turn Structure` + numbered list (`1. ...`, `2. ...`)
       - `## Winning Condition` + `{winning_condition}`
       - `## Key Rules` + bullet list (`- ...`) — omit `## Key Rules` heading if `key_rules` is empty.

2. **`QuickRecap`**:
   - Fields:
     - `game_title: str` (non-blank)
     - `goal: str` (non-blank)
     - `turn_summary: tuple[str, ...]` (coerced to `tuple`, at least 1 item, every item non-blank)
     - `setup_highlights: tuple[str, ...] = ()` (coerced to `tuple`, may be empty for partial RAG chunks, every item non-blank)
     - `key_rules_to_remember: tuple[str, ...] = ()` (coerced to `tuple`, may be empty, every item non-blank)
     - `is_grounded: bool = False`
     - `cited_chunk_ids: tuple[str, ...] = ()` (coerced to `tuple`, every item non-blank)
   - Invariant in `__post_init__`: If `not self.is_grounded and self.cited_chunk_ids`, raise `DomainValidationError("cited_chunk_ids must be empty when is_grounded is False.")`.
   - Method: `to_markdown() -> str`:
     - Clean, pure Markdown (no hardcoded AI warning banner).
     - Exact sections: `# {game_title} — Quick Recap`, `## Goal`, `## Setup Highlights` (bullet list, omit if empty), `## Turn Summary` (numbered list), `## Key Rules to Remember` (bullet list, omit if empty).

3. **`GeneratedRuleAnswer`**:
   - Lean LLM output value object (callers like `rag/qa.py` and Task 8 attach `game_id`, `question`, and `ManualSource` onto `RuleAnswer`):
   - Fields:
     - `answer_text: str` (non-blank)
     - `found_in_rules: bool`
     - `cited_chunk_ids: tuple[str, ...] = ()` (coerced to `tuple`, every item non-blank)
     - `is_grounded: bool = True`
   - Invariants in `__post_init__`:
     - If `not self.is_grounded and self.found_in_rules`, raise `DomainValidationError("found_in_rules cannot be True when is_grounded is False.")`.
     - If `(not self.is_grounded or not self.found_in_rules) and self.cited_chunk_ids`, raise `DomainValidationError("cited_chunk_ids must be empty when ungrounded or not found in rules.")`.

#### 2.2 `src/boardgamerules/domain/rag.py` (`RuleAnswer`)
- Add `found_in_rules: bool = True`.
- In `__post_init__`: if `not self.found_in_rules and self.citations`, raise `DomainValidationError("citations must be empty when found_in_rules is False.")`.
- Add `@property def is_verified(self) -> bool: return self.source != ManualSource.AI_GENERATED`.

#### 2.3 `src/boardgamerules/domain/contracts.py` (`AiRuleGenerator`)
Keep the exact 1–3 argument signatures; update return types only:
```python
class AiRuleGenerator(ABC):
    @abstractmethod
    async def generate_fallback_rules(self, game_title: str) -> GeneratedRulebook: ...

    @abstractmethod
    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> QuickRecap: ...

    @abstractmethod
    async def answer_question(
        self,
        game_title: str,
        question: str,
        chunks: Sequence[RuleChunk],
    ) -> GeneratedRuleAnswer: ...
```

#### 2.4 `src/boardgamerules/rag/qa.py` (`answer_rulebook_question`)
- Call `generated = await ai_generator.answer_question(game_title=query.game_title, question=query.question, chunks=retrieved_chunks)`.
- Extract pure helper `_select_citations(retrieved_chunks: tuple[RuleChunk, ...], generated: GeneratedRuleAnswer) -> tuple[RuleChunk, ...]`:
  - If `not generated.found_in_rules`: return `()` (never attach fake citations).
  - If `generated.cited_chunk_ids`: filter `retrieved_chunks` matching `generated.cited_chunk_ids` (if non-empty, return them; else fall back to `retrieved_chunks`).
  - Else (`found_in_rules=True` and `cited_chunk_ids` empty): return `retrieved_chunks`.
- Construct `RuleAnswer(..., answer_markdown=generated.answer_text, citations=citations, source=query.source, found_in_rules=generated.found_in_rules)`.

---

### 3. AI Package Specifications (`src/boardgamerules/ai/`)

#### 3.1 `src/boardgamerules/ai/config.py`
Frozen `AiSettings`:
- `gemini_api_key: str | None = field(default=None, repr=False)`
- `gemini_model: str = "gemini-2.5-flash"`
- `use_vertexai: bool = False`
- `temperature: float = 0.2`
- `max_output_tokens: int = 4096`
- `max_context_chars: int = 40_000`
- `max_retries: int = 2`
- `base_retry_seconds: float = 2.0`
- `max_retry_wait_seconds: float = 10.0`
- Validation in `__post_init__`:
  - `require_non_blank(self.gemini_model, "gemini_model")`
  - Reject `bool` for numeric fields (`isinstance(x, bool)`), check `math.isfinite` on floats.
  - `0.0 <= temperature <= 2.0`
  - `max_output_tokens >= 256`
  - `max_context_chars >= 500`
  - `max_retries >= 0`
  - `base_retry_seconds >= 0.0`, `max_retry_wait_seconds >= 0.0`
- `from_env(cls, environ=None, dotenv_path=DEFAULT_DOTENV_PATH) -> AiSettings`:
  - Uses `boardgamerules.env_loader` (`load_env_vars`, `read_optional_env`).
  - Reads `GEMINI_API_KEY`, `GEMINI_MODEL` (default `"gemini-2.5-flash"`), and `GOOGLE_GENAI_USE_VERTEXAI` (`value.lower() in {"true", "1", "yes"}`).

#### 3.2 `src/boardgamerules/ai/schemas.py`
Add `# CONCEPT: [Design Pattern] Anti-Corruption Layer (Pydantic Schema to Domain Mapper)` in plain English.
- Pydantic v2 `BaseModel` wire schemas using simple Gemini-compatible types (`str`, `list[str]`, `bool`) with `Field(description=...)`:
  - `FallbackRulesSchema`: `overview: str`, `setup_steps: list[str]`, `turn_structure: list[str]`, `winning_condition: str`, `key_rules: list[str]`
  - `QuickRecapSchema`: `goal: str`, `setup_highlights: list[str]`, `turn_summary: list[str]`, `key_rules_to_remember: list[str]`, `cited_chunk_ids: list[str]`
  - `RuleAnswerSchema`: `answer: str`, `found_in_rules: bool`, `cited_chunk_ids: list[str]`
- Pure mapper functions:
  - `map_fallback_rules_to_domain(schema: FallbackRulesSchema, game_title: str) -> GeneratedRulebook`
  - `map_quick_recap_to_domain(schema: QuickRecapSchema, game_title: str, allowed_chunk_ids: Sequence[str], is_grounded: bool) -> QuickRecap`
  - `map_rule_answer_to_domain(schema: RuleAnswerSchema, allowed_chunk_ids: Sequence[str], is_grounded: bool) -> GeneratedRuleAnswer`
- Mapping & sanitization rules:
  - Strip leading/trailing whitespace from all strings; drop empty/whitespace-only list entries.
  - Filter `cited_chunk_ids` against `set(allowed_chunk_ids)` preserving order and deduplicating (blocks hallucinated chunk IDs).
  - If `not is_grounded`: force `cited_chunk_ids = ()` (and for `RuleAnswerSchema`, force `found_in_rules = False`).
  - If `not found_in_rules`: force `cited_chunk_ids = ()`.
  - Wrap `DomainValidationError` from domain constructors (e.g., blank `overview` or empty `setup_steps`) into `AiGenerationError` with a safe message (never include raw LLM text).

#### 3.3 `src/boardgamerules/ai/prompts.py`
Add `# CONCEPT: [AI Engineering] Prompt Injection Defense (System vs. Data Separation)` in plain English.
- Frozen `PromptBundle(system_instruction: str, user_prompt: str, included_chunk_ids: tuple[str, ...] = ())`.
- Input sanitization helper `_sanitize_xml_text(value: str) -> str`:
  - Strip ASCII control characters (`\x00-\x08`, `\x0b-\x0c`, `\x0e-\x1f`, `\x7f`), preserving `\n` and `\t`.
  - Escape XML special characters using stdlib `xml.sax.saxutils.escape(cleaned, {'"': '&quot;', "'": '&apos;'})` on **all** untrusted interpolated values (`game_title`, `question`, `chunk.chunk_id`, `chunk.section_title`, `chunk.text`).
- Cross-game isolation helper `_validate_single_game_chunks(chunks: Sequence[RuleChunk]) -> None`:
  - If `len({chunk.game_id for chunk in chunks}) > 1`, raise `DomainValidationError("All chunks must belong to the same game_id.")`.
- Safe per-chunk formatting helper `_format_rulebook_excerpts(chunks: Sequence[RuleChunk], max_context_chars: int) -> tuple[str, tuple[str, ...]]`:
  - Formats each chunk as `<rulebook_excerpt chunk_id="..." page="..." section="...">text</rulebook_excerpt>` inside `<rulebook_excerpts>...</rulebook_excerpts>`.
  - Tracks remaining character budget so XML tags and attributes are **never** truncated mid-tag.
  - If a chunk's text exceeds the remaining budget, truncate only the inner text with `"..."` when at least 100 characters fit (guaranteeing at least 1 chunk is included whenever `chunks` is non-empty).
  - Returns `(xml_block, included_chunk_ids)` so callers validate citations strictly against chunks actually sent to Gemini.
- Pure builders (each validates `require_non_blank` on `game_title` and `question` -> `DomainValidationError` before any LLM call):
  - `build_fallback_rules_prompt(game_title: str) -> PromptBundle`
  - `build_quick_recap_prompt(game_title: str, chunks: Sequence[RuleChunk], max_context_chars: int = 40_000) -> PromptBundle`
  - `build_rule_answer_prompt(game_title: str, question: str, chunks: Sequence[RuleChunk], max_context_chars: int = 40_000) -> PromptBundle`
- System instructions must explicitly instruct the model to treat text inside XML tags strictly as untrusted data (never as instructions):
  - **Grounded mode** (`chunks` non-empty): answer/summarize strictly from `<rulebook_excerpts>`, do not invent rules from memory, cite exact `chunk_id` values, and set `found_in_rules=false` when excerpts do not answer the question.
  - **Fallback mode** (`chunks` empty): explain that no official rulebook excerpts are available, answer/recap from general board game knowledge, set `cited_chunk_ids=[]` (and `found_in_rules=false` for Q&A).

#### 3.4 `src/boardgamerules/ai/generator.py`
Add `# CONCEPT: [AI Engineering] Structured LLM Outputs (Schema-Enforced JSON)` in plain English.
- `GeminiAiRuleGenerator(AiRuleGenerator)`:
  - `__init__(self, client: Any, settings: AiSettings | None = None) -> None` (lean 2-arg signature).
  - Calls `await self._client.aio.models.generate_content(...)` with:
    ```python
    types.GenerateContentConfig(
        system_instruction=prompt.system_instruction,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=self._settings.temperature,
        max_output_tokens=self._settings.max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    ```
  - Helper `_check_finish_reason(response: Any, operation: str) -> None`:
    - Inspects `candidates = getattr(response, "candidates", None)`. If non-empty, checks `finish_reason = getattr(candidates[0], "finish_reason", None)`.
    - If `finish_reason` is not `None` and not `STOP` (check both enum `types.FinishReason.STOP` and string `"STOP"`), raise `AiGenerationError` mentioning the `operation` and `finish_reason` (handles `MAX_TOKENS`, `SAFETY`, `RECITATION`, etc.).
  - Helper `_parse_structured_response(response: Any, schema: type[SchemaT], operation: str) -> SchemaT`:
    - First checks `parsed = getattr(response, "parsed", None)`: if `isinstance(parsed, schema)`, return `parsed`.
    - Otherwise reads `raw_text = getattr(response, "text", None)`. If blank/`None`, raise `AiGenerationError`.
    - Calls `schema.model_validate_json(raw_text)`. Catch `ValidationError` -> raise `AiGenerationError(f"Gemini returned invalid structured output for '{operation}' ({exc.error_count()} validation error(s)).") from exc`. **Never log or include `raw_text` or `str(exc)` raw input dumps** (`AGENTS.md §1.8`).
  - Interactive capped 429 retry loop:
    - Detect rate limits via `getattr(exc, "code", None) == 429` or `"429"` / `"RESOURCE_EXHAUSTED"` in `str(exc).upper()`.
    - Parse server retry delay (`r"retry in (\d+(?:\.\d+)?)s"`) or fall back to `base_retry_seconds`, **always capped** by `min(wait, settings.max_retry_wait_seconds)`.
    - Log `WARNING` on retry with safe metadata (`model`, `operation`, `attempt`, `wait_seconds`); `await asyncio.sleep(wait)`.
    - Wrap terminal/exhausted SDK errors into `AiGenerationError`.
  - Centralized logging (`logger = logging.getLogger(__name__)`):
    - Log safe metadata only (`model`, `operation`, `chunk_count`, `is_grounded`, `question_length`) at `DEBUG`. Never log `gemini_api_key`, raw questions, or rulebook text.
- Factory `create_gemini_ai_generator(settings: AiSettings) -> GeminiAiRuleGenerator`:
  - If `settings.use_vertexai`: build `genai.Client(vertexai=True)`.
  - Else if `settings.gemini_api_key`: build `genai.Client(api_key=settings.gemini_api_key)`.
  - Else: raise `DomainValidationError("Set GEMINI_API_KEY or GOOGLE_GENAI_USE_VERTEXAI=true to create GeminiAiRuleGenerator.")`.

---

### 4. Planned Unit Tests (100% Offline, AAA Pattern, `$0.00` Cost)

In `tests/unit/test_ai_generator.py`:
1. `test_should_load_ai_settings_from_env_with_api_key_and_vertexai_flag`
2. `test_should_raise_validation_error_when_ai_settings_values_are_invalid`
3. `test_should_escape_xml_delimiters_and_strip_control_chars_in_prompts`
4. `test_should_truncate_chunk_text_within_budget_without_breaking_xml_tags`
5. `test_should_raise_validation_error_when_chunks_mix_multiple_game_ids`
6. `test_should_generate_fallback_rules_with_ai_generated_source_and_clean_markdown`
7. `test_should_generate_grounded_quick_recap_filtering_hallucinated_chunk_ids`
8. `test_should_generate_fallback_quick_recap_with_ungrounded_flag_when_chunks_empty`
9. `test_should_answer_grounded_question_with_validated_citations_and_found_flag`
10. `test_should_clear_citations_when_grounded_question_is_not_found_in_rules`
11. `test_should_answer_fallback_question_with_ungrounded_flag_when_chunks_empty`
12. `test_should_parse_structured_output_from_parsed_object_or_json_text`
13. `test_should_raise_ai_generation_error_when_finish_reason_is_safety_or_max_tokens`
14. `test_should_raise_ai_generation_error_when_gemini_returns_malformed_or_empty_schema`
15. `test_should_retry_on_429_rate_limit_with_capped_wait_and_wrap_terminal_errors`
16. `test_should_create_gemini_generator_or_fail_fast_when_credentials_missing`

In `tests/unit/test_rag_qa.py`:
- Update `_RecordingAiRuleGenerator` to return `GeneratedRuleAnswer`.
- Add `test_should_return_empty_citations_when_answer_is_not_found_in_rules`.

In `tests/unit/test_contracts.py`:
- Update `_StubAiGenerator` to return `GeneratedRulebook`, `QuickRecap`, `GeneratedRuleAnswer`.

---

### 5. Verification & Workflow Checklist for Implementation Model
1. Sync `CONCEPTS.md`: `uv run --offline python scripts/collect_concepts.py`
2. Run offline test suite: `uv run --offline pytest`
3. Lint & format: `uv run --offline ruff check --fix . && uv run --offline ruff format .`
4. Verify concept sync: `uv run --offline python scripts/collect_concepts.py --check`
5. Follow `skills/pr-review/SKILL.md` strictly:
   - Stage 1: Initial AI PR Reviewer (`pr-reviewer` subagent) -> fix any findings until `APPROVED`.
   - Stage 2: Present summary for Human PR Review -> **wait for explicit `pr approved`**.
   - Stage 3: Post-approval final AI PR Review -> only after `APPROVED`, move task to `tasks/done/`, update `tasks/README.md`, commit, rebase/merge onto `master`, and push.
