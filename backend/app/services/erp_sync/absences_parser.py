"""Парсер отчёта ERP «Кадровая история сотрудников за период» (1С).

Второй поток ERP-синхронизации — отсутствия в офисе (отпуска/отгулы/болезни/
командировки). В отличие от потока «дни рождения» (фиксированные 3 колонки
ФИО+дата+пол), здесь **иерархическая** структура: блок «шапка → ФИО-строка →
N строк периодов отсутствия».

Структура реального файла (заказчик, 2026-08-04):

::

    Кадровая история сотрудников за период
    <пустая строка>
    Параметры:\tСтандартный период: 01.01.2026 - 31.12.2026
    Отбор:\t"..."
    <пустая строка>
    Сотрудник
    Должность\tПодразделение\tСостояние\tНачало\tОкончание
    Абдуллаев Андрей Ахмедуллаевич              ← строка сотрудника (1 ячейка)
    Начальник базы\tБаза флота\tОтпуск основной\t27.07.2026 0:00:00\t09.08.2026
    Начальник базы\tБаза флота\tДополнительный отпуск\t10.08.2026 0:00:00\t25.08.2026
    Агранов Григорий Дмитриевич                 ← следующий сотрудник
    ...

Формат дат смешанный: колонка «Начало» приходит с временем
(``27.07.2026 0:00:00``), «Окончание» — без (``09.08.2026``). Парсер tolerantен
к обоим (отрезает `` 0:00:00`` если есть).

Формат файла — таб-separated txt/csv (через :mod:`parser_utils`); xlsx/xls
поддерживаются той же инфраструктурой (ячейки → список строк ячеек).

Алгоритм: пропускаем шапку до строки-заголовка колонок; далее чередуем
«строка без парсимой даты = текущий сотрудник» ↔ «строка с датой = период
для текущего сотрудника». Дедуп по (fio_norm, kind, start, end) внутри файла.

Чистые функции — тестируются без БД/Redis (см. ``test_erp_absences_parser``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.core.logging import get_logger
from app.services.erp_sync.parser import SUPPORTED_FORMATS, ParseError, detect_format, normalize_fio
from app.services.erp_sync.parser_utils import (
    extract_text_records,
    extract_xls_records,
    extract_xlsx_records,
)

logger = get_logger(__name__)

# Классификация отсутствий. Согласована с CHECK-ограничением миграции 092 и
# ABSENCE_KIND_VALUES в models/erp_sync.py.
AbsenceKind = Literal[
    "vacation_main",
    "vacation_extra",
    "unpaid_leave",
    "sick",
    "business_trip",
    "day_off_paid",
    "day_off_unpaid",
]

# Маппинг русских «Состояний» из 1С → canonical kind. Матчинг — по contains
# (CI), ключи отсортированы от более специфичных к менее (порядок важен: «отпуск
# основной» содержит «отпуск», но это НЕ «дополнительный»). Первый совпавший
# ключ выигрывает. «Отпуск неоплачиваемый» ловим раньше «отпуск», чтобы не
# свалиться в vacation_main.
_KIND_MAP: list[tuple[str, AbsenceKind]] = [
    ("отпуск неоплачиваемый", "unpaid_leave"),
    ("отпуск основной", "vacation_main"),
    ("дополнительный отпуск", "vacation_extra"),
    ("дополнительные выходные дни неоплачиваемые", "day_off_unpaid"),
    ("дополнительные выходные дни оплачиваемые", "day_off_paid"),
    ("дополнительные выходные дни (оплачиваемые)", "day_off_paid"),
    ("болезнь", "sick"),
    ("командировка", "business_trip"),
]

# «27.07.2026» или «27.07.2026 0:00:00» (1С шлёт колонку «Начало» с временем).
# Время может быть и ненулевым теоретически — отрезаем любое ``HH:MM:SS``.
_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$")


@dataclass
class ParsedAbsenceRow:
    """Один период отсутствия (после нормализации)."""

    fio: str  # display-форма (с заглавных, как в файле) — для отчёта/матчинга
    fio_normalized: str  # lower + ё→е + обрезка скобок — ключ дедупа/матчинга
    kind: AbsenceKind
    position: str | None
    department: str | None
    start_date: date
    end_date: date


@dataclass
class ParsedAbsencesFile:
    """Результат парсинга отчёта отсутствий.

    ``rows`` — дедуплицированные периоды (для матчинга). ``errors`` — строки,
    которые не удалось распознать (некритично: отчёт обрабатывается частично).
    """

    rows: list[ParsedAbsenceRow] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)

    @property
    def total_raw(self) -> int:
        """Сумма всех распознанных случаев (для ``rows_total`` в отчёте)."""
        return len(self.rows) + len(self.errors)


# ── Нормализация полей ──────────────────────────────────────────────────────


def parse_absence_date(raw: str | None) -> date | None:
    """Парсинг даты из колонок «Начало»/«Окончание».

    Принимает как ``ДД.ММ.ГГГГ``, так и ``ДД.ММ.ГГГГ 0:00:00`` (1С шлёт колонку
    «Начало» с временем). ``None`` для невалидных/нестроковых.
    """
    if not isinstance(raw, str):
        return None
    m = _DATE_RE.match(raw)
    if not m:
        return None
    try:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y, mo, d)
    except ValueError:
        return None


def classify_kind(raw_state: str | None) -> AbsenceKind | None:
    """Классифицировать «Состояние» из 1С в canonical kind.

    Матчинг — CI-contains по :data:`_KIND_MAP`. ``None`` если не распознано
    (строка попадёт в errors с указанием исходного состояния).
    """
    if not isinstance(raw_state, str):
        return None
    token = raw_state.strip().lower()
    if not token:
        return None
    for needle, kind in _KIND_MAP:
        if needle in token:
            return kind
    return None


def _has_date_in_row(cells: list[str]) -> bool:
    """Есть ли в строке парсимая дата отсутствия (признак «строка-период»).

    Строка-сотрудник — это одна ячейка с ФИО без дат; строка-период содержит
    дату в колонке «Начало» (index 3 после ФИО-less интерпретации) ИЛИ где-то
    ещё. Надёжный признак: любая ячейка строки парсится как дата отсутствия.
    """
    return any(parse_absence_date(c) is not None for c in cells)


# ── Детект шапки/заголовка ──────────────────────────────────────────────────


def _looks_like_column_header(cells: list[str]) -> bool:
    """Признак строки-заголовка колонок «Должность|Подразделение|...|Начало|Окончание».

    Без этого детектора заголовок попадал бы в errors на каждой выгрузке
    (засорял отчёт). Типовая выгрузка содержит слова «должность» и «начало» в
    шапке; используем оба (AND) для устойчивости.
    """
    joined = " ".join((c or "").lower() for c in cells)
    return "должность" in joined and "начало" in joined


# ── Основной entry-point ────────────────────────────────────────────────────


def parse_absences_attachment(*, filename: str, data: bytes) -> ParsedAbsencesFile:
    """Распарсить вложение отчёта отсутствий.

    Args:
        filename: имя файла (формат определяется по расширению).
        data: сырые байты содержимого.

    Returns:
        :class:`ParsedAbsencesFile` с дедуплицированными ``rows`` и ``errors``.
        Никогда не бросает исключение — всё невалидное попадает в ``errors``,
        чтобы один битый файл не ронял весь импорт.
    """
    fmt = detect_format(filename)
    if fmt is None:
        return ParsedAbsencesFile(
            errors=[
                ParseError(
                    raw=filename[:200],
                    reason=(
                        f"Неподдерживаемый формат файла. Допустимо: {', '.join(SUPPORTED_FORMATS)}."
                    ),
                )
            ]
        )

    try:
        raw_records = _extract_records(fmt, data)
    except Exception as exc:
        logger.warning("erp_sync.absences_parser.extract_failed", filename=filename, error=str(exc))
        return ParsedAbsencesFile(
            errors=[ParseError(raw=filename[:200], reason=f"Ошибка чтения файла: {exc}")]
        )

    return _build_rows(raw_records)


def _extract_records(fmt: Literal["txt", "csv", "xlsx", "xls"], data: bytes) -> list[list[str]]:
    """Диспетчер форматов. Переиспользует общую инфраструктуру parser_utils."""
    if fmt in ("txt", "csv"):
        return extract_text_records(data)
    if fmt == "xlsx":
        return extract_xlsx_records(data)
    if fmt == "xls":
        return extract_xls_records(data)
    raise ValueError(f"Unsupported format: {fmt}")


def _build_rows(records: list[list[str]]) -> ParsedAbsencesFile:
    """Собрать периоды отсутствий из «сырых» строк ячеек.

    Алгоритм — линейный проход с «текущим сотрудником»:

    1. Пропускаем шапку (всё до строки-заголовка колонок).
    2. Строка-заголовок → устанавливаем флаг «данные начались», пропускаем саму.
    3. Строка без даты (только ФИО) → обновляем текущего сотрудника.
    4. Строка с датой → период для текущего сотрудника.
    5. Дедуп по (fio_norm, kind, start, end).

    Если строка-период встречается до первого сотрудника (мусор после шапки) —
    она попадает в errors с понятной причиной.
    """
    rows: list[ParsedAbsenceRow] = []
    errors: list[ParseError] = []
    seen: set[tuple[str, str, date, date]] = set()

    current_fio_display: str | None = None
    current_fio_norm: str | None = None
    data_started = False

    for cells in records:
        if not any((c or "").strip() for c in cells):
            continue

        # 1. Шапка: пропускаем всё до строки-заголовка колонок.
        if not data_started:
            if _looks_like_column_header(cells):
                data_started = True
            continue

        # 2. Определяем тип строки: сотрудник (без даты) или период (с датой).
        if not _has_date_in_row(cells):
            # Строка сотрудника: берём первую непустую ячейку как ФИО.
            fio_raw = next((c.strip() for c in cells if c.strip()), "")
            if not fio_raw:
                continue
            fio_display, fio_norm = normalize_fio(fio_raw)
            if fio_norm:
                current_fio_display = fio_display
                current_fio_norm = fio_norm
            # Нераспознанное ФИО (пустое после нормализации) — пропускаем молча;
            # следующий период без сотрудника уйдёт в errors с понятной причиной.
            continue

        # 3. Строка-период: валидация + (опционально) добавление в rows.
        _process_period_row(
            cells,
            current_fio_display=current_fio_display,
            current_fio_norm=current_fio_norm,
            rows=rows,
            errors=errors,
            seen=seen,
        )

    logger.info(
        "erp_sync.absences_parser.done",
        rows=len(rows),
        errors=len(errors),
    )
    return ParsedAbsencesFile(rows=rows, errors=errors)


def _process_period_row(
    cells: list[str],
    *,
    current_fio_display: str | None,
    current_fio_norm: str | None,
    rows: list[ParsedAbsenceRow],
    errors: list[ParseError],
    seen: set[tuple[str, str, date, date]],
) -> None:
    """Распарсить строку-период и добавить её в ``rows`` либо ``errors``.

    Вынесено из :func:`_build_rows` для снижения цикломатической сложности
    (quality-чек CC≤10). Все ветки валидации здесь; мутирует переданные списки.
    """
    # Колонки приходят в фиксированном порядке после строки-заголовка.
    if len(cells) < 5:
        errors.append(
            ParseError(
                raw=" | ".join(cells)[:200],
                reason=f"Строка периода без полного набора колонок ({len(cells)}/5)",
            )
        )
        return

    position = cells[0].strip() or None
    department = cells[1].strip() or None
    raw_state = cells[2].strip()
    raw_start = cells[3]
    raw_end = cells[4]

    start = parse_absence_date(raw_start)
    end = parse_absence_date(raw_end)
    kind = classify_kind(raw_state)

    reasons: list[str] = []
    if current_fio_norm is None:
        reasons.append("период без предшествующей строки сотрудника")
    if start is None:
        reasons.append(f"дата начала не распознана («{raw_start}»)")
    if end is None:
        reasons.append(f"дата окончания не распознана («{raw_end}»)")
    if kind is None:
        reasons.append(f"состояние не распознано («{raw_state}»)")
    if reasons:
        raw_preview = (
            f"{current_fio_display or '?'} | {raw_state} | {raw_start} | {raw_end}"
        ).strip()[:200]
        errors.append(ParseError(raw=raw_preview, reason="; ".join(reasons)))
        return

    # После guards — все not None, но mypy не сужает через список reasons.
    assert start is not None and end is not None and kind is not None
    assert current_fio_display is not None and current_fio_norm is not None

    # end < start — ошибка данных (1С такого не шлёт, но защитимся).
    if end < start:
        errors.append(
            ParseError(
                raw=f"{current_fio_display} | {raw_state} | {start} > {end}"[:200],
                reason="окончание раньше начала",
            )
        )
        return

    key = (current_fio_norm, kind, start, end)
    if key in seen:
        return  # дедуп идентичных периодов (1С дублирует при нескольких должностях)
    seen.add(key)

    rows.append(
        ParsedAbsenceRow(
            fio=current_fio_display,
            fio_normalized=current_fio_norm,
            kind=kind,
            position=position,
            department=department,
            start_date=start,
            end_date=end,
        )
    )
