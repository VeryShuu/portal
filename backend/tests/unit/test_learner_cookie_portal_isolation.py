"""Явный тест §10.2 ТЗ: learner-cookie не проходит на штатный эндпоинт портала.

Изоляция пространств ключей Redis (``learning_session:*`` vs ``session:*``)
покрыта в ``test_learning_sessions.py`` на уровне сервиса; здесь — контракт
на уровне зависимости портала: идентификатор валидной learner-сессии,
подставленный в портал-cookie, не резолвится ни в какого пользователя (401).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_user
from app.services.learning import sessions as ls


class FakeRedis:
    """Async-двойник Redis: setex для записи learner-сессии сервисом,
    get для портального резолвера (до БД дело не доходит)."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def sadd(self, key: str, member: str) -> int:
        return 0  # индекс сессий аккаунта в этом тесте не проверяется

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


async def test_learner_session_id_in_portal_cookie_is_unauthorized():
    """Валидная learner-сессия существует в learning_session:*, но портал
    ищет session:<id> — промах, 401 «Session expired» (а не 500/чужой юзер)."""
    r = FakeRedis()
    payload = {"principal_type": "learning_account", "account_id": "a" * 32}
    sid = "learner-sid-123"
    await ls.save_session(r, sid, "acc-1", payload)
    # сессия реально сохранена в своём пространстве
    assert await ls.get_session_payload(r, sid) == payload

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            request=None,  # Request не используется до резолвера сессии
            redis=r,
            db=None,
            session_id=sid,
        )
    assert exc.value.status_code == 401


def _dep_of(fn, param: str):
    """FastAPI-зависимость параметра (Annotated[AsyncSession, Depends(...)]).

    inspect.signature вместо get_type_hints: возврат функции аннотирован
    TYPE_CHECKING-only строкой, eval которой в тестовом неймспейсе падает."""
    import inspect
    from typing import get_args

    ann = inspect.signature(fn).parameters[param].annotation
    if isinstance(ann, str):  # from __future__ import annotations в deps.py
        ann = eval(ann, fn.__globals__)
    deps = [a for a in get_args(ann) if a.__class__.__name__ == "Depends"]
    assert deps, f"параметр {param} без Depends"
    return deps[0].dependency


def test_learner_reads_go_through_learning_pool():
    """§10.8: принципал learner'а читает learning_accounts через learning-пул,
    а participant-деп несёт ОБА движка (learner — learning, staff — основной).
    Проводка фиксируется тестом: смена аннотации на основной пул роняет CI."""
    from app.api.deps import (
        get_current_learner,
        get_current_user,
        get_learning_db,
        get_learning_participant,
    )
    from app.core.database import get_db

    assert _dep_of(get_current_learner, "db") is get_learning_db

    assert (
        _dep_of(get_learning_participant, "db") is get_db
    )  # staff: users вне грантов learning_app
    assert _dep_of(get_learning_participant, "learning_db") is get_learning_db  # learner

    # контраст: портал-пользователь по-прежнему на основном пуле
    assert _dep_of(get_current_user, "db") is get_db
