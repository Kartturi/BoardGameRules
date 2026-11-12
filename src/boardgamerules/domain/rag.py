"""RAG vector chunk and grounded Q&A answer domain entities."""

from __future__ import annotations

from dataclasses import dataclass

from boardgamerules.domain.enums import ManualSource
from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import require_canonical_game_id, require_non_blank


# CONCEPT: [AI Engineering] Grounded Citation & Chunk Metadata
# Storing page_number and section_title alongside each vector chunk allows the RAG system
# to cite exact rulebook pages in its answers, reducing hallucination and building user trust.
@dataclass(frozen=True)
class RuleChunk:
    chunk_id: str
    game_id: str
    text: str
    page_number: int | None = None
    section_title: str | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.chunk_id, "chunk_id")
        require_canonical_game_id(self.game_id)
        require_non_blank(self.text, "text")
        if self.page_number is not None and self.page_number < 1:
            raise DomainValidationError("page_number must be >= 1 when provided.")


@dataclass(frozen=True)
class RuleAnswer:
    game_id: str
    question: str
    answer_markdown: str
    citations: tuple[RuleChunk, ...] = ()
    source: ManualSource = ManualSource.MANUAL_PDF

    def __post_init__(self) -> None:
        require_canonical_game_id(self.game_id)
        require_non_blank(self.question, "question")
        require_non_blank(self.answer_markdown, "answer_markdown")
        object.__setattr__(self, "citations", tuple(self.citations))
