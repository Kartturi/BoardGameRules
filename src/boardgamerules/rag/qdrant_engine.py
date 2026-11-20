"""Qdrant vector store adapter implementing the RagEngine contract."""

from __future__ import annotations

import logging
import uuid
import warnings
from collections.abc import Sequence
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from boardgamerules.domain.contracts import RagEngine
from boardgamerules.domain.exceptions import (
    DomainValidationError,
    RagIngestionError,
    StorageOperationError,
)
from boardgamerules.domain.rag import RuleChunk
from boardgamerules.domain.validators import require_canonical_game_id, require_non_blank
from boardgamerules.rag.embeddings import EmbeddingProvider

_QDRANT_POINT_NAMESPACE = uuid.UUID("9f8d5a2b-3c4e-4f1a-8b9c-0d1e2f3a4b5c")
_DEFAULT_COLLECTION_NAME = "rule_chunks"
_DEFAULT_VECTOR_SIZE = 768
logger = logging.getLogger(__name__)


# CONCEPT: [System Design] Embedded In-Memory Database Engine vs. Hand-Rolled Fake
# Unlike MongoDB (which requires a separate server process and therefore needed a hand-rolled
# InMemoryNoSqlRepository fake for unit tests), Qdrant's client ships with a built-in embedded
# engine via AsyncQdrantClient(location=":memory:"). Passing ":memory:" in tests exercises the
# exact same QdrantRagEngine filter AST, UUID mapping, and payload serialization code that runs
# in production against Qdrant Cloud/Docker, without maintaining a second vector engine.
#
# CONCEPT: [AI Engineering] Metadata-Filtered Vector Retrieval (Multi-Game Isolation)
# All board games share one Qdrant vector collection partitioned by a keyword index on game_id.
# Every semantic search and deletion applies a strict Filter(must=[FieldCondition(key="game_id")])
# so chunks from one board game never bleed into another game's rule answers.
class QdrantRagEngine(RagEngine):
    def __init__(
        self,
        client: AsyncQdrantClient,
        embedder: EmbeddingProvider,
        *,
        collection_name: str = _DEFAULT_COLLECTION_NAME,
        vector_size: int = _DEFAULT_VECTOR_SIZE,
    ) -> None:
        require_non_blank(collection_name, "collection_name")
        if vector_size < 2:
            raise DomainValidationError("vector_size must be >= 2.")
        self._client = client
        self._embedder = embedder
        self._collection_name = collection_name
        self._vector_size = vector_size

    async def ensure_collection(self) -> None:
        try:
            exists = await self._client.collection_exists(self._collection_name)
            if not exists:
                logger.info(
                    "Creating Qdrant collection",
                    extra={
                        "collection_name": self._collection_name,
                        "vector_size": self._vector_size,
                    },
                )
                await self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(
                        size=self._vector_size,
                        distance=Distance.COSINE,
                    ),
                )
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="Payload indexes have no effect in the local Qdrant.*",
                        category=UserWarning,
                    )
                    await self._client.create_payload_index(
                        collection_name=self._collection_name,
                        field_name="game_id",
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
        except Exception as exc:
            raise RagIngestionError(
                f"Failed to initialize Qdrant collection '{self._collection_name}': {exc}"
            ) from exc

    async def index_chunks(self, chunks: Sequence[RuleChunk]) -> None:
        if not chunks:
            return
        try:
            await self.ensure_collection()
            vectors = await self._embedder.embed_documents([chunk.text for chunk in chunks])
            points = [
                PointStruct(
                    id=_deterministic_point_id(chunk.game_id, chunk.chunk_id),
                    vector=list(vector),
                    payload=_chunk_to_payload(chunk),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            await self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
            logger.debug(
                "Upserted rulebook chunks into Qdrant",
                extra={
                    "collection_name": self._collection_name,
                    "chunk_count": len(points),
                },
            )
        except Exception as exc:
            raise RagIngestionError(f"Qdrant indexing failed: {exc}") from exc

    async def search_chunks(
        self,
        game_id: str,
        query: str,
        top_k: int = 5,
    ) -> tuple[RuleChunk, ...]:
        require_canonical_game_id(game_id)
        require_non_blank(query, "query")
        if isinstance(top_k, bool) or top_k < 1:
            raise DomainValidationError("top_k must be an integer >= 1.")

        try:
            if not await self._client.collection_exists(self._collection_name):
                return ()
            query_vector = await self._embedder.embed_query(query)
            response = await self._client.query_points(
                collection_name=self._collection_name,
                query=list(query_vector),
                query_filter=_game_id_filter(game_id),
                limit=top_k,
                with_payload=True,
            )
            return tuple(
                _chunk_from_payload(point.payload)
                for point in response.points
                if point.payload is not None
            )
        except Exception as exc:
            raise StorageOperationError(
                f"Qdrant search failed for game_id '{game_id}': {exc}"
            ) from exc

    async def delete_game_chunks(self, game_id: str) -> None:
        require_canonical_game_id(game_id)
        try:
            if not await self._client.collection_exists(self._collection_name):
                return
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=FilterSelector(filter=_game_id_filter(game_id)),
                wait=True,
            )
        except Exception as exc:
            raise StorageOperationError(
                f"Qdrant delete failed for game_id '{game_id}': {exc}"
            ) from exc


# CONCEPT: [System Design] Deterministic UUIDv5 Point IDs for Idempotent Vector Upserts
# Qdrant requires point IDs to be UUIDs or unsigned 64-bit integers. Hashing "{game_id}:{chunk_id}"
# with UUIDv5 produces a deterministic UUID so re-indexing a manual overwrites existing points
# in place instead of creating duplicate chunks.
def _deterministic_point_id(game_id: str, chunk_id: str) -> str:
    return str(uuid.uuid5(_QDRANT_POINT_NAMESPACE, f"{game_id}:{chunk_id}"))


def _game_id_filter(game_id: str) -> Filter:
    return Filter(
        must=[
            FieldCondition(
                key="game_id",
                match=MatchValue(value=game_id),
            )
        ]
    )


def _chunk_to_payload(chunk: RuleChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "game_id": chunk.game_id,
        "text": chunk.text,
        "page_number": chunk.page_number,
        "section_title": chunk.section_title,
    }


def _chunk_from_payload(payload: dict[str, Any]) -> RuleChunk:
    return RuleChunk(
        chunk_id=str(payload["chunk_id"]),
        game_id=str(payload["game_id"]),
        text=str(payload["text"]),
        page_number=payload.get("page_number"),
        section_title=payload.get("section_title"),
    )
