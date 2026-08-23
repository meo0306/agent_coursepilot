# Pre-P17 r2 修订报告

- Integration r2 Bundle：`7e613ea920077cf0c811ac36c4867df6901c915340f17a330c4d7018d29fae54`；修复 20 条，原样结转 18 条。
  - Delta 审核 JSON：`storage_eval/p17_integration_review/7e613ea920077cf0c811ac36c4867df6901c915340f17a330c4d7018d29fae54/p17_integration_r2_review_template.json`。
- Security r2 Bundle：`be1f7a235b5c40e55b8b6814b78f8759d17b4987dfcbe0175af3ab099f869b8b`；修复 91 条，原样结转 29 条。
  - Delta 审核 JSON：`storage_eval/p17_security_review/be1f7a235b5c40e55b8b6814b78f8759d17b4987dfcbe0175af3ab099f869b8b/p17_security_r2_review_template.json`。
- CP-DS8 仍为 30 个场景、34 个真实执行变体。
- Security 仍为 60 malicious/60 benign；24 条 malicious 的混淆现在实际出现在正文中。
- Blind Commitment 未变，仍为 48 条、`empty_unread`，正文未创建。
- r2 仅输出 JSON 审核模板，不生成 HTML。
