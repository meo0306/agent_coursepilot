from __future__ import annotations

import json
from pathlib import Path

from coursepilot.domain.exam import ExamQuestion
from evaluation.p15_exam_eval import build_blueprint
from evaluation.p15_targeted_repair import build_delta_review_package, scan_existing

ROOT = Path(__file__).resolve().parents[2]


def test_targeted_repair_preflight_is_network_free_and_finds_multi_select_contract(
    tmp_path: Path,
) -> None:
    dataset = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    targets = {item["target_id"]: item for item in dataset["targets"]}
    cases: dict[str, object] = {}
    expected_multi = 0
    for case in dataset["cases"]:
        blueprint = build_blueprint(case, targets)
        questions: list[dict[str, object]] = []
        for number, slot in enumerate(blueprint.slots, start=1):
            is_choice = slot.question_type in {"single_choice", "multiple_choice"}
            if slot.question_type == "multiple_choice":
                expected_multi += 1
            question = ExamQuestion(
                question_id=f"q:{slot.slot_id}",
                slot_id=slot.slot_id,
                question_number=number,
                question_type=slot.question_type,
                score=slot.score,
                difficulty=slot.difficulty,
                content_role=slot.content_role,
                stem=f"Independent question {number} for {slot.slot_id}",
                options={"A": f"a-{number}", "B": f"b-{number}", "C": f"c-{number}"}
                if is_choice
                else {},
                answer="A" if is_choice else f"answer-{number}-{slot.slot_id}",
                explanation=f"Explanation {number} for {slot.slot_id}",
                knowledge_point_ids=slot.knowledge_point_ids,
                evidence_ids=slot.evidence_ids,
            )
            questions.append(question.model_dump(mode="json"))
        cases[f"p3:{case['record_id']}"] = {
            "case_id": case["record_id"],
            "status": "completed",
            "questions": questions,
        }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"status": "completed", "cases": cases}), encoding="utf-8")

    result = scan_existing(ROOT, source_state=state_path)

    assert result["external_calls_made"] == 0
    assert result["repair_target_count"] >= expected_multi
    # This deliberately minimal synthetic corpus reuses the same answer pattern
    # across every slot, so the semantic-duplicate guard may add more targets
    # than the approved real closure. The preflight must report that condition
    # without making a network call; the production cap remains unchanged.
    if result["repair_target_count"] > result["maximum_allowed_targets"]:
        assert result["within_target_limit"] is False
        assert result["stop_reason"] == "P15_TARGETED_REPAIR_SCOPE_EXCEEDED"
    issue_codes = [
        code
        for case in result["cases"]
        for codes in case["question_issue_codes"].values()
        for code in codes
    ]
    assert issue_codes.count("EXAM_MULTIPLE_CHOICE_CARDINALITY") == expected_multi

    case_report = result["cases"][0]
    question_id = case_report["repair_question_ids"][0]
    source_case = cases[f"p3:{case_report['case_id']}"]
    repaired_questions = json.loads(json.dumps(source_case["questions"]))
    repaired = next(item for item in repaired_questions if item["question_id"] == question_id)
    repaired["stem"] += " repaired"
    repair_result = {
        "preflight": result,
        "cases": [
            {
                "case_id": case_report["case_id"],
                "questions": repaired_questions,
                "repaired_question_ids": [question_id],
            }
        ],
    }
    package = build_delta_review_package(
        source_state={"cases": cases},
        result=repair_result,
        output_dir=tmp_path / "review",
    )

    assert package is not None
    assert package["review_question_count"] == 1
    review_html = (tmp_path / "review/review.html").read_text(encoding="utf-8")
    assert 'id="download-progress"' in review_html
    assert 'id="download"' in review_html
    assert "addEventListener('click',finalDownload)" in review_html
    assert "new Blob" in review_html
    assert "p15_targeted_repair_review_decisions.json" in review_html
