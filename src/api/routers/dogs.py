"""Dog CRUD endpoints. Every single-dog route (get/update/delete) calls get_owned_dog
(deps.py) directly to do the 404-then-403 ownership check — not via Depends() injection,
since the id now always comes from the parsed request body, never the URL path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_role
from ..codes import BusinessCode
from ..db import get_db
from ..deps import get_owned_dog
from ..enums import DogStatus, UserRole
from ..errors import ApiError, envelope
from ..models import Dog, User
from ..openapi_responses import (
    ADMIN_ONLY,
    DOG_NOT_FOUND,
    FORBIDDEN,
    SERVER_ERROR,
    UNAUTHORIZED,
    success,
)
from ..schemas.dog import DogCreateRequest, DogIdRequest, DogListRequest, DogUpdateRequest

router = APIRouter(prefix="/api/v1/dogs", tags=["dogs"])

_DOG_EXAMPLE = {
    "dog_id": "3a21c9e0-1111-4a2b-9c3d-abcdef123456",
    "user_id": "8f14e45f-ceea-4ee8-a5b1-1234567890ab",
    "dog_name": "Rex", "dog_breed": "Labrador", "dog_age": 4,
    "dog_gender": "male", "profile_picture": None,
}


def _dog_out(dog: Dog) -> dict:
    return {
        "dog_id": str(dog.dog_id),
        "user_id": str(dog.user_id),
        "dog_name": dog.dog_name,
        "dog_breed": dog.dog_breed,
        "dog_age": dog.dog_age,
        "dog_gender": dog.dog_gender.value if dog.dog_gender else None,
        "profile_picture": dog.profile_picture,
    }


@router.post("/create", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **SERVER_ERROR,
})
def create_dog(
    payload: DogCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # The dog is always owned by whoever is logged in — there's no "create a dog for
    # someone else" path, even for admins.
    dog = Dog(
        user_id=user.user_id,
        dog_name=payload.dog_name,
        dog_breed=payload.dog_breed,
        dog_age=payload.dog_age,
        dog_gender=payload.dog_gender,
        profile_picture=payload.profile_picture,
        created_by=user.user_id,
    )
    db.add(dog)
    db.commit()
    db.refresh(dog)
    return envelope(BusinessCode.SUCCESS, [_dog_out(dog)])


@router.post("/list", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **SERVER_ERROR,
})
def list_dogs(
    payload: DogListRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Omitted user_id (or your own id) -> your own dogs. Any other user_id -> that
    # user's dogs, admin only — for every owner's dogs at once, see get_all_dogs below.
    target_user_id = payload.user_id or user.user_id
    if target_user_id != user.user_id and user.role != UserRole.ADMIN:
        raise ApiError(BusinessCode.OWNERSHIP_VIOLATION, "not your dogs")
    dogs = db.scalars(
        select(Dog).where(Dog.user_id == target_user_id, Dog.status != DogStatus.DELETED)
    ).all()
    return envelope(BusinessCode.SUCCESS, [_dog_out(d) for d in dogs])


@router.get("/all", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **ADMIN_ONLY,
    **SERVER_ERROR,
})
def get_all_dogs(_admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db)):
    dogs = db.scalars(select(Dog).where(Dog.status != DogStatus.DELETED)).all()
    return envelope(BusinessCode.SUCCESS, [_dog_out(d) for d in dogs])


@router.post("/get", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def get_dog(
    payload: DogIdRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dog = get_owned_dog(payload.dog_id, user=user, db=db)
    return envelope(BusinessCode.SUCCESS, [_dog_out(dog)])


@router.post("/update", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def update_dog(
    payload: DogUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dog = get_owned_dog(payload.dog_id, user=user, db=db)
    for field in ("dog_name", "dog_breed", "dog_age", "dog_gender", "profile_picture"):
        value = getattr(payload, field)
        if value is not None:
            setattr(dog, field, value)
    dog.updated_by = user.user_id
    db.commit()
    db.refresh(dog)
    return envelope(BusinessCode.SUCCESS, [_dog_out(dog)])


@router.post("/delete", responses={
    **success(envelope(BusinessCode.SUCCESS, [{"message": "dog deleted"}])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def delete_dog(
    payload: DogIdRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dog = get_owned_dog(payload.dog_id, user=user, db=db)
    dog.status = DogStatus.DELETED
    dog.updated_by = user.user_id
    db.commit()
    return envelope(BusinessCode.SUCCESS, [{"message": "dog deleted"}])
