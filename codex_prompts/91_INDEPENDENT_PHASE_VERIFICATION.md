# Codex 独立验收 Prompt

请对刚完成的阶段做一次只读验收，不继续新增功能。

1. 读取当前阶段 Prompt、冻结文档、`EXECUTION_STATUS.md` 和阶段报告；
2. 检查实际 diff 是否越界、遗漏任务或提前实现后续阶段；
3. 检查 API、数据库迁移、配置、错误处理、幂等、安全和兼容性；
4. 运行或复核阶段规定的测试、Lint、Type Check 和专项评测；
5. 查找静默 Fallback、硬编码 Provider/Secret、临时代码、未使用配置、数据双写不一致和测试跳过；
6. 按 Exit Gate 逐项给出 pass/fail/evidence；
7. 只修复本阶段明确的缺陷，不能借验收扩展范围；
8. 输出阻止进入下一阶段的问题、可延期问题和建议修复顺序。
