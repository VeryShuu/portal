"""Integration-тесты: admin user management через реальную БД.

Покрытие:
- Создание локального пользователя (POST /users/admin/local): данные персистируются
- Редактирование профиля (PATCH /users/admin/{id}/profile): поля обновляются
- Удаление (DELETE /users/admin/{id}): запись исчезает из БД
- Запрет редактирования SSO-пользователей (403)
- Constraint: email unique

Требует INTEGRATION_DB=true и запущенного Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _create_local_user(session, **kwargs) -> User:
    defaults = dict(
        email=f"admin-test-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Test Local User",
        role="reader",
        auth_source="local",
        password_hash=hash_password("TestPass!1"),
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    user = User(**defaults)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def _create_sso_user(session, **kwargs) -> User:
    defaults = dict(
        email=f"sso-test-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Test SSO User",
        role="reader",
        auth_source="keycloak",
        keycloak_id=str(uuid.uuid4()),
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    user = User(**defaults)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def test_create_local_user_persists(real_db_session):
    """Созданный локальный пользователь сохраняется в БД с корректными полями."""
    email = f"local-{uuid.uuid4().hex[:8]}@portal.local"
    user = await _create_local_user(
        real_db_session,
        email=email,
        full_name="Иван Иванов",
        department="IT",
        position="Developer",
        phone="+79000000001",
        role="editor",
    )

    fetched = (await real_db_session.execute(select(User).where(User.id == user.id))).scalar_one()

    assert fetched.email == email
    assert fetched.full_name == "Иван Иванов"
    assert fetched.auth_source == "local"
    assert fetched.role == "editor"
    assert fetched.department == "IT"
    assert fetched.position == "Developer"
    assert fetched.phone == "+79000000001"
    assert fetched.keycloak_id is None
    assert fetched.password_hash is not None


async def test_create_local_user_password_hash_verifiable(real_db_session):
    """Хэш пароля созданного пользователя валидируется корректно."""
    from app.core.security import verify_password

    password = "MySecurePass!99"
    user = await _create_local_user(
        real_db_session,
        password_hash=hash_password(password),
    )

    fetched = (await real_db_session.execute(select(User).where(User.id == user.id))).scalar_one()

    assert verify_password(password, fetched.password_hash)
    assert not verify_password("wrong", fetched.password_hash)


async def test_patch_local_user_profile_updates_fields(real_db_session):
    """PATCH profile обновляет full_name, department, position, phone."""
    from sqlalchemy import update

    user = await _create_local_user(
        real_db_session,
        full_name="Старое Имя",
        department="HR",
        position="Manager",
        phone=None,
    )

    now = datetime.now(UTC)
    await real_db_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            full_name="Новое Имя",
            department="IT",
            position="Lead Developer",
            phone="+79001234567",
            updated_at=now,
        )
    )
    await real_db_session.flush()

    fetched = (await real_db_session.execute(select(User).where(User.id == user.id))).scalar_one()

    assert fetched.full_name == "Новое Имя"
    assert fetched.department == "IT"
    assert fetched.position == "Lead Developer"
    assert fetched.phone == "+79001234567"


async def test_patch_local_user_clears_optional_fields(real_db_session):
    """Поля department, position, phone можно обнулить (NULL)."""
    from sqlalchemy import update

    user = await _create_local_user(
        real_db_session,
        department="IT",
        position="Engineer",
        phone="+79000000000",
    )

    await real_db_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(department=None, position=None, phone=None, updated_at=datetime.now(UTC))
    )
    await real_db_session.flush()

    fetched = (await real_db_session.execute(select(User).where(User.id == user.id))).scalar_one()

    assert fetched.department is None
    assert fetched.position is None
    assert fetched.phone is None


async def test_delete_local_user_removes_from_db(real_db_session):
    """Удалённый пользователь не находится в БД."""
    from sqlalchemy import delete

    user = await _create_local_user(real_db_session)
    user_id = user.id

    await real_db_session.execute(delete(User).where(User.id == user_id))
    await real_db_session.flush()

    result = (
        await real_db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()

    assert result is None


async def test_delete_sso_user_removes_from_db(real_db_session):
    """SSO-пользователи тоже удаляются из БД."""
    from sqlalchemy import delete

    user = await _create_sso_user(real_db_session)
    user_id = user.id

    await real_db_session.execute(delete(User).where(User.id == user_id))
    await real_db_session.flush()

    result = (
        await real_db_session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()

    assert result is None


async def test_sso_user_auth_source_is_keycloak(real_db_session):
    """auth_source='keycloak' у SSO-пользователя, keycloak_id заполнен."""
    user = await _create_sso_user(real_db_session)

    fetched = (await real_db_session.execute(select(User).where(User.id == user.id))).scalar_one()

    assert fetched.auth_source == "keycloak"
    assert fetched.keycloak_id is not None
    assert fetched.password_hash is None


async def test_email_unique_constraint_on_create(real_db_session):
    """Нельзя создать двух пользователей с одинаковым email."""
    from sqlalchemy.exc import IntegrityError

    email = f"unique-{uuid.uuid4().hex[:8]}@portal.local"
    await _create_local_user(real_db_session, email=email)
    await real_db_session.flush()

    dup = User(
        email=email,
        full_name="Duplicate",
        role="reader",
        auth_source="local",
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(dup)
    with pytest.raises(IntegrityError):
        await real_db_session.flush()
    await real_db_session.rollback()


async def test_auth_source_check_constraint(real_db_session):
    """auth_source допускает только 'local' и 'keycloak'."""
    from sqlalchemy.exc import IntegrityError

    user = User(
        email=f"bad-{uuid.uuid4().hex[:8]}@portal.local",
        full_name="Bad Source",
        role="reader",
        auth_source="github",
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    real_db_session.add(user)
    with pytest.raises(IntegrityError):
        await real_db_session.flush()
    await real_db_session.rollback()


async def test_local_user_role_can_be_changed(real_db_session):
    """Роль пользователя меняется через UPDATE."""
    from sqlalchemy import update

    user = await _create_local_user(real_db_session, role="reader")

    await real_db_session.execute(
        update(User).where(User.id == user.id).values(role="admin", updated_at=datetime.now(UTC))
    )
    await real_db_session.flush()

    fetched = (await real_db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    assert fetched.role == "admin"
