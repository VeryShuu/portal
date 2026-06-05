"""SQLAlchemy models for the object directories feature (docs/wip/directories.md).

A universal "directory of objects with contacts" engine. A
:class:`ObjectDirectory` is a *type* (rendered as a tab in ``/staff`` — Fleet,
Warehouses, …) carrying its own field schema and communication channels as
JSONB. :class:`ObjectDirectoryEntry` is a concrete object (a ship, a
warehouse) and :class:`ObjectEntryContact` is a single role × channel × value
contact row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.files import FileFolder
    from app.models.user import User


class ObjectDirectory(Base):
    __tablename__ = "object_directories"
    __table_args__ = (Index("idx_object_directories_sort", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    label_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    label_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    field_schema: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    channels: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE"), default=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entries: Mapped[list[ObjectDirectoryEntry]] = relationship(
        "ObjectDirectoryEntry",
        back_populates="directory",
        cascade="all, delete-orphan",
        lazy="select",
    )


class ObjectDirectoryEntry(Base):
    __tablename__ = "object_directory_entries"
    __table_args__ = (
        Index("idx_ode_directory", "directory_id", "sort_order"),
        Index("idx_ode_active", "deleted_at"),
        Index("idx_ode_folder", "folder_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    directory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("object_directories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    directory: Mapped[ObjectDirectory] = relationship(
        "ObjectDirectory", back_populates="entries", lazy="select"
    )
    contacts: Mapped[list[ObjectEntryContact]] = relationship(
        "ObjectEntryContact",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="ObjectEntryContact.sort_order",
        lazy="selectin",
    )
    creator: Mapped[User | None] = relationship(
        "User", foreign_keys=[created_by], lazy="select"
    )
    folder: Mapped[FileFolder | None] = relationship(
        "FileFolder", foreign_keys=[folder_id], lazy="select"
    )

    @property
    def folder_name(self) -> str | None:
        """Name of the bound ``/files`` folder (eager-loaded), if any."""
        return self.folder.name if self.folder is not None else None


class ObjectEntryContact(Base):
    __tablename__ = "object_entry_contacts"
    __table_args__ = (Index("idx_oec_entry", "entry_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("object_directory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    entry: Mapped[ObjectDirectoryEntry] = relationship(
        "ObjectDirectoryEntry", back_populates="contacts", lazy="select"
    )
