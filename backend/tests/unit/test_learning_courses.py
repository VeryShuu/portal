"""Unit-тесты чистой логики курсов (инкремент 2 + ревью 2026-08-28): slug-генератор,
письмо и ссылки зачисления, сборка ответа прогресса, валидация схем элементов."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.learning import courses_service as cs
from app.services.learning import emails


class TestSlugify:
    def test_cyrillic_transliterated(self):
        assert cs.slugify("Охрана труда") == "ohrana-truda"

    def test_lower_and_hyphens(self):
        assert cs.slugify("Безопасность 2026!") == "bezopasnost-2026"

    def test_trims_and_collapses_separators(self):
        assert cs.slugify("  --Привет,   мир--  ") == "privet-mir"

    def test_length_capped(self):
        assert len(cs.slugify("а" * 500)) <= 140

    def test_non_empty_fallback(self):
        assert cs.slugify("!!!???") == "course"


class TestEnrollmentLetter:
    def test_contains_course_title_and_link(self):
        subject, body, _html = emails.enrollment_letter(
            full_name="Иван",
            course_title="Пожарная безопасность",
            link="https://learn.mage.ru/courses/pozharnaya-bezopasnost",
        )
        assert "зачислены" in subject and "Пожарная безопасность" in subject
        assert "Иван" in body
        assert "Вы зачислены на курс «Пожарная безопасность»" in body
        assert "Перейдите по ссылке" in body
        assert "https://learn.mage.ru/courses/pozharnaya-bezopasnost" in body

    def test_html_part_is_filled_and_escapes(self):
        """HTML-часть обязательна: отправитель кладёт её в multipart/alternative
        всегда, и клиенты вроде Outlook показывали пустое письмо
        (прод-кейс 2026-09-03). Пользовательские строки — экранированные."""
        _subject, _text, html = emails.enrollment_letter(
            full_name="Иван <script>",
            course_title="Курс «А» & Б",
            link="https://portal.example.org/learning/courses/kurs?a=1&b=2",
        )
        assert html.strip()  # не пустота
        assert "<script>" not in html
        assert "Иван &lt;script&gt;" in html
        assert "Курс «А» &amp; Б" in html
        assert 'href="https://portal.example.org/learning/courses/kurs?a=1&amp;b=2"' in html


class TestEnrollRequiresPublishedCourse:
    """Зачисление на черновик запрещено: курс невидим участнику (published-фильтр
    списка «мои курсы» и 404 по прямой ссылке), письмо уходило в никуда
    (прод-кейс 2026-09-02). Гард срабатывает до обращения к БД — db=None."""

    @staticmethod
    def _draft_course() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), slug="kurs", title="Курс", status="draft")

    async def test_single_enroll_on_draft_is_409(self):
        with pytest.raises(HTTPException) as ei:
            await cs.enroll_participant(
                None,  # type: ignore[arg-type]
                self._draft_course(),
                user_id=uuid.uuid4(),
                display_name="Иван",
                email="i@x.ru",
                enrolled_by=None,
            )
        assert ei.value.status_code == 409
        assert "опубликов" in str(ei.value.detail)

    async def test_bulk_enroll_on_draft_is_409(self):
        with pytest.raises(HTTPException) as ei:
            await cs.enroll_participants_bulk(
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
                self._draft_course(),
                user_ids=[uuid.uuid4()],
                enrolled_by=None,
            )
        assert ei.value.status_code == 409


class TestCourseLink:
    """§6.1: сотрудники — портал с префиксом /learning/courses/,
    внешние — learn-домен без префикса (ревью 2026-08-28)."""

    def test_staff_link_uses_portal_prefix(self, monkeypatch: pytest.MonkeyPatch):
        from types import SimpleNamespace

        from app.core import system_config

        monkeypatch.setattr(
            system_config,
            "load_system_settings",
            lambda: SimpleNamespace(portal_base_url="https://portal.example.org"),
        )
        link = cs.course_link(course_slug="kurs-1", is_staff=True)
        assert link == "https://portal.example.org/learning/courses/kurs-1"

    def test_external_link_uses_learn_domain_without_prefix(self):
        from app.services.learning.accounts_service import LEARN_BASE_URL

        link = cs.course_link(course_slug="kurs-1", is_staff=False)
        assert link == f"{LEARN_BASE_URL}/courses/kurs-1"
        assert "/learning/courses/" not in link


class TestItemUrlScheme:
    """ItemUpdate валидирует схему url так же, как ItemCreate (ревью 2026-08-28);
    материал допустимо создать без url — PDF прикладывается отдельным вызовом."""

    def test_create_material_without_url_is_allowed(self):
        from app.schemas.learning import ItemCreate

        item = ItemCreate(type="material", title="Инструкция")
        assert item.url is None

    def test_update_rejects_non_http_scheme(self):
        from app.schemas.learning import ItemUpdate

        with pytest.raises(ValidationError):
            ItemUpdate(url="javascript:alert(1)")

    def test_update_accepts_https(self):
        from app.schemas.learning import ItemUpdate

        assert ItemUpdate(url="https://example.com/a.pdf").url == "https://example.com/a.pdf"


class TestProgressToApi:
    def test_completed_sums_materials_and_tests(self):
        now = datetime.now(UTC)
        pid = uuid.uuid4()
        row = cs.ProgressRow(
            participant_id=pid,
            kind="external",
            display_name="Внешний Ученик",
            email="ext@example.com",
            enrolled_at=now,
            completed_items=frozenset({uuid.uuid4()}),
            passed_tests=frozenset({uuid.uuid4(), uuid.uuid4()}),
        )
        out = cs.progress_to_api(uuid.uuid4(), total_items=4, rows=[row])
        p = out["participants"][0]
        assert p["progress_completed"] == 3
        assert p["progress_total"] == 4
        assert p["participant_kind"] == "external"
        assert uuid.UUID(p["id"]) == pid


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def first(self):
        return self._value


class _FakeDb:
    """Минимальный AsyncSession-дублер для create/update курса."""

    def __init__(self):
        self.added = []
        self.flushes = 0

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(None)

    async def flush(self):
        self.flushes += 1

    async def rollback(self):
        pass


class TestDescriptionRichText:
    """Описание курса — rich-text (тот же редактор, что у новостей/БЗ):
    sanitize_markdown на записи, storage = истина (ревью 2026-08-31)."""

    async def test_create_strips_dangerous_html_keeps_formatting(self, monkeypatch):
        async def _unique_slug(_db, slug, exclude_id=None):
            return slug

        monkeypatch.setattr(cs, "_ensure_unique_slug", _unique_slug)
        db = _FakeDb()
        course = await cs.create_course(
            db,
            title="Курс",
            description="<p>Привет <script>alert(1)</script><strong>мир</strong></p>",
            slug=None,
        )
        assert course.description is not None
        assert "<script>" not in course.description
        assert "alert(1)" not in course.description
        assert "<strong>мир</strong>" in course.description

    async def test_create_empty_after_sanitize_becomes_none(self, monkeypatch):
        async def _unique_slug(_db, slug, exclude_id=None):
            return slug

        monkeypatch.setattr(cs, "_ensure_unique_slug", _unique_slug)
        db = _FakeDb()
        course = await cs.create_course(
            db, title="Курс", description="<script>alert(1)</script>", slug=None
        )
        assert course.description is None

    async def test_create_none_stays_none(self, monkeypatch):
        async def _unique_slug(_db, slug, exclude_id=None):
            return slug

        monkeypatch.setattr(cs, "_ensure_unique_slug", _unique_slug)
        db = _FakeDb()
        course = await cs.create_course(db, title="Курс", description=None, slug=None)
        assert course.description is None

    def _course(self):
        from types import SimpleNamespace

        return SimpleNamespace(slug="kurs", description="старое", title="Курс", deadline_at=None)

    async def test_update_sanitizes_description(self):
        db = _FakeDb()
        course = self._course()
        await cs.update_course(db, course, description="Текст <img src=x onerror=alert(1)>")
        assert course.description is not None
        assert "onerror" not in course.description
        assert "Текст" in course.description

    async def test_update_explicit_none_clears(self):
        db = _FakeDb()
        course = self._course()
        await cs.update_course(db, course, description=None)
        assert course.description is None

    async def test_update_absent_key_keeps_value(self):
        db = _FakeDb()
        course = self._course()
        await cs.update_course(db, course, title="Новое имя")
        assert course.description == "старое"


class TestItemDescription:
    """Описание/комментарий материала — rich-text с sanitize на записи
    (миграция 108, прод-запрос 2026-09-03). Описание задаётся только
    материалу; update: отсутствующий ключ = «не менять», явный null = очистить."""

    @staticmethod
    def _item() -> Any:
        return SimpleNamespace(
            id=uuid.uuid4(),
            course_id=uuid.uuid4(),
            type="material",
            title="Инструктаж",
            url="https://example.org/doc",
            file_path=None,
            description="<p>Старое описание</p>",
            updated_at=None,
        )

    async def test_add_material_sanitizes_description(self, monkeypatch):
        async def _lock(_db, _cid):
            return SimpleNamespace(id=_cid, status="draft")

        async def _items(_db, _cid):
            return []

        monkeypatch.setattr(cs, "lock_course", _lock)
        monkeypatch.setattr(cs, "active_items", _items)
        db = _FakeDb()
        item = await cs.add_item(
            db,
            uuid.uuid4(),
            type_="material",
            title="Материал",
            url="https://example.org/doc",
            description="<p>Смотри <script>alert(1)</script><strong>внимательно</strong></p>",
        )
        assert item.description is not None
        assert "<script>" not in item.description
        assert "alert(1)" not in item.description
        assert "внимательно" in item.description

    async def test_add_test_ignores_description(self, monkeypatch):
        async def _lock(_db, _cid):
            return SimpleNamespace(id=_cid, status="draft")

        async def _items(_db, _cid):
            return []

        monkeypatch.setattr(cs, "lock_course", _lock)
        monkeypatch.setattr(cs, "active_items", _items)
        db = _FakeDb()
        item = await cs.add_item(
            db,
            uuid.uuid4(),
            type_="test",
            title="Тест",
            url=None,
            description="<p>лишнее</p>",
        )
        assert item.description is None

    async def test_update_description_provided_and_clear(self):
        db = _FakeDb()
        item = self._item()
        await cs.update_item(
            db,
            item,
            title=None,
            url=None,
            description="Новое **описание**",
            description_provided=True,
        )
        assert item.description is not None
        assert "**описание**" in item.description

        await cs.update_item(
            db,
            item,
            title=None,
            url=None,
            description=None,
            description_provided=True,
        )
        assert item.description is None

    async def test_update_absent_key_keeps_description(self):
        db = _FakeDb()
        item = self._item()
        await cs.update_item(db, item, title="Новое имя", url=None)
        assert item.description == "<p>Старое описание</p>"

    async def test_update_description_on_test_is_422(self):
        db = _FakeDb()
        item = self._item()
        item.type = "test"
        with pytest.raises(HTTPException) as ei:
            await cs.update_item(
                db,
                item,
                title=None,
                url=None,
                description=None,
                description_provided=True,
            )
        assert ei.value.status_code == 422


class TestCourseCategories:
    """Категория курса (миграция 109): set при создании, PATCH-семантика
    при правке (отсутствующий ключ = «не менять», null = снять)."""

    async def test_create_course_sets_category(self, monkeypatch):
        async def _unique_slug(_db, slug, exclude_id=None):
            return slug

        async def _ensure(_db, _cid):
            return None

        monkeypatch.setattr(cs, "_ensure_unique_slug", _unique_slug)
        monkeypatch.setattr(cs.cats_svc, "ensure_category_exists", _ensure)
        cid = uuid.uuid4()
        db = _FakeDb()
        course = await cs.create_course(
            db, title="Курс", description=None, slug=None, category_id=cid
        )
        assert course.category_id == cid

    async def test_update_course_absent_key_keeps_category(self, monkeypatch):
        async def _ensure(_db, _cid):
            return None

        monkeypatch.setattr(cs.cats_svc, "ensure_category_exists", _ensure)
        db = _FakeDb()
        cat_id = uuid.uuid4()
        course = SimpleNamespace(
            id=uuid.uuid4(),
            slug="s",
            title="t",
            description=None,
            category_id=cat_id,
            updated_at=None,
        )
        await cs.update_course(db, course, title="Новое имя")
        assert course.category_id == cat_id

    async def test_update_course_null_clears_category(self, monkeypatch):
        async def _ensure(_db, _cid):
            return None

        monkeypatch.setattr(cs.cats_svc, "ensure_category_exists", _ensure)
        db = _FakeDb()
        course = SimpleNamespace(
            id=uuid.uuid4(),
            slug="s",
            title="t",
            description=None,
            category_id=uuid.uuid4(),
            updated_at=None,
        )
        await cs.update_course(db, course, category_id=None)
        assert course.category_id is None


class TestSectionItems:
    """Разделы-заголовки (миграция 110): допустимы в опубликованном курсе,
    не создают LearningTest, не участвуют в прогрессе."""

    async def test_add_section_to_published_course(self, monkeypatch):
        async def _lock(_db, _cid):
            return SimpleNamespace(id=_cid, status="published")

        async def _items(_db, _cid):
            return []

        monkeypatch.setattr(cs, "lock_course", _lock)
        monkeypatch.setattr(cs, "active_items", _items)
        db = _FakeDb()
        item = await cs.add_item(
            db, uuid.uuid4(), type_="section", title="Инструкции", url=None, description=None
        )
        assert item.type == "section"
        assert item.title == "Инструкции"
        # одна строка item, без заготовки LearningTest
        assert len(db.added) == 1

    async def test_compute_progress_ignores_sections(self, monkeypatch):
        material = SimpleNamespace(id=uuid.uuid4(), type="material")
        section = SimpleNamespace(id=uuid.uuid4(), type="section")

        async def _items(_db, _cid):
            return [material, section]

        async def _collect_done(_db, ids):
            assert material.id in ids and section.id not in ids
            return {}

        async def _collect_passed(_db, ids):
            return {}

        async def _collect_certified(_db, _cid):
            return {}

        class _RowsResult:
            def scalars(self):
                return self

            def all(self):
                return []

        class _RowsDb:
            async def execute(self, *args, **kwargs):
                return _RowsResult()

        monkeypatch.setattr(cs, "active_items", _items)
        monkeypatch.setattr(cs, "_collect_completed_materials", _collect_done)
        monkeypatch.setattr(cs, "_collect_passed_tests", _collect_passed)
        monkeypatch.setattr(cs, "_collect_certified", _collect_certified)

        total, rows = await cs.compute_progress(_RowsDb(), uuid.uuid4())
        assert total == 1
        assert rows == []


class TestCategoryAndSectionsCoverage:
    """Добор покрытия изменённых веток: set-категории в update, reorder_items,
    get_item, my_course_list (категории + пропуск разделов в прогрессе)."""

    async def test_update_course_sets_non_null_category(self, monkeypatch):
        seen: dict[str, uuid.UUID] = {}

        async def _ensure(_db, cid):
            seen["cid"] = cid

        monkeypatch.setattr(cs.cats_svc, "ensure_category_exists", _ensure)
        db = _FakeDb()
        cat_id = uuid.uuid4()
        course = SimpleNamespace(
            id=uuid.uuid4(),
            slug="s",
            title="t",
            description=None,
            category_id=None,
            updated_at=None,
        )
        await cs.update_course(db, course, category_id=cat_id)
        assert seen["cid"] == cat_id
        assert course.category_id == cat_id

    async def test_reorder_items_assigns_positions(self, monkeypatch):
        i1 = SimpleNamespace(id=uuid.uuid4(), sort_order=0)
        i2 = SimpleNamespace(id=uuid.uuid4(), sort_order=1)

        async def _items(_db, _cid):
            return [i1, i2]

        monkeypatch.setattr(cs, "active_items", _items)
        db = _FakeDb()
        await cs.reorder_items(db, uuid.uuid4(), [i2.id, i1.id])
        assert i2.sort_order == 0
        assert i1.sort_order == 1

    async def test_reorder_items_rejects_incomplete_list(self, monkeypatch):
        i1 = SimpleNamespace(id=uuid.uuid4(), sort_order=0)

        async def _items(_db, _cid):
            return [i1]

        monkeypatch.setattr(cs, "active_items", _items)
        with pytest.raises(HTTPException) as ei:
            await cs.reorder_items(db := _FakeDb(), uuid.uuid4(), [])
        assert ei.value.status_code == 422
        assert db  # db используется только после валидации

    async def test_get_item_returns_row_or_none(self):
        item = SimpleNamespace(id=uuid.uuid4())

        class _Db:
            def __init__(self, value):
                self._value = value

            async def execute(self, *args, **kwargs):
                return _FakeResult(self._value)

        assert await cs.get_item(_Db(item), item.id) is item
        assert await cs.get_item(_Db(None), item.id) is None

    async def test_my_course_list_returns_categories_and_skips_sections(self, monkeypatch):
        cid = uuid.uuid4()
        course = SimpleNamespace(id=cid, slug="kurs", title="Курс")
        material = SimpleNamespace(id=uuid.uuid4(), course_id=cid, type="material")
        section = SimpleNamespace(id=uuid.uuid4(), course_id=cid, type="section")

        class _SeqResult:
            """Последовательный .scalars()/.all() с очередью значений."""

            def __init__(self, value):
                self._value = value

            def scalar_one_or_none(self):
                return self._value

            def scalars(self):
                return self

            def all(self):
                v = self._value
                return v if isinstance(v, list) else [v]

        class _QueueDb:
            def __init__(self, results):
                self._results = list(results)
                self.flushes = 0

            async def execute(self, *args, **kwargs):
                return _SeqResult(self._results.pop(0))

            async def flush(self):
                self.flushes += 1

        db = _QueueDb(
            [
                [cid],  # enrolled ids
                [],  # обязательные «для всех» (пусто)
                [(course, "Инструктажи", 2)],  # курсы + категория (outer join)
                [material, section],  # элементы курса
            ]
        )

        async def _collect_done(_db, ids):
            return {(participant_key, material.id)}

        async def _collect_passed(_db, ids):
            return {}

        monkeypatch.setattr(cs, "_collect_completed_materials", _collect_done)
        monkeypatch.setattr(cs, "_collect_passed_tests", _collect_passed)
        monkeypatch.setattr(
            cs,
            "_completion_of_key",
            lambda done, passed, key: ({material.id} if done else set(), set()),
        )

        participant = SimpleNamespace(
            kind=cs.KIND_USER,
            user_id="u1",
            learning_account_id=None,
            key=lambda: participant_key,
            matching=lambda model: True,
        )
        participant_key = ("user", "u1")

        rows = await cs.my_course_list(db, participant)
        assert len(rows) == 1
        c, completed, total, cat_title, cat_sort = rows[0]
        assert c.id == cid
        assert (completed, total) == (1, 1)  # раздел не считается
        assert (cat_title, cat_sort) == ("Инструктажи", 2)


class TestForAllStaff:
    """Обязательные курсы «для всех сотрудников» (миграция 111): виртуальный
    доступ (в т.ч. для новых сотрудников без строки участника), внешние
    учётки не затронуты, массовое покрытие без писем."""

    @staticmethod
    def _course(status: str = "published", for_all: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid.uuid4(),
            slug="kurs",
            title="Курс",
            status=status,
            for_all_staff=for_all,
        )

    @staticmethod
    def _participant(kind: str) -> SimpleNamespace:
        ident = uuid.uuid4()
        return SimpleNamespace(
            kind=kind,
            user_id=ident if kind == "user" else None,
            learning_account_id=None if kind == "user" else ident,
            key=lambda: ("user" if kind == "user" else "acc", ident),
            matching=lambda model: True,
        )

    async def test_staff_has_access_without_enrollment_row(self):
        db = _FakeDb()
        participant = self._participant("user")
        assert await cs.has_course_access(db, participant, self._course()) is True

    async def test_external_not_covered_by_flag(self):
        db = _FakeDb()
        participant = self._participant("acc")
        assert await cs.has_course_access(db, participant, self._course()) is False

    async def test_staff_without_flag_still_needs_enrollment(self):
        db = _FakeDb()
        participant = self._participant("user")
        assert await cs.has_course_access(db, participant, self._course(for_all=False)) is False

    async def test_create_course_sets_flag(self, monkeypatch):
        async def _unique_slug(_db, slug, exclude_id=None):
            return slug

        monkeypatch.setattr(cs, "_ensure_unique_slug", _unique_slug)
        db = _FakeDb()
        course = await cs.create_course(
            db, title="Курс", description=None, slug=None, for_all_staff=True
        )
        assert course.for_all_staff is True

    async def test_update_course_flag_absent_key_keeps(self):
        db = _FakeDb()
        course = self._course()
        await cs.update_course(db, course, title="Новое имя")
        assert course.for_all_staff is True

    async def test_update_course_flag_off(self):
        db = _FakeDb()
        course = self._course()
        await cs.update_course(db, course, for_all_staff=False)
        assert course.for_all_staff is False

    async def test_my_course_list_includes_mandatory_without_row(self, monkeypatch):
        cid = uuid.uuid4()
        course = SimpleNamespace(id=cid, slug="obaz", title="Обязательный")
        participant = self._participant("user")

        class _SeqResult:
            def __init__(self, value):
                self._value = value

            def scalars(self):
                return self

            def all(self):
                v = self._value
                return v if isinstance(v, list) else [v]

        class _QueueDb:
            def __init__(self, results):
                self._results = list(results)

            async def execute(self, *args, **kwargs):
                return _SeqResult(self._results.pop(0))

            async def flush(self):
                pass

        db = _QueueDb(
            [
                [],  # явных зачислений нет
                [cid],  # обязательный курс (for_all_staff)
                [(course, None, None)],  # курсы + категория
                [],  # элементов нет
            ]
        )

        async def _collect_done(_db, ids):
            return {}

        async def _collect_passed(_db, ids):
            return {}

        monkeypatch.setattr(cs, "_collect_completed_materials", _collect_done)
        monkeypatch.setattr(cs, "_collect_passed_tests", _collect_passed)

        rows = await cs.my_course_list(db, participant)
        assert len(rows) == 1
        assert rows[0][0].id == cid
        assert rows[0][3] is None  # без категории

    async def test_enroll_all_staff_missing_skips_existing_and_letters(self, monkeypatch):
        course = self._course()
        existing_uid = uuid.uuid4()
        new_user = SimpleNamespace(id=uuid.uuid4(), full_name="Новый Сотрудник", email="n@x")

        class _RowsResult:
            def __init__(self, value):
                self._value = value

            def all(self):
                return self._value

            def scalars(self):
                return self

        class _Db:
            def __init__(self):
                self.added = []

            async def execute(self, *args, **kwargs):
                return _RowsResult([(existing_uid,)])

            def begin_nested(self):
                return self

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def add(self, obj):
                self.added.append(obj)

            async def flush(self):
                pass

            async def rollback(self):
                pass

        db = _Db()

        async def fake_enqueue(db, **kw):
            raise AssertionError("письма при массовом покрытии не шлются")

        monkeypatch.setattr(cs, "enqueue_outbox_email", fake_enqueue)

        user_rows = [
            SimpleNamespace(id=existing_uid, full_name="Старый", email="s@x"),
            new_user,
        ]

        class _Dba:
            async def execute(self, *args, **kwargs):
                return _RowsResult(user_rows)

        count = await cs.enroll_all_staff_missing(db, _Dba(), course, enrolled_by=None)
        assert count == 1  # existing пропущен, new_user зачислен
        assert len(db.added) == 1
        assert db.added[0].user_id == new_user.id


class TestForAllStaffSync:
    """Set-based дозачисление после Keycloak-синка (worker hook)."""

    async def test_executes_idempotent_sql(self):
        from app.services.learning import for_all_staff as fas

        captured: dict[str, str] = {}

        class _Conn:
            async def fetchval(self, sql: str):
                captured["sql"] = sql
                return 5

        count = await fas.enroll_missing_staff(_Conn())
        assert count == 5
        assert "for_all_staff" in captured["sql"]
        # идемпотентность: вставка только при отсутствии строки участника
        assert "NOT EXISTS" in captured["sql"]
        # только опубликованные и не удалённые курсы, живые сотрудники
        assert "status = 'published'" in captured["sql"]
        assert "u.deleted_at IS NULL" in captured["sql"]

    async def test_enroll_participant_with_notify_sends_letter(self, monkeypatch):
        letters: list[str] = []

        async def fake_enqueue(db, **kw):
            letters.append(kw["to_email"])

        monkeypatch.setattr(cs, "enqueue_outbox_email", fake_enqueue)

        async def _lock(_db, _cid):
            return SimpleNamespace(id=_cid, status="published")

        monkeypatch.setattr(cs, "lock_course", _lock)

        async def _items(_db, _cid):
            return []

        monkeypatch.setattr(cs, "active_items", _items)
        db = _FakeDb()
        await cs.enroll_participant(
            db,
            SimpleNamespace(id=uuid.uuid4(), slug="kurs", title="Курс", status="published"),
            user_id=uuid.uuid4(),
            display_name="Иван",
            email="i@x.ru",
            enrolled_by=None,
        )
        assert letters == ["i@x.ru"]

    async def test_my_course_list_counts_completed_items(self, monkeypatch):
        cid = uuid.uuid4()
        course = SimpleNamespace(id=cid, slug="kurs", title="Курс")
        material = SimpleNamespace(id=uuid.uuid4(), course_id=cid, type="material")

        class _SeqResult:
            def __init__(self, value):
                self._value = value

            def scalars(self):
                return self

            def all(self):
                return self._value if isinstance(self._value, list) else [self._value]

        class _QueueDb:
            def __init__(self, results):
                self._results = list(results)

            async def execute(self, *args, **kwargs):
                return _SeqResult(self._results.pop(0))

            async def flush(self):
                pass

        db = _QueueDb([[cid], [], [(course, None, None)], [material]])
        participant = SimpleNamespace(
            kind=cs.KIND_USER,
            user_id="u1",
            learning_account_id=None,
            key=lambda: ("user", "u1"),
            matching=lambda model: True,
        )

        async def _collect_done(_db, ids):
            return {("user", "u1"): {material.id}}

        async def _collect_passed(_db, ids):
            return {}

        monkeypatch.setattr(cs, "_collect_completed_materials", _collect_done)
        monkeypatch.setattr(cs, "_collect_passed_tests", _collect_passed)

        rows = await cs.my_course_list(db, participant)
        assert rows[0][1] == 1  # completed учтён
