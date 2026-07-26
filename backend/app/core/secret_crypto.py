"""Symmetric secret encryption at rest (ТЗ §1.3.5).

Используется для шифрования IMAP-пароля helpdesk-mailbox (и других модульных
секретов). Ключ детерминированно выводится из ``Settings.secret_key`` (поле
существует, ``min_length=32`` — проверено в ``app/core/config.py``) через
SHA-256 → urlsafe base64 и применяется с ``cryptography.fernet.Fernet``.

Детерминизм ключа означает, что любой backend-инстанс с тем же ``SECRET_KEY``
может расшифровать секрет — это требуется для распределённой отправки
(outbox обрабатывается несколькими воркерами). ``SECRET_KEY`` сам по себе
секрет сервера и не логируется.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import cast

from cryptography.fernet import Fernet

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _build_fernet() -> Fernet:
    """Build a Fernet cipher derived from ``SECRET_KEY``.

    Вычисление детерминировано (один и тот же ``SECRET_KEY`` → один и тот же
    ключ), поэтому ``lru_cache(maxsize=1)`` корректен и потокобезопасен
    (см. audit [L16]): раньше module-level ``_fernet: Fernet | None`` с ручным
    guard'ом имел теоретическую race при concurrent first-call из
    thread-pool executor'а. ``lru_cache`` атомарен на уровне CPython.
    Для инвалидации в тестах (смена ``SECRET_KEY``) — ``rotate_key_cache()``.
    """
    secret = get_settings().secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string → Fernet token (str, safe to store in DB)."""
    return cast(str, _build_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8"))


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token → original secret string."""
    return cast(str, _build_fernet().decrypt(token.encode("utf-8")).decode("utf-8"))


def rotate_key_cache() -> None:
    """Drop the cached Fernet so the next call re-derives the key from settings.

    Useful in tests that monkeypatch ``SECRET_KEY`` between cases."""
    _build_fernet.cache_clear()
