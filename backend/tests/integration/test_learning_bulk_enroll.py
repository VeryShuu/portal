"""Integration: групповое зачисление сотрудников (этап 2, §15) — дубли
пропускаются, письма зачисления в той же транзакции, 403/лимиты."""

from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from app.core.database import AsyncSessionLocal
from app.models.email_outbox import EmailOutbox
from app.models.learning import LearningCourse, LearningCourseParticipant
from app.models.user import User

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_learning_rows(redis_client):
    yield

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM email_outbox WHERE kind = 'learning'"))
        await db.execute(text("DELETE FROM learning_item_progress"))
        await db.execute(text("DELETE FROM learning_test_attempts"))
        await db.execute(text("DELETE FROM learning_question_options"))
        await db.execute(text("DELETE FROM learning_questions"))
        await db.execute(text("DELETE FROM learning_tests"))
        await db.execute(text("DELETE FROM learning_course_items"))
        await db.execute(text("DELETE FROM learning_courses"))
        await db.execute(text("DELETE FROM learning_course_participants"))
        await db.execute(text("DELETE FROM learning_admins"))
        await db.execute(text("DELETE FROM learning_accounts WHERE email LIKE '%@example.com'"))
        await db.commit()
    for prefix in ("learning_session:", "learning_sessions:"):
        for key in await redis_client.keys(f"{prefix}*"):
            await redis_client.delete(key)
    for key in await redis_client.keys("session:sid-bulk-*"):
        await redis_client.delete(key)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    import importlib

    import app.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest_asyncio.fixture
async def live_limiter(redis_client):
    from fastapi_limiter import FastAPILimiter
    from fastapi_limiter.depends import RateLimiter

    import tests.conftest as _root_conftest

    saved_call = RateLimiter.__call__
    if getattr(_root_conftest, "_real_rate_limiter_call", None) is not None:
        RateLimiter.__call__ = _root_conftest._real_rate_limiter_call  # type: ignore[method-assign]

    await FastAPILimiter.init(redis_client)
    try:
        yield redis_client
    finally:
        RateLimiter.__call__ = saved_call  # type: ignore[method-assign]
        with contextlib.suppress(Exception):
            await FastAPILimiter.close()


def _enable_module(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import modules_config

    async def fake_load(redis):
        return SimpleNamespace(learning=SimpleNamespace(enabled=True))

    monkeypatch.setattr(modules_config, "load_modules_shared", fake_load)


async def _seed(*, pre_enrolled: bool) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Курс + методист + 3 сотрудника (первый уже зачислен, если pre_enrolled)."""
    from app.models.learning import LearningAdmin, LearningCourseItem

    async with AsyncSessionLocal() as db:
        course = LearningCourse(
            slug=f"bulk-{uuid.uuid4().hex[:8]}",
            title="Курс группового зачисления",
            status="published",
        )
        db.add(course)
        await db.flush()
        db.add(
            LearningCourseItem(course_id=course.id, type="material", title="Материал", sort_order=0)
        )
        admin = User(
            email=f"bulk-admin-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Методист Масс",
            role="reader",
            auth_source="keycloak",
            current_status="working",
        )
        db.add(admin)
        await db.flush()
        db.add(LearningAdmin(user_id=admin.id))
        users: list[User] = []
        for i in range(3):
            u = User(
                email=f"bulk-staff-{i}-{uuid.uuid4().hex[:8]}@example.com",
                full_name=f"Сотрудник Масс {i}",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            users.append(u)
        await db.flush()
        if pre_enrolled:
            db.add(
                LearningCourseParticipant(
                    course_id=course.id,
                    user_id=users[0].id,
                    display_name=users[0].full_name,
                    email=users[0].email,
                )
            )
        await db.commit()
        return course.id, admin.id, [u.id for u in users]


def _client(app, sid: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Origin": "http://test",
            "Cookie": f"portal_session={sid}; XSRF-TOKEN=xsrf-bulk",
            "X-XSRF-TOKEN": "xsrf-bulk",
        },
        follow_redirects=False,
    )


async def _login(redis_client, sid: str, uid: uuid.UUID) -> None:
    from app.services.session import save_session

    await save_session(redis_client, sid, {"user_id": str(uid), "auth_source": "local"})


class TestBulkEnroll:
    async def test_bulk_skips_duplicates_and_reports(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        course_id, admin_uid, user_ids = await _seed(pre_enrolled=True)
        await _login(redis_client, "sid-bulk-admin", admin_uid)

        unknown = uuid.uuid4()
        app.state.redis = redis_client
        async with _client(app, "sid-bulk-admin") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{course_id}/participants/bulk",
                json={"user_ids": [str(u) for u in user_ids] + [str(unknown)]},
            )
            assert r.status_code == 201, r.text
            body = r.json()
            # первый уже зачислен, неизвестный — в errors
            assert body["enrolled"] == 2
            assert body["skipped_duplicates"] == 1
            assert len(body["errors"]) == 1
            assert body["errors"][0]["message"] == "Сотрудник не найден"

            # письма только новым участникам, в той же транзакции (outbox)
            async with AsyncSessionLocal() as db:
                letters = (
                    await db.execute(
                        select(func.count())
                        .select_from(EmailOutbox)
                        .where(EmailOutbox.kind == "learning")
                    )
                ).scalar_one()
                assert letters == 2
                participants = (
                    await db.execute(
                        select(func.count())
                        .select_from(LearningCourseParticipant)
                        .where(
                            LearningCourseParticipant.course_id == course_id,
                            LearningCourseParticipant.deleted_at.is_(None),
                        )
                    )
                ).scalar_one()
                assert participants == 3

        await redis_client.delete("session:sid-bulk-admin")

    async def test_rejects_over_limit_and_requires_admin(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        course_id, admin_uid, staff_ids = await _seed(pre_enrolled=False)
        # не методист — 403
        await _login(redis_client, "sid-bulk-admin", staff_ids[0])
        app.state.redis = redis_client
        async with _client(app, "sid-bulk-admin") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{course_id}/participants/bulk",
                json={"user_ids": [str(staff_ids[0])]},
            )
            assert r.status_code == 403

        # методист, но >100 id — 422
        await _login(redis_client, "sid-bulk-admin", admin_uid)
        many = [str(uuid.uuid4()) for _ in range(101)]
        async with _client(app, "sid-bulk-admin") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{course_id}/participants/bulk",
                json={"user_ids": many},
            )
            assert r.status_code == 422


class TestBulkEnrollRace:
    async def test_savepoint_conflict_becomes_error_not_500(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        """Ревью 2026-08-30: гонка с одиночным зачислением давала IntegrityError
        на commit роутера → 500. Savepoint превращает конфликт в строку отчёта,
        остальной батч и письма не страдают."""
        from app.services.learning import courses_service as cs

        course_id, _admin_uid, user_ids = await _seed(pre_enrolled=True)
        async with AsyncSessionLocal() as db:
            course = (
                await db.execute(select(LearningCourse).where(LearningCourse.id == course_id))
            ).scalar_one()
            staff = (await db.execute(select(User).where(User.id == user_ids[0]))).scalar_one()
            # user_ids[0] уже зачислен (_seed pre_enrolled=True) — предварительный
            # SELECT дублей в реальном флоу мог его не увидеть (гонка): helper
            # обязан вернуть конфликт, а не уронить транзакцию.
            conflict = await cs._enroll_one_savepoint(
                db,
                course,
                user_id=staff.id,
                user=SimpleNamespace(full_name=staff.full_name, email=staff.email),
                enrolled_by=None,
            )
            await db.rollback()
        assert conflict is not None
        assert "уже зачислен" in conflict.lower()

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(func.count())
                    .select_from(LearningCourseParticipant)
                    .where(
                        LearningCourseParticipant.course_id == course_id,
                        LearningCourseParticipant.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
            letters = (
                await db.execute(
                    select(func.count())
                    .select_from(EmailOutbox)
                    .where(EmailOutbox.kind == "learning")
                )
            ).scalar_one()
        assert rows == 1, "конфликтная вставка не должна оставить строку"
        assert letters == 0, "письмо при конфликте не должно уйти в outbox"
