"""Dog CRUD endpoints. Every single-dog route (get/update/delete) goes through
get_owned_dog (deps.py), which does the 404-then-403 ownership check once so it
doesn't need repeating in each handler below.
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
from ..errors import envelope
from ..models import Dog, User
from ..openapi_responses import (
    ADMIN_ONLY,
    DOG_NOT_FOUND,
    FORBIDDEN,
    SERVER_ERROR,
    UNAUTHORIZED,
    success,
)
from ..schemas.dog import DogCreateRequest, DogUpdateRequest

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


@router.get("", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **SERVER_ERROR,
})
def list_dogs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Only the caller's OWN dogs — for every owner's dogs, see get_all_dogs below.
    dogs = db.scalars(
        select(Dog).where(Dog.user_id == user.user_id, Dog.status != DogStatus.DELETED)
    ).all()
    return envelope(BusinessCode.SUCCESS, [_dog_out(d) for d in dogs])


# Registered BEFORE "/{dog_id}" below — FastAPI matches routes in registration order,
# so GET /api/v1/dogs/all must be defined here or it would instead be swallowed by
# "/{dog_id}" (with dog_id="all", which would then fail UUID parsing).
@router.get("/all", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **ADMIN_ONLY,
    **SERVER_ERROR,
})
def get_all_dogs(_admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db)):
    dogs = db.scalars(select(Dog).where(Dog.status != DogStatus.DELETED)).all()
    return envelope(BusinessCode.SUCCESS, [_dog_out(d) for d in dogs])


@router.get("/{dog_id}", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def get_dog(dog: Dog = Depends(get_owned_dog)):
    # get_owned_dog reads "dog_id" out of the URL itself (see deps.py) — nothing here
    # has to mention it explicitly.
    return envelope(BusinessCode.SUCCESS, [_dog_out(dog)])


@router.post("/update/{dog_id}", responses={
    **success(envelope(BusinessCode.SUCCESS, [_DOG_EXAMPLE])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def update_dog(
    payload: DogUpdateRequest,
    dog: Dog = Depends(get_owned_dog),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for field in ("dog_name", "dog_breed", "dog_age", "dog_gender", "profile_picture"):
        value = getattr(payload, field)
        if value is not None:
            setattr(dog, field, value)
    dog.updated_by = user.user_id
    db.commit()
    db.refresh(dog)
    return envelope(BusinessCode.SUCCESS, [_dog_out(dog)])


@router.post("/delete/{dog_id}", responses={
    **success(envelope(BusinessCode.SUCCESS, [{"message": "dog deleted"}])),
    **UNAUTHORIZED,
    **FORBIDDEN,
    **DOG_NOT_FOUND,
    **SERVER_ERROR,
})
def delete_dog(
    dog: Dog = Depends(get_owned_dog),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # POST, not GET, even though there's no request body — a GET here would be an
    # unsafe destructive action (browsers/proxies can cache or prefetch GETs).
    dog.status = DogStatus.DELETED
    dog.updated_by = user.user_id
    db.commit()
    return envelope(BusinessCode.SUCCESS, [{"message": "dog deleted"}])
