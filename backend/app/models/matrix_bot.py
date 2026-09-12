"""SQLAlchemy-модель настроек Matrix-бота (singleton)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MatrixBotSettings(Base):
    """Singleton row (``id = 1``) holding the Matrix (Synapse) bot configuration
    for personal chat notifications.

    MXID-конвенция: Matrix ID пользователя портала выводится из его email —
    ``borzihin.vs@mage.ru`` → ``@borzihin.vs:{server_name}``. Поле в профиле
    не нужно (все аккаунты растут из одного Keycloak).

    ``access_token_enc`` — Fernet через ``app.core.secret_crypto`` (ключ из
    ``SECRET_KEY``); токен long-lived ``mct_...``, выдаётся на сервере
    ``mas-cli manage issue-compatibility-token`` (MAS-конфигурация Synapse —
    shared-secret/password-login недоступны). Plaintext никогда не
    возвращается API (write-only, как ``HelpdeskMaxBotSettings.bot_token_enc``).

    ``bot_user_id`` (``@portal-bot:matrix.mage.ru``) нужен для account data
    ``m.direct`` — стандартного хранилища «пользователь → DM-комнаты», где
    воркер кэширует созданные ботом персональные комнаты.

    По образцу :class:`app.models.helpdesk.HelpdeskMaxBotSettings` (миграция
    081): строка сеется миграцией 097 с ``enabled=False``.
    """

    __tablename__ = "matrix_bot_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("FALSE"), default=False
    )
    homeserver_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    server_name: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default=sql_text("'matrix.mage.ru'")
    )
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    bot_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_text("NOW()"),
        onupdate=lambda: datetime.now(UTC),
    )

    updated_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[updated_by_user_id], lazy="select"
    )
