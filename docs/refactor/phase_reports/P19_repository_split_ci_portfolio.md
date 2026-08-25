# P19 Repository Split, CI and Portfolio Release

## Status

P19 is in progress under the Course Owner-approved portfolio disposition. The target is two public
repositories, `meo0306/course-rag` and `meo0306/course-pilot`, created from a clean monorepo source
checkpoint. They will share one PostgreSQL instance while using independent schemas, roles and
Alembic histories.

P18 evaluation execution is complete but its formal quality Gate remains failed. P19 may package
verified engineering capabilities and disclose limitations; it may not represent P18 as passed or
as a production release.

## Planned evidence

- clean-checkout Unit/Contract/Integration tests in each repository;
- CoursePilot-to-CourseRAG HTTP contract validation without Python package imports;
- PostgreSQL schema ownership and cross-role denial checks;
- Docker cold-start and one evidence-to-lesson-to-writeback demo journey;
- Secret, large-file, license and upstream-attribution review;
- public README, architecture diagrams, interview notes and `v0.1.0` releases.
