"""Unit-тесты secret_crypto (Этап 5, ТЗ §1.3.5).

Шифрование секретов Fernet'ом, ключ детерминированно выводится из SECRET_KEY.
Проверяем roundtrip, детерминизм ключа между вызовами и rotate_key_cache.
"""

from __future__ import annotations

from app.core import secret_crypto


class TestRoundtrip:
    def test_encrypt_decrypt(self) -> None:
        token = secret_crypto.encrypt_secret("super-secret-password")
        assert token != "super-secret-password"
        assert secret_crypto.decrypt_secret(token) == "super-secret-password"

    def test_unicode(self) -> None:
        plaintext = "пароль-123-🔑"
        assert secret_crypto.decrypt_secret(secret_crypto.encrypt_secret(plaintext)) == plaintext

    def test_different_inputs_different_tokens(self) -> None:
        # Fernet генерирует случайный IV → разные шифр-тексты для одного входа.
        a = secret_crypto.encrypt_secret("x")
        b = secret_crypto.encrypt_secret("x")
        assert a != b  # но оба расшифровываются в "x"
        assert secret_crypto.decrypt_secret(a) == "x"
        assert secret_crypto.decrypt_secret(b) == "x"


class TestKeyDerivation:
    def test_rotate_rebuilds(self) -> None:
        # rotate не должен ломать roundtrip (ключ тот же, т.к. SECRET_KEY не менялся).
        token = secret_crypto.encrypt_secret("v1")
        secret_crypto.rotate_key_cache()
        assert secret_crypto.decrypt_secret(token) == "v1"
