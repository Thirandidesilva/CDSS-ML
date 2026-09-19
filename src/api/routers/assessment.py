"""Assessment endpoints: the questionnaire itself, submitting answers, and reading
back history. submit_assessment() is intentionally thin — all the real scoring and
persistence logic lives in services/scoring.py so it stays out of the router.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import run_pipeline  # noqa: E402

from ..auth import get_current_user, require_role  # noqa: E402
from ..codes import BusinessCode  # noqa: E402
from ..db import get_db  # noqa: E402
from ..deps import get_owned_assessment, get_owned_dog  # noqa: E402
from ..enums import AssessmentStatus, UserRole  # noqa: E402
from ..errors import envelope  # noqa: E402
from ..models import Assessment, Dog, User  # noqa: E402
from ..openapi_responses import (  # noqa: E402
    ADMIN_ONLY,
    ASSESSMENT_NOT_FOUND,
    DOG_NOT_FOUND,
    FORBIDDEN,
    SERVER_ERROR,
    UNAUTHORIZED,
    success,
    success_variants,
)
from ..schemas.assessment import AssessmentOut, AssessmentSubmitRequest  # noqa: E402
from ..services.scoring import run_assessment  # noqa: E402

router = APIRouter(prefix="/api/v1/assessment", tags=["assessment"])

_ASSESSMENT_EXAMPLE = {
    "assessment_id": "c1a2b3d4-5555-4e6f-8a9b-0123456789ab",
    "dog_id": "3a21c9e0-1111-4a2b-9c3d-abcdef123456",
    "session_number": 1,
    "theta_irt": None, "theta_calibrated": -0.376, "theta_se": 0.309,
    "severity_band": "Low", "phenotype": "Noise-specific", "rf_confidence": 0.79,
    "flag_irt": False, "flag_rf": False,
    "subscales": {"separation": 1.75, "noise": 2.0, "fear": 0.5,
                  "aggression": 4.0, "compulsive": 2.0, "physiological": 1.5},
    "recommendation": {
        "rule_id": "R-NOISE-LOW", "urgency": "routine",
        "action": "No behavioural intervention indicated by this screening...",
        "evidence": "MSD Veterinary Manual, Behavior Problems of Dogs...",
        "withheld": False, "withheld_reason": None,
        "caveats": ["This is a behavioural screening result, not a veterinary diagnosis."],
    },
}
_WITHHELD_ASSESSMENT_EXAMPLE = {
    **_ASSESSMENT_EXAMPLE,
    "theta_calibrated": 0.930, "theta_se": 0.536, "flag_irt": True,
    "recommendation": {
        **_ASSESSMENT_EXAMPLE["recommendation"],
        "urgency": "unknown",
        "action": "Recommendation withheld pending a more precise assessment; consult your veterinarian if you have concerns.",
        "withheld": True,
        "withheld_reason": "theta SE 0.536 exceeds 0.5; severity band is too imprecise to act on",
    },
}


@router.get("/questions", responses={
    **success(envelope(BusinessCode.SUCCESS, [{"item_code": "Q4", "text": "..."}])),
    **UNAUTHORIZED,
    **SERVER_ERROR,
})
def get_all_questions(_user: User = Depends(get_current_user)):
    # Read straight from run_pipeline.ITEM_TEXT — no DB table for questions, since the
    # 12 items are fixed by the research instrument, not something that changes at runtime.
    questions = [{"item_code": code, "text": text} for code, text in run_pipeline.ITEM_TEXT.items()]
    return envelope(BusinessCode.SUCCESS, questions)


@router.post("/submit", responses={
    **success_variants(
        ("scored", "Severity band is precise enough to act on", envelope(BusinessCode.SUCCESS, [_ASSESSMENT_EXAMPLE])),
        ("withheld", "theta SE too high — recommendation withheld, still HTTP 200",
         envelope(BusinessCode.SUCCESS, [_WITHHELD_ASSESSMENT_EXAMPLE])),
    ),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def submit_assessment(
    payload: AssessmentSubmitRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Called directly (not via Depends) because it needs payload.dog_id, which isn't
    # known until AssessmentSubmitRequest has already been parsed.
    dog = get_owned_dog(payload.dog_id, user=user, db=db)
    # Loaded once at app startup (app.py) and stashed here — never re-loaded per request.
    scoring_model = request.app.state.scoring_model
    assessment = run_assessment(db, dog, payload, user, scoring_model)
    return envelope(BusinessCode.SUCCESS, [AssessmentOut.from_orm_row(assessment).model_dump(mode="json")])


@router.get("/all", responses={
    **success(envelope(BusinessCode.SUCCESS, [_ASSESSMENT_EXAMPLE])),
    **UNAUTHORIZED,
    **ADMIN_ONLY,
    **SERVER_ERROR,
})
def get_all_assessments(_admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Assessment).where(Assessment.status != AssessmentStatus.DELETED)
    ).all()
    return envelope(BusinessCode.SUCCESS, [AssessmentOut.from_orm_row(r).model_dump(mode="json") for r in rows])


@router.get("/dog/{dog_id}", responses={
    **success(envelope(BusinessCode.SUCCESS, [_ASSESSMENT_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def list_dog_assessments(dog: Dog = Depends(get_owned_dog), db: Session = Depends(get_db)):
    # get_owned_dog already confirmed this caller may see this dog's data.
    rows = db.scalars(
        select(Assessment)
        .where(Assessment.dog_id == dog.dog_id, Assessment.status != AssessmentStatus.DELETED)
        .order_by(Assessment.created_at)
    ).all()
    return envelope(BusinessCode.SUCCESS, [AssessmentOut.from_orm_row(r).model_dump(mode="json") for r in rows])


@router.get("/{assessment_id}", responses={
    **success(envelope(BusinessCode.SUCCESS, [_ASSESSMENT_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **ASSESSMENT_NOT_FOUND,
    **SERVER_ERROR,
})
def get_assessment_result(assessment: Assessment = Depends(get_owned_assessment)):
    return envelope(BusinessCode.SUCCESS, [AssessmentOut.from_orm_row(assessment).model_dump(mode="json")])


@router.post("/delete/{assessment_id}", responses={
    **success(envelope(BusinessCode.SUCCESS, [{"message": "assessment deleted"}])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **ASSESSMENT_NOT_FOUND,
    **SERVER_ERROR,
})
def delete_assessment(
    assessment: Assessment = Depends(get_owned_assessment),
    db: Session = Depends(get_db),
):
    # Soft delete — the IRTResponse rows and any generated reports stay in the DB,
    # they just no longer show up in list/get results (see the ".status != DELETED"
    # filters above and in services/report.py's callers).
    assessment.status = AssessmentStatus.DELETED
    db.commit()
    return envelope(BusinessCode.SUCCESS, [{"message": "assessment deleted"}])
