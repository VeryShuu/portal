"""Unit-тесты для ``GET /helpdesk/users/search`` (CC typeahead).

Endpoint stateless (только проксирует в Keycloak) — тестируем на уровне функции
роутера с замоканным ``search_users``, по образцу test_search.py. Валидация:
``<3 символов`` → пустой список (не 422 — n-select ломается на ошибке),
фильтрация пользователей без email, маппинг Keycloak-полей → ``HelpdeskUserOption``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.helpdesk.users import search_helpdesk_users
from app.schemas.helpdesk import HelpdeskUserOption


def _kc_user(
    *, uid: str, email: str | None, first: str = "", last: str = "", username: str = ""
) -> dict:
    return {"id": uid, "email": email, "firstName": first, "lastName": last, "username": username}


@pytest.mark.asyncio
class TestSearchHelpdeskUsers:
    async def test_maps_results_and_filters_no_email(self) -> None:
        """Пользователи с email → ``HelpdeskUserOption``; без email (сервисные
        аккаунты Keycloak) — отфильтрованы (бесполезны для CC)."""
        with patch(
            "app.services.keycloak.directory.search_users",
            new=AsyncMock(
                return_value=[
                    _kc_user(uid="u1", email="ivan@corp.local", first="Иван", last="Петров"),
                    _kc_user(uid="u2", email=None, username="svc-account"),
                    _kc_user(uid="u3", email="anna@corp.local", first="Anna"),
                ]
            ),
        ):
            result = await search_helpdesk_users(user=object(), redis=object(), q="анна")

        assert len(result) == 2
        assert result[0] == HelpdeskUserOption(
            user_id="u1", full_name="Иван Петров", email="ivan@corp.local"
        )
        # Без lastName — только firstName (без висячего пробела).
        assert result[1] == HelpdeskUserOption(
            user_id="u3", full_name="Anna", email="anna@corp.local"
        )

    async def test_short_query_returns_empty_list(self) -> None:
        """``<3 символов`` → ``[]`` (не 422): n-select на фронте покажет empty-state,
        422 ломал бы его обработку. Keycloak НЕ дёргается (ранний return)."""
        with patch(
            "app.services.keycloak.directory.search_users",
            new=AsyncMock(return_value=[_kc_user(uid="x", email="x@y.z")]),
        ) as kc:
            result = await search_helpdesk_users(user=object(), redis=object(), q="ab")
        assert result == []
        kc.assert_not_awaited()

    async def test_whitespace_short_returns_empty(self) -> None:
        """``strip()`` перед проверкой длины: ``\"  a  \"`` → 1 значащий символ → ``[]``."""
        with patch(
            "app.services.keycloak.directory.search_users", new=AsyncMock(return_value=[])
        ) as kc:
            result = await search_helpdesk_users(user=object(), redis=object(), q="  a  ")
        assert result == []
        kc.assert_not_awaited()

    async def test_falls_back_to_username_when_no_name(self) -> None:
        """Keycloak-аккаунт без firstName/lastName → ``full_name`` = ``username``
        (иначе карточка CC была бы пустой)."""
        with patch(
            "app.services.keycloak.directory.search_users",
            new=AsyncMock(
                return_value=[_kc_user(uid="u", email="x@y.z", username="legacy.user")]
            ),
        ):
            result = await search_helpdesk_users(user=object(), redis=object(), q="legacy")
        assert result[0].full_name == "legacy.user"

    async def test_passes_limit_to_keycloak(self) -> None:
        """``limit`` прокидывается в ``search_users`` (чтобы не тянуть весь справочник)."""
        with patch(
            "app.services.keycloak.directory.search_users", new=AsyncMock(return_value=[])
        ) as kc:
            await search_helpdesk_users(user=object(), redis=object(), q="query", limit=42)
        kc.assert_awaited_once_with("query", max_results=42)

    async def test_propagates_keycloak_error(self) -> None:
        """Сбой Keycloak поднимается (не маскируется в пустой список) — симметрично
        meetings/participants.py (там тоже нет try/except). Фронт покажет
        ``cc.searchError``; в server-лог попадёт полный traceback. Если позже
        решим возвращать ``[]`` при сбое — изменить и этот тест."""
        with patch(
            "app.services.keycloak.directory.search_users",
            new=AsyncMock(side_effect=RuntimeError("kc down")),
        ), pytest.raises(RuntimeError, match="kc down"):
            await search_helpdesk_users(user=object(), redis=object(), q="query")
