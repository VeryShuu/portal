"""Pure data-access helpers for KB permission endpoints.

Keeps SQL out of the HTTP layer (see ``app/api/news/repo.py`` for the pattern).
Each helper performs exactly one ``db.execute`` so the calling routes preserve
their original query ordering and counts.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KbArticlePermission, KbSection, KbSectionPermission
from app.models.user import User

_DESCENDANT_IDS_SQL = """
            WITH RECURSIVE descendants AS (
                SELECT id FROM kb_sections
                WHERE id = :section_id AND deleted_at IS NULL
                UNION ALL
                SELECT s.id FROM kb_sections s
                JOIN descendants d ON s.parent_id = d.id
                WHERE s.deleted_at IS NULL
            )
            SELECT id FROM descendants
        """


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def get_section(db: AsyncSession, section_id: uuid.UUID) -> KbSection | None:
    res = await db.execute(select(KbSection).where(KbSection.id == section_id))
    return res.scalar_one_or_none()


async def list_section_permissions(
    db: AsyncSession, section_id: uuid.UUID
) -> Sequence[KbSectionPermission]:
    res = await db.execute(
        select(KbSectionPermission).where(KbSectionPermission.section_id == section_id)
    )
    return res.scalars().all()


async def upsert_section_permission(
    db: AsyncSession,
    *,
    section_id: uuid.UUID,
    subject_type: str,
    subject_id: str,
    subject_name: str | None,
    permission: str,
    granted_by: uuid.UUID,
) -> KbSectionPermission:
    stmt = (
        pg_insert(KbSectionPermission)
        .values(
            section_id=section_id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            permission=permission,
            granted_by=granted_by,
        )
        .on_conflict_do_update(
            constraint="uq_kb_sec_perm_section_subject",
            set_={
                "permission": permission,
                "subject_name": subject_name,
                "granted_by": granted_by,
            },
        )
        .returning(KbSectionPermission)
    )
    res = await db.execute(stmt)
    return res.scalar_one()


async def delete_section_permission(
    db: AsyncSession, *, section_id: uuid.UUID, subject_id: str
) -> None:
    await db.execute(
        delete(KbSectionPermission).where(
            KbSectionPermission.section_id == section_id,
            KbSectionPermission.subject_id == subject_id,
        )
    )


async def list_article_permissions(
    db: AsyncSession, article_id: uuid.UUID
) -> Sequence[KbArticlePermission]:
    res = await db.execute(
        select(KbArticlePermission).where(KbArticlePermission.article_id == article_id)
    )
    return res.scalars().all()


async def upsert_article_permission(
    db: AsyncSession,
    *,
    article_id: uuid.UUID,
    subject_type: str,
    subject_id: str,
    subject_name: str | None,
    permission: str,
    granted_by: uuid.UUID,
) -> KbArticlePermission:
    stmt = (
        pg_insert(KbArticlePermission)
        .values(
            article_id=article_id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            permission=permission,
            granted_by=granted_by,
        )
        .on_conflict_do_update(
            constraint="uq_kb_art_perm_article_subject",
            set_={
                "permission": permission,
                "subject_name": subject_name,
                "granted_by": granted_by,
            },
        )
        .returning(KbArticlePermission)
    )
    res = await db.execute(stmt)
    return res.scalar_one()


async def delete_article_permission(
    db: AsyncSession, *, article_id: uuid.UUID, subject_id: str
) -> None:
    await db.execute(
        delete(KbArticlePermission).where(
            KbArticlePermission.article_id == article_id,
            KbArticlePermission.subject_id == subject_id,
        )
    )


async def copy_section_permission(
    db: AsyncSession,
    *,
    section_id: uuid.UUID,
    subject_type: str,
    subject_id: str,
    subject_name: str | None,
    permission: str,
    granted_by: uuid.UUID,
) -> None:
    stmt = (
        pg_insert(KbSectionPermission)
        .values(
            section_id=section_id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            permission=permission,
            granted_by=granted_by,
        )
        .on_conflict_do_nothing()
    )
    await db.execute(stmt)


async def copy_article_permission(
    db: AsyncSession,
    *,
    article_id: uuid.UUID,
    subject_type: str,
    subject_id: str,
    subject_name: str | None,
    permission: str,
    granted_by: uuid.UUID,
) -> None:
    stmt = (
        pg_insert(KbArticlePermission)
        .values(
            article_id=article_id,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_name=subject_name,
            permission=permission,
            granted_by=granted_by,
        )
        .on_conflict_do_nothing()
    )
    await db.execute(stmt)


async def list_descendant_section_ids(db: AsyncSession, section_id: uuid.UUID) -> list[uuid.UUID]:
    res = await db.execute(
        text(_DESCENDANT_IDS_SQL),
        {"section_id": str(section_id)},
    )
    return [row[0] for row in res.fetchall()]
