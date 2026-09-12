"""Прохождение курсов участником (инкремент 3, ТЗ §8).

``/learning/me/*`` — общий контур для обеих категорий: сотрудники портала
(портальная сессия) и внешние учётки (learner-cookie, после смены временного
пароля). Знание ссылки доступа не даёт: не участник, курс не опубликован или
элемент не активен — одинаковый 404 «Курс недоступен» (анти-перечисление).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentLearningParticipant, LearningDbDep, RedisDep
from app.api.deps import require_learning_module as _module_gate
from app.models.learning import (
    LearningCourse,
    LearningCourseItem,
    LearningTest,
    LearningTestAttempt,
)
from app.schemas.learning import (
    AttemptBrief,
    AttemptResult,
    AttemptView,
    MyAttemptsOut,
    MyCourseDetailOut,
    MyCourseItemOut,
    MyCourseOut,
    SubmitAnswers,
)
from app.services.audit import push_audit_event
from app.services.learning import certificates as cert_svc
from app.services.learning import courses_service as cs
from app.services.learning import covers as cover_svc
from app.services.learning import tests_service as ts
from app.services.learning.participant import LearningParticipant

router = APIRouter(
    prefix="/learning/me",
    tags=["learning"],
    dependencies=[Depends(_module_gate)],
)


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Курс недоступен")


async def _accessible_item(
    db: LearningDbDep,
    participant: LearningParticipant,
    item_id: uuid.UUID,
    *,
    lock_course: bool = False,
) -> tuple[LearningCourse, LearningCourseItem]:
    """Активный элемент опубликованного курса с зачисленным участником."""
    item = await cs.get_item(db, item_id)
    if item is None:
        raise _unavailable()
    if lock_course:
        course = await cs.lock_course(db, item.course_id)
        if course is not None and course.status != "published":
            course = None
    else:
        course = (
            await db.execute(
                select(LearningCourse).where(
                    LearningCourse.id == item.course_id,
                    LearningCourse.deleted_at.is_(None),
                    LearningCourse.status == "published",
                )
            )
        ).scalar_one_or_none()
    if course is None or not await cs.has_course_access(db, participant, course):
        raise _unavailable()
    return course, item


async def _test_or_404(db: LearningDbDep, item_id: uuid.UUID) -> LearningTest:
    test = await ts.get_test(db, item_id)
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Тест не настроен")
    return test


async def _accessible_attempt(
    db: LearningDbDep,
    participant: LearningParticipant,
    attempt_id: uuid.UUID,
) -> LearningTestAttempt:
    """Попытка доступна только пока доступен её опубликованный курс.

    Владение UUID недостаточно: soft-delete/unpublish курса или исключение
    участника должны закрывать и прямые attempt endpoints.
    """
    attempt = await ts.get_attempt_for_participant(db, participant, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Попытка не найдена")
    await _accessible_item(db, participant, attempt.test_item_id)
    return attempt


# ── курсы ────────────────────────────────────────────────────────────────────


@router.get("/courses", summary="Мои курсы (обе категории участников)")
async def my_courses(
    participant: CurrentLearningParticipant, db: LearningDbDep
) -> list[MyCourseOut]:
    rows = await cs.my_course_list(db, participant)
    return [
        MyCourseOut(
            id=c.id,
            slug=c.slug,
            title=c.title,
            description=c.description,
            status=c.status,
            published_at=c.published_at,
            created_at=c.created_at,
            cover_path=c.cover_path,
            updated_at=c.updated_at,
            progress_completed=completed,
            progress_total=total,
            category_title=cat_title,
            category_sort=cat_sort,
        )
        for c, completed, total, cat_title, cat_sort in rows
    ]


@router.get("/courses/{slug}", summary="Карточка моего курса")
async def my_course(
    slug: str, participant: CurrentLearningParticipant, db: LearningDbDep
) -> MyCourseDetailOut:
    course, items = await cs.course_for_participant(db, participant, slug)
    # прогресс — только по оцениваемым элементам; разделы-заголовки не считаются
    graded = [r for r in items if r.item.type != "section"]
    return MyCourseDetailOut(
        id=course.id,
        slug=course.slug,
        title=course.title,
        description=course.description,
        status=course.status,
        published_at=course.published_at,
        created_at=course.created_at,
        cover_path=course.cover_path,
        updated_at=course.updated_at,
        progress_completed=sum(1 for r in graded if r.completed),
        progress_total=len(graded),
        items=[
            MyCourseItemOut(
                id=r.item.id,
                type=r.item.type,
                title=r.item.title,
                description=r.item.description,
                sort_order=r.item.sort_order,
                url=r.item.url,
                has_file=bool(r.item.file_path),
                completed=r.completed,
            )
            for r in items
        ],
    )


@router.get(
    "/courses/{slug}/cover",
    summary="Обложка моего курса (WebP-превью)",
    response_class=StreamingResponse,
)
async def my_course_cover(
    slug: str, participant: CurrentLearningParticipant, db: LearningDbDep
) -> StreamingResponse:
    """Та же проверка доступа, что у карточки курса (анти-перечисление:
    не участник / не опубликован / обложки нет — одинаковый 404)."""
    course = await cs.get_published_course_by_slug(db, slug)
    await cs.assert_participant_access(db, participant, course)
    path = cover_svc.resolve_cover_path(course)
    if path is None:
        raise _unavailable()
    return await cover_svc.file_response(path)


@router.get(
    "/courses/{slug}/certificate",
    summary="Сертификат о прохождении (PDF; ленивая выдача)",
    response_class=StreamingResponse,
)
async def course_certificate(
    slug: str,
    request: Request,
    participant: CurrentLearningParticipant,
    redis: RedisDep,
    db: LearningDbDep,
) -> StreamingResponse:
    """Первый запрос за полностью пройденный курс генерирует PDF через
    screenshot-service и сохраняет его; повторные — отдают сохранённый."""
    course, items = await cs.course_for_participant(db, participant, slug)
    cert, issued = await cert_svc.ensure_certificate(db, course, participant, items=items)
    await db.commit()
    if issued:
        await push_audit_event(
            redis,
            event_type="learning.certificate_issued",
            user_id=str(participant.user_id) if participant.user_id else None,
            resource_type="learning_certificate",
            resource_id=str(cert.id),
            resource_title=course.title,
            ip_address=request.client.host if request.client else None,
            metadata={
                "course_id": str(course.id),
                "kind": participant.kind,
                "serial": cert.serial,
            },
        )
    return await cert_svc.file_response(cert)


@router.post("/items/{item_id}/complete", summary="Отметить материал ознакомленным")
async def complete_item(
    item_id: uuid.UUID, participant: CurrentLearningParticipant, db: LearningDbDep
) -> dict[str, Any]:
    _, item = await _accessible_item(db, participant, item_id)
    created = await cs.complete_material(db, participant, item)
    await db.commit()
    return {"ok": True, "already_completed": not created}


@router.get(
    "/items/{item_id}/file",
    summary="Скачать PDF материала",
    response_class=StreamingResponse,
)
async def download_material(
    item_id: uuid.UUID, participant: CurrentLearningParticipant, db: LearningDbDep
) -> StreamingResponse:
    """Стриминг из локального хранилища модуля (§6.2), как вложения helpdesk:
    не FileResponse и не буферизация в bytes."""
    _, item = await _accessible_item(db, participant, item_id)
    if item.type != "material" or not item.file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Файл не приложен")

    # file_path заполняется только сервером при загрузке; проверка соответствия
    # каноническому пути страхует от подмены значения в БД напрямую.
    from pathlib import Path

    path = Path(item.file_path)
    expected_dir = Path(cs.LEARNING_DATA_DIR) / "materials" / str(item.course_id)
    if path.parent != expected_dir or path.name != f"{item.id}.pdf" or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Файл не найден")

    async def chunk_iter() -> AsyncIterator[bytes]:
        import aiofiles

        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        chunk_iter(),
        media_type="application/pdf",
        headers={
            # RFC 5987: русские названия материалов не ломают заголовок
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'{item.title}.pdf')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── попытки ──────────────────────────────────────────────────────────────────


async def _attempt_view(
    db: LearningDbDep, participant: LearningParticipant, attempt: LearningTestAttempt
) -> AttemptView:
    test = await _test_or_404(db, attempt.test_item_id)
    submitted_count = await ts.count_submitted(db, participant, attempt.test_item_id)
    return AttemptView(
        id=attempt.id,
        status="open",
        test_item_id=attempt.test_item_id,
        questions=await ts.get_attempt_questions(db, attempt),
        max_attempts=test.max_attempts,
        submitted_count=submitted_count,
        remaining_attempts=ts.remaining_attempts(test.max_attempts, submitted_count),
        started_at=attempt.started_at,
        time_limit_minutes=test.time_limit_minutes,
        expires_at=ts.attempt_expires_at(test, attempt),
    )


async def _attempt_result(
    db: LearningDbDep, participant: LearningParticipant, attempt: LearningTestAttempt
) -> AttemptResult:
    test = await _test_or_404(db, attempt.test_item_id)
    submitted_count = await ts.count_submitted(db, participant, attempt.test_item_id)
    return AttemptResult(
        id=attempt.id,
        status="submitted",
        score=attempt.score,
        passed=attempt.passed,
        remaining_attempts=ts.remaining_attempts(test.max_attempts, submitted_count),
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
    )


@router.post("/tests/{item_id}/attempts", summary="Начать/возобновить попытку теста")
async def start_attempt(
    item_id: uuid.UUID, participant: CurrentLearningParticipant, db: LearningDbDep
) -> AttemptView:
    """Повторный вызов при незакрытой попытке возвращает её же — старт не
    расходует лимит (считаются только отправленные)."""
    _, item = await _accessible_item(db, participant, item_id)
    attempt, _created = await ts.start_attempt(db, participant, item=item, course_published=True)
    await db.commit()
    return await _attempt_view(db, participant, attempt)


@router.get("/tests/{item_id}/my-attempts", summary="Мои попытки по тесту и остаток лимита")
async def my_attempts(
    item_id: uuid.UUID, participant: CurrentLearningParticipant, db: LearningDbDep
) -> MyAttemptsOut:
    await _accessible_item(db, participant, item_id)
    rows, submitted, remaining = await ts.my_attempts(db, participant, item_id)
    test = await _test_or_404(db, item_id)
    await db.commit()  # ленивое клеймо abandoned могло измениться

    def brief_status(a: LearningTestAttempt) -> str:
        if a.submitted_at is not None:
            return "submitted"
        return "abandoned" if a.abandoned_at is not None else "open"

    return MyAttemptsOut(
        test_item_id=item_id,
        max_attempts=test.max_attempts,
        submitted_count=submitted,
        remaining_attempts=remaining,
        attempts=[
            AttemptBrief(
                id=a.id,
                status=brief_status(a),
                score=a.score,
                passed=a.passed,
                started_at=a.started_at,
                submitted_at=a.submitted_at,
            )
            for a in rows
        ],
    )


@router.get("/attempts/{attempt_id}", summary="Состояние попытки")
async def attempt_state(
    attempt_id: uuid.UUID, participant: CurrentLearningParticipant, db: LearningDbDep
) -> AttemptView | AttemptResult:
    attempt = await _accessible_attempt(db, participant, attempt_id)
    if attempt.submitted_at is not None:
        return await _attempt_result(db, participant, attempt)
    return await _attempt_view(db, participant, attempt)


@router.post("/attempts/{attempt_id}/submit", summary="Отправить ответы попытки")
async def submit(
    attempt_id: uuid.UUID,
    body: SubmitAnswers,
    participant: CurrentLearningParticipant,
    db: LearningDbDep,
) -> AttemptResult:
    attempt = await ts.get_attempt_for_participant(db, participant, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Попытка не найдена")
    await _accessible_item(db, participant, attempt.test_item_id, lock_course=True)
    # сервис работает со строковыми ключами; UUID-и pydantic — сюда не доходят
    answers = {str(q): [str(o) for o in opts] for q, opts in body.answers.items()}
    attempt, _score = await ts.submit_attempt(db, participant, attempt_id, answers)
    await db.commit()
    return await _attempt_result(db, participant, attempt)
