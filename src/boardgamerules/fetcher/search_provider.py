"""Search-grounded rulebook PDF URL discovery powered by Google Gemini."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from google.genai import types as genai_types

from boardgamerules.domain.exceptions import ExternalRuleFetchError
from boardgamerules.domain.validators import require_non_blank

_URL_PATTERN = re.compile(r"https://[^\s<>()\"'\]]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?"
logger = logging.getLogger(__name__)


class RulebookUrlFinder(ABC):
    @abstractmethod
    async def find_pdf_urls(self, game_title: str) -> tuple[str, ...]: ...


# CONCEPT: [AI Engineering] Search-Grounded URL Discovery (Grounding Metadata)
# "Grounding" means anchoring an AI model's answer in verifiable real-world facts rather
# than letting it guess from memory (which often hallucinates broken links). With Google
# Search grounding enabled, Gemini attaches `grounding_chunks` metadata containing the actual
# web pages and PDF URLs returned by Google Search. We extract and prioritize these verified
# grounding links ahead of any unverified URLs mentioned in the generated text.
class GeminiRulebookUrlFinder(RulebookUrlFinder):
    def __init__(self, client: Any, model: str = "gemini-2.5-flash") -> None:
        require_non_blank(model, "model")
        self._client = client
        self._model = model

    async def find_pdf_urls(self, game_title: str) -> tuple[str, ...]:
        require_non_blank(game_title, "game_title")
        prompt = _build_search_prompt(game_title)
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    temperature=0.0,
                ),
            )
        except Exception as exc:
            raise ExternalRuleFetchError(
                f"Gemini search grounding failed for '{game_title}': {exc}"
            ) from exc

        grounding_urls = _extract_grounding_urls(response)
        text_urls = _extract_text_urls(response)
        ordered = _deduplicate_urls((*grounding_urls, *text_urls))
        logger.debug(
            "Discovered candidate rulebook URLs via Gemini search",
            extra={"candidate_count": len(ordered)},
        )
        return ordered


def _build_search_prompt(game_title: str) -> str:
    return (
        f"Find direct downloadable official PDF rulebook URLs for the board game '{game_title}'. "
        "Prefer official publisher websites and direct .pdf links. "
        "List only the direct URLs, one per line."
    )


def _extract_grounding_urls(response: Any) -> list[str]:
    scored: list[tuple[int, int, str]] = []
    candidates = getattr(response, "candidates", None) or ()
    order = 0
    for candidate in candidates:
        metadata = getattr(candidate, "grounding_metadata", None)
        chunks = getattr(metadata, "grounding_chunks", None) or ()
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None)
            if not uri:
                continue
            title = str(getattr(web, "title", "") or "")
            scored.append((_score_candidate(uri, title), order, uri.strip()))
            order += 1

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [uri for _, _, uri in scored]


def _extract_text_urls(response: Any) -> list[str]:
    text = getattr(response, "text", None) or ""
    matches = [match.rstrip(_TRAILING_PUNCTUATION) for match in _URL_PATTERN.findall(text)]
    matches.sort(key=lambda uri: -_score_candidate(uri, ""))
    return matches


def _score_candidate(uri: str, title: str) -> int:
    combined = f"{uri} {title}".lower()
    score = 0
    if ".pdf" in combined or "pdf" in combined:
        score += 3
    if "rule" in combined or "manual" in combined:
        score += 2
    return score


def _deduplicate_urls(urls: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return tuple(unique)
