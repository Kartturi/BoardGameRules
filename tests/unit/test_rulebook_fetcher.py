"""Unit tests for the internet rulebook fetcher, Gemini URL finder, and PDF downloader."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from types import SimpleNamespace

import httpx
import pymupdf
import pytest

from boardgamerules.domain.exceptions import (
    DomainValidationError,
    ExternalRuleFetchError,
    RulebookNotFoundError,
)
from boardgamerules.fetcher.config import FetcherSettings
from boardgamerules.fetcher.pdf_downloader import PdfDownloadConfig, PdfDownloader
from boardgamerules.fetcher.rulebook_fetcher import InternetRulebookFetcher, RulebookFetcherConfig
from boardgamerules.fetcher.search_provider import GeminiRulebookUrlFinder, RulebookUrlFinder
from boardgamerules.rag.pdf_extractor import PyMuPdfTextExtractor

_PUBLIC_IP = (ipaddress.ip_address("93.184.216.34"),)
_LOOPBACK_IP = (ipaddress.ip_address("127.0.0.1"),)


def _create_valid_pdf_bytes(text: str = "Setup: Place the hex tiles and deal resources.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


async def _resolve_public(_host: str, _port: int):
    return _PUBLIC_IP


class _StubUrlFinder(RulebookUrlFinder):
    def __init__(self, urls: tuple[str, ...] = (), error: Exception | None = None) -> None:
        self._urls = urls
        self._error = error

    async def find_pdf_urls(self, game_title: str) -> tuple[str, ...]:
        if self._error is not None:
            raise self._error
        return self._urls


def test_should_load_and_validate_fetcher_settings_from_env(tmp_path: Path) -> None:
    # Arrange
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        'GEMINI_API_KEY="secret-key"\nGEMINI_SEARCH_MODEL="gemini-2.5-flash"\n',
        encoding="utf-8",
    )

    # Act
    settings = FetcherSettings.from_env(environ={}, dotenv_path=dotenv_file)

    # Assert
    assert settings.gemini_search_model == "gemini-2.5-flash"
    assert "secret-key" not in repr(settings)

    with pytest.raises(DomainValidationError):
        FetcherSettings(http_timeout_seconds=0.0)


@pytest.mark.anyio
async def test_should_prioritize_verified_grounding_urls_in_gemini_url_finder() -> None:
    # Arrange
    grounding_chunk = SimpleNamespace(
        web=SimpleNamespace(
            uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123",
            title="Catan Official Rulebook PDF",
        )
    )
    fake_response = SimpleNamespace(
        text="Official PDF: https://publisher.example/catan-rules.pdf",
        candidates=[
            SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[grounding_chunk]))
        ],
    )

    async def _fake_generate_content(**_kwargs):
        return fake_response

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=_fake_generate_content))
    )
    finder = GeminiRulebookUrlFinder(client=fake_client, model="gemini-2.5-flash")

    # Act
    urls = await finder.find_pdf_urls("Catan")

    # Assert
    assert urls == (
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123",
        "https://publisher.example/catan-rules.pdf",
    )


@pytest.mark.anyio
async def test_should_follow_redirect_validate_pdf_and_return_fetched_rulebook() -> None:
    # Arrange
    valid_pdf = _create_valid_pdf_bytes()

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "vertexaisearch.cloud.google.com":
            return httpx.Response(
                302,
                headers={"Location": "https://www.catan.com/rules/catan_base.pdf"},
            )
        if str(request.url) == "https://www.catan.com/rules/catan_base.pdf":
            assert "authorization" not in {k.lower() for k in request.headers}
            return httpx.Response(
                200,
                content=valid_pdf,
                headers={"Content-Type": "application/pdf"},
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http_client:
        fetcher = InternetRulebookFetcher(
            url_finder=_StubUrlFinder(
                urls=("https://vertexaisearch.cloud.google.com/grounding-api-redirect/catan",)
            ),
            downloader=PdfDownloader(http_client=http_client, resolve_host=_resolve_public),
            pdf_extractor=PyMuPdfTextExtractor(),
        )

        # Act
        fetched = await fetcher.fetch_rulebook("Catan")

    # Assert
    assert fetched.game_title == "Catan"
    assert fetched.bgg_id is None
    assert fetched.source_url == "https://www.catan.com/rules/catan_base.pdf"
    assert fetched.pdf_bytes == valid_pdf
    assert len(fetched.content_sha256) == 64


@pytest.mark.anyio
async def test_should_skip_invalid_candidates_and_return_next_valid_pdf() -> None:
    # Arrange
    valid_pdf = _create_valid_pdf_bytes()

    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/missing.pdf"):
            return httpx.Response(404)
        if url.endswith("/html_page.pdf"):
            return httpx.Response(200, text="<html>Not a PDF</html>")
        if url.endswith("/corrupt.pdf"):
            return httpx.Response(200, content=b"%PDF-1.4 corrupted garbage")
        if url.endswith("/good.pdf"):
            return httpx.Response(200, content=valid_pdf)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http_client:
        fetcher = InternetRulebookFetcher(
            url_finder=_StubUrlFinder(
                urls=(
                    "https://publisher.example/missing.pdf",
                    "https://publisher.example/html_page.pdf",
                    "https://publisher.example/corrupt.pdf",
                    "https://publisher.example/good.pdf",
                )
            ),
            downloader=PdfDownloader(http_client=http_client, resolve_host=_resolve_public),
            pdf_extractor=PyMuPdfTextExtractor(),
        )

        # Act
        fetched = await fetcher.fetch_rulebook("Scythe")

    # Assert
    assert fetched.source_url == "https://publisher.example/good.pdf"
    assert fetched.game_title == "Scythe"
    assert fetched.bgg_id is None


@pytest.mark.anyio
async def test_should_block_ssrf_redirect_and_oversized_pdf_downloads() -> None:
    # Arrange
    async def _mixed_resolver(host: str, _port: int):
        return _LOOPBACK_IP if host == "internal.local" else _PUBLIC_IP

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ssrf":
            return httpx.Response(302, headers={"Location": "https://internal.local/secret.pdf"})
        if request.url.path == "/huge.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 " + b"A" * 2048)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http_client:
        downloader = PdfDownloader(
            http_client=http_client,
            config=PdfDownloadConfig(max_pdf_bytes=512),
            resolve_host=_mixed_resolver,
        )

        # Act / Assert
        with pytest.raises(ExternalRuleFetchError):
            await downloader.download_pdf("https://public.example/ssrf")
        with pytest.raises(ExternalRuleFetchError):
            await downloader.download_pdf("https://public.example/huge.pdf")


@pytest.mark.anyio
async def test_should_raise_rulebook_not_found_or_propagate_external_search_errors() -> None:
    # Arrange
    transport = httpx.MockTransport(lambda _req: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as http_client:
        downloader = PdfDownloader(http_client=http_client, resolve_host=_resolve_public)
        empty_fetcher = InternetRulebookFetcher(
            url_finder=_StubUrlFinder(urls=()),
            downloader=downloader,
            pdf_extractor=PyMuPdfTextExtractor(),
            config=RulebookFetcherConfig(max_candidates=3),
        )
        broken_fetcher = InternetRulebookFetcher(
            url_finder=_StubUrlFinder(error=ExternalRuleFetchError("Gemini quota exhausted")),
            downloader=downloader,
            pdf_extractor=PyMuPdfTextExtractor(),
        )

        # Act / Assert
        with pytest.raises(DomainValidationError):
            await empty_fetcher.fetch_rulebook("   ")
        with pytest.raises(RulebookNotFoundError):
            await empty_fetcher.fetch_rulebook("Unknown Board Game")
        with pytest.raises(ExternalRuleFetchError, match="Gemini quota exhausted"):
            await broken_fetcher.fetch_rulebook("Catan")
