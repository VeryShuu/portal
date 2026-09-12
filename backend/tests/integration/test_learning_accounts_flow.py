"""Integration: сквозные флоу модуля обучения (этап 1 — учётки и сессии).

Реальные PostgreSQL/Redis из тестового стека (scripts/test-integration.sh).
Покрывает: passwordless-вход (email → код из outbox-письма → verify → сессия);
политику попыток (5 неверных вводов убивают код); инвалидацию кода повторным
запросом; ручную выдачу кода админом; отказы анти-enumeration; методистские
хендлеры напрямую (реальная БД).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import re
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import func, select, text
from starlette.datastructures import UploadFile

from app.core.database import AsyncSessionLocal
from app.models.email_outbox import EmailOutbox
from app.models.learning import LearningAccount

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_learning_rows(redis_client):
    """Не оставлять следов в общей test-БД: письма learning + учётки/коды/токены.
    Без этого ломаются предсуществующие тесты email_outbox (dispatcher/cleanup),
    которые рассчитаны на таблицу без посторонних строк."""
    yield
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        # kind='learning' создаём только мы; чистим безусловно, иначе письма
        # staff (@learning-test.local) ломают cleanup-тест outbox'а.
        await db.execute(text("DELETE FROM email_outbox WHERE kind = 'learning'"))
        await db.execute(text("DELETE FROM learning_login_codes"))
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
    for key in await redis_client.keys("learning_session:*"):
        await redis_client.delete(key)
    for key in await redis_client.keys("learning_sessions:*"):
        await redis_client.delete(key)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    import importlib

    import app.main as main_mod

    importlib.reload(main_mod)
    _app = main_mod.app
    return _app


@pytest_asyncio.fixture
async def live_limiter(redis_client):
    """Реальный fastapi-limiter поверх тестового redis (root-conftest ставит
    заглушку глобально; как в rate_limit_matrix — возвращаем честный .call)."""
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


# ── helpers ──────────────────────────────────────────────────────────────────


def _enable_module(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import modules_config

    async def fake_load(redis):
        return SimpleNamespace(learning=SimpleNamespace(enabled=True))

    monkeypatch.setattr(modules_config, "load_modules_shared", fake_load)


def _csrf(ip: str) -> dict[str, str]:
    # Уникальный IP на тест: не пересекаем бакеты rate-limiter между кейсами
    return {"Origin": "http://test", "X-Real-IP": ip}


def _mk_client(app, redis_client, ip: str, cookies: dict | None = None):
    from httpx import ASGITransport, AsyncClient

    app.state.redis = redis_client  # deps get_redis берёт отсюда
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_csrf(ip),
        follow_redirects=False,
        cookies=cookies or {},
    )


async def _fresh_session():
    """Сессия на том же движке/DSN, что используют HTTP-запросы приложения:
    SAVEPOINT-фикстура для API-флоу не подходит (запросы её данные не видят)."""
    return AsyncSessionLocal()


async def _mk_account(email: str) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        acc = LearningAccount(
            email=email,
            full_name="Тестовый Обучаемый",
        )
        db.add(acc)
        await db.commit()
        return acc.id


def _extract_code(body_text: str | None) -> str:
    m = re.search(r"\b(\d{6})\b", body_text or "")
    assert m, f"нет кода в письме: {body_text!r}"
    return m.group(1)


# ── API-флоу learner'а ───────────────────────────────────────────────────────


class TestLearnerAuthFlow:
    async def test_code_request_is_enumeration_safe(
        self,
        app,
        redis_client,
        live_limiter,
        monkeypatch,
    ):
        """Ответ на запрос кода одинаков для существующей и неизвестной почты;
        письмо уходит только существующей учётке."""
        _enable_module(monkeypatch)
        email = f"enum-{uuid.uuid4().hex[:8]}@example.com"
        await _mk_account(email)

        async with _mk_client(app, redis_client, "10.50.0.1") as ac:
            unknown = await ac.post(
                "/api/v1/auth/learning/login",
                json={"email": "ghost@example.com"},
            )
            known = await ac.post(
                "/api/v1/auth/learning/login",
                json={"email": email.upper()},  # регистр не важен
            )
            assert unknown.status_code == known.status_code == 200
            assert unknown.json() == {"ok": True} == known.json()

        async with await _fresh_session() as db:
            letters = (
                (await db.execute(select(EmailOutbox).where(EmailOutbox.to_email == email)))
                .scalars()
                .all()
            )
            assert len(letters) == 1 and letters[0].kind == "learning"

    async def test_login_flow_via_email_code(
        self, app, redis_client, live_limiter, real_db_session, monkeypatch
    ):
        """Сквозной passwordless-вход: запрос кода → письмо из outbox → verify →
        типизированная сессия + cookie."""
        _enable_module(monkeypatch)
        email = f"codelogin-{uuid.uuid4().hex[:8]}@example.com"
        await _mk_account(email)

        async with _mk_client(app, redis_client, "10.50.0.2") as ac:
            r1 = await ac.post("/api/v1/auth/learning/login", json={"email": email})
            assert r1.status_code == 200, r1.text

            code = await _latest_outbox_code(email)
            r2 = await ac.post(
                "/api/v1/auth/learning/verify",
                json={"email": email, "code": code},
            )
            assert r2.status_code == 200, r2.text
            assert r2.json() == {"ok": True}

            from app.services.learning.sessions import COOKIE_NAME, get_session_payload

            sid = r2.cookies[COOKIE_NAME]
            payload = await get_session_payload(redis_client, sid)
            assert payload["principal_type"] == "learning_account"
            assert payload["account_id"] == str(await _account_id_by_email(email))

            # код одноразовый: повторный verify с тем же кодом — отказ
            r3 = await ac.post(
                "/api/v1/auth/learning/verify",
                json={"email": email, "code": code},
            )
            assert r3.status_code == 400

    async def test_wrong_code_five_attempts_kills_code(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        from app.core.config import get_settings
        from app.services.learning import accounts_service as svc

        _enable_module(monkeypatch)
        max_attempts = get_settings().learning_code_max_attempts
        email = f"bruteforce-{uuid.uuid4().hex[:8]}@example.com"
        await _mk_account(email)

        async with _mk_client(app, redis_client, "10.50.0.3") as ac:
            await ac.post("/api/v1/auth/learning/login", json={"email": email})
            code = await _latest_outbox_code(email)

        # Неверные попытки через сервис (без расхода HTTP-бакета лимитера):
        async with await _fresh_session() as db:
            wrong_code = "000000" if code != "000000" else "000001"
            for _ in range(max_attempts):
                outcome = await svc.verify_login_code(db, email=email, code=wrong_code)
                assert outcome is None

        async with _mk_client(app, redis_client, "10.50.0.31") as ac2:
            # верный код после исчерпания попыток тоже мёртв
            dead = await ac2.post(
                "/api/v1/auth/learning/verify",
                json={"email": email, "code": code},
            )
            assert dead.status_code == 400

    async def test_resend_invalidates_previous_code(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        email = f"resend-{uuid.uuid4().hex[:8]}@example.com"
        await _mk_account(email)

        async with _mk_client(app, redis_client, "10.50.0.4") as ac:
            await ac.post("/api/v1/auth/learning/login", json={"email": email})
            first = await _latest_outbox_code(email)
            await ac.post("/api/v1/auth/learning/login", json={"email": email})
            second = await _latest_outbox_code(email)
            assert first != second

            stale = await ac.post(
                "/api/v1/auth/learning/verify",
                json={"email": email, "code": first},
            )
            assert stale.status_code == 400

            fresh = await ac.post(
                "/api/v1/auth/learning/verify",
                json={"email": email, "code": second},
            )
            assert fresh.status_code == 200

    async def test_verify_unknown_email_generic_400(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        """Нет учётки / нет кода / неверный код — один и тот же 400."""
        _enable_module(monkeypatch)
        async with _mk_client(app, redis_client, "10.50.0.5") as ac:
            no_account = await ac.post(
                "/api/v1/auth/learning/verify",
                json={"email": "nobody@example.com", "code": "123456"},
            )
            assert no_account.status_code == 400
            assert no_account.json() == {"detail": "Invalid or expired code"}

    async def test_logout_invalidates_session(self, app, redis_client, monkeypatch):
        from app.services.learning.sessions import COOKIE_NAME

        _enable_module(monkeypatch)  # logout за тем же module-gate (ревью 2026-08-28)

        email = f"logout-{uuid.uuid4().hex[:8]}@example.com"
        acc_id = await _mk_account(email)
        await save_session_simple(redis_client, "sid-logout", str(acc_id))
        async with _mk_client(
            app, redis_client, "10.50.0.6", cookies={COOKIE_NAME: "sid-logout"}
        ) as ac:
            lo = await ac.post("/api/v1/auth/learning/logout")
            assert lo.status_code == 200
            assert lo.json() == {"ok": True}
            # cookie сброшена
            assert "learning_session=" in lo.headers.get("set-cookie", "")
        # сессия удалена из Redis — ключ исчез
        key_after = await redis_client.get("learning_session:sid-logout")
        assert key_after is None


async def save_session_simple(redis, sid: str, account_id: str) -> None:
    from app.services.learning.sessions import save_session

    await save_session(redis, sid, account_id, {"account_id": account_id})


async def _latest_outbox_code(email: str) -> str:
    """Свежее письмо учётке → код входа из тела (пароль существовал только
    в письме — теперь так же живёт код)."""
    async with await _fresh_session() as db:
        letters = (
            (
                await db.execute(
                    select(EmailOutbox)
                    .where(EmailOutbox.to_email == email)
                    .order_by(EmailOutbox.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .all()
        )
        assert letters, f"нет письма для {email}"
        return _extract_code(letters[0].body_text)


async def _account_id_by_email(email: str) -> uuid.UUID:
    async with await _fresh_session() as db:
        return (
            await db.execute(
                select(LearningAccount.id).where(func.lower(LearningAccount.email) == email.lower())
            )
        ).scalar_one()


# ── методистские хендлеры напрямую (реальная БД) ─────────────────────────────


class TestAdminHandlersDirect:
    def _admin(self):
        return SimpleNamespace(id=uuid.uuid4(), role="admin", email="boss@example.com")

    def _req(self):
        return SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"User-Agent": "integration-test"},
        )

    async def test_xlsx_import_reports_created_duplicates_and_invalid_rows(self, redis_client):
        from app.api.learning import admin_routes as ar
        from app.services.learning import accounts_service

        suffix = uuid.uuid4().hex[:8]
        existing_email = f"existing-{suffix}@example.com"
        deleted_email = f"deleted-{suffix}@example.com"
        async with await _fresh_session() as seed:
            await accounts_service.create_account(seed, email=existing_email, full_name="Уже Есть")
            seed.add(
                LearningAccount(
                    email=deleted_email,
                    full_name="Удалённая Учётка",
                    deleted_at=datetime.now(UTC),
                )
            )
            await seed.commit()

        new_email = f"new-{suffix}@example.com"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(("Фамилия Имя", "email", "отдел", "должность"))
        sheet.append(("Новая Учётка", new_email.upper(), "ИТ", "Инженер"))
        sheet.append(("Дубль Базы", existing_email, "", ""))
        sheet.append(("Удалённый Дубль", deleted_email, "", ""))
        sheet.append(("Ошибка", "bad-email", "", ""))
        sheet.append(("Дубль Файла", new_email, "", ""))
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()
        buffer.seek(0)

        db = await _fresh_session()
        report = await ar.import_accounts(
            file=UploadFile(file=buffer, filename="accounts.xlsx"),
            request=self._req(),
            admin=self._admin(),
            redis=redis_client,
            db=db,
        )
        await db.close()

        assert report.created == 1
        assert report.skipped_duplicates == 3
        assert report.error_count == 1
        assert report.errors[0].row == 5
        assert "email" in report.errors[0].message

        async with await _fresh_session() as check:
            account = (
                await check.execute(
                    select(LearningAccount).where(LearningAccount.email == new_email)
                )
            ).scalar_one()
            assert account.full_name == "Новая Учётка"
            assert account.department == "ИТ"
            # письма при импорте больше не отправляются — код человек запросит сам
            messages = (
                (
                    await check.execute(
                        select(EmailOutbox).where(
                            EmailOutbox.kind == "learning",
                            EmailOutbox.to_email == new_email,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert not messages

    async def test_concurrent_imports_count_unique_conflict_as_duplicate(self):
        from app.schemas.learning import LearningAccountCreate
        from app.services.learning import account_import

        email = f"race-import-{uuid.uuid4().hex[:8]}@example.com"
        parsed = account_import.ParsedImport(
            rows=[
                account_import.ImportRow(
                    row_number=2,
                    account=LearningAccountCreate(email=email, full_name="Гонка Импорта"),
                )
            ],
            errors=[],
        )

        async def run_one() -> tuple[int, int]:
            db = await _fresh_session()
            try:
                result = await account_import.import_accounts(db, parsed)
                await db.commit()
                return result.created, result.skipped_duplicates
            finally:
                await db.close()

        outcomes = sorted(await asyncio.gather(run_one(), run_one()))

        assert outcomes == [(0, 1), (1, 0)]
        async with await _fresh_session() as check:
            count = (
                await check.execute(
                    select(func.count())
                    .select_from(LearningAccount)
                    .where(LearningAccount.email == email)
                )
            ).scalar_one()
            assert count == 1

    async def test_import_outbox_failure_rolls_back_all_accounts(self, monkeypatch):
        """Удалённый сценарий: писем при импорте больше нет (passwordless) —
        проверяем, что импорт вообще не кладёт ничего в outbox."""
        from app.schemas.learning import LearningAccountCreate
        from app.services.learning import account_import

        email = f"noletter-import-{uuid.uuid4().hex[:8]}@example.com"
        parsed = account_import.ParsedImport(
            rows=[
                account_import.ImportRow(
                    row_number=2,
                    account=LearningAccountCreate(email=email, full_name="Без Писем"),
                )
            ],
            errors=[],
        )
        db = await _fresh_session()
        result = await account_import.import_accounts(db, parsed)
        await db.commit()
        await db.close()
        assert result.created == 1

        async with await _fresh_session() as check:
            letters = (
                (await check.execute(select(EmailOutbox).where(EmailOutbox.to_email == email)))
                .scalars()
                .all()
            )
            assert not letters

    async def test_full_lifecycle(self, redis_client):
        from app.api.learning import admin_routes as ar
        from app.schemas.learning import LearningAccountCreate

        email = f"lifecycle-{uuid.uuid4().hex[:8]}@example.com"
        db = await _fresh_session()
        created = await ar.create_account(
            body=LearningAccountCreate(email=email, full_name="Жизненный Цикл"),
            request=self._req(),
            admin=self._admin(),
            redis=redis_client,
            db=db,
        )
        await db.commit()
        await db.close()
        assert created.status == "active"

        db_l = await _fresh_session()
        listing = await ar.list_accounts(
            _admin=self._admin(), db=db_l, q="жизненный", limit=20, offset=0
        )
        await db_l.close()
        assert listing.total >= 1
        assert any(i.id == created.id for i in listing.items)

        dup_db = await _fresh_session()
        with pytest.raises(HTTPException) as exc_dup:
            await ar.create_account(
                body=LearningAccountCreate(email=email.upper(), full_name="Дубль Один"),
                request=self._req(),
                admin=self._admin(),
                redis=redis_client,
                db=dup_db,
            )
        assert exc_dup.value.status_code == 409
        await dup_db.close()

        # запасной путь «письмо не дошло»: админ выпускает код вручную
        db_c = await _fresh_session()
        issued = await ar.issue_login_code(
            account_id=created.id,
            request=self._req(),
            admin=self._admin(),
            redis=redis_client,
            db=db_c,
        )
        await db_c.close()
        assert re.fullmatch(r"\d{6}", issued.code)
        assert issued.expires_at > datetime.now(UTC)

        # выданный вручную код принимается verify-сервисом
        from app.services.learning import accounts_service as svc

        async with await _fresh_session() as db_v:
            outcome = await svc.verify_login_code(db_v, email=email, code=issued.code)
            assert outcome is not None

        for action in ("block",):
            db_b = await _fresh_session()
            res = await getattr(ar, f"{action}_account")(
                account_id=created.id,
                request=self._req(),
                admin=self._admin(),
                redis=redis_client,
                db=db_b,
            )
            await db_b.close()
            assert res == {"ok": True}

        # повторный block идемпотентен
        db_b2 = await _fresh_session()
        assert await ar.block_account(
            account_id=created.id,
            request=self._req(),
            admin=self._admin(),
            redis=redis_client,
            db=db_b2,
        ) == {"ok": True}
        await db_b2.close()

        # статус в БД — blocked
        async with await _fresh_session() as ch:
            row = (
                await ch.execute(select(LearningAccount).where(LearningAccount.id == created.id))
            ).scalar_one()
            assert row.status == "blocked"

        # код для заблокированной учётки не выдаётся
        db_cb = await _fresh_session()
        with pytest.raises(HTTPException) as exc_blocked:
            await ar.issue_login_code(
                account_id=created.id,
                request=self._req(),
                admin=self._admin(),
                redis=redis_client,
                db=db_cb,
            )
        assert exc_blocked.value.status_code == 409
        await db_cb.close()

        db_u = await _fresh_session()
        assert await ar.unblock_account(
            account_id=created.id,
            request=self._req(),
            admin=self._admin(),
            redis=redis_client,
            db=db_u,
        ) == {"ok": True}
        await db_u.close()

        missing = uuid.uuid4()
        db_m = await _fresh_session()
        with pytest.raises(HTTPException) as exc404:
            await ar.block_account(
                account_id=missing,
                request=self._req(),
                admin=self._admin(),
                redis=redis_client,
                db=db_m,
            )
        assert exc404.value.status_code == 404
        await db_m.close()

        # паролей больше нет — писем при жизни учётки не появлялось
        async with await _fresh_session() as ch2:
            letters = (
                (await ch2.execute(select(EmailOutbox).where(EmailOutbox.to_email == email)))
                .scalars()
                .all()
            )
            assert not letters


class TestCoursesLifecycle:
    """Инкремент 2: CRUD курсов, элементы, зачисление обоих типов, прогресс."""

    async def _mk_staff(self, email: str, full_name: str = "Курсовой Сотрудник") -> uuid.UUID:
        from app.models.user import User

        async with await _fresh_session() as db:
            exists = (
                await db.execute(select(User.id).where(User.email == email))
            ).scalar_one_or_none()
            if exists:
                return uuid.UUID(str(exists))
            u = User(
                email=email,
                full_name=full_name,
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            await db.commit()
            return u.id

    def _req(self):
        from types import SimpleNamespace

        return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})

    def _admin(self, user_id: uuid.UUID, email: str):
        from types import SimpleNamespace

        return SimpleNamespace(id=user_id, role="admin", email=email)

    async def test_full_course_lifecycle_with_progress(self, redis_client):
        from datetime import UTC
        from datetime import datetime as dt

        from fastapi import HTTPException
        from pydantic import ValidationError

        from app.api.learning import admin_courses as ac
        from app.models.learning import (
            LearningCourseItem,
            LearningCourseParticipant,
            LearningItemProgress,
            LearningTestAttempt,
        )
        from app.schemas.learning import (
            CourseCreate,
            ItemCreate,
            ItemsReorder,
            ParticipantEnroll,
        )

        req = self._req()
        m_mail = f"methodist-{uuid.uuid4().hex[:8]}@learning-test.local"
        admin = self._admin(await self._mk_staff(m_mail, "Методист Тестовый"), m_mail)

        # 1) создание: slug автогенерится из RU-названия, дубль получает суффикс
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Охрана труда и безопасность"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            cid = course.id
            c2 = await ac.create_course(
                body=CourseCreate(title="Охрана труда и безопасность"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            assert course.status == "draft"
            assert course.slug.startswith("ohrana-truda")
            assert c2.slug != course.slug
            await db.commit()

        # 2) элементы: материал-ссылка + заготовка теста
        async with await _fresh_session() as db:
            mat = await ac.add_item(
                cid,
                ItemCreate(
                    type="material", title="Регламент", url="https://docs.example.com/reg.pdf"
                ),
                req,
                admin,
                redis_client,
                db,
            )
            tst = await ac.add_item(
                cid, ItemCreate(type="test", title="Экзамен"), req, admin, redis_client, db
            )
            mid, tid = uuid.UUID(mat["id"]), uuid.UUID(tst["id"])
            await db.commit()

        # порядок: неполный список → 422; полный → пересортирован
        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as exc422:
                await ac.reorder_items_endpoint(
                    cid, ItemsReorder(ordered_ids=[mid]), req, admin, redis_client, db
                )
            assert exc422.value.status_code == 422
            await ac.reorder_items_endpoint(
                cid, ItemsReorder(ordered_ids=[tid, mid]), req, admin, redis_client, db
            )
            await db.commit()

        async with await _fresh_session() as chk:
            orders = {
                str(i.id): i.sort_order
                for i in (
                    await chk.execute(
                        select(LearningCourseItem).where(LearningCourseItem.course_id == cid)
                    )
                )
                .scalars()
                .all()
            }
        assert orders[str(tid)] < orders[str(mid)]

        # 2b) тесту нужен отвечаемый вопрос: publish-gate (ревью 2026-08-30)
        # не публикует курс с тестом без вопросов с вариантами
        async with await _fresh_session() as db:
            from app.models.learning import LearningQuestion, LearningQuestionOption

            q = LearningQuestion(test_item_id=tid, text="2+2?", multi=False, sort_order=0)
            db.add(q)
            await db.flush()
            db.add(
                LearningQuestionOption(question_id=q.id, text="4", is_correct=True, sort_order=0)
            )
            await db.commit()

        # 3) публикация
        async with await _fresh_session() as db:
            published = await ac.publish_course(cid, req, admin, redis_client, db)
            assert published["status"] == "published"

        # 4) участники обоих типов; дубликат → 409; XOR схемы → отказ
        ext_acc_id = await _mk_account(f"lifecycle-course-{uuid.uuid4().hex[:8]}@example.com")
        staff_uid = await self._mk_staff(f"learner-{uuid.uuid4().hex[:8]}@learning-test.local")

        async with await _fresh_session() as db:
            await ac.enroll_participant(
                cid,
                ParticipantEnroll(learning_account_id=ext_acc_id),
                req,
                admin,
                redis_client,
                db,
                db,
            )
            await ac.enroll_participant(
                cid, ParticipantEnroll(user_id=staff_uid), req, admin, redis_client, db, db
            )
            await db.commit()

        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as exc409:
                await ac.enroll_participant(
                    cid, ParticipantEnroll(user_id=staff_uid), req, admin, redis_client, db, db
                )
            assert exc409.value.status_code == 409

        async with await _fresh_session() as db:
            with pytest.raises((HTTPException, ValidationError)):
                await ac.enroll_participant(
                    cid,
                    ParticipantEnroll(user_id=staff_uid, learning_account_id=ext_acc_id),
                    req,
                    admin,
                    redis_client,
                    db,
                    db,
                )

        # письма зачисления ушли обоим типам получателей
        async with await _fresh_session() as ch2:
            letters = (
                (
                    await ch2.execute(
                        text(
                            "SELECT to_email FROM email_outbox "
                            "WHERE kind='learning' AND subject LIKE 'Вы зачислены%'"
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert any("@learning-test.local" in e for e in letters)
        assert any("@example.com" in e for e in letters)

        # 5) прогресс: материал ознакомлен внешним, тест сдан сотрудником
        async with await _fresh_session() as w:
            w.add(LearningItemProgress(item_id=mid, learning_account_id=ext_acc_id))
            w.add(
                LearningTestAttempt(
                    test_item_id=tid,
                    user_id=staff_uid,
                    submitted_at=dt.now(UTC),
                    score=90,
                    passed=True,
                    answers={},
                )
            )
            await w.commit()

        async with await _fresh_session() as db:
            prog = await ac.course_progress(cid, admin, db)
        by_kind = {p["participant_kind"]: p for p in prog["participants"]}
        assert set(by_kind) == {"external", "staff"}
        assert by_kind["external"]["progress_completed"] == 1
        assert by_kind["staff"]["progress_completed"] == 1
        assert prog["total_items"] == 2

        # 6) исключение (soft) → повторное зачисление возможно
        async with await _fresh_session() as f1:
            part_row = (
                await f1.execute(
                    select(LearningCourseParticipant.id).where(
                        LearningCourseParticipant.learning_account_id == ext_acc_id,
                        LearningCourseParticipant.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
            removed = await ac.unenroll_participant(
                cid, uuid.UUID(str(part_row)), req, admin, redis_client, f1
            )
            assert removed == {"ok": True}

        async with await _fresh_session() as f2:
            re_enrolled = await ac.enroll_participant(
                cid,
                ParticipantEnroll(learning_account_id=ext_acc_id),
                req,
                admin,
                redis_client,
                f2,
                f2,
            )
            assert re_enrolled["ok"] is True

        # 7) unpublish → draft; soft-delete → 404 на чтении
        async with await _fresh_session() as f3:
            unp = await ac.unpublish_course(cid, req, admin, redis_client, f3)
            assert unp["status"] == "draft"
            assert (await ac.delete_course(cid, req, admin, redis_client, f3))["ok"] is True
            with pytest.raises(HTTPException) as exc404:
                await ac.get_course(cid, admin, f3)
            assert exc404.value.status_code == 404

    async def test_upload_material_rejects_non_pdf(self, redis_client, tmp_path, monkeypatch):
        import io

        from fastapi import HTTPException, UploadFile
        from starlette.datastructures import Headers

        from app.api.learning import admin_courses as ac
        from app.schemas.learning import CourseCreate, ItemCreate
        from app.services.learning import courses_service as _cs

        monkeypatch.setattr(_cs, "LEARNING_DATA_DIR", str(tmp_path))

        req = self._req()
        m_mail = f"m-{uuid.uuid4().hex[:8]}@learning-test.local"
        admin = self._admin(await self._mk_staff(m_mail, "Методист Аплоад"), m_mail)

        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Материалы upload"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            item = await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Ф", url="https://x.example.com/a.pdf"),
                req,
                admin,
                redis_client,
                db,
            )
            await db.commit()

            up = UploadFile(
                file=io.BytesIO(b"not a pdf at all"),
                filename="fake.pdf",
                headers=Headers({"content-type": "application/pdf"}),
            )
            with pytest.raises(HTTPException) as exc:
                await ac.upload_material_file(
                    uuid.UUID(item["id"]), req, admin, redis_client, db, up
                )
            assert exc.value.status_code == 422  # python-magic отверг контент


class TestMethodistsDirect:
    """Назначение/снятие методистов (ревью 2026-08-28): только глобальный админ."""

    def _admin(self):
        return SimpleNamespace(id=uuid.uuid4(), role="admin", email="boss@example.com")

    def _req(self):
        return SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"User-Agent": "integration-test"},
        )

    async def _mk_user(
        self, *, full_name: str = "Методист Тестовый", email_domain: str = "methodist"
    ) -> uuid.UUID:
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            u = User(
                email=f"{email_domain}-{uuid.uuid4().hex[:8]}@example.com",
                full_name=full_name,
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            await db.commit()
            return u.id

    async def test_assign_list_revoke(self, redis_client):
        from sqlalchemy import select

        from app.api.learning import methodists as mt
        from app.models.learning import LearningAdmin
        from app.schemas.learning import LearningAdminCreate

        # added_by — FK на users: админ нужен реальной строкой, не чужим id.
        boss_id = await self._mk_user(full_name="Босс Тестовый", email_domain="boss")
        uid = await self._mk_user()
        boss = SimpleNamespace(id=boss_id, role="admin", email="boss@example.com")
        async with await _fresh_session() as db:
            assigned = await mt.assign_methodist(
                body=LearningAdminCreate(user_id=uid),
                request=self._req(),
                admin=boss,
                redis=redis_client,
                db=db,
            )
            assert assigned == {"ok": True, "user_id": str(uid)}

            with pytest.raises(HTTPException) as dup:
                await mt.assign_methodist(
                    body=LearningAdminCreate(user_id=uid),
                    request=self._req(),
                    admin=boss,
                    redis=redis_client,
                    db=db,
                )
            assert dup.value.status_code == 409

            listing = await mt.list_methodists(_admin=boss, db=db)
            assert any(row.user_id == uid for row in listing)

            revoked = await mt.revoke_methodist(uid, self._req(), boss, redis_client, db)
            assert revoked == {"ok": True}
            with pytest.raises(HTTPException) as gone:
                await mt.revoke_methodist(uid, self._req(), boss, redis_client, db)
            assert gone.value.status_code == 404
            assert (
                await db.execute(select(LearningAdmin).where(LearningAdmin.user_id == uid))
            ).first() is None

    async def test_assign_unknown_user_404(self, redis_client):
        from app.api.learning import methodists as mt
        from app.schemas.learning import LearningAdminCreate

        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as exc:
                await mt.assign_methodist(
                    body=LearningAdminCreate(user_id=uuid.uuid4()),
                    request=self._req(),
                    admin=self._admin(),
                    redis=redis_client,
                    db=db,
                )
            assert exc.value.status_code == 404


class TestPublishGateAndDeletePolicy:
    """Ревью 2026-08-28 (P1): publish-gate «материал = PDF или ссылка» (§6.1)
    и запрет удаления теста с попытками (§15 распространяется на удаление)."""

    _boss_id: uuid.UUID | None = None

    def _admin(self):
        return SimpleNamespace(id=self._boss_id, role="admin", email="boss@example.com")

    def _req(self):
        return SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"User-Agent": "integration-test"},
        )

    async def _mk_boss(self) -> None:
        """created_by — FK на users: нужна реальная строка. Роль ровно reader:
        лишняя строка role="admin" в общей test-БД заставляет bootstrap_admin
        пропустить создание первого админа и валит TestBootstrapAdmin
        (проверка требует «админов нет»); direct-вызовы роль строки не
        проверяют — AdminDep подменяется SimpleNamespace'ом."""
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            u = User(
                email=f"gate-boss-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Босс Публикации",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            await db.commit()
            self._boss_id = u.id

    async def test_publish_requires_material_content(self, redis_client):
        from app.api.learning import admin_courses as ac
        from app.schemas.learning import CourseCreate, ItemCreate, ItemUpdate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Пустые материалы"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            m = await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Инструкция без содержимого"),
                req,
                admin,
                redis_client,
                db,
            )
            tst = await ac.add_item(
                course.id,
                ItemCreate(type="test", title="Тест"),
                req,
                admin,
                redis_client,
                db,
            )
            # Пустой материал ломает публикацию, пустой тест — тоже
            # (ревью 2026-08-30): обе проблемы приходят одним 422.
            with pytest.raises(HTTPException) as empty_gate:
                await ac.publish_course(course.id, req, admin, redis_client, db)
            assert empty_gate.value.status_code == 422
            assert "Инструкция без содержимого" in empty_gate.value.detail
            assert "нет ни одного вопроса" in empty_gate.value.detail

            from app.models.learning import LearningQuestion, LearningQuestionOption

            q = LearningQuestion(
                test_item_id=uuid.UUID(tst["id"]), text="2+2?", multi=False, sort_order=0
            )
            db.add(q)
            await db.flush()
            db.add(
                LearningQuestionOption(question_id=q.id, text="4", is_correct=True, sort_order=0)
            )
            await db.commit()

            with pytest.raises(HTTPException) as e:
                await ac.publish_course(course.id, req, admin, redis_client, db)
            assert e.value.status_code == 422
            assert "Инструкция без содержимого" in e.value.detail
            assert "нет ни одного вопроса" not in e.value.detail

            # Материал получает ссылку → курс публикуется
            await ac.update_item(
                uuid.UUID(m["id"]),
                ItemUpdate(url="https://x.example.com/a.pdf"),
                req,
                admin,
                redis_client,
                db,
            )
            await db.commit()
            ok = await ac.publish_course(course.id, req, admin, redis_client, db)
            assert ok["status"] == "published"

            # Publish-gate обязан сохраняться и после публикации: иначе
            # двухшаговый PDF-item (сначала строка, потом upload) мгновенно
            # появляется у learner'ов пустым.
            with pytest.raises(HTTPException) as published_err:
                await ac.add_item(
                    course.id,
                    ItemCreate(type="material", title="Пустой после публикации"),
                    req,
                    admin,
                    redis_client,
                    db,
                )
            assert published_err.value.status_code == 409
            await db.rollback()

    async def test_publish_accepts_pdf_material(self, redis_client):
        from sqlalchemy import update as sa_update

        from app.api.learning import admin_courses as ac
        from app.models.learning import LearningCourseItem
        from app.schemas.learning import CourseCreate, ItemCreate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="PDF-материалы"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            m = await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Инструкция PDF"),
                req,
                admin,
                redis_client,
                db,
            )
            # file_path как после успешного upload (заполняет только сервер)
            await db.execute(
                sa_update(LearningCourseItem)
                .where(LearningCourseItem.id == uuid.UUID(m["id"]))
                .values(file_path="/data/learning/materials/x/y.pdf")
            )
            await db.commit()
            ok = await ac.publish_course(course.id, req, admin, redis_client, db)
            assert ok["status"] == "published"

    async def test_publish_rejects_test_without_questions(self, redis_client):
        """Ревью 2026-08-30 (P1): курс с тестом без вопросов непроходим —
        learner получает 409 на старте попытки, 100% + сертификат недостижимы.
        Publish-gate обязан ловить это до публикации; наполнение — 422 уходит."""
        from app.api.learning import admin_courses as ac
        from app.models.learning import LearningQuestion, LearningQuestionOption
        from app.schemas.learning import CourseCreate, ItemCreate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Курс с пустым тестом"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Материал", url="https://x.example.com"),
                req,
                admin,
                redis_client,
                db,
            )
            tst = await ac.add_item(
                course.id,
                ItemCreate(type="test", title="Итоговый тест"),
                req,
                admin,
                redis_client,
                db,
            )
            await db.commit()

            with pytest.raises(HTTPException) as e:
                await ac.publish_course(course.id, req, admin, redis_client, db)
            assert e.value.status_code == 422
            assert "Итоговый тест" in e.value.detail
            assert "нет ни одного вопроса" in e.value.detail

            # вопрос без вариантов всё ещё не отвечаем (start_attempt его
            # отфильтровывает) — гейт остаётся
            q_bare = LearningQuestion(
                test_item_id=uuid.UUID(tst["id"]), text="Пустой", multi=False, sort_order=0
            )
            db.add(q_bare)
            await db.commit()
            with pytest.raises(HTTPException) as bare:
                await ac.publish_course(course.id, req, admin, redis_client, db)
            assert bare.value.status_code == 422

            # появился вариант → тест отвечаем → курс публикуется
            db.add(
                LearningQuestionOption(
                    question_id=q_bare.id, text="4", is_correct=True, sort_order=0
                )
            )
            await db.commit()
            ok = await ac.publish_course(course.id, req, admin, redis_client, db)
            assert ok["status"] == "published"

    async def test_add_test_to_published_course_conflict(self, redis_client):
        """Ревью 2026-08-30 (P1): тест создаётся пустым, поэтому в опубликованный
        курс его добавлять нельзя — как PDF-материал без файла (409)."""
        from app.api.learning import admin_courses as ac
        from app.schemas.learning import CourseCreate, ItemCreate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Опубликованный курс"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Материал", url="https://x.example.com"),
                req,
                admin,
                redis_client,
                db,
            )
            await db.commit()
            ok = await ac.publish_course(course.id, req, admin, redis_client, db)
            assert ok["status"] == "published"

            with pytest.raises(HTTPException) as e:
                await ac.add_item(
                    course.id,
                    ItemCreate(type="test", title="Тест следом"),
                    req,
                    admin,
                    redis_client,
                    db,
                )
            assert e.value.status_code == 409
            assert "перед добавлением теста" in e.value.detail

            # материал-ссылка по-прежнему добавляется в опубликованный курс
            extra = await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Ещё ссылка", url="https://x.example.com/b"),
                req,
                admin,
                redis_client,
                db,
            )
            assert extra["sort_order"] == 1

    async def test_patch_slug_sanitized_like_create(self, redis_client):
        """Ревью 2026-08-30 (P1): PATCH применяет slugify — «a/b», пробелы и
        спецсимволы не сохраняются сырыми и не ломают /courses/{slug}."""
        from app.api.learning import admin_courses as ac
        from app.schemas.learning import CourseCreate, CourseUpdate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Охрана труда"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            await db.commit()
            assert course.slug == "ohrana-truda"

            updated = await ac.update_course(
                course.id,
                CourseUpdate(slug="a/b"),
                req,
                admin,
                redis_client,
                db,
                db,
            )
            assert updated.slug == "a-b"
            await db.commit()

            # коллизия с занятым slug по-прежнему получает суффикс, не 500
            other = await ac.create_course(
                body=CourseCreate(title="Другой курс"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            renamed = await ac.update_course(
                other.id,
                CourseUpdate(slug="a/b"),
                req,
                admin,
                redis_client,
                db,
                db,
            )
            assert renamed.slug == "a-b-2"

            # переименование первого курса санитизируется так же
            updated2 = await ac.update_course(
                course.id,
                CourseUpdate(slug="Проводка/Обучение #1"),
                req,
                admin,
                redis_client,
                db,
                db,
            )
            assert updated2.slug == "provodka-obuchenie-1"
            await db.commit()
        from app.api.learning import admin_courses as ac
        from app.models.learning import LearningTestAttempt
        from app.models.user import User
        from app.schemas.learning import CourseCreate, ItemCreate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Удаление с попытками"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            m = await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Материал", url="https://x.example.com"),
                req,
                admin,
                redis_client,
                db,
            )
            t = await ac.add_item(
                course.id,
                ItemCreate(type="test", title="Тест"),
                req,
                admin,
                redis_client,
                db,
            )
            u = User(
                email=f"del-policy-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Сотрудник Удаляемый",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            await db.flush()
            attempt = LearningTestAttempt(
                test_item_id=uuid.UUID(t["id"]),
                user_id=u.id,
                started_at=datetime.now(UTC),
                answers={},
            )
            db.add(attempt)
            await db.commit()

            # §15 на удаление: тест с попыткой удалить нельзя
            with pytest.raises(HTTPException) as e:
                await ac.delete_item(uuid.UUID(t["id"]), req, admin, redis_client, db)
            assert e.value.status_code == 409
            assert "удаление" in e.value.detail

            # материал без попыток удаляется свободно
            removed = await ac.delete_item(uuid.UUID(m["id"]), req, admin, redis_client, db)
            assert removed == {"ok": True}

            # удаление всего КУРСА с попытками разрешено (soft, история сохраняется)
            deleted = await ac.delete_course(course.id, req, admin, redis_client, db)
            assert deleted == {"ok": True}

            # История остаётся в БД, но прямые attempt endpoints закрыты тем же
            # course/enrollment gate, что карточка курса.
            from app.api.learning import me_routes as mr
            from app.schemas.learning import SubmitAnswers
            from app.services.learning.participant import KIND_USER, LearningParticipant

            participant = LearningParticipant(kind=KIND_USER, user_id=u.id)
            with pytest.raises(HTTPException) as state_err:
                await mr.attempt_state(attempt.id, participant, db)
            assert state_err.value.status_code == 404
            with pytest.raises(HTTPException) as submit_err:
                await mr.submit(attempt.id, SubmitAnswers(answers={}), participant, db)
            assert submit_err.value.status_code == 404


class TestPatchClearSemantics:
    """Ревью 2026-08-30: явный null в PATCH должен очищать описание и url —
    с защитой инварианта опубликованного курса (непроходимый материал)."""

    _boss_id: uuid.UUID | None = None

    def _admin(self):
        return SimpleNamespace(id=self._boss_id, role="admin", email="boss@example.com")

    def _req(self):
        return SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"User-Agent": "integration-test"},
        )

    async def _mk_boss(self) -> None:
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            u = User(
                email=f"patch-boss-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Босс Правок",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            await db.commit()
            self._boss_id = u.id

    async def test_patch_null_clears_description_and_updates_title(self, redis_client):
        from app.api.learning import admin_courses as ac
        from app.schemas.learning import CourseCreate, CourseUpdate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Курс", description="Было описание"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            await db.commit()
            assert course.description == "Было описание"

            # явный null → очистить; title отсутствует → не менять
            updated = await ac.update_course(
                course.id,
                CourseUpdate(description=None),
                req,
                admin,
                redis_client,
                db,
                db,
            )
            assert updated.description is None
            assert updated.title == "Курс"

            # новое описание записывается
            updated2 = await ac.update_course(
                course.id,
                CourseUpdate(description="Стало описание"),
                req,
                admin,
                redis_client,
                db,
                db,
            )
            assert updated2.description == "Стало описание"
            await db.commit()

    async def test_patch_url_null_guarded_for_published_course(self, redis_client):
        from app.api.learning import admin_courses as ac
        from app.schemas.learning import CourseCreate, ItemCreate, ItemUpdate

        await self._mk_boss()
        admin, req = self._admin(), self._req()
        async with await _fresh_session() as db:
            course = await ac.create_course(
                body=CourseCreate(title="Курс со ссылкой"),
                request=req,
                admin=admin,
                redis=redis_client,
                db=db,
                dba=db,
            )
            m = await ac.add_item(
                course.id,
                ItemCreate(type="material", title="Материал-ссылка", url="https://x.example.com"),
                req,
                admin,
                redis_client,
                db,
            )
            await db.commit()
            ok = await ac.publish_course(course.id, req, admin, redis_client, db)
            assert ok["status"] == "published"

            # в опубликованном курсе очистка url без PDF запрещена (инвариант)
            with pytest.raises(HTTPException) as e:
                await ac.update_item(
                    uuid.UUID(m["id"]),
                    ItemUpdate(url=None),
                    req,
                    admin,
                    redis_client,
                    db,
                )
            assert e.value.status_code == 409

            # отсутствующее поле url — «не менять»: правка названия проходит
            renamed = await ac.update_item(
                uuid.UUID(m["id"]),
                ItemUpdate(title="Новое имя"),
                req,
                admin,
                redis_client,
                db,
            )
            assert renamed == {"ok": True}

        from app.models.learning import LearningCourseItem

        async with await _fresh_session() as db:
            await ac.unpublish_course(course.id, req, admin, redis_client, db)
            # черновик: null очищает ссылку
            await ac.update_item(
                uuid.UUID(m["id"]),
                ItemUpdate(url=None),
                req,
                admin,
                redis_client,
                db,
            )
            await db.commit()
            item = (
                await db.execute(
                    select(LearningCourseItem).where(LearningCourseItem.id == uuid.UUID(m["id"]))
                )
            ).scalar_one()
            assert item.url is None
