"""Integration: пофайловый шеринг (file_shares) на реальных PostgreSQL + Redis.

Аудит тестирования 2026-08-21 (docs/wip/test-audit-remediation.md, фаза
«модули по прод-риску», files). Unit-тесты ACL (test_file_shares_acl.py)
построены на моках обоих резолверов — реальное поведение SQL (фильтры
активности шеры, группы, инвалидация кэша) не проверялось. Здесь — реальные
бизнес-инварианты доступа к файлам (ошибка здесь = утечка данных):

* активная шера даёт доступ; истекшая/отозванная/чужая — нет;
* группы Keycloak и ``__all_users__`` резолвятся;
* лучшая из нескольких шер;
* доступ через шер без folder-ACL; отзыв снимает доступ;
* инвалидация файлового кэша (не ждём TTL 300с);
* CHECK-констрейнт: ``manager`` на файл не выдаётся.

Запуск: ./scripts/test-integration.sh tests/integration/test_files_shares_acl_db.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.files import FileFolder
    from app.models.user import User

_FILENAME = "report-2026.pdf"


def _now() -> datetime:
    return datetime.now(UTC)


def _make_user(**kwargs) -> User:
    """Неперсистентный User: резолверы читают только id/role/keycloak_*."""
    from app.models.user import User as _User

    defaults: dict = {
        "id": uuid.uuid4(),
        "email": f"fs-{uuid.uuid4().hex[:8]}@x.test",
        "full_name": "Files Share Test",
        "role": "reader",
        "auth_source": "local",
    }
    defaults.update(kwargs)
    return _User(**defaults)


async def _make_folder(session: AsyncSession) -> FileFolder:
    from app.models.files import FileFolder as _FileFolder

    folder = _FileFolder(
        name=f"F-{uuid.uuid4().hex[:8]}",
        nc_path=f"/F-{uuid.uuid4().hex[:8]}",
        inherit_permissions=True,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(folder)
    await session.flush()
    return folder


async def _make_share(
    session: AsyncSession,
    folder: FileFolder,
    *,
    subject_id: str,
    permission: str = "viewer",
    subject_type: str = "user",
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> None:
    from app.models.files import FileShare

    session.add(
        FileShare(
            folder_id=folder.id,
            filename=_FILENAME,
            nc_path=f"{folder.nc_path}/{_FILENAME}",
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name="Test Subject",
            permission=permission,
            expires_at=expires_at,
            revoked_at=revoked_at,
            created_at=_now(),
        )
    )
    await session.flush()


@pytest_asyncio.fixture
async def folder(real_db_session):
    return await _make_folder(real_db_session)


class TestResolveFileSharePermission:
    async def test_active_share_by_user_id(self, real_db_session, redis_client, folder):
        from app.services.files_acl import resolve_file_share_permission

        user = _make_user()
        await _make_share(real_db_session, folder, subject_id=str(user.id), permission="editor")

        perm = await resolve_file_share_permission(
            user, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm == "editor"

    async def test_expired_share_ignored(self, real_db_session, redis_client, folder):
        from app.services.files_acl import resolve_file_share_permission

        user = _make_user()
        await _make_share(
            real_db_session,
            folder,
            subject_id=str(user.id),
            expires_at=_now() - timedelta(hours=1),
        )

        perm = await resolve_file_share_permission(
            user, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm is None

    async def test_future_expiry_still_active(self, real_db_session, redis_client, folder):
        from app.services.files_acl import resolve_file_share_permission

        user = _make_user()
        await _make_share(
            real_db_session,
            folder,
            subject_id=str(user.id),
            permission="viewer",
            expires_at=_now() + timedelta(days=7),
        )

        perm = await resolve_file_share_permission(
            user, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm == "viewer"

    async def test_revoked_share_ignored(self, real_db_session, redis_client, folder):
        from app.services.files_acl import resolve_file_share_permission

        user = _make_user()
        await _make_share(
            real_db_session,
            folder,
            subject_id=str(user.id),
            revoked_at=_now() - timedelta(minutes=5),
        )

        perm = await resolve_file_share_permission(
            user, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm is None

    async def test_other_subject_ignored_and_all_users_grants(
        self, real_db_session, redis_client, folder
    ):
        from app.services.acl_base import SYSTEM_ALL_USERS_SUBJECT_ID
        from app.services.files_acl import resolve_file_share_permission

        stranger = _make_user()
        await _make_share(real_db_session, folder, subject_id=str(uuid.uuid4()))

        # шер выдана чужому subject — наш пользователь доступа не имеет…
        perm = await resolve_file_share_permission(
            stranger, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm is None

        # …а шера на __all_users__ действует для любого пользователя
        await _make_share(
            real_db_session,
            folder,
            subject_id=SYSTEM_ALL_USERS_SUBJECT_ID,
            subject_type="group",
            permission="viewer",
        )
        another = _make_user()
        perm2 = await resolve_file_share_permission(
            another, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm2 == "viewer"

    async def test_keycloak_group_share(self, real_db_session, redis_client, folder):
        from app.services.files_acl import resolve_file_share_permission

        user = _make_user(keycloak_groups=["/dep-it"])
        # subject без слэша — subject_ids_for_user добавляет оба варианта
        await _make_share(
            real_db_session,
            folder,
            subject_id="dep-it",
            subject_type="group",
            permission="editor",
        )

        perm = await resolve_file_share_permission(
            user, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm == "editor"

    async def test_best_of_multiple_shares(self, real_db_session, redis_client, folder):
        from app.services.files_acl import resolve_file_share_permission

        user = _make_user(keycloak_groups=["/dep-sales"])
        await _make_share(real_db_session, folder, subject_id=str(user.id), permission="viewer")
        await _make_share(
            real_db_session,
            folder,
            subject_id="/dep-sales",
            subject_type="group",
            permission="editor",
        )

        perm = await resolve_file_share_permission(
            user, folder.id, _FILENAME, real_db_session, redis_client
        )
        assert perm == "editor", "должна выбираться лучшая из шер"


class TestRequireFileAccess:
    async def test_share_grants_access_without_folder_acl(
        self, real_db_session, redis_client, folder
    ):
        """Шер даёт доступ к файлу, когда folder-ACL у пользователя нет вообще."""
        from app.services.files_acl import require_file_access

        user = _make_user()
        await _make_share(real_db_session, folder, subject_id=str(user.id), permission="editor")

        effective = await require_file_access(
            user, folder, _FILENAME, "editor", real_db_session, redis_client
        )
        assert effective == "editor"

    async def test_no_share_no_folder_acl_is_403(self, real_db_session, redis_client, folder):
        from fastapi import HTTPException

        from app.services.files_acl import require_file_access

        user = _make_user()

        with pytest.raises(HTTPException) as exc_info:
            await require_file_access(
                user, folder, _FILENAME, "viewer", real_db_session, redis_client
            )
        assert exc_info.value.status_code == 403

    async def test_revoke_with_cache_invalidation_removes_access(
        self, real_db_session, redis_client, folder
    ):
        """Production-отзыв (сервис revoke_share) снимает доступ немедленно.

        audit-review 2026-08-22, P1: тест драйвит настоящую функцию отзыва
        (soft-revoke + инвалидация кэша одним вызовом), а не воспроизводит
        её руками — удаление invalidation из API теперь валит этот тест.
        """
        from fastapi import HTTPException
        from sqlalchemy import select

        from app.models.files import FileShare
        from app.services.files_acl import (
            require_file_access,
            resolve_file_share_permission,
        )
        from app.services.files_shares import revoke_share

        user = _make_user()
        await _make_share(real_db_session, folder, subject_id=str(user.id), permission="editor")

        # первый резолв — доступ есть, кэш заполнен
        assert (
            await resolve_file_share_permission(
                user, folder.id, _FILENAME, real_db_session, redis_client
            )
            == "editor"
        )

        share_id = (
            await real_db_session.execute(
                select(FileShare.id).where(
                    FileShare.folder_id == folder.id,
                    FileShare.filename == _FILENAME,
                    FileShare.subject_id == str(user.id),
                )
            )
        ).scalar_one()

        await revoke_share(
            real_db_session,
            redis_client,
            folder_id=folder.id,
            filename=_FILENAME,
            share_id=share_id,
        )

        assert (
            await resolve_file_share_permission(
                user, folder.id, _FILENAME, real_db_session, redis_client
            )
            is None
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_file_access(
                user, folder, _FILENAME, "viewer", real_db_session, redis_client
            )
        assert exc_info.value.status_code == 403


class TestDbConstraints:
    async def test_manager_permission_rejected_by_db(self, real_db_session, folder):
        """`manager` на файл не выдаётся — CHECK-констрейнт (sharing.md §3)."""
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError, match=r"file_shares_permission_check|permission"):
            await _make_share(
                real_db_session, folder, subject_id=str(uuid.uuid4()), permission="manager"
            )
            await real_db_session.flush()
