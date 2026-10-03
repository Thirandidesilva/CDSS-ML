"""Assembles the flat dict of template variables the vet-report PDF needs, from the
Assessment/Dog/User/IRTResponse rows plus the scoring model's population norms.
No Jinja2, no Playwright, no HTTP concerns — just data.
"""
from __future__ import annotations

from typing import Optional

import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import run_pipeline    # noqa: E402
import longitudinal    # noqa: E402 - track_theta_change(), the blessed trend-detection entry point

from ..enums import AssessmentStatus  # noqa: E402
from ..models import Assessment  # noqa: E402
from .report_chart import render_severity_chart_svg  # noqa: E402
from .report_sources import detect_sources  # noqa: E402

_SUBSCALE_LABELS = {
    "separation": "Separation-related",
    "noise": "Noise sensitivity",
    "fear": "Fear",
    "aggression": "Aggression",
    "compulsive": "Compulsive",
    "physiological": "Physiological",
}
_SUBSCALE_ORDER = list(_SUBSCALE_LABELS)
_LIKERT_BY_VALUE = {v: k for k, v in run_pipeline.LIKERT.items()}
_ITEM_TO_SUBSCALE = {
    item: _SUBSCALE_LABELS[name] for name, items in run_pipeline.SUBSCALES.items() for item in items
}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _report_display_id(report_id: uuid.UUID, generated_at: datetime) -> str:
    digits = int(uuid.UUID(str(report_id)).hex[:8], 16) % 10000
    return f"PWS-{generated_at.year}-{digits:04d}"


def _owner_display_name(user) -> str:
    if user.first_name and user.last_name:
        return f"{user.first_name[0]}. {user.last_name}"
    return user.user_name


def _theta_of(assessment: Assessment) -> float:
    return assessment.theta_irt if assessment.theta_irt is not None else assessment.theta_calibrated


def _build_alert_banner(assessment: Assessment, previous: Optional[Assessment]) -> Optional[dict]:
    rec = assessment.recommendation_snapshot
    if not (rec["withheld"] or rec["urgency"] == "prompt"):
        return None

    if rec["withheld"]:
        return {"lead": "Veterinary review recommended.", "body": rec["withheld_reason"]}

    body = f"This assessment returned a {assessment.severity_band.value} severity level"
    if (
        previous is not None
        and previous.score_model_name == assessment.score_model_name
    ):
        change = longitudinal.track_theta_change(
            theta_before=_theta_of(previous), theta_after=_theta_of(assessment),
            se_before=previous.theta_se, se_after=assessment.theta_se,
        )
        if change["detectable"]:
            body += " with an escalating trend" if change["delta"] > 0 else " with an improving trend"
    body += ". Clinical confirmation and a behavioural consultation are advised."
    return {"lead": "Veterinary review recommended.", "body": body}


def build_pdf_context(
    assessment: Assessment,
    report_id: uuid.UUID,
    generated_at: datetime,
    scoring_model,
    db: Session,
) -> dict:
    dog = assessment.dog
    owner = dog.owner

    norms = scoring_model[4]
    cut = norms.set_index("percentile").theta_cutpoint
    cut_75, cut_90 = float(cut.loc[75]), float(cut.loc[90])

    assessments_on_record = db.scalar(
        select(func.count())
        .select_from(Assessment)
        .where(Assessment.dog_id == dog.dog_id, Assessment.status != AssessmentStatus.DELETED)
    )

    history = db.scalars(
        select(Assessment)
        .where(
            Assessment.dog_id == dog.dog_id,
            Assessment.status != AssessmentStatus.DELETED,
            Assessment.session_number <= assessment.session_number,
        )
        .order_by(Assessment.session_number)
    ).all()
    previous = history[-2] if len(history) >= 2 else None

    chart_points = [(a.created_at.strftime("%d %b %Y"), _theta_of(a)) for a in history]
    chart_svg = render_severity_chart_svg(chart_points, cut_75, cut_90)

    subscale_values = {name: assessment.subscales[name] for name in _SUBSCALE_ORDER}
    highest_subscale = max(subscale_values, key=lambda name: subscale_values[name])
    subscale_rows = [
        {
            "label": _SUBSCALE_LABELS[name],
            "value": subscale_values[name],
            "pct": subscale_values[name] / 4 * 100,
            "is_highlight": name == highest_subscale,
        }
        for name in _SUBSCALE_ORDER
    ]

    rec = assessment.recommendation_snapshot
    recommendation_header = (
        f"{assessment.severity_band.value} severity • assessment withheld"
        if rec["withheld"]
        else f"{assessment.severity_band.value} severity • {assessment.phenotype.value} presentation"
    )
    recommendation_bullets = [s.strip() for s in _SENTENCE_SPLIT.split(rec["action"]) if s.strip()]

    theta = _theta_of(assessment)
    theta_ci_low = round(theta - 1.96 * assessment.theta_se, 2)
    theta_ci_high = round(theta + 1.96 * assessment.theta_se, 2)

    questionnaire_rows = [
        {
            "item_code": r.item_code,
            "text": run_pipeline.ITEM_TEXT[r.item_code],
            "subscale_label": _ITEM_TO_SUBSCALE[r.item_code],
            "value": r.likert_value,
            "likert_label": _LIKERT_BY_VALUE[r.likert_value],
        }
        for r in sorted(assessment.responses, key=lambda r: int(r.item_code[1:]))
    ]

    return {
        "report_display_id": _report_display_id(report_id, generated_at),
        "generated_at_display": generated_at.strftime("%d %b %Y, %H:%M"),
        "assessment_date_display": assessment.created_at.strftime("%d %b %Y"),
        "dog_name": dog.dog_name,
        "dog_breed_display": dog.dog_breed or "Not recorded",
        "dog_age_display": f"{dog.dog_age} years" if dog.dog_age is not None else "Not recorded",
        "dog_gender_display": dog.dog_gender.value.capitalize() if dog.dog_gender else "Unknown",
        "owner_display_name": _owner_display_name(owner),
        "assessments_on_record": assessments_on_record,
        "severity_band": assessment.severity_band.value,
        "phenotype": assessment.phenotype.value,
        "rf_confidence_pct": round(assessment.rf_confidence * 100),
        "theta": round(theta, 2),
        "theta_se": round(assessment.theta_se, 2),
        "theta_ci_low": theta_ci_low,
        "theta_ci_high": theta_ci_high,
        "subscale_rows": subscale_rows,
        "recommendation_header": recommendation_header,
        "recommendation_rationale": rec["evidence"],
        "recommendation_bullets": recommendation_bullets,
        "recommendation_caveats": rec["caveats"],
        "recommendation_sources": detect_sources(rec["action"], rec["evidence"]),
        "alert_banner": _build_alert_banner(assessment, previous),
        "chart_svg": chart_svg,
        "questionnaire_rows": questionnaire_rows,
    }
