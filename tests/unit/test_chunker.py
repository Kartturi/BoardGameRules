"""Unit tests for section-aware rulebook chunking."""

from __future__ import annotations

import pytest

from boardgamerules.domain import DomainValidationError, RagIngestionError
from boardgamerules.rag import ChunkingConfig, PdfPageText, chunk_rulebook_pages


def test_should_chunk_pages_preserving_page_numbers_and_carrying_forward_section_titles() -> None:
    pages = (
        PdfPageText(
            page_number=1,
            text=(
                "# Game Setup\n\n"
                "Each player receives 5 wooden meeples and 10 coins.\n\n"
                "## Starting Resources\n\n"
                "Place the robber on the desert hex."
            ),
        ),
        PdfPageText(
            page_number=2,
            text=(
                "Shuffle the development card deck and place it face down.\n\n"
                "TURN OVERVIEW\n\n"
                "On your turn, roll two six-sided dice for resource production."
            ),
        ),
    )

    chunks = chunk_rulebook_pages(
        game_id="catan",
        pages=pages,
        config=ChunkingConfig(max_chunk_chars=120, overlap_chars=20),
    )

    assert len(chunks) >= 3
    assert chunks[0].chunk_id == "catan-p1-c0001"
    assert chunks[0].page_number == 1
    assert chunks[0].section_title == "Game Setup"
    assert any(c.page_number == 2 and c.section_title == "Starting Resources" for c in chunks)
    assert any(c.page_number == 2 and c.section_title == "TURN OVERVIEW" for c in chunks)


def test_should_split_oversized_paragraph_with_overlap_on_word_boundaries() -> None:
    long_paragraph = " ".join(f"ruleword{idx:02d}" for idx in range(30))
    pages = (PdfPageText(page_number=4, text=f"# Combat Rules\n\n{long_paragraph}"),)

    chunks = chunk_rulebook_pages(
        game_id="twilight-imperium",
        pages=pages,
        config=ChunkingConfig(max_chunk_chars=100, overlap_chars=25),
    )

    assert len(chunks) >= 3
    for chunk in chunks:
        assert len(chunk.text) <= 100
        assert chunk.page_number == 4
        assert chunk.section_title == "Combat Rules"
    assert "ruleword00" in chunks[0].text
    assert "ruleword29" in chunks[-1].text


@pytest.mark.parametrize(
    ("max_chars", "overlap_chars"),
    [
        (0, 0),
        (-10, 0),
        (100, -1),
        (100, 100),
        (100, 150),
    ],
)
def test_should_raise_validation_error_when_chunking_config_overlap_is_invalid(
    max_chars: int,
    overlap_chars: int,
) -> None:
    with pytest.raises(DomainValidationError):
        ChunkingConfig(max_chunk_chars=max_chars, overlap_chars=overlap_chars)


def test_should_raise_error_when_pages_are_empty_or_game_id_is_not_canonical() -> None:
    page = PdfPageText(page_number=1, text="Valid rule text.")

    with pytest.raises(DomainValidationError, match="canonical normalized slug"):
        chunk_rulebook_pages(game_id="Not Canonical!", pages=(page,))

    with pytest.raises(RagIngestionError, match="pages cannot be empty"):
        chunk_rulebook_pages(game_id="catan", pages=())
