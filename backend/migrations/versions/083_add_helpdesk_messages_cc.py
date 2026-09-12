"""add helpdesk_messages.cc (email Cc — «ответить всем»)

Revision ID: 083
Revises: 082
Create Date: 2026-07-22

JSONB-колонка ``cc`` на ``helpdesk_messages`` — список адресатов в копии письма:
``[{"email": "a@x", "name": "Иван"}, ...]``.

* **Inbound** (письмо → тикет): заполняется из заголовка ``Cc`` входящего письма
  (парсится в ``threading.extract_cc``). Раньше Cc полностью игнорировался в
  ``_parse_inbound_headers`` — адреса из копии терялись, и «ответить всем» было
  физически невозможно.
* **Outbound** (ответ агента): при включённом агентом чекбоксе «Ответить всем»
  список Cc проходит в ``enqueue_reply_outbound`` → ``payload["cc"]`` → заголовок
  ``Cc`` в MIME (``_apply_helpdesk_headers``). Threading не меняется:
  ``In-Reply-To``/``References``/``Reply-To`` без изменений.

Zero-downtime: nullable-колонка без DEFAULT, обратная совместимость — старые
сообщения без Cc читаются как ``None``/``[]`` (сериализатор нормализует в пустой
список). DDL через ``op.execute`` (как 075–082) с ``IF NOT EXISTS`` — идемпотентно.
"""

from alembic import op

revision: str = "083"
down_revision: str | None = "082"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE helpdesk_messages
            ADD COLUMN IF NOT EXISTS cc JSONB
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE helpdesk_messages DROP COLUMN IF EXISTS cc")
