"""SQLAlchemy-модели модуля «Согласование документов» (docs/wip/erp-approvals.md).

ERP (1С, ``erp.mage.ru/MageErp/hs/Auth/...``) — источник истины: документы,
этапы согласования и вложения через портал **не хранятся** (чистый прокси,
MVP). Единственная сущность — singleton настроек подключения (клон
``directum_settings``): базовый URL публикации, служебная учётка Portal и
Fernet-шифр пароля (write-only в API).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ApprovalsSettings(Base):
    """Singleton row (``id = 1``) с настройками подключения к ERP.

    Пароль служебной учётки — шифр Fernet (``auth_password_enc``, как
    ``directum_settings.auth_password_enc``); plaintext write-only — API
    возвращает ``password_set: bool``. Базовый URL — публикация HTTP-сервисов
    **без хвостового слеша** (клиент добавляет ``/<Метод>?...``).

    Гейтинг: ``modules.approvals.enabled`` (``modules.json``) —
    мастер-переключатель фичи; «configured» = base_url + учётка + пароль.
    """

    __tablename__ = "approvals_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_approvals_settings_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    base_url: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'https://erp.mage.ru/MageErp/hs/Auth'"),
        default="https://erp.mage.ru/MageErp/hs/Auth",
    )
    # Служебная учётка публикации 1С (Basic); 1С-сторона пускает под ней
    # только выдачу токенов (GETTokenByLogin), остальное — по токену.
    auth_username: Mapped[str] = mapped_column(String(255), nullable=False, default="Portal")
    auth_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Отдельный RootURL выдачи токенов (миграция 116): 1С публикует
    # GETTokenByLogin под …/hs/PortalAuth, документы — под …/hs/Auth.
    # NULL/пусто = использовать base_url (обратная совместимость).
    token_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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

    updated_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[updated_by_user_id], lazy="select"
    )
