"""SMTP-проверка соединения для ``POST /helpdesk/settings/mailbox/test-smtp``.

Зеркало ``probe_imap_connection`` из ``ingress.py``: подключение → login (если
есть креды) → ``NOOP`` → ``quit``, возвращает ``(ok, detail)``. Используется
админ-кнопкой «Проверить SMTP» в mailbox-настройках helpdesk.

Собственный исходящий SMTP-контур helpdesk (миграция ``086``): письма уходят с
учётки support-ящика, а не с общего порталного SMTP. Эта функция проверяет, что
админ корректно заполнил host/port/учётку/TLS — до того, как реальные ответы
заявителям начнут падать в DLQ outbox'а.
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)

# Таймаут как у IMAP-probe (``ingress.probe_imap_connection``): 10 с на каждое
# асинхронное действие. Достаточно для внутрикорпоративного релея; защищает
# админ-UI от зависания на недоступном хосте.
_PROBE_TIMEOUT_SECONDS = 10


async def probe_smtp_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool,
    use_starttls: bool,
) -> tuple[bool, str]:
    """Проверка SMTP-соединения для ``POST /settings/mailbox/test-smtp``.

    Поднимает соединение через ``aiosmtplib.SMTP``, применяет TLS/STARTTLS по
    флагам, логинится при наличии кредов и делает ``NOOP``. Возвращает
    ``(True, detail)`` при успехе или ``(False, detail)`` при ошибке (детали —
    ``"{тип исключения}: {сообщение}"``, без маскировки здесь — маскировка
    делается слоем выше в API-эндпоинте, см. ``settings.test_mailbox_smtp_connection``).
    """
    import aiosmtplib

    client = aiosmtplib.SMTP(
        hostname=host,
        port=port,
        use_tls=use_tls,
        start_tls=False,  # STARTTLS поднимаем вручную ниже после EHLO
        timeout=_PROBE_TIMEOUT_SECONDS,
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=_PROBE_TIMEOUT_SECONDS)
        if use_starttls:
            await asyncio.wait_for(client.starttls(), timeout=_PROBE_TIMEOUT_SECONDS)
        if username and password:
            await asyncio.wait_for(client.login(username, password), timeout=_PROBE_TIMEOUT_SECONDS)
        # NOOP — финальная проверка готовности сервера принимать почту (EHLO +
        # опционально AUTH уже прошли; NOOP подтверждает, что сессия жива).
        await asyncio.wait_for(client.noop(), timeout=_PROBE_TIMEOUT_SECONDS)
        auth_info = "authenticated" if (username and password) else "no-auth"
        tls_info = "TLS" if use_tls else ("STARTTLS" if use_starttls else "plain")
        return True, f"Connected via {host}:{port} ({tls_info}, {auth_info})"
    except Exception as exc:
        # Не маскируем здесь — детали полезны для диагностики, а верхний слой
        # (API-эндпоинт) маскирует единообразно с IMAP-test (defence-in-depth).
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        try:
            await client.quit()
        except Exception:
            # ``quit`` после ошибки/таймаута может бросить повторно — не критично,
            # соединение уже проверено (или провалено).
            logger.debug("helpdesk.smtp.probe.quit_failed", host=host, port=port)
