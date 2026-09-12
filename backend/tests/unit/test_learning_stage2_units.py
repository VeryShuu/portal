"""Unit-тесты веток этапа 2, которые на CI недостижимы через integration-контур
(coverage-артефакт integration-джобы частичен): гонки сертификата, ветки
bulk-зачисления, дедлайн в update_course, таймер сабмита, _collect_certified.

Все тесты герметичны: стабы db/monkeypatch вместо HTTP и БД.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from app.models.learning import LearningCertificate
from app.services.learning import certificates as cert_svc
from app.services.learning import courses_service as cs
from app.services.learning import tests_service as ts


class _Result:
    """Стаб db.execute: scalar_one_or_none / scalars().all() / first()."""

    def __init__(
        self,
        *,
        scalar: Any = None,
        scalars_all: list[Any] | None = None,
        first: Any = None,
        all_rows: list[Any] | None = None,
    ):
        self._scalar = scalar
        self._scalars_all = scalars_all or []
        self._first = first
        self._all_rows = all_rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars_all)

    def first(self):
        return self._first

    def all(self):
        return self._all_rows


class _FakeDb:
    """Стаб AsyncSession: последовательность результатов execute + события."""

    def __init__(
        self,
        results: list[_Result] | None = None,
        *,
        flush_error: Exception | None = None,
        flush_error_from: int = 2,
    ):
        self.results = list(results or [])
        self.executed = 0
        self.flush_calls = 0
        self.rollback_calls = 0
        self.commit_calls = 0
        self.added: list[Any] = []
        self.flush_error = flush_error
        self.flush_error_from = flush_error_from
        self.nested_exits: list[bool] = []  # True — выход с исключением (rollback)

    async def execute(self, _query):
        idx = min(self.executed, len(self.results) - 1) if self.results else 0
        res = self.results[idx] if self.results else _Result()
        self.executed += 1
        return res

    async def flush(self):
        self.flush_calls += 1
        if self.flush_error is not None and self.flush_calls >= self.flush_error_from:
            raise self.flush_error

    async def rollback(self):
        self.rollback_calls += 1

    async def commit(self):
        self.commit_calls += 1

    def add(self, obj):
        self.added.append(obj)

    def begin_nested(self):
        """Стаб SAVEPOINT (ревью 2026-08-30: зачисление/сертификат в nested)."""
        outer = self

        class _Nested:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                outer.nested_exits.append(exc_type is not None)
                return False  # исключение пробрасывается вызывающему

        return _Nested()


def _participant(*, account: bool = False) -> Any:
    if account:
        return SimpleNamespace(
            kind="acc",
            user_id=None,
            learning_account_id=uuid.uuid4(),
            display_name="Внешний Ученик",
            email="acc@example.com",
        )
    return SimpleNamespace(
        kind="user",
        user_id=uuid.uuid4(),
        learning_account_id=None,
        display_name="Сотрудник Ученик",
        email="staff@example.com",
    )


def _course() -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        slug="kurs-1",
        title="Курс",
        # зачисление проходит гард публикации (2026-09-03): фейк — published
        status="published",
        deadline_at=None,
        updated_at=None,
        description=None,
        title_field=None,
    )


# ── get_certificate: обе ветки принципала ────────────────────────────────────


class TestGetCertificate:
    async def test_account_branch_and_return(self):
        found = LearningCertificate()
        db = _FakeDb([_Result(scalar=found)])
        participant = _participant(account=True)
        out = await cert_svc.get_certificate(db, uuid.uuid4(), participant)
        assert out is found

    async def test_user_branch(self):
        db = _FakeDb([_Result(scalar=None)])
        participant = _participant()
        out = await cert_svc.get_certificate(db, uuid.uuid4(), participant)
        assert out is None


# ── ensure_certificate: ранний выход, 404, happy, 503, гонка ─────────────────


class TestEnsureCertificate:
    async def test_existing_returns_without_reissue(self):
        existing = LearningCertificate()
        db = _FakeDb([_Result(scalar=existing)])
        cert, created = await cert_svc.ensure_certificate(db, _course(), _participant(), items=[])
        assert created is False and cert is existing

    async def test_incomplete_items_raises_404(self):
        db = _FakeDb([_Result(scalar=None)])
        items = [SimpleNamespace(completed=False)]
        with pytest.raises(HTTPException) as exc:
            await cert_svc.ensure_certificate(db, _course(), _participant(), items=cast(Any, items))
        assert exc.value.status_code == 404

    async def test_happy_path_writes_file_and_returns_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from app.services.learning import courses_service as cs

        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        monkeypatch.setattr("app.core.pdf.render_pdf", _fake_render, raising=False)

        async def fake_render(html: str) -> bytes:
            return b"%PDF-1.4 unit"

        monkeypatch.setattr("app.core.pdf.render_pdf", fake_render)

        db = _FakeDb([_Result(scalar=None)])
        course = _course()
        items = [SimpleNamespace(completed=True)]
        cert, created = await cert_svc.ensure_certificate(
            cast(Any, db),
            cast(Any, course),
            cast(Any, _participant()),
            items=cast(Any, items),
        )
        assert created is True
        assert cert.serial.startswith("LC-")
        assert cert.pdf_path.endswith(".pdf")

        assert Path(cert.pdf_path).is_file()

    async def test_render_failure_raises_503(self, monkeypatch: pytest.MonkeyPatch):
        db = _FakeDb([_Result(scalar=None)])
        items = [SimpleNamespace(completed=True)]

        async def broken_render(html: str) -> bytes:
            raise RuntimeError("down")

        monkeypatch.setattr("app.core.pdf.render_pdf", broken_render)
        with pytest.raises(HTTPException) as exc:
            await cert_svc.ensure_certificate(
                cast(Any, db),
                cast(Any, _course()),
                cast(Any, _participant()),
                items=cast(Any, items),
            )
        assert exc.value.status_code == 503

    async def test_race_loses_insert_returns_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Гонка (ревью 2026-08-30): IntegrityError на ЕДИНСТВЕННОМ flush
        вставки — savepoint откатывается, победитель перечитывается
        (арбитр — частичный уникальный индекс), без 500."""
        from sqlalchemy.exc import IntegrityError

        from app.services.learning import courses_service as cs

        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))

        async def fake_render(html: str) -> bytes:
            return b"%PDF-1.4 x"

        monkeypatch.setattr("app.core.pdf.render_pdf", fake_render)

        existing = LearningCertificate()
        # execute №1: get_certificate → None; execute №2: перечитка → existing
        db = _FakeDb(
            [_Result(scalar=None), _Result(scalar=existing)],
            flush_error=IntegrityError("dup", None, Exception("uniq")),
            flush_error_from=1,
        )

        cert, created = await cert_svc.ensure_certificate(
            cast(Any, db),
            cast(Any, _course()),
            cast(Any, _participant()),
            items=cast(Any, [SimpleNamespace(completed=True)]),
        )
        assert created is False and cert is existing
        # savepoint откатился с ошибкой; внешний rollback не зовётся
        assert db.rollback_calls == 0
        assert db.nested_exits == [True]


async def _fake_render(html: str) -> bytes:  # pragma: no cover — заменяется в тестах
    return b""


# ── update_course: ветка дедлайна ────────────────────────────────────────────


class TestUpdateCourseDeadline:
    async def test_explicit_none_clears_deadline(self):
        from datetime import UTC, datetime

        course = SimpleNamespace(
            slug="s", title="T", description=None, deadline_at=datetime.now(UTC), updated_at=None
        )
        db = _FakeDb()
        await cs.update_course(
            cast(Any, db),
            cast(Any, course),
            title=None,
            description=None,
            slug=None,
            deadline_at=None,
        )
        assert course.deadline_at is None

    async def test_absent_key_keeps_deadline(self):
        from datetime import UTC, datetime

        keep = datetime.now(UTC)
        course = SimpleNamespace(
            slug="s", title="T", description=None, deadline_at=keep, updated_at=None
        )
        db = _FakeDb()
        await cs.update_course(
            cast(Any, db), cast(Any, course), title="Новое", description=None, slug=None
        )
        assert course.deadline_at is keep
        assert course.title == "Новое"


# ── enroll_participants_bulk: дубли/неизвестные/письма ───────────────────────


class TestEnrollParticipantsBulk:
    async def test_mixed_batch(self, monkeypatch: pytest.MonkeyPatch):
        existing_uid = uuid.uuid4()
        known1, known2, unknown = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        users = [
            SimpleNamespace(id=known1, full_name="А", email="a@x"),
            SimpleNamespace(id=known2, full_name="Б", email="b@x"),
        ]

        db = _FakeDb([_Result(scalars_all=[existing_uid])])  # существующие участники
        dba = _FakeDb([_Result(scalars_all=users)])  # users по основному движку
        course = _course()

        letters: list[str] = []

        async def fake_enqueue(db: Any, **kw: Any) -> None:
            letters.append(kw["to_email"])

        monkeypatch.setattr(
            "app.services.learning.courses_service.enqueue_outbox_email", fake_enqueue
        )

        enrolled, skipped, errors = await cs.enroll_participants_bulk(
            cast(Any, db),
            cast(Any, dba),
            cast(Any, course),
            user_ids=[existing_uid, known1, unknown, known2],
            enrolled_by=None,
        )
        assert (enrolled, skipped) == (2, 1)
        assert errors == [{"user_id": str(unknown), "message": "Сотрудник не найден"}]
        assert sorted(letters) == ["a@x", "b@x"]
        assert len(db.added) == 2

    async def test_empty_batch_is_noop(self, monkeypatch: pytest.MonkeyPatch):
        async def fake_enqueue(db: Any, **kw: Any) -> None:
            return None

        monkeypatch.setattr(
            "app.services.learning.courses_service.enqueue_outbox_email", fake_enqueue
        )
        enrolled, skipped, errors = await cs.enroll_participants_bulk(
            cast(Any, _FakeDb()),
            cast(Any, _FakeDb()),
            cast(Any, _course()),
            user_ids=[],
            enrolled_by=None,
        )
        assert (enrolled, skipped, errors) == (0, 0, [])


# ── _collect_certified: оба типа принципала ──────────────────────────────────


class TestCollectCertified:
    async def test_kinds_mapped(self):
        uid, aid = uuid.uuid4(), uuid.uuid4()
        db = _FakeDb([_Result(all_rows=[(uid, None), (None, aid)])])
        certified = await cs._collect_certified(cast(Any, db), uuid.uuid4())
        assert ("user", uid) in certified
        assert ("acc", aid) in certified

    async def test_empty(self):
        db = _FakeDb([_Result(all_rows=[])])
        assert await cs._collect_certified(cast(Any, db), uuid.uuid4()) == frozenset()


# ── update_settings: таймер ──────────────────────────────────────────────────


class TestUpdateSettingsTimeLimit:
    async def _run(self, *, provided: bool, value: int | None) -> SimpleNamespace:
        test = SimpleNamespace(
            pass_score=70,
            max_attempts=3,
            shuffle_questions=False,
            shuffle_answers=False,
            time_limit_minutes=30,
        )
        item = SimpleNamespace(id=uuid.uuid4(), type="test")
        # execute: 1) assert_test_editable FOR UPDATE, 2) attempts check,
        # 3) update statements
        db = _FakeDb([_Result(first=None), _Result(first=None), _Result(scalar=test), _Result()])
        await ts.update_settings(
            cast(Any, db),
            cast(Any, item),
            pass_score=None,
            max_attempts=None,
            shuffle_questions=None,
            shuffle_answers=None,
            time_limit_minutes=value,
            time_limit_provided=provided,
        )
        return test

    async def test_explicit_none_clears_limit(self):
        test = await self._run(provided=True, value=None)
        assert test.time_limit_minutes is None

    async def test_explicit_value_sets_limit(self):
        test = await self._run(provided=True, value=45)
        assert test.time_limit_minutes == 45

    async def test_not_provided_keeps_limit(self):
        test = await self._run(provided=False, value=None)
        assert test.time_limit_minutes == 30


# ── submit_attempt: ветки «уже отправлена» и таймера ─────────────────────────


class TestSubmitAttemptBranches:
    async def test_already_submitted_raises_409(self, monkeypatch: pytest.MonkeyPatch):
        attempt = SimpleNamespace(submitted_at=datetime.now(UTC))
        monkeypatch.setattr(ts, "_owned_attempt", _mk_async(cast(Any, attempt)))
        with pytest.raises(HTTPException) as exc:
            await ts.submit_attempt(
                cast(Any, _FakeDb()), cast(Any, _participant()), uuid.uuid4(), {}
            )
        assert exc.value.status_code == 409

    async def test_missing_test_raises_404(self, monkeypatch: pytest.MonkeyPatch):
        attempt = SimpleNamespace(
            submitted_at=None,
            started_at=datetime.now(UTC),
            abandoned_at=None,
            answers={},
            test_item_id=uuid.uuid4(),
        )
        monkeypatch.setattr(ts, "_owned_attempt", _mk_async(cast(Any, attempt)))
        monkeypatch.setattr(ts, "get_test", _mk_async(None))
        with pytest.raises(HTTPException) as exc:
            await ts.submit_attempt(
                cast(Any, _FakeDb()), cast(Any, _participant()), uuid.uuid4(), {}
            )
        assert exc.value.status_code == 404

    async def test_expired_attempt_committed_and_409(self, monkeypatch: pytest.MonkeyPatch):
        started = datetime.now(UTC) - timedelta(minutes=10)
        attempt = SimpleNamespace(
            submitted_at=None,
            started_at=started,
            abandoned_at=None,
            answers={},
            test_item_id=uuid.uuid4(),
        )
        monkeypatch.setattr(ts, "_owned_attempt", _mk_async(cast(Any, attempt)))
        test = SimpleNamespace(pass_score=70, time_limit_minutes=1)
        monkeypatch.setattr(ts, "get_test", _mk_async(cast(Any, test)))

        db = _FakeDb()
        with pytest.raises(HTTPException) as exc:
            await ts.submit_attempt(cast(Any, db), cast(Any, _participant()), uuid.uuid4(), {})
        assert exc.value.status_code == 409
        assert "истекло" in exc.value.detail
        assert attempt.abandoned_at is not None
        assert db.commit_calls == 1  # клеймо переживает 409


class TestFileResponse:
    async def test_missing_file_raises_404(self, tmp_path: Path):
        cert = cast(
            Any,
            SimpleNamespace(
                id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                serial="LC-TEST",
                pdf_path=str(tmp_path / "nope.webp"),
            ),
        )
        with pytest.raises(HTTPException) as exc:
            await cert_svc.file_response(cert)
        assert exc.value.status_code == 404

    async def test_stream_yields_file_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from app.services.learning import courses_service as cs

        monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path))
        cert = cast(
            Any,
            SimpleNamespace(
                id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                serial="LC-TEST",
                pdf_path="",
            ),
        )
        dest = cert_svc.certificate_pdf_path(cert.course_id, cert.id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4-a" + b"x" * 2048)  # > одного чанка? нет — один
        cert.pdf_path = str(dest)

        resp = await cert_svc.file_response(cert)
        raw = [c async for c in resp.body_iterator]  # type: ignore[attr-defined]
        body = b"".join(bytes(c) for c in raw)  # type: ignore[arg-type]
        assert body.startswith(b"%PDF-1.4-a")


def _mk_async(value: Any):
    async def _inner(*args: Any, **kwargs: Any):
        return value

    return _inner


# ── _completed_for ───────────────────────────────────────────────────────────


class TestCompletedFor:
    def test_returns_completed_union(self):
        from app.worker.tasks.learning_deadlines import _completed_for

        pid = uuid.uuid4()
        row = SimpleNamespace(
            participant_id=pid,
            completed_items=frozenset({uuid.uuid4()}),
            passed_tests=frozenset({uuid.uuid4()}),
        )
        assert _completed_for([row], pid) == 2
        assert _completed_for([row], uuid.uuid4()) == 0
