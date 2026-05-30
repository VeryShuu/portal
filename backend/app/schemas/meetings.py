from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as _Date  # noqa: N812
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator, model_validator


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _validate_start_not_too_late_in_past(start: datetime) -> datetime:
    if _as_utc(start) < datetime.now(UTC) - timedelta(hours=1):
        raise ValueError("[START_TIME_IN_PAST] start_time cannot be more than 1 hour in the past")
    return start


RoomKind = Literal["physical", "virtual"]


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: RoomKind = "physical"
    email: EmailStr | None = None
    link: str | None = Field(default=None, max_length=2048)
    timezone: str = Field(default="Europe/Moscow", max_length=64)
    sort_order: int = 0

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: RoomKind | None = None
    email: EmailStr | None = None
    link: str | None = Field(default=None, max_length=2048)
    timezone: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v


class RoomOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    kind: RoomKind
    email: EmailStr | None
    link: str | None
    timezone: str
    is_active: bool
    sort_order: int


class InvitedUser(BaseModel):
    user_id: str
    full_name: str
    email: EmailStr


class RecurrenceRule(BaseModel):
    freq: Literal["DAILY", "WEEKDAYS", "WEEKLY", "BIWEEKLY", "MONTHLY"]
    until_date: _Date


class BookingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    start_time: datetime
    end_time: datetime
    room_ids: list[uuid.UUID] = Field(min_length=1)
    invited_users: list[InvitedUser] = Field(default_factory=list, max_length=100)
    recurrence: RecurrenceRule | None = None

    @field_validator("start_time")
    @classmethod
    def start_not_too_late_in_past(cls, v: datetime) -> datetime:
        return _validate_start_not_too_late_in_past(v)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("end_time must be after start_time")
        return v

    @field_validator("room_ids")
    @classmethod
    def no_duplicate_rooms(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(v) != len(set(v)):
            raise ValueError("room_ids must not contain duplicates")
        return v

    @model_validator(mode="after")
    def monthly_day_in_safe_range(self) -> BookingCreate:
        if (
            self.recurrence is not None
            and self.recurrence.freq == "MONTHLY"
            and self.start_time is not None
            and self.start_time.day > 28
        ):
            raise ValueError("Monthly recurrence requires start day in range 1-28")
        return self


class BookingUpdate(BaseModel):
    apply_to: Literal["this", "series"] = "this"
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    room_ids: list[uuid.UUID] | None = None
    invited_users: list[InvitedUser] | None = Field(default=None, max_length=100)
    recurrence: RecurrenceRule | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> BookingUpdate:
        if self.start_time is not None:
            _validate_start_not_too_late_in_past(self.start_time)
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        return self

    @field_validator("room_ids")
    @classmethod
    def no_duplicate_rooms(cls, v: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("room_ids must not contain duplicates")
        return v


class BookingDelete(BaseModel):
    apply_to: Literal["this", "series"] = "this"


class BookingOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    organizer_name: str = Field(max_length=255)
    creator_id: uuid.UUID | None
    description: str | None
    start_time: datetime
    end_time: datetime
    rooms: list[RoomOut]
    invited_users: list[InvitedUser]
    series_id: uuid.UUID | None
    recurrence_rule: str | None
    update_count: int
    created_at: datetime
    updated_at: datetime


class SeriesUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    invited_users: list[InvitedUser] | None = Field(default=None, max_length=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    room_ids: list[uuid.UUID] | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> SeriesUpdate:
        if self.start_time is not None:
            _validate_start_not_too_late_in_past(self.start_time)
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        return self

    @field_validator("room_ids")
    @classmethod
    def no_duplicate_rooms(cls, v: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if v is not None and len(v) != len(set(v)):
            raise ValueError("room_ids must not contain duplicates")
        return v


class SeriesCountOut(BaseModel):
    count: int


class BookingListParams(BaseModel):
    date: _Date | None = None
    start_date: _Date | None = None
    end_date: _Date | None = None
    room_id: uuid.UUID | None = None
    creator_id: uuid.UUID | None = None
    limit: int = Field(default=500, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ConflictDetail(BaseModel):
    room_name: str
    booking_title: str
    start: datetime
    end: datetime


class BookingConflictOut(BaseModel):
    code: str = "BOOKING_CONFLICT"
    conflicts: list[ConflictDetail]
