"""Модуль обучения (LMS): таблицы этапа 1 — учётки, курсы, тесты, прогресс

Revision ID: 101
Revises: 100
Create Date: 2026-08-26

Полный набор таблиц этапа 1 (ТЗ docs/wip/learning.md §7). Все объекты новые —
zero-downtime по построению (только CREATE TABLE/INDEX; существующие таблицы
не затрагиваются).

Особенности:
- участники/прогресс/попытки: двойной FK ``user_id`` XOR ``learning_account_id``
  с CHECK «ровно один заполнен»;
- уникальность участника в курсе — частичными уникальными индексами
  (обычный UNIQUE с двумя nullable-колонками пропускает дубли);
- индекс email_ci_active — аналог idx_users_email_ci_active (миграция 030/037);
- DDL вручную через op.execute (паттерн миграций 081–100).
"""

from alembic import op

revision: str = "101"
down_revision: str | None = "100"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_accounts (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email                VARCHAR(255) NOT NULL,
            full_name            VARCHAR(255) NOT NULL,
            department           VARCHAR(255),
            position             VARCHAR(255),
            password_hash        VARCHAR(255) NOT NULL,
            status               VARCHAR(16) NOT NULL DEFAULT 'active',
            must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
            failed_attempts      INTEGER NOT NULL DEFAULT 0,
            locked_until         TIMESTAMPTZ,
            last_login_at        TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at           TIMESTAMPTZ,
            CONSTRAINT ck_learning_accounts_status CHECK (status IN ('active', 'blocked'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_accounts_email_ci_active
            ON learning_accounts (lower(email))
            WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_password_resets (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id  UUID NOT NULL REFERENCES learning_accounts(id) ON DELETE CASCADE,
            token_hash  VARCHAR(64) NOT NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_resets_token_hash "
        "ON learning_password_resets (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_resets_account "
        "ON learning_password_resets (account_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_admins (
            user_id  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            added_by UUID REFERENCES users(id) ON DELETE SET NULL,
            added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_courses (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug         VARCHAR(140) NOT NULL,
            title        VARCHAR(255) NOT NULL,
            description  TEXT,
            cover_path   VARCHAR(512),
            status       VARCHAR(16) NOT NULL DEFAULT 'draft',
            created_by   UUID REFERENCES users(id) ON DELETE SET NULL,
            published_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at   TIMESTAMPTZ,
            CONSTRAINT ck_learning_courses_status CHECK (status IN ('draft', 'published'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_courses_slug ON learning_courses (slug)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_course_items (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id   UUID NOT NULL REFERENCES learning_courses(id) ON DELETE CASCADE,
            type        VARCHAR(16) NOT NULL,
            title       VARCHAR(255) NOT NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            file_path   VARCHAR(512),
            url         VARCHAR(2048),
            test_config_used BOOLEAN,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at  TIMESTAMPTZ,
            CONSTRAINT ck_learning_items_type CHECK (type IN ('material', 'test'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_items_course "
        "ON learning_course_items (course_id, sort_order)"
    )

    # ── участники ────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_course_participants (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            course_id           UUID NOT NULL REFERENCES learning_courses(id) ON DELETE CASCADE,
            user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
            learning_account_id UUID REFERENCES learning_accounts(id) ON DELETE CASCADE,
            enrolled_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            enrolled_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at          TIMESTAMPTZ,
            CONSTRAINT ck_learning_course_participants_participant_xor
                CHECK (((user_id IS NOT NULL)::int
                        + (learning_account_id IS NOT NULL)::int) = 1)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_participants_user
            ON learning_course_participants (course_id, user_id)
            WHERE deleted_at IS NULL AND user_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_participants_account
            ON learning_course_participants (course_id, learning_account_id)
            WHERE deleted_at IS NULL AND learning_account_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_participants_user "
        "ON learning_course_participants (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_participants_account "
        "ON learning_course_participants (learning_account_id)"
    )

    # ── тесты и вопросы ──────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_tests (
            item_id           UUID PRIMARY KEY
                REFERENCES learning_course_items(id) ON DELETE CASCADE,
            pass_score        INTEGER NOT NULL DEFAULT 70,
            max_attempts      INTEGER NOT NULL DEFAULT 3,
            shuffle_answers   BOOLEAN NOT NULL DEFAULT FALSE,
            shuffle_questions BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_questions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            test_item_id UUID NOT NULL REFERENCES learning_tests(item_id) ON DELETE CASCADE,
            text         TEXT NOT NULL,
            multi        BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order   INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_questions_test "
        "ON learning_questions (test_item_id, sort_order)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_question_options (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id UUID NOT NULL REFERENCES learning_questions(id) ON DELETE CASCADE,
            text        TEXT NOT NULL,
            is_correct  BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_options_question "
        "ON learning_question_options (question_id, sort_order)"
    )

    # ── прогресс и попытки ───────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_item_progress (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id             UUID NOT NULL
                REFERENCES learning_course_items(id) ON DELETE CASCADE,
            user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
            learning_account_id UUID REFERENCES learning_accounts(id) ON DELETE CASCADE,
            completed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_learning_item_progress_participant_xor
                CHECK (((user_id IS NOT NULL)::int
                        + (learning_account_id IS NOT NULL)::int) = 1)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_progress_user
            ON learning_item_progress (item_id, user_id)
            WHERE user_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_progress_account
            ON learning_item_progress (item_id, learning_account_id)
            WHERE learning_account_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_progress_user ON learning_item_progress (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_progress_account "
        "ON learning_item_progress (learning_account_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_test_attempts (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            test_item_id        UUID NOT NULL
                REFERENCES learning_tests(item_id) ON DELETE CASCADE,
            user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
            learning_account_id UUID REFERENCES learning_accounts(id) ON DELETE CASCADE,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            submitted_at        TIMESTAMPTZ,
            abandoned_at        TIMESTAMPTZ,
            score               INTEGER,
            passed              BOOLEAN,
            answers             JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT ck_learning_test_attempts_participant_xor
                CHECK (((user_id IS NOT NULL)::int
                        + (learning_account_id IS NOT NULL)::int) = 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_attempts_test_submitted "
        "ON learning_test_attempts (test_item_id, submitted_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_attempts_user ON learning_test_attempts (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_attempts_account "
        "ON learning_test_attempts (learning_account_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS learning_test_attempts")
    op.execute("DROP TABLE IF EXISTS learning_item_progress")
    op.execute("DROP TABLE IF EXISTS learning_question_options")
    op.execute("DROP TABLE IF EXISTS learning_questions")
    op.execute("DROP TABLE IF EXISTS learning_tests")
    op.execute("DROP TABLE IF EXISTS learning_course_participants")
    op.execute("DROP TABLE IF EXISTS learning_course_items")
    op.execute("DROP TABLE IF EXISTS learning_courses")
    op.execute("DROP TABLE IF EXISTS learning_admins")
    op.execute("DROP TABLE IF EXISTS learning_password_resets")
    op.execute("DROP TABLE IF EXISTS learning_accounts")
