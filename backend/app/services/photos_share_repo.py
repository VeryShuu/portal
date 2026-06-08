from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photos import (
    PhotoFolder,
    PhotoFolderShareToken,
    PhotoShareToken,
)


async def list_folder_share_tokens(
    db: AsyncSession, folder_id: uuid.UUID
) -> Sequence[PhotoFolderShareToken]:
    res = await db.execute(
        select(PhotoFolderShareToken)
        .where(PhotoFolderShareToken.folder_id == folder_id)
        .order_by(PhotoFolderShareToken.created_at.desc())
    )
    return res.scalars().all()


async def list_my_photo_shares(db: AsyncSession, user_id: uuid.UUID) -> Sequence[PhotoShareToken]:
    res = await db.execute(
        select(PhotoShareToken)
        .where(
            PhotoShareToken.created_by == user_id,
            PhotoShareToken.revoked_at.is_(None),
        )
        .order_by(PhotoShareToken.created_at.desc())
    )
    return res.scalars().all()


async def list_my_folder_shares(db: AsyncSession, user_id: uuid.UUID) -> Sequence[Any]:
    res = await db.execute(
        select(PhotoFolderShareToken, PhotoFolder.name)
        .join(PhotoFolder, PhotoFolderShareToken.folder_id == PhotoFolder.id)
        .where(
            PhotoFolderShareToken.created_by == user_id,
            PhotoFolderShareToken.revoked_at.is_(None),
        )
        .order_by(PhotoFolderShareToken.created_at.desc())
    )
    return res.all()


async def get_photo_share_token(db: AsyncSession, token_id: uuid.UUID) -> PhotoShareToken | None:
    tok: PhotoShareToken | None = await db.scalar(
        select(PhotoShareToken).where(PhotoShareToken.id == token_id)
    )
    return tok


async def get_folder_share_token(
    db: AsyncSession, token_id: uuid.UUID
) -> PhotoFolderShareToken | None:
    tok: PhotoFolderShareToken | None = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.id == token_id)
    )
    return tok


async def fetch_photo_share_token_by_token(db: AsyncSession, token: str) -> PhotoShareToken | None:
    res = await db.execute(select(PhotoShareToken).where(PhotoShareToken.token == token))
    return res.scalar_one_or_none()


async def scalar_folder_share_token_by_token(
    db: AsyncSession, token: str
) -> PhotoFolderShareToken | None:
    tok: PhotoFolderShareToken | None = await db.scalar(
        select(PhotoFolderShareToken).where(PhotoFolderShareToken.token == token)
    )
    return tok
