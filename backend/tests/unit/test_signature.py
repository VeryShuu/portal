"""Unit tests for the email-signature module (pure, no DB).

Covers the renderer (the 4 device layouts × 2 languages × mobile-present/absent
matrix that replaces the 16 legacy PHP templates), filename suffixes, HTML
escaping, city-suffix mapping, and request-schema validation (@mage.ru domain,
extension pattern).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.signature import (
    Device,
    Language,
    SignatureGenerateRequest,
    SignatureSettings,
)
from app.services import signature as svc


def _req(**overrides) -> SignatureGenerateRequest:
    base: dict[str, Any] = {
        "name": "Иван",
        "surname": "Петров",
        "position": "Инженер",
        "language": "Ru",
        "device": "PC",
        "city_id": 2,
        "office_phone": "+7 (8152) 400 580",
        "extension": "123",
        "mobile_phone": "+7 (900) 000 0000",
        "email": "ivan@mage.ru",
    }
    base.update(overrides)
    return SignatureGenerateRequest(**base)


_SETTINGS = SignatureSettings()


# ── City suffix ───────────────────────────────────────────────────────────────


class TestCitySuffix:
    def test_murmansk_no_suffix(self):
        assert svc._city_suffix(_req(city_id=1), _SETTINGS) == ""

    def test_moscow_ru(self):
        assert svc._city_suffix(_req(city_id=2), _SETTINGS) == ", МАГЭ Москва"

    def test_moscow_eng(self):
        assert svc._city_suffix(_req(city_id=2, language="Eng"), _SETTINGS) == ", MAGE Moscow"

    def test_unknown_city_empty(self):
        assert svc._city_suffix(_req(city_id=999), _SETTINGS) == ""


# ── Phone line ────────────────────────────────────────────────────────────────


class TestPhoneLine:
    def test_with_extension(self):
        assert svc._phone_line(_req()) == "+7 (8152) 400 580 / 123"

    def test_without_extension(self):
        assert svc._phone_line(_req(extension=None)) == "+7 (8152) 400 580"

    def test_no_office_phone(self):
        assert svc._phone_line(_req(office_phone=None, extension=None)) == ""


# ── Filenames (8 device×lang combinations) ────────────────────────────────────


class TestFilename:
    @pytest.mark.parametrize(
        ("device", "language", "expected"),
        [
            ("PC", "Ru", "ИванПетров_Ru.htm"),
            ("PC", "Eng", "ИванПетров_Eng.htm"),
            ("Web", "Ru", "ИванПетров_Ru.htm"),
            ("Web", "Eng", "ИванПетров_Eng.htm"),
            ("Apple", "Ru", "ИванПетров_AppleRu.htm"),
            ("Apple", "Eng", "ИванПетров_AppleEng.htm"),
            ("Phone", "Ru", "ИванПетров_AndroidRu.htm"),
            ("Phone", "Eng", "ИванПетров_AndroidEng.htm"),
        ],
    )
    def test_suffix(self, device: Device, language: Language, expected: str):
        out = svc.render_signature(_req(device=device, language=language), _SETTINGS)
        assert out.filename == expected


# ── Logo selection (PC/Apple/Web) ─────────────────────────────────────────────


class TestLogos:
    def test_pc_ru_logo(self):
        html = svc.render_signature(_req(device="PC", language="Ru"), _SETTINGS).html
        assert "http://mage.ru/signature/images/Mage_Ru.png" in html
        assert 'width="60"' in html and 'height="48"' in html

    def test_pc_eng_logo(self):
        html = svc.render_signature(_req(device="PC", language="Eng"), _SETTINGS).html
        assert "Mage_Eng.png" in html

    def test_apple_uses_mage_logo(self):
        html = svc.render_signature(_req(device="Apple", language="Ru"), _SETTINGS).html
        assert "Mage_Ru.png" in html

    def test_web_logo_and_dimensions(self):
        html = svc.render_signature(_req(device="Web", language="Ru"), _SETTINGS).html
        assert "WebRu.png" in html
        assert 'width="68"' in html and 'height="125"' in html

    def test_logo_base_url_trailing_slash_normalised(self):
        s = SignatureSettings(logo_base_url="http://x/img")
        html = svc.render_signature(_req(device="PC"), s).html
        assert "http://x/img/Mage_Ru.png" in html


# ── Phone (text) layout ───────────────────────────────────────────────────────


class TestPhoneLayout:
    def test_no_logo(self):
        html = svc.render_signature(_req(device="Phone"), _SETTINGS).html
        assert "<img" not in html
        assert ".png" not in html

    def test_ends_with_site_line(self):
        html = svc.render_signature(_req(device="Phone"), _SETTINGS).html
        assert "www.mage.ru" in html

    def test_contains_spans(self):
        html = svc.render_signature(_req(device="Phone"), _SETTINGS).html
        assert "<span>Иван Петров</span>" in html


# ── Mobile present/absent ─────────────────────────────────────────────────────


class TestMobileRow:
    def test_table_includes_mobile_when_present(self):
        html = svc.render_signature(_req(device="PC", mobile_phone="+7 (900) 111"), _SETTINGS).html
        assert "+7 (900) 111" in html

    def test_table_omits_mobile_when_absent(self):
        html = svc.render_signature(_req(device="PC", mobile_phone=None), _SETTINGS).html
        assert "+7 (900)" not in html

    def test_phone_omits_mobile_when_absent(self):
        html = svc.render_signature(_req(device="Phone", mobile_phone=None), _SETTINGS).html
        assert "+7 (900)" not in html


# ── Common content / escaping ─────────────────────────────────────────────────


class TestContent:
    def test_name_position_email_present(self):
        out = svc.render_signature(_req(device="PC"), _SETTINGS)
        assert "Иван Петров" in out.html
        assert "Инженер, МАГЭ Москва" in out.html
        assert "mailto:ivan@mage.ru" in out.html

    def test_html_is_escaped(self):
        out = svc.render_signature(_req(position="A & <b>B</b>"), _SETTINGS)
        assert "&amp;" in out.html
        assert "<b>B</b>" not in out.html


# ── Schema validation ─────────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_email_must_be_mage(self):
        with pytest.raises(ValidationError):
            _req(email="ivan@gmail.com")

    def test_email_mage_ok_case_insensitive(self):
        assert _req(email="Ivan@MAGE.ru").email == "Ivan@MAGE.ru"

    def test_email_without_at_rejected(self):
        with pytest.raises(ValidationError):
            _req(email="ivanmage.ru")

    def test_extension_must_be_three_digits(self):
        with pytest.raises(ValidationError):
            _req(extension="12")
        with pytest.raises(ValidationError):
            _req(extension="abc")

    def test_extension_optional(self):
        assert _req(extension=None).extension is None

    def test_name_length_limit(self):
        with pytest.raises(ValidationError):
            _req(name="x" * 21)

    def test_strips_whitespace(self):
        assert _req(name="  Иван  ").name == "Иван"


# ── build_prefill (profile → form prefill) ────────────────────────────────────


class TestBuildPrefill:
    def _build(self, **kwargs):
        base = {
            "full_name": "Гаврин Михаил Владимирович",
            "lang": "ru",
            "position": "Инженер",
            "email": "ivan@mage.ru",
            "attributes": {},
            "settings": SignatureSettings(),
        }
        base.update(kwargs)
        return svc.build_prefill(**base)

    def test_full_name_surname_first(self):
        p = self._build(full_name="Гаврин Михаил Владимирович")
        # «Фамилия Имя Отчество» → surname=Фамилия, name=Имя (отчество отброшено)
        assert p.surname == "Гаврин"
        assert p.name == "Михаил"

    def test_full_name_single_token(self):
        p = self._build(full_name="Гаврин")
        assert p.surname == "Гаврин"
        assert p.name == ""

    def test_full_name_empty(self):
        p = self._build(full_name="")
        assert p.surname == ""
        assert p.name == ""

    def test_full_name_truncated_to_20(self):
        p = self._build(full_name="Я" * 25 + " " + "И" * 25)
        assert len(p.surname) == 20
        assert len(p.name) == 20

    def test_office_phone_and_extension_parsed(self):
        p = self._build(attributes={"telephoneNumber": "8(495)6655566,346"})
        # 8(495)6655566 нормализуется к настроенному +7 (495) 66 555 66
        assert p.office_phone == "+7 (495) 66 555 66"
        assert p.extension == "346"

    def test_office_phone_no_match_left_empty(self):
        p = self._build(attributes={"telephoneNumber": "8(999)1234567,111"})
        assert p.office_phone is None
        assert p.extension == "111"

    def test_extension_non_three_digits_dropped(self):
        p = self._build(attributes={"telephoneNumber": "8(495)6655566,12"})
        assert p.extension is None

    def test_no_telephone_attr(self):
        p = self._build(attributes={})
        assert p.office_phone is None
        assert p.extension is None

    def test_mobile_from_attribute(self):
        p = self._build(attributes={"mobile": "+7 911 000 11 22"})
        assert p.mobile_phone == "+7 911 000 11 22"

    def test_mobile_list_value_takes_first(self):
        p = self._build(attributes={"mobile": ["+7 911 000 11 22", "ignored"]})
        assert p.mobile_phone == "+7 911 000 11 22"

    def test_city_matched_by_label(self):
        assert self._build(attributes={"city": "Москва"}).city_id == 2
        assert self._build(attributes={"city": "Moscow"}).city_id == 2
        assert self._build(attributes={"city": "  москва "}).city_id == 2

    def test_city_unknown_is_none(self):
        assert self._build(attributes={"city": "Казань"}).city_id is None

    def test_language_from_lang(self):
        assert self._build(lang="en").language == "Eng"
        assert self._build(lang="ru").language == "Ru"
        assert self._build(lang=None).language == "Ru"

    def test_custom_attribute_keys(self):
        settings = SignatureSettings(attr_mobile="mob", attr_office_phone="tel", attr_city="town")
        p = self._build(
            settings=settings,
            attributes={"mob": "+7 911 5", "tel": "8(495)6655566,777", "town": "Москва"},
        )
        assert p.mobile_phone == "+7 911 5"
        assert p.extension == "777"
        assert p.city_id == 2
