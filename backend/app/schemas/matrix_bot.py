"""Pydantic-схемы настроек Matrix-бота (admin endpoints ``/admin/matrix-bot``).

Зеркалируют ``HelpdeskMaxBotSettings*`` (app/schemas/helpdesk.py): токен
write-only (пустое поле = оставить прежний шифр), ``configured`` —
производное (enabled + токен + обязательные поля).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MatrixBotSettingsIn(BaseModel):
    enabled: bool = False
    # Long-lived mct_... от mas-cli; write-only — пусто/None = не менять.
    access_token: str | None = Field(default=None, min_length=1, max_length=512)
    # API endpoint Synapse (FQDN или внутренний адрес), со схемой http(s).
    homeserver_url: str | None = Field(default=None, min_length=1, max_length=255)
    # Server-часть MXID (borzihin.vs@mage.ru → @borzihin.vs:matrix.mage.ru).
    server_name: str | None = Field(default=None, min_length=1, max_length=255)
    # @portal-bot:matrix.mage.ru — нужен для account data m.direct.
    bot_user_id: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("access_token")
    @classmethod
    def strip_token(cls, v: str | None) -> str | None:
        # Токен вставляют копипастой из вывода mas-cli: хвостовой пробел/перенос
        # доходит до ``Authorization: Bearer`` и h11 отклоняет заголовок
        # («Illegal header value»), а админ видит вводящую в заблуждение
        # ошибку «Homeserver unreachable». Стриппим на входе.
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("access_token must not be blank")
        return v

    @field_validator("homeserver_url")
    @classmethod
    def validate_homeserver_scheme(cls, v: str | None) -> str | None:
        # scheme обязателен (как portal_base_url): без него httpx/CSRF-логика
        # ведёт себя неожидаемо.
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("homeserver_url must not be blank")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("homeserver_url must start with http:// or https://")
        return v

    @field_validator("server_name", "bot_user_id")
    @classmethod
    def strip_lower(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            raise ValueError("value must not be blank")
        return v


class MatrixBotSettingsOut(BaseModel):
    configured: bool
    enabled: bool
    access_token_set: bool
    homeserver_url: str | None
    server_name: str
    bot_user_id: str | None
    updated_at: datetime


class MatrixBotTestResult(BaseModel):
    ok: bool
    error: str | None = None
    detail: str | None = None


class MatrixBotTestIn(BaseModel):
    """Кому отправить тестовое сообщение (POST /admin/matrix-bot/test).

    ``target`` опционален и понимает три формы: полный MXID
    (``@user:server``), email (→ MXID по конвенции) или голый localpart
    (``ivanov`` → ``@ivanov:server_name``). Пусто/None → MXID самого админа
    по конвенции из его email (локальный админ может отличаться — тогда
    указывайте MXID явно).
    """

    target: str | None = Field(default=None, min_length=1, max_length=255)
