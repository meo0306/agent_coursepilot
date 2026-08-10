# LibreOffice Headless Renderer v1

This profile is the P04 reproducible DOCX pagination baseline. Runtime rendering is accepted only
when `soffice --version` and the Debian font-package version match the lock files. The recorded font
Manifest hash is bound to the existing exact QA container provenance. The service image installs
the locked Noto CJK package and uses an isolated LibreOffice user profile for every render.

`raw_pdf_sha256` records the exact renderer output. `canonical_pdf_sha256` records the same PDF
after volatile metadata and trailer identifiers are removed; DS1 uses the canonical hash. Page
labels are read from the PDF or source-visible header/footer text and are never inferred from a
physical page number.
