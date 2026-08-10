# CourseRAG architecture

## Layering

```text
CoursePilot / HTTP API
        |
        v
CourseRAG contracts and application services
        |
        +--> repositories --> PostgreSQL facts
        +--> jobs/stages --> content-addressed artifacts
        +--> indexing --> Primary + Verified Overlay versions
        +--> providers --> embedding/reranking/structured generation
```

Domain and application code depend on ports, not SQLAlchemy sessions or provider SDKs. Infrastructure adapters implement persistence, indexes, files, and HTTP providers. CoursePilot sees only the public contracts.

## Incremental build

Section matching checks stable path and content hash first, then unique content moves, same-path edits, and unique structural matches. Ambiguous matches are conservatively reprocessed. Profile changes expand the impact scope: parser/OCR changes invalidate the full document, chunk changes preserve Evidence but rebuild chunks/indexes, KP changes rerun affected windows, embedding changes rebuild vectors, and reranker changes do not rebuild the index.

Artifact reuse is accepted only when the planned artifact hash exists and verifies. A cache miss or mismatch is reported; it is never silently counted as reuse. Change coverage must remain 100% before reuse ratio is meaningful.

## Citation migration

Migration resolves in this order:

1. still-valid Evidence;
2. unique content hash and structural anchor;
3. section path, normalized text, and neighborhood;
4. unique high-similarity candidate;
5. explicit `needs_review` for ambiguity;
6. `invalid` for deleted, unresolvable sources.

Every result records source and target versions, candidates, method, score, profile hash, and final state. Chunk IDs are not permanent citations.

## Verified overlay

```text
Primary Active Index ----------------------+
                                            +--> fused retrieval result + dual-version trace
Teacher-Verified Overlay Active Index -----+
```

The overlay has its own immutable versions, manifest, artifacts, and active pointer. A verified write builds and validates a candidate overlay before the database transaction exposes the new pointer. Revoke creates another overlay version without deleting content or changing the Primary index.

## Enrichment

Pending items become eligible when any threshold is reached: 10 records, 3,000 tokens, 24 hours, or manual owner/system action. Trigger priority is manual, record count, token count, then age. Batch identity is deterministic; row locking and item leases prevent duplicate side effects. Per-item failures remain retryable without reverting successful items or immediate retrieval.

## Evaluation boundary

Dev is the only calibration split. The P10 candidate is limited to the preregistered 12 affected P09 Dev cases and does not rerun retrieval. A frozen manifest must bind the code workspace, approved data, profiles, prompts, models, tokenizer, indexes, budgets, and fallback policy before Test can be locked. Formal Test results cannot tune this release.
