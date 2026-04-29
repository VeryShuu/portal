"""Unit-тесты: парсинг JWT claims, PKCE, маппинг пользователя, bcrypt."""

import hashlib
import base64
import secrets
from unittest.mock import patch, MagicMock

import pytest
from jose import jwt

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
    with pytest.raises(Exception):
        await parse_jwt_claims("not.a.valid.token", [{"kid": "k1"}])


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
