"""Unit-тесты встраивания локализованных email-attachments в исходящее письмо.

``_embed_helpdesk_attachment_images`` — находит в HTML ``<img src="/api/v1/
helpdesk/attachments/{id}">`` (картинки из истории переписки — локализованные
email-attachments, сохранённые через ``email_images.py`` при ingress), одним
DB-запросом подтягивает метаданные, читает файлы с диска и переписывает
``src`` на ``cid:``. Без этой ветки почтовый клиент не грузит картинки
(endpoint attachments требует session-cookie, а письмо — нет).

Покрывает:
* rewrite src→cid для картинки из attachments (от заявителя, email-ingress).
* один DB-запрос на все id (защита от N+1).
* фильтр по image/* (PDF/DOCX пропускаются, не падают).
* missing-file best-effort (src остаётся URL).
* отсутствие attachment-ссылок — ранний выход без DB-запроса.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.tasks.email_outbox import _embed_helpdesk_attachment_images


def _img_html(url: str) -> str:
    return f'<p>История:</p><img src="{url}" alt="скрин"/>'


def _att_url(att_id: uuid.UUID) -> str:
    return f"/api/v1/helpdesk/attachments/{att_id}"


def _mock_db_session(rows: list[tuple]) -> MagicMock:
    """Мок ``AsyncSessionLocal()``: ``db.execute(...)`` возвращает ``rows``.

    ``rows`` — список кортежей ``(att_id, filename, content_type)``
    (как в реальном SELECT)."""
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestEmbedAttachmentImages:
    """Прямые тесты хелпера ``_embed_helpdesk_attachment_images``."""

    @pytest.mark.asyncio
    async def test_rewrites_src_to_cid(self, tmp_path) -> None:
        """Картинка из attachments → cid:-attach (читается с диска)."""
        att_id = uuid.uuid4()
        filename = "abc_image001.png"
        img_path = tmp_path / "TKT-123" / filename
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\x89PNG fake png data")
        url = _att_url(att_id)
        html = _img_html(url)

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([(att_id, filename, "image/png")]),
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 123)

        assert 'src="cid:img-' in new_html
        assert url not in new_html
        assert len(images) == 1
        assert images[0]["mime"] == "image/png"
        assert images[0]["cid"].startswith("img-")

    @pytest.mark.asyncio
    async def test_absolute_url_with_scheme_and_host(self, tmp_path) -> None:
        """URL с scheme://host (``https://portal.local/api/...``) тоже матчится
        (email_template._absolutize_img_src делает абсолютный URL для письма)."""
        att_id = uuid.uuid4()
        filename = "ab_photo.jpg"
        img_path = tmp_path / "TKT-7" / filename
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\xff\xd8\xff\xe0 fake jpg")
        url = f"https://portal.local/api/v1/helpdesk/attachments/{att_id}"
        html = _img_html(url)

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([(att_id, filename, "image/jpeg")]),
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 7)

        assert 'src="cid:img-' in new_html
        assert len(images) == 1
        assert images[0]["mime"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_single_db_query_for_all_ids(self, tmp_path) -> None:
        """Несколько картинок → ОДИН DB-запрос (``id IN (...)``), не N+1."""
        att1, att2 = uuid.uuid4(), uuid.uuid4()
        f1, f2 = "a_img1.png", "b_img2.png"
        ticket_dir = tmp_path / "TKT-1"
        ticket_dir.mkdir(parents=True, exist_ok=True)
        for fn in (f1, f2):
            (ticket_dir / fn).write_bytes(b"\x89PNG fake")
        html = _img_html(_att_url(att1)) + _img_html(_att_url(att2))

        session_ctx = _mock_db_session([(att1, f1, "image/png"), (att2, f2, "image/png")])
        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=session_ctx,
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 1)

        # Один db.execute (один SELECT IN).
        inner_session = session_ctx.__aenter__.return_value
        assert inner_session.execute.await_count == 1
        assert len(images) == 2
        assert new_html.count('src="cid:img-') == 2

    @pytest.mark.asyncio
    async def test_dedup_same_attachment_referenced_twice(self, tmp_path) -> None:
        """Одна и та же картинка встречается 2 раза в HTML → 1 inline-image,
        оба src переписаны на один cid."""
        att_id = uuid.uuid4()
        filename = "dup.png"
        img_path = tmp_path / "TKT-9" / filename
        img_path.parent.mkdir(parents=True)
        img_path.write_bytes(b"\x89PNG dup")
        url = _att_url(att_id)
        html = _img_html(url) + "<hr/>" + _img_html(url)

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([(att_id, filename, "image/png")]),
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 9)

        assert len(images) == 1, "дедуп по id — одна картинка, два src на один cid"
        assert new_html.count('src="cid:img-') == 2

    @pytest.mark.asyncio
    async def test_non_image_attachments_skipped(self, tmp_path) -> None:
        """PDF/DOCX (``content_type != image/*``) не встраиваются как cid —
        ``<img>`` всё равно не отрендерит, и они должны пойти как обычные
        attachment (через payload.attachments в ``_build_helpdesk_mime``)."""
        pdf_att = uuid.uuid4()
        url = _att_url(pdf_att)
        html = _img_html(url)

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([(pdf_att, "doc.pdf", "application/pdf")]),
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 5)

        # src НЕ переписан (PDF пропущен), inline_images пустой.
        assert url in new_html
        assert images == []

    @pytest.mark.asyncio
    async def test_missing_file_keeps_url_best_effort(self, tmp_path) -> None:
        """Файл отсутствует на диске (удалён к моменту отправки письма) — src
        остаётся URL, письмо не роняется. В веб-ленте картинка всё равно видна."""
        att_id = uuid.uuid4()
        url = _att_url(att_id)
        html = _img_html(url)
        # Не создаём файл — disk_path.exists() == False.

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([(att_id, "missing.png", "image/png")]),
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 99)

        assert url in new_html, "URL остаётся (файл не найден)"
        assert images == []

    @pytest.mark.asyncio
    async def test_no_attachment_urls_early_exit_no_db_query(self) -> None:
        """HTML без attachment-ссылок (только rich-inline или plain текст) —
        ранний выход без DB-запроса (экономия)."""
        html = "<p>Просто текст, без картинок</p>"
        session_ctx = _mock_db_session([])

        with patch(
            "app.worker.tasks.email_outbox.AsyncSessionLocal",
            return_value=session_ctx,
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 1)

        assert new_html == html
        assert images == []
        # db.execute не вызывался (ранний выход до DB-прохода).
        inner_session = session_ctx.__aenter__.return_value
        inner_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_attachment_not_in_db_keeps_url(self, tmp_path) -> None:
        """UUID в HTML есть, но в БД такого attachment уже нет (удалён через
        CASCADE при архивации) — src остаётся URL, письмо не роняется."""
        att_id = uuid.uuid4()
        url = _att_url(att_id)
        html = _img_html(url)

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([]),  # БД вернула пусто
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 42)

        assert url in new_html
        assert images == []

    @pytest.mark.asyncio
    async def test_unsupported_image_format_skipped(self, tmp_path) -> None:
        """``image/svg+xml`` (или другое не из allow-list) — пропускаем (XSS через
        ``<script>`` в SVG; allow-list: jpeg/png/gif/webp)."""
        svg_att = uuid.uuid4()
        url = _att_url(svg_att)
        html = _img_html(url)

        with (
            patch("app.core.constants.HELPDESK_FILES_DIR", tmp_path),
            patch(
                "app.worker.tasks.email_outbox.AsyncSessionLocal",
                return_value=_mock_db_session([(svg_att, "logo.svg", "image/svg+xml")]),
            ),
        ):
            new_html, images = await _embed_helpdesk_attachment_images(html, 1)

        assert url in new_html
        assert images == []
