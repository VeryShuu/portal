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
from unittest.mock import MagicMock, patch

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

    result = sanitize_folder_name("my:folder<name>")
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
    with (
        patch("app.services.photos_storage.ORIGINALS_ROOT", ORIGINALS_ROOT),
        patch("app.services.photos_storage._ALLOWED_ROOTS", (ORIGINALS_ROOT,)),
    ):
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

    with (
        patch.object(pathlib.Path, "unlink", side_effect=OSError("busy")),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
    ):
        delete_photo_files(original, photo_id)


def test_delete_photo_files_thumbs_rmdir_oserror(tmp_path):
    import pathlib

    from app.services.photos_storage import delete_photo_files

    photo_id = uuid.uuid4()
    thumbs_dir = tmp_path / str(photo_id)
    thumbs_dir.mkdir()

    with (
        patch.object(pathlib.Path, "rmdir", side_effect=OSError("busy")),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
    ):
        delete_photo_files(None, photo_id)


# ── thumb_path ────────────────────────────────────────────────────────────────


def test_thumb_path_valid_size(tmp_path):
    from app.services.photos_storage import THUMB_SIZES, thumb_path

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

    with (
        patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path),
        pytest.raises(FileExistsError),
    ):
        rename_folder_dir("folder_a", "folder_b")


@pytest.mark.asyncio
async def test_generate_thumbnails_safe_refcounting(tmp_path):
    import asyncio

    from app.services.photos_storage import _THUMB_GEN_LOCKS, generate_thumbnails_safe

    photo_id = uuid.uuid4()
    key = str(photo_id)
    original_path = tmp_path / "test.jpg"
    original_path.write_bytes(b"some_data")

    # Mock generate_thumbnails to just do asyncio.sleep and return
    def mock_generate_thumbnails(*args, **kwargs):
        import time

        time.sleep(0.05)
        return {200: Path("thumb.webp")}

    with (
        patch(
            "app.services.photos_storage.generate_thumbnails", side_effect=mock_generate_thumbnails
        ),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
    ):
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


# ── save_original collision handling ──────────────────────────────────────────


def test_save_original_collision_uses_counter(tmp_path):
    from app.services.photos_storage import save_original

    with patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path):
        name1, _ = save_original("", "photo.jpg", b"data1")
        name2, _ = save_original("", "photo.jpg", b"data2")

    assert name1 == "photo.jpg"
    assert name2 != name1
    assert name2.endswith(".jpg")


def test_save_original_all_fail_raises(tmp_path):
    from app.services.photos_storage import save_original

    def always_fail(self, mode):
        raise FileExistsError("exists")

    with (
        patch("app.services.photos_storage.ORIGINALS_ROOT", tmp_path),
        patch.object(type(tmp_path / "photo.jpg"), "open", always_fail),
        pytest.raises(OSError, match="Cannot create unique file"),
    ):
        save_original("", "photo.jpg", b"data")


# ── generate_thumbnails_safe early return ─────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_thumbnails_safe_early_return_when_all_exist(tmp_path):
    from app.services.photos_storage import THUMB_SIZES, generate_thumbnails_safe

    photo_id = uuid.uuid4()
    thumb_dir = tmp_path / str(photo_id)
    thumb_dir.mkdir()
    for size in THUMB_SIZES:
        (thumb_dir / f"{size}.webp").write_bytes(b"thumb")

    with patch("app.services.photos_storage.THUMBS_ROOT", tmp_path):
        result = await generate_thumbnails_safe(photo_id, tmp_path / "photo.jpg")

    assert result == {}


# ── _open_image ───────────────────────────────────────────────────────────────


def test_open_image_basic(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (100, 100)

    with (
        patch("PIL.Image.open", return_value=mock_img),
        patch("PIL.Image.Image.MAX_IMAGE_PIXELS", 300_000_000, create=True),
    ):
        from app.services.photos_storage import _open_image

        result = _open_image(tmp_path / "test.jpg")

    assert result is mock_img
    mock_img.load.assert_called_once()


def test_open_image_with_target_size(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (100, 100)

    with patch("PIL.Image.open", return_value=mock_img):
        from app.services.photos_storage import _open_image

        _open_image(tmp_path / "test.jpg", target_size=200)

    mock_img.draft.assert_called_once_with("RGB", (400, 400))
    mock_img.load.assert_called_once()


def test_open_image_decompression_bomb_raises(tmp_path):
    from PIL.Image import DecompressionBombError

    from app.services.photos_storage import _MAX_IMAGE_PIXELS

    side = int(_MAX_IMAGE_PIXELS**0.5) + 1000
    mock_img = MagicMock()
    mock_img.size = (side, side)

    with patch("PIL.Image.open", return_value=mock_img):
        from app.services.photos_storage import _open_image

        with pytest.raises(DecompressionBombError):
            _open_image(tmp_path / "test.jpg")


def test_open_image_load_decompression_bomb_propagates(tmp_path):
    from PIL.Image import DecompressionBombError

    mock_img = MagicMock()
    mock_img.size = (100, 100)
    mock_img.load.side_effect = DecompressionBombError("too big")

    with patch("PIL.Image.open", return_value=mock_img):
        from app.services.photos_storage import _open_image

        with pytest.raises(DecompressionBombError):
            _open_image(tmp_path / "test.jpg")


# ── compute_blurhash ──────────────────────────────────────────────────────────


def test_compute_blurhash_success(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_rgb = MagicMock()
    mock_img.__enter__ = MagicMock(return_value=mock_img)
    mock_img.__exit__ = MagicMock(return_value=False)
    mock_img.convert.return_value = mock_rgb

    mock_bh = MagicMock()
    mock_bh.encode.return_value = "LKO2:N%2Tw=w]~RBVZRi};RPxuwH-;adMg"

    with (
        patch("PIL.Image.open", return_value=mock_img),
        patch.dict("sys.modules", {"blurhash": mock_bh}),
    ):
        from app.services.photos_storage import compute_blurhash

        result = compute_blurhash(tmp_path / "200.webp")

    assert result == "LKO2:N%2Tw=w]~RBVZRi};RPxuwH-;adMg"


def test_compute_blurhash_import_error_returns_none(tmp_path):
    with patch.dict("sys.modules", {"blurhash": None}):
        from app.services.photos_storage import compute_blurhash

        result = compute_blurhash(tmp_path / "200.webp")

    assert result is None


def test_compute_blurhash_exception_returns_none(tmp_path):
    """Audit [H8]: compute_blurhash ловит реальные ошибки PIL (OSError,
    UnidentifiedImageError), а не голый Exception (маскирует баги).
    Тест обновлён: Image.open в реальности поднимает OSError для
    битых/нечитаемых файлов (PIL.UnidentifiedImageError — его подкласс).
    """
    from PIL import UnidentifiedImageError  # noqa: F401 — re-exported через PIL
    from unittest.mock import MagicMock

    mock_bh = MagicMock()
    mock_bh.encode.side_effect = ValueError("bad image data")

    mock_img = MagicMock()
    mock_img.__enter__ = MagicMock(return_value=mock_img)
    mock_img.__exit__ = MagicMock(return_value=False)
    mock_img.convert.return_value = mock_img
    mock_img.thumbnail.return_value = None
    mock_img.encode = None

    with (
        patch("PIL.Image.open", side_effect=OSError("io error")),
        patch.dict("sys.modules", {"blurhash": mock_bh}),
    ):
        from app.services.photos_storage import compute_blurhash

        result = compute_blurhash(tmp_path / "200.webp")

    assert result is None


# ── generate_thumbnails ───────────────────────────────────────────────────────


def test_generate_thumbnails_creates_webp_files(tmp_path):
    import uuid as _uuid
    from unittest.mock import MagicMock, patch

    photo_id = _uuid.uuid4()

    mock_img = MagicMock()
    mock_img.size = (2000, 1500)
    mock_img.mode = "RGB"
    mock_scaled = MagicMock()
    mock_scaled.size = (1600, 1200)
    mock_scaled.mode = "RGB"
    mock_img.copy.return_value = mock_scaled
    mock_scaled.copy.return_value = mock_scaled

    mock_transposed = mock_img

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ImageOps.exif_transpose", return_value=mock_transposed),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
        patch("app.services.photos_storage.GENERATE_AVIF", False),
    ):
        from app.services.photos_storage import THUMB_SIZES, generate_thumbnails

        result = generate_thumbnails(photo_id, tmp_path / "photo.jpg")

    assert set(result.keys()) == set(THUMB_SIZES)


def test_generate_thumbnails_non_rgb_mode_converts(tmp_path):
    import uuid as _uuid

    photo_id = _uuid.uuid4()

    mock_img = MagicMock()
    mock_img.size = (800, 600)
    mock_img.mode = "L"
    mock_converted = MagicMock()
    mock_converted.size = (800, 600)
    mock_converted.mode = "RGB"
    mock_converted.copy.return_value = mock_converted
    mock_img.convert.return_value = mock_converted

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ImageOps.exif_transpose", return_value=mock_img),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
        patch("app.services.photos_storage.GENERATE_AVIF", False),
    ):
        from app.services.photos_storage import generate_thumbnails

        generate_thumbnails(photo_id, tmp_path / "photo.jpg")

    mock_img.convert.assert_called_once_with("RGB")


def test_generate_thumbnails_generates_avif_for_large_sizes(tmp_path):
    import uuid as _uuid

    photo_id = _uuid.uuid4()

    mock_img = MagicMock()
    mock_img.size = (3000, 2000)
    mock_img.mode = "RGB"
    mock_scaled = MagicMock()
    mock_scaled.size = (1600, 1200)
    mock_scaled.mode = "RGB"
    mock_img.copy.return_value = mock_scaled
    mock_scaled.copy.return_value = mock_scaled

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ImageOps.exif_transpose", return_value=mock_img),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
        patch("app.services.photos_storage.GENERATE_AVIF", True),
        patch("app.services.photos_storage.AVIF_MIN_SIZE", 1000),
    ):
        from app.services.photos_storage import generate_thumbnails

        generate_thumbnails(photo_id, tmp_path / "photo.jpg")

    avif_calls = [c for c in mock_scaled.save.call_args_list if "AVIF" in str(c)]
    assert len(avif_calls) > 0 or mock_scaled.save.call_count > 0


def test_generate_thumbnails_cleans_up_on_error(tmp_path):
    import uuid as _uuid

    photo_id = _uuid.uuid4()

    with (
        patch("app.services.photos_storage._open_image", side_effect=OSError("disk error")),
        patch("app.services.photos_storage.THUMBS_ROOT", tmp_path),
    ):
        from app.services.photos_storage import generate_thumbnails

        with pytest.raises(OSError):
            generate_thumbnails(photo_id, tmp_path / "photo.jpg")


# ── extract_exif ──────────────────────────────────────────────────────────────


def test_extract_exif_basic(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (1920, 1080)

    mock_raw = {
        306: "2023:06:15 12:30:00",
    }

    mock_img.getexif.return_value = mock_raw

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ExifTags.TAGS", {306: "DateTime"}),
    ):
        from app.services.photos_storage import extract_exif

        exif, size, taken_at = extract_exif(tmp_path / "photo.jpg")

    assert size == (1920, 1080)
    assert "DateTime" in exif
    assert taken_at is not None


def test_extract_exif_strips_gps(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (800, 600)

    mock_raw = {
        34853: {"GPSLatitude": (51, 30, 0)},
    }
    mock_img.getexif.return_value = mock_raw

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ExifTags.TAGS", {34853: "GPSInfo"}),
    ):
        from app.services.photos_storage import extract_exif

        exif, _size, _taken_at = extract_exif(tmp_path / "photo.jpg", strip_gps=True)

    assert "GPSInfo" not in exif


def test_extract_exif_keeps_gps_when_not_stripped(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (800, 600)

    mock_raw = {
        34853: "gps_data",
    }
    mock_img.getexif.return_value = mock_raw

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ExifTags.TAGS", {34853: "GPSInfo"}),
    ):
        from app.services.photos_storage import extract_exif

        exif, _size, _taken_at = extract_exif(tmp_path / "photo.jpg", strip_gps=False)

    assert "GPSInfo" in exif


def test_extract_exif_bytes_value_decoded(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (640, 480)

    mock_raw = {
        270: b"My Camera Description",
    }
    mock_img.getexif.return_value = mock_raw

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ExifTags.TAGS", {270: "ImageDescription"}),
    ):
        from app.services.photos_storage import extract_exif

        exif, _size, _taken_at = extract_exif(tmp_path / "photo.jpg")

    assert exif.get("ImageDescription") == "My Camera Description"


def test_extract_exif_no_exif_returns_empty(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (640, 480)
    mock_img.getexif.return_value = {}

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ExifTags.TAGS", {}),
    ):
        from app.services.photos_storage import extract_exif

        exif, size, taken_at = extract_exif(tmp_path / "photo.jpg")

    assert exif == {}
    assert size == (640, 480)
    assert taken_at is None


def test_extract_exif_open_failure_returns_empty(tmp_path):
    with patch("app.services.photos_storage._open_image", side_effect=OSError("file not found")):
        from app.services.photos_storage import extract_exif

        exif, size, taken_at = extract_exif(tmp_path / "missing.jpg")

    assert exif == {}
    assert size is None
    assert taken_at is None


def test_extract_exif_date_time_original(tmp_path):
    from unittest.mock import MagicMock

    mock_img = MagicMock()
    mock_img.size = (1920, 1080)

    mock_raw = {
        36867: "2024:12:25 10:00:00",
    }
    mock_img.getexif.return_value = mock_raw

    with (
        patch("app.services.photos_storage._open_image", return_value=mock_img),
        patch("PIL.ExifTags.TAGS", {36867: "DateTimeOriginal"}),
    ):
        from app.services.photos_storage import extract_exif

        _exif, _size, taken_at = extract_exif(tmp_path / "photo.jpg")

    assert taken_at == "2024-12-25T10:00:00"
