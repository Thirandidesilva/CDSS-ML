"""Request/response shapes for the dogs/ router."""
from __future__ import annotations

from typing import Optional

import uuid

from pydantic import BaseModel, ConfigDict

from ..enums import DogGender


class DogCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dog_name: str  # the only required field — everything else can be filled in later
    dog_breed: Optional[str] = None
    dog_age: Optional[int] = None
    dog_gender: Optional[DogGender] = None
    profile_picture: Optional[str] = None


class DogListRequest(BaseModel):
    # user_id is optional: omitted (or set to your own id) means "my dogs" — set to
    # someone else's id, it means "that user's dogs," which only an admin may ask for.
    model_config = ConfigDict(extra="forbid")

    user_id: Optional[uuid.UUID] = None


class DogIdRequest(BaseModel):
    # Every id-bearing dog endpoint takes the id in the body, never in the URL path —
    # this is the shape shared by dogs/get and dogs/delete.
    model_config = ConfigDict(extra="forbid")

    dog_id: uuid.UUID


class DogUpdateRequest(BaseModel):
    # dog_id is required (which dog); every other field is optional — the router only
    # changes fields the caller actually sent, same pattern as UserUpdateRequest.
    model_config = ConfigDict(extra="forbid")

    dog_id: uuid.UUID
    dog_name: Optional[str] = None
    dog_breed: Optional[str] = None
    dog_age: Optional[int] = None
    dog_gender: Optional[DogGender] = None
    profile_picture: Optional[str] = None


class DogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # can be built straight from a Dog ORM row

    dog_id: uuid.UUID
    user_id: uuid.UUID  # the owner
    dog_name: str
    dog_breed: Optional[str]
    dog_age: Optional[int]
    dog_gender: Optional[DogGender]
    profile_picture: Optional[str]
