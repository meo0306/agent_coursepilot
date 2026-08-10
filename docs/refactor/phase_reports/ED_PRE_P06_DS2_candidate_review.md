# ED-PRE06 正式 DS2 Candidate r7 必要邻接全量审计报告

- r7 Candidate：`datasets/courserag_eval/v1/candidates/ds2/p06_evidence_r7.json`
- r7 Candidate SHA-256：`ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad`
- 全量邻接审计：`datasets/courserag_eval/v1/provenance/ds2_p06_necessary_neighbor_audit_r7.json`
- 最小上下文规则：`datasets/courserag_eval/v1/provenance/ds2_necessary_neighbor_policy_v1.json`
- r6 审核决定：`datasets/courserag_eval/v1/reviews/ds2_p06_review_decisions_r6.json`
- r7 委托上下文审核决定：`datasets/courserag_eval/v1/reviews/ds2_p06_review_decisions_r7.json`
- 可选审计页面：`storage_eval/ds2_p06_review/ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad/index.html`

## 课程所有者指令与修订边界

课程所有者报告 r6 审核完毕，并要求不能再用通用 Section 小标题代替真正的必要邻接；120 条记录均须检查代词、列表、表格、公式、代码、步骤及转折依赖。课程所有者同时明确授权跳过本次上下文字段的再次逐条审核。

r7 仅修改 `requires_parent`、`necessary_neighbor_text` 和 `necessary_neighbors`。与 r6 相比，120/120 的 `gold_text`、精确/规范化内容 Hash、Source Units、SourceSpan、BBox、语义标签、上游 Approved 引用及稳定 Evidence ID 均保持不变。78 条记录 Hash 因邻接字段调整而改变；Gold 内容 Hash 和稳定 ID 的变化数均为 0。

## 最小必要邻接结果

- 55 条记录需要至少一项真实邻接；65 条记录经逐条检查后可独立解释，不附加帮助性背景。
- 依赖类命中数：代词/指代 20，列表范围 8，表格范围 13，公式符号 5，步骤顺序 7，因果/转折 5，代码作用域 2。一条记录可命中多个类别。
- 表格完整网格只补表题；独立表行补表题和表头。
- 列表只补总领句；除非解释目标本身需要，不复制兄弟条目。
- 公式只补缺失的相邻符号定义、公式或公式目的；公式视觉对象继续绑定冻结 LibreOffice 7.4.7.2 渲染和已批准的线性化规则。
- 通用父 Section 小标题全部移除。唯一保留的 `parent_heading` 是 `（2）R3-LIVE[23]`，因为它本身是“它的视觉-IMU子系统”的最近且唯一先行词。
- PDF 第 24 页跨块错序句按可见阅读顺序核对；其余 PDF 邻接逐字落在指定 Poppler 块，DOCX 邻接逐字落在 OOXML 段落、表格或冻结渲染公式对象。

## 审批和阶段状态

课程所有者已明确批准精确 r7 Candidate SHA-256
`ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad`。审批工具在写入前重新校验 Candidate 文件 Hash、120 个记录 Hash、四个完整审核组、零退回、空 Dev/Test 和未锁定 Test。

提升结果：

- Approved DS2：`datasets/courserag_eval/v1/approved/ds2/p06_evidence.json`
- Approved 文件 SHA-256：`f49d84027cde8341d906e270d29cc46e7b71eb6de4da5220188cb03894436b78`
- 批级审批：`datasets/courserag_eval/v1/provenance/ds2_p06_approval.json`
- 批级审批 SHA-256：`e77d055da2ee173a2a931ef74d3b910a98679f83e3e5ec7d2340354d13869603`
- 审批时间：`2026-08-03T23:01:48+08:00`
- 审批身份：`course_owner`

Approved 文件包含 120 条 `approved` Evidence 和 120 个绑定 Candidate/Approved 记录 Hash 的 `ApprovalRecord`。`review_log.jsonl` 从 79 条增加到 199 条，恰好追加 120 条记录级审批；使用完全相同参数重放后，两个产物 Hash 不变、日志不再增长。Candidate r7 保持原 Hash 和 `candidate` 状态，没有被原地改写。

Manifest 已更新为 `gold_status=ds2_p06_evidence_approved`、`gold_components.ds2=approved`、`phase_input_status.p06=formal_eval_ready`。Dev/Test 仍为空，Test 仍未锁定。未运行 P06 B1/B2；本次批准只表示 P06 正式输入已准备好，不表示 P06 Exit Gate 已通过。

## 验证记录

- r7 构造器连续执行三次，Candidate SHA-256 均为 `ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad`；审计 SHA-256 均为 `74b200a873a52d75a21b96aba8380a09ee9d5d1903285c8aac90388f840e29e6`。
- Candidate Manifest SHA-256：`3c33cafaaa23789e725d1cf0af75c9d8c25483b822ffccec371510c688366403`。
- 结构检查：120 条唯一记录、55/65 邻接分布、所有邻接 Hash 自校验、`requires_parent == bool(necessary_neighbors)`、四组各 30 条、两份 Primary DocumentVersion 不变。
- 内容冻结检查：Gold 内容 Hash 0 变化、稳定 ID 0 变化、Source Units/Span/BBox/语义标签 0 变化。
- Candidate 阶段专项测试：28 passed；审批后 DS2/数据边界/Schema 专项：29 passed；P04 兼容及 Streamlit 定向复跑：14 passed。
- 审批后全量测试：最终 352 passed、5 skipped。首次审批后全量运行有 4 项失败：一项由容器生成的有效 `.pyc` 内嵌 `/workspace` 路径导致主机 Streamlit 测试找不到文件；三项暴露 P04 旧代码将全局 `gold_status` 固定在 DS1、不能容纳后续 DS2 状态。改用独立主机字节码缓存，并让 P04 Runner 读取稳定的 `gold_components.ds1_native_docx=approved`（同时兼容旧 Manifest）后，定向和全量复跑均通过。
- Schema：38 份导出文件与当前模型一致。
- Ruff：316 个文件 format check 通过，lint 通过。
- Mypy：223 个源文件 `Success: no issues found`。

## 未完成项

- P06 Evidence Builder/Chunker 实现尚未在本批执行。
- P06 B1/B2 尚未运行；P06 Exit Gate 尚未评估。
