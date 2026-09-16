# P16 PPT Architecture、模板导出与渲染检查阶段报告

## 当前完成情况

本轮完成 P16 的第一批可运行功能闭环：

- `P16-T01/T02/T03`：新增强类型 `SlideArchitecture`、`SlidePlan`、`SlideContent`、引用和素材占位合同；Architecture Review 与 Final Review 使用既有 P12 Interrupt 类型。
- `P16-T04/T05`：新增 PPT 模板 Profile/Snapshot/Importer，枚举全部 Master/Layout 和 Placeholder 角色；导出使用可编辑文本、图形占位和 Speaker Notes 引用，不改动旧 P11 模板文件。
- `P16-T06/T07`：新增静态 PPTX 重开、页数、Shape 边界、空页和可编辑对象检查，以及确定性字段修复入口。
- `P16-T08`：新增 `/tasks/{task_id}/ppt/export` 与 `/tasks/{task_id}/ppt/writeback` 加法端点，复用 EXPORT/VERIFIED_WRITEBACK 审批范围；写回限制为单页或单页 Notes。
- `P16-T09`：新增离线/Provider Runner；Provider Runner 支持 checkpoint/resume 和预算硬门禁。

## 已运行证据

- P16 输入、模板注册表、旧 PPT Graph/API/Exporter 回归：`21 passed`。
- 离线 Runner 生成 3 页可编辑 PPTX，静态 Render Report `passed=true`，外部请求数为 `0`。
- 新增配置默认关闭 `COURSEPILOT_PPT_V2_ENABLED=false`，Legacy PPT 行为保持不变。
- Provider 涨价后按控制台实付重新冻结低峰计费：缓存命中输入/未命中输入/输出分别按 `¥0.05/¥1.50/¥4.50` 每百万 Token，控制台基线 `¥1.02`，追加硬上限 `¥0.80/32 requests/230k input/90k output`。Runner 已实现低峰窗口、人民币/Token/请求联合门禁、原子 Checkpoint、授权起点跨 Resume 固定和失败响应待对账记录。
- r3 从原 `20 requests / 149,491 input / 44,023 output` 精确恢复。第二案例第 5 页首次返回仅 Thinking、无最终 JSON；系统停止后仅按 Course Owner 对精确 Request SHA 的授权重试一次，重试成功且未发生第三次调用或模型切换。
- 三案例 Provider Pilot 已完成，共生成 `24 + 12 + 10 = 46` 页。追加阶段最终为 `30 requests / 165,872 input / 86,545 output+thinking / ¥0.526344`，控制台累计估算 `¥1.546344`，均低于批准的 `32 / 230k / 91k / ¥0.80` 与控制台 `¥1.82` 上限。
- 三份 PPTX 的本地结构检查均通过：可打开、页数一致、严重越界为 0，可编辑对象分别为 `49/26/21`。内容校验最初误把 `notes_required=false` 的标题/引用页判为缺 Notes；Validator 已改为服从逐页 Architecture 合同，缓存重算后三案例均为 `validation_passed=true`，且没有新增 Provider 调用。
- 另有一次最小 Smoke（1 次成功，3,487 输入/5,312 输出）和一次 Architecture 结构化解析失败响应；这些独立运行必须与 r3 一起按 Provider 控制台账单做累计 reconciliation，不能把 r3 单目录数字误当作全阶段总量。

## 尚未完成与质量债务

1. 第一轮 46 页人工审核已完成，但发现 17 个 `critical_defect` 页面；一次性定向修复已完成，尚需 Course Owner 对这 17 页做最终复审。
2. 自动渲染边界检查曾漏掉人工可见的裁切和教学内容缺失，因此其结论只作为必要条件，不能替代人工视觉审核。
3. 29 个非 Critical 页面保持内容 Hash 不变；其风格、密度等非阻塞偏好不再进入修复循环，可在最终复审后登记质量债务。
4. 本轮是唯一修复轮次。若复审仍发现硬缺陷，必须如实记录并由 Course Owner处置，不能再次调用模型修复。

## Gate 状态

P16 当前为 `gate_pending_owner_critical_repair_review`，尚不能标记 `completed` 或 `completed_with_quality_debt`。Provider Pilot、预算门禁、固定 LibreOffice QA、CP-DS7 导入、本地内容/结构 Gate 以及唯一一次 Critical-only 修复均已完成；下一步只需 Course Owner 复审 17 页修复结果，不再重跑三案例 Provider 生成或执行第二轮修复。P17 暂不具备开始条件。

## P16 closure execution (no external Provider calls)

本次窄范围收尾未修改已批准数据集、r3 Provider 报告或历史 v1 模板，也未产生外部调用：

- 新增 `PPTWorkflowService`，通过 `RuntimeRepository` 解析已审核 Lesson Artifact，并只经 CourseRAG Port 获取 KP、Context 和 Evidence；持久化状态保留 ID、Hash 与 `ContextPackageRef`。
- 新增三套独立 v2 PPTX 资源和 `p16_profiles_v2.json`；Exporter 按 SlideType→Layout 映射选择真实 Layout，不再固定使用某个布局索引。
- 新增固定 LibreOffice/Poppler 渲染入口；静态检查不再冒充真实渲染。Docker QA 对 24/12/10 页三套 Deck 执行两次 PDF/PNG 渲染，PNG Hash 一致，严重溢出和越界均为 0。
- 只读执行 CP-DS7：三套内置模板、Velis 用户模板和两个预期失败合同均通过，`provider_requests=0`。
- 最终审核包位于 `storage_eval/p16_closure_docker/review/`，包含 46 页预览、审核 JSON 模板和自动保存/下载页面。当前环境的浏览器运行时未能初始化，因此尚未完成浏览器实际点击下载验证；该项仍是 Owner Review 前的工具验证事项。

固定渲染证据：`storage_eval/p16_closure_docker/report.json`。P16 现在为 `gate_pending_owner_review`；完成 Course Owner 审核并验证下载后，才可收口为 `completed / passed`（若仅有非阻塞视觉偏好，可记录为 `completed_with_quality_debt`）。

## P16 Critical-only 一次性修复收尾

### 问题现象与原因

Course Owner 对 46 页最终 Deck 完成人工评分后，发现 17 页存在事实表达、结构完整性、
表格物化、引用页密度或人工可见裁切等 Critical 问题。固定 LibreOffice/Poppler 检查仍
报告边界与空页为 0，说明几何检查只能发现页面外越界，不能覆盖布局内部裁切、教学语义
缺失和视觉可读性；人工审核因此是这类缺陷的最终判据。

### 修复边界与执行结果

- 预检绑定源报告 SHA-256 `10898a46...`、Owner Decision SHA-256 `8d23d664...` 和精确
  17 个页面 ID；每页最多修复一次，29 个非 Critical 页面 Hash 必须保持不变。
- 新增 `p16_critical_repair_v1` Profile 和 Evidence-bound Repair Prompt；QKV、Add & Norm、
  感知机偏置、职业风险表格、来源归属、引用页密度和可见裁切分别采用定向修复。
- Provider 执行使用 9 次请求、19,971 输入 Token、53,342 输出/Thinking Token，估算
  CNY 0.266655；低于 CNY 0.45 / 20 请求 / 130k 输入 / 60k 输出硬上限。
- 一个已计费响应因模型自行生成错误 `content_sha256` 而无法直接解析，系统只恢复该已付费
  JSON 并本地重算 Hash，没有再次调用；另一个请求超时后没有重试。最终 8 页来自成功
  Provider Checkpoint，9 页在停止外部调用后依据 Approved Evidence 和 Owner Notes 确定性完成。
- 三套 24/12/10 页 PPTX 均可重开并通过固定 Docker LibreOffice/Poppler 渲染；自动严重
  Overflow、越界和空页均为 0，CP-DS7 仍为 4 个正例和 2 个预期负例通过。
- 专项回归为 `28 passed`；Ruff Format/Check、目标文件 Mypy 和 `git diff --check` 通过。

### 最终人工检查点

只需复审 `storage_eval/p16_critical_repair_closure/review/index.html` 中的 17 页。页面包含
新预览、结构化内容、Notes、Evidence 和“上一轮 Critical 问题”，并可导出 JSON。
本轮之后禁止第二次修复：若只剩视觉偏好或轻微密度问题，P16 可按
`completed_with_quality_debt` 收口；若仍有事实错误、严重裁切、不可编辑对象或无效引用，
必须记录为未通过并请求显式处置，而不是继续调参。

## Final Provider completion and closure — 2026-08-21

### Problem and cause

The first Critical-only run changed all 17 owner-selected pages, but only eight pages had successful
Provider checkpoints. Nine pages had deterministic Evidence-bound completion after the bounded run
stopped. The owner required consistent Provider treatment for those nine pages. The first scheduled
completion process then stopped after two pages because the PowerShell wrapper used
`ErrorActionPreference=Stop`, which promoted a non-fatal Python stderr warning to a terminating
wrapper error. This was orchestration failure, not a Provider or checkpoint failure.

### Repair and execution result

- The wrapper now treats native stderr as diagnostic output and determines success from the native
  exit code. The runner emits one progress event per page and persists response/checkpoint state.
- Resume reused the two completed responses and processed the remaining seven pages. No successful
  request was duplicated, no fallback or model switch occurred, and no timeout retry was needed.
- The exact nine-page completion produced 9 valid Provider results with 9 physical requests,
  26,657 input tokens and 64,073 output/Thinking tokens. One valid JSON response carried an invalid
  self-authored `content_sha256`; the system discarded that untrusted hash, recomputed it locally,
  and reused the same paid response without another call.
- The merged report proves all 17 Critical pages now use Provider output: eight original
  `provider_checkpoint`, eight `provider_completion`, and one
  `provider_completion_recovered_response`. No deterministic repair source remains.
- A zero-Provider-call closure rerendered all three decks in the fixed Docker renderer. The 24, 12
  and 10 page decks all reopen and render; severe overflow, out-of-bounds and empty required
  placeholder counts are all zero. All six CP-DS7 template cases pass.

Evidence:

- `storage_eval/p16_provider_completion/report.json`
- `storage_eval/p16_provider_completion_closure/report.json`

### Final gate and remaining quality debt

P16-T01 through P16-T09 are complete. PPTX open/render/editability, severe-overflow and Citation
contracts pass, whole-deck writeback remains prohibited, and the Provider-consistency issue is
closed. Per the Course Owner's explicit disposition, the successful nine-page completion does not
require a new final review package. The earlier 46-page review remains the record of visual and
pedagogical limitations; residual non-critical style, density and teaching-quality variance is
accepted as quality debt rather than starting another repair loop.

Final status: `completed_with_quality_debt`; Exit Gate passed. P17 may start, but it inherits the
P10-D013 detector debt as mandatory security work before P17/P18 security freeze.
