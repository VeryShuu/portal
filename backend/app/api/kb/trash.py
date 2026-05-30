"""KB trash (корзина): список soft-deleted статей, restore, purge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.system_config import load_system_settings
from app.models.kb import KbArticle, KbArticleFile, KbSection
from app.models.user import User
from app.schemas.kb import (
    KbTrashItem,
    KbTrashList,
    KbTrashPurgeResult,
    KbUserRef,
)
from app.services.audit import push_audit_event
from app.services.kb_acl import invalidate_article_cache
from app.services.kb_trash import (
    purge_all_trash as _purge_all,
)
from app.services.kb_trash import (
    purge_article,
    purge_expired_articles,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


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

    total_res = await db.execute(
        select(func.count(KbArticle.id)).where(KbArticle.deleted_at.isnot(None))
    )
    total = int(total_res.scalar() or 0)

    purge_due = 0
    if retention > 0:
        threshold = datetime.now(UTC) - timedelta(days=retention)
        due_res = await db.execute(
            select(func.count(KbArticle.id)).where(
                KbArticle.deleted_at.isnot(None),
                KbArticle.deleted_at < threshold,
            )
        )
        purge_due = int(due_res.scalar() or 0)

    stmt = (
        select(KbArticle)
        .where(KbArticle.deleted_at.isnot(None))
        .order_by(KbArticle.deleted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
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

    sections_map: dict[uuid.UUID, str] = {}
    if section_ids:
        s_res = await db.execute(
            select(KbSection.id, KbSection.title).where(KbSection.id.in_(section_ids))
        )
        sections_map = {row[0]: row[1] for row in s_res.all()}

    users_map: dict[uuid.UUID, KbUserRef] = {}
    if user_ids:
        u_res = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in u_res.scalars().all():
            users_map[u.id] = KbUserRef.model_validate(u)

    files_res = await db.execute(
        select(
            KbArticleFile.article_id,
            func.count(KbArticleFile.id),
            func.coalesce(func.sum(KbArticleFile.size_bytes), 0),
        )
        .where(KbArticleFile.article_id.in_(article_ids))
        .group_by(KbArticleFile.article_id)
    )
    files_map: dict[uuid.UUID, tuple[int, int]] = {
        row[0]: (int(row[1]), int(row[2])) for row in files_res.all()
    }

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
                deleted_at=a.deleted_at,  # type: ignore[arg-type]
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
    res = await db.execute(
        select(KbArticle)
        .options(selectinload(KbArticle.tags))
        .where(KbArticle.id == article_id, KbArticle.deleted_at.isnot(None))
    )
    article = res.scalar_one_or_none()
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
    await push_audit_event(
        redis,
        event_type="kb.article_restored",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_article",
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
    pre = await db.execute(
        select(KbArticle.id).where(KbArticle.id == article_id, KbArticle.deleted_at.isnot(None))
    )
    if pre.scalar_one_or_none() is None:
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
    await push_audit_event(
        redis,
        event_type="kb.article_purged",
        user_id=str(user.id),
        user_email=user.email,
        resource_type="kb_article",
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
        await push_audit_event(
            redis,
            event_type="kb.trash_purged",
            user_id=str(user.id),
            user_email=user.email,
            resource_type="kb_trash",
            metadata={"older_than_days": older_than_days, "purged": purged},
        )
    return KbTrashPurgeResult(purged=purged)
