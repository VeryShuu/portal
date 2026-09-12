"""Администрирование курсов — эндпоинты методиста (инкремент 2).

Только внутренний контур (портал): ``require_learning_admin`` + мастер-ключ
модуля. Все мутации — audit-события; письма зачисления идут через outbox
в той же транзакции.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbDep, LearningAdminDep, LearningDbDep, RedisDep
from app.api.deps import require_learning_module as _module_gate
from app.models.learning import LearningCourse, LearningCourseItem, LearningCourseParticipant
from app.schemas.learning import (
    CourseCreate,
    CourseDetailOut,
    CourseListOut,
    CourseOut,
    CourseUpdate,
    ItemCreate,
    ItemOut,
    ItemsReorder,
    ItemUpdate,
    ParticipantAttemptsResetOut,
    ParticipantBulkEnroll,
    ParticipantEnroll,
    ParticipantItemsOut,
    ParticipantItemStatusOut,
)
from app.services.audit import push_audit_event
from app.services.learning import certificates as cert_svc
from app.services.learning import courses_service as cs
from app.services.learning import covers as cover_svc
from app.services.learning import progress_export
from app.services.learning import tests_service as ts
from app.services.learning.participant import LearningParticipant

router = APIRouter(
    prefix="/learning/admin/courses",
    tags=["learning"],
    dependencies=[Depends(_module_gate)],
)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _course_or_404(db: LearningDbDep, course_id: uuid.UUID) -> LearningCourse:
    course = await cs.get_course(db, course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Курс не найден")
    return course


@router.post("", summary="Создать курс (черновик)", status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    dba: DbDep,
) -> CourseOut:
    course = await cs.create_course(
        db,
        title=body.title,
        description=body.description,
        slug=body.slug,
        deadline_at=body.deadline_at,
        created_by=admin.id,
        category_id=body.category_id,
        for_all_staff=body.for_all_staff,
    )
    if body.for_all_staff:
        # материал сплошного покрытия: строки участников создаются сразу
        await cs.enroll_all_staff_missing(db, dba, course, enrolled_by=admin.id)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_created",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
    )
    return CourseOut.model_validate(course)


@router.get("", summary="Список курсов")
async def list_courses(
    _admin: LearningAdminDep,
    db: LearningDbDep,
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CourseListOut:
    rows, total = await cs.list_courses(db, q=q, limit=limit, offset=offset)
    return CourseListOut(
        items=[CourseOut.model_validate(c) for c in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{course_id}", summary="Карточка курса с элементами")
async def get_course(
    course_id: uuid.UUID, _admin: LearningAdminDep, db: LearningDbDep
) -> CourseDetailOut:
    course = await _course_or_404(db, course_id)
    items = await cs.active_items(db, course.id)
    detail = CourseDetailOut.model_validate(course)
    detail.items = [ItemOut.model_validate(i) for i in items]
    return detail


@router.patch("/{course_id}", summary="Правка названия/описания/slug")
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    dba: DbDep,
) -> CourseOut:
    course = await _course_or_404(db, course_id)
    # PATCH-семантика: в changes попадают только ПРИСЛАННЫЕ поля — ключ
    # отсутствует = «не менять»; явный null у description/deadline = очистить
    # (ревью 2026-08-30: service отличает «не пришло» от «пришло null»).
    changes: dict[str, Any] = {}
    if "deadline_at" in body.model_fields_set:
        changes["deadline_at"] = body.deadline_at
    if "category_id" in body.model_fields_set:
        changes["category_id"] = body.category_id
    if "for_all_staff" in body.model_fields_set:
        changes["for_all_staff"] = body.for_all_staff
    if "description" in body.model_fields_set:
        changes["description"] = body.description
    if body.title is not None:
        changes["title"] = body.title
    was_for_all = course.for_all_staff
    await cs.update_course(db, course, slug=body.slug, **changes)
    if changes.get("for_all_staff") and not was_for_all:
        # включили «для всех сотрудников» — материализуем участников сразу
        await cs.enroll_all_staff_missing(db, dba, course, enrolled_by=admin.id)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_updated",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
    )
    return CourseOut.model_validate(course)


# ── обложка (этап 2, ТЗ §6.2) ────────────────────────────────────────────────


@router.post("/{course_id}/cover", summary="Загрузить обложку курса")
async def upload_course_cover(
    course_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    file: UploadFile,
) -> CourseOut:
    course = await _course_or_404(db, course_id)
    course = await cover_svc.upload_cover(db, course, file)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_cover_uploaded",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
        metadata={"mime": file.content_type},
    )
    return CourseOut.model_validate(course)


@router.delete("/{course_id}/cover", summary="Удалить обложку курса")
async def delete_course_cover(
    course_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> CourseOut:
    course = await _course_or_404(db, course_id)
    course = await cover_svc.delete_cover(db, course)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_cover_deleted",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
    )
    return CourseOut.model_validate(course)


@router.get(
    "/{course_id}/cover",
    summary="Обложка курса (WebP-превью)",
    response_class=StreamingResponse,
)
async def get_course_cover(
    course_id: uuid.UUID, _admin: LearningAdminDep, db: LearningDbDep
) -> StreamingResponse:
    course = await _course_or_404(db, course_id)
    path = cover_svc.resolve_cover_path(course)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Обложка не задана")
    return await cover_svc.file_response(path)


@router.post("/{course_id}/publish", summary="Опубликовать курс")
async def publish_course(
    course_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    course = await _course_or_404(db, course_id)
    await cs.set_published(db, course, published=True)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_published",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
        metadata={"published": True},
    )
    return {"ok": True, "status": course.status}


@router.post("/{course_id}/unpublish", summary="Снять с публикации")
async def unpublish_course(
    course_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    course = await _course_or_404(db, course_id)
    await cs.set_published(db, course, published=False)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_published",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
        metadata={"published": False},
    )
    return {"ok": True, "status": course.status}


@router.delete("/{course_id}", summary="Удалить курс (soft)")
async def delete_course(
    course_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    course = await _course_or_404(db, course_id)
    title = course.title
    await cs.soft_delete_course(db, course)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.course_deleted",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course_id),
        resource_title=title,
        ip_address=_ip(request),
    )
    return {"ok": True}


# ── элементы ─────────────────────────────────────────────────────────────────


@router.post(
    "/{course_id}/items",
    summary="Добавить элемент (материал или заготовка теста)",
    status_code=status.HTTP_201_CREATED,
)
async def add_item(
    course_id: uuid.UUID,
    body: ItemCreate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    # Материал допустимо создать без url: PDF-файл прикладывается отдельным
    # вызовом POST /items/{item_id}/file к созданному элементу (§6.2).
    course = await _course_or_404(db, course_id)
    item = await cs.add_item(
        db,
        course.id,
        type_=body.type,
        title=body.title,
        url=body.url,
        description=body.description,
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.item_created",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        resource_title=item.title,
        ip_address=_ip(request),
        metadata={"item_type": body.type, "course_id": str(course.id)},
    )
    return {"id": str(item.id), "sort_order": item.sort_order}


@router.post("/items/{item_id}/file", summary="Приложить PDF-файл к материалу")
async def upload_material_file(
    item_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    file: UploadFile,
) -> dict[str, Any]:
    from pathlib import Path

    from app.core.uploads import stream_upload_to_path

    item = await cs.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Элемент не найден")
    if item.type != "material":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Файл прикладывается только материалу",
        )

    dest = Path(cs.LEARNING_DATA_DIR) / "materials" / str(item.course_id) / f"{item_id}.pdf"
    _, mime = await stream_upload_to_path(
        file, dest, max_size=cs.MATERIAL_MAX_BYTES, allowed_mimes={cs.MATERIAL_MIME}
    )
    item.file_path = str(dest)
    item.updated_at = datetime.now(UTC)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.material_uploaded",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        resource_title=item.title,
        ip_address=_ip(request),
        metadata={"mime": mime or cs.MATERIAL_MIME},
    )
    return {"ok": True, "file_path": str(dest), "mime": mime or cs.MATERIAL_MIME}


@router.post("/{course_id}/items/reorder", summary="Перепорядочить элементы")
async def reorder_items_endpoint(
    course_id: uuid.UUID,
    body: ItemsReorder,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    await _course_or_404(db, course_id)
    await cs.reorder_items(db, course_id, body.ordered_ids)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.items_reordered",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course_id),
        ip_address=_ip(request),
        metadata={"count": len(body.ordered_ids)},
    )
    return {"ok": True}


@router.patch("/items/{item_id}", summary="Правка элемента")
async def update_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    item = await cs.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Элемент не найден")
    # Явный null в url = очистить ссылку (с защитой инварианта опубликованного
    # курса в сервисе); отсутствующее поле = «не менять». То же для описания.
    await cs.update_item(
        db,
        item,
        title=body.title,
        url=body.url,
        url_provided="url" in body.model_fields_set,
        description=body.description,
        description_provided="description" in body.model_fields_set,
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.item_updated",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        resource_title=item.title,
        ip_address=_ip(request),
    )
    return {"ok": True}


@router.delete("/items/{item_id}", summary="Удалить элемент (soft)")
async def delete_item(
    item_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    item = await cs.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Элемент не найден")
    # §15 распространяется и на удаление: тест с попытками исчез бы из курса,
    # а открытые попытки продолжали бы сдаваться «в никуда». Материалы
    # удаляются свободно (на прохождение попыток не влияют).
    if item.type == "test":
        await ts.assert_test_editable(db, item.id, denied="удаление запрещено")
    await cs.soft_delete_item(db, item)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.item_deleted",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item.id),
        ip_address=_ip(request),
    )
    return {"ok": True}


# ── участники ────────────────────────────────────────────────────────────────


@router.post(
    "/{course_id}/participants",
    summary="Зачислить участника (сотрудник или внешняя учётка)",
    status_code=status.HTTP_201_CREATED,
)
async def enroll_participant(
    course_id: uuid.UUID,
    body: ParticipantEnroll,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    dba: DbDep,
) -> dict[str, Any]:
    if (body.user_id is None) == (body.learning_account_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Передайте ровно одно: user_id ИЛИ learning_account_id",
        )
    course = await _course_or_404(db, course_id)
    # Личность резолвим до снапшота (миграция 103): сотрудники — по основному
    # движку (users недоступны роли learning_app), внешние — по learning-движку.
    if body.user_id is not None:
        display_name, email = await cs.get_staff_identity(dba, body.user_id)
    else:
        assert body.learning_account_id is not None  # XOR проверен выше
        display_name, email = await cs.get_external_identity(db, body.learning_account_id)
    participant = await cs.enroll_participant(
        db,
        course,
        user_id=body.user_id,
        learning_account_id=body.learning_account_id,
        display_name=display_name,
        email=email,
        enrolled_by=admin.id,
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.participant_enrolled",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
        metadata={
            "participant_row": str(participant.id),
            "kind": "staff" if body.user_id else "external",
        },
    )
    return {"ok": True, "participant_id": str(participant.id)}


@router.post(
    "/{course_id}/participants/bulk",
    summary="Групповое зачисление сотрудников",
    status_code=status.HTTP_201_CREATED,
)
async def enroll_participants_bulk(
    course_id: uuid.UUID,
    body: ParticipantBulkEnroll,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
    dba: DbDep,
) -> dict[str, Any]:
    course = await _course_or_404(db, course_id)
    enrolled, skipped, errors = await cs.enroll_participants_bulk(
        db, dba, course, user_ids=body.user_ids, enrolled_by=admin.id
    )
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.participants_bulk_enrolled",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course.id),
        resource_title=course.title,
        ip_address=_ip(request),
        metadata={"enrolled": enrolled, "skipped_duplicates": skipped},
    )
    return {"enrolled": enrolled, "skipped_duplicates": skipped, "errors": errors}


@router.delete("/{course_id}/participants/{participant_id}", summary="Исключить участника (soft)")
async def unenroll_participant(
    course_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> dict[str, Any]:
    await _course_or_404(db, course_id)
    removed = await cs.unenroll_participant(db, participant_id, course_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.participant_removed",
        user_id=str(admin.id),
        resource_type="learning_course",
        resource_id=str(course_id),
        ip_address=_ip(request),
        metadata={"participant_row": str(participant_id)},
    )
    return {"ok": True}


@router.get("/{course_id}/progress", summary="Прогресс участников (оба типа одним списком)")
async def course_progress(
    course_id: uuid.UUID, _admin: LearningAdminDep, db: LearningDbDep
) -> dict[str, Any]:
    await _course_or_404(db, course_id)
    total_items, rows = await cs.compute_progress(db, course_id)
    return cs.progress_to_api(course_id, total_items, rows)


@router.get(
    "/{course_id}/progress/export",
    summary="Экспорт прогресса курса в xlsx",
    response_class=StreamingResponse,
)
async def export_progress(
    course_id: uuid.UUID, _admin: LearningAdminDep, db: LearningDbDep
) -> StreamingResponse:
    course = await _course_or_404(db, course_id)
    total_items, rows = await cs.compute_progress(db, course_id)
    # openpyxl-генерация CPU-лёгкая, но синхронная — выносим из цикла событий.
    data = await asyncio.to_thread(
        progress_export.build_progress_xlsx,
        course_title=course.title,
        total_items=total_items,
        rows=rows,
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="learning-progress-{course.slug}.xlsx"'
        },
    )


# ── участник: детализация статуса, сброс попыток, сертификат ─────────────────


async def _participant_row_or_404(
    db: LearningDbDep, course_id: uuid.UUID, participant_id: uuid.UUID
) -> LearningCourseParticipant:
    row = (
        await db.execute(
            select(LearningCourseParticipant).where(
                LearningCourseParticipant.id == participant_id,
                LearningCourseParticipant.course_id == course_id,
                LearningCourseParticipant.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Участник не найден")
    return row


def _participant_of_row(row: LearningCourseParticipant) -> LearningParticipant:
    return LearningParticipant(
        kind="user" if row.user_id is not None else "acc",
        user_id=row.user_id,
        learning_account_id=row.learning_account_id,
        display_name=row.display_name or "",
        email=row.email or "",
    )


@router.get(
    "/{course_id}/participants/{participant_id}/items",
    summary="Статус решения курса участником: каждый элемент с флагом и попытками",
)
async def participant_items(
    course_id: uuid.UUID,
    participant_id: uuid.UUID,
    _admin: LearningAdminDep,
    db: LearningDbDep,
) -> ParticipantItemsOut:
    await _course_or_404(db, course_id)
    row = await _participant_row_or_404(db, course_id, participant_id)
    statuses = await cs.participant_items_status(db, course_id, _participant_of_row(row))
    return ParticipantItemsOut(
        participant_id=participant_id,
        items=[ParticipantItemStatusOut(**asdict(s)) for s in statuses],
    )


@router.post(
    "/{course_id}/participants/{participant_id}/items/{item_id}/reset-attempts",
    summary="Сбросить попытки теста участнику (тест снова «Не пройден»)",
)
async def reset_participant_attempts(
    course_id: uuid.UUID,
    participant_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> ParticipantAttemptsResetOut:
    await _course_or_404(db, course_id)
    row = await _participant_row_or_404(db, course_id, participant_id)
    item = (
        await db.execute(
            select(LearningCourseItem).where(
                LearningCourseItem.id == item_id,
                LearningCourseItem.course_id == course_id,
                LearningCourseItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if item is None or item.type != "test":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден в курсе")
    deleted = await ts.reset_attempts(db, _participant_of_row(row), item_id)
    await db.commit()
    await push_audit_event(
        redis,
        event_type="learning.attempts_reset",
        user_id=str(admin.id),
        resource_type="learning_course_item",
        resource_id=str(item_id),
        ip_address=_ip(request),
        metadata={
            "course_id": str(course_id),
            "participant_row": str(participant_id),
            "deleted_attempts": deleted,
        },
    )
    return ParticipantAttemptsResetOut(deleted_attempts=deleted)


@router.get(
    "/{course_id}/participants/{participant_id}/certificate",
    summary="Сертификат участника (PDF): скачивание выданного либо выпуск за пройденный курс",
    response_class=StreamingResponse,
)
async def participant_certificate(
    course_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    admin: LearningAdminDep,
    redis: RedisDep,
    db: LearningDbDep,
) -> StreamingResponse:
    """Участник получает сертификат лениво (первое скачивание на своей
    странице). Методисту же нужен файл вне зависимости от того, дошёл ли
    сотрудник до кнопки: если сертификата ещё нет, но курс пройден полностью —
    выпускаем здесь (тот же ensure_certificate, идемпотентный)."""
    course = await _course_or_404(db, course_id)
    row = await _participant_row_or_404(db, course_id, participant_id)
    participant = _participant_of_row(row)
    items = await cs.items_with_completion(db, course.id, participant)
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
                "kind": "staff" if row.user_id is not None else "external",
                "serial": cert.serial,
                "issued_by": "admin",
            },
        )
    return await cert_svc.file_response(cert)
