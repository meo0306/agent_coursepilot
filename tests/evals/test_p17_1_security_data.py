from evaluation.p17_1_security_data import build_calibration_candidate, build_review_template


def test_p17_1_calibration_candidate_has_preregistered_balance() -> None:
    dataset = build_calibration_candidate()
    malicious = [case for case in dataset.cases if case.label == "malicious"]
    negatives = [case for case in dataset.cases if case.label == "hard_negative"]
    assert len(dataset.cases) == 240
    assert len(malicious) == len(negatives) == 120
    assert {case.language for case in dataset.cases} == {"en", "zh"}
    assert len({case.text_sha256 for case in dataset.cases}) == 240
    assert dataset.consumed_blind_access is False


def test_p17_1_construction_groups_do_not_mix_labels() -> None:
    dataset = build_calibration_candidate()
    labels_by_group: dict[str, set[str]] = {}
    for case in dataset.cases:
        labels_by_group.setdefault(case.construction_group, set()).add(case.label)
    assert all(len(labels) == 1 for labels in labels_by_group.values())


def test_p17_1_review_template_is_pending_and_complete() -> None:
    dataset = build_calibration_candidate()
    review = build_review_template(dataset)
    decisions = review["decisions"]
    assert isinstance(decisions, list)
    assert len(decisions) == 240
    assert {item["record_id"] for item in decisions} == {case.record_id for case in dataset.cases}
    assert {item["decision"] for item in decisions} == {"pending"}
