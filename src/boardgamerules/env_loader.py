"""Shared environment variable and .env file loading utilities."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from boardgamerules.domain.exceptions import DomainValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"


def load_env_vars(
    environ: Mapping[str, str] | None,
    dotenv_path: Path = DEFAULT_DOTENV_PATH,
) -> dict[str, str]:
    runtime_env = dict(os.environ) if environ is None else dict(environ)
    if environ is not None and dotenv_path == DEFAULT_DOTENV_PATH:
        return runtime_env
    return {**_parse_dotenv_file(dotenv_path), **runtime_env}


def read_required_env(env: Mapping[str, str], key: str) -> str:
    value = read_optional_env(env, key)
    if value is None:
        raise DomainValidationError(f"{key} environment variable is required.")
    return value


def read_optional_env(env: Mapping[str, str], key: str) -> str | None:
    raw = env.get(key)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def _parse_dotenv_file(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        parsed[key.strip()] = _unwrap_matching_quotes(raw_value.strip())
    return parsed


def _unwrap_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value
