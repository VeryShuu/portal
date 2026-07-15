"""Фильтр ARQ-логов высокочастотных cron-задач.

ARQ (`python -m arq`) при старте вызывает ``logging.config.dictConfig`` со своим
конфигом (``arq.logs.default_log_config``) — это перенастраивает логгер ``arq``
собственным форматом ``%(asctime)s: %(message)s`` и перезаписывает наш structlog
handler. Кроме того, ARQ пишет по две INFO-строки на *каждый* запуск задачи
(``→ ref()`` / ``← ref ● result``) через логгер ``arq.worker``.

Для высокочастотных cron-задач это создаёт огромный бесполезный объём: на проде
за ~2 месяца набегает ~145K таких строк, из них ~132K — четыре задачи:

    flush_audit_queue        каждые 5с  → ~72K строк
    process_email_outbox     каждые 10с → ~36K строк
    worker_heartbeat         каждые 30с → ~12K строк
    refresh_custom_metrics   каждые 30с → ~12K строк

``QuietCronFilter`` приглушает только INFO-сообщения о старте/успешном завершении
этих задач. Ошибки (``! failed``, logger.exception), ретраи (``↻``), прерывания
(``⊘``), редкие cron и все ручные задачи остаются в логе как есть.

Восстановление structlog handler на логгере ``arq``/``arq.worker`` делается в
``app.worker.main.startup`` через ``restore_arq_loggers()`` — ARQ CLI уже
выполнил свой ``dictConfig`` к этому моменту.
"""

from __future__ import annotations

import logging

# CRON-задачи, чей успешный старт/финиш логируется слишком часто и не несёт
# ценности (по 2 строки на запуск). Их INFO-вывод о старте/завершении гасим.
# Сюда НЕ добавлять задачи, которые могут падать молча — для них нужен след в
# логе. Ошибки этих задач всё равно проходят (фильтр пропускает WARNING+).
QUIET_CRON_REFS: frozenset[str] = frozenset(
    {
        "cron:app.worker.tasks.audit.flush_audit_queue",
        "cron:app.worker.tasks.email_outbox.process_email_outbox",
        "cron:app.worker.tasks.metrics.worker_heartbeat",
        "cron:app.worker.tasks.metrics.refresh_custom_metrics",
    }
)

# Маркеры ARQ для «старт/успешный финиш задачи». Другие маркеры (! failed,
# ↻ retry, ⊘ aborted) НЕ попадают под фильтр — их видно всегда.
_QUIET_MARKERS: tuple[str, ...] = (" → ", " ← ")


class QuietCronFilter(logging.Filter):
    """Гасит INFO о старте/успешном завершении высокочастотных cron-задач.

    Пропускает (не фильтрует):
      - любые записи уровня WARNING и выше (ошибки, ретраи);
      - задачи не из ``QUIET_CRON_REFS`` (редкие cron, ручные задачи);
      - сообщения без маркера ``→``/``←`` (стартовые баннеры ARQ и т.п.).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # ``record.getMessage()`` — уже интерполированное сообщение (%-args
        # подставлены), именно в нём ARQ оставляет ``→ ref()`` / ``← ref ● n``.
        if record.levelno > logging.INFO:
            return True
        msg = record.getMessage()
        # Быстрая проверка: есть ли маркер старт/финиш. Если нет — пропускаем.
        if not any(marker in msg for marker in _QUIET_MARKERS):
            return True
        return not any(ref in msg for ref in QUIET_CRON_REFS)
