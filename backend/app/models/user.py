import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('reader', 'editor', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "presence_status IN ('office', 'remote', 'vacation')",
            name="ck_users_presence_status",
        ),
        CheckConstraint("lang IN ('ru', 'en')", name="ck_users_lang"),
        CheckConstraint(
            "auth_source IN ('keycloak', 'local')",
            name="ck_users_auth_source",
        ),
        UniqueConstraint("keycloak_id", name="uq_users_keycloak_id"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    keycloak_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    auth_source: Mapped[str] = mapped_column(String(20), nullable=False, default="keycloak")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="reader")
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    presence_status: Mapped[str] = mapped_column(String(20), nullable=False, default="office")
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_inapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="ru")
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    keycloak_groups: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
