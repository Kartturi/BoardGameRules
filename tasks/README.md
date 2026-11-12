# Tasks

Each task is defined in a concise markdown file with an **Objective** and **Requirements** list (see [`template.md`](template.md)).

## Completed Tasks (`tasks/done/`)
1. **[Task 1: Project Bootstrap & Architecture Guidelines](done/task_001_project_bootstrap.md)**
2. **[Task 2: Domain Models & Module Contracts](done/task_002_domain_models_and_module_contracts.md)**
3. **[Task 3: NoSQL Database & Repositories](done/task_003_nosql_database_repositories.md)**
4. **[Task 12: GitHub Actions CI Pipeline](done/task_012_github_actions_ci_pipeline.md)**

## Task Backlog
4. **[Task 4: RAG Engine & Vector Store Module](task_004_rag_engine_and_vector_store.md)**
5. **[Task 5: Batch PDF Ingestion Job](task_005_pdf_batch_ingestion_job.md)**
6. **[Task 6: Internet API Rulebook Fetcher Module](task_006_internet_rulebook_fetcher.md)**
7. **[Task 7: AI Fallback & Quick Recap Generator Module](task_007_ai_fallback_and_recap_generator.md)**
8. **[Task 8: Rule Orchestrator ("Organisation Body")](task_008_rule_orchestrator_service.md)**
9. **[Task 9: Backend HTTP API & Google OAuth Login](task_009_backend_api_and_google_auth.md)**
10. **[Task 10: React & TypeScript Frontend UI](task_010_react_typescript_frontend.md)**
11. **[Task 11: Docker & Docker Compose Containerization](task_011_docker_containerization.md)**
13. **[Task 13: GCP Cloud Run CD Deployment Pipeline](task_013_gcp_cd_deployment_pipeline.md)**

## Workflow
When a task is started, the [`task-workflow`](../skills/task-workflow/SKILL.md) and [`pr-review`](../skills/pr-review/SKILL.md) skills run automatically:
1. Checkout branch `feat/task-<number>-<short-slug>`.
2. Draft a design plan and challenge it with a **Devil's Advocate** subagent.
3. Review the design and Devil's Advocate feedback with the user in **Design Mode** until accepted.
4. Implement the solution and unit tests, then verify with `uv run pytest` and `uv run ruff check .`.
5. Spawn a **Security & Clean Code PR Reviewer** subagent; when approved, move the task into `tasks/done/` and rebase/merge onto `master`.
