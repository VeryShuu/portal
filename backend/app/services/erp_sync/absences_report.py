"""HTML-отчёт админу о результате импорта отсутствий.

Клон :mod:`report` (поток дней рождения), но:

* раздел «Обновлено» (changed с diff old→new) заменён на «Добавлено» (inserted —
  full-replace, не upsert, diff old→new не имеет смысла);
* отсутствует раздел «Конфликты в файле» (парсер отсутствий не детектит
  конфликты — одинаковые периоды просто дедуплицируются);
* сводка содержит ``rows_inserted`` вместо ``rows_updated``.

f-string + inline styles (email-клиенты игнорируют CSS-классы) + ``html.escape``
на каждом пользовательском значении (XSS-защита, как в helpdesk-дайджесте).
Возвращает ``(html, plain)``.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any

from app.models.erp_sync import ErpAbsencesRun

# Палитра (инлайн, как в report.py).
_ACCENT = "#0969da"
_TEXT = "#24292f"
_MUTED = "#57606a"
_BORDER = "#d0d7de"

# Человекочитаемые названия типов отсутствий (согласованы с ABSENCE_KIND_VALUES
# в models/erp_sync.py и absences_parser._KIND_MAP).
_KIND_LABELS = {
    "vacation_main": "Отпуск основной",
    "vacation_extra": "Дополнительный отпуск",
    "unpaid_leave": "Отпуск неоплачиваемый",
    "sick": "Болезнь",
    "business_trip": "Командировка",
    "day_off_paid": "Доп. выходные (оплачиваемые)",
    "day_off_unpaid": "Доп. выходные (неоплачиваемые)",
}


def build_absences_subject(run: ErpAbsencesRun) -> str:
    """Тема письма: «Отсутствия: N добавлено, M требуют внимания»."""
    problems = (run.rows_unmatched or 0) + (run.rows_ambiguous or 0) + (run.errors or 0)
    inserted = run.rows_inserted or 0
    status_label = {
        "failed": "ОШИБКА: ",
        "skipped": "пропуск: ",
    }.get(run.status, "")
    if problems:
        return f"{status_label}ERP-отсутствия: {inserted} добавлено, {problems} требуют внимания"
    return f"{status_label}ERP-отсутствия: импорт завершён, {inserted} добавлено"


def build_absences_report_bodies(run: ErpAbsencesRun) -> tuple[str, str]:
    """Построить ``(html, plain)`` тела письма-отчёта по результатам ``run``.

    ``run.report`` (JSONB) содержит списки inserted/unmatched/ambiguous/errors
    (структура зафиксирована в :mod:`absences_importer`).
    """
    report: dict[str, Any] = run.report or {}
    inserted: list[dict] = report.get("inserted", [])
    unmatched: list[dict] = report.get("unmatched", [])
    ambiguous: list[dict] = report.get("ambiguous", [])
    errors: list[dict] = report.get("errors", [])

    html_parts: list[str] = []
    plain_parts: list[str] = []

    html_parts.append(f'<div style="font-family:Arial,sans-serif;color:{_TEXT};line-height:1.5">')
    plain_parts.append("ERP-отсутствия сотрудников")

    # Сводка.
    started = _fmt_dt(run.started_at)
    html_parts.append(
        f'<p style="margin:0 0 12px">Импорт от <strong>{html.escape(started)}</strong> '
        f"(запуск #{run.id}, {html.escape(_triggered_by_label(run.triggered_by))}).</p>"
    )
    plain_parts.append(f"Импорт от {started} (запуск #{run.id}).")

    html_parts.append(_summary_table(run))
    plain_parts.append(_summary_plain(run))

    if inserted:
        html_parts.append(_section(f"Добавлено ({len(inserted)})", _inserted_html(inserted)))
        plain_parts.append(
            _section_plain(f"Добавлено ({len(inserted)})", _inserted_plain(inserted))
        )

    if unmatched:
        html_parts.append(
            _section(f"Не сопоставлено ({len(unmatched)})", _unmatched_html(unmatched))
        )
        plain_parts.append(
            _section_plain(f"Не сопоставлено ({len(unmatched)})", _unmatched_plain(unmatched))
        )

    if ambiguous:
        html_parts.append(_section(f"Неоднозначно ({len(ambiguous)})", _ambiguous_html(ambiguous)))
        plain_parts.append(
            _section_plain(f"Неоднозначно ({len(ambiguous)})", _ambiguous_plain(ambiguous))
        )

    if errors:
        html_parts.append(_section(f"Ошибки парсинга ({len(errors)})", _errors_html(errors)))
        plain_parts.append(
            _section_plain(f"Ошибки парсинга ({len(errors)})", _errors_plain(errors))
        )

    html_parts.append(
        f'<p style="margin-top:16px;color:{_MUTED};font-size:0.9em">'
        "Это автоматическое уведомление ERP-синхронизации отсутствий портала. "
        "Ответ на него не требуется."
        "</p></div>"
    )

    return "\n".join(html_parts), "\n".join(plain_parts)


# ── Сводка ───────────────────────────────────────────────────────────────────


def _summary_table(run: ErpAbsencesRun) -> str:
    rows = [
        ("Всего строк в файле", run.rows_total),
        ("Сопоставлено", run.rows_matched),
        ("Добавлено", run.rows_inserted),
        ("Не сопоставлено", run.rows_unmatched),
        ("Неоднозначно", run.rows_ambiguous),
        ("Ошибки парсинга", run.errors),
    ]
    body = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:{_MUTED}'>{html.escape(label)}</td>"
        f"<td style='padding:4px 0'><strong>{val if val is not None else '—'}</strong></td></tr>"
        for label, val in rows
    )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-bottom:16px;border:1px solid {_BORDER};border-radius:6px;'
        f'padding:8px 12px">{body}</table>'
    )


def _summary_plain(run: ErpAbsencesRun) -> str:
    return (
        f"Всего: {run.rows_total}, сопоставлено: {run.rows_matched}, "
        f"добавлено: {run.rows_inserted}, не сопоставлено: {run.rows_unmatched}, "
        f"неоднозначно: {run.rows_ambiguous}, ошибки: {run.errors}."
    )


# ── Секции ───────────────────────────────────────────────────────────────────


def _section(title: str, inner_html: str) -> str:
    return (
        f'<h3 style="margin:16px 0 8px;font-size:14px;color:{_TEXT}">{html.escape(title)}</h3>'
        + inner_html
    )


def _section_plain(title: str, body: str) -> str:
    return f"\n{title}:\n{body}"


def _inserted_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0" style="width:100%">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        kind = html.escape(_kind_label(it.get("kind")))
        period = html.escape(_fmt_period(it.get("start_date"), it.get("end_date")))
        position = html.escape(str(it.get("position") or ""))
        out.append(
            f"<tr>"
            f'<td colspan="2" style="color:{_ACCENT};font-weight:600">{fio}</td></tr>'
            f"<tr><td style='color:{_MUTED};padding-left:16px'>{kind}</td>"
            f"<td>{period}"
            + (
                f"<br><span style='color:{_MUTED};font-size:0.9em'>{position}</span>"
                if position
                else ""
            )
            + "</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


def _inserted_plain(items: list[dict]) -> str:
    lines = []
    for it in items:
        kind = _kind_label(it.get("kind"))
        period = _fmt_period(it.get("start_date"), it.get("end_date"))
        lines.append(f"- {it.get('fio', '')} ({kind}, {period})")
    return "\n".join(lines)


def _unmatched_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        kind = html.escape(_kind_label(it.get("kind")))
        period = html.escape(_fmt_period(it.get("start_date"), it.get("end_date")))
        out.append(
            f"<tr><td>{fio}</td>"
            f"<td style='color:{_MUTED}'>{kind}</td>"
            f"<td style='color:{_MUTED}'>{period}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


def _unmatched_plain(items: list[dict]) -> str:
    return "\n".join(
        f"- {it.get('fio', '')} ({_kind_label(it.get('kind'))}, "
        f"{_fmt_period(it.get('start_date'), it.get('end_date'))})"
        for it in items
    )


def _ambiguous_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        cands = ", ".join(
            html.escape(str(c.get("full_name", ""))) for c in it.get("candidates", [])
        )
        out.append(f"<tr><td>{fio}</td><td style='color:{_MUTED}'>→ {cands}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _ambiguous_plain(items: list[dict]) -> str:
    return "\n".join(
        f"- {it.get('fio', '')} → "
        + ", ".join(str(c.get("full_name", "")) for c in it.get("candidates", []))
        for it in items
    )


def _errors_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0">']
    for it in items:
        raw = html.escape(str(it.get("raw", "")))[:120]
        reason = html.escape(str(it.get("reason", "")))
        out.append(f"<tr><td><code>{raw}</code></td><td style='color:{_MUTED}'>{reason}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _errors_plain(items: list[dict]) -> str:
    return "\n".join(f"- {it.get('raw', '')[:120]} — {it.get('reason', '')}" for it in items)


# ── Утилиты форматирования ───────────────────────────────────────────────────


def _kind_label(value: Any) -> str:
    return _KIND_LABELS.get(str(value) if value else "", str(value) if value else "")


def _fmt_period(start: Any, end: Any) -> str:
    """Формат периода: «10.08.2026 – 20.08.2026» (или «10.08.2026» для однодневного)."""
    s = _iso_to_ru(start)
    e = _iso_to_ru(end)
    if not s:
        return e or "—"
    if not e:
        return s
    if s == e:
        return s  # однодневный отгул
    return f"{s} – {e}"


def _iso_to_ru(value: Any) -> str:
    """ISO-строка (2026-08-10) → ru-формат (10.08.2026). Для date/str/None."""
    if value is None:
        return ""
    s = str(value)
    try:
        parts = s.split("-")
        if len(parts) == 3:
            y, m, d = parts
            return f"{d}.{m}.{y}"
    except Exception:
        pass
    return s


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d.%m.%Y %H:%M")


def _triggered_by_label(value: str) -> str:
    return {"cron": "автоматически", "manual": "вручную"}.get(value, value)
