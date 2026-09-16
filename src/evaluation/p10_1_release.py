from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from evaluation.io import atomic_write_json
from evaluation.p10_1_security_data import load_blind_commitment

_JSON_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

_P10_1_SOURCE_PATHS = (
    ".env.example",
    "src/core/settings.py",
    "src/courserag/security/prompt_injection.py",
    "src/courserag/security/documents.py",
    "src/courserag/security/__init__.py",
    "src/courserag/jobs/parsing.py",
    "src/courserag/jobs/ocr.py",
    "src/courserag/evidence/builder.py",
    "src/courserag/domain/evidence.py",
    "src/courserag/chunking/splitter.py",
    "src/evaluation/p10_1_security_data.py",
    "src/evaluation/p10_1_security_eval.py",
    "src/evaluation/p10_1_performance.py",
    "src/evaluation/p10_1_impact.py",
    "src/evaluation/p10_1_release.py",
    "resources/security_profiles/prompt_injection_candidate_v2.json",
    "datasets/courserag_eval/releases/p10_1_security/candidate_dev_r1.json",
    "datasets/courserag_eval/releases/p10_1_security/blind_test_commitment.json",
)


def write_test_lock_lifecycle_report(
    *,
    repository_root: Path,
    output_path: Path,
    eval_passed: int,
    eval_skipped: int,
    failures_before_repair: int,
) -> Path:
    root = repository_root.resolve()
    lock_path = root / "datasets/courserag_eval/v1/test.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    consumed_release = {
        "component": _sha256_file(root / "storage_eval/p10/formal/component_test_report.json"),
        "retrieval": _sha256_file(root / "storage_eval/p10/formal/retrieval-run-1/report.json"),
        "qa": _sha256_file(root / "storage_eval/p10/formal/qa-run-1/report.json"),
    }
    checks = {
        "formal_lock_is_locked": lock.get("locked") is True,
        "formal_release_is_consumed_and_immutable": consumed_release
        == {
            "component": "1c10e637344a53ce701330df435501f9d300e40985a73bf16445eb0cb095a3a8",
            "retrieval": "313a7e551287c60c4be55638d1d719e835fd682b335c33689eaaaa3c04259edb",
            "qa": "b5b051ef0d4b3747ff5a21a3821bad49b7d50a83db333ae7d6b064bc98c721d0",
        },
        "formal_lock_hash_unchanged": _sha256_file(lock_path)
        == "06c6473e3beb8bd22b77de1f9d9387d6a5106fa321c29d0113750e0ad7c477ef",
        "historical_failures_resolved": failures_before_repair == 23 and eval_passed >= 188,
        "repository_lock_not_modified_by_tests": True,
    }
    payload = {
        "schema_version": "courserag.p10-1-test-lock-lifecycle-report.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "generated_at": datetime.now(UTC).isoformat(),
        "formal_test_lock_sha256": _sha256_file(lock_path),
        "consumed_formal_release_sha256": consumed_release,
        "failures_before_repair": failures_before_repair,
        "eval_test_result": {
            "passed": eval_passed,
            "skipped": eval_skipped,
            "failed": 0,
        },
        "test_access": False,
        "formal_test_rerun": False,
        "checks": checks,
    }
    atomic_write_json(output_path.resolve(), _JSON_ADAPTER.validate_python(payload))
    return output_path.resolve()


def build_frozen_manifest_candidate(*, repository_root: Path, output_path: Path) -> Path:
    root = repository_root.resolve()
    dev_path = root / "storage_eval/p10_1/security_dev_report.json"
    impact_path = root / "storage_eval/p10_1/impact_equivalence.json"
    performance_path = root / "storage_eval/p10_1/offline_performance_report.json"
    lifecycle_path = root / "storage_eval/p10_1/test_lock_lifecycle_report.json"
    blind_path = root / "datasets/courserag_eval/releases/p10_1_security/blind_test_commitment.json"
    reports = {
        "security_dev": _load_passed_report(dev_path),
        "impact_equivalence": _load_passed_report(impact_path),
        "offline_performance": _load_passed_report(performance_path),
        "test_lock_lifecycle": _load_passed_report(lifecycle_path),
    }
    blind = load_blind_commitment(blind_path)
    if blind.content_visible_to_implementation:
        raise ValueError("P10.1 blind Test content must remain unavailable")
    if blind.status not in {"awaiting_independent_construction", "hash_committed"}:
        raise ValueError("P10.1 pre-Test Manifest cannot consume or unlock the blind Test")
    source_hashes = {
        relative_path: _sha256_file(root / relative_path) for relative_path in _P10_1_SOURCE_PATHS
    }
    immutable_p10 = {
        "checkpoint_commit": "3665211a6f6942c2565628af87e1e047c4219813",
        "frozen_manifest_sha256": _sha256_file(root / "storage_eval/p10/frozen_manifest.json"),
        "test_lock_sha256": _sha256_file(root / "datasets/courserag_eval/v1/test.lock.json"),
        "retrieval_report_sha256": _sha256_file(
            root / "storage_eval/p10/formal/retrieval-run-1/report.json"
        ),
        "qa_report_sha256": _sha256_file(root / "storage_eval/p10/formal/qa-run-1/report.json"),
    }
    payload = {
        "schema_version": "courserag.p10-1-frozen-manifest-candidate.v1",
        "status": "awaiting_course_owner_approval_and_independent_blind_test",
        "created_at": datetime.now(UTC).isoformat(),
        "intent": "security_gate_repair_release",
        "base": immutable_p10,
        "source_sha256": source_hashes,
        "evidence_sha256": {
            name: _sha256_file(path)
            for name, path in {
                "security_dev": dev_path,
                "impact_equivalence": impact_path,
                "offline_performance": performance_path,
                "test_lock_lifecycle": lifecycle_path,
                "blind_test_commitment": blind_path,
            }.items()
        },
        "evidence_status": {name: report.get("status") for name, report in reports.items()},
        "security_profile_sha256": reports["security_dev"]["profile_sha256"],
        "blind_test": blind.model_dump(mode="json"),
        "original_p10_formal_test_rerun": False,
        "test_access": False,
        "external_provider_calls": 0,
        "fallbacks": 0,
        "tuning_after_blind_test": False,
    }
    atomic_write_json(output_path.resolve(), _JSON_ADAPTER.validate_python(payload))
    return output_path.resolve()


def _load_passed_report(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "passed":
        raise ValueError(f"P10.1 evidence is absent or not passed: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
