from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestGetFullNameAttrKeySa:
    async def test_returns_attr_key_when_found(self):
        from app.services.full_name_source import get_full_name_attr_key_sa

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = "display_name"
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_full_name_attr_key_sa(db)
        assert result == "display_name"

    async def test_returns_none_when_not_found(self):
        from app.services.full_name_source import get_full_name_attr_key_sa

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_full_name_attr_key_sa(db)
        assert result is None

    async def test_executes_query(self):
        from app.services.full_name_source import get_full_name_attr_key_sa

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=execute_result)

        await get_full_name_attr_key_sa(db)
        db.execute.assert_awaited_once()


class TestGetFullNameAttrKeyAsyncpg:
    async def test_returns_str_value(self):
        from app.services.full_name_source import get_full_name_attr_key_asyncpg

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value="preferred_name")

        result = await get_full_name_attr_key_asyncpg(conn)
        assert result == "preferred_name"

    async def test_returns_none_when_no_row(self):
        from app.services.full_name_source import get_full_name_attr_key_asyncpg

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=None)

        result = await get_full_name_attr_key_asyncpg(conn)
        assert result is None

    async def test_returns_none_for_non_string_value(self):
        from app.services.full_name_source import get_full_name_attr_key_asyncpg

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=42)

        result = await get_full_name_attr_key_asyncpg(conn)
        assert result is None

    async def test_executes_query(self):
        from app.services.full_name_source import get_full_name_attr_key_asyncpg

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=None)

        await get_full_name_attr_key_asyncpg(conn)
        conn.fetchval.assert_awaited_once()


class TestResolveFullName:
    def test_returns_default_when_attr_key_is_none(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default Name", {"display_name": "Other"}, None)
        assert result == "Default Name"

    def test_returns_default_when_attr_key_is_empty_string(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default Name", {"display_name": "Other"}, "")
        assert result == "Default Name"

    def test_returns_attr_value_when_found(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": "John Doe"}, "display_name")
        assert result == "John Doe"

    def test_strips_whitespace_from_value(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": "  John Doe  "}, "display_name")
        assert result == "John Doe"

    def test_returns_default_when_key_not_in_attrs(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {}, "display_name")
        assert result == "Default"

    def test_returns_default_when_value_is_empty_string(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": ""}, "display_name")
        assert result == "Default"

    def test_returns_default_when_value_is_whitespace_only(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": "   "}, "display_name")
        assert result == "Default"

    def test_handles_list_single_element(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": ["John Doe"]}, "display_name")
        assert result == "John Doe"

    def test_handles_list_empty_returns_default(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": []}, "display_name")
        assert result == "Default"

    def test_handles_non_string_value_returns_default(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": 42}, "display_name")
        assert result == "Default"

    def test_handles_none_value_returns_default(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": None}, "display_name")
        assert result == "Default"

    def test_list_with_whitespace_only_first_element_returns_default(self):
        from app.services.full_name_source import resolve_full_name

        result = resolve_full_name("Default", {"display_name": ["   "]}, "display_name")
        assert result == "Default"
