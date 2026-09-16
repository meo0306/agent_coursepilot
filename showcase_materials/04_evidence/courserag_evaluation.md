# Evaluation summary

The development program used approved, evidence-level course retrieval datasets and separated
retrieval quality from upstream parsing gaps. Representative frozen development results included:

- Hybrid B4 Recall@10: 0.9167.
- Hybrid B4 complete evidence-group Recall@8: 0.8611.
- Cohere-reranked B5 MRR@10: 0.7014 and nDCG@10: 0.8006.
- Cited-QA answer-status accuracy: 0.9167; unanswerable recall: 1.0.
- Citation resolvability and claim-citation completeness: 1.0 in the cited-QA run.

These are small, course-specific development results, not broad benchmark claims. The later P18
system formal quality Gate failed for CoursePilot output completeness and missing Track-B index
provisioning. CourseRAG's automatic prompt-injection detector also failed its release qualification
and remains disabled.
