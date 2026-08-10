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
