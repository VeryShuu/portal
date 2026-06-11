"""Pydantic schemas for the email-signature generator (docs/wip/signature.md).

Stateless module: no DB tables. Runtime config (cities, office phones, support
email, company/logo URLs) lives in ``/data/settings/signature.json`` and is
modelled by :class:`SignatureSettings`. The corporate email domain is a code
constant, not a configurable field.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Language = Literal["Ru", "Eng"]
Device = Literal["PC", "Web", "Apple", "Phone"]

EMAIL_DOMAIN = "mage.ru"


# ── Runtime settings (/data/settings/signature.json) ─────────────────────────


class SignatureCity(BaseModel):
    id: int
    label_ru: str
    label_eng: str
    suffix_ru: str = ""
    suffix_eng: str = ""


def _default_cities() -> list[SignatureCity]:
    return [
        SignatureCity(id=1, label_ru="Мурманск", label_eng="Murmansk"),
        SignatureCity(
            id=2,
            label_ru="Москва",
            label_eng="Moscow",
            suffix_ru=", МАГЭ Москва",
            suffix_eng=", MAGE Moscow",
        ),
        SignatureCity(
            id=3,
            label_ru="Санкт-Петербург",
            label_eng="St. Petersburg",
            suffix_ru=", МАГЭ Санкт-Петербург",
            suffix_eng=", MAGE St. Petersburg",
        ),
        SignatureCity(
            id=4,
            label_ru="Сочи",
            label_eng="Sochi",
            suffix_ru=", МАГЭ Сочи",
            suffix_eng=", MAGE Sochi",
        ),
    ]


def _default_office_phones() -> list[str]:
    return [
        "+7 (8152) 400 580",
        "+7 (495) 66 555 66",
        "+7 (812) 339 64 04",
        "+7 (862) 2 665 665",
    ]


class SignatureSettings(BaseModel):
    cities: list[SignatureCity] = Field(default_factory=_default_cities)
    office_phones: list[str] = Field(default_factory=_default_office_phones)
    support_email: str = "it@mage.ru"
    company_url: str = "http://mage.ru/"
    logo_base_url: str = "http://mage.ru/signature/images/"


class SignatureSettingsIn(BaseModel):
    cities: list[SignatureCity] = Field(min_length=1)
    office_phones: list[str] = Field(min_length=1)
    support_email: str = Field(min_length=1, max_length=255)
    company_url: str = Field(min_length=1, max_length=512)
    logo_base_url: str = Field(min_length=1, max_length=512)


# ── Config served to the form ────────────────────────────────────────────────


class SignatureConfigResponse(BaseModel):
    cities: list[SignatureCity]
    office_phones: list[str]
    support_email: str
    email_domain: str = EMAIL_DOMAIN


# ── Generation ───────────────────────────────────────────────────────────────


class SignatureGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    surname: str = Field(min_length=1, max_length=20)
    position: str = Field(min_length=1, max_length=150)
    language: Language = "Ru"
    device: Device = "PC"
    city_id: int
    office_phone: str | None = Field(default=None, max_length=50)
    extension: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    mobile_phone: str | None = Field(default=None, max_length=50)
    email: str = Field(min_length=1, max_length=255)

    @field_validator("name", "surname", "position", "mobile_phone", "office_phone")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        # EmailStr не используется намеренно (DNS-проверка ломается на
        # корпоративных доменах, см. AGENTS.md). Домен — строго @mage.ru.
        v = v.strip()
        if "@" not in v:
            raise ValueError("Invalid email")
        if not v.lower().endswith("@" + EMAIL_DOMAIN):
            raise ValueError(f"Email must be on @{EMAIL_DOMAIN}")
        return v


class SignatureGenerateResponse(BaseModel):
    html: str
    filename: str
