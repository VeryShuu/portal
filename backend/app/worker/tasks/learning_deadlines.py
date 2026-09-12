"""Напоминания о дедлайне курса (этап 2, ТЗ §15).

Cron ARQ раз в сутки: по опубликованным курсам с дедлайном, до которого
осталось ≤ ``learning_deadline_reminder_days`` суток, участникам, ещё не
прошедшим курс, уходит одно письмо (outbox, kind=learning). Отметка
``deadline_notified_at`` на строке зачисления гарантирует одно напоминание
на участника: повторные прогоны и перенос дедлайна на более позднюю дату
письма не дублируют (осознанное упрощение — перенос дедлайна вперёд не
возвращает напоминание; зафиксировано в wip/learning.md §12).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.learning import LearningCourse, LearningCourseParticipant
from app.services.email_outbox import enqueue_outbox_email
from app.services.learning import courses_service as cs
from app.services.learning.emails import deadline_reminder_letter

logger = get_logger(__name__)


async def process_deadline_reminders(ctx: dict) -> int:
    """Разослать напоминания о близком дедлайне. Возвращает число писем."""
    settings = get_settings()
    window_days = settings.learning_deadline_reminder_days
    now = datetime.now(UTC)
    window_end = now + timedelta(days=window_days)

    sent = 0
    async with AsyncSessionLocal() as db:
        courses = (
            (
                await db.execute(
                    select(LearningCourse).where(
                        LearningCourse.status == "published",
                        LearningCourse.deleted_at.is_(None),
                        LearningCourse.deadline_at.is_not(None),
                        LearningCourse.deadline_at > now,
                        LearningCourse.deadline_at <= window_end,
                    )
                )
            )
            .scalars()
            .all()
        )
        for course in courses:
            total_items, rows = await cs.compute_progress(db, course.id)
            participants = (
                (
                    await db.execute(
                        select(LearningCourseParticipant).where(
                            LearningCourseParticipant.course_id == course.id,
                            LearningCourseParticipant.deleted_at.is_(None),
                            LearningCourseParticipant.deadline_notified_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            notified_rows = [
                p
                for p in participants
                if p.display_name and _completed_for(rows, p.id) < total_items
            ]
            assert course.deadline_at is not None  # фильтр is_not(None) выше
            for p in notified_rows:
                staff = p.user_id is not None
                link = cs.course_link(course_slug=course.slug, is_staff=staff)
                subject, body, html = deadline_reminder_letter(
                    full_name=p.display_name or "",
                    course_title=course.title,
                    deadline_at=course.deadline_at,
                    remaining=total_items - _completed_for(rows, p.id),
                    link=link,
                )
                await enqueue_outbox_email(
                    db,
                    kind="learning",
                    to_email=p.email or "",
                    subject=subject,
                    body_html=html,
                    body_text=body,
                    related_resource_type="learning_course",
                    related_resource_id=course.id,
                )
                p.deadline_notified_at = now
                sent += 1
        await db.commit()

    if sent:
        logger.info("learning.deadline_reminders_sent", count=sent)
    return sent


def _completed_for(rows: list[cs.ProgressRow], participant_id: uuid.UUID) -> int:
    for r in rows:
        if r.participant_id == participant_id:
            return len(r.completed_items | r.passed_tests)
    return 0
