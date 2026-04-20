"""Unit-тесты: парсинг JWT claims, PKCE, маппинг пользователя."""
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
    parse_jwt_claims,
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
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
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


def test_parse_jwt_claims_invalid_token():
    from jose import JWTError
    with pytest.raises(Exception):
        parse_jwt_claims("not.a.valid.token", [{"kid": "k1"}])
