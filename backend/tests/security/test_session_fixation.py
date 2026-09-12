"""Security test: session_id rotation on login (anti-fixation, 12.3.2).

Verifies that:
1. POST /auth/local/login issues a fresh session_id every time.
2. The old session_id is deleted from Redis after re-login.
3. An attacker who obtained the pre-login cookie cannot use it after login.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_local_user(email: str, password: str):
    """Build a minimal mock User for local-auth tests."""
    from app.core.security import hash_password

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.auth_source = "local"
    user.password_hash = hash_password(password)
    user.last_login_at = None
    user.deleted_at = None
    return user


def _make_db_override(user):
    """Return an async-generator dependency override that yields a mock session."""

    async def _fake_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=user)
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        yield session

    return _fake_db


async def _do_login(app, email: str, password: str, cookies: dict | None = None):
    """Helper: POST /auth/local/login via ASGITransport, return Response."""
    from httpx import ASGITransport, AsyncClient

    csrf_token = "test-csrf-token"
    all_cookies = {"XSRF-TOKEN": csrf_token}
    if cookies:
        all_cookies.update(cookies)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
        cookies=all_cookies,
    ) as ac:
        r = await ac.post(
            "/api/v1/auth/local/login",
            json={"email": email, "password": password},
        )
    return r


async def test_session_id_rotates_on_each_login(app, monkeypatch):
    """Two consecutive logins must produce different session_id cookies."""
    monkeypatch.setenv("LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")

    user = _make_local_user("alice@portal.local", "SecurePass123!")

    from app.core.database import get_db

    app.dependency_overrides[get_db] = _make_db_override(user)

    try:
        with patch("app.api.auth.local.push_audit_event", new_callable=AsyncMock):
            r1 = await _do_login(app, "alice@portal.local", "SecurePass123!")
            r2 = await _do_login(app, "alice@portal.local", "SecurePass123!")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r1.status_code == 200, f"First login failed: {r1.text}"
    assert r2.status_code == 200, f"Second login failed: {r2.text}"

    sid1 = r1.cookies.get("portal_session")
    sid2 = r2.cookies.get("portal_session")

    assert sid1 is not None, "First login did not set portal_session cookie"
    assert sid2 is not None, "Second login did not set portal_session cookie"
    assert sid1 != sid2, "Session ID was NOT rotated on second login (session fixation risk)"


async def test_old_session_invalidated_after_login(app, monkeypatch):
    """Anti-fixation: чужая (фиксационная) сессия в cookie инвалидируется при логине.

    Сценарий: атакующий украл cookie и подсунул её жертве до входа. После логина
    жертвы sid атакующего должен быть удалён — иначе атакующий сохранит доступ.

    Замечание о cascade (плавающий SSO login-loop, log 2026-07-22 14:05-14:10):
    раньше тест требовал удаления ЛЮБОЙ старой сессии, включая ту, что
    принадлежит тому же пользователю (повторный логин Bob → sid1 убивался).
    Это правильное поведение для чужой cookie, но для своей — оно и вызывало
    cascade: один браузер, одна cookie, повторный логин во 2-й вкладке убивал
    сессию 1-й → 401 → login-loop. Теперь ``rotate_session`` различает «чужая»
    (удаляем) и «своя» (оставляем). Здесь проверяем чужую.
    """
    pytest.importorskip("fakeredis")
    import fakeredis.aioredis as fakeredis_aio

    monkeypatch.setenv("LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")

    fake_redis = fakeredis_aio.FakeRedis(decode_responses=True)
    app.state.redis = fake_redis

    # Сессия ДРУГОГО (атакующего) пользователя, подсунутая в cookie жертвы.
    attacker_sid = "attacker-fixed-session"
    await fake_redis.set(
        f"session:{attacker_sid}",
        '{"user_id": "attacker-user-id", "auth_source": "local"}',
    )

    victim = _make_local_user("bob@portal.local", "AnotherPass456!")

    from app.core.database import get_db
    from app.core.security import SESSION_COOKIE_NAME
    from app.services.session import SESSION_KEY_PREFIX

    app.dependency_overrides[get_db] = _make_db_override(victim)

    try:
        with patch("app.api.auth.local.push_audit_event", new_callable=AsyncMock):
            r = await _do_login(
                app,
                "bob@portal.local",
                "AnotherPass456!",
                cookies={SESSION_COOKIE_NAME: attacker_sid},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    sid_victim = r.cookies.get(SESSION_COOKIE_NAME)
    assert sid_victim is not None, "Login did not set portal_session cookie"
    assert sid_victim != attacker_sid, "Session ID was NOT rotated (session fixation risk)"

    # Чужая (фиксационная) сессия убита — атакующий потерял доступ.
    attacker_exists = await fake_redis.exists(f"{SESSION_KEY_PREFIX}{attacker_sid}")
    assert attacker_exists == 0, "Foreign (fixation) session was NOT deleted after login"

    # Новая сессия жертвы валидна.
    victim_exists = await fake_redis.exists(f"{SESSION_KEY_PREFIX}{sid_victim}")
    assert victim_exists == 1, "New victim session key must exist in Redis"


async def test_same_user_session_survives_relogin(app, monkeypatch):
    """Re-login того же пользователя НЕ убивает его предыдущую сессию (cascade-fix).

    Сценарий cascade: одна вкладка залогинилась (sid1), вторая вкладка того же
    юзера в том же браузере делает повторный логин (cookie=sid1). Раньше sid1
    удалялся → первая вкладка падала в 401-loop. Теперь sid1 остаётся жить.
    """
    pytest.importorskip("fakeredis")
    import fakeredis.aioredis as fakeredis_aio

    monkeypatch.setenv("LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "development")

    fake_redis = fakeredis_aio.FakeRedis(decode_responses=True)
    app.state.redis = fake_redis

    user = _make_local_user("bob@portal.local", "AnotherPass456!")

    from app.core.database import get_db
    from app.core.security import SESSION_COOKIE_NAME
    from app.services.session import SESSION_KEY_PREFIX

    app.dependency_overrides[get_db] = _make_db_override(user)

    try:
        with patch("app.api.auth.local.push_audit_event", new_callable=AsyncMock):
            r1 = await _do_login(app, "bob@portal.local", "AnotherPass456!")

        sid1 = r1.cookies.get(SESSION_COOKIE_NAME)
        assert sid1 is not None

        # Второй логин того же юзера с cookie=sid1 (как из соседней вкладки).
        with patch("app.api.auth.local.push_audit_event", new_callable=AsyncMock):
            r2 = await _do_login(
                app,
                "bob@portal.local",
                "AnotherPass456!",
                cookies={SESSION_COOKIE_NAME: sid1},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    sid2 = r2.cookies.get(SESSION_COOKIE_NAME)
    assert sid2 is not None
    assert sid1 != sid2, "Session ID was NOT rotated (session fixation risk)"

    # КЛЮЧЕВОЙ инвариант cascade-фикса: первая сессия остаётся живой.
    sid1_exists = await fake_redis.exists(f"{SESSION_KEY_PREFIX}{sid1}")
    assert sid1_exists == 1, "Same-user session must survive re-login (cascade bug)"
    sid2_exists = await fake_redis.exists(f"{SESSION_KEY_PREFIX}{sid2}")
    assert sid2_exists == 1
