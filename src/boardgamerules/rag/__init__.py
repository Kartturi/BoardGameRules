"""RAG Engine & Vector Store module for board game rulebook ingestion and retrieval."""

from boardgamerules.rag.chunker import ChunkingConfig, chunk_rulebook_pages
from boardgamerules.rag.config import (
    RagSettings,
    create_embedding_provider_from_settings,
    create_qdrant_client_from_settings,
)
from boardgamerules.rag.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
)
from boardgamerules.rag.pdf_extractor import (
    PdfPageText,
    PdfTextExtractor,
    PyMuPdfTextExtractor,
)
from boardgamerules.rag.qa import RulebookQuestion, answer_rulebook_question
from boardgamerules.rag.qdrant_engine import QdrantRagEngine

__all__ = [
    "ChunkingConfig",
    "DeterministicEmbeddingProvider",
    "EmbeddingProvider",
    "GeminiEmbeddingProvider",
    "PdfPageText",
    "PdfTextExtractor",
    "PyMuPdfTextExtractor",
    "QdrantRagEngine",
    "RagSettings",
    "RulebookQuestion",
    "answer_rulebook_question",
    "chunk_rulebook_pages",
    "create_embedding_provider_from_settings",
    "create_qdrant_client_from_settings",
]
