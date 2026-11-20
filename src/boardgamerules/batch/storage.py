"""Local directory PdfStorage adapter managing incoming, processed, and failed rulebooks."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from boardgamerules.domain.contracts import PdfStorage
from boardgamerules.domain.exceptions import StorageOperationError
from boardgamerules.domain.validators import validate_safe_file_key

_INCOMING_DIR_NAME = "incoming"
_PROCESSED_DIR_NAME = "processed"
_FAILED_DIR_NAME = "failed"
logger = logging.getLogger(__name__)


# CONCEPT: [System Design] Moving Files by Status (incoming/ -> processed/ or failed/)
# Moving each PDF out of incoming/ as soon as it finishes ensures the batch job never
# processes the same file twice if it restarts, and keeps broken PDFs separated in failed/
# instead of retrying them forever.
class LocalPdfStorage(PdfStorage):
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir.resolve()
        self._incoming_dir = self._base_dir / _INCOMING_DIR_NAME
        self._processed_dir = self._base_dir / _PROCESSED_DIR_NAME
        self._failed_dir = self._base_dir / _FAILED_DIR_NAME
        self._create_folders()

    async def list_unprocessed_keys(self) -> tuple[str, ...]:
        return await asyncio.to_thread(self._list_incoming_pdf_keys)

    async def read_pdf_bytes(self, file_key: str) -> bytes:
        source_path = self._resolve_safe_path(file_key)
        return await asyncio.to_thread(self._read_file, source_path, file_key)

    async def move_to_processed(self, file_key: str) -> None:
        await self._move_to_folder(file_key, self._processed_dir)

    async def move_to_failed(self, file_key: str) -> None:
        await self._move_to_folder(file_key, self._failed_dir)

    async def _move_to_folder(self, file_key: str, target_dir: Path) -> None:
        source_path = self._resolve_safe_path(file_key)
        destination = target_dir / source_path.name
        await asyncio.to_thread(self._move_file, source_path, destination)
        logger.debug(
            "Moved PDF file",
            extra={"file_key": file_key, "destination_folder": target_dir.name},
        )

    def _create_folders(self) -> None:
        try:
            self._incoming_dir.mkdir(parents=True, exist_ok=True)
            self._processed_dir.mkdir(parents=True, exist_ok=True)
            self._failed_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageOperationError(
                f"Failed to initialize PDF storage directories at '{self._base_dir}': {exc}"
            ) from exc

    def _list_incoming_pdf_keys(self) -> tuple[str, ...]:
        try:
            keys = [
                f"{_INCOMING_DIR_NAME}/{entry.name}"
                for entry in self._incoming_dir.iterdir()
                if _is_pdf_file(entry)
            ]
            keys.sort()
            return tuple(keys)
        except OSError as exc:
            raise StorageOperationError(
                f"Failed to scan incoming PDF directory '{self._incoming_dir}': {exc}"
            ) from exc

    def _resolve_safe_path(self, file_key: str) -> Path:
        validate_safe_file_key(file_key)
        candidate = self._base_dir / file_key
        if candidate.is_symlink():
            raise StorageOperationError(f"Refusing to access symlink PDF key '{file_key}'.")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._base_dir):
            raise StorageOperationError(
                f"Resolved path for '{file_key}' escapes storage root '{self._base_dir}'."
            )
        return resolved

    def _read_file(self, source_path: Path, file_key: str) -> bytes:
        if not source_path.is_file():
            raise StorageOperationError(f"PDF file '{file_key}' does not exist.")
        try:
            return source_path.read_bytes()
        except OSError as exc:
            raise StorageOperationError(f"Failed to read PDF '{file_key}': {exc}") from exc

    def _move_file(self, source_path: Path, destination: Path) -> None:
        if not source_path.is_file():
            raise StorageOperationError(f"Cannot move missing PDF file '{source_path.name}'.")
        try:
            source_path.replace(destination)
        except OSError as exc:
            raise StorageOperationError(
                f"Failed to move PDF '{source_path.name}' to '{destination}': {exc}"
            ) from exc


def _is_pdf_file(entry: Path) -> bool:
    return not entry.is_symlink() and entry.is_file() and entry.suffix.lower() == ".pdf"
