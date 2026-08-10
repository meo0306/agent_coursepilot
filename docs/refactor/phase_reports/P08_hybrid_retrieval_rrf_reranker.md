# P08 Hybrid Retrieval, RRF and Dedicated Reranker Report

## Phase verdict

- Implementation: P08-T01 through T08 are implemented. Formal Dev B3/B4/B5 completed twice with a
  frozen local Qwen3 Embedding snapshot; all four system result Hashes reproduce and cache replay
  makes zero external Provider requests.
- Exit Gate: **passed**. The owner approved exact Candidate `5b5d973e...`, Cohere
  `rerank-v4.0-pro` and threshold `0.7502601`; checked `default_v1` SHA is `dc4109b1...`.
- Start/end Git commit: `b6483f5ae8a0b3c3e45858c3872b4ed86e94502d` / uncommitted at the
  same commit; branch `refactor/p00-baseline`.
- Scope protection: no commit, push, PR, Test access, P09 work, legacy Collection deletion,
  Provider fallback, LLM judge or Gold rewrite.

## Task results

| Task | Result | Evidence |
|---|---|---|
| P08-T01 | completed | independent Embedding/Dense ports, versioned Chroma, Repository hydration and frozen local SentenceTransformers Adapter with full bundle/weights verification |
| P08-T02 | completed | BM25S matrix/mapping persistence, jieba search tokens, NFKC protected English/numeric/special terms and explicit CJK bigram zero-term fallback |
| P08-T03 | completed | equal/optional weighted RRF, `k=60`, source deduplication, stable Chunk-ID tie-break and complete stage Rank/Score preservation |
| P08-T04 | completed_implementation | shared Jina/Cohere/Voyage HTTP contract, fail-closed optional local CrossEncoder and explicit disabled mode |
| P08-T05 | completed | Candidate-K/Top-N, batch/listwise request, truncation, timeout, transient retry, order-sensitive cache, production warning fallback, evaluation fail-sample and three hard budgets |
| P08-T06 | completed | Course, Document, DocumentVersion, Section, KP, SourceTier and IndexVersion isolation |
| P08-T07 | completed_gate_passed | two 54-Dev result sets reproduce; owner-approved Cohere/threshold are frozen in checked `default_v1` |
| P08-T08 | completed | additive public Rank/Trace fields and complete RetrievalRun request/config/result Hash, stage latency, usage, fallback and warning facts |

## Changed files

### Retrieval, indexing and Providers

- `src/courserag/retrieval/`
- `src/courserag/indexing/dense.py`
- `src/courserag/indexing/sparse.py`
- `src/courserag/indexing/manifests.py`
- `src/courserag/indexing/version_manager.py`
- `src/courserag/providers/reranker.py`
- `resources/retrieval_profiles/`

### Contract, persistence and compatibility

- `src/courserag/contracts/retrieval.py`
- `src/courserag/persistence/models/document.py`
- `src/courserag/persistence/models/run.py`
- `src/courserag/persistence/models/__init__.py`
- `src/courserag/persistence/repositories.py`
- `alembic/versions/2026_08_07_0013-hybrid-retrieval.py`
- `src/coursepilot/adapters/local_courserag.py`
- `src/coursepilot/services/courserag_runtime.py`
- `src/core/settings.py`
- `.env.example`
- `pyproject.toml`, `uv.lock`

### Evaluation and tests

- `src/courserag/evals/p08_metrics.py`
- `src/evaluation/p08_corpus.py`
- `src/evaluation/p08_embedding_diagnostic.py`
- `src/evaluation/p08_systems.py`
- `src/evaluation/p08_retrieval_eval.py`
- `tests/courserag/retrieval/`
- `tests/courserag/indexing/`
- `tests/courserag/test_p08_migrations.py`
- `tests/evals/test_p08_retrieval_eval.py`
- revision-boundary update in `tests/courserag/test_p03_migrations.py`

## Database, API and configuration

Revision 0013 is additive. It adds SourceTier to SourceDocument; IndexVersion-to-Chunk N:N with
stable ordinal; complete RetrievalRun identity, stage timing, usage/cost, fallback, warnings and
Debug Trace; and an identity-keyed Rerank Cache. `0012 -> 0013 -> 0012 -> 0013` passes while an
existing SourceDocument survives. Downgrade removes P08 facts and therefore remains an explicit
operator action after writes stop and audit/report artifacts are retained.

Search filters add optional DocumentVersion, KP and IndexVersion fields. Search hits add an
optional Rank breakdown, while Trace adds Run/Provider/Model/Manifest/stage/usage/fallback fields.
Defaults preserve old Remote/Mock/Local decoding. `COURSERAG_RETRIEVAL_BACKEND=legacy` remains
default; explicit `versioned` without a valid Active Index returns `INDEX_NOT_READY` and never
falls back to old Chroma.

Provider/model/endpoint and Embedding values are configuration-only. `.env.example` has blank
Secret fields. Jina and Cohere use their separate configured fields from ignored `.env`; Secrets
never enter cache keys, Manifests, reports or errors. Formal limits are Jina 8M tokens, Cohere 500
Search Units/requests and Embedding 500k estimated input tokens.

## Local Embedding deployment

`Qwen/Qwen3-Embedding-0.6B` was downloaded with the ModelScope CLI to
`D:\AI\models\modelscope\Qwen\Qwen3-Embedding-0.6B`. The snapshot contains 13 files and
1,207,489,671 bytes. Profile `resources/retrieval_profiles/qwen3_embedding_0_6b_local_v1.json`
records every file Hash, complete bundle SHA-256
`1db2c971796b1b286f6b73a22ee05c213a51211fdb595640cc361c1b790c9920`, and weights SHA-256
`0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd`. The Adapter rejects any
snapshot/tokenizer/config/weights drift and symbolic links before loading.

Runtime is an explicit `local-embedding-cu126` extra: PyTorch 2.12.1+cu126,
sentence-transformers 5.7.0 and transformers 5.14.1. It uses local-only loading, CUDA BF16/SDPA,
1,024 dimensions, maximum length 2,048, batch size 8, normalized embeddings, no document prompt
and query prompt `query`. The exact 2,620,768,231-byte PyTorch wheel is retained at
`D:\AI\wheels\pytorch-cu126`; its uv-lock SHA-256 is `71ee0eca...36aa1` for offline recovery.

Benchmark report `storage_eval/p08_local_embedding/benchmark.json` has SHA-256
`c458a3515b745548b15e04aa9f80f67f7d34a437b5e85b933d1ecae14252a9c0`. On this RTX 4060 Laptop
8GB/20-logical-CPU system: cold load is 23.38s; steady process RSS is 1.37-1.41 GiB; PyTorch
reserved VRAM is 1.13-1.28 GiB; one query is 91.8ms; batch 8 reaches 123.44 items/s. GPU peaks at
78%, process CPU peaks around one logical core (4.99% of the full 20-thread machine), and measured
GPU power peaks at 30.73W.

## Formal evaluation

The corpus Adapter reads the retained P06 run-4 Child Chunks, resolves their system Evidence back
to Approved DS2 through the existing text/span adapter, and derives Course identity from the
approved P08 Source Packages. It does not treat Chunk IDs as Gold. The Runner verifies exact r3
Bundle `ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396`, loads exactly 54
`retrieval_main` Dev cases and rejects Test/diagnostic IDs.

Metrics include Hit/Recall/Precision@5/@10, MRR@10, nDCG@10 with unique-Evidence gain,
Complete Evidence Group Recall@5/@8/@10, hard-negative intrusion, Provider-specific rejection
curves, stage P50/P95, requests/tokens/Search Units, cache hits, warnings and fallback counts.

| System | Hit@5 | Recall@10 | MRR@10 | nDCG@10 | Complete Group Recall@8 | Hard-negative intrusion@10 |
|---|---:|---:|---:|---:|---:|---:|
| B3 Dense | 0.6852 | 0.7932 | 0.4851 | 0.6368 | 0.7315 | 0.6296 |
| B4 Hybrid RRF | 0.7222 | 0.8302 | 0.5432 | 0.6808 | 0.7870 | 0.6667 |
| B5 Jina | 0.6852 | 0.7593 | 0.5537 | 0.6664 | 0.7130 | 0.4259 |
| B5 Cohere | 0.7963 | 0.8858 | 0.7384 | 0.8259 | 0.8426 | 0.6111 |

Run 1 report SHA-256 is `1e9f3ff7...`; Jina used 224,207 tokens in 66 requests with rerank P95
4,518ms, while Cohere used 54 Search Units in 56 requests with P95 19,486ms. Both had zero
Fallback and zero warnings. Run 2 report SHA-256 is `4e0baf7e...`; it reproduced every system
result Hash and used 54 cache hits per Reranker with zero Provider requests, Fallbacks or warnings.
Exact Freeze Candidate SHA-256 is
`5b5d973ebf70d32cc10fa0ad4103261eee745dc4604f9e9f1a693817d3c3c95f`. The owner selected Cohere
`rerank-v4.0-pro` and threshold `0.7502601`; `default_v1.json` SHA-256 is
`dc4109b16fb0bdfda8b226ca7f66adeb6a8b833b9a213eecea36adb1e1afcb3d`.

## Verification

| Command/check | Result |
|---|---|
| `uv sync --frozen` | passed for the base environment |
| `uv sync --frozen --extra local-embedding-cu126 --offline` | passed after seeding the exact uv-lock wheel; 10 optional packages installed |
| P08 retrieval/indexing/migration/contracts/eval focused | 63 passed |
| 0013 migration | 1 passed |
| Local/Remote/Mock contracts | 27 passed |
| P08 Runner + Approved r3 data gate | passed; 54 Dev only, Test rejected |
| user PDF/DOCX B0 Smoke | 1 passed |
| final full `pytest -q` | 446 passed, 5 gated skips, 6 dependency warnings |
| `ruff format --check` | 409 files formatted |
| `uv run ruff check` | passed |
| `mypy src/` | 0 errors in 283 source files |
| `uv run alembic heads` | `0013_hybrid_retrieval (head)` |
| `git diff --check` | passed; Windows LF/CRLF notices only |
| Secret/temporary check | `.env.example` has no non-empty Secret-like value; no new `*.tmp/*.bak/*.orig` found |
| local GPU probe | CUDA 12.6 available; 1,024 dimensions; norm 0.999669; identity `5b7458e1...` |

The first full run stopped during collection because the new test filename duplicated the existing
service test module name; the file was renamed without product change. The next full run found one
expected revision-boundary assertion: the P03 migration test did not yet exclude P08 tables/columns.
After explicitly adding the P08 boundary, its two-test repair passed and the clean full run passed.

## Risks and rollback

- External ModelScope moderation instability is removed from the formal path by the frozen local
  snapshot. Bundle/weights are verified before load and `local_files_only=True` prevents runtime
  downloads. Secrets remain only in ignored `.env` and never entered logs or artifacts.
- Reranker absolute scores are Provider-specific. Freeze tooling stores separate rejection curves
  and never creates a cross-Provider threshold.
- The production-only Fusion-order fallback always emits a stable warning; formal evaluation is
  fail-sample and has no fallback.
- Rollback runtime by keeping Backend `legacy` or setting Reranker `disabled`. Existing Active
  Indexes, legacy Chroma Collections, old tables and Approved Gold are untouched.
- Downgrade 0013 only after P08 writes stop and reports/cache audit are retained.

## Exit Gate

| Gate | Result | Evidence |
|---|---|---|
| Hybrid and Rerank are independently ablatable | passed | real B3/B4/B5 composition plus RRF and Provider contract tests |
| Formal Eval failure does not silently fall back | passed | both real B5 candidates completed under `fail_sample` with zero fallback/warnings |
| Index version matches query results | passed | fixed local model identity, Active pointer pin, v2 Manifest/PostgreSQL Chunk-set validation, filter and migration tests |
| Required P08-T07 real comparison | passed | two 54-Dev reports reproduce every system result Hash |
| Owner Freeze | passed | Cohere/threshold approved against exact Candidate; checked `default_v1` retained |

Overall P08 Exit Gate: **passed**. P09 meets its start prerequisite but has not been started.
