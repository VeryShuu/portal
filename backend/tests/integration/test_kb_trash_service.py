"""Integration-тесты для app/services/kb_trash.py.

Покрывает:
- purge_article: happy + missing id
- purge_articles_bulk: batched DELETE + rmtree
- purge_all_trash: пагинация по soft-deleted
- purge_expired_articles: retention<=0 ранний выход; threshold-фильтр; chunk loop
- cleanup_orphan_dirs: удаление чужих папок; skip несоответствующих имен;
  symlink-outside защита (best-effort)
- remove_article_dirs / try_remove_empty_article_dir: пустая/непустая dir
- _kb_files_root / _kb_media_root: настройка через tmp_path
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.kb import KbArticle, KbSection
from app.services import kb_trash as kbt

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def kb_dirs(tmp_path, monkeypatch):
    """Перенаправляет kb_files_dir/kb_media_dir в tmp_path и сбрасывает get_settings."""
    from app.core.config import get_settings

    files_root = tmp_path / "kb_files"
    media_root = tmp_path / "kb_media"
    files_root.mkdir()
    media_root.mkdir()

    settings = get_settings()
    monkeypatch.setattr(settings, "kb_files_dir", str(files_root))
    monkeypatch.setattr(settings, "kb_media_dir", str(media_root))
    return files_root, media_root


async def _make_section(db, *, title: str | None = None) -> KbSection:
    section = KbSection(
        title=title or f"sec-{uuid.uuid4().hex[:6]}",
        slug=f"slug-{uuid.uuid4().hex[:6]}",
    )
    db.add(section)
    await db.flush()
    return section


async def _make_article(
    db, section: KbSection, *, deleted_at: datetime | None = None
) -> KbArticle:
    article = KbArticle(
        section_id=section.id,
        title="t",
        body="b",
        status="draft",
        version=1,
        deleted_at=deleted_at,
    )
    db.add(article)
    await db.flush()
    return article


def _seed_dirs(files_root: Path, media_root: Path, article_id: uuid.UUID) -> None:
    f = files_root / str(article_id)
    m = media_root / str(article_id)
    f.mkdir()
    m.mkdir()
    (f / "a.txt").write_text("hello")
    (m / "img.png").write_bytes(b"\x89PNG")


class TestRoots:
    async def test_kb_files_root_uses_settings(self, kb_dirs):
        files_root, _ = kb_dirs
        assert kbt._kb_files_root() == files_root.resolve()

    async def test_kb_media_root_uses_settings(self, kb_dirs):
        _, media_root = kb_dirs
        assert kbt._kb_media_root() == media_root.resolve()


class TestRemoveArticleDirs:
    async def test_remove_existing_dirs(self, kb_dirs):
        files_root, media_root = kb_dirs
        aid = uuid.uuid4()
        _seed_dirs(files_root, media_root, aid)

        await kbt.remove_article_dirs(aid)
        assert not (files_root / str(aid)).exists()
        assert not (media_root / str(aid)).exists()

    async def test_remove_missing_dirs_silently(self, kb_dirs):
        # No-op without raising.
        await kbt.remove_article_dirs(uuid.uuid4())


class TestTryRemoveEmptyDir:
    async def test_removes_empty_files_dir(self, kb_dirs):
        files_root, _ = kb_dirs
        aid = uuid.uuid4()
        target = files_root / str(aid)
        target.mkdir()
        await kbt.try_remove_empty_article_dir(aid, "files")
        assert not target.exists()

    async def test_removes_empty_media_dir(self, kb_dirs):
        _, media_root = kb_dirs
        aid = uuid.uuid4()
        target = media_root / str(aid)
        target.mkdir()
        await kbt.try_remove_empty_article_dir(aid, "media")
        assert not target.exists()

    async def test_keeps_nonempty_dir(self, kb_dirs):
        files_root, _ = kb_dirs
        aid = uuid.uuid4()
        target = files_root / str(aid)
        target.mkdir()
        (target / "stay.txt").write_text("x")
        await kbt.try_remove_empty_article_dir(aid, "files")
        assert target.exists()

    async def test_missing_dir_is_noop(self, kb_dirs):
        await kbt.try_remove_empty_article_dir(uuid.uuid4(), "files")


class TestPurgeArticle:
    async def test_purge_existing(self, real_db_session, kb_dirs):
        files_root, media_root = kb_dirs
        section = await _make_section(real_db_session)
        article = await _make_article(
            real_db_session, section, deleted_at=datetime.now(UTC)
        )
        await real_db_session.commit()
        _seed_dirs(files_root, media_root, article.id)

        ok = await kbt.purge_article(real_db_session, article.id)
        assert ok is True
        # DB row gone.
        res = await real_db_session.execute(
            select(KbArticle).where(KbArticle.id == article.id)
        )
        assert res.scalar_one_or_none() is None
        # FS gone.
        assert not (files_root / str(article.id)).exists()
        assert not (media_root / str(article.id)).exists()

    async def test_purge_missing_returns_false(self, real_db_session, kb_dirs):
        ok = await kbt.purge_article(real_db_session, uuid.uuid4())
        assert ok is False


class TestPurgeBulk:
    async def test_purge_articles_bulk_chunks_and_removes_dirs(
        self, real_db_session, kb_dirs, monkeypatch
    ):
        files_root, media_root = kb_dirs
        # Force tiny chunk to exercise the loop.
        monkeypatch.setattr(kbt, "PURGE_BATCH_SIZE", 2)

        section = await _make_section(real_db_session)
        ids: list[uuid.UUID] = []
        for _ in range(3):
            a = await _make_article(
                real_db_session, section, deleted_at=datetime.now(UTC)
            )
            ids.append(a.id)
            _seed_dirs(files_root, media_root, a.id)
        await real_db_session.commit()

        total = await kbt.purge_articles_bulk(real_db_session, ids)
        assert total == 3
        for aid in ids:
            assert not (files_root / str(aid)).exists()
            assert not (media_root / str(aid)).exists()

    async def test_purge_articles_bulk_empty_list(self, real_db_session, kb_dirs):
        assert await kbt.purge_articles_bulk(real_db_session, []) == 0


class TestPurgeAllTrash:
    async def test_purge_all_only_soft_deleted(self, real_db_session, kb_dirs):
        files_root, media_root = kb_dirs
        section = await _make_section(real_db_session)
        # 2 soft-deleted + 1 alive
        a1 = await _make_article(
            real_db_session, section, deleted_at=datetime.now(UTC)
        )
        a2 = await _make_article(
            real_db_session, section, deleted_at=datetime.now(UTC)
        )
        alive = await _make_article(real_db_session, section)
        await real_db_session.commit()
        for a in (a1, a2, alive):
            _seed_dirs(files_root, media_root, a.id)

        total = await kbt.purge_all_trash(real_db_session)
        assert total == 2
        # Alive untouched in DB.
        res = await real_db_session.execute(
            select(KbArticle.id).where(KbArticle.id == alive.id)
        )
        assert res.scalar_one() == alive.id


class TestPurgeExpired:
    async def test_retention_zero_is_noop(self, real_db_session, kb_dirs):
        assert await kbt.purge_expired_articles(real_db_session, 0) == 0
        assert await kbt.purge_expired_articles(real_db_session, -5) == 0

    async def test_purges_only_old_enough(self, real_db_session, kb_dirs):
        files_root, media_root = kb_dirs
        section = await _make_section(real_db_session)
        old = await _make_article(
            real_db_session,
            section,
            deleted_at=datetime.now(UTC) - timedelta(days=40),
        )
        recent = await _make_article(
            real_db_session,
            section,
            deleted_at=datetime.now(UTC) - timedelta(days=1),
        )
        await real_db_session.commit()
        _seed_dirs(files_root, media_root, old.id)
        _seed_dirs(files_root, media_root, recent.id)

        total = await kbt.purge_expired_articles(real_db_session, retention_days=30)
        assert total == 1
        assert not (files_root / str(old.id)).exists()
        # Recent stays.
        res = await real_db_session.execute(
            select(KbArticle.id).where(KbArticle.id == recent.id)
        )
        assert res.scalar_one() == recent.id


class TestCleanupOrphanDirs:
    async def test_removes_unknown_uuid_dirs(self, real_db_session, kb_dirs):
        files_root, media_root = kb_dirs
        # Create a registered article + dirs (should be kept).
        section = await _make_section(real_db_session)
        keeper = await _make_article(real_db_session, section)
        await real_db_session.commit()
        _seed_dirs(files_root, media_root, keeper.id)

        # Orphans (random UUIDs, no DB row).
        orphans = [uuid.uuid4() for _ in range(2)]
        for oid in orphans:
            _seed_dirs(files_root, media_root, oid)

        removed = await kbt.cleanup_orphan_dirs(real_db_session)
        # Orphans counted per-root: files + media → 2 per orphan × 2 orphans = 4.
        assert removed == 4
        # Keeper survives.
        assert (files_root / str(keeper.id)).exists()
        # Orphans gone.
        for oid in orphans:
            assert not (files_root / str(oid)).exists()
            assert not (media_root / str(oid)).exists()

    async def test_skips_non_uuid_dirs_and_files(self, real_db_session, kb_dirs):
        files_root, media_root = kb_dirs
        # Non-UUID directory and a plain file at root.
        (files_root / "notes").mkdir()
        (files_root / "stray.txt").write_text("x")
        (media_root / "thumbs").mkdir()

        removed = await kbt.cleanup_orphan_dirs(real_db_session)
        assert removed == 0
        assert (files_root / "notes").exists()
        assert (files_root / "stray.txt").exists()
        assert (media_root / "thumbs").exists()

    async def test_symlink_outside_root_is_skipped(
        self, real_db_session, kb_dirs, tmp_path
    ):
        files_root, _ = kb_dirs
        # A symlink whose name LOOKS like a uuid but points outside root.
        outside = tmp_path / "outside_target"
        outside.mkdir()
        link_uuid = uuid.uuid4()
        link = files_root / str(link_uuid)
        os.symlink(str(outside), str(link))

        removed = await kbt.cleanup_orphan_dirs(real_db_session)
        # The symlink should be skipped (real path is outside root) and outside
        # target must remain intact.
        assert outside.exists()
        assert removed == 0

    async def test_missing_roots_short_circuits(self, real_db_session, monkeypatch, tmp_path):
        from app.core.config import get_settings

        # Point both roots to non-existent paths.
        settings = get_settings()
        monkeypatch.setattr(settings, "kb_files_dir", str(tmp_path / "absent_files"))
        monkeypatch.setattr(settings, "kb_media_dir", str(tmp_path / "absent_media"))

        assert await kbt.cleanup_orphan_dirs(real_db_session) == 0
