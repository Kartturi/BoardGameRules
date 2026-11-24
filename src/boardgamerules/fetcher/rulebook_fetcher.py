"""Internet rulebook fetcher coordinating search discovery and verified PDF download."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from boardgamerules.domain.contracts import RulebookFetcher
from boardgamerules.domain.exceptions import (
    DomainValidationError,
    ExternalRuleFetchError,
    RagIngestionError,
    RulebookNotFoundError,
)
from boardgamerules.domain.manual import FetchedRulebook
from boardgamerules.domain.validators import require_non_blank
from boardgamerules.fetcher.pdf_downloader import DownloadedPdf, PdfDownloader
from boardgamerules.fetcher.search_provider import RulebookUrlFinder
from boardgamerules.rag.pdf_extractor import PdfTextExtractor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RulebookFetcherConfig:
    max_candidates: int = 5

    def __post_init__(self) -> None:
        if self.max_candidates < 1:
            raise DomainValidationError("max_candidates must be >= 1.")


class InternetRulebookFetcher(RulebookFetcher):
    def __init__(
        self,
        url_finder: RulebookUrlFinder,
        downloader: PdfDownloader,
        pdf_extractor: PdfTextExtractor,
        *,
        config: RulebookFetcherConfig | None = None,
    ) -> None:
        self._url_finder = url_finder
        self._downloader = downloader
        self._pdf_extractor = pdf_extractor
        self._config = config or RulebookFetcherConfig()

    async def fetch_rulebook(self, game_title: str) -> FetchedRulebook:
        require_non_blank(game_title, "game_title")
        cleaned_title = game_title.strip()
        candidate_urls = await self._url_finder.find_pdf_urls(cleaned_title)

        candidates_to_try = candidate_urls[: self._config.max_candidates]
        for candidate_url in candidates_to_try:
            downloaded = await self._try_download_valid_pdf(candidate_url)
            if downloaded is not None:
                logger.info(
                    "Fetched verified online PDF rulebook",
                    extra={
                        "game_title": cleaned_title,
                        "byte_count": len(downloaded.pdf_bytes),
                    },
                )
                return FetchedRulebook(
                    game_title=cleaned_title,
                    source_url=downloaded.final_url,
                    pdf_bytes=downloaded.pdf_bytes,
                )

        logger.info(
            "No valid online PDF rulebook found",
            extra={"game_title": cleaned_title, "candidates_tried": len(candidates_to_try)},
        )
        raise RulebookNotFoundError(cleaned_title)

    async def _try_download_valid_pdf(self, candidate_url: str) -> DownloadedPdf | None:
        try:
            downloaded = await self._downloader.download_pdf(candidate_url)
            await asyncio.to_thread(self._pdf_extractor.extract_pages, downloaded.pdf_bytes)
            return downloaded
        except (ExternalRuleFetchError, RagIngestionError) as exc:
            logger.debug(
                "Skipping invalid rulebook candidate",
                extra={"error_type": type(exc).__name__},
            )
            return None
