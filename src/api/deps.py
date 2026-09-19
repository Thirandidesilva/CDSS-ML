"""Ownership dependencies shared by dogs/assessment/report routers: 404 if the resource
doesn't exist at all, 403 if it exists but isn't the caller's (admins bypass the check).
"""
from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from .auth import get_current_user
from .codes import BusinessCode
from .db import get_db
from .enums import AssessmentStatus, DogStatus, UserRole
from .errors import ApiError
from .models import Assessment, Dog, User


def get_owned_dog(
    # FastAPI reads "dog_id" from the URL path (e.g. /api/v1/dogs/{dog_id}) and passes
    # it in here automatically, matched by parameter name — nothing else wires this up.
    dog_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dog:
    dog = db.get(Dog, dog_id)
    # Soft-deleted counts as "not found" — a deleted dog should behave as if it's gone.
    if dog is None or dog.status == DogStatus.DELETED:
        raise ApiError(BusinessCode.DOG_NOT_FOUND, "dog not found")
    # 404 first, then 403: don't reveal whether a dog you don't own even exists.
    if user.role != UserRole.ADMIN and dog.user_id != user.user_id:
        raise ApiError(BusinessCode.OWNERSHIP_VIOLATION, "not your dog")
    return dog


def get_owned_assessment(
    assessment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.status == AssessmentStatus.DELETED:
        raise ApiError(BusinessCode.ASSESSMENT_NOT_FOUND, "assessment not found")
    # Assessments don't have their own owner column — ownership is inherited from the
    # dog they belong to, via the assessment.dog relationship.
    if user.role != UserRole.ADMIN and assessment.dog.user_id != user.user_id:
        raise ApiError(BusinessCode.OWNERSHIP_VIOLATION, "not your assessment")
    return assessment
