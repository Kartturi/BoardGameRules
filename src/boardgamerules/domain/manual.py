"""Board game manual, pending PDF queue, and external rulebook payload entities."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from boardgamerules.domain.enums import ManualSource, ManualStatus, PendingPdfStatus
from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import (
    compute_pdf_sha256,
    require_canonical_game_id,
    require_non_blank,
    require_utc_datetime,
    utc_now,
    validate_safe_file_key,
    validate_sha256_hex,
)


# CONCEPT: [AI Engineering] Tiered Source Attribution & Verification Badge
# When Tier-3 AI fallback generates rules because no official PDF was found, we cache them
# with source=AI_GENERATED (is_verified=False). When an official PDF arrives later, the AI
# version is marked SUPERSEDED so verified ground-truth rules take precedence.
@dataclass(frozen=True)
class GameManual:
    manual_id: str
    game_id: str
    game_title: str
    source: ManualSource
    edition: str = "standard"
    status: ManualStatus = ManualStatus.READY
    summary_markdown: str = ""
    source_url_or_path: str | None = None
    bgg_id: int | None = None
    product_code: str | None = None
    content_sha256: str | None = None
    indexed_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        require_non_blank(self.manual_id, "manual_id")
        require_canonical_game_id(self.game_id)
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.edition, "edition")
        if self.bgg_id is not None and self.bgg_id < 1:
            raise DomainValidationError("bgg_id must be a positive integer when provided.")
        if self.product_code is not None:
            require_non_blank(self.product_code, "product_code")
        if self.content_sha256 is not None:
            validate_sha256_hex(self.content_sha256)
        require_utc_datetime(self.indexed_at, "indexed_at")

    @property
    def is_verified(self) -> bool:
        return self.source != ManualSource.AI_GENERATED

    # CONCEPT: [Design Pattern] Immutable State Machine Transition
    # Instead of mutating self.status in place, transition methods return a new frozen instance
    # via dataclasses.replace(), preserving Command-Query Separation and history safety.
    def mark_superseded(self) -> GameManual:
        return replace(self, status=ManualStatus.SUPERSEDED)


@dataclass(frozen=True)
class PendingPdfManual:
    pending_id: str
    file_key: str
    game_title: str
    edition: str = "standard"
    content_sha256: str | None = None
    status: PendingPdfStatus = PendingPdfStatus.PENDING
    error_message: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    processed_at: datetime | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.pending_id, "pending_id")
        validate_safe_file_key(self.file_key)
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.edition, "edition")
        if self.content_sha256 is not None:
            validate_sha256_hex(self.content_sha256)
        require_utc_datetime(self.created_at, "created_at")
        if self.processed_at is not None:
            require_utc_datetime(self.processed_at, "processed_at")

    def mark_processing(self) -> PendingPdfManual:
        return replace(self, status=PendingPdfStatus.PROCESSING, error_message=None)

    def mark_completed(self, processed_at: datetime | None = None) -> PendingPdfManual:
        timestamp = processed_at or utc_now()
        return replace(
            self,
            status=PendingPdfStatus.COMPLETED,
            error_message=None,
            processed_at=timestamp,
        )

    def mark_failed(
        self,
        error_message: str,
        processed_at: datetime | None = None,
    ) -> PendingPdfManual:
        require_non_blank(error_message, "error_message")
        timestamp = processed_at or utc_now()
        return replace(
            self,
            status=PendingPdfStatus.FAILED,
            error_message=error_message,
            processed_at=timestamp,
        )


@dataclass(frozen=True)
class FetchedRulebook:
    game_title: str
    source_url: str
    pdf_bytes: bytes
    edition: str = "standard"
    bgg_id: int | None = None
    product_code: str | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.game_title, "game_title")
        require_non_blank(self.source_url, "source_url")
        require_non_blank(self.edition, "edition")
        if not self.pdf_bytes:
            raise DomainValidationError("pdf_bytes cannot be empty.")
        if self.bgg_id is not None and self.bgg_id < 1:
            raise DomainValidationError("bgg_id must be a positive integer when provided.")
        if self.product_code is not None:
            require_non_blank(self.product_code, "product_code")

    @property
    def content_sha256(self) -> str:
        return compute_pdf_sha256(self.pdf_bytes)
