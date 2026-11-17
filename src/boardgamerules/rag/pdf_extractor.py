"""Page-preserving PDF text extraction with resource exhaustion guards."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pymupdf

from boardgamerules.domain.exceptions import DomainValidationError, RagIngestionError
from boardgamerules.domain.validators import require_non_blank

_DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024
_DEFAULT_MAX_PAGES = 500


# CONCEPT: [AI Engineering] Page-Preserving PDF Extraction for Grounded Citations
# Extracting text page-by-page with 1-based page numbers ensures every downstream vector
# chunk retains its exact source page number for verifiable user citations.
@dataclass(frozen=True)
class PdfPageText:
    page_number: int
    text: str

    def __post_init__(self) -> None:
        if isinstance(self.page_number, bool) or self.page_number < 1:
            raise DomainValidationError("page_number must be an integer >= 1.")
        require_non_blank(self.text, "text")


class PdfTextExtractor(ABC):
    @abstractmethod
    def extract_pages(self, pdf_bytes: bytes) -> tuple[PdfPageText, ...]: ...


# CONCEPT: [System Design] Resource Exhaustion & PDF Bomb Defense
# Enforcing byte-size and page-count upper bounds before iterating over a PDF stream
# protects stateless containers from out-of-memory crashes caused by malicious or
# abnormally large external rulebook files.
class PyMuPdfTextExtractor(PdfTextExtractor):
    def __init__(
        self,
        max_pdf_bytes: int = _DEFAULT_MAX_PDF_BYTES,
        max_pages: int = _DEFAULT_MAX_PAGES,
    ) -> None:
        if max_pdf_bytes < 1:
            raise DomainValidationError("max_pdf_bytes must be >= 1.")
        if max_pages < 1:
            raise DomainValidationError("max_pages must be >= 1.")
        self._max_pdf_bytes = max_pdf_bytes
        self._max_pages = max_pages

    def extract_pages(self, pdf_bytes: bytes) -> tuple[PdfPageText, ...]:
        self._validate_pdf_size(pdf_bytes)
        with _open_pdf_stream(pdf_bytes) as doc:
            self._validate_page_count(doc.page_count)
            pages = _read_non_blank_pages(doc)

        if not pages:
            raise RagIngestionError("PDF contains no extractable text across any pages.")
        return pages

    def _validate_pdf_size(self, pdf_bytes: bytes) -> None:
        if not pdf_bytes:
            raise RagIngestionError("pdf_bytes cannot be empty.")
        if len(pdf_bytes) > self._max_pdf_bytes:
            raise RagIngestionError(
                f"PDF size ({len(pdf_bytes)} bytes) exceeds maximum allowed size "
                f"({self._max_pdf_bytes} bytes)."
            )

    def _validate_page_count(self, page_count: int) -> None:
        if page_count > self._max_pages:
            raise RagIngestionError(
                f"PDF page count ({page_count}) exceeds maximum allowed "
                f"page count ({self._max_pages})."
            )


def _open_pdf_stream(pdf_bytes: bytes) -> pymupdf.Document:
    try:
        return pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise RagIngestionError(f"Failed to parse PDF byte stream: {exc}") from exc


def _read_non_blank_pages(doc: pymupdf.Document) -> tuple[PdfPageText, ...]:
    extracted: list[PdfPageText] = []
    for page_number, page in enumerate(doc, start=1):
        page_text = page.get_text("text").strip()
        if page_text:
            extracted.append(PdfPageText(page_number=page_number, text=page_text))
    return tuple(extracted)
