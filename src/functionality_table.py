"""Prints a per-functionality table (Total / Success / Failure) from `pytest -v` output.

Usage: pytest tests/ -v | python src/functionality_table.py
Each test is assigned to the first functionality whose pattern matches "<file>::<test name>",
so ordering below matters (ownership checks come before the feature they belong to).
"""
from __future__ import annotations

import re
import sys

# (functionality, regex matched against "<file>::<test name>")
FUNCTIONALITIES = [
    ("Ownership and authorization checks", r"someone_else|requires_admin|returns_403"),
    ("User registration", r"test_register_then_login|test_duplicate_email"),
    ("User login and authentication", r"test_login_wrong_password|test_missing_token|test_api_refresh\.py"),
    ("Forget username / password recovery", r"forget_|otp|username_recovery|unknown_email|resend|network_failure_reaching"),
    ("Service health and configuration", r"openapi|test_health|test_engine_uses_a_pool"),
    ("Dog profile management (add, view, update, delete)", r"test_api_dogs\.py"),
    ("Profile picture upload", r"test_api_profile_pictures\.py"),
    ("User profile endpoints", r"test_api_users\.py"),
    ("Assessment submission endpoint", r"test_get_all_questions|test_normal_case|test_withheld_case|test_missing_item|test_out_of_range_value|test_wrong_type|test_session_number|test_submit_returns"),
    ("Assessment history retrieval", r"test_list_dog_assessment|test_get_nonexistent_assessment|test_delete_assessment|groups_by_dog_id|test_list_and_get_return"),
    ("Assessment statistic endpoints", r"test_stats_|test_weekly_summary"),
    ("Anxiety index and severity bands (Low/Moderate/High)", r"anxiety_index|band_cut_points"),
    ("IRT graded response model scoring", r"test_irt\.py|test_fit_params\.py"),
    ("Phenotype clustering and random forest", r"test_cluster\.py|test_pipeline\.py"),
    ("Recommendation rules engine", r"test_rules\.py"),
    ("Longitudinal change tracking", r"test_longitudinal\.py"),
    ("Pipeline and cohort scoring", r"test_run_pipeline\.py|test_score_cohort\.py"),
    ("PDF report API (generate, download, list)", r"test_api_report\.py"),
    ("PDF chart generation", r"test_chart_"),
    ("PDF rendering and source detection (ReportLab)", r"test_report_pdf_helpers\.py"),
]

_LINE = re.compile(r"^tests/(\S+\.py)::(.+?) (PASSED|FAILED|ERROR)")


def main() -> int:
    rows = {name: [0, 0] for name, _ in FUNCTIONALITIES}  # [passed, failed]
    other = [0, 0]
    for line in sys.stdin:
        m = _LINE.match(line)
        if not m:
            continue
        key = f"{m.group(1)}::{m.group(2)}"
        bucket = next((rows[n] for n, rx in FUNCTIONALITIES if re.search(rx, key)), other)
        bucket[0 if m.group(3) == "PASSED" else 1] += 1

    if any(other):
        rows["Other"] = other
    width = max(len(n) for n in rows) + 2
    print(f"{'Functionality':<{width}}{'Total Test':>12}{'Success':>10}{'Failure':>10}")
    print("-" * (width + 32))
    tp = tf = 0
    for name, (p, f) in rows.items():
        if p + f == 0:
            continue
        tp += p
        tf += f
        print(f"{name:<{width}}{p + f:>12}{p:>10}{f:>10}")
    print("-" * (width + 32))
    print(f"{'TOTAL':<{width}}{tp + tf:>12}{tp:>10}{tf:>10}")
    return 1 if tf else 0


if __name__ == "__main__":
    sys.exit(main())
