# P10.1 独立盲测交接说明

## 已冻结输入

- P10.1 Profile Freeze Candidate SHA-256：
  `ffe8f58220cf3b1b821d25e25a681a34cef039d8cf20d8ab87c929c5cb71401e`
- Security Profile SHA-256：
  `8ce80b54cd2cd7a8b3c7af9294302691278ff0034a9fb925dbb43ba41a6bb8a2`
- Course Owner 已批准 Profile Freeze；该批准不等于批准尚未构造的 Blind Test Bundle。

## 隔离要求

Blind Test 必须在当前实现对话之外独立构造。构造者不得读取：

- `datasets/courserag_eval/releases/p10_1_security/candidate_dev_r1.json`；
- `resources/security_profiles/prompt_injection_candidate_v2.json`；
- `src/courserag/security/prompt_injection.py`；
- 原 P10 已曝光失败句子的具体规则实现。

当前实现对话在 Owner Lock 前不得查看 Blind Test 正文。交接时只接收文件路径、文件
SHA-256、两轮审核结果摘要和审核文件 SHA-256。

## Bundle 合同

独立构造者需要生成 12 条记录：8 条攻击正例、4 条 Hard Negative。正例应覆盖冻结的五个
行为族，但不得复制 Dev 或已曝光 Sentinel 文本。Bundle 顶层合同为：

```json
{
  "schema_version": "courserag.p10-1-security-blind-test.v1",
  "dataset_id": "courserag-p10-1-security",
  "dataset_version": "blind-test-r1",
  "status": "approved_locked",
  "independently_constructed": true,
  "first_review_approved": true,
  "second_review_approved": true,
  "cases": []
}
```

每条记录必须包含：

- `record_id`：`p10-1-sec-test-01` 至 `p10-1-sec-test-12`；
- `category`：`policy_override`、`role_impersonation`、`secret_extraction`、
  `tool_coercion`、`obfuscation` 或 `hard_negative`；
- `text`：1—1000 字符；
- `expected_marked`：正例为 `true`，Hard Negative 为 `false`。

## 两轮审核

第一轮审核检查语义标签、类别、分布、是否复制已知样本以及是否包含真实 Secret。第二轮由另一
审核身份在不查看 Scanner 输出的条件下复核全部 12 条。两轮审核文件应分别记录：审核者、时间、
Bundle SHA-256、12 个 Record ID、逐条 pass/return 和理由；所有条目均 pass 后才可申请 Owner Lock。

## 回传与锁定顺序

1. 将 Bundle 和两轮审核结果放入非公开、未被实现侧预读的位置；
2. 只向当前实现对话提供三个文件路径及各自 SHA-256；
3. 当前实现对话只做文件 Hash 和审核覆盖校验，不读取 Bundle 正文；
4. Course Owner 明确批准精确 Bundle SHA-256；
5. 将 `blind_test_commitment.json` 从 `awaiting_independent_construction` 原子更新为 `locked`，
   同时绑定 Bundle SHA、已批准 Manifest SHA、锁定时间和 Owner；
6. Blind Runner 一次性读取 Bundle并输出不含原文的结果；结果不得回流当前 Profile 调参。

若 Blind Gate 失败，本版本记录限制并保持 P10 未通过；不得修改当前 Profile 后重复运行同一
Blind Bundle。
