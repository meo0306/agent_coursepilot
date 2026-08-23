# Pre-P17 数据构造报告

- P16 按 Owner 决定直接采用最终成果，不再生成 17 页复审包。
- Integration Bundle：`01b7549801efad637b4da39c271fe932c2ae44104ab73f3c618add0dfdac7b78`。
  - CP-DS8 Candidate：`datasets/coursepilot_eval/v1/candidates/cp_ds8/p17_fault_security_r1.json`，30 条场景、34 个执行变体。
  - SYS-DS1 Candidate：`datasets/coursepilot_eval/v1/candidates/sys_ds1/p17_system_journeys_r1.json`，8 条 Journey。
  - 审核页：`storage_eval/p17_integration_review/01b7549801efad637b4da39c271fe932c2ae44104ab73f3c618add0dfdac7b78/index.html`。
- Security Qualification Dev Bundle：`f230655e5ed60c9462401e0824b6a3ec4e302b275faf16460ce61a50fd54ad8b`。
  - Candidate：`datasets/courserag_eval/releases/p17_security/qualification_dev_candidate_r1.json`，120 条（60 malicious/60 benign）。
  - 审核页：`storage_eval/p17_security_review/f230655e5ed60c9462401e0824b6a3ec4e302b275faf16460ce61a50fd54ad8b/index.html`。
- Blind：48 条仅承诺规模，正文为空且未读取。
- 两个 Bundle 均只设置一轮人工审核；未生成 Approved 文件。
- 不运行 P17、安全 Dev/Blind、真实 Provider 或 P18 正式评测。
