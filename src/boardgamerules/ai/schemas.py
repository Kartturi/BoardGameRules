"""Pydantic v2 structured output schemas and domain anti-corruption mappers."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from boardgamerules.domain.ai import GeneratedRuleAnswer, GeneratedRulebook, QuickRecap
from boardgamerules.domain.exceptions import AiGenerationError, DomainValidationError


class FallbackRulesSchema(BaseModel):
    overview: str = Field(
        description="High-level summary of the board game theme, components, and objective."
    )
    setup_steps: list[str] = Field(
        description="Step-by-step instructions to set up the game board and player components."
    )
    turn_structure: list[str] = Field(
        description="Ordered phases or actions players take on their turn."
    )
    winning_condition: str = Field(
        description="Exact end-game trigger and condition for declaring a winner."
    )
    key_rules: list[str] = Field(
        default_factory=list,
        description="Important edge cases, special actions, or frequently forgotten rules.",
    )


class QuickRecapSchema(BaseModel):
    goal: str = Field(description="One-to-two sentence summary of the game objective.")
    setup_highlights: list[str] = Field(
        default_factory=list,
        description="Key initial setup highlights players need to know.",
    )
    turn_summary: list[str] = Field(description="Concise summary of what players do on their turn.")
    key_rules_to_remember: list[str] = Field(
        default_factory=list,
        description="Crucial rules and scoring reminders.",
    )
    cited_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Identifiers of rulebook chunks directly supporting this recap.",
    )


class RuleAnswerSchema(BaseModel):
    answer: str = Field(
        description="Clear and concise direct answer to the player's rule question."
    )
    found_in_rules: bool = Field(
        description="Whether the answer was explicitly found in the provided rulebook excerpts."
    )
    cited_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Identifiers of rulebook chunks directly supporting the answer.",
    )


# CONCEPT: [Design Pattern] Anti-Corruption Layer (Pydantic Schema to Domain Mapper)
# External LLM responses arrive as unvalidated JSON dictionaries. Using Pydantic models as an
# intermediate parsing layer and mapping them through explicit sanitizers insulates the pure
# domain layer from malformed outputs, strips whitespace, drops empty items, and prevents
# hallucinated citation IDs from corrupting verified rulebook citations.
def map_fallback_rules_to_domain(
    schema: FallbackRulesSchema,
    game_title: str,
) -> GeneratedRulebook:
    try:
        return GeneratedRulebook(
            game_title=game_title.strip(),
            overview=schema.overview.strip(),
            setup_steps=_clean_string_list(schema.setup_steps),
            turn_structure=_clean_string_list(schema.turn_structure),
            winning_condition=schema.winning_condition.strip(),
            key_rules=_clean_string_list(schema.key_rules),
        )
    except DomainValidationError as exc:
        raise AiGenerationError(
            f"Generated fallback rules for '{game_title}' failed validation: {exc}"
        ) from exc


def map_quick_recap_to_domain(
    schema: QuickRecapSchema,
    game_title: str,
    allowed_chunk_ids: Sequence[str],
    is_grounded: bool,
) -> QuickRecap:
    if not is_grounded:
        cited_ids = ()
    else:
        cited_ids = _filter_cited_chunk_ids(schema.cited_chunk_ids, allowed_chunk_ids)

    try:
        return QuickRecap(
            game_title=game_title.strip(),
            goal=schema.goal.strip(),
            setup_highlights=_clean_string_list(schema.setup_highlights),
            turn_summary=_clean_string_list(schema.turn_summary),
            key_rules_to_remember=_clean_string_list(schema.key_rules_to_remember),
            is_grounded=is_grounded,
            cited_chunk_ids=cited_ids,
        )
    except DomainValidationError as exc:
        raise AiGenerationError(
            f"Generated quick recap for '{game_title}' failed validation: {exc}"
        ) from exc


def map_rule_answer_to_domain(
    schema: RuleAnswerSchema,
    allowed_chunk_ids: Sequence[str],
    is_grounded: bool,
) -> GeneratedRuleAnswer:
    if not is_grounded:
        found_in_rules = False
        cited_ids = ()
    else:
        found_in_rules = bool(schema.found_in_rules)
        if not found_in_rules:
            cited_ids = ()
        else:
            cited_ids = _filter_cited_chunk_ids(schema.cited_chunk_ids, allowed_chunk_ids)

    try:
        return GeneratedRuleAnswer(
            answer_text=schema.answer.strip(),
            found_in_rules=found_in_rules,
            cited_chunk_ids=cited_ids,
            is_grounded=is_grounded,
        )
    except DomainValidationError as exc:
        raise AiGenerationError(f"Generated rule answer failed validation: {exc}") from exc


def _clean_string_list(items: Sequence[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for item in items:
        stripped = item.strip()
        if stripped:
            cleaned.append(stripped)
    return tuple(cleaned)


def _filter_cited_chunk_ids(
    cited_ids: Sequence[str],
    allowed_ids: Sequence[str],
) -> tuple[str, ...]:
    allowed_set = set(allowed_ids)
    seen: set[str] = set()
    result: list[str] = []
    for raw_id in cited_ids:
        cleaned_id = raw_id.strip()
        if cleaned_id in allowed_set and cleaned_id not in seen:
            seen.add(cleaned_id)
            result.append(cleaned_id)
    return tuple(result)
