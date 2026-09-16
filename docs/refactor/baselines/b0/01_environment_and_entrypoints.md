# B0 Environment and Entrypoints

- Captured on: 2026-07-23 (Asia/Shanghai)
- Baseline `main` commit: `eb9b3a6aa51348cf1fba0de7a21e5d073761939b`
- `origin/main` at capture: `eb9b3a6aa51348cf1fba0de7a21e5d073761939b`
- Working branch: `refactor/p00-baseline`
- Working tree at capture: dirty; pre-existing owner changes are preserved
- Commit subject: `after evaluate`
- Commit authored at: `2026-07-21T12:57:02+08:00`

## Runtime and dependency lock

| Item | B0 value |
|---|---|
| `uv` | `0.11.28` |
| Active project Python | `3.11.9` |
| Supported Python range | `>=3.11,<3.14` |
| `langgraph.json` Python | `3.12` |
| Starting `pyproject.toml` SHA-256 | `ca951e41247556bd4973ce4b669169a62a2f6df44c97b3218e40eb71437311b1` |
| P00 result `pyproject.toml` SHA-256 | `19843f6e58702c03abbd9e1bfe6d8c241308008743c02fc7820306014226308b` |
| Starting/final `uv.lock` SHA-256 | `2330c4c36b889c456ec1bac21aece0475e0e0e9a25e3332a9ee31072df281e5b` |
| Alembic head | `0007_add_async_task_queue_fields` |

The active environment uses a supported Python version. LangGraph's development configuration
selects Python 3.12, so results from that surface must record its interpreter separately.
On this Windows environment, the `uv run alembic` script trampoline cannot canonicalize its
launcher path; `uv run python -m alembic` is the verified equivalent entrypoint.

## Environment-variable inventory

Only names, purpose, and sensitivity are recorded. Values from `.env`, `.env.eval`, or
`.env.origin` are excluded.

| Group | Names | Secret-bearing |
|---|---|---|
| Web runtime | `HOST`, `PORT`, `MODE`, `LOG_LEVEL`, `GRACEFUL_SHUTDOWN_TIMEOUT`, `AGENT_URL` | no |
| HTTP authentication | `AUTH_SECRET` | yes |
| Prompt-agent providers | `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `USE_FAKE_MODEL`, `DEFAULT_MODEL` | API keys |
| Compatible chat provider | `COMPATIBLE_BASE_URL`, `COMPATIBLE_MODEL`, `COMPATIBLE_API_KEY` | API key |
| Checkpoint database | `DATABASE_TYPE`, `SQLITE_DB_PATH` | no |
| PostgreSQL | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_APPLICATION_NAME`, `POSTGRES_MIN_CONNECTIONS_PER_POOL`, `POSTGRES_MAX_CONNECTIONS_PER_POOL` | password |
| CoursePilot database/storage | `COURSEPILOT_DATABASE_URL`, `COURSEPILOT_STORAGE_DIR`, `COURSEPILOT_CHROMA_DIR`, `COURSEPILOT_ENABLED` | URL may contain credentials |
| Generation controls | `COURSEPILOT_GENERATION_MODE`, `COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK`, `COURSEPILOT_MAX_REPAIR_ROUNDS`, `COURSEPILOT_DUPLICATE_THRESHOLD`, `COURSEPILOT_LLM_TIMEOUT_SECONDS`, `COURSEPILOT_LLM_MAX_RETRIES`, `COURSEPILOT_LLM_HEALTH_CHECK_MODE`, `COURSEPILOT_LLM_HEALTH_CHECK_TIMEOUT_SECONDS`, `COURSEPILOT_TOKENIZER_PATH` | no |
| Idempotency/worker | `COURSEPILOT_IDEMPOTENCY_LEASE_SECONDS`, `COURSEPILOT_ASYNC_WORKER_ENABLED`, `COURSEPILOT_ASYNC_WORKER_POLL_SECONDS`, `COURSEPILOT_ASYNC_TASK_LEASE_SECONDS`, `COURSEPILOT_ASYNC_WORKER_SHUTDOWN_TIMEOUT_SECONDS` | no |
| Embeddings | `COURSEPILOT_EMBEDDING_PROVIDER`, `COURSEPILOT_EMBEDDING_MODEL`, `COURSEPILOT_EMBEDDING_BASE_URL`, `COURSEPILOT_EMBEDDING_API_KEY`, `COURSEPILOT_EMBEDDING_MAX_RETRIES`, `COURSEPILOT_EMBEDDING_RETRY_BASE_SECONDS`, `COURSEPILOT_EMBEDDING_RETRY_MAX_SECONDS` | API key |
| Evaluation | `COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE`, `COURSEPILOT_EVAL_BUILD_KB_TIMEOUT_SECONDS`, `COURSEPILOT_EVAL_GENERATION_TIMEOUT_SECONDS`, `COURSEPILOT_EVAL_ENV_FILE` | env file may contain secrets |

## Canonical startup and validation commands

```powershell
uv sync --frozen
uv run python -m alembic upgrade head
uv run python src/run_service.py
uv run streamlit run src/streamlit_app.py
```

Container startup:

```powershell
docker compose up --build
docker compose exec agent_service python -m alembic upgrade head
```

Evaluation stack:

```powershell
docker compose --env-file .env.eval -f compose.yaml -f compose.eval.yaml up --build
docker compose --env-file .env.eval -f compose.yaml -f compose.eval.yaml exec -T agent_service python -m alembic upgrade head
```

Required P00 verification:

```powershell
uv run pytest -q
uv run ruff format --check
uv run ruff check
uv run mypy src/
```
