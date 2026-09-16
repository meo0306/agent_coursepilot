from evaluation.system_optimization.baseline_runner import run_baseline


def test_offline_baseline_uses_only_loader_validated_approved_data() -> None:
    report = run_baseline()

    assert report["dataset_status"] == "approved"
    assert report["quality_metrics_eligible"] is True
    assert report["candidate_labels_are_gold"] is False
    assert report["human_approved_adequacy_eligible"] is True
    assert (
        report["historical_reference"]["new_dev_baseline"]["status"]
        == "pending_provider_authorization"
    )
    assert report["task_cases_checked"] == 27
    assert report["failure_replays_checked"] == 7
    assert report["external_provider_calls"] == 0
    assert report["p18_test_or_blind_loaded"] is False


def test_offline_baseline_can_filter_one_artifact() -> None:
    report = run_baseline(artifact="exam", prefer_approved=False)

    assert report["task_cases_checked"] == 9
    assert set(report["coverage"]) == {"exam"}
    assert report["coverage"]["exam"]["output_counts"] == [2, 4, 6]
