"""Имена photo-folder'ов: разрешение коллизий slug и FS-сегмента.

Чистые функции без зависимостей от FastAPI/HTTP — выделены из
``app.api.photos.folder_service`` чтобы worker (см.
``app.worker.tasks.photos.import_scan``) не зависел от API-слоя
(см. audit [H5]: цикл worker → api → fastapi.HTTPException/deps удлинял
cold-start воркера и нарушал слоистость).

API-слой (``folder_service``) импортирует эти функции отсюда; поведение 1:1.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import photos_folder_repo as folder_repo
from app.services import photos_storage


def _slugify(text_: str) -> str:
    """ASCII-нормализация строки в URL-safe slug.

    Локальная копия ``app.api.photos._common._slugify`` (перенос вместе с
    функциями именования, чтобы не тянуть api-зависимости в worker).
    """
    norm = unicodedata.normalize("NFKD", text_).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", norm).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "folder"


async def resolve_unique_slug(
    db: AsyncSession,
    *,
    base_name: str,
    parent_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None = None,
) -> str:
    base_slug = _slugify(base_name)
    slug = base_slug
    i = 1
    while True:
        if not await folder_repo.count_siblings_with_slug(
            db, parent_id=parent_id, slug=slug, exclude_id=exclude_id
        ):
            return slug
        i += 1
        slug = f"{base_slug}-{i}"
        if i > 9999:
            return f"{base_slug}-{uuid.uuid4().hex[:8]}"


async def resolve_unique_fs_seg(
    db: AsyncSession,
    *,
    name: str,
    parent_id: uuid.UUID | None,
    exclude_id: uuid.UUID | None = None,
) -> str:
    fs_seg = photos_storage.sanitize_folder_name(name)
    base_seg = fs_seg
    used_segs = await folder_repo.fetch_sibling_fs_segments(
        db, parent_id=parent_id, exclude_id=exclude_id
    )
    j = 2
    while fs_seg in used_segs:
        fs_seg = f"{base_seg} ({j})"
        j += 1
        if j > 9999:
            return f"{base_seg}-{uuid.uuid4().hex[:8]}"
    return fs_seg
