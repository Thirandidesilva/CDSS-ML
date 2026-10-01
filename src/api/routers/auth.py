"""Auth endpoints: register, login, forget-username (plain email lookup),
forget-password (OTP-gated) + reset-password. None of these require a logged-in
user — that's why no route here takes `Depends(get_current_user)`, unlike every
other router.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_access_token, create_reset_token, hash_password, verify_password, verify_reset_token
from ..codes import BusinessCode
from ..db import get_db
from ..enums import OtpPurpose
from ..errors import ApiError, envelope
from ..models import User
from ..openapi_responses import SERVER_ERROR, success_variants
from ..schemas.auth import (
    ForgetPasswordRequest,
    ForgetUsernameRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyOtpRequest,
)
from ..services import email as email_service
from ..services import otp as otp_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", responses={
    **success_variants(
        ("registered", "New account created", envelope(BusinessCode.SUCCESS, [{
            "user_id": "8f14e45f-ceea-4ee8-a5b1-1234567890ab",
            "user_name": "alice", "email": "alice@example.com", "role": "owner",
        }])),
        ("duplicate_email", "Email already registered", envelope(BusinessCode.DUPLICATE_EMAIL, [
            {"message": "email already registered"}])),
        ("duplicate_username", "Username already taken", envelope(BusinessCode.DUPLICATE_USERNAME, [
            {"message": "username already taken"}])),
    ),
    **SERVER_ERROR,
})
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # Both checked up front so the error names the actual conflict (email vs username)
    # instead of relying on the DB's unique constraint to fail generically.
    if db.scalar(select(User).where(User.email == payload.email)):
        raise ApiError(BusinessCode.DUPLICATE_EMAIL, "email already registered")
    if db.scalar(select(User).where(User.user_name == payload.user_name)):
        raise ApiError(BusinessCode.DUPLICATE_USERNAME, "username already taken")

    user = User(
        user_name=payload.user_name,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),  # never store the plaintext password
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # re-reads the row so user.user_id (server-generated) is populated

    return envelope(BusinessCode.SUCCESS, [{
        "user_id": str(user.user_id),
        "user_name": user.user_name,
        "email": user.email,
        "role": user.role.value,
    }])


@router.post("/login", responses={
    **success_variants(
        ("logged_in", "Valid credentials", envelope(BusinessCode.SUCCESS, [{
            "access_token": "eyJhbGciOiJIUzI1NiIs...", "token_type": "bearer", "expires_in": 3600,
            "user": {"user_id": "8f14e45f-ceea-4ee8-a5b1-1234567890ab", "role": "owner"},
        }])),
        ("invalid_credentials", "Wrong username/email or password", envelope(BusinessCode.INVALID_CREDENTIALS, [
            {"message": "invalid username/email or password"}])),
    ),
    **SERVER_ERROR,
})
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    # Accepts either the username or the email in the same field.
    user = db.scalar(
        select(User).where(
            (User.user_name == payload.user_name_or_email) | (User.email == payload.user_name_or_email)
        )
    )
    # Same error for "no such user" and "wrong password" — never reveal which one it
    # was, or an attacker could use this endpoint to find out which emails are registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(BusinessCode.INVALID_CREDENTIALS, "invalid username/email or password")

    token, expires_in = create_access_token(user)
    return envelope(BusinessCode.SUCCESS, [{
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": {"user_id": str(user.user_id), "role": user.role.value},
    }])


@router.post("/forget-username", responses={
    **success_variants(
        ("found", "Account exists — username emailed", envelope(BusinessCode.SUCCESS, [
            {"message": "your username has been emailed to you"}])),
        ("not_found", "No account with that email", envelope(BusinessCode.ACCOUNT_NOT_FOUND, [
            {"message": "we couldn't find an account with that email"}])),
    ),
    **SERVER_ERROR,
})
def forget_username(payload: ForgetUsernameRequest, db: Session = Depends(get_db)):
    # No OTP step here (unlike forget-password below) — a username is not a secret
    # the way a password-reset capability is, so there's nothing worth gating behind
    # a verification code. One lookup, one email, done.
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise ApiError(BusinessCode.ACCOUNT_NOT_FOUND, "we couldn't find an account with that email")

    email_service.send_email(
        user.email, "Your Pawsitivity username", f"Your username is: {user.user_name}",
    )
    return envelope(BusinessCode.SUCCESS, [{"message": "your username has been emailed to you"}])


@router.post("/forget-password", responses={
    **success_variants(
        ("found", "Account exists — a verification code was emailed", envelope(BusinessCode.SUCCESS, [
            {"message": "a verification code has been sent to your email"}])),
        ("not_found", "No account with that email", envelope(BusinessCode.ACCOUNT_NOT_FOUND, [
            {"message": "no account with that email"}])),
    ),
    **SERVER_ERROR,
})
def forget_password(payload: ForgetPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise ApiError(BusinessCode.ACCOUNT_NOT_FOUND, "no account with that email")

    code = otp_service.create_otp(db, user, OtpPurpose.FORGET_PASSWORD)
    email_service.send_email(
        user.email, "Your Pawsitivity verification code",
        f"Your verification code is {code}. It expires in a few minutes.",
    )
    return envelope(BusinessCode.SUCCESS, [{"message": "a verification code has been sent to your email"}])


@router.post("/forget-password/verify-otp", responses={
    **success_variants(
        ("verified", "Code correct — reset token issued", envelope(BusinessCode.SUCCESS, [
            {"reset_token": "eyJhbGciOiJIUzI1NiIs...", "expires_in": 900}])),
        ("invalid", "Wrong/expired code, or too many attempts", envelope(BusinessCode.OTP_INVALID, [
            {"message": "invalid or expired code"}])),
    ),
    **SERVER_ERROR,
})
def forget_password_verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise ApiError(BusinessCode.OTP_INVALID, "invalid or expired code")

    otp_service.verify_otp(db, user, OtpPurpose.FORGET_PASSWORD, payload.otp)
    # Verifying the code is what unlocks the reset-password step — same mechanism
    # forget-password used to hand back immediately, before OTP gated it.
    token, expires_in = create_reset_token(user)
    return envelope(BusinessCode.SUCCESS, [{"reset_token": token, "expires_in": expires_in}])


@router.post("/reset-password", responses={
    **success_variants(
        ("reset", "Password updated", envelope(BusinessCode.SUCCESS, [{"message": "password updated"}])),
        ("invalid_token", "Reset token is invalid, expired, or already used",
         envelope(BusinessCode.INVALID_RESET_TOKEN, [{"message": "reset token is invalid or expired"}])),
    ),
    **SERVER_ERROR,
})
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    # verify_reset_token() raises ApiError itself if the token is bad/expired/reused —
    # by the time it returns, `user` is confirmed genuine.
    user = verify_reset_token(payload.reset_token, db)
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return envelope(BusinessCode.SUCCESS, [{"message": "password updated"}])
