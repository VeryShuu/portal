"""Юнит-тесты ``learning_base_url`` (ADR-050, инкремент 6).

Контракты:
- настройка отсутствует/пуста → письма и ссылки идут на дефолт домена
  (``LEARN_BASE_URL``) — публичный контур ещё не введён;
- настройка задана → используется она (письма учёток, ссылки внешним участникам);
- значение без scheme нормализуется (``learn.mage.ru`` → ``https://learn.mage.ru``),
  как у ``portal_base_url`` — иначе CSRF Origin-проверка ломается.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.system_config import _schemas as schemas
from app.services.learning import accounts_service as accounts
from app.services.learning.courses_service import course_link


def _settings(**over: Any) -> schemas.SystemSettings:
    return schemas.SystemSettings(**over)


@pytest.fixture()
def _patch_settings(monkeypatch):
    def _install(**over: Any) -> None:
        data = _settings(**over)
        import app.core.system_config as sc

        monkeypatch.setattr(sc, "load_system_settings", lambda: data)

    return _install


def test_default_empty_falls_back_to_learn_constant(_patch_settings):
    _patch_settings()  # learning_base_url по умолчанию ""
    assert accounts.learning_base_url() == accounts.LEARN_BASE_URL


def test_setting_overrides_constant(_patch_settings):
    _patch_settings(learning_base_url="https://edu.example.com")
    assert accounts.learning_base_url() == "https://edu.example.com"


def test_scheme_normalization():
    assert schemas.SystemSettings(learning_base_url="learn.mage.ru").learning_base_url == (
        "https://learn.mage.ru"
    )
    # пустая строка остаётся пустой (контур не введён)
    assert schemas.SystemSettings(learning_base_url="").learning_base_url == ""


def test_external_course_link_uses_setting(_patch_settings):
    _patch_settings(learning_base_url="https://edu.example.com")
    assert course_link(course_slug="otrana", is_staff=False) == (
        "https://edu.example.com/courses/otrana"
    )


def test_staff_course_link_prefers_portal_base(_patch_settings):
    _patch_settings(
        portal_base_url="https://portal.example.com",
        learning_base_url="https://edu.example.com",
    )
    assert course_link(course_slug="otrana", is_staff=True) == (
        "https://portal.example.com/learning/courses/otrana"
    )


# ── Строгая валидация на записи (Admin API), PA-025 ─────────────────────────
# Значение попадает в письма с одноразовым reset-токеном: только https-origin
# без userinfo/path/query. Хранимая модель (SystemSettings) остаётся мягкой —
# падение парса system.json целиком уронило бы все настройки на дефолты.


class TestStrictHttpsValidationOnWrite:
    @pytest.mark.parametrize(
        "value",
        [
            "http://learn.mage.ru",
            "ftp://learn.mage.ru",
            "https://",
            "https://user:pass@learn.mage.ru",
            "https://learn.mage.ru/courses",
            "https://learn.mage.ru/?next=/courses",
            "https://learn.mage.ru/#frag",
        ],
    )
    def test_rejects_insecure_or_non_origin_values(self, value):
        with pytest.raises(ValueError):
            schemas.SystemSettingsIn(learning_base_url=value)
        with pytest.raises(ValueError):
            schemas.SystemSettingsPatch(learning_base_url=value)

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("", ""),
            ("learn.mage.ru", "https://learn.mage.ru"),  # нормализация scheme
            ("https://learn.mage.ru", "https://learn.mage.ru"),
            ("https://learn.mage.ru:8443", "https://learn.mage.ru:8443"),
        ],
    )
    def test_accepts_valid_origins(self, value, expected):
        assert schemas.SystemSettingsIn(learning_base_url=value).learning_base_url == expected
        patched = schemas.SystemSettingsPatch(learning_base_url=value)
        assert patched.learning_base_url == expected

    def test_storage_model_stays_lenient_for_legacy_disk_values(self):
        # Легаси http-значение в system.json должно продолжать парситься
        # (fail-closed делает рендерер, а не валидатор загрузки).
        assert (
            schemas.SystemSettings(learning_base_url="http://learn.mage.ru").learning_base_url
            == "http://learn.mage.ru"
        )
