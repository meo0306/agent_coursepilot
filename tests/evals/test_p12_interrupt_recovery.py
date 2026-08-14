from evaluation.p12_interrupt_recovery import run


def test_cp_ds6_approved_input_is_structurally_ready() -> None:
    report = run()
    assert report["case_count"] == 24
    assert set(report["interrupt_counts"].values()) == {4}
    assert report["external_calls"] == 0
    assert report["gold_promotion"] is False
