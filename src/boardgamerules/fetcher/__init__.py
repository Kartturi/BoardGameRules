"""Internet rulebook discovery and SSRF-safe PDF downloading."""

from boardgamerules.fetcher.config import FetcherSettings
from boardgamerules.fetcher.pdf_downloader import DownloadedPdf, PdfDownloadConfig, PdfDownloader
from boardgamerules.fetcher.rulebook_fetcher import InternetRulebookFetcher, RulebookFetcherConfig
from boardgamerules.fetcher.search_provider import GeminiRulebookUrlFinder, RulebookUrlFinder
from boardgamerules.fetcher.url_safety import validate_safe_public_url

__all__ = [
    "DownloadedPdf",
    "FetcherSettings",
    "GeminiRulebookUrlFinder",
    "InternetRulebookFetcher",
    "PdfDownloadConfig",
    "PdfDownloader",
    "RulebookFetcherConfig",
    "RulebookUrlFinder",
    "validate_safe_public_url",
]
