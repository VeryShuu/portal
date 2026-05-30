"""Unit-тесты api/photos/photo_service.py.

Покрытие чистых хелперов и оркестрационных функций с моками БД/Redis:
- `_pick_unique_filename`: безопасное имя / коллизии / fallback на uuid
- `_move_photo_file_on_disk`: обычное перемещение / коллизия / no-op
- `_rollback_uploaded_files`: удаление файлов с suppress
- `_validate_upload_context`: модуль выключен / папка не найдена
- `_load_bulk_target_folder`: обязательный target / not-found / admin skip
- `list_folder_photos`: 404 при отсутствии папки
- `get_storage_stats`: проксирование вызова
- `list_recent_photos`: пустой результат при выключенном модуле
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_user(role: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="user@example.com",
        role=role,
    )


def _make_folder(fs_path: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        path="folder-a",
        fs_path=fs_path or "folder-a",
    )


# ── _pick_unique_filename ─────────────────────────────────────────────────────


def test_pick_unique_filename_no_conflict(tmp_path: Path) -> None:
    from app.api.photos.photo_service import _pick_unique_filename

    result = _pick_unique_filename(tmp_path, "photo.jpg")
    assert result.endswith(".jpg")
    assert "photo" in result


def test_pick_unique_filename_collision(tmp_path: Path) -> None:
    from app.api.photos.photo_service import _pick_unique_filename

    (tmp_path / "photo.jpg").write_bytes(b"x")
    result = _pick_unique_filename(tmp_path, "photo.jpg")
    assert result != "photo.jpg"
    assert result.endswith(".jpg")
    assert result.startswith("photo-")


def test_pick_unique_filename_none_falls_back(tmp_path: Path) -> None:
    from app.api.photos.photo_service import _pick_unique_filename

    result = _pick_unique_filename(tmp_path, None)
    assert result.endswith(".bin") or "." in result


def test_pick_unique_filename_many_collisions_uuid_fallback(tmp_path: Path) -> None:
    from app.api.photos.photo_service import _pick_unique_filename

    # При 9999 коллизиях возвращается uuid-fallback. Проверим путь с уже
    # занятыми первыми вариантами — функция должна вернуть валидное имя.
    (tmp_path / "photo.jpg").write_bytes(b"x")
    for i in range(1, 5):
        (tmp_path / f"photo-{i}.jpg").write_bytes(b"x")
    result = _pick_unique_filename(tmp_path, "photo.jpg")
    assert result.endswith(".jpg")
    assert not (tmp_path / result).exists()


# ── _move_photo_file_on_disk ──────────────────────────────────────────────────


def test_move_photo_file_on_disk_basic(tmp_path: Path) -> None:
    from app.api.photos import photo_service
    from app.services import photos_storage

    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    (src_dir / "p.jpg").write_bytes(b"data")

    photo = SimpleNamespace(filename="p.jpg")
    src_folder = _make_folder(fs_path="src")
    dst_folder = _make_folder(fs_path="dst")

    moved: list[tuple[str, str]] = []
    with patch.object(photos_storage, "folder_fs_path", side_effect=lambda p: tmp_path / p):
        photo_service._move_photo_file_on_disk(photo, src_folder, dst_folder, moved)

    assert (dst_dir / "p.jpg").exists()
    assert not (src_dir / "p.jpg").exists()
    assert len(moved) == 1


def test_move_photo_file_on_disk_collision_renames(tmp_path: Path) -> None:
    from app.api.photos import photo_service
    from app.services import photos_storage

    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    (src_dir / "p.jpg").write_bytes(b"new")
    (dst_dir / "p.jpg").write_bytes(b"existing")

    photo = SimpleNamespace(filename="p.jpg")
    src_folder = _make_folder(fs_path="src")
    dst_folder = _make_folder(fs_path="dst")

    moved: list[tuple[str, str]] = []
    with patch.object(photos_storage, "folder_fs_path", side_effect=lambda p: tmp_path / p):
        photo_service._move_photo_file_on_disk(photo, src_folder, dst_folder, moved)

    assert photo.filename != "p.jpg"
    assert photo.filename.endswith(".jpg")
    assert (dst_dir / photo.filename).exists()
    assert (dst_dir / "p.jpg").read_bytes() == b"existing"


def test_move_photo_file_on_disk_no_src_folder_noop(tmp_path: Path) -> None:
    from app.api.photos import photo_service

    photo = SimpleNamespace(filename="p.jpg")
    moved: list[tuple[str, str]] = []
    photo_service._move_photo_file_on_disk(photo, None, _make_folder(), moved)
    assert moved == []


def test_move_photo_file_on_disk_missing_src_file_noop(tmp_path: Path) -> None:
    from app.api.photos import photo_service
    from app.services import photos_storage

    (tmp_path / "src").mkdir()
    (tmp_path / "dst").mkdir()

    photo = SimpleNamespace(filename="absent.jpg")
    src_folder = _make_folder(fs_path="src")
    dst_folder = _make_folder(fs_path="dst")

    moved: list[tuple[str, str]] = []
    with patch.object(photos_storage, "folder_fs_path", side_effect=lambda p: tmp_path / p):
        photo_service._move_photo_file_on_disk(photo, src_folder, dst_folder, moved)
    assert moved == []


# ── _rollback_uploaded_files ──────────────────────────────────────────────────


def test_rollback_uploaded_files_removes_files(tmp_path: Path) -> None:
    from app.api.photos.photo_service import _rollback_uploaded_files

    f1 = tmp_path / "1.jpg"
    f2 = tmp_path / "2.jpg"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")

    pending = [
        (SimpleNamespace(), 1, f1),
        (SimpleNamespace(), 2, f2),
    ]
    _rollback_uploaded_files(pending)
    assert not f1.exists()
    assert not f2.exists()


def test_rollback_uploaded_files_suppresses_errors(tmp_path: Path) -> None:
    from app.api.photos.photo_service import _rollback_uploaded_files

    missing = tmp_path / "ghost.jpg"
    pending = [(SimpleNamespace(), 0, missing)]
    # Should not raise even though file doesn't exist.
    _rollback_uploaded_files(pending)


# ── _validate_upload_context ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_upload_context_module_disabled() -> None:
    from app.api.photos import photo_service

    fake_cfg = SimpleNamespace(
        enabled=False, max_size_mb=None, allowed_mime=None, widget_limit=None
    )
    with patch.object(photo_service, "_module_settings", return_value=fake_cfg):
        with pytest.raises(HTTPException) as exc:
            await photo_service._validate_upload_context(
                AsyncMock(), _make_user(), AsyncMock(), uuid.uuid4()
            )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_validate_upload_context_folder_not_found() -> None:
    from app.api.photos import photo_service
    from app.services import photos_photo_repo

    fake_cfg = SimpleNamespace(
        enabled=True, max_size_mb=10, allowed_mime=["image/jpeg"], widget_limit=8
    )
    with (
        patch.object(photo_service, "_module_settings", return_value=fake_cfg),
        patch.object(photos_photo_repo, "fetch_active_folder", new=AsyncMock(return_value=None)),
    ):
        with pytest.raises(HTTPException) as exc:
            await photo_service._validate_upload_context(
                AsyncMock(), _make_user(), AsyncMock(), uuid.uuid4()
            )
    assert exc.value.status_code == 404


# ── _load_bulk_target_folder ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_bulk_target_folder_requires_id() -> None:
    from app.api.photos.photo_service import _load_bulk_target_folder

    with pytest.raises(HTTPException) as exc:
        await _load_bulk_target_folder(AsyncMock(), _make_user(), AsyncMock(), None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_load_bulk_target_folder_not_found() -> None:
    from app.api.photos.photo_service import _load_bulk_target_folder
    from app.services import photos_photo_repo

    with patch.object(photos_photo_repo, "fetch_active_folder", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await _load_bulk_target_folder(AsyncMock(), _make_user(), AsyncMock(), uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_load_bulk_target_folder_admin_skips_acl_check() -> None:
    from app.api.photos import photo_service
    from app.services import photos_photo_repo

    folder = _make_folder()
    with (
        patch.object(photos_photo_repo, "fetch_active_folder", new=AsyncMock(return_value=folder)),
        patch.object(photo_service, "require_folder_permission", new=AsyncMock()) as req,
    ):
        result = await photo_service._load_bulk_target_folder(
            AsyncMock(), _make_user("admin"), AsyncMock(), uuid.uuid4()
        )
    assert result is folder
    req.assert_not_called()


# ── list_folder_photos ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_folder_photos_404_when_missing() -> None:
    from app.api.photos.photo_service import list_folder_photos
    from app.services import photos_photo_repo

    with patch.object(photos_photo_repo, "fetch_active_folder", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await list_folder_photos(
                AsyncMock(),
                _make_user(),
                AsyncMock(),
                uuid.uuid4(),
                page=1,
                per_page=20,
                sort="-created_at",
                min_date=None,
                max_date=None,
                min_size=None,
                max_size=None,
                mime_type=None,
            )
    assert exc.value.status_code == 404


# ── get_storage_stats ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_storage_stats_proxies_to_repo() -> None:
    from app.api.photos.photo_service import get_storage_stats
    from app.services import photos_photo_repo

    stats = {"total_photos": 7, "total_size_bytes": 123}
    with patch.object(photos_photo_repo, "fetch_storage_stats", new=AsyncMock(return_value=stats)):
        result = await get_storage_stats(AsyncMock())
    assert result == stats


# ── list_recent_photos ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recent_photos_module_disabled_returns_empty() -> None:
    from app.api.photos import photo_service

    fake_cfg = SimpleNamespace(
        enabled=False, max_size_mb=None, allowed_mime=None, widget_limit=None
    )
    with patch.object(photo_service, "_module_settings", return_value=fake_cfg):
        result = await photo_service.list_recent_photos(
            AsyncMock(), _make_user(), AsyncMock(), limit=5
        )
    assert result == []


@pytest.mark.asyncio
async def test_list_recent_photos_empty_rows() -> None:
    from app.api.photos import photo_service
    from app.services import photos_photo_repo

    fake_cfg = SimpleNamespace(enabled=True, max_size_mb=10, allowed_mime=[], widget_limit=8)
    with (
        patch.object(photo_service, "_module_settings", return_value=fake_cfg),
        patch.object(
            photos_photo_repo, "fetch_recent_photos_with_folders", new=AsyncMock(return_value=[])
        ),
    ):
        result = await photo_service.list_recent_photos(
            AsyncMock(), _make_user("admin"), AsyncMock(), limit=5
        )
    assert result == []


# ── _bulk_delete_photo ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_delete_photo_admin_marks_deleted() -> None:
    from app.api.photos import photo_service

    photo = MagicMock()
    with patch.object(photo_service.TrashService, "mark_photo_deleted") as mark:
        result = await photo_service._bulk_delete_photo(
            photo, _make_user("admin"), AsyncMock(), AsyncMock()
        )
    assert result is None
    mark.assert_called_once_with(photo)


@pytest.mark.asyncio
async def test_bulk_delete_photo_non_admin_insufficient_perms() -> None:
    from app.api.photos import photo_service

    photo = MagicMock()
    user = _make_user("user")
    with patch.object(
        photo_service, "resolve_photo_permission", new=AsyncMock(return_value="viewer")
    ):
        result = await photo_service._bulk_delete_photo(photo, user, AsyncMock(), AsyncMock())
    assert result == "insufficient permissions"
