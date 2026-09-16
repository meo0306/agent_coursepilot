"""Build the deterministic P14 CP-DS1 Lesson Pilot input package.

This module only assembles human-reviewable input Gold from approved CourseRAG
DS2/DS3 records.  It never calls a Provider and never writes approved Gold.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from coursepilot.evals.formal_schemas import (
    CPDS1P14PilotDataset,
    P14ContextFixture,
    P14EvidenceFixture,
    P14FixtureBundle,
    P14InsufficientEvidenceCase,
    P14KnowledgePointFixture,
    P14LessonTaskCase,
    P14ReviewScenario,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
COURSE_ROOT = Path("datasets/courserag_eval/v1")
PILOT_PATH = DATASET_ROOT / "candidates/cp_ds1/p14_lesson_pilot_r1.json"
FIXTURE_PATH = DATASET_ROOT / "provenance/p14_agent_fixtures_r1.json"
MANIFEST_PATH = DATASET_ROOT / "provenance/p14_cp_ds1_bundle_manifest.json"
REPORT_PATH = Path("docs/refactor/phase_reports/ED_PRE_P14_CPDS1_candidate_review.md")

DS2_PATH = COURSE_ROOT / "approved/ds2/p06_evidence.json"
DS3_PATH = COURSE_ROOT / "approved/ds3/p07_knowledge_points.json"
DS3_SPLIT_PATH = COURSE_ROOT / "provenance/ds3_p07_split.json"
DEV_RETRIEVAL_PATH = COURSE_ROOT / "approved/ds5/p08_retrieval.json"

DOCX_COURSE = "course_ai_algorithms_systems"
PDF_COURSE = "course_ai_general_education"
RUBRIC_VERSION = "coursepilot.lesson-rubric.v1"


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record_sha(record: dict[str, Any]) -> str:
    approval = record.get("approval")
    if not isinstance(approval, dict) or not approval.get("approved_record_sha256"):
        raise ValueError(
            f"approved upstream record has no approval hash: {record.get('record_id')}"
        )
    return str(approval["approved_record_sha256"])


def _load_upstream(
    root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    ds2_path = root / DS2_PATH
    ds3_path = root / DS3_PATH
    split_path = root / DS3_SPLIT_PATH
    ds2 = json.loads(ds2_path.read_text(encoding="utf-8"))
    ds3 = json.loads(ds3_path.read_text(encoding="utf-8"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    evidence = {item["evidence_id"]: item for item in ds2["evidence"]}
    knowledge_points = {item["gold_kp_id"]: item for item in ds3["knowledge_points"]}
    calibration = set(split["calibration_ids"])
    selected_kps = {
        "gold-kp-124478c59a174f685eb27731b0777556",
        "gold-kp-66ae2b25924aac9fd92347d0a5f67061",
        "gold-kp-ef904a521f09a778f872f0879db3a10e",
        "gold-kp-a4ac5b5c2b47bccc1653b1c20260c9c5",
        "gold-kp-aa2da4d3c15ccea6516e7df6436d8de1",
        "gold-kp-015bf6265b50f25bf0679e78c21901f0",
        "gold-kp-39534f977f5fd0fae25105d009d1b5d9",
        "gold-kp-b746208bec27a41ca899db24ea39f5b9",
        "gold-kp-72d89298dfc07914d1f62d4a3c98eb76",
        "gold-kp-a47837b2940d01fbf5ae0d9b83793b01",
        "gold-kp-45eb73abb93d6175f6177512183193aa",
    }
    if not selected_kps <= calibration:
        raise ValueError("P14 Pilot must not use DS3 Holdout Knowledge Points")
    upstream_hashes = {
        "ds2": sha256_file(ds2_path),
        "ds3": sha256_file(ds3_path),
        "ds3_split": sha256_file(split_path),
    }
    return evidence, knowledge_points, upstream_hashes


def _validate_track_b_queries(root: Path) -> dict[str, str]:
    payload = json.loads((root / DEV_RETRIEVAL_PATH).read_text(encoding="utf-8"))
    by_id = {item["record_id"]: item for item in payload["cases"]}
    query_ids = {
        "docx": "gold-rq-ae9fe9ee546a6bff2158672fd5082657",
        "pdf": "gold-rq-7e84566911bef14e497181d6e601dd20",
    }
    for query_id in query_ids.values():
        item = by_id.get(query_id)
        if (
            item is None
            or item.get("split") != "dev"
            or item.get("evaluation_stratum") != "retrieval_main"
        ):
            raise ValueError(
                f"P14 Track B query is not an Approved retrieval_main Dev case: {query_id}"
            )
    return query_ids


def _evidence_fixture(item: dict[str, Any]) -> P14EvidenceFixture:
    span = item["source_span"]
    return P14EvidenceFixture(
        evidence_id=item["evidence_id"],
        record_sha256=_record_sha(item),
        course_id=item["course_id"],
        gold_text=item["gold_text"],
        necessary_neighbors=[
            str(neighbor["text"]) for neighbor in item.get("necessary_neighbors", [])
        ],
        source_document_id=span["document_id"],
        source_document_version=span["document_version"],
        page_start=span.get("page_start"),
        page_end=span.get("page_end"),
        content_sha256=item["content_sha256"],
    )


def _kp_fixture(item: dict[str, Any]) -> P14KnowledgePointFixture:
    return P14KnowledgePointFixture(
        gold_kp_id=item["gold_kp_id"],
        record_sha256=_record_sha(item),
        course_id=item["course_id"],
        canonical_name=item["canonical_name"],
        summary=item["summary"],
        importance=item["importance"],
        section_ids=item["section_ids"],
        evidence_ids=item["evidence_ids"],
    )


def _make_context(
    fixture_id: str,
    course_id: str,
    evidence: dict[str, dict[str, Any]],
    evidence_ids: list[str],
    kp_to_evidence: dict[str, list[str]],
) -> P14ContextFixture:
    records = [_evidence_fixture(evidence[evidence_id]) for evidence_id in evidence_ids]
    content_hash = _digest(
        {
            "course_id": course_id,
            "purpose": "lesson_generation",
            "evidence": [
                {"id": record.evidence_id, "hash": record.content_sha256} for record in records
            ],
        }
    )
    return P14ContextFixture(
        context_package_id=fixture_id,
        purpose="lesson_generation",
        course_id=course_id,
        index_version="eval-index-v1",
        content_hash=content_hash,
        trace_id=f"trace-{fixture_id}",
        evidence_ids=evidence_ids,
        evidence_records=records,
        citation_map=kp_to_evidence,
        token_count=sum(max(1, len(record.gold_text) // 2) for record in records),
        retrieval_trace_summary={
            "source": "approved_courserag_dev_fixture",
            "fallback_applied": False,
            "provider_calls": 0,
        },
    )


def _case(
    record_id: str,
    course_id: str,
    template_id: str,
    chapter_range: str,
    teaching_focus: str,
    total_sessions: int,
    session_duration: int,
    audience: str,
    kp_ids: list[str],
    evidence_ids: list[str],
    activity_types: list[str],
    forbidden_claims: list[str],
    context_fixture_id: str,
    kps: dict[str, dict[str, Any]],
    review_scenario: P14ReviewScenario,
    upstream_hashes: dict[str, str],
) -> P14LessonTaskCase:
    return P14LessonTaskCase(
        record_id=record_id,
        course_id=course_id,
        template_id=template_id,
        chapter_range=chapter_range,
        teaching_focus=teaching_focus,
        total_sessions=total_sessions,
        session_duration=session_duration,
        audience=audience,
        required_knowledge_point_ids=kp_ids,
        required_evidence_ids=evidence_ids,
        required_activity_types=activity_types,
        forbidden_claims=forbidden_claims,
        required_interrupts=["lesson_session_plan_review", "lesson_final_review"],
        context_fixture_id=context_fixture_id,
        knowledge_point_snapshot=[_kp_fixture(kps[kp_id]) for kp_id in kp_ids],
        review_scenario=review_scenario,
        source_provenance=[
            "approved/ds2/p06_evidence.json:" + upstream_hashes["ds2"],
            "approved/ds3/p07_knowledge_points.json:" + upstream_hashes["ds3"],
            "provenance/ds3_p07_split.json:" + upstream_hashes["ds3_split"],
        ],
    )


def _render_review(
    root: Path,
    dataset: CPDS1P14PilotDataset,
    fixtures: P14FixtureBundle,
    bundle_sha256: str,
    *,
    second_review: bool,
) -> str:
    cards: list[str] = []
    fixture_by_id = {fixture.context_package_id: fixture for fixture in fixtures.context_fixtures}
    for case in dataset.cases:
        fixture = fixture_by_id[case.context_fixture_id]
        kp_lines = "".join(
            f"<li><b>{html.escape(kp.canonical_name)}</b> ({html.escape(kp.gold_kp_id)})<br>"
            f"{html.escape(kp.summary)}</li>"
            for kp in case.knowledge_point_snapshot
        )
        evidence_lines = "".join(
            f"<li><b>{html.escape(item.evidence_id)}</b>：{html.escape(item.gold_text)}"
            + (
                "<br><span class='neighbor'>必要邻接："
                + html.escape("\n".join(item.necessary_neighbors))
                + "</span>"
                if item.necessary_neighbors
                else ""
            )
            + f"<br><span class='meta'>{html.escape(item.source_document_id)} / "
            f"{html.escape(item.source_document_version)} / 页 {item.page_start or '—'}</span></li>"
            for item in fixture.evidence_records
        )
        action = case.review_scenario
        action_text = (
            f"{action.plan_action}; 字段修改={action.field_edits}; "
            f"重规划={action.replan_instruction or '无'}; "
            f"导出={'允许' if action.final_export_approved else '拒绝'}; "
            f"写回={action.writeback_scope}"
        )
        cards.append(
            "<article class='card '><h2>"
            + html.escape(case.record_id)
            + "</h2><p class='tag'>"
            + html.escape(case.template_id)
            + " · "
            + html.escape(case.course_id)
            + " · "
            + str(case.total_sessions)
            + "×"
            + str(case.session_duration)
            + " 分钟</p><h3>你只需要判断</h3><ol><li>主题、学生层次和课时约束是否合理。</li>"
            "<li>每个必需 KP 是否确实值得讲授，且由下面 Evidence 支持。</li>"
            "<li>必要邻接、禁止事实和审核动作是否准确。</li></ol>"
            "<h3>任务</h3><p>"
            + html.escape(case.teaching_focus)
            + "；章节范围："
            + html.escape(case.chapter_range)
            + "；活动："
            + html.escape(", ".join(case.required_activity_types))
            + "</p><h3>Knowledge Points</h3><ul>"
            + kp_lines
            + "</ul><h3>Evidence（逐字原文）</h3><ul>"
            + evidence_lines
            + "</ul><h3>审核动作</h3><p>"
            + html.escape(action_text)
            + "</p><h3>禁止内容</h3><ul>"
            + "".join(f"<li>{html.escape(item)}</li>" for item in case.forbidden_claims)
            + "</ul><details><summary>存疑时再看：完整 Fixture JSON</summary><pre>"
            + html.escape(fixture.model_dump_json(indent=2))
            + "</pre></details><label><input type='radio' name='"
            + html.escape(case.record_id)
            + "' value='approve'>通过</label> <label><input type='radio' name='"
            + html.escape(case.record_id)
            + "' value='return'>退回</label><textarea placeholder='退回原因/备注'></textarea></article>"
        )
    review_file = (
        f"p14_second_review_{bundle_sha256[:12]}.json"
        if second_review
        else f"p14_first_review_{bundle_sha256[:12]}.json"
    )
    title = "P14 CP-DS1 Pilot 第二轮盲化审核" if second_review else "P14 CP-DS1 Pilot 首轮审核"
    negative = fixtures.negative_case
    negative_fixture = fixture_by_id[negative.context_fixture_id]
    negative_html = (
        "<section class='negative'><h2>非 Gold 合同负例："
        + html.escape(negative.record_id)
        + "</h2><p>仅确认预期行为，不计入 3 条 Pilot 审批：Context 缺少必需 Evidence 时，"
        "必须在 Provider 调用、Artifact 生成、导出和写回前 fail closed。</p><p>必需 KP："
        + html.escape(", ".join(negative.required_knowledge_point_ids))
        + "<br>故意缺少 Evidence："
        + html.escape(", ".join(negative.omitted_required_evidence_ids))
        + "<br>当前 Context Evidence："
        + html.escape(", ".join(negative_fixture.evidence_ids))
        + "<br>预期 Provider 调用：0；预期副作用：0</p></section>"
    )
    review_pass = "second" if second_review else "first"
    review_script = f"""
<section class='review-tools'>
  <h2>审核记录</h2>
  <p>选择每条记录的“通过/退回”后会自动保存在本浏览器。全部选择完成后，点击按钮导出 JSON。</p>
  <button type='button' id='export-review'>导出本轮审核 JSON</button>
  <span id='review-progress' aria-live='polite'></span>
</section>
<script>
(() => {{
  const bundle = {json.dumps(bundle_sha256)};
  const reviewPass = {json.dumps(review_pass)};
  const filename = {json.dumps(review_file)};
  const storageKey = `coursepilot:p14:${{bundle}}:${{reviewPass}}`;
  const cards = [...document.querySelectorAll('article.card')];
  const ids = cards.map(card => card.querySelector('h2').textContent.trim());
  const read = () => {{
    try {{ return JSON.parse(localStorage.getItem(storageKey) || '{{}}'); }}
    catch (_) {{ return {{}}; }}
  }};
  const saved = read();
  cards.forEach(card => {{
    const id = card.querySelector('h2').textContent.trim();
    const note = card.querySelector('textarea');
    const prior = saved[id] || {{}};
    if (prior.decision) {{
      const radio = card.querySelector(`input[value='${{prior.decision}}']`);
      if (radio) radio.checked = true;
    }}
    note.value = prior.notes || '';
  }});
  const collect = () => Object.fromEntries(cards.map(card => {{
    const id = card.querySelector('h2').textContent.trim();
    const selected = card.querySelector("input[type='radio']:checked");
    return [id, {{decision: selected ? selected.value : '', notes: card.querySelector('textarea').value.trim()}}];
  }}));
  const update = () => {{
    const state = collect();
    try {{ localStorage.setItem(storageKey, JSON.stringify(state)); }} catch (_) {{}}
    const completed = Object.values(state).filter(item => item.decision).length;
    document.getElementById('review-progress').textContent = ` 已完成 ${{completed}} / ${{ids.length}}`;
  }};
  cards.forEach(card => card.addEventListener('input', update));
  update();
  document.getElementById('export-review').addEventListener('click', () => {{
    const state = collect();
    const incomplete = ids.filter(id => !state[id].decision);
    const missingReturnNotes = ids.filter(id => state[id].decision === 'return' && !state[id].notes);
    if (incomplete.length || missingReturnNotes.length) {{
      alert(`无法导出：未选择 ${{incomplete.length}} 条；退回但未填写原因 ${{missingReturnNotes.length}} 条。`);
      return;
    }}
    const payload = {{
      schema_version: 'coursepilot.p14-review-decisions.v1',
      bundle_sha256: bundle,
      review_pass: reviewPass,
      expected_record_ids: ids,
      reviewer_id: 'course_owner',
      reviewed_at: new Date().toISOString(),
      attestation_source: 'html_export',
      decisions: ids.map(id => ({{
        record_id: id,
        decision: state[id].decision === 'approve' ? 'pass' : 'return',
        notes: state[id].notes,
      }})),
    }};
    const blob = new Blob([JSON.stringify(payload, null, 2) + '\\n'], {{type: 'application/json'}});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }});
}})();
</script>"""
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>"
        + title
        + "</title>"
        + "<style>body{font-family:system-ui;max-width:1100px;margin:24px auto;color:#222}"
        ".card{border:1px solid #bbb;border-radius:8px;padding:18px;margin:18px 0}"
        ".tag{color:#555}.meta{color:#666;font-size:.9em}.neighbor{white-space:pre-wrap;color:#075}"
        "pre{white-space:pre-wrap;background:#f5f5f5;padding:12px;max-height:420px;overflow:auto}"
        "textarea{display:block;width:100%;min-height:55px;margin-top:8px}</style>"
        + f"<h1>{title}</h1><p>Bundle SHA-256：<code>{bundle_sha256}</code></p>"
        + "<p>审核完成后导出：<code>"
        + review_file
        + "</code>。本页面不包含系统预测结果。</p>"
        + "".join(cards)
        + negative_html
        + review_script
        + "</html>"
    )


def generate(root: Path) -> dict[str, str | int]:
    evidence, knowledge_points, upstream_hashes = _load_upstream(root)
    track_b_queries = _validate_track_b_queries(root)
    transformer_kps = [
        "gold-kp-124478c59a174f685eb27731b0777556",
        "gold-kp-66ae2b25924aac9fd92347d0a5f67061",
        "gold-kp-ef904a521f09a778f872f0879db3a10e",
        "gold-kp-a4ac5b5c2b47bccc1653b1c20260c9c5",
    ]
    transformer_ev = [
        "gold-ev-7056e327e4d297eadf4eeb60f00fcf21",
        "gold-ev-9abde4ba81915c311db9ade93789806e",
        "gold-ev-520d6a9a5468ceca52daee6f7de7e998",
        "gold-ev-baaff1e84d4d4e0415499eef709178cd",
    ]
    perceptron_kps = [
        "gold-kp-aa2da4d3c15ccea6516e7df6436d8de1",
        "gold-kp-015bf6265b50f25bf0679e78c21901f0",
        "gold-kp-39534f977f5fd0fae25105d009d1b5d9",
        "gold-kp-b746208bec27a41ca899db24ea39f5b9",
    ]
    perceptron_ev = [
        "gold-ev-cbcdb714a5167c63838bba512eee2b4c",
        "gold-ev-475a17360c717b3221789247426a4d70",
        "gold-ev-f333ceb9cf96f580ec2a714438e94d27",
        "gold-ev-615b210d350379cf26677f84c3064531",
    ]
    risk_kps = [
        "gold-kp-72d89298dfc07914d1f62d4a3c98eb76",
        "gold-kp-a47837b2940d01fbf5ae0d9b83793b01",
        "gold-kp-45eb73abb93d6175f6177512183193aa",
    ]
    risk_ev = [
        "gold-ev-73452f80b793aba65cdb9b1032838d27",
        "gold-ev-331fa0be83528a68d9fae5234494bbd4",
        "gold-ev-e3e6a8faf68b6e239ae34c4cfdda2fb1",
    ]
    contexts = [
        _make_context(
            "ctx-p14-lesson-01-transformer",
            DOCX_COURSE,
            evidence,
            transformer_ev,
            {
                kp_id: [evidence_id]
                for kp_id, evidence_id in zip(transformer_kps, transformer_ev, strict=True)
            },
        ),
        _make_context(
            "ctx-p14-lesson-02-perceptron-lab",
            DOCX_COURSE,
            evidence,
            perceptron_ev,
            {
                kp_id: [evidence_id]
                for kp_id, evidence_id in zip(perceptron_kps, perceptron_ev, strict=True)
            },
        ),
        _make_context(
            "ctx-p14-lesson-03-occupation-risk-seminar",
            PDF_COURSE,
            evidence,
            risk_ev,
            {kp_id: [evidence_id] for kp_id, evidence_id in zip(risk_kps, risk_ev, strict=True)},
        ),
        _make_context(
            "ctx-p14-negative-missing-emergent-evidence",
            DOCX_COURSE,
            evidence,
            [transformer_ev[2]],
            {transformer_kps[2]: [transformer_ev[2]]},
        ),
    ]
    cases = [
        _case(
            "p14-lesson-01-transformer",
            DOCX_COURSE,
            "lesson_standard_university_v1",
            "3.5.3 注意力机制和Transformer",
            "从传统 seq2seq 长序列局限过渡到 Transformer 编码器结构及 Q/K/V 来源",
            2,
            50,
            "本科二年级",
            transformer_kps,
            transformer_ev,
            ["comparison", "concept_mapping"],
            [
                "Transformer 编码器不包含位置编码。",
                "编码器—解码器注意力中的 Q、K、V 全部来自解码器。",
            ],
            contexts[0].context_package_id,
            knowledge_points,
            P14ReviewScenario(plan_action="approve"),
            upstream_hashes,
        ),
        _case(
            "p14-lesson-02-perceptron-lab",
            DOCX_COURSE,
            "lesson_lab_practice_v1",
            "2.2.2 感知机",
            "用原始训练算法和线性可分性解释感知机的训练过程与适用边界",
            2,
            45,
            "本科二年级",
            perceptron_kps,
            perceptron_ev,
            ["algorithm_trace", "guided_practice"],
            [
                "感知机能够直接解决任意非线性可分数据集。",
                "感知机原始训练算法在满足线性可分条件时不会收敛。",
            ],
            contexts[1].context_package_id,
            knowledge_points,
            P14ReviewScenario(
                plan_action="edit",
                field_edits={"sessions[0].teaching_focus": "感知机定义与线性可分性"},
                writeback_scope="verified_lesson_fragment",
            ),
            upstream_hashes,
        ),
        _case(
            "p14-lesson-03-occupation-risk-seminar",
            PDF_COURSE,
            "lesson_seminar_v1",
            "1.2.2 人工智能的影响",
            "解读职业自动化淘汰概率表，并讨论资料列出的不易被人工智能取代的工作特征",
            1,
            90,
            "本科一年级通识课",
            risk_kps,
            risk_ev,
            ["data_interpretation", "case_discussion"],
            [
                "表中所有职业的被淘汰概率都超过 50%。",
                "教材断言教师的被淘汰概率为 99%。",
            ],
            contexts[2].context_package_id,
            knowledge_points,
            P14ReviewScenario(
                plan_action="replan",
                replan_instruction="保留 90 分钟总时长，将表格数据解读安排在案例讨论之前。",
            ),
            upstream_hashes,
        ),
    ]
    pilot = CPDS1P14PilotDataset(cases=cases)
    negative = P14InsufficientEvidenceCase(
        record_id="p14-contract-negative-missing-evidence",
        course_id=DOCX_COURSE,
        required_knowledge_point_ids=[
            "gold-kp-ef904a521f09a778f872f0879db3a10e",
            "gold-kp-07c87ce697fc1dd864b09c4c99776978",
        ],
        context_fixture_id=contexts[3].context_package_id,
        omitted_required_evidence_ids=["gold-ev-365b0dc23cff9bb089df5923e2212264"],
    )
    fixture_bundle = P14FixtureBundle(context_fixtures=contexts, negative_case=negative)
    pilot_bytes = json.dumps(
        pilot.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    fixture_bytes = json.dumps(
        fixture_bundle.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    bundle_sha256 = _digest(
        {
            "pilot": hashlib.sha256(pilot_bytes).hexdigest(),
            "fixtures": hashlib.sha256(fixture_bytes).hexdigest(),
        }
    )
    pilot_path = root / PILOT_PATH
    fixture_path = root / FIXTURE_PATH
    manifest_path = root / MANIFEST_PATH
    atomic_write_json(pilot_path, pilot.model_dump(mode="json"))
    atomic_write_json(fixture_path, fixture_bundle.model_dump(mode="json"))
    manifest: dict[str, Any] = {
        "schema_version": "coursepilot.p14-cp-ds1-bundle-manifest.v1",
        "dataset_id": "coursepilot-eval",
        "dataset_version": "p14-pilot-r1",
        "approval_scope": "cp_ds1_p14_pilot_input_only",
        "candidate_hashes": {
            "pilot": sha256_file(pilot_path),
            "fixtures": sha256_file(fixture_path),
        },
        "bundle_sha256": bundle_sha256,
        "record_ids": [case.record_id for case in cases],
        "negative_record_id": negative.record_id,
        "counts": {"pilot_cases": 3, "context_fixtures": 4, "negative_cases": 1},
        "upstream_hashes": upstream_hashes,
        "track_b_smoke_queries": track_b_queries,
        "gold_promotion": False,
        "external_provider_calls": 0,
    }
    atomic_write_json(manifest_path, manifest)
    review_root = root / "storage_eval/cpds1_p14_review" / bundle_sha256
    atomic_write_text(
        review_root / "index.html",
        _render_review(root, pilot, fixture_bundle, bundle_sha256, second_review=False),
    )
    atomic_write_text(
        review_root / "second_review.html",
        _render_review(root, pilot, fixture_bundle, bundle_sha256, second_review=True),
    )
    report = f"""# Pre-P14 CP-DS1 Lesson Pilot Candidate Review

任务：`ED-PRE14-CPDS1-T01` 至 `ED-PRE14-CPDS1-T08`

本批生成 3 条 CP-DS1 Pilot Gold Candidate 和 1 条非 Gold 证据不足合同负例。语义来源仍只有两个 Approved CourseRAG Primary 课程，未调用 Provider，未读取 Test/Holdout，未生成系统教案输出。

- Pilot Candidate SHA-256：`{manifest["candidate_hashes"]["pilot"]}`
- Fixture SHA-256：`{manifest["candidate_hashes"]["fixtures"]}`
- Bundle SHA-256：`{bundle_sha256}`
- 记录：3 条 Gold Pilot、4 个 Context Fixture、1 条负例
- 审核入口：`storage_eval/cpds1_p14_review/{bundle_sha256}/index.html`
- 二轮入口：`storage_eval/cpds1_p14_review/{bundle_sha256}/second_review.html`

Candidate 文件本身保持 `candidate`，Approved 副本仅在精确 Bundle 审批后另行生成。审核重点为任务目标/课时、KP 与 Evidence 的对应、必要邻接、禁止事实和审核动作。
"""
    approval_path = root / DATASET_ROOT / "provenance/p14_cp_ds1_bundle_approval.json"
    if approval_path.is_file():
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        if approval.get("bundle_sha256") == bundle_sha256:
            report += (
                "\n## 审批结果\n\n"
                "该精确 Bundle 已由 `course_owner` 批准。因原审核页缺少导出渠道，"
                "两轮全通过决定由对话中的精确 Bundle 批准补录；无需重新审核。"
                "Approved Pilot 和审批文件分别位于 `approved/cp_ds1/p14_lesson_pilot.json` "
                "与 `provenance/p14_cp_ds1_bundle_approval.json`。当前 P14 输入状态为 "
                "`formal_eval_ready`，但 P14 Exit Gate 尚未运行。\n"
            )
    atomic_write_text(root / REPORT_PATH, report)
    return {
        "pilot_sha256": manifest["candidate_hashes"]["pilot"],
        "fixtures_sha256": manifest["candidate_hashes"]["fixtures"],
        "bundle_sha256": bundle_sha256,
        "review_path": str(review_root.relative_to(root)).replace("\\", "/"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(generate(args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
