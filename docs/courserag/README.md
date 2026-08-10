# CourseRAG

CourseRAG is the versioned retrieval and evidence subsystem used by CoursePilot. PostgreSQL is the business source of truth; parser artifacts, dense/sparse indexes, caches, and traces are derived and replaceable.

The P03–P10 implementation provides:

- immutable document versions and resumable build stages;
- canonical PDF/DOCX parsing, page-level OCR, stable Evidence, and parent/child chunks;
- reviewable course-level knowledge-point assets;
- versioned dense + BM25 retrieval, RRF fusion, dedicated reranking, evidence-aware context packing, and claim–citation QA;
- section-level impact planning, citation migration, verified-content overlay indexing, revocation, and enrichment batches;
- trusted-principal course isolation and bounded document-security checks.

## Runtime boundary

CoursePilot depends on CourseRAG through the frozen Port/DTO contracts under `src/courserag/contracts/`. CoursePilot code must not import parser, chunker, Chroma, BM25, or provider internals.

The default compatibility mode remains `COURSERAG_RETRIEVAL_BACKEND=legacy`. Versioned CourseRAG is fail-closed: missing active indexes, profiles, trusted identity headers, embedding configuration, or provider configuration do not silently fall back to legacy behavior.

## Data and index ownership

```text
PostgreSQL facts
  -> immutable DocumentVersion / Evidence / Chunk / KP / VerifiedContent
  -> content-addressed artifacts and build-stage cache
  -> Primary Index active pointer
  -> independent Teacher-Verified Overlay active pointer
  -> request fixes both versions in trace
```

Primary source content is never overwritten by verified write-back. Revocation publishes a new overlay version and preserves the immutable content and audit facts.

## Documentation

- [API v1](API_v1.md)
- [Architecture](ARCHITECTURE.md)
- [Security, deployment, and limits](SECURITY_AND_LIMITS.md)

The current refactor execution and quality status remains authoritative in `docs/refactor/EXECUTION_STATUS.md` and the P10 phase report. P10 formal Test remains unavailable until its frozen manifest and external-call budget receive separate owner approval.
