"""Integration: вопросы теста и движок попыток (инкремент 3, ТЗ §6.3).

Реальные PostgreSQL/Redis из тестового стека (scripts/test-integration.sh).
Покрывает: замок правок теста после отправленных попыток, старт/возобновление/
submit, скоринг (multi = строгое множество, частично верный = 0), лимит по
отправленным, ленивое клеймо abandoned, гейты доступа участника и сквозной
API-флоу внешней учётки через cookie ``learning_session``.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.learning import (
    LearningAccount,
    LearningCourse,
    LearningCourseItem,
    LearningCourseParticipant,
    LearningTest,
    LearningTestAttempt,
)

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
    """Реальный fastapi-limiter поверх тестового redis (как в accounts_flow)."""
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


# ── builders (реальная БД) ───────────────────────────────────────────────────


class Builder:
    def __init__(self):
        self.course_row: LearningCourse | None = None
        self.items: dict[uuid.UUID, LearningCourseItem] = {}

    async def course(
        self, *, slug: str | None = None, status_: str = "published"
    ) -> LearningCourse:
        async with AsyncSessionLocal() as db:
            c = LearningCourse(
                slug=slug or f"t-{uuid.uuid4().hex[:10]}",
                title="Курс движка попыток",
                status=status_,
                published_at=datetime.now(UTC) if status_ == "published" else None,
            )
            db.add(c)
            await db.commit()
            self.course_row = c
            return c

    async def set_status(self, status_: str) -> None:
        assert self.course_row is not None, "сначала course()"
        async with AsyncSessionLocal() as db:
            c = (
                await db.execute(
                    select(LearningCourse).where(LearningCourse.id == self.course_row.id)
                )
            ).scalar_one()
            c.status = status_
            c.published_at = datetime.now(UTC) if status_ == "published" else None
            await db.commit()

    async def test_item(self, **settings) -> LearningCourseItem:
        assert self.course_row is not None, "сначала course()"
        async with AsyncSessionLocal() as db:
            item = LearningCourseItem(
                course_id=self.course_row.id,
                type="test",
                title="Тест",
                sort_order=len(self.items),
            )
            db.add(item)
            await db.flush()
            db.add(
                LearningTest(
                    item_id=item.id,
                    pass_score=settings.get("pass_score", 70),
                    max_attempts=settings.get("max_attempts", 0),
                    shuffle_questions=settings.get("shuffle_questions", False),
                    shuffle_answers=settings.get("shuffle_answers", False),
                )
            )
            await db.commit()
            self.items[item.id] = item
            return item

    async def material_item(self) -> LearningCourseItem:
        assert self.course_row is not None, "сначала course()"
        async with AsyncSessionLocal() as db:
            item = LearningCourseItem(
                course_id=self.course_row.id,
                type="material",
                title="Материал",
                url="https://example.com/doc",
                sort_order=len(self.items),
            )
            db.add(item)
            await db.commit()
            self.items[item.id] = item
            return item

    @staticmethod
    async def add_question(
        item: LearningCourseItem,
        *,
        text_: str = "Вопрос?",
        multi: bool = False,
        options: tuple[tuple[str, bool], ...] = (("a", True), ("b", False)),
    ) -> uuid.UUID:
        from app.schemas.learning import OptionIn, QuestionCreate
        from app.services.learning import tests_service as ts

        body = QuestionCreate(
            text=text_,
            multi=multi,
            options=[OptionIn(text=t, is_correct=ok) for t, ok in options],
        )
        async with AsyncSessionLocal() as db:
            q = await ts.add_question(
                db,
                item,
                text=body.text,
                multi=body.multi,
                options=[{"text": o.text, "is_correct": o.is_correct} for o in body.options],
            )
            await db.commit()
            return q.id

    @staticmethod
    async def question_map(qids: list[uuid.UUID]) -> dict[str, dict]:
        """{qid: {text, correct: frozenset(option_ids), options: {text: oid}}}"""
        from sqlalchemy import select as sa_select

        from app.models.learning import LearningQuestion, LearningQuestionOption

        out: dict[str, dict] = {}
        async with AsyncSessionLocal() as db:
            for row in (
                await db.execute(sa_select(LearningQuestion).where(LearningQuestion.id.in_(qids)))
            ).scalars():
                opts = (
                    await db.execute(
                        sa_select(LearningQuestionOption).where(
                            LearningQuestionOption.question_id == row.id
                        )
                    )
                ).scalars()
                pairs = list(opts)
                out[str(row.id)] = {
                    "multi": row.multi,
                    "correct": frozenset(o.id for o in pairs if o.is_correct),
                    "options": {o.text: o.id for o in pairs},
                }
        return out

    async def enroll_staff(self) -> uuid.UUID:
        from app.models.user import User

        assert self.course_row is not None, "сначала course()"
        async with AsyncSessionLocal() as db:
            u = User(
                email=f"engine-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Движковый Сотрудник",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add(u)
            await db.flush()
            db.add(
                LearningCourseParticipant(
                    course_id=self.course_row.id,
                    user_id=u.id,
                    display_name=u.full_name,
                    email=u.email,
                )
            )
            await db.commit()
            return u.id

    async def enroll_account(self) -> uuid.UUID:
        assert self.course_row is not None, "сначала course()"
        async with AsyncSessionLocal() as db:
            acc = LearningAccount(
                email=f"engine-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Внешний Движковый",
            )
            db.add(acc)
            await db.flush()
            db.add(
                LearningCourseParticipant(
                    course_id=self.course_row.id,
                    learning_account_id=acc.id,
                    display_name=acc.full_name,
                    email=acc.email,
                )
            )
            await db.commit()
            return acc.id


def _staff(uid: uuid.UUID):
    from app.services.learning.participant import KIND_USER, LearningParticipant

    return LearningParticipant(
        kind=KIND_USER,
        user_id=uid,
        display_name="Движковый Сотрудник",
        email="staff@example.com",
    )


def _ext(aid: uuid.UUID):
    from app.services.learning.participant import KIND_ACCOUNT, LearningParticipant

    return LearningParticipant(
        kind=KIND_ACCOUNT,
        learning_account_id=aid,
        display_name="Внешний Движковый",
        email="ext@example.com",
    )


async def _fresh_session():
    return AsyncSessionLocal()


async def _wait_until_db_lock(pid: int, *, timeout: float = 5.0) -> None:
    """Дождаться реального ожидания PostgreSQL-lock, а не угадывать по sleep."""
    async with asyncio.timeout(timeout):
        while True:
            async with AsyncSessionLocal() as probe:
                wait_type = (
                    await probe.execute(
                        text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                        {"pid": pid},
                    )
                ).scalar_one_or_none()
            if wait_type == "Lock":
                return
            await asyncio.sleep(0.02)


# ── замок неизменяемости теста ───────────────────────────────────────────────


class TestQuestionManagementAndLock:
    async def test_add_question_normalizes_and_locks_after_submitted(self):
        from app.services.learning import tests_service as ts

        b = Builder()
        await b.course()
        item = await b.test_item()

        qid = await b.add_question(item, multi=True, options=(("x", True), ("y", True)))
        m = await b.question_map([qid])
        # normalize: оба варианта сохранены, порядок вариантов детерминирован
        assert len(m[str(qid)]["options"]) == 2

        # до попытки настройки правятся свободно
        async with await _fresh_session() as db:
            test = await ts.update_settings(
                db,
                item,
                pass_score=50,
                max_attempts=5,
                shuffle_questions=None,
                shuffle_answers=None,
            )
            await db.commit()
        assert test.pass_score == 50 and test.max_attempts == 5

        # появилась отправленная попытка (вставляем строку напрямую)
        uid = await b.enroll_staff()
        async with await _fresh_session() as db:
            db.add(
                LearningTestAttempt(
                    test_item_id=item.id,
                    user_id=uid,
                    started_at=datetime.now(UTC),
                    submitted_at=datetime.now(UTC),
                    score=100,
                    passed=True,
                    answers={"version": 1},
                )
            )
            await db.commit()

        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e:
                await ts.update_settings(
                    db,
                    item,
                    pass_score=10,
                    max_attempts=None,
                    shuffle_questions=None,
                    shuffle_answers=None,
                )
            assert e.value.status_code == 409
        async with await _fresh_session() as db:
            fresh_item = (
                await db.execute(select(LearningCourseItem).where(LearningCourseItem.id == item.id))
            ).scalar_one()
            with pytest.raises(HTTPException) as e2:
                await b.add_question(fresh_item, text_="Ещё?")
            assert e2.value.status_code == 409  # замок до добавления вопросов тоже

    async def test_single_choice_rejects_two_correct(self):
        b = Builder()
        await b.course()
        item = await b.test_item()
        from app.services.learning import tests_service as ts

        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e:
                await ts.add_question(
                    db,
                    item,
                    text="?",
                    multi=False,
                    options=[{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}],
                )
            assert e.value.status_code == 422


# ── жизненный цикл попытки ───────────────────────────────────────────────────


class TestAttemptLifecycle:
    async def test_start_resume_submit_rescore_progress(self):
        from app.services.learning import courses_service as cs
        from app.services.learning import tests_service as ts

        b = Builder()
        course = await b.course()
        item = await b.test_item(pass_score=70, max_attempts=3)
        material = await b.material_item()
        uid = await b.enroll_staff()
        p = _staff(uid)

        q_sing = await b.add_question(
            item, text_="Один ответ?", options=(("да", True), ("нет", False))
        )
        q_multi = await b.add_question(
            item, text_="Несколько?", multi=True, options=(("c1", True), ("c2", True), ("w", False))
        )
        qm = await b.question_map([q_sing, q_multi])

        # старт (материал ещё не пройден)
        async with await _fresh_session() as db:
            attempt, created = await ts.start_attempt(db, p, item=item, course_published=True)
            await db.commit()
        assert created is True

        # возобновление возвращает ту же попытку и не расходует лимит
        async with await _fresh_session() as db:
            again, created2 = await ts.start_attempt(db, p, item=item, course_published=True)
            await db.commit()
        assert again.id == attempt.id and created2 is False

        # частично верный multi («частично верный = 0») + верный single = 50 < 70
        resp1 = {
            str(q_sing): [qm[str(q_sing)]["options"]["да"]],
            str(q_multi): [qm[str(q_multi)]["options"]["c1"]],  # неполный набор!
        }
        async with await _fresh_session() as db:
            a1, score = await ts.submit_attempt(db, p, attempt.id, resp1)
            await db.commit()
        assert score == 50 and a1.passed is False and a1.submitted_at is not None

        # повторный submit той же попытки запрещён
        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e:
                await ts.submit_attempt(db, p, attempt.id, resp1)
            assert e.value.status_code == 409

        # пересдача: полные наборы обоих вопросов → 100/passed
        async with await _fresh_session() as db:
            att2, created3 = await ts.start_attempt(db, p, item=item, course_published=True)
            await db.commit()
        assert created3 is True

        # незнакомый вопрос в ответах → 422 (пока попытка открыта)
        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e4:
                await ts.submit_attempt(db, p, att2.id, {str(uuid.uuid4()): []})
            assert e4.value.status_code == 422

        resp2 = {
            str(q_sing): [qm[str(q_sing)]["options"]["да"]],
            str(q_multi): sorted(str(x) for x in qm[str(q_multi)]["correct"]),
        }
        async with await _fresh_session() as db:
            a2, score2 = await ts.submit_attempt(db, p, att2.id, resp2)
            await db.commit()
        assert score2 == 100 and a2.passed is True

        # отправленных две, лимит 3 → третья стартует
        async with await _fresh_session() as db:
            att3, created4 = await ts.start_attempt(db, p, item=item, course_published=True)
            await db.commit()
        assert created4 is True
        async with await _fresh_session() as db:
            a3, score3 = await ts.submit_attempt(db, p, att3.id, resp1)
            await db.commit()
        assert score3 == 50 and a3.passed is False

        # лимит исчерпан ровно на четвёртом старте
        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e3:
                await ts.start_attempt(db, p, item=item, course_published=True)
            assert e3.value.status_code == 409

        # правило «последний результат»: последняя пересдача провалена →
        # тест в прогрессе НЕ засчитан, несмотря на прошлый зачёт
        total, rows = await self._progress(course.id)
        assert total == 2
        assert rows[0].passed_tests == frozenset()

        # материал в прогрессе учитывается отметкой
        async with await _fresh_session() as db:
            made = await cs.complete_material(db, p, material)
            await db.commit()
        assert made is True
        async with await _fresh_session() as db:
            made_again = await cs.complete_material(db, p, material)
            await db.commit()
        assert made_again is False  # идемпотентна

    @staticmethod
    async def _progress(course_id):
        from app.services.learning import courses_service as cs

        async with await _fresh_session() as db:
            return await cs.compute_progress(db, course_id)


class TestAttemptLimits:
    async def test_limit_counts_only_submitted_and_abandoned_frees(self):
        from app.services.learning import tests_service as ts

        b = Builder()
        await b.course()
        item = await b.test_item(max_attempts=2)
        uid = await b.enroll_staff()
        p = _staff(uid)
        q = await b.add_question(item)
        qm = await b.question_map([q])
        right = list(qm[str(q)]["correct"])

        async with await _fresh_session() as db:
            a, _ = await ts.start_attempt(db, p, item=item, course_published=True)
            _, sc = await ts.submit_attempt(db, p, a.id, {str(q): right})
            await db.commit()
        assert sc == 100

        # брошенная 25 часов назад попытка: не считается отправленной и не
        # возобновляется — старт создаёт свежую
        async with await _fresh_session() as db:
            db.add(
                LearningTestAttempt(
                    test_item_id=item.id,
                    user_id=uid,
                    started_at=datetime.now(UTC) - timedelta(hours=25),
                    answers={},
                )
            )
            await db.commit()

        async with await _fresh_session() as db:
            second, created2 = await ts.start_attempt(db, p, item=item, course_published=True)
            await db.commit()
        assert created2 is True

        async with await _fresh_session() as db:
            _, sc2 = await ts.submit_attempt(db, p, second.id, {str(q): right})
            await db.commit()
        assert sc2 == 100

        # теперь 2 отправленные → лимит исчерпан, даже если брошенная «висит»
        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e:
                await ts.start_attempt(db, p, item=item, course_published=True)
            assert e.value.status_code == 409
            assert "Лимит" in e.value.detail

        rows, submitted, remaining = await self._my(p, item.id)
        assert submitted == 2
        assert any(a.abandoned_at is not None for a in rows)
        assert remaining == 0

    @staticmethod
    async def _my(p, item_id):
        from app.services.learning import tests_service as ts

        async with await _fresh_session() as db:
            return await ts.my_attempts(db, p, item_id)


# ── гейты доступа ────────────────────────────────────────────────────────────


class TestAccessGates:
    async def test_draft_course_and_non_enrolled_are_unavailable(self):
        from app.api.learning import me_routes as mr
        from app.services.learning import courses_service as cs

        b = Builder()
        course = await b.course(status_="draft")
        item = await b.test_item()
        stranger_uid = await b.enroll_staff()  # зачислен, но курс черновик
        p_stranger = _staff(stranger_uid)

        with pytest.raises(HTTPException) as e:
            async with await _fresh_session() as db:
                await cs.get_published_course_by_slug(db, course.slug)
        assert e.value.status_code == 404

        # через хендлер: черновик недоступен даже зачисленному
        with pytest.raises(HTTPException) as e2:
            async with await _fresh_session() as db:
                await mr.start_attempt(item_id=item.id, participant=p_stranger, db=db)
        assert e2.value.status_code == 404

    async def test_foreign_attempt_hidden(self):
        from app.api.learning import me_routes as mr
        from app.services.learning import tests_service as ts

        b = Builder()
        await b.course()
        item = await b.test_item()
        await b.add_question(item)
        owner_uid = await b.enroll_staff()
        other_uid = await b.enroll_staff()

        async with await _fresh_session() as db:
            attempt, _ = await ts.start_attempt(
                db, _staff(owner_uid), item=item, course_published=True
            )
            await db.commit()

        with pytest.raises(HTTPException) as e:
            async with await _fresh_session() as db:
                await mr.attempt_state(attempt_id=attempt.id, participant=_staff(other_uid), db=db)
        assert e.value.status_code == 404

        # у владельца видно состояние открытой попытки без ответов на ответы
        async with await _fresh_session() as db:
            view = await mr.attempt_state(
                attempt_id=attempt.id, participant=_staff(owner_uid), db=db
            )
        assert view.status == "open"
        payload = view.model_dump(mode="json")
        flat = str(payload)
        assert '"is_correct"' not in flat and "correct" not in flat


# ── сотрудник портала через портальную сессию ────────────────────────────────


class TestStaffPortalAccess:
    async def test_staff_via_portal_cookie_courses_and_completion(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        from httpx import ASGITransport, AsyncClient

        from app.services.session import save_session

        b = Builder()
        await b.course(slug="sotrudnik-portal")
        await b.test_item(pass_score=1)
        await b.material_item()
        uid = await b.enroll_staff()
        await save_session(
            redis_client,
            "sid-staff-portal",
            {"user_id": str(uid), "auth_source": "local"},
        )

        app.state.redis = redis_client
        xsrf = "xsrf-staff"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "Origin": "http://test",
                "Cookie": f"portal_session=sid-staff-portal; XSRF-TOKEN={xsrf}",
                "X-XSRF-TOKEN": xsrf,
            },
            follow_redirects=False,
        ) as client:
            r = await client.get("/api/v1/learning/me/courses")
            assert r.status_code == 200
            assert [c["slug"] for c in r.json()] == ["sotrudnik-portal"]

            r = await client.get("/api/v1/learning/me/courses/sotrudnik-portal")
            assert r.status_code == 200
            detail = r.json()
            assert detail["progress_total"] == 2
            mat = next(i for i in detail["items"] if i["type"] == "material")
            assert mat["completed"] is False and mat["has_file"] is False

            r = await client.post(f"/api/v1/learning/me/items/{mat['id']}/complete")
            assert r.status_code == 200
            assert r.json()["already_completed"] is False

            r = await client.get("/api/v1/learning/me/courses/sotrudnik-portal")
            assert r.json()["progress_completed"] == 1
            mat2 = next(i for i in r.json()["items"] if i["type"] == "material")
            assert mat2["completed"] is True

        await redis_client.delete("session:sid-staff-portal")

    async def test_my_course_list_empty_draft_and_published(self):
        from app.services.learning import courses_service as cs

        b = Builder()
        await b.course(status_="draft")
        await b.test_item()
        staff_enrolled = await b.enroll_staff()
        other = await b.enroll_staff()
        p_enrolled = _staff(staff_enrolled)
        p_other = _staff(other)

        # зачислен, но курс черновик → пусто; без зачислений → пусто
        async with await _fresh_session() as db:
            assert await cs.my_course_list(db, p_enrolled) == []
        async with await _fresh_session() as db:
            assert await cs.my_course_list(db, p_other) == []

        # публикация открывает доступ; счётчики (пройдено 0, всего 1)
        await b.set_status("published")
        async with await _fresh_session() as db:
            rows = await cs.my_course_list(db, p_enrolled)
        assert len(rows) == 1
        # (курс, пройдено, всего, категория_название, категория_порядок) — 109
        course_row, completed, total, cat_title, cat_sort = rows[0]
        assert course_row.slug.startswith("t-")
        assert (completed, total) == (0, 1)
        assert cat_title is None and cat_sort is None

    async def test_complete_material_rejects_test_item(self):
        from app.services.learning import courses_service as cs

        b = Builder()
        await b.course()
        item = await b.test_item()
        uid = await b.enroll_staff()

        with pytest.raises(HTTPException) as e:
            async with await _fresh_session() as db:
                await cs.complete_material(db, _staff(uid), item)
        assert e.value.status_code == 422


# ── сквозной API-флоу внешней учётки ─────────────────────────────────────────


class TestLearnerApiFlow:
    async def test_login_see_course_take_test_via_cookie(
        self, app, redis_client, live_limiter, monkeypatch
    ):
        _enable_module(monkeypatch)
        from httpx import ASGITransport, AsyncClient

        from app.services.learning.sessions import build_login_payload, save_session

        b = Builder()
        await b.course(slug="dvizhok-api")
        item = await b.test_item(pass_score=1, max_attempts=1)
        uid_q = await b.add_question(item, options=(("верно", True), ("неверно", False)))
        qm = await b.question_map([uid_q])
        aid = await b.enroll_account()

        payload = build_login_payload(str(aid))
        await save_session(redis_client, "sid-engine-flow", str(aid), payload)

        app.state.redis = redis_client  # deps get_redis берёт отсюда
        ip = f"10.77.7.{uuid.uuid4().int % 200 + 2}"
        # POST на /me/* идёт с double-submit CSRF-парой, как реальный SPA
        xsrf = "xsrf-engine-flow"
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "Origin": "http://test",
                "X-Real-IP": ip,
                "Cookie": f"learning_session=sid-engine-flow; XSRF-TOKEN={xsrf}",
                "X-XSRF-TOKEN": xsrf,
            },
            follow_redirects=False,
        ) as client:
            r = await client.get("/api/v1/learning/me/courses")
            assert r.status_code == 200
            body = r.json()
            assert len(body) == 1 and body[0]["slug"] == "dvizhok-api"

            r = await client.post(f"/api/v1/learning/me/tests/{item.id}/attempts")
            assert r.status_code == 200
            view = r.json()
            attempt_id = view["id"]
            assert view["status"] == "open"
            assert len(view["questions"]) == 1
            q_view = view["questions"][0]
            assert all("is_correct" not in o for o in q_view["options"])

            wrong = str(qm[str(uid_q)]["options"]["неверно"])
            r = await client.post(
                f"/api/v1/learning/me/attempts/{attempt_id}/submit",
                json={"answers": {str(uid_q): [wrong]}},
            )
            assert r.status_code == 200
            res = r.json()
            assert res["status"] == "submitted"
            assert res["passed"] is False and res["score"] == 0

            # лимит max_attempts=1: новая попытка → 409
            r = await client.post(f"/api/v1/learning/me/tests/{item.id}/attempts")
            assert r.status_code == 409

        await redis_client.delete("learning_session:sid-engine-flow")

    async def test_no_cookie_unauthorized(self, app, redis_client, live_limiter, monkeypatch):
        _enable_module(monkeypatch)
        from httpx import ASGITransport, AsyncClient

        app.state.redis = redis_client
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Origin": "http://test"}
        ) as client:
            r = await client.get("/api/v1/learning/me/courses")
            assert r.status_code == 401


class TestEditLockConcurrency:
    """Ревью 2026-08-28 (P1): замок правки и старт попытки сериализуются на
    FOR UPDATE одной строки learning_tests — старт не может вклиниться между
    проверкой «нет попыток» и правкой конфигурации."""

    async def test_edit_waits_for_start_lock_then_409(self):
        from app.models.learning import LearningTest
        from app.services.learning import tests_service as ts

        b = Builder()
        await b.course()
        item = await b.test_item()
        uid = await b.enroll_staff()
        p = _staff(uid)
        # попытке нужен хотя бы один вопрос с вариантами
        await b.add_question(item)

        # Сессия A держит строку настроек — критическая секция start_attempt
        # (FOR UPDATE), попытка ещё не создана.
        a = await _fresh_session()
        try:
            await a.execute(
                select(LearningTest).where(LearningTest.item_id == item.id).with_for_update()
            )

            pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

            async def edit_settings():
                async with await _fresh_session() as b_db:
                    pid = (await b_db.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                    pid_ready.set_result(int(pid))
                    await ts.update_settings(
                        b_db,
                        item,
                        pass_score=90,
                        max_attempts=None,
                        shuffle_questions=None,
                        shuffle_answers=None,
                    )
                    await b_db.commit()

            task = asyncio.create_task(edit_settings())
            blocked_pid = await asyncio.wait_for(pid_ready, timeout=2)
            await _wait_until_db_lock(blocked_pid)
            # Правка действительно дошла до PostgreSQL и ждёт row-lock A.
            assert not task.done(), "правка не ждала FOR UPDATE строки learning_tests"

            # Внутри того же лока A завершает старт попытки и коммитит.
            attempt, created = await ts.start_attempt(a, p, item=item, course_published=True)
            await a.commit()
            assert created is True
            _ = attempt
        finally:
            await a.close()

        # Лок отпущен: правка доходит до проверки «есть попытки» → 409.
        with pytest.raises(HTTPException) as e:
            await asyncio.wait_for(task, timeout=5)
        assert e.value.status_code == 409

    async def test_start_rechecks_item_after_delete_wins_lock(self):
        """Обратный порядок: delete коммитится первым, stale start получает 404."""
        from app.services.learning import courses_service as cs
        from app.services.learning import tests_service as ts

        b = Builder()
        await b.course()
        item = await b.test_item()
        uid = await b.enroll_staff()
        participant = _staff(uid)
        await b.add_question(item)

        deleter = await _fresh_session()
        try:
            # Тот же lock, который берёт production delete_item.
            await ts.assert_test_editable(deleter, item.id, denied="удаление запрещено")
            live_item = await cs.get_item(deleter, item.id)
            assert live_item is not None
            await cs.soft_delete_item(deleter, live_item)

            pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

            async def stale_start():
                async with await _fresh_session() as starter:
                    pid = (await starter.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                    pid_ready.set_result(int(pid))
                    await ts.start_attempt(
                        starter,
                        participant,
                        item=item,
                        course_published=True,
                    )
                    await starter.commit()

            task = asyncio.create_task(stale_start())
            blocked_pid = await asyncio.wait_for(pid_ready, timeout=2)
            await _wait_until_db_lock(blocked_pid)
            assert not task.done(), "start не ждал lock удаления теста"

            await deleter.commit()
        finally:
            await deleter.close()

        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(task, timeout=5)
        assert exc.value.status_code == 404

    async def test_started_attempt_blocks_edit_and_question_crud(self):
        from app.services.learning import tests_service as ts

        b = Builder()
        await b.course()
        item = await b.test_item()
        uid = await b.enroll_staff()
        p = _staff(uid)
        q_id = await b.add_question(item)

        async with await _fresh_session() as db:
            attempt, created = await ts.start_attempt(db, p, item=item, course_published=True)
            await db.commit()
        assert created is True and attempt.submitted_at is None
        async with await _fresh_session() as db2:
            q_model = await ts.get_question(db2, q_id)
        assert q_model is not None

        # Попытка НАЧАТА (не отправлена): замок уже действует.
        async with await _fresh_session() as db:
            with pytest.raises(HTTPException) as e:
                await ts.update_settings(
                    db,
                    item,
                    pass_score=50,
                    max_attempts=None,
                    shuffle_questions=None,
                    shuffle_answers=None,
                )
            assert e.value.status_code == 409
            with pytest.raises(HTTPException):
                await ts.add_question(
                    db,
                    item,
                    text="Ещё?",
                    multi=False,
                    options=({"text": "да", "is_correct": True},),
                )
            with pytest.raises(HTTPException):
                await ts.delete_question(db, q_model)
            await db.rollback()


async def test_attempts_composite_indexes_exist():
    """§7 ТЗ: попытки индексированы по (тест, участник) — история/лимимт
    фильтруют по test_item_id + конкретному участнику (ревью инкремента 6,
    P3; миграция 104)."""
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE tablename = 'learning_test_attempts' "
                        "AND indexname IN ("
                        "'idx_learning_attempts_test_user', "
                        "'idx_learning_attempts_test_account')"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert set(rows) == {
        "idx_learning_attempts_test_user",
        "idx_learning_attempts_test_account",
    }
