"""Domain exceptions for BoardGameRules."""

from __future__ import annotations


# CONCEPT: [Design Pattern] Domain Exception Hierarchy
# Defining a single base domain exception (BoardGameRulesError) with specific subclasses
# lets higher layers (like FastAPI exception handlers) map domain failures cleanly to HTTP
# status codes (e.g., 400, 404, 502) without coupling domain code to HTTP frameworks.
class BoardGameRulesError(Exception):
    pass


class DomainValidationError(BoardGameRulesError):
    pass


class ManualNotFoundError(BoardGameRulesError):
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        super().__init__(f"No indexed manual found for game_id '{game_id}'.")


class RulebookNotFoundError(BoardGameRulesError):
    def __init__(self, game_title: str) -> None:
        self.game_title = game_title
        super().__init__(f"Could not find an online rulebook for '{game_title}'.")


class ExternalRuleFetchError(BoardGameRulesError):
    pass


class RagIngestionError(BoardGameRulesError):
    pass


class StorageOperationError(BoardGameRulesError):
    pass


class AiGenerationError(BoardGameRulesError):
    pass
