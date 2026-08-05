"""
Тесты публичных endpoints справочника сотрудников.

Покрытие:
- GET /users/departments — список отделов (только авторизованные)
- GET /users/offices     — список офисов (только авторизованные)
- GET /users/export      — CSV-экспорт (только авторизованные)
- Расширения GET /users  — параметры office, sort
- Контроль доступа: 401 без авторизации
- Валидация query: некорректный sort → 422
- Порядок маршрутов: /departments, /offices, /export не парсятся
  как /{user_id} (UUID-валидация не выкидывает 422)

Используют моки без реального DB/Redis.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_db_user(
    user_id: uuid.UUID | None = None,
    full_name: str = "Иванов Иван",
    position: str | None = "Инженер",
    phone: str | None = "+7 999 123 45 67",
    department: str | None = "Разработка",
    attributes: dict | None = None,
):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"user-{uuid.uuid4().hex[:6]}@portal.local"
    u.full_name = full_name
    u.department = department
    u.position = position
    u.phone = phone
    u.role = "reader"
    u.auth_source = "local"
    u.avatar_url = None
    u.current_status = "working"
    u.current_status_until = None
    u.lang = "ru"
    u.notify_email = True
    u.notify_inapp = True
    u.preferences = {}
    u.attributes = attributes or {}
    u.keycloak_id = None
    u.created_at = "2024-01-01T00:00:00+00:00"
    u.updated_at = "2024-01-01T00:00:00+00:00"
    u.last_login_at = None
    u.birth_date = None
    u.gender = None
    return u


def _make_fake_db(
    *,
    users: list | None = None,
    scalars_results: list | None = None,
):
    """Фейковая async DB-сессия.

    ``users``: список объектов User для list_users_page (через scalars().all())
    ``scalars_results``: дополнительный per-call список результатов для scalars().all()
        (например, для list_departments / list_offices, которые делают select(distinct))
    """

    async def _fake_db():
        session = MagicMock()

        # Подготовим очередь результатов — каждый вызов execute() возвращает свой результат
        results_queue: list = []
        if scalars_results is not None:
            for items in scalars_results:
                r = MagicMock()
                r.scalar_one = MagicMock(return_value=len(items))
                r.scalar_one_or_none = MagicMock(return_value=None)
                r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
                results_queue.append(r)

        # Универсальный fallback (для users list_users_page + count_users)
        default = MagicMock()
        default.scalar_one = MagicMock(return_value=len(users or []))
        default.scalar_one_or_none = MagicMock(return_value=None)
        default.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=users or [])))

        async def execute_side_effect(*_args, **_kwargs):
            if results_queue:
                return results_queue.pop(0)
            return default

        session.execute = AsyncMock(side_effect=execute_side_effect)
        # для stream_users мы переопределяем напрямую через monkeypatching repo
        session.stream = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    return _fake_db


# ── /users/departments ──────────────────────────────────────────────────────
class TestListDepartments:
    async def test_unauthenticated_returns_401(self, client):
        r = await client.get("/api/v1/users/departments")
        assert r.status_code == 401

    async def test_returns_200_with_items(self, app, authed_client_factory):
        from app.api.deps import get_db

        depts = ["Бухгалтерия", "ИТ", "Маркетинг"]
        app.dependency_overrides[get_db] = _make_fake_db(scalars_results=[depts])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/departments")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["items"] == depts

    async def test_filters_empty_strings(self, app, authed_client_factory):
        """Репозиторий отфильтровывает None и пустые строки."""
        from app.api.deps import get_db

        # БД может вернуть None / "  " — repo фильтрует
        app.dependency_overrides[get_db] = _make_fake_db(scalars_results=[[None, "", "   ", "ИТ"]])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/departments")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        assert r.json()["items"] == ["ИТ"]

    async def test_route_does_not_collide_with_user_id(self, app, authed_client_factory):
        """`departments` не должно парситься как UUID и давать 422."""
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(scalars_results=[[]])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/departments")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200, (
            f"Маршрут /departments перехвачен /{{user_id}}? "
            f"status={r.status_code}, body={r.text[:200]}"
        )


# ── /users/offices ──────────────────────────────────────────────────────────
class TestListOffices:
    async def test_unauthenticated_returns_401(self, client):
        r = await client.get("/api/v1/users/offices")
        assert r.status_code == 401

    async def test_returns_200_with_items(self, app, authed_client_factory):
        from app.api.deps import get_db

        offices = ["Москва", "Мурманск"]
        app.dependency_overrides[get_db] = _make_fake_db(scalars_results=[offices])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/offices")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        assert r.json()["items"] == offices

    async def test_route_does_not_collide_with_user_id(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(scalars_results=[[]])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/offices")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200


# ── /users/export ───────────────────────────────────────────────────────────
class TestExportUsers:
    async def test_unauthenticated_returns_401(self, client):
        r = await client.get("/api/v1/users/export")
        assert r.status_code == 401

    async def test_invalid_sort_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/users/export", params={"sort": "bogus"})
        assert r.status_code == 422

    async def test_invalid_format_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/users/export", params={"format": "pdf"})
        assert r.status_code == 422

    async def test_returns_csv_with_bom_and_headers(self, app, authed_client_factory, monkeypatch):
        """Тело: BOM + заголовки + строки данных. Headers: text/csv + attachment."""
        from app.api.deps import get_db
        from app.api.users import users_repo

        users = [
            _make_db_user(
                full_name="Алексей Петров",
                position="Инженер",
                phone="+7 999 000 00 01",
                department="ИТ",
                attributes={"city": "Москва", "internal_phone": "312"},
            ),
            _make_db_user(
                full_name="Борис Сидоров",
                position=None,
                phone=None,
                department=None,
                attributes={},
            ),
        ]

        async def fake_stream(_db, **_kw):
            for u in users:
                yield u

        monkeypatch.setattr(users_repo, "stream_users", fake_stream)
        app.dependency_overrides[get_db] = _make_fake_db()
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/export")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "staff-" in cd and ".csv" in cd

        body = r.content.decode("utf-8")
        # BOM в начале для корректного открытия в Excel
        assert body.startswith("\ufeff"), "Тело должно начинаться с UTF-8 BOM"

        lines = body.lstrip("\ufeff").splitlines()
        assert lines[0] == (
            "full_name,position,department,office,internal_phone,mobile_phone,email"
        )
        # Алексей: всё заполнено. internal_phone = user.phone, mobile_phone из attributes
        assert "Алексей Петров" in lines[1]
        assert "Инженер" in lines[1]
        assert "ИТ" in lines[1]
        assert "Москва" in lines[1]
        assert "+7 999 000 00 01" in lines[1]
        # Борис: пустые поля → пустые ячейки, без падения
        assert lines[2].startswith("Борис Сидоров,,,,,,")

    async def test_route_does_not_collide_with_user_id(
        self, app, authed_client_factory, monkeypatch
    ):
        from app.api.deps import get_db
        from app.api.users import users_repo

        async def empty_stream(_db, **_kw):
            if False:
                yield  # pragma: no cover

        monkeypatch.setattr(users_repo, "stream_users", empty_stream)
        app.dependency_overrides[get_db] = _make_fake_db()
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/export")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200

    async def test_csv_injection_values_are_prefixed(self, app, authed_client_factory, monkeypatch):
        from app.api.deps import get_db
        from app.api.users import users_repo

        evil = _make_db_user(
            full_name="=cmd|'/c calc'!A0",
            position="@SUM(A1:A10)",
            phone="+12345",
            department="-bad",
            attributes={"city": "+Москва", "mobile": "\tmob"},
        )

        async def fake_stream(_db, **_kw):
            yield evil

        monkeypatch.setattr(users_repo, "stream_users", fake_stream)
        app.dependency_overrides[get_db] = _make_fake_db()
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users/export")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        body = r.content.decode("utf-8").lstrip("\ufeff")
        data_line = body.splitlines()[1]
        assert "'=cmd" in data_line
        assert "'@SUM(A1:A10)" in data_line
        assert "'-bad" in data_line
        assert "'+Москва" in data_line


# ── GET /users параметры office/sort ────────────────────────────────────────
class TestListUsersExtended:
    async def test_invalid_sort_returns_422(self, authed_client_factory):
        ac, _ = authed_client_factory(role="reader")
        r = await ac.get("/api/v1/users", params={"sort": "bogus"})
        assert r.status_code == 422

    async def test_accepts_office_and_sort_params(self, app, authed_client_factory):
        """Endpoint принимает новые query-параметры без 422."""
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(users=[])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get(
                "/api/v1/users",
                params={"office": "Москва", "sort": "department"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data

    async def test_include_hidden_for_non_admin_returns_403(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(users=[])
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get("/api/v1/users", params={"include_hidden": "true"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 403

    async def test_include_hidden_for_admin_returns_200(self, app, authed_client_factory):
        from app.api.deps import get_db

        app.dependency_overrides[get_db] = _make_fake_db(users=[])
        ac, _ = authed_client_factory(role="admin")
        try:
            r = await ac.get("/api/v1/users", params={"include_hidden": "true"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200

    async def test_office_param_passed_to_repo(self, app, authed_client_factory, monkeypatch):
        """Параметр `office` пробрасывается в репозиторий."""
        from app.api.deps import get_db
        from app.api.users import users_repo

        captured: dict = {}

        async def fake_count(_db, **kw):
            captured["count"] = kw
            return 0

        async def fake_list(_db, **kw):
            captured["list"] = kw
            return []

        monkeypatch.setattr(users_repo, "count_users", fake_count)
        monkeypatch.setattr(users_repo, "list_users_page", fake_list)

        app.dependency_overrides[get_db] = _make_fake_db()
        ac, _ = authed_client_factory(role="reader")
        try:
            r = await ac.get(
                "/api/v1/users",
                params={"office": "Мурманск", "sort": "department", "q": "ива"},
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        assert captured["count"]["office"] == "Мурманск"
        assert captured["count"]["q"] == "ива"
        assert captured["list"]["office"] == "Мурманск"
        assert captured["list"]["sort"] == "department"
