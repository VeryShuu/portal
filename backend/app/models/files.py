"""SQLAlchemy models for the Nextcloud file module (ADR-032).

file_folders            — portal-managed shadow tree of NC folders with ACL.
file_folder_permissions — per-folder permissions (viewer/editor/manager).
file_items              — per-file upload tracking (migration 038).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FileFolder(Base):
    __tablename__ = "file_folders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_folders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    nc_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        unique=True,
        comment="Path relative to portal-svc WebDAV root (e.g. PortalFiles/HR/Docs)",
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    inherit_permissions: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default=text("true")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    permissions: Mapped[list[FileFolderPermission]] = relationship(
        "FileFolderPermission",
        back_populates="folder",
        cascade="all, delete-orphan",
        lazy="select",
    )


class FileFolderPermission(Base):
    __tablename__ = "file_folder_permissions"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('user', 'group')",
            name="ck_file_folder_perm_subject_type",
        ),
        CheckConstraint(
            "permission IN ('viewer', 'editor', 'manager')",
            name="ck_file_folder_perm_permission",
        ),
        UniqueConstraint("folder_id", "subject_id", name="uq_file_folder_perm_folder_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_folders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_type: Mapped[str] = mapped_column(String(10), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    folder: Mapped[FileFolder] = relationship("FileFolder", back_populates="permissions")


class FileShare(Base):
    """Per-file share (ADR-032 / sharing.md).

    Addresses a single file by (folder_id, filename); nc_path is stored
    denormalized for persistence and the admin registry. Only viewer/editor
    levels are granted on a file (manager is never issued).
    """

    __tablename__ = "file_shares"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('user', 'group')",
            name="ck_file_share_subject_type",
        ),
        CheckConstraint(
            "permission IN ('viewer', 'editor')",
            name="ck_file_share_permission",
        ),
        UniqueConstraint(
            "folder_id", "filename", "subject_id", name="uq_file_share_folder_file_subject"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_folders.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    nc_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        comment="Denormalized folder.nc_path + '/' + filename",
    )
    subject_type: Mapped[str] = mapped_column(String(10), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False)
    shared_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileItem(Base):
    """Tracks files uploaded through the portal (migration 038).

    One record per file. Soft-deleted when the file is removed via portal.
    Files uploaded directly to Nextcloud (bypassing portal) won't have a record.
    """

    __tablename__ = "file_items"
    __table_args__ = (
        Index(
            "uq_file_items_folder_name_active",
            "folder_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_folders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nc_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        comment="Full nc_path: folder.nc_path + '/' + filename",
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
