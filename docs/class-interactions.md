# System Class Interactions & Architecture

This document visualizes the current architectural structure of **BoardGameRules** following Task 7, explaining how domain entities, abstract ports (ABCs), infrastructure adapters, and application pipelines interact.

---

## 1. Class & Contract Architecture Diagram

The system adheres to **Hexagonal Architecture (Ports and Adapters)**. High-level workflows depend only on abstract domain ports (`contracts.py`), while concrete adapters (`MongoNoSqlRepository`, `QdrantRagEngine`, `InternetRulebookFetcher`, `GeminiAiRuleGenerator`) implement those contracts.

```mermaid
classDiagram
    direction TB

    %% Domain Contracts (Ports / ABCs)
    class RagEngine {
        <<interface / ABC>>
        +index_chunks(chunks)
        +search_chunks(game_id, query, top_k)
        +delete_game_chunks(game_id)
    }

    class AiRuleGenerator {
        <<interface / ABC>>
        +generate_fallback_rules(game_title) GeneratedRulebook
        +generate_quick_recap(game_title, chunks) QuickRecap
        +answer_question(game_title, question, chunks) GeneratedRuleAnswer
    }

    class RulebookFetcher {
        <<interface / ABC>>
        +fetch_rulebook(game_title) FetchedRulebook
    }

    class NoSqlRepository {
        <<interface / Composite ABC>>
        +save_user(user)
        +save_manual(manual)
        +get_active_manual(game_id)
        +save_pending_pdf(pdf)
        +save_history_entry(entry)
    }

    class PdfStorage {
        <<interface / ABC>>
        +list_unprocessed_keys()
        +read_pdf_bytes(key)
        +move_to_processed(key)
        +move_to_failed(key)
    }

    %% Infrastructure Adapters
    class QdrantRagEngine {
        -_client: AsyncQdrantClient
        -_embedder: EmbeddingProvider
        +index_chunks()
        +search_chunks()
    }
    RagEngine <|.. QdrantRagEngine : implements

    class GeminiAiRuleGenerator {
        -_client: genai.Client
        -_settings: AiSettings
        +generate_fallback_rules()
        +generate_quick_recap()
        +answer_question()
    }
    AiRuleGenerator <|.. GeminiAiRuleGenerator : implements

    class InternetRulebookFetcher {
        -_finder: RulebookUrlFinder
        -_downloader: PdfDownloader
        -_extractor: PdfTextExtractor
        +fetch_rulebook()
    }
    RulebookFetcher <|.. InternetRulebookFetcher : implements

    class MongoNoSqlRepository {
        -_db: AsyncIOMotorDatabase
    }
    NoSqlRepository <|.. MongoNoSqlRepository : implements

    %% Pipelines & Coordinators
    class answer_rulebook_question {
        <<Pipeline Function>>
        +search_chunks() via RagEngine
        +answer_question() via AiRuleGenerator
        +_select_citations()
    }
    answer_rulebook_question ..> RagEngine : searches
    answer_rulebook_question ..> AiRuleGenerator : synthesizes
    answer_rulebook_question ..> RuleAnswer : produces

    class PdfBatchIngestor {
        -_storage: PdfStorage
        -_repo: GameManualRepository & PendingPdfRepository
        -_rag: RagEngine
        -_extractor: PdfTextExtractor
        -_chunker: TextChunker
        +run_ingestion_cycle()
    }
    PdfBatchIngestor ..> PdfStorage : reads/moves PDFs
    PdfBatchIngestor ..> RagEngine : indexes vectors
    PdfBatchIngestor ..> NoSqlRepository : records status

    %% Domain Entities / Value Objects
    class RuleAnswer {
        +game_id: str
        +question: str
        +answer_markdown: str
        +citations: tuple[RuleChunk]
        +found_in_rules: bool
        +source: ManualSource
        +is_verified: bool
    }

    class GeneratedRulebook {
        +game_title: str
        +overview: str
        +setup_steps: tuple[str]
        +turn_structure: tuple[str]
        +winning_condition: str
        +key_rules: tuple[str]
        +source: ManualSource
        +to_markdown() str
    }

    class QuickRecap {
        +game_title: str
        +goal: str
        +turn_summary: tuple[str]
        +setup_highlights: tuple[str]
        +key_rules_to_remember: tuple[str]
        +is_grounded: bool
        +cited_chunk_ids: tuple[str]
        +to_markdown() str
    }

    GeminiAiRuleGenerator ..> GeneratedRulebook : creates
    GeminiAiRuleGenerator ..> QuickRecap : creates
```

---

## 2. Core Interaction Workflows

### 2.1 Grounded RAG Question-Answering Pipeline (`rag/qa.py`)

When a player asks a rule question, `answer_rulebook_question` acts as a pure pipeline function coordinating vector retrieval and LLM synthesis with anti-corruption mapping:

```mermaid
sequenceDiagram
    autonumber
    actor Player as Player / HTTP API
    participant QA as answer_rulebook_question (rag/qa.py)
    participant Qdrant as QdrantRagEngine (rag/qdrant_engine.py)
    participant Generator as GeminiAiRuleGenerator (ai/generator.py)
    participant AntiCorruption as schemas.py (Anti-Corruption Layer)

    Player->>QA: query = RulebookQuestion(game_id="catan", question="What happens on a 7?")
    QA->>Qdrant: search_chunks(game_id="catan", query="...", top_k=5)
    Qdrant-->>QA: tuple[RuleChunk, ...] (relevant paragraphs with page/section metadata)
    
    QA->>Generator: answer_question("Catan", question, chunks)
    Generator->>Generator: build_rule_answer_prompt(XML tags + character escaping)
    Generator->>Generator: aio.models.generate_content(response_schema=RuleAnswerSchema)
    Generator->>AntiCorruption: map_rule_answer_to_domain(schema, allowed_chunk_ids, is_grounded=True)
    AntiCorruption-->>Generator: GeneratedRuleAnswer(answer_text, found_in_rules=True, cited_chunk_ids=("catan-p9-c0002",))
    Generator-->>QA: GeneratedRuleAnswer
    
    QA->>QA: _select_citations(retrieved_chunks, generated)
    Note over QA: Matches cited_chunk_ids with retrieved chunks.<br/>If found_in_rules is False, forces citations=().
    QA-->>Player: RuleAnswer(answer_markdown, citations=(catan-p9-c0002,), source=MANUAL_PDF, is_verified=True)
```

---

### 2.2 Three-Tier Rule Resolution Chain (Tasks 4, 6, 7 → Task 8)

The system is designed around a 3-tier fallback hierarchy that **Task 8 (Rule Orchestrator)** coordinates:

```mermaid
flowchart TD
    Start(["Player Requests Rules or Quick Recap"]) --> Tier1{"Tier 1: Check Database & RAG"}
    
    Tier1 -- "Manual is READY" --> RAGPath["Retrieve RuleChunks from QdrantRagEngine
    Run GeminiAiRuleGenerator (generate_quick_recap or answer_question)
    Source = MANUAL_PDF (is_verified = True)"]
    
    Tier1 -- "Not Indexed" --> Tier2{"Tier 2: InternetRulebookFetcher"}
    
    Tier2 -- "PDF Found & Extracted" --> Ingest["Ingest PDF chunks into Qdrant & MongoDB
    Serve through Tier 1 RAG pipeline
    Source = INTERNET_API (is_verified = True)"]
    
    Tier2 -- "Not Found Online" --> Tier3["Tier 3: GeminiAiRuleGenerator (AI Fallback)
    generate_fallback_rules() / generate_quick_recap(chunks=())"]
    Tier3 --> CachedAI["Return GeneratedRulebook
    Source = AI_GENERATED (is_verified = False)
    Save to MongoDB as READY (automatically superseded if official PDF arrives)"]
```

---

### 2.3 Batch PDF Ingestion Pipeline (`batch/ingestor.py`)

When official PDFs are dropped into storage, `PdfBatchIngestor` processes them in a single batch cycle:

```mermaid
sequenceDiagram
    autonumber
    participant Ingestor as PdfBatchIngestor
    participant Storage as PdfStorage (Local / GCS)
    participant Extractor as PyMuPdfTextExtractor
    participant Chunker as TextChunker
    participant Qdrant as QdrantRagEngine
    participant Repo as NoSqlRepository (MongoDB)

    Ingestor->>Storage: list_unprocessed_keys()
    Storage-->>Ingestor: ("incoming/catan.pdf",)
    
    Ingestor->>Storage: read_pdf_bytes("incoming/catan.pdf")
    Storage-->>Ingestor: raw PDF bytes
    
    Ingestor->>Extractor: extract_pages(pdf_bytes)
    Extractor-->>Ingestor: list of ExtractedPages (text + 1-based page numbers)
    
    Ingestor->>Chunker: chunk_pages("catan", pages)
    Chunker-->>Ingestor: list of RuleChunks (overlapping, preserving section titles & pages)
    
    Ingestor->>Qdrant: index_chunks(chunks)
    Note over Qdrant: Computes embeddings & stores in Qdrant with game_id filter
    
    Ingestor->>Repo: save_manual(GameManual(status=READY, source=MANUAL_PDF))
    Ingestor->>Storage: move_to_processed("incoming/catan.pdf")
```

---

## 3. Key Architectural Patterns in Use

| Concept Tag | Location | Plain-English Purpose |
|:---|:---|:---|
| **`[Design Pattern] Explicit Abstract Base Class (ABC) Ports`** | [`domain/contracts.py`](../src/boardgamerules/domain/contracts.py) | Outer infrastructure tools (databases, vector stores, LLMs, storage) depend on inner domain ABCs, allowing all I/O to be substituted with fast in-memory fakes in tests. |
| **`[Design Pattern] Anti-Corruption Layer`** | [`ai/schemas.py`](../src/boardgamerules/ai/schemas.py) | Uses Pydantic v2 schemas to parse untrusted JSON from Gemini, sanitizing whitespace and filtering hallucinated citation IDs before mapping to frozen domain entities. |
| **`[AI Engineering] Prompt Injection Defense`** | [`ai/prompts.py`](../src/boardgamerules/ai/prompts.py) | Isolates untrusted queries and PDF excerpts inside XML tags (`<rulebook_excerpts>`), stripping control chars and escaping XML delimiters to protect system instructions. |
| **`[AI Engineering] Structured LLM Outputs`** | [`ai/generator.py`](../src/boardgamerules/ai/generator.py) | Constrains Gemini output directly via `response_schema` and `response_mime_type="application/json"` instead of fragile regex parsing of markdown text. |
| **`[System Design] SSRF Protection`** | [`fetcher/url_safety.py`](../src/boardgamerules/fetcher/url_safety.py) | Asynchronously resolves hostnames and blocks private, loopback, link-local, and cloud metadata IPs before fetching external PDFs. |
| **`[Design Pattern] Immutable State Machine Transition`** | [`domain/manual.py`](../src/boardgamerules/domain/manual.py) | Entities like `GameManual` use frozen dataclasses and return new instances (`replace()`) upon state changes (e.g. `mark_superseded()`), preventing hidden mutation bugs. |
