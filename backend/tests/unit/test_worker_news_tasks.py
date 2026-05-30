"""Unit-тесты для app/worker/tasks/news.py.

Покрытие:
- _flatten_kc_attributes: пустой/невалидный вход; фильтрация LDAP_/KERBEROS_/Timestamp;
  unwrap single-element list; multi-element passthrough; пропуск None/"".
- publish_scheduled_news: пустой результат → 0; ненулевой → enqueue для каждой строки;
  всегда закрывает соединение.
- _enqueue_news_notifications: успешный enqueue; ошибка → swallowed.
- archive_expired_news: парсинг строки UPDATE 'UPDATE N'; невалидная строка → 0.
- sync_users_from_keycloak: happy path с 1 страницей; обработка disabled пользователей;
  fallback get_user_groups при пустом groups_map; запись sync_last_run в Redis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Импортируем заранее, чтобы patch("app.services.keycloak", ...) сработал.
import app.services.keycloak  # noqa: F401
from app.worker.tasks import news as news_task


class TestFlattenKcAttributes:
    def test_non_dict_returns_empty(self):
        assert news_task._flatten_kc_attributes("nope") == {}  # type: ignore[arg-type]
        assert news_task._flatten_kc_attributes(None) == {}  # type: ignore[arg-type]

    def test_drops_internal_attrs(self):
        raw = {
            "LDAP_ID": ["x"],
            "KERBEROS_PRINC": ["y"],
            "modifyTimestamp": ["t"],
            "department": ["IT"],
        }
        out = news_task._flatten_kc_attributes(raw)
        assert out == {"department": "IT"}

    def test_unwraps_single_and_keeps_multi(self):
        raw = {"a": ["one"], "b": ["x", "y"], "c": "scalar", "d": [None, ""]}
        out = news_task._flatten_kc_attributes(raw)
        assert out["a"] == "one"
        assert out["b"] == ["x", "y"]
        assert out["c"] == "scalar"
        assert "d" not in out

    def test_skips_non_str_keys(self):
        raw = {1: ["bad"], "ok": ["v"]}
        out = news_task._flatten_kc_attributes(raw)
        assert out == {"ok": "v"}


def _conn_mock(fetch_rows: list | None = None, execute_result: str = "UPDATE 0") -> MagicMock:
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=fetch_rows or [])
    conn.execute = AsyncMock(return_value=execute_result)
    conn.fetchval = AsyncMock(return_value=0)
    conn.close = AsyncMock()
    return conn


class TestPublishScheduledNews:
    @pytest.mark.asyncio
    async def test_no_rows_returns_zero(self):
        conn = _conn_mock([])
        with patch("asyncpg.connect", AsyncMock(return_value=conn)):
            count = await news_task.publish_scheduled_news({"redis": MagicMock()})
        assert count == 0
        conn.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueues_per_row(self):
        rows = [
            {"id": "n1", "title": "T1", "target_departments": ["IT"], "target_roles": None},
            {"id": "n2", "title": "T2", "target_departments": None, "target_roles": ["admin"]},
        ]
        conn = _conn_mock(rows)
        redis = MagicMock()
        redis.enqueue_job = AsyncMock()

        with patch("asyncpg.connect", AsyncMock(return_value=conn)):
            count = await news_task.publish_scheduled_news({"redis": redis})

        assert count == 2
        assert redis.enqueue_job.await_count == 2

    @pytest.mark.asyncio
    async def test_close_called_even_on_error(self):
        conn = _conn_mock()
        conn.fetch = AsyncMock(side_effect=RuntimeError("db"))
        with patch("asyncpg.connect", AsyncMock(return_value=conn)):
            with pytest.raises(RuntimeError):
                await news_task.publish_scheduled_news({"redis": MagicMock()})
        conn.close.assert_awaited_once()


class TestEnqueueNewsNotifications:
    @pytest.mark.asyncio
    async def test_success(self):
        redis = MagicMock()
        redis.enqueue_job = AsyncMock()
        await news_task._enqueue_news_notifications(
            {"redis": redis},
            news_id="n",
            news_title="t",
            target_departments=["IT"],
            target_roles=[],
        )
        redis.enqueue_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_swallows_errors(self):
        redis = MagicMock()
        redis.enqueue_job = AsyncMock(side_effect=RuntimeError("redis"))
        # Не должна пробрасывать наружу
        await news_task._enqueue_news_notifications(
            {"redis": redis},
            news_id="n",
            news_title="t",
            target_departments=[],
            target_roles=[],
        )


class TestArchiveExpiredNews:
    @pytest.mark.asyncio
    async def test_parses_count_from_update_string(self):
        conn = _conn_mock(execute_result="UPDATE 5")
        with patch("asyncpg.connect", AsyncMock(return_value=conn)):
            count = await news_task.archive_expired_news({})
        assert count == 5

    @pytest.mark.asyncio
    async def test_unparseable_result_returns_zero(self):
        conn = _conn_mock(execute_result="weird")
        with patch("asyncpg.connect", AsyncMock(return_value=conn)):
            count = await news_task.archive_expired_news({})
        assert count == 0


class TestSyncUsersFromKeycloak:
    @pytest.mark.asyncio
    async def test_happy_path_one_page(self):
        conn = _conn_mock()
        conn.fetchval = AsyncMock(return_value=0)

        kc_users = [
            {
                "id": "kc-1",
                "email": "a@x",
                "firstName": "A",
                "lastName": "B",
                "username": "ab",
                "enabled": True,
                "attributes": {"department": ["IT"]},
            },
            {
                "id": "kc-2",
                "email": "c@x",
                "firstName": "",
                "lastName": "",
                "username": "cd",
                "enabled": False,  # disabled — пропускаем INSERT
                "attributes": {},
            },
        ]

        kc_service = MagicMock()
        kc_service.get_groups_members_map = AsyncMock(return_value={"kc-1": ["g1"]})
        kc_service.get_admin_users = AsyncMock(side_effect=[kc_users, []])
        kc_service.get_user_groups = AsyncMock(return_value=[])

        redis = MagicMock()
        redis.set = AsyncMock()

        with (
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
            patch("app.services.keycloak", kc_service),
            patch(
                "app.core.security.extract_user_data",
                side_effect=lambda c: {
                    "keycloak_id": c["sub"],
                    "email": c["email"],
                    "full_name": c["name"],
                    "department": c.get("department"),
                    "position": c.get("job_title"),
                    "phone": c.get("phone"),
                    "role": "user",
                    "keycloak_groups": c.get("groups", []),
                },
            ),
        ):
            count = await news_task.sync_users_from_keycloak({"redis": redis})

        # Только kc-1 INSERTed (kc-2 disabled).
        assert count == 1
        # 1 INSERT + 1 final UPDATE для soft-delete = >=1
        assert conn.execute.await_count >= 1
        redis.set.assert_awaited_once()
        conn.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_groups_bulk_failure_does_not_break(self):
        conn = _conn_mock()
        kc_service = MagicMock()
        kc_service.get_groups_members_map = AsyncMock(side_effect=RuntimeError("kc down"))
        kc_service.get_admin_users = AsyncMock(return_value=[])
        redis = MagicMock()
        redis.set = AsyncMock()

        with (
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
            patch("app.services.keycloak", kc_service),
        ):
            count = await news_task.sync_users_from_keycloak({"redis": redis})
        assert count == 0
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_records_error_status_in_redis_when_loop_fails(self):
        conn = _conn_mock()
        kc_service = MagicMock()
        kc_service.get_groups_members_map = AsyncMock(return_value={})
        kc_service.get_admin_users = AsyncMock(side_effect=RuntimeError("kc fail"))
        redis = MagicMock()
        redis.set = AsyncMock()

        with (
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
            patch("app.services.keycloak", kc_service),
        ):
            count = await news_task.sync_users_from_keycloak({"redis": redis})
        assert count == 0
        # Snapshot записан со status=error
        payload = redis.set.await_args.args[1]
        assert '"status": "error"' in payload
