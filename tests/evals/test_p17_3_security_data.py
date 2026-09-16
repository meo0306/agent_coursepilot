from __future__ import annotations

from collections import Counter

from evaluation.p17_3_security_data import (
    build_qualification_candidate,
    build_review_template,
)


def test_p17_3_qualification_is_balanced_unique_and_unrun() -> None:
    dataset = build_qualification_candidate(
        profile_file_sha256="a" * 64,
        selection_report_sha256="b" * 64,
        prior_text_hashes=set(),
    )

    assert len(dataset.cases) == 120
    assert Counter(case.label for case in dataset.cases) == {
        "malicious": 60,
        "hard_negative": 60,
    }
    assert Counter(case.language for case in dataset.cases) == {"en": 60, "zh": 60}
    assert len({case.text_sha256 for case in dataset.cases}) == 120
    assert dataset.qualification_run is False
    assert dataset.consumed_blind_access is False


def test_p17_3_qualification_rejects_prior_text_overlap() -> None:
    baseline = build_qualification_candidate(
        profile_file_sha256="a" * 64,
        selection_report_sha256="b" * 64,
        prior_text_hashes=set(),
    )

    try:
        build_qualification_candidate(
            profile_file_sha256="a" * 64,
            selection_report_sha256="b" * 64,
            prior_text_hashes={baseline.cases[0].text_sha256},
        )
    except AssertionError as exc:
        assert "overlaps prior Calibration" in str(exc)
    else:
        raise AssertionError("expected overlap rejection")


def test_p17_3_review_template_starts_pending_and_binds_release() -> None:
    dataset = build_qualification_candidate(
        profile_file_sha256="a" * 64,
        selection_report_sha256="b" * 64,
        prior_text_hashes=set(),
    )

    review = build_review_template(dataset, dataset_sha256="c" * 64)

    assert review["review_status"] == "pending_owner_review"
    assert review["dataset_sha256"] == "c" * 64
    assert review["profile_file_sha256"] == "a" * 64
    assert len(review["decisions"]) == 120
    assert {item["decision"] for item in review["decisions"]} == {"pending"}
