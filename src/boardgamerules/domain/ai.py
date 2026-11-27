"""AI-generated rulebook fallback, quick recap, and rule answer domain entities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from boardgamerules.domain.enums import ManualSource
from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import require_non_blank


@dataclass(frozen=True)
class GeneratedRulebook:
    game_title: str
    overview: str
    setup_steps: tuple[str, ...]
    turn_structure: tuple[str, ...]
    winning_condition: str
    key_rules: tuple[str, ...] = ()
    source: ManualSource = ManualSource.AI_GENERATED

    def __post_init__(self) -> None:
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.overview, "overview")
        object.__setattr__(
            self,
            "setup_steps",
            _validate_string_tuple(self.setup_steps, "setup_steps", allow_empty=False),
        )
        object.__setattr__(
            self,
            "turn_structure",
            _validate_string_tuple(self.turn_structure, "turn_structure", allow_empty=False),
        )
        require_non_blank(self.winning_condition, "winning_condition")
        object.__setattr__(
            self,
            "key_rules",
            _validate_string_tuple(self.key_rules, "key_rules", allow_empty=True),
        )

    @property
    def is_verified(self) -> bool:
        return self.source != ManualSource.AI_GENERATED

    def to_markdown(self) -> str:
        lines = [
            f"# {self.game_title}",
            "",
            "## Overview",
            self.overview,
            "",
            "## Setup",
        ]
        for index, step in enumerate(self.setup_steps, start=1):
            lines.append(f"{index}. {step}")
        lines.extend(
            [
                "",
                "## Turn Structure",
            ]
        )
        for index, item in enumerate(self.turn_structure, start=1):
            lines.append(f"{index}. {item}")
        lines.extend(
            [
                "",
                "## Winning Condition",
                self.winning_condition,
            ]
        )
        if self.key_rules:
            lines.extend(
                [
                    "",
                    "## Key Rules",
                ]
            )
            for rule in self.key_rules:
                lines.append(f"- {rule}")
        return "\n".join(lines)


@dataclass(frozen=True)
class QuickRecap:
    game_title: str
    goal: str
    turn_summary: tuple[str, ...]
    setup_highlights: tuple[str, ...] = ()
    key_rules_to_remember: tuple[str, ...] = ()
    is_grounded: bool = False
    cited_chunk_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.goal, "goal")
        object.__setattr__(
            self,
            "turn_summary",
            _validate_string_tuple(self.turn_summary, "turn_summary", allow_empty=False),
        )
        object.__setattr__(
            self,
            "setup_highlights",
            _validate_string_tuple(self.setup_highlights, "setup_highlights", allow_empty=True),
        )
        object.__setattr__(
            self,
            "key_rules_to_remember",
            _validate_string_tuple(
                self.key_rules_to_remember, "key_rules_to_remember", allow_empty=True
            ),
        )
        object.__setattr__(
            self,
            "cited_chunk_ids",
            _validate_string_tuple(self.cited_chunk_ids, "cited_chunk_ids", allow_empty=True),
        )
        if not self.is_grounded and self.cited_chunk_ids:
            raise DomainValidationError("cited_chunk_ids must be empty when is_grounded is False.")

    def to_markdown(self) -> str:
        lines = [
            f"# {self.game_title} — Quick Recap",
            "",
            "## Goal",
            self.goal,
        ]
        if self.setup_highlights:
            lines.extend(
                [
                    "",
                    "## Setup Highlights",
                ]
            )
            for item in self.setup_highlights:
                lines.append(f"- {item}")
        lines.extend(
            [
                "",
                "## Turn Summary",
            ]
        )
        for index, item in enumerate(self.turn_summary, start=1):
            lines.append(f"{index}. {item}")
        if self.key_rules_to_remember:
            lines.extend(
                [
                    "",
                    "## Key Rules to Remember",
                ]
            )
            for item in self.key_rules_to_remember:
                lines.append(f"- {item}")
        return "\n".join(lines)


@dataclass(frozen=True)
class GeneratedRuleAnswer:
    answer_text: str
    found_in_rules: bool
    cited_chunk_ids: tuple[str, ...] = ()
    is_grounded: bool = True

    def __post_init__(self) -> None:
        require_non_blank(self.answer_text, "answer_text")
        object.__setattr__(
            self,
            "cited_chunk_ids",
            _validate_string_tuple(self.cited_chunk_ids, "cited_chunk_ids", allow_empty=True),
        )
        if not self.is_grounded and self.found_in_rules:
            raise DomainValidationError("found_in_rules cannot be True when is_grounded is False.")
        if (not self.is_grounded or not self.found_in_rules) and self.cited_chunk_ids:
            raise DomainValidationError(
                "cited_chunk_ids must be empty when ungrounded or not found in rules."
            )


def _validate_string_tuple(
    items: Sequence[str] | Any,
    field_name: str,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if items is None:
        if allow_empty:
            return ()
        raise DomainValidationError(f"{field_name} must contain at least 1 item.")

    coerced = tuple(items)
    if not coerced and not allow_empty:
        raise DomainValidationError(f"{field_name} must contain at least 1 item.")

    for item in coerced:
        require_non_blank(item, field_name)
    return coerced
