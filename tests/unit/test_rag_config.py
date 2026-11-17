"""Unit tests for environment-driven RAG settings and Qdrant client factory."""

from __future__ import annotations

from pathlib import Path

import pytest

from boardgamerules.domain import DomainValidationError
from boardgamerules.rag import RagSettings, create_qdrant_client_from_settings

_VALID_ENV = {
    "QDRANT_URL": ":memory:",
    "QDRANT_COLLECTION_NAME": "rulebook_chunks",
    "QDRANT_VECTOR_SIZE": "768",
    "GEMINI_EMBEDDING_MODEL": "text-embedding-004",
}


def test_should_load_rag_settings_from_dotenv_file(tmp_path: Path) -> None:
    # Arrange
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        'QDRANT_URL="http://localhost:6333"\n'
        'QDRANT_COLLECTION_NAME="dev_chunks"\n'
        'QDRANT_VECTOR_SIZE="768"\n'
        'GEMINI_EMBEDDING_MODEL="text-embedding-004"\n',
        encoding="utf-8",
    )

    # Act
    settings = RagSettings.from_env({}, dotenv_path=dotenv_file)

    # Assert
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.qdrant_collection_name == "dev_chunks"
    assert settings.qdrant_vector_size == 768
    assert settings.gemini_embedding_model == "text-embedding-004"


def test_should_override_dotenv_values_with_os_environment_variables(tmp_path: Path) -> None:
    # Arrange
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        'QDRANT_URL="http://localhost:6333"\n'
        'QDRANT_COLLECTION_NAME="dev_chunks"\n'
        'QDRANT_VECTOR_SIZE="768"\n'
        'GEMINI_EMBEDDING_MODEL="text-embedding-004"\n',
        encoding="utf-8",
    )

    # Act
    settings = RagSettings.from_env(
        {
            "QDRANT_URL": "https://cluster.qdrant.io:6333",
            "QDRANT_API_KEY": "prod-qdrant-key",
            "GEMINI_API_KEY": "prod-gemini-key",
        },
        dotenv_path=dotenv_file,
    )

    # Assert
    assert settings.qdrant_url == "https://cluster.qdrant.io:6333"
    assert settings.qdrant_api_key == "prod-qdrant-key"
    assert settings.gemini_api_key == "prod-gemini-key"


@pytest.mark.parametrize(
    "missing_key",
    [
        "QDRANT_URL",
        "QDRANT_COLLECTION_NAME",
        "QDRANT_VECTOR_SIZE",
        "GEMINI_EMBEDDING_MODEL",
    ],
)
def test_should_fail_fast_when_any_required_env_var_is_missing(missing_key: str) -> None:
    # Arrange
    incomplete_env = {k: v for k, v in _VALID_ENV.items() if k != missing_key}

    # Act / Assert
    with pytest.raises(
        DomainValidationError, match=f"{missing_key} environment variable is required"
    ):
        RagSettings.from_env(incomplete_env)


def test_should_raise_validation_error_when_rag_settings_values_are_invalid() -> None:
    # Act / Assert
    with pytest.raises(DomainValidationError, match="QDRANT_VECTOR_SIZE"):
        RagSettings.from_env({**_VALID_ENV, "QDRANT_VECTOR_SIZE": "not-a-number"})

    with pytest.raises(DomainValidationError, match="qdrant_vector_size"):
        RagSettings(
            qdrant_url=":memory:",
            qdrant_collection_name="rulebook_chunks",
            qdrant_vector_size=1,
            gemini_embedding_model="text-embedding-004",
        )


@pytest.mark.anyio
async def test_should_create_in_memory_qdrant_client_when_qdrant_url_is_memory() -> None:
    # Arrange
    settings = RagSettings.from_env(_VALID_ENV)

    # Act
    client = create_qdrant_client_from_settings(settings)

    # Assert
    assert await client.collection_exists(settings.qdrant_collection_name) is False
    await client.close()
