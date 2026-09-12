"""add users.avatar_focal_x/y/zoom (позиционирование аватара как у news-cover)

Revision ID: 096
Revises: 095
Create Date: 2026-08-15

Фокальная точка + зум аватара пользователя — тот же паттерн, что у обложек
новостей (миграция ~074, ``news.cover_focal_*``): пользователь после загрузки
перетаскивает точку фокуса и приближает картинку, порталу достаточно хранить
три числа, отрисовка — CSS (``object-position`` + ``scale``), файл не режется.

Колонки nullable: NULL = дефолт (центр 50/50, зум 100%). CHECK-ограничения
зеркалят ``ck_news_cover_focal_*`` — x/y ∈ [0, 100], zoom ∈ [100, 300].
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "096"
down_revision: str | None = "095"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_focal_x SMALLINT"))
    op.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_focal_y SMALLINT"))
    op.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_focal_zoom SMALLINT"))
    op.execute(
        text(
            "ALTER TABLE users ADD CONSTRAINT ck_users_avatar_focal_x_range "
            "CHECK (avatar_focal_x IS NULL OR (avatar_focal_x BETWEEN 0 AND 100))"
        )
    )
    op.execute(
        text(
            "ALTER TABLE users ADD CONSTRAINT ck_users_avatar_focal_y_range "
            "CHECK (avatar_focal_y IS NULL OR (avatar_focal_y BETWEEN 0 AND 100))"
        )
    )
    op.execute(
        text(
            "ALTER TABLE users ADD CONSTRAINT ck_users_avatar_focal_zoom_range "
            "CHECK (avatar_focal_zoom IS NULL OR (avatar_focal_zoom BETWEEN 100 AND 300))"
        )
    )


def downgrade() -> None:
    op.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_avatar_focal_zoom_range"))
    op.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_avatar_focal_y_range"))
    op.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_avatar_focal_x_range"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS avatar_focal_zoom"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS avatar_focal_y"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS avatar_focal_x"))
