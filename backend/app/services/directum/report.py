"""HTML-сводка прогона Directum для админов (email).

Клон паттерна :mod:`app.services.erp_sync.report`: f-string + inline styles +
``html.escape`` на каждом значении (темы задач — пользовательские данные).

Разделы (только непустые):

* **Сводка** — задачи / исполнители / уведомлено / пропущено opt-in /
  не сопоставлено / неоднозначно.
* **Уведомлено** — кому ушёл дайджест (ФИО → задач).
* **Пропущено (чат выключен)** — найдены, но ``chat_notifications_enabled``
  выключен — actionable: админ может включить в профиле сотрудника.
* **Не сопоставлено** — ФИО из Directum, которых нет на портале.
* **Неоднозначно** — ФИО → несколько кандидатов (однофамильцы).
* **Matrix недоступен** — бот выключен/не настроен, уведомления не ушли.
* **Ошибка** — для failed-прогонов ( причина сбоя OData).
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any

from app.models.directum import DirectumRun

_ACCENT = "#0969da"
_TEXT = "#24292f"
_MUTED = "#57606a"
_BORDER = "#d0d7de"
_ERR_BG = "#ffebe9"


def build_subject(run: DirectumRun) -> str:
    """Тема письма: «Directum: 12 задач, 8 уведомлено» / «… требуют внимания»."""
    if run.status == "failed":
        return "⚠ Directum: сбой прогона"
    problems = (run.users_unmatched or 0) + (run.users_ambiguous or 0)
    base = (
        f"Directum: просроченные задачи — {run.tasks_total or 0} задач, "
        f"уведомлено {run.users_notified or 0}"
    )
    if problems:
        return f"{base}, {problems} требуют внимания"
    return base


def build_report_bodies(run: DirectumRun) -> tuple[str, str]:
    """``(html, plain)`` тела сводки по результатам ``run``."""
    report: dict[str, Any] = run.report or {}
    notified: list[dict] = report.get("notified", [])
    skipped_opt_in: list[dict] = report.get("skipped_opt_in", [])
    unmatched: list[dict] = report.get("unmatched", [])
    ambiguous: list[dict] = report.get("ambiguous", [])
    matrix_disabled: bool = bool(report.get("matrix_disabled"))
    error: str | None = report.get("error")

    html_parts: list[str] = []
    plain_parts: list[str] = []

    html_parts.append(f'<div style="font-family:Arial,sans-serif;color:{_TEXT};line-height:1.5">')
    plain_parts.append("Directum: просроченные задачи")

    started = _fmt_dt(run.started_at)
    html_parts.append(
        f'<p style="margin:0 0 12px">Прогон от <strong>{html.escape(started)}</strong> '
        f"(запуск #{run.id}, {html.escape(_triggered_by_label(run.triggered_by))}).</p>"
    )
    plain_parts.append(f"Прогон от {started} (запуск #{run.id}).")

    html_parts.append(_summary_table(run))
    plain_parts.append(_summary_plain(run))

    if error:
        html_parts.append(
            f'<div style="margin-bottom:16px;padding:8px 12px;background:{_ERR_BG};'
            f'border-radius:6px">Ошибка: {html.escape(error)}</div>'
        )
        plain_parts.append(f"Ошибка: {error}")

    if matrix_disabled:
        hint = (
            "Matrix-бот выключен или не настроен — уведомления не отправлены. "
            "Проверьте админку → «Корпоративный чат»."
        )
        html_parts.append(
            f'<div style="margin-bottom:16px;padding:8px 12px;background:{_ERR_BG};'
            f'border-radius:6px">{html.escape(hint)}</div>'
        )
        plain_parts.append(hint)

    if notified:
        html_parts.append(_section(f"Уведомлено ({len(notified)})", _pairs_html(notified)))
        plain_parts.append(_section_plain(f"Уведомлено ({len(notified)})", _pairs_plain(notified)))

    if skipped_opt_in:
        title = f"Пропущено — чат выключен ({len(skipped_opt_in)})"
        hint = "Сотрудник найден, но у него выключены чат-уведомления. Включить: "
        "профиль сотрудника → уведомления (или сам сотрудник в своём профиле)."
        inner = _pairs_html(skipped_opt_in) + (
            f'<p style="margin:8px 0 0;color:{_MUTED};font-size:0.9em">{html.escape(hint)}</p>'
        )
        html_parts.append(_section(title, inner))
        plain_parts.append(_section_plain(title, _pairs_plain(skipped_opt_in) + f"\n{hint}"))

    if unmatched:
        html_parts.append(_section(f"Не сопоставлено ({len(unmatched)})", _pairs_html(unmatched)))
        plain_parts.append(
            _section_plain(f"Не сопоставлено ({len(unmatched)})", _pairs_plain(unmatched))
        )

    if ambiguous:
        html_parts.append(_section(f"Неоднозначно ({len(ambiguous)})", _ambiguous_html(ambiguous)))
        plain_parts.append(
            _section_plain(f"Неоднозначно ({len(ambiguous)})", _ambiguous_plain(ambiguous))
        )

    html_parts.append(
        f'<p style="margin-top:16px;color:{_MUTED};font-size:0.9em">'
        "Это автоматическое уведомление интеграции Directum. Ответ не требуется."
        "</p></div>"
    )
    return "\n".join(html_parts), "\n".join(plain_parts)


# ── Сводка ───────────────────────────────────────────────────────────────────


def _summary_table(run: DirectumRun) -> str:
    rows = [
        ("Просроченных задач", run.tasks_total),
        ("Исполнителей", run.performers_total),
        ("Уведомлено в Matrix", run.users_notified),
        ("Пропущено (чат выключен)", run.users_skipped_opt_in),
        ("Не сопоставлено", run.users_unmatched),
        ("Неоднозначно", run.users_ambiguous),
        ("Ошибок", run.errors),
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


def _summary_plain(run: DirectumRun) -> str:
    return (
        f"Задач: {run.tasks_total}, исполнителей: {run.performers_total}, "
        f"уведомлено: {run.users_notified}, чат выключен: {run.users_skipped_opt_in}, "
        f"не сопоставлено: {run.users_unmatched}, неоднозначно: {run.users_ambiguous}, "
        f"ошибок: {run.errors}."
    )


# ── Секции ───────────────────────────────────────────────────────────────────


def _section(title: str, inner_html: str) -> str:
    return (
        f'<h3 style="margin:16px 0 8px;font-size:14px;color:{_TEXT}">{html.escape(title)}</h3>'
        + inner_html
    )


def _section_plain(title: str, body: str) -> str:
    return f"\n{title}:\n{body}"


def _pairs_html(items: list[dict]) -> str:
    """Список «ФИО → N задач» (notified / skipped_opt_in / unmatched)."""
    out = ['<table cellpadding="4" cellspacing="0" border="0">']
    for it in items:
        fio = html.escape(str(it.get("fio", "")))
        tasks = it.get("tasks")
        right = f"→ {tasks} задач(и)" if tasks is not None else ""
        out.append(f"<tr><td>{fio}</td><td style='color:{_MUTED}'>{right}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _pairs_plain(items: list[dict]) -> str:
    return "\n".join(
        f"- {it.get('fio', '')}"
        + (f" ({it.get('tasks')} задач)" if it.get("tasks") is not None else "")
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


# ── Утилиты ──────────────────────────────────────────────────────────────────


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%d.%m.%Y %H:%M")


def _triggered_by_label(value: str) -> str:
    return {"cron": "автоматически", "manual": "вручную"}.get(value, value)
