"""Pure computation for the two assessment-analytics endpoints — no DB access, no
Jinja2, no HTTP concerns, same separation-of-concerns as report_pdf_data.py.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, timedelta

_SUBSCALE_KEYS = ["separation", "noise", "fear", "aggression", "compulsive", "physiological"]
_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _theta_of(assessment) -> float:
    return assessment.theta_irt if assessment.theta_irt is not None else assessment.theta_calibrated


def _avg_median(values: list) -> dict:
    return {"average": round(statistics.mean(values), 2), "median": round(statistics.median(values), 2)}


def compute_dog_stats(rows: list) -> dict:
    """rows: this dog's non-deleted Assessment rows, any order (sorted internally)."""
    assessment_count = len(rows)
    if assessment_count == 0:
        return {
            "assessment_count": 0,
            "theta": None,
            "theta_se": None,
            "rf_confidence": None,
            "subscales": None,
            "severity_band_counts": {},
            "phenotype_counts": {},
        }

    rows = sorted(rows, key=lambda r: r.created_at)

    # Averaging theta across different parameter sets (own vs. calibrated) isn't
    # statistically valid — same concern report_pdf_data.py already guards against for
    # trend claims. Only assessments sharing the most recent score_model_name count.
    latest_model = rows[-1].score_model_name
    theta_rows = [r for r in rows if r.score_model_name == latest_model]
    theta_stats = {
        **_avg_median([_theta_of(r) for r in theta_rows]),
        "n": len(theta_rows),
        "score_model_name": latest_model,
    }

    # rf_confidence, theta_se, and the 6 subscale means are on fixed scales regardless
    # of parameter set, so they're safely aggregated over the FULL history.
    theta_se_stats = _avg_median([r.theta_se for r in rows])
    rf_confidence_stats = _avg_median([r.rf_confidence for r in rows])
    subscale_stats = {key: _avg_median([r.subscales[key] for r in rows]) for key in _SUBSCALE_KEYS}

    severity_band_counts = dict(Counter(r.severity_band.value for r in rows))
    phenotype_counts = dict(Counter(r.phenotype.value for r in rows))

    return {
        "assessment_count": assessment_count,
        "theta": theta_stats,
        "theta_se": theta_se_stats,
        "rf_confidence": rf_confidence_stats,
        "subscales": subscale_stats,
        "severity_band_counts": severity_band_counts,
        "phenotype_counts": phenotype_counts,
    }


def build_weekly_summary(dogs: list, assessments: list, week_start: date) -> dict:
    """dogs: the target user's non-deleted Dog rows. assessments: their non-deleted
    Assessment rows already filtered to [week_start, week_start+6]. Every dog appears
    with a full 7-day grid even if it had zero activity — a frontend calendar needs
    the full week, not just the days/dogs with something to show.
    """
    week_end = week_start + timedelta(days=6)

    by_dog_and_day: dict = {}
    for a in assessments:
        by_dog_and_day.setdefault(a.dog_id, Counter())[a.created_at.date()] += 1

    dog_summaries = []
    for dog in dogs:
        day_counts = by_dog_and_day.get(dog.dog_id, Counter())
        days = []
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            count = day_counts.get(day, 0)
            days.append({
                "date": day.isoformat(),
                "weekday": _WEEKDAY_NAMES[offset],
                "assessed": count > 0,
                "assessment_count": count,
            })
        dog_summaries.append({"dog_id": str(dog.dog_id), "dog_name": dog.dog_name, "days": days})

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "dogs": dog_summaries,
    }
