"""Gemini-powered AI rule generator implementing schema-enforced structured generation."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from boardgamerules.ai.config import AiSettings
from boardgamerules.ai.prompts import (
    PromptBundle,
    build_fallback_rules_prompt,
    build_quick_recap_prompt,
    build_rule_answer_prompt,
)
from boardgamerules.ai.schemas import (
    FallbackRulesSchema,
    QuickRecapSchema,
    RuleAnswerSchema,
    map_fallback_rules_to_domain,
    map_quick_recap_to_domain,
    map_rule_answer_to_domain,
)
from boardgamerules.domain.ai import GeneratedRuleAnswer, GeneratedRulebook, QuickRecap
from boardgamerules.domain.contracts import AiRuleGenerator
from boardgamerules.domain.exceptions import AiGenerationError, DomainValidationError
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.domain.validators import require_non_blank

logger = logging.getLogger(__name__)


# CONCEPT: [AI Engineering] Structured LLM Outputs (Schema-Enforced JSON)
# Guarantees that the LLM produces valid, type-safe JSON matching a pre-defined schema. Rather
# than parsing free-form Markdown with fragile regular expressions, the model's generation tokens
# are constrained directly by the Gemini engine to match the required fields and types.
class GeminiAiRuleGenerator(AiRuleGenerator):
    def __init__(self, client: Any, settings: AiSettings | None = None) -> None:
        self._client = client
        self._settings = settings or AiSettings()

    async def generate_fallback_rules(self, game_title: str) -> GeneratedRulebook:
        require_non_blank(game_title, "game_title")
        prompt = build_fallback_rules_prompt(game_title)
        logger.debug(
            "Generating fallback rules via Gemini",
            extra={"model": self._settings.gemini_model, "game_title_length": len(game_title)},
        )
        schema = await self._generate_with_retry(
            prompt=prompt,
            schema_cls=FallbackRulesSchema,
            operation="generate_fallback_rules",
        )
        return map_fallback_rules_to_domain(schema, game_title)

    async def generate_quick_recap(
        self,
        game_title: str,
        chunks: Sequence[RuleChunk],
    ) -> QuickRecap:
        require_non_blank(game_title, "game_title")
        prompt = build_quick_recap_prompt(game_title, chunks, self._settings.max_context_chars)
        logger.debug(
            "Generating quick recap via Gemini",
            extra={
                "model": self._settings.gemini_model,
                "chunk_count": len(chunks),
                "is_grounded": bool(chunks),
            },
        )
        schema = await self._generate_with_retry(
            prompt=prompt,
            schema_cls=QuickRecapSchema,
            operation="generate_quick_recap",
        )
        return map_quick_recap_to_domain(
            schema=schema,
            game_title=game_title,
            allowed_chunk_ids=prompt.included_chunk_ids,
            is_grounded=bool(chunks),
        )

    async def answer_question(
        self,
        game_title: str,
        question: str,
        chunks: Sequence[RuleChunk],
    ) -> GeneratedRuleAnswer:
        require_non_blank(game_title, "game_title")
        require_non_blank(question, "question")
        prompt = build_rule_answer_prompt(
            game_title=game_title,
            question=question,
            chunks=chunks,
            max_context_chars=self._settings.max_context_chars,
        )
        logger.debug(
            "Synthesizing rule answer via Gemini",
            extra={
                "model": self._settings.gemini_model,
                "chunk_count": len(chunks),
                "question_length": len(question),
                "is_grounded": bool(chunks),
            },
        )
        schema = await self._generate_with_retry(
            prompt=prompt,
            schema_cls=RuleAnswerSchema,
            operation="answer_question",
        )
        return map_rule_answer_to_domain(
            schema=schema,
            allowed_chunk_ids=prompt.included_chunk_ids,
            is_grounded=bool(chunks),
        )

    async def _generate_with_retry[SchemaT: BaseModel](
        self,
        prompt: PromptBundle,
        schema_cls: type[SchemaT],
        operation: str,
    ) -> SchemaT:
        config = genai_types.GenerateContentConfig(
            system_instruction=prompt.system_instruction,
            response_mime_type="application/json",
            response_schema=schema_cls,
            temperature=self._settings.temperature,
            max_output_tokens=self._settings.max_output_tokens,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        )

        for attempt in range(self._settings.max_retries + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=prompt.user_prompt,
                    config=config,
                )
                _check_finish_reason(response, operation)
                return _parse_structured_response(response, schema_cls, operation)
            except AiGenerationError:
                raise
            except Exception as exc:
                if _is_rate_limit_error(exc) and attempt < self._settings.max_retries:
                    wait_seconds = _parse_retry_delay_seconds(
                        str(exc),
                        self._settings.base_retry_seconds,
                        self._settings.max_retry_wait_seconds,
                    )
                    logger.warning(
                        "Gemini rate limit hit during rule generation; retrying after backoff",
                        extra={
                            "model": self._settings.gemini_model,
                            "operation": operation,
                            "attempt": attempt + 1,
                            "wait_seconds": wait_seconds,
                        },
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                raise AiGenerationError(
                    f"Gemini generation failed for '{operation}': {type(exc).__name__}"
                ) from exc

        raise AiGenerationError(
            f"Exhausted retries for Gemini model '{self._settings.gemini_model}' "
            f"on operation '{operation}'."
        )


def create_gemini_ai_generator(settings: AiSettings) -> GeminiAiRuleGenerator:
    if settings.use_vertexai:
        client = genai.Client(vertexai=True)
    elif settings.gemini_api_key:
        client = genai.Client(api_key=settings.gemini_api_key)
    else:
        raise DomainValidationError(
            "Set GEMINI_API_KEY or GOOGLE_GENAI_USE_VERTEXAI=true to create GeminiAiRuleGenerator."
        )
    return GeminiAiRuleGenerator(client=client, settings=settings)


_RETRY_DELAY_PATTERN = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)


def _check_finish_reason(response: Any, operation: str) -> None:
    candidates = getattr(response, "candidates", None) or ()
    if not candidates:
        raise AiGenerationError(f"Gemini returned no candidates for '{operation}'.")

    finish_reason = getattr(candidates[0], "finish_reason", None)
    if finish_reason is not None:
        reason_str = str(finish_reason).upper()
        if "STOP" not in reason_str and finish_reason != genai_types.FinishReason.STOP:
            raise AiGenerationError(
                f"Gemini generation stopped unexpectedly for '{operation}' "
                f"(finish_reason: {finish_reason})."
            )


def _parse_structured_response[SchemaT: BaseModel](
    response: Any,
    schema_cls: type[SchemaT],
    operation: str,
) -> SchemaT:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema_cls):
        return parsed

    raw_text = getattr(response, "text", None)
    if not raw_text or not raw_text.strip():
        raise AiGenerationError(f"Gemini returned empty response for '{operation}'.")

    try:
        return schema_cls.model_validate_json(raw_text.strip())
    except ValidationError as exc:
        raise AiGenerationError(
            f"Gemini returned invalid structured output for '{operation}' "
            f"({exc.error_count()} validation error(s))."
        ) from exc


def _is_rate_limit_error(exc: Exception) -> bool:
    if getattr(exc, "code", None) == 429:
        return True
    message = str(exc).upper()
    return "429" in message or "RESOURCE_EXHAUSTED" in message


def _parse_retry_delay_seconds(error_text: str, default_seconds: float, max_wait: float) -> float:
    match = _RETRY_DELAY_PATTERN.search(error_text)
    delay = float(match.group(1)) + 1.0 if match is not None else default_seconds
    return min(max(delay, 0.0), max_wait)
