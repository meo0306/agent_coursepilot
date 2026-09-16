# P18 正式数据构造报告（Candidate）

## 当前交付

- Business Bundle：`4ce0ac60ca70c1f1fd23e62aaab911718dc763882ceee0d371d726926bd9a869`，30 条全新任务（Lesson/Exam/PPT 各10；Dev/Test各6/4）。
- Quality/Recovery 最终 Bundle：`d724a1c430ed1c02ae42b770b46714fe3ff0b73abb94d83906d9e6268470a082`，CP-DS4正式90、CP-DS5正式60、新CP-DS6 24；审核129条。
- Integration/Export 最终 Bundle：`5d42d4428aad1f31b07434febcd9ff9b487436095c5c99d3f3e2348627a46683`，CP-DS7 11、CP-DS8 30、SYS-DS1 8；复用模板不重复审核。
- 三批构造时均为 Candidate，仅使用一轮 JSON 人工审核、无 HTML 审核页；现已按精确 Bundle Hash 批准。
- P14/P15/P16 Pilot 不进入正式业务指标；P13 CP-DS4/5 只进入 Dev。
- CP-DS8 Blind 身份已随正式 Gold 批准，但 Dev Loader 仍无权读取；正文只允许在后续 Test Lock 边界释放。

## 自定义 DOCX 修正

计划假定的 `Invoice.docx` 在固定提交中不存在。执行时改用同一 MIT 仓库、同一提交内真实存在的
`test-crate/templates/combined_areas.docx`，其正文、表格、页眉和页脚均含静态占位符。源文件
SHA-256 为 `45b4b86d5927381b0502659c4604e2ce6bd28f6ff6a4a5a0b76f170628f319bc`。没有静默切换仓库或许可证。

首轮审核后已恢复固定 Docker LibreOffice 7.4.7.2 Renderer。两次渲染均为1页，页面 PNG Hash 一致；
人工检查未发现裁切、重叠、表格破损、缺字或页眉页脚错位。r2 已保存完整 GitHub 仓库、仓库内路径、
Renderer 版本、预览路径及视觉检查结果。

## 未执行

- 未锁定或运行 Test，未调用 Provider，未运行 P18 Dev/Track A/Track B。
- 最终 CP-DS0 必须等待 P18 Dev 结果和 Profile/Graph/Renderer/Exporter/Index 冻结后另行生成。

## 精确审批结果（2026-08-23）

- Business Bundle `4ce0ac60ca70c1f1fd23e62aaab911718dc763882ceee0d371d726926bd9a869` 已批准，30/30 首审通过。
- Quality/Recovery Bundle `d724a1c430ed1c02ae42b770b46714fe3ff0b73abb94d83906d9e6268470a082` 已批准；r1 通过 111、退回 18，r2 的 18 条增量复审全部通过。
- Integration/Export Bundle `5d42d4428aad1f31b07434febcd9ff9b487436095c5c99d3f3e2348627a46683` 已批准；r1 通过 31、退回 8，r2 的 8 条增量复审全部通过。
- 九个正式数据文件合计 208 条记录已经提升至 `approved/`；记录级 ApprovalRecord、批级审批、合并审核决定与追加式 Review Log 已写入。
- 组件 Split Manifest SHA-256 为 `acf9421a8dfa2512ae568a0eb8d468c5994ec757edf912b3683473ad8005cf4e`；正式业务任务保持 Dev 18 / Test 12。
- 当前治理状态为 `gold_status=p18_formal_gold_approved`、`phase_input_status.p18=formal_dev_eval_ready`。
- 本次没有生成 CP-DS0，没有锁定或运行 Test，也没有调用 Provider；`test.lock.json` 继续为 `locked=false`。

## 首轮审核与 r2 增量修复

- Business 首轮 30/30 通过，Bundle `4ce0ac60ca70c1f1fd23e62aaab911718dc763882ceee0d371d726926bd9a869` 保持不变。
- Quality/Recovery 首轮通过111、退回18；r2 仅修复 CP-DS5 `allowed_paths` 与 `forbidden_paths` 的交叉，Bundle 为 `d724a1c430ed1c02ae42b770b46714fe3ff0b73abb94d83906d9e6268470a082`。
- Integration/Export 首轮通过31、退回8；r2 补齐自定义 DOCX 来源和渲染证据、修正两条持久化故障合同及五条 SYS-DS1 时间线，Bundle 为 `5d42d4428aad1f31b07434febcd9ff9b487436095c5c99d3f3e2348627a46683`。
- 固定 Docker LibreOffice 7.4.7.2 两次渲染均为1页，PNG SHA-256 均为 `9265d1d02f7d729eaa0435b782d22b6c8cd69990eed587526ee2db0983c82e79`。
- r2 只需一轮增量复审18+8条；首轮已通过记录保持原 ID、记录 Hash 和审核决定。
