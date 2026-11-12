"""Shared test fixtures for BoardGameRules test suite."""

from datetime import UTC, datetime

import pytest

from boardgamerules.domain import (
    GameManual,
    ManualSource,
    PendingPdfManual,
    RuleChunk,
    UserProfile,
)


@pytest.fixture
def fixed_utc_now() -> datetime:
    return datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_user(fixed_utc_now: datetime) -> UserProfile:
    return UserProfile(
        user_id="user-001",
        google_sub="google-oauth-sub-123",
        email="player@example.com",
        display_name="BoardGameFan",
        created_at=fixed_utc_now,
    )


@pytest.fixture
def sample_chunk() -> RuleChunk:
    return RuleChunk(
        chunk_id="chunk-catan-01",
        game_id="catan",
        text="Players begin the game with 2 settlements and 2 roads.",
        page_number=3,
        section_title="Setup",
    )


@pytest.fixture
def sample_manual(fixed_utc_now: datetime) -> GameManual:
    return GameManual(
        manual_id="manual-catan-01",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.MANUAL_PDF,
        summary_markdown="Collect resources and build settlements to reach 10 VP.",
        source_url_or_path="processed/catan.pdf",
        bgg_id=13,
        indexed_at=fixed_utc_now,
    )


@pytest.fixture
def sample_pending_pdf(fixed_utc_now: datetime) -> PendingPdfManual:
    return PendingPdfManual(
        pending_id="pending-001",
        file_key="incoming/catan_rules.pdf",
        game_title="Catan",
        created_at=fixed_utc_now,
    )
