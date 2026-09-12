"""Integration: обложки курсов (этап 2, ТЗ §6.2) — загрузка методистом,
раздача с проверками прав обоим контурам участников, удаление.

Реальные PostgreSQL/Redis из тестового стека (scripts/test-integration.sh).
Файловые операции идут во временный каталог (LEARNING_DATA_DIR подменяется),
БД-строки курсов/участников после теста удаляются общим cleanup'ом.
"""

from __future__ import annotations

import contextlib
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.learning import LearningCourse
from app.services.learning import courses_service as cs

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
        await db.execute(text("DELETE FROM learning_courses"))
        await db.execute(text("DELETE FROM learning_course_participants"))
        await db.execute(text("DELETE FROM learning_admins"))
        await db.execute(text("DELETE FROM learning_accounts WHERE email LIKE '%@example.com'"))
        await db.commit()
    for prefix in ("learning_session:", "learning_sessions:"):
        for key in await redis_client.keys(f"{prefix}*"):
            await redis_client.delete(key)
    for key in await redis_client.keys("session:sid-cover-*"):
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
    """Реальный fastapi-limiter поверх тестового redis (как в attempts_flow)."""
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


def _png_bytes(width: int = 1600, height: int = 400) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 10, 10)).save(buf, "PNG")
    return buf.getvalue()


def _portal_client(app, sid: str, *, xsrf: str | None = None) -> AsyncClient:
    cookie = f"portal_session={sid}; XSRF-TOKEN=xsrf-cover"
    headers = {"Origin": "http://test", "Cookie": cookie}
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
        follow_redirects=False,
    )


def _learner_client(app, sid: str, *, xsrf: str | None = None) -> AsyncClient:
    cookie = f"learning_session={sid}; XSRF-TOKEN=xsrf-cover"
    headers = {"Origin": "http://test", "Cookie": cookie}
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
        follow_redirects=False,
    )


class _Seed:
    """Публикуемый курс + методист + двое сотрудников (участник и посторонний)."""

    def __init__(self):
        self.course: LearningCourse | None = None
        self.admin_uid: uuid.UUID | None = None
        self.staff_uid: uuid.UUID | None = None
        self.outsider_uid: uuid.UUID | None = None

    async def build(self, *, slug: str, status_: str = "published") -> None:
        from app.models.learning import LearningAdmin
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            self.course = LearningCourse(
                slug=slug,
                title="Курс обложек",
                status=status_,
                published_at=datetime.now(UTC) if status_ == "published" else None,
            )
            db.add(self.course)
            admin = User(
                email=f"cover-admin-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Методист Обложек",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(admin)
            await db.flush()
            db.add(LearningAdmin(user_id=admin.id))
            staff = User(
                email=f"cover-staff-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Сотрудник Обложек",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(staff)
            outsider = User(
                email=f"cover-outsider-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Посторонний Сотрудник",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(outsider)
            await db.commit()
            self.admin_uid = admin.id
            self.staff_uid = staff.id
            self.outsider_uid = outsider.id

    async def enroll_staff(self):
        from app.models.learning import LearningCourseParticipant

        async with AsyncSessionLocal() as db:
            db.add(
                LearningCourseParticipant(
                    course_id=self.course.id,
                    user_id=self.staff_uid,
                    display_name="Сотрудник Обложек",
                    email=f"cover-staff-{uuid.uuid4().hex[:8]}@example.com",
                )
            )
            await db.commit()


async def _login_admin(app, redis_client, admin_uid: uuid.UUID) -> None:
    from app.services.session import save_session

    await save_session(
        redis_client, "sid-cover-admin", {"user_id": str(admin_uid), "auth_source": "local"}
    )


class TestCoverAdminFlow:
    async def test_upload_serve_delete_roundtrip(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        seed = _Seed()
        await seed.build(slug="cover-roundtrip")
        assert seed.course is not None and seed.admin_uid is not None
        await _login_admin(app, redis_client, seed.admin_uid)

        app.state.redis = redis_client
        async with _portal_client(app, "sid-cover-admin", xsrf="xsrf-cover") as ac:
            # upload → cover_url, путь в ответе не светится
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{seed.course.id}/cover",
                files={"file": ("cover.png", _png_bytes(), "image/png")},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["cover_url"].startswith(
                f"/api/v1/learning/admin/courses/{seed.course.id}/cover?v="
            )
            assert "cover_path" not in body

            preview = Path(cs.LEARNING_DATA_DIR) / "covers" / f"{seed.course.id}.webp"
            assert preview.is_file()
            with Image.open(preview) as img:
                assert img.format == "WEBP" and img.width <= 1200

            # GET админом — то самое превью
            r = await ac.get(f"/api/v1/learning/admin/courses/{seed.course.id}/cover")
            assert r.status_code == 200
            assert r.headers["content-type"] == "image/webp"

            # DELETE → путь очищен, раздача 404
            r = await ac.delete(f"/api/v1/learning/admin/courses/{seed.course.id}/cover")
            assert r.status_code == 200
            assert r.json()["cover_url"] is None
            assert not preview.exists()
            r = await ac.get(f"/api/v1/learning/admin/courses/{seed.course.id}/cover")
            assert r.status_code == 404

            # несуществующий курс → 404 на обоих эндпоинтах
            missing = "00000000-0000-0000-0000-000000000000"
            missing_get = await ac.get(f"/api/v1/learning/admin/courses/{missing}/cover")
            assert missing_get.status_code == 404
            missing_del = await ac.delete(f"/api/v1/learning/admin/courses/{missing}/cover")
            assert missing_del.status_code == 404

    async def test_upload_requires_learning_admin(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        seed = _Seed()
        await seed.build(slug="cover-guard")
        assert seed.course is not None and seed.admin_uid is not None and seed.staff_uid is not None
        # Обычный сотрудник (не методист): 403 на загрузку и раздачу
        from app.services.session import save_session

        await save_session(
            redis_client,
            "sid-cover-admin",
            {"user_id": str(seed.staff_uid), "auth_source": "local"},
        )

        app.state.redis = redis_client
        async with _portal_client(app, "sid-cover-admin", xsrf="xsrf-cover") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{seed.course.id}/cover",
                files={"file": ("cover.png", _png_bytes(), "image/png")},
            )
            assert r.status_code == 403
            r = await ac.get(f"/api/v1/learning/admin/courses/{seed.course.id}/cover")
            assert r.status_code == 403

        # Методист, но не-изображение (magic не совпадает с заявленным) — 422
        await _login_admin(app, redis_client, seed.admin_uid)
        async with _portal_client(app, "sid-cover-admin", xsrf="xsrf-cover") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{seed.course.id}/cover",
                files={"file": ("cover.png", b"not an image at all", "image/png")},
            )
            assert r.status_code == 422


class TestCoverLearnerAccess:
    """Раздача участникам: сотрудник через портал-сессию, внешняя учётка через
    learner-cookie; не-участник и черновик — одинаковый 404 (анти-перечисление)."""

    async def test_enrolled_see_cover_others_do_not(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        from app.models.learning import LearningAccount, LearningCourseParticipant
        from app.services.learning.sessions import build_login_payload
        from app.services.learning.sessions import save_session as save_learner
        from app.services.session import save_session as save_portal

        seed = _Seed()
        await seed.build(slug="cover-learner")
        assert (
            seed.course is not None and seed.admin_uid is not None and seed.outsider_uid is not None
        )
        await seed.enroll_staff()
        await _login_admin(app, redis_client, seed.admin_uid)
        await save_portal(
            redis_client,
            "sid-cover-outsider",
            {"user_id": str(seed.outsider_uid), "auth_source": "local"},
        )

        app.state.redis = redis_client
        async with _portal_client(app, "sid-cover-admin", xsrf="xsrf-cover") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{seed.course.id}/cover",
                files={"file": ("cover.png", _png_bytes(), "image/png")},
            )
            assert r.status_code == 200

        # Участник-сотрудник: обложка доступна, cover_url в «моих курсах»
        await save_portal(
            redis_client,
            "sid-cover-staff",
            {"user_id": str(seed.staff_uid), "auth_source": "local"},
        )
        async with _portal_client(app, "sid-cover-staff") as staff_ac:
            r = await staff_ac.get("/api/v1/learning/me/courses/cover-learner/cover")
            assert r.status_code == 200
            assert r.headers["content-type"] == "image/webp"
            r = await staff_ac.get("/api/v1/learning/me/courses")
            mine = next(c for c in r.json() if c["slug"] == "cover-learner")
            assert mine["cover_url"] is not None
            assert mine["cover_url"].startswith(
                "/api/v1/learning/me/courses/cover-learner/cover?v="
            )

        # Не-участник-сотрудник — 404
        async with _portal_client(app, "sid-cover-outsider") as out_ac:
            r = await out_ac.get("/api/v1/learning/me/courses/cover-learner/cover")
            assert r.status_code == 404

        # Внешняя учётка: зачисленная видит, незачисленная — 404
        async with AsyncSessionLocal() as db:
            enrolled_acc = LearningAccount(
                email=f"cover-l-en-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Внешний Участник",
            )
            stranger_acc = LearningAccount(
                email=f"cover-l-str-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Внешний Чужой",
            )
            db.add_all([enrolled_acc, stranger_acc])
            await db.flush()
            db.add(
                LearningCourseParticipant(
                    course_id=seed.course.id,
                    learning_account_id=enrolled_acc.id,
                    display_name=enrolled_acc.full_name,
                    email=enrolled_acc.email,
                )
            )
            await db.commit()
            enrolled_id, stranger_id = enrolled_acc.id, stranger_acc.id

        await save_learner(
            redis_client,
            "sid-cover-learner",
            str(enrolled_id),
            build_login_payload(str(enrolled_id)),
        )
        await save_learner(
            redis_client,
            "sid-cover-stranger",
            str(stranger_id),
            build_login_payload(str(stranger_id)),
        )
        async with _learner_client(app, "sid-cover-learner") as lc:
            r = await lc.get("/api/v1/learning/me/courses/cover-learner/cover")
            assert r.status_code == 200
            assert r.headers["content-type"] == "image/webp"
        async with _learner_client(app, "sid-cover-stranger") as lc:
            r = await lc.get("/api/v1/learning/me/courses/cover-learner/cover")
            assert r.status_code == 404

    async def test_draft_course_cover_hidden_from_learner(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        from app.services.session import save_session as save_portal

        seed = _Seed()
        await seed.build(slug="cover-draft", status_="draft")
        assert seed.course is not None and seed.admin_uid is not None
        await seed.enroll_staff()
        await _login_admin(app, redis_client, seed.admin_uid)

        app.state.redis = redis_client
        async with _portal_client(app, "sid-cover-admin", xsrf="xsrf-cover") as ac:
            r = await ac.post(
                f"/api/v1/learning/admin/courses/{seed.course.id}/cover",
                files={"file": ("cover.png", _png_bytes(), "image/png")},
            )
            assert r.status_code == 200

        # Участнику черновик недоступен целиком — и обложка тоже
        await save_portal(
            redis_client,
            "sid-cover-staff",
            {"user_id": str(seed.staff_uid), "auth_source": "local"},
        )
        async with _portal_client(app, "sid-cover-staff") as staff_ac:
            r = await staff_ac.get("/api/v1/learning/me/courses/cover-draft/cover")
            assert r.status_code == 404
            r = await staff_ac.get("/api/v1/learning/me/courses")
            assert r.json() == []  # черновик не попадает в «мои курсы»

    async def test_course_without_cover_returns_404(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        from app.services.session import save_session as save_portal

        seed = _Seed()
        await seed.build(slug="cover-none")
        await seed.enroll_staff()
        await save_portal(
            redis_client,
            "sid-cover-staff",
            {"user_id": str(seed.staff_uid), "auth_source": "local"},
        )
        app.state.redis = redis_client
        async with _portal_client(app, "sid-cover-staff") as staff_ac:
            r = await staff_ac.get("/api/v1/learning/me/courses/cover-none/cover")
            assert r.status_code == 404
            mine = (await staff_ac.get("/api/v1/learning/me/courses")).json()
            assert mine and mine[0]["cover_url"] is None
