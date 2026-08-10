from __future__ import annotations

from tests.courserag.knowledge_points.conftest import evidence, windows


def test_short_section_is_one_reproducible_window() -> None:
    first = windows(evidence(1), evidence(2), maximum=200)
    second = windows(evidence(1), evidence(2), maximum=200)

    assert first == second
    assert len(first) == 1
    assert [item.evidence_id for item in first[0].evidence] == [
        f"ev1_{1:064x}",
        f"ev1_{2:064x}",
    ]


def test_long_section_uses_one_evidence_overlap_not_child_chunks() -> None:
    result = windows(
        *(evidence(index, f"证据{index}" * 6) for index in range(1, 7)),
        minimum=40,
        maximum=70,
    )

    assert len(result) > 1
    for previous, current in zip(result, result[1:], strict=False):
        assert previous.evidence[-1].evidence_id == current.evidence[0].evidence_id
    assert all(item.section_id == "section-1" for item in result)


def test_oversized_atomic_evidence_is_visible() -> None:
    result = windows(evidence(1, "超长" * 100), minimum=20, maximum=40)

    assert len(result) == 1
    assert result[0].warning_codes == ("OVERSIZED_EVIDENCE",)
