"""
Auth request / response models and enums.

The public shapes of the auth module. Access tokens are returned in the body (the
frontend keeps them in memory); refresh tokens never appear in any schema because they
travel only in the httpOnly cookie set by the router.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class MembershipRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(repr=False)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(repr=False)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    is_personal: bool
    role: MembershipRole


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class AuthConfigOut(BaseModel):
    signup_open: bool
    password_min_length: int


class MeOut(BaseModel):
    user: UserOut
    organizations: list[OrganizationOut]


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int | None = Field(default=90, ge=1, le=365)

    @field_validator("name")
    @classmethod
    def _trimmed(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Give the token a name.")
        return name


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreated(ApiTokenOut):
    """The only time the token itself is returned."""

    token: str = Field(repr=False)
