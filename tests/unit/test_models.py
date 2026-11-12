"""Unit tests for core domain models and invariants."""

from datetime import UTC, datetime

import pytest

from boardgamerules.domain import (
    DomainValidationError,
    FetchedRulebook,
    GameManual,
    ManualNotFoundError,
    ManualSource,
    ManualStatus,
    PendingPdfManual,
    PendingPdfStatus,
    RuleAnswer,
    RulebookNotFoundError,
    RuleChunk,
    SavedEntryType,
    SavedUserEntry,
    UserProfile,
    compute_pdf_sha256,
    normalize_game_id,
)


@pytest.mark.parametrize(
    ("raw_title", "expected_slug"),
    [
        ("Catan", "catan"),
        ("The Settlers of Catan!", "the-settlers-of-catan"),
        ("  Ticket to Ride: Europe (2005)  ", "ticket-to-ride-europe-2005"),
        ("7 Wonders Duel", "7-wonders-duel"),
    ],
)
def test_should_normalize_game_title_into_canonical_slug(
    raw_title: str,
    expected_slug: str,
) -> None:
    slug = normalize_game_id(raw_title)

    assert slug == expected_slug


@pytest.mark.parametrize("invalid_title", ["", "   ", "!!!", "---"])
def test_should_raise_validation_error_when_game_title_has_no_alphanumeric_chars(
    invalid_title: str,
) -> None:
    with pytest.raises(DomainValidationError):
        normalize_game_id(invalid_title)


def test_should_create_user_profile_with_valid_attributes(sample_user: UserProfile) -> None:
    assert sample_user.user_id == "user-001"
    assert sample_user.email == "player@example.com"


def test_should_raise_validation_error_when_user_email_is_invalid() -> None:
    with pytest.raises(DomainValidationError, match="email must be a valid email address"):
        UserProfile(
            user_id="user-001",
            google_sub="sub-123",
            email="not-an-email",
            display_name="Alice",
        )


def test_should_raise_validation_error_when_datetime_is_naive() -> None:
    naive_timestamp = datetime(2026, 11, 12, 12, 0, 0)

    with pytest.raises(DomainValidationError, match="timezone-aware"):
        UserProfile(
            user_id="user-001",
            google_sub="sub-123",
            email="alice@example.com",
            display_name="Alice",
            created_at=naive_timestamp,
        )


def test_should_raise_validation_error_when_rule_chunk_has_unnormalized_game_id() -> None:
    with pytest.raises(DomainValidationError, match="canonical normalized slug"):
        RuleChunk(
            chunk_id="chunk-1",
            game_id="Catan With Spaces",
            text="Some rule text",
        )


def test_should_raise_validation_error_when_rule_chunk_page_number_is_zero() -> None:
    with pytest.raises(DomainValidationError, match="page_number must be >= 1"):
        RuleChunk(
            chunk_id="chunk-1",
            game_id="catan",
            text="Some rule text",
            page_number=0,
        )


def test_should_distinguish_verified_manual_from_ai_generated_fallback(
    sample_manual: GameManual,
) -> None:
    ai_manual = GameManual(
        manual_id="man-ai-1",
        game_id="rainbow",
        game_title="Rainbow",
        source=ManualSource.AI_GENERATED,
    )

    assert sample_manual.is_verified is True
    assert ai_manual.is_verified is False


def test_should_return_new_superseded_manual_without_mutating_original(
    sample_manual: GameManual,
) -> None:
    superseded = sample_manual.mark_superseded()

    assert sample_manual.status == ManualStatus.READY
    assert superseded.status == ManualStatus.SUPERSEDED
    assert superseded.manual_id == sample_manual.manual_id


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "",
        "   ",
        "/etc/passwd",
        "\\windows\\system32",
        "C:/Windows/System32/cmd.exe",
        "incoming/rules\x00.pdf",
        "incoming/rules\n.pdf",
        "incoming/../../secret.pdf",
        "../outside.pdf",
        "incoming//double_slash.pdf",
        "incoming/./dot.pdf",
    ],
)
def test_should_reject_unsafe_file_key_in_pending_pdf_manual(unsafe_key: str) -> None:
    with pytest.raises(DomainValidationError, match="file_key"):
        PendingPdfManual(
            pending_id="p-1",
            file_key=unsafe_key,
            game_title="Catan",
        )


def test_should_transition_pending_pdf_through_processing_to_completed(
    sample_pending_pdf: PendingPdfManual,
) -> None:
    completion_time = datetime(2026, 11, 12, 13, 30, 0, tzinfo=UTC)

    processing = sample_pending_pdf.mark_processing()
    completed = processing.mark_completed(processed_at=completion_time)

    assert sample_pending_pdf.status == PendingPdfStatus.PENDING
    assert processing.status == PendingPdfStatus.PROCESSING
    assert completed.status == PendingPdfStatus.COMPLETED
    assert completed.processed_at == completion_time
    assert completed.error_message is None


def test_should_transition_pending_pdf_to_failed_with_required_reason(
    sample_pending_pdf: PendingPdfManual,
) -> None:
    failed = sample_pending_pdf.mark_failed("Corrupted PDF header")

    assert failed.status == PendingPdfStatus.FAILED
    assert failed.error_message == "Corrupted PDF header"
    assert failed.processed_at is not None


def test_should_raise_validation_error_when_marking_pending_pdf_failed_with_blank_reason(
    sample_pending_pdf: PendingPdfManual,
) -> None:
    with pytest.raises(DomainValidationError, match="error_message"):
        sample_pending_pdf.mark_failed("   ")


def test_should_defensively_coerce_rule_answer_citations_to_immutable_tuple(
    sample_chunk: RuleChunk,
) -> None:
    mutable_list = [sample_chunk]

    answer = RuleAnswer(
        game_id="catan",
        question="How many settlements do you start with?",
        answer_markdown="You start with 2 settlements and 2 roads.",
        citations=mutable_list,  # type: ignore[arg-type]
    )
    mutable_list.clear()

    assert isinstance(answer.citations, tuple)
    assert len(answer.citations) == 1
    assert answer.citations[0] == sample_chunk


def test_should_create_saved_user_entry_and_fetched_rulebook() -> None:
    entry = SavedUserEntry(
        entry_id="entry-1",
        user_id="user-001",
        game_id="catan",
        game_title="Catan",
        entry_type=SavedEntryType.QUICK_RECAP,
        prompt_or_heading="Quick Recap",
        content_markdown="1. Roll dice. 2. Trade. 3. Build.",
        source=ManualSource.MANUAL_PDF,
    )
    fetched = FetchedRulebook(
        game_title="Catan",
        source_url="https://example.com/catan.pdf",
        pdf_bytes=b"%PDF-1.7 sample bytes",
        bgg_id=13,
    )

    assert entry.entry_type == SavedEntryType.QUICK_RECAP
    assert fetched.pdf_bytes.startswith(b"%PDF")


def test_should_format_domain_lookup_exceptions_with_context() -> None:
    manual_err = ManualNotFoundError("catan")
    fetch_err = RulebookNotFoundError("Rainbow")

    assert manual_err.game_id == "catan"
    assert "catan" in str(manual_err)
    assert fetch_err.game_title == "Rainbow"
    assert "Rainbow" in str(fetch_err)


def test_should_compute_deterministic_sha256_and_validate_manual_deduplication_fields() -> None:
    pdf_bytes = b"%PDF-1.7 Catan 5th Edition Rules"
    digest = compute_pdf_sha256(pdf_bytes)
    fetched = FetchedRulebook(
        game_title="Catan",
        source_url="https://example.com/catan-5e.pdf",
        pdf_bytes=pdf_bytes,
        edition="5th-edition",
        bgg_id=13,
        product_code="4002051693251",
    )
    manual = GameManual(
        manual_id="man-catan-5e",
        game_id="catan",
        game_title="Catan",
        source=ManualSource.INTERNET_API,
        edition=fetched.edition,
        bgg_id=fetched.bgg_id,
        product_code=fetched.product_code,
        content_sha256=fetched.content_sha256,
    )

    assert len(digest) == 64
    assert fetched.content_sha256 == digest
    assert manual.content_sha256 == digest
    assert manual.edition == "5th-edition"
    assert manual.product_code == "4002051693251"


def test_should_reject_invalid_sha256_digest_on_game_manual() -> None:
    with pytest.raises(DomainValidationError, match="content_sha256"):
        GameManual(
            manual_id="man-1",
            game_id="catan",
            game_title="Catan",
            source=ManualSource.MANUAL_PDF,
            content_sha256="not-a-valid-sha256",
        )
