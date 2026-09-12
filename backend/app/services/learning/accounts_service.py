"""Сервис внешних учёток модуля обучения: создание, вход по одноразовому коду.

Passwordless (миграция 113): паролей у внешних учёток нет. Вход = email →
6-значный код письмом (outbox той же транзакцией) → verify → сессия. Код
хранится только SHA-256 хэшем, живёт минуты, одноразовый, ограничен числом
неверных вводов. Запасной путь «письмо не дошло» — админ выпускает код
вручную (``issue_manual_code``, plaintext только в ответе админского API).

Чистая логика (генерация/сверка кода, политика попыток) вынесена в чистые
функции — покрывается unit-тестами без моков SQLAlchemy; DB-слой тонкий.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.learning import LearningAccount, LearningLoginCode
from app.services.email_outbox import enqueue_outbox_email
from app.services.learning import emails
from app.services.learning.sessions import (
    COOKIE_NAME,
    build_login_payload,
    delete_session,
    invalidate_all_sessions,
    save_session,
)

logger = get_logger(__name__)

# Дефолт домена публичного контура: используется, пока в system.json не задан
# `learning_base_url` (ввод контура — ADR-050). Не использовать напрямую в
# новых местах — брать `learning_base_url()`.
LEARN_BASE_URL = "https://learn.mage.ru"


def learning_base_url() -> str:
    """База learn-домена для писем/ссылок: runtime-настройка `learning_base_url`
    (Admin UI), пока пуста — дефолт константы."""
    from app.core.system_config import load_system_settings

    return load_system_settings().learning_base_url or LEARN_BASE_URL


CODE_LENGTH = 6


def generate_login_code() -> str:
    """6-значный код без modulo bias: одно равновероятное число из 10^6,
    дополненное нулями (000000 допустим)."""
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def code_matches(code: str, code_hash: str) -> bool:
    # constant-time: хэш строки сравнивается с хэшем из БД.
    return hmac.compare_digest(hash_code(code), code_hash)


def is_code_expired(expires_at: datetime, now: datetime) -> bool:
    return expires_at <= now


def is_code_exhausted(attempts: int, max_attempts: int) -> bool:
    """После max_attempts неверных вводов код мёртв, даже если следующий верный."""
    return attempts >= max_attempts


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    account: LearningAccount


# ── DB-слой ──────────────────────────────────────────────────────────────────


async def get_active_by_email(db: AsyncSession, email: str) -> LearningAccount | None:
    result = await db.execute(
        select(LearningAccount).where(
            func.lower(LearningAccount.email) == email.strip().lower(),
            LearningAccount.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_active_by_id(db: AsyncSession, account_id: uuid.UUID) -> LearningAccount | None:
    result = await db.execute(
        select(LearningAccount).where(
            LearningAccount.id == account_id,
            LearningAccount.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_account(
    db: AsyncSession,
    *,
    email: str,
    full_name: str,
    department: str | None = None,
    position: str | None = None,
) -> LearningAccount:
    """Поштучное создание методистом. Пароля нет (passwordless): человек входит
    кодом из письма, когда до него дойдёт очередь задачи. Письмо при создании
    не отправляется — нечего сообщать, кроме самого факта (спам без действия)."""
    existing = await get_active_by_email(db, email)
    if existing or (await db.execute(_blocked_email_probe(email))).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email уже используется")

    account = LearningAccount(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        department=department,
        position=position,
    )
    db.add(account)
    await db.flush()
    return account


def _blocked_email_probe(email: str) -> Select:
    """Soft-deleted учётка тоже занимает email: uniqueness-индекс частичный,
    но повторное создание под тем же адресом создало бы двусмысленность —
    считаем адрес занятым независимо от deleted_at."""
    return select(LearningAccount).where(
        func.lower(LearningAccount.email) == email.strip().lower(),
        LearningAccount.deleted_at.is_not(None),
    )


async def _invalidate_active_codes(db: AsyncSession, account_id: uuid.UUID) -> None:
    """Единственный активный код на учётку: новый запрос гасит предыдущие
    («отправить снова» из UI не оставляет несколько живых кодов)."""
    await db.execute(
        update(LearningLoginCode)
        .where(
            LearningLoginCode.account_id == account_id,
            LearningLoginCode.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
    )


async def request_login_code(db: AsyncSession, *, email: str) -> None:
    """Шаг 1 входа: выпустить код и отправить письмом. Ответ эндпоинта одинаков
    всегда (анти-enumeration) — фактическая отправка только существующей
    активной учётке; blocked тоже молчит (адрес занят, доступа нет)."""
    account = await get_active_by_email(db, email)
    if not account or account.status != "active":
        logger.info("learning.code_requested_unknown", email=_mask(email))
        return
    await _invalidate_active_codes(db, account.id)
    code = generate_login_code()
    ttl_minutes = get_settings().learning_code_ttl_minutes
    now = datetime.now(UTC)
    db.add(
        LearningLoginCode(
            account_id=account.id,
            code_hash=hash_code(code),
            expires_at=now + timedelta(minutes=ttl_minutes),
        )
    )
    subject, body_text, body_html = emails.login_code(
        full_name=account.full_name, code=code, ttl_minutes=ttl_minutes
    )
    await enqueue_outbox_email(
        db,
        kind="learning",
        to_email=account.email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        related_resource_type="learning_account",
        related_resource_id=account.id,
    )
    await db.commit()
    logger.info("learning.code_requested", account_id=str(account.id))


async def verify_login_code(db: AsyncSession, *, email: str, code: str) -> LoginOutcome | None:
    """Шаг 2 входа: сверить код. ``None`` — отказ (нет учётки / нет активного
    кода / неверный / истёк / исчерпаны попытки / учётка blocked); эндпоинт
    отвечает на всё это одним и тем же 400. Неверный ввод инкрементит attempts
    атомарным UPDATE и коммитится — счётчик переживает параллельные запросы."""
    now = datetime.now(UTC)
    account = await get_active_by_email(db, email)
    if not account or account.status != "active":
        logger.info("learning.code_verify_denied", email=_mask(email))
        return None

    result = await db.execute(
        select(LearningLoginCode)
        .where(
            LearningLoginCode.account_id == account.id,
            LearningLoginCode.used_at.is_(None),
            LearningLoginCode.expires_at > now,
        )
        .order_by(LearningLoginCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None:
        await db.rollback()
        logger.info("learning.code_verify_denied", email=_mask(email))
        return None
    max_attempts = get_settings().learning_code_max_attempts
    if is_code_exhausted(row.attempts, max_attempts) or not code_matches(code, row.code_hash):
        if not is_code_exhausted(row.attempts, max_attempts):
            await db.execute(
                update(LearningLoginCode)
                .where(LearningLoginCode.id == row.id)
                .values(attempts=LearningLoginCode.attempts + 1)
            )
            await db.commit()
        else:
            await db.rollback()
        logger.info("learning.code_verify_denied", email=_mask(email))
        return None

    # Одноразовость — тот же паттерн, что у токенов восстановления: FOR UPDATE
    # сериализует гонки, условный UPDATE с проверкой rowcount — страховка.
    claim = await db.execute(
        update(LearningLoginCode)
        .where(LearningLoginCode.id == row.id, LearningLoginCode.used_at.is_(None))
        .values(used_at=now)
    )
    if int(cast(CursorResult, claim).rowcount or 0) != 1:
        await db.rollback()
        logger.info("learning.code_verify_denied", email=_mask(email))
        return None
    await db.execute(
        update(LearningAccount).where(LearningAccount.id == account.id).values(last_login_at=now)
    )
    await db.commit()
    return LoginOutcome(account=account)


async def issue_manual_code(db: AsyncSession, *, account: LearningAccount) -> tuple[str, datetime]:
    """Запасной путь «письмо не дошло»: админ выпускает код и передаёт его
    человеку по телефону/мессенджеру. Plaintext возвращается только сюда —
    дальше он живёт в ответе админского API и нигде не логируется."""
    if account.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Учётка заблокирована",
        )
    await _invalidate_active_codes(db, account.id)
    code = generate_login_code()
    ttl_minutes = get_settings().learning_code_ttl_minutes
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    db.add(
        LearningLoginCode(
            account_id=account.id,
            code_hash=hash_code(code),
            expires_at=expires_at,
        )
    )
    await db.commit()
    logger.info("learning.code_issued_manually", account_id=str(account.id))
    return code, expires_at


async def create_login_session(
    redis: Any, outcome: LoginOutcome, old_session_id: str | None
) -> str:
    payload = build_login_payload(str(outcome.account.id))
    session_id = secrets.token_urlsafe(32)
    # Anti-fixation: чужая cookie до логина уничтожается. Свои живые сессии этой
    # же учётки не трогаем (второй таб браузера не отваливается).
    if old_session_id:
        from app.services.learning.sessions import get_session_payload

        old_payload = await get_session_payload(redis, old_session_id)
        if old_payload is None or old_payload.get("account_id") != str(outcome.account.id):
            await delete_session(redis, old_session_id)
    await save_session(redis, session_id, str(outcome.account.id), payload)
    return session_id


def set_session_cookie(response: Any, session_id: str, *, secure: bool) -> None:
    # secure вычисляет вызывающий по фактическому протоколу запроса
    # (request_is_secure, ADR-021): сервисный слой не знает про транспорт.
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=8 * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        # Host-only (без domain=): cookie живёт только на learn-домене.
    )


def clear_session_cookie(response: Any) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


async def admin_set_status(
    db: AsyncSession, redis: Any, account: LearningAccount, *, blocked: bool
) -> None:
    new_status = "blocked" if blocked else "active"
    await db.execute(
        update(LearningAccount)
        .where(LearningAccount.id == account.id)
        .values(status=new_status, updated_at=datetime.now(UTC))
    )
    if blocked:
        # Сессии и неиспользованные коды гасятся: blocked не должен войти даже
        # с кодом, выпущенным до блокировки (проверка статуса в verify —
        # страховка, здесь зачистка состояния).
        await _invalidate_active_codes(db, account.id)
        await invalidate_all_sessions(redis, str(account.id))
    await db.commit()
    logger.info("learning.status_changed", account_id=str(account.id), status=new_status)


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:2]}***@{domain}" if name else "***"
