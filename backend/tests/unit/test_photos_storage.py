"""Unit-тесты services/photos_storage.py (Фаза 3.4).

Покрытие:
- sanitize_filename: ascii / cyr fallback / spec chars / long name / no ext / dir sep
- is_allowed_ext: allowed / not allowed / case insensitive
- sanitize_folder_name: basic / trailing dots / double hyphens / empty → folder / too long
- folder_fs_path: relative safe / path traversal blocked / absolute within allowed / absolute outside
- delete_photo_files: no original path / original removed / thumbs dir removed
- thumb_path: valid size / invalid size raises
- thumb_avif_path: valid size / invalid size raises
- save_original: bytes / file-like / duplicate names handled
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ── sanitize_filename ─────────────────────────────────────────────────────────


def test_sanitize_filename_ascii():
    from app.services.photos_storage import sanitize_filename

    assert sanitize_filename("photo.jpg") == "photo.jpg"


def test_sanitize_filename_cyrillic_falls_back():
    from app.services.photos_storage import sanitize_filename

    result = sanitize_filename("фото.jpg")
    assert result.endswith(".jpg")
    assert "фото" not in result


def test_sanitize_filename_special_chars():
    from app.services.photos_storage import sanitize_filename

    result = sanitize_filename("my photo! (2).jpg")
    assert "!" not in result
    assert result.endswith(".jpg")


def test_sanitize_filename_empty_stem_uses_photo():
    from app.services.photos_storage import sanitize_filename

    result = sanitize_filename("!!!!!.jpg")
    assert result.endswith(".jpg")
    assert len(result) > 4


def test_sanitize_filename_no_extension():
    from app.services.photos_storage import sanitize_filename

    result = sanitize_filename("myfile")
    assert "myfile" in result


def test_sanitize_filename_long_name():
    from app.services.photos_storage import sanitize_filename

    long_name = "a" * 200 + ".jpg"
    result = sanitize_filename(long_name)
    assert len(result) <= 180


def test_sanitize_filename_no_path_traversal():
    from app.services.photos_storage import sanitize_filename

    result = sanitize_filename("../secret.jpg")
    assert "/" not in result
    assert ".." not in result


# ── is_allowed_ext ────────────────────────────────────────────────────────────


def test_is_allowed_ext_jpg():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("photo.jpg") is True


def test_is_allowed_ext_jpeg():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("photo.JPEG") is True


def test_is_allowed_ext_png():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("image.png") is True


def test_is_allowed_ext_heic():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("photo.heic") is True


def test_is_allowed_ext_not_allowed():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("document.pdf") is False


def test_is_allowed_ext_exe_not_allowed():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("virus.exe") is False


def test_is_allowed_ext_case_insensitive():
    from app.services.photos_storage import is_allowed_ext

    assert is_allowed_ext("photo.JPG") is True
    assert is_allowed_ext("photo.WebP") is True


# ── sanitize_folder_name ──────────────────────────────────────────────────────


def test_sanitize_folder_name_basic():
    from app.services.photos_storage import sanitize_folder_name

    assert sanitize_folder_name("My Folder") == "My Folder"


def test_sanitize_folder_name_cyrillic_preserved():
    from app.services.photos_storage import sanitize_folder_name

    result = sanitize_folder_name("Мои Фото")
    assert result == "Мои Фото"


def test_sanitize_folder_name_strips_dots():
    from app.services.photos_storage import sanitize_folder_name

    result = sanitize_folder_name("...folder...")
    assert not result.startswith(".")
    assert not result.endswith(".")


def test_sanitize_folder_name_collapses_hyphens():
    from app.services.photos_storage import sanitize_folder_name

    result = sanitize_folder_name("my---folder")
    assert "--" not in result


def test_sanitize_folder_name_empty_becomes_folder():
    from app.services.photos_storage import sanitize_folder_name

    assert sanitize_folder_name("") == "folder"
    assert sanitize_folder_name("   ") == "folder"


def test_sanitize_folder_name_dot_dot_becomes_folder():
    from app.services.photos_storage import sanitize_folder_name

    assert sanitize_folder_name("..") == "folder"


def test_sanitize_folder_name_long_name():
    from app.services.photos_storage import sanitize_folder_name

    long_name = "Ф" * 300
    result = sanitize_folder_name(long_name)
    assert len(result) <= 200


def test_sanitize_folder_name_removes_forbidden_chars():
    from app.services.photos_storage import sanitize_folder_name

    result = sanitize_folder_name('my:folder<name>')
    assert ":" not in result
    assert "<" not in result
    assert ">" not in result


# ── folder_fs_path ────────────────────────────────────────────────────────────


def test_folder_fs_path_relative_safe():
    from app.services.photos_storage import ORIGINALS_ROOT, folder_fs_path

    p = folder_fs_path("HR/Docs")
    assert str(p).startswith(str(ORIGINALS_ROOT.resolve()))


def test_folder_fs_path_traversal_blocked():
    from app.services.photos_storage import folder_fs_path

    with pytest.raises(ValueError, match="Invalid folder path"):
        folder_fs_path("../../etc/passwd")


def test_folder_fs_path_double_dot_segment_blocked():
    from app.services.photos_storage import folder_fs_path

    with pytest.raises(ValueError, match="Invalid folder path"):
        folder_fs_path("HR/../../../etc")


def test_folder_fs_path_absolute_within_originals(tmp_path):
    from app.services.photos_storage import ORIGINALS_ROOT, folder_fs_path

    allowed_path = str(ORIGINALS_ROOT / "test_dir")
    with patch("app.services.photos_storage.ORIGINALS_ROOT", ORIGINALS_ROOT):
        with patch("app.services.photos_storage._ALLOWED_ROOTS", (ORIGINALS_ROOT,)):
            result = folder_fs_path(allowed_path)
            assert str(result).startswith(str(ORIGINALS_ROOT.resolve()))


def test_folder_fs_path_absolute_outside_raises():
    from app.services.photos_storage import folder_fs_path

    with pytest.raises(ValueError, match="Invalid folder path"):
        folder_fs_path("/etc/passwd")


def test_folder_fs_path_prefix_bypass_raises():
    from app.services.photos_storage import ORIGINALS_ROOT, folder_fs_path

    evil_path = str(ORIGINALS_ROOT) + "_evil/photo.jpg"
    with pytest.raises(ValueError, match="Invalid folder path"):
        folder_fs_path(evil_path)


def test_folder_fs_path_empty_returns_originals_root():
    from app.services.photos_storage import ORIGINALS_ROOT, folder_fs_path

    p = folder_fs_path("")
    assert p == ORIGINALS_ROOT.resolve()


# ── delete_photo_files ────────────────────────────────────────────────────────


def test_delete_photo_files_no_original(tmp_path):
    from app.services.photos_storage import delete_photo_files

    photo_id = uuid.uuid4()
    thumbs = tmp_path / str(photo_id)
    thumbs.mkdir()
    (thumbs / "200.webp").write_bytes(b"thumb")

    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        delete_photo_files(None, photo_id)

    assert not thumbs.exists()


def test_delete_photo_files_removes_original(tmp_path):
    from app.services.photos_storage import delete_photo_files

    original = tmp_path / "photo.jpg"
    original.write_bytes(b"data")
    photo_id = uuid.uuid4()

    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        delete_photo_files(original, photo_id)

    assert not original.exists()


def test_delete_photo_files_original_missing_no_error(tmp_path):
    from app.services.photos_storage import delete_photo_files

    missing = tmp_path / "missing.jpg"
    photo_id = uuid.uuid4()

    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        delete_photo_files(missing, photo_id)


def test_delete_photo_files_removes_thumbs_dir(tmp_path):
    from app.services.photos_storage import delete_photo_files

    photo_id = uuid.uuid4()
    thumbs = tmp_path / str(photo_id)
    thumbs.mkdir()
    (thumbs / "200.webp").write_bytes(b"thumb1")
    (thumbs / "600.webp").write_bytes(b"thumb2")

    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        delete_photo_files(None, photo_id)

    assert not thumbs.exists()


def test_delete_photo_files_no_thumbs_dir_no_error(tmp_path):
    from app.services.photos_storage import delete_photo_files

    photo_id = uuid.uuid4()
    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        delete_photo_files(None, photo_id)


def test_delete_photo_files_original_unlink_oserror(tmp_path):
    import pathlib

    from app.services.photos_storage import delete_photo_files

    photo_id = uuid.uuid4()
    original = tmp_path / "original.jpg"
    original.write_bytes(b"data")

    with patch.object(pathlib.Path, "unlink", side_effect=OSError("busy")):
        with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
            delete_photo_files(original, photo_id)


def test_delete_photo_files_thumbs_rmdir_oserror(tmp_path):
    import pathlib

    from app.services.photos_storage import delete_photo_files

    photo_id = uuid.uuid4()
    thumbs_dir = tmp_path / str(photo_id)
    thumbs_dir.mkdir()

    with patch.object(pathlib.Path, "rmdir", side_effect=OSError("busy")):
        with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
            delete_photo_files(None, photo_id)


# ── thumb_path ────────────────────────────────────────────────────────────────


def test_thumb_path_valid_size(tmp_path):
    from app.services.photos_storage import THUMB_SIZES, THUMBS_ROOT, thumb_path

    photo_id = uuid.uuid4()
    size = THUMB_SIZES[0]
    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        p = thumb_path(photo_id, size)
    assert p.name == f"{size}.webp"


def test_thumb_path_invalid_size():
    from app.services.photos_storage import thumb_path

    with pytest.raises(ValueError, match="Invalid thumbnail size"):
        thumb_path(uuid.uuid4(), 9999)


# ── thumb_avif_path ───────────────────────────────────────────────────────────


def test_thumb_avif_path_valid_size(tmp_path):
    from app.services.photos_storage import THUMB_SIZES, thumb_avif_path

    photo_id = uuid.uuid4()
    size = THUMB_SIZES[1]
    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        p = thumb_avif_path(photo_id, size)
    assert p.name == f"{size}.avif"


def test_thumb_avif_path_invalid_size():
    from app.services.photos_storage import thumb_avif_path

    with pytest.raises(ValueError, match="Invalid thumbnail size"):
        thumb_avif_path(uuid.uuid4(), 0)


# ── save_original ─────────────────────────────────────────────────────────────


def test_save_original_bytes(tmp_path):
    from app.services.photos_storage import save_original

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        name, size = save_original("HR/Docs", "photo.jpg", b"jpeg_data")

    assert name.endswith(".jpg")
    assert size == len(b"jpeg_data")
    assert (tmp_path / "HR" / "Docs" / name).exists()


def test_save_original_file_like(tmp_path):
    from app.services.photos_storage import save_original

    data = b"binary_photo_data"
    stream = io.BytesIO(data)

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        name, size = save_original("", "shot.png", stream)

    assert name.endswith(".png")
    assert size == len(data)


# ── rename_folder_dir ──────────────────────────────────────────────────────────


def test_rename_folder_dir_empty_old_path_noop(tmp_path):
    from app.services.photos_storage import rename_folder_dir

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        rename_folder_dir("", "new_folder")


def test_rename_folder_dir_same_path_noop(tmp_path):
    from app.services.photos_storage import rename_folder_dir

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        rename_folder_dir("my_folder", "my_folder")


def test_rename_folder_dir_old_missing_noop(tmp_path):
    from app.services.photos_storage import rename_folder_dir

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        rename_folder_dir("non_existent", "new_name")


def test_rename_folder_dir_simple_rename(tmp_path):
    from app.services.photos_storage import rename_folder_dir

    old = tmp_path / "old_folder"
    old.mkdir()
    (old / "photo.jpg").write_bytes(b"data")

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        rename_folder_dir("old_folder", "new_folder")

    assert not old.exists()
    assert (tmp_path / "new_folder" / "photo.jpg").exists()


def test_rename_folder_dir_destination_exists_raises(tmp_path):
    import pytest

    from app.services.photos_storage import rename_folder_dir

    old = tmp_path / "folder_a"
    old.mkdir()
    (old / "photo1.jpg").write_bytes(b"photo1")

    new = tmp_path / "folder_b"
    new.mkdir()
    (new / "photo2.jpg").write_bytes(b"photo2")

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        with pytest.raises(FileExistsError):
            rename_folder_dir("folder_a", "folder_b")


@pytest.mark.asyncio
async def test_generate_thumbnails_safe_refcounting(tmp_path):
    from app.services.photos_storage import generate_thumbnails_safe, _THUMB_GEN_LOCKS
    import asyncio

    photo_id = uuid.uuid4()
    key = str(photo_id)
    original_path = tmp_path / "test.jpg"
    original_path.write_bytes(b"some_data")

    # Mock generate_thumbnails to just do asyncio.sleep and return
    def mock_generate_thumbnails(*args, **kwargs):
        import time
        time.sleep(0.05)
        return {200: Path("thumb.webp")}

    with patch("app.services.photos_storage.generate_thumbnails", side_effect=mock_generate_thumbnails), \
         patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        
        # Launch two concurrent generate_thumbnails_safe tasks for the same photo_id
        t1 = asyncio.create_task(generate_thumbnails_safe(photo_id, original_path))
        await asyncio.sleep(0.01)  # let t1 start and acquire/create lock
        
        assert key in _THUMB_GEN_LOCKS
        assert _THUMB_GEN_LOCKS[key][1] == 1  # refcount is 1
        
        t2 = asyncio.create_task(generate_thumbnails_safe(photo_id, original_path))
        await asyncio.sleep(0.01)  # let t2 start and increment refcount
        
        assert _THUMB_GEN_LOCKS[key][1] == 2  # refcount is now 2
        
        await asyncio.gather(t1, t2)
        
        assert key not in _THUMB_GEN_LOCKS  # lock popped successfully after all tasks finished
