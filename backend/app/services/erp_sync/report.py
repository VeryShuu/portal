"""HTML-отчёт админу о результате ERP-импорта.

Клон паттерна ``helpdesk/digest.py::build_digest_bodies``: f-string + inline
styles (email-клиенты игнорируют CSS-классы) + ``html.escape`` на каждом
пользовательском значении (ФИО может содержать ``<script>`` — XSS-защита).

Возвращает ``(html, plain)`` — HTML для письма, plain-text для fallback'а
(некоторые клиенты показывают только text).

Разделы отчёта (только непустые):

* **Сводка** — цифры (всего / обновлено / не сопоставлено / неоднозначно /
  конфликты / ошибки).
* **Обновлено** — список изменённых пользователей с old→new diff по полям.
* **Не сопоставлено** — ФИО из ERP, которых нет на портале.
* **Неоднозначно** — ФИО → до 5 кандидатов (однофамильцы).
* **Конфликты в файле** — одно ФИО с разными датами/полом.
* **Ошибки** — строки, которые не распарсились (с причиной).

Тема письма строится отдельно в :func:`build_subject` — чтобы админ по теме
понял, есть ли проблемы («5 обновлено, 3 требуют внимания»).
"""

from __future__ import annotations

import html
from datetime import UTC, date, datetime
from typing import Any

from app.models.erp_sync import ErpSyncRun

# Палитра (инлайн, как в helpdesk-дайджесте).
_ACCENT = "#0969da"
_TEXT = "#24292f"
_MUTED = "#57606a"
_BORDER = "#d0d7de"
_WARN_BG = "#fff8c5"
_ERR_BG = "#ffebe9"
_OK_BG = "#dafbe1"


def build_subject(run: ErpSyncRun) -> str:
    """Тема письма: «ERP-синхронизация: N обновлено, M требуют внимания»."""
    problems = (
        (run.rows_unmatched or 0)
        + (run.rows_ambiguous or 0)
        + (run.conflicts or 0)
        + (run.errors or 0)
    )
    updated = run.rows_updated or 0
    if problems:
        return f"ERP-синхронизация: {updated} обновлено, {problems} требуют внимания"
    return f"ERP-синхронизация завершена: {updated} обновлено"


def build_report_bodies(run: ErpSyncRun) -> tuple[str, str]:
    """Построить ``(html, plain)`` тела письма-отчёта по результатам ``run``.

    ``run.report`` (JSONB) содержит списки changed/unmatched/ambiguous/
    conflicts/errors (структура зафиксирована в :mod:`importer`).
    """
    report: dict[str, Any] = run.report or {}
    changed: list[dict] = report.get("changed", [])
    unmatched: list[dict] = report.get("unmatched", [])
    ambiguous: list[dict] = report.get("ambiguous", [])
    conflicts: list[dict] = report.get("conflicts", [])
    errors: list[dict] = report.get("errors", [])

    html_parts: list[str] = []
    plain_parts: list[str] = []

    html_parts.append(f'<div style="font-family:Arial,sans-serif;color:{_TEXT};line-height:1.5">')
    plain_parts.append("ERP-синхронизация сотрудников")

    # Сводка.
    started = _fmt_dt(run.started_at)
    html_parts.append(
        f'<p style="margin:0 0 12px">Импорт от <strong>{html.escape(started)}</strong> '
        f"(запуск #{run.id}, {html.escape(_triggered_by_label(run.triggered_by))}).</p>"
    )
    plain_parts.append(f"Импорт от {started} (запуск #{run.id}).")

    html_parts.append(_summary_table(run))
    plain_parts.append(_summary_plain(run))

    if changed:
        html_parts.append(_section(f"Обновлено ({len(changed)})", _changed_html(changed)))
        plain_parts.append(_section_plain(f"Обновлено ({len(changed)})", _changed_plain(changed)))

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

    if conflicts:
        html_parts.append(
            _section(f"Конфликты в файле ({len(conflicts)})", _conflicts_html(conflicts))
        )
        plain_parts.append(
            _section_plain(f"Конфликты в файле ({len(conflicts)})", _conflicts_plain(conflicts))
        )

    if errors:
        html_parts.append(_section(f"Ошибки парсинга ({len(errors)})", _errors_html(errors)))
        plain_parts.append(
            _section_plain(f"Ошибки парсинга ({len(errors)})", _errors_plain(errors))
        )

    html_parts.append(
        f'<p style="margin-top:16px;color:{_MUTED};font-size:0.9em">'
        "Это автоматическое уведомление ERP-синхронизации портала. "
        "Ответ на него не требуется."
        "</p></div>"
    )

    return "\n".join(html_parts), "\n".join(plain_parts)


# ── Сводка ───────────────────────────────────────────────────────────────────


def _summary_table(run: ErpSyncRun) -> str:
    rows = [
        ("Всего строк в файле", run.rows_total),
        ("Сопоставлено", run.rows_matched),
        ("Обновлено", run.rows_updated),
        ("Не сопоставлено", run.rows_unmatched),
        ("Неоднозначно", run.rows_ambiguous),
        ("Конфликты в файле", run.conflicts),
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


def _summary_plain(run: ErpSyncRun) -> str:
    return (
        f"Всего: {run.rows_total}, сопоставлено: {run.rows_matched}, "
        f"обновлено: {run.rows_updated}, не сопоставлено: {run.rows_unmatched}, "
        f"неоднозначно: {run.rows_ambiguous}, конфликты: {run.conflicts}, "
        f"ошибки: {run.errors}."
    )


# ── Секции ───────────────────────────────────────────────────────────────────


def _section(title: str, inner_html: str) -> str:
    return (
        f'<h3 style="margin:16px 0 8px;font-size:14px;color:{_TEXT}">{html.escape(title)}</h3>'
        + inner_html
    )


def _section_plain(title: str, body: str) -> str:
    return f"\n{title}:\n{body}"


def _changed_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0" style="width:100%">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        out.append(f'<tr><td colspan="2" style="color:{_ACCENT};font-weight:600">{fio}</td></tr>')
        for field, diff in it.get("fields", []).items():
            label = html.escape(_field_label(field))
            old = html.escape(_fmt_value(diff.get("old")))
            new = html.escape(_fmt_value(diff.get("new")))
            out.append(
                f"<tr><td style='color:{_MUTED};padding-left:16px'>{label}</td>"
                f"<td><s style='color:{_MUTED}'>{old}</s> → <strong>{new}</strong></td></tr>"
            )
    out.append("</table>")
    return "".join(out)


def _changed_plain(items: list[dict]) -> str:
    lines = []
    for it in items:
        lines.append(f"- {it.get('fio', '')}")
        for field, diff in it.get("fields", []).items():
            lines.append(f"    {_field_label(field)}: {diff.get('old')} → {diff.get('new')}")
    return "\n".join(lines)


def _unmatched_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        bd = html.escape(str(it.get("birth_date", "")))
        g = html.escape(_gender_label(it.get("gender")))
        out.append(
            "<tr>"
            f"<td>{fio}</td>"
            f"<td style='color:{_MUTED}'>{bd}</td>"
            f"<td style='color:{_MUTED}'>{g}</td>"
            "</tr>"
        )
    out.append("</table>")
    return "".join(out)


def _unmatched_plain(items: list[dict]) -> str:
    return "\n".join(
        f"- {it.get('fio', '')} ({it.get('birth_date', '')}, {_gender_label(it.get('gender'))})"
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


def _conflicts_html(items: list[dict]) -> str:
    out = ['<table cellpadding="4" cellspacing="0" border="0">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        variants = "; ".join(
            f"{html.escape(str(v.get('birth_date', '')))}/"
            f"{html.escape(_gender_label(v.get('gender')))}"
            for v in it.get("variants", [])
        )
        out.append(f"<tr><td>{fio}</td><td style='color:{_MUTED}'>{variants}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _conflicts_plain(items: list[dict]) -> str:
    return "\n".join(
        f"- {it.get('fio', '')}: "
        + "; ".join(
            f"{v.get('birth_date', '')}/{_gender_label(v.get('gender'))}"
            for v in it.get("variants", [])
        )
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


def _field_label(field: str) -> str:
    return {"birth_date": "Дата рождения", "gender": "Пол"}.get(field, field)


def _gender_label(value: Any) -> str:
    if value == "male":
        return "Мужской"
    if value == "female":
        return "Женский"
    return str(value) if value else ""


def _fmt_value(value: Any) -> str:
    """Форматирование значения поля для diff (date → ISO, None → «—»)."""
    if value is None:
        return "—"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d.%m.%Y %H:%M")


def _triggered_by_label(value: str) -> str:
    return {"cron": "автоматически", "manual": "вручную"}.get(value, value)
