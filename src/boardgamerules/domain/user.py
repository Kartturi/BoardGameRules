"""User profile and saved user history domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from boardgamerules.domain.enums import ManualSource, SavedEntryType
from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import (
    require_canonical_game_id,
    require_non_blank,
    require_utc_datetime,
    utc_now,
)


# CONCEPT: [Design Pattern] Value Object & Immutable Entity
# Using @dataclass(frozen=True) makes domain entities thread-safe, hashable, and predictable:
# functions cannot secretly mutate shared state as objects pass through the pipeline.
@dataclass(frozen=True)
class UserProfile:
    user_id: str
    google_sub: str
    email: str
    display_name: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        require_non_blank(self.user_id, "user_id")
        require_non_blank(self.google_sub, "google_sub")
        require_non_blank(self.email, "email")
        if "@" not in self.email:
            raise DomainValidationError("email must be a valid email address.")
        require_non_blank(self.display_name, "display_name")
        require_utc_datetime(self.created_at, "created_at")


@dataclass(frozen=True)
class SavedUserEntry:
    entry_id: str
    user_id: str
    game_id: str
    game_title: str
    entry_type: SavedEntryType
    prompt_or_heading: str
    content_markdown: str
    source: ManualSource
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        require_non_blank(self.entry_id, "entry_id")
        require_non_blank(self.user_id, "user_id")
        require_canonical_game_id(self.game_id)
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.prompt_or_heading, "prompt_or_heading")
        require_non_blank(self.content_markdown, "content_markdown")
        require_utc_datetime(self.created_at, "created_at")
