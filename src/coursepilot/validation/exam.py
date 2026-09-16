from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from coursepilot.domain.exam import ExamBlueprintV2, ExamGlobalReport, ExamQuestion

_STIMULUS_REFERENCE = re.compile(
    r"(?:根据|参照|见|阅读|使用)(?:上|下|以下|上述|所给)?"
    r"(?:表格|表(?!述)|图|数据|材料)"
    r"|(?:如下|下列|上述)(?:表格|表(?!述)|图)"
    r"|according\s+to\s+(?:the\s+)?(?:table|figure|data)",
    re.IGNORECASE,
)
_OMITTED_STIMULUS = re.compile(
    r"(?:省略|未展示|未提供|未附上)(?:的)?(?:表格|表|图|数据|材料)"
    r"|(?:表格|表|图|数据|材料)(?:被省略|未展示|未提供|未附上)"
    r"|(?:table|figure|data)\s+(?:omitted|not\s+(?:shown|provided))",
    re.IGNORECASE,
)


def normalize_question_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value)


def text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None, normalize_question_text(left), normalize_question_text(right)
    ).ratio()


def detect_duplicate_pairs(
    questions: list[ExamQuestion],
    *,
    threshold: float = 0.85,
    slot_target_ids: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for index, left in enumerate(questions):
        for right in questions[index + 1 :]:
            stem_similarity = text_similarity(left.stem, right.stem)
            same_target = bool(
                slot_target_ids
                and slot_target_ids.get(left.slot_id)
                and slot_target_ids.get(left.slot_id) == slot_target_ids.get(right.slot_id)
            )
            same_evidence = set(left.evidence_ids) == set(right.evidence_ids)
            answer_similarity = text_similarity(
                _answer_text(left),
                _answer_text(right),
            )
            # Paraphrased questions generated from the same approved target can
            # evade a stem-only threshold.  The combined rule stays conservative:
            # it applies only to the same target/evidence and requires meaningful
            # overlap in both the question and its supported answer.
            target_duplicate = (
                same_target and same_evidence and (stem_similarity + answer_similarity) / 2 >= 0.44
            )
            if stem_similarity >= threshold or target_duplicate:
                pairs.append((left.question_id, right.question_id))
    return pairs


def _answer_keys(question: ExamQuestion) -> list[str]:
    raw = question.answer.strip()
    if not raw:
        return []
    separated = [item.strip() for item in re.split(r"[,，、;/；]+", raw) if item.strip()]
    if len(separated) > 1:
        return separated
    if raw in question.options:
        return [raw]
    if question.options and all(character in question.options for character in raw):
        return list(raw)
    return [raw]


def _answer_text(question: ExamQuestion) -> str:
    return " ".join(question.options.get(key, key) for key in _answer_keys(question))


def _append_issue(issues: dict[str, list[str]], question_id: str, code: str) -> None:
    values = issues.setdefault(question_id, [])
    if code not in values:
        values.append(code)


def detect_answer_leakage_findings(
    questions: list[ExamQuestion],
) -> tuple[list[str], list[tuple[str, str]]]:
    direct: list[str] = []
    cross: list[tuple[str, str]] = []
    seen_direct: set[str] = set()
    seen_cross: set[tuple[str, str]] = set()
    for question in questions:
        stem = normalize_question_text(question.stem)
        answer_values = [
            question.options.get(key, question.answer) for key in _answer_keys(question)
        ]
        for answer in answer_values:
            answer_text = normalize_question_text(answer)
            if (
                len(answer_text) >= 4
                and answer_text in stem
                and question.question_id not in seen_direct
            ):
                seen_direct.add(question.question_id)
                direct.append(question.question_id)
        for other in questions:
            if other.question_id == question.question_id:
                continue
            other_answers = [other.options.get(key, other.answer) for key in _answer_keys(other)]
            pair = (question.question_id, other.question_id)
            if pair in seen_cross:
                continue
            if any(
                len(normalize_question_text(answer)) >= 6
                and normalize_question_text(answer) in stem
                for answer in other_answers
            ):
                seen_cross.add(pair)
                cross.append(pair)
    return direct, cross


def detect_answer_leakage(questions: list[ExamQuestion]) -> list[str]:
    direct, cross = detect_answer_leakage_findings(questions)
    errors: list[str] = []
    errors.extend(f"ANSWER_LEAKAGE:{question_id}" for question_id in direct)
    errors.extend(
        f"CROSS_ANSWER_LEAKAGE:{question_id}:{source_id}" for question_id, source_id in cross
    )
    return errors


def validate_exam_global(
    blueprint: ExamBlueprintV2,
    questions: list[ExamQuestion],
    *,
    resolvable_evidence_ids: set[str] | None = None,
) -> ExamGlobalReport:
    errors: list[str] = []
    slot_by_id = {slot.slot_id: slot for slot in blueprint.slots}
    issue_codes: dict[str, list[str]] = {}
    expected_count = len(blueprint.slots)
    question_count_valid = len(questions) == expected_count and {
        q.slot_id for q in questions
    } == set(slot_by_id)
    if not question_count_valid:
        errors.append("QUESTION_COUNT_OR_SLOT_MISMATCH")
    score_valid = sum(question.score for question in questions) == sum(
        slot.score for slot in blueprint.slots
    )
    if not score_valid:
        errors.append("TOTAL_SCORE_MISMATCH")
    distribution_valid = all(
        question.question_type == slot_by_id[question.slot_id].question_type
        and question.difficulty == slot_by_id[question.slot_id].difficulty
        and question.content_role == slot_by_id[question.slot_id].content_role
        for question in questions
        if question.slot_id in slot_by_id
    )
    if not distribution_valid:
        errors.append("SLOT_DISTRIBUTION_MISMATCH")
    coverage_valid = all(
        set(question.knowledge_point_ids) <= set(blueprint.knowledge_point_ids)
        and set(question.evidence_ids) <= set(blueprint.evidence_ids)
        for question in questions
    ) and set().union(*(set(q.knowledge_point_ids) for q in questions)) >= set(
        blueprint.knowledge_point_ids
    )
    if not coverage_valid:
        errors.append("KP_COVERAGE_OR_SCOPE_MISMATCH")
    citation_resolvable = all(
        set(question.evidence_ids) <= (resolvable_evidence_ids or set(blueprint.evidence_ids))
        for question in questions
    )
    if not citation_resolvable:
        errors.append("EVIDENCE_NOT_RESOLVABLE")

    choice_contract_ids: list[str] = []
    answer_set_ids: list[str] = []
    stimulus_ids: list[str] = []
    for question in questions:
        if question.question_type in {"single_choice", "multiple_choice"}:
            answer_keys = _answer_keys(question)
            option_keys = set(question.options)
            invalid_answer = not answer_keys or not set(answer_keys) <= option_keys
            invalid_cardinality = (
                question.question_type == "single_choice" and len(answer_keys) != 1
            ) or (question.question_type == "multiple_choice" and len(answer_keys) < 2)
            if invalid_answer or invalid_cardinality:
                choice_contract_ids.append(question.question_id)
                code = (
                    "EXAM_MULTIPLE_CHOICE_CARDINALITY"
                    if question.question_type == "multiple_choice" and len(answer_keys) < 2
                    else "EXAM_ANSWER_NOT_IN_OPTIONS"
                )
                _append_issue(issue_codes, question.question_id, code)

            if question.option_assessments:
                assessment_keys = set(question.option_assessments)
                correct_keys = [
                    key
                    for key in question.options
                    if question.option_assessments.get(key)
                    and question.option_assessments[key].is_correct
                ]
                assessments_valid = assessment_keys == option_keys and all(
                    set(assessment.evidence_ids) <= set(question.evidence_ids)
                    for assessment in question.option_assessments.values()
                )
                if not assessments_valid:
                    answer_set_ids.append(question.question_id)
                    _append_issue(
                        issue_codes, question.question_id, "EXAM_OPTION_ASSESSMENT_MISMATCH"
                    )
                if set(correct_keys) != set(answer_keys):
                    if question.question_id not in answer_set_ids:
                        answer_set_ids.append(question.question_id)
                    _append_issue(issue_codes, question.question_id, "EXAM_ANSWER_SET_INCONSISTENT")

        stem_requires_stimulus = bool(_STIMULUS_REFERENCE.search(question.stem))
        omitted_stimulus = bool(_OMITTED_STIMULUS.search(question.stem))
        has_stimulus = bool(question.stimulus and question.stimulus.strip())
        if omitted_stimulus or (stem_requires_stimulus and not has_stimulus):
            stimulus_ids.append(question.question_id)
            _append_issue(
                issue_codes,
                question.question_id,
                "EXAM_OMITTED_STIMULUS_REFERENCE"
                if omitted_stimulus
                else "EXAM_REQUIRED_STIMULUS_MISSING",
            )

    if choice_contract_ids:
        errors.append("CHOICE_CONTRACT_INVALID")
    if answer_set_ids:
        errors.append("ANSWER_SET_INCONSISTENT")
    if stimulus_ids:
        errors.append("STIMULUS_CONTRACT_INVALID")

    duplicate_pairs = detect_duplicate_pairs(
        questions,
        threshold=blueprint.duplicate_similarity_threshold,
        slot_target_ids={
            slot.slot_id: slot.assessment_target or slot.target_id for slot in blueprint.slots
        },
    )
    if duplicate_pairs:
        errors.append("DUPLICATE_QUESTIONS")
        for _, right_id in duplicate_pairs:
            _append_issue(issue_codes, right_id, "EXAM_SEMANTIC_DUPLICATE")
    direct_leakage_ids, cross_leakage_pairs = detect_answer_leakage_findings(questions)
    leakage_errors = [
        *(f"ANSWER_LEAKAGE:{question_id}" for question_id in direct_leakage_ids),
        *(
            f"CROSS_ANSWER_LEAKAGE:{question_id}:{source_id}"
            for question_id, source_id in cross_leakage_pairs
        ),
    ]
    errors.extend(leakage_errors)
    return ExamGlobalReport(
        question_count_valid=question_count_valid,
        score_valid=score_valid,
        distribution_valid=distribution_valid,
        coverage_valid=coverage_valid,
        citation_resolvable=citation_resolvable,
        duplicate_valid=not duplicate_pairs,
        answer_leakage_valid=not leakage_errors,
        choice_contract_valid=not choice_contract_ids,
        answer_set_valid=not answer_set_ids,
        stimulus_valid=not stimulus_ids,
        duplicate_pairs=duplicate_pairs,
        answer_leakage_question_ids=direct_leakage_ids,
        cross_answer_leakage_pairs=cross_leakage_pairs,
        choice_contract_question_ids=choice_contract_ids,
        answer_set_question_ids=answer_set_ids,
        stimulus_question_ids=stimulus_ids,
        question_issue_codes=issue_codes,
        errors=errors,
    )
