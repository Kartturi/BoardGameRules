"""Unit tests for the LocalPdfStorage adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardgamerules.batch import LocalPdfStorage
from boardgamerules.domain import DomainValidationError, PdfStorage, StorageOperationError


@pytest.mark.anyio
async def test_should_list_read_and_move_pdfs_to_processed_and_failed_in_local_storage(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = LocalPdfStorage(base_dir=tmp_path)
    incoming_dir = tmp_path / "incoming"
    (incoming_dir / "catan_rules.pdf").write_bytes(b"%PDF-1.7 catan")
    (incoming_dir / "WINGSPAN.PDF").write_bytes(b"%PDF-1.7 wingspan")
    (incoming_dir / "notes.txt").write_text("ignore non-pdf", encoding="utf-8")

    # Act
    keys = await storage.list_unprocessed_keys()
    catan_bytes = await storage.read_pdf_bytes("incoming/catan_rules.pdf")
    await storage.move_to_processed("incoming/catan_rules.pdf")
    await storage.move_to_failed("incoming/WINGSPAN.PDF")
    remaining_keys = await storage.list_unprocessed_keys()

    # Assert
    assert isinstance(storage, PdfStorage)
    assert keys == ("incoming/WINGSPAN.PDF", "incoming/catan_rules.pdf")
    assert catan_bytes == b"%PDF-1.7 catan"
    assert remaining_keys == ()
    assert (tmp_path / "processed" / "catan_rules.pdf").read_bytes() == b"%PDF-1.7 catan"
    assert (tmp_path / "failed" / "WINGSPAN.PDF").read_bytes() == b"%PDF-1.7 wingspan"


@pytest.mark.anyio
async def test_should_ignore_symlinks_and_reject_unsafe_or_missing_keys_in_local_storage(
    tmp_path: Path,
) -> None:
    # Arrange
    storage = LocalPdfStorage(base_dir=tmp_path)
    outside_file = tmp_path.parent / "secret.pdf"
    outside_file.write_bytes(b"%PDF-1.7 secret")
    symlink_path = tmp_path / "incoming" / "linked.pdf"
    symlink_path.symlink_to(outside_file)

    # Act
    keys = await storage.list_unprocessed_keys()

    # Assert: symlinks in incoming/ are ignored during scan and rejected on read
    assert keys == ()
    with pytest.raises(StorageOperationError, match="symlink"):
        await storage.read_pdf_bytes("incoming/linked.pdf")

    with pytest.raises(DomainValidationError):
        await storage.read_pdf_bytes("../secret.pdf")

    with pytest.raises(StorageOperationError, match="does not exist"):
        await storage.read_pdf_bytes("incoming/nonexistent.pdf")
