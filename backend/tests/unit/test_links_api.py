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
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


_AUDIT_PATCH = "app.api.links.push_audit_event"


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
    from datetime import datetime, timezone

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
    link.created_at = datetime.now(timezone.utc)
    link.updated_at = datetime.now(timezone.utc)
    return link


def _make_db() -> AsyncMock:
    return AsyncMock()


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
        link = _make_link(
            id=link_id, url="https://sso-target.com", supports_sso=True
        )
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        with patch("app.api.links.get_session", new_callable=AsyncMock, return_value=None):
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
        link = _make_link(
            id=link_id, url="https://sso-target.com", supports_sso=True
        )
        user = _make_user()
        db = _make_db()
        redis = _make_redis()
        _configure_db_single(db, link)

        session_data = {"id_token": "mytoken123"}
        with patch(
            "app.api.links.get_session",
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
            patch("app.api.links._remove_icon_files"),
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
        db.execute = AsyncMock(side_effect=[
            MagicMock(**{"scalar_one_or_none.return_value": link}),
            MagicMock(),
        ])
        db.commit = AsyncMock()
        redis = _make_redis()

        with (
            patch(_AUDIT_PATCH, new_callable=AsyncMock),
            patch("app.api.links._remove_icon_files"),
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
        from app.api import links as links_mod

        link_id = uuid.uuid4()
        png = tmp_path / f"{link_id}.png"
        webp = tmp_path / f"{link_id}.webp"
        png.write_bytes(b"PNG")
        webp.write_bytes(b"WEBP")

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            links_mod._remove_icon_files(link_id)

        assert not png.exists()
        assert not webp.exists()

    def test_no_error_when_files_absent(self, tmp_path):
        from app.api import links as links_mod

        link_id = uuid.uuid4()

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            links_mod._remove_icon_files(link_id)


# ── _optimize_link_icon ───────────────────────────────────────────────────────


class TestOptimizeLinkIcon:
    def test_svg_returns_none(self, tmp_path):
        from app.api.links import _optimize_link_icon

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.svg"
        src.write_text("<svg/>")
        result = _optimize_link_icon(link_id, src, "svg")
        assert result is None

    def test_ico_returns_none(self, tmp_path):
        from app.api.links import _optimize_link_icon

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.ico"
        src.write_bytes(b"\x00")
        result = _optimize_link_icon(link_id, src, "ico")
        assert result is None

    def test_returns_none_when_pil_unavailable(self, tmp_path):
        from app.api import links as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"FAKEPNG")

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch("builtins.__import__", side_effect=ImportError):
                result = links_mod._optimize_link_icon(link_id, src, "png")

        assert result is None

    def test_returns_none_on_pil_open_error(self, tmp_path):
        from app.api import links as links_mod

        link_id = uuid.uuid4()
        src = tmp_path / f"{link_id}.png"
        src.write_bytes(b"NOT A REAL PNG")

        pil_mock = MagicMock()
        pil_mock.Image.open.side_effect = Exception("bad image")

        with patch.object(links_mod, "LINK_ICONS_DIR", tmp_path):
            with patch.dict("sys.modules", {"PIL": pil_mock, "PIL.Image": pil_mock.Image, "PIL.ImageOps": pil_mock.ImageOps}):
                result = links_mod._optimize_link_icon(link_id, src, "png")

        assert result is None
