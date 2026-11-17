"""Unit tests for PDF text extraction and resource exhaustion guards."""

from __future__ import annotations

import pymupdf
import pytest

from boardgamerules.domain import DomainValidationError, RagIngestionError
from boardgamerules.rag import PdfPageText, PdfTextExtractor, PyMuPdfTextExtractor


def _build_pdf_bytes(page_texts: list[str]) -> bytes:
    with pymupdf.open() as doc:
        for text in page_texts:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        return doc.tobytes()


def test_should_extract_non_blank_pages_with_one_based_page_numbers_from_pdf_bytes() -> None:
    pdf_bytes = _build_pdf_bytes(["# Setup\nPlace the board.", "   ", "# Turn Order\nRoll dice."])
    extractor = PyMuPdfTextExtractor()

    pages = extractor.extract_pages(pdf_bytes)

    assert isinstance(extractor, PdfTextExtractor)
    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert "Setup" in pages[0].text
    assert pages[1].page_number == 3
    assert "Turn Order" in pages[1].text


@pytest.mark.parametrize("invalid_bytes", [b"", b"not-a-valid-pdf-stream"])
def test_should_raise_rag_ingestion_error_when_pdf_bytes_are_empty_or_corrupted(
    invalid_bytes: bytes,
) -> None:
    extractor = PyMuPdfTextExtractor()

    with pytest.raises(RagIngestionError):
        extractor.extract_pages(invalid_bytes)


def test_should_raise_rag_ingestion_error_when_pdf_exceeds_max_bytes() -> None:
    pdf_bytes = _build_pdf_bytes(["Some valid rule text."])
    extractor = PyMuPdfTextExtractor(max_pdf_bytes=10)

    with pytest.raises(RagIngestionError, match="exceeds maximum allowed size"):
        extractor.extract_pages(pdf_bytes)


def test_should_raise_rag_ingestion_error_when_pdf_exceeds_max_pages() -> None:
    pdf_bytes = _build_pdf_bytes(["Page 1", "Page 2", "Page 3"])
    extractor = PyMuPdfTextExtractor(max_pages=2)

    with pytest.raises(RagIngestionError, match="exceeds maximum allowed page count"):
        extractor.extract_pages(pdf_bytes)


def test_should_raise_rag_ingestion_error_when_pdf_contains_only_blank_pages() -> None:
    pdf_bytes = _build_pdf_bytes(["", "   \n  "])
    extractor = PyMuPdfTextExtractor()

    with pytest.raises(RagIngestionError, match="no extractable text"):
        extractor.extract_pages(pdf_bytes)


def test_should_raise_validation_error_when_pdf_page_text_is_invalid() -> None:
    with pytest.raises(DomainValidationError, match="page_number"):
        PdfPageText(page_number=0, text="Valid text")

    with pytest.raises(DomainValidationError, match="text"):
        PdfPageText(page_number=1, text="   ")
