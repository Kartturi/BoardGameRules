"""BoardGameRules entry point demonstrating core domain models."""

from boardgamerules.domain import (
    GameManual,
    ManualSource,
    PendingPdfManual,
    RuleAnswer,
    RuleChunk,
    normalize_game_id,
)


def main() -> None:
    game_title = "The Settlers of Catan"
    game_id = normalize_game_id(game_title)

    pending = PendingPdfManual(
        pending_id="pdf-001",
        file_key="incoming/catan_base_rules.pdf",
        game_title=game_title,
    )
    completed = pending.mark_processing().mark_completed()

    manual = GameManual(
        manual_id="man-001",
        game_id=game_id,
        game_title=game_title,
        source=ManualSource.MANUAL_PDF,
        summary_markdown="Trade, build, and settle the island of Catan to reach 10 victory points.",
    )

    chunk = RuleChunk(
        chunk_id="chunk-001",
        game_id=game_id,
        text="When a 7 is rolled, any player with more than 7 resource cards discards half.",
        page_number=4,
        section_title="The Robber",
    )

    answer = RuleAnswer(
        game_id=game_id,
        question="What happens when a 7 is rolled?",
        answer_markdown=(
            "Players with more than 7 cards discard half (rounded down), "
            "and the active player moves the Robber."
        ),
        citations=(chunk,),
        source=manual.source,
    )

    cited_page = answer.citations[0].page_number
    print(f"Game '{manual.game_title}' (id={manual.game_id}, verified={manual.is_verified})")
    print(f"PDF '{completed.file_key}' ingestion status: {completed.status}")
    print(f"Q: {answer.question}\nA: {answer.answer_markdown} (cited page {cited_page})")


if __name__ == "__main__":
    main()
