"""The only place that calls score_case() and persists its result. Never lets the raw
model tuple (fitted IRT arrays + loaded RF model) reach a response or a DB row.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import run_pipeline  # noqa: E402

from ..enums import AssessmentStatus  # noqa: E402
from ..models import Assessment, Dog, IRTResponse, Recommendation, User  # noqa: E402
from ..schemas.assessment import AssessmentSubmitRequest  # noqa: E402


def run_assessment(
    db: Session,
    dog: Dog,
    payload: AssessmentSubmitRequest,
    current_user: User,
    scoring_model,
) -> Assessment:
    # Drop dog_id before handing off to score_case() — it only wants the 12 raw items,
    # nothing about who the dog or the caller is.
    answers = payload.model_dump(exclude={"dog_id"})
    result = run_pipeline.score_case(answers, scoring_model, verbose=False)

    # score_case() returns a single bare "theta" — this is the one place that decides
    # which of the two DB columns it belongs in, based on which parameter file produced
    # it (scoring_model[0] is that filename, e.g. "params_calibrated.csv").
    pname = scoring_model[0]
    theta_irt = None
    theta_calibrated = None
    if pname.startswith("params_calibrated"):
        theta_calibrated = result["theta"]
    else:
        theta_irt = result["theta"]

    # 1st assessment for this dog, 2nd, 3rd, ... — counts only non-deleted rows, so a
    # deleted assessment doesn't leave a gap in the numbering for the next one.
    session_number = (
        db.scalar(
            select(func.count())
            .select_from(Assessment)
            .where(Assessment.dog_id == dog.dog_id, Assessment.status != AssessmentStatus.DELETED)
        )
        or 0
    ) + 1

    rec = result["recommendation"]
    # Convenience link only (see models.py's Assessment.recommendation_rec_id) — matched
    # by rule_id, but the full `rec` dict below is what's actually stored and displayed.
    rec_row = db.scalar(select(Recommendation).where(Recommendation.rule_id == rec["rule_id"]))

    assessment = Assessment(
        dog_id=dog.dog_id,
        session_number=session_number,
        theta_irt=theta_irt,
        theta_calibrated=theta_calibrated,
        theta_se=result["theta_se"],
        score_model_name=pname,
        severity_band=result["severity"],
        phenotype=result["phenotype"],
        rf_confidence=result["rf_confidence"],
        flag_irt=result["flag_irt"],
        flag_rf=result["flag_rf"],
        subscales=result["subscales"],
        recommendation_snapshot=rec,
        recommendation_rec_id=rec_row.rec_id if rec_row else None,
        created_by=current_user.user_id,
    )
    db.add(assessment)
    db.flush()  # assigns assessment.assessment_id (needed below) without committing yet

    # One row per answered item, using the same Q4..Q15 keys score_case() was given.
    for item_code in run_pipeline.ITEM_TEXT:
        db.add(IRTResponse(
            assessment_id=assessment.assessment_id,
            item_code=item_code,
            likert_value=answers[item_code],
        ))

    # Single commit: the assessment row and all 12 response rows succeed or fail together.
    db.commit()
    db.refresh(assessment)
    return assessment
