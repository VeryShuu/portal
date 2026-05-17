"""SQL push-down фильтрация видимости статей по KB-ACL."""

from __future__ import annotations

from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import CTE

from app.models.kb import KbArticle, KbArticlePermission, KbSection, KbSectionPermission
from app.models.user import User

from ._common import _subject_ids_for_user


def _accessible_sections_cte(subject_ids: list[str]) -> CTE:
    """Recursive CTE: все section_id, к которым у subject_ids есть доступ
    напрямую или через предков (наследование вниз по дереву разделов).

    База: разделы с прямой permission-row для subject_ids.
    Шаг: дочерние разделы accessible-разделов (не удалённые).
    """
    base = (
        select(KbSection.id.label("section_id"))
        .where(
            exists().where(
                and_(
                    KbSectionPermission.section_id == KbSection.id,
                    KbSectionPermission.subject_id.in_(subject_ids),
                )
            )
        )
        .cte("accessible_sections", recursive=True)
    )
    descendant = (
        select(KbSection.id)
        .join(base, KbSection.parent_id == base.c.section_id)
        .where(KbSection.deleted_at.is_(None))
    )
    return base.union_all(descendant)


async def apply_article_visibility(
    stmt: Select,
    user: User,
    db: AsyncSession,
) -> Select:
    """Добавляет к Select WHERE-условие, оставляющее только статьи, к которым
    у пользователя есть ACL-доступ (push-down фильтрация в SQL).

    Эквивалент batch_resolve_article_permissions, но выполняется в БД, что
    позволяет корректно считать total и применять LIMIT/OFFSET.
    """
    if user.role == "admin":
        return stmt

    subject_ids = await _subject_ids_for_user(user)
    if not subject_ids:
        return stmt.where(KbArticle.created_by == user.id)

    sections_cte = _accessible_sections_cte(subject_ids)

    direct_exists = exists().where(
        and_(
            KbArticlePermission.article_id == KbArticle.id,
            KbArticlePermission.subject_id.in_(subject_ids),
        )
    )

    section_accessible = KbArticle.section_id.in_(select(sections_cte.c.section_id))

    return stmt.where(
        or_(
            KbArticle.created_by == user.id,
            and_(
                KbArticle.inherit_permissions.is_(False),
                direct_exists,
            ),
            and_(
                KbArticle.inherit_permissions.is_(True),
                KbArticle.section_id.is_not(None),
                section_accessible,
            ),
            and_(
                KbArticle.inherit_permissions.is_(True),
                KbArticle.section_id.is_(None),
                direct_exists,
            ),
        )
    )
