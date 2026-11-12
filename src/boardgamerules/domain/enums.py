"""Domain enumerations for rule sources, manual statuses, and saved entry types."""

from __future__ import annotations

from enum import StrEnum


class ManualSource(StrEnum):
    MANUAL_PDF = "manual_pdf"
    INTERNET_API = "internet_api"
    AI_GENERATED = "ai_generated"


class ManualStatus(StrEnum):
    READY = "ready"
    SUPERSEDED = "superseded"


class PendingPdfStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SavedEntryType(StrEnum):
    FULL_RULES = "full_rules"
    QUICK_RECAP = "quick_recap"
    QA_ANSWER = "qa_answer"
