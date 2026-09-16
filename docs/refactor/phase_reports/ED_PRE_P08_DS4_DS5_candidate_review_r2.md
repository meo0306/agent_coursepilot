# ED-PRE08 DS4/DS5 r2 Candidate 审核报告

## r1 系统审计结论

- 60/60 DS4 卡片只显示不透明 KP ID，Course Owner 无法独立核对原文。
- 30 条 DS4 专门边界案例使用词面启发式链接；已全部替换为六个逐项策划的真实术语案例。
- 90 条 DS5 使用未经独立核验的启发式 1 分 Evidence；r2 全部删除，不把同源包误当相关性。
- 78 条 DS5 至少有一个 0 分项与 Required Evidence 位于同一 Source Package；r2 全部改为所属课程内、Required 包之外的候选。
- 所有 15 条 paraphrase 和 10 条 procedure Query 已改为内容相关的自然问法。
- 完整审计：`datasets/courserag_eval/v1/provenance/p08_r1_systemic_audit.json`；逐条 r1→r2 变化：`datasets/courserag_eval/v1/provenance/p08_r1_to_r2_record_changes.json`。
- 标准修订历史：`datasets/courserag_eval/v1/provenance/p08_candidate_revision_history.json`、`datasets/courserag_eval/v1/provenance/p08_ds5_candidate_revision_history.json`。
- r2 确定性语义链验证：`datasets/courserag_eval/v1/provenance/p08_r2_semantic_validation.json`；它验证全部 Query–KP–Required
  Evidence 直接闭合、课程一致、无遗漏同 KP Evidence、无自动 1 分和无 Required 包负例碰撞。

## r2 审核对象

- Bundle SHA-256：`7f6b22556e3261d242dbd2b425812eeb18489dc75f6086697d808bbffbfbdf52`
- DS4：60；DS5：100；Source Package：10。
- 首轮：`storage_eval/ds45_p08_review/7f6b22556e3261d242dbd2b425812eeb18489dc75f6086697d808bbffbfbdf52/index.html`（160 条）。
- 二轮：`storage_eval/ds45_p08_review/7f6b22556e3261d242dbd2b425812eeb18489dc75f6086697d808bbffbfbdf52/second_review.html`（132 条）。
- 每个 KP ID 旁显示 canonical name、Summary、主 Evidence 原文、必要邻接、Section、页码、BBox 和覆盖图。
- 每个 DS5 Evidence ID 旁显示 2/0 分角色及逐字原文；r2 没有自动 1 分标签。

## 验证结果

- r2 连续生成得到同一 Bundle SHA-256；r1 两个 Candidate 的文件 Hash 与 r1 Manifest 一致。
- DS4/DS5 与数据集边界专项测试：15 passed；全量 Pytest：416 passed、5 skipped。
- 48 个 JSON Schema 导出文件通过 `--check`；381 个文件通过 Ruff Format Check 和 Ruff Check。
- 全量 Mypy：263 个源文件无问题；`git diff --check` 无空白错误，仅有既有 LF/CRLF 提示。
- Approved DS4/DS5、全局 Dev/Test 和 Test Lock 均未改变；QA Gold 继续 `pending_p09`。

r1 保留但已标记 superseded；不得审批 r1 Hash。r2 全部审核通过后才可回复精确 Bundle 审批语句。
