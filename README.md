# CoursePilot

CoursePilot is a teacher-facing course preparation assistant built around a
workflow-first agent architecture. It helps instructors turn course source
materials into a private knowledge base, then generate lesson designs, exams,
answer materials, and PPT outlines with source-grounded retrieval, structured
validation, export, review, and verified write-back.

[中文说明](README.zh-CN.md)

## Core Capabilities

- Dynamic course knowledge base: upload course files, parse them, split them into
  chunks, embed them, and search course-scoped Chroma collections.
- Workflow-first agents: three LangGraph workflows cover lesson design, exam /
  homework generation, and PPT outline generation.
- Structured LLM generation: CoursePilot asks the model for JSON, validates it
  with Pydantic schemas, and applies repair or deterministic fallback when
  needed.
- Source-grounded outputs: lesson plans, questions, and slide outlines retain
  references to retrieved course context.
- File exports: DOCX and PPTX files are rendered by exporters from structured
  data. The LLM never writes Office files directly.
- Human review loop: approved lesson designs, questions, and PPT outlines can be
  written back into the verified knowledge base for later retrieval.
- Operational metadata: workflow thread IDs, prompt hashes, LLM attempts, token
  usage estimates, fallback counts, and validation reports are stored with
  generation tasks.

## Product Workflow

```text
Create course
  -> upload textbook / syllabus / knowledge graph files
  -> build course-scoped Chroma knowledge base
  -> search source-grounded course context
  -> generate lesson designs, exam blueprints/questions, and PPT outlines
  -> validate structured JSON and repair when needed
  -> export DOCX/PPTX files
  -> review generated content
  -> write approved content back as verified knowledge
```

## Architecture

```text
FastAPI service
  -> minimal prompt-entry Agent API
  -> /api/coursepilot/* product API
  -> CoursePilot services and database transactions
  -> LangGraph lesson / exam / PPT workflows
  -> PostgreSQL business tables
  -> Chroma vector collections
  -> local upload/export storage

Streamlit app
  -> CoursePilotClient
  -> CoursePilot workflow page
```

The main implementation lives in these layers:

- `src/coursepilot/`: product APIs, services, schemas, ORM models, RAG, LLM
  helpers, validators, exporters, and Streamlit UI modules.
- `src/agents/coursepilot/`: LangGraph workflows for lesson, exam, and PPT
  generation.
- `src/service/`: FastAPI app, authentication, prompt-entry agent endpoints, and
  CoursePilot router mounting.
- `src/client/`: `CoursePilotClient` for product APIs and a minimal
  `AgentClient` for prompt-entry agent calls.
- `alembic/`: CoursePilot business database migrations.

## API Boundary

CoursePilot has two intentionally separate API surfaces.

### Product API

`/api/coursepilot/*` is the real product API. It owns structured inputs,
database writes, exports, review, and knowledge-base write-back.

Representative endpoints:

| Area | Endpoint | Purpose |
| --- | --- | --- |
| Courses | `POST /api/coursepilot/courses` | Create a course |
| Documents | `POST /api/coursepilot/courses/{course_id}/documents/upload` | Upload course material |
| Knowledge base | `POST /api/coursepilot/documents/{document_id}/build-kb` | Parse, chunk, embed, and index a document |
| Knowledge base | `POST /api/coursepilot/courses/{course_id}/kb/search` | Search course context |
| Lessons | `POST /api/coursepilot/courses/{course_id}/lessons/generate` | Generate a lesson design |
| Lessons | `POST /api/coursepilot/lessons/{lesson_id}/export` | Export a lesson DOCX |
| Exams | `POST /api/coursepilot/courses/{course_id}/exams/blueprint` | Generate an exam blueprint |
| Exams | `POST /api/coursepilot/exams/{blueprint_id}/generate` | Generate questions after blueprint confirmation |
| Exams | `POST /api/coursepilot/exams/{blueprint_id}/export` | Export student exam, answer key, explanation, and answer sheet |
| PPT | `POST /api/coursepilot/lessons/{lesson_id}/ppt/generate` | Generate a PPT outline from a lesson design |
| PPT | `POST /api/coursepilot/ppt/{outline_id}/export` | Export an editable PPTX |
| Review | `POST /api/coursepilot/reviews` | Record teacher review status |
| Review | `POST /api/coursepilot/reviews/{review_id}/write-back` | Write approved content back to verified knowledge |
| Files | `GET /api/coursepilot/files/{file_id}/download` | Download an exported file |

The full interactive API reference is available from FastAPI at `/docs` when
the service is running.

### Prompt-Entry Agent API

The generic agent API is kept narrow for compatibility and prompt guidance:

- `GET /info`
- `POST /invoke` and `POST /{agent_id}/invoke`
- `POST /stream` and `POST /{agent_id}/stream`
- `POST /history`
- `GET /health`

Only three prompt-entry agents are registered:

- `coursepilot-lesson-agent` (default)
- `coursepilot-exam-agent`
- `coursepilot-ppt-agent`

These endpoints do not accept CoursePilot's structured lesson, exam, or PPT
business parameters. Use `/api/coursepilot/*` for product workflows.

## Quickstart

### Requirements

- Python 3.11, 3.12, or 3.13
- `uv`
- PostgreSQL for the CoursePilot product database
- Docker and Docker Compose for containerized startup

### Local Setup

Install dependencies:

```powershell
uv sync --frozen
```

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Configure PostgreSQL for CoursePilot in `.env`. Either set
`COURSEPILOT_DATABASE_URL` directly or fill in the `POSTGRES_*` variables.

Apply business database migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Start the FastAPI service:

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

Start the Streamlit app in another terminal:

```powershell
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py
```

Open:

- Streamlit app: `http://localhost:8501`
- FastAPI docs: `http://localhost:8080/docs`
- Health check: `http://localhost:8080/health`

### Docker Compose

Start PostgreSQL, FastAPI, and Streamlit:

```powershell
docker compose up --build
```

If the database volume is new, apply migrations against the Compose database:

```powershell
docker compose exec agent_service python -m alembic upgrade head
```

Open the Streamlit app at `http://localhost:8501`.

## Configuration

Copy `.env.example` to `.env` and only set the values needed by your
environment.

### Service and Auth

- `HOST`, `PORT`, `MODE`, `LOG_LEVEL`: web service runtime settings.
- `AUTH_SECRET`: optional bearer token. When set, both prompt-entry and
  CoursePilot product routes require `Authorization: Bearer <AUTH_SECRET>`.

### Models

CoursePilot supports OpenAI, DeepSeek, OpenAI-compatible endpoints, and a fake
model for local tests.

For production-style OpenAI-compatible generation:

```env
COMPATIBLE_BASE_URL=https://your-compatible-endpoint/v1
COMPATIBLE_MODEL=your-chat-model
COMPATIBLE_API_KEY=your-key
COURSEPILOT_GENERATION_MODE=llm
```

Generation mode options:

- `auto`: use a real configured model when available, otherwise use deterministic
  fallback.
- `llm`: require a real LLM path and run a startup health check.
- `deterministic`: force local deterministic generation for tests and smoke
  demos.

### Databases and Storage

- `DATABASE_TYPE` and `SQLITE_DB_PATH` configure LangGraph prompt-agent
  persistence used by `/history`.
- CoursePilot business data uses PostgreSQL through `COURSEPILOT_DATABASE_URL`
  or the `POSTGRES_*` fallback variables.
- `COURSEPILOT_STORAGE_DIR` stores uploaded and exported files.
- `COURSEPILOT_CHROMA_DIR` stores Chroma vector collections.

### Embeddings

For production embeddings:

```env
COURSEPILOT_EMBEDDING_PROVIDER=openai-compatible
COURSEPILOT_EMBEDDING_MODEL=your-embedding-model
COURSEPILOT_EMBEDDING_BASE_URL=https://your-compatible-endpoint/v1
COURSEPILOT_EMBEDDING_API_KEY=your-key
```

When embedding settings are absent, CoursePilot uses deterministic hashing
embeddings for tests and local smoke demos.

### LLM Reliability and Usage

- `COURSEPILOT_LLM_TIMEOUT_SECONDS`: per-call timeout. Defaults to `120` seconds.
- `COURSEPILOT_LLM_MAX_RETRIES`: retry count before fallback.
- `COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK`: set to `true` for real
  evaluations so failed LLM calls fail the sample instead of using
  deterministic fallback output.
- `COURSEPILOT_LLM_HEALTH_CHECK_MODE`: startup health check mode for `llm`
  generation.
- `COURSEPILOT_TOKENIZER_PATH`: DeepSeek tokenizer path used to estimate token
  usage when provider usage metadata is unavailable.
- `COURSEPILOT_EMBEDDING_MAX_RETRIES`: retries after embedding 429 responses.
  Defaults to `4`.
- `COURSEPILOT_EMBEDDING_RETRY_BASE_SECONDS`: first embedding 429 backoff.
  Defaults to `15` seconds.
- `COURSEPILOT_EMBEDDING_RETRY_MAX_SECONDS`: maximum embedding 429 backoff.
  Defaults to `120` seconds.
- `COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE`: chunk knowledge-point extraction mode
  during ingestion. Supported values are `auto`, `llm`, and `deterministic`.
- `COURSEPILOT_IDEMPOTENCY_LEASE_SECONDS`: in-progress protection window for
  idempotent request records. It defaults to `14400` seconds.
- `COURSEPILOT_ASYNC_WORKER_ENABLED`: start the database task worker in the API
  process. Defaults to `true`.
- `COURSEPILOT_ASYNC_WORKER_POLL_SECONDS`: idle poll interval. Defaults to `1`.
- `COURSEPILOT_ASYNC_TASK_LEASE_SECONDS`: renewable task lease. Defaults to
  `300` seconds.
- `COURSEPILOT_ASYNC_WORKER_SHUTDOWN_TIMEOUT_SECONDS`: worker shutdown wait.
  Defaults to `10` seconds.

### P0 Async Tasks and Idempotency

KB build, lesson generation, exam blueprint/question generation, and PPT
outline generation now enqueue database-backed tasks and return `202 Accepted`
with `task_id`, `status=pending`, and `status_url`. Poll
`GET /api/coursepilot/tasks/{task_id}` until `completed`, `needs_review`, or
`failed`; terminal responses contain `result` or `error_message`. Renewable
worker leases allow an expired `running` task to be reclaimed after a process
failure.

These endpoints and course creation accept `Idempotency-Key`. The same key and
payload returns the same task, while a changed payload returns `409`. A failed
task is re-enqueued on the next same-key request so evaluation resume can retry.
The high-level `CoursePilotClient` automatically enqueues, polls, and returns
the final domain result; raw HTTP clients must poll explicitly.

Run `python -m alembic upgrade head` after upgrading to create the idempotency
table and add queue, lease, and result fields to `coursepilot_generation_tasks`.

## Sample Data

Sample course files are kept in `data/coursepilot_sample/`. The current sample
set contains:

- textbook / teaching material
- knowledge graph XLSX

These files are useful for local upload, knowledge-base build, retrieval, and
generation smoke tests.

## Tests and Evaluation

Run the main test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run lint and type checks:

```powershell
.\.venv\Scripts\python.exe -m ruff format --check
.\.venv\Scripts\python.exe -m ruff check
.\.venv\Scripts\python.exe -m mypy src/
```

Run deterministic evaluation metrics:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m coursepilot.evals.run_sample_eval --output storage\coursepilot_eval_report.json
```

Run the P00 local B0 smoke with the owner-supplied, independent DOCX and PDF in
`data/sample_files/`:

```powershell
$env:PYTHONPATH='src'
uv run python -m coursepilot.evals.run_b0_smoke `
  --sample-dir data/sample_files `
  --output docs/refactor/baselines/b0/05_b0_smoke_report.json
```

The B0 runner uses isolated SQLite/Chroma state, deterministic generation, and
hashing embeddings. It makes no external provider calls and stores only file
fingerprints and structural results, never source text. Its retrieval probes are
non-Gold smoke checks and must not be reported as quality metrics. To execute the
gated fixture test, set `COURSEPILOT_RUN_B0_SAMPLE_SMOKE=1`.

Run a real-model evaluation with isolated Postgres and Chroma state:

```powershell
Copy-Item .env.eval.example .env.eval
# Fill COMPATIBLE_* and embedding settings in .env.eval
docker compose --env-file .env.eval -f compose.yaml -f compose.eval.yaml up --build
```

After the service starts, apply migrations to the isolated evaluation database
in another terminal:

```powershell
docker compose --env-file .env.eval -f compose.yaml -f compose.eval.yaml exec -T agent_service python -m alembic upgrade head
```

Then run the evaluation runner:

```powershell
$env:PYTHONPATH='src'
$env:COURSEPILOT_CHROMA_DIR='chroma_db_eval'
.\.venv\Scripts\python.exe -m coursepilot.evals.run_real_eval `
  --base-url http://localhost:8080 `
  --sample-dir data\coursepilot_sample `
  --chroma-dir chroma_db_eval `
  --build-kb-timeout 7200 `
  --generation-timeout 1800 `
  --checkpoint storage_eval\coursepilot_real_eval_checkpoint.json `
  --output storage_eval\coursepilot_real_eval_report.json
```

The runner atomically updates the checkpoint and partial report before and after
each upload, KB build, retrieval, generation, and export step. After a failure,
run the same command with the additional option:

```powershell
  --resume
```

Resume validates the environment options and sample-file SHA-256 values, then
skips every `succeeded` step. Use `--force-resume` only after reviewing a
configuration or sample-data mismatch. Increasing `--build-kb-timeout` does not
invalidate a checkpoint; neither does changing `--generation-timeout`. When a checkpoint already exists, the runner requires
`--resume`; use `--overwrite-checkpoint` only to explicitly discard it and start
over. Without `--checkpoint`, the runner creates `<output-stem>.checkpoint.json`
beside the report.

The real evaluation environment enables
`COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK=true`. If an LLM call,
structured parse, or schema validation fails, the task fails and is reported
instead of using deterministic fallback output.

Real evaluation defaults to `COURSEPILOT_EMBEDDING_PROVIDER=openai-compatible`
and `COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE=llm`. Each chunk invokes the LLM for
knowledge-point extraction, and vectorization calls the `/embeddings` endpoint
configured by `COURSEPILOT_EMBEDDING_BASE_URL`.

The 27 MB sample textbook produces hundreds of chunks, so full ingestion can
take substantially longer than 300 seconds and make hundreds of LLM calls.
`--build-kb-timeout` and `--generation-timeout` control only how long the
evaluation client polls; they do not stop server tasks or enable fallback. The
matching environment variables are `COURSEPILOT_EVAL_BUILD_KB_TIMEOUT_SECONDS`
and `COURSEPILOT_EVAL_GENERATION_TIMEOUT_SECONDS`.

The evaluation client sends stable idempotency keys derived from checkpoint
`run_id + step_id`. After a client timeout, lost response, or local process
termination, the server task keeps running; resume retrieves the same `task_id`
and continues polling without another LLM call. A task that explicitly failed
is re-enqueued on the next same-key resume request.

Real LLM integration tests are intentionally gated and skipped by default. Enable
them only when a compatible model endpoint and API key are available.

## Documentation

Detailed product and engineering documents live in `CoursePilot_markdown_docs/`:

- PRD and MVP acceptance criteria
- Technical architecture
- Development plan
- Phase audit notes
- LLM engineering, tracing, fallback, and usage-statistics notes

The README is the project entry point; the documents folder contains the deeper
design record.

## Repository Layout

```text
src/coursepilot/          Product APIs, services, schemas, models, RAG, validators, exporters
src/agents/coursepilot/   LangGraph lesson, exam, and PPT workflows
src/service/              FastAPI app, auth, prompt-entry endpoints
src/client/               CoursePilot product client and minimal Agent client
src/memory/               LangGraph checkpoint/store persistence
alembic/                  CoursePilot PostgreSQL migrations
data/coursepilot_sample/  Sample course materials
tests/coursepilot/        CoursePilot product and workflow tests
CoursePilot_markdown_docs/ PRD, architecture, phase audits, and implementation notes
```

## License

This project is licensed under the MIT License. See `LICENSE` for details.
