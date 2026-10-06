"""Password hashing (bcrypt directly — passlib 1.7.4 is incompatible with bcrypt>=4.1),
JWT session tokens, and the FastAPI dependencies that gate every authenticated route.
"""
from __future__ import annotations

from typing import Optional

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .codes import BusinessCode
from .config import get_settings
from .db import get_db
from .enums import AccountStatus, UserRole
from .errors import ApiError
from .models import RefreshToken, User

# Marks a JWT as a password-reset token so it can never be reused as a login/session token.
RESET_TOKEN_PURPOSE = "password_reset"


def hash_password(password: str) -> str:
    # bcrypt.gensalt() makes a fresh random salt each call, so hashing the same
    # password twice gives two different hashes — that's expected, not a bug.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    # bcrypt reads the salt back out of password_hash itself, so no salt is passed here.
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user: User) -> tuple[str, int]:
    # This is the token returned by /auth/login — sent as "Authorization: Bearer <token>"
    # on every request afterwards.
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60  # minutes -> seconds
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.user_id),   # "subject" — whose token this is
        "role": user.role.value,    # owner/admin, read by require_role() without a DB hit
        "iat": now,                 # issued-at
        "exp": now + timedelta(seconds=expires_in),  # jwt.decode() rejects it after this
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


# A refresh token that was already traded in is normally a sign it was copied. But a phone
# on a bad connection can send the refresh, lose the answer, and send it again, so a
# second use within this window gets a fresh token instead of ending the session.
REFRESH_REUSE_GRACE = timedelta(seconds=30)


def _hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    # SQLite hands datetimes back without a zone; Postgres keeps it. Both mean UTC here.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def issue_refresh_token(user: User, db: Session, family_id: Optional[uuid.UUID] = None) -> tuple[str, int]:
    """Creates a refresh token for [user] and returns (raw token, seconds it lasts). Only
    the hash is stored. The caller commits. A new sign-in starts a new family; a refresh
    continues the family of the token it replaces."""
    settings = get_settings()
    expires_in = settings.refresh_token_expire_days * 24 * 60 * 60
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user.user_id,
        family_id=family_id or uuid.uuid4(),
        token_hash=_hash_refresh_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    ))
    return raw, expires_in


def rotate_refresh_token(raw: str, db: Session) -> tuple[User, str, int]:
    """Trades a refresh token for a new one: returns (user, new raw token, seconds it
    lasts). Commits. Raises INVALID_REFRESH_TOKEN for an unknown, expired or revoked
    token, a deleted account, or a token traded in long ago (which also revokes the
    whole family, since someone is replaying a copy)."""
    invalid = ApiError(BusinessCode.INVALID_REFRESH_TOKEN, "refresh token is invalid or expired")
    now = datetime.now(timezone.utc)

    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh_token(raw)))
    if row is None or row.revoked_at is not None or _utc(row.expires_at) <= now:
        raise invalid

    user = db.get(User, row.user_id)
    if user is None or user.status != AccountStatus.ACTIVE:
        raise invalid

    if row.used_at is not None:
        if now - _utc(row.used_at) > REFRESH_REUSE_GRACE:
            _revoke_family(row.family_id, db)
            db.commit()  # the revocation must survive the error below
            raise invalid
    else:
        row.used_at = now

    new_raw, expires_in = issue_refresh_token(user, db, row.family_id)
    db.commit()
    return user, new_raw, expires_in


def _revoke_family(family_id: uuid.UUID, db: Session) -> None:
    now = datetime.now(timezone.utc)
    for token in db.scalars(select(RefreshToken).where(
        RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
    )):
        token.revoked_at = now


def revoke_refresh_token_family(raw: str, db: Session) -> None:
    """Sign-out: ends the session [raw] belongs to. Unknown tokens are ignored."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh_token(raw)))
    if row is not None:
        _revoke_family(row.family_id, db)
        db.commit()


def revoke_all_refresh_tokens(user_id: uuid.UUID, db: Session) -> None:
    """Account deletion: every session of the user ends. The caller commits."""
    now = datetime.now(timezone.utc)
    for token in db.scalars(select(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )):
        token.revoked_at = now


def create_reset_token(user: User) -> tuple[str, int]:
    # Separate from the access token above: short-lived, single-purpose, and never
    # accepted by get_current_user() because it carries "purpose" instead of a role.
    settings = get_settings()
    expires_in = settings.reset_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.user_id),
        "purpose": RESET_TOKEN_PURPOSE,
        # A fingerprint of the CURRENT password hash. Once the password actually
        # changes, this fingerprint no longer matches — see verify_reset_token() below —
        # so the token can't be replayed. No database table of "used tokens" needed.
        "pwd_fp": hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()[:16],
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def verify_reset_token(token: str, db: Session) -> User:
    """Naturally single-use: a successful reset changes password_hash, invalidating pwd_fp."""
    settings = get_settings()
    try:
        # Checks the signature and the expiry ("exp") in one call; raises if either is bad.
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise ApiError(BusinessCode.INVALID_RESET_TOKEN, "reset token is invalid or expired")

    # Refuse a normal login/access token here even if it's otherwise well-formed.
    if payload.get("purpose") != RESET_TOKEN_PURPOSE:
        raise ApiError(BusinessCode.INVALID_RESET_TOKEN, "reset token is invalid or expired")

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise ApiError(BusinessCode.INVALID_RESET_TOKEN, "reset token is invalid or expired")

    # Recompute the fingerprint from the user's CURRENT hash and compare to the one baked
    # into the token. If the password was already reset since this token was issued, the
    # hashes (and therefore the fingerprints) won't match — that's the single-use check.
    expected_fp = hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()[:16]
    if payload.get("pwd_fp") != expected_fp:
        raise ApiError(BusinessCode.INVALID_RESET_TOKEN, "reset token is invalid or expired")

    return user


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    # FastAPI dependency: add `user: User = Depends(get_current_user)` to any route
    # parameter list and it runs automatically before that route's own code.
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(BusinessCode.MISSING_OR_INVALID_TOKEN, "missing bearer token")

    token = authorization.removeprefix("Bearer ")  # strip the "Bearer " prefix, keep the JWT
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise ApiError(BusinessCode.MISSING_OR_INVALID_TOKEN, "invalid or expired token")

    user = db.get(User, uuid.UUID(payload["sub"]))
    # Covers two cases at once: the account was deleted after the token was issued, or
    # the token's user_id doesn't exist at all (shouldn't happen, but fail closed).
    if user is None or user.status != AccountStatus.ACTIVE:
        raise ApiError(BusinessCode.MISSING_OR_INVALID_TOKEN, "invalid or expired token")

    return user


def require_role(role: UserRole):
    # A dependency FACTORY: require_role(UserRole.ADMIN) builds and returns a dependency
    # function, so routes write `Depends(require_role(UserRole.ADMIN))` to gate on role.
    def _dependency(user: User = Depends(get_current_user)) -> User:
        # get_current_user() already ran above, so we know the token is valid — this
        # only adds the extra "and are they the right role" check on top.
        if user.role != role:
            raise ApiError(BusinessCode.OWNERSHIP_VIOLATION, f"requires {role.value} role")
        return user

    return _dependency
