"""KB trash (корзина): список soft-deleted статей, restore, purge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.system_config import load_system_settings
from app.schemas.kb import (
    KbTrashItem,
    KbTrashList,
    KbTrashPurgeResult,
    KbUserRef,
)
from app.services.audit import make_audit_emitter
from app.services.kb_acl import invalidate_article_cache
from app.services.kb_trash import (
    purge_all_trash as _purge_all,
)
from app.services.kb_trash import (
    purge_article,
    purge_expired_articles,
)

from . import trash_repo

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

_emit_article = make_audit_emitter("kb_article")
_emit_trash = make_audit_emitter("kb_trash")


@router.get(
    "/trash/articles",
    response_model=KbTrashList,
    summary="Список статей в корзине (admin)",
)
async def list_trash(
    db: DbDep,
    _user: AdminDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> KbTrashList:
    sys_settings = load_system_settings()
    retention = sys_settings.kb_trash_retention_days

    total = await trash_repo.count_trashed(db)

    purge_due = 0
    if retention > 0:
        threshold = datetime.now(UTC) - timedelta(days=retention)
        purge_due = await trash_repo.count_trashed_due(db, threshold)

    rows = await trash_repo.list_trashed(db, limit=limit, offset=offset)
    if not rows:
        return KbTrashList(
            items=[],
            total=total,
            retention_days=retention,
            purge_due_count=purge_due,
        )

    article_ids = [a.id for a in rows]
    section_ids = {a.section_id for a in rows if a.section_id}
    user_ids = {a.created_by for a in rows if a.created_by} | {
        a.updated_by for a in rows if a.updated_by
    }

    sections_map = await trash_repo.get_section_titles(db, section_ids)

    users_map: dict[uuid.UUID, KbUserRef] = {}
    for u in await trash_repo.get_users(db, user_ids):
        users_map[u.id] = KbUserRef.model_validate(u)

    files_map = await trash_repo.get_file_stats(db, article_ids)

    # Размер inline-медиа не считаем: на больших корзинах rglob по диску
    # под каждый запрос листинга — десятки секунд I/O и блокировка event loop.
    # Каталоги inline-медиа всё равно удаляются вместе со статьёй при purge,
    # а полную оценку «сирот» даёт фоновый cleanup_kb_orphan_dirs.

    items: list[KbTrashItem] = []
    for a in rows:
        files_count, files_bytes = files_map.get(a.id, (0, 0))
        items.append(
            KbTrashItem(
                id=a.id,
                title=a.title,
                section_id=a.section_id,
                section_title=sections_map.get(a.section_id) if a.section_id else None,
                status=a.status,
                deleted_at=a.deleted_at,
                updated_at=a.updated_at,
                files_count=files_count,
                files_bytes=files_bytes,
                media_bytes=0,
                created_by=users_map.get(a.created_by) if a.created_by else None,
                updated_by=users_map.get(a.updated_by) if a.updated_by else None,
            )
        )

    return KbTrashList(
        items=items,
        total=total,
        retention_days=retention,
        purge_due_count=purge_due,
    )


@router.post(
    "/trash/articles/{article_id}/restore",
    summary="Восстановить статью из корзины (admin)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def restore_trash_article(
    article_id: uuid.UUID,
    db: DbDep,
    user: AdminDep,
    redis: RedisDep,
) -> None:
    article = await trash_repo.get_trashed_with_tags(db, article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found in trash",
        )
    article.deleted_at = None
    article.updated_by = user.id
    await db.commit()
    # Сбрасываем кэш ACL: за время soft-delete права раздела могли поменяться.
    await invalidate_article_cache(redis, article_id)
    await _emit_article(
        redis,
        event_type="kb.article_restored",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article_id),
    )


@router.post(
    "/trash/articles/{article_id}/purge",
    summary="Удалить статью из корзины окончательно (admin)",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def purge_trash_article(
    article_id: uuid.UUID,
    db: DbDep,
    user: AdminDep,
    redis: RedisDep,
) -> None:
    if not await trash_repo.trashed_exists(db, article_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found in trash",
        )
    removed = await purge_article(db, article_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found",
        )
    await invalidate_article_cache(redis, article_id)
    await _emit_article(
        redis,
        event_type="kb.article_purged",
        user_id=str(user.id),
        user_email=user.email,
        resource_id=str(article_id),
        metadata={"source": "trash_ui"},
    )


@router.post(
    "/trash/purge-all",
    response_model=KbTrashPurgeResult,
    summary="Очистить всю корзину или статьи старше N дней (admin)",
)
async def purge_all_trash(
    db: DbDep,
    user: AdminDep,
    redis: RedisDep,
    older_than_days: int | None = Query(
        default=None,
        ge=0,
        le=3650,
        description=(
            "Если задано — удалить только статьи, у которых deleted_at старше N дней. "
            "Если null — удалить ВСЕ статьи из корзины."
        ),
    ),
) -> KbTrashPurgeResult:
    if older_than_days is None:
        purged = await _purge_all(db)
    else:
        purged = await purge_expired_articles(db, max(older_than_days, 1))

    if purged > 0:
        await _emit_trash(
            redis,
            event_type="kb.trash_purged",
            user_id=str(user.id),
            user_email=user.email,
            metadata={"older_than_days": older_than_days, "purged": purged},
        )
    return KbTrashPurgeResult(purged=purged)
