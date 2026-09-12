"""Unit-тесты для app/services/signature_settings.py (stateless storage).

Покрытие:
- load_signature_settings: дефолты при отсутствии файла
- save → read round-trip (атомарная запись, валидный JSON)
- read_signature_settings: None при отсутствии файла и при битом JSON
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.signature import SignatureSettings
from app.services import signature_settings as store


@pytest.fixture()
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "signature.json"
    monkeypatch.setattr(store, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(store, "SIGNATURE_SETTINGS_FILE", path)
    return path


def test_load_defaults_when_file_missing(settings_file: Path):
    assert not settings_file.exists()
    s = store.load_signature_settings()
    assert s.support_email == "it@mage.ru"
    assert len(s.cities) == 4


def test_read_returns_none_when_file_missing(settings_file: Path):
    assert store.read_signature_settings() is None


def test_save_then_read_round_trip(settings_file: Path):
    original = SignatureSettings(
        support_email="help@mage.ru",
        company_url="http://example.org/",
        logo_base_url="http://example.org/img/",
    )
    store.save_signature_settings(original)

    assert settings_file.exists()
    loaded = store.read_signature_settings()
    assert loaded is not None
    assert loaded.support_email == "help@mage.ru"
    assert loaded.company_url == "http://example.org/"
    assert loaded.logo_base_url == "http://example.org/img/"
    assert [c.id for c in loaded.cities] == [c.id for c in original.cities]


def test_read_returns_none_on_corrupt_json(settings_file: Path):
    settings_file.write_text("{ not valid json", encoding="utf-8")
    assert store.read_signature_settings() is None


def test_load_falls_back_to_defaults_on_corrupt_json(settings_file: Path):
    settings_file.write_text("{ not valid json", encoding="utf-8")
    s = store.load_signature_settings()
    assert s.support_email == "it@mage.ru"
