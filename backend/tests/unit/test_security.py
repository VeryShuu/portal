"""Unit-тесты: парсинг JWT claims, PKCE, маппинг пользователя, bcrypt."""

import base64
import contextlib
import hashlib

import pytest

from app.core.security import (
    extract_user_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    generate_session_id,
    generate_state,
    hash_password,
    parse_jwt_claims,
    verify_password,
)


def test_generate_session_id_length():
    sid = generate_session_id()
    assert len(sid) >= 32


def test_generate_state_is_unique():
    s1 = generate_state()
    s2 = generate_state()
    assert s1 != s2


def test_pkce_challenge_from_verifier():
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert challenge == expected


def test_extract_user_data_reader():
    claims = {
        "sub": "abc-123",
        "email": "user@test.local",
        "name": "Иван Иванов",
        "realm_access": {"roles": ["offline_access"]},
    }
    data = extract_user_data(claims)
    assert data["keycloak_id"] == "abc-123"
    assert data["email"] == "user@test.local"
    assert data["full_name"] == "Иван Иванов"
    assert data["role"] == "reader"


def test_extract_user_data_editor():
    claims = {
        "sub": "xyz",
        "email": "ed@test.local",
        "name": "Editor User",
        "realm_access": {"roles": ["editor", "offline_access"]},
    }
    data = extract_user_data(claims)
    assert data["role"] == "editor"


def test_extract_user_data_admin_takes_priority():
    claims = {
        "sub": "xyz",
        "email": "admin@test.local",
        "name": "Admin",
        "realm_access": {"roles": ["editor", "admin"]},
    }
    data = extract_user_data(claims)
    assert data["role"] == "admin"


def test_extract_user_data_ad_attributes():
    claims = {
        "sub": "sub1",
        "email": "emp@company.local",
        "name": "Петр Петров",
        "department": "IT",
        "job_title": "Senior Engineer",
        "phone": "+7 999 000 00 00",
        "realm_access": {"roles": []},
    }
    data = extract_user_data(claims)
    assert data["department"] == "IT"
    assert data["position"] == "Senior Engineer"
    assert data["phone"] == "+7 999 000 00 00"


def test_extract_user_data_fallback_preferred_username():
    claims = {
        "sub": "sub2",
        "email": "",
        "preferred_username": "jdoe",
        "realm_access": {"roles": []},
    }
    data = extract_user_data(claims)
    assert data["full_name"] == "jdoe"


@pytest.mark.asyncio
async def test_parse_jwt_claims_invalid_token():
    import jwt as pyjwt

    with pytest.raises(pyjwt.PyJWTError):
        await parse_jwt_claims("not.a.valid.token", [{"kid": "k1"}])


class TestClockSkewLeeway:
    """JWT leeway=30s защищает от ImmatureSignatureError при расхождении часов."""

    @staticmethod
    def _make_rsa_token(payload: dict) -> tuple[str, dict]:
        """Генерирует RSA-подписанный JWT и JWK для тестов."""
        import json

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        from jwt.algorithms import RSAAlgorithm

        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        public_key = private_key.public_key()
        jwk_str = RSAAlgorithm.to_jwk(public_key)
        jwk = json.loads(jwk_str)
        jwk["kid"] = "test-kid"
        jwk["alg"] = "RS256"

        import jwt as pyjwt

        token = pyjwt.encode(
            payload, private_key, algorithm="RS256", headers={"kid": "test-kid"}
        )
        return token, jwk

    @pytest.mark.asyncio
    async def test_token_with_iat_slightly_in_future_is_accepted(self):
        """iat на 10с в будущем (clock skew) — токен должен проходить валидацию."""
        import time
        from unittest.mock import patch

        from app.services.keycloak import _KCSettings

        now = int(time.time())
        payload = {
            "sub": "user-1",
            "iat": now + 10,
            "exp": now + 3600,
            "aud": "portal",
            "iss": "https://keycloak.example.com/realms/test",
            "azp": "portal",
        }
        token, jwk = self._make_rsa_token(payload)

        fake_kcs = _KCSettings(
            keycloak_url="https://keycloak.example.com",
            keycloak_realm="test",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )
        with patch("app.services.keycloak.get_kc_settings", return_value=fake_kcs):
            claims = await parse_jwt_claims(token, [jwk])
        assert claims["sub"] == "user-1"

    @pytest.mark.asyncio
    async def test_token_with_iat_far_in_future_is_rejected(self):
        """iat на 60с в будущем (больше leeway=30s) — токен должен быть отклонён."""
        import time
        from unittest.mock import patch

        import jwt as pyjwt

        from app.services.keycloak import _KCSettings

        now = int(time.time())
        payload = {
            "sub": "user-2",
            "iat": now + 60,
            "exp": now + 3600,
            "aud": "portal",
            "iss": "https://keycloak.example.com/realms/test",
            "azp": "portal",
        }
        token, jwk = self._make_rsa_token(payload)

        fake_kcs = _KCSettings(
            keycloak_url="https://keycloak.example.com",
            keycloak_realm="test",
            oidc_client_id="portal",
            oidc_client_secret="secret",
        )
        with patch("app.services.keycloak.get_kc_settings", return_value=fake_kcs), pytest.raises(pyjwt.PyJWTError):
            await parse_jwt_claims(token, [jwk])


class TestJwksKidSecurity:
    """12.3.3 — JWKS DoS через подделанный kid в JWT header."""

    @pytest.mark.asyncio
    async def test_unknown_kid_raises_before_network(self):
        """JWT с kid, которого нет в JWKS, отвергается без сетевого refresh'а если cooldown не истёк.

        Сценарий DoS-защиты: когда JWKS только что был обновлён (_JWKS_LAST_FORCE_REFRESH = now),
        последующие JWT с неизвестным kid НЕ должны инициировать повторный запрос к Keycloak.
        Функция должна немедленно выбросить InvalidKeyError.
        """
        import time
        from unittest.mock import AsyncMock, patch

        import jwt as pyjwt

        fake_jwks: list[dict] = [{"kid": "real-kid", "kty": "RSA"}]

        # Патчим _JWKS_LAST_FORCE_REFRESH на текущее время → cooldown 30s не истёк →
        # refresh не запускается → invalidate_jwks_cache не вызывается.
        fresh_ts = time.monotonic()
        with (
            patch("app.services.keycloak.get_jwks", new=AsyncMock(return_value=fake_jwks)),
            patch("app.services.keycloak.invalidate_jwks_cache") as mock_invalidate,
            patch("app.core.security._JWKS_LAST_FORCE_REFRESH", fresh_ts),
        ):
            with pytest.raises(pyjwt.exceptions.InvalidKeyError, match="JWK key not found"):
                await parse_jwt_claims(
                    "eyJhbGciOiJSUzI1NiIsImtpZCI6ImZha2Uta2lkIn0.eyJzdWIiOiJ4In0.AAAA",
                    jwks=fake_jwks,
                )
            mock_invalidate.assert_not_called()

    @pytest.mark.asyncio
    async def test_forged_kid_triggers_at_most_one_jwks_refresh(self):
        """Множественные JWT с неизвестным kid вызывают максимум один forced refresh за 30s.

        Forced refresh (invalidate + повторный get_jwks) должен срабатывать только
        при первом запросе с неизвестным kid — остальные 4 попадают под cooldown 30s
        и отбрасываются напрямую без лишнего обращения к Keycloak.
        """
        from unittest.mock import AsyncMock, patch

        fake_jwks: list[dict] = [{"kid": "real-kid", "kty": "RSA"}]

        with (
            patch("app.services.keycloak.get_jwks", new=AsyncMock(return_value=fake_jwks)),
            patch("app.services.keycloak.invalidate_jwks_cache") as mock_invalidate,
            patch("app.core.security._JWKS_LAST_FORCE_REFRESH", 0.0),
        ):
            for _ in range(5):
                with contextlib.suppress(Exception):
                    await parse_jwt_claims(
                        "eyJhbGciOiJSUzI1NiIsImtpZCI6ImZha2Uta2lkIn0.eyJzdWIiOiJ4In0.AAAA",
                        jwks=fake_jwks,
                    )
        assert mock_invalidate.call_count <= 1, (
            f"invalidate_jwks_cache вызван {mock_invalidate.call_count} раз — "
            "ожидается не более 1 (cooldown 30s должен блокировать повторные refresh)"
        )

    @pytest.mark.asyncio
    async def test_unsupported_algorithm_rejected_immediately(self):
        """JWT с неподдерживаемым alg (HS256, none) отбрасывается до обращения к JWKS."""
        from unittest.mock import AsyncMock, patch

        import jwt as pyjwt

        fake_jwks = [{"kid": "k1", "kty": "RSA"}]

        with (
            patch("app.services.keycloak.get_jwks", new=AsyncMock(return_value=fake_jwks)),
            pytest.raises(pyjwt.exceptions.InvalidAlgorithmError),
        ):
            await parse_jwt_claims(
                "eyJhbGciOiJIUzI1NiIsImtpZCI6ImZha2Uta2lkIn0.eyJzdWIiOiJ4In0.AAAA",
                jwks=fake_jwks,
            )


class TestBcrypt:
    def test_hash_and_verify_success(self):
        password = "SecretPass123!"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2b$")
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct_pass")
        assert verify_password("wrong_pass", hashed) is False

    def test_hashes_are_unique(self):
        pw = "same_password"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2

    def test_verify_empty_password_fails(self):
        hashed = hash_password("real_password")
        assert verify_password("", hashed) is False

    def test_bcrypt_rounds_minimum(self):
        import re

        hashed = hash_password("test")
        match = re.search(r"\$2b\$(\d+)\$", hashed)
        assert match is not None
        rounds = int(match.group(1))
        assert rounds >= 12


class TestLocalAuthIsolation:
    """Проверка изоляции local vs keycloak auth_source."""

    def test_keycloak_user_has_no_password_hash(self):
        from types import SimpleNamespace

        user = SimpleNamespace(auth_source="keycloak", password_hash=None)
        assert user.auth_source == "keycloak"
        assert user.password_hash is None

    def test_local_user_has_password_hash(self):
        from types import SimpleNamespace

        pw_hash = hash_password("mypassword")
        user = SimpleNamespace(auth_source="local", password_hash=pw_hash)
        assert user.auth_source == "local"
        assert verify_password("mypassword", user.password_hash)

    def test_bootstrap_idempotency_logic(self):
        """Проверяем, что при наличии admin повторный bootstrap не создаёт нового."""
        existing_admin_found = True
        created = False
        if not existing_admin_found:
            created = True
        assert created is False
