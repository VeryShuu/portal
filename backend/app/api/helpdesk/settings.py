"""Admin mailbox settings for helpdesk (Этап 5, ТЗ §3.6, §9.2).

Singleton-строка (``id=1``) с IMAP-конфигом. Пароль шифруется через
``secret_crypto`` (write-only: в ответах только ``imap_password_set``).
``GET`` до первого ``PUT`` возвращает ``configured=false`` (строка ещё не
создана — ``imap_password_enc NOT NULL`` не даёт засеять её без пароля).
``POST /test`` проверяет IMAP-соединение.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret, encrypt_secret
from app.models.helpdesk import (
    HelpdeskDigestSettings,
    HelpdeskMailboxSettings,
    HelpdeskMaxBotSettings,
)
from app.schemas.helpdesk import (
    HelpdeskDigestSettingsIn,
    HelpdeskDigestSettingsOut,
    HelpdeskMailboxSettingsIn,
    HelpdeskMailboxSettingsOut,
    HelpdeskMaxBotSettingsIn,
    HelpdeskMaxBotSettingsOut,
    HelpdeskMaxBotTestResult,
)
from app.services.audit import push_audit_event

logger = get_logger(__name__)

router = APIRouter(prefix="/helpdesk/settings", tags=["helpdesk"])


async def _load_singleton(db: DbDep) -> HelpdeskMailboxSettings | None:
    res = await db.execute(select(HelpdeskMailboxSettings).where(HelpdeskMailboxSettings.id == 1))
    row = res.scalars().one_or_none()
    return row


def _to_out(row: HelpdeskMailboxSettings | None) -> HelpdeskMailboxSettingsOut:
    if row is None:
        return HelpdeskMailboxSettingsOut(configured=False)
    return HelpdeskMailboxSettingsOut(
        configured=True,
        imap_host=row.imap_host,
        imap_port=row.imap_port,
        imap_username=row.imap_username,
        imap_password_set=True,
        imap_use_ssl=row.imap_use_ssl,
        imap_folder=row.imap_folder,
        poll_interval_seconds=row.poll_interval_seconds,
        delete_after_fetch=row.delete_after_fetch,
        support_address=row.support_address,
        support_reply_to=row.support_reply_to,
        updated_at=row.updated_at,
    )


@router.get("/mailbox", response_model=HelpdeskMailboxSettingsOut)
async def get_mailbox_settings(_admin: AdminDep, db: DbDep) -> HelpdeskMailboxSettingsOut:
    return _to_out(await _load_singleton(db))


@router.put("/mailbox", response_model=HelpdeskMailboxSettingsOut)
async def put_mailbox_settings(
    payload: HelpdeskMailboxSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> HelpdeskMailboxSettingsOut:
    row = await _load_singleton(db)
    if row is None:
        # Создание singleton'а: пароль обязателен (без него NOT NULL-колонка).
        if not payload.imap_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="imap_password is required on first configuration",
            )
        row = HelpdeskMailboxSettings(id=1, updated_by_user_id=admin.id)
        _apply_fields(row, payload, is_create=True)
        db.add(row)
    else:
        # Обновление: пароль опционален (None = оставить прежний шифр).
        row.updated_by_user_id = admin.id
        _apply_fields(row, payload, is_create=False)

    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="helpdesk.mailbox_settings_changed",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="helpdesk_mailbox_settings",
        resource_id="1",
        metadata={"support_address": payload.support_address},
    )
    return _to_out(row)


def _apply_fields(
    row: HelpdeskMailboxSettings, p: HelpdeskMailboxSettingsIn, *, is_create: bool
) -> None:
    row.imap_host = p.imap_host
    row.imap_port = p.imap_port
    row.imap_username = p.imap_username
    if p.imap_password:  # write-only: пусто/None = оставить прежний шифр
        row.imap_password_enc = encrypt_secret(p.imap_password)
    elif is_create:
        # На случай если валидация пропустила пустой пароль при создании.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="imap_password is required on first configuration",
        )
    row.imap_use_ssl = p.imap_use_ssl
    row.imap_folder = p.imap_folder
    row.poll_interval_seconds = p.poll_interval_seconds
    row.delete_after_fetch = p.delete_after_fetch
    row.support_address = p.support_address
    row.support_reply_to = p.support_reply_to


@router.post("/mailbox/test")
async def test_mailbox_connection(_admin: AdminDep, db: DbDep) -> dict:
    """Проверка IMAP-соединения с текущими настройками. Возвращает OK/детали."""
    row = await _load_singleton(db)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mailbox not configured")
    password = decrypt_secret(row.imap_password_enc)
    try:
        from app.services.helpdesk.ingress import probe_imap_connection

        ok, detail = await probe_imap_connection(
            host=row.imap_host,
            port=row.imap_port,
            username=row.imap_username,
            password=password,
            use_ssl=row.imap_use_ssl,
            folder=row.imap_folder,
        )
    except Exception:
        # H-9: не отдаём ``str(exc)`` наружу. aioimaplib (и другие IMAP-библиотеки)
        # в исключения иногда включает выполненную команду, где фигурирует пароль
        # (``C: A1 LOGIN <user> <password>``). Defense-in-depth: даже AdminDep —
        # маскируем, чтобы креды не утекли в HTTP-ответ и прокси/access-логи.
        # Полный traceback остаётся в server-log через ``logger.exception``.
        logger.exception("helpdesk.mailbox.test_connection_failed")
        return {"ok": False, "error": "IMAP connection failed (see server logs for details)"}
    return {"ok": ok, "detail": detail}


# ---------------------------------------------------------------------------
# Daily digest settings (singleton, seeded by migration 076).
# ---------------------------------------------------------------------------


async def _load_digest_singleton(db: DbDep) -> HelpdeskDigestSettings:
    """Singleton helpdesk_digest_settings (id=1).

    В отличие от mailbox, строка засевается миграцией — всегда существует.
    Защитный fallback: если миграция ещё не применена/строка удалена, создаём
    новую с дефолтами (best-effort; нормальный путь — миграция).
    """
    res = await db.execute(select(HelpdeskDigestSettings).where(HelpdeskDigestSettings.id == 1))
    row = res.scalars().one_or_none()
    if row is None:
        row = HelpdeskDigestSettings(id=1)
        db.add(row)
        await db.flush()
    return row


@router.get("/digest", response_model=HelpdeskDigestSettingsOut)
async def get_digest_settings(_admin: AdminDep, db: DbDep) -> HelpdeskDigestSettingsOut:
    row = await _load_digest_singleton(db)
    return HelpdeskDigestSettingsOut.model_validate(row)


@router.put("/digest", response_model=HelpdeskDigestSettingsOut)
async def put_digest_settings(
    payload: HelpdeskDigestSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> HelpdeskDigestSettingsOut:
    row = await _load_digest_singleton(db)
    row.enabled = payload.enabled
    row.digest_hour = payload.digest_hour
    row.digest_minute = payload.digest_minute
    row.digest_schedule = payload.digest_schedule
    row.updated_by_user_id = admin.id
    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="helpdesk.digest_settings_changed",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="helpdesk_digest_settings",
        resource_id="1",
        metadata={
            "enabled": payload.enabled,
            "digest_hour": payload.digest_hour,
            "digest_minute": payload.digest_minute,
            "digest_schedule": payload.digest_schedule,
        },
    )
    return HelpdeskDigestSettingsOut.model_validate(row)


# ---------------------------------------------------------------------------
# MAX-messenger bot settings (singleton, seeded by migration 081).
# ---------------------------------------------------------------------------


async def _load_max_bot_singleton(db: DbDep) -> HelpdeskMaxBotSettings:
    """Singleton helpdesk_max_bot_settings (id=1).

    Засевается миграцией 081 — всегда существует. Защитный fallback: если
    миграция ещё не применена/строка удалена, создаём новую с дефолтами
    (best-effort; нормальный путь — миграция, как и в ``_load_digest_singleton``).
    """
    res = await db.execute(
        select(HelpdeskMaxBotSettings).where(HelpdeskMaxBotSettings.id == 1)
    )
    row = res.scalars().one_or_none()
    if row is None:
        row = HelpdeskMaxBotSettings(id=1)
        db.add(row)
        await db.flush()
    return row


def _max_bot_to_out(row: HelpdeskMaxBotSettings) -> HelpdeskMaxBotSettingsOut:
    bot_token_set = bool(row.bot_token_enc)
    configured = bool(row.enabled and bot_token_set and row.chat_id)
    return HelpdeskMaxBotSettingsOut(
        configured=configured,
        enabled=row.enabled,
        bot_token_set=bot_token_set,
        chat_id=row.chat_id,
        updated_at=row.updated_at,
    )


@router.get("/max-bot", response_model=HelpdeskMaxBotSettingsOut)
async def get_max_bot_settings(
    _admin: AdminDep, db: DbDep
) -> HelpdeskMaxBotSettingsOut:
    row = await _load_max_bot_singleton(db)
    return _max_bot_to_out(row)


@router.put("/max-bot", response_model=HelpdeskMaxBotSettingsOut)
async def put_max_bot_settings(
    payload: HelpdeskMaxBotSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> HelpdeskMaxBotSettingsOut:
    """Сохранить конфигурацию MAX-бота (токен write-only, как IMAP-пароль).

    Валидация: при ``enabled=True`` обязательно наличие токена (либо в текущем
    payload, либо уже сохранённого) и ``chat_id`` — иначе 400 (нельзя включить
    канал без валидных кредов).
    """
    row = await _load_max_bot_singleton(db)
    row.enabled = payload.enabled
    row.chat_id = payload.chat_id
    if payload.bot_token:  # write-only: пусто/None = оставить прежний шифр
        row.bot_token_enc = encrypt_secret(payload.bot_token)
    row.updated_by_user_id = admin.id

    # Валидация enabled=True требует полный набор кредов.
    if row.enabled:
        if not row.bot_token_enc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="bot_token is required when enabled=true",
            )
        if not row.chat_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="chat_id is required when enabled=true",
            )

    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="helpdesk.max_bot_settings_changed",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="helpdesk_max_bot_settings",
        resource_id="1",
        metadata={
            "enabled": payload.enabled,
            "chat_id": payload.chat_id,
            "token_changed": bool(payload.bot_token),
        },
    )
    return _max_bot_to_out(row)


@router.post("/max-bot/test", response_model=HelpdeskMaxBotTestResult)
async def test_max_bot_connection(admin: AdminDep, db: DbDep) -> HelpdeskMaxBotTestResult:
    """Отправить тестовое сообщение в чат поддержки через MAX Bot API.

    В отличие от ``POST /mailbox/test`` (который проверяет только IMAP-логин),
    здесь мы делаем **полный end-to-end тест**: отправляем реальное сообщение
    в настроенный ``chat_id``. Это проверяет:
    * токен бота валиден (401 от MAX иначе);
    * бот добавлен в чат и имеет права писать (403/400 иначе);
    * ``chat_id`` корректный (400 «chat not found» иначе);
    * TLS к MAX работает (Russian Trusted CA в trust store).

    Пользователь видит сообщение в MAX — это и есть подтверждение «всё работает».

    Defense-in-depth: на ошибку маскируем ``str(exc)`` (MAX в JSON-ошибках
    иногда отражает часть токена или чувствительные детали). Полный traceback
    остаётся в server-log через ``logger.exception``.
    """
    row = await _load_max_bot_singleton(db)
    if not row.bot_token_enc:
        return HelpdeskMaxBotTestResult(
            ok=False, error="Bot token is not configured"
        )
    if not row.chat_id:
        return HelpdeskMaxBotTestResult(
            ok=False, error="Chat ID is not configured"
        )
    bot_token = decrypt_secret(row.bot_token_enc)
    # Тестовое сообщение: короткое, с подписью кто инициировал проверку.
    # ``markdown`` (а не ``plain``): MAX падает с "Can't deserialize body"
    # при format=plain. Текст без разметки — markdown-парсер проходит без
    # проблем (это просто текст без специальных символов).
    text = (
        "✅ Тест портала: уведомления helpdesk работают.\n"
        f"Инициатор проверки: {admin.full_name}."
    )
    try:
        from app.services.max_messenger import send_message

        await send_message(
            bot_token=bot_token,
            chat_id=row.chat_id,
            text=text,
            format_="markdown",
            attachments=None,
            notify=True,
        )
    except Exception as exc:
        logger.exception("helpdesk.max_bot.test_connection_failed")
        # Подсказываем наиболее частые причины, исходя из статус-кода MAX.
        # Это спасает админа от необходимости лезть в server-логи при типовых
        # проблемах конфигурации (404 = бот не в чате, 403 = нет прав и т.д.).
        status_code = getattr(exc, "status_code", None)
        hint = "See server logs for details."
        if status_code == 404:
            hint = (
                "MAX returned 'chat not found'. Add the bot to the support "
                "chat in MAX (the bot must be a chat member), then re-check."
            )
        elif status_code == 403:
            hint = "MAX denied access — bot lacks write permission in this chat."
        elif status_code == 401:
            hint = "Bot token is invalid or revoked. Re-issue the token in MAX."
        return HelpdeskMaxBotTestResult(
            ok=False,
            error=f"MAX API call failed (HTTP {status_code}). {hint}",
        )
    return HelpdeskMaxBotTestResult(
        ok=True,
        detail=f"Test message sent to chat {row.chat_id}. Check MAX.",
    )
