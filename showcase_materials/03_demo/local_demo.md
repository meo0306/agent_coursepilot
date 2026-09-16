# Local portfolio demo

This demo runs CoursePilot, CourseRAG and PostgreSQL locally. It uses deterministic generation and
labelled demo Evidence: no paid model, private textbook, model weight or evaluation Gold is used.

## Prerequisites

- Docker Desktop with Compose v2
- `course-pilot` and `course-rag` cloned as sibling directories

## Run

From `course-pilot`:

```powershell
docker compose down -v
docker compose build
docker compose up -d
docker compose -p courseportfolio exec -T coursepilot \
  python scripts/demo_local.py --base-url http://localhost:8000
```

Expected final fields include `task_status: completed`, `remote_courserag_mode: true` and
`paid_provider_calls: 0`.

OpenAPI remains available at:

- CoursePilot: <http://localhost:8000/docs>
- CourseRAG: <http://localhost:8001/docs>

Stop the demo without deleting its volume:

```powershell
docker compose down
```

## What this proves

1. Both clean repositories build and start independently.
2. Each service applies its own Alembic baseline to its own PostgreSQL schema.
3. CoursePilot creates a task, calls CourseRAG over HTTP, receives bounded Evidence and completes a
   deterministic lesson workflow.
4. The deprecated in-process RAG path remains disabled.

This is an engineering-path demo, not evidence that the failed P18 formal human-quality Gate passed.
