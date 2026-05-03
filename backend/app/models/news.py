from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.users import User


class News(Base):
    __tablename__ = "news"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_news_status",
        ),
        Index("idx_news_status_published_at", "status", "publish_at"),
        Index("idx_news_author", "author_id"),
        Index("idx_news_fts", "body_tsvector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # P0-9: matches the GENERATED tsvector column produced by migration 002
    # (renamed from body_tsv -> body_tsvector in migration 007).
    body_tsvector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('russian_hunspell', coalesce(title, '') || ' ' || coalesce(body, ''))",
            persisted=True,
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list, server_default="{}")

    target_departments: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    target_roles: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author: Mapped[User] = relationship("User", foreign_keys=[author_id], lazy="select")

    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_focal_point: Mapped[str | None] = mapped_column(String(16), nullable=True)

    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    versions: Mapped[list[NewsVersion]] = relationship(
        "NewsVersion", back_populates="news", lazy="dynamic"
    )


class NewsVersion(Base):
    __tablename__ = "news_versions"
    __table_args__ = (Index("idx_news_versions_news_id", "news_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    editor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    news: Mapped[News] = relationship("News", back_populates="versions")


class NewsGalleryImage(Base):
    __tablename__ = "news_gallery_images"
    __table_args__ = (Index("idx_gallery_news_id_sort", "news_id", "sort_order"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class NewsAttachment(Base):
    __tablename__ = "news_attachments"
    __table_args__ = (Index("idx_attachments_news_id", "news_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
