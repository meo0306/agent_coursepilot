# CourseRAG v1 API

The stable CourseRAG HTTP prefix is `/api/courserag/v1`. Requests retain the common request/trace context contract and return structured errors. All routes below require the service Bearer credential and trusted gateway identity headers.

## Trusted identity headers

| Header | Meaning |
|---|---|
| `X-CoursePilot-Principal-ID` | Authenticated principal identifier |
| `X-CoursePilot-Course-ID` | Course authorized by the gateway |
| `X-CoursePilot-Roles` | Comma-separated `reader`, `editor`, `owner`, or `system` roles |

The course in the path, body, trusted header, and stored entity must agree. Identity-like fields supplied in a request body never grant access.

## Retrieval and QA

| Method and path | Minimum role | Purpose |
|---|---|---|
| `POST /knowledge-bases/{course_id}/search` | `reader` | Version-fixed hybrid retrieval with rank/score trace |
| `POST /knowledge-bases/{course_id}/contexts` | `reader` | Evidence-aware context package and citation map |
| `POST /knowledge-bases/{course_id}/qa` | `reader` | Structured answer claims bound to context Evidence |

These endpoints fail closed in versioned mode if the active index or required provider/profile is unavailable. Formal evaluation does not permit silent provider fallback.

## Verified content

| Method and path | Minimum role | Purpose |
|---|---|---|
| `POST /knowledge-bases/{course_id}/verified-content` | `editor` | Write a whitelisted, approved item and publish the verified overlay atomically |
| `POST /verified-content/{content_id}/revoke` | `owner` | Revoke retrieval visibility through a new overlay version |
| `POST /knowledge-bases/{course_id}/enrichment-batches` | `owner` | Manually request an enrichment batch |

Whitelisted write types are `verified_question`, `verified_answer_explanation`, and `verified_lesson_fragment`. A write must include stable Evidence IDs, approval identity, task identity, and an idempotency key in the request context. The same key and request hash replay the original result; changed content with the same key returns `IDEMPOTENCY_CONFLICT`.

Writes use a separate `teacher_verified` overlay. Database facts and the new active overlay pointer are committed only after the candidate manifest and artifacts validate. A publish failure leaves both the previous overlay and the Primary index unchanged.

## CoursePilot compatibility endpoint

`POST /api/coursepilot/reviews/{review_id}/write-back` retains its response shape. Approved question content can map to verified question/answer fragments when stable Evidence is present. Whole lesson and PPT artifacts return `requires_fragment_selection`; legacy chunk-only references return `requires_evidence_migration`. Neither state writes to an index.

Citation migration and incremental planning are internal Application/Build Ports in P10 and are not exposed as unfrozen public HTTP endpoints.
