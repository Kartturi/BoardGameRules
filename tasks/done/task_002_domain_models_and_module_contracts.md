# Task 2: Domain Models & Module Contracts

## Objective
Replace the placeholder models with the core domain entities and module protocol interfaces defined in `DESIGN.md`.

## Requirements
- Create immutable domain models in `src/boardgamerules/domain/models.py` for `UserProfile`, `GameManual`, `PendingPdfManual`, and `SavedUserEntry` (saved rules, quick recaps, and Q&A answers).
- Define clean `Protocol` interfaces for the 5 core boundaries: `NoSqlRepository`, `RagEngine`, `RulebookFetcher`, `AiRuleGenerator`, and `PdfStorage` (abstracting local folder vs. GCP Cloud Storage bucket).
- Define domain exceptions in `src/boardgamerules/domain/exceptions.py` for rule lookup, ingestion, and storage errors.
- Replace placeholder unit tests in `tests/unit/` with unit tests for the new domain models.
