"""Unit-тесты для роутера draft-attachments (commit-инвариант + wiring).

Regression-фокус: ``POST /draft-attachments`` обязан вызывать ``db.commit()``,
иначе flush'нутая строка теряется при закрытии сессии (``get_db`` ->
``autocommit=False``, после yield только ``close()``). Баг всплыл на проде
(2026-07-22): POST возвращал валидный ``id``, но последующий GET → 404 — строка
не сохранялась. Integration-тесты это маскировали, т.к. ``real_db_session``
фикстура коммитит внутри setup'а ``real_user``.

Здесь мокаем ``db`` и проверяем, что ``upload_draft_attachment`` вызывает
``commit`` после ``create_draft_attachment``. Также — wiring роутера (путь,
префикс, response-модель).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.api.helpdesk.drafts import router


def _fake_user() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


def _png_upload(name: str = "screen.png") -> UploadFile:
    import io

    return UploadFile(
        filename=name,
        file=io.BytesIO(b"bytes"),
        headers={"content-type": "image/png"},  # type: ignore[dict-item]
    )


@pytest.mark.asyncio
class TestUploadDraftAttachmentCommit:
    """``get_db()`` (``autocommit=False``) не коммитит автоматически — endpoint,
    пишущий в БД, обязан звать ``db.commit()`` сам. Без этого flush'нутая
    ``HelpdeskDraftAttachment`` теряется на ``session.close()`` (баг 2026-07-22)."""

    async def test_commits_after_create(self) -> None:
        from app.api.helpdesk.drafts import upload_draft_attachment

        db = AsyncMock()
        db.commit = AsyncMock()
        fake_draft = MagicMock()
        fake_draft.id = uuid.uuid4()
        fake_draft.filename = "abc_screen.png"

        with patch(
            "app.api.helpdesk.drafts.create_draft_attachment",
            new=AsyncMock(return_value=fake_draft),
        ) as create:
            resp = await upload_draft_attachment(
                file=_png_upload(), db=db, user=_fake_user(), redis=AsyncMock()
            )
        assert resp.url.endswith(str(fake_draft.id))
        create.assert_awaited_once()
        # Ключевой инвариант: строка зафиксирована, иначе GET после POST → 404.
        db.commit.assert_awaited_once()

    async def test_rejects_bad_extension_before_db_work(self) -> None:
        """Неподдерживаемое расширение → 400 ДО обращения к БД (ни create, ни commit)."""
        from fastapi import HTTPException

        from app.api.helpdesk.drafts import upload_draft_attachment

        db = AsyncMock()
        with (
            patch("app.api.helpdesk.drafts.create_draft_attachment", new=AsyncMock()) as create,
            pytest.raises(HTTPException) as exc,
        ):
            await upload_draft_attachment(
                file=_png_upload("evil.svg"), db=db, user=_fake_user(), redis=AsyncMock()
            )
        assert exc.value.status_code == 400
        create.assert_not_awaited()
        db.commit.assert_not_awaited()


class TestRouterWiring:
    """Роутер зарегистрирован под правильным префиксом с двумя эндпоинтами."""

    def test_routes_registered(self) -> None:
        paths = sorted(r.path for r in router.routes if hasattr(r, "path"))
        assert paths == [
            "/helpdesk/draft-attachments",
            "/helpdesk/draft-attachments/{draft_id}",
        ]

    def test_upload_returns_201(self) -> None:
        """``status_code=201`` (как inline-media ответов) — важно для корректности
        OpenAPI/фронтенда (``apiUpload`` трактует не-2xx как ошибку)."""
        from app.api.helpdesk.drafts import upload_draft_attachment

        # ``@router.post(..., status_code=201)`` кладёт ``status_code`` на
        # underlying APIRoute, не на декорированную функцию — ищем через роутер.
        route = next(r for r in router.routes if getattr(r, "endpoint", None) is upload_draft_attachment)
        assert route.status_code == 201  # type: ignore[attr-defined]
