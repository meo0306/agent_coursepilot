# ED-PRE12 CP-DS6 Pilot Candidate Review

- Candidate: `datasets/coursepilot_eval/v1/candidates/cp_ds6/p12_interrupt_recovery_r1.json`
- Candidate SHA-256: `e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18b3ae1701a1`
- Records: 24 (six interrupt types × four scenarios; four scenario types × six interrupts)
- Fixture: course-agnostic structural cases; no future P12 UUIDs, database rows, model output or CourseRAG content.
- Status: `candidate`; awaiting Course Owner review. No Approved file and no P12 runtime evaluation has been generated.

## Review entry

`storage_eval/cp_ds6_p12_review/e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18b3ae1701a1/index.html`

## Review focus

- Every interrupt covers Approve, Edit+Resume, Replan and Reject.
- Edit changes only the listed editable path and creates exactly one new Artifact Version.
- Replan detects stale Context/Index versions and invalidates affected nodes.
- Reject enters `cancelled`, forbids resume, and performs no Export or Writeback.
- Duplicate Decision, duplicate Artifact, Export and Writeback side effects remain zero where expected.
