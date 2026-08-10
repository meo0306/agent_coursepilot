# ED-PRE07 DS3 Candidate 审核报告

- Bundle SHA-256: `2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400`
- Knowledge Point Candidate SHA-256: `e5365e52cef33bcceca9d729ad29db84b03bb3f205ab3378070dfc847e564976`
- DS2-KP Support Candidate SHA-256: `e94df4c8c4d79adc136b1aa14a8e09968dbf1d4a31c4a1d3a237dad6266b50d5`
- 知识点：107（DOCX 73 / PDF 34）
- Section：24（DOCX 16 / PDF 8）
- Supplemental Evidence：0（现有 Approved DS2 足以直接支撑全部入选项）
- Calibration/Holdout：75/32
- 首轮：107 条；第二轮：37 条。

首轮审核入口：`storage_eval/ds3_p07_review/2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400/index.html`；第二轮盲化入口：`storage_eval/ds3_p07_review/2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400/second_review.html`。先核对教学意义、名称/Alias、逐字 Summary、粒度、Evidence、Importance、Parent 与重复。

批准语句：`批准正式 P07 Gold Bundle 2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400`。

## 审核范围与重点

- 四组均为 6 个 Section；首轮必须审核 107/107，第二轮独立复核 37/37。
- 第二轮覆盖全部 Alias、OCR、公式记录以及其余记录的稳定 Hash 20% 样本；页面不读取或
  展示首轮决定。
- 重点检查：教学意义；名称/Alias 的原文依据；Summary 与逐字 Evidence 的一致性；
  atomic 粒度；Evidence 的直接性和必要邻接；Importance；Parent；课程内重复/近似概念。
- 五个边界需特别核对：DOCX `5.3.4`、`6.3`、`9.2.2`、`9.5.1`，以及 PDF
  `1.3.7`。前四个来自原始 OOXML 标题边界；`1.3.7` 来自独立 Poppler 标题/下节边界。
- 当前没有无法唯一定位的入选知识点，也没有 Supplemental Evidence、Parent、Composite、
  跨 Section 归并或待裁定冲突。若审核发现这些需求，应退回对应记录并生成 r2，不能在
  r1 上静默修改。

## 分布与治理状态

- Importance：core 23、supporting 82、optional 2。
- Evidence 角色：definition 8、principle 11、formula 4、process 7、application 24、
  example 2、support 51。
- Alias 记录 8 条；同名概念按课程形成不同 concept family，不跨课程归并。
- Manifest SHA-256：`c042ee0924c88a18b4f19176eb13ff3761f316ebd6d259995045d91df7fe1091`。
- 107 个审核图像/BBox 资源全部存在并逐项 Hash 绑定。Approved DS3 不存在；全局 Dev/Test
  为空，Test 未锁定，P07 尚未开始。

## 验证记录

- 连续生成两次：Candidate、Manifest、记录顺序、分组和 Split Hash 一致。
- P06 冻结资产保持不变：Approved DS2 `f49d8402…36b78`、审批 `e77d055d…9603`、
  B1/B2 系统输出 `bfa6a41e…6d396` 均与 Bundle 中绑定值一致。
- 审批后专项测试：22 passed；全量 Pytest：372 passed、5 gated skips。
- Schema：43/43 导出校验通过；Ruff format/check 通过；Mypy 241 source files 通过；
  `git diff --check` 无空白错误（仅既有 Windows CRLF 提示）。
- 未运行 P07 实现、正式阈值评测、数据库迁移、产品 API 修改、DS4/DS5 构造或审批提升。

## 2026-08-05 审批结果

Course Owner 明确声明首轮 107 条和第二轮 37 条均已审核、全部通过、零退回，并批准
Bundle `2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400`。系统据此生成
两份可追溯审核决定文件，注明其来源为对话中的人工明确声明，并通过原审批工具完成
全部覆盖率、Hash、源文件、上游 Approved、P06 冻结产物、Split 和审核资源校验。

- Approved DS3：`approved/ds3/p07_knowledge_points.json`，107 条，SHA-256
  `339a51f6f8f8fedeb533b6cbe0efa3ad96783dbae9580a4309924b63358b9566`。
- Approved DS2-KP Support：0 条，SHA-256
  `e94df4c8c4d79adc136b1aa14a8e09968dbf1d4a31c4a1d3a237dad6266b50d5`。
- Batch Approval SHA-256：`db180e9cc043f8c13e90b1c203089c12ab276ddb6d122a76b6d7b0cb4c23783c`。
- 幂等重放后审批日志仍为 107 条，无重复追加。
- `gold_status=ds3_p07_knowledge_points_approved`；`phase_input_status.p07=formal_eval_ready`。
