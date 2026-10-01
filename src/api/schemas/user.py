"""Request/response shapes for the users/ router."""
from __future__ import annotations

from typing import Optional

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from ..enums import UserRole


class UserOut(BaseModel):
    # from_attributes=True lets this be built straight from a User ORM row
    # (UserOut.model_validate(user)) instead of unpacking fields by hand.
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    user_name: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: EmailStr
    phone_number: Optional[str]
    role: UserRole
    profile_picture: Optional[str]
    # Deliberately no password_hash field — this model IS the response shape, so a
    # field that doesn't exist here can never accidentally leak into an API response.


class UserUpdateRequest(BaseModel):
    # extra="forbid" rejects any field not listed below with a 422, instead of silently
    # ignoring typos/unexpected keys in the request body.
    model_config = ConfigDict(extra="forbid")

    # Every field is optional and defaults to None — the router only updates the ones
    # the caller actually sent (see routers/users.py's "if value is not None" checks).
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    profile_picture: Optional[str] = None
    email: Optional[EmailStr] = None
    # Both must be present together to change the password — see routers/users.py,
    # which checks current_password before accepting new_password.
    current_password: Optional[str] = None
    new_password: Optional[str] = None
