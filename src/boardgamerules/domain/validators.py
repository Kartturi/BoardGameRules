"""Domain invariant validators, canonical slug normalization, and content hashing."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from boardgamerules.domain.exceptions import DomainValidationError

_SLUG_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_non_blank(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise DomainValidationError(f"{field_name} cannot be empty or blank.")


def require_utc_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise DomainValidationError(f"{field_name} must be a timezone-aware datetime.")


def require_canonical_game_id(game_id: str) -> None:
    require_non_blank(game_id, "game_id")
    if game_id != normalize_game_id(game_id):
        raise DomainValidationError(
            f"game_id '{game_id}' must be in canonical normalized slug format."
        )


def validate_sha256_hex(digest: str) -> None:
    if not _SHA256_HEX_PATTERN.match(digest):
        raise DomainValidationError(
            "content_sha256 must be a 64-character lowercase hexadecimal SHA-256 digest."
        )


# CONCEPT: [System Design] Content-Addressable Deduplication (SHA-256)
# Hashing raw PDF bytes with SHA-256 produces a deterministic 64-char fingerprint. Checking
# this hash before chunking or embedding guarantees the same rulebook PDF is never ingested
# twice, even when uploaded under different filenames or fetched from mirror URLs.
def compute_pdf_sha256(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        raise DomainValidationError("pdf_bytes cannot be empty.")
    return hashlib.sha256(pdf_bytes).hexdigest()


# CONCEPT: [System Design] Path Traversal Defense-in-Depth
# Validating storage keys inside the domain model prevents malicious inputs like
# "../../etc/passwd", null bytes, or absolute paths from reaching filesystem or blob adapters.
def validate_safe_file_key(file_key: str) -> None:
    require_non_blank(file_key, "file_key")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in file_key):
        raise DomainValidationError("file_key cannot contain control characters or null bytes.")
    if ":" in file_key or file_key.startswith(("/", "\\")) or "\\" in file_key:
        raise DomainValidationError("file_key must be a relative forward-slash path.")
    segments = file_key.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise DomainValidationError("file_key cannot contain empty, '.', or '..' path segments.")


# CONCEPT: [System Design] Canonical Identifier Normalization
# Because both MongoDB (document metadata) and Qdrant (vector chunk filters) partition data
# by game_id, normalizing arbitrary user input ("Settlers of Catan!") into a deterministic
# slug ("settlers-of-catan") prevents duplicate silos and cache misses across databases.
def normalize_game_id(game_title: str) -> str:
    require_non_blank(game_title, "game_title")
    slug = _SLUG_NON_ALNUM_PATTERN.sub("-", game_title.lower()).strip("-")
    if not slug:
        raise DomainValidationError(
            f"game_title '{game_title}' must contain at least one alphanumeric character."
        )
    return slug
