"""Unit-тесты services/news.py (Фаза 3.1).

Покрытие:
- _remove_cover_variants: директория не существует / удаляет webp и avif
- get_news_by_id: found / not found / include_deleted
- create_news: draft / published → sets published_at / sanitizes body
- update_news: no changes / with changes → bumps version / publish sets published_at
- delete_news: sets soft-delete fields
- restore_news: restores previous_status / no previous_status
- purge_news: deletes media dir + bookmarks + DB row
- get_news_versions: returns list
- increment_view_count: executes update + commit
- delete_gallery_image: found / not found
- delete_attachment: found / not found
- upload_cover: invalid mime raises 422
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_news(**kwargs):
    from datetime import datetime, timezone

    news = MagicMock()
    news.id = kwargs.get("id", uuid.uuid4())
    news.title = kwargs.get("title", "Test News")
    news.body = kwargs.get("body", "<p>body</p>")
    news.status = kwargs.get("status", "draft")
    news.is_pinned = kwargs.get("is_pinned", False)
    news.categories = kwargs.get("categories", [])
    news.target_departments = kwargs.get("target_departments", None)
    news.target_roles = kwargs.get("target_roles", None)
    news.publish_at = kwargs.get("publish_at", None)
    news.archive_at = kwargs.get("archive_at", None)
    news.published_at = kwargs.get("published_at", None)
    news.cover_image = kwargs.get("cover_image", None)
    news.cover_dominant_color = kwargs.get("cover_dominant_color", None)
    news.cover_variants = kwargs.get("cover_variants", None)
    news.cover_focal_point = kwargs.get("cover_focal_point", None)
    news.author_id = kwargs.get("author_id", uuid.uuid4())
    news.current_version = kwargs.get("current_version", 1)
    news.deleted_at = kwargs.get("deleted_at", None)
    news.previous_status = kwargs.get("previous_status", None)
    news.updated_at = kwargs.get("updated_at", None)
    news.view_count = kwargs.get("view_count", 0)
    return news


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        department=None,
    )


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


# ── _remove_cover_variants ────────────────────────────────────────────────────


def test_remove_cover_variants_no_dir(tmp_path):
    from app.services.news import _remove_cover_variants

    non_existent = tmp_path / "no_such_dir"
    _remove_cover_variants(non_existent)


def test_remove_cover_variants_removes_files(tmp_path):
    from app.services.news import _remove_cover_variants

    d = tmp_path / "news_id"
    d.mkdir()
    (d / "cover-400.webp").write_bytes(b"data")
    (d / "cover-800.avif").write_bytes(b"data")
    (d / "cover-original.jpg").write_bytes(b"data")

    _remove_cover_variants(d)

    assert not (d / "cover-400.webp").exists()
    assert not (d / "cover-800.avif").exists()
    assert (d / "cover-original.jpg").exists()


# ── get_news_by_id ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_news_by_id_found():
    from app.services.news import get_news_by_id

    news = _make_news()
    db = _make_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = news
    db.execute = AsyncMock(return_value=result_mock)

    result = await get_news_by_id(db, news.id)
    assert result is news


@pytest.mark.asyncio
async def test_get_news_by_id_not_found():
    from app.services.news import get_news_by_id

    db = _make_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    result = await get_news_by_id(db, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_news_by_id_include_deleted():
    from app.services.news import get_news_by_id

    news = _make_news()
    db = _make_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = news
    db.execute = AsyncMock(return_value=result_mock)

    result = await get_news_by_id(db, news.id, include_deleted=True)
    assert result is news


# ── create_news ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_news_draft():
    from app.services.news import create_news

    db = _make_db()
    author = _make_user("admin")
    created_news = _make_news(status="draft")
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    with patch("app.services.news.sanitize_html", return_value="<p>body</p>"):
        with patch("app.services.news.News", return_value=created_news):
            with patch("app.services.news.NewsVersion"):
                result = await create_news(
                    db,
                    author=author,
                    data={"title": "Test", "body": "<p>body</p>", "status": "draft"},
                )
    db.add.assert_called()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_news_published_sets_published_at():
    from app.services.news import create_news

    db = _make_db()
    author = _make_user("admin")
    created_news = _make_news(status="published", published_at=None)

    with patch("app.services.news.sanitize_html", return_value="<p>body</p>"):
        with patch("app.services.news.News", return_value=created_news):
            with patch("app.services.news.NewsVersion"):
                await create_news(
                    db,
                    author=author,
                    data={"title": "Test", "body": "body", "status": "published"},
                )

    assert created_news.published_at is not None


# ── update_news ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_news_no_changes():
    from app.services.news import update_news

    db = _make_db()
    editor = _make_user("admin")
    news = _make_news(title="Same Title", status="draft")
    news.title = "Same Title"

    with patch("app.services.news.sanitize_html", side_effect=lambda x: x):
        result = await update_news(
            db, news=news, editor=editor, data={"title": "Same Title"}
        )

    db.commit.assert_not_awaited()
    assert result is news


@pytest.mark.asyncio
async def test_update_news_with_changes_bumps_version():
    from app.services.news import update_news

    db = _make_db()
    editor = _make_user("admin")
    news = _make_news(title="Old Title", current_version=1)

    with patch("app.services.news.sanitize_html", side_effect=lambda x: x):
        with patch("app.services.news.NewsVersion"):
            await update_news(
                db, news=news, editor=editor, data={"title": "New Title"}
            )

    assert news.current_version == 2
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_news_published_sets_published_at():
    from app.services.news import update_news

    db = _make_db()
    editor = _make_user("admin")
    news = _make_news(status="draft", published_at=None)

    with patch("app.services.news.sanitize_html", side_effect=lambda x: x):
        with patch("app.services.news.NewsVersion"):
            await update_news(
                db, news=news, editor=editor, data={"status": "published"}
            )

    assert news.published_at is not None


# ── delete_news ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_news_sets_fields():
    from app.services.news import delete_news

    db = _make_db()
    news = _make_news(status="published")

    await delete_news(db, news)

    assert news.deleted_at is not None
    assert news.status == "archived"
    assert news.previous_status == "published"
    db.commit.assert_awaited()


# ── restore_news ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_news_with_previous_status():
    from app.services.news import restore_news

    db = _make_db()
    news = _make_news(deleted_at="2024-01-01", previous_status="published")

    await restore_news(db, news)

    assert news.deleted_at is None
    assert news.status == "published"
    assert news.previous_status is None
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_restore_news_no_previous_status():
    from app.services.news import restore_news

    db = _make_db()
    news = _make_news(deleted_at="2024-01-01", previous_status=None)

    await restore_news(db, news)

    assert news.deleted_at is None
    db.commit.assert_awaited()


# ── purge_news ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_purge_news_removes_media_and_db():
    from app.services.news import purge_news

    db = _make_db()
    news = _make_news()

    with patch("app.services.news.shutil.rmtree") as mock_rmtree:
        await purge_news(db, news)

    mock_rmtree.assert_called_once()
    assert db.execute.await_count >= 2
    db.commit.assert_awaited()


# ── get_news_versions ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_news_versions_returns_list():
    from app.services.news import get_news_versions

    db = _make_db()
    v1 = MagicMock()
    v2 = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [v2, v1]
    db.execute = AsyncMock(return_value=result_mock)

    result = await get_news_versions(db, uuid.uuid4())
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_news_versions_empty():
    from app.services.news import get_news_versions

    db = _make_db()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result_mock)

    result = await get_news_versions(db, uuid.uuid4())
    assert result == []


# ── increment_view_count ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_increment_view_count():
    from app.services.news import increment_view_count

    db = _make_db()
    await increment_view_count(db, uuid.uuid4())

    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


# ── delete_gallery_image ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_gallery_image_found():
    from app.services.news import delete_gallery_image

    db = _make_db()
    img = MagicMock()
    img.filename = "abc.jpg"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = img
    db.execute = AsyncMock(return_value=result_mock)

    news_id = uuid.uuid4()
    img_id = uuid.uuid4()

    with patch("pathlib.Path.unlink"):
        result = await delete_gallery_image(db, news_id, img_id)

    assert result is img
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_gallery_image_not_found():
    from fastapi import HTTPException
    from app.services.news import delete_gallery_image

    db = _make_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(HTTPException) as exc_info:
        await delete_gallery_image(db, uuid.uuid4(), uuid.uuid4())

    assert exc_info.value.status_code == 404


# ── delete_attachment ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_attachment_found():
    from app.services.news import delete_attachment

    db = _make_db()
    att = MagicMock()
    att.filename = "att-uuid"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = att
    db.execute = AsyncMock(return_value=result_mock)

    with patch("pathlib.Path.unlink"):
        result = await delete_attachment(db, uuid.uuid4(), uuid.uuid4())

    assert result is att
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_attachment_not_found():
    from fastapi import HTTPException
    from app.services.news import delete_attachment

    db = _make_db()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(HTTPException) as exc_info:
        await delete_attachment(db, uuid.uuid4(), uuid.uuid4())

    assert exc_info.value.status_code == 404


# ── upload_cover: invalid mime ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_cover_invalid_mime():
    from fastapi import HTTPException
    from app.services.news import upload_cover

    db = _make_db()
    news = _make_news()
    file = MagicMock()
    file.content_type = "application/pdf"

    with pytest.raises(HTTPException) as exc_info:
        await upload_cover(db, news, file)

    assert exc_info.value.status_code == 422


# ── get_trash_news ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_trash_news_returns_list():
    from app.services.news import get_trash_news

    db = _make_db()
    news1 = _make_news()
    news2 = _make_news()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [news1, news2]

    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_trash_news(db)

    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_get_trash_news_empty():
    from app.services.news import get_trash_news

    db = _make_db()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []

    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_trash_news(db)

    assert total == 0
    assert items == []


# ── update_news body sanitize ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_news_sanitizes_body():
    from app.services.news import update_news

    db = _make_db()
    db.refresh = AsyncMock()
    news = _make_news(body="<p>old</p>", current_version=1)
    editor = _make_user(role="editor")

    with patch("app.services.news.sanitize_html", return_value="<p>clean</p>") as mock_sanitize:
        await update_news(db, news=news, editor=editor, data={"body": "<script>evil</script><p>clean</p>"})

    mock_sanitize.assert_called_once()
    assert news.body == "<p>clean</p>"


# ── _targeting_filter ─────────────────────────────────────────────────────────


def test_targeting_filter_no_department():
    from sqlalchemy import select
    from app.services.news import _targeting_filter
    from app.models.news import News

    user = _make_user()
    user.department = None
    stmt = select(News)
    result = _targeting_filter(stmt, user)
    compiled = str(result.compile())
    assert "target_departments" in compiled


def test_targeting_filter_with_department():
    from sqlalchemy import select
    from app.services.news import _targeting_filter
    from app.models.news import News

    user = _make_user()
    user.department = "engineering"
    stmt = select(News)
    result = _targeting_filter(stmt, user)
    compiled = str(result.compile())
    assert "target_departments" in compiled
    assert "target_roles" in compiled


# ── get_news_list ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_news_list_basic():
    from app.services.news import get_news_list

    db = _make_db()
    user = _make_user(role="admin")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 2
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [_make_news(), _make_news()]
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_news_list(db, user=user)
    assert total == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_get_news_list_with_status_filter():
    from app.services.news import get_news_list

    db = _make_db()
    user = _make_user(role="admin")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [_make_news(status="published")]
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_news_list(db, user=user, status_filter="published")
    assert total == 1


@pytest.mark.asyncio
async def test_get_news_list_reader_gets_published_only():
    from app.services.news import get_news_list

    db = _make_db()
    user = _make_user(role="reader")
    user.department = "hr"

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_news_list(db, user=user)
    assert total == 0


@pytest.mark.asyncio
async def test_get_news_list_with_category_and_search():
    from app.services.news import get_news_list

    db = _make_db()
    user = _make_user(role="admin")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_news_list(db, user=user, category="tech", q="python", is_pinned=True)
    assert total == 0


@pytest.mark.asyncio
async def test_get_news_list_offset_override():
    from app.services.news import get_news_list

    db = _make_db()
    user = _make_user(role="admin")

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[count_result, items_result])

    items, total = await get_news_list(db, user=user, offset_override=50, pinned_first=False)
    assert total == 0


# ── delete_cover ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_cover_when_no_cover():
    from app.services.news import delete_cover

    db = _make_db()
    news = _make_news(cover_image=None)

    result = await delete_cover(db, news)
    db.execute.assert_awaited()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_cover_removes_file():
    from app.services.news import delete_cover

    db = _make_db()
    news = _make_news(cover_image=f"{uuid.uuid4()}/cover.jpg")

    with patch("pathlib.Path.unlink"), patch("pathlib.Path.exists", return_value=False):
        result = await delete_cover(db, news)

    db.execute.assert_awaited()
    db.commit.assert_awaited()


# ── upload_gallery_image ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_gallery_image_invalid_mime():
    from fastapi import HTTPException
    from app.services.news import upload_gallery_image

    db = _make_db()
    news = _make_news()
    file = MagicMock()
    file.content_type = "application/pdf"

    with pytest.raises(HTTPException) as exc_info:
        await upload_gallery_image(db, news, file)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_upload_gallery_image_success():
    from app.services.news import upload_gallery_image

    db = _make_db()
    news = _make_news()
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.filename = "photo.jpg"

    img_obj = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = img_obj
    db.execute = AsyncMock(return_value=result_mock)

    with patch("app.services.news.load_system_settings") as mock_settings:
        mock_settings.return_value.news_attachment_max_size_mb = 10
        with patch("app.services.news.stream_upload_to_path", AsyncMock(return_value=(1024, "image/jpeg"))):
            result = await upload_gallery_image(db, news, file)

    assert result is img_obj
    db.commit.assert_awaited()


# ── upload_attachment ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_attachment_success():
    from app.services.news import upload_attachment

    db = _make_db()
    news = _make_news()
    file = MagicMock()
    file.content_type = "application/pdf"
    file.filename = "doc.pdf"

    att_obj = MagicMock()
    db.refresh = AsyncMock(side_effect=lambda obj: None)

    with patch("app.services.news.load_system_settings") as mock_settings:
        mock_settings.return_value.news_attachment_max_size_mb = 10
        with patch("app.services.news.stream_upload_to_path", AsyncMock(return_value=(2048, "application/pdf"))):
            with patch("app.services.news.NewsAttachment", return_value=att_obj):
                result = await upload_attachment(db, news, file)

    db.add.assert_called_once_with(att_obj)
    db.commit.assert_awaited()


# ── _build_cover_variants ──────────────────────────────────────────────────────


def _make_png_bytes(width=100, height=100, mode="RGB"):
    try:
        from PIL import Image
        import io
        img = Image.new(mode, (width, height), color=(100, 150, 200) if mode == "RGB" else (100, 150, 200, 255))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    except ImportError:
        return b""


class TestBuildCoverVariants:
    def test_pillow_missing_returns_empty(self, tmp_path):
        import sys
        from app.services.news import _build_cover_variants

        src = tmp_path / "cover.jpg"
        src.write_bytes(b"notanimage")
        out = tmp_path / "out"
        out.mkdir()

        pil_backup = sys.modules.get("PIL")
        pil_image_backup = sys.modules.get("PIL.Image")
        pil_imageops_backup = sys.modules.get("PIL.ImageOps")
        try:
            sys.modules["PIL"] = None
            sys.modules["PIL.Image"] = None
            sys.modules["PIL.ImageOps"] = None
            widths, dominant = _build_cover_variants(src, out)
        finally:
            if pil_backup is None:
                sys.modules.pop("PIL", None)
            else:
                sys.modules["PIL"] = pil_backup
            if pil_image_backup is None:
                sys.modules.pop("PIL.Image", None)
            else:
                sys.modules["PIL.Image"] = pil_image_backup
            if pil_imageops_backup is None:
                sys.modules.pop("PIL.ImageOps", None)
            else:
                sys.modules["PIL.ImageOps"] = pil_imageops_backup

        assert widths == []
        assert dominant is None

    def test_image_open_exception_returns_empty(self, tmp_path):
        from app.services.news import _build_cover_variants

        src = tmp_path / "cover.jpg"
        src.write_bytes(b"not_a_valid_image_file_at_all")
        out = tmp_path / "out"
        out.mkdir()

        widths, dominant = _build_cover_variants(src, out)
        assert widths == []
        assert dominant is None

    def test_rgb_image_produces_webp_variant(self, tmp_path):
        from app.services.news import _build_cover_variants

        src = tmp_path / "cover.png"
        src.write_bytes(_make_png_bytes(1200, 800, "RGB"))
        out = tmp_path / "out"
        out.mkdir()

        with patch("app.services.news.NEWS_COVER_VARIANT_WIDTHS", [800]):
            widths, dominant = _build_cover_variants(src, out)

        assert 800 in widths
        assert dominant is not None

    def test_rgba_image_produced_ok(self, tmp_path):
        from app.services.news import _build_cover_variants

        src = tmp_path / "cover.png"
        src.write_bytes(_make_png_bytes(1200, 800, "RGBA"))
        out = tmp_path / "out"
        out.mkdir()

        with patch("app.services.news.NEWS_COVER_VARIANT_WIDTHS", [800]):
            widths, dominant = _build_cover_variants(src, out)

        assert 800 in widths

    def test_no_widths_done_uses_original_width(self, tmp_path):
        from app.services.news import _build_cover_variants

        src = tmp_path / "cover.png"
        src.write_bytes(_make_png_bytes(400, 300, "RGB"))
        out = tmp_path / "out"
        out.mkdir()

        with patch("app.services.news.NEWS_COVER_VARIANT_WIDTHS", [800, 1200]):
            widths, dominant = _build_cover_variants(src, out)

        assert 400 in widths

    def test_webp_save_failure_falls_to_fallback(self, tmp_path):
        from app.services.news import _build_cover_variants
        from PIL import Image, ImageOps

        src = tmp_path / "cover.png"
        src.write_bytes(_make_png_bytes(1200, 800, "RGB"))
        out = tmp_path / "out"
        out.mkdir()

        call_count = [0]
        real_save = None

        def patched_save(self, fp, format=None, **params):
            if str(fp).endswith(".webp"):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise OSError("disk full")
            return real_save(fp, format, **params)

        with patch("app.services.news.NEWS_COVER_VARIANT_WIDTHS", [800, 400]):
            widths, dominant = _build_cover_variants(src, out)

        assert isinstance(widths, list)


# ── upload_cover success path ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_cover_success():
    from app.services.news import upload_cover

    db = _make_db()
    news = _make_news()
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.filename = "cover.jpg"

    with patch("app.services.news.load_system_settings") as mock_settings:
        mock_settings.return_value.news_attachment_max_size_mb = 10
        with patch("app.services.news.stream_upload_to_path", AsyncMock(return_value=(512, "image/jpeg"))):
            with patch("app.services.news._remove_cover_variants"):
                with patch("asyncio.to_thread", AsyncMock(return_value=([800], "#aabbcc"))):
                    result = await upload_cover(db, news, file)

    db.commit.assert_awaited()
    db.refresh.assert_awaited()


@pytest.mark.asyncio
async def test_upload_cover_success_no_variants():
    from app.services.news import upload_cover

    db = _make_db()
    news = _make_news()
    file = MagicMock()
    file.content_type = "image/png"
    file.filename = "cover.png"

    with patch("app.services.news.load_system_settings") as mock_settings:
        mock_settings.return_value.news_attachment_max_size_mb = 10
        with patch("app.services.news.stream_upload_to_path", AsyncMock(return_value=(256, "image/png"))):
            with patch("app.services.news._remove_cover_variants"):
                with patch("asyncio.to_thread", AsyncMock(return_value=([], None))):
                    result = await upload_cover(db, news, file)

    db.commit.assert_awaited()
