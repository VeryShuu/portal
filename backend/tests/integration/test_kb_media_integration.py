"""Integration tests — KB media upload, file download (X-Accel-Redirect), vault ZIP import.

Requires INTEGRATION_DB=true.
Uses httpx AsyncClient with dependency override for get_current_user.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_user_obj(role: str = "editor", **kwargs):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid.uuid4(),
        email=f"{role}-{uuid.uuid4().hex[:6]}@portal.local",
        full_name=f"Test {role.title()}",
        department="IT",
        role=role,
        auth_source="local",
        preferences={},
    )


async def _create_db_user(db, role: str = "editor"):
    from app.models.user import User

    u = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@portal.local",
        full_name=f"Integration {role.title()}",
        department="IT",
        role=role,
        auth_source="local",
        password_hash=None,
        presence_status="office",
        notify_email=False,
        notify_inapp=False,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _create_db_section(db, user_id: uuid.UUID, title: str = "Test Section"):
    import re

    from app.models.kb import KbSection

    slug = re.sub(r"[\s_-]+", "-", title.lower()) + f"-{uuid.uuid4().hex[:4]}"
    sec = KbSection(title=title, slug=slug, created_by=user_id)
    db.add(sec)
    await db.commit()
    await db.refresh(sec)
    return sec


async def _create_db_article(db, user_id: uuid.UUID, section_id: uuid.UUID | None = None):
    from app.models.kb import KbArticle

    art = KbArticle(
        title=f"Article {uuid.uuid4().hex[:6]}",
        body="# Hello\nTest content.",
        status="published",
        section_id=section_id,
        created_by=user_id,
        updated_by=user_id,
        inherit_permissions=True,
    )
    db.add(art)
    await db.commit()
    await db.refresh(art)
    return art


@pytest_asyncio.fixture
async def authed_app(real_db_session):
    """Returns (app, editor_user) with get_current_user overridden."""
    import importlib
    import os

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    import app.main as main_mod

    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    return application, editor, real_db_session


# ─────────────────────────────────────────────────────────────────────────────
# 1. Media upload → X-Accel-Redirect returned (mocked filesystem)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_upload_returns_url(real_db_session):
    """POST /kb/articles/{id}/media returns URL containing the article ID."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    section = await _create_db_section(real_db_session, editor.id)
    article = await _create_db_article(real_db_session, editor.id, section.id)

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.setex = AsyncMock()
    fake_redis.xadd = AsyncMock()

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db
    application.dependency_overrides[get_redis] = lambda: fake_redis

    image_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\xff\xd9"
    )

    csrf_token = "test-csrf-token"

    with patch("app.core.uploads.stream_upload_to_path", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = (len(image_bytes), "image/jpeg")
        with patch("app.api.kb.media.KB_MEDIA_DIR"):
            transport = ASGITransport(app=application)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
                cookies={"XSRF-TOKEN": csrf_token},
            ) as client:
                files = {"file": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")}
                resp = await client.post(f"/api/v1/kb/articles/{article.id}/media", files=files)

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "url" in data
    assert str(article.id) in data["url"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Media serve → X-Accel-Redirect header present
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_serve_returns_x_accel_redirect(real_db_session):
    """GET /kb/media/{id}/{filename} returns X-Accel-Redirect header."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    section = await _create_db_section(real_db_session, editor.id)
    article = await _create_db_article(real_db_session, editor.id, section.id)

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="viewer")
    fake_redis.setex = AsyncMock()
    application.dependency_overrides[get_redis] = lambda: fake_redis

    filename = f"{uuid.uuid4().hex[:8]}_image.jpg"

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        resp = await client.get(f"/api/v1/kb/media/{article.id}/{filename}")

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    assert "x-accel-redirect" in resp.headers
    assert f"/internal/kb-media/{article.id}/{filename}" in resp.headers["x-accel-redirect"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. File upload → returns KbFilePublic with original_name
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_upload_stores_original_name(real_db_session):
    """POST /kb/articles/{id}/files stores original filename in DB."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    section = await _create_db_section(real_db_session, editor.id)
    article = await _create_db_article(real_db_session, editor.id, section.id)

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="editor")
    fake_redis.setex = AsyncMock()
    fake_redis.xadd = AsyncMock()

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db
    application.dependency_overrides[get_redis] = lambda: fake_redis

    original_name = "Технический_регламент.pdf"
    pdf_bytes = b"%PDF-1.4 test pdf content"
    csrf_token = "test-csrf-token"

    with patch(
        "app.api.kb.attachments.stream_upload_to_path", new_callable=AsyncMock
    ) as mock_upload:
        mock_upload.return_value = (len(pdf_bytes), "application/pdf")
        with patch("app.api.kb.attachments.KB_FILES_DIR"):
            transport = ASGITransport(app=application)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
                cookies={"XSRF-TOKEN": csrf_token},
            ) as client:
                files = {"file": (original_name, io.BytesIO(pdf_bytes), "application/pdf")}
                resp = await client.post(f"/api/v1/kb/articles/{article.id}/files", files=files)

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["original_name"] == original_name


# ─────────────────────────────────────────────────────────────────────────────
# 4. File download → X-Accel-Redirect + Content-Disposition with original name
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_download_x_accel_redirect(real_db_session):
    """GET /kb/files/{id}/{filename} returns X-Accel-Redirect and RFC-5987 Content-Disposition."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db
    from app.models.kb import KbArticleFile

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    section = await _create_db_section(real_db_session, editor.id)
    article = await _create_db_article(real_db_session, editor.id, section.id)

    stored_name = f"{uuid.uuid4().hex}_doc.pdf"
    original_name = "Регламент 2025.pdf"
    kb_file = KbArticleFile(
        article_id=article.id,
        filename=stored_name,
        original_name=original_name,
        size_bytes=1024,
        mime_type="application/pdf",
        uploaded_by=editor.id,
    )
    real_db_session.add(kb_file)
    await real_db_session.commit()

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="viewer")
    fake_redis.setex = AsyncMock()
    fake_redis.xadd = AsyncMock()
    application.dependency_overrides[get_redis] = lambda: fake_redis

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        resp = await client.get(f"/api/v1/kb/files/{article.id}/{stored_name}")

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    assert "x-accel-redirect" in resp.headers
    assert stored_name in resp.headers["x-accel-redirect"]
    cd = resp.headers.get("content-disposition", "")
    assert "UTF-8''" in cd


# ─────────────────────────────────────────────────────────────────────────────
# 5. File access by unauthorized user → 403
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_access_without_permission_returns_403(real_db_session):
    """User without section/article permission gets 403 on file list."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    owner = await _create_db_user(real_db_session, role="editor")
    stranger = await _create_db_user(real_db_session, role="reader")
    section = await _create_db_section(real_db_session, owner.id)
    article = await _create_db_article(real_db_session, owner.id, section.id)

    async def fake_user():
        return stranger

    async def fake_db():
        yield real_db_session

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.setex = AsyncMock()
    application.dependency_overrides[get_redis] = lambda: fake_redis

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        resp = await client.get(f"/api/v1/kb/articles/{article.id}/files")

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 6. Vault ZIP import — articles created from MD files with frontmatter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vault_import_creates_articles(real_db_session):
    """POST /kb/import/vault with valid ZIP creates articles in DB."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db
    from app.models.kb import KbArticle

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value=None)
    fake_redis.setex = AsyncMock()
    fake_redis.xadd = AsyncMock()

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db
    application.dependency_overrides[get_redis] = lambda: fake_redis

    unique_title = f"Vault Article {uuid.uuid4().hex[:8]}"
    md_content = f"---\ntitle: {unique_title}\ntags:\n  - test\n---\n\n# Content\nBody text."

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Engineering/article.md", md_content.encode("utf-8"))
    buf.seek(0)

    csrf_token = "test-csrf-token"

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
        cookies={"XSRF-TOKEN": csrf_token},
    ) as client:
        files = {"file": ("vault.zip", buf, "application/zip")}
        resp = await client.post("/api/v1/kb/import/vault?strategy=skip", files=files)

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["created"] >= 1
    assert data["errors"] == []

    result = await real_db_session.execute(select(KbArticle).where(KbArticle.title == unique_title))
    article = result.scalar_one_or_none()
    assert article is not None
    assert "Body text" in (article.body or "")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Vault ZIP import — strategy=overwrite updates existing article
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vault_import_overwrite_updates_body(real_db_session):
    """POST /kb/import/vault with strategy=overwrite updates existing article body."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db
    from app.models.kb import KbArticle

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    section = await _create_db_section(real_db_session, editor.id)

    unique_title = f"Overwrite Article {uuid.uuid4().hex[:8]}"
    existing = KbArticle(
        title=unique_title,
        body="# Old body",
        status="draft",
        section_id=section.id,
        created_by=editor.id,
        updated_by=editor.id,
        inherit_permissions=True,
    )
    real_db_session.add(existing)
    await real_db_session.commit()
    await real_db_session.refresh(existing)

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="manager")
    fake_redis.setex = AsyncMock()
    fake_redis.xadd = AsyncMock()

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db
    application.dependency_overrides[get_redis] = lambda: fake_redis

    updated_md = f"---\ntitle: {unique_title}\n---\n\n# Updated body"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("article.md", updated_md.encode("utf-8"))
    buf.seek(0)

    csrf_token = "test-csrf-token"

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test", "x-xsrf-token": csrf_token},
        cookies={"XSRF-TOKEN": csrf_token},
    ) as client:
        files = {"file": ("vault.zip", buf, "application/zip")}
        resp = await client.post("/api/v1/kb/import/vault?strategy=overwrite", files=files)

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["updated"] >= 1

    await real_db_session.refresh(existing)
    assert "Updated body" in (existing.body or "")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Section export ZIP → contains article MD
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_section_export_zip_contains_article(real_db_session):
    """GET /kb/sections/{id}/export/zip returns ZIP with article Markdown."""
    import importlib
    import os

    from httpx import ASGITransport, AsyncClient

    import app.main as main_mod
    from app.api.deps import get_current_user, get_redis
    from app.core.database import get_db

    os.environ.setdefault("ADMIN_EMAIL", "")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    importlib.reload(main_mod)
    application = main_mod.app

    editor = await _create_db_user(real_db_session, role="editor")
    section = await _create_db_section(real_db_session, editor.id, "Export Section")
    article = await _create_db_article(real_db_session, editor.id, section.id)

    async def fake_user():
        return editor

    async def fake_db():
        yield real_db_session

    application.dependency_overrides[get_current_user] = fake_user
    application.dependency_overrides[get_db] = fake_db

    fake_redis = AsyncMock()
    fake_redis.get = AsyncMock(return_value="manager")
    fake_redis.setex = AsyncMock()
    application.dependency_overrides[get_redis] = lambda: fake_redis

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        resp = await client.get(f"/api/v1/kb/sections/{section.id}/export/zip")

    application.dependency_overrides.pop(get_current_user, None)
    application.dependency_overrides.pop(get_db, None)
    application.dependency_overrides.pop(get_redis, None)

    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert any(n.endswith(".md") for n in names)
        md_content = zf.read(names[0]).decode("utf-8")
        assert article.title in md_content
