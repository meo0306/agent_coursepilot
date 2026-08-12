# Llama Prompt Guard 2 86M notice

- Upstream model: `meta-llama/Llama-Prompt-Guard-2-86M`
- Upstream page: <https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M>
- License: Llama 4 Community License Agreement
- Intended use in this repository: local, offline prompt-injection classification over
  extracted course-document text.
- Weight storage: external local directory only; model weights are not part of this Git
  repository or its MIT-licensed source distribution.

The repository's MIT License continues to apply to repository-owned source code. Use and
distribution of the external model are separately governed by the upstream Llama license.
Do not remove upstream license and attribution files from the local model snapshot.

The model is a defense-in-depth signal, not a complete security boundary. P10.2 combines
it with deterministic source mapping, fail-closed model identity checks, bounded evaluation,
and downstream instruction/data separation.
