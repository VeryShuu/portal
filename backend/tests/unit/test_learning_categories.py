"""Unit-тесты categories_service (справочник категорий курсов, миграция 109).

Роутеры покрываются integration-контуром; здесь — чистая логика сервиса:
дедуп названий (case-insensitive), сортировка со счётчиками, reorder-валидность,
soft-delete с отвязкой курсов, валидация ссылки из курса.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.services.learning import categories_service as cats


class _SeqResult:
    """Последовательный .scalars()/.all()/.first() с фиксированным значением."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def first(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value if isinstance(self._value, list) else [self._value]


class _QueueDb:
    """AsyncSession-дублер с очередью результатов execute."""

    def __init__(self, results: list[Any]):
        self._results = list(results)
        self.executed: list[tuple] = []
        self.flushes = 0

    async def execute(self, *args, **kwargs):
        self.executed.append(args)
        return _SeqResult(self._results.pop(0))

    async def flush(self):
        self.flushes += 1

    def add(self, obj):
        pass


def _cat(title: str, sort_order: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title=title,
        sort_order=sort_order,
        created_at=None,
        updated_at=None,
        deleted_at=None,
    )


class TestCreateCategory:
    async def test_creates_with_next_sort_order(self):
        # очередь: [title_taken → None, список категорий, счётчики курсов]
        db = _QueueDb([None, [_cat("Инструктажи", 0), _cat("ГО и ЧС", 1)], []])
        cat = await cats.create_category(db, title="  Электробезопасность  ")
        assert cat.title == "Электробезопасность"
        assert cat.sort_order == 2

    async def test_duplicate_title_case_insensitive_409(self):
        # очередь: [title_taken → нашёл дубль]
        db = _QueueDb([_cat("Инструктажи")])
        with pytest.raises(HTTPException) as ei:
            await cats.create_category(db, title="инструктажи")
        assert ei.value.status_code == 409


class TestUpdateCategory:
    async def test_renames_and_stamps_updated_at(self, monkeypatch):
        monkeypatch.setattr(cats, "_title_taken", _async(False))
        cat = _cat("Старое", 0)
        db = _QueueDb([])
        await cats.update_category(db, cat, title="Новое")
        assert cat.title == "Новое"
        assert cat.updated_at is not None

    async def test_rename_to_duplicate_409(self, monkeypatch):
        monkeypatch.setattr(cats, "_title_taken", _async(True))
        cat = _cat("Старое", 0)
        db = _QueueDb([])
        with pytest.raises(HTTPException) as ei:
            await cats.update_category(db, cat, title="Дубль")
        assert ei.value.status_code == 409

    async def test_title_none_keeps_name(self, monkeypatch):
        monkeypatch.setattr(cats, "_title_taken", _async(False))
        cat = _cat("Неизменное", 0)
        db = _QueueDb([])
        await cats.update_category(db, cat, title=None)
        assert cat.title == "Неизменное"


class TestReorderCategories:
    async def test_assigns_positions(self):
        k1, k2, k3 = _cat("A", 0), _cat("B", 1), _cat("C", 2)
        db = _QueueDb([[k1, k2, k3]])  # активные категории
        await cats.reorder_categories(db, [k3.id, k1.id, k2.id])
        assert (k3.sort_order, k1.sort_order, k2.sort_order) == (0, 1, 2)

    async def test_incomplete_list_422(self):
        db = _QueueDb([[_cat("A", 0)]])
        with pytest.raises(HTTPException) as ei:
            await cats.reorder_categories(db, [uuid.uuid4()])
        assert ei.value.status_code == 422


class TestSoftDelete:
    async def test_unlinks_courses(self, monkeypatch):
        cat = _cat("Инструктажи", 0)
        db = _QueueDb([None])  # update(...) курс вернёт None
        await cats.soft_delete_category(db, cat)
        assert cat.deleted_at is not None
        # второй execute — UPDATE отвязки курсов
        assert len(db.executed) == 1


class TestEnsureCategoryExists:
    async def test_missing_category_422(self):
        db = _QueueDb([None])  # get_category → None
        with pytest.raises(HTTPException) as ei:
            await cats.ensure_category_exists(db, uuid.uuid4())
        assert ei.value.status_code == 422

    async def test_active_category_passes(self):
        db = _QueueDb([_cat("Есть")])
        await cats.ensure_category_exists(db, uuid.uuid4())


def _async(value):
    async def _fn(*_args, **_kwargs):
        return value

    return _fn
