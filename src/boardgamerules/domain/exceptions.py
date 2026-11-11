"""Domain exceptions for BoardGameRules.

Explicit exceptions ensure that error conditions are clear, domain-specific,
and easy to catch and handle without relying on generic Python errors.
"""


class BoardGameError(Exception):
    """Base exception for all BoardGameRules domain errors."""


class RuleViolationError(BoardGameError):
    """Raised when an action violates the rules of the game."""

    def __init__(self, rule_name: str, reason: str) -> None:
        self.rule_name = rule_name
        self.reason = reason
        super().__init__(f"Rule violation [{rule_name}]: {reason}")
