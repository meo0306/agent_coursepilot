# CourseRAG review records

`review_log.jsonl` contains one `ReviewLogEntry` JSON object per line. QA
claim-level human scores use
`datasets/schemas/v1/courserag_qa_human_scores.schema.json`.

Candidate generation never appends approvals or human scores. An `approved`
record requires an explicit reviewer identity, candidate/result hashes, and a
matching approval entry in `review_log.jsonl`.
