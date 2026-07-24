"""Integration: ротация сессии при ре-логине — защита от cascade между вкладками.

Воспроизводит плавающий продакшен-баг SSO login-loop (log 2026-07-22 14:05-14:10):
пользователь с несколькими вкладками/браузерами. Когда одна вкладка делает
OIDC-callback (ре-логин), она удаляла ``old_session_id`` из cookie — но в одном
браузере cookie одна на все вкладки, поэтому callback вкладки B убивал сессию,
созданную вкладкой A → 401 на следующий bootstrap A → новый login-loop.

Инварианты (см. ``rotate_session``):
  1. session_id всегда ротируется (anti-fixation) — новый логин = новый sid.
  2. Старый sid удаляется, ТОЛЬКО если он не принадлежит текущему (входящему)
     пользователю — защита от session fixation (подсунутая чужая cookie).
  3. Старый sid того же пользователя остаётся живым — соседние вкладки не падают.
"""

from __future__ import annotations

import pytest

from app.services.session import (
    SESSION_KEY_PREFIX,
    get_session,
    rotate_session,
    save_session,
)

pytestmark = pytest.mark.asyncio


async def test_rotate_session_returns_new_id_and_preserves_same_user_session(redis_client):
    """Ре-логин того же пользователя: старая сессия (вкладка A) остаётся живой.

    Это ядро фикса cascade: callback вкладки B (cookie=sidA) НЕ должен убивать
    sidA, потому что sidA принадлежит тому же user_id.
    """
    user_id = "user-1"
    sid_a = "session-tab-A"
    await save_session(
        redis_client,
        sid_a,
        {"user_id": user_id, "keycloak_id": "kc-1", "auth_source": "keycloak"},
    )
    assert await get_session(redis_client, sid_a) is not None

    new_session = {
        "user_id": user_id,
        "keycloak_id": "kc-1",
        "access_token": "fresh-at",
        "auth_source": "keycloak",
    }
    new_sid = await rotate_session(redis_client, old_session_id=sid_a, data=new_session)

    # Инвариант 1: session_id ротирован (anti-fixation).
    assert new_sid != sid_a

    # Инвариант 3: старая сессия того же юзера осталась жить (вкладка A работает).
    assert await get_session(redis_client, sid_a) is not None, (
        "same-user session must survive re-login of that user (cascade bug)"
    )

    # Новая сессия создана и доступна.
    fresh = await get_session(redis_client, new_sid)
    assert fresh is not None
    assert fresh["access_token"] == "fresh-at"


async def test_rotate_session_kills_foreign_session_fixation(redis_client):
    """Anti-fixation: sid из cookie, принадлежащий ДРУГОМУ юзеру, удаляется.

    Сценарий: злоумышленник украл cookie жертвы и подсунул свою (атакующий-2)
    в браузер жертвы до её входа. После логина жертвы (user-victim) sid
    атакующего должен быть убит — иначе атакующий сохранит доступ.
    """
    attacker_sid = "session-attacker"
    await save_session(
        redis_client,
        attacker_sid,
        {"user_id": "user-attacker", "auth_source": "keycloak"},
    )
    assert await get_session(redis_client, attacker_sid) is not None

    # Жертва логинится: в её cookie сидит attacker_sid (подсунутый).
    victim_session = {
        "user_id": "user-victim",
        "access_token": "victim-at",
        "auth_source": "keycloak",
    }
    new_sid = await rotate_session(redis_client, old_session_id=attacker_sid, data=victim_session)

    # Инвариант 2: чужая (фиксационная) сессия убита.
    assert await get_session(redis_client, attacker_sid) is None, (
        "foreign session (session fixation) must be invalidated on login"
    )

    # Новая сессия жертвы валидна.
    assert await get_session(redis_client, new_sid) is not None


async def test_rotate_session_without_old_cookie(redis_client):
    """Нет old_session_id (холодный старт, чистый браузер) — просто создаётся новый sid."""
    new_sid = await rotate_session(
        redis_client,
        old_session_id=None,
        data={"user_id": "u", "auth_source": "keycloak"},
    )
    assert await get_session(redis_client, new_sid) is not None


async def test_rotate_session_old_sid_unknown_is_noop_delete(redis_client):
    """old_session_id есть, но в Redis его нет (истёк/уже удалён) — молча, без ошибки."""
    # sid отсутствует в Redis — delete_session и так no-op, но проверяем, что
    # новый sid создаётся корректно.
    new_sid = await rotate_session(
        redis_client,
        old_session_id="ghost-session",
        data={"user_id": "u-new", "auth_source": "keycloak"},
    )
    assert await get_session(redis_client, new_sid) is not None
    # ghost-session так и не появился.
    assert await redis_client.exists(f"{SESSION_KEY_PREFIX}ghost-session") == 0


async def test_rotate_session_two_tabs_no_cascade(redis_client):
    """Полный сценарий cascade: две вкладки одного юзера делают callback подряд.

    До фикса: callback B убивал sidA → A падала в 401-loop.
    После фикса: обе сессии (sidA, sidB) остаются валидными.
    """
    user_id = "user-1"

    # Вкладка A: первый логин.
    sid_a = await rotate_session(
        redis_client,
        old_session_id=None,
        data={"user_id": user_id, "auth_source": "keycloak", "access_token": "at-a"},
    )

    # Вкладка B: второй логин того же юзера. В её cookie сейчас sid_a
    # (один браузер = одна cookie, поставленная вкладкой A).
    sid_b = await rotate_session(
        redis_client,
        old_session_id=sid_a,
        data={"user_id": user_id, "auth_source": "keycloak", "access_token": "at-b"},
    )

    assert sid_a != sid_b
    # Обе сессии живы — нет cascade.
    assert await get_session(redis_client, sid_a) is not None, "tab A session killed (cascade)"
    assert await get_session(redis_client, sid_b) is not None
