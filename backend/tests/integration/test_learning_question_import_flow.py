"""Integration: xlsx-импорт вопросов теста (этап 2) — шаблон, предпросмотр,
импорт с отчётом по строкам, замок §15 при наличии попыток.

Реальные PostgreSQL/Redis из тестового стека (scripts/test-integration.sh).
"""

from __future__ import annotations

import contextlib
import io
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.models.learning import LearningCourse, LearningCourseItem, LearningTest

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
    for key in await redis_client.keys("session:sid-qimport-*"):
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
    """Черновик курса с заготовкой теста + методист."""

    def __init__(self):
        self.course: LearningCourse | None = None
        self.item: LearningCourseItem | None = None
        self.admin_uid: uuid.UUID | None = None

    async def build(self) -> None:
        from app.models.learning import LearningAdmin
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            self.course = LearningCourse(
                slug=f"qimport-{uuid.uuid4().hex[:8]}",
                title="Курс импорта вопросов",
                status="draft",
            )
            db.add(self.course)
            await db.flush()
            self.item = LearningCourseItem(
                course_id=self.course.id, type="test", title="Тест импорта", sort_order=0
            )
            db.add(self.item)
            await db.flush()
            db.add(
                LearningTest(
                    item_id=self.item.id,
                    pass_score=70,
                    max_attempts=3,
                    shuffle_questions=False,
                    shuffle_answers=False,
                )
            )
            admin = User(
                email=f"qimport-admin-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Методист Импорта",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(admin)
            await db.flush()
            db.add(LearningAdmin(user_id=admin.id))
            await db.commit()
            self.admin_uid = admin.id


def _client(app, sid: str = "sid-qimport-admin") -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Origin": "http://test",
            "Cookie": f"portal_session={sid}; XSRF-TOKEN=xsrf-qimport",
            "X-XSRF-TOKEN": "xsrf-qimport",
        },
        follow_redirects=False,
    )


def _xlsx(rows: list[tuple[Any, ...]], header: tuple[Any, ...] | None = None) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    from app.services.learning import question_import as qi

    ws.append(header or qi._QUESTION_HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


VALID_ROWS = [
    ("Вопрос про высоту?", "Да", "Нет", "", "", "A", ""),
    ("Выберите СИЗ:", "Каска", "Кроссовки", "Привязь", "", "A, C", "да"),
]


async def _login_admin(redis_client, admin_uid: uuid.UUID) -> None:
    from app.services.session import save_session

    await save_session(
        redis_client, "sid-qimport-admin", {"user_id": str(admin_uid), "auth_source": "local"}
    )


class TestQuestionsImportFlow:
    async def test_template_preview_import(
        self, app, redis_client, live_limiter, monkeypatch, tmp_path: Path
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build()
        assert seed.item is not None and seed.admin_uid is not None
        await _login_admin(redis_client, seed.admin_uid)

        from app.services.learning import question_import as qi

        app.state.redis = redis_client
        async with _client(app) as ac:
            base = f"/api/v1/learning/admin/courses/items/{seed.item.id}/questions"

            r = await ac.get(f"{base}/template")
            assert r.status_code == 200
            assert r.content[:2] == b"PK"
            assert "attachment" in r.headers.get("content-disposition", "")

            data = _xlsx(VALID_ROWS)
            r = await ac.post(
                f"{base}/import/preview",
                files={
                    "file": (
                        "questions.xlsx",
                        data,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert [q["text"] for q in body["questions"]] == [VALID_ROWS[0][0], VALID_ROWS[1][0]]
            assert body["errors"] == []
            assert body["questions"][1]["multi"] is True

            r = await ac.post(
                f"{base}/import",
                files={
                    "file": (
                        "questions.xlsx",
                        data,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
            assert r.status_code == 200, r.text
            assert r.json() == {"created": 2, "errors": []}

            # Вопросы реально в конфиге теста, с правильными флагами
            r = await ac.get(f"{base[: -len('/questions')]}/test")
            assert r.status_code == 200
            questions = r.json()["questions"]
            assert [q["text"] for q in questions] == [VALID_ROWS[0][0], VALID_ROWS[1][0]]
            assert questions[1]["multi"] is True
            # пустой вариант D в файл не попадает — вариантов 3
            assert [o["is_correct"] for o in questions[1]["options"]] == [True, False, True]

            # Разбор нетронутого шаблона — чисто (подсказка не ошибка)
            template = await ac.get(f"{base}/template")
            parsed = qi.parse_xlsx(template.content)
            assert parsed.questions == [] and parsed.errors == []

    async def test_import_reports_row_errors_and_skips_them(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build()
        assert seed.item is not None and seed.admin_uid is not None
        await _login_admin(redis_client, seed.admin_uid)

        app.state.redis = redis_client
        async with _client(app) as ac:
            base = f"/api/v1/learning/admin/courses/items/{seed.item.id}/questions"
            data = _xlsx(
                [
                    ("Хороший вопрос?", "Да", "Нет", "", "", "A", ""),
                    ("Плохой — два верных в single", "Да", "Нет", "", "", "A, B", ""),
                    ("Ещё хороший", "Белый", "Чёрный", "", "", "B", "да"),
                ]
            )
            r = await ac.post(
                f"{base}/import",
                files={"file": ("q.xlsx", data, "application/octet-stream")},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["created"] == 2
            assert len(body["errors"]) == 1
            assert body["errors"][0]["row"] == 3
            assert "ровно один" in body["errors"][0]["message"]

    async def test_lock_after_attempt_and_bad_file(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        from app.core.database import AsyncSessionLocal as SessionLocal
        from app.models.learning import LearningAccount, LearningTestAttempt

        seed = _Seed()
        await seed.build()
        assert seed.item is not None and seed.admin_uid is not None
        await _login_admin(redis_client, seed.admin_uid)

        # Попытка по тесту существует → замок §15
        async with SessionLocal() as db:
            acc = LearningAccount(
                email=f"qimport-lock-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Замок Обучаемый",
            )
            db.add(acc)
            await db.flush()
            db.add(LearningTestAttempt(test_item_id=seed.item.id, learning_account_id=acc.id))
            await db.commit()

        app.state.redis = redis_client
        async with _client(app) as ac:
            base = f"/api/v1/learning/admin/courses/items/{seed.item.id}/questions"
            data = _xlsx(VALID_ROWS)
            r = await ac.post(
                f"{base}/import",
                files={"file": ("q.xlsx", data, "application/octet-stream")},
            )
            assert r.status_code == 409
            assert "копией" in r.json()["detail"]

            # Битый файл — 422 целиком
            r = await ac.post(
                f"{base}/import",
                files={"file": ("q.xlsx", b"not a zip", "application/octet-stream")},
            )
            assert r.status_code == 422

    async def test_import_requires_learning_admin(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build()
        assert seed.item is not None

        from app.core.database import AsyncSessionLocal as SessionLocal
        from app.models.user import User
        from app.services.session import save_session

        async with SessionLocal() as db:
            stranger = User(
                email=f"qimport-stranger-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Не Методист",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(stranger)
            await db.commit()
            stranger_id = stranger.id

        await save_session(
            redis_client, "sid-qimport-admin", {"user_id": str(stranger_id), "auth_source": "local"}
        )
        app.state.redis = redis_client
        async with _client(app) as ac:
            r = await ac.get(
                f"/api/v1/learning/admin/courses/items/{seed.item.id}/questions/template"
            )
            assert r.status_code == 403

    async def test_template_and_preview_error_branches(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build()
        assert seed.item is not None and seed.admin_uid is not None

        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal as SessionLocal
        from app.models.learning import LearningCourseItem

        async with SessionLocal() as db:
            db.add(
                LearningCourseItem(
                    course_id=seed.course.id, type="material", title="Не тест", sort_order=1
                )
            )
            await db.commit()

        await _login_admin(redis_client, seed.admin_uid)
        app.state.redis = redis_client
        async with _client(app) as ac:
            # несуществующий элемент → 404
            r = await ac.get(
                "/api/v1/learning/admin/courses/items/"
                "00000000-0000-0000-0000-000000000000/questions/template"
            )
            assert r.status_code == 404

            # шаблон/предпросмотр для материала (не теста) → 422
            async with SessionLocal() as db:
                material = (
                    await db.execute(
                        select(LearningCourseItem).where(
                            LearningCourseItem.course_id == seed.course.id,
                            LearningCourseItem.type == "material",
                        )
                    )
                ).scalar_one()
                material_id = material.id
            r = await ac.get(
                f"/api/v1/learning/admin/courses/items/{material_id}/questions/template"
            )
            assert r.status_code == 422

            # предпросмотр битого файла → 422 (файл целиком не разбирается)
            r = await ac.post(
                f"/api/v1/learning/admin/courses/items/{seed.item.id}/questions/import/preview",
                files={"file": ("q.xlsx", b"garbage", "application/octet-stream")},
            )
            assert r.status_code == 422


class TestImportSizeCap:
    async def test_oversized_upload_rejected_before_ram(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        """Ревью 2026-08-30: тело читалось в память целиком, лимит 5МБ
        проверялся постфактум. Теперь кап применяется при чтении (413)."""
        _enable_module(monkeypatch)
        seed = _Seed()
        await seed.build()
        assert seed.item is not None and seed.admin_uid is not None
        await _login_admin(redis_client, seed.admin_uid)

        from app.services.learning import question_import as qi

        oversized = b"0" * (qi.MAX_IMPORT_BYTES + 1)
        app.state.redis = redis_client
        async with _client(app) as ac:
            base = f"/api/v1/learning/admin/courses/items/{seed.item.id}/questions"
            for endpoint in ("import/preview", "import"):
                r = await ac.post(
                    f"{base}/{endpoint}",
                    files={
                        "file": (
                            "questions.xlsx",
                            oversized,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )
                assert r.status_code == 413, (endpoint, r.status_code, r.text)
