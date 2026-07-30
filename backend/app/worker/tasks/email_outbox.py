"""ARQ-задачи для transactional email outbox.

`process_email_outbox` — основной диспетчер, запускается каждые несколько секунд:
   1. Атомарно захватывает PENDING-записи (FOR UPDATE SKIP LOCKED).
   2. Для каждой строит MIME и шлёт через aiosmtplib.
   3. По результату обновляет outbox-строку (SENT / PENDING+next_attempt_at / DLQ).

`cleanup_email_outbox` — раз в сутки чистит старые SENT записи.
"""

from __future__ import annotations

import base64
import re
import secrets
import uuid
from contextlib import suppress
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

import aiofiles
from redis.asyncio import Redis

from app.core.constants import (
    EMAIL_OUTBOX_DISPATCH_BATCH_SIZE as DISPATCH_BATCH_SIZE,
)
from app.core.constants import (
    EMAIL_OUTBOX_STALE_SENDING_TIMEOUT_SECONDS as STALE_SENDING_TIMEOUT_SECONDS,
)
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.email_outbox import (
    KIND_HELPDESK,
    KIND_MEETING,
    claim_pending,
    cleanup_old_sent,
    decode_ical_bytes,
    mark_failed,
    mark_sent,
    requeue_stale_sending,
)
from app.worker.tasks.email_utils import (
    classify_smtp_error,
    load_helpdesk_smtp_config,
    load_smtp_config,
    smtp_send,
)

logger = get_logger(__name__)

# Параметры диспетчеризации вынесены в централизованный реестр констант
# (audit [M10]): когда понадобиться tuning без redeploy, можно вынести в
# SystemSettings. Выше — re-export под короткими именами для обратной
# совместимости с остальным кодом модуля.

# Distributed lock для watchdog-фазы (audit [L4]): requeue_stale_sending делает
# массовый UPDATE по WHERE status='SENDING' AND updated_at<... БЕЗ SKIP LOCKED.
# Если два воркера одновременно запустят диспетчер (рестарт пула, deploy),
# оба выполнят UPDATE по одним строкам. Lock по образцу messenger_outbox /
# helpdesk.poll_lock защищает от этой race.
EMAIL_OUTBOX_LOCK_KEY = "email:outbox:dispatch:lock"
# 3 минуты: batch до 20 писем × SMTP timeout ~5s = ~100s worst case + overhead.
EMAIL_OUTBOX_LOCK_TTL = 180

_LOCK_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) "
    "else return 0 end"
)


async def _acquire_lock(redis: Redis, key: str, ttl: int) -> str | None:
    """Тот же паттерн, что в ``app.worker.tasks.helpdesk._acquire_lock``."""
    token = secrets.token_hex(16)
    acquired = await redis.set(key, token, nx=True, ex=ttl)
    if not acquired:
        return None
    return token


async def _release_lock(redis: Redis, key: str, token: str) -> None:
    with suppress(Exception):
        # ``redis.asyncio.Redis.eval`` асинхронен, но в stub'е redis-py имеет
        # перегрузку, возвращающую ``Awaitable[str] | str`` → mypy-error на
        # ``await`` (см. ``tasks/helpdesk.py:_release_lock``).
        await redis.eval(_LOCK_RELEASE_LUA, 1, key, token)  # type: ignore[misc]  # redis-py async-overload typing


async def process_email_outbox(ctx: dict) -> int:
    """Обрабатывает очередную пачку PENDING писем. Возвращает кол-во отправленных."""
    sent_ok = 0
    # Distributed lock на всю диспетчеризацию (audit [L4]): watchdog-фаза
    # ``requeue_stale_sending`` делает массовый UPDATE без SKIP LOCKED — без
    # lock два одновременно стартовавших воркера (рестарт пула, deploy)
    # выполнят UPDATE по одним строкам. claim_pending защищён SKIP LOCKED,
    # но watchdog — нет. Lock живёт EMAIL_OUTBOX_LOCK_TTL (180s), чтобы
    # пережить worst-case batch (20 писем × SMTP timeout ~5s).
    redis = ctx.get("redis")
    if redis is None:
        logger.warning("email_outbox.no_redis_in_context")
        return 0
    lock_token = await _acquire_lock(redis, EMAIL_OUTBOX_LOCK_KEY, EMAIL_OUTBOX_LOCK_TTL)
    if lock_token is None:
        # Другой воркер уже обрабатывает батч — пропускаем этот tick.
        return 0
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await requeue_stale_sending(
                    session, older_than_seconds=STALE_SENDING_TIMEOUT_SECONDS
                )
                claimed = await claim_pending(session, limit=DISPATCH_BATCH_SIZE)
            if not claimed:
                return 0

            cfg = load_smtp_config()
            # Собственный SMTP-контур helpdesk (миграция 086): если настроен,
            # helpdesk-почта уходит с support-ящика, а не с общего порталного SMTP.
            # Грузим один раз за batch (read-only запрос к singleton-строке).
            helpdesk_cfg = await load_helpdesk_smtp_config()
            smtp_configured = bool(cfg.get("host")) or helpdesk_cfg is not None
            if not smtp_configured:
                logger.warning("email_outbox.dispatch.smtp_not_configured", claimed=len(claimed))

            for row in claimed:
                # Маршрутизация: helpdesk-строка (kind=helpdesk ИЛИ generic с
                # маркером smtp_source=helpdesk — письма агентам) → собственный SMTP
                # при наличии; иначе общий порталный SMTP (fallback).
                row_cfg = _cfg_for_row(row, cfg, helpdesk_cfg)
                if not row_cfg.get("host"):
                    async with session.begin():
                        await mark_failed(
                            session,
                            row["id"],
                            error="SMTP host is not configured",
                            error_type="ConfigurationError",
                            error_class="transient",
                            current_attempts=row["attempts"],
                            max_attempts=row["max_attempts"],
                        )
                    continue

                try:
                    # helpdesk-ветка: async, т.к. вложения читаются с локального
                    # диска через aiofiles (существующий _build_mime синхронный).
                    if row["kind"] == KIND_HELPDESK:
                        msg = await _build_helpdesk_mime(row, row_cfg)
                    else:
                        msg = _build_mime(row, row_cfg)
                    await smtp_send(msg, row_cfg)
                except Exception as exc:
                    error_class = classify_smtp_error(exc)
                    error_type = type(exc).__name__
                    logger.exception(
                        "email_outbox.send_failed",
                        outbox_id=str(row["id"]),
                        kind=row["kind"],
                        to=row["to_email"],
                        error=str(exc),
                        error_type=error_type,
                        error_class=error_class,
                        attempts=row["attempts"],
                    )
                    async with session.begin():
                        await mark_failed(
                            session,
                            row["id"],
                            error=str(exc),
                            error_type=error_type,
                            error_class=error_class,
                            current_attempts=row["attempts"],
                            max_attempts=row["max_attempts"],
                        )
                    continue

                async with session.begin():
                    await mark_sent(session, row["id"])
                sent_ok += 1
                logger.info(
                    "email_outbox.sent",
                    outbox_id=str(row["id"]),
                    kind=row["kind"],
                    to=row["to_email"],
                )
    except Exception as exc:
        logger.exception("email_outbox.dispatch_failed", error=str(exc))
    finally:
        await _release_lock(redis, EMAIL_OUTBOX_LOCK_KEY, lock_token)
    return sent_ok


async def cleanup_email_outbox(ctx: dict) -> int:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            deleted = await cleanup_old_sent(session, older_than_days=30)
        logger.info("email_outbox.cleanup", deleted=deleted)
        return deleted


def _is_helpdesk_outbound(row: dict) -> bool:
    """Принадлежит ли outbox-строка контуру helpdesk (собственный SMTP, 086).

    Два пути распознавания:

    * ``kind=helpdesk`` — ответы заявителю, уведомления о назначении/создании
      (продюсеры в ``services/helpdesk/outbound.py``);
    * ``kind=generic`` c ``payload.smtp_source == "helpdesk"`` — внутренние
      письма агентам (digest-сводка и уведомление о новой заявке; продюсеры в
      ``services/helpdesk/digest.py`` и ``notifications.py``). Маркер нужен,
      потому что ``claim_pending`` не возвращает ``related_resource_type``, а
      отличить generic-от-helpdesk от generic-от-news/meetings иначе нельзя.
    """
    if row["kind"] == KIND_HELPDESK:
        return True
    payload = row.get("payload") or {}
    return payload.get("smtp_source") == "helpdesk"


def _cfg_for_row(row: dict, portal_cfg: dict, helpdesk_cfg: dict | None) -> dict:
    """Выбрать SMTP-cfg для строки: helpdesk → собственный, иначе порталный.

    Если строка принадлежит контуру helpdesk, но собственный SMTP не настроен
    (``helpdesk_cfg is None``) — fallback на общий порталный cfg (backward-
    compatible: helpdesk-почта продолжает уходить, как до миграции 086). Логируем
    warning для наблюдаемости — админ видит, что письма идут не с support-ящика.
    """
    if _is_helpdesk_outbound(row):
        if helpdesk_cfg is not None:
            return helpdesk_cfg
        logger.warning(
            "email_outbox.helpdesk_smtp_fallback",
            outbox_id=str(row["id"]),
            kind=row["kind"],
            reason="helpdesk SMTP not configured, falling back to portal-wide SMTP",
        )
    return portal_cfg


def _sanitize_header(value: str) -> str:
    """Удаляет CR/LF из значения MIME-заголовка (защита от header injection, E3).

    Subject/To берутся из данных БД (`news_title`, `booking.title`), которые
    может контролировать пользователь. На политике ``compat32`` присвоение
    ``msg["Subject"] = value`` НЕ фильтрует переводы строк, поэтому
    ``"тема\\r\\nBcc: victim@x"`` инъектировала бы скрытого получателя или
    лишние заголовки. Схлопываем любые CR/LF в пробел.
    """
    if not value:
        return value
    return value.replace("\r", " ").replace("\n", " ")


def _build_mime(row: dict, cfg: dict) -> MIMEMultipart:
    kind = row["kind"]
    to_email = _sanitize_header(row["to_email"])
    subject = _sanitize_header(row["subject"])
    from_address = _sanitize_header(cfg["from_address"] or "portal@company.local")
    body_html = row["body_html"] or ""
    body_text = row["body_text"]
    payload = row["payload"] or {}

    if kind == KIND_MEETING:
        outer = MIMEMultipart("mixed")
        outer["Subject"] = subject
        outer["From"] = from_address
        outer["To"] = to_email
        outer["Content-Class"] = "urn:content-classes:calendarmessage"

        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(body_html, "html", "utf-8"))

        ical_b64 = payload.get("ical_b64") or ""
        method = payload.get("method") or "REQUEST"
        if ical_b64:
            ical_bytes = decode_ical_bytes(ical_b64)
            ical_inline = MIMEText(ical_bytes.decode("utf-8"), "calendar", "utf-8")
            ical_inline.set_param("method", method)
            ical_inline.set_param("charset", "UTF-8")
            alternative.attach(ical_inline)

        outer.attach(alternative)
        return outer

    alternative = MIMEMultipart("alternative")
    if body_text:
        alternative.attach(MIMEText(body_text, "plain", "utf-8"))
    alternative.attach(MIMEText(body_html, "html", "utf-8"))

    inline_images = payload.get("inline_images") or []
    if inline_images:
        related = MIMEMultipart("related")
        related["Subject"] = subject
        related["From"] = from_address
        related["To"] = to_email
        related.attach(alternative)
        for img in inline_images:
            _attach_inline_image(related, img)
        return related

    alternative["Subject"] = subject
    alternative["From"] = from_address
    alternative["To"] = to_email
    return alternative


# Regex для поиска inline-картинок rich-редактора в body_html helpdesk-письма.
# URL бывает двух видов (см. _absolutize_img_src в email_template.py):
#   относительный:  src="/api/v1/helpdesk/tickets/{uuid}/inline-media/{file}"
#   абсолютный:     src="https://portal.local/api/v1/helpdesk/tickets/{uuid}/inline-media/{file}"
# Поэтому матчим с optional scheme://host перед /api/v1. filename = {uuid8}_{safe_name}
# (см. media.py — только [\w.-]). Группа 1 = полный path (без scheme/host),
# группа 2 = filename. Используем (?P<scheme>...) чтобы сохранить позицию для замены.
_INLINE_IMG_SRC_RE = re.compile(
    r'src="(?:https?://[^/"]+)?(/api/v1/helpdesk/tickets/[0-9a-fA-F-]+/inline-media/([\w.\-]+))"',
    re.IGNORECASE,
)

# Regex для картинок из истории переписки — локализованные email-attachments
# (картинки, сохранённые из входящих писем заявителя через email_images.py).
# URL тот же префикс, но путь ``/api/v1/helpdesk/attachments/{uuid}``. Группа 1 =
# полный path (для замены), группа 2 = attachment UUID (для DB-lookup).
# ``\b`` перед UUID — защита от частичных матчей в более длинных строках.
_ATTACHMENT_IMG_SRC_RE = re.compile(
    r'src="(?:https?://[^/"]+)?(/api/v1/helpdesk/attachments/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}))"',
    re.IGNORECASE,
)

# Поддерживаемые inline-форматы → MIME-подтип для MIMEImage.
_INLINE_MIME_BY_EXT = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".gif": "gif",
    ".webp": "webp",
}


async def _embed_helpdesk_inline_images(
    body_html: str, ticket_number: int
) -> tuple[str, list[dict]]:
    """Встроить inline-картинки rich-редактора в HTML как ``cid:``-attach.

    Находит все ``<img src="/api/v1/helpdesk/tickets/{id}/inline-media/{file}">``
    в ``body_html``, читает файлы с диска (``HELPDESK_FILES_DIR / TKT-{n} /
    inline / {file}``), генерирует ``Content-ID`` (cid) и переписывает ``src``
    на ``cid:{token}``. Возвращает ``(html_with_cid, inline_images)`` где
    ``inline_images`` — список ``{cid, b64, mime}`` для ``_attach_inline_image``.

    Best-effort: если файл не найден / не читается / не поддерживаемый формат —
    ``src`` остаётся относительным (в веб-ленте портала картинка всё равно
    видна; в почтовом клиенте будет placeholder, но письмо не роняется).
    """
    import aiofiles

    from app.core.constants import HELPDESK_FILES_DIR

    if not body_html:
        return body_html, []

    # 1-й проход: находим уникальные inline-картинки (дедуп по original_src).
    # filename в URL уникален → ключ по нему. Сохраняем original_src для отката.
    found: dict[str, dict] = {}  # filename → {original_src, ext_key}
    for match in _INLINE_IMG_SRC_RE.finditer(body_html):
        original_src, filename = match.group(1), match.group(2)
        if filename in found:
            continue
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        if ext not in _INLINE_MIME_BY_EXT:
            continue  # неподдерживаемый формат — пропускаем (src останется как есть)
        found[filename] = {"original_src": original_src, "ext_key": ext}

    if not found:
        return body_html, []

    # 2-й проход: читаем файлы с диска, строим mapping original_src → cid.
    # Недоступные файлы — пропускаем (их src не переписывается, остаётся URL).
    inline_dir = HELPDESK_FILES_DIR / f"TKT-{ticket_number}" / "inline"
    src_to_cid: dict[str, str] = {}
    inline_images: list[dict] = []
    for filename, meta in found.items():
        disk_path = inline_dir / filename
        try:
            async with aiofiles.open(disk_path, "rb") as f:
                data = await f.read()
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "helpdesk.inline_image.missing_for_email",
                filename=filename,
                ticket_number=ticket_number,
                error=str(exc),
            )
            continue
        cid = f"img-{uuid.uuid4().hex[:12]}"
        src_to_cid[meta["original_src"]] = cid
        inline_images.append(
            {
                "cid": cid,
                "b64": base64.b64encode(data).decode("ascii"),
                "mime": f"image/{_INLINE_MIME_BY_EXT[meta['ext_key']]}",
            }
        )

    if not src_to_cid:
        return body_html, []

    # 3-й проход: заменяем src на cid для всех найденных (читаемых) картинок.
    def _replace_src(match: re.Match[str]) -> str:
        cid = src_to_cid.get(match.group(1))
        return f'src="cid:{cid}"' if cid else match.group(0)

    html_with_cid = _INLINE_IMG_SRC_RE.sub(_replace_src, body_html)
    return html_with_cid, inline_images


async def _embed_helpdesk_attachment_images(
    body_html: str, ticket_number: int
) -> tuple[str, list[dict]]:
    """Встроить картинки из истории переписки как ``cid:``-attach.

    Картинки в истории (блок ``build_thread_history``) бывают двух видов:
    * rich-редактор агента — обрабатываются :func:`_embed_helpdesk_inline_images`
      (``/api/v1/helpdesk/tickets/{id}/inline-media/{file}``).
    * локализованные email-attachments — **вот они**: входящие письма заявителя
      с inline ``cid:`` (или внешними http) картинками, сохранённые в
      ``helpdesk_attachments`` через ``email_images.py`` при ingress. В
      ``body_html`` их ``src`` указывает на ``/api/v1/helpdesk/attachments/{id}``
      (требует session-cookie на чтение — почтовый клиент НЕ передаёт cookie).

    Эта функция находит все такие ссылки, одним DB-запросом подтягивает метаданные
    (``filename``, ``content_type``), фильтрует по ``image/*`` (не-картинки —
    пропускаем: PDF-вложение в ``<img>`` всё равно не отрендерится), читает
    файлы с диска (``/data/helpdesk/TKT-{n}/{filename}``) и возвращает
    ``(html, inline_images)`` в том же формате, что и
    :func:`_embed_helpdesk_inline_images` — для совместимости с
    :func:`_attach_inline_image`.

    Best-effort: отсутствующие в БД attachment-ids / не-читаемые файлы /
    не-поддерживаемые форматы → ``src`` остаётся (веб-лента портала картинку
    видит, письмо роняться не должно).
    """
    import aiofiles
    from sqlalchemy import select

    from app.core.constants import HELPDESK_FILES_DIR
    from app.models.helpdesk import HelpdeskAttachment

    if not body_html:
        return body_html, []

    # 1-й проход: собираем уникальные attachment-ids из HTML.
    # Группа 1 = полный path (для замены), группа 2 = UUID.
    found_src_by_id: dict[str, str] = {}  # uuid_str → original_src_path
    for match in _ATTACHMENT_IMG_SRC_RE.finditer(body_html):
        att_id_str = match.group(2)
        if att_id_str not in found_src_by_id:
            found_src_by_id[att_id_str] = match.group(1)

    if not found_src_by_id:
        return body_html, []

    # 2-й проход: один DB-запрос по всем id (защита от N+1). Фильтруем по
    # ``image/*`` (остальные — PDF/DOCX — не ``<img>``-встраиваемые).
    att_ids: list[uuid.UUID] = []
    for aid in found_src_by_id:
        try:
            att_ids.append(uuid.UUID(aid))
        except ValueError:
            continue  # битый UUID в URL — пропускаем (regex уже фильтрует, но defence-in-depth)

    if not att_ids:
        return body_html, []

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(
                HelpdeskAttachment.id,
                HelpdeskAttachment.filename,
                HelpdeskAttachment.content_type,
            ).where(HelpdeskAttachment.id.in_(att_ids))
        )
        rows = res.all()

    # Поддерживаемые форматы (те же, что у inline-media — mime-маппинг одинаковый).
    # Используем content_type из БД (он определяется через python-magic, точнее,
    # чем расширение имени — attachments из email могут прийти без расширения).
    supported_mime_suffixes = {"jpeg", "png", "gif", "webp"}
    src_to_cid: dict[str, str] = {}
    inline_images: list[dict] = []
    ticket_dir = HELPDESK_FILES_DIR / f"TKT-{ticket_number}"
    for att_id, filename, content_type in rows:
        ct = (content_type or "").lower()
        # ``image/png`` → ``png``, ``image/jpeg`` → ``jpeg`` и т.д.
        mime_suffix = ct.split("/", 1)[1] if "/" in ct else ""
        if mime_suffix not in supported_mime_suffixes:
            # PDF/DOCX/нестандартные — пропускаем (в письмо пойдут как обычные
            # attachment, не cid — в ``<img>`` они всё равно не отрендерятся).
            continue
        src_path = found_src_by_id.get(str(att_id))
        if not src_path:
            continue
        disk_path = ticket_dir / (filename or "")
        try:
            async with aiofiles.open(disk_path, "rb") as f:
                data = await f.read()
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "helpdesk.attachment_image.missing_for_email",
                attachment_id=str(att_id),
                filename=filename,
                ticket_number=ticket_number,
                error=str(exc),
            )
            continue
        cid = f"img-{uuid.uuid4().hex[:12]}"
        src_to_cid[src_path] = cid
        inline_images.append(
            {
                "cid": cid,
                "b64": base64.b64encode(data).decode("ascii"),
                "mime": f"image/{mime_suffix}",
            }
        )

    if not src_to_cid:
        return body_html, []

    # 3-й проход: заменяем src на cid для найденных (читаемых) картинок.
    def _replace_src(match: re.Match[str]) -> str:
        cid = src_to_cid.get(match.group(1))
        return f'src="cid:{cid}"' if cid else match.group(0)

    html_with_cid = _ATTACHMENT_IMG_SRC_RE.sub(_replace_src, body_html)
    return html_with_cid, inline_images


_DEFAULT_FROM_ADDRESS = "portal@company.local"


def _resolve_helpdesk_reply_to(payload: dict, cfg: dict) -> str:
    """Чистый адрес ящика из настроек (без plus-addressing).

    Матчинг входящих ответов идёт по ``In-Reply-To`` / ``References`` и токену
    ``[#TKT-{number}]`` в теме — plus-маркер в ``Reply-To`` для этого не нужен
    и ломал доставку на ящиках, где local-part ≠ ``support`` (напр. при
    ``portal@domain`` ответ уходил на несуществующий ``support+TKT-N@domain``).
    """
    return _sanitize_header(
        (payload.get("support_address") or "").strip()
        or cfg.get("from_address")
        or _DEFAULT_FROM_ADDRESS
    )


def _build_helpdesk_body_root(body_text: str, body_html: str, inline_images: list) -> MIMEMultipart:
    """Тело письма: ``multipart/alternative`` (plain + html), при наличии
    inline-картинок rich-редактора оборачивается в ``multipart/related``.

    HTML ссылается на картинки через ``cid:``, сами картинки идут как related-части
    (Content-ID) — заявитель видит их прямо в почтовом клиенте.
    """
    alternative = MIMEMultipart("alternative")
    if body_text:
        alternative.attach(MIMEText(body_text, "plain", "utf-8"))
    alternative.attach(MIMEText(body_html, "html", "utf-8"))

    if not inline_images:
        return alternative

    body_root: MIMEMultipart = MIMEMultipart("related")
    body_root.attach(alternative)
    for img in inline_images:
        _attach_inline_image(body_root, img)
    return body_root


async def _read_helpdesk_attachment(ticket_number: int, att_meta: dict) -> MIMEBase:
    """Читает файл вложения с диска (aiofiles) и собирает MIME-часть.

    Вложения лежат в ``/data/helpdesk/TKT-{number}/{file}``; их содержимое НЕ
    лежит в JSONB ``payload`` — только метаданные (filename/original_name/content_type).
    """
    from app.core.constants import HELPDESK_FILES_DIR

    filename = att_meta.get("filename") or ""
    content_type = att_meta.get("content_type") or "application/octet-stream"
    original_name = att_meta.get("original_name") or filename
    disk_path = HELPDESK_FILES_DIR / f"TKT-{ticket_number}" / filename
    async with aiofiles.open(disk_path, "rb") as f:
        data = await f.read()
    maintype, _, subtype = content_type.partition("/")
    part = MIMEBase(maintype or "application", subtype or "octet-stream")
    part.set_payload(data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=original_name)
    return part


def _apply_helpdesk_headers(
    outer: MIMEMultipart,
    *,
    subject: str,
    from_address: str,
    to_email: str,
    reply_to_address: str,
    payload: dict,
) -> None:
    """Канонические заголовки на корневую часть (ТЗ §1.3.3/§5.2).

    Subject, From, To, Date, Message-ID, In-Reply-To, References, Reply-To, Cc —
    все проходят через ``_sanitize_header`` (защита от CRLF-injection, ТЗ H-4).
    """
    outer["Subject"] = subject
    outer["From"] = from_address
    outer["To"] = to_email
    outer["Date"] = formatdate(localtime=True)
    message_id_header = payload.get("message_id_header")
    if message_id_header:
        outer["Message-ID"] = _sanitize_header(message_id_header)
    in_reply_to = payload.get("in_reply_to")
    if in_reply_to:
        outer["In-Reply-To"] = _sanitize_header(in_reply_to)
    references = payload.get("references") or []
    if references:
        outer["References"] = _sanitize_header(" ".join(references))
    outer["Reply-To"] = reply_to_address
    # Cc («ответить всем», миграция 083): ставится только если агент явно включил
    # чекбокс и добавил получателей в форме ответа. ``formataddr`` корректно
    # оформляет ``Name <a@x>``; голый email — без угловых скобок. Каждый адрес
    # санизируется повторно (defense-in-depth: продюсер уже стрипал, но
    # outbox-payload мог быть изменён вручную в БД).
    cc_header = _format_cc_header(payload.get("cc") or [])
    if cc_header:
        outer["Cc"] = _sanitize_header(cc_header)


def _format_cc_header(cc: list) -> str:
    """Собрать значение заголовка ``Cc`` из списка участников.

    Принимает ``list[CcRecipient | dict]`` — Pydantic-модели (новый код, audit
    [L10]) или dict (старые записи в JSONB до миграции на типизированный
    контракт). JSONB-сериализация превращает CcRecipient в dict, поэтому
    consumer работает с обоими форматами.

    ``[{"email": "a@x", "name": "Иван"}, {"email": "b@y", "name": None}]`` →
    ``"Иван <a@x>, b@y"``. Пустая строка для пустого списка — заголовок не
    ставится (см. ``_apply_helpdesk_headers``). ``formataddr`` корректно
    экранирует спецсимволы в display-name (RFC 5322: запятые/точки-с-запятой
    в имени → кавычки).
    """
    from email.utils import formataddr

    def _get(p: object, key: str) -> str | None:
        # Pydantic v2 BaseModel: __getitem__ отсутствует, используем getattr.
        # dict: ключи. Покрывает оба представления Cc (модель + JSONB-dict).
        if isinstance(p, dict):
            return p.get(key)
        return getattr(p, key, None)

    parts = []
    for p in cc:
        email = (_get(p, "email") or "").strip() if _get(p, "email") else ""
        if not email:
            continue
        name_raw = _get(p, "name")
        name = (name_raw or "").strip() or None
        parts.append(formataddr((name, email)))
    return ", ".join(parts)


async def _build_helpdesk_mime(row: dict, cfg: dict) -> MIMEMultipart:
    """Сборка MIME для исходящего helpdesk-письма (ТЗ §5.2).

    Канонические заголовки (ТЗ §1.3.3):
    * ``Message-ID: <tkn-{ticket_number}-{message_uuid}@{support_domain}>`` —
      берётся из ``payload.message_id_header`` (генерируется заранее сервисом).
    * ``In-Reply-To`` / ``References`` — цепочка Message-ID предшествующих
      сообщений тикета.
    * ``Reply-To: {support_address}`` — чистый настроенный адрес ящика (без
      plus-addressing). См. :func:`_resolve_helpdesk_reply_to`.
    * ``Subject: "[#TKT-{number}] {original_subject}"``.

    Вложения читаются с локального диска через aiofiles (см.
    :func:`_read_helpdesk_attachment`). Если ``support_domain`` пуст/невалиден —
    raise (outbox → mark_failed): RFC 5322 требует валидный домен в msg-id,
    ``localhost`` подставлять нельзя.

    Inline-картинки rich-редактора встраиваются как ``cid:``-attach в
    ``multipart/related`` — заявитель видит их прямо в почтовом клиенте (без
    доступа к порталу, как OTRS). Best-effort: если файл не найден/не читается —
    ``src`` остаётся относительным (в веб-ленте портала картинка всё равно видна).
    """
    payload = row["payload"] or {}
    to_email = _sanitize_header(row["to_email"])
    from_address = _sanitize_header(cfg.get("from_address") or _DEFAULT_FROM_ADDRESS)
    body_html = row["body_html"] or ""
    body_text = row["body_text"]

    ticket_number = payload.get("ticket_number")
    support_domain = (payload.get("support_domain") or "").strip()
    if not ticket_number or not support_domain:
        raise ValueError(
            "helpdesk outbound requires payload.ticket_number and "
            "payload.support_domain (from helpdesk_mailbox_settings.support_address)"
        )

    # Встраиваем inline-картинки rich-редактора как cid:-attach (multipart/related).
    # Делаем до сборки тела: HTML уже должен содержать src="cid:...". Файлы читаются
    # из HELPDESK_FILES_DIR / TKT-{n} / inline / {file} (см. media.py).
    body_html, inline_images = await _embed_helpdesk_inline_images(body_html, ticket_number)
    # Картинки из истории переписки — локализованные email-attachments (входящие
    # письма заявителя с inline cid:/внешними http, сохранённые в БД через
    # email_images.py). Без этой ветки их ``src=/api/v1/.../attachments/{id}``
    # остаётся URL — почтовый клиент cookie не передаёт, картинка не грузится.
    # Здесь — встраиваем как cid: (как rich-картинки), один DB-запрос на все.
    body_html, att_inline_images = await _embed_helpdesk_attachment_images(body_html, ticket_number)
    inline_images.extend(att_inline_images)

    subject_original = _sanitize_header(payload.get("subject_original") or "")
    subject = _sanitize_header(f"[#TKT-{ticket_number}] {subject_original}")
    reply_to_address = _resolve_helpdesk_reply_to(payload, cfg)

    body_root = _build_helpdesk_body_root(body_text, body_html, inline_images)

    # outer: mixed — если есть обычные вложения (body_root + attachments),
    # иначе body_root сам становится корневым (related или alternative).
    if not payload.get("attachments"):
        outer = body_root
    else:
        outer = MIMEMultipart("mixed")
        outer.attach(body_root)
        for att_meta in payload["attachments"]:
            outer.attach(await _read_helpdesk_attachment(ticket_number, att_meta))

    _apply_helpdesk_headers(
        outer,
        subject=subject,
        from_address=from_address,
        to_email=to_email,
        reply_to_address=reply_to_address,
        payload=payload,
    )
    return outer


def _attach_inline_image(container: MIMEMultipart, img: dict) -> None:
    """Attach one base64 inline image (referenced from HTML via ``cid:``)."""
    cid = str(img.get("cid") or "").strip()
    b64 = img.get("b64") or ""
    if not cid or not b64:
        return
    try:
        data = base64.b64decode(b64)
    except Exception:
        logger.warning("email_outbox.inline_image_decode_failed", cid=cid)
        return
    subtype = (img.get("mime") or "image/jpeg").split("/")[-1] or "jpeg"
    part = MIMEImage(data, _subtype=subtype)
    part.add_header("Content-ID", f"<{cid}>")
    part.add_header("Content-Disposition", "inline", filename=f"{cid}.{subtype}")
    container.attach(part)


__all__ = ["cleanup_email_outbox", "process_email_outbox"]
