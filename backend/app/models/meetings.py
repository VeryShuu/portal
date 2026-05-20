from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MeetingRoom(Base):
    __tablename__ = "meeting_rooms"
    __table_args__ = (
        UniqueConstraint("name", name="uq_meeting_rooms_name"),
        Index("idx_meeting_rooms_active", "is_active"),
        Index("idx_meeting_rooms_sort", "sort_order", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    link: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="Europe/Moscow"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )

    bookings: Mapped[list[MeetingBookingRoom]] = relationship(
        "MeetingBookingRoom", back_populates="room", lazy="select"
    )


class MeetingBooking(Base):
    __tablename__ = "meeting_bookings"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_meeting_bookings_time_order"),
        Index("idx_meeting_bookings_time", "start_time", "end_time"),
        Index("idx_meeting_bookings_series", "series_id"),
        Index("idx_meeting_bookings_creator", "creator_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    organizer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_users: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )

    creator: Mapped[User | None] = relationship(
        "User", foreign_keys=[creator_id], lazy="select"
    )
    rooms: Mapped[list[MeetingBookingRoom]] = relationship(
        "MeetingBookingRoom", back_populates="booking", lazy="select", cascade="all, delete-orphan"
    )


class MeetingBookingRoom(Base):
    __tablename__ = "meeting_booking_rooms"
    __table_args__ = (
        PrimaryKeyConstraint("booking_id", "room_id"),
        Index("idx_meeting_booking_rooms_room", "room_id"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meeting_bookings.id", ondelete="CASCADE"), nullable=False
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meeting_rooms.id", ondelete="RESTRICT"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    booking: Mapped[MeetingBooking] = relationship(
        "MeetingBooking", back_populates="rooms", lazy="select"
    )
    room: Mapped[MeetingRoom] = relationship(
        "MeetingRoom", back_populates="bookings", lazy="select"
    )

