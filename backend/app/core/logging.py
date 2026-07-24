"""Комплексная система структурированного логирования.

Ключевые принципы:
- Один источник конфигурации (configure_logging) вызывается ДО создания логгеров.
- Структурированный key=value стиль через structlog.
- В production — JSON (совместимо с Loki/ELK/Vector).
- В development — цветной ConsoleRenderer (только для TTY).
- Сквозной contextvars: request_id, user_id, role, job_id, correlation_id.
- Redaction: пароли, токены, секреты, cookies — маскируются автоматически.
- PII masking: email маскируется до a***@domain.
- Truncation: значения > MAX_VALUE_SIZE обрезаются (защита от раздувания).
- Uvicorn-логгеры перехвачены единым handler.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any, cast

import structlog
from structlog.types import EventDict, Processor

# ---------------------------------------------------------------------------
# Константы редакции секретов и PII.
# ---------------------------------------------------------------------------

SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session_id",
    "session-id",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "refresh_token",
    "access_token",
    "id_token",
    "jwt",
    "csrf",
    "bearer",
)

REDACTED = "***REDACTED***"

MAX_VALUE_SIZE = 4096  # 4 КБ — после чего значение обрезается
MAX_STRING_VALUES_IN_EVENT = 50_000  # суммарно на один event_dict

MANAGED_LOGGER_NAMES: tuple[str, ...] = (
    "",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "fastapi",
    "arq",
    "arq.worker",
)

# Сторонние библиотеки, которые спамят килограммы мусора и при этом их
# подробный вывод не нужен НИКОГДА (даже в dev при DEBUG). Намертво фиксируем
# их уровень на WARNING вне зависимости от настроек root-логгера.
# PIL парсит каждый EXIF-tag в DEBUG → на крупных JPEG обработка одного фото
# вырастает с долей секунды до десятков секунд.
NOISY_LIBRARY_LOGGERS: tuple[str, ...] = (
    "PIL",
    "PIL.Image",
    "PIL.TiffImagePlugin",
    "PIL.PngImagePlugin",
    "PIL.JpegImagePlugin",
    "PIL.WebPImagePlugin",
    "pillow_heif",
)

# Сторонние библиотеки, которые спамят в prod, но ПОЛЕЗНЫ в dev-режиме DEBUG.
# При LOG_LEVEL >= INFO (prod/staging) фиксируем их на WARNING; при DEBUG —
# позволяют им следовать за root, чтобы разработчик видел SQL и HTTP-вызовы.
#   - sqlalchemy.engine на INFO логирует КАЖДЫЙ SQL-запрос целиком — на проде
#     это ~60% объёма backend-логов и ~40% worker-логов (замерено на реальном
#     прод-слепке: 278K строк в backend, 221K в worker);
#   - httpx на INFO пишет по строке на каждый HTTP-вызов (cron-синк Keycloak
#     каждые 5 минут, email-outbox polling раз в 10с, фотозадачи);
#   - sqlalchemy.pool — сообщения о checkin/checkout соединений.
NOISY_IN_PRODUCTION_LOGGERS: tuple[str, ...] = (
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "httpx",
)

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


# ---------------------------------------------------------------------------
# Кастомные processors.
# ---------------------------------------------------------------------------


def _is_sensitive_key(key: str) -> bool:
    low = key.lower()
    return any(s in low for s in SENSITIVE_KEY_SUBSTRINGS)


def _redact_value(value: Any) -> Any:
    """Рекурсивно маскирует значения в dict/list."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_sensitive_key(k) else _redact_value(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v) for v in value)
    return value


def redact_secrets_processor(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Маскирует все значения с чувствительными ключами (на любом уровне вложенности)."""
    for key in list(event_dict.keys()):
        if _is_sensitive_key(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def _mask_email(value: str) -> str:
    """a***@domain.com — первая буква + домен остаются, середина маскируется."""
    return _EMAIL_RE.sub(r"\1***\2", value)


def _mask_pii_value(value: Any) -> Any:
    """Рекурсивно маскирует email-адреса в строках, dict и list/tuple."""
    if isinstance(value, str):
        return _mask_email(value) if "@" in value else value
    if isinstance(value, dict):
        return {k: _mask_pii_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_mask_pii_value(v) for v in value)
    return value


def mask_pii_processor(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Маскирует email на любом уровне вложенности (строки, dict, list/tuple).

    НЕ трогает поля ``user_id``/``sub``/``keycloak_id`` — они не содержат ``@``.
    """
    for key, value in list(event_dict.items()):
        event_dict[key] = _mask_pii_value(value)
    return event_dict


def truncate_large_values_processor(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Защита от раздувания: строки > MAX_VALUE_SIZE обрезаются, ставится флаг."""
    truncated_keys: list[str] = []
    total = 0
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            total += len(value)
            if len(value) > MAX_VALUE_SIZE:
                event_dict[key] = value[:MAX_VALUE_SIZE] + "...[TRUNCATED]"
                truncated_keys.append(key)
        elif isinstance(value, (bytes, bytearray)):
            event_dict[key] = f"<{type(value).__name__} len={len(value)}>"
            truncated_keys.append(key)
    if truncated_keys:
        event_dict["_truncated_fields"] = truncated_keys
    if total > MAX_STRING_VALUES_IN_EVENT:
        event_dict["_event_oversize"] = True
    return event_dict


def add_service_name_processor(service_name: str) -> Processor:
    def _add(logger: logging.Logger, method_name: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", service_name)
        return event_dict

    return _add


# ---------------------------------------------------------------------------
# Конфигурация.
# ---------------------------------------------------------------------------


def _parse_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    try:
        return int(getattr(logging, level.upper()))
    except AttributeError:
        return logging.INFO


def _apply_noisy_logger_levels(level: int) -> None:
    """Фиксирует шумные сторонние логгеры на WARNING.

    ``NOISY_LIBRARY_LOGGERS`` (PIL и т.п.) приглушаются всегда. SQL/httpx из
    ``NOISY_IN_PRODUCTION_LOGGERS`` — только когда общий уровень выше DEBUG:
    в dev их INFO-вывод полезен для отладки, в prod составляет львиную долю
    бесполезного лог-объёма.
    """
    for noisy in NOISY_LIBRARY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if level > logging.DEBUG:
        for noisy in NOISY_IN_PRODUCTION_LOGGERS:
            logging.getLogger(noisy).setLevel(logging.WARNING)


def configure_logging(
    environment: str = "development",
    log_level: str | int = "INFO",
    service_name: str = "portal-backend",
    force_json: bool | None = None,
) -> None:
    """Настраивает structlog + stdlib logging единообразно.

    :param environment: ``development`` / ``staging`` / ``production``
    :param log_level: уровень логирования (``DEBUG``/``INFO``/``WARNING``/``ERROR``)
    :param service_name: проставляется в каждое событие как ``service=...``
    :param force_json: принудительно JSON-рендер (обычно ``True`` для staging/production).
        Если ``None`` — автоматически: JSON вне dev ИЛИ когда stdout не TTY.
    """
    level = _parse_level(log_level)
    is_tty = getattr(sys.stdout, "isatty", lambda: False)()
    use_json = (
        force_json if force_json is not None else (environment != "development" or not is_tty)
    )

    # Shared processors — applied to structlog and to stdlib loggers via ProcessorFormatter.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service_name_processor(service_name),
        redact_secrets_processor,
        mask_pii_processor,
        truncate_large_values_processor,
    ]

    if use_json:
        shared_processors.append(structlog.processors.dict_tracebacks)
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        shared_processors.append(structlog.processors.StackInfoRenderer())
        renderer = structlog.dev.ConsoleRenderer(colors=is_tty)

    # Для structlog-логгеров: shared + renderer.
    structlog_processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        *shared_processors,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=structlog_processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Единый форматтер для stdlib handler — чтобы чужие логи (uvicorn, sqlalchemy)
    # проходили те же processors, что и structlog-логи.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    for logger_name in MANAGED_LOGGER_NAMES:
        if not logger_name:
            continue
        lg = logging.getLogger(logger_name)
        lg.handlers = [handler]
        lg.propagate = False
        lg.setLevel(level)

    _apply_noisy_logger_levels(level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def restore_managed_loggers(
    level: str | int = "INFO",
    extra_filters: dict[str, list[logging.Filter]] | None = None,
) -> None:
    """Восстанавливает structlog handler на MANAGED-логгерах.

    Сторонние точки входа могут перенастраивать stdlib-логгеры через собственный
    ``logging.config.dictConfig`` уже *после* ``configure_logging``. Критический
    кейс — ARQ CLI (``python -m arq``): он вызывает ``dictConfig`` со своим
    форматом ``%(asctime)s: %(message)s`` и перехватывает логгер ``arq``.
    В результате ARQ-логи идут голым текстом мимо structlog-процессоров
    (редакция секретов, PII-маскинг, JSON-рендер).

    Вызывать в ``on_startup`` воркера (когда ARQ уже выполнил свой ``dictConfig``).

    :param level: целевой уровень (строка или int).
    :param extra_filters: ``{logger_name: [Filter, ...]}`` — навесить доп. фильтры
        на конкретные логгеры (например, для приглушения частых cron).
    """
    numeric = _parse_level(level)
    root_handler = logging.getLogger().handlers[0] if logging.getLogger().handlers else None
    if root_handler is None:
        # Нечего восстанавливать — configure_logging не вызывался.
        return

    extra: dict[str, list[logging.Filter]] = extra_filters or {}
    for logger_name in MANAGED_LOGGER_NAMES:
        if not logger_name:
            continue
        lg = logging.getLogger(logger_name)
        lg.handlers = [root_handler]
        lg.propagate = False
        lg.setLevel(numeric)
        # Сбрасываем фильтры перед повторным навешиванием — иначе при
        # многократных вызовах (restart воркера в tests) они дублировались бы.
        lg.filters = list(extra.get(logger_name, []))

    _apply_noisy_logger_levels(numeric)


# ---------------------------------------------------------------------------
# Удобные хелперы для биндинга контекста.
# ---------------------------------------------------------------------------


def bind_request_context(**kwargs: Any) -> None:
    """Обёртка над structlog.contextvars.bind_contextvars, фильтрует None."""
    structlog.contextvars.bind_contextvars(**{k: v for k, v in kwargs.items() if v is not None})


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()


def set_log_level(level: str) -> None:
    """Применяет новый уровень логирования без перезапуска приложения.

    Обновляет stdlib-логгеры (uvicorn, sqlalchemy, root) и structlog-фильтр.
    Фактическая фильтрация structlog выполняется через filter_by_level processor,
    который проверяет уровень stdlib-логгера — поэтому достаточно обновить stdlib.
    """
    numeric = _parse_level(level)
    logging.getLogger().setLevel(numeric)
    for name in MANAGED_LOGGER_NAMES:
        logging.getLogger(name).setLevel(numeric)
    _apply_noisy_logger_levels(numeric)
