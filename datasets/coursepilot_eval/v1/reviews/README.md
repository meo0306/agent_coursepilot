# CoursePilot review records

`review_log.jsonl` contains one `ReviewLogEntry` JSON object per line. Lesson,
exam-question, and PPT-slide scoring uses
`datasets/schemas/v1/coursepilot_human_scores.schema.json`.

No synthetic fixture is represented as a completed human review. Review
metadata and approval transitions must be written only by an explicit human
review workflow.
