# ED-PRE09 DS5 QA/Context Candidate r2 审核报告

## 精确身份

- Parent r1 Bundle：`0634c618279e8c4ddd432eeff2a20974924c06ddfe641f48da528d8311bb30e0`
- r2 Bundle：`5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1`
- QA Candidate SHA-256：`e2cd285336211e7989bd6b8d591224ad49dc02c57135c64dc84595b0ee2354ca`
- Context Candidate SHA-256：`abf6b1d6ffa95f28515ce50a603e300d07e4ddb9a5cdbafc187730d90dcc7d06`
- Coverage Audit SHA-256：`2ce71cbb5e258024fad879e099a7b7533a8d1571cc22cee00eccef033a829b64`

## 修订结论

- 100 条 P08 Query、课程、Split、Retrieval Gold 均未改变。
- 18 条 QA 记录发生原子 Claim 或答案覆盖修订；其余 82 条 QA 记录 Hash 不变。
- 仅 ERNIE 过程题增加一个经原始 OOXML与固定 Renderer 第272物理页核对的必要邻接；其余99条 Context记录 Hash不变。
- 90 条可回答记录均具有完整回答义务覆盖；10条不可回答记录保持无答案、无 Claims。
- 比较题遵循冻结文档示例：无唯一短答案，由两侧 Required Claims 共同评分。
- r1 两轮全通过采用 Course Owner 对话中的明确声明保存为继承审计；r2 两轮只复核18条实质变化。

## 统计

- Answer Type：`{'comparison': 10, 'explanatory': 48, 'factoid': 14, 'list': 8, 'procedure': 10, 'unanswerable': 10}`
- Gold Claims：`243`；必要邻接：`65`。
- 覆盖审计：100条，其中90条 complete、10条 not_applicable_unanswerable、0条 uncovered。

## 审核重点

1. 每个回答义务是否被所列 Claim 完整覆盖。
2. Claim 是否为单一事实，且未引入原文之外的信息。
3. Evidence 正文与必要邻接来源是否区分正确。
4. 事实题短答案是否完整；解释/比较/过程题的空短答案是否明确标为“不适用”。
5. ERNIE 配置与两次 `run_infer.py` 执行步骤是否与原始 DOCX 一致。

批准前必须完成 r2 的两份差异审核 JSON，并使用新的 Bundle SHA-256。

## 验证结果

- r2 连续生成两次，QA、Context、Coverage 和 Bundle SHA-256 字节级一致。
- 回答义务审计：90 条可回答记录全部 `complete`，10 条不可回答记录全部
  `not_applicable_unanswerable`，未覆盖义务为 0。
- 修订隔离：82 条 QA 与 99 条 Context 保持 r1 记录 Hash；r1 QA/Context 均通过独立修订历史
  标为 superseded，通用数据集加载器只加载 r2。
- 专项测试：23 passed；修订边界补充复测：6 passed。
- 全量测试：453 passed，5 skipped（环境门控），0 failed。
- Ruff Format/Check 通过；Mypy 289 个源文件无问题；54 份 Schema 校验一致；
  `git diff --check` 无空白错误，仅报告既有 Windows LF/CRLF 提示。
- 未创建 Approved P09 Gold，未锁定 Test，未运行 P09 Dev/Test 评测。

## 精确审批结果

- Course Owner 于 2026-08-07 明确确认两轮差异审核全部完成，并批准精确 Bundle
  `5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1`。
- Approved QA SHA-256：`d3460b0831b5ce7567e0c97c82b0574c2aeb31776944fba9982e3f21d84d62c7`。
- Approved Context SHA-256：`0f23da3eba8b76e29040e4a5a8632f24b170e65e8fd792d7a98a6633c51ee330`。
- 100 条 QA 和 100 条 Context 均生成记录级 ApprovalRecord；review log 有 200 条唯一审批记录。
- 同一审批复放返回相同 Hash，未增加重复记录；QA/Context r2 修订状态均为 `approved`。
- Manifest 状态为 `ds5_p09_qa_context_approved`，P09 输入状态为 `formal_dev_eval_ready`。
- Test 继续 `locked=false`；P09 Loader 仅加载 Dev 60（主集 54、上游缺口诊断 6）。
- 本审批仅表示 Pre-P09 数据 Gate 通过，不表示 P09 Exit Gate 已通过。
