"""Письма модуля обучения (kind=learning). Только текст + простой HTML.

Все рассылки идут через общий email_outbox (outbox-паттерн); письмо ставится
в той же транзакции, что и бизнес-операция (§5.3 ТЗ). Код входа здесь —
единственное легальное место его существования в plaintext.

Все строители возвращают ``(subject, body_text, body_html)`` и обязаны
заполнять HTML-часть: SMTP-отправитель кладёт её в multipart/alternative
всегда, и клиенты, предпочитающие HTML (Outlook), показывают письмо,
пустое внутри, если строитель отдал только текст (прод-кейс 2026-09-03).
"""

from __future__ import annotations

from datetime import datetime
from html import escape


def _wrap(title: str, body_html: str) -> str:
    return (
        '<html><body style="font-family:sans-serif;max-width:560px">'
        f'<h2 style="font-size:16px">{title}</h2>{body_html}'
        '<p style="color:#888;font-size:12px">Сообщение отправлено автоматически, '
        "отвечать на него не нужно.</p></body></html>"
    )


def login_code(*, full_name: str, code: str, ttl_minutes: int) -> tuple[str, str, str]:
    """Одноразовый код входа (passwordless). Код — отдельной строкой body_text
    (интеграционные тесты извлекают его регуляркой по всему телу)."""
    subject = "Код для входа на портал обучения"
    text = (
        f"Здравствуйте, {full_name}!\n\n"
        f"Код для входа (действует {ttl_minutes} мин., одноразовый):\n"
        f"{code}\n\n"
        "Если код запрашивали не вы — просто проигнорируйте письмо.\n"
    )
    safe_name = escape(full_name)
    safe_code = escape(code)
    html = _wrap(
        subject,
        f"<p>Здравствуйте, {safe_name}!</p>"
        f"<p>Код для входа (действует {escape(str(ttl_minutes))} мин., одноразовый):</p>"
        '<p style="font-family:monospace;font-size:22px;letter-spacing:4px">'
        f"<b>{safe_code}</b></p>"
        '<p style="color:#888;font-size:12px">Если код запрашивали не вы — '
        "проигнорируйте письмо.</p>",
    )
    return subject, text, html


def enrollment_letter(*, full_name: str, course_title: str, link: str) -> tuple[str, str, str]:
    """Зачисление на курс (ТЗ §5.3 п.2) — сотрудникам и внешним учёткам."""
    subject = f"Вы зачислены на курс «{course_title}»"
    text = (
        f"Уважаемый(ая) {full_name}!\n\n"
        f"Вы зачислены на курс «{course_title}».\n\n"
        "Перейдите по ссылке для прохождения курса:\n"
        f"{link}\n"
    )
    safe_name = escape(full_name)
    safe_title = escape(course_title)
    safe_link = escape(link, quote=True)
    html = _wrap(
        subject,
        f"<p>Уважаемый(ая) {safe_name}!</p>"
        f"<p>Вы зачислены на курс «{safe_title}».</p>"
        f'<p><a href="{safe_link}">Перейти к прохождению курса</a></p>'
        '<p style="color:#888;font-size:12px">Если ссылка не открывается, '
        f"скопируйте её в браузер:<br>{safe_link}</p>",
    )
    return subject, text, html


def deadline_reminder_letter(
    *,
    full_name: str,
    course_title: str,
    deadline_at: datetime,
    remaining: int,
    link: str,
) -> tuple[str, str, str]:
    """Напоминание о близком дедлайне курса (cron learning_deadlines)."""
    date_text = deadline_at.strftime("%d.%m.%Y")
    subject = f"Дедлайн по курсу «{course_title}» — {date_text}"
    text = (
        f"Здравствуйте, {full_name}!\n\n"
        f"Напоминаем: срок прохождения курса «{course_title}» истекает {date_text}.\n"
        f"Осталось пройти элементов: {remaining}.\n"
        f"Ссылка на курс: {link}\n\n"
        "Успешного обучения!\n"
    )
    safe_name = escape(full_name)
    safe_title = escape(course_title)
    safe_link = escape(link, quote=True)
    html = _wrap(
        subject,
        f"<p>Здравствуйте, {safe_name}!</p>"
        f"<p>Напоминаем: срок прохождения курса «{safe_title}» истекает {date_text}.</p>"
        f"<p>Осталось пройти элементов: {escape(str(remaining))}.</p>"
        f'<p><a href="{safe_link}">Перейти к курсу</a></p>'
        '<p style="color:#888;font-size:12px">Если ссылка не открывается, '
        f"скопируйте её в браузер:<br>{safe_link}</p>"
        "<p>Успешного обучения!</p>",
    )
    return subject, text, html
