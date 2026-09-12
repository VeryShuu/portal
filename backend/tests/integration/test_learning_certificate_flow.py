"""Integration: сертификаты о прохождении (этап 2) — ленивая выдача за
полностью пройденный курс, повторная раздача, has_certificate в прогрессе,
403/404-ветки, отказ при недоступности screenshot-service.

Реальные PostgreSQL/Redis из тестового стека; render_pdf мокается —
screenshot-service в тестовый стек не входит.
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
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.learning import LearningCourse

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_learning_rows(redis_client):
    """Не оставлять следов в общей test-БД (см. test_learning_accounts_flow)."""
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
    for key in await redis_client.keys("session:sid-cert-*"):
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
                title="Курс сертификатов",
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
                    max_attempts=0,
                    shuffle_questions=False,
                    shuffle_answers=False,
                )
            )
            staff = User(
                email=f"cert-staff-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Сотрудник Сертификат",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(staff)
            admin = User(
                email=f"cert-admin-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Методист Сертификат",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(admin)
            await db.flush()
            db.add(LearningAdmin(user_id=admin.id))
            db.add(
                LearningCourseParticipant(
                    course_id=course.id,
                    user_id=staff.id,
                    display_name=staff.full_name,
                    email=staff.email,
                )
            )
            await db.commit()
            self.course = course
            self.material_id = material.id
            self.test_item_id = test_item.id
            self.staff_uid = staff.id
            self.admin_uid = admin.id


def _portal_client(app, sid: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://test", "Cookie": f"portal_session={sid}"},
        follow_redirects=False,
    )


async def _login(redis_client, sid: str, user_id: uuid.UUID) -> None:
    from app.services.session import save_session

    await save_session(redis_client, sid, {"user_id": str(user_id), "auth_source": "local"})


class TestCertificateFlow:
    async def test_lazy_issue_and_reuse(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        from app.services.learning import courses_service as cs_mod

        monkeypatch.setattr(cs_mod, "LEARNING_DATA_DIR", str(tmp_path))
        seed = _Seed()
        await seed.build(slug="cert-flow")
        assert seed.course is not None and seed.staff_uid is not None
        await _login(redis_client, "sid-cert-staff", seed.staff_uid)

        calls: list[str] = []

        async def fake_render_pdf(html: str) -> bytes:
            calls.append(html)
            return b"%PDF-1.4 fake-certificate"

        monkeypatch.setattr("app.core.pdf.render_pdf", fake_render_pdf)

        # До прохождения — 404
        app.state.redis = redis_client
        async with _portal_client(app, "sid-cert-staff") as ac:
            r = await ac.get("/api/v1/learning/me/courses/cert-flow/certificate")
            assert r.status_code == 404

            # Полное прохождение: материал + сданная попытка
            from app.core.database import AsyncSessionLocal
            from app.models.learning import LearningItemProgress, LearningTestAttempt

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

            r = await ac.get("/api/v1/learning/me/courses/cert-flow/certificate")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "application/pdf"
            assert r.content.startswith(b"%PDF-1.4")
            assert len(calls) == 1

            # Повторный запрос — тот же файл, повторного рендера нет
            r2 = await ac.get("/api/v1/learning/me/courses/cert-flow/certificate")
            assert r2.status_code == 200
            assert r2.content == r.content
            assert len(calls) == 1

        # PDF на диске по каноническому пути; одна строка сертификата
        from sqlalchemy import func, select

        from app.core.database import AsyncSessionLocal
        from app.models.learning import LearningCertificate

        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(select(func.count()).select_from(LearningCertificate))
            ).scalar_one()
            cert = (await db.execute(select(LearningCertificate).limit(1))).scalar_one()
            assert total == 1
            assert cert.serial.startswith("LC-")
            assert Path(cert.pdf_path).is_file()

        # Прогресс для методиста помечает has_certificate
        assert seed.admin_uid is not None
        await _login(redis_client, "sid-cert-admin", seed.admin_uid)
        async with _portal_client(app, "sid-cert-admin") as admin_ac:
            r = await admin_ac.get(f"/api/v1/learning/admin/courses/{seed.course.id}/progress")
            assert r.status_code == 200
            participants = r.json()["participants"]
            assert any(p["has_certificate"] for p in participants)

    async def test_render_failure_is_503(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        from app.services.learning import courses_service as cs_mod

        monkeypatch.setattr(cs_mod, "LEARNING_DATA_DIR", str(tmp_path))
        seed = _Seed()
        await seed.build(slug="cert-fail")
        assert seed.staff_uid is not None and seed.material_id is not None
        await _login(redis_client, "sid-cert-staff", seed.staff_uid)

        async def broken_render_pdf(html: str) -> bytes:
            raise RuntimeError("screenshot-service down")

        monkeypatch.setattr("app.core.pdf.render_pdf", broken_render_pdf)

        from app.core.database import AsyncSessionLocal
        from app.models.learning import LearningItemProgress, LearningTestAttempt

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

        app.state.redis = redis_client
        async with _portal_client(app, "sid-cert-staff") as ac:
            r = await ac.get("/api/v1/learning/me/courses/cert-fail/certificate")
            assert r.status_code == 503

        # Строки сертификата не осталось (PDF не удался — выдачи нет)
        from sqlalchemy import func, select

        from app.models.learning import LearningCertificate

        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(select(func.count()).select_from(LearningCertificate))
            ).scalar_one()
            assert total == 0

    async def test_submitted_failed_attempt_does_not_complete(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        """Сданная, но НЕ сданная (passed=False) попытка не даёт сертификат."""
        _enable_module(monkeypatch)
        from app.services.learning import courses_service as cs_mod

        monkeypatch.setattr(cs_mod, "LEARNING_DATA_DIR", str(tmp_path))
        seed = _Seed()
        await seed.build(slug="cert-failed")
        assert seed.staff_uid is not None and seed.test_item_id is not None
        await _login(redis_client, "sid-cert-staff", seed.staff_uid)

        async def no_render(html: str) -> bytes:  # pragma: no cover
            raise AssertionError("render не должен вызываться")

        monkeypatch.setattr("app.core.pdf.render_pdf", no_render)

        from app.core.database import AsyncSessionLocal
        from app.models.learning import LearningTestAttempt

        async with AsyncSessionLocal() as db:
            db.add(
                LearningTestAttempt(
                    test_item_id=seed.test_item_id,
                    user_id=seed.staff_uid,
                    submitted_at=datetime.now(UTC),
                    score=0,
                    passed=False,
                )
            )
            await db.commit()

        app.state.redis = redis_client
        async with _portal_client(app, "sid-cert-staff") as ac:
            r = await ac.get("/api/v1/learning/me/courses/cert-failed/certificate")
            assert r.status_code == 404
