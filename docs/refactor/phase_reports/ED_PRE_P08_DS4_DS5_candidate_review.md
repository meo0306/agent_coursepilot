# ED-PRE08 DS4/DS5 r3 Candidate 审核报告

## r2 首轮裁决与全面修订

- r2 首轮反馈包含 160 条已审记录、25 条退回；导出文件未携带文本备注。
- 独立复核接受 17 条退回，8 条按测试目的保留；裁决见 `datasets/courserag_eval/v1/provenance/p08_r2_first_review_adjudication.json`。
- 全部 15 条 Cross-section 改为分别说明两项，不再要求推断原文未建立的联系。
- 全部 100 条 DS5 均重新执行正例包含关系和同课程混淆负例审计；完整 Top-8 排名见 `datasets/courserag_eval/v1/provenance/p08_r3_relevance_audit.json`。
- r3 恢复经原文包含关系证明的部分相关 1 分项，共 1 个，不为配额制造 1 分。
- 审核导出现在保存 `record_notes`、`reviewer_id` 和 `reviewed_at`，退回但未写原因时禁止导出。

## r3 审核入口

- Bundle SHA-256：`ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396`
- DS4：60；DS5：100；变化记录：117。
- 变化记录首轮复核：`storage_eval/ds45_p08_review/ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396/index.html`。
- 固定 132 条盲化二轮：`storage_eval/ds45_p08_review/ff64abba71d392496e7ce530f7de5c612794616557b65a7aa11e739e20759396/second_review.html`。
- 未变化记录通过精确记录 Hash 继承 r2 首轮决定；不会继承发生任何字段变化的记录。

r3 仍是 Candidate；Approved、Dev/Test 和 Test Lock 均未改变。

## Course Owner 审核结论

2026-08-06，Course Owner 在会话中明确确认两轮审核全部通过、零退回，并要求不再提供
浏览器导出的 JSON。该结论已固化为 `datasets/courserag_eval/v1/reviews/p08_r3_first_review_decisions.json` 和
`datasets/courserag_eval/v1/reviews/p08_r3_second_review_decisions.json`；正式提升仍等待独立的精确 Bundle 批准语句。

