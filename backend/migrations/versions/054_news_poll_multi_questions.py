"""News polls: multi-question + custom answer refactor

Revision ID: 054
Revises: 053
Create Date: 2026-05-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "054"
down_revision: str | None = "053"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Create news_poll_questions
    op.create_table(
        "news_poll_questions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "poll_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_polls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_multiple", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("max_choices", sa.Integer(), nullable=True),
        sa.Column(
            "allow_custom_answer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "max_choices IS NULL OR (is_multiple = true AND max_choices >= 1)",
            name="ck_news_poll_questions_max_choices",
        ),
    )
    op.create_index(
        "idx_news_poll_questions_poll_sort",
        "news_poll_questions",
        ["poll_id", "sort_order"],
    )

    # 2. Backfill: one question per existing poll
    op.execute(
        sa.text(
            """
            INSERT INTO news_poll_questions (
                id, poll_id, text, sort_order, is_required, is_multiple,
                max_choices, allow_custom_answer, created_at
            )
            SELECT
                gen_random_uuid(),
                p.id,
                p.question,
                0,
                true,
                p.is_multiple,
                p.max_choices,
                false,
                p.created_at
            FROM news_polls p
            """
        )
    )

    # 3. Add question_id to options, backfill, then drop poll_id
    op.add_column(
        "news_poll_options",
        sa.Column("question_id", UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE news_poll_options o
            SET question_id = q.id
            FROM news_poll_questions q
            WHERE q.poll_id = o.poll_id
            """
        )
    )
    op.alter_column("news_poll_options", "question_id", nullable=False)
    op.create_foreign_key(
        "fk_news_poll_options_question_id",
        "news_poll_options",
        "news_poll_questions",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("idx_poll_options_poll_id_sort", table_name="news_poll_options")
    op.drop_constraint(
        "news_poll_options_poll_id_fkey", "news_poll_options", type_="foreignkey"
    )
    op.drop_column("news_poll_options", "poll_id")
    op.create_index(
        "idx_news_poll_options_question_sort",
        "news_poll_options",
        ["question_id", "sort_order"],
    )

    # 4. news_poll_votes: add question_id, custom_text; relax option_id
    op.add_column(
        "news_poll_votes",
        sa.Column("question_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "news_poll_votes",
        sa.Column("custom_text", sa.String(length=500), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE news_poll_votes v
            SET question_id = o.question_id
            FROM news_poll_options o
            WHERE v.option_id = o.id
            """
        )
    )
    op.alter_column("news_poll_votes", "question_id", nullable=False)
    op.create_foreign_key(
        "fk_news_poll_votes_question_id",
        "news_poll_votes",
        "news_poll_questions",
        ["question_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "uq_news_poll_votes_option_voter", "news_poll_votes", type_="unique"
    )
    op.drop_index("idx_news_poll_votes_poll_id_option_id", table_name="news_poll_votes")
    op.alter_column("news_poll_votes", "option_id", nullable=True)

    op.create_check_constraint(
        "ck_news_poll_votes_kind",
        "news_poll_votes",
        "(option_id IS NOT NULL AND custom_text IS NULL)"
        " OR (option_id IS NULL AND custom_text IS NOT NULL)",
    )
    op.create_index(
        "idx_news_poll_votes_question_option",
        "news_poll_votes",
        ["question_id", "option_id"],
    )
    op.create_index(
        "idx_news_poll_votes_voter_question",
        "news_poll_votes",
        ["voter_id", "question_id"],
    )
    # Partial unique: prevent duplicate option per voter per question
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_news_poll_votes_voter_question_option"
            " ON news_poll_votes (voter_id, question_id, option_id)"
            " WHERE option_id IS NOT NULL"
        )
    )

    # 5. Drop migrated columns from news_polls
    op.drop_constraint("ck_news_polls_max_choices", "news_polls", type_="check")
    op.drop_column("news_polls", "question")
    op.drop_column("news_polls", "is_multiple")
    op.drop_column("news_polls", "max_choices")


def downgrade() -> None:
    # Re-add columns on news_polls
    op.add_column(
        "news_polls",
        sa.Column("question", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "news_polls",
        sa.Column(
            "is_multiple",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "news_polls",
        sa.Column("max_choices", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE news_polls p
            SET question = q.text,
                is_multiple = q.is_multiple,
                max_choices = q.max_choices
            FROM news_poll_questions q
            WHERE q.poll_id = p.id
              AND q.sort_order = (
                SELECT MIN(sort_order) FROM news_poll_questions WHERE poll_id = p.id
              )
            """
        )
    )
    op.alter_column("news_polls", "question", nullable=False)
    op.create_check_constraint(
        "ck_news_polls_max_choices",
        "news_polls",
        "max_choices IS NULL OR (is_multiple = true AND max_choices >= 1)",
    )

    # Restore options.poll_id
    op.add_column(
        "news_poll_options",
        sa.Column("poll_id", UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE news_poll_options o
            SET poll_id = q.poll_id
            FROM news_poll_questions q
            WHERE q.id = o.question_id
            """
        )
    )
    op.alter_column("news_poll_options", "poll_id", nullable=False)
    op.drop_index(
        "idx_news_poll_options_question_sort", table_name="news_poll_options"
    )
    op.drop_constraint(
        "fk_news_poll_options_question_id", "news_poll_options", type_="foreignkey"
    )
    op.drop_column("news_poll_options", "question_id")
    op.create_foreign_key(
        "news_poll_options_poll_id_fkey",
        "news_poll_options",
        "news_polls",
        ["poll_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_poll_options_poll_id_sort",
        "news_poll_options",
        ["poll_id", "sort_order"],
    )

    # Revert votes
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS uq_news_poll_votes_voter_question_option"
        )
    )
    op.drop_index(
        "idx_news_poll_votes_voter_question", table_name="news_poll_votes"
    )
    op.drop_index(
        "idx_news_poll_votes_question_option", table_name="news_poll_votes"
    )
    op.drop_constraint("ck_news_poll_votes_kind", "news_poll_votes", type_="check")
    # Drop custom-only votes (cannot represent them in old schema)
    op.execute(sa.text("DELETE FROM news_poll_votes WHERE option_id IS NULL"))
    op.alter_column("news_poll_votes", "option_id", nullable=False)
    op.create_unique_constraint(
        "uq_news_poll_votes_option_voter",
        "news_poll_votes",
        ["option_id", "voter_id"],
    )
    op.create_index(
        "idx_news_poll_votes_poll_id_option_id",
        "news_poll_votes",
        ["poll_id", "option_id"],
    )
    op.drop_constraint(
        "fk_news_poll_votes_question_id", "news_poll_votes", type_="foreignkey"
    )
    op.drop_column("news_poll_votes", "custom_text")
    op.drop_column("news_poll_votes", "question_id")

    op.drop_index(
        "idx_news_poll_questions_poll_sort", table_name="news_poll_questions"
    )
    op.drop_table("news_poll_questions")
