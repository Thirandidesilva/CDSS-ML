"""Report endpoints: generate a clinical/audit report from an assessment, list them,
and download one. download_report() is the one route in this whole API that does NOT
return the {"code","response"} envelope — see the comment on it below for why.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..codes import BusinessCode
from ..db import get_db
from ..deps import get_owned_assessment
from ..enums import UserRole
from ..errors import ApiError, envelope
from ..models import Report, User
from ..openapi_responses import (
    ADMIN_ONLY,
    ASSESSMENT_NOT_FOUND,
    FORBIDDEN,
    REPORT_NOT_FOUND,
    SERVER_ERROR,
    UNAUTHORIZED,
    success,
)
from ..schemas.report import ReportGenerateRequest
from ..services.report import build_report_content

router = APIRouter(prefix="/api/v1/report", tags=["report"])

_REPORT_EXAMPLE = {
    "report_id": "d2e3f4a5-6666-4b7c-9d8e-fedcba987654",
    "assessment_id": "c1a2b3d4-5555-4e6f-8a9b-0123456789ab",
    "dog_id": "3a21c9e0-1111-4a2b-9c3d-abcdef123456",
    "generated_by": "8f14e45f-ceea-4ee8-a5b1-1234567890ab",
    "generated_at": "2026-09-19T12:00:00+00:00",
    "report_format": "json", "status": "ready",
    "content": {"assessment_id": "c1a2b3d4-5555-4e6f-8a9b-0123456789ab", "theta_calibrated": -0.376,
                "severity_band": "Low", "phenotype": "Noise-specific", "flag_irt": False, "flag_rf": False},
}


def _report_out(report: Report) -> dict:
    return {
        "report_id": str(report.report_id),
        "assessment_id": str(report.assessment_id),
        "dog_id": str(report.dog_id),
        "generated_by": str(report.generated_by),
        "generated_at": report.generated_at.isoformat(),
        "report_format": report.report_format,
        "status": report.status.value,
        "content": report.content,
    }


def _get_owned_report(report_id: uuid.UUID, user: User, db: Session) -> Report:
    # Same 404-then-403 shape as deps.py's get_owned_dog/get_owned_assessment, but kept
    # local since only this router needs report ownership checks.
    report = db.get(Report, report_id)
    if report is None:
        raise ApiError(BusinessCode.REPORT_NOT_FOUND, "report not found")
    if user.role != UserRole.ADMIN and report.generated_by != user.user_id:
        raise ApiError(BusinessCode.OWNERSHIP_VIOLATION, "not your report")
    return report


@router.post("/generate", responses={
    **success(envelope(BusinessCode.SUCCESS, [_REPORT_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **ASSESSMENT_NOT_FOUND,
    **SERVER_ERROR,
})
def generate_report(
    payload: ReportGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # get_owned_assessment (not Depends here, same reason as submit_assessment: the id
    # comes from the request body, not the URL) confirms the caller may see this
    # assessment before any report content is built from it.
    assessment = get_owned_assessment(payload.assessment_id, user=user, db=db)
    content = build_report_content(assessment)
    report = Report(
        assessment_id=assessment.assessment_id,
        dog_id=assessment.dog_id,
        generated_by=user.user_id,
        content=content,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return envelope(BusinessCode.SUCCESS, [_report_out(report)])


@router.get("", responses={
    **success(envelope(BusinessCode.SUCCESS, [_REPORT_EXAMPLE])),
    **UNAUTHORIZED,
    **SERVER_ERROR,
})
def list_my_reports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Only the caller's own reports — see get_all_reports below for the admin version.
    reports = db.scalars(select(Report).where(Report.generated_by == user.user_id)).all()
    return envelope(BusinessCode.SUCCESS, [_report_out(r) for r in reports])


@router.get("/all", responses={
    **success(envelope(BusinessCode.SUCCESS, [_REPORT_EXAMPLE])),
    **UNAUTHORIZED,
    **ADMIN_ONLY,
    **SERVER_ERROR,
})
def get_all_reports(_admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db)):
    reports = db.scalars(select(Report)).all()
    return envelope(BusinessCode.SUCCESS, [_report_out(r) for r in reports])


@router.get("/download/{report_id}", responses={
    200: {
        "description": "The report file, streamed directly (not wrapped in the {code,response} envelope)",
        "content": {"application/json": {"example": _REPORT_EXAMPLE}},
    },
    **UNAUTHORIZED,
    **FORBIDDEN,
    **REPORT_NOT_FOUND,
    **SERVER_ERROR,
})
def download_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Deliberately a plain GET (every other single-item route above uses GET too, but
    # this one also skips the {"code","response"} envelope): browsers and curl expect
    # a GET link to hand back a downloadable file body directly, not a JSON envelope
    # to unwrap first. The Content-Disposition header is what makes a browser treat
    # this as a file save instead of just displaying the JSON.
    report = _get_owned_report(report_id, user, db)
    body = json.dumps(_report_out(report), indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="report_{report.report_id}.json"'},
    )
