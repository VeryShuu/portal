"""Password hashing edge-cases (bcrypt + SHA256 pre-hash)."""

from __future__ import annotations

from app.core.security import hash_password, verify_password


def test_basic_roundtrip():
    h = hash_password("CorrectHorseBatteryStaple!")
    assert verify_password("CorrectHorseBatteryStaple!", h)
    assert not verify_password("wrong", h)


def test_long_password_not_truncated():
    """Bcrypt усекает до 72 байт; pre-hash через SHA256 устраняет проблему."""
    long_pw = "a" * 200 + "Z9!"
    long_pw_diff = "a" * 200 + "Z9?"
    h = hash_password(long_pw)
    assert verify_password(long_pw, h)
    assert not verify_password(long_pw_diff, h)


def test_unicode_password():
    pw = "Парол ь 🔐 !"
    h = hash_password(pw)
    assert verify_password(pw, h)
    assert not verify_password("Парол ь 🔓 !", h)


def test_hash_is_unique_per_call():
    """Salt должен делать хэши разными при одинаковом пароле."""
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a)
    assert verify_password("same", b)


def test_verify_invalid_hash_returns_false():
    assert verify_password("any", "not-a-bcrypt-hash") is False
    assert verify_password("any", "") is False


def test_bcrypt_format():
    h = hash_password("x")
    assert h.startswith("$2b$") or h.startswith("$2a$") or h.startswith("$2y$")
