# Application Design & Specification

## Overview

I wish to have an application that can give you any boardgame rule there is to read and save it to later use.
There is simple and clear UI for the user that use's google login only.

The rules are downloaded to the rag system, so users can ask specific questions about rules.


## Core Features & User Flows
    User chooses the game and it show the rules. There are ways to make shorter quick recap option maybe in a button. 
    And then there is text field user can ask about specific rules in the rules book in rag.
    User can save the generated rules and recaps and other answers.


## Architecture & Components
    I wish to have game rules downloaded into rag system in following way. 

    1.There is manual way to drop rules pdf to file
    or db and some process takes it and creates rag system. Some batch job goes all the files downloads them to rag and 
    mark ready or transfer them out
    2.There is some kind of api try to fetch the rules from internet and then rag it.
    3. Actual ai product tells the rules if other ways fails.

    So when user fetches rainbow games rule. It checks the current rag -> it check the api and rag it. It uses AI 
    resource to fetch it or create it.
    
    We need NoSql database to keep track of following data: 
    1.user login information
    2. Ragged game manuals already in system.
    3.What pdf manuals exists in the folder waiting for some batch job to run and rag it.
    4.User history of created text

    Ui: should be some nice standard using maybe react and typescript or something easy.

## Open Questions & Notes
    Present me questions and options when needed, like which vector database to choose from.
    
    I want this also containerized.

    Present opinions should this be monorepo or use different repos. There is separeate ragging module. api fething 
    module, and the actual ai resource use module. There is some kind of organisation body which determines when to use
    which action. There is also batch job that can rag the folder of rules.

    Ask opnions a lot before committin.

---

## Architectural Evaluation, Opinions & Decisions Log

### 1. Repository Strategy: Modular Monorepo vs. Multi-Repo
- **Recommendation: Modular Monorepo**
  - **Why**: The Batch PDF Job, RAG Module, Internet API Fetcher, AI Module, and Orchestrator ("organisation body") all share the exact same domain models (`GameManual`, `PendingPdfManual`, `UserProfile`, `SavedUserEntry`) and NoSQL/Vector DB schemas. In a multi-repo setup, every schema tweak requires publishing versioned packages and syncing across 4–5 repos.
  - **How to keep strict separation**: Enforce clean module boundaries inside `src/boardgamerules/` (`rag/`, `fetcher/`, `ai/`, `orchestrator/`, `batch/`, `db/`, `api/`) using Python `Protocol` interfaces, plus a `frontend/` folder at root for React + TypeScript, all orchestrated by a single `docker-compose.yml`.

### 2. Vector Database Options (for RAG)
- **Option A (Recommended): Qdrant** — Runs as a lightweight Docker container (`qdrant/qdrant`), also supports an embedded local/in-memory mode (`QdrantClient(":memory:")`) for zero-dependency unit tests, and has first-class metadata filtering (e.g., filtering chunks by `game_id`).
- **Option B: ChromaDB** — Very easy Python integration and embedded mode, great for prototyping, slightly less production-featured for complex metadata filtering.
- **Option C: MongoDB Atlas Vector Search / pgvector** — Combines document/relational storage and vectors in one DB, though local Docker setup for Atlas Vector Search is heavier than standalone Qdrant + MongoDB.

### 3. NoSQL Database Options
- **Option A (Recommended): MongoDB (via `motor` / `pymongo` or `beanie`)** — Easy to run in Docker (`mongo:7`), natural fit for the 4 collections (`users`, `manuals`, `pending_pdfs`, `user_history`), flexible schema for varying rulebook metadata.
- **Option B: Firestore / DynamoDB (with local emulator)** — Great if deploying serverless to GCP/AWS, more boilerplate for local Docker setups.
- **Option C: TinyDB / Document-SQLite** — Zero-container file-based NoSQL, good only for single-node local setups.

### 4. AI / LLM & Embedding Provider
- **Option A (Recommended): Google Gemini (`google-genai` SDK)** — Fast, huge context window for full board game PDFs, native embeddings (`text-embedding-004`), and low cost.
- **Option B: OpenAI (`openai` SDK)** — Industry standard (`gpt-4o` + `text-embedding-3-small`).
- **Option C: Provider-agnostic adapter (LiteLLM / Custom Protocol) with local Ollama support** — Allows switching between Gemini, OpenAI, Claude, or local models.

### 5. Internet Rulebook Fetching Strategy
- **Option A (Recommended): BoardGameGeek (BGG) XML API2 + Web Search API (Tavily / DuckDuckGo / Google Custom Search)** — Use BGG to canonicalize the board game title/ID and metadata, then search for official `<game name> rulebook filetype:pdf` links.
- **Option B: Direct Web Search API only** — Search directly for PDF rulebooks via search API.

### 6. Recorded Decisions
- **Repository Structure**: **Modular Monorepo** — Single repository with strict Python module boundaries (`src/boardgamerules/{domain,db,rag,fetcher,ai,orchestrator,batch,api}`) + `frontend/` (React + TypeScript) + unified `docker-compose.yml`.
- **Vector Database**: **Qdrant** — Runs in Docker (`qdrant/qdrant`) for production/dev and uses `QdrantClient(":memory:")` for fast, isolated unit tests; filters chunks by `game_id`.
- **NoSQL Database**: **MongoDB** — Runs in Docker (`mongo:7`) storing the 4 core collections (`users`, `game_manuals`, `pending_pdfs`, `user_history`), paired with an in-memory repository implementation for unit tests.
- **AI & Embeddings Provider**: **Google Gemini (`google-genai`)** behind a clean `AiProvider` / `EmbeddingProvider` Protocol so other LLMs can be swapped in at any time.
- **Tier-3 AI Fallback Caching**: **Cache with badge** — AI-generated fallback rules are saved in MongoDB/Qdrant marked with `source="ai_generated"` (`AI-Generated / Unverified` badge in UI) and automatically superseded when an official PDF manual is ingested.
- **Batch PDF Job Trigger**: **Both** — Background worker container polling/watching the PDF drop folder + CLI/API trigger to run on demand.
- **Internet Rulebook Fetcher (Tier 2)**: **BoardGameGeek (BGG) XML API2 + Web Search API (Tavily / DuckDuckGo)** — BGG resolves canonical game title/ID/metadata, and Web Search locates official PDF rulebooks.
- **PDF Text Extraction**: **PyMuPDF (`pymupdf` / `pymupdf4llm`)** — Extracts markdown-structured text and page numbers for accurate RAG citations.
- **Frontend Stack**: **Vite + React + TypeScript + Tailwind CSS** in `frontend/`.
- **Google Authentication**: **Google OAuth ID Token (`@react-oauth/google`)** verified by the FastAPI backend (`google-auth`), issuing a signed session JWT.
- **Schema & Domain Modeling Strategy (Hybrid)**:
  - **Inner Domain (`src/boardgamerules/domain/models.py`)**: Pure standard-library `@dataclass(frozen=True)` entities with zero third-party dependencies.
  - **Outer Boundaries (`ai/` & `api/`)**: **Pydantic v2 (`BaseModel`)** DTOs for Gemini structured outputs (`response_schema` in Task 7) and FastAPI HTTP request/response validation (in Task 9).
- **GCP Target Architecture**:
  - **Compute**: **Cloud Run Services** (Backend API & Frontend listening on `$PORT=8080`) + **Cloud Run Jobs** (for the Batch PDF Ingestion Job, triggered via Cloud Scheduler / Eventarc or CLI).
  - **PDF Storage Abstraction (`PdfStorage` Protocol)**: **Local filesystem folder** (`LocalPdfStorage`) for local Docker Compose development and **Google Cloud Storage (GCS) bucket** (`GcsPdfStorage`) for stateless GCP deployment.
  - **Cloud Databases**: **MongoDB** (`mongo:7` locally, **MongoDB Atlas** free tier on GCP via `MONGODB_URI`) + **Qdrant** (`qdrant/qdrant` locally, **Qdrant Cloud** free tier on GCP via `QDRANT_URL` & `QDRANT_API_KEY`).
  - **AI Configuration**: `google-genai` configured to support both a local `GEMINI_API_KEY` and GCP **Vertex AI** IAM (`GOOGLE_GENAI_USE_VERTEXAI=true`).

