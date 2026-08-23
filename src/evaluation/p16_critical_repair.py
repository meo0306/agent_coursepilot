"""One-shot, owner-authorized repair of the 17 Critical P16 review pages."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.ppt import PPTArtifact, SlideContent
from coursepilot.llm import (
    CoursePilotLLMCallError,
    collect_coursepilot_llm_metadata,
    generate_structured,
)
from evaluation.p16_ppt_eval import _BudgetCheckpoint, _write_json_atomic

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REPORT = ROOT / "storage_eval/p16_closure_docker/report.json"
DECISIONS = ROOT / "storage_eval/p16_closure_docker/review/p16_review_decisions.json"
DATASET = ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds3/p16_ppt_pilot.json"
MAX_CRITICAL = 17
MAX_COST_CNY = Decimal("0.45")
MAX_INPUT_TOKENS = 130_000
MAX_OUTPUT_TOKENS = 60_000
MAX_REQUESTS = 20


def _load() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    report = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    return report, decisions, dataset


def preflight() -> dict[str, Any]:
    report, decisions, dataset = _load()
    critical = [item for item in decisions["records"] if item.get("critical_defect") is True]
    case_ids = {item["record_id"] for item in report["cases"]}
    dataset_ids = {item["record_id"] for item in dataset["cases"]}
    mapped = all(item["record_id"] in case_ids & dataset_ids for item in critical)
    result = {
        "schema_version": "coursepilot.p16-critical-repair-preflight.v1",
        "external_calls_made": 0,
        "critical_page_count": len(critical),
        "scope_exact": len(critical) == MAX_CRITICAL and mapped,
        "source_report_sha256": canonical_sha256(report),
        "owner_decisions_sha256": canonical_sha256(decisions),
        "critical_review_ids": [item["review_id"] for item in critical],
        "hard_limits": {
            "max_cost_cny": str(MAX_COST_CNY),
            "max_input_tokens": MAX_INPUT_TOKENS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_requests": MAX_REQUESTS,
            "max_repairs_per_slide": 1,
        },
    }
    if not result["scope_exact"]:
        result["stop_reason"] = "P16_CRITICAL_REPAIR_SCOPE_MISMATCH"
    return result


def _target(case: dict[str, Any], slide_id: str) -> dict[str, Any]:
    return next(item for item in case["slide_targets"] if item["slide_id"] == slide_id)


def _reference_bullets(slide: SlideContent) -> list[str]:
    seen: set[tuple[str, str, int | None, int | None]] = set()
    bullets: list[str] = []
    for citation in slide.citations:
        key = (
            citation.source_document_id,
            citation.source_document_version,
            citation.page_start,
            citation.page_end,
        )
        if key in seen:
            continue
        seen.add(key)
        pages = "页码未标注"
        if citation.page_start is not None:
            pages = f"第 {citation.page_start} 页"
            if citation.page_end not in {None, citation.page_start}:
                pages = f"第 {citation.page_start}–{citation.page_end} 页"
        bullets.append(f"{citation.source_document_id} · {pages}")
    return bullets


def _postprocess(
    candidate: SlideContent,
    *,
    original: SlideContent,
    target: dict[str, Any],
    issue: str,
) -> tuple[SlideContent, dict[str, Any]]:
    updates: dict[str, Any] = {
        "slide_id": original.slide_id,
        "citations": original.citations,
        "assets": original.assets,
        "content_sha256": None,
    }
    hints: dict[str, Any] = {"title_top": True}
    if any(token in issue for token in ("截断", "溢出", "字体过大", "超出")):
        hints["compact_text"] = True
    if original.assets:
        hints["materialize_assets"] = True
    evidence = list(target.get("evidence_snapshots", []))
    if target.get("asset_kind") == "editable_table" and evidence:
        table_text = str(evidence[0].get("gold_text", ""))
        if "\t" in table_text:
            updates.update({"bullets": [], "body_text": table_text})
            hints["editable_table_tsv"] = table_text
    if target.get("slide_type") == "references":
        repaired = candidate.model_copy(update=updates)
        updates.update(
            {
                "bullets": _reference_bullets(repaired),
                "body_text": "",
                "speaker_notes": repaired.speaker_notes
                + "\nEvidence IDs: "
                + ", ".join(item.evidence_id for item in original.citations),
            }
        )
        hints["compact_text"] = True
    return candidate.model_copy(update=updates), hints


class _RecoverableResponseCheckpoint(Protocol):
    failed_invocations: list[dict[str, Any]]
    cache: dict[str, dict[str, Any]]

    def _persist(self) -> None: ...


def _recover_structured_response(
    checkpoint: _RecoverableResponseCheckpoint,
) -> SlideContent:
    """Recover a complete billed response rejected only for its model-authored hash."""
    invocation = checkpoint.failed_invocations[-1]
    if invocation.get("error_category") != "structured_parse_error":
        raise RuntimeError("P16_CRITICAL_REPAIR_RESPONSE_NOT_RECOVERABLE")
    attempt = invocation["attempts"][-1]
    message = str(attempt.get("error_message", ""))
    marker = "Failed to parse SlideContent from completion "
    if marker not in message:
        raise RuntimeError("P16_CRITICAL_REPAIR_RESPONSE_NOT_RECOVERABLE")
    raw, _ = json.JSONDecoder().raw_decode(message.split(marker, 1)[1])
    raw["content_sha256"] = None
    candidate = SlideContent.model_validate(raw)
    request_sha256 = str(invocation["request_sha256"])
    checkpoint.cache[request_sha256] = {
        "request_sha256": request_sha256,
        "prompt_name": "ppt/p16_repair_slide",
        "profile_id": "content_repair_main",
        "schema": "SlideContent",
        "result": candidate.model_dump(mode="json"),
        "usage": attempt.get("usage"),
        "recovered_without_provider_retry": True,
    }
    checkpoint._persist()
    return candidate


def _deterministic_repair(
    original: SlideContent, *, target: dict[str, Any], issue: str
) -> SlideContent:
    """Finish the approved page without a second Provider request."""
    title = original.title
    bullets = list(original.bullets)
    body = original.body_text
    notes = original.speaker_notes
    if "Q/K/V" in issue or "Q 来自解码器" in issue or "注意力" in issue:
        title = title.replace("注意力", "编码器—解码器交叉注意力", 1)
        bullets = [
            "本页证据限定为编码器—解码器交叉注意力",
            "Q 来自解码器当前位置的隐藏状态或输出",
            "K、V 来自编码器各位置的隐藏状态或输出",
            "编码器自注意力不使用上述跨端来源表述",
        ]
    if "残差连接" in issue or "Add & Norm" in issue:
        bullets = [
            "输入嵌入与位置编码构成编码器输入",
            "每层包含多头自注意力与前馈网络",
            "每个子层后连接残差路径并执行 Add & Norm",
            "多层堆叠后输出上下文表示",
        ]
    if "遗漏偏置 b" in issue or "遗漏 b" in issue:
        replacements = {
            "Yᵢ(ωᵀXᵢ)≤0": "Yᵢ(ωᵀXᵢ+b)≤0",
            "yᵢ(wᵀxᵢ)≤0": "yᵢ(wᵀxᵢ+b)≤0",
        }
        for old, new in replacements.items():
            title = title.replace(old, new)
            bullets = [item.replace(old, new) for item in bullets]
            body = body.replace(old, new)
            notes = notes.replace(old, new)
        if "未提供 X" in issue:
            bullets = [
                "给定 X₁=(2,1)、Y₁=+1，X₂=(-1,-2)、Y₂=-1",
                "初始 ω=(0,0)、b=0，学习率 η=1",
                "按 Yᵢ(ωᵀXᵢ+b)≤0 判断误分类",
                "误分类时更新 ω←ω+ηYᵢXᵢ，b←b+ηYᵢ",
            ]
    if "机构" in issue or "来源归属" in issue:
        bullets = [
            item.replace("牛津大学", "教材所引 BBC 数据体系").replace(
                "剑桥大学研究者", "教材所引研究者"
            )
            for item in bullets
        ]
        body = body.replace("牛津大学", "教材所引 BBC 数据体系").replace(
            "剑桥大学研究者", "教材所引研究者"
        )
        notes = notes.replace("牛津大学", "教材所引 BBC 数据体系").replace(
            "剑桥大学研究者", "教材所引研究者"
        )
    if any(token in issue for token in ("截断", "溢出", "字体过大")):
        bullets = [item[:72].rstrip() for item in bullets[:4]]
        body = body[:240].rstrip()
    return original.model_copy(
        update={
            "title": title,
            "bullets": bullets,
            "body_text": body,
            "speaker_notes": notes + "\n[本页按 Course Owner Critical 意见定向修复]",
            "content_sha256": None,
        }
    )


def run(*, output_dir: Path, allow_provider: bool = True) -> dict[str, Any]:
    check = preflight()
    if not check["scope_exact"]:
        raise RuntimeError("P16_CRITICAL_REPAIR_SCOPE_MISMATCH")
    output_dir.mkdir(parents=True, exist_ok=True)
    completed_report = output_dir / "report.json"
    if completed_report.is_file():
        existing = json.loads(completed_report.read_text(encoding="utf-8"))
        if existing.get("status") == "completed":
            return existing
    source, decisions, dataset = _load()
    decision_by_slide = {
        item["slide_id"]: item
        for item in decisions["records"]
        if item.get("critical_defect") is True
    }
    dataset_by_case = {item["record_id"]: item for item in dataset["cases"]}
    checkpoint = _BudgetCheckpoint(
        additional_max_input=MAX_INPUT_TOKENS,
        additional_max_output=MAX_OUTPUT_TOKENS,
        additional_max_requests=MAX_REQUESTS,
        additional_max_cost_cny=MAX_COST_CNY,
        console_baseline_cny=Decimal("0"),
        console_total_cap_cny=MAX_COST_CNY,
        path=output_dir / "checkpoint.json",
        enforce_off_peak=False,
    )
    repaired_cases: list[dict[str, Any]] = []
    repaired_ids: list[str] = []
    repair_sources: dict[str, str] = {}
    cached_by_slide = {
        str(payload.get("result", {}).get("slide_id")): payload
        for payload in checkpoint.cache.values()
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict)
    }
    with collect_coursepilot_llm_metadata(
        thread_id="p16:critical-only-repair", checkpoint=checkpoint
    ) as collector:
        for source_case in source["cases"]:
            artifact = PPTArtifact.model_validate(source_case["artifact"])
            case_spec = dataset_by_case[source_case["record_id"]]
            before = {slide.slide_id: slide.content_sha256 for slide in artifact.slides}
            slides = list(artifact.slides)
            hints: dict[str, dict[str, Any]] = {}
            for index, original in enumerate(list(slides)):
                decision = decision_by_slide.get(original.slide_id)
                if decision is None:
                    continue
                target = _target(case_spec, original.slide_id)
                plan = artifact.architecture.plans[index]
                cached = cached_by_slide.get(original.slide_id)
                if cached is not None:
                    candidate = SlideContent.model_validate(cached["result"])
                    repair_sources[original.slide_id] = "provider_checkpoint"
                elif not allow_provider:
                    candidate = _deterministic_repair(
                        original,
                        target=target,
                        issue=decision["reviewer_notes"],
                    )
                    repair_sources[original.slide_id] = "deterministic_after_provider_stop"
                else:
                    try:
                        candidate = generate_structured(
                            prompt_name="ppt/p16_repair_slide",
                            output_schema=SlideContent,
                            payload={
                                "original_slide": original.model_dump(mode="json"),
                                "slide_plan": plan.model_dump(mode="json"),
                                "review_issue": decision["reviewer_notes"],
                                "evidence": target.get("evidence_snapshots", []),
                                "required_claims": target.get("required_claims", []),
                                "allowed_fields": [
                                    "title",
                                    "bullets",
                                    "body_text",
                                    "speaker_notes",
                                    "assets",
                                ],
                            },
                            fallback=lambda: (_ for _ in ()).throw(
                                RuntimeError("P16_CRITICAL_REPAIR_FALLBACK_FORBIDDEN")
                            ),
                            profile_id="content_repair_main",
                            allow_fallback=False,
                        )
                        repair_sources[original.slide_id] = "provider"
                    except CoursePilotLLMCallError as exc:
                        if exc.category != "structured_parse_error":
                            raise
                        candidate = _recover_structured_response(checkpoint)
                        repair_sources[original.slide_id] = "recovered_billed_response"
                expected_citations = {item.evidence_id for item in original.citations}
                if (
                    candidate.slide_id != original.slide_id
                    or {item.evidence_id for item in candidate.citations} - expected_citations
                ):
                    raise ValueError("P16_CRITICAL_REPAIR_IDENTITY_OR_CITATION_CHANGED")
                repaired, slide_hints = _postprocess(
                    candidate,
                    original=original,
                    target=target,
                    issue=decision["reviewer_notes"],
                )
                slides[index] = repaired
                hints[original.slide_id] = slide_hints
                repaired_ids.append(original.slide_id)
            repaired_artifact = artifact.model_copy(update={"slides": slides})
            unchanged_preserved = all(
                slide.content_sha256 == before[slide.slide_id]
                for slide in repaired_artifact.slides
                if slide.slide_id not in decision_by_slide
            )
            if not unchanged_preserved:
                raise RuntimeError("P16_NONCRITICAL_SLIDE_CHANGED")
            repaired_cases.append(
                {
                    "record_id": source_case["record_id"],
                    "artifact": repaired_artifact.model_dump(mode="json"),
                    "slide_render_hints": hints,
                    "repaired_slide_ids": sorted(hints),
                    "unchanged_noncritical_slides_preserved": True,
                }
            )
    result = {
        "schema_version": "coursepilot.p16-critical-repair-report.v1",
        "status": "completed",
        "preflight": check,
        "repair_rounds": 1,
        "repaired_slide_ids": repaired_ids,
        "repair_sources": repair_sources,
        "provider_usage": collector.to_task_metadata(),
        "budget": checkpoint.summary(),
        "cases": repaired_cases,
    }
    _write_json_atomic(completed_report, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p16_critical_repair"))
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--external-data-authorized", action="store_true")
    parser.add_argument("--offline-complete", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        result = preflight()
    else:
        if not args.external_data_authorized:
            parser.error("repair requires --external-data-authorized")
        result = run(output_dir=args.output_dir, allow_provider=not args.offline_complete)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
