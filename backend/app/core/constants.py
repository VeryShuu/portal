PERM_VIEWER = "viewer"
IDEMPOTENCY_TTL = 86400
PERM_EDITOR = "editor"
PERM_MANAGER = "manager"
PERM_UPLOADER = "uploader"
VIEW_DEDUP_TTL_SECONDS = 3600

MAX_BULK_FILES = 100
BULK_INFLIGHT_TTL = 60

ALLOWED_AVATAR_IMG_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_NEWS_COVER_IMG_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)

# ── Helpdesk runtime parameters (docs/helpdesk.md §11) ──────────────────────
# Константы, а не SystemSettings: операционные окна меняются редко, а перенос в
# system_config требует правок 3-4 Pydantic-классов + Admin UI + фронта.
HELPDESK_MAX_ATTACHMENT_MB = 25
HELPDESK_MAX_TOTAL_INGRESS_MB = 50
HELPDESK_ARCHIVE_AFTER_DAYS = 14
HELPDESK_ARCHIVE_FILES_TTL_DAYS = 180
HELPDESK_REOPEN_WINDOW_DAYS = 7

# Локальное хранение вложений (по образцу feedback — /data/feedback/files/).
# Папка тикета: HELPDESK_FILES_DIR / f"TKT-{number}" / filename.
from pathlib import Path  # noqa: E402

HELPDESK_FILES_DIR: Path = Path("/data/helpdesk")
HELPDESK_ATTACHMENT_ALLOWED_MIMES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/zip",
        "application/x-zip-compressed",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
    }
)
# Inline-картинки rich-редактора ответов (POST /tickets/{id}/inline-media).
# Уже входит в HELPDESK_ATTACHMENT_ALLOWED_MIMES как подмножество, но вынесено
# отдельно: редактор грузит только растровые форматы (без SVG — XSS через
# <script> в SVG; без документов). Лимит — HELPDESK_MAX_ATTACHMENT_MB.
HELPDESK_INLINE_IMAGE_MIMES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)
