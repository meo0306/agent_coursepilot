from __future__ import annotations

from pathlib import Path

from courserag.chunking.tokenizer import LocalTokenizer
from courserag.evals.p06_metrics import map_gold_to_system_evidence
from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS3SectionScopeDataset,
    DS3SplitManifest,
)
from courserag.knowledge_points.profile import load_knowledge_point_profile
from courserag.knowledge_points.provider import (
    KnowledgePointProviderTransientError,
    ProviderExtraction,
)
from evaluation.p07_knowledge_point_eval import (
    APPROVED_DS2,
    P06_OUTPUT,
    P06_REPORT,
    P07_SCOPES,
    P07_SPLIT,
    PROFILE_PATH,
    TOKENIZER_PATH,
    _extract,
    _load_p06_runtime,
    _validated_protocol_approval,
    build_p07_windows,
    mixed_split_scopes,
)
from tests.courserag.knowledge_points.conftest import evidence, windows

ROOT = Path(__file__).resolve().parents[2]


def test_p07_eval_retries_only_transient_provider_failures() -> None:
    class TransientThenSuccessProvider:
        provider_name = "fake"
        model_name = "fake-v1"
        structured_output_method = "fake-structured"

        def __init__(self) -> None:
            self.calls = 0

        def extract(self, window, prompt: str) -> ProviderExtraction:
            del window, prompt
            self.calls += 1
            if self.calls == 1:
                raise KnowledgePointProviderTransientError("temporary")
            return ProviderExtraction(candidates=())

    provider = TransientThenSuccessProvider()
    window = windows(evidence(1), maximum=200)[0]

    result = _extract(provider, window, "prompt", "a" * 64, "e" * 64, 1, 0, 0)

    assert provider.calls == 2
    assert result["candidates"] == []


def test_p07_windows_use_p06_runtime_evidence_for_all_24_scopes() -> None:
    assert (ROOT / P06_OUTPUT).is_file() and (ROOT / P06_REPORT).is_file()
    scopes = DS3SectionScopeDataset.model_validate_json(
        (ROOT / P07_SCOPES).read_text(encoding="utf-8")
    )
    profile, _, _ = load_knowledge_point_profile(ROOT / PROFILE_PATH, repository_root=ROOT)
    tokenizer = LocalTokenizer(
        ROOT / TOKENIZER_PATH,
        tokenizer_id=profile.window.tokenizer_id,
        expected_sha256=profile.window.tokenizer_sha256,
    )
    evidence, aliases, _ = _load_p06_runtime(ROOT)

    windows = build_p07_windows(scopes, evidence, aliases, profile.window, tokenizer)

    assert len({item.section_id for item in windows}) == 24
    assert all(item.evidence and item.window_id.startswith("kpw1_") for item in windows)


def test_p07_evidence_metrics_apply_p06_document_identity_adapter() -> None:
    ds2 = DS2EvidenceDataset.model_validate_json((ROOT / APPROVED_DS2).read_text(encoding="utf-8"))
    runtime_evidence, aliases, _ = _load_p06_runtime(ROOT)

    matches = map_gold_to_system_evidence(
        ds2.evidence,
        runtime_evidence,
        document_aliases=aliases,
    )

    assert len(matches) == 101


def test_ds3_r2_split_isolates_calibration_holdout_windows() -> None:
    gold = DS3KnowledgePointDataset.model_validate_json(
        (ROOT / "datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json").read_text(
            encoding="utf-8"
        )
    )
    split = DS3SplitManifest.model_validate_json((ROOT / P07_SPLIT).read_text(encoding="utf-8"))

    mixed = mixed_split_scopes(gold, split)

    assert not mixed


def test_p07_runner_requires_exact_r2_protocol_approval() -> None:
    approval = _validated_protocol_approval(ROOT)

    assert (
        approval.protocol_bundle_sha256
        == "7261cb63b81f5b2e260a6a578383bd41df55c690aae999891d479146395b215b"
    )
