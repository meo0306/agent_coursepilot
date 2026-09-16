# Evaluation and limitations

P18 used frozen Dev/Test inputs, real Provider calls, no LLM-as-a-Judge, and explicit human
review. The formal run is complete, but the human-quality gate failed: among 24 reviewed
artifacts, 7 were minor, 13 major, and 4 rejected; the four generation failures were marked
critical. The system therefore demonstrates engineering closure, not production content quality.

Strongest evidence is functional: typed workflow state, six interrupt/resume paths, immutable
artifact versions, targeted repair boundaries, editable export, remote trace/version continuity,
and idempotent side effects. Known debt includes uneven Exam diversity, some PPT/lesson quality,
and isolated prompt-injection automation limitations. Public claims must preserve these limits.
