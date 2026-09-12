"""Admin endpoints для настроек Matrix-бота (персональные чат-уведомления).

Зеркалирует max-bot endpoints из :mod:`app.api.helpdesk.settings`: токен
write-only (шифруется Fernet), ``enabled=true`` требует полный конфиг,
test — end-to-end проверка (whoami → DM админу → сообщение). Отличие:
этот бот — общий провайдер уведомлений (не helpdesk-специфичный), настройки
живут в админке в группе «Уведомления» → вкладка «Корпоративный чат».
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, DbDep, RedisDep
from app.core.logging import get_logger
from app.core.secret_crypto import decrypt_secret, encrypt_secret
from app.models.matrix_bot import MatrixBotSettings
from app.schemas.matrix_bot import (
    MatrixBotSettingsIn,
    MatrixBotSettingsOut,
    MatrixBotTestIn,
    MatrixBotTestResult,
)
from app.services.audit import push_audit_event
from app.services.matrix_messenger import matrix_id_for_user, whoami
from app.services.messenger_outbox import PROVIDER_MATRIX, enqueue_messenger_message

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/matrix-bot", tags=["admin", "matrix-bot"])

_MXID_RE = re.compile(r"^@[^:\s]+:\S+$")


def resolve_test_target(raw: str | None, *, admin_email: str, server_name: str) -> str:
    """Получатель теста из ручного ввода: MXID как есть, email → конвенция,
    голый localpart → ``@localpart:server``. Пусто → MXID админа из его email
    (дефолт; локальный админ с другим MXID задаёт его явно)."""
    if not raw or not raw.strip():
        return matrix_id_for_user(admin_email, server_name)
    value = raw.strip()
    if _MXID_RE.match(value):
        return value
    if "@" in value:
        return matrix_id_for_user(value, server_name)
    return f"@{value.lower()}:{server_name}"


async def load_matrix_bot_singleton(db: AsyncSession) -> MatrixBotSettings:
    """Singleton matrix_bot_settings (id=1), сеется миграцией 097.

    Защитный fallback — как в ``helpdesk.settings._load_max_bot_singleton``.
    """
    res = await db.execute(select(MatrixBotSettings).where(MatrixBotSettings.id == 1))
    row = res.scalars().one_or_none()
    if row is None:
        row = MatrixBotSettings(id=1)
        db.add(row)
        await db.flush()
    return row


def _to_out(row: MatrixBotSettings) -> MatrixBotSettingsOut:
    access_token_set = bool(row.access_token_enc)
    configured = bool(
        row.enabled
        and access_token_set
        and row.homeserver_url
        and row.bot_user_id
        and row.server_name
    )
    return MatrixBotSettingsOut(
        configured=configured,
        enabled=row.enabled,
        access_token_set=access_token_set,
        homeserver_url=row.homeserver_url,
        server_name=row.server_name,
        bot_user_id=row.bot_user_id,
        updated_at=row.updated_at,
    )


@router.get("", response_model=MatrixBotSettingsOut, summary="Настройки Matrix-бота")
async def get_matrix_bot_settings(_admin: AdminDep, db: DbDep) -> MatrixBotSettingsOut:
    row = await load_matrix_bot_singleton(db)
    return _to_out(row)


@router.put("", response_model=MatrixBotSettingsOut, summary="Сохранить настройки Matrix-бота")
async def put_matrix_bot_settings(
    payload: MatrixBotSettingsIn,
    admin: AdminDep,
    db: DbDep,
    redis: RedisDep,
) -> MatrixBotSettingsOut:
    """Сохранить конфигурацию (токен write-only, как IMAP-пароль/MAX-токен).

    Валидация: при ``enabled=True`` обязателен полный набор — токен (новый или
    сохранённый), homeserver_url, server_name, bot_user_id. Иначе 400: нельзя
    включить канал без валидных кредов.
    """
    row = await load_matrix_bot_singleton(db)
    row.enabled = payload.enabled
    row.homeserver_url = payload.homeserver_url
    row.server_name = payload.server_name or row.server_name
    row.bot_user_id = payload.bot_user_id
    if payload.access_token:  # write-only: пусто/None = оставить прежний шифр
        row.access_token_enc = encrypt_secret(payload.access_token)
    row.updated_by_user_id = admin.id

    if row.enabled:
        missing = [
            label
            for label, value in (
                ("access_token", row.access_token_enc),
                ("homeserver_url", row.homeserver_url),
                ("server_name", row.server_name),
                ("bot_user_id", row.bot_user_id),
            )
            if not value
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"required when enabled=true: {', '.join(missing)}",
            )

    await db.commit()
    await db.refresh(row)
    await push_audit_event(
        redis,
        event_type="matrix.bot_settings_changed",
        user_id=str(admin.id),
        user_email=admin.email,
        resource_type="matrix_bot_settings",
        resource_id="1",
        metadata={
            "enabled": payload.enabled,
            "homeserver_url": payload.homeserver_url,
            "server_name": row.server_name,
            "bot_user_id": payload.bot_user_id,
            "token_changed": bool(payload.access_token),
        },
    )
    return _to_out(row)


@router.post("/test", response_model=MatrixBotTestResult, summary="Тест Matrix-бота")
async def test_matrix_bot_connection(
    admin: AdminDep,
    db: DbDep,
    body: MatrixBotTestIn | None = None,
) -> MatrixBotTestResult:
    """End-to-end тест: whoami (токен) → сообщение получателю через
    messenger_outbox (настоящий путь доставки).

    Получатель — из ``body.target`` (MXID как есть / email → конвенция /
    localpart → ``@localpart:server``); пусто → MXID самого админа по
    конвенции из его email (локальный админ может иметь другой MXID — тогда
    цель задаётся явно).

    Шаг 1 синхронный: whoami даёт мгновенную диагностику токена/доступности
    (401 M_UNKNOWN_TOKEN → перевыпустить токен, unreachable → url). Шаг 2 —
    enqueue в ``messenger_outbox`` (provider=matrix): сообщение идёт тем же
    конвейером, что и продакшн-уведомления (воркер 15с → DM-резолв →
    отправка), поэтому видно во вкладке «Очередь мессенджеров» и честно
    проверяет весь путь. Ошибки доставки (например, 400 «пользователь не
    существует») — в очереди, в ``last_error``.

    Defense-in-depth: ``str(exc)`` маскируется (в Matrix-ошибках могут быть
    чувствительные детали); полный traceback — в server-log.
    """
    row = await load_matrix_bot_singleton(db)
    if not row.access_token_enc:
        return MatrixBotTestResult(ok=False, error="Access token is not configured")
    if not row.homeserver_url:
        return MatrixBotTestResult(ok=False, error="Homeserver URL is not configured")
    if not row.bot_user_id:
        return MatrixBotTestResult(ok=False, error="Bot user ID is not configured")

    access_token = decrypt_secret(row.access_token_enc)
    homeserver_url = row.homeserver_url

    # Шаг 1: токен (быстрая диагностика без побочных эффектов).
    try:
        me = await whoami(homeserver_url=homeserver_url, access_token=access_token)
    except Exception as exc:
        logger.exception("matrix_bot.test_connection_failed")
        status_code = getattr(exc, "status_code", None)
        hint = "See server logs for details."
        if status_code == 401:
            hint = (
                "Access token is invalid or revoked. Re-issue it with "
                "'mas-cli manage issue-compatibility-token'."
            )
        elif status_code is None:
            hint = "Homeserver unreachable (DNS/TLS/network). Check homeserver_url."
        return MatrixBotTestResult(
            ok=False,
            error=f"Matrix whoami failed (HTTP {status_code}). {hint}",
        )

    # Шаг 2: сообщение получателю через messenger_outbox — как продакшн.
    target_mxid = resolve_test_target(
        body.target if body else None,
        admin_email=admin.email,
        server_name=row.server_name,
    )
    text = (
        "✅ Тест портала: персональные уведомления работают.\n"
        f"Инициатор проверки: {admin.full_name}."
    )
    try:
        await enqueue_messenger_message(
            db,
            provider=PROVIDER_MATRIX,
            chat_id=target_mxid,
            text=text,
            payload={
                "formatted_body": (
                    "<b>✅ Тест портала:</b> персональные уведомления работают.<br>"
                    f"Инициатор проверки: {admin.full_name}."
                )
            },
            related_resource_type="matrix_bot_test",
        )
        await db.commit()
    except Exception as exc:
        logger.exception("matrix_bot.test_enqueue_failed")
        return MatrixBotTestResult(
            ok=False, error=f"Failed to enqueue test message: {type(exc).__name__}"
        )

    bot_mxid = me.get("user_id") if isinstance(me, dict) else None
    return MatrixBotTestResult(
        ok=True,
        detail=(
            f"Test message to {target_mxid} queued (delivery by {bot_mxid or row.bot_user_id} "
            "within ~30s). Status: admin → Messenger queue."
        ),
    )
