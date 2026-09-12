"""Integration: напоминания о дедлайне (этап 2) — письма непрошедшим
участникам через outbox, отметка deadline_notified_at (одно на участника),
прошедшие участники и курсы без дедлайна не затрагиваются."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.core.database import AsyncSessionLocal
from app.models.email_outbox import EmailOutbox
from app.models.learning import (
    LearningCourse,
    LearningCourseItem,
    LearningCourseParticipant,
    LearningItemProgress,
)
from app.models.user import User
from app.worker.tasks.learning_deadlines import process_deadline_reminders

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_learning_rows(redis_client):
    yield

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM email_outbox WHERE kind = 'learning'"))
        await db.execute(text("DELETE FROM learning_item_progress"))
        await db.execute(text("DELETE FROM learning_test_attempts"))
        await db.execute(text("DELETE FROM learning_question_options"))
        await db.execute(text("DELETE FROM learning_questions"))
        await db.execute(text("DELETE FROM learning_tests"))
        await db.execute(text("DELETE FROM learning_course_items"))
        await db.execute(text("DELETE FROM learning_courses"))
        await db.execute(text("DELETE FROM learning_course_participants"))
        await db.execute(text("DELETE FROM learning_admins"))
        await db.execute(text("DELETE FROM learning_accounts WHERE email LIKE '%@example.com'"))
        await db.commit()
    for prefix in ("learning_session:", "learning_sessions:"):
        for key in await redis_client.keys(f"{prefix}*"):
            await redis_client.delete(key)


class _Seed:
    def __init__(self):
        self.course: LearningCourse | None = None
        self.material_id: uuid.UUID | None = None
        self.done_user_id: uuid.UUID | None = None
        self.pending_user_id: uuid.UUID | None = None

    async def build(self, *, with_deadline: bool = True) -> None:

        async with AsyncSessionLocal() as db:
            course = LearningCourse(
                slug=f"dl-{uuid.uuid4().hex[:8]}",
                title="Курс с дедлайном",
                status="published",
                published_at=datetime.now(UTC),
                deadline_at=datetime.now(UTC) + timedelta(days=2) if with_deadline else None,
            )
            db.add(course)
            await db.flush()
            material = LearningCourseItem(
                course_id=course.id, type="material", title="Материал", sort_order=0
            )
            db.add(material)
            await db.flush()

            done = User(
                email=f"dl-done-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Прошедший Сотрудник",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            pending = User(
                email=f"dl-pending-{uuid.uuid4().hex[:8]}@example.com",
                full_name="Отстающий Сотрудник",
                role="reader",
                auth_source="keycloak",
                current_status="working",
            )
            db.add_all([done, pending])
            await db.flush()

            done_p = LearningCourseParticipant(
                course_id=course.id,
                user_id=done.id,
                display_name=done.full_name,
                email=done.email,
            )
            pending_p = LearningCourseParticipant(
                course_id=course.id,
                user_id=pending.id,
                display_name=pending.full_name,
                email=pending.email,
            )
            db.add_all([done_p, pending_p])
            db.add(LearningItemProgress(item_id=material.id, user_id=done.id))
            await db.commit()
            self.course = course
            self.material_id = material.id
            self.done_user_id = done.id
            self.pending_user_id = pending.id


@pytest.mark.asyncio
class TestDeadlineReminders:
    async def test_sends_once_to_incomplete_only(self):
        seed = _Seed()
        await seed.build(with_deadline=True)
        assert seed.course is not None and seed.done_user_id is not None

        sent_first = await process_deadline_reminders({})
        assert sent_first == 1  # только отстающий; прошедшему — нет

        async with AsyncSessionLocal() as db:
            letters = (
                (await db.execute(select(EmailOutbox).where(EmailOutbox.kind == "learning")))
                .scalars()
                .all()
            )
            assert len(letters) == 1
            assert "Дедлайн" in letters[0].subject
            assert "Отстающий Сотрудник" in letters[0].body_text

            notified = (
                await db.execute(
                    select(LearningCourseParticipant.deadline_notified_at).where(
                        LearningCourseParticipant.user_id == seed.pending_user_id
                    )
                )
            ).scalar_one()
            assert notified is not None
            done_notified = (
                await db.execute(
                    select(LearningCourseParticipant.deadline_notified_at).where(
                        LearningCourseParticipant.user_id == seed.done_user_id
                    )
                )
            ).scalar_one()
            assert done_notified is None

        # Повторный прогон — писем больше нет (одно на участника)
        sent_second = await process_deadline_reminders({})
        assert sent_second == 0

        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(
                    select(func.count())
                    .select_from(EmailOutbox)
                    .where(EmailOutbox.kind == "learning")
                )
            ).scalar_one()
        assert total == 1

    async def test_course_without_deadline_is_skipped(self):
        seed = _Seed()
        await seed.build(with_deadline=False)
        assert seed.course is not None

        sent = await process_deadline_reminders({})
        assert sent == 0

        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(
                    select(func.count())
                    .select_from(EmailOutbox)
                    .where(EmailOutbox.kind == "learning")
                )
            ).scalar_one()
            assert total == 0
