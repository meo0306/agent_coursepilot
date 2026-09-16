# CourseRAG architecture

```mermaid
flowchart LR
    CP[CoursePilot / HTTP client] --> API[FastAPI v1 contract]
    API --> APP[Application services]
    APP --> PG[(PostgreSQL: courserag schema)]
    APP --> PARSE[PDF/DOCX + OCR]
    PARSE --> EV[Stable Evidence / Chunk / KP]
    EV --> IDX[Dense + BM25 indexes]
    IDX --> RRF[RRF + optional reranker]
    RRF --> CTX[Evidence-aware context packing]
    CTX --> QA[Claim-evidence QA]
    APP --> OV[Teacher-verified overlay]
```

## Boundary

PostgreSQL is the business fact source. Vector indexes and caches are rebuildable. CoursePilot
does not import these implementations; it communicates through the versioned HTTP contract.

## Local portfolio mode

`COURSERAG_RUNTIME_MODE=demo` uses labelled deterministic evidence so the public demo can run
without redistributing textbooks, model weights, private evaluation data, or paid credentials.
It demonstrates the contract and trace path, not retrieval quality.
