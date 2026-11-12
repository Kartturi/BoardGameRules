"""Domain models, contracts, and exceptions for BoardGameRules."""

from boardgamerules.domain.contracts import (
    AiRuleGenerator,
    GameManualRepository,
    NoSqlRepository,
    PdfStorage,
    PendingPdfRepository,
    RagEngine,
    RulebookFetcher,
    UserHistoryRepository,
    UserRepository,
)
from boardgamerules.domain.enums import (
    ManualSource,
    ManualStatus,
    PendingPdfStatus,
    SavedEntryType,
)
from boardgamerules.domain.exceptions import (
    AiGenerationError,
    BoardGameRulesError,
    DomainValidationError,
    ExternalRuleFetchError,
    ManualNotFoundError,
    RagIngestionError,
    RulebookNotFoundError,
    StorageOperationError,
)
from boardgamerules.domain.manual import FetchedRulebook, GameManual, PendingPdfManual
from boardgamerules.domain.rag import RuleAnswer, RuleChunk
from boardgamerules.domain.user import SavedUserEntry, UserProfile
from boardgamerules.domain.validators import compute_pdf_sha256, normalize_game_id

__all__ = [
    "AiGenerationError",
    "AiRuleGenerator",
    "BoardGameRulesError",
    "DomainValidationError",
    "ExternalRuleFetchError",
    "FetchedRulebook",
    "GameManual",
    "GameManualRepository",
    "ManualNotFoundError",
    "ManualSource",
    "ManualStatus",
    "NoSqlRepository",
    "PdfStorage",
    "PendingPdfManual",
    "PendingPdfRepository",
    "PendingPdfStatus",
    "RagEngine",
    "RagIngestionError",
    "RuleAnswer",
    "RuleChunk",
    "RulebookFetcher",
    "RulebookNotFoundError",
    "SavedEntryType",
    "SavedUserEntry",
    "StorageOperationError",
    "UserHistoryRepository",
    "UserProfile",
    "UserRepository",
    "compute_pdf_sha256",
    "normalize_game_id",
]
