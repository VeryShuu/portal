"""KB article versions and diff endpoints."""

from __future__ import annotations

import asyncio
import difflib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbDep, RedisDep
from app.models.kb import KbArticleVersion
from app.schemas.kb import KbArticlePublic, KbUserRef, KbVersionList, KbVersionPublic
from app.schemas.kb_extra import DiffHunk, DiffResponse
from app.services.kb_acl import require_article_permission

from . import versions_repo
from ._common import _article_to_public, _get_article_or_404, _get_breadcrumbs

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get(
    "/articles/{article_id}/versions", response_model=KbVersionList, summary="Версии статьи"
)
async def list_versions(
    article_id: uuid.UUID,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> KbVersionList:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    total = await versions_repo.count_versions(db, article_id)
    versions = await versions_repo.list_versions(db, article_id, limit=limit, offset=offset)

    user_ids = {v.changed_by for v in versions if v.changed_by}
    users_map = await versions_repo.get_version_changers(db, user_ids)

    items = []
    for v in versions:
        changer = users_map.get(v.changed_by) if v.changed_by else None
        items.append(
            KbVersionPublic(
                id=v.id,
                article_id=v.article_id,
                version=v.version,
                title=v.title,
                body=None,
                change_comment=v.change_comment,
                changed_by=KbUserRef(
                    id=changer.id, full_name=changer.full_name, avatar_url=changer.avatar_url
                )
                if changer
                else None,
                created_at=v.created_at,
            )
        )

    return KbVersionList(items=items, total=total)


@router.get(
    "/articles/{article_id}/versions/{version_number}",
    response_model=KbVersionPublic,
    summary="Детали версии статьи",
)
async def get_version(
    article_id: uuid.UUID,
    version_number: int,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbVersionPublic:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    v = await versions_repo.get_version(db, article_id=article_id, version_number=version_number)
    if not v:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    changer = None
    if v.changed_by:
        changer = await versions_repo.get_user(db, v.changed_by)

    return KbVersionPublic(
        id=v.id,
        article_id=v.article_id,
        version=v.version,
        title=v.title,
        body=v.body,
        change_comment=v.change_comment,
        changed_by=KbUserRef(
            id=changer.id, full_name=changer.full_name, avatar_url=changer.avatar_url
        )
        if changer
        else None,
        created_at=v.created_at,
    )


@router.post(
    "/articles/{article_id}/versions/{version_number}/restore",
    response_model=KbArticlePublic,
    summary="Откат к версии N",
)
async def restore_version(
    article_id: uuid.UUID,
    version_number: int,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> KbArticlePublic:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "editor", db, redis)

    if version_number == article.version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot restore to the current active version",
        )

    version_snap = await versions_repo.get_version(
        db, article_id=article_id, version_number=version_number
    )
    if not version_snap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    snapshot = KbArticleVersion(
        article_id=article.id,
        version=article.version,
        title=article.title,
        body=article.body,
        changed_by=user.id,
        change_comment=f"Откат к версии {version_number}",
    )
    db.add(snapshot)

    if version_snap.title is not None:
        article.title = version_snap.title
    if version_snap.body is not None:
        article.body = version_snap.body
    article.version += 1
    article.updated_by = user.id
    article.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(article)

    breadcrumbs = await _get_breadcrumbs(db, article.section_id)
    creator = None
    if article.created_by:
        creator = await versions_repo.get_user(db, article.created_by)
    return _article_to_public(article, breadcrumbs, creator, user)


def _compute_diff(lines1: list[str], lines2: list[str], v1: int, v2: int) -> list[str]:
    return list(
        difflib.unified_diff(
            lines1,
            lines2,
            fromfile=f"v{v1}",
            tofile=f"v{v2}",
            lineterm="",
        )
    )


@router.get("/articles/{article_id}/versions/{v1}/diff/{v2}", response_model=DiffResponse)
async def diff_versions(
    article_id: uuid.UUID,
    v1: int,
    v2: int,
    db: DbDep,
    user: CurrentUser,
    redis: RedisDep,
) -> DiffResponse:
    article = await _get_article_or_404(db, article_id)
    await require_article_permission(user, article, "viewer", db, redis)

    async def _get_body(ver: int) -> str:
        if ver == article.version:
            return article.body or ""
        ver_row = await versions_repo.get_version(db, article_id=article_id, version_number=ver)
        if ver_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {ver} not found"
            )
        return ver_row.body or ""

    body1 = await _get_body(v1)
    body2 = await _get_body(v2)

    if len(body1) > 500_000 or len(body2) > 500_000:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Версии статьи слишком велики для сравнения (максимум 500 000 символов)",
        )

    lines1 = body1.splitlines(keepends=True)
    lines2 = body2.splitlines(keepends=True)

    loop = asyncio.get_running_loop()
    diff = await loop.run_in_executor(None, _compute_diff, lines1, lines2, v1, v2)

    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    added = removed = 0

    for line in diff:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = DiffHunk(header=line.rstrip(), lines=[])
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif current_hunk is not None:
            current_hunk.lines.append(line.rstrip("\n"))
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1

    if current_hunk:
        hunks.append(current_hunk)

    return DiffResponse(hunks=hunks, stats={"added": added, "removed": removed})
