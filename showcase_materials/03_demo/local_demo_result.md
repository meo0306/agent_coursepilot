# Verified local demo result

Verified on 2026-08-26 with Docker Desktop and Compose v2 on Windows.

## Result

- PostgreSQL 16: healthy
- CourseRAG API: healthy on port 8001
- CoursePilot API: healthy on port 8000
- PostgreSQL schemas: `courserag`, `coursepilot`
- CoursePilot task terminal state: `completed`
- Generated artifact: one lesson record
- CourseRAG boundary: remote HTTP
- Paid provider calls: 0
- Legacy in-process Chroma path: disabled

The verification command was:

```powershell
python scripts/demo_local.py
```

The script creates an idempotent demo course, starts a deterministic lesson task, polls the task
to a terminal state, and fails unless the task completes through the remote CourseRAG boundary.

## Quality boundary

This result proves the local engineering journey and service split. It does not replace the P18
formal human-quality result, whose quality gate did not pass and remains disclosed in
[`EVALUATION.md`](EVALUATION.md).
