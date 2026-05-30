"""Integration-tests for ``app/api/photos/*`` route handlers.

Поднимают folder/photo/sharing/zip-эндпойнты через прямой вызов route-функций
(тот же стиль, что в ``test_meetings_bookings_extra.py``) на реальной БД.
Redis-зависимости мокаются — ACL-резолверы пишут/читают только ключи кэша,
поведение покрыто отдельно в ``test_photos_acl.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _redis_mock() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.lpush = AsyncMock()
    r.ltrim = AsyncMock()
    r.expire = AsyncMock()
    return r


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"), app=SimpleNamespace(state=SimpleNamespace())
    )


@pytest_asyncio.fixture
async def folder(real_db_session, real_admin):
    from app.api.photos.folders import create_folder
    from app.schemas.photos import CreateFolderRequest

    req = _request()
    redis = _redis_mock()
    folder_out = await create_folder(
        CreateFolderRequest(name=f"FolderA-{uuid.uuid4().hex[:6]}"),
        req,
        real_db_session,
        real_admin,
        redis,
    )
    return folder_out


@pytest_asyncio.fixture
async def photo_in_folder(real_db_session, folder, real_admin):
    from app.models.photos import Photo

    p = Photo(
        folder_id=folder.id,
        filename=f"{uuid.uuid4().hex}.jpg",
        original_name="test.jpg",
        size_bytes=1024,
        mime_type="image/jpeg",
        width=100,
        height=100,
        uploaded_by=real_admin.id,
        processed=True,
    )
    real_db_session.add(p)
    await real_db_session.commit()
    await real_db_session.refresh(p)
    return p


class TestFolderRoutes:
    async def test_create_root_folder_admin_ok(self, real_db_session, real_admin):
        from app.api.photos.folders import create_folder
        from app.schemas.photos import CreateFolderRequest

        out = await create_folder(
            CreateFolderRequest(name=f"Root-{uuid.uuid4().hex[:6]}"),
            _request(),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.id is not None
        assert out.permission == "manager"
        assert out.parent_id is None

    async def test_create_root_folder_reader_forbidden(self, real_db_session, real_user):
        from app.api.photos.folders import create_folder
        from app.schemas.photos import CreateFolderRequest

        with pytest.raises(HTTPException) as exc:
            await create_folder(
                CreateFolderRequest(name="x"),
                _request(),
                real_db_session,
                real_user,
                _redis_mock(),
            )
        assert exc.value.status_code == 403

    async def test_create_subfolder_under_parent(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import create_folder
        from app.schemas.photos import CreateFolderRequest

        out = await create_folder(
            CreateFolderRequest(parent_id=folder.id, name="Child"),
            _request(),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.parent_id == folder.id
        assert "/" in out.path

    async def test_create_folder_unknown_parent_404(self, real_db_session, real_admin):
        from app.api.photos.folders import create_folder
        from app.schemas.photos import CreateFolderRequest

        with pytest.raises(HTTPException) as exc:
            await create_folder(
                CreateFolderRequest(parent_id=uuid.uuid4(), name="x"),
                _request(),
                real_db_session,
                real_admin,
                _redis_mock(),
            )
        assert exc.value.status_code == 404

    async def test_get_folder_happy(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import get_folder

        out = await get_folder(folder.id, real_db_session, real_admin, _redis_mock())
        assert out.id == folder.id
        assert out.permission == "manager"

    async def test_get_folder_404(self, real_db_session, real_admin):
        from app.api.photos.folders import get_folder

        with pytest.raises(HTTPException) as exc:
            await get_folder(uuid.uuid4(), real_db_session, real_admin, _redis_mock())
        assert exc.value.status_code == 404

    async def test_get_folder_reader_no_access_403(self, real_db_session, real_user, folder):
        from app.api.photos.folders import get_folder

        with pytest.raises(HTTPException) as exc:
            await get_folder(folder.id, real_db_session, real_user, _redis_mock())
        assert exc.value.status_code == 403

    async def test_update_folder_rename(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import update_folder
        from app.schemas.photos import UpdateFolderRequest

        out = await update_folder(
            folder.id,
            UpdateFolderRequest(name="NewName"),
            _request(),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.name == "NewName"

    async def test_update_folder_description(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import update_folder
        from app.schemas.photos import UpdateFolderRequest

        out = await update_folder(
            folder.id,
            UpdateFolderRequest(description="hello"),
            _request(),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.description == "hello"

    async def test_update_folder_404(self, real_db_session, real_admin):
        from app.api.photos.folders import update_folder
        from app.schemas.photos import UpdateFolderRequest

        with pytest.raises(HTTPException) as exc:
            await update_folder(
                uuid.uuid4(),
                UpdateFolderRequest(name="x"),
                _request(),
                real_db_session,
                real_admin,
                _redis_mock(),
            )
        assert exc.value.status_code == 404

    async def test_update_folder_set_cover_photo(
        self, real_db_session, real_admin, folder, photo_in_folder
    ):
        from app.api.photos.folders import update_folder
        from app.schemas.photos import UpdateFolderRequest

        out = await update_folder(
            folder.id,
            UpdateFolderRequest(cover_photo_id=photo_in_folder.id),
            _request(),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.cover_photo_id == photo_in_folder.id

    async def test_update_folder_cover_outside_400(self, real_db_session, real_admin, folder):
        """Cover photo не из этой папки → 400."""
        from app.api.photos.folders import create_folder, update_folder
        from app.models.photos import Photo
        from app.schemas.photos import CreateFolderRequest, UpdateFolderRequest

        other = await create_folder(
            CreateFolderRequest(name=f"Other-{uuid.uuid4().hex[:6]}"),
            _request(),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        p = Photo(
            folder_id=other.id,
            filename="x.jpg",
            original_name="x.jpg",
            size_bytes=1,
            mime_type="image/jpeg",
            processed=True,
        )
        real_db_session.add(p)
        await real_db_session.commit()
        await real_db_session.refresh(p)

        with pytest.raises(HTTPException) as exc:
            await update_folder(
                folder.id,
                UpdateFolderRequest(cover_photo_id=p.id),
                _request(),
                real_db_session,
                real_admin,
                _redis_mock(),
            )
        assert exc.value.status_code == 400

    async def test_delete_then_restore_then_purge(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import delete_folder, purge_folder, restore_folder

        await delete_folder(folder.id, _request(), real_db_session, real_admin, _redis_mock())

        restored = await restore_folder(
            folder.id, _request(), real_db_session, real_admin, _redis_mock()
        )
        assert restored.id == folder.id

        # delete again, then purge
        await delete_folder(folder.id, _request(), real_db_session, real_admin, _redis_mock())
        await purge_folder(folder.id, _request(), real_db_session, real_admin, _redis_mock())

    async def test_restore_not_deleted_400(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import restore_folder

        with pytest.raises(HTTPException) as exc:
            await restore_folder(folder.id, _request(), real_db_session, real_admin, _redis_mock())
        assert exc.value.status_code == 400

    async def test_purge_not_trashed_400(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import purge_folder

        with pytest.raises(HTTPException) as exc:
            await purge_folder(folder.id, _request(), real_db_session, real_admin, _redis_mock())
        assert exc.value.status_code == 400

    async def test_list_folder_tree(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import list_folder_tree

        tree = await list_folder_tree(real_db_session, real_admin, _redis_mock())
        ids = [n.id for n in tree.items]
        assert folder.id in ids

    async def test_list_deleted_admin_includes(self, real_db_session, real_admin, folder):
        from app.api.photos.folders import delete_folder, list_deleted_folders

        await delete_folder(folder.id, _request(), real_db_session, real_admin, _redis_mock())
        out = await list_deleted_folders(real_db_session, real_admin, _redis_mock())
        assert any(f.id == folder.id for f in out)


class TestPhotoRoutes:
    async def test_list_folder_photos_happy(
        self, real_db_session, real_admin, folder, photo_in_folder
    ):
        from app.api.photos.photos import list_folder_photos

        out = await list_folder_photos(
            folder.id,
            real_db_session,
            real_admin,
            _redis_mock(),
            page=1,
            per_page=50,
            sort="created_at",
            min_date=None,
            max_date=None,
            min_size=None,
            max_size=None,
            mime_type=None,
            tag_id=None,
        )
        assert out.total == 1
        assert out.items[0].id == photo_in_folder.id

    async def test_list_folder_photos_404(self, real_db_session, real_admin):
        from app.api.photos.photos import list_folder_photos

        with pytest.raises(HTTPException) as exc:
            await list_folder_photos(
                uuid.uuid4(),
                real_db_session,
                real_admin,
                _redis_mock(),
                page=1,
                per_page=50,
                sort="created_at",
                min_date=None,
                max_date=None,
                min_size=None,
                max_size=None,
                mime_type=None,
                tag_id=None,
            )
        assert exc.value.status_code == 404

    async def test_list_folder_photos_reader_403(
        self, real_db_session, real_user, folder, photo_in_folder
    ):
        from app.api.photos.photos import list_folder_photos

        with pytest.raises(HTTPException) as exc:
            await list_folder_photos(
                folder.id,
                real_db_session,
                real_user,
                _redis_mock(),
                page=1,
                per_page=50,
                sort="created_at",
                min_date=None,
                max_date=None,
                min_size=None,
                max_size=None,
                mime_type=None,
                tag_id=None,
            )
        assert exc.value.status_code == 403

    async def test_list_deleted_photos_empty(self, real_db_session, real_admin):
        from app.api.photos.photos import list_deleted_photos

        out = await list_deleted_photos(
            real_db_session, real_admin, _redis_mock(), page=1, per_page=50
        )
        assert out.total >= 0


class TestSharingRoutes:
    async def test_create_folder_share_then_list_then_revoke(
        self, real_db_session, real_admin, folder
    ):
        from app.api.photos.sharing import (
            create_folder_share,
            list_folder_shares,
            revoke_folder_share,
        )
        from app.schemas.photos import FolderShareLinkRequest

        out = await create_folder_share(
            folder.id,
            FolderShareLinkRequest(expires_in_days=7),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.folder_id == folder.id
        assert out.token

        listed = await list_folder_shares(folder.id, real_db_session, real_admin, _redis_mock())
        assert any(s.id == out.id for s in listed)

        await revoke_folder_share(out.id, real_db_session, real_admin, _redis_mock())

    async def test_create_folder_share_404(self, real_db_session, real_admin):
        from app.api.photos.sharing import create_folder_share
        from app.schemas.photos import FolderShareLinkRequest

        with pytest.raises(HTTPException) as exc:
            await create_folder_share(
                uuid.uuid4(),
                FolderShareLinkRequest(expires_in_days=7),
                real_db_session,
                real_admin,
                _redis_mock(),
            )
        assert exc.value.status_code == 404

    async def test_create_folder_share_reader_403(self, real_db_session, real_user, folder):
        from app.api.photos.sharing import create_folder_share
        from app.schemas.photos import FolderShareLinkRequest

        with pytest.raises(HTTPException) as exc:
            await create_folder_share(
                folder.id,
                FolderShareLinkRequest(expires_in_days=7),
                real_db_session,
                real_user,
                _redis_mock(),
            )
        assert exc.value.status_code == 403

    async def test_create_photo_share_happy(self, real_db_session, real_admin, photo_in_folder):
        from app.api.photos.sharing import create_share_link
        from app.schemas.photos import ShareLinkRequest

        req = _request()
        req.base_url = "http://test/"
        out = await create_share_link(
            photo_in_folder.id,
            req,
            ShareLinkRequest(expires_in_days=7),
            real_db_session,
            real_admin,
            _redis_mock(),
        )
        assert out.photo_id == photo_in_folder.id
        assert out.token

    async def test_create_photo_share_404(self, real_db_session, real_admin):
        from app.api.photos.sharing import create_share_link
        from app.schemas.photos import ShareLinkRequest

        req = _request()
        req.base_url = "http://test/"
        with pytest.raises(HTTPException) as exc:
            await create_share_link(
                uuid.uuid4(),
                req,
                ShareLinkRequest(expires_in_days=7),
                real_db_session,
                real_admin,
                _redis_mock(),
            )
        assert exc.value.status_code == 404

    async def test_get_my_shares_filters_expired_and_revoked(
        self, real_db_session, real_admin, folder, photo_in_folder
    ):
        from app.api.photos.sharing import get_my_shares
        from app.models.photos import PhotoFolderShareToken, PhotoShareToken

        active = PhotoShareToken(
            photo_id=photo_in_folder.id,
            token=uuid.uuid4().hex,
            created_by=real_admin.id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        expired = PhotoShareToken(
            photo_id=photo_in_folder.id,
            token=uuid.uuid4().hex,
            created_by=real_admin.id,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        revoked = PhotoShareToken(
            photo_id=photo_in_folder.id,
            token=uuid.uuid4().hex,
            created_by=real_admin.id,
            revoked_at=datetime.now(UTC),
        )
        ftok = PhotoFolderShareToken(
            folder_id=folder.id,
            token=uuid.uuid4().hex,
            created_by=real_admin.id,
        )
        for x in (active, expired, revoked, ftok):
            real_db_session.add(x)
        await real_db_session.commit()

        out = await get_my_shares(real_db_session, real_admin)
        photo_ids = {t.id for t in out.photo_tokens}
        assert active.id in photo_ids
        assert expired.id not in photo_ids
        assert revoked.id not in photo_ids
        assert any(t.id == ftok.id for t in out.folder_tokens)

    async def test_revoke_photo_share_404(self, real_db_session, real_admin):
        from app.api.photos.sharing import revoke_photo_share

        with pytest.raises(HTTPException) as exc:
            await revoke_photo_share(uuid.uuid4(), real_db_session, real_admin, _redis_mock())
        assert exc.value.status_code == 404

    async def test_revoke_photo_share_other_user_403(
        self, real_db_session, real_user, real_admin, photo_in_folder
    ):
        """Не-owner и не-admin — 403."""
        from app.api.photos.sharing import revoke_photo_share
        from app.models.photos import PhotoShareToken

        tok = PhotoShareToken(
            photo_id=photo_in_folder.id,
            token=uuid.uuid4().hex,
            created_by=real_admin.id,
        )
        real_db_session.add(tok)
        await real_db_session.commit()
        await real_db_session.refresh(tok)

        with pytest.raises(HTTPException) as exc:
            await revoke_photo_share(tok.id, real_db_session, real_user, _redis_mock())
        assert exc.value.status_code == 403

    async def test_revoke_folder_share_404(self, real_db_session, real_admin):
        from app.api.photos.sharing import revoke_folder_share

        with pytest.raises(HTTPException) as exc:
            await revoke_folder_share(uuid.uuid4(), real_db_session, real_admin, _redis_mock())
        assert exc.value.status_code == 404


class TestZipJobsRoutes:
    async def test_create_zip_job_happy(self, real_db_session, real_admin, folder):
        from app.api.photos.zip_jobs import create_zip_job

        out = await create_zip_job(
            folder.id, _request(), real_db_session, real_admin, _redis_mock()
        )
        assert out.folder_id == folder.id
        assert out.status == "pending"

    async def test_create_zip_job_folder_404(self, real_db_session, real_admin):
        from app.api.photos.zip_jobs import create_zip_job

        with pytest.raises(HTTPException) as exc:
            await create_zip_job(
                uuid.uuid4(), _request(), real_db_session, real_admin, _redis_mock()
            )
        assert exc.value.status_code == 404

    async def test_get_zip_job_404(self, real_db_session, real_admin):
        from app.api.photos.zip_jobs import get_zip_job

        with pytest.raises(HTTPException) as exc:
            await get_zip_job(uuid.uuid4(), real_db_session, real_admin)
        assert exc.value.status_code == 404

    async def test_get_zip_job_other_user_403(self, real_db_session, real_user, real_admin, folder):
        from app.api.photos.zip_jobs import create_zip_job, get_zip_job

        out = await create_zip_job(
            folder.id, _request(), real_db_session, real_admin, _redis_mock()
        )
        with pytest.raises(HTTPException) as exc:
            await get_zip_job(out.id, real_db_session, real_user)
        assert exc.value.status_code == 403

    async def test_get_zip_job_owner_ok(self, real_db_session, real_admin, folder):
        from app.api.photos.zip_jobs import create_zip_job, get_zip_job

        out = await create_zip_job(
            folder.id, _request(), real_db_session, real_admin, _redis_mock()
        )
        got = await get_zip_job(out.id, real_db_session, real_admin)
        assert got.id == out.id

    async def test_download_zip_job_not_ready_404(self, real_db_session, real_admin, folder):
        from app.api.photos.zip_jobs import create_zip_job, download_zip_job

        out = await create_zip_job(
            folder.id, _request(), real_db_session, real_admin, _redis_mock()
        )
        # status is "pending" → 404 "File not ready"
        with pytest.raises(HTTPException) as exc:
            await download_zip_job(out.id, real_db_session, real_admin)
        assert exc.value.status_code == 404
