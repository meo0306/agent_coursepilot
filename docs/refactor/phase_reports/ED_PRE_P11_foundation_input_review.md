# ED-PRE11 P11 Foundation Input 工作包报告

## 当前结果

- 依赖判断：`eligible_for_candidate`，依据 `p10_d013_dependency_waiver`。
- 独立 Draft：37 条（1 Foundation、9 Template、12 Model Gateway、15 Runtime）。
- 完整 Candidate：已生成 40 条 Candidate；Bundle `ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522`。
- CoursePilot 正式 Gold：未生成，`gold_status=skeleton_no_formal_gold`。
- P10.3 安全 Profile：`candidate_rejected_default_off`，失败报告未改写为通过。

## 文件

- Draft：`datasets/coursepilot_eval/v1/drafts/p11/p11_foundation_independent_r1.json`
- Candidate：`datasets/coursepilot_eval/v1/candidates/work_packages/p11_foundation_input_r1.json`
- Candidate Manifest：`datasets/coursepilot_eval/v1/provenance/p11_foundation_input_manifest.json`
- P10 Gate/Waiver Audit：`datasets/coursepilot_eval/v1/provenance/p11_p10_gate_audit.json`

## P10-D013 精确检查

- PASS `p10.d013.dependency_waiver`：P10-D013 owner waiver and ready_to_start status present；要求：exact owner-approved P10-D013 dependency waiver remains authoritative
- PASS `p10.d013.failed_profile_preserved`：report=26e5eb98bfe08536987cd8a6b36d769ce3e3370319f8479d57c15b1ba596f0bb, status=failed, profile_emitted=false；要求：failed P10.3 report remains exact and no Profile is emitted
- PASS `p10.d013.blind_unread`：blind_status=awaiting_independent_construction, visible=False, report_blind_access=False；要求：P10.3 Blind content remains unbuilt, invisible and unread
- PASS `p10.frozen_manifest.authorized`：authorization=cad5df9ce87fc9682bef2441ed66aa957064f467a5ffdbd209b37e358c40937a, file=cad5df9ce87fc9682bef2441ed66aa957064f467a5ffdbd209b37e358c40937a；要求：authorization and owner approval bind the exact Frozen Manifest
- PASS `p10.lock.and.run.identity`：lock_file=06c6473e3beb8bd22b77de1f9d9387d6a5106fa321c29d0113750e0ad7c477ef, canonical_test_ids=b21a030a790ee30a11ee83417469ad28a6b78bba1e89081d3ad6a30b4cc561ea, split_file=e910d726f450957c6d30ecee7314a02f64d5063ae3dbc2567e325d2e33660134, frozen=cad5df9ce87fc9682bef2441ed66aa957064f467a5ffdbd209b37e358c40937a；要求：formal runs bind both Test identity layers and the exact Frozen Manifest
- PASS `p10.formal_reports.complete`：report.json=present, report.json=present, component_test_report.json=present；要求：QA, retrieval and component final reports all present
- PASS `p10.courserag_port.present`：src/coursepilot/ports/courserag.py；要求：CoursePilot CourseRAG consumer Port artifact exists

## 继承的安全边界

- `retrieved_context_is_untrusted_data`
- `system_and_developer_instructions_cannot_be_overridden`
- `tool_execution_is_default_deny`
- `tool_execution_requires_explicit_capability_and_authorization`
- `course_acl_and_trusted_gateway_claims_remain_enforced`
- `secrets_are_excluded_from_context_trace_and_artifacts`
- `security_decisions_are_audited_without_trusting_p10_3_findings`
- `p10_3_candidate_must_remain_default_off`

## 审批边界

完整 Candidate 已完成首轮 40/40 与二轮 27/27 审核，退回数均为 0。Course Owner 已批准
精确 Bundle `ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522`。审批只提升为 P11
实施输入工作包，不构成 CP-DS0—8 正式 Gold；Dev/Test 继续为空，CoursePilot Test 继续未锁定。
P10.3 Blind 未构建、未读取，失败候选无 Profile 且 Runtime 默认仍为 `legacy_rules`。

- Approved 工作包：`datasets/coursepilot_eval/v1/approved/work_packages/p11_foundation_input.json`
- Approval：`datasets/coursepilot_eval/v1/provenance/p11_foundation_input_approval.json`
- Approved 工作包 SHA-256：`357a9c0d242bd28c9c574086ace6c7a93383643f497364e728a0f2af9eebe3dd`
- Approval SHA-256：`09b2525848469d219590c373095415dc454de7d37590aeb2ab68990dce4fc234`
- 治理状态：`phase_input_status.p11=approved_for_implementation`；P11 执行仍为 `not_started`。

本批没有修改产品 HTTP API、业务数据库、迁移、运行配置或三条业务 Graph。

## 人工审核入口与标准

- 首轮（40 条全部审核）：`storage_eval/p11_foundation_review/ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522/index.html`
- 二轮盲化（固定 27 条）：`storage_eval/p11_foundation_review/ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522/second_review.html`
- 首轮依次核对输入合同、预期行为、禁止行为、依据与通过条件是否相互一致。
- 9 条 Template 只审核合同和资源角色映射，不审核未来视觉质量。
- 12 条 Model Gateway 重点检查能力不足、超时、429、非法 JSON、Usage 缺失时不会静默切模、编造数据或启用 Fallback。
- 18 条 Runtime 重点检查版本不可变、Fingerprint 复用边界、Secret 排除、B0 兼容和 CourseRAG fail-closed。
- 3 条 CourseRAG Port 必须只使用两个指定 Dev Query 或无课程事实的失败夹具；不得出现 Test、DS3 Holdout 或新增课程事实。
- P10.3 相关卡片必须保持“失败、无 Profile、默认关闭、Runtime 仍为 legacy_rules”，不得审核成安全能力已通过。

## 自动验证结果

- 确定性生成：连续两次 Candidate SHA、Manifest、首轮页和二轮页 Hash 完全一致。
- Schema 导出检查：76 个 Schema 全部一致。
- 专项测试：审批前 `25 passed`；审批与幂等重放回归补充后 `26 passed`。
- 全量测试：`603 passed, 6 skipped`。
- Ruff Format Check：528 个文件均已格式化；Ruff Check：通过。
- Mypy：369 个源文件无问题。
- `git diff --check`：通过；仅报告仓库既有 CRLF 转换提示，无空白错误。
- 审批幂等重放：返回同一 Approval/Approved SHA，Review Log 对应 `review_id` 仍仅 1 条。
