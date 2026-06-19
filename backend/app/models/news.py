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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import text as sa_text
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
        CheckConstraint(
            "cover_focal_x IS NULL OR (cover_focal_x BETWEEN 0 AND 100)",
            name="ck_news_cover_focal_x_range",
        ),
        CheckConstraint(
            "cover_focal_y IS NULL OR (cover_focal_y BETWEEN 0 AND 100)",
            name="ck_news_cover_focal_y_range",
        ),
        CheckConstraint(
            "cover_focal_zoom IS NULL OR (cover_focal_zoom BETWEEN 100 AND 300)",
            name="ck_news_cover_focal_zoom_range",
        ),
        Index("idx_news_status_published_at", "status", "publish_at"),
        Index("idx_news_author", "author_id"),
        Index("idx_news_fts", "body_tsvector", postgresql_using="gin"),
        Index(
            "idx_news_active", "status", "publish_at", postgresql_where=text("deleted_at IS NULL")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
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
    categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default="{}"
    )

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
    cover_focal_x: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cover_focal_y: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cover_focal_zoom: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    cover_dominant_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    cover_variants: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    comment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    versions: Mapped[list[NewsVersion]] = relationship(
        "NewsVersion", back_populates="news", lazy="dynamic"
    )
    poll: Mapped[NewsPoll | None] = relationship(
        "NewsPoll", back_populates="news", uselist=False, cascade="all, delete-orphan"
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


class NewsPoll(Base):
    __tablename__ = "news_polls"
    __table_args__ = (
        CheckConstraint(
            "results_visibility IN ('always', 'after_vote', 'after_close', 'only_admin_editor')",
            name="ck_news_polls_results_visibility",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_revote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    results_visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="after_vote"
    )
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )

    news: Mapped[News] = relationship("News", back_populates="poll")
    questions: Mapped[list[NewsPollQuestion]] = relationship(
        "NewsPollQuestion",
        back_populates="poll",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="NewsPollQuestion.sort_order",
    )
    voters: Mapped[list[NewsPollVoter]] = relationship(
        "NewsPollVoter", back_populates="poll", cascade="all, delete-orphan"
    )


class NewsPollQuestion(Base):
    __tablename__ = "news_poll_questions"
    __table_args__ = (
        CheckConstraint(
            "max_choices IS NULL OR (is_multiple = true AND max_choices >= 1)",
            name="ck_news_poll_questions_max_choices",
        ),
        Index("idx_news_poll_questions_poll_sort", "poll_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    poll_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_polls.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_multiple: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_choices: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_custom_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )

    poll: Mapped[NewsPoll] = relationship("NewsPoll", back_populates="questions")
    options: Mapped[list[NewsPollOption]] = relationship(
        "NewsPollOption",
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="NewsPollOption.sort_order",
    )
    votes: Mapped[list[NewsPollVote]] = relationship(
        "NewsPollVote", back_populates="question", cascade="all, delete-orphan"
    )


class NewsPollOption(Base):
    __tablename__ = "news_poll_options"
    __table_args__ = (
        CheckConstraint(
            "text IS NOT NULL OR image_url IS NOT NULL",
            name="ck_news_poll_options_text_or_image",
        ),
        Index("idx_news_poll_options_question_sort", "question_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_poll_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    votes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )

    question: Mapped[NewsPollQuestion] = relationship("NewsPollQuestion", back_populates="options")
    votes: Mapped[list[NewsPollVote]] = relationship(
        "NewsPollVote", back_populates="option", cascade="all, delete-orphan"
    )


class NewsPollVoter(Base):
    __tablename__ = "news_poll_voters"
    __table_args__ = (
        UniqueConstraint("poll_id", "user_id", name="uq_news_poll_voters_poll_user"),
        Index("idx_news_poll_voters_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    poll_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_polls.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )

    poll: Mapped[NewsPoll] = relationship("NewsPoll", back_populates="voters")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id], lazy="select")
    votes: Mapped[list[NewsPollVote]] = relationship(
        "NewsPollVote", back_populates="voter", cascade="all, delete-orphan"
    )


class NewsPollVote(Base):
    __tablename__ = "news_poll_votes"
    __table_args__ = (
        CheckConstraint(
            "(option_id IS NOT NULL AND custom_text IS NULL)"
            " OR (option_id IS NULL AND custom_text IS NOT NULL)",
            name="ck_news_poll_votes_kind",
        ),
        Index("idx_news_poll_votes_question_option", "question_id", "option_id"),
        Index("idx_news_poll_votes_voter_question", "voter_id", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    poll_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_polls.id", ondelete="CASCADE"), nullable=False
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_poll_voters.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_poll_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_poll_options.id", ondelete="CASCADE"), nullable=True
    )
    custom_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )

    voter: Mapped[NewsPollVoter] = relationship("NewsPollVoter", back_populates="votes")
    question: Mapped[NewsPollQuestion] = relationship("NewsPollQuestion", back_populates="votes")
    option: Mapped[NewsPollOption | None] = relationship("NewsPollOption", back_populates="votes")


class NewsLike(Base):
    __tablename__ = "news_likes"
    __table_args__ = (
        UniqueConstraint("news_id", "user_id", name="uq_news_likes_news_user"),
        Index("idx_news_likes_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )


class NewsComment(Base):
    __tablename__ = "news_comments"
    __table_args__ = (
        Index("idx_news_comments_news", "news_id", "created_at"),
        Index(
            "idx_news_comments_active",
            "news_id",
            postgresql_where=sa_text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("NOW()")
    )
