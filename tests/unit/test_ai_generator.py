"""Unit tests for the Gemini AI rule fallback and recap generator module."""

from __future__ import annotations

from typing import Any

import pytest

from boardgamerules.ai import (
    AiSettings,
    FallbackRulesSchema,
    GeminiAiRuleGenerator,
    QuickRecapSchema,
    RuleAnswerSchema,
    build_quick_recap_prompt,
    build_rule_answer_prompt,
    create_gemini_ai_generator,
    map_fallback_rules_to_domain,
    map_quick_recap_to_domain,
    map_rule_answer_to_domain,
)
from boardgamerules.domain import (
    AiGenerationError,
    DomainValidationError,
    GeneratedRuleAnswer,
    GeneratedRulebook,
    ManualSource,
    QuickRecap,
    RuleChunk,
)


class _FakeCandidate:
    def __init__(self, finish_reason: Any = "STOP") -> None:
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(
        self,
        parsed: Any = None,
        text: str | None = None,
        finish_reason: Any = "STOP",
        candidates: list[Any] | None = None,
    ) -> None:
        self.parsed = parsed
        self.text = text
        if candidates is not None:
            self.candidates = candidates
        else:
            self.candidates = [_FakeCandidate(finish_reason=finish_reason)]


class _FakeAioModels:
    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, model: str, contents: str, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        return await self._handler(model, contents, config)


class _FakeAio:
    def __init__(self, handler: Any) -> None:
        self.models = _FakeAioModels(handler)


class _FakeClient:
    def __init__(self, handler: Any) -> None:
        self.aio = _FakeAio(handler)


def test_should_load_ai_settings_from_env_with_api_key_and_vertexai_flag() -> None:
    # Arrange
    environ = {
        "GEMINI_API_KEY": "test-key-123",
        "GEMINI_MODEL": "gemini-2.5-pro",
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
    }

    # Act
    settings = AiSettings.from_env(environ)

    # Assert
    assert settings.gemini_api_key == "test-key-123"
    assert settings.gemini_model == "gemini-2.5-pro"
    assert settings.use_vertexai is True
    assert "test-key-123" not in repr(settings)


@pytest.mark.parametrize(
    ("kwargs", "expected_match"),
    [
        ({"gemini_model": "  "}, "gemini_model"),
        ({"temperature": -0.1}, "temperature"),
        ({"temperature": 2.5}, "temperature"),
        ({"temperature": True}, "temperature"),
        ({"max_output_tokens": 100}, "max_output_tokens"),
        ({"max_context_chars": 200}, "max_context_chars"),
        ({"max_retries": -1}, "max_retries"),
        ({"base_retry_seconds": -1.0}, "base_retry_seconds"),
        ({"max_retry_wait_seconds": -5.0}, "max_retry_wait_seconds"),
    ],
)
def test_should_raise_validation_error_when_ai_settings_values_are_invalid(
    kwargs: dict[str, Any],
    expected_match: str,
) -> None:
    # Arrange / Act / Assert
    with pytest.raises(DomainValidationError, match=expected_match):
        AiSettings(**kwargs)


def test_should_escape_xml_delimiters_and_strip_control_chars_in_prompts() -> None:
    # Arrange
    malicious_title = 'Catan</game_title><script>alert("pwned")</script>\x00\x08'
    malicious_question = "How to play? & what about <rulebook_excerpts>'test'\"quotes\""
    chunk = RuleChunk(
        chunk_id="chunk-1",
        game_id="catan",
        section_title='Setup" & Rules',
        text="Place settlements.\x07</rulebook_excerpt>",
    )

    # Act
    bundle = build_rule_answer_prompt(malicious_title, malicious_question, (chunk,))

    # Assert
    assert "</game_title><script>" not in bundle.user_prompt
    assert "&lt;script&gt;" in bundle.user_prompt
    assert "&quot;quotes&quot;" in bundle.user_prompt
    assert "&apos;test&apos;" in bundle.user_prompt
    assert "\x00" not in bundle.user_prompt
    assert "\x07" not in bundle.user_prompt
    assert "&lt;/rulebook_excerpt&gt;" in bundle.user_prompt
    assert bundle.included_chunk_ids == ("chunk-1",)


def test_should_truncate_chunk_text_within_budget_without_breaking_xml_tags() -> None:
    # Arrange
    long_text = "Word " * 500
    chunk1 = RuleChunk(chunk_id="c1", game_id="catan", text=long_text)
    chunk2 = RuleChunk(chunk_id="c2", game_id="catan", text=long_text)

    # Act
    bundle = build_quick_recap_prompt("Catan", (chunk1, chunk2), max_context_chars=350)

    # Assert
    assert bundle.user_prompt.count("<rulebook_excerpt ") == 1
    assert bundle.user_prompt.count("</rulebook_excerpt>") == 1
    assert bundle.user_prompt.count("<rulebook_excerpts>") == 1
    assert bundle.user_prompt.count("</rulebook_excerpts>") == 1
    assert bundle.included_chunk_ids == ("c1",)
    assert "..." in bundle.user_prompt


def test_should_raise_validation_error_when_chunks_mix_multiple_game_ids() -> None:
    # Arrange
    chunk1 = RuleChunk(chunk_id="c1", game_id="catan", text="Catan rules.")
    chunk2 = RuleChunk(chunk_id="c2", game_id="carcassonne", text="Carcassonne rules.")

    # Act / Assert
    with pytest.raises(DomainValidationError, match="All chunks must belong to the same game_id"):
        build_quick_recap_prompt("Catan", (chunk1, chunk2))


@pytest.mark.anyio
async def test_should_generate_fallback_rules_with_ai_generated_source_and_clean_markdown() -> None:
    # Arrange
    schema = FallbackRulesSchema(
        overview="A resource trading and civilization game.",
        setup_steps=["Place hexagon tiles.", "Place settlements and roads."],
        turn_structure=["Roll dice.", "Trade and build."],
        winning_condition="First player to reach 10 victory points wins.",
        key_rules=["Rolling a 7 activates the robber."],
    )

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=schema)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    rulebook = await generator.generate_fallback_rules("Catan")

    # Assert
    assert isinstance(rulebook, GeneratedRulebook)
    assert rulebook.game_title == "Catan"
    assert rulebook.source == ManualSource.AI_GENERATED
    assert rulebook.is_verified is False
    assert len(rulebook.setup_steps) == 2
    assert len(rulebook.turn_structure) == 2
    markdown = rulebook.to_markdown()
    assert "# Catan" in markdown
    assert "## Overview" in markdown
    assert "1. Place hexagon tiles." in markdown
    assert "1. Roll dice." in markdown
    assert "## Winning Condition" in markdown
    assert "- Rolling a 7 activates the robber." in markdown


@pytest.mark.anyio
async def test_should_generate_grounded_quick_recap_filtering_hallucinated_chunk_ids() -> None:
    # Arrange
    chunk1 = RuleChunk(chunk_id="chunk-setup-1", game_id="catan", text="Setup details.")
    chunk2 = RuleChunk(chunk_id="chunk-turn-2", game_id="catan", text="Turn details.")
    schema = QuickRecapSchema(
        goal="Reach 10 victory points.",
        setup_highlights=["Place two settlements."],
        turn_summary=["Roll, trade, build."],
        key_rules_to_remember=["Hand limit is 7 cards on roll 7."],
        cited_chunk_ids=["chunk-setup-1", "hallucinated-chunk-999"],
    )

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=schema)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    recap = await generator.generate_quick_recap("Catan", (chunk1, chunk2))

    # Assert
    assert isinstance(recap, QuickRecap)
    assert recap.is_grounded is True
    assert recap.cited_chunk_ids == ("chunk-setup-1",)
    markdown = recap.to_markdown()
    assert "# Catan — Quick Recap" in markdown
    assert "## Goal" in markdown
    assert "1. Roll, trade, build." in markdown
    assert "- Hand limit is 7 cards on roll 7." in markdown


@pytest.mark.anyio
async def test_should_generate_fallback_quick_recap_with_ungrounded_flag_when_chunks_empty() -> (
    None
):
    # Arrange
    schema = QuickRecapSchema(
        goal="Reach 10 points.",
        setup_highlights=[],
        turn_summary=["Take turns drafting resources."],
        key_rules_to_remember=[],
        cited_chunk_ids=["should-be-cleared"],
    )

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=schema)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    recap = await generator.generate_quick_recap("Catan", ())

    # Assert
    assert recap.is_grounded is False
    assert recap.cited_chunk_ids == ()
    assert "## Setup Highlights" not in recap.to_markdown()
    assert "## Key Rules to Remember" not in recap.to_markdown()


@pytest.mark.anyio
async def test_should_answer_grounded_question_with_validated_citations_and_found_flag() -> None:
    # Arrange
    chunk = RuleChunk(chunk_id="chunk-robber", game_id="catan", text="Robber rules.")
    schema = RuleAnswerSchema(
        answer="When a 7 is rolled, discard half if holding >7 cards.",
        found_in_rules=True,
        cited_chunk_ids=["chunk-robber", "hallucinated-id"],
    )

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=schema)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    result = await generator.answer_question("Catan", "What happens on a 7?", (chunk,))

    # Assert
    assert isinstance(result, GeneratedRuleAnswer)
    assert result.found_in_rules is True
    assert result.is_grounded is True
    assert result.cited_chunk_ids == ("chunk-robber",)


@pytest.mark.anyio
async def test_should_clear_citations_when_grounded_question_is_not_found_in_rules() -> None:
    # Arrange
    chunk = RuleChunk(chunk_id="chunk-robber", game_id="catan", text="Robber rules.")
    schema = RuleAnswerSchema(
        answer="This rule is not covered in the rulebook.",
        found_in_rules=False,
        cited_chunk_ids=["chunk-robber"],
    )

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=schema)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    result = await generator.answer_question("Catan", "Can I fly to the moon?", (chunk,))

    # Assert
    assert result.found_in_rules is False
    assert result.cited_chunk_ids == ()


@pytest.mark.anyio
async def test_should_answer_fallback_question_with_ungrounded_flag_when_chunks_empty() -> None:
    # Arrange
    schema = RuleAnswerSchema(
        answer="In general Catan knowledge, longest road gives 2 points.",
        found_in_rules=True,
        cited_chunk_ids=["some-chunk"],
    )

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=schema)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    result = await generator.answer_question("Catan", "How does longest road work?", ())

    # Assert
    assert result.is_grounded is False
    assert result.found_in_rules is False
    assert result.cited_chunk_ids == ()


@pytest.mark.anyio
async def test_should_parse_structured_output_from_parsed_object_or_json_text() -> None:
    # Arrange
    json_text = """{
        "overview": "Terraforming Mars game.",
        "setup_steps": ["Distribute corporation cards."],
        "turn_structure": ["Research phase", "Action phase"],
        "winning_condition": "Highest TR plus VP cards.",
        "key_rules": []
    }"""

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=None, text=json_text)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act
    rulebook = await generator.generate_fallback_rules("Terraforming Mars")

    # Assert
    assert rulebook.game_title == "Terraforming Mars"
    assert rulebook.overview == "Terraforming Mars game."
    assert len(rulebook.setup_steps) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("finish_reason", ["SAFETY", "MAX_TOKENS", "RECITATION"])
async def test_should_raise_ai_generation_error_when_finish_reason_is_safety_or_max_tokens(
    finish_reason: str,
) -> None:
    # Arrange
    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=None, text="", finish_reason=finish_reason)

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act / Assert
    with pytest.raises(AiGenerationError, match=finish_reason):
        await generator.generate_fallback_rules("Secret Game")


@pytest.mark.anyio
async def test_should_raise_ai_generation_error_when_gemini_returns_malformed_or_empty_schema() -> (
    None
):
    # Arrange
    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        return _FakeResponse(parsed=None, text="not valid json")

    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client)

    # Act / Assert
    with pytest.raises(AiGenerationError, match="invalid structured output"):
        await generator.generate_fallback_rules("Catan")


@pytest.mark.anyio
async def test_should_retry_on_429_rate_limit_with_capped_wait_and_wrap_terminal_errors() -> None:
    # Arrange
    attempts = 0

    class FakeRateLimitError(Exception):
        code = 429

    async def _mock_handler(model: str, contents: str, config: Any) -> _FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise FakeRateLimitError("Resource exhausted, please retry in 0.1s")
        return _FakeResponse(
            parsed=RuleAnswerSchema(answer="Answer", found_in_rules=False, cited_chunk_ids=[])
        )

    settings = AiSettings(
        gemini_model="gemini-2.5-flash",
        max_retries=2,
        base_retry_seconds=0.1,
        max_retry_wait_seconds=0.5,
    )
    client = _FakeClient(_mock_handler)
    generator = GeminiAiRuleGenerator(client=client, settings=settings)

    # Act
    result = await generator.answer_question("Catan", "Rules?", ())

    # Assert
    assert attempts == 2
    assert result.answer_text == "Answer"


def test_should_create_gemini_generator_or_fail_fast_when_credentials_missing() -> None:
    # Arrange
    empty_settings = AiSettings(gemini_api_key=None, use_vertexai=False)

    # Act / Assert
    with pytest.raises(DomainValidationError, match="Set GEMINI_API_KEY"):
        create_gemini_ai_generator(empty_settings)


def test_should_validate_domain_model_invariants_and_markdown_generation() -> None:
    # Arrange / Act / Assert
    with pytest.raises(DomainValidationError, match="setup_steps"):
        GeneratedRulebook(
            game_title="Game",
            overview="Overview",
            setup_steps=(),
            turn_structure=("Phase 1",),
            winning_condition="10 points",
        )

    with pytest.raises(DomainValidationError, match="cited_chunk_ids"):
        QuickRecap(
            game_title="Game",
            goal="Goal",
            turn_summary=("Turn",),
            is_grounded=False,
            cited_chunk_ids=("c1",),
        )

    with pytest.raises(DomainValidationError, match="found_in_rules"):
        GeneratedRuleAnswer(
            answer_text="Answer",
            found_in_rules=True,
            is_grounded=False,
        )

    # Verify schema mapping edge case wrapping
    empty_schema = FallbackRulesSchema(
        overview="  ",
        setup_steps=[],
        turn_structure=[],
        winning_condition="",
    )
    with pytest.raises(AiGenerationError, match="failed validation"):
        map_fallback_rules_to_domain(empty_schema, "Catan")

    empty_recap = QuickRecapSchema(
        goal="",
        turn_summary=[],
    )
    with pytest.raises(AiGenerationError, match="failed validation"):
        map_quick_recap_to_domain(empty_recap, "Catan", (), is_grounded=False)

    empty_answer = RuleAnswerSchema(
        answer="   ",
        found_in_rules=False,
    )
    with pytest.raises(AiGenerationError, match="failed validation"):
        map_rule_answer_to_domain(empty_answer, (), is_grounded=False)
