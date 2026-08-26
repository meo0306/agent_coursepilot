# P19 Repository Split, CI and Portfolio Release

## Outcome

P19 is complete for the Course Owner-approved portfolio scope. The combined development repository
was checkpointed at `334de3a`, then published as two public repositories with clean single-root
histories:

- CourseRAG: <https://github.com/meo0306/course-rag>, release `v0.1.0`, commit `79a19f9`;
- CoursePilot: <https://github.com/meo0306/course-pilot>, release `v0.1.0`, commit `e27118d`.

The necessary local-portfolio closure was subsequently verified and published at CourseRAG commit
`f80cac0` and CoursePilot commit `90174af`. The existing public `v0.1.0` release remains available;
the closure commits advance `main` without rewriting that release tag.

P18 was not re-run or tuned. Its execution status remains complete and its formal quality Gate
remains failed. Both READMEs label the artifacts as portfolio/engineering MVPs and disclose the
quality and automatic prompt-injection-classifier limitations.

## Architecture delivered

- CourseRAG owns its FastAPI app factory, settings, SQLAlchemy session, domain/application code,
  clean Alembic baseline and PostgreSQL schema `courserag`.
- CoursePilot owns schema `coursepilot`, its own clean Alembic baseline, and vendored versioned HTTP
  wire contracts. Its production code does not import the CourseRAG Python package or mount
  CourseRAG server routes.
- CoursePilot defaults to the remote CourseRAG boundary in the public deployment. The sibling
  Compose demo starts both services and one PostgreSQL database; the schemas and Alembic version
  tables remain independent.
- The public demo uses one local database login for ease of startup. Separate database roles are a
  production-deployment hardening item; this does not create an application-level cross-service
  call path.
- Each repository retains MIT licensing, upstream attribution, provenance, `.env.example`, a
  deterministic no-paid-provider demo mode, and its own CI workflow.
- The CoursePilot default server install no longer pulls Chroma or Streamlit. Both are explicit
  optional extras; the legacy in-process RAG path is disabled unless the operator opts in.

## Verification

CourseRAG final local results:

- Pytest: `199 passed, 2 skipped`;
- Ruff Format/Check: passed;
- Mypy: `148` source files passed;
- Alembic: `0001_courserag_clean_baseline (head)`;
- Git diff check: passed;
- public GitHub Actions for `f80cac0`: passed,
  <https://github.com/meo0306/course-rag/actions/runs/32931478320>.

CoursePilot final local results:

- Pytest: `258 passed, 8 skipped`;
- Ruff Format/Check: passed;
- Mypy: `214` default-runtime source files passed; the optional Streamlit UI is excluded from the
  default-runtime type target;
- Alembic: `0001_coursepilot_clean_baseline (head)`;
- Git diff check: passed;
- public GitHub Actions for `90174af`: passed,
  <https://github.com/meo0306/course-pilot/actions/runs/32931535620>.

Both clean migrations were applied to the same local PostgreSQL database. The resulting logical
ownership was `51` CourseRAG tables in `courserag` and `22` CoursePilot tables in `coursepilot`.
Template definitions now use line-ending-normalized text hashes, so Windows and Linux checkouts
resolve the same snapshot identity; binary DOCX/PPTX resources continue to use raw byte hashes.

On 2026-08-26 the local portfolio Compose was rebuilt from the two clean repositories and verified
end to end. PostgreSQL, CourseRAG and CoursePilot were all healthy; schemas `courserag` and
`coursepilot` existed; `scripts/demo_local.py` created an idempotent course, completed a lesson task
through the remote CourseRAG HTTP boundary, and returned a lesson artifact with zero paid Provider
calls. The local machine's existing port 5432 was not disturbed because demo PostgreSQL is exposed
only to the Compose network. GHCR publication is intentionally not a portfolio Gate: the supported
demonstration target is a local Docker build from the two public source repositories.

## P19 task closure

- Physical split and clean histories: completed.
- HTTP-only CoursePilot-to-CourseRAG production boundary: completed.
- Shared PostgreSQL with dual schemas and independent migration histories: completed.
- Public CI, releases, README, licensing and provenance: completed.
- Local Docker cold-build, health checks, dual-schema verification and deterministic journey:
  completed.
- Architecture, local-demo, legacy-deprecation and interview deep-dive documentation: completed.
- P18 truthful portfolio disposition: completed; failed formal quality metrics remain visible.

## Remaining limitations

- This is not a production security certification or a claim that P18 quality passed.
- The P18 formal CourseRAG Test Index was not reconstructed; seven Track-B journeys remain blocked
  in that immutable release.
- The automatic prompt-injection classifier remains rejected/default-off; ACL, course scope, tool
  denial, Secret isolation and idempotent side-effect controls remain the enforced boundaries.
- The demo database login is shared even though schemas and migration histories are separate.
- Image distribution is source-build/local only; GHCR publication is optional backlog work.
- P15 semantic diversity and P14/P16 content-quality debts remain backlog items, not release blockers.

## Exit Gate

P19 portfolio release Gate: **passed**. Both public repositories and `v0.1.0` releases exist, both
CI workflows pass from clean Linux checkouts, runtime package coupling is removed, dual-schema
persistence is operational, and public claims preserve the failed P18 Gate. No production-readiness
or positive formal-quality claim is made.
