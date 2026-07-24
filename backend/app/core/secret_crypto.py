"""Symmetric secret encryption at rest (ТЗ §1.3.5).

Используется для шифрования IMAP-пароля helpdesk-mailbox (и других модульных
секретов). Ключ детерминированно выводится из ``Settings.secret_key`` (поле
существует, ``min_length=32`` — проверено в ``app/core/config.py``) через
SHA-256 → urlsafe base64 и применяется с ``cryptography.fernet.Fernet``.

Детерминизм ключа означает, что любой backend-инстанс с тем же ``SECRET_KEY``
может расшифровать секрет — это требуется для распределённой отправки
(outbox обрабатывается несколькими воркерами). ``SECRET_KEY`` сам по себе
已是 секрет сервера и не логируется.
"""

from __future__ import annotations

import base64
import hashlib
from typing import cast

from cryptography.fernet import Fernet

from app.core.config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazily build a Fernet cipher derived from ``SECRET_KEY`` (cached)."""
    global _fernet
    if _fernet is None:
        secret = get_settings().secret_key.encode("utf-8")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret string → Fernet token (str, safe to store in DB)."""
    return cast(str, _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8"))


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token → original secret string."""
    return cast(str, _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8"))


def rotate_key_cache() -> None:
    """Drop the cached Fernet so the next call re-derives the key from settings.

    Useful in tests that monkeypatch ``SECRET_KEY`` between cases."""
    global _fernet
    _fernet = None
