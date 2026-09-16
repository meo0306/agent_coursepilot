# CourseRAG security, deployment, and limits

## Trusted gateway requirement

P10 uses a trusted-gateway claim boundary, not a complete IAM system. The public gateway must:

1. authenticate the caller and validate the service Bearer credential;
2. remove any client-supplied `X-CoursePilot-Principal-ID`, `X-CoursePilot-Course-ID`, and `X-CoursePilot-Roles` headers;
3. inject verified values after authentication;
4. prevent direct untrusted network access to the CourseRAG service.

If this boundary is not configured, versioned CourseRAG must remain unavailable. Body fields cannot override the trusted course or role. Read/search/context/QA require `reader+`, verified writes require `editor+`, and revoke/manual enrichment require `owner+`.

## Document admission policy

Security inspection runs before database or artifact writes. The default limits are:

| Control | Default |
|---|---:|
| Document bytes | 100 MiB |
| PDF pages | 2,000 |
| DOCX ZIP entries | 20,000 |
| DOCX uncompressed bytes | 512 MiB |
| DOCX compression ratio | 200 |
| OCR DPI | 600 |
| Parse timeout | 300 seconds |

Only PDF and DOCX are accepted. Declared MIME, file extension context, and magic bytes must agree. Encrypted PDFs, filename/ZIP path traversal, malformed archives, excessive page counts, decompression bombs, excessive DPI, and timeouts fail closed. Prompt-injection-like source text is preserved as source data and marked; it is never executed as instruction.

Known formal-Test limitation (P10, 2026-08-11): the consumed release scanned raw document bytes
and did not recognize one English policy-override paraphrase. The source remained inert and caused
no database, artifact, external-call, or tool side effect, but the required warning was absent.

P10.1 moves semantic marking after PDF/DOCX parsing and OCR merge. The deterministic v2 scanner
normalizes Unicode, zero-width characters and whitespace; detects policy override, role
impersonation, secret extraction, tool coercion and light obfuscation in Chinese and English; and
binds each finding to Page, Block and character Span. Original source text remains unchanged.
Warnings propagate to Evidence and Chunk audit metadata but do not change stable semantic IDs.
Missing or invalid Security Profiles fail closed. This implementation has passed its 30-case Dev
gate, but it is not yet a frozen CoursePilot dependency: an independently constructed and
Course-Owner-locked 12-case blind Test must still pass once without tuning feedback.

P10.2 showed that no single evaluated classifier covered the full repository threat contract.
The HikmaAI multilingual model was precise but missed Chinese and tool-coercion cases, while
Llama Prompt Guard 2 was narrowly useful for explicit policy override. P10.3 therefore separates
the contract into independently auditable axes instead of weakening a shared threshold:

- HikmaAI is the required general untrusted-instruction semantic axis;
- deterministic action + target + effect detectors cover role impersonation, secret extraction,
  and tool coercion, with Context Guard preventing quoted or educational text from becoming an
  automatic finding;
- obfuscation is a modifier only and cannot independently mark content;
- Llama Prompt Guard 2 is a policy-override challenger and is retained only if the one permitted
  Qualification Dev run proves at least one unique true positive and zero added false positives;
- the final decision is a high-confidence union, not a majority vote. A required missing model,
  manifest mismatch, invalid profile, or runtime failure stops the security stage.

This P10.3 architecture is candidate-only. The runtime default remains `legacy_rules` until an
owner-approved Qualification Dev release and a new independent one-shot Blind Gate both pass.
The consumed P10.1/P10.2 datasets and blind results are not reused for selection. No document text
is sent to an external safety service.

The P10.3 Qualification Dev later rejected the candidate (Recall `0.95`, Specificity `0.7333`), so
no P10.3 Profile was released and `multi_axis_local` remains default-off. P10-D013 allows unrelated
Model Gateway development to proceed, but does not make detector output a trusted boundary. All
retrieved/document content must remain untrusted data, must not override system/developer policy,
and must not authorize tools or side effects. Tool execution remains default-deny and ACL, Secret
isolation and audit controls remain mandatory. A new independent detector release is required
before the P17/P18 integration and formal security gates can pass.

## Secrets and external providers

Secrets belong only in the ignored `.env` or a production secret manager. They must not enter fixtures, logs, traces, manifests, reports, or committed examples. `.env.example` contains empty secret fields.

External evaluation calls require explicit approval of the data scope and budget. The current P10 Dev protocol permits at most 12 approved Dev questions and their bounded textbook contexts, at most 180,000 DeepSeek tokens, zero Cohere Search Units, no Test records, no Gold labels, no complete documents, and no user identity. This permission is not active until separately approved.

## Fail-closed and rollback behavior

- Incremental-to-full-build switching is explicit; it is not an invisible fallback.
- Verified overlay publication failure keeps the previous active overlay and Primary index.
- QA/provider failures do not emit deterministic factual substitutes in formal evaluation.
- Revocation preserves immutable content and audit history.
- Database downgrade is an operator action after writes stop and P10 audit facts are exported; it is never automatic.
- Formal Test remains inaccessible until the exact frozen manifest, Test lock, data scope, and provider budget are separately approved.

P10 does not implement user login, membership administration, or a complete IAM backend; those remain an explicit P17 responsibility.
