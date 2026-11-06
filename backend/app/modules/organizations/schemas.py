"""Organization key store and guardrail shapes. A key is accepted once, on creation or rotation, and never returned."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, SecretStr


class OrgKeyCreate(BaseModel):
    provider: str
    api_key: SecretStr | None = None
    base_url: str | None = None
    label: str | None = Field(default=None, max_length=120)
    rpm_limit: int | None = Field(default=None, gt=0)
    tpm_limit: int | None = Field(default=None, gt=0)


class OrgKeyUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    rpm_limit: int | None = Field(default=None, gt=0)
    tpm_limit: int | None = Field(default=None, gt=0)


class OrgKeyRotate(BaseModel):
    api_key: SecretStr


class OrgKeyAttach(BaseModel):
    project_id: uuid.UUID


class OrgKeyFromCredential(BaseModel):
    """Move a project's own key to the workspace store."""

    project_id: uuid.UUID
    credential_id: uuid.UUID


class KeyProjectOut(BaseModel):
    project_id: uuid.UUID
    project_name: str


class OrgKeyOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str | None
    key_last4: str | None
    base_url: str | None
    rpm_limit: int | None
    tpm_limit: int | None
    created_at: datetime
    rotated_at: datetime | None
    used_in: list[KeyProjectOut]


class GuardrailsUpdate(BaseModel):
    monthly_spend_limit: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)


class GuardrailsOut(BaseModel):
    monthly_spend_limit: Decimal | None
    spent_this_month: Decimal
    month_started_at: datetime
    percent_used: float | None
    limit_reached: bool
