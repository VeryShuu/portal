"""Tests for the generic dataset registry (audit M8).

Characterization: регистр ``_DATASETS`` — единый источник истины для list-
endpoints и экспорта. Тесты гарантируют, что добавление dataset'а в реестр
автоматически подтягивает его в /export-валидацию и что все существующие
dataset'ы имеют непротиворечивые export_columns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.api.analytics import _DATASETS, _export_pattern, _export_rows, _fetch_dataset


def test_registry_covers_six_tabular_datasets():
    # План M8: 6 list-dataset'ов в реестре (dashboard/feedback/resource-trend —
    # нестандартные, отдельно).
    assert set(_DATASETS) == {
        "top-articles",
        "top-news",
        "top-files",
        "top-links",
        "departments",
        "stale-content",
    }


def test_export_pattern_matches_exactly_registry_keys():
    # /export-pattern строится из реестра → нет расхождения с хардкодом.
    import re

    pattern = re.compile(_export_pattern())
    for name in _DATASETS:
        assert pattern.match(name), f"{name} should match export pattern"
    assert pattern.match("unknown-dataset") is None


def test_every_dataset_has_mapper_and_columns():
    for name, spec in _DATASETS.items():
        assert callable(spec.mapper), f"{name}: mapper must be callable"
        assert callable(spec.repo_fn), f"{name}: repo_fn must be callable"
        assert len(spec.export_columns) > 0, f"{name}: export_columns required"
        # Каждая колонка — (data_key, ru_label).
        for entry in spec.export_columns:
            assert len(entry) == 2, f"{name}: column entry must be (key, label) tuple"
            assert isinstance(entry[0], str) and isinstance(entry[1], str)


def test_departments_has_no_limit_others_have():
    assert _DATASETS["departments"].has_limit is False
    for name in ("top-articles", "top-news", "top-files", "top-links", "stale-content"):
        assert _DATASETS[name].has_limit is True, f"{name} should accept limit"


async def test_fetch_dataset_with_limit_passes_limit_to_repo():
    """Dataset с has_limit=True прокидывает limit в repo_fn."""
    captured: dict[str, object] = {}

    async def fake_repo(db, *, cutoff, limit):
        captured["limit"] = limit
        captured["cutoff"] = cutoff
        return []

    _DATASETS["__test_with_limit"] = _DATASETS["top-articles"].__class__(
        repo_fn=fake_repo,
        mapper=lambda r: r,
        export_columns=[("x", "X")],
        has_limit=True,
    )
    try:
        await _fetch_dataset(MagicMock(), "__test_with_limit", days=7, limit=42)
    finally:
        del _DATASETS["__test_with_limit"]

    assert captured["limit"] == 42
    assert isinstance(captured["cutoff"], datetime)


async def test_fetch_dataset_without_limit_omits_limit():
    """Dataset с has_limit=False (departments) НЕ передаёт limit в repo_fn."""
    captured: dict[str, object] = {}

    async def fake_repo(db, *, cutoff):
        captured["called_kwargs"] = list({"cutoff": cutoff}.keys())
        return []

    _DATASETS["__test_no_limit"] = _DATASETS["top-articles"].__class__(
        repo_fn=fake_repo,
        mapper=lambda r: r,
        export_columns=[("x", "X")],
        has_limit=False,
    )
    try:
        await _fetch_dataset(MagicMock(), "__test_no_limit", days=7, limit=999)
    finally:
        del _DATASETS["__test_no_limit"]

    assert "limit" not in captured["called_kwargs"]


async def test_export_rows_maps_datetime_to_isoformat():
    """_export_rows сериализует datetime в isoformat (для CSV/XLSX)."""
    dt = datetime(2024, 1, 1, tzinfo=UTC)

    async def fake_repo(db, *, cutoff, limit):
        row = MagicMock()
        row.__getitem__ = lambda self, key: {"title": "T", "updated_at": dt}[key]
        return [row]

    _DATASETS["__test_export"] = _DATASETS["top-articles"].__class__(
        repo_fn=fake_repo,
        mapper=lambda r: r,
        export_columns=[("title", "Название"), ("updated_at", "Обновлено")],
    )
    try:
        rows = await _export_rows(MagicMock(), "__test_export", days=7, limit=1)
    finally:
        del _DATASETS["__test_export"]

    assert rows == [{"title": "T", "updated_at": dt.isoformat()}]
