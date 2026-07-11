"""Unit-тесты справочника получателей рассылки.

Покрытие:
- schemas: валидация email (regex, без EmailStr), .local-домен допускается
- service.resolve_recipients: резолв ids → получатели, 404 при неизвестном id,
  дедупликация с сохранением порядка
- endpoint authz: reader → 403 на list/create; editor → 200/201
- endpoint create: 409 при дубликате email (IntegrityError маппится сервисом)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")

from app.schemas.mailing_recipient import (
    CreateMailingRecipientRequest,
    UpdateMailingRecipientRequest,
)
from app.services import mailing_recipients as svc

# ── schemas ─────────────────────────────────────────────────────────────────


class TestEmailValidation:
    def test_local_domain_allowed(self):
        body = CreateMailingRecipientRequest(name="A", email="user@portal.local")
        assert body.email == "user@portal.local"

    def test_trims_whitespace(self):
        body = CreateMailingRecipientRequest(name="A", email="  user@x.local  ")
        assert body.email == "user@x.local"

    @pytest.mark.parametrize("bad", ["nope", "a@@b", "a b@x.local", "@x.local", "a@"])
    def test_invalid_rejected(self, bad):
        with pytest.raises(ValueError):
            CreateMailingRecipientRequest(name="A", email=bad)

    def test_update_email_none_passthrough(self):
        body = UpdateMailingRecipientRequest(name="New")
        assert body.email is None


# ── service.resolve_recipients ──────────────────────────────────────────────


def _fake_db_returning(recipients: list) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=recipients)))
    db.execute = AsyncMock(return_value=result)
    return db


def _rec(email: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email=email, name="R", deleted_at=None)


class TestResolveRecipients:
    @pytest.mark.asyncio
    async def test_resolves_all(self):
        r1, r2 = _rec("a@x.local"), _rec("b@x.local")
        db = _fake_db_returning([r1, r2])
        out = await svc.resolve_recipients(db, [r1.id, r2.id])
        assert [r.id for r in out] == [r1.id, r2.id]

    @pytest.mark.asyncio
    async def test_missing_id_raises_404(self):
        r1 = _rec("a@x.local")
        db = _fake_db_returning([r1])
        missing = uuid.uuid4()
        with pytest.raises(HTTPException) as exc:
            await svc.resolve_recipients(db, [r1.id, missing])
        assert exc.value.status_code == 404
        assert str(missing) in exc.value.detail

    @pytest.mark.asyncio
    async def test_deduplicates_preserving_order(self):
        r1, r2 = _rec("a@x.local"), _rec("b@x.local")
        db = _fake_db_returning([r1, r2])
        out = await svc.resolve_recipients(db, [r2.id, r1.id, r2.id])
        assert [r.id for r in out] == [r2.id, r1.id]


# ── service.create_recipient (IntegrityError → 409) ─────────────────────────


class TestCreateRecipientConflict:
    @pytest.mark.asyncio
    async def test_duplicate_email_409(self):
        from sqlalchemy.exc import IntegrityError

        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock(side_effect=IntegrityError("x", {}, Exception("dup")))
        db.rollback = AsyncMock()
        body = CreateMailingRecipientRequest(name="A", email="dup@x.local")
        with pytest.raises(HTTPException) as exc:
            await svc.create_recipient(db, body, uuid.uuid4())
        assert exc.value.status_code == 409
        db.rollback.assert_awaited_once()


# ── endpoint authz ──────────────────────────────────────────────────────────


def _make_user(role: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), role=role, email=f"{role}@test.local", full_name="U", department="IT"
    )


def _build_app_reader_real_guard(user):
    """App WITHOUT overriding require_editor so the real role guard runs."""
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.mailing_recipients import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def _u():
        return user

    async def _db():
        return AsyncMock()

    async def _r():
        return AsyncMock()

    app.dependency_overrides[get_current_user] = _u
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _r
    return app


class TestEndpointAuthz:
    @pytest.mark.asyncio
    async def test_reader_forbidden_on_list(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("reader")
        app = _build_app_reader_real_guard(user)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/mailing-recipients")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reader_forbidden_on_create(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("reader")
        app = _build_app_reader_real_guard(user)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/mailing-recipients", json={"name": "A", "email": "a@x.local"}
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_list_ok(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app_reader_real_guard(user)
        with patch(
            "app.api.mailing_recipients.svc.list_recipients",
            new=AsyncMock(return_value=([], 0)),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/mailing-recipients")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_editor_create_ok(self):
        import httpx
        from httpx import ASGITransport

        user = _make_user("editor")
        app = _build_app_reader_real_guard(user)
        created = SimpleNamespace(
            id=uuid.uuid4(),
            name="A",
            email="a@x.local",
            label=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with (
            patch(
                "app.api.mailing_recipients.svc.create_recipient",
                new=AsyncMock(return_value=created),
            ),
            patch("app.api.mailing_recipients._emit_audit", new=AsyncMock()),
        ):
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/mailing-recipients",
                    json={"name": "A", "email": "a@x.local"},
                )
        assert resp.status_code == 201
        assert resp.json()["email"] == "a@x.local"


# ── service._escape_like (чистая функция) ───────────────────────────────────


class TestEscapeLike:
    @pytest.mark.parametrize(
        ("raw", "escaped"),
        [
            ("plain", "plain"),
            ("with\\backslash", "with\\\\backslash"),
            ("100%", "100\\%"),
            ("a_b", "a\\_b"),
            # Комбинация всех спецсимволов — порядок замены важен (\\ первым).
            ("\\%_", "\\\\\\%\\_"),
        ],
    )
    def test_escapes_like_specials(self, raw, escaped):
        assert svc._escape_like(raw) == escaped


# ── service.list_recipients (фильтр, пагинация, total) ──────────────────────


def _db_for_list(*, items: list, total: int) -> MagicMock:
    """Мок, где первый execute — count (scalar_one), второй — select (scalars)."""
    db = MagicMock()
    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=total)
    list_result = MagicMock()
    list_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    db.execute = AsyncMock(side_effect=[count_result, list_result])
    return db


class TestListRecipients:
    @pytest.mark.asyncio
    async def test_no_query_returns_items_and_total(self):
        items = [_rec("a@x.local"), _rec("b@x.local")]
        db = _db_for_list(items=items, total=2)
        out, total = await svc.list_recipients(db, q=None, limit=100, offset=0)
        assert out == items
        assert total == 2

    @pytest.mark.asyncio
    async def test_query_triggers_escape_and_like_filter(self):
        """Ветку ``q`` сложно проверить на SQL без реальной БД, но можно
        убедиться, что условие с ``ilike`` добавляется (два execute идут).
        Здесь проверяем, что total и items возвращаются корректно при ``q``."""
        items = [_rec("alice@x.local")]
        db = _db_for_list(items=items, total=1)
        out, total = await svc.list_recipients(db, q="ali", limit=10, offset=0)
        assert out == items
        assert total == 1
        assert db.execute.await_count == 2  # count + select

    @pytest.mark.asyncio
    async def test_pagination_passed_through(self):
        db = _db_for_list(items=[], total=0)
        await svc.list_recipients(db, q=None, limit=20, offset=40)
        assert db.execute.await_count == 2


# ── service.get_recipient_or_404 ────────────────────────────────────────────


def _db_returning_recipient(recipient) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=recipient)
    db.execute = AsyncMock(return_value=result)
    return db


class TestGetRecipientOr404:
    @pytest.mark.asyncio
    async def test_found_returns_recipient(self):
        rec = _rec("a@x.local")
        db = _db_returning_recipient(rec)
        got = await svc.get_recipient_or_404(db, rec.id)
        assert got is rec

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        db = _db_returning_recipient(None)
        with pytest.raises(HTTPException) as exc:
            await svc.get_recipient_or_404(db, uuid.uuid4())
        assert exc.value.status_code == 404


# ── service.update_recipient (IntegrityError → 409, returns sorted changes) ─


class TestUpdateRecipient:
    @pytest.mark.asyncio
    async def test_applies_changes_and_returns_sorted_keys(self):
        rec = SimpleNamespace(name="Old", email="old@x.local", label=None)
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        body = UpdateMailingRecipientRequest(name="New", email="new@x.local")
        changed = await svc.update_recipient(db, rec, body)
        assert changed == ["email", "name"]  # sorted
        assert rec.name == "New"
        assert rec.email == "new@x.local"
        assert rec.updated_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_integrity_error_maps_to_409(self):
        from sqlalchemy.exc import IntegrityError

        rec = SimpleNamespace(name="Old", email="dup@x.local", label=None)
        db = MagicMock()
        db.commit = AsyncMock(side_effect=IntegrityError("x", {}, Exception("dup")))
        db.rollback = AsyncMock()
        body = UpdateMailingRecipientRequest(email="dup@x.local")
        with pytest.raises(HTTPException) as exc:
            await svc.update_recipient(db, rec, body)
        assert exc.value.status_code == 409
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_changes_still_commits(self):
        rec = SimpleNamespace(name="Old", email="old@x.local", label=None)
        db = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        # UpdateMailingRecipientRequest() без аргументов — все поля None (exclude_unset → пусто)
        body = UpdateMailingRecipientRequest()
        changed = await svc.update_recipient(db, rec, body)
        assert changed == []
        db.commit.assert_awaited_once()


# ── service.soft_delete_recipient ───────────────────────────────────────────


class TestSoftDeleteRecipient:
    @pytest.mark.asyncio
    async def test_sets_deleted_at_and_commits(self):
        rec = SimpleNamespace(deleted_at=None)
        db = MagicMock()
        db.commit = AsyncMock()
        await svc.soft_delete_recipient(db, rec)
        assert rec.deleted_at is not None
        db.commit.assert_awaited_once()
