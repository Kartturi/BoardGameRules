# Task 5: Batch PDF Ingestion Job

## Objective
Create the batch job that scans the drop folder for manual PDF rulebooks, ingests them into the RAG system, updates NoSQL status, and moves processed files out.

## Requirements
- Implement `PdfStorage` adapters for both local directory (`LocalPdfStorage`) and GCP Cloud Storage bucket (`GcsPdfStorage`).
- Scan the configured `PdfStorage` input location (and/or pending NoSQL records) for new PDF rulebooks.
- Ingest each PDF into the RAG vector store and register the `GameManual` as ready in the NoSQL database.
- Move successfully processed PDFs to `processed/` (local folder or GCS prefix) and mark failed files with error details.
- Provide a stateless CLI entry point compatible with both local background polling and GCP **Cloud Run Jobs**.
