import json
from pathlib import Path

import pytest

from evaluation.p10_eval import (
    FRESH_CASE_IDS,
    P10TestLock,
    _fresh_checkpoint_tokens,
    authorize_test_run,
    build_dev_protocol,
    create_frozen_manifest,
)


def test_workspace_sha256_ignores_python_bytecode(tmp_path: Path) -> None:
    from evaluation.p10_eval import _workspace_sha256

    source = tmp_path / "src" / "package"
    source.mkdir(parents=True)
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=\n", encoding="utf-8")
    baseline = _workspace_sha256(tmp_path)

    cache = source / "__pycache__"
    cache.mkdir()
    (cache / "module.cpython-312.pyc").write_bytes(b"runtime cache")
    (source / "orphan.pyc").write_bytes(b"runtime cache")

    assert _workspace_sha256(tmp_path) == baseline


ROOT = Path(__file__).resolve().parents[2]


def test_dev_protocol_is_delta_only_and_test_closed() -> None:
    protocol = build_dev_protocol(ROOT)
    assert protocol.fresh_case_ids == FRESH_CASE_IDS
    assert protocol.test_access is False
    assert protocol.cohere_search_unit_cap == 0
    assert protocol.external_data_authorized is False


def test_freeze_and_test_lock_require_independent_authority() -> None:
    protocol = build_dev_protocol(ROOT)
    with pytest.raises(ValueError, match="authorization"):
        create_frozen_manifest(
            protocol=protocol,
            qa_dev_report_sha256="a" * 64,
            qa_gate_sha256="b" * 64,
            component_dev_report_sha256="c" * 64,
            usage_audit_sha256="d" * 64,
            workspace_sha256="b" * 64,
            test_ids_sha256="c" * 64,
            deepseek_dev_tokens=1,
            gates_passed=True,
            fallback_count=0,
        )
    authorized = protocol.model_copy(update={"external_data_authorized": True})
    manifest = create_frozen_manifest(
        protocol=authorized,
        qa_dev_report_sha256="a" * 64,
        qa_gate_sha256="b" * 64,
        component_dev_report_sha256="c" * 64,
        usage_audit_sha256="d" * 64,
        workspace_sha256="b" * 64,
        test_ids_sha256="c" * 64,
        deepseek_dev_tokens=1,
        gates_passed=True,
        fallback_count=0,
    )
    lock = P10TestLock(
        frozen_manifest_sha256="d" * 64,
        owner_approval_sha256="e" * 64,
        external_budget_authorized=False,
    )
    with pytest.raises(ValueError, match="does not match"):
        authorize_test_run(lock, frozen_manifest_sha256="f" * 64)
    with pytest.raises(ValueError, match="budget"):
        authorize_test_run(
            lock.model_copy(update={"frozen_manifest_sha256": "f" * 64}),
            frozen_manifest_sha256="f" * 64,
        )
    assert manifest.status == "awaiting_owner_test_lock"


def test_resume_budget_counts_only_fresh_succeeded_provider_usage(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "cases": {
                    f"q3:{FRESH_CASE_IDS[0]}": {
                        "status": "succeeded",
                        "result": {"usage": {"deepseek_total_tokens": 123}},
                    },
                    f"q3:{FRESH_CASE_IDS[1]}": {
                        "status": "failed",
                        "result": {"usage": {"deepseek_total_tokens": 999}},
                    },
                    "q3:hash-reused-case": {
                        "status": "succeeded",
                        "result": {"usage": {"deepseek_total_tokens": 45678}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    assert _fresh_checkpoint_tokens(checkpoint) == 123
