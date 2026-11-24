"""Environment-driven settings for the internet rulebook fetcher module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import require_non_blank
from boardgamerules.env_loader import DEFAULT_DOTENV_PATH, load_env_vars, read_optional_env

_DEFAULT_GEMINI_SEARCH_MODEL = "gemini-2.5-flash"
_DEFAULT_USER_AGENT = "BoardGameRules/0.1"
_DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class FetcherSettings:
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_search_model: str = _DEFAULT_GEMINI_SEARCH_MODEL
    http_timeout_seconds: float = 15.0
    max_pdf_bytes: int = _DEFAULT_MAX_PDF_BYTES
    max_redirects: int = 5
    max_candidates: int = 5
    user_agent: str = _DEFAULT_USER_AGENT

    def __post_init__(self) -> None:
        require_non_blank(self.gemini_search_model, "gemini_search_model")
        require_non_blank(self.user_agent, "user_agent")
        if self.http_timeout_seconds <= 0.0:
            raise DomainValidationError("http_timeout_seconds must be > 0.")
        if self.max_pdf_bytes < 1:
            raise DomainValidationError("max_pdf_bytes must be >= 1.")
        if self.max_redirects < 0:
            raise DomainValidationError("max_redirects must be >= 0.")
        if self.max_candidates < 1:
            raise DomainValidationError("max_candidates must be >= 1.")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path = DEFAULT_DOTENV_PATH,
    ) -> FetcherSettings:
        env = load_env_vars(environ, dotenv_path)
        return cls(
            gemini_api_key=read_optional_env(env, "GEMINI_API_KEY"),
            gemini_search_model=(
                read_optional_env(env, "GEMINI_SEARCH_MODEL") or _DEFAULT_GEMINI_SEARCH_MODEL
            ),
        )
