# ED-PRE08 DS4/DS5 Candidate 审核报告

## 审核对象

- Bundle SHA-256：`329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d`
- DS4 Candidate：`datasets/courserag_eval/v1/candidates/ds4/p08_query_processing_r1.json`（60 条）
- DS5 Candidate：`datasets/courserag_eval/v1/candidates/ds5/p08_retrieval_r1.json`（100 条）
- 审批范围：`ds4_query_processing_and_ds5_retrieval_only`；QA Gold 明确为 `pending_p09`。
- 语义来源：2；Source Package：10；派生文档未进入 Retrieval Gold。

## 审核入口

- 首轮：`storage_eval/ds45_p08_review/329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d/index.html`，160 条全部审核。
- 二轮：`storage_eval/ds45_p08_review/329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d/second_review.html`，132 条盲化复核。
- 第 1 组（20 条）：`index.html` 中筛选记录 1–20
- 第 2 组（20 条）：`index.html` 中筛选记录 21–40
- 第 3 组（20 条）：`index.html` 中筛选记录 41–60
- 第 4 组（20 条）：`index.html` 中筛选记录 61–80
- 第 5 组（20 条）：`index.html` 中筛选记录 81–100
- 第 6 组（20 条）：`index.html` 中筛选记录 101–120
- 第 7 组（20 条）：`index.html` 中筛选记录 121–140
- 第 8 组（20 条）：`index.html` 中筛选记录 141–160

## 必查顺序

1. Query 是否自然、只问所属课程且没有新增课程事实。
2. Query 类型、难度、Filter、KP 和 Source Package 是否合理。
3. 每个 2 分 Evidence 是否直接且完整；多证据组是否缺一不可。
4. 每个 1 分 Evidence 是否确实有帮助但单独不足；必要邻接是否消除依赖。
5. 3–5 个 0 分硬负例是否容易混淆但不能回答；未列 Evidence 默认 0。
6. 不可回答项是否完成全课程审计，最近假阳性是否都不能回答。
7. 页码/BBox、P06 诊断层和 `qa_gold_status=pending_p09` 是否正确。

## 构造验证

- Candidate 连续生成两次后，两个 Candidate、Source Package、Split、分组、顺序和 Bundle Hash 完全一致。
- DS4/DS5/Schema/边界专项测试：30 passed；全量 Pytest：415 passed、5 skipped。
- JSON Schema：48 个导出文件通过 `--check`；Ruff Format/Check 与全量 Mypy（262 个源文件）通过。
- `git diff --check` 通过，仅显示 Windows 工作区既有的 LF/CRLF 提示。
- `approved/ds4`、`approved/ds5` 仍只有 `.gitkeep`；全局 Dev/Test 仍为空，Test 未锁定。
- 未运行 P08、B3–B5、外部 Provider、正式 Test 或 P09 QA 标注。

任何退回都按记录 ID 生成 r2，不覆盖 r1。两轮全部通过后，请回复：

`批准正式 P08 Gold Bundle 329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d`
