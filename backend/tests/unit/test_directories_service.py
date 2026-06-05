"""Unit tests for the object-directories service (pure, no DB).

Covers ``validate_attributes`` / ``validate_channels`` and the CSV/XLSX export
builders.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.object_directory import ObjectDirectory, ObjectDirectoryEntry, ObjectEntryContact
from app.schemas.object_directory import ContactInput
from app.services import directories as svc

_FIELD_SCHEMA = [
    {"key": "imo", "label_ru": "IMO", "type": "text", "required": True, "sort_order": 0},
    {"key": "mmsi", "label_ru": "MMSI", "type": "number", "required": False, "sort_order": 1},
    {"key": "contact_email", "label_ru": "E-mail", "type": "email", "sort_order": 2},
    {"key": "site", "label_ru": "Сайт", "type": "url", "sort_order": 3},
]

_CHANNELS = [
    {"key": "email", "label_ru": "E-mail", "sort_order": 0},
    {"key": "mobile", "label_ru": "Мобильный", "sort_order": 1},
]


class TestValidateAttributes:
    def test_unknown_key_rejected(self):
        with pytest.raises(HTTPException) as exc:
            svc.validate_attributes(_FIELD_SCHEMA, {"imo": "1", "bogus": "x"})
        assert exc.value.status_code == 422
        assert "bogus" in exc.value.detail

    def test_required_missing_rejected(self):
        with pytest.raises(HTTPException) as exc:
            svc.validate_attributes(_FIELD_SCHEMA, {"mmsi": "123"})
        assert exc.value.status_code == 422
        assert "imo" in exc.value.detail

    def test_number_invalid_rejected(self):
        with pytest.raises(HTTPException) as exc:
            svc.validate_attributes(_FIELD_SCHEMA, {"imo": "1", "mmsi": "abc"})
        assert exc.value.status_code == 422

    def test_number_accepts_comma_decimal(self):
        out = svc.validate_attributes(_FIELD_SCHEMA, {"imo": "1", "mmsi": "12,5"})
        assert out["mmsi"] == "12,5"

    def test_email_invalid_rejected(self):
        with pytest.raises(HTTPException):
            svc.validate_attributes(_FIELD_SCHEMA, {"imo": "1", "contact_email": "nope"})

    def test_url_invalid_rejected(self):
        with pytest.raises(HTTPException):
            svc.validate_attributes(_FIELD_SCHEMA, {"imo": "1", "site": "ftp://x"})

    def test_normalizes_and_trims(self):
        out = svc.validate_attributes(_FIELD_SCHEMA, {"imo": "  9489481  "})
        assert out == {"imo": "9489481"}

    def test_blank_optional_dropped(self):
        out = svc.validate_attributes(_FIELD_SCHEMA, {"imo": "1", "mmsi": "   "})
        assert "mmsi" not in out


class TestValidateChannels:
    def test_unknown_channel_rejected(self):
        contacts = [ContactInput(channel="telex", value="1")]
        with pytest.raises(HTTPException) as exc:
            svc.validate_channels(_CHANNELS, contacts)
        assert exc.value.status_code == 422

    def test_known_channels_ok(self):
        contacts = [
            ContactInput(channel="email", value="a@b.ru"),
            ContactInput(channel="mobile", value="+7"),
        ]
        svc.validate_channels(_CHANNELS, contacts)


def _entry() -> ObjectDirectoryEntry:
    return ObjectDirectoryEntry(
        name="Академик Казанин",
        attributes={"imo": "9489481"},
        note="заметка",
        contacts=[
            ObjectEntryContact(role="Мостик", channel="email", value="a@b.ru", sort_order=1),
            ObjectEntryContact(role="Капитан", channel="mobile", value="+7", sort_order=0),
        ],
    )


def _directory() -> ObjectDirectory:
    return ObjectDirectory(
        slug="fleet",
        label_ru="Флот",
        field_schema=[{"key": "imo", "label_ru": "IMO", "type": "text", "sort_order": 0}],
        channels=_CHANNELS,
    )


class TestExport:
    def test_build_export_table(self):
        headers, rows = svc.build_export_table(_directory(), [_entry()])
        assert headers == ["Название", "IMO", "Контакты", "Заметка"]
        assert rows[0][0] == "Академик Казанин"
        assert rows[0][1] == "9489481"
        # contacts ordered by sort_order: mobile (0) before email (1)
        assert rows[0][2].index("Капитан") < rows[0][2].index("Мостик")
        assert rows[0][3] == "заметка"

    def test_build_csv_has_bom_and_content(self):
        data = svc.build_csv(_directory(), [_entry()])
        assert data.startswith("\ufeff".encode())
        text = data.decode("utf-8")
        assert "Академик Казанин" in text
        assert "9489481" in text

    def test_build_xlsx_is_zip(self):
        data = svc.build_xlsx(_directory(), [_entry()])
        assert data[:2] == b"PK"

    def test_export_filename(self):
        name = svc.export_filename(_directory(), "csv")
        assert name.startswith("fleet-")
        assert name.endswith(".csv")
