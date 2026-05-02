"""Unit-тесты для services/photos_storage.py.

Покрытие:
- sanitize_filename: ASCII, unicode, длинные имена, пустые, спецсимволы
- sanitize_folder_name: кириллица, path-traversal, OS-reserved символы, пустые
- is_allowed_ext: допустимые/недопустимые расширения
- folder_fs_path: relative path → ORIGINALS_ROOT, path-traversal защита
- folder_fs_path: абсолютный путь внутри разрешённых корней
- folder_fs_path: абсолютный путь вне корней → ValueError
- _unique_name: коллизии добавляют суффикс
- save_original: сохранение bytes и file-like объекта
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── sanitize_filename ─────────────────────────────────────────────────────────


class TestSanitizeFilename:
    def test_plain_ascii_unchanged(self):
        from app.services.photos_storage import sanitize_filename

        assert sanitize_filename("photo.jpg") == "photo.jpg"

    def test_cyrillic_transliterated_to_hyphens(self):
        from app.services.photos_storage import sanitize_filename

        result = sanitize_filename("фото.jpg")
        assert result.endswith(".jpg") or result == "photo"
        assert "\u0444" not in result

    def test_spaces_replaced_with_hyphens(self):
        from app.services.photos_storage import sanitize_filename

        result = sanitize_filename("my photo.jpg")
        assert " " not in result

    def test_empty_name_returns_photo(self):
        from app.services.photos_storage import sanitize_filename

        result = sanitize_filename("")
        assert result == "photo"

    def test_long_name_truncated_with_hash(self):
        from app.services.photos_storage import sanitize_filename

        long_name = "a" * 200 + ".jpg"
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_special_chars_removed(self):
        from app.services.photos_storage import sanitize_filename

        result = sanitize_filename("file@name!.jpg")
        assert "@" not in result
        assert "!" not in result

    def test_keeps_extension(self):
        from app.services.photos_storage import sanitize_filename

        result = sanitize_filename("image.PNG")
        assert "." in result

    def test_only_dots_and_dashes(self):
        from app.services.photos_storage import sanitize_filename

        result = sanitize_filename("...")
        assert result != ""
        assert len(result) > 0


# ── sanitize_folder_name ──────────────────────────────────────────────────────


class TestSanitizeFolderName:
    def test_keeps_cyrillic(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("Отдел кадров")
        assert "Отдел" in result
        assert "кадров" in result

    def test_empty_returns_folder(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("")
        assert result == "folder"

    def test_path_traversal_dots_rejected(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("..")
        assert result == "folder"

    def test_reserved_chars_replaced(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("folder/name")
        assert "/" not in result

    def test_backslash_replaced(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("folder\\name")
        assert "\\" not in result

    def test_long_name_truncated(self):
        from app.services.photos_storage import sanitize_folder_name

        long_name = "А" * 250
        result = sanitize_folder_name(long_name)
        assert len(result) <= 210

    def test_trailing_dots_stripped(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("folder...")
        assert not result.endswith(".")

    def test_multiple_hyphens_collapsed(self):
        from app.services.photos_storage import sanitize_folder_name

        result = sanitize_folder_name("a  b  c")
        assert "  " not in result


# ── is_allowed_ext ────────────────────────────────────────────────────────────


class TestIsAllowedExt:
    def test_jpg_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("photo.jpg") is True
        assert is_allowed_ext("photo.jpeg") is True

    def test_png_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("image.png") is True

    def test_webp_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("image.webp") is True

    def test_heic_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("image.heic") is True
        assert is_allowed_ext("image.heif") is True

    def test_gif_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("anim.gif") is True

    def test_tif_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("scan.tif") is True
        assert is_allowed_ext("scan.tiff") is True

    def test_uppercase_extension_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("photo.JPG") is True
        assert is_allowed_ext("photo.PNG") is True

    def test_exe_not_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("virus.exe") is False

    def test_pdf_not_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("doc.pdf") is False

    def test_mp4_not_allowed(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("video.mp4") is False

    def test_no_extension(self):
        from app.services.photos_storage import is_allowed_ext

        assert is_allowed_ext("noext") is False


# ── folder_fs_path ────────────────────────────────────────────────────────────


class TestFolderFsPath:
    def test_relative_path_resolves_to_originals_root(self, tmp_path):
        from app.services import photos_storage as ps

        with patch.object(ps, "ORIGINALS_ROOT", tmp_path / "originals"):
            from app.services.photos_storage import folder_fs_path

            result = folder_fs_path("HR/Docs")
        expected = (tmp_path / "originals" / "HR" / "Docs").resolve()
        assert result == expected

    def test_empty_path_returns_originals_root(self, tmp_path):
        from app.services import photos_storage as ps

        originals = tmp_path / "originals"
        with patch.object(ps, "ORIGINALS_ROOT", originals):
            from app.services.photos_storage import folder_fs_path

            result = folder_fs_path("")
        assert result == originals.resolve()

    def test_path_traversal_rejected(self, tmp_path):
        from app.services import photos_storage as ps

        with patch.object(ps, "ORIGINALS_ROOT", tmp_path / "originals"):
            from app.services.photos_storage import folder_fs_path

            with pytest.raises(ValueError, match="Invalid folder path"):
                folder_fs_path("../../etc/passwd")

    def test_absolute_path_within_allowed_root(self, tmp_path):
        from app.services import photos_storage as ps

        import_root = tmp_path / "import"
        import_root.mkdir(parents=True)
        target = import_root / "subfolder"
        target.mkdir()

        with (
            patch.object(ps, "ORIGINALS_ROOT", tmp_path / "originals"),
            patch.object(ps, "IMPORT_ROOT", import_root),
            patch.object(ps, "_ALLOWED_ROOTS", (tmp_path / "originals", import_root, tmp_path / "zips")),
        ):
            from app.services.photos_storage import folder_fs_path

            result = folder_fs_path(str(target))
        assert result == target.resolve()

    def test_absolute_path_outside_allowed_roots_raises(self, tmp_path):
        from app.services import photos_storage as ps

        with (
            patch.object(ps, "ORIGINALS_ROOT", tmp_path / "originals"),
            patch.object(ps, "IMPORT_ROOT", tmp_path / "import"),
            patch.object(ps, "ZIPS_ROOT", tmp_path / "zips"),
            patch.object(ps, "_ALLOWED_ROOTS", (tmp_path / "originals", tmp_path / "import", tmp_path / "zips")),
        ):
            from app.services.photos_storage import folder_fs_path

            with pytest.raises(ValueError, match="Invalid folder path"):
                folder_fs_path("/etc/passwd")

    def test_dot_dot_segments_filtered(self, tmp_path):
        from app.services import photos_storage as ps

        with patch.object(ps, "ORIGINALS_ROOT", tmp_path / "originals"):
            from app.services.photos_storage import folder_fs_path

            result = folder_fs_path("valid/../valid")
        expected = (tmp_path / "originals" / "valid").resolve()
        assert result == expected


# ── save_original ─────────────────────────────────────────────────────────────


class TestSaveOriginal:
    def test_save_bytes(self, tmp_path):
        from app.services import photos_storage as ps

        originals = tmp_path / "originals"
        with patch.object(ps, "ORIGINALS_ROOT", originals):
            from app.services.photos_storage import save_original

            fname, size = save_original("folder1", "test.jpg", b"fakeimagebytes")
        assert size == len(b"fakeimagebytes")
        assert fname.endswith(".jpg") or "." in fname
        saved = originals / "folder1" / fname
        assert saved.exists()
        assert saved.read_bytes() == b"fakeimagebytes"

    def test_save_file_like(self, tmp_path):
        from app.services import photos_storage as ps

        originals = tmp_path / "originals"
        data = b"binary data content"
        with patch.object(ps, "ORIGINALS_ROOT", originals):
            from app.services.photos_storage import save_original

            fobj = io.BytesIO(data)
            fname, size = save_original("folder2", "photo.png", fobj)
        assert size == len(data)
        saved = originals / "folder2" / fname
        assert saved.exists()

    def test_collision_adds_suffix(self, tmp_path):
        from app.services import photos_storage as ps

        originals = tmp_path / "originals"
        folder = originals / "col"
        folder.mkdir(parents=True)
        (folder / "img.jpg").write_bytes(b"existing")

        with patch.object(ps, "ORIGINALS_ROOT", originals):
            from app.services.photos_storage import save_original

            fname, _ = save_original("col", "img.jpg", b"new")
        assert fname != "img.jpg"
        assert (folder / fname).exists()
