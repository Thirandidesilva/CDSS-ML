"""Assessment endpoints: the questionnaire itself, submitting answers, and reading
back history. submit_assessment() is intentionally thin — all the real scoring and
persistence logic lives in services/scoring.py so it stays out of the router.
"""
from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
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
from ..enums import AssessmentStatus, DogStatus, UserRole  # noqa: E402
from ..errors import ApiError, envelope  # noqa: E402
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
from ..schemas.assessment import (  # noqa: E402
    AssessmentIdRequest,
    AssessmentOut,
    AssessmentSubmitRequest,
    DogIdRequest,
    WeeklySummaryRequest,
)
from ..services.assessment_stats import band_cut_points, build_weekly_summary, compute_dog_stats  # noqa: E402
from ..services.scoring import run_assessment  # noqa: E402

router = APIRouter(prefix="/api/v1/assessment", tags=["assessment"])

_ASSESSMENT_EXAMPLE = {
    "assessment_id": "c1a2b3d4-5555-4e6f-8a9b-0123456789ab",
    "dog_id": "3a21c9e0-1111-4a2b-9c3d-abcdef123456",
    "session_number": 1,
    "theta_irt": None, "theta_calibrated": -0.376, "theta_se": 0.309,
    "anxiety_index": 0.136, "created_at": "2026-09-19T12:00:00",
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
# /assessment/all groups by dog_id (one admin call spans every owner's dogs, so a flat
# list mixing them together is awkward to filter client-side) — dog_id is hoisted out
# to the group level instead of repeated inside every assessment entry.
_GROUPED_ASSESSMENTS_EXAMPLE = {
    "dog_id": _ASSESSMENT_EXAMPLE["dog_id"],
    "assessments": [{k: v for k, v in _ASSESSMENT_EXAMPLE.items() if k != "dog_id"}],
}
_STATS_EXAMPLE = {
    "assessment_count": 5,
    "theta": {"average": 0.42, "median": 0.38, "n": 3, "score_model_name": "params_calibrated.csv"},
    "theta_se": {"average": 0.31, "median": 0.29},
    "rf_confidence": {"average": 0.81, "median": 0.83},
    "subscales": {
        "separation": {"average": 1.9, "median": 2.0}, "noise": {"average": 2.4, "median": 2.5},
        "fear": {"average": 0.6, "median": 0.5}, "aggression": {"average": 1.2, "median": 1.0},
        "compulsive": {"average": 0.8, "median": 1.0}, "physiological": {"average": 1.7, "median": 1.5},
    },
    "severity_band_counts": {"Low": 2, "Moderate": 3},
    "phenotype_counts": {"Noise-specific": 4, "Mild": 1},
}
_WEEKLY_SUMMARY_EXAMPLE = {
    "week_start": "2026-09-22", "week_end": "2026-09-28",
    "dogs": [{
        "dog_id": "3a21c9e0-1111-4a2b-9c3d-abcdef123456", "dog_name": "Rex",
        "days": [
            {"date": "2026-09-22", "weekday": "Monday", "assessed": True, "assessment_count": 1},
            {"date": "2026-09-23", "weekday": "Tuesday", "assessed": False, "assessment_count": 0},
            {"date": "2026-09-24", "weekday": "Wednesday", "assessed": False, "assessment_count": 0},
            {"date": "2026-09-25", "weekday": "Thursday", "assessed": False, "assessment_count": 0},
            {"date": "2026-09-26", "weekday": "Friday", "assessed": False, "assessment_count": 0},
            {"date": "2026-09-27", "weekday": "Saturday", "assessed": False, "assessment_count": 0},
            {"date": "2026-09-28", "weekday": "Sunday", "assessed": False, "assessment_count": 0},
        ],
    }],
}


def _assessment_json(row, request: Request) -> dict:
    # The index is built from the loaded scoring model's norms, the same ones the band uses.
    cut_points = band_cut_points(request.app.state.scoring_model[4])
    return AssessmentOut.from_orm_row(row, cut_points).model_dump(mode="json")


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
    return envelope(BusinessCode.SUCCESS, [_assessment_json(assessment, request)])


@router.get("/all", responses={
    **success(envelope(BusinessCode.SUCCESS, [_GROUPED_ASSESSMENTS_EXAMPLE])),
    **UNAUTHORIZED,
    **ADMIN_ONLY,
    **SERVER_ERROR,
})
def get_all_assessments(
    request: Request,
    _admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    # Ordered by dog_id first so rows for the same dog land together — grouping below
    # then just has to append in the order they arrive, no separate sort needed.
    rows = db.scalars(
        select(Assessment)
        .where(Assessment.status != AssessmentStatus.DELETED)
        .order_by(Assessment.dog_id, Assessment.created_at)
    ).all()

    grouped: dict = {}
    for r in rows:
        item = _assessment_json(r, request)
        dog_id = item.pop("dog_id")  # hoisted out to the group level, not repeated per item
        grouped.setdefault(dog_id, []).append(item)

    response = [{"dog_id": dog_id, "assessments": items} for dog_id, items in grouped.items()]
    return envelope(BusinessCode.SUCCESS, response)


@router.post("/list-by-dog", responses={
    **success(envelope(BusinessCode.SUCCESS, [_ASSESSMENT_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def list_dog_assessments(
    payload: DogIdRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # get_owned_dog confirms this caller may see this dog's data before anything else runs.
    dog = get_owned_dog(payload.dog_id, user=user, db=db)
    rows = db.scalars(
        select(Assessment)
        .where(Assessment.dog_id == dog.dog_id, Assessment.status != AssessmentStatus.DELETED)
        .order_by(Assessment.created_at)
    ).all()
    return envelope(BusinessCode.SUCCESS, [_assessment_json(r, request) for r in rows])


@router.post("/get", responses={
    **success(envelope(BusinessCode.SUCCESS, [_ASSESSMENT_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **ASSESSMENT_NOT_FOUND,
    **SERVER_ERROR,
})
def get_assessment_result(
    payload: AssessmentIdRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assessment = get_owned_assessment(payload.assessment_id, user=user, db=db)
    return envelope(BusinessCode.SUCCESS, [_assessment_json(assessment, request)])


@router.post("/delete", responses={
    **success(envelope(BusinessCode.SUCCESS, [{"message": "assessment deleted"}])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **ASSESSMENT_NOT_FOUND,
    **SERVER_ERROR,
})
def delete_assessment(
    payload: AssessmentIdRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Soft delete — the IRTResponse rows and any generated reports stay in the DB,
    # they just no longer show up in list/get results (see the ".status != DELETED"
    # filters above and in services/report.py's callers).
    assessment = get_owned_assessment(payload.assessment_id, user=user, db=db)
    assessment.status = AssessmentStatus.DELETED
    db.commit()
    return envelope(BusinessCode.SUCCESS, [{"message": "assessment deleted"}])


@router.post("/stats", responses={
    **success(envelope(BusinessCode.SUCCESS, [_STATS_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def get_assessment_stats(
    payload: DogIdRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dog = get_owned_dog(payload.dog_id, user=user, db=db)
    rows = db.scalars(
        select(Assessment)
        .where(Assessment.dog_id == dog.dog_id, Assessment.status != AssessmentStatus.DELETED)
        .order_by(Assessment.created_at)
    ).all()
    return envelope(BusinessCode.SUCCESS, [compute_dog_stats(rows)])


@router.post("/weekly-summary", responses={
    **success(envelope(BusinessCode.SUCCESS, [_WEEKLY_SUMMARY_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **SERVER_ERROR,
})
def get_weekly_summary(
    payload: WeeklySummaryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Same admin-override shape as dogs/list: omitted user_id (or your own) -> your own
    # week; any other user_id -> that user's week, admin only.
    target_user_id = payload.user_id or user.user_id
    if target_user_id != user.user_id and user.role != UserRole.ADMIN:
        raise ApiError(BusinessCode.OWNERSHIP_VIOLATION, "not your weekly summary")

    # Monday-Sunday of the CURRENT week, UTC — this project has no per-user timezone
    # support anywhere (see report_pdf_data.py), so "current week" means the server's.
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    dogs = db.scalars(
        select(Dog).where(Dog.user_id == target_user_id, Dog.status != DogStatus.DELETED)
    ).all()
    # created_at is a datetime column — comparing it against bare date objects behaves
    # inconsistently across dialects (especially SQLite's string-based comparison), so
    # the bounds are built as explicit UTC datetimes instead.
    range_start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(week_end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    assessments = db.scalars(
        select(Assessment).where(
            Assessment.dog_id.in_([dog.dog_id for dog in dogs]),
            Assessment.status != AssessmentStatus.DELETED,
            Assessment.created_at >= range_start,
            Assessment.created_at < range_end,
        )
    ).all()
    return envelope(BusinessCode.SUCCESS, [build_weekly_summary(dogs, assessments, week_start)])
