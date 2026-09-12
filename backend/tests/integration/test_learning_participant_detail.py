"""Integration: панель участника у методиста — детализация статуса решения
курса, сброс попыток теста, скачивание/выпуск сертификата сотрудника.

Реальные PostgreSQL/Redis из тестового стека; render_pdf мокается —
screenshot-service в тестовый стек не входит (как в test_learning_certificate_flow).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.learning import LearningCourse

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_learning_rows(redis_client):
    """Не оставлять следов в общей test-БД (см. test_learning_certificate_flow)."""
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
    for key in await redis_client.keys("session:sid-pd-*"):
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
    """Опубликованный курс (материал + тест), зачисленный сотрудник, методист."""

    def __init__(self):
        self.course: LearningCourse | None = None
        self.material_id: uuid.UUID | None = None
        self.test_item_id: uuid.UUID | None = None
        self.staff_uid: uuid.UUID | None = None
        self.participant_id: uuid.UUID | None = None
        self.admin_uid: uuid.UUID | None = None

    async def build(self, *, slug: str) -> None:
        from datetime import UTC, datetime

        from app.models.learning import (
            LearningAdmin,
            LearningCourseItem,
            LearningCourseParticipant,
            LearningTest,
        )
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            course = LearningCourse(
                slug=slug,
                title="Курс панели участника",
                status="published",
                published_at=datetime.now(UTC),
            )
            db.add(course)
            await db.flush()
            material = LearningCourseItem(
                course_id=course.id, type="material", title="Материал", sort_order=0
            )
            test_item = LearningCourseItem(
                course_id=course.id, type="test", title="Тест", sort_order=1
            )
            db.add_all([material, test_item])
            await db.flush()
            db.add(
                LearningTest(
                    item_id=test_item.id,
                    pass_score=70,
                    max_attempts=1,
                    shuffle_questions=False,
                    shuffle_answers=False,
                )
            )
            staff = User(
                email=f"pd-staff-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Сотрудник Панель",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(staff)
            admin = User(
                email=f"pd-admin-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Методист Панель",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(admin)
            await db.flush()
            db.add(LearningAdmin(user_id=admin.id))
            participant = LearningCourseParticipant(
                course_id=course.id,
                user_id=staff.id,
                display_name=staff.full_name,
                email=staff.email,
            )
            db.add(participant)
            await db.commit()
            self.course = course
            self.material_id = material.id
            self.test_item_id = test_item.id
            self.staff_uid = staff.id
            self.participant_id = participant.id
            self.admin_uid = admin.id


def _portal_client(app, sid: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://test", "Cookie": f"portal_session={sid}"},
        follow_redirects=False,
    )


def _admin_client(app, sid: str) -> AsyncClient:
    """Клиент методиста; POST-запросы требуют CSRF-пару cookie+заголовок."""
    xsrf = "xsrf-pd"
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Origin": "http://test",
            "Cookie": f"portal_session={sid}; XSRF-TOKEN={xsrf}",
            "X-XSRF-TOKEN": xsrf,
        },
        follow_redirects=False,
    )


async def _login(redis_client, sid: str, user_id: uuid.UUID) -> None:
    from app.services.session import save_session

    await save_session(redis_client, sid, {"user_id": str(user_id), "auth_source": "local"})


async def _complete_course(seed: _Seed) -> None:
    """Материал «ознакомлен» + сданная попытка теста (passed)."""
    from app.models.learning import LearningItemProgress, LearningTestAttempt

    assert seed.material_id is not None and seed.test_item_id is not None
    async with AsyncSessionLocal() as db:
        db.add(LearningItemProgress(item_id=seed.material_id, user_id=seed.staff_uid))
        db.add(
            LearningTestAttempt(
                test_item_id=seed.test_item_id,
                user_id=seed.staff_uid,
                submitted_at=datetime.now(UTC),
                score=100,
                passed=True,
            )
        )
        await db.commit()


class TestParticipantItems:
    async def test_status_and_reset_flow(self, app, redis_client, live_limiter, monkeypatch):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build(slug="pd-status")
        assert seed.admin_uid is not None
        await _login(redis_client, "sid-pd-admin", seed.admin_uid)
        app.state.redis = redis_client

        async with _admin_client(app, "sid-pd-admin") as ac:
            # пустой прогресс: оба элемента не пройдены
            r = await ac.get(
                f"/api/v1/learning/admin/courses/{seed.course.id}"
                f"/participants/{seed.participant_id}/items"
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["participant_id"] == str(seed.participant_id)
            by_type = {i["type"]: i for i in body["items"]}
            assert by_type["material"]["completed"] is False
            assert by_type["test"]["completed"] is False
            assert by_type["test"]["attempts_submitted"] == 0

            # прохождение: материал + сданная попытка + брошенная попытка
            from app.models.learning import LearningItemProgress, LearningTestAttempt

            await _complete_course(seed)
            async with AsyncSessionLocal() as db:
                db.add(
                    LearningTestAttempt(
                        test_item_id=seed.test_item_id,
                        user_id=seed.staff_uid,
                        abandoned_at=datetime.now(UTC),
                    )
                )
                await db.commit()

            r = await ac.get(
                f"/api/v1/learning/admin/courses/{seed.course.id}"
                f"/participants/{seed.participant_id}/items"
            )
            by_type = {i["type"]: i for i in r.json()["items"]}
            assert by_type["material"]["completed"] is True
            assert by_type["test"]["completed"] is True
            assert by_type["test"]["test_passed"] is True
            # брошенная не считается: лимит считает только отправленные
            assert by_type["test"]["attempts_submitted"] == 1

            # сброс попыток теста
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{seed.course.id}"
                f"/participants/{seed.participant_id}"
                f"/items/{seed.test_item_id}/reset-attempts"
            )
            assert r.status_code == 200, r.text
            assert r.json() == {"ok": True, "deleted_attempts": 2}

            r = await ac.get(
                f"/api/v1/learning/admin/courses/{seed.course.id}"
                f"/participants/{seed.participant_id}/items"
            )
            by_type = {i["type"]: i for i in r.json()["items"]}
            assert by_type["test"]["completed"] is False
            assert by_type["test"]["attempts_submitted"] == 0
            # материал не затронут
            assert by_type["material"]["completed"] is True

        async with AsyncSessionLocal() as db:
            attempts = (
                await db.execute(
                    select(LearningTestAttempt).where(
                        LearningTestAttempt.test_item_id == seed.test_item_id
                    )
                )
            ).scalars()
            assert attempts.all() == []
            progress = (
                await db.execute(
                    select(LearningItemProgress).where(
                        LearningItemProgress.item_id == seed.test_item_id
                    )
                )
            ).scalars()
            assert progress.all() == []

        # сводный прогресс пересчитался: был 2/2, стал 1/2
        async with _admin_client(app, "sid-pd-admin") as ac:
            r = await ac.get(f"/api/v1/learning/admin/courses/{seed.course.id}/progress")
            participant = r.json()["participants"][0]
            assert participant["progress_completed"] == 1
            assert participant["progress_total"] == 2

    async def test_reset_validations(self, app, redis_client, live_limiter, monkeypatch):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build(slug="pd-reset-guards")
        assert seed.admin_uid is not None and seed.material_id is not None
        await _login(redis_client, "sid-pd-admin", seed.admin_uid)
        app.state.redis = redis_client

        async with _admin_client(app, "sid-pd-admin") as ac:
            base = f"/api/v1/learning/admin/courses/{seed.course.id}/participants"
            # материал сбрасывать нельзя — только тест
            r = await ac.post(
                f"{base}/{seed.participant_id}/items/{seed.material_id}/reset-attempts"
            )
            assert r.status_code == 404
            # неизвестный элемент
            r = await ac.post(f"{base}/{seed.participant_id}/items/{uuid.uuid4()}/reset-attempts")
            assert r.status_code == 404
            # неизвестный участник
            r = await ac.post(f"{base}/{uuid.uuid4()}/items/{seed.material_id}/reset-attempts")
            assert r.status_code == 404
            # детали неизвестного участника
            r = await ac.get(f"{base}/{uuid.uuid4()}/items")
            assert r.status_code == 404

    async def test_admin_certificate_issue_and_reuse(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        from app.services.learning import courses_service as cs_mod

        monkeypatch.setattr(cs_mod, "LEARNING_DATA_DIR", str(tmp_path))
        seed = _Seed()
        await seed.build(slug="pd-cert")
        assert seed.admin_uid is not None
        await _login(redis_client, "sid-pd-admin", seed.admin_uid)
        app.state.redis = redis_client

        calls: list[str] = []

        async def fake_render_pdf(html: str) -> bytes:
            calls.append(html)
            return b"%PDF-1.4 fake-admin-certificate"

        monkeypatch.setattr("app.core.pdf.render_pdf", fake_render_pdf)

        assert seed.course is not None and seed.participant_id is not None
        url = (
            f"/api/v1/learning/admin/courses/{seed.course.id}"
            f"/participants/{seed.participant_id}/certificate"
        )
        async with _admin_client(app, "sid-pd-admin") as ac:
            # курс не пройден — выпуск невозможен
            r = await ac.get(url)
            assert r.status_code == 404

            await _complete_course(seed)

            # методист первым запрашивает сертификат — он выпускается здесь
            r = await ac.get(url)
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "application/pdf"
            assert r.content.startswith(b"%PDF-1.4")
            assert len(calls) == 1

            # повторный запрос — тот же файл, без повторного рендера
            r2 = await ac.get(url)
            assert r2.status_code == 200
            assert r2.content == r.content
            assert len(calls) == 1

        # одна строка сертификата, PDF по каноническому пути
        from app.models.learning import LearningCertificate

        async with AsyncSessionLocal() as db:
            cert = (await db.execute(select(LearningCertificate))).scalars().all()
            assert len(cert) == 1
            assert cert[0].serial.startswith("LC-")
            assert Path(cert[0].pdf_path).is_file()

        # has_certificate виден в сводном прогрессе
        assert seed.course is not None
        async with _admin_client(app, "sid-pd-admin") as ac:
            r = await ac.get(f"/api/v1/learning/admin/courses/{seed.course.id}/progress")
            assert r.json()["participants"][0]["has_certificate"] is True
