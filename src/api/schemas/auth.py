"""Request shapes for the auth/ router — register, login, and the forgot/reset flow."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr  # pydantic validates the format; routers/auth.py checks it's unique
    phone_number: Optional[str] = None
    password: str  # plaintext in the request only — hashed immediately in routers/auth.py


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_name_or_email: str  # accepts either, see routers/auth.py's login query
    password: str


class ForgetUsernameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ForgetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class VerifyOtpRequest(BaseModel):
    # Shared by both /forget-username/verify-otp and /forget-password/verify-otp — the
    # purpose is implicit in which endpoint is called, not a field here.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")  # malformed input is a 422, before it reaches verify_otp()


class ResetPasswordRequest(BaseModel):
    # Completes the forgot-password flow: reset_token comes from the response of
    # POST /auth/forget-password (see auth.py's create_reset_token()).
    model_config = ConfigDict(extra="forbid")

    reset_token: str
    new_password: str
