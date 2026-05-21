"""News service package.

Раньше — монолитный ``app/services/news.py`` (522 строки). Разложен
на подмодули по ответственности (см. ref.md, пункт 3.1):

- :mod:`._helpers` — константы, ``_build_cover_variants``,
  ``_remove_cover_variants``, ``_targeting_filter``.
- :mod:`.crud` — CRUD-операции и работа с версиями.
- :mod:`.cover` — загрузка / удаление обложки + responsive-варианты.
- :mod:`.gallery` — изображения галереи.
- :mod:`.attachments` — произвольные вложения.

Все публичные имена реэкспортированы из пакета — внешние импорты
``from app.services.news import X`` остаются совместимыми.
"""

from __future__ import annotations

from ._helpers import (
    _CONTENT_TYPE_TO_EXT,
    _NEWS_COVER_QUALITY,
    _NEWS_MEDIA_DIR,
    NEWS_COVER_VARIANT_WIDTHS,
    _build_cover_variants,
    _remove_cover_variants,
    _targeting_filter,
    logger,
)
from .attachments import delete_attachment, upload_attachment
from .cover import delete_cover, upload_cover
from .crud import (
    create_news,
    delete_news,
    get_news_by_id,
    get_news_list,
    get_news_versions,
    get_trash_news,
    increment_view_count,
    purge_news,
    restore_news,
    update_news,
)
from .gallery import delete_gallery_image, upload_gallery_image
from .poll import (
    get_poll_by_news_id,
    build_poll_public_response,
    create_poll,
    update_poll,
    delete_poll,
    close_poll,
    reopen_poll,
    cast_vote,
    revoke_vote,
    get_voters_list,
    is_poll_closed,
)

__all__ = [
    "NEWS_COVER_VARIANT_WIDTHS",
    "_CONTENT_TYPE_TO_EXT",
    "_NEWS_COVER_QUALITY",
    "_NEWS_MEDIA_DIR",
    "_build_cover_variants",
    "_remove_cover_variants",
    "_targeting_filter",
    "create_news",
    "delete_attachment",
    "delete_cover",
    "delete_gallery_image",
    "delete_news",
    "get_news_by_id",
    "get_news_list",
    "get_news_versions",
    "get_trash_news",
    "increment_view_count",
    "logger",
    "purge_news",
    "restore_news",
    "update_news",
    "upload_attachment",
    "upload_cover",
    "upload_gallery_image",
    "get_poll_by_news_id",
    "build_poll_public_response",
    "create_poll",
    "update_poll",
    "delete_poll",
    "close_poll",
    "reopen_poll",
    "cast_vote",
    "revoke_vote",
    "get_voters_list",
    "is_poll_closed",
]
