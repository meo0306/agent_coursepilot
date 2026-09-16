"""Generate the final owner-review package from P16 closure artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.p16_closure import _review_package


def build_review_package(
    *,
    closure_report: Path,
    output_dir: Path,
    critical_decisions: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(closure_report.read_text(encoding="utf-8"))
    review_root = output_dir / "review"
    included: set[str] | None = None
    prior: dict[str, dict[str, Any]] | None = None
    if critical_decisions is not None:
        decisions = json.loads(critical_decisions.read_text(encoding="utf-8"))
        critical = [item for item in decisions["records"] if item.get("critical_defect")]
        included = {str(item["slide_id"]) for item in critical}
        prior = {str(item["slide_id"]): item for item in critical}
    _review_package(
        output_dir,
        list(payload.get("cases", [])),
        included_slide_ids=included,
        prior_decisions=prior,
    )
    return {
        "review_package": str(review_root / "review_package.json"),
        "decision_template": str(review_root / "review_decisions_template.json"),
        "index": str(review_root / "index.html"),
        "record_count": len(
            json.loads((review_root / "review_package.json").read_text(encoding="utf-8")).get(
                "records", []
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--closure-report", type=Path, default=Path("storage_eval/p16_closure/report.json")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p16_closure"))
    parser.add_argument("--critical-decisions", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            build_review_package(
                closure_report=args.closure_report,
                output_dir=args.output_dir,
                critical_decisions=args.critical_decisions,
            ),
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
