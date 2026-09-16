"""Bounded P15 owner-review closure over the existing three P3 exam artifacts."""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.exam import ExamQuestion, QuestionBatchPlan
from coursepilot.llm import collect_coursepilot_llm_metadata
from coursepilot.validation.exam import validate_exam_global
from evaluation.p15_exam_eval import (
    DATASET,
    P15ResponseCheckpoint,
    ProviderBatch,
    _question_payload,
    build_blueprint,
)

DEFAULT_SOURCE_STATE = Path("storage_eval/p15_provider_smoke/checkpoint/state.json")
DEFAULT_OUTPUT = Path("storage_eval/p15_targeted_repair")
MAX_TARGETS = 20
MAX_COST_CNY = 0.50
MAX_INPUT_TOKENS = 100_000
MAX_OUTPUT_TOKENS = 150_000
MAX_REQUESTS = 20

RESIDUAL_TARGET_SUFFIXES = {
    "p15-exam-02-ai-agi-quiz": ("batch-multiple_choice-01:slot-1",),
    "p15-exam-03-llm-midterm": ("batch-short_answer-01:slot-5",),
}


def _load_inputs(root: Path, source_state: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = json.loads((root / DATASET).read_text(encoding="utf-8"))
    state = json.loads(source_state.read_text(encoding="utf-8"))
    if len(dataset.get("cases", [])) != 3:
        raise ValueError("P15 closure requires the three Approved CP-DS2 Pilot cases")
    if state.get("status") != "completed":
        raise ValueError("P15 source checkpoint is not completed")
    return dataset, state


def scan_existing(
    root: Path,
    *,
    source_state: Path = DEFAULT_SOURCE_STATE,
) -> dict[str, Any]:
    dataset, state = _load_inputs(root, source_state)
    targets = {item["target_id"]: item for item in dataset["targets"]}
    rows: list[dict[str, Any]] = []
    all_target_ids: set[str] = set()
    for case in dataset["cases"]:
        case_id = case["record_id"]
        source = state["cases"].get(f"p3:{case_id}")
        if not isinstance(source, dict) or source.get("status") != "completed":
            raise ValueError(f"P15 source case is not complete: {case_id}")
        blueprint = build_blueprint(case, targets)
        questions = [ExamQuestion.model_validate(item) for item in source["questions"]]
        report = validate_exam_global(
            blueprint,
            questions,
            resolvable_evidence_ids=set(blueprint.evidence_ids),
        )
        case_targets = set(report.question_issue_codes)
        all_target_ids.update(case_targets)
        rows.append(
            {
                "case_id": case_id,
                "question_count": len(questions),
                "repair_question_ids": sorted(case_targets),
                "question_issue_codes": report.question_issue_codes,
                "global_errors": report.errors,
                "source_questions_sha256": canonical_sha256(
                    [item.model_dump(mode="json") for item in questions]
                ),
            }
        )
    target_count = len(all_target_ids)
    result = {
        "schema_version": "coursepilot.p15-targeted-repair-preflight.v1",
        "external_calls_made": 0,
        "source_state": str(source_state.resolve()),
        "source_state_sha256": canonical_sha256(state),
        "repair_target_count": target_count,
        "maximum_allowed_targets": MAX_TARGETS,
        "within_target_limit": target_count <= MAX_TARGETS,
        "estimated_budget": {
            "maximum_requests": target_count,
            "estimated_input_tokens": target_count * 3_500,
            "estimated_output_tokens": target_count * 5_000,
            "estimated_cost_cny": round(target_count * (3_500 + 2 * 5_000) / 1_000_000, 6),
            "hard_limits": {
                "max_cost_cny": MAX_COST_CNY,
                "max_input_tokens": MAX_INPUT_TOKENS,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "max_requests": MAX_REQUESTS,
            },
        },
        "cases": rows,
    }
    if target_count > MAX_TARGETS:
        result["stop_reason"] = "P15_TARGETED_REPAIR_SCOPE_EXCEEDED"
    return result


async def _run_real_async(
    root: Path,
    *,
    source_state: Path,
    output_dir: Path,
    resume: bool,
) -> dict[str, Any]:
    from coursepilot.llm import generate_structured

    preflight = scan_existing(root, source_state=source_state)
    if not preflight["within_target_limit"]:
        raise RuntimeError("P15_TARGETED_REPAIR_SCOPE_EXCEEDED")
    dataset, state = _load_inputs(root, source_state)
    targets = {item["target_id"]: item for item in dataset["targets"]}
    checkpoint = P15ResponseCheckpoint(
        output_dir / "checkpoint",
        resume=resume,
        max_cost_cny=MAX_COST_CNY,
        max_input_tokens=MAX_INPUT_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        max_requests=MAX_REQUESTS,
    )
    cases: list[dict[str, Any]] = []

    async def repair_question(
        original: ExamQuestion,
        issue_ids: list[str],
        all_questions: list[ExamQuestion],
        blueprint: Any,
    ) -> ExamQuestion:
        slot = next(item for item in blueprint.slots if item.slot_id == original.slot_id)
        batch = QuestionBatchPlan(
            batch_id=f"repair:{slot.slot_id}",
            ordinal=0,
            question_type=slot.question_type,
            slot_ids=[slot.slot_id],
        )
        payload = _question_payload(blueprint, batch, targets, variant="p15:owner_targeted_repair")
        payload.update(
            {
                "repair_issue_ids": issue_ids,
                "original_question": original.model_dump(mode="json"),
                "allowed_fields": [
                    "stimulus",
                    "stem",
                    "options",
                    "option_assessments",
                    "answer",
                    "explanation",
                ],
                "forbidden_overlap": [
                    {
                        "question_id": item.question_id,
                        "stem": item.stem,
                        "answer": item.answer,
                        "options": item.options,
                    }
                    for item in all_questions
                    if item.question_id != original.question_id
                ],
            }
        )
        result = await asyncio.to_thread(
            generate_structured,
            prompt_name="exam/p15_repair_question",
            output_schema=ProviderBatch,
            payload=payload,
            fallback=lambda: (_ for _ in ()).throw(RuntimeError("P15_FALLBACK_FORBIDDEN")),
            profile_id="content_repair_main",
            allow_fallback=False,
        )
        if len(result.questions) != 1:
            raise ValueError("P15_REPAIR_MUST_RETURN_ONE_QUESTION")
        item = result.questions[0]
        if item.slot_id != original.slot_id:
            raise ValueError("P15_REPAIR_SLOT_ID_CHANGED")
        return original.model_copy(
            update={
                "stimulus": item.stimulus,
                "stem": item.stem,
                "options": item.options,
                "option_assessments": item.option_assessments,
                "answer": item.answer,
                "explanation": item.explanation,
            }
        )

    with collect_coursepilot_llm_metadata(thread_id="p15:targeted-repair", checkpoint=checkpoint):
        for case in dataset["cases"]:
            case_id = case["record_id"]
            source = state["cases"][f"p3:{case_id}"]
            blueprint = build_blueprint(case, targets)
            original_questions = [ExamQuestion.model_validate(item) for item in source["questions"]]
            original_hashes = {
                item.question_id: canonical_sha256(item.model_dump(mode="json"))
                for item in original_questions
            }
            report = validate_exam_global(
                blueprint,
                original_questions,
                resolvable_evidence_ids=set(blueprint.evidence_ids),
            )
            # This closure is intentionally narrower than the reusable repair
            # planner. Freeze the exact preflight targets so a failed duplicate
            # repair cannot redirect the next call to the other side of the
            # duplicate pair and silently expand the approved scope.
            repaired_questions = list(original_questions)
            events: list[str] = []
            target_ids = set(report.question_issue_codes)
            for index, original in enumerate(original_questions):
                if original.question_id not in target_ids:
                    continue
                try:
                    candidate = await repair_question(
                        original,
                        report.question_issue_codes[original.question_id],
                        list(repaired_questions),
                        blueprint,
                    )
                except Exception as exc:
                    events.append(f"FAILED:{original.question_id}:{type(exc).__name__}")
                    continue
                if candidate == original:
                    events.append(f"NOOP:{original.question_id}")
                    continue
                repaired_questions[index] = candidate
                events.append(f"REPAIRED:{original.question_id}")
            final_report = validate_exam_global(
                blueprint,
                repaired_questions,
                resolvable_evidence_ids=set(blueprint.evidence_ids),
            )
            repaired_ids = {
                item.question_id
                for item in repaired_questions
                if canonical_sha256(item.model_dump(mode="json"))
                != original_hashes[item.question_id]
            }
            unchanged_hashes_preserved = all(
                canonical_sha256(item.model_dump(mode="json")) == original_hashes[item.question_id]
                for item in repaired_questions
                if item.question_id not in repaired_ids
            )
            case_result = {
                "case_id": case_id,
                "status": "completed" if final_report.passed else "needs_review",
                "source_questions_sha256": canonical_sha256(
                    [item.model_dump(mode="json") for item in original_questions]
                ),
                "questions_sha256": canonical_sha256(
                    [item.model_dump(mode="json") for item in repaired_questions]
                ),
                "questions": [item.model_dump(mode="json") for item in repaired_questions],
                "repaired_question_ids": sorted(repaired_ids),
                "repair_events": events,
                "unchanged_hashes_preserved": unchanged_hashes_preserved,
                "global_report": final_report.model_dump(mode="json"),
            }
            checkpoint.save_case(case_id, case_result, experiment="targeted_repair")
            cases.append(case_result)

    input_tokens, output_tokens, requests = checkpoint.provider_usage_totals()
    cost = input_tokens / 1_000_000 + output_tokens * 2 / 1_000_000
    completed = all(item["status"] == "completed" for item in cases)
    result = {
        "schema_version": "coursepilot.p15-targeted-repair-report.v1",
        "status": "completed" if completed else "needs_review",
        "completed_at": datetime.now(UTC).isoformat(),
        "preflight": preflight,
        "actual": {
            "provider_requests": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_cny": round(cost, 6),
        },
        "hard_cap_ok": requests <= MAX_REQUESTS
        and input_tokens <= MAX_INPUT_TOKENS
        and output_tokens <= MAX_OUTPUT_TOKENS
        and cost <= MAX_COST_CNY,
        "all_global_validation_passed": completed,
        "cases": cases,
    }
    checkpoint.finish(result)
    return result


async def _run_residual_async(
    root: Path,
    *,
    source_state: Path,
    output_dir: Path,
    resume: bool,
) -> dict[str, Any]:
    """Run the two explicitly approved second-round repairs.

    This consumes the existing closure checkpoint and sends only the two
    already-identified question IDs. It never reopens the original 17-target
    scope or regenerates a batch/exam.
    """
    from coursepilot.llm import generate_structured

    base_report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    if not base_report.get("hard_cap_ok"):
        raise RuntimeError("P15_TARGETED_REPAIR_BASE_REPORT_OUTSIDE_CAP")
    dataset, _ = _load_inputs(root, source_state)
    targets = {item["target_id"]: item for item in dataset["targets"]}
    checkpoint = P15ResponseCheckpoint(
        output_dir / "checkpoint",
        resume=resume,
        max_cost_cny=MAX_COST_CNY,
        max_input_tokens=MAX_INPUT_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        max_requests=MAX_REQUESTS,
    )
    cases: list[dict[str, Any]] = []

    async def repair_question(
        original: ExamQuestion,
        issue_ids: list[str],
        all_questions: list[ExamQuestion],
        blueprint: Any,
    ) -> ExamQuestion:
        slot = next(item for item in blueprint.slots if item.slot_id == original.slot_id)
        batch = QuestionBatchPlan(
            batch_id=f"repair-r2:{slot.slot_id}",
            ordinal=0,
            question_type=slot.question_type,
            slot_ids=[slot.slot_id],
        )
        payload = _question_payload(
            blueprint,
            batch,
            targets,
            variant="p15:owner_targeted_repair_r2",
        )
        payload.update(
            {
                "repair_issue_ids": issue_ids,
                "original_question": original.model_dump(mode="json"),
                "allowed_fields": [
                    "stimulus",
                    "stem",
                    "options",
                    "option_assessments",
                    "answer",
                    "explanation",
                ],
                "forbidden_overlap": [
                    {
                        "question_id": item.question_id,
                        "stem": item.stem,
                        "answer": item.answer,
                        "options": item.options,
                    }
                    for item in all_questions
                    if item.question_id != original.question_id
                ],
            }
        )
        result = await asyncio.to_thread(
            generate_structured,
            prompt_name="exam/p15_repair_question",
            output_schema=ProviderBatch,
            payload=payload,
            fallback=lambda: (_ for _ in ()).throw(RuntimeError("P15_FALLBACK_FORBIDDEN")),
            profile_id="content_repair_main",
            allow_fallback=False,
        )
        if len(result.questions) != 1:
            raise ValueError("P15_REPAIR_MUST_RETURN_ONE_QUESTION")
        item = result.questions[0]
        if item.slot_id != original.slot_id:
            raise ValueError("P15_REPAIR_SLOT_ID_CHANGED")
        return original.model_copy(
            update={
                "stimulus": item.stimulus,
                "stem": item.stem,
                "options": item.options,
                "option_assessments": item.option_assessments,
                "answer": item.answer,
                "explanation": item.explanation,
            }
        )

    with collect_coursepilot_llm_metadata(
        thread_id="p15:targeted-repair-r2", checkpoint=checkpoint
    ):
        for base_case in base_report["cases"]:
            case_id = base_case["case_id"]
            case_spec = next(item for item in dataset["cases"] if item["record_id"] == case_id)
            blueprint = build_blueprint(case_spec, targets)
            questions = [ExamQuestion.model_validate(item) for item in base_case["questions"]]
            before_hashes = {
                item.question_id: canonical_sha256(item.model_dump(mode="json"))
                for item in questions
            }
            events = list(base_case.get("repair_events", []))
            residual_ids = {
                item.question_id
                for item in questions
                if any(
                    item.question_id.endswith(suffix)
                    for suffix in RESIDUAL_TARGET_SUFFIXES.get(case_id, ())
                )
            }
            issue_map: dict[str, list[str]] = {}
            if case_id == "p15-exam-02-ai-agi-quiz":
                issue_map[next(iter(residual_ids))] = ["EXAM_SEMANTIC_DUPLICATE"]
            elif case_id == "p15-exam-03-llm-midterm":
                target_id = next(iter(residual_ids))
                issue_map[target_id] = ["CROSS_ANSWER_LEAKAGE"]
            for index, original in enumerate(list(questions)):
                if original.question_id not in issue_map:
                    continue
                try:
                    candidate = await repair_question(
                        original,
                        issue_map[original.question_id],
                        list(questions),
                        blueprint,
                    )
                except Exception as exc:
                    events.append(f"FAILED_R2:{original.question_id}:{type(exc).__name__}")
                    continue
                if candidate == original:
                    events.append(f"NOOP_R2:{original.question_id}")
                    continue
                questions[index] = candidate
                events.append(f"REPAIRED_R2:{original.question_id}")
            final_report = validate_exam_global(
                blueprint,
                questions,
                resolvable_evidence_ids=set(blueprint.evidence_ids),
            )
            changed_ids = {
                item.question_id
                for item in questions
                if canonical_sha256(item.model_dump(mode="json")) != before_hashes[item.question_id]
            }
            all_repaired_ids = sorted(set(base_case.get("repaired_question_ids", [])) | changed_ids)
            cases.append(
                {
                    **base_case,
                    "status": "completed" if final_report.passed else "needs_review",
                    "questions_sha256": canonical_sha256(
                        [item.model_dump(mode="json") for item in questions]
                    ),
                    "questions": [item.model_dump(mode="json") for item in questions],
                    "repaired_question_ids": all_repaired_ids,
                    "repair_events": events,
                    "unchanged_hashes_preserved": all(
                        canonical_sha256(item.model_dump(mode="json"))
                        == before_hashes[item.question_id]
                        for item in questions
                        if item.question_id not in changed_ids
                    ),
                    "global_report": final_report.model_dump(mode="json"),
                }
            )

    input_tokens, output_tokens, requests = checkpoint.provider_usage_totals()
    cost = input_tokens / 1_000_000 + output_tokens * 2 / 1_000_000
    completed = all(item["status"] == "completed" for item in cases)
    result = {
        "schema_version": "coursepilot.p15-targeted-repair-report.v2",
        "status": "completed" if completed else "needs_review",
        "completed_at": datetime.now(UTC).isoformat(),
        "previous_report_sha256": canonical_sha256(base_report),
        "preflight": base_report["preflight"],
        "residual_targets": RESIDUAL_TARGET_SUFFIXES,
        "actual": {
            "provider_requests": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_cny": round(cost, 6),
        },
        "hard_cap_ok": requests <= MAX_REQUESTS
        and input_tokens <= MAX_INPUT_TOKENS
        and output_tokens <= MAX_OUTPUT_TOKENS
        and cost <= MAX_COST_CNY,
        "all_global_validation_passed": completed,
        "cases": cases,
    }
    checkpoint.finish(result)
    return result


def _atomic_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _delta_review_html(items: list[dict[str, Any]], template: dict[str, Any]) -> str:
    cards: list[str] = []
    for item in items:
        old = item["before"]
        new = item["after"]
        question_id = html.escape(item["question_id"])
        cards.append(
            f'<article data-id="{question_id}"><h2>{question_id}</h2>'
            f"<p><strong>修复原因：</strong>{html.escape(', '.join(item['issue_codes']))}</p>"
            '<div class="compare">'
            f"<section><h3>修复前</h3><pre>{html.escape(json.dumps(old, ensure_ascii=False, indent=2))}</pre></section>"
            f"<section><h3>修复后</h3><pre>{html.escape(json.dumps(new, ensure_ascii=False, indent=2))}</pre></section>"
            '</div><label>审核结论 <select data-field="decision">'
            '<option value="">--请选择--</option><option value="pass">pass</option>'
            '<option value="minor_edit">minor_edit</option><option value="major_edit">major_edit</option>'
            '<option value="reject">reject</option></select></label>'
            '<label>备注 <textarea data-field="notes"></textarea></label></article>'
        )
    template_json = json.dumps(template, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>P15 定向修复增量审核</title><style>
body{{font-family:system-ui;margin:24px;background:#f3f5f7;color:#17202a}}.toolbar{{position:sticky;top:0;background:white;padding:12px;border:1px solid #cbd3da;z-index:4}}button{{margin-right:8px;padding:9px 14px}}article{{background:white;border:1px solid #cbd3da;border-radius:8px;padding:16px;margin:16px 0}}.compare{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}pre{{white-space:pre-wrap;background:#f4f5f6;padding:10px;max-height:520px;overflow:auto}}label{{display:block;margin-top:10px}}select,textarea{{margin-left:8px;min-width:220px}}textarea{{min-height:54px}}#status{{font-weight:650}}@media(max-width:900px){{.compare{{grid-template-columns:1fr}}}}
</style></head><body><div class="toolbar"><button id="save" type="button">保存到本地</button><button id="download-progress" type="button">下载当前进度 JSON</button><button id="download" type="button">校验并下载最终决策 JSON</button><span id="status">0 / {len(items)} 已完成</span></div>
<h1>P15 Targeted Repair 增量审核</h1><p>只审核实际发生变化的题目。重点检查多选答案集合、逐项判断、题干自洽、材料完整和与其他题目的实质重复。</p>{"".join(cards)}
<script>const KEY='coursepilot-p15-targeted-repair:{template["source_report_sha256"]}';const BASE={template_json};
function collect(){{const data=JSON.parse(JSON.stringify(BASE));data.reviewed_at=new Date().toISOString();for(const d of data.decisions){{const card=document.querySelector(`[data-id="${{CSS.escape(d.question_id)}}"]`);d.decision=card.querySelector('[data-field="decision"]').value;d.notes=card.querySelector('[data-field="notes"]').value;}}return data;}}
function completed(d){{return Boolean(d.decision);}}function status(message){{const data=collect();const count=data.decisions.filter(completed).length;document.getElementById('status').textContent=message||`${{count}} / ${{data.decisions.length}} 已完成`;}}
function save(){{localStorage.setItem(KEY,JSON.stringify(collect()));status('已保存到本地');}}
function restore(){{const raw=localStorage.getItem(KEY);if(!raw){{status();return;}}const data=JSON.parse(raw);for(const d of data.decisions){{const card=document.querySelector(`[data-id="${{CSS.escape(d.question_id)}}"]`);if(!card)continue;card.querySelector('[data-field="decision"]').value=d.decision||'';card.querySelector('[data-field="notes"]').value=d.notes||'';}}status('已恢复本地进度');}}
function downloadData(data,name){{const blob=new Blob([JSON.stringify(data,null,2)+'\\n'],{{type:'application/json'}});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}}
function progress(){{const data=collect();localStorage.setItem(KEY,JSON.stringify(data));downloadData(data,'p15_targeted_repair_review_progress.json');status('当前进度 JSON 已下载');}}
function finalDownload(){{const data=collect();const missing=data.decisions.find(d=>!completed(d));if(missing){{status(`请先完成 ${{missing.question_id}}`);return;}}const serious=data.decisions.find(d=>(d.decision==='major_edit'||d.decision==='reject')&&!d.notes.trim());if(serious){{status(`请说明 ${{serious.question_id}} 的问题`);return;}}localStorage.setItem(KEY,JSON.stringify(data));downloadData(data,'p15_targeted_repair_review_decisions.json');status('最终决策 JSON 已下载');}}
document.getElementById('save').addEventListener('click',save);document.getElementById('download-progress').addEventListener('click',progress);document.getElementById('download').addEventListener('click',finalDownload);document.querySelectorAll('select,textarea').forEach(el=>{{el.addEventListener('change',save);el.addEventListener('input',()=>status());}});restore();</script></body></html>"""


def build_delta_review_package(
    *,
    source_state: dict[str, Any],
    result: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any] | None:
    source_by_case = {
        value["case_id"]: value
        for key, value in source_state["cases"].items()
        if key.startswith("p3:") and isinstance(value, dict)
    }
    issue_codes = {
        row["case_id"]: row["question_issue_codes"] for row in result["preflight"]["cases"]
    }
    items: list[dict[str, Any]] = []
    for case in result["cases"]:
        before = {
            item["question_id"]: item for item in source_by_case[case["case_id"]]["questions"]
        }
        after = {item["question_id"]: item for item in case["questions"]}
        for question_id in case["repaired_question_ids"]:
            items.append(
                {
                    "case_id": case["case_id"],
                    "question_id": question_id,
                    "issue_codes": issue_codes[case["case_id"]].get(question_id, []),
                    "before": before[question_id],
                    "after": after[question_id],
                }
            )
    if not items:
        return None
    source_report_sha256 = canonical_sha256(result)
    template = {
        "schema_version": "coursepilot.p15-targeted-repair-review-decisions.v1",
        "source_report_sha256": source_report_sha256,
        "reviewer_id": "course_owner",
        "reviewed_at": None,
        "decisions": [
            {
                "case_id": item["case_id"],
                "question_id": item["question_id"],
                "decision": "",
                "notes": "",
            }
            for item in items
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_report(output_dir / "review_items.json", {"items": items})
    _atomic_report(output_dir / "review_decisions_template.json", template)
    (output_dir / "review.html").write_text(_delta_review_html(items, template), encoding="utf-8")
    package = {
        "schema_version": "coursepilot.p15-targeted-repair-review-package.v1",
        "status": "pending_owner_review",
        "source_report_sha256": source_report_sha256,
        "review_question_count": len(items),
        "review_page": str(output_dir / "review.html"),
        "decision_template": str(output_dir / "review_decisions_template.json"),
    }
    _atomic_report(output_dir / "package_manifest.json", package)
    return package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source-state", type=Path, default=DEFAULT_SOURCE_STATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", choices=("preflight", "real", "residual"), default="preflight")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--external-data-authorized", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    source_state = args.source_state.resolve()
    output = args.output_dir.resolve()
    if args.mode == "preflight":
        result = scan_existing(root, source_state=source_state)
        _atomic_report(output / "preflight.json", result)
    else:
        if not args.external_data_authorized:
            raise ValueError("P15_TARGETED_REPAIR_EXTERNAL_DATA_AUTHORIZATION_REQUIRED")
        runner = _run_real_async if args.mode == "real" else _run_residual_async
        result = asyncio.run(
            runner(root, source_state=source_state, output_dir=output, resume=args.resume)
        )
        source_state = json.loads(source_state.read_text(encoding="utf-8"))
        result["review_package"] = build_delta_review_package(
            source_state=source_state,
            result=result,
            output_dir=output / ("review" if args.mode == "real" else "review_final"),
        )
        _atomic_report(
            output / ("report.json" if args.mode == "real" else "report_final.json"), result
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
