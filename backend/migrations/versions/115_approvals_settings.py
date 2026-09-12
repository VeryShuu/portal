"""approvals module — settings singleton (ERP document approvals)

Revision ID: 115
Revises: 114
Create Date: 2026-09-04

Модуль «Согласование документов» (docs/wip/erp-approvals.md): перенос
PHP-приложения order.* в портал. Backend — прокси к HTTP-сервисам 1С
(``erp.mage.ru/MageErp/hs/Auth/...``) под служебной учёткой Portal:
``GETTokenByLogin?Login=<email>`` (вариант 2, ответ 1С-разработчика
2026-09-04) → обычный токен → ``DocumentsForApproval`` / ``GETAgreed`` /
``GETNotAgreed`` / ``GETDocumentAttachments``.

Единственная новая сущность — ``approvals_settings`` (singleton ``id=1``,
клон ``directum_settings``): базовый URL публикации, учётка и Fernet-шифр
пароля (write-only в API). Документы/токены в БД портала не хранятся —
источник истины 1С (чистый прокси, MVP).

Изменения additive (zero-downtime): CREATE TABLE + seeded singleton.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "115"
down_revision: str | None = "114"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # Singleton настроек (id=1, сеется сразу — GET /approvals/settings всегда отвечает).
    # nosec B608 — статический DDL без интерполяции.
    op.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS approvals_settings (
                id                SMALLINT PRIMARY KEY,
                base_url          VARCHAR(255) NOT NULL
                    DEFAULT 'https://erp.mage.ru/MageErp/hs/Auth',
                auth_username     VARCHAR(255) NOT NULL DEFAULT 'Portal',
                auth_password_enc TEXT,
                updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_approvals_settings_singleton CHECK (id = 1)
            )
            """
        )
    )
    op.execute(text("INSERT INTO approvals_settings (id) VALUES (1) ON CONFLICT DO NOTHING"))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS approvals_settings"))
