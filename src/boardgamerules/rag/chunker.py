"""Section-aware overlapping text chunker for board game rulebook pages."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from boardgamerules.domain.exceptions import DomainValidationError, RagIngestionError
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.domain.validators import require_canonical_game_id
from boardgamerules.rag.pdf_extractor import PdfPageText

_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")
_NUMBERED_HEADING_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)*|[IVX]+)\.\s+[A-Z][^\n]{1,65}$")
_ALL_CAPS_HEADING_PATTERN = re.compile(r"^[A-Z][A-Z0-9\s,&:'/-]{2,60}$")


@dataclass(frozen=True)
class ChunkingConfig:
    max_chunk_chars: int = 1600
    overlap_chars: int = 200
    default_section_title: str = "General Rules"

    def __post_init__(self) -> None:
        if self.max_chunk_chars <= 0:
            raise DomainValidationError("max_chunk_chars must be greater than 0.")
        if self.overlap_chars < 0:
            raise DomainValidationError("overlap_chars cannot be negative.")
        if self.overlap_chars >= self.max_chunk_chars:
            raise DomainValidationError("overlap_chars must be strictly less than max_chunk_chars.")


_DEFAULT_CHUNKING_CONFIG = ChunkingConfig()


# CONCEPT: [AI Engineering] Section-Aware Overlapping Chunking
# Splitting rulebooks purely by fixed character counts cuts rules mid-sentence and loses
# the heading context (e.g., whether a rule belongs to "Setup" or "End of Game"). Tracking
# active section headers and sliding with overlap keeps rules coherent for vector retrieval.
def chunk_rulebook_pages(
    game_id: str,
    pages: Sequence[PdfPageText],
    config: ChunkingConfig = _DEFAULT_CHUNKING_CONFIG,
) -> tuple[RuleChunk, ...]:
    require_canonical_game_id(game_id)
    if not pages:
        raise RagIngestionError("pages cannot be empty when chunking a rulebook.")

    builder = _RulebookChunkBuilder(game_id=game_id, config=config)
    for page in pages:
        builder.process_page(page)
    return builder.build()


@dataclass
class _RulebookChunkBuilder:
    game_id: str
    config: ChunkingConfig
    active_section: str = field(init=False)
    chunk_counter: int = field(default=0, init=False)
    current_page_number: int = field(default=1, init=False)
    buffer: str = field(default="", init=False)
    chunks: list[RuleChunk] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.active_section = self.config.default_section_title

    def process_page(self, page: PdfPageText) -> None:
        self.current_page_number = page.page_number
        self.buffer = ""

        for raw_paragraph in _PARAGRAPH_SPLIT_PATTERN.split(page.text.strip()):
            paragraph = raw_paragraph.strip()
            if paragraph:
                self._process_paragraph(paragraph)

        self._flush_buffer()

    def build(self) -> tuple[RuleChunk, ...]:
        return tuple(self.chunks)

    def _process_paragraph(self, paragraph: str) -> None:
        heading, remainder = _extract_leading_heading(paragraph)
        if heading is not None:
            self._flush_buffer()
            self.active_section = heading
            if not remainder:
                self.buffer = f"# {heading}"
                return
            piece = f"# {heading}\n{remainder}"
        else:
            piece = paragraph

        if len(piece) > self.config.max_chunk_chars:
            self._append_oversized_piece(piece)
        else:
            self._append_standard_piece(piece)

    def _append_oversized_piece(self, piece: str) -> None:
        if self._buffer_has_only_heading():
            piece = f"{self.buffer}\n\n{piece}"
            self.buffer = ""
        else:
            self._flush_buffer()

        for sub_piece in _split_text_with_overlap(piece, self.config):
            self._emit_chunk(sub_piece)

    def _append_standard_piece(self, piece: str) -> None:
        candidate = f"{self.buffer}\n\n{piece}" if self.buffer else piece
        if len(candidate) <= self.config.max_chunk_chars:
            self.buffer = candidate
            return

        self._flush_buffer()
        self.buffer = piece

    def _buffer_has_only_heading(self) -> bool:
        return bool(self.buffer) and self.buffer.startswith("# ") and "\n" not in self.buffer

    def _flush_buffer(self) -> None:
        if not self.buffer:
            return
        self._emit_chunk(self.buffer)
        self.buffer = ""

    def _emit_chunk(self, text: str) -> None:
        self.chunk_counter += 1
        self.chunks.append(
            RuleChunk(
                game_id=self.game_id,
                chunk_id=f"{self.game_id}-p{self.current_page_number}-c{self.chunk_counter:04d}",
                page_number=self.current_page_number,
                section_title=self.active_section,
                text=text,
            )
        )


def _extract_leading_heading(paragraph: str) -> tuple[str | None, str]:
    lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return None, ""
    first_line = lines[0]
    remainder = "\n".join(lines[1:]).strip()

    if first_line.startswith("#"):
        heading = first_line.lstrip("#").strip()
        if heading:
            return heading, remainder

    if _NUMBERED_HEADING_PATTERN.match(first_line) or _ALL_CAPS_HEADING_PATTERN.match(first_line):
        return first_line, remainder

    return None, paragraph


def _split_text_with_overlap(text: str, config: ChunkingConfig) -> list[str]:
    slices: list[str] = []
    start = 0

    while start < len(text):
        if start + config.max_chunk_chars >= len(text):
            tail = text[start:].strip()
            if tail:
                slices.append(tail)
            break

        end = _find_word_boundary_end(text, start, config.max_chunk_chars)
        piece = text[start:end].strip()
        if piece:
            slices.append(piece)

        start = max(start + 1, _find_overlap_start(text, end, config.overlap_chars))

    return slices


def _find_word_boundary_end(text: str, start: int, max_chars: int) -> int:
    hard_limit = start + max_chars
    midpoint = start + (max_chars // 2)
    last_space = text.rfind(" ", midpoint, hard_limit)
    return last_space if last_space != -1 else hard_limit


def _find_overlap_start(text: str, end: int, overlap_chars: int) -> int:
    raw_start = max(0, end - overlap_chars)
    space_after_overlap = text.find(" ", raw_start, end)
    if space_after_overlap != -1 and space_after_overlap + 1 < end:
        return space_after_overlap + 1
    return raw_start
