"""
Test coverage for app/api/kb/export_import.py

Coverage:
- GET /kb/articles/{id}/export/md: success / 404 / no perm
- GET /kb/sections/{id}/export/zip: success / 404 section / no perm
- GET /kb/export/vault.zip: success (empty root sections)
- POST /kb/articles/import:
  - strategy=skip: existing title → skip
  - strategy=overwrite: existing title → overwrite
  - strategy=create_new: existing title → duplicate title
  - new article created
  - too large (file.size header)
  - body too large (content)
  - bad encoding → 422
- POST /kb/import/vault:
  - bad zip → 422
  - empty zip → 0 created/skipped
  - strategy=skip: existing file → skipped
  - strategy=create_new: creates article with suffix
- GET /kb/articles/{id}/export/pdf: success / 404 / no perm / draft+viewer
- GET /kb/articles/{id}/export/docx: success / 404
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed locally")
pytest.importorskip("httpx", reason="httpx not installed locally")


def _make_user(role: str = "editor") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        email=f"{role}@test.local",
        full_name="Test User",
        avatar_url=None,
    )


def _make_article(
    *,
    id: uuid.UUID | None = None,
    title: str = "Article",
    body: str = "# Hello",
    status: str = "published",
    section_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    deleted_at=None,
) -> MagicMock:
    a = MagicMock()
    a.id = id or uuid.uuid4()
    a.title = title
    a.body = body
    a.status = status
    a.section_id = section_id
    a.created_by = created_by
    a.deleted_at = deleted_at
    a.created_at = datetime.now(UTC)
    a.updated_at = datetime.now(UTC)
    a.published_at = datetime.now(UTC) if status == "published" else None
    a.view_count = 0
    a.tags = []
    return a


def _make_section(
    *,
    id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
    title: str = "Section",
    slug: str = "section",
) -> MagicMock:
    s = MagicMock()
    s.id = id or uuid.uuid4()
    s.parent_id = parent_id
    s.title = title
    s.slug = slug
    s.deleted_at = None
    s.sort_order = 0
    s.created_at = datetime.now(UTC)
    return s


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.refresh = MagicMock()
    db.expunge = MagicMock()
    db.add_all = MagicMock()
    db.execute.return_value = MagicMock()
    nested_mock = MagicMock()
    nested_mock.__aenter__ = AsyncMock(return_value=MagicMock())
    nested_mock.__aexit__ = AsyncMock(return_value=None)
    db.begin_nested = MagicMock(return_value=nested_mock)
    return db


def _make_redis() -> AsyncMock:
    return AsyncMock()


def _build_app(user: SimpleNamespace, db: AsyncMock, redis: AsyncMock):
    from fastapi import FastAPI

    from app.api.deps import get_current_user, get_db, get_redis
    from app.api.kb.export_import import router

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


async def _post_file(app, url: str, content: bytes, filename: str = "article.md"):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(
            url,
            files={"file": (filename, io.BytesIO(content), "text/markdown")},
        )


async def _post_zip(app, url: str, zip_bytes: bytes, filename: str = "vault.zip"):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        return await ac.post(
            url,
            files={"file": (filename, io.BytesIO(zip_bytes), "application/zip")},
        )


def _make_zip(*md_files: tuple[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in md_files:
            zf.writestr(name, content)
    return buf.getvalue()


# ── GET /kb/articles/{id}/export/md ──────────────────────────────────────────


class TestExportArticleMd:
    @pytest.mark.asyncio
    async def test_export_md_success(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, title="My Article", body="# Hello")
        db = _make_db()
        redis = _make_redis()

        author_result = MagicMock()
        author_result.scalar_one_or_none.return_value = "Test User"

        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=article)),
            author_result,
        ]

        with (
            patch(
                "app.api.kb.export_import.require_article_permission",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.kb.export_import._get_section_path",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.kb.export_import._build_frontmatter",
                return_value="---\ntitle: My Article\n---\n",
            ),
            patch(
                "app.api.kb.export_import.push_audit_event",
                new_callable=AsyncMock,
            ) as mock_push,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/export/md")

        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "My Article" in resp.text
        mock_push.assert_called_once_with(
            redis,
            event_type="kb.article_exported_md",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="kb_article",
            resource_id=str(article_id),
        )

    @pytest.mark.asyncio
    async def test_export_md_404(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/kb/articles/{article_id}/export/md")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_md_403_no_perm(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        from fastapi import HTTPException

        with patch(
            "app.api.kb.export_import.require_article_permission",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=403, detail="Forbidden"),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/export/md")

        assert resp.status_code == 403


# ── GET /kb/sections/{id}/export/zip ─────────────────────────────────────────


class TestExportSectionZip:
    @pytest.mark.asyncio
    async def test_export_zip_404_section(self):
        user = _make_user()
        section_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/kb/sections/{section_id}/export/zip")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_zip_success(self):
        user = _make_user()
        section_id = uuid.uuid4()
        section = _make_section(id=section_id, title="Docs")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=section)
        )

        with (
            patch(
                "app.api.kb.export_import.require_section_permission",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.kb.export_import._zip_section",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/sections/{section_id}/export/zip")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"


# ── GET /kb/export/vault.zip ──────────────────────────────────────────────────


class TestExportVault:
    @pytest.mark.asyncio
    async def test_export_vault_empty(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        sections_result = MagicMock()
        sections_result.scalars.return_value.all.return_value = []
        db.execute.return_value = sections_result

        app = _build_app(user, db, redis)
        resp = await _get(app, "/kb/export/vault.zip")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    @pytest.mark.asyncio
    async def test_export_vault_with_accessible_section(self):
        user = _make_user(role="admin")
        db = _make_db()
        redis = _make_redis()

        section = _make_section(title="Main")
        sections_result = MagicMock()
        sections_result.scalars.return_value.all.return_value = [section]
        db.execute.return_value = sections_result

        with (
            patch(
                "app.api.kb.export_import.batch_resolve_section_permissions",
                new_callable=AsyncMock,
                return_value={section.id: "viewer"},
            ),
            patch(
                "app.api.kb.export_import._zip_section",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, "/kb/export/vault.zip")

        assert resp.status_code == 200


# ── POST /kb/articles/import ──────────────────────────────────────────────────


class TestImportArticleMd:
    @pytest.mark.asyncio
    async def test_import_skip_existing(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        existing = _make_article(title="Existing Article")
        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=existing)
        )

        content = b"---\ntitle: Existing Article\n---\n# Body"

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({"title": "Existing Article"}, "# Body"),
            ),
            patch(
                "app.api.kb.export_import.load_system_settings",
                return_value=MagicMock(kb_import_max_size_mb=10),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(
                app, "/kb/articles/import?strategy=skip", content
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["skipped"] == 1
        assert data["created"] == 0

    @pytest.mark.asyncio
    async def test_import_overwrite_existing(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        existing = _make_article(title="Existing Article")
        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=existing)
        )
        db.commit = AsyncMock(return_value=None)

        content = b"---\ntitle: Existing Article\n---\n# Updated"

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({"title": "Existing Article"}, "# Updated"),
            ),
            patch(
                "app.api.kb.export_import.require_article_permission",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.kb.export_import.sanitize_markdown",
                return_value="# Updated",
            ),
            patch(
                "app.api.kb.export_import.load_system_settings",
                return_value=MagicMock(kb_import_max_size_mb=10),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(
                app, "/kb/articles/import?strategy=overwrite", content
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["updated"] == 1

    @pytest.mark.asyncio
    async def test_import_create_new_when_exists(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        existing = _make_article(title="Old Article")

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing
        tag_result = MagicMock()
        tag_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [existing_result, tag_result]
        db.flush = AsyncMock(return_value=None)
        db.commit = AsyncMock(return_value=None)

        content = b"---\ntitle: Old Article\ntags: [news]\n---\n# Body"

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({"title": "Old Article", "tags": ["news"]}, "# Body"),
            ),
            patch(
                "app.api.kb.export_import.sanitize_markdown",
                return_value="# Body",
            ),
            patch(
                "app.api.kb.export_import.load_system_settings",
                return_value=MagicMock(kb_import_max_size_mb=10),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(
                app, "/kb/articles/import?strategy=create_new", content
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1

    @pytest.mark.asyncio
    async def test_import_new_article(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        db.flush = AsyncMock(return_value=None)
        db.commit = AsyncMock(return_value=None)

        content = b"# New Article\n\nContent here"

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({}, "# New Article\n\nContent here"),
            ),
            patch(
                "app.api.kb.export_import.sanitize_markdown",
                return_value="# New Article\n\nContent here",
            ),
            patch(
                "app.api.kb.export_import.load_system_settings",
                return_value=MagicMock(kb_import_max_size_mb=10),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(
                app, "/kb/articles/import", content, filename="new-article.md"
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1

    @pytest.mark.asyncio
    async def test_import_new_article_into_section_without_perm_403(self):
        from fastapi import HTTPException

        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        section = _make_section()
        existing_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        section_result = MagicMock(scalar_one_or_none=MagicMock(return_value=section))
        db.execute.side_effect = [existing_result, section_result]
        db.flush = AsyncMock(return_value=None)
        db.commit = AsyncMock(return_value=None)

        content = b"---\ntitle: New Doc\nsection: /restricted\n---\n# Body"

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({"title": "New Doc", "section": "/restricted"}, "# Body"),
            ),
            patch(
                "app.api.kb.export_import._get_or_create_section_by_path",
                new_callable=AsyncMock,
                return_value=section.id,
            ),
            patch(
                "app.api.kb.export_import.require_section_permission",
                new_callable=AsyncMock,
                side_effect=HTTPException(
                    status_code=403, detail="Insufficient KB permissions"
                ),
            ),
            patch(
                "app.api.kb.export_import.sanitize_markdown", return_value="# Body"
            ),
            patch(
                "app.api.kb.export_import.load_system_settings",
                return_value=MagicMock(kb_import_max_size_mb=10),
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(app, "/kb/articles/import", content)

        assert resp.status_code == 403
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_too_large_returns_413(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        with patch(
            "app.api.kb.export_import.load_system_settings",
            return_value=MagicMock(kb_import_max_size_mb=0),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(app, "/kb/articles/import", b"x", filename="big.md")

        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_import_bad_encoding_returns_422(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        with patch(
            "app.api.kb.export_import.load_system_settings",
            return_value=MagicMock(kb_import_max_size_mb=10),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_file(
                app,
                "/kb/articles/import",
                b"\xff\xfe bad bytes \x00\x01",
                filename="bad.md",
            )

        assert resp.status_code == 422


# ── POST /kb/import/vault ─────────────────────────────────────────────────────


class TestImportVaultZip:
    @pytest.mark.asyncio
    async def test_bad_zip_returns_422(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        with patch(
            "app.api.kb.export_import._kb_import_max_bytes", return_value=10 * 1024 * 1024
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault", b"not a zip file")

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_zip_returns_zero_counts(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        zip_bytes = _make_zip()
        db.commit = AsyncMock(return_value=None)

        with patch(
            "app.api.kb.export_import._kb_import_max_bytes", return_value=10 * 1024 * 1024
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault", zip_bytes)

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 0
        assert data["skipped"] == 0
        assert data["errors"] == []

    @pytest.mark.asyncio
    async def test_skip_existing_article(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        existing = _make_article(title="Vault Article")
        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=existing)
        )
        db.commit = AsyncMock(return_value=None)

        md_content = "---\ntitle: Vault Article\n---\n# Body"
        zip_bytes = _make_zip(("section/vault-article.md", md_content))

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({"title": "Vault Article"}, "# Body"),
            ),
            patch(
                "app.api.kb.export_import._get_or_create_section_by_path",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.kb.export_import._kb_import_max_bytes",
                return_value=10 * 1024 * 1024,
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault?strategy=skip", zip_bytes)

        assert resp.status_code == 201
        data = resp.json()
        assert data["skipped"] == 1

    @pytest.mark.asyncio
    async def test_create_new_articles_from_vault(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )
        db.flush = AsyncMock(return_value=None)
        db.commit = AsyncMock(return_value=None)

        md_content = "---\ntitle: New Doc\n---\n# Content"
        zip_bytes = _make_zip(("docs/new-doc.md", md_content))

        with (
            patch(
                "app.api.kb.export_import._parse_frontmatter",
                return_value=({"title": "New Doc"}, "# Content"),
            ),
            patch(
                "app.api.kb.export_import._get_or_create_section_by_path",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.kb.export_import.sanitize_markdown", return_value="# Content"
            ),
            patch(
                "app.api.kb.export_import._kb_import_max_bytes",
                return_value=10 * 1024 * 1024,
            ),
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault?strategy=create_new", zip_bytes)

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1

    @pytest.mark.asyncio
    async def test_zip_bomb_uncompressed_limit(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big.md", "A" * 30000)
        zip_bytes = buf.getvalue()

        with patch(
            "app.api.kb.export_import._kb_import_max_bytes", return_value=5000
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault", zip_bytes)

        assert resp.status_code == 400
        assert "Uncompressed archive size is too large" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_zip_too_many_files_limit(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, "w") as zf:
            for i in range(1001):
                zf.writestr(f"f{i}.md", "")
        zip_bytes = zip_io.getvalue()

        with patch(
            "app.api.kb.export_import._kb_import_max_bytes", return_value=10 * 1024 * 1024
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault", zip_bytes)

        assert resp.status_code == 400
        assert "Archive contains too many files" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_zip_bad_filename_rejections(self):
        user = _make_user()
        db = _make_db()
        redis = _make_redis()

        zip_bytes = _make_zip(
            ("../traversal.md", "traversal"),
            ("/absolute.md", "absolute"),
            ("back\\slash.md", "backslash"),
            ("colon:byte.md", "colon"),
        )
        db.commit = AsyncMock(return_value=None)

        with patch(
            "app.api.kb.export_import._kb_import_max_bytes", return_value=10 * 1024 * 1024
        ):
            app = _build_app(user, db, redis)
            resp = await _post_zip(app, "/kb/import/vault", zip_bytes)

        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 0
        assert len(data["errors"]) == 4
        assert any("traversal" in err for err in data["errors"])
        assert any("absolute" in err for err in data["errors"])
        assert any("backslash" in err for err in data["errors"])
        assert any("character" in err or "Filename" in err or "char" in err for err in data["errors"])


# ── GET /kb/articles/{id}/export/pdf ─────────────────────────────────────────


class TestExportArticlePdf:
    @pytest.mark.asyncio
    async def test_export_pdf_404(self):
        user = _make_user()
        article_id = uuid.uuid4()
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        app = _build_app(user, db, redis)
        resp = await _get(app, f"/kb/articles/{article_id}/export/pdf")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_pdf_403_no_perm(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id)
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with patch(
            "app.api.kb.export_import.resolve_article_permission",
            new_callable=AsyncMock,
            return_value=None,
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/export/pdf")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_export_pdf_403_draft_as_viewer(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, status="draft")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with patch(
            "app.api.kb.export_import.resolve_article_permission",
            new_callable=AsyncMock,
            return_value="viewer",
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/export/pdf")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_export_pdf_success(self):
        user = _make_user()
        article_id = uuid.uuid4()
        article = _make_article(id=article_id, title="Report", body="# Hello")
        db = _make_db()
        redis = _make_redis()

        db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=article))

        with (
            patch(
                "app.api.kb.export_import.resolve_article_permission",
                new_callable=AsyncMock,
                return_value="editor",
            ),
            patch(
                "app.core.pdf.render_pdf",
                new_callable=AsyncMock,
                return_value=b"%PDF-1.4 fake",
            ),
            patch("app.api.kb.export_import.push_audit_event", new_callable=AsyncMock),
        ):
            app = _build_app(user, db, redis)
            resp = await _get(app, f"/kb/articles/{article_id}/export/pdf")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
