"""Configuration settings for Gemini AI rule generation and recap synthesis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from boardgamerules.domain.exceptions import DomainValidationError
from boardgamerules.domain.validators import require_non_blank
from boardgamerules.env_loader import DEFAULT_DOTENV_PATH, load_env_vars, read_optional_env

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_MAX_OUTPUT_TOKENS = 4096
_DEFAULT_MAX_CONTEXT_CHARS = 40_000
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_BASE_RETRY_SECONDS = 2.0
_DEFAULT_MAX_RETRY_WAIT_SECONDS = 10.0


@dataclass(frozen=True)
class AiSettings:
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str = _DEFAULT_GEMINI_MODEL
    use_vertexai: bool = False
    temperature: float = _DEFAULT_TEMPERATURE
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS
    max_context_chars: int = _DEFAULT_MAX_CONTEXT_CHARS
    max_retries: int = _DEFAULT_MAX_RETRIES
    base_retry_seconds: float = _DEFAULT_BASE_RETRY_SECONDS
    max_retry_wait_seconds: float = _DEFAULT_MAX_RETRY_WAIT_SECONDS

    def __post_init__(self) -> None:
        require_non_blank(self.gemini_model, "gemini_model")
        if (
            isinstance(self.temperature, bool)
            or not math.isfinite(self.temperature)
            or not (0.0 <= self.temperature <= 2.0)
        ):
            raise DomainValidationError("temperature must be a finite float between 0.0 and 2.0.")
        if isinstance(self.max_output_tokens, bool) or self.max_output_tokens < 256:
            raise DomainValidationError("max_output_tokens must be an integer >= 256.")
        if isinstance(self.max_context_chars, bool) or self.max_context_chars < 500:
            raise DomainValidationError("max_context_chars must be an integer >= 500.")
        if isinstance(self.max_retries, bool) or self.max_retries < 0:
            raise DomainValidationError("max_retries cannot be negative.")
        if (
            isinstance(self.base_retry_seconds, bool)
            or not math.isfinite(self.base_retry_seconds)
            or self.base_retry_seconds < 0.0
        ):
            raise DomainValidationError("base_retry_seconds cannot be negative.")
        if (
            isinstance(self.max_retry_wait_seconds, bool)
            or not math.isfinite(self.max_retry_wait_seconds)
            or self.max_retry_wait_seconds < 0.0
        ):
            raise DomainValidationError("max_retry_wait_seconds cannot be negative.")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path = DEFAULT_DOTENV_PATH,
    ) -> AiSettings:
        env = load_env_vars(environ, dotenv_path)
        raw_vertexai = (read_optional_env(env, "GOOGLE_GENAI_USE_VERTEXAI") or "").strip().lower()
        use_vertexai = raw_vertexai in {"true", "1", "yes"}
        return cls(
            gemini_api_key=read_optional_env(env, "GEMINI_API_KEY"),
            gemini_model=read_optional_env(env, "GEMINI_MODEL") or _DEFAULT_GEMINI_MODEL,
            use_vertexai=use_vertexai,
        )
