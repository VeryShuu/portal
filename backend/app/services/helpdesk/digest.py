"""Daily digest email for helpdesk agents (ТЗ: ежедневная сводка по заявкам).

Раз в день (cron-driven ``send_helpdesk_digest`` worker) каждый активный
helpdesk-агент получает email-сводку с двумя блоками:

1. **Личные тикеты** — назначенные на агента, в статусе ``open``/``pending``:
   ссылка на тикет, автор (ФИО/email), сколько дней в работе (от
   ``assigned_at``).
2. **Неназначенные** — ``assignee_user_id IS NULL`` в статусах
   ``new``/``open``/``pending``: общий блок, одинаковый во всех сводках
   (дней в работе — от ``created_at``, т.к. ``assigned_at`` пуст).

Письмо отправляется через транзакционный outbox ``kind=generic`` (не
``helpdesk``) — дайджест не входит в email-тред конкретного тикета, ему не
нужны threading-заголовки (``Message-ID``/``References``/``Reply-To``) и не
требуется настроенный mailbox (SMTP-настройки общие). Абсолютная ссылка на
тикет строится из ``portal_base_url`` (SystemSettings, runtime).

Правила:
- Агент без личных тикетов **и** без неназначенных в системе — письмо не
  получает (не спамим пустых).
- Расписание (час/минута/будни-ежедневно/enabled) — в singleton
  ``helpdesk_digest_settings`` (миграция 076), проверяется в воркере через
  ``should_send_today`` + Redis-ключ ``DIGEST_LAST_SENT_KEY`` (идемпотентность
  внутри дня).
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.helpdesk import HelpdeskAgent, HelpdeskTicket
from app.models.user import User
from app.services.email_outbox import KIND_GENERIC, enqueue_outbox_email

logger = get_logger(__name__)

# Redis-ключ даты последней отправки сводки (идемпотентность внутри дня —
# защита от двойного запуска при рестарте воркера). По образцу
# ``helpdesk:imap:last_poll_at`` (см. ``ingress.py``).
DIGEST_LAST_SENT_KEY = "helpdesk:digest:last_sent_at"

# Статусы «в работе» у ответственного (активные, не завершённые).
ASSIGNED_ACTIVE_STATUSES: tuple[str, ...] = ("open", "pending")
# Статусы неназначенных тикетов (включая ``new`` — он по определению ничей).
UNASSIGNED_ACTIVE_STATUSES: tuple[str, ...] = ("new", "open", "pending")


@dataclass(frozen=True, slots=True)
class DigestTicketRow:
    """Одна строка тикета в сводке (личная или из общего блока)."""

    ticket_id: uuid.UUID
    number: int
    subject: str
    author_display: str  # ФИО заявителя, fallback на email
    days_in_work: int  # полные дни от assigned_at (личные) / created_at (общие)


@dataclass(frozen=True, slots=True)
class DigestData:
    """Данные для одного письма-сводки: личные тикеты агента + общий блок
    неназначенных. Общий блок считается «пустым для агента» только если он
    пуст в системе (один запрос на всех)."""

    assigned: list[DigestTicketRow]
    unassigned: list[DigestTicketRow]

    def is_empty(self) -> bool:
        return not self.assigned and not self.unassigned


# ---------------------------------------------------------------------------
# Schedule check (pure, unit-testable without DB).
# ---------------------------------------------------------------------------


def should_send_today(
    now: datetime,
    *,
    enabled: bool,
    digest_hour: int,
    digest_minute: int,
    digest_schedule: str,
) -> bool:
    """Должна ли сводка отправиться в данный запуск cron.

    Воркер запускается ежечасно (``minute=0``); здесь — точная проверка:
    ``enabled`` + день недели (``weekdays`` → пн–пт, ``daily`` → всегда) +
    совпадение часа и минуты. ``now`` ожидается в UTC (воркер работает в UTC).

    ``datetime.weekday()``: 0=пн .. 6=вс → будни это 0..4.
    """
    if not enabled:
        return False
    if digest_schedule == "weekdays" and now.weekday() >= 5:
        return False
    return now.hour == digest_hour and now.minute == digest_minute


def already_sent_today(last_sent: str | None, *, now: datetime) -> bool:
    """Идемпотентность: сводка уже слалась сегодня (та же календарная дата в
    UTC). ``last_sent`` — ISO-строка из ``DIGEST_LAST_SENT_KEY``."""
    if not last_sent:
        return False
    try:
        last_dt = datetime.fromisoformat(last_sent)
    except ValueError:
        return False  # битое значение — идём дальше
    return last_dt.date() == now.date()


# ---------------------------------------------------------------------------
# Data collection.
# ---------------------------------------------------------------------------


def _author_display(name: str | None, email: str) -> str:
    return name or email


async def collect_assigned(
    db: AsyncSession, *, agent_id: uuid.UUID, now: datetime
) -> list[DigestTicketRow]:
    """Личные тикеты агента (``open``/``pending``). Дней в работе — от
    ``assigned_at`` (сFallback на ``created_at`` если ``assigned_at`` пуст,
    хотя по инварианту назначенный тикет всегда имеет ``assigned_at``)."""
    age_expr = (
        func.extract(
            "epoch",
            now - func.coalesce(HelpdeskTicket.assigned_at, HelpdeskTicket.created_at),
        )
        / 86400.0
    )
    res = await db.execute(
        select(
            HelpdeskTicket.id,
            HelpdeskTicket.number,
            HelpdeskTicket.subject,
            HelpdeskTicket.requester_name,
            HelpdeskTicket.requester_email,
            age_expr.label("days"),
        )
        .where(
            HelpdeskTicket.assignee_user_id == agent_id,
            HelpdeskTicket.status.in_(ASSIGNED_ACTIVE_STATUSES),
        )
        .order_by(HelpdeskTicket.assigned_at.asc())
    )
    rows = res.all()
    return [
        DigestTicketRow(
            ticket_id=r.id,
            number=r.number,
            subject=r.subject,
            author_display=_author_display(r.requester_name, r.requester_email),
            days_in_work=int(r.days),
        )
        for r in rows
    ]


async def collect_unassigned(db: AsyncSession, *, now: datetime) -> list[DigestTicketRow]:
    """Неназначенные тикеты (``new``/``open``/``pending``). Дней в работе — от
    ``created_at`` (``assigned_at`` пуст). Один запрос на всех — общий блок."""
    age_expr = func.extract("epoch", now - HelpdeskTicket.created_at) / 86400.0
    res = await db.execute(
        select(
            HelpdeskTicket.id,
            HelpdeskTicket.number,
            HelpdeskTicket.subject,
            HelpdeskTicket.requester_name,
            HelpdeskTicket.requester_email,
            age_expr.label("days"),
        )
        .where(
            HelpdeskTicket.assignee_user_id.is_(None),
            HelpdeskTicket.status.in_(UNASSIGNED_ACTIVE_STATUSES),
        )
        .order_by(HelpdeskTicket.created_at.asc())
    )
    rows = res.all()
    return [
        DigestTicketRow(
            ticket_id=r.id,
            number=r.number,
            subject=r.subject,
            author_display=_author_display(r.requester_name, r.requester_email),
            days_in_work=int(r.days),
        )
        for r in rows
    ]


async def _load_active_agents(db: AsyncSession) -> list[User]:
    """Все helpdesk-агенты с живым аккаунтом (``deleted_at IS NULL``).
    Каждый получает персональную сводку. JOIN users — единый источник прав."""
    res = await db.execute(
        select(User)
        .join(HelpdeskAgent, HelpdeskAgent.user_id == User.id)
        .where(User.deleted_at.is_(None))
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Email body builders (pure, unit-testable).
# ---------------------------------------------------------------------------


def build_digest_subject() -> str:
    """Тема письма-сводки. Фиксированная — не привязана к конкретному тикету,
    поэтому без ``[#TKT-{number}]`` токена (это не часть треда тикета)."""
    return "Ежедневная сводка заявок техподдержки"


def _normalize_base_url(url: str) -> str:
    """Убирает trailing-slash, чтобы конкатенация с путём не давала ``//``."""
    return url.rstrip("/")


def _ticket_link(portal_base_url: str, ticket_id: uuid.UUID) -> str:
    return f"{_normalize_base_url(portal_base_url)}/helpdesk/tickets/{ticket_id}"


def _plural_days(n: int) -> str:
    """Русская плюрализация: «1 день», «2 дня», «5 дней»."""
    if n % 10 == 1 and n % 100 != 11:
        word = "день"
    elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        word = "дня"
    else:
        word = "дней"
    return f"{n} {word}"


def build_digest_bodies(agent: User, data: DigestData, *, portal_base_url: str) -> tuple[str, str]:
    """Тела письма-сводки (plain, html).

    Структура: приветствие (ФИО агента) → блок «Ваши заявки» → блок
    «Неназначенные». Пустые секции не выводятся. Все пользовательские данные
    (тема/имя заявителя) экранируются через ``html.escape`` (XSS-защита, по
    образцу ``build_assigned_email_bodies``). Абсолютная ссылка строится из
    ``portal_base_url``.
    """
    agent_name_esc = html.escape(agent.full_name or agent.email)

    plain_lines: list[str] = [
        f"Здравствуйте, {agent.full_name or agent.email}!",
        "",
    ]

    html_parts: list[str] = [
        '<div style="font-family: sans-serif; color: #333; line-height: 1.5;">',
        f"<p>Здравствуйте, <strong>{agent_name_esc}</strong>!</p>",
    ]

    # --- Block 1: assigned tickets ---
    if data.assigned:
        plain_lines.append("Ваши заявки в работе:")
        html_parts.append('<h3 style="margin-bottom:8px">Ваши заявки в работе</h3>')
        html_parts.append('<table cellpadding="4" cellspacing="0" border="0">')
        for row in data.assigned:
            link = _ticket_link(portal_base_url, row.ticket_id)
            subject_esc = html.escape(row.subject)
            author_esc = html.escape(row.author_display)
            days = _plural_days(row.days_in_work)
            plain_lines.append(
                f"- #{row.number} «{row.subject}» — {row.author_display}, в работе {days}\n  {link}"
            )
            html_parts.append(
                "<tr>"
                f'<td style="vertical-align:top"><strong>#{row.number}</strong></td>'
                f"<td>«{subject_esc}»<br>"
                f'<span style="color:#666;font-size:0.9em">{author_esc}, в работе {days}</span><br>'
                f'<a href="{link}">Открыть заявку</a>'
                "</td>"
                "</tr>"
            )
        html_parts.append("</table>")
        plain_lines.append("")

    # --- Block 2: unassigned tickets ---
    if data.unassigned:
        plain_lines.append("Неназначенные заявки (взять в работу):")
        html_parts.append('<h3 style="margin-top:16px;margin-bottom:8px">Неназначенные заявки</h3>')
        html_parts.append('<table cellpadding="4" cellspacing="0" border="0">')
        for row in data.unassigned:
            link = _ticket_link(portal_base_url, row.ticket_id)
            subject_esc = html.escape(row.subject)
            author_esc = html.escape(row.author_display)
            days = _plural_days(row.days_in_work)
            plain_lines.append(
                f"- #{row.number} «{row.subject}» — {row.author_display}, {days}\n  {link}"
            )
            html_parts.append(
                "<tr>"
                f'<td style="vertical-align:top"><strong>#{row.number}</strong></td>'
                f"<td>«{subject_esc}»<br>"
                f'<span style="color:#666;font-size:0.9em">{author_esc}, {days}</span><br>'
                f'<a href="{link}">Открыть заявку</a>'
                "</td>"
                "</tr>"
            )
        html_parts.append("</table>")
        plain_lines.append("")

    html_parts.append("</div>")
    return "\n".join(plain_lines), "\n".join(html_parts)


# ---------------------------------------------------------------------------
# Orchestration (called by worker).
# ---------------------------------------------------------------------------


async def send_digests(
    db: AsyncSession,
    redis: Redis,
    *,
    portal_base_url: str,
    now: datetime | None = None,
) -> dict[str, int]:
    """Отправить сводные письма всем активным helpdesk-агентам.

    Неназначенные тикеты собираются один раз (общий блок). Для каждого агента
    — его личные тикеты + общий блок; если оба пусты, письмо не создаётся.
    После успешной enqueue-обработки фиксируется ``DIGEST_LAST_SENT_KEY``
    (дата отправки для идемпотентности).

    Возвращает ``{sent, skipped}``.
    """
    now = now or datetime.now(UTC)
    agents = await _load_active_agents(db)
    if not agents:
        logger.info("helpdesk.digest.no_agents")
        return {"sent": 0, "skipped": 0}

    # Общий блок — один запрос на всех.
    unassigned = await collect_unassigned(db, now=now)

    sent = 0
    skipped = 0
    for agent in agents:
        assigned = await collect_assigned(db, agent_id=agent.id, now=now)
        data = DigestData(assigned=assigned, unassigned=unassigned)
        if data.is_empty():
            skipped += 1
            continue
        plain, html_body = build_digest_bodies(agent, data, portal_base_url=portal_base_url)
        await enqueue_outbox_email(
            db,
            kind=KIND_GENERIC,
            to_email=agent.email,
            subject=build_digest_subject(),
            body_html=html_body,
            body_text=plain,
            payload={"smtp_source": "helpdesk"},
            related_resource_type="helpdesk_digest",
            created_by_user_id=agent.id,
        )
        sent += 1

    if sent:
        await db.commit()
        await redis.set(DIGEST_LAST_SENT_KEY, now.isoformat())

    logger.info("helpdesk.digest.sent", sent=sent, skipped=skipped, agents=len(agents))
    return {"sent": sent, "skipped": skipped}
