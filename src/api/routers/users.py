"""User profile endpoints: get/update/delete self, plus the admin-only list-everyone route."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, hash_password, require_role, verify_password
from ..codes import BusinessCode
from ..db import get_db
from ..enums import AccountStatus, UserRole
from ..errors import ApiError, envelope
from ..models import User
from ..openapi_responses import ADMIN_ONLY, SERVER_ERROR, UNAUTHORIZED, UPLOAD_ERRORS, success, success_variants
from ..schemas.user import UserUpdateRequest
from ..services.cloudinary import resolve_picture

router = APIRouter(prefix="/api/v1/users", tags=["users"])

_USER_EXAMPLE = {
    "user_id": "8f14e45f-ceea-4ee8-a5b1-1234567890ab", "user_name": "alice",
    "first_name": "Alice", "last_name": "Smith", "email": "alice@example.com",
    "phone_number": "0771234567", "role": "owner", "profile_picture": None,
}


def _user_out(user: User) -> dict:
    # Shared by every route below so the public shape of a user is defined once —
    # notably, password_hash is never included.
    return {
        "user_id": str(user.user_id),
        "user_name": user.user_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "role": user.role.value,
        "profile_picture": user.profile_picture,
    }


@router.get("/me", responses={
    **success(envelope(BusinessCode.SUCCESS, [_USER_EXAMPLE])),
    **UNAUTHORIZED,
    **SERVER_ERROR,
})
def get_profile(user: User = Depends(get_current_user)):
    # get_current_user() already resolved "who is this" from the bearer token —
    # this route has nothing left to do but return them.
    return envelope(BusinessCode.SUCCESS, [_user_out(user)])


@router.post("/update", responses={
    **success_variants(
        ("updated", "Profile updated", envelope(BusinessCode.SUCCESS, [_USER_EXAMPLE])),
        ("duplicate_email", "Email already used by another account", envelope(BusinessCode.DUPLICATE_EMAIL, [
            {"message": "email already in use"}])),
        ("wrong_current_password", "current_password didn't match, so new_password was rejected",
         envelope(BusinessCode.INVALID_CREDENTIALS, [{"message": "current password is incorrect"}])),
    ),
    **UNAUTHORIZED,
    **UPLOAD_ERRORS,
    **SERVER_ERROR,
})
def update_profile(
    payload: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # A base64 photo is uploaded to Cloudinary first, so a failed upload aborts the whole
    # update before anything is changed; an ordinary URL (or None) passes straight through.
    profile_picture = resolve_picture(payload.profile_picture, f"pawsitivity/users/{user.user_id}")

    # Changing email needs a uniqueness check against every OTHER user (hence
    # User.user_id != user.user_id) — a user "changing" their email to their own
    # current email shouldn't trip the duplicate check.
    if payload.email and payload.email != user.email:
        if db.scalar(select(User).where(User.email == payload.email, User.user_id != user.user_id)):
            raise ApiError(BusinessCode.DUPLICATE_EMAIL, "email already in use")
        user.email = payload.email

    # Only overwrite fields the caller actually sent (None means "leave unchanged").
    for field in ("first_name", "last_name", "phone_number", "profile_picture"):
        value = profile_picture if field == "profile_picture" else getattr(payload, field)
        if value is not None:
            setattr(user, field, value)

    if payload.new_password:
        # Changing the password requires proving you know the current one — even
        # though the caller is already authenticated via the bearer token.
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise ApiError(BusinessCode.INVALID_CREDENTIALS, "current password is incorrect")
        user.password_hash = hash_password(payload.new_password)

    db.commit()
    db.refresh(user)
    return envelope(BusinessCode.SUCCESS, [_user_out(user)])


@router.post("/delete", responses={
    **success(envelope(BusinessCode.SUCCESS, [{"message": "account deleted"}])),
    **UNAUTHORIZED,
    **SERVER_ERROR,
})
def delete_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Soft delete only — the row stays for the assessment history it's linked to, but
    # get_current_user() will reject this user's token on every future request.
    user.status = AccountStatus.DELETED
    db.commit()
    return envelope(BusinessCode.SUCCESS, [{"message": "account deleted"}])


@router.get("", responses={
    **success(envelope(BusinessCode.SUCCESS, [_USER_EXAMPLE])),
    **UNAUTHORIZED,
    **ADMIN_ONLY,
    **SERVER_ERROR,
})
def get_all_users(_admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db)):
    # `_admin` is intentionally unused beyond gating access — require_role() already
    # raised 403 before this line runs if the caller isn't an admin.
    users = db.scalars(select(User)).all()
    return envelope(BusinessCode.SUCCESS, [_user_out(u) for u in users])
