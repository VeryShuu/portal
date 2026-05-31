"""Unit-тесты для services/files_shares_persistence.py (sharing.md §7).

Покрытие:
- _read_raw: файл отсутствует → {}, невалидный JSON → {}, валидный → dict
- _write_raw: атомарная запись через tmp-файл, без хвостов
- save_file_shares: добавляет/обновляет записи, empty list удаляет ключ
- drop_file_shares: удаляет ключ, нет ключа — без ошибки
- rename_file_shares: переносит запись на новый nc_path
- drop_file_shares_under_prefix: удаляет все записи под папкой
- load_all: возвращает полный dict
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_write_lock():
    import app.services.files_shares_persistence as mod

    mod._write_lock = None
    yield
    mod._write_lock = None


def _entry(subject_id: str = "u1", permission: str = "viewer") -> dict:
    return {
        "subject_type": "user",
        "subject_id": subject_id,
        "subject_name": "Test",
        "permission": permission,
        "expires_at": None,
    }


# ── _read_raw ─────────────────────────────────────────────────────────────────


class TestReadRaw:
    def test_missing_file_returns_empty(self, tmp_path):
        import app.services.files_shares_persistence as mod

        with patch.object(mod, "_SHARES_FILE", tmp_path / "no.json"):
            from app.services.files_shares_persistence import _read_raw

            assert _read_raw() == {}

    def test_invalid_json_returns_empty(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text("{broken", encoding="utf-8")
        with patch.object(mod, "_SHARES_FILE", f):
            from app.services.files_shares_persistence import _read_raw

            assert _read_raw() == {}

    def test_valid_json_returns_dict(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(json.dumps({"HR/report.xlsx": [_entry()]}), encoding="utf-8")
        with patch.object(mod, "_SHARES_FILE", f):
            from app.services.files_shares_persistence import _read_raw

            result = _read_raw()
        assert "HR/report.xlsx" in result
        assert result["HR/report.xlsx"][0]["subject_id"] == "u1"


# ── _write_raw ────────────────────────────────────────────────────────────────


class TestWriteRaw:
    def test_writes_file_atomically(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _write_raw

            _write_raw({"HR/a.docx": [_entry()]})
        assert f.exists()
        assert "HR/a.docx" in json.loads(f.read_text("utf-8"))

    def test_no_tmp_files_left(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _write_raw

            _write_raw({"X/y.txt": [_entry()]})
        assert list(tmp_path.glob(".files-shares-*.json")) == []


# ── save_file_shares ──────────────────────────────────────────────────────────


class TestSaveFileShares:
    @pytest.mark.asyncio
    async def test_saves_entries_for_path(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _read_raw, save_file_shares

            await save_file_shares("HR/report.xlsx", [_entry(permission="editor")])
            data = _read_raw()
        assert data["HR/report.xlsx"][0]["permission"] == "editor"

    @pytest.mark.asyncio
    async def test_empty_entries_removes_key(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(json.dumps({"HR/report.xlsx": [_entry()]}), encoding="utf-8")
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _read_raw, save_file_shares

            await save_file_shares("HR/report.xlsx", [])
            data = _read_raw()
        assert "HR/report.xlsx" not in data

    @pytest.mark.asyncio
    async def test_overwrites_existing(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(json.dumps({"HR/r.xlsx": [_entry(subject_id="old")]}), encoding="utf-8")
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _read_raw, save_file_shares

            await save_file_shares("HR/r.xlsx", [_entry(subject_id="new")])
            data = _read_raw()
        assert len(data["HR/r.xlsx"]) == 1
        assert data["HR/r.xlsx"][0]["subject_id"] == "new"


# ── drop_file_shares ──────────────────────────────────────────────────────────


class TestDropFileShares:
    @pytest.mark.asyncio
    async def test_removes_existing_key(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(json.dumps({"A/a.txt": [_entry()], "B/b.txt": [_entry()]}), encoding="utf-8")
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _read_raw, drop_file_shares

            await drop_file_shares("A/a.txt")
            data = _read_raw()
        assert "A/a.txt" not in data
        assert "B/b.txt" in data

    @pytest.mark.asyncio
    async def test_no_error_when_missing(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text("{}", encoding="utf-8")
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import drop_file_shares

            await drop_file_shares("nope/x.txt")


# ── rename_file_shares ────────────────────────────────────────────────────────


class TestRenameFileShares:
    @pytest.mark.asyncio
    async def test_moves_entry(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(json.dumps({"HR/old.docx": [_entry()]}), encoding="utf-8")
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _read_raw, rename_file_shares

            await rename_file_shares("HR/old.docx", "HR/new.docx")
            data = _read_raw()
        assert "HR/old.docx" not in data
        assert "HR/new.docx" in data

    @pytest.mark.asyncio
    async def test_no_op_when_source_missing(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text("{}", encoding="utf-8")
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import _read_raw, rename_file_shares

            await rename_file_shares("HR/old.docx", "HR/new.docx")
            data = _read_raw()
        assert data == {}


# ── drop_file_shares_under_prefix ─────────────────────────────────────────────


class TestDropUnderPrefix:
    @pytest.mark.asyncio
    async def test_drops_only_matching_prefix(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(
            json.dumps(
                {
                    "HR/sub/a.txt": [_entry()],
                    "HR/b.txt": [_entry()],
                    "Other/c.txt": [_entry()],
                }
            ),
            encoding="utf-8",
        )
        with (
            patch.object(mod, "_SHARES_FILE", f),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_shares_persistence import (
                _read_raw,
                drop_file_shares_under_prefix,
            )

            await drop_file_shares_under_prefix("HR")
            data = _read_raw()
        assert "HR/sub/a.txt" not in data
        assert "HR/b.txt" not in data
        assert "Other/c.txt" in data


# ── load_all ──────────────────────────────────────────────────────────────────


class TestLoadAll:
    def test_returns_full_dict(self, tmp_path):
        import app.services.files_shares_persistence as mod

        f = tmp_path / "files-shares.json"
        f.write_text(json.dumps({"A/a.txt": [_entry()], "B/b.txt": [_entry()]}), encoding="utf-8")
        with patch.object(mod, "_SHARES_FILE", f):
            from app.services.files_shares_persistence import load_all

            result = load_all()
        assert set(result) == {"A/a.txt", "B/b.txt"}
