# Pre-P16 CP-DS3/CP-DS7 Candidate Review r2

- Tasks: `ED-PRE16-CPDS37-T01` through `ED-PRE16-CPDS37-T09`
- CP-DS3 r2 SHA-256: `7001ec09dcf7ca782fadb2468a39fb5b0a51b81dc8be35d8f14e4d57bdd5b039`
- CP-DS7 r2 SHA-256: `ef6ec83bba30a1ddb02bc93437421034eaab87acbc5b6e54dc4fa316d02fccb9`
- Bundle SHA-256: `e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91`
- First review: 55 objects (3 Architecture + 46 Slide Target + 6 Template/Negative cases)
- Blind second review: 23 objects (3 Architecture + 9 high-risk slides + Velis + 2 negatives + 8 stable-hash samples)
- Fixed renderer: LibreOffice `7.4.7.2`, Poppler `22.12.0`, image `agent-coursepilot-pptx-qa:lo-7.4.7.2`
- Repeated render: 17/17 page PNG hashes identical
- External editable smoke: `storage_eval/p16_render_work_r3/velis-smoke-8slides.pptx`
- Review entry: `storage_eval/cpds37_p16_review/e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91/index.html`
- Second review: `storage_eval/cpds37_p16_review/e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91/second_review.html`
- Browser verification: 55/23 decision controls, 17/8 loaded preview images, local autosave and
  reload restore, completeness validation, and the schema-shaped 55-record export payload passed.

The three built-in template files remain byte-identical and are shown once as the same visual
baseline while retaining three separate logical-role decisions. Velis exposes 2 Masters and 32
Layouts. Its smoke deck preserves editable shapes/placeholders and contains no image-only slide.
The fixed renderer substitutes locked Noto Sans CJK/DejaVu fonts; the review page declares this
explicitly. The visible fixed date/footer and Close-layout star are review findings, not silently
accepted behavior.

`@oai/artifact-tool` was not available from the public npm registry and its expected private
runtime dependency was absent. Per the Course Owner's explicit fallback authorization, local
PowerPoint 2021 automation was used only to instantiate the editable Velis smoke. LibreOffice
7.4.7.2 remains the fixed evaluation renderer.

At Candidate generation time, no Approved Gold, Dev/Test data, Provider output, database, API or
runtime configuration changed.

## Approval closure

The Course Owner supplied both exported review files. Validation confirmed 55/55 first-pass and
23/23 blind second-pass records, all PASS, exact record order, exact Bundle binding and no returned
item. Bundle `e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91`
was promoted to P16 Pilot Approved input.

- Final Approval SHA-256: `e9017dd61a02843750036d2112515c8c47e93f36fcc764b17f5d8a9e6eda6d58`
- Approved CP-DS3 SHA-256: `198695213fe99241983dc29d6c35ffdb8f0e5bfe7d067e1fcd5ed16d99babdc5`
- Approved CP-DS7 SHA-256: `2e923d29faba9319e5cbd0f530d10461e0173fcbeaa3213ff8eb81583a611b3e`
- Record-level approvals/review-log additions: 55
- CoursePilot Dev/Test: empty; Test lock: false
- Provider calls: 0

This closes the pre-P16 input Gate only. P16 implementation, generated-deck evaluation and the P16
Exit Gate have not run. P18 formal Gold remains unchanged.

The repository boundary test rejected two same-turn intermediate approval serializations before
closure: one used review-card hashes for embedded records, and one logged Architecture IDs instead
of the embedded Deck record IDs. Both artifacts are retained with `superseded_invalid_*` names.
The final approval uses the common approval-free record digest and matching ReviewLog record ID;
the full Candidate/Approved/ReviewLog inventory validation passes.
