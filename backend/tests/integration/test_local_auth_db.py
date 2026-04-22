"""Integration: локальная аутентификация через реальные PG + Redis."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models.user import User


pytestmark = pytest.mark.asyncio


async def test_bcrypt_roundtrip():
    """Pre-hash через SHA256+base64 + bcrypt должен корректно валидироваться."""
    pw = "S3cret!Long Password длинный"
    h = hash_password(pw)
    assert h.startswith("$2b$") or h.startswith("$2a$") or h.startswith("$2y$")
    assert verify_password(pw, h)
    assert not verify_password("wrong", h)


async def test_bcrypt_does_not_truncate_long_passwords():
    """SHA256 pre-hash снимает 72-байтовый лимит bcrypt."""
    a = "a" * 100
    b = "a" * 99 + "b"
    assert hash_password(a) != hash_password(b)
    assert verify_password(a, hash_password(a))
    assert not verify_password(a, hash_password(b))


async def test_local_user_persisted_with_hash(real_db_session):
    user = User(
        email=f"local-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Local User",
        role="reader",
        auth_source="local",
        password_hash=hash_password("MyPassword!1"),
    )
    real_db_session.add(user)
    await real_db_session.commit()

    fetched = (
        await real_db_session.execute(select(User).where(User.email == user.email))
    ).scalar_one()
    assert fetched.auth_source == "local"
    assert verify_password("MyPassword!1", fetched.password_hash)
    assert fetched.keycloak_id is None


async def test_email_unique_constraint(real_db_session):
    from sqlalchemy.exc import IntegrityError

    email = f"dup-{uuid.uuid4().hex[:8]}@portal.local"
    u1 = User(email=email, full_name="One", role="reader", auth_source="local")
    real_db_session.add(u1)
    await real_db_session.commit()

    u2 = User(email=email, full_name="Two", role="reader", auth_source="local")
    real_db_session.add(u2)
    with pytest.raises(IntegrityError):
        await real_db_session.commit()
    await real_db_session.rollback()


async def test_keycloak_id_can_be_null_for_local(real_db_session):
    """auth_source='local' допускает NULL keycloak_id (миграция 004)."""
    user = User(
        email=f"null-kc-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Local",
        role="reader",
        auth_source="local",
        keycloak_id=None,
    )
    real_db_session.add(user)
    await real_db_session.commit()
    assert user.id is not None
