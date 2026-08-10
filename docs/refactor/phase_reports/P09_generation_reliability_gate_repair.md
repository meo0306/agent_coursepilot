# P09 Generation Reliability Freeze Gate Repair Report

## 1. Repair motivation and observed problem

The owner-approved Claim-Citation evaluation established strong formal Citation quality
(`Precision=0.9600`, `Recall=0.8034`, `F1=0.8748`), but the independent Freeze guards still
failed. Q3 retained one visible QA schema failure and its factoid short-answer Token F1 was below
the fixed Q2 reference. Freezing that profile would therefore have hidden a generation-reliability
defect behind good Citation metrics.

The concrete original failure was a long occupational list. The Provider had to repeat long stable
Evidence IDs for every item inside a bounded JSON response. That made the structured payload large
and brittle: a response could be semantically useful yet fail schema validation or be truncated.
At the same time, several factoid Gold cases were routed through a broad list contract, producing
answers that contained relevant material but were too expansive for the requested answer shape.

This was not treated as an isolated metric patch. The repair was preregistered as a joint
reliability experiment with two non-negotiable protection axes:

- structured generation must have zero QA failures and retain fully cited list items;
- short-answer quality must not fall more than `0.02` below the fixed Q2 baseline.

## 2. Root-cause hypothesis

The first hypothesis had two parts. First, transmitting full Evidence IDs inside every generated
list item consumed output budget without adding semantic value. Short local aliases could reduce
JSON transport pressure while preserving exact Evidence identity through deterministic restoration.
Second, a task-factoid contract and a concise list summary could keep the user-visible answer closer
to the requested granularity while retaining a complete structured item list for downstream use.

The repair intentionally did not change retrieval, reranking, Context selection, Gold, Test data,
the Citation Composer or the frozen formal scoring contract. This isolation made it possible to
attribute changes to generation shape rather than another coupled subsystem.

## 3. Proposed and implemented solution

The candidate introduced an explicitly gated generation-reliability contract:

- Context Evidence IDs are mapped to compact local aliases only inside the Provider request;
- the validated response restores aliases to full stable Evidence IDs before service validation;
- list output receives a `3,200`-token ceiling and must contain a concise summary plus complete,
  individually cited `list_items`;
- an explicit task-factoid rule requests one self-contained sentence;
- invalid JSON, unknown aliases, incomplete list structure and invalid citations fail closed;
- the one allowed Repair receives only a safe error code and never the full validation payload;
- finish reason, output limit, usage and response hashes are retained as non-secret diagnostics.

The candidate is disabled by default. Only the evaluation runner enables it. No public API,
database migration, retrieval behavior, Gold record or runtime default was changed.

The exact preregistration identities were:

- Protocol Manifest SHA-256:
  `52e32dbb193cba141084f7006cb7477c72d3c50349536236e73867b55b71310f`;
- Candidate Profile SHA-256:
  `8b2c7b37964c146b50eb2878028ea881be5b9e47bbc364c364dcc0eac779bfc7`;
- fixed Answer Grounding source Report SHA-256:
  `b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b`;
- fixed B7 Retrieval Snapshot SHA-256: `d85d9603...`;
- fixed formal Claim-Citation Report SHA-256:
  `652d2a08dcd1c7b175002fc5f4d32ec1beb71bbc2991a81b6a6175c746a9c392`.

The protocol allowed exactly 12 Approved Dev delta cases, no Test access, no Cohere calls, no
post-result tuning and at most 180,000 additional DeepSeek tokens. The unchanged other 48 Q3 cases
were reused by exact Hash rather than regenerated.

## 4. Real-run result

The resumed exact run completed all 12 fresh cases. It used 82,552 DeepSeek tokens, taking the P09
cumulative total from 824,734 to 907,286 of the 2,500,000 phase cap. Cohere usage was zero.

Artifacts:

- run Report SHA-256:
  `fc7b0bbe284e36d7abf5545dd2963762c6717c26383f346b8fdaf896b448045f`;
- Checkpoint SHA-256:
  `0da50dcf06b998e37164e99a1c238b05b799d81d5cf7a9e7ef3fe959c991f9e2`;
- automatic Gate Report SHA-256:
  `a3f387973d669dedbfc83467857b11889ee93178d2ca9daed4607cbc0515c4b2`;
- automatic Gate status: `failed_no_further_tuning`;
- Test access: false; fallback count: zero; false-answer rate: zero;
  unanswerable recall: `1.0`; Citation resolvability and Claim-Citation completeness: `1.0`.

The original long occupational-list transport failure was fixed. The Provider returned valid JSON
with a summary, 36 structured items and 36 cited Claims, `finish_reason=stop`, and no Repair. This
confirms that short aliases and the larger shape-specific budget solved the original output-size and
schema-transport problem.

However, the joint Freeze Gate still failed:

| Guard | Fixed reference / requirement | Candidate result | Outcome |
|---|---:|---:|---|
| QA failure rate | `0` | `1/54 = 0.0185185` | failed |
| Factoid short-answer Token F1 | at least `0.426108 - 0.02 = 0.406108` | `0.360260` | failed |
| Structured list completion | all approved list cases answered with cited items | satisfied | passed |
| Citation resolvability | `1.0` | `1.0` | passed |
| Claim-Citation completeness | `1.0` | `1.0` | passed |

The single failure moved to the ERNIE task-factoid case
`gold-qa-f6ec6bb28fa466f2958eb45ee887480e`. Generation and the one directed Repair both returned
`SCHEMA_VALIDATION_FAILED` despite `finish_reason=stop`; each output was about 90 tokens under a
600-token limit. This rules out truncation and points to Provider schema compliance in the new
task-factoid path. Because raw Provider content is deliberately not retained, the exact invalid
field cannot be reconstructed without a new, separately approved diagnostic protocol.

Short-answer F1 improved over the earlier Q3 value (`0.334885 -> 0.360260`) but remained below the
protection floor. Several factoid cases still followed a list-oriented route and produced broader
summaries than their Gold answer granularity. The two formal list cases also remained at List Set
F1 `0.0`: the system returned many atomic details (for example 36 occupational items) while Gold
used fewer grouped semantic items. The repair therefore fixed transport completeness but did not
solve semantic grouping.

## 5. Why the candidate is rejected

The result demonstrates why coupled metrics cannot be repaired by repeatedly optimizing whichever
number is currently lowest. Increasing output capacity and list completeness fixed one failure, but
the generic shape change exposed a different schema failure and did not restore factoid precision.
Treating that as success would trade reliability across answer types and create a profile that is
hard to reason about.

Per the preregistered stopping rule, no Prompt was tuned after seeing the result, no second candidate
was run, no human delta-review package or Freeze Candidate was generated, and no threshold was
relaxed. The candidate remains off by default and P09 remains Gate-failed.

## 6. Compatibility, safety and rollback

- No database, ORM, Alembic, public API, retrieval/index, Context, Gold or Test change was made.
- The candidate is reachable only through an explicit evaluation flag; normal construction keeps
  the v3 contract and previous output limits.
- No partial answer is returned when validation fails; the failure remains visible and auditable.
- Secrets, raw Provider responses and full validation payloads are not written to reports.
- Rollback is configuration-level: leave the candidate flag disabled. No data rollback is needed.

## 7. Engineering lesson for project deep-dive interviews

The important lesson is the separation of transport reliability, semantic granularity and formal
grounding. A structured-output failure can originate in response size, schema compliance or answer
shape, and improving one axis does not prove the others. We therefore froze retrieval and Context,
preregistered a small Dev delta, defined primary and protection metrics before the call, preserved
exact hashes and stopped when the combined Gate failed. The experiment produced useful causal
evidence—the alias design fixed the original long-list failure—but the architecture was not frozen
because system-level reliability, not local metric movement, is the acceptance criterion.

Any next attempt needs a new owner-approved plan. It should address answer-type routing and semantic
grouping together, add privacy-safe schema-failure observability, and retain the same zero-failure,
factoid-protection, Citation and no-Test guards rather than iterating on this failed candidate.

## 8. Final verification

- `uv sync --frozen`: passed; the optional local CUDA Embedding extra was removed as expected by
  the base lock profile, while the completed formal artifacts remained intact;
- Generation Reliability focused suite: 18 passed;
- full regression: 505 passed, five explicit gated skips;
- owner PDF/DOCX B0 Smoke: one passed;
- `ruff format --check`: 462 files already formatted;
- `ruff check`: passed;
- `mypy src/`: zero issues in 314 source files;
- JSON Schema verification: 60 schemas verified;
- Alembic: sole head `0014_query_context_qa`;
- `git diff --check`: passed; only existing Windows LF/CRLF notices were emitted;
- `.env` is ignored and untracked; `.env.example` API-key fields are empty and Settings use
  `SecretStr | None` defaults;
- no Generation Reliability temporary file, live runner process, silent fallback, Test access or
  destructive migration was found.

These engineering checks pass. The measured Candidate Profile Gate remains failed and the Candidate
is not frozen, but the owner-approved governance decision below separates that Profile result from
the frozen P09 phase Exit Gate.

## 9. Owner-approved dual-layer Gate classification

The frozen roadmap defines the P09 Exit Gate as three core contracts, not as the later candidate
Profile protection thresholds:

| Frozen P09 Exit Gate | Evidence | Result |
|---|---|---|
| every Query Processing step is ablatable | independent toggle/trace tests and disabled-step state | passed |
| every QA Claim binds valid Evidence | Citation resolvability and Claim-Citation completeness `1.0` | passed |
| unanswerable samples are correctly rejected | six of six main-Dev cases rejected; false-answer rate zero | passed |

The owner therefore approved status `completed_with_quality_debt / passed_core_contracts` and made
P10 ready to start. This does not retroactively pass the Generation Reliability Candidate, relax
its thresholds or create `default_v1`. Candidate `8b2c7b37...` remains rejected and default-off.

The one QA failure, factoid F1 `0.360260`, List Set F1 zero, intent accuracy `0.3958` and B8 Evidence
coverage `0.7130` are carried into P10 as explicit quality debt. P10 must preserve zero false
answers, full Citation integrity, correct abstention, no silent fallback and no Test leakage. Any
final Dev calibration must be separately preregistered, bounded to one candidate and completed
before Test is locked and run. This reclassification itself made no code change or Provider call.
