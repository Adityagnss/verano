"""
Auth request / response models and enums.

The public shapes of the auth module. Access tokens are returned in the body (the
frontend keeps them in memory); refresh tokens never appear in any schema because they
travel only in the httpOnly cookie set by the router. Roles and token scopes are defined once in
`app.core.permissions` and re-exported here.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.permissions import Role as MembershipRole
from app.core.permissions import TokenScope

__all__ = ["MembershipRole", "TokenScope"]


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(repr=False)
    name: str = Field(min_length=1, max_length=120)
    invite_token: str | None = Field(default=None, repr=False)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(repr=False)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime
    email_verified: bool = False


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


class SignInProviderOut(BaseModel):
    name: str
    display_name: str
    kind: str


class AuthConfigOut(BaseModel):
    signup_open: bool
    password_min_length: int
    email_verification_required: bool = False
    sign_in_providers: list[SignInProviderOut] = []


class MeOut(BaseModel):
    user: UserOut
    organizations: list[OrganizationOut]


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int | None = Field(default=90, ge=1, le=365)
    scope: TokenScope = TokenScope.WRITE

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
    scope: TokenScope = TokenScope.WRITE
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreated(ApiTokenOut):
    """The only time the token itself is returned."""

    token: str = Field(repr=False)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: MembershipRole
    joined_at: datetime
    email_verified: bool


class RoleChange(BaseModel):
    role: MembershipRole


class InviteCreate(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.MEMBER


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: MembershipRole
    created_at: datetime
    expires_at: datetime
    status: str  # open, accepted, expired or revoked
    emailed: bool
    invited_by_name: str | None = None


class InviteIssued(InviteOut):
    """Returned when an invite is created or issued again: the link is shown here so the owner can pass it on
    when email is not set up (or did not arrive). It is never shown again."""

    link: str = Field(repr=False)


class InvitePreview(BaseModel):
    """What a person sees on opening an invite link, before signing in."""

    organization_name: str
    email: str
    role: MembershipRole
    expires_at: datetime
    status: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(repr=False)


class OidcStart(BaseModel):
    authorization_url: str
