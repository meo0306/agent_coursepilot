# Pre-P16 CP-DS3/CP-DS7 PPT Pilot Candidate Review

任务：`ED-PRE16-CPDS37-T01` 至 `ED-PRE16-CPDS37-T09`

本批生成 3 条 CP-DS3 Pilot（24/12/10 页）、4 条 CP-DS7 正例和 2 条合同负例。所有事实来自 Approved P14/P06/P07；未调用 Provider、未读取 Test/Holdout、未生成 P16 输出。

- CP-DS3 Candidate SHA-256：`667a4373d9fd177302f2cfc6d8468e56d88141fd51baa6a69695f80c9d1030d8`
- CP-DS7 Candidate SHA-256：`e765fba3643913036f4a04029d91b28b62df36c763b6da47ba365b365aa81c95`
- Bundle SHA-256：`697a00183e3c84ab7ff70152a54479e6802a3c353250740291bcb51c84f4d57c`
- 记录：3 个 Deck、46 个 Slide Target、4 个模板正例、2 个负例
- 审核入口：`storage_eval/cpds37_p16_review/697a00183e3c84ab7ff70152a54479e6802a3c353250740291bcb51c84f4d57c/index.html`
- 二轮入口：`storage_eval/cpds37_p16_review/697a00183e3c84ab7ff70152a54479e6802a3c353250740291bcb51c84f4d57c/second_review.html`
- 外部模板：lrkrol/powerpoint Velis，提交 `0f18f3f1fe2d76413c45b0106e7585d64beb920d`，CC0，源 Hash `54f58da18846a40976c2b2aa13950343d4b24d112b5a0b64f1f8efbe251dcbcd`，规范化 PPTX Hash `caec81e7bbcc4712dc60e90af2bae26a3a7890b3300432c0b1cfaa8dc024e32a`

## 当前限制

本机未发现可执行的 `soffice`，Docker Engine 也未运行，因此 Manifest 的 Renderer Preflight 为 `available=false`。结构、Hash、Master/Layout/Placeholder 已检查；固定 LibreOffice Render Preview 尚未完成。按照 P16 计划，当前 Bundle 不应直接审批，需在 Renderer 可用后补跑并重新绑定 Candidate/Bundle Hash。

Candidate 保持 `candidate`，没有写入 `approved/`。
