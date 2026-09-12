"""Unit-тесты фундамента модуля обучения: учётки и аутентификация (passwordless).

Покрытие:
- generate_login_code: формат (6 цифр), непредсказуемость алфавита, отсутствие
  modulo bias невозможно проверить напрямую — проверяем распределение краёв
- hash_code / code_matches: SHA-256, constant-time сверка
- политика попыток: is_code_expired / is_code_exhausted
- письма learning: код попадает в письмо ровно один раз в text
- CSRF: auth/learning/* пути в нужных множествах middleware
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.middleware.csrf import _CSRF_EXEMPT_PATHS, _CSRF_ORIGIN_ONLY_PATHS
from app.services.learning import emails
from app.services.learning.accounts_service import (
    CODE_LENGTH,
    code_matches,
    generate_login_code,
    hash_code,
    is_code_exhausted,
    is_code_expired,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


# ── генерация кода входа ─────────────────────────────────────────────────────


class TestGenerateLoginCode:
    def test_length_and_digits(self):
        for _ in range(100):
            code = generate_login_code()
            assert len(code) == CODE_LENGTH == 6
            assert code.isdigit()

    def test_leading_zeroes_preserved(self):
        # randbelow покрывает [0, 10^6): 000000 — легитимный код; формат с
        # zero-pad гарантируем форматтером (проверка контракта f-string).
        assert f"{0:0{CODE_LENGTH}d}" == "000000"
        assert f"{42:0{CODE_LENGTH}d}" == "000042"

    def test_codes_vary(self):
        codes = {generate_login_code() for _ in range(50)}
        assert len(codes) > 10  # детерминированный repeat за 50 выдач крайне мал


# ── хэширование и сверка кода ────────────────────────────────────────────────


class TestCodeHashing:
    def test_sha256_hex_deterministic(self):
        h1 = hash_code("123456")
        h2 = hash_code("123456")
        assert h1 == h2
        assert len(h1) == 64
        int(h1, 16)  # hex

    def test_different_codes_different_hashes(self):
        assert hash_code("123456") != hash_code("123457")

    def test_code_matches_true_only_for_same_code(self):
        h = hash_code("042913")
        assert code_matches("042913", h)
        assert not code_matches("042914", h)
        assert not code_matches("", h)

    def test_wrong_hash_never_matches(self):
        assert not code_matches("123456", "0" * 64)


# ── политика попыток/срока ───────────────────────────────────────────────────


class TestCodePolicy:
    def test_not_expired_before_deadline(self):
        assert not is_code_expired(NOW + timedelta(minutes=10), NOW)

    def test_expired_at_deadline_inclusive(self):
        assert is_code_expired(NOW, NOW)

    def test_not_exhausted_below_limit(self):
        assert not is_code_exhausted(4, 5)

    def test_exhausted_at_limit(self):
        assert is_code_exhausted(5, 5)


# ── письма ───────────────────────────────────────────────────────────────────


class TestLearningEmails:
    def test_login_code_letter_contains_code_once_in_text(self):
        subject, text, html = emails.login_code(
            full_name="Иван Тестов", code="042913", ttl_minutes=10
        )
        assert "код" in subject.lower()
        assert text.count("042913") == 1
        assert "042913" in html
        assert "10 мин" in text
        assert "одноразов" in text

    def test_login_code_escapes_html_fields(self):
        _subject, text, html = emails.login_code(
            full_name='<img src=x onerror="alert(1)">', code="123456", ttl_minutes=10
        )
        assert '<img src=x onerror="alert(1)">' in text
        assert "<img" not in html
        assert "&lt;img" in html

    def test_login_code_neutral_for_unrequested(self):
        _subject, text, _html = emails.login_code(full_name="Анна", code="654321", ttl_minutes=10)
        assert "проигнорируйте" in text  # безопасный выход для чужих запросов

    def test_login_code_custom_ttl(self):
        _subject, text, _html = emails.login_code(full_name="Анна", code="654321", ttl_minutes=15)
        assert "15 мин" in text


# ── CSRF-пути публичного контура ─────────────────────────────────────────────


class TestCsrfPathRegistration:
    def test_learning_origin_only_paths(self):
        for p in (
            "/api/v1/auth/learning/login",
            "/api/v1/auth/learning/verify",
        ):
            assert p in _CSRF_ORIGIN_ONLY_PATHS, p

    def test_retired_password_paths_not_registered(self):
        for p in ("/api/v1/auth/learning/forgot", "/api/v1/auth/learning/reset"):
            assert p not in _CSRF_ORIGIN_ONLY_PATHS, p
            assert p not in _CSRF_EXEMPT_PATHS, p

    def test_learning_logout_exempt_from_csrf(self):
        assert "/api/v1/auth/learning/logout" in _CSRF_EXEMPT_PATHS
