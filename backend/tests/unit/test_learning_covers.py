"""Unit-тесты обложек курсов (этап 2, ТЗ §6.2): Pillow-превью, канонический
путь раздачи, загрузка/удаление на файловой системе, построение cover_url."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.models.learning import LearningCourse
from app.services.learning import courses_service as cs
from app.services.learning import covers as cover_svc


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(cs, "LEARNING_DATA_DIR", str(tmp_path / "learning"))
    return tmp_path / "learning" / "covers"


def _png_bytes(width: int = 2000, height: int = 500) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


def _upload(data: bytes, content_type: str, filename: str = "cover.png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _course() -> LearningCourse:
    """Стаб курса: сервис трогает только id/cover_path/updated_at."""
    return cast(LearningCourse, SimpleNamespace(id=uuid.uuid4(), cover_path=None, updated_at=None))


def _db() -> AsyncSession:
    """Стаб сессии: сервис вызывает только db.flush()."""
    return cast(AsyncSession, _DbStub())


class _DbStub:
    async def flush(self):
        return None


class TestUploadCover:
    async def test_rejects_non_image_content_type(self, data_dir: Path):
        with pytest.raises(HTTPException) as exc:
            await cover_svc.upload_cover(_db(), _course(), _upload(b"x", "application/pdf"))
        assert exc.value.status_code == 422
        assert not data_dir.exists()  # до стриминга дело не дошло

    async def test_rejects_real_mime_mismatch(self, data_dir: Path):
        """python-magic видит не-изображение, несмотря на заявленный PNG."""
        with pytest.raises(HTTPException) as exc:
            await cover_svc.upload_cover(
                _db(), _course(), _upload(b"definitely not an image", "image/png")
            )
        assert exc.value.status_code == 422

    async def test_builds_webp_preview_and_cleans_staging(self, data_dir: Path):
        course = _course()
        out = await cover_svc.upload_cover(
            _db(), course, _upload(_png_bytes(width=2000, height=500), "image/png")
        )
        preview = data_dir / f"{course.id}.webp"
        assert out.cover_path == str(preview)
        assert preview.is_file()
        from PIL import Image

        with Image.open(preview) as img:
            assert img.format == "WEBP"
            assert img.width <= cover_svc.COVER_MAX_WIDTH  # 2000 → уменьшено
        assert list(data_dir.glob("*.staging.*")) == []  # staging убран

    async def test_reupload_replaces_old_files(self, data_dir: Path):
        course = _course()
        await cover_svc.upload_cover(
            _db(), course, _upload(_png_bytes(width=300, height=100), "image/png")
        )
        await cover_svc.upload_cover(
            _db(), course, _upload(_png_bytes(width=400, height=100), "image/png")
        )
        files = list(data_dir.iterdir())
        assert files == [data_dir / f"{course.id}.webp"]

    async def test_corrupt_image_yields_422(self, data_dir: Path):
        """Валидный по magic заголовок, битое содержимое — 422, без пути в БД."""
        png = _png_bytes(width=10, height=10)
        with pytest.raises(HTTPException) as exc:
            await cover_svc.upload_cover(
                _db(), _course(), _upload(png[:12] + b"\x00" * 32, "image/png")
            )
        assert exc.value.status_code == 422
        course_files = list(data_dir.glob("*.webp"))
        assert course_files == []


class TestDeleteCover:
    async def test_removes_files_and_clears_path(self, data_dir: Path):
        course = _course()
        await cover_svc.upload_cover(
            _db(), course, _upload(_png_bytes(width=300, height=100), "image/png")
        )
        out = await cover_svc.delete_cover(_db(), course)
        assert out.cover_path is None
        assert list(data_dir.iterdir()) == []


class TestResolveCoverPath:
    def test_none_without_cover(self, data_dir: Path):
        course = _course()
        assert cover_svc.resolve_cover_path(course) is None

    def test_none_on_foreign_path(self, data_dir: Path):
        course = _course()
        course.cover_path = "/etc/passwd"
        assert cover_svc.resolve_cover_path(course) is None

    def test_none_when_file_missing(self, data_dir: Path):
        course = _course()
        expected = data_dir / f"{course.id}.webp"
        course.cover_path = str(expected)
        assert cover_svc.resolve_cover_path(course) is None

    def test_canonical_path_when_file_exists(self, data_dir: Path):
        course = _course()
        expected = data_dir / f"{course.id}.webp"
        data_dir.mkdir(parents=True)
        expected.write_bytes(b"webp-bytes")
        course.cover_path = str(expected)
        assert cover_svc.resolve_cover_path(course) == expected


class TestBuildCoverPreview:
    def test_rgba_transparency_preserved(self, tmp_path: Path):
        from PIL import Image

        src = tmp_path / "src.png"
        Image.new("RGBA", (100, 80), (1, 2, 3, 128)).save(src, "PNG")
        dest = tmp_path / "out.webp"
        cover_svc.build_cover_preview(src, dest)
        with Image.open(dest) as img:
            assert img.format == "WEBP"
            assert img.mode == "RGBA"

    def test_small_image_not_upscaled(self, tmp_path: Path):
        from PIL import Image

        src = tmp_path / "src.png"
        Image.new("RGB", (50, 20), (0, 0, 0)).save(src, "PNG")
        dest = tmp_path / "out.webp"
        cover_svc.build_cover_preview(src, dest)
        with Image.open(dest) as img:
            assert img.size == (50, 20)


class TestCoverUrls:
    """cover_path наружу не идёт (exclude); URL зависит от контура:
    админу — admin-роут, участнику — me-роут (проверка зачисления)."""

    @staticmethod
    def _payload(cover: str | None) -> dict:
        return {
            "id": uuid.uuid4(),
            "slug": "kurs-1",
            "title": "Курс",
            "description": None,
            "status": "published",
            "published_at": None,
            "created_at": datetime(2026, 8, 29, tzinfo=UTC),
            "updated_at": datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
            "cover_path": cover,
        }

    def test_admin_url_built_from_cover(self):
        from app.schemas.learning import CourseOut

        out = CourseOut.model_validate(self._payload(cover="/data/learning/covers/x.webp"))
        assert out.cover_url is not None
        assert out.cover_url.startswith(f"/api/v1/learning/admin/courses/{out.id}/cover?v=")
        assert "cover_path" not in out.model_dump()
        assert "updated_at" not in out.model_dump()

    def test_no_cover_no_url(self):
        from app.schemas.learning import CourseOut

        out = CourseOut.model_validate(self._payload(cover=None))
        assert out.cover_url is None

    def test_learner_url_overrides_admin(self):
        from app.schemas.learning import MyCourseDetailOut

        out = MyCourseDetailOut.model_validate(
            {**self._payload(cover="/data/learning/covers/x.webp"), "items": []}
        )
        expected_v = int(datetime(2026, 8, 29, 12, 0, tzinfo=UTC).timestamp())
        assert out.cover_url == f"/api/v1/learning/me/courses/kurs-1/cover?v={expected_v}"
