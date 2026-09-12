PERM_VIEWER = "viewer"
IDEMPOTENCY_TTL = 86400
PERM_EDITOR = "editor"
PERM_MANAGER = "manager"
PERM_UPLOADER = "uploader"
VIEW_DEDUP_TTL_SECONDS = 3600

MAX_BULK_FILES = 100
BULK_INFLIGHT_TTL = 60

# Redis-кеш сводного дашборда аналитики (audit L2): 5 SQL, включая distinct-scan
# по партициям audit_log, на каждый запрос. Дашборд — статистика для админов,
# устаревание на TTL не критично; кешируется целиком по параметру ``days``.
ANALYTICS_DASHBOARD_CACHE_TTL_SECONDS = 600

ALLOWED_AVATAR_IMG_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_NEWS_COVER_IMG_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)

# Дефолт списка доверенных видеохостингов для встраивания в iframe (rich-контент
# новостей/БЗ и материалы модуля обучения). Это ЗНАЧЕНИЕ ПО УМОЛЧАНИЮ runtime-
# настройки ``system.json → video_iframe_origins`` (Admin UI → System, ADR-037):
# админ управляет списком без деплоя, CSP (frame-src) подхватывает его через
# nginx-sidecar автоматически. Константа используется как default схемы и
# fallback в render-config.sh — держать эти два места равными (тест
# test_video_iframe_origins_default_matches_sidecar не даёт разъехаться).
# iframe исполняет сторонний контент в браузере пользователя — список обязан
# оставаться минимальным; ссылки-оригиналы в embed-URL переводит
# фронтовый utils/videoEmbed.ts (известные провайдеры — код, не настройка).
DEFAULT_VIDEO_IFRAME_ORIGINS: tuple[str, ...] = (
    "https://video.mage.ru",
    "https://www.youtube-nocookie.com",
    "https://rutube.ru",
    "https://vk.com",
    "https://vkvideo.ru",
    "https://player.vimeo.com",
)

# ── Helpdesk runtime parameters (docs/helpdesk.md §11) ──────────────────────
# Константы, а не SystemSettings: операционные окна меняются редко, а перенос в
# system_config требует правок 3-4 Pydantic-классов + Admin UI + фронта.
HELPDESK_MAX_ATTACHMENT_MB = 25
HELPDESK_MAX_TOTAL_INGRESS_MB = 50
# Агентский ответ уходит по SMTP: base64 увеличивает размер файлов примерно на
# треть. Ограничиваем именно сумму исходящих файлов, чтобы итоговое письмо не
# упиралось в типичные лимиты почтовых шлюзов 20–25 MiB.
HELPDESK_MAX_TOTAL_OUTBOUND_MB = 15
HELPDESK_ARCHIVE_AFTER_DAYS = 14
HELPDESK_ARCHIVE_BATCH_SIZE = 100
HELPDESK_REOPEN_WINDOW_DAYS = 7
# Draft-attachments (inline-картинки в форме создания заявки — нет ticket_id до
# сохранения, см. ``services/helpdesk/drafts.py``). TTL — сколько неотправленный
# черновик живёт на диске до очистки cron'ом ``cleanup_expired_drafts``.
# Лимит активных draft-файлов на юзера — anti-abuse (старые нужно удалить вручную
# через повторную отправку или дождаться TTL). Период полужизни типового
# заполнения формы — часы/день, поэтому 24 часа покрывают обед/ночь/выходные.
HELPDESK_DRAFT_TTL_HOURS = 24
HELPDESK_DRAFT_MAX_PER_USER = 20

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
        # Bounce/forward-вложения (письма-уведомления о недоставке и пересланные
        # сообщения): ``message/delivery-status`` (Postfix NDN), ``message/rfc822``
        # (вложенные заголовки/тела писем — magic так определяет ``text/rfc822-headers``
        # и ``message/rfc822``-части из bounce). См. helpdesk IMAP-ingress.
        "message/rfc822",
        "message/delivery-status",
    }
)
# Inline-картинки rich-редактора ответов (POST /tickets/{id}/inline-media).
# Уже входит в HELPDESK_ATTACHMENT_ALLOWED_MIMES как подмножество, но вынесено
# отдельно: редактор грузит только растровые форматы (без SVG — XSS через
# <script> в SVG; без документов). Лимит — HELPDESK_MAX_ATTACHMENT_MB.
HELPDESK_INLINE_IMAGE_MIMES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)

# ── Email outbox / диспетчеризация (docs/email.md) ──────────────────────────
# Параметры cron'а process_email_outbox. Вынесены из worker/tasks/email_outbox.py
# в централизованный реестр (audit [M10]) — раньше были захардкожены в воркере.
# BATCH_SIZE — сколько PENDING-писем за один claim (FOR UPDATE SKIP LOCKED).
# STALE_SENDING_TIMEOUT — через сколько секунд SENDING-письмо считается
# зависшим (воркер упал во время SMTP) и перевыделяется watchdog'ом.
EMAIL_OUTBOX_DISPATCH_BATCH_SIZE = 20
EMAIL_OUTBOX_STALE_SENDING_TIMEOUT_SECONDS = 600

# ── Observability: SSE-стрим уведомлений ────────────────────────────────────
# Долгоживущее соединение (~60 c на реконнект): его «длительность» — время
# жизни соединения, а не латентность обработки. Поэтому стрим исключается из
# latency-гистограммы (middleware/metrics.py) и из nginx access-лога для 2xx
# (system_data/nginx/nginx.conf) — иначе каждый реконнект выглядит «медленным
# запросом» и забивает p99-панели/Loki. Счётчик запросов и ошибки (429/5xx)
# логируются как обычно.
NOTIFICATIONS_STREAM_PATH = "/api/v1/notifications/stream"
