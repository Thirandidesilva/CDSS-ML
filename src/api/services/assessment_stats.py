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


def band_cut_points(norms) -> tuple:
    """(cut_75, cut_90, cut_99) from the scoring model's population-norms table — the same
    75th/90th percentile theta cut-points that decide the Low/Moderate/High band. cut_99 is
    None when the table has no 99th percentile.
    """
    cut = norms.set_index("percentile").theta_cutpoint
    cut_99 = float(cut.loc[99]) if 99 in cut.index else None
    return float(cut.loc[75]), float(cut.loc[90]), cut_99


def anxiety_index(theta: float, cut_75: float, cut_90: float, cut_99=None) -> float:
    """theta on a 0-1 scale that always agrees with the severity band.

    The band itself comes from theta against the population 75th/90th percentile cut-points
    (calibrate.assign_band), so the index is a piecewise-linear map that pins those cut-points
    to fixed positions: Low always lands in [0, 1/3), Moderate in [1/3, 2/3), High in
    [2/3, 1]. Inside a band it rises smoothly with theta, so a rising score is visible before
    it crosses into the next band. Not a percentile and not a sum of item scores: the band
    and theta stay the clinical result, this is a display scale.

    Anchors: (cut_75 - 2u -> 0), (cut_75 -> 1/3), (cut_90 -> 2/3), (cut_99 -> 1) with
    u = cut_90 - cut_75; when there is no usable 99th percentile the top anchor is cut_90 + 2u.
    Values beyond the outer anchors clamp to 0 and 1.
    """
    unit = cut_90 - cut_75
    bottom = cut_75 - 2 * unit
    top = cut_99 if cut_99 is not None and cut_99 > cut_90 else cut_90 + 2 * unit
    anchors = [(bottom, 0.0), (cut_75, 1 / 3), (cut_90, 2 / 3), (top, 1.0)]

    if theta <= anchors[0][0]:
        return 0.0
    if theta >= anchors[-1][0]:
        return 1.0
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if theta < x1:
            return round(y0 + (theta - x0) / (x1 - x0) * (y1 - y0), 3)
    return 1.0


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


def build_weekly_summary(
    dogs: list, assessments: list, week_start: date, utc_offset_minutes: int = 0
) -> dict:
    """dogs: the target user's non-deleted Dog rows. assessments: their non-deleted
    Assessment rows already filtered to [week_start, week_start+6]. Every dog appears
    with a full 7-day grid even if it had zero activity — a frontend calendar needs
    the full week, not just the days/dogs with something to show. Each assessment counts
    on the day it falls on at `utc_offset_minutes` from UTC (its created_at is UTC).
    """
    offset = timedelta(minutes=utc_offset_minutes)
    week_end = week_start + timedelta(days=6)

    by_dog_and_day: dict = {}
    for a in assessments:
        by_dog_and_day.setdefault(a.dog_id, Counter())[(a.created_at + offset).date()] += 1

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
