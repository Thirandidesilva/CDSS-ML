"""Runs the pytest suite and buckets results by area (backend API / ML core pipeline /
report-PDF service) for the thesis's Functionality evaluation section.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

# Report/PDF service is called out on its own since it's currently uncommitted work
# (see docs/THESIS_GUIDE.md §7) and must not be presented as a finished subsystem.
CATEGORIES = {
    "Backend / API": [
        "test_api_assessment.py", "test_api_auth.py", "test_api_dogs.py",
        "test_api_report.py", "test_api_users.py",
    ],
    "ML core pipeline": [
        "test_irt.py", "test_rules.py", "test_longitudinal.py", "test_cluster.py",
        "test_fit_params.py", "test_pipeline.py", "test_run_pipeline.py",
        "test_score_cohort.py",
    ],
    "Report / PDF generation service": [
        "test_report_pdf_helpers.py",
    ],
}

_RESULT_LINE = re.compile(r"^(tests/\S+\.py)::(\S+) (PASSED|FAILED|ERROR)")


def _category_for(file_name: str) -> str:
    for category, files in CATEGORIES.items():
        if file_name in files:
            return category
    return "Uncategorized"


def run_suite() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v"],
        cwd=ROOT, capture_output=True, text=True,
    )

    tests_by_category: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    tests_by_category["Uncategorized"] = []

    for line in proc.stdout.splitlines():
        match = _RESULT_LINE.match(line)
        if not match:
            continue
        path, test_name, outcome = match.groups()
        file_name = path.split("/")[-1]
        tests_by_category[_category_for(file_name)].append({
            "file": file_name, "test": test_name, "outcome": outcome,
        })

    tests_by_category = {c: t for c, t in tests_by_category.items() if t}

    summary = {}
    for category, tests in tests_by_category.items():
        passed = sum(1 for t in tests if t["outcome"] == "PASSED")
        failed = sum(1 for t in tests if t["outcome"] != "PASSED")
        summary[category] = {"total": len(tests), "passed": passed, "failed": failed}

    return {
        "summary": summary,
        "total": sum(s["total"] for s in summary.values()),
        "total_passed": sum(s["passed"] for s in summary.values()),
        "total_failed": sum(s["failed"] for s in summary.values()),
        "tests_by_category": tests_by_category,
        "pytest_exit_code": proc.returncode,
    }


def main():
    result = run_suite()

    RESULTS.mkdir(exist_ok=True)
    dest = RESULTS / "functionality_test_report.json"
    with open(dest, "w") as f:
        json.dump(result, f, indent=2)
    print(f"wrote {dest}\n")

    print(f"{'category':<35}{'total':>8}{'passed':>8}{'failed':>8}")
    for category, s in result["summary"].items():
        print(f"{category:<35}{s['total']:>8}{s['passed']:>8}{s['failed']:>8}")
    print(f"{'TOTAL':<35}{result['total']:>8}{result['total_passed']:>8}{result['total_failed']:>8}")


if __name__ == "__main__":
    main()
