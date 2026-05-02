"""Unit-тесты для services/files_acl_persistence.py.

Покрытие:
- _read_raw: файл отсутствует → {}, невалидный JSON → {}, валидный → dict
- _write_raw: атомарная запись через tmp-файл
- save_folder_perms: добавляет/обновляет записи, empty list удаляет ключ
- drop_folder_perms: удаляет ключ, нет ключа — без ошибки
- get_folder_perms: возвращает список для пути, [] для неизвестного пути
- load_all: возвращает полный dict
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_write_lock():
    import app.services.files_acl_persistence as mod

    mod._write_lock = None
    yield
    mod._write_lock = None


# ── _read_raw ─────────────────────────────────────────────────────────────────


class TestReadRaw:
    def test_missing_file_returns_empty(self, tmp_path):
        import app.services.files_acl_persistence as mod

        with patch.object(mod, "_ACL_FILE", tmp_path / "no.json"):
            from app.services.files_acl_persistence import _read_raw

            result = _read_raw()
        assert result == {}

    def test_invalid_json_returns_empty(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        acl_file.write_text("{invalid json}", encoding="utf-8")
        with patch.object(mod, "_ACL_FILE", acl_file):
            from app.services.files_acl_persistence import _read_raw

            result = _read_raw()
        assert result == {}

    def test_valid_json_returns_dict(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        data = {"HR": [{"subject_type": "user", "subject_id": "u1", "subject_name": "Иван", "permission": "editor"}]}
        acl_file.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(mod, "_ACL_FILE", acl_file):
            from app.services.files_acl_persistence import _read_raw

            result = _read_raw()
        assert "HR" in result
        assert result["HR"][0]["permission"] == "editor"


# ── _write_raw ────────────────────────────────────────────────────────────────


class TestWriteRaw:
    def test_writes_file_atomically(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import _write_raw

            data = {"IT": [{"subject_type": "group", "subject_id": "g1", "subject_name": "IT Dept", "permission": "viewer"}]}
            _write_raw(data)

        assert acl_file.exists()
        loaded = json.loads(acl_file.read_text("utf-8"))
        assert "IT" in loaded

    def test_no_tmp_files_left_after_write(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import _write_raw

            _write_raw({"A": []})

        tmp_files = list(tmp_path.glob(".files-acl-*.json"))
        assert len(tmp_files) == 0


# ── save_folder_perms ─────────────────────────────────────────────────────────


class TestSaveFolderPerms:
    @pytest.mark.asyncio
    async def test_saves_entries_for_path(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import save_folder_perms, _read_raw

            entries = [{"subject_type": "user", "subject_id": "u1", "subject_name": "Alice", "permission": "manager"}]
            await save_folder_perms("HR", entries)
            data = _read_raw()
        assert "HR" in data
        assert data["HR"][0]["subject_id"] == "u1"

    @pytest.mark.asyncio
    async def test_empty_entries_removes_key(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        acl_file.write_text(
            json.dumps({"HR": [{"subject_type": "user", "subject_id": "u1", "subject_name": "A", "permission": "viewer"}]}),
            encoding="utf-8",
        )
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import save_folder_perms, _read_raw

            await save_folder_perms("HR", [])
            data = _read_raw()
        assert "HR" not in data

    @pytest.mark.asyncio
    async def test_overwrites_existing_entries(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        acl_file.write_text(
            json.dumps({"HR": [{"subject_type": "user", "subject_id": "old", "subject_name": "Old", "permission": "viewer"}]}),
            encoding="utf-8",
        )
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import save_folder_perms, _read_raw

            new_entries = [{"subject_type": "user", "subject_id": "new", "subject_name": "New", "permission": "editor"}]
            await save_folder_perms("HR", new_entries)
            data = _read_raw()
        assert len(data["HR"]) == 1
        assert data["HR"][0]["subject_id"] == "new"


# ── drop_folder_perms ─────────────────────────────────────────────────────────


class TestDropFolderPerms:
    @pytest.mark.asyncio
    async def test_removes_existing_key(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        acl_file.write_text(
            json.dumps({"HR": [], "IT": []}),
            encoding="utf-8",
        )
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import drop_folder_perms, _read_raw

            await drop_folder_perms("HR")
            data = _read_raw()
        assert "HR" not in data
        assert "IT" in data

    @pytest.mark.asyncio
    async def test_no_error_when_key_missing(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        acl_file.write_text(json.dumps({}), encoding="utf-8")
        with (
            patch.object(mod, "_ACL_FILE", acl_file),
            patch.object(mod, "_SETTINGS_DIR", tmp_path),
        ):
            from app.services.files_acl_persistence import drop_folder_perms

            await drop_folder_perms("nonexistent")


# ── get_folder_perms ──────────────────────────────────────────────────────────


class TestGetFolderPerms:
    def test_returns_entries_for_known_path(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        entry = {"subject_type": "user", "subject_id": "u1", "subject_name": "Bob", "permission": "viewer"}
        acl_file.write_text(json.dumps({"Docs": [entry]}), encoding="utf-8")
        with patch.object(mod, "_ACL_FILE", acl_file):
            from app.services.files_acl_persistence import get_folder_perms

            result = get_folder_perms("Docs")
        assert len(result) == 1
        assert result[0]["subject_id"] == "u1"

    def test_returns_empty_for_unknown_path(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        acl_file.write_text(json.dumps({}), encoding="utf-8")
        with patch.object(mod, "_ACL_FILE", acl_file):
            from app.services.files_acl_persistence import get_folder_perms

            result = get_folder_perms("NoSuchPath")
        assert result == []


# ── load_all ──────────────────────────────────────────────────────────────────


class TestLoadAll:
    def test_returns_full_dict(self, tmp_path):
        import app.services.files_acl_persistence as mod

        acl_file = tmp_path / "files-acl.json"
        data = {
            "HR": [{"subject_type": "user", "subject_id": "u1", "subject_name": "A", "permission": "editor"}],
            "IT": [{"subject_type": "group", "subject_id": "g1", "subject_name": "IT", "permission": "viewer"}],
        }
        acl_file.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(mod, "_ACL_FILE", acl_file):
            from app.services.files_acl_persistence import load_all

            result = load_all()
        assert len(result) == 2
        assert "HR" in result
        assert "IT" in result
