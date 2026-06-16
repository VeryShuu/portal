"""Pydantic schemas for the news mailing recipients directory."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Pragmatic email check: EmailStr is intentionally avoided because it performs
# DNS-style validation that rejects internal ``.local`` corporate domains
# (see AGENTS.md). We only require a single ``@`` with non-empty local/domain
# parts and no whitespace.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


def _validate_email(value: str) -> str:
    cleaned = value.strip()
    if not _EMAIL_RE.match(cleaned):
        raise ValueError("Invalid email address")
    return cleaned


class MailingRecipientPublic(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    label: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MailingRecipientList(BaseModel):
    items: list[MailingRecipientPublic]
    total: int
    limit: int
    offset: int


class CreateMailingRecipientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=320)
    label: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _validate_email(v)


class UpdateMailingRecipientRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=1, max_length=320)
    label: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return None if v is None else _validate_email(v)
