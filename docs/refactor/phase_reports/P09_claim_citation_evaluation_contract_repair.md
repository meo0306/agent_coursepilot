# P09 Claim-Citation Evaluation Contract Repair Report

## 1. Problem phenomenon

The fixed P09 Answer Grounding Dev run completed all 60 Cases, but Protocol r2 failed and produced
no Freeze Candidate. Its main-Dev automated Citation Precision/Recall/F1 were
`0.5168/0.6596/0.5508`. Repeated Citation Composer tuning had become unstable: 25 Cases changed,
zero improved under the proxy and nine became worse. Answer-shape tuning also increased explicit
lists where Gold expected short factoids, so one metric could rise while another fell.

## 2. Root-cause analysis

The metric implementation did not match the frozen contract. Frozen document 03 defines Citation
Precision at individual Claim-Citation links and Citation Recall at correctly cited Gold Claims,
requiring human support and Claim mapping judgements. The implementation instead intersected the
global set of output Evidence IDs with Gold Evidence IDs. This measures identity overlap, not
whether an Evidence directly supports its bound Claim.

The earlier Shadow Composer was more problematic: it constructed its candidate Evidence text only
from system Evidence that already mapped to Gold. Its higher score therefore included Gold-side
candidate filtering and cannot demonstrate a deployable runtime improvement.

Two related defects were confirmed. Formal Gold Claim Coverage counted only
`correct_supported`, incorrectly excluding a correctly expressed but uncited Claim. Automatic
Answerability treated choosing to answer as a true positive without checking Claim correctness.
Short Answer scoring also included two list Cases, while List Set used Claim strings instead of the
structured `list_items` field.

## 3. Repair design

The repair separates three namespaces: automatic structure checks, diagnostic Evidence-ID overlap,
and formal human Claim-Citation metrics. Evidence overlap is renamed and cannot satisfy a formal
Citation Gate. Gold Claim Coverage includes both correct-supported and correct-but-uncited matches;
the latter remains unsupported for precision/support metrics. Formal Answerability is derived only
after human Claim correctness is available.

Automatic answer metrics are type-scoped: nine factoid Cases receive EM/Token F1, two list Cases
receive normalized exact List Set metrics, and explanatory/comparison/procedure Cases rely on
human Claim scoring. Fixed Q2 and Q3 outputs must be recomputed under the same rule.

Human review uses two sequential local passes. Phase 1 shows the Query, fixed system Answer and
Claim, its actual cited Evidence, the stable resolved source Evidence and the remaining Context, but
hides Gold Claims. Phase 2 will expose Gold Claims only after the first decisions are submitted and
Hash-locked. No Provider or LLM-as-a-Judge is involved.

## 4. Phase-1 implementation result

The exact input identities are:

- Answer Grounding Report: `b04fc9b620fccddecaf889c201fa5b8d0cec139b92686a2ac354dffed853f77b`;
- Checkpoint: `2a53b2693592c6810781c05036a9110a39d72599b2c6c36b170bf12e48da4ccc`;
- Approved P09 Bundle: `5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1`.

The phase-1 package contains exactly 54 main-Dev Cases: 47 answered, six abstained and one failed;
150 system Claims, 150 Citation Links and 117 Required Gold Claims hidden from this pass. Report
`gold-ev_*` identities are resolved through a required unique adapter mapping to stable `ev1_*`
source Evidence; both identities are retained instead of pretending they are the same ID.

Generated artifacts:

- Package SHA-256: `ffde9da5545d6184d507128e1329300d334d136f0746e22231345dcb52e62281`;
- Repaired Review HTML SHA-256: `96b421e2ce7a526cd726954a1e76cc5f1885b4afd3c6bd8faf1817ade3a12796`;
- Decision template SHA-256: `1dba5ba77c0e0955f2500e74214a3836dab5afcad0760bdb75143f42f969d6f7`;
- Recovery exporter SHA-256: `6a0f10a079fa3f820130a29414af981a2c3027f6556434c5e4c7746d09945629`;
- Manifest SHA-256: `0c5e46a0ca517ca787e5c7ed2bffcc9b9a51287ee4030336370e6a3b53b7f6a5`.

Generation is byte-reproducible. Submitted decisions must bind the exact Package and contain every
Case, Answer, Claim and Citation identity once. Missing labels, incompatible support/Claim labels,
unknown IDs and inapplicable conciseness decisions fail closed.

## 5. Verification checkpoint

- focused review/formal-metric/Schema tests: 38 passed;
- full regression: 496 passed and five explicit gated skips;
- owner PDF/DOCX B0 Smoke: one passed;
- Ruff on touched files: passed;
- JSON Schema export: 60 Schemas verified;
- Mypy: zero issues in 313 source files;
- Provider calls: DeepSeek 0, Cohere 0, other 0;
- Test access: false;
- database/API/configuration/runtime behavior: unchanged.

The phase is intentionally paused for Course Owner phase-2 Gold Claim mapping. No formal Citation result,
Freeze Candidate or `default_v1` is generated at this checkpoint. P09 Gate remains pending and P10
remains blocked.

## 6. Human-review export incident and recovery

After completing the form, the Course Owner reported that the download button did nothing. The
generated inline JavaScript contained three Python-interpreted newline characters inside quoted
JavaScript strings, so the browser rejected the entire script before registering the click handler.
The form values themselves remained in the live page DOM and were not erased.

The exporter was moved into a separate `recovery_export.js` artifact with literal escaped newline
assertions and a syntax-load check. The repaired page loads this external script normally. An
already-filled old page can inject the same local script and invoke `recoverP09Decisions()` without
refreshing, preserving all completed selections. This incident does not alter the Package, Gold,
Claim identities or review decisions, but it is retained as a critical human-work-preservation
lesson.

## 7. Interview deep-dive summary

The important engineering lesson is that an evaluation metric is an executable contract, not just
a label. A set-overlap proxy can be useful for diagnosis, but calling it Citation Precision creates
Goodhart pressure: the system learns to select Gold-shaped IDs rather than support each Claim. The
repair therefore protects metric semantics with distinct names, immutable source Hashes, staged
human review, exact applicability sets and fail-closed identity reconciliation. It also prevents a
common offline-evaluation leak where a reranker or Composer only sees candidates already known to
map to Gold. The result is slower than another Prompt tweak, but it produces evidence that can
actually justify a production Freeze and a defensible technical explanation in an interview.

## 8. Phase 1 approval and Phase 2 Gold mapping checkpoint

The recovered Phase 1 Decisions were validated against every immutable Case, Answer, Claim and
Citation identity and then explicitly approved by the Course Owner at SHA-256
`52e0044ecc702e3ecc0cc9c0b3045a0f5a1f4c0aeaa95dc86f37c0a7b50ec314`. The decisions cover all
54 main-Dev Cases, 150 system Claims and 150 Citation Links. Their measured labels are 144
`correct_supported`, five `correct_but_uncited` and one `unsupported`; 144 links were judged to
support their bound Claim and six were judged not to support it. Conciseness passed for 45 answered
Cases and failed for two. These are human decisions over fixed outputs, not new model output.

The approval is frozen in `phase1_approval.json` with SHA-256
`1213567444943afeb32ed41df3c5164c3a021dd6429116ec44193ef28259110c`. This record unlocks a separate
Phase 2 Package with SHA-256 `0ad531262b39d660c580c7797712b395d6f21bfa8be5c48105df69d0c9f07ffb`.
The package contains the same 54 Cases and 150 system Claims, their locked Phase 1 labels, and 117
Approved Required Gold Claims with exact source-support excerpts. Invalid Phase 1 Claims cannot be
mapped to Gold, and the validator requires missed Gold IDs to be the exact complement of all valid
mappings. This prevents later coverage scoring from rewriting Phase 1 correctness judgments.

The Phase 2 review page SHA-256 is
`3585c9f7e25ec8f20e319cbbf9c2bc60280e6e5975bc38f3e93efe2448d8a717`; its external exporter is
`3a58fefc33e25486ec51d62184e783adc8fc39e1fb744ba6c7e76dd1eb5dc3ba`. The exporter uses the same
literal-newline regression guard added after the Phase 1 incident. Focused schema and review tests
now report 23 passed and 59 JSON Schemas are exported. No Provider was called, no Test record was
read, and no Gold, runtime, API, database or configuration behavior changed.

This checkpoint does not calculate formal Claim Coverage or Citation Precision/Recall/F1. Those
metrics remain blocked until the Course Owner submits and explicitly approves the exact Phase 2
decision Hash. Consequently P09 remains Gate-pending and P10 remains blocked.

## 9. Phase 2 approval and formal result

The Course Owner explicitly approved Phase 2 Decisions SHA-256
`85cb33ebdf2d26ab7360fda3d59738746de5bf1bae6a433a26120f1e146fcd58`. Validation confirmed all
54 Cases, 128 system-Claim-to-Gold mapping links, 99 covered Required Gold Claims and 18 missed
Required Gold Claims. Seventeen misses belong to the one fail-closed QA Case; the remaining miss is
an omitted fine-tuning definition in an otherwise answered cross-topic Case. No unsupported Claim
was mapped to Gold.

The deterministic Phase 2 Approval SHA-256 is
`87e61b5fe9a444d3bc22ce0d4a403a0031761fb46c38cb7fd350f9e77dc354b3`. The formal report uses the
frozen MVP correct-answer threshold of 0.5 Required Gold Claim Coverage and produces:

| Metric | Result |
|---|---:|
| Gold Claim Coverage | 0.8462 (99/117) |
| Correct Claim Precision | 0.9600 (144/150) |
| Unsupported Claim Rate | 0.0400 (6/150) |
| Contradictory / Irrelevant Claim Rate | 0 / 0 |
| Citation Claim Support Rate | 0.9600 |
| Citation Precision | 0.9600 (144/150) |
| Citation Recall | 0.8034 (94/117) |
| Citation F1 | 0.8748 |
| Claim-aware Answerability Precision / Recall / F1 | 1.0000 / 0.9792 / 0.9895 |
| False Answer / False Abstention Rate | 0 / 0.0208 |
| Answer Conciseness Pass Rate | 0.9574 (45/47) |

These results confirm that the earlier Evidence-ID overlap proxy substantially understated actual
Claim-level citation correctness. They also confirm that the system has strong grounding without
using Gold information at runtime: all labels come from the two owner-approved review passes over
fixed output, and formal scoring made zero Provider calls.

## 10. Why the Freeze Gate still fails

Formal Claim-Citation repair resolves the invalid metric contract, but it cannot erase independent
failures in the fixed generation output. Corrected automatic scoring applies Short Answer only to
nine factoid Cases and List Set only to two list Cases. Q2 factoid Token F1 is `0.4261`, while Q3 is
`0.3349`, a decline of approximately `0.0912` against the preregistered maximum decline of `0.02`.
Q3 also has one visible `QA_SCHEMA_REPAIR_FAILED`, so its QA failure rate is `0.0185` rather than
the preregistered zero requirement. List Set F1 is zero in both Q2 and Q3 and therefore passes only
the no-regression comparison, not an absolute quality claim.

Seventeen of nineteen Freeze checks pass. The failed checks are exactly
`qa_failure_rate_0` and `short_answer_token_f1_q2_delta`. Strong Citation metrics cannot compensate
for these orthogonal answer-generation failures without changing the approved evaluation contract
after observing the result. Consequently no Freeze Candidate or `default_v1` was written.

Final artifacts:

- Phase 2 Approval SHA-256: `87e61b5fe9a444d3bc22ce0d4a403a0031761fb46c38cb7fd350f9e77dc354b3`;
- Formal Report SHA-256: `652d2a08dcd1c7b175002fc5f4d32ec1beb71bbc2991a81b6a6175c746a9c392`;
- Formal Manifest SHA-256: `341c128784bee31c8eb558f3375b45d7a83e7092099c3f2aba881ff1cb0693ba`;
- Provider calls: zero; Test access: false; runtime default activation: false.

P09 Exit Gate is **failed on measured quality**, and P10 remains blocked. The next safe action is
not another unbounded Prompt tweak. It requires a separately approved, narrow candidate plan that
jointly handles factoid answer shape and the one long-list JSON failure while preserving the now
verified grounding, refusal and Citation behavior.
