"""SSRF-hardened asynchronous PDF downloader with streaming size limits."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from boardgamerules.domain.exceptions import DomainValidationError, ExternalRuleFetchError
from boardgamerules.domain.validators import require_non_blank
from boardgamerules.fetcher.url_safety import HostResolver, validate_safe_public_url

_PDF_MAGIC_HEADER = b"%PDF-"
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024
_STREAM_CHUNK_BYTES = 65536
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfDownloadConfig:
    timeout_seconds: float = 15.0
    max_pdf_bytes: int = _DEFAULT_MAX_PDF_BYTES
    max_redirects: int = 5
    user_agent: str = "BoardGameRules/0.1"

    def __post_init__(self) -> None:
        require_non_blank(self.user_agent, "user_agent")
        if self.timeout_seconds <= 0.0:
            raise DomainValidationError("timeout_seconds must be > 0.")
        if self.max_pdf_bytes < 1:
            raise DomainValidationError("max_pdf_bytes must be >= 1.")
        if self.max_redirects < 0:
            raise DomainValidationError("max_redirects must be >= 0.")


@dataclass(frozen=True)
class DownloadedPdf:
    final_url: str
    pdf_bytes: bytes


class PdfDownloader:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        config: PdfDownloadConfig | None = None,
        resolve_host: HostResolver | None = None,
    ) -> None:
        self._http_client = http_client
        self._config = config or PdfDownloadConfig()
        self._resolve_host = resolve_host

    async def download_pdf(self, url: str) -> DownloadedPdf:
        current_url = await self._validate_url(url)
        headers = {
            "User-Agent": self._config.user_agent,
            "Accept": "application/pdf,*/*;q=0.8",
        }

        # Follow redirects step-by-step to validate each destination securely.
        for _ in range(self._config.max_redirects + 1):
            next_url, pdf_bytes = await self._fetch_single_hop(current_url, headers)
            if pdf_bytes is not None:
                _require_pdf_magic_header(pdf_bytes, current_url)
                logger.debug(
                    "Downloaded candidate PDF rulebook",
                    extra={"byte_count": len(pdf_bytes)},
                )
                return DownloadedPdf(final_url=current_url, pdf_bytes=pdf_bytes)
            if next_url is None:
                raise ExternalRuleFetchError("Redirect response did not provide a target URL.")
            current_url = await self._validate_url(next_url)

        raise ExternalRuleFetchError(
            f"Exceeded maximum redirects ({self._config.max_redirects}) downloading rulebook."
        )

    async def _validate_url(self, url: str) -> str:
        return await validate_safe_public_url(url, resolve_host=self._resolve_host)

    async def _fetch_single_hop(
        self,
        url: str,
        headers: dict[str, str],
    ) -> tuple[str | None, bytes | None]:
        try:
            async with self._http_client.stream(
                "GET",
                url,
                headers=headers,
                follow_redirects=False,
                timeout=self._config.timeout_seconds,
            ) as response:
                if response.status_code in _REDIRECT_STATUS_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise ExternalRuleFetchError("Redirect response missing Location header.")
                    return urljoin(url, location), None

                if response.status_code != 200:
                    raise ExternalRuleFetchError(
                        f"Rulebook download failed with HTTP {response.status_code}."
                    )

                _check_content_length(
                    response.headers.get("content-length"),
                    self._config.max_pdf_bytes,
                )
                return None, await self._read_bounded_bytes(response)
        except httpx.HTTPError as exc:
            raise ExternalRuleFetchError(f"HTTP error downloading rulebook: {exc}") from exc

    async def _read_bounded_bytes(self, response: httpx.Response) -> bytes:
        chunks = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=_STREAM_CHUNK_BYTES):
            chunks.extend(chunk)
            if len(chunks) > self._config.max_pdf_bytes:
                raise ExternalRuleFetchError(
                    f"Downloaded file exceeds maximum allowed size "
                    f"({self._config.max_pdf_bytes} bytes)."
                )
        return bytes(chunks)


def _check_content_length(raw_length: str | None, max_bytes: int) -> None:
    if raw_length is None:
        return
    try:
        declared_size = int(raw_length)
    except ValueError:
        return
    if declared_size > max_bytes:
        raise ExternalRuleFetchError(
            f"Declared Content-Length ({declared_size} bytes) exceeds limit ({max_bytes} bytes)."
        )


def _require_pdf_magic_header(data: bytes, url: str) -> None:
    if not data.startswith(_PDF_MAGIC_HEADER):
        raise ExternalRuleFetchError(f"Downloaded content from '{url}' is not a valid PDF file.")
