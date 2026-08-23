"""Build the deterministic P15 CP-DS2 Exam Pilot input package."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import (
    CPDS2P15PilotDataset,
    P15AssessmentTarget,
    P15BlueprintGold,
    P15ConstraintConflictCase,
    P15ContextFixture,
    P15EvidenceFixture,
    P15ExamPilotCase,
    P15FixtureBundle,
    P15InsufficientEvidenceCase,
    P15KnowledgePointFixture,
    P15QuestionBatchPlan,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
COURSE_ROOT = Path("datasets/courserag_eval/v1")
PILOT_PATH = DATASET_ROOT / "candidates/cp_ds2/p15_exam_pilot_r1.json"
FIXTURE_PATH = DATASET_ROOT / "provenance/p15_exam_fixtures_r1.json"
MANIFEST_PATH = DATASET_ROOT / "provenance/p15_cp_ds2_bundle_manifest.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P15_CPDS2_candidate_review.md")

DS2_PATH = COURSE_ROOT / "approved/ds2/p06_evidence.json"
DS3_PATH = COURSE_ROOT / "approved/ds3/p07_knowledge_points.json"
DS3_SPLIT_PATH = COURSE_ROOT / "provenance/ds3_p07_split.json"
DEV_RETRIEVAL_PATH = COURSE_ROOT / "approved/ds5/p08_retrieval.json"

DOCX_COURSE = "course_ai_algorithms_systems"
PDF_COURSE = "course_ai_general_education"


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_sha(item: dict[str, Any]) -> str:
    approval = item.get("approval")
    if not isinstance(approval, dict) or not approval.get("approved_record_sha256"):
        raise ValueError(f"approved upstream record has no approval hash: {item.get('record_id')}")
    return str(approval["approved_record_sha256"])


def _load_upstream(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    ds2_path = root / DS2_PATH
    ds3_path = root / DS3_PATH
    split_path = root / DS3_SPLIT_PATH
    ds2 = json.loads(ds2_path.read_text(encoding="utf-8"))
    ds3 = json.loads(ds3_path.read_text(encoding="utf-8"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    evidence = {item["evidence_id"]: item for item in ds2["evidence"]}
    knowledge_points = {item["gold_kp_id"]: item for item in ds3["knowledge_points"]}
    calibration = set(split["calibration_ids"])
    hashes = {
        "ds2": sha256_file(ds2_path),
        "ds3": sha256_file(ds3_path),
        "ds3_split": sha256_file(split_path),
    }
    return evidence, {**knowledge_points, "__calibration__": calibration}, hashes


def _validate_track_b_queries(root: Path) -> dict[str, str]:
    payload = json.loads((root / DEV_RETRIEVAL_PATH).read_text(encoding="utf-8"))
    by_id = {item["record_id"]: item for item in payload["cases"]}
    query_ids = {
        "docx": "gold-rq-2417aa8d3269b1406dce95d8297fe170",
        "pdf": "gold-rq-62df7d3d129d5b2d4ebcf68836c64576",
    }
    for query_id in query_ids.values():
        item = by_id.get(query_id)
        if (
            item is None
            or item.get("split") != "dev"
            or item.get("evaluation_stratum") != "retrieval_main"
            or item.get("review_status") != "approved"
        ):
            raise ValueError(
                f"P15 Track B query is not an Approved retrieval_main Dev case: {query_id}"
            )
    return query_ids


def _evidence_fixture(item: dict[str, Any]) -> P15EvidenceFixture:
    span = item["source_span"]
    return P15EvidenceFixture(
        evidence_id=item["evidence_id"],
        record_sha256=_record_sha(item),
        course_id=item["course_id"],
        gold_text=item["gold_text"],
        necessary_neighbors=[str(value) for value in item.get("necessary_neighbor_text", [])],
        source_document_id=span["document_id"],
        source_document_version=span["document_version"],
        page_start=span.get("page_start"),
        page_end=span.get("page_end"),
        source_type=item["source_type"],
        semantic_unit_type=item["semantic_unit_type"],
        content_sha256=item["content_sha256"],
    )


def _kp_fixture(item: dict[str, Any]) -> P15KnowledgePointFixture:
    return P15KnowledgePointFixture(
        gold_kp_id=item["gold_kp_id"],
        record_sha256=_record_sha(item),
        course_id=item["course_id"],
        canonical_name=item["canonical_name"],
        summary=item["summary"],
        section_ids=item["section_ids"],
    )


def _target(
    *,
    target_id: str,
    case_id: str,
    kp: dict[str, Any],
    evidence: dict[str, Any],
    evidence_ids: list[str],
    role: str,
    allowed_types: list[str],
    difficulty_range: list[str],
    risks: list[str],
    hard_negative_ids: list[str],
    hard_negative_evidence: dict[str, dict[str, Any]],
    hashes: dict[str, str],
) -> P15AssessmentTarget:
    supporting = [_evidence_fixture(evidence[item]) for item in evidence_ids[1:]]
    primary = _evidence_fixture(evidence[evidence_ids[0]])
    return P15AssessmentTarget(
        record_id=target_id,
        target_id=target_id,
        case_id=case_id,
        course_id=kp["course_id"],
        knowledge_point=_kp_fixture(kp),
        primary_evidence=primary,
        supporting_evidence=supporting,
        allowed_question_types=allowed_types,
        content_role=role,
        difficulty_range=difficulty_range,
        required_claims=[primary.gold_text],
        optional_claims=[kp["summary"]],
        forbidden_claims=[],
        hard_negative_evidence_ids=hard_negative_ids,
        hard_negative_evidence=[
            _evidence_fixture(hard_negative_evidence[item]) for item in hard_negative_ids
        ],
        risk_flags=risks,
        source_provenance=[
            f"approved/ds2/p06_evidence.json:{hashes['ds2']}",
            f"approved/ds3/p07_knowledge_points.json:{hashes['ds3']}",
            f"provenance/ds3_p07_split.json:{hashes['ds3_split']}",
        ],
    )


def _batch_plan(
    case_prefix: str, counts: dict[str, int], target_ids: list[str]
) -> list[P15QuestionBatchPlan]:
    batches: list[P15QuestionBatchPlan] = []
    for question_type in ("single_choice", "multiple_choice", "judgement", "short_answer"):
        count = counts[question_type]
        if case_prefix.startswith("p15-exam-03") and question_type == "single_choice":
            pieces = [5, 5]
        else:
            pieces = [count]
        offset = 0
        for index, piece in enumerate(pieces, 1):
            selected = [target_ids[(offset + n) % len(target_ids)] for n in range(piece)]
            batches.append(
                P15QuestionBatchPlan(
                    batch_id=f"{case_prefix}-batch-{question_type}-{index:02d}",
                    question_type=question_type,
                    question_count=piece,
                    target_ids=selected,
                )
            )
            offset += piece
    return batches


def _context(
    *,
    context_id: str,
    case_id: str,
    course_id: str,
    targets: list[P15AssessmentTarget],
) -> P15ContextFixture:
    records: list[P15EvidenceFixture] = []
    seen: set[str] = set()
    for target in targets:
        for item in [target.primary_evidence, *target.supporting_evidence]:
            if item.evidence_id not in seen:
                records.append(item)
                seen.add(item.evidence_id)
    return P15ContextFixture(
        context_package_id=context_id,
        purpose="exam_generation",
        case_id=case_id,
        course_id=course_id,
        evidence_records=records,
        target_ids=[target.target_id for target in targets],
        content_hash=_digest(
            {"case_id": case_id, "evidence": [item.content_sha256 for item in records]}
        ),
        token_count=sum(max(1, len(item.gold_text) // 2) for item in records),
    )


def _render_review(
    dataset: CPDS2P15PilotDataset,
    fixtures: P15FixtureBundle,
    bundle_sha256: str,
    review_ids: list[str],
    *,
    second_review: bool,
) -> str:
    cases = {case.record_id: case for case in dataset.cases}
    targets = {target.target_id: target for target in dataset.targets}
    negatives: dict[str, P15InsufficientEvidenceCase | P15ConstraintConflictCase] = {
        fixtures.insufficient_evidence_case.record_id: fixtures.insufficient_evidence_case,
        fixtures.constraint_conflict_case.record_id: fixtures.constraint_conflict_case,
    }
    cards: list[str] = []
    for record_id in review_ids:
        if record_id in cases:
            case = cases[record_id]
            blueprint = case.blueprint
            body = (
                f"<p><b>模板：</b>{html.escape(blueprint.template_id)}；<b>课程：</b>"
                f"{html.escape(blueprint.course_id)}；<b>章节：</b>{html.escape(blueprint.chapter_range)}</p>"
                f"<p><b>题量/总分：</b>{sum(blueprint.question_counts.values())} / "
                f"{blueprint.required_total_score}；<b>题型：</b>{html.escape(json.dumps(blueprint.question_counts, ensure_ascii=False))}<br>"
                f"<b>难度：</b>{html.escape(json.dumps(blueprint.difficulty_counts, ensure_ascii=False))}；"
                f"<b>Batch：</b>{len(blueprint.batch_plan)}；<b>并发上限：</b>{blueprint.max_concurrency}</p>"
                f"<p><b>审核动作：</b>Blueprint={blueprint.blueprint_review_action}；Global={blueprint.global_review_action}</p>"
                f"<p><b>Track B 烟测 Query：</b>{html.escape(case.track_b_query_id)}</p>"
            )
            label = "Blueprint / 全局约束"
        elif record_id in targets:
            target = targets[record_id]
            evidence_text = "\n".join(
                [target.primary_evidence.gold_text]
                + [item.gold_text for item in target.supporting_evidence]
            )
            body = (
                f"<p><b>知识点：</b>{html.escape(target.knowledge_point.canonical_name)}<br>"
                f"<b>课程：</b>{html.escape(target.course_id)}；<b>角色：</b>{html.escape(target.content_role)}；"
                f"<b>题型：</b>{html.escape(', '.join(target.allowed_question_types))}；"
                f"<b>风险：</b>{html.escape(', '.join(target.risk_flags) or 'none')}</p>"
                f"<p><b>Evidence 原文：</b><br>{html.escape(evidence_text)}</p>"
                f"<p><b>Required Claims：</b><br>{html.escape(chr(10).join(target.required_claims))}<br>"
                f"<b>Optional Claims：</b>{html.escape(chr(10).join(target.optional_claims))}</p>"
                f"<p><b>Hard Negative：</b>{html.escape(', '.join(target.hard_negative_evidence_ids) or 'none')}<br>"
                f"<b>Hard Negative 原文：</b><br>{html.escape(chr(10).join(item.gold_text for item in target.hard_negative_evidence) or 'none')}<br>"
                f"<b>来源页：</b>{target.primary_evidence.page_start or 'null'}；"
                f"<b>来源类型：</b>{html.escape(target.primary_evidence.source_type)}</p>"
            )
            label = "Assessment Target"
        else:
            negative = negatives[record_id]
            body = f"<p><b>负例预期：</b>{html.escape(negative.expected_failure)}<br>"
            if isinstance(negative, P15InsufficientEvidenceCase):
                body += (
                    f"<b>省略 Evidence：</b>{html.escape(', '.join(negative.omitted_required_evidence_ids))}<br>"
                    f"<b>Provider/副作用：</b>{negative.provider_calls_allowed}/{negative.side_effects_allowed}"
                )
            else:
                body += (
                    f"<b>计算总分：</b>{negative.computed_total_score}；<b>要求总分：</b>{negative.required_total_score}<br>"
                    f"<b>Provider/副作用：</b>{negative.provider_calls_allowed}/{negative.side_effects_allowed}"
                )
            body += "</p>"
            label = "Fail-closed 合同负例"
        cards.append(
            f"<article class='card' data-record-id='{html.escape(record_id)}'><h2>{html.escape(record_id)}</h2>"
            f"<p class='tag'>{label}</p>{body}<details><summary>查看完整记录 JSON</summary><pre>"
            + html.escape(
                json.dumps(
                    (
                        cases[record_id].model_dump(mode="json")
                        if record_id in cases
                        else targets[record_id].model_dump(mode="json")
                        if record_id in targets
                        else negatives[record_id].model_dump(mode="json")
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            + "</pre></details>"
            + f"<label><input type='radio' name='{html.escape(record_id)}' value='approve'>通过</label> "
            + f"<label><input type='radio' name='{html.escape(record_id)}' value='return'>退回</label>"
            + "<textarea placeholder='退回原因/备注'></textarea></article>"
        )
    review_file = f"p15_{'second' if second_review else 'first'}_review_{bundle_sha256[:12]}.json"
    title = (
        "P15 CP-DS2 Exam Pilot 二轮盲化审核" if second_review else "P15 CP-DS2 Exam Pilot 首轮审核"
    )
    ids_json = json.dumps(review_ids, ensure_ascii=False)
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>{title}</title>
<style>body{{font-family:system-ui;max-width:1150px;margin:24px auto;color:#222}}.card{{border:1px solid #bbb;border-radius:8px;padding:18px;margin:18px 0}}.tag{{color:#555}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:12px;max-height:360px;overflow:auto}}textarea{{display:block;width:100%;min-height:55px;margin-top:8px}}.review-tools{{position:sticky;top:0;background:white;border:1px solid #888;padding:12px;z-index:2}}</style>
<h1>{title}</h1><p>Bundle SHA-256：<code>{bundle_sha256}</code></p>
<section class='review-tools'><b>审核记录</b><p>页面会自动保存选择；全部完成后可导出 JSON。退回必须填写原因。</p><button type='button' id='export-review'>导出本轮审核 JSON</button><span id='review-progress'></span></section>
{"".join(cards)}
<script>
(() => {{
  const bundle = {json.dumps(bundle_sha256)}; const reviewPass = {json.dumps("second" if second_review else "first")};
  const ids = {ids_json}; const filename = {json.dumps(review_file)}; const key = `coursepilot:p15:${{bundle}}:${{reviewPass}}`;
  const cards = [...document.querySelectorAll('.card')]; const read = () => {{ try {{ return JSON.parse(localStorage.getItem(key) || '{{}}'); }} catch (_) {{ return {{}}; }} }};
  const saved = read(); cards.forEach(card => {{ const id = card.dataset.recordId; const old = saved[id] || {{}}; if (old.decision) {{ const radio = card.querySelector(`input[value='${{old.decision}}']`); if (radio) radio.checked = true; }} card.querySelector('textarea').value = old.notes || ''; }});
  const collect = () => Object.fromEntries(cards.map(card => {{ const id = card.dataset.recordId; const radio = card.querySelector("input[type='radio']:checked"); return [id, {{decision: radio ? radio.value : '', notes: card.querySelector('textarea').value.trim()}}]; }}));
  const update = () => {{ const state = collect(); try {{ localStorage.setItem(key, JSON.stringify(state)); }} catch (_) {{}} document.getElementById('review-progress').textContent = ` 已完成 ${{Object.values(state).filter(x => x.decision).length}} / ${{ids.length}}`; }};
  cards.forEach(card => card.addEventListener('input', update)); update();
  document.getElementById('export-review').addEventListener('click', () => {{ const state = collect(); const missing = ids.filter(id => !state[id].decision); const noReason = ids.filter(id => state[id].decision === 'return' && !state[id].notes); if (missing.length || noReason.length) {{ alert(`无法导出：未选择 ${{missing.length}} 条；退回无原因 ${{noReason.length}} 条。`); return; }} const payload = {{schema_version:'coursepilot.p15-review-decisions.v1',bundle_sha256:bundle,review_pass:reviewPass,expected_record_ids:ids,reviewer_id:'course_owner',reviewed_at:new Date().toISOString(),attestation_source:'html_export',decisions:ids.map(id => ({{record_id:id,decision:state[id].decision === 'approve' ? 'pass' : 'return',notes:state[id].notes}}))}}; const blob = new Blob([JSON.stringify(payload,null,2)+'\\n'],{{type:'application/json'}}); const link = document.createElement('a'); link.href=URL.createObjectURL(blob); link.download=filename; link.click(); setTimeout(() => URL.revokeObjectURL(link.href),0); }});
}})();</script></html>"""


def generate(root: Path) -> dict[str, Any]:
    evidence, knowledge_points, hashes = _load_upstream(root)
    calibration = knowledge_points.pop("__calibration__")
    track_b = _validate_track_b_queries(root)

    configs: list[dict[str, Any]] = [
        {
            "case_id": "p15-exam-01-nerf-gaussian-assignment",
            "course_id": DOCX_COURSE,
            "template_id": "exam_chapter_assignment_v1",
            "chapter_range": "6.2.2—6.2.3 NeRF与3D高斯点染三维重建",
            "counts": {
                "single_choice": 2,
                "multiple_choice": 2,
                "judgement": 2,
                "short_answer": 2,
            },
            "scores": {
                "single_choice": 4,
                "multiple_choice": 6,
                "judgement": 5,
                "short_answer": 10,
            },
            "difficulty_distribution": {"easy": 0.25, "medium": 0.5, "hard": 0.25},
            "difficulty_counts": {"easy": 2, "medium": 4, "hard": 2},
            "blueprint_action": "approve",
            "global_action": "approve",
            "track": track_b["docx"],
            "targets": [
                (
                    "gold-kp-6480379262a13e32e1bd3bc0e556f609",
                    "gold-ev-335662f3142fb805ce0d560f4eccdd7a",
                    "application",
                    ["single_choice", "short_answer"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-fccb808f30813de371dd5645d2498922",
                    "gold-ev-6f70e7f62938bf78ba45c307de1adaef",
                    "formula",
                    ["multiple_choice", "short_answer"],
                    ["medium", "hard"],
                    ["formula"],
                ),
                (
                    "gold-kp-e7ed3f70cf3b923fa46d3ed2d9f37486",
                    "gold-ev-488132baeca3f0acc28854e2d6ab51b8",
                    "formula",
                    ["judgement", "short_answer"],
                    ["medium", "hard"],
                    ["formula"],
                ),
                (
                    "gold-kp-fb9db166a268fd3b93e2b6907fd0d5ed",
                    "gold-ev-6b00087df687acba07757febbd553d19",
                    "definition",
                    ["single_choice", "multiple_choice"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-ebd0de0280047285fb5153e413c9829b",
                    "gold-ev-e21068d14748c7ffc033f2ec37f88501",
                    "formula",
                    ["multiple_choice", "short_answer"],
                    ["medium", "hard"],
                    ["formula"],
                ),
                (
                    "gold-kp-0ee4716d1cd566faa82e513b9bb4526d",
                    "gold-ev-ce0b58d4e9bed39607616060acc59261",
                    "procedure",
                    ["judgement", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
            ],
        },
        {
            "case_id": "p15-exam-02-ai-agi-quiz",
            "course_id": PDF_COURSE,
            "template_id": "exam_unit_quiz_v1",
            "chapter_range": "1.1.2—1.2.3 人工智能定义、发展与通用人工智能",
            "counts": {
                "single_choice": 4,
                "multiple_choice": 3,
                "judgement": 3,
                "short_answer": 2,
            },
            "scores": {
                "single_choice": 3,
                "multiple_choice": 4,
                "judgement": 2,
                "short_answer": 10,
            },
            "difficulty_distribution": {"easy": 1 / 3, "medium": 0.5, "hard": 1 / 6},
            "difficulty_counts": {"easy": 4, "medium": 6, "hard": 2},
            "blueprint_action": "edit_resume",
            "global_action": "approve",
            "track": track_b["pdf"],
            "targets": [
                (
                    "gold-kp-9fea9aad0349530b8fecd24d8685f488",
                    "gold-ev-47ac1a377be899cf37f3403ae7f7568d",
                    "definition",
                    ["single_choice", "short_answer"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-159b2e8e8d4afce2bb39c5ded345b659",
                    "gold-ev-7898c01ada50d223ac64a6779dc775d3",
                    "definition",
                    ["judgement", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-4e659c3501ecbb1ce06e3455ee4b9e51",
                    "gold-ev-38cd360af1237ea0f2ab5fa2a180c208",
                    "example",
                    ["single_choice", "judgement"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-90ccc5c8790242574c98edd956313bd0",
                    "gold-ev-a95425415c717538eb8e12984a3caaef",
                    "example",
                    ["single_choice", "short_answer"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-dda5c1fe396a386e759d371a71e90a82",
                    "gold-ev-63b2a09988aa11ff3c6d483a0b162917",
                    "application",
                    ["multiple_choice", "judgement"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-9042005569bcb8403b20f3b7e22b43db",
                    "gold-ev-e45b2242f6d079448a93922b96e5c4d0",
                    "definition",
                    ["single_choice", "short_answer"],
                    ["medium", "hard"],
                    ["ocr"],
                ),
                (
                    "gold-kp-b49206a1595be66884b9d6fc3a61684f",
                    "gold-ev-ae3c8bbcde5fb29d3c00dbf07a25b002",
                    "principle",
                    ["multiple_choice", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-178b3f85ded00640ce7ef7752cc2140a",
                    "gold-ev-e9e4e1f98f3694dcc2445c4623bb72c9",
                    "principle",
                    ["multiple_choice", "judgement"],
                    ["medium", "hard"],
                    [],
                ),
            ],
        },
        {
            "case_id": "p15-exam-03-llm-midterm",
            "course_id": DOCX_COURSE,
            "template_id": "exam_midterm_final_v1",
            "chapter_range": "5.1.1—5.3.4 大模型、训练数据、微调与对齐",
            "counts": {
                "single_choice": 10,
                "multiple_choice": 5,
                "judgement": 5,
                "short_answer": 5,
            },
            "scores": {
                "single_choice": 2,
                "multiple_choice": 4,
                "judgement": 2,
                "short_answer": 10,
            },
            "difficulty_distribution": {"easy": 0.32, "medium": 0.48, "hard": 0.2},
            "difficulty_counts": {"easy": 8, "medium": 12, "hard": 5},
            "blueprint_action": "replan",
            "global_action": "edit_resume",
            "track": track_b["docx"],
            "targets": [
                (
                    "gold-kp-b848f1b022a479c770521458bce143a4",
                    "gold-ev-3ff41ae49e326e1cc942ca04e5ed998c",
                    "definition",
                    ["single_choice", "short_answer"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-02c0be5ab5dca476eed78a23ad8f3726",
                    "gold-ev-035088153234134744f10d335a333cc0",
                    "table",
                    ["multiple_choice", "short_answer"],
                    ["medium", "hard"],
                    ["table"],
                ),
                (
                    "gold-kp-07c87ce697fc1dd864b09c4c99776978",
                    "gold-ev-365b0dc23cff9bb089df5923e2212264",
                    "principle",
                    ["judgement", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-c4bccb05477b6493be85edff2aeec2a4",
                    "gold-ev-c4302e898ef633d4ffb54fd4fc102e01",
                    "application",
                    ["single_choice", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-c55066739a5ac77a2f2f7298840d80a6",
                    "gold-ev-5c3010622081949981b20043ffc9cdd4",
                    "application",
                    ["single_choice", "judgement"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-27811de0b82ecc5959117325f79cb544",
                    "gold-ev-9e3623c3ff225b129b6e1d87ac893905",
                    "procedure",
                    ["single_choice", "short_answer"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-fc62fc1858f986fdb9c48fd5c9e7eb46",
                    "gold-ev-75d22d8bcfbf8c36e0066355d522c1c2",
                    "definition",
                    ["single_choice", "multiple_choice"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-3a201b005a2597cc062d5c8b79227c96",
                    "gold-ev-bd7d355279cc06aac5841601572cfe04",
                    "principle",
                    ["multiple_choice", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-c4d8dc4599f8925448d68a3767a83665",
                    "gold-ev-f622172906b893ec87c367db5ea298b3",
                    "definition",
                    ["single_choice", "short_answer"],
                    ["easy", "medium"],
                    [],
                ),
                (
                    "gold-kp-863d84db226b93cbb6c7dd9d69081d79",
                    "gold-ev-7ca952b51845ec8726626df3371c02a6",
                    "procedure",
                    ["single_choice", "multiple_choice"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-080644a6db95884d487495ae1597e84b",
                    "gold-ev-adecfc060732ab29684a055efdaacecc",
                    "principle",
                    ["judgement", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
                (
                    "gold-kp-01fac9e8c352226a5bc4f792c8965856",
                    "gold-ev-1be29628ef3d24c8ac4e22d1e444c7fb",
                    "procedure",
                    ["multiple_choice", "short_answer"],
                    ["medium", "hard"],
                    [],
                ),
            ],
        },
    ]

    targets: list[P15AssessmentTarget] = []
    cases: list[P15ExamPilotCase] = []
    contexts: list[P15ContextFixture] = []
    for config in configs:
        target_models: list[P15AssessmentTarget] = []
        for index, (kp_id, evidence_id, role, allowed, difficulty, risks) in enumerate(
            config["targets"], 1
        ):
            if kp_id not in calibration:
                raise ValueError(f"P15 target uses DS3 Holdout: {kp_id}")
            kp = knowledge_points[kp_id]
            ev = evidence[evidence_id]
            if kp["course_id"] != config["course_id"] or ev["course_id"] != config["course_id"]:
                raise ValueError(f"P15 target crosses course boundary: {kp_id}/{evidence_id}")
            target = _target(
                target_id=f"p15-target-{len(targets) + 1:02d}",
                case_id=config["case_id"],
                kp=kp,
                evidence=evidence,
                evidence_ids=[evidence_id],
                role=role,
                allowed_types=allowed,
                difficulty_range=difficulty,
                risks=risks,
                hard_negative_ids=(
                    ["gold-ev-2207b94aec4a32d1c12dbba4d33c4de0"]
                    if config["course_id"] == DOCX_COURSE
                    else ["gold-ev-73452f80b793aba65cdb9b1032838d27"]
                ),
                hard_negative_evidence=evidence,
                hashes=hashes,
            )
            target_models.append(target)
            targets.append(target)
        target_ids = [target.target_id for target in target_models]
        blueprint = P15BlueprintGold(
            case_id=config["case_id"],
            course_id=config["course_id"],
            template_id=config["template_id"],
            chapter_range=config["chapter_range"],
            question_counts=config["counts"],
            score_per_question=config["scores"],
            difficulty_distribution=config["difficulty_distribution"],
            difficulty_counts=config["difficulty_counts"],
            required_total_score=sum(
                config["counts"][key] * config["scores"][key] for key in config["counts"]
            ),
            required_knowledge_point_ids=[
                target.knowledge_point.gold_kp_id for target in target_models
            ],
            required_evidence_ids=[target.primary_evidence.evidence_id for target in target_models],
            target_ids=target_ids,
            batch_plan=_batch_plan(config["case_id"], config["counts"], target_ids),
            context_package_id=f"ctx-{config['case_id']}",
            max_concurrency=3,
            blueprint_review_action=config["blueprint_action"],
            global_review_action=config["global_action"],
            source_provenance=[
                f"approved/ds2/p06_evidence.json:{hashes['ds2']}",
                f"approved/ds3/p07_knowledge_points.json:{hashes['ds3']}",
                f"provenance/ds3_p07_split.json:{hashes['ds3_split']}",
            ],
        )
        case = P15ExamPilotCase(
            record_id=config["case_id"],
            blueprint=blueprint,
            track_b_query_id=config["track"],
            target_ids=target_ids,
            required_interrupts=["exam_blueprint_review", "exam_global_review"],
        )
        cases.append(case)
        contexts.append(
            _context(
                context_id=blueprint.context_package_id,
                case_id=config["case_id"],
                course_id=config["course_id"],
                targets=target_models,
            )
        )

    dataset = CPDS2P15PilotDataset(cases=cases, targets=targets)
    fixtures = P15FixtureBundle(
        context_fixtures=contexts,
        insufficient_evidence_case=P15InsufficientEvidenceCase(
            record_id="p15-negative-insufficient-evidence",
            case_id=cases[0].record_id,
            course_id=DOCX_COURSE,
            required_target_ids=[cases[0].target_ids[0], cases[0].target_ids[-1]],
            omitted_required_evidence_ids=[cases[0].blueprint.required_evidence_ids[-1]],
            context_package_id=contexts[0].context_package_id,
        ),
        constraint_conflict_case=P15ConstraintConflictCase(
            record_id="p15-negative-constraint-conflict",
            case_id=cases[1].record_id,
            course_id=PDF_COURSE,
            question_counts={
                "single_choice": 4,
                "multiple_choice": 3,
                "judgement": 3,
                "short_answer": 2,
            },
            score_per_question={
                "single_choice": 3,
                "multiple_choice": 4,
                "judgement": 2,
                "short_answer": 10,
            },
            required_total_score=55,
            computed_total_score=50,
        ),
    )
    pilot_path = root / PILOT_PATH
    fixture_path = root / FIXTURE_PATH
    atomic_write_json(pilot_path, dataset.model_dump(mode="json"))
    atomic_write_json(fixture_path, fixtures.model_dump(mode="json"))
    bundle_sha = _digest({"pilot": sha256_file(pilot_path), "fixtures": sha256_file(fixture_path)})
    review_root = root / "storage_eval/cpds2_p15_review" / bundle_sha
    all_review_ids = (
        [case.record_id for case in cases]
        + [target.target_id for target in targets]
        + [
            fixtures.insufficient_evidence_case.record_id,
            fixtures.constraint_conflict_case.record_id,
        ]
    )
    high_risk = {
        target.target_id
        for target in targets
        if target.risk_flags or target.hard_negative_evidence_ids
    }
    stable_remaining = sorted(
        [target.target_id for target in targets if target.target_id not in high_risk],
        key=lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest(),
    )
    second_ids = (
        [case.record_id for case in cases]
        + sorted(
            [
                fixtures.insufficient_evidence_case.record_id,
                fixtures.constraint_conflict_case.record_id,
            ]
        )
        + sorted(high_risk)
        + stable_remaining[: max(1, (len(stable_remaining) + 4) // 5)]
    )
    atomic_write_text(
        review_root / "index.html",
        _render_review(dataset, fixtures, bundle_sha, all_review_ids, second_review=False),
    )
    atomic_write_text(
        review_root / "second_review.html",
        _render_review(dataset, fixtures, bundle_sha, second_ids, second_review=True),
    )
    atomic_write_json(
        review_root / "manual_review_template_first.json",
        cast(
            JsonValue,
            {
                "schema_version": "coursepilot.p15-review-decisions.v1",
                "bundle_sha256": bundle_sha,
                "review_pass": "first",
                "expected_record_ids": all_review_ids,
                "decisions": [
                    {"record_id": item, "decision": "", "notes": ""} for item in all_review_ids
                ],
            },
        ),
    )
    atomic_write_json(
        review_root / "manual_review_template_second.json",
        cast(
            JsonValue,
            {
                "schema_version": "coursepilot.p15-review-decisions.v1",
                "bundle_sha256": bundle_sha,
                "review_pass": "second",
                "expected_record_ids": second_ids,
                "decisions": [
                    {"record_id": item, "decision": "", "notes": ""} for item in second_ids
                ],
            },
        ),
    )
    manifest: dict[str, Any] = {
        "schema_version": "coursepilot.p15-cp-ds2-bundle-manifest.v1",
        "dataset_id": "coursepilot-eval",
        "dataset_version": "p15-pilot-r1",
        "approval_scope": "cp_ds2_p15_pilot_input_only",
        "candidate_hashes": {
            "pilot": sha256_file(pilot_path),
            "fixtures": sha256_file(fixture_path),
        },
        "bundle_sha256": bundle_sha,
        "record_ids": all_review_ids,
        "second_review_record_ids": second_ids,
        "counts": {"cases": 3, "targets": 26, "negative_cases": 2, "planned_questions": 45},
        "track_b_smoke_queries": track_b,
        "upstream_hashes": hashes,
        "gold_promotion": False,
        "external_provider_calls": 0,
    }
    atomic_write_json(root / MANIFEST_PATH, cast(JsonValue, manifest))
    report = f"""# Pre-P15 CP-DS2 Exam Pilot Candidate Review

任务：`ED-PRE15-CPDS2-T01` 至 `ED-PRE15-CPDS2-T08`

本批生成 3 条 Exam Pilot Candidate、26 个 Assessment Target、3 个固定 Context 和 2 条合同负例。
只使用两个 Approved CourseRAG Primary 课程；未调用 Provider、未读取 Test/Holdout、未使用 P14 运行输出。

- Pilot Candidate SHA-256：`{manifest["candidate_hashes"]["pilot"]}`
- Fixture SHA-256：`{manifest["candidate_hashes"]["fixtures"]}`
- Bundle SHA-256：`{bundle_sha}`
- 题量计划：8 / 12 / 25，共45题；总分50 / 50 / 100
- 首轮审核：`storage_eval/cpds2_p15_review/{bundle_sha}/index.html`
- 二轮审核：`storage_eval/cpds2_p15_review/{bundle_sha}/second_review.html`
- 手工模板：同目录 `manual_review_template_first.json` 和 `manual_review_template_second.json`

当前状态为 Candidate。请重点检查 Blueprint 的题量/分值/难度计算、KP/Evidence 原文、Required Claims、公式/表格/OCR 风险、Hard Negative 和两个 fail-closed 负例。收到绑定完整 Bundle SHA-256 的两轮通过确认后，才会生成 Approved P15 输入包。
"""
    # Keep the handoff report readable even on consoles with a legacy code page.
    report = f"""# Pre-P15 CP-DS2 Exam Pilot Candidate Review

Tasks: ED-PRE15-CPDS2-T01 through ED-PRE15-CPDS2-T08

This candidate contains 3 Exam Pilot blueprints, 26 Assessment Targets, 3 fixed Context
fixtures, and 2 fail-closed contract negatives. Only the two Approved CourseRAG Primary
courses are used. No Provider, Test/Holdout, P14 runtime output, or external facts were used.

- Pilot Candidate SHA-256: `{manifest["candidate_hashes"]["pilot"]}`
- Fixture SHA-256: `{manifest["candidate_hashes"]["fixtures"]}`
- Bundle SHA-256: `{bundle_sha}`
- Planned questions: 8 / 12 / 25 (45 total); total scores: 50 / 50 / 100
- First review: `storage_eval/cpds2_p15_review/{bundle_sha}/index.html`
- Second review: `storage_eval/cpds2_p15_review/{bundle_sha}/second_review.html`
- Manual fallbacks: `manual_review_template_first.json` and `manual_review_template_second.json`

Review blueprint arithmetic, question-type and difficulty counts, KP/Evidence source text,
Required Claims, formula/table/OCR risk flags, Hard Negative source text, and both fail-closed
negative cases. This is Candidate-only; Approved P15 input is written only after two complete
owner review passes and exact Bundle approval.
"""
    atomic_write_text(root / REPORT_PATH, report)
    atomic_write_json(
        root / MANIFEST_PATH,
        cast(
            JsonValue,
            {
                **manifest,
                "candidate_record_sha256": {
                    **{case.record_id: record_digest(case) for case in cases},
                    **{target.target_id: record_digest(target) for target in targets},
                },
            },
        ),
    )
    return {
        "pilot_sha256": manifest["candidate_hashes"]["pilot"],
        "fixtures_sha256": manifest["candidate_hashes"]["fixtures"],
        "bundle_sha256": bundle_sha,
        "review_path": str(review_root.relative_to(root)).replace("\\", "/"),
        "record_count": len(all_review_ids),
        "second_review_count": len(second_ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(generate(args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
