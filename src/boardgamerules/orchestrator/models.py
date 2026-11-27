"""Domain entities and parameter models for the rule orchestrator service."""

from __future__ import annotations

from dataclasses import dataclass, field

from boardgamerules.domain.contracts import (
    AiRuleGenerator,
    GameManualRepository,
    RagEngine,
    RulebookFetcher,
    UserHistoryRepository,
)
from boardgamerules.domain.enums import ManualSource, SavedEntryType
from boardgamerules.domain.manual import GameManual
from boardgamerules.domain.validators import normalize_game_id, require_non_blank
from boardgamerules.rag.chunker import ChunkingConfig
from boardgamerules.rag.pdf_extractor import PdfTextExtractor, PyMuPdfTextExtractor


# CONCEPT: [Design Pattern] Parameter Object (Dependency Injection Bundle)
# Bundling multiple collaborating services and configuration objects into a single immutable
# dataclass prevents long, fragile constructor signatures (known as the "Long Parameter List" code
# smell). It simplifies wiring dependencies in DI containers and testing with mock/fake adapters.
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

    def __post_init__(self) -> None:
        require_non_blank(self.user_id, "user_id")
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.prompt_or_heading, "prompt_or_heading")
        require_non_blank(self.content_markdown, "content_markdown")
        normalize_game_id(self.game_title)
