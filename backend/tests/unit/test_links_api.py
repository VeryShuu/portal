"""Unit-тесты для app/api/links.py.

Покрытие:
- list_links: базовый список, с category, include_inactive, orphaned (только admin),
  фильтрация hidden_link_ids
- get_link: found / 404
- create_link: 201 created
- update_link: found / 404
- delete_link: found / 404
- sso_redirect: non-sso / sso без cookie / sso с cookie / 404
- get_sso_url: non-sso / sso / 404
- reorder_links: пустой список / 404 при несовпадении ids / happy-path
- delete_link_icon: found / 404
- _remove_icon_files: создаёт каталог, удаляет существующие файлы
- _optimize_link_icon: svg/ico пропускается, PIL недоступен, PIL оптимизирует
- list_links: include_inactive, category filter, orphaned+admin, malformed hidden_link_ids
- get_sso_url: SSO with token returns sso=True
- sso_redirect: URL with existing query string uses &
- upload_link_icon: success / 404 / optimized ext
- _optimize_link_icon: PIL success path, original removed when ext≠webp, webp input kept
- audit events: exact event_type for created/updated/deleted/reordered
"""

from __future__ import annotations

import uuid
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


_AUDIT_PATCH = "app.services.audit.push_audit_event"


def _make_user(role: str = "reader") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        preferences={},
    )


def _make_link(
    *,
    id: uuid.UUID | None = None,
    title: str = "Test",
    url: str = "https://example.com",
    icon_url: str | None = None,
    description: str | None = None,
    category: str | None = None,
    sort_order: int = 0,
    supports_sso: bool = False,
    is_active: bool = True,
    created_by: uuid.UUID | None = None,
):
    from datetime import datetime

    link = MagicMock()
    link.id = id or uuid.uuid4()
    link.title = title
    link.url = url
    link.icon_url = icon_url
    link.description = description
    link.category = category
    link.sort_order = sort_order
    link.supports_sso = supports_sso
    link.is_active = is_active
    link.created_by = created_by
    link.created_at = datetime.now(UTC)
    link.updated_at = datetime.now(UTC)
    return link


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.expunge = MagicMock()
    db.execute.return_value = MagicMock()
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.links import router

    _app = FastAPI()
    _app.include_router(router)

    async def _fake_user():
        return user

    async def _fake_db():
        return db

    async def _fake_redis():
        return redis

    _app.dependency_overrides[get_current_user] = _fake_user
    _app.dependency_overrides[get_db] = _fake_db
    _app.dependency_overrides[get_redis] = _fake_redis
    return _app


async def _get(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.get(url)


async def _post(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, json=json)


async def _put(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.put(url, json=json)


async def _delete(app, url: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.delete(url)


async def _patch(app, url: str, json: dict | None = None):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.patch(url, json=json)


def _configure_db_list(db: AsyncMock, links: list, total: int):
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = links
    list_result = MagicMock()
    list_result.scalars.return_value = scalars_mock

    count_result = MagicMock()
    count_result.scalar_one.return_value = total

    db.execute = AsyncMock(side_effect=[list_result, count_result])


def _configure_db_single(db: AsyncMock, link):
    result = MagicMock()
    result.scalar_one_or_none.return_value = link
    db.execute = AsyncMock(return_value=result)


# ── list_links ────────────────────────────────────────────────────────────────


class TestListLinks:
    async def test_returns_empty_list(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [], 0)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    async def test_returns_active_links(self):
        link = _make_link(title="JIRA")
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [link], 1)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["title"] == "JIRA"

    async def test_hidden_links_filtered(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, title="Hidden")
        user = _make_user()
        user.preferences = {"hidden_link_ids": [str(link_id)]}
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [link], 1)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links")

        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_orphaned_only_for_admin(self):
        user = _make_user(role="reader")
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [], 0)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links?orphaned=true")

        assert resp.status_code == 200


# ── get_link ──────────────────────────────────────────────────────────────────


class TestGetLink:
    async def test_returns_found_link(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, title="Confluence")
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/links/{link_id}")

        assert resp.status_code == 200
        assert resp.json()["title"] == "Confluence"

    async def test_returns_404_when_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, None)

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/links/{link_id}")

        assert resp.status_code == 404


# ── sso_redirect ──────────────────────────────────────────────────────────────


class TestSsoRedirect:
    async def test_non_sso_link_redirects_directly(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://target.com", supports_sso=False)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        app = _build_app(user, db, redis)
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as ac:
            resp = await ac.get(f"/links/{link_id}/sso-redirect")

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://target.com"

    async def test_sso_link_without_cookie(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://sso-target.com", supports_sso=True)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        with patch("app.services.links_sso.get_session", new_callable=AsyncMock, return_value=None):
            app = _build_app(user, db, redis)
            import httpx

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as ac:
                resp = await ac.get(f"/links/{link_id}/sso-redirect")

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://sso-target.com"

    async def test_sso_link_with_cookie_and_token(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://sso-target.com", supports_sso=True)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        session_data = {"id_token": "mytoken123"}
        with patch(
            "app.services.links_sso.get_session",
            new_callable=AsyncMock,
            return_value=session_data,
        ):
            app = _build_app(user, db, redis)
            import httpx

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
                cookies={"portal_session": "sess-id"},
            ) as ac:
                resp = await ac.get(f"/links/{link_id}/sso-redirect")

        assert resp.status_code == 302
        assert "id_token_hint=mytoken123" in resp.headers["location"]

    async def test_404_when_link_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, None)

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/links/{link_id}/sso-redirect")

        assert resp.status_code == 404


# ── get_sso_url ───────────────────────────────────────────────────────────────


class TestGetSsoUrl:
    async def test_non_sso_returns_plain_url(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://plain.com", supports_sso=False)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/links/{link_id}/sso-url")

        assert resp.status_code == 200
        assert resp.json()["url"] == "https://plain.com"

    async def test_sso_link_non_sso_returns_url(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://sso.com", supports_sso=False)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/links/{link_id}/sso-url")

        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://sso.com"

    async def test_404_when_link_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, None)

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/links/{link_id}/sso-url")

        assert resp.status_code == 404


# ── create_link ───────────────────────────────────────────────────────────────


class TestCreateLink:
    async def test_creates_and_returns_201(self):
        link_id = uuid.uuid4()
        created_link = _make_link(id=link_id, title="Grafana", url="https://grafana.com")

        user = _make_user(role="admin")
        db = _make_db()
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        async def _fake_refresh(obj):
            obj.id = created_link.id
            obj.title = created_link.title
            obj.url = created_link.url
            obj.icon_url = created_link.icon_url
            obj.description = created_link.description
            obj.category = created_link.category
            obj.sort_order = created_link.sort_order
            obj.supports_sso = created_link.supports_sso
            obj.is_active = created_link.is_active
            obj.created_at = created_link.created_at
            obj.updated_at = created_link.updated_at

        db.refresh = AsyncMock(side_effect=_fake_refresh)
        redis = _make_redis()

        with patch(_AUDIT_PATCH, new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _post(
                app,
                "/links",
                json={
                    "title": "Grafana",
                    "url": "https://grafana.com",
                    "sort_order": 1,
                    "supports_sso": False,
                    "is_active": True,
                },
            )

        assert resp.status_code == 201
        db.add.assert_called_once()
        db.commit.assert_awaited()

    async def test_validates_url_scheme(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _post(
            app,
            "/links",
            json={"title": "Bad", "url": "ftp://bad.com"},
        )

        assert resp.status_code == 422


# ── update_link ───────────────────────────────────────────────────────────────


class TestUpdateLink:
    async def test_updates_and_returns_link(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, title="Old")
        user = _make_user(role="admin")
        db = _make_db()

        _configure_db_single(db, link)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        redis = _make_redis()

        with patch(_AUDIT_PATCH, new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _put(
                app,
                f"/links/{link_id}",
                json={"title": "New", "url": "https://example.com"},
            )

        assert resp.status_code == 200

    async def test_404_when_link_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, None)
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _put(
            app,
            f"/links/{link_id}",
            json={"title": "X", "url": "https://x.com"},
        )

        assert resp.status_code == 404


# ── delete_link ───────────────────────────────────────────────────────────────


class TestDeleteLink:
    async def test_deletes_link(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id)
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, link)
        db.commit = AsyncMock()
        redis = _make_redis()

        with (
            patch(_AUDIT_PATCH, new_callable=AsyncMock),
            patch("app.services.link_icon.remove_icon_files"),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/links/{link_id}")

        assert resp.status_code == 204
        db.delete.assert_awaited_once_with(link)

    async def test_404_when_link_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, None)
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/links/{link_id}")

        assert resp.status_code == 404


# ── delete_link_icon ──────────────────────────────────────────────────────────


class TestDeleteLinkIcon:
    async def test_clears_icon_url(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, icon_url="/media/link_icons/test.png")
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, link)
        db.execute = AsyncMock(
            side_effect=[
                MagicMock(**{"scalar_one_or_none.return_value": link}),
                MagicMock(),
            ]
        )
        db.commit = AsyncMock()
        redis = _make_redis()

        with (
            patch(_AUDIT_PATCH, new_callable=AsyncMock),
            patch("app.services.link_icon.remove_icon_files"),
        ):
            app = _build_app(user, db, redis)
            resp = await _delete(app, f"/links/{link_id}/icon")

        assert resp.status_code == 204

    async def test_404_when_link_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, None)
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _delete(app, f"/links/{link_id}/icon")

        assert resp.status_code == 404


# ── reorder_links ─────────────────────────────────────────────────────────────


class TestReorderLinks:
    async def test_empty_list_returns_204(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        with patch(_AUDIT_PATCH, new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _patch(app, "/links/reorder", json={"items": []})

        assert resp.status_code == 204

    async def test_404_when_ids_mismatch(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        id1 = uuid.uuid4()
        id2 = uuid.uuid4()

        existing_result = MagicMock()
        existing_result.all.return_value = [(id1,)]
        db.execute = AsyncMock(return_value=existing_result)

        app = _build_app(user, db, redis)
        resp = await _patch(
            app,
            "/links/reorder",
            json={"items": [{"id": str(id1), "sort_order": 0}, {"id": str(id2), "sort_order": 1}]},
        )

        assert resp.status_code == 404

    async def test_happy_path_returns_204(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        id1 = uuid.uuid4()
        id2 = uuid.uuid4()

        existing_result = MagicMock()
        existing_result.all.return_value = [(id1,), (id2,)]
        db.execute = AsyncMock(return_value=existing_result)
        db.commit = AsyncMock()

        with patch(_AUDIT_PATCH, new_callable=AsyncMock):
            app = _build_app(user, db, redis)
            resp = await _patch(
                app,
                "/links/reorder",
                json={
                    "items": [
                        {"id": str(id1), "sort_order": 0},
                        {"id": str(id2), "sort_order": 1},
                    ]
                },
            )

        assert resp.status_code == 204


# ── _remove_icon_files ────────────────────────────────────────────────────────


class TestRemoveIconFiles:
    def test_removes_all_extensions(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        png = tmp_path / f"{link_id}.png"
        webp = tmp_path / f"{link_id}.webp"
        png.write_bytes(b"PNG")
        webp.write_bytes(b"WEBP")

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            links_mod.remove_icon_files(link_id)

        assert not png.exists()
        assert not webp.exists()

    def test_no_error_when_files_absent(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            links_mod.remove_icon_files(link_id)


# ── _optimize_link_icon ───────────────────────────────────────────────────────


class TestOptimizeLinkIcon:
    def test_svg_returns_none(self, tmp_path):
        from app.services.link_icon import optimize_link_icon

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.svg"
        src.write_text("<svg/>")
        result = optimize_link_icon(link_id, src, "svg")
        assert result is None

    def test_ico_returns_none(self, tmp_path):
        from app.services.link_icon import optimize_link_icon

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.ico"
        src.write_bytes(b"\x00")
        result = optimize_link_icon(link_id, src, "ico")
        assert result is None

    def test_returns_none_when_pil_unavailable(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"FAKEPNG")

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch("builtins.__import__", side_effect=ImportError):
                result = links_mod.optimize_link_icon(link_id, src, "png")

        assert result is None

    def test_returns_none_on_pil_open_error(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"NOT A REAL PNG")

        pil_mock = MagicMock()
        pil_mock.Image.open.side_effect = Exception("bad image")

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch.dict(
                "sys.modules",
                {"PIL": pil_mock, "PIL.Image": pil_mock.Image, "PIL.ImageOps": pil_mock.ImageOps},
            ):
                result = links_mod.optimize_link_icon(link_id, src, "png")

        assert result is None

    def _make_pil_mock(self):
        pil_mock = MagicMock()
        img_mock = MagicMock()
        img_mock.mode = "RGB"
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=img_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)
        pil_mock.Image.open.return_value = ctx_mock
        pil_mock.ImageOps.exif_transpose.return_value = img_mock
        return pil_mock

    def test_pil_success_returns_webp(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"PNG_DATA")

        pil_mock = self._make_pil_mock()
        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch.dict(
                "sys.modules",
                {"PIL": pil_mock, "PIL.Image": pil_mock.Image, "PIL.ImageOps": pil_mock.ImageOps},
            ):
                result = links_mod.optimize_link_icon(link_id, src, "png")

        assert result == "webp"

    def test_pil_success_removes_original_non_webp(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"PNG_DATA")

        pil_mock = self._make_pil_mock()
        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch.dict(
                "sys.modules",
                {"PIL": pil_mock, "PIL.Image": pil_mock.Image, "PIL.ImageOps": pil_mock.ImageOps},
            ):
                links_mod.optimize_link_icon(link_id, src, "png")

        assert not src.exists()

    def test_pil_webp_input_no_delete(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.webp"
        src.write_bytes(b"WEBP_DATA")

        pil_mock = self._make_pil_mock()
        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch.dict(
                "sys.modules",
                {"PIL": pil_mock, "PIL.Image": pil_mock.Image, "PIL.ImageOps": pil_mock.ImageOps},
            ):
                result = links_mod.optimize_link_icon(link_id, src, "webp")

        assert result == "webp"
        assert src.exists()

    def test_pil_non_rgb_mode_converted(self, tmp_path):
        from app.services import link_icon as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"PNG_DATA")

        pil_mock = MagicMock()
        img_mock = MagicMock()
        img_mock.mode = "P"
        converted_mock = MagicMock()
        converted_mock.mode = "RGBA"
        img_mock.convert.return_value = converted_mock
        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=img_mock)
        ctx_mock.__exit__ = MagicMock(return_value=False)
        pil_mock.Image.open.return_value = ctx_mock
        pil_mock.ImageOps.exif_transpose.return_value = img_mock

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch.dict(
                "sys.modules",
                {"PIL": pil_mock, "PIL.Image": pil_mock.Image, "PIL.ImageOps": pil_mock.ImageOps},
            ):
                result = links_mod.optimize_link_icon(link_id, src, "png")

        assert result == "webp"
        img_mock.convert.assert_called_once_with("RGBA")


# ── list_links extended filters ───────────────────────────────────────────────


async def _post_file(
    app,
    url: str,
    *,
    content: bytes = b"FAKE",
    content_type: str = "image/png",
    filename: str = "icon.png",
):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(url, files={"file": (filename, content, content_type)})


class TestListLinksFilters:
    async def test_include_inactive_skips_active_filter(self):
        link = _make_link(title="Inactive", is_active=False)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [link], 1)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links?include_inactive=true")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_category_filter_returns_200(self):
        link = _make_link(title="JIRA", category="Dev Tools")
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [link], 1)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links?category=Dev+Tools")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_orphaned_filter_for_admin(self):
        link = _make_link(title="Orphan", created_by=None)
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [link], 1)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links?orphaned=true")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_malformed_hidden_link_id_does_not_crash(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, title="Visible")
        user = _make_user()
        user.preferences = {"hidden_link_ids": ["not-a-uuid", "also-bad"]}
        db = _make_db()
        redis = _make_redis()
        _configure_db_list(db, [link], 1)

        app = _build_app(user, db, redis)
        resp = await _get(app, "/links")

        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1


# ── get_sso_url: SSO token path ───────────────────────────────────────────────


class TestGetSsoUrlToken:
    async def test_sso_link_with_token_returns_sso_true(self):
        from app.api.links import get_sso_url

        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://sso.com", supports_sso=True)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        request_mock = MagicMock()
        request_mock.cookies.get.return_value = "sess-id"

        session_data = {"id_token": "testtoken"}
        with patch(
            "app.services.links_sso.get_session", new_callable=AsyncMock, return_value=session_data
        ):
            result = await get_sso_url(link_id, user, db, request_mock, redis)

        assert result.get("sso") is True
        assert "id_token_hint=testtoken" in result["url"]

    async def test_sso_redirect_url_with_existing_query_string_uses_ampersand(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, url="https://sso.com/login?redirect=1", supports_sso=True)
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        session_data = {"id_token": "tok123"}
        with patch(
            "app.services.links_sso.get_session",
            new_callable=AsyncMock,
            return_value=session_data,
        ):
            app = _build_app(user, db, redis)
            import httpx

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
                cookies={"portal_session": "sess-id"},
            ) as ac:
                resp = await ac.get(f"/links/{link_id}/sso-redirect")

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "redirect=1" in location
        assert "&id_token_hint=tok123" in location


# ── upload_link_icon ──────────────────────────────────────────────────────────


class TestUploadLinkIcon:
    def _configure_db_for_upload(self, db, link):
        select_result = MagicMock()
        select_result.scalar_one_or_none.return_value = link
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[select_result, update_result])
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

    async def test_success_returns_200(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id)
        user = _make_user(role="admin")
        db = _make_db()
        self._configure_db_for_upload(db, link)
        redis = _make_redis()

        with (
            patch(
                "app.services.link_icon.stream_upload_to_path",
                new_callable=AsyncMock,
                return_value=(512, "image/png"),
            ),
            patch("app.services.link_icon.remove_icon_files"),
            patch("app.services.link_icon.optimize_link_icon", return_value=None),
            patch(_AUDIT_PATCH, new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(app, f"/links/{link_id}/icon")

        assert resp.status_code == 200
        db.commit.assert_awaited()

    async def test_404_when_link_not_found(self):
        link_id = uuid.uuid4()
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, None)
        redis = _make_redis()

        app = _build_app(user, db, redis)
        resp = await _post_file(app, f"/links/{link_id}/icon")

        assert resp.status_code == 404

    async def test_optimized_ext_changes_icon_url(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id)
        user = _make_user(role="admin")
        db = _make_db()
        self._configure_db_for_upload(db, link)
        redis = _make_redis()

        with (
            patch(
                "app.services.link_icon.stream_upload_to_path",
                new_callable=AsyncMock,
                return_value=(512, "image/png"),
            ),
            patch("app.services.link_icon.remove_icon_files"),
            patch("app.services.link_icon.optimize_link_icon", return_value="webp"),
            patch(_AUDIT_PATCH, new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(app, f"/links/{link_id}/icon")

        assert resp.status_code == 200
        update_call_stmt = db.execute.call_args_list[1][0][0]
        compiled = update_call_stmt.compile(compile_kwargs={"literal_binds": True})
        assert f"/media/link_icons/{link_id}.webp" in str(compiled)

    async def test_icon_url_format_without_optimizer(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id)
        user = _make_user(role="admin")
        db = _make_db()
        self._configure_db_for_upload(db, link)
        redis = _make_redis()

        with (
            patch(
                "app.services.link_icon.stream_upload_to_path",
                new_callable=AsyncMock,
                return_value=(512, "image/png"),
            ),
            patch("app.services.link_icon.remove_icon_files"),
            patch("app.services.link_icon.optimize_link_icon", return_value=None),
            patch(_AUDIT_PATCH, new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(
                app,
                f"/links/{link_id}/icon",
                content_type="image/png",
                filename="icon.png",
            )

        assert resp.status_code == 200
        update_call_stmt = db.execute.call_args_list[1][0][0]
        compiled = update_call_stmt.compile(compile_kwargs={"literal_binds": True})
        assert f"/media/link_icons/{link_id}.png" in str(compiled)

    async def test_audit_event_emitted_on_upload(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id)
        user = _make_user(role="admin")
        db = _make_db()
        self._configure_db_for_upload(db, link)
        redis = _make_redis()

        audit_mock = AsyncMock()
        with (
            patch(
                "app.services.link_icon.stream_upload_to_path",
                new_callable=AsyncMock,
                return_value=(512, "image/png"),
            ),
            patch("app.services.link_icon.remove_icon_files"),
            patch("app.services.link_icon.optimize_link_icon", return_value=None),
            patch(_AUDIT_PATCH, audit_mock),
        ):
            app = _build_app(user, db, redis)
            await _post_file(app, f"/links/{link_id}/icon")

        audit_mock.assert_awaited_once()
        call_kwargs = audit_mock.call_args.kwargs
        assert call_kwargs["event_type"] == "links.updated"
        assert call_kwargs["resource_id"] == str(link_id)
        assert call_kwargs["metadata"] == {"fields": ["icon_url"]}


# ── audit events ──────────────────────────────────────────────────────────────


class TestAuditEvents:
    async def test_create_link_emits_correct_event(self):
        link_id = uuid.uuid4()
        created_link = _make_link(id=link_id, title="New")
        user = _make_user(role="admin")
        db = _make_db()

        async def _fake_refresh(obj):
            obj.id = created_link.id
            obj.title = created_link.title
            obj.url = created_link.url
            obj.icon_url = created_link.icon_url
            obj.description = created_link.description
            obj.category = created_link.category
            obj.sort_order = created_link.sort_order
            obj.supports_sso = created_link.supports_sso
            obj.is_active = created_link.is_active
            obj.created_at = created_link.created_at
            obj.updated_at = created_link.updated_at

        db.refresh = AsyncMock(side_effect=_fake_refresh)
        redis = _make_redis()

        audit_mock = AsyncMock()
        with patch(_AUDIT_PATCH, audit_mock):
            app = _build_app(user, db, redis)
            await _post(
                app,
                "/links",
                json={"title": "New", "url": "https://new.example.com"},
            )

        audit_mock.assert_awaited_once()
        assert audit_mock.call_args.kwargs["event_type"] == "links.created"
        assert audit_mock.call_args.kwargs["resource_type"] == "link"

    async def test_update_link_emits_correct_event_with_fields(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id, title="Old")
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, link)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        redis = _make_redis()

        audit_mock = AsyncMock()
        with patch(_AUDIT_PATCH, audit_mock):
            app = _build_app(user, db, redis)
            await _put(
                app,
                f"/links/{link_id}",
                json={"title": "Updated", "url": "https://updated.com"},
            )

        audit_mock.assert_awaited_once()
        call_kwargs = audit_mock.call_args.kwargs
        assert call_kwargs["event_type"] == "links.updated"
        assert call_kwargs["resource_id"] == str(link_id)
        assert "title" in call_kwargs["metadata"]["fields"]

    async def test_delete_link_emits_correct_event(self):
        link_id = uuid.uuid4()
        link = _make_link(id=link_id)
        user = _make_user(role="admin")
        db = _make_db()
        _configure_db_single(db, link)
        db.commit = AsyncMock()
        redis = _make_redis()

        audit_mock = AsyncMock()
        with (
            patch(_AUDIT_PATCH, audit_mock),
            patch("app.services.link_icon.remove_icon_files"),
        ):
            app = _build_app(user, db, redis)
            await _delete(app, f"/links/{link_id}")

        audit_mock.assert_awaited_once()
        call_kwargs = audit_mock.call_args.kwargs
        assert call_kwargs["event_type"] == "links.deleted"
        assert call_kwargs["resource_id"] == str(link_id)

    async def test_reorder_links_emits_correct_event(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        id1 = uuid.uuid4()
        id2 = uuid.uuid4()

        existing_result = MagicMock()
        existing_result.all.return_value = [(id1,), (id2,)]
        db.execute = AsyncMock(return_value=existing_result)
        db.commit = AsyncMock()

        audit_mock = AsyncMock()
        with patch(_AUDIT_PATCH, audit_mock):
            app = _build_app(user, db, redis)
            await _patch(
                app,
                "/links/reorder",
                json={
                    "items": [
                        {"id": str(id1), "sort_order": 1},
                        {"id": str(id2), "sort_order": 0},
                    ]
                },
            )

        audit_mock.assert_awaited_once()
        call_kwargs = audit_mock.call_args.kwargs
        assert call_kwargs["event_type"] == "links.reordered"
        assert call_kwargs["metadata"] == {"count": 2}
        assert call_kwargs["resource_id"] is None
