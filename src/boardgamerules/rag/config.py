"""Environment-driven configuration and client factories for RAG and persistence."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from qdrant_client import AsyncQdrantClient

from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import require_non_blank
from boardgamerules.rag.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_IN_MEMORY_QDRANT_URL = ":memory:"
_DEFAULT_DOTENV_PATH = _PROJECT_ROOT / ".env"


# CONCEPT: [System Design] Twelve-Factor Externalized Configuration & Fail-Fast Startup
# Rather than hardcoding server URLs, model names, or collection names inside config code,
# all settings are read strictly from environment variables (.env locally, OS env in
# production) and validated at startup so missing configuration fails fast.
@dataclass(frozen=True)
class RagSettings:
    qdrant_url: str
    qdrant_collection_name: str
    qdrant_vector_size: int
    gemini_embedding_model: str
    gemini_api_key: str | None = field(default=None, repr=False)
    qdrant_api_key: str | None = field(default=None, repr=False)
    mongodb_uri: str | None = field(default=None, repr=False)
    mongodb_database: str | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.qdrant_url, "qdrant_url")
        require_non_blank(self.qdrant_collection_name, "qdrant_collection_name")
        require_non_blank(self.gemini_embedding_model, "gemini_embedding_model")
        if isinstance(self.qdrant_vector_size, bool) or self.qdrant_vector_size < 2:
            raise DomainValidationError("qdrant_vector_size must be an integer >= 2.")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path = _DEFAULT_DOTENV_PATH,
    ) -> RagSettings:
        env = _load_env_vars(environ, dotenv_path)
        return cls(
            qdrant_url=_read_required(env, "QDRANT_URL"),
            qdrant_collection_name=_read_required(env, "QDRANT_COLLECTION_NAME"),
            qdrant_vector_size=_parse_vector_size(env),
            gemini_embedding_model=_read_required(env, "GEMINI_EMBEDDING_MODEL"),
            gemini_api_key=_read_optional(env, "GEMINI_API_KEY"),
            qdrant_api_key=_read_optional(env, "QDRANT_API_KEY"),
            mongodb_uri=_read_optional(env, "MONGODB_URI"),
            mongodb_database=_read_optional(env, "MONGODB_DATABASE"),
        )


def create_qdrant_client_from_settings(settings: RagSettings) -> AsyncQdrantClient:
    if settings.qdrant_url == _IN_MEMORY_QDRANT_URL:
        return AsyncQdrantClient(location=_IN_MEMORY_QDRANT_URL)
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        check_compatibility=False,
    )


def create_embedding_provider_from_settings(settings: RagSettings) -> EmbeddingProvider:
    if settings.gemini_api_key:
        genai_client = genai.Client(api_key=settings.gemini_api_key)
        return GeminiEmbeddingProvider(
            client=genai_client,
            model=settings.gemini_embedding_model,
            output_dimensionality=settings.qdrant_vector_size,
        )
    return DeterministicEmbeddingProvider(vector_size=settings.qdrant_vector_size)


def _load_env_vars(
    environ: Mapping[str, str] | None,
    dotenv_path: Path,
) -> dict[str, str]:
    runtime_env = dict(os.environ) if environ is None else dict(environ)
    if environ is not None and dotenv_path == _DEFAULT_DOTENV_PATH:
        return runtime_env
    return {**_parse_dotenv_file(dotenv_path), **runtime_env}


def _read_required(env: Mapping[str, str], key: str) -> str:
    value = _read_optional(env, key)
    if value is None:
        raise DomainValidationError(f"{key} environment variable is required.")
    return value


def _read_optional(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def _parse_vector_size(env: Mapping[str, str]) -> int:
    raw_vector_size = _read_required(env, "QDRANT_VECTOR_SIZE")
    try:
        return int(raw_vector_size)
    except ValueError as exc:
        raise DomainValidationError(
            f"QDRANT_VECTOR_SIZE must be a valid integer, got '{raw_vector_size}'."
        ) from exc


def _parse_dotenv_file(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_val = line.partition("=")
        cleaned_val = raw_val.strip().strip('"').strip("'")
        parsed[key.strip()] = cleaned_val
    return parsed
