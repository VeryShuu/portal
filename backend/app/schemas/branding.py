"""Pydantic schemas for the branding / email-settings API.

Extracted from ``app.api.branding`` so that handlers stay thin and schemas can
be reused by other modules (for example the bootstrap aggregator) without
pulling in router dependencies.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BrandingSettings(BaseModel):
    portal_name: str = "Корпоративный портал"
    portal_tagline: str = ""
    accent_color: str = "#d8262c"
    # Режим подзаголовка Hero: auto (по времени суток, стандартные тексты i18n) /
    # custom (свои тексты ниже, по тому же расписанию) / hidden (не показывать).
    hero_subtitle_mode: Literal["auto", "custom", "hidden"] = "auto"
    # Свои тексты подзаголовка по слотам (только в режиме custom). Каждый
    # показывается в своё время суток (границы — hero_*_hour выше).
    hero_subtitle_morning: str = ""
    hero_subtitle_day: str = ""
    hero_subtitle_evening: str = ""
    hero_subtitle_night: str = ""
    banner_enabled: bool = False
    banner_text: str = ""
    banner_type: Literal["info", "warning", "error", "success"] = "info"
    banner_expires_at: str | None = None
    logo_hidden: bool = False
    # Hero-фон главной страницы (эксперимент): границы часовых слотов (0..23),
    # по которым HeroBlock выбирает утренний/дневной/вечерний фон. Сами изображения
    # загружаются как ассеты hero-bg-morning/day/evening (механизм как у login-bg).
    hero_morning_hour: int = Field(default=6, ge=0, le=23)
    hero_day_hour: int = Field(default=12, ge=0, le=23)
    hero_evening_hour: int = Field(default=18, ge=0, le=23)
    # Focal-point позиционирования Hero-фонов (механизм как у news cover focal).
    # x/y — integer percent 0..100 (точка фокуса), zoom — 100..300 (100=без zoom).
    # Все nullable: null = центрирование без zoom (sane default). Нет БД-миграций —
    # branding хранится в settings.json, новые поля появляются автоматически.
    hero_bg_morning_focal_x: int | None = Field(default=None, ge=0, le=100)
    hero_bg_morning_focal_y: int | None = Field(default=None, ge=0, le=100)
    hero_bg_morning_focal_zoom: int | None = Field(default=None, ge=100, le=300)
    hero_bg_day_focal_x: int | None = Field(default=None, ge=0, le=100)
    hero_bg_day_focal_y: int | None = Field(default=None, ge=0, le=100)
    hero_bg_day_focal_zoom: int | None = Field(default=None, ge=100, le=300)
    hero_bg_evening_focal_x: int | None = Field(default=None, ge=0, le=100)
    hero_bg_evening_focal_y: int | None = Field(default=None, ge=0, le=100)
    hero_bg_evening_focal_zoom: int | None = Field(default=None, ge=100, le=300)


class BrandingSettingsOut(BrandingSettings):
    has_favicon: bool = False
    has_login_bg: bool = False
    has_logo: bool = False
    logo_updated_at: str | None = None
    allowed_iframe_origins: list[str] = []
    has_hero_bg_morning: bool = False
    has_hero_bg_day: bool = False
    has_hero_bg_evening: bool = False


class EmailSettings(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=25, ge=1, le=65535)
    from_address: str = Field(default="")
    username: str = Field(default="")
    password: str = Field(default="", description="Masked as '***' in GET response if set")
    use_tls: bool = Field(default=False)
    use_starttls: bool = Field(default=False)
    # Общий приёмник почты портала (ADR-048): используется модулями (erp_sync),
    # фильтры писём остаются per-module. Пароль хранится Fernet-шифром
    # (imap_password_enc на диске), в отличие от SMTP-пароля (plaintext).
    imap_host: str = Field(default="")
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_use_ssl: bool = Field(default=True)
    imap_username: str = Field(default="")
    imap_password: str = Field(default="", description="Fernet-encrypted on disk")
    imap_folder: str = Field(default="INBOX", min_length=1, max_length=100)


class EmailSettingsIn(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=25, ge=1, le=65535)
    from_address: str = Field(default="")
    username: str = Field(default="")
    password: str | None = Field(
        default=None,
        description=(
            "Pass null or '***' to keep existing password; "
            "pass '' to clear; pass new value to update"
        ),
    )
    use_tls: bool = Field(default=False)
    use_starttls: bool = Field(default=False)
    # IMAP-пароль — write-only с той же keep/clear/update семантикой, но хранится
    # Fernet-шифром (см. EmailSettings.imap_password).
    imap_host: str = Field(default="")
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_use_ssl: bool = Field(default=True)
    imap_username: str = Field(default="")
    imap_password: str | None = Field(default=None, min_length=1, max_length=512)
    imap_folder: str = Field(default="INBOX", min_length=1, max_length=100)


class EmailSettingsOut(BaseModel):
    host: str
    port: int
    from_address: str
    username: str
    password_set: bool
    use_tls: bool
    use_starttls: bool
    imap_host: str
    imap_port: int
    imap_use_ssl: bool
    imap_username: str
    imap_password_set: bool
    imap_folder: str


class EmailTestRequest(BaseModel):
    to: str = Field(description="Email address to send test message to")
