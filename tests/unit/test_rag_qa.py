"""Unit tests for the grounded RAG question-answering pipeline."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from qdrant_client import AsyncQdrantClient

from boardgamerules.domain import (
    AiRuleGenerator,
    DomainValidationError,
    GeneratedRuleAnswer,
    GeneratedRulebook,
    ManualNotFoundError,
    ManualSource,
    QuickRecap,
    RuleChunk,
)
from boardgamerules.rag import (
    DeterministicEmbeddingProvider,
    QdrantRagEngine,
    RulebookQuestion,
    answer_rulebook_question,
)


class _RecordingAiRuleGenerator(AiRuleGenerator):
    def __init__(
        self,
        found_in_rules: bool = True,
        cited_chunk_ids: tuple[str, ...] = (),
    ) -> None:
        self.calls: list[tuple[str, str, tuple[RuleChunk, ...]]] = []
        self.found_in_rules = found_in_rules
        self.cited_chunk_ids = cited_chunk_ids

    async def generate_fallback_rules(self, game_title: str) -> GeneratedRulebook:
        return GeneratedRulebook(
            game_title=game_title,
            overview=f"Fallback rules for {game_title}",
            setup_steps=("Step 1",),
            turn_structure=("Phase 1",),
            winning_condition="10 victory points",
        )

    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> QuickRecap:
        return QuickRecap(
            game_title=game_title,
            goal=f"Goal for {game_title}",
            turn_summary=("Turn summary",),
            is_grounded=bool(chunks),
        )

    async def answer_question(
        self,
        game_title: str,
        question: str,
        chunks: Sequence[RuleChunk],
    ) -> GeneratedRuleAnswer:
        chunks_tuple = tuple(chunks)
        self.calls.append((game_title, question, chunks_tuple))
        return GeneratedRuleAnswer(
            answer_text=f"Grounded answer for {game_title}: {chunks_tuple[0].text}",
            found_in_rules=self.found_in_rules,
            cited_chunk_ids=self.cited_chunk_ids,
            is_grounded=bool(chunks),
        )


@pytest.mark.anyio
async def test_should_retrieve_chunks_and_return_grounded_rule_answer_with_citations() -> None:
    # Arrange
    client = AsyncQdrantClient(location=":memory:")
    engine = QdrantRagEngine(
        client=client,
        embedder=DeterministicEmbeddingProvider(vector_size=16),
        vector_size=16,
    )
    chunks = (
        RuleChunk(
            game_id="catan",
            chunk_id="catan-p3-c0001",
            page_number=3,
            section_title="Setup",
            text="Each player starts with 2 settlements and 2 roads.",
        ),
        RuleChunk(
            game_id="catan",
            chunk_id="catan-p9-c0002",
            page_number=9,
            section_title="Robber",
            text="Rolling a 7 activates the robber and discards cards over 7.",
        ),
    )
    await engine.index_chunks(chunks)
    ai_generator = _RecordingAiRuleGenerator()
    query = RulebookQuestion(
        game_id="catan",
        game_title="Catan",
        question="What happens when rolling a 7 activates the robber?",
        top_k=2,
    )

    # Act
    answer = await answer_rulebook_question(
        rag_engine=engine,
        ai_generator=ai_generator,
        query=query,
    )

    # Assert
    assert answer.game_id == "catan"
    assert answer.source == ManualSource.MANUAL_PDF
    assert len(answer.citations) == 2
    assert answer.citations[0].page_number == 9
    assert answer.citations[0].section_title == "Robber"
    assert len(ai_generator.calls) == 1
    await client.close()


@pytest.mark.anyio
async def test_should_return_empty_citations_when_answer_is_not_found_in_rules() -> None:
    # Arrange
    client = AsyncQdrantClient(location=":memory:")
    engine = QdrantRagEngine(
        client=client,
        embedder=DeterministicEmbeddingProvider(vector_size=16),
        vector_size=16,
    )
    chunk = RuleChunk(
        game_id="catan",
        chunk_id="catan-p1-c1",
        text="Setup rules here.",
    )
    await engine.index_chunks((chunk,))
    ai_generator = _RecordingAiRuleGenerator(found_in_rules=False)
    query = RulebookQuestion(
        game_id="catan",
        game_title="Catan",
        question="Can I build a rocket ship?",
    )

    # Act
    answer = await answer_rulebook_question(
        rag_engine=engine,
        ai_generator=ai_generator,
        query=query,
    )

    # Assert
    assert answer.found_in_rules is False
    assert answer.citations == ()
    await client.close()


@pytest.mark.anyio
async def test_should_raise_manual_not_found_error_when_no_chunks_exist_for_game() -> None:
    # Arrange
    client = AsyncQdrantClient(location=":memory:")
    engine = QdrantRagEngine(
        client=client,
        embedder=DeterministicEmbeddingProvider(vector_size=16),
        vector_size=16,
    )
    ai_generator = _RecordingAiRuleGenerator()
    query = RulebookQuestion(
        game_id="catan",
        game_title="Catan",
        question="How do I win?",
    )

    # Act / Assert
    with pytest.raises(ManualNotFoundError, match="catan"):
        await answer_rulebook_question(
            rag_engine=engine,
            ai_generator=ai_generator,
            query=query,
        )
    assert len(ai_generator.calls) == 0
    await client.close()


def test_should_validate_inputs_when_constructing_rulebook_question() -> None:
    # Act / Assert
    with pytest.raises(DomainValidationError, match="canonical normalized slug"):
        RulebookQuestion(
            game_id="Catan!",
            game_title="Catan",
            question="How do I win?",
        )

    with pytest.raises(DomainValidationError, match="game_title"):
        RulebookQuestion(
            game_id="catan",
            game_title="   ",
            question="How do I win?",
        )

    with pytest.raises(DomainValidationError, match="question"):
        RulebookQuestion(
            game_id="catan",
            game_title="Catan",
            question="   ",
        )

    with pytest.raises(DomainValidationError, match="top_k"):
        RulebookQuestion(
            game_id="catan",
            game_title="Catan",
            question="How do I win?",
            top_k=0,
        )
