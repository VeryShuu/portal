"""Integration: таймер попытки (этап 2, §15) — серверный контроль времени:
просроченный submit → 409 + abandoned, лимит настраивается методистом,
settings round-trip. Реальные PostgreSQL/Redis из тестового стека."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.learning import LearningCourse

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
        await db.execute(text("DELETE FROM learning_certificates"))
        await db.execute(text("DELETE FROM learning_courses"))
        await db.execute(text("DELETE FROM learning_course_participants"))
        await db.execute(text("DELETE FROM learning_admins"))
        await db.execute(text("DELETE FROM learning_accounts WHERE email LIKE '%@example.com'"))
        await db.commit()
    for prefix in ("learning_session:", "learning_sessions:"):
        for key in await redis_client.keys(f"{prefix}*"):
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


class _Seed:
    """Опубликованный курс с тестом-вопросом и learner-учёткой в курсе."""

    def __init__(self):
        self.course: LearningCourse | None = None
        self.test_item_id: uuid.UUID | None = None
        self.question_id: uuid.UUID | None = None
        self.correct_option_id: uuid.UUID | None = None
        self.wrong_option_id: uuid.UUID | None = None
        self.account_id: uuid.UUID | None = None

    async def build(self, *, time_limit_minutes: int | None) -> None:
        from datetime import UTC, datetime

        from app.models.learning import (
            LearningAccount,
            LearningCourseItem,
            LearningCourseParticipant,
            LearningQuestion,
            LearningQuestionOption,
            LearningTest,
        )

        async with AsyncSessionLocal() as db:
            course = LearningCourse(
                slug=f"timer-{uuid.uuid4().hex[:8]}",
                title="Курс таймера",
                status="published",
                published_at=datetime.now(UTC),
            )
            db.add(course)
            await db.flush()
            item = LearningCourseItem(
                course_id=course.id, type="test", title="Тест на время", sort_order=0
            )
            db.add(item)
            await db.flush()
            db.add(
                LearningTest(
                    item_id=item.id,
                    pass_score=50,
                    max_attempts=0,
                    shuffle_questions=False,
                    shuffle_answers=False,
                    time_limit_minutes=time_limit_minutes,
                )
            )
            await db.flush()
            q = LearningQuestion(test_item_id=item.id, text="2+2?", multi=False, sort_order=0)
            db.add(q)
            await db.flush()
            ok = LearningQuestionOption(question_id=q.id, text="4", is_correct=True, sort_order=0)
            bad = LearningQuestionOption(question_id=q.id, text="5", is_correct=False, sort_order=1)
            db.add_all([ok, bad])
            acc = LearningAccount(
                email=f"timer-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Таймер Обучаемый",
            )
            db.add(acc)
            await db.flush()
            db.add(
                LearningCourseParticipant(
                    course_id=course.id,
                    learning_account_id=acc.id,
                    display_name=acc.full_name,
                    email=acc.email,
                )
            )
            await db.commit()
            self.course = course
            self.test_item_id = item.id
            self.question_id = q.id
            self.correct_option_id = ok.id
            self.wrong_option_id = bad.id
            self.account_id = acc.id

    async def add_open_attempt(self, *, minutes_ago: int) -> uuid.UUID:
        from app.models.learning import LearningTestAttempt

        started = datetime.now(UTC) - timedelta(minutes=minutes_ago)
        async with AsyncSessionLocal() as db:
            attempt = LearningTestAttempt(
                test_item_id=self.test_item_id,
                learning_account_id=self.account_id,
                started_at=started,
            )
            db.add(attempt)
            await db.commit()
            return attempt.id

    async def add_second_test_with_limit(
        self, *, time_limit_minutes: int, minutes_ago: int
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Второй тест в том же курсе для того же участника + открытая попытка.
        Нужен контрпримеру «таймер одного теста не трогает попытки других»."""
        from app.models.learning import LearningCourseItem, LearningTest, LearningTestAttempt

        started = datetime.now(UTC) - timedelta(minutes=minutes_ago)
        assert self.course is not None and self.account_id is not None
        async with AsyncSessionLocal() as db:
            item = LearningCourseItem(
                course_id=self.course.id, type="test", title="Второй тест", sort_order=1
            )
            db.add(item)
            await db.flush()
            db.add(
                LearningTest(
                    item_id=item.id,
                    pass_score=50,
                    max_attempts=0,
                    shuffle_questions=False,
                    shuffle_answers=False,
                    time_limit_minutes=time_limit_minutes,
                )
            )
            attempt = LearningTestAttempt(
                test_item_id=item.id,
                learning_account_id=self.account_id,
                started_at=started,
            )
            db.add(attempt)
            await db.commit()
            return item.id, attempt.id


def _learner_client(app, sid: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Origin": "http://test",
            "Cookie": f"learning_session={sid}; XSRF-TOKEN=xsrf-t",
            "X-XSRF-TOKEN": "xsrf-t",
        },
        follow_redirects=False,
    )


async def _login_learner(redis_client, account_id: uuid.UUID) -> None:
    from app.services.learning.sessions import build_login_payload, save_session

    await save_session(
        redis_client,
        "sid-timer-learner",
        str(account_id),
        build_login_payload(str(account_id)),
    )


class TestAttemptTimer:
    async def test_expired_submit_rejected_and_marked_abandoned(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build(time_limit_minutes=1)
        assert seed.account_id is not None and seed.correct_option_id is not None
        assert seed.test_item_id is not None and seed.question_id is not None
        await _login_learner(redis_client, seed.account_id)

        attempt_id = await seed.add_open_attempt(minutes_ago=5)

        app.state.redis = redis_client
        async with _learner_client(app, "sid-timer-learner") as ac:
            r = await ac.post(
                f"/api/v1/learning/me/attempts/{attempt_id}/submit",
                json={"answers": {str(seed.question_id): [str(seed.correct_option_id)]}},
            )
            assert r.status_code == 409, r.text
            assert "истекло" in r.json()["detail"]

        from sqlalchemy import select

        from app.models.learning import LearningTestAttempt

        async with AsyncSessionLocal() as db:
            attempt = (
                await db.execute(
                    select(LearningTestAttempt).where(LearningTestAttempt.id == attempt_id)
                )
            ).scalar_one()
            assert attempt.submitted_at is None
            assert attempt.abandoned_at is not None

        # Новая попытка доступна: просроченная не считалась отправленной
        async with _learner_client(app, "sid-timer-learner") as ac:
            r = await ac.get(f"/api/v1/learning/me/tests/{seed.test_item_id}/my-attempts")
            assert r.status_code == 200
            assert r.json()["submitted_count"] == 0

    async def test_timer_expired_attempt_freed_for_new_start(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        """Ревью 2026-08-30 (P1): попытка, просроченная по таймеру теста, не
        должна блокировать участника до общего 24-часового cutoff. Раньше
        повторный старт возвращал ту же просроченную попытку: UI запрещал
        submit, сервер отклонял 409 «начните новую» — а «новой» не было."""
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build(time_limit_minutes=30)
        assert seed.account_id is not None and seed.test_item_id is not None
        await _login_learner(redis_client, seed.account_id)

        # открытая попытка, начатая 60 минут назад при лимите 30 — просрочена
        expired_id = await seed.add_open_attempt(minutes_ago=60)

        app.state.redis = redis_client
        async with _learner_client(app, "sid-timer-learner") as ac:
            r = await ac.post(f"/api/v1/learning/me/tests/{seed.test_item_id}/attempts")
            assert r.status_code == 200, r.text
            new_id = r.json()["id"]
            assert new_id != str(expired_id), "старт вернул ту же просроченную попытку"

            # свежая попытка жизнеспособна: submit проходит
            assert seed.question_id is not None and seed.correct_option_id is not None
            r = await ac.post(
                f"/api/v1/learning/me/attempts/{new_id}/submit",
                json={"answers": {str(seed.question_id): [str(seed.correct_option_id)]}},
            )
            assert r.status_code == 200, r.text
            assert r.json()["passed"] is True

        from sqlalchemy import select

        from app.models.learning import LearningTestAttempt

        async with AsyncSessionLocal() as db:
            expired = (
                await db.execute(
                    select(LearningTestAttempt).where(LearningTestAttempt.id == expired_id)
                )
            ).scalar_one()
            assert expired.submitted_at is None
            assert expired.abandoned_at is not None

    async def test_timer_is_scoped_to_its_own_test(self):
        """Контрпример к UPDATE..FROM: просрочка по таймеру теста B не клеймит
        открытую попытку теста A того же участника (у A лимита нет, 24ч не
        прошло). Без JOIN-условия декартово произведение портило бы чужие
        попытки."""
        seed = _Seed()
        await seed.build(time_limit_minutes=None)
        assert seed.account_id is not None

        open_a = await seed.add_open_attempt(minutes_ago=60)
        _second_test_id, open_b = await seed.add_second_test_with_limit(
            time_limit_minutes=30, minutes_ago=60
        )

        from app.services.learning import tests_service as ts
        from app.services.learning.participant import LearningParticipant

        participant = LearningParticipant(kind="acc", learning_account_id=seed.account_id)
        async with AsyncSessionLocal() as db:
            marked = await ts.mark_stale_abandoned(db, participant)
            await db.commit()
        assert marked == 1, "клеймится только просроченная по СВОЕМУ таймеру попытка"

        from sqlalchemy import select

        from app.models.learning import LearningTestAttempt

        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(LearningTestAttempt).where(
                            LearningTestAttempt.id.in_([open_a, open_b])
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_id = {row.id: row for row in rows}
            assert by_id[open_b].abandoned_at is not None
            assert by_id[open_a].abandoned_at is None, (
                "таймер теста B заклеймил попытку теста A без лимита"
            )

    async def test_within_limit_submits_and_exposes_deadline(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build(time_limit_minutes=30)
        assert seed.account_id is not None and seed.correct_option_id is not None
        assert seed.test_item_id is not None and seed.question_id is not None
        await _login_learner(redis_client, seed.account_id)

        app.state.redis = redis_client
        async with _learner_client(app, "sid-timer-learner") as ac:
            r = await ac.post(f"/api/v1/learning/me/tests/{seed.test_item_id}/attempts")
            assert r.status_code == 200, r.text
            view = r.json()
            assert view["time_limit_minutes"] == 30
            assert view["expires_at"] is not None
            expires = datetime.fromisoformat(view["expires_at"])
            started = datetime.fromisoformat(view["started_at"])
            assert expires - started == timedelta(minutes=30)

            r = await ac.post(
                f"/api/v1/learning/me/attempts/{view['id']}/submit",
                json={"answers": {str(seed.question_id): [str(seed.correct_option_id)]}},
            )
            assert r.status_code == 200, r.text
            assert r.json()["passed"] is True

    async def test_settings_roundtrip_without_limit(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build(time_limit_minutes=None)
        assert seed.test_item_id is not None

        from app.services.session import save_session as save_portal

        seed_admin = await _mk_admin()
        await save_portal(
            redis_client,
            "sid-timer-admin",
            {"user_id": str(seed_admin), "auth_source": "local"},
        )
        await _login_learner(redis_client, seed.account_id)

        admin_client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "Origin": "http://test",
                "Cookie": "portal_session=sid-timer-admin; XSRF-TOKEN=xsrf-t",
                "X-XSRF-TOKEN": "xsrf-t",
            },
            follow_redirects=False,
        )
        app.state.redis = redis_client
        async with admin_client as ac:
            base = f"/api/v1/learning/admin/courses/items/{seed.test_item_id}/test"

            r = await ac.patch(base, json={"time_limit_minutes": 45})
            assert r.status_code == 200, r.text
            r = await ac.get(base)
            assert r.json()["time_limit_minutes"] == 45

            r = await ac.patch(base, json={"time_limit_minutes": None})
            assert r.status_code == 200
            r = await ac.get(base)
            assert r.json()["time_limit_minutes"] is None


async def _mk_admin() -> uuid.UUID:
    from app.models.learning import LearningAdmin
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        admin = User(
            email=f"timer-admin-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Методист Таймер",
            role="reader",
            auth_source="keycloak",
            current_status="working",
        )
        db.add(admin)
        await db.flush()
        db.add(LearningAdmin(user_id=admin.id))
        await db.commit()
        return admin.id
