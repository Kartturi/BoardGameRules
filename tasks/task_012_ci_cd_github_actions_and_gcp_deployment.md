# Task 12: CI/CD Pipelines (GitHub Actions & GCP Cloud Run Deployment)

## Objective
Build automated CI/CD pipelines in GitHub Actions for continuous quality checks (linting, testing, build verification) and automated container deployment to GCP Cloud Run.

## Requirements
- Create a GitHub Actions CI workflow (`.github/workflows/ci.yml`) triggered on pushes and pull requests to run `ruff check`, `ruff format --check`, `pytest`, and frontend type/build checks.
- Create a GitHub Actions CD workflow (`.github/workflows/deploy-gcp.yml`) to build Docker images, push them to Google Artifact Registry, and deploy the backend, frontend, and batch job to GCP Cloud Run Services & Jobs.
- Configure keyless authentication using GCP Workload Identity Federation (OIDC) instead of long-lived service account JSON keys.
- Document the CI/CD setup, required GitHub repository variables/secrets, and GCP IAM setup commands.
