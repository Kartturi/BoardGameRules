"""Grounded RAG question-answering pipeline combining vector retrieval and AI generation."""

from __future__ import annotations

from dataclasses import dataclass

from boardgamerules.domain.contracts import AiRuleGenerator, RagEngine
from boardgamerules.domain.enums import ManualSource
from boardgamerules.domain.exceptions import DomainValidationError, ManualNotFoundError
from boardgamerules.domain.rag import RuleAnswer
from boardgamerules.domain.validators import require_canonical_game_id, require_non_blank


@dataclass(frozen=True)
class RulebookQuestion:
    game_id: str
    game_title: str
    question: str
    top_k: int = 5
    source: ManualSource = ManualSource.MANUAL_PDF

    def __post_init__(self) -> None:
        require_canonical_game_id(self.game_id)
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.question, "question")
        if isinstance(self.top_k, bool) or self.top_k < 1:
            raise DomainValidationError("top_k must be an integer >= 1.")


# CONCEPT: [AI Engineering] Grounded RAG Question-Answering Pipeline
# Rather than asking an LLM to answer board game rules from its pre-training memory (which
# often hallucinates house rules or wrong editions), the RAG pipeline first retrieves the
# top-k relevant rulebook chunks from the vector store. If no chunks exist for the game,
# it fails fast with ManualNotFoundError so the caller can trigger a verified fallback
# rather than letting the LLM guess without context.
async def answer_rulebook_question(
    rag_engine: RagEngine,
    ai_generator: AiRuleGenerator,
    query: RulebookQuestion,
) -> RuleAnswer:
    retrieved_chunks = await rag_engine.search_chunks(
        game_id=query.game_id,
        query=query.question,
        top_k=query.top_k,
    )
    if not retrieved_chunks:
        raise ManualNotFoundError(query.game_id)

    answer_markdown = await ai_generator.answer_question(
        game_title=query.game_title,
        question=query.question,
        chunks=retrieved_chunks,
    )
    return RuleAnswer(
        game_id=query.game_id,
        question=query.question,
        answer_markdown=answer_markdown,
        citations=retrieved_chunks,
        source=query.source,
    )
