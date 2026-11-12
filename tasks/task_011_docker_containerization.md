# Task 11: Docker & Docker Compose Containerization

## Objective
Containerize the backend API, batch PDF processor, frontend UI, NoSQL database, and vector database for one-command local and production deployment.

## Requirements
- Create Cloud Run–compatible `Dockerfile` definitions (listening on `$PORT`, default `8080`, stateless) for the Python backend/batch worker and the React + TypeScript frontend.
- Create `docker-compose.yml` wiring together the backend API, batch ingestion worker (with mounted PDF drop volume), frontend, MongoDB, and Qdrant for local development.
- Provide `.env.example` documenting environment variables for both local Docker and GCP Cloud Run (MongoDB Atlas URI, Qdrant Cloud URL/API key, GCS bucket name, Vertex AI / Gemini API key, Google OAuth client ID).
