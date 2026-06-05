"""object directories (universal directories of objects with contacts)

Revision ID: 064
Revises: 063
Create Date: 2026-06-04
"""

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "064"
down_revision: str | None = "063"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_FLEET_FIELD_SCHEMA = [
    {
        "key": "imo",
        "label_ru": "IMO",
        "label_en": "IMO",
        "type": "text",
        "required": False,
        "sort_order": 0,
    },
    {
        "key": "callsign",
        "label_ru": "Позывной",
        "label_en": "Call sign",
        "type": "text",
        "required": False,
        "sort_order": 1,
    },
    {
        "key": "mmsi",
        "label_ru": "MMSI",
        "label_en": "MMSI",
        "type": "text",
        "required": False,
        "sort_order": 2,
    },
    {
        "key": "vsat_main",
        "label_ru": "V-SAT (основной)",
        "label_en": "V-SAT (main)",
        "type": "text",
        "required": False,
        "sort_order": 3,
    },
    {
        "key": "dial_note",
        "label_ru": "Порядок набора",
        "label_en": "Dialing note",
        "type": "multiline",
        "required": False,
        "sort_order": 4,
    },
]

_FLEET_CHANNELS = [
    {"key": "vsat_ext", "label_ru": "V-SAT (доб.)", "label_en": "V-SAT (ext.)", "sort_order": 0},
    {"key": "iridium", "label_ru": "Iridium", "label_en": "Iridium", "sort_order": 1},
    {"key": "inmarsat", "label_ru": "Inmarsat", "label_en": "Inmarsat", "sort_order": 2},
    {"key": "email", "label_ru": "E-mail", "label_en": "E-mail", "sort_order": 3},
    {"key": "mobile", "label_ru": "Мобильный", "label_en": "Mobile", "sort_order": 4},
]


def upgrade() -> None:
    op.create_table(
        "object_directories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(50), nullable=False, unique=True),
        sa.Column("label_ru", sa.String(100), nullable=False),
        sa.Column("label_en", sa.String(100), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "field_schema",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "channels",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_object_directories_sort", "object_directories", ["sort_order"])

    op.create_table(
        "object_directory_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "directory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("object_directories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("avatar_path", sa.String(500), nullable=True),
        sa.Column("folder_url", sa.String(2048), nullable=True),
        sa.Column(
            "attributes",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_ode_directory", "object_directory_entries", ["directory_id", "sort_order"])
    op.create_index("idx_ode_active", "object_directory_entries", ["deleted_at"])

    op.create_table(
        "object_entry_contacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("object_directory_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("idx_oec_entry", "object_entry_contacts", ["entry_id", "sort_order"])

    _seed_fleet()


def _seed_fleet() -> None:
    directory_id = uuid.uuid4()
    entry_id = uuid.uuid4()

    op.execute(
        sa.text(
            """
            INSERT INTO object_directories
                (id, slug, label_ru, label_en, icon, description,
                 field_schema, channels, enabled, sort_order)
            VALUES
                (:id, :slug, :label_ru, :label_en, :icon, :description,
                 CAST(:field_schema AS jsonb), CAST(:channels AS jsonb), TRUE, 0)
            """
        ).bindparams(
            id=directory_id,
            slug="fleet",
            label_ru="Флот",
            label_en="Fleet",
            icon="boat",
            description="Перечень судов компании: идентификация и каналы связи.",
            field_schema=json.dumps(_FLEET_FIELD_SCHEMA, ensure_ascii=False),
            channels=json.dumps(_FLEET_CHANNELS, ensure_ascii=False),
        )
    )

    attributes = {
        "imo": "9489481",
        "callsign": "UBXQ6",
        "mmsi": "273411580",
        "vsat_main": "+7 (8152) 400-580",
        "dial_note": "При наборе из России: 8 10 8 (8167) …",
    }
    op.execute(
        sa.text(
            """
            INSERT INTO object_directory_entries
                (id, directory_id, name, attributes, sort_order)
            VALUES
                (:id, :directory_id, :name, CAST(:attributes AS jsonb), 0)
            """
        ).bindparams(
            id=entry_id,
            directory_id=directory_id,
            name="Академик Казанин",
            attributes=json.dumps(attributes, ensure_ascii=False),
        )
    )

    contacts = [
        ("Мостик", "vsat_ext", None, "262", 0),
        ("Мостик", "email", None, "akz_bridge@mage.ru", 1),
        ("Капитан", "vsat_ext", None, "261", 2),
        ("Начальник рейса", "vsat_ext", None, "263", 3),
        ("Навигаторы", "email", None, "akznav@mage.ru", 4),
        (None, "iridium", None, "+8 (8167) 710-56-09", 5),
        (None, "inmarsat", None, "427312475 / 427312474", 6),
        (None, "mobile", None, "+7 (911) 313-07-11", 7),
    ]
    for role, channel, label, value, sort_order in contacts:
        op.execute(
            sa.text(
                """
                INSERT INTO object_entry_contacts
                    (id, entry_id, role, channel, label, value, sort_order)
                VALUES
                    (:id, :entry_id, :role, :channel, :label, :value, :sort_order)
                """
            ).bindparams(
                id=uuid.uuid4(),
                entry_id=entry_id,
                role=role,
                channel=channel,
                label=label,
                value=value,
                sort_order=sort_order,
            )
        )


def downgrade() -> None:
    op.drop_index("idx_oec_entry", table_name="object_entry_contacts")
    op.drop_table("object_entry_contacts")
    op.drop_index("idx_ode_active", table_name="object_directory_entries")
    op.drop_index("idx_ode_directory", table_name="object_directory_entries")
    op.drop_table("object_directory_entries")
    op.drop_index("idx_object_directories_sort", table_name="object_directories")
    op.drop_table("object_directories")
