"""One-time codes for the forget-password flow: generation, and verification with
attempt-limiting. DB-backed (see models.OtpCode) rather than a stateless JWT like the
password-reset token, because a 6-digit code needs the server to actually count
verification attempts across separate requests.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..codes import BusinessCode
from ..config import get_settings
from ..enums import OtpPurpose
from ..errors import ApiError
from ..models import OtpCode, User


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _pending_otp(db: Session, user: User, purpose: OtpPurpose):
    return db.scalar(
        select(OtpCode)
        .where(OtpCode.user_id == user.user_id, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None))
        .order_by(OtpCode.created_at.desc())
    )


def create_otp(db: Session, user: User, purpose: OtpPurpose) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # Requesting a new code invalidates any still-pending one for the same user+purpose
    # — a "resend" doesn't leave two codes valid at once, and needs no separate cooldown.
    previous = _pending_otp(db, user, purpose)
    if previous is not None:
        previous.consumed_at = now

    code = f"{secrets.randbelow(1_000_000):06d}"  # secrets, not random — this is a credential
    db.add(OtpCode(
        user_id=user.user_id,
        purpose=purpose,
        code_hash=_hash(code),
        expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
    ))
    db.commit()
    return code


def verify_otp(db: Session, user: User, purpose: OtpPurpose, code: str) -> None:
    """Raises ApiError(OTP_INVALID) on any failure — wrong code, expired, no pending
    code, or attempts already exhausted are never distinguished in the response."""
    settings = get_settings()
    otp = _pending_otp(db, user, purpose)

    if otp is None or datetime.now(timezone.utc) > otp.expires_at.replace(tzinfo=timezone.utc):
        raise ApiError(BusinessCode.OTP_INVALID, "invalid or expired code")

    if otp.attempts >= settings.otp_max_attempts:
        # Maxed out stays dead even if the right code is supplied later — the user has
        # to request a fresh one, not keep guessing against the same code indefinitely.
        raise ApiError(BusinessCode.OTP_INVALID, "invalid or expired code")

    if _hash(code) != otp.code_hash:
        otp.attempts += 1
        db.commit()
        raise ApiError(BusinessCode.OTP_INVALID, "invalid or expired code")

    otp.consumed_at = datetime.now(timezone.utc)
    db.commit()
