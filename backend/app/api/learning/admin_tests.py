"""Настройки тестов и вопросы — эндпоинты методиста (инкремент 3, ТЗ §6.3).

Тест с любой попыткой (в т.ч. начатой) правится только копией элемента
(§15): сервис отвечает 409, правки на уровне API не делают исключений.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from app.api.deps import LearningAdminDep, LearningDbDep, RedisDep
from app.api.deps import require_learning_module as _module_gate
from app.models.learning import LearningCourseItem, LearningQuestion
from app.schemas.learning import (
    OptionOut,
    QuestionCreate,
    QuestionOut,
    TestSettingsOut,
    TestSettingsUpdate,
)
from app.services.audit import push_audit_event
from app.services.learning import courses_service as cs
from app.services.learning import question_import as qi
from app.services.learning import tests_service as ts

router = APIRouter(
    prefix="/learning/admin/courses",
    tags=["learning"],
    dependencies=[Depends(_module_gate)],
)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _test_item_or_404(db: LearningDbDep, item_id: uuid.UUID) -> LearningCourseItem:
    item = await cs.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Элемент не найден")
    if item.type != "test":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Элемент не тест"
        )
    return item


@router.get("/items/{item_id}/test", summary="Настройки теста и вопросы (с ответами)")
async def get_test_config(
    item_id: uuid.UUID, _admin: LearningAdminDep, db: LearningDbDep
) -> dict[str, Any]:
    item = await _test_item_or_404(db, item_id)
    test = await ts.get_test(db, item.id)
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не настроен")
    pairs = await ts.questions_with_options(db, item.id, include_correct=True)
    questions = [
        QuestionOut(
            id=q.id,
            text=q.text,
            multi=q.multi,
            sort_order=q.sort_order,
            options=[
                OptionOut(id=o.id, text=o.text, is_correct=o.is_correct, sort_order=o.sort_order)
                for o in opts
            ],
        )
        for q, opts in pairs
    ]
    return TestSettingsOut(
        pass_score=test.pass_score,
        max_attempts=test.max_attempts,
        shuffle_questions=test.shuffle_questions,
        shuffle_answers=test.shuffle_answers,
        time_limit_minutes=test.time_limit_minutes,
    ).model_dump() | {"questions": [q.model_dump(mode="json") for q in questions]}


@router.patch("/items/{item_id}/test", summary="Правка настроек теста")
async def update_test_settings(
    item_id: uuid.UUID,
    body: TestSettingsUpdate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    item = await _test_item_or_404(db, item_id)
    test = await ts.update_settings(
        db,
        item,
        pass_score=body.pass_score,
        max_attempts=body.max_attempts,
        shuffle_questions=body.shuffle_questions,
        shuffle_answers=body.shuffle_answers,
        # Таймер: отсутствующее поле «не менять», явный null — снять (этап 2).
        time_limit_minutes=body.time_limit_minutes,
        time_limit_provided="time_limit_minutes" in body.model_fields_set,
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.test_settings_updated",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        resource_title=item.title,
        ip_address=_ip(request),
        metadata={
            "pass_score": test.pass_score,
            "max_attempts": test.max_attempts,
            "shuffle_questions": test.shuffle_questions,
            "shuffle_answers": test.shuffle_answers,
        },
    )
    return {"ok": True}


def _options_to_dicts(body: QuestionCreate) -> list[dict[str, Any]]:
    return [{"text": o.text, "is_correct": o.is_correct} for o in body.options]


@router.post(
    "/items/{item_id}/questions",
    summary="Добавить вопрос с вариантами",
    status_code=status.HTTP_201_CREATED,
)
async def add_question(
    item_id: uuid.UUID,
    body: QuestionCreate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    item = await _test_item_or_404(db, item_id)
    question = await ts.add_question(
        db, item, text=body.text, multi=body.multi, options=_options_to_dicts(body)
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.question_added",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        resource_title=item.title,
        ip_address=_ip(request),
        metadata={"question_id": str(question.id), "multi": question.multi},
    )
    return {"ok": True, "question_id": str(question.id)}


async def _question_or_404(
    db: LearningDbDep, item_id: uuid.UUID, question_id: uuid.UUID
) -> LearningQuestion:
    from sqlalchemy import select

    from app.models.learning import LearningQuestion

    q = (
        await db.execute(
            select(LearningQuestion).where(
                LearningQuestion.id == question_id,
                LearningQuestion.test_item_id == item_id,
            )
        )
    ).scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вопрос не найден")
    return q


# ── импорт вопросов из xlsx (этап 2, ТЗ §13/§15) ────────────────────────────


@router.get("/items/{item_id}/questions/template", summary="Скачать шаблон импорта вопросов")
async def download_questions_template(
    item_id: uuid.UUID, _admin: LearningAdminDep, db: LearningDbDep
) -> Response:
    await _test_item_or_404(db, item_id)
    return Response(
        content=qi.build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{qi.QUESTION_TEMPLATE_FILENAME}"'},
    )


@router.post(
    "/items/{item_id}/questions/import/preview",
    summary="Предпросмотр импорта вопросов (без сохранения)",
)
async def preview_questions_import(
    item_id: uuid.UUID,
    _admin: LearningAdminDep,
    db: LearningDbDep,
    file: UploadFile,
) -> dict[str, Any]:
    await _test_item_or_404(db, item_id)
    # Кап ДО чтения в память (паттерн импорта учёток, admin_routes): иначе
    # тело из nginx буферизовалось целиком, а лимит 5МБ проверялся постфактум.
    data = await file.read(qi.MAX_IMPORT_BYTES + 1)
    if len(data) > qi.MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Файл больше 5 МБ")
    try:
        parsed = qi.parse_xlsx(data)
    except qi.ImportFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return {
        "questions": [
            {
                "row": pq.row_number,
                "text": pq.question.text,
                "multi": pq.question.multi,
                "options": [
                    {"text": o.text, "is_correct": o.is_correct} for o in pq.question.options
                ],
            }
            for pq in parsed.questions
        ],
        "errors": [{"row": e.row_number, "message": e.message} for e in parsed.errors],
    }


@router.post("/items/{item_id}/questions/import", summary="Импортировать вопросы из xlsx")
async def import_questions(
    item_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    file: UploadFile,
) -> dict[str, Any]:
    item = await _test_item_or_404(db, item_id)
    data = await file.read(qi.MAX_IMPORT_BYTES + 1)
    if len(data) > qi.MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Файл больше 5 МБ")
    try:
        parsed = qi.parse_xlsx(data)
    except qi.ImportFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    created = await ts.add_questions_bulk(
        db, item, [pq.question.model_dump() for pq in parsed.questions]
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.questions_imported",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        resource_title=item.title,
        ip_address=_ip(request),
        metadata={"created": created, "row_errors": len(parsed.errors)},
    )
    return {
        "created": created,
        "errors": [{"row": e.row_number, "message": e.message} for e in parsed.errors],
    }


@router.patch("/items/{item_id}/questions/{question_id}", summary="Правка вопроса целиком")
async def update_question(
    item_id: uuid.UUID,
    question_id: uuid.UUID,
    body: QuestionCreate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    await _test_item_or_404(db, item_id)
    question = await _question_or_404(db, item_id, question_id)
    await ts.update_question(
        db, question, text=body.text, multi=body.multi, options=_options_to_dicts(body)
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.question_updated",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item_id),
        ip_address=_ip(request),
        metadata={"question_id": str(question.id)},
    )
    return {"ok": True}


@router.delete("/items/{item_id}/questions/{question_id}", summary="Удалить вопрос")
async def delete_question(
    item_id: uuid.UUID,
    question_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    await _test_item_or_404(db, item_id)
    question = await _question_or_404(db, item_id, question_id)
    await ts.delete_question(db, question)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.question_deleted",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item_id),
        ip_address=_ip(request),
        metadata={"question_id": str(question.id)},
    )
    return {"ok": True}
