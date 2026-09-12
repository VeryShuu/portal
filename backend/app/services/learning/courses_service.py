"""Сервис курсов модуля обучения: CRUD методиста, элементы, зачисление,
прогресс (инкремент 2; ТЗ §6.1–6.2, §8).

Скалирование: участники курса — десятки/сотни, поэтому агрегаты прогресса
считаются в python после двух дешёвых SQL-выборок (attempt'ы + отметки
материалов) — без оконных функций и ORM-гибридов.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.sanitize import sanitize_markdown
from app.models.learning import (
    LearningAccount,
    LearningCertificate,
    LearningCourse,
    LearningCourseCategory,
    LearningCourseItem,
    LearningCourseParticipant,
    LearningItemProgress,
    LearningQuestion,
    LearningQuestionOption,
    LearningTestAttempt,
)
from app.schemas.learning import ParticipantOut
from app.services.email_outbox import enqueue_outbox_email
from app.services.learning import categories_service as cats_svc
from app.services.learning import emails
from app.services.learning.accounts_service import learning_base_url
from app.services.learning.participant import KIND_USER, LearningParticipant

logger = get_logger(__name__)

# Локальные материалы курса (§6.2 — исключение «контент модуля» по образцу
# photos/helpdesk). Файл-аплоад отдаётся только в PDF.
LEARNING_DATA_DIR = "/data/learning"
MATERIAL_MIME = "application/pdf"
MATERIAL_MAX_BYTES = 100 * 1024 * 1024

# Порог «методист полностью задал slug сам» vs автогенерация из названия.
_SLUG_MAX_LEN = 140


def slugify(title: str) -> str:
    """RU→латиница транслитерация → lower → дефисы. Спецсимволы выбрасываются."""
    table = str.maketrans(
        {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "g",
            "д": "d",
            "е": "e",
            "ё": "e",
            "ж": "zh",
            "з": "z",
            "и": "i",
            "й": "y",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "h",
            "ц": "c",
            "ч": "ch",
            "ш": "sh",
            "щ": "sch",
            "ъ": "",
            "ы": "y",
            "ь": "",
            "э": "e",
            "ю": "yu",
            "я": "ya",
        }
    )
    lowered = title.lower().translate(table)
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:_SLUG_MAX_LEN] or "course"


async def _ensure_unique_slug(
    db: AsyncSession, desired: str, *, exclude_id: uuid.UUID | None = None
) -> str:
    base = desired[:_SLUG_MAX_LEN]
    candidate = base
    n = 2
    while True:
        q = select(LearningCourse.id).where(LearningCourse.slug == candidate)
        if exclude_id:
            q = q.where(LearningCourse.id != exclude_id)
        exists = (await db.execute(q)).first()
        if not exists:
            return candidate
        suffix = f"-{n}"
        candidate = f"{base[: _SLUG_MAX_LEN - len(suffix)]}{suffix}"
        n += 1


def _course_404() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Курс не найден")


async def get_course(db: AsyncSession, course_id: uuid.UUID) -> LearningCourse | None:
    res = await db.execute(
        select(LearningCourse).where(
            LearningCourse.id == course_id, LearningCourse.deleted_at.is_(None)
        )
    )
    return res.scalar_one_or_none()


async def lock_course(db: AsyncSession, course_id: uuid.UUID) -> LearningCourse | None:
    """Заблокировать живой курс до конца транзакции и перечитать его состояние.

    Один row-lock сериализует публикацию, добавление элементов, удаление курса
    и старт попытки. Это не даёт конкурентной мутации нарушить инварианты уже
    опубликованного курса.
    """
    res = await db.execute(
        select(LearningCourse)
        .where(LearningCourse.id == course_id, LearningCourse.deleted_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return res.scalar_one_or_none()


@dataclass(frozen=True, slots=True)
class CourseCreated:
    course: LearningCourse


async def create_course(
    db: AsyncSession,
    *,
    title: str,
    description: str | None,
    slug: str | None,
    deadline_at: datetime | None = None,
    created_by: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    for_all_staff: bool = False,
) -> LearningCourse:
    desired_slug = slug if slug else title
    final_slug = await _ensure_unique_slug(db, slugify(desired_slug))
    if category_id is not None:
        await cats_svc.ensure_category_exists(db, category_id)
    course = LearningCourse(
        title=title.strip(),
        # Описание — rich-text (тот же редактор, что у новостей/БЗ): sanitize
        # на записи, storage = истина; вычищенное до пустоты значение = None.
        description=sanitize_markdown(description) or None,
        slug=final_slug,
        deadline_at=deadline_at,
        created_by=created_by,
        category_id=category_id,
        for_all_staff=for_all_staff,
    )
    db.add(course)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug уже используется") from exc
    logger.info("learning.course_created", course_id=str(course.id), slug=final_slug)
    return course


async def update_course(
    db: AsyncSession, course: LearningCourse, **fields: str | None
) -> LearningCourse:
    """PATCH-семантика: роутер кладёт в ``fields`` только ПРИСЛАННЫЕ поля —
    отсутствующий ключ «не менять»; явный ``None`` у description/deadline_at
    очищает значение (ревью 2026-08-30: иначе описанием курса нельзя было
    распорядиться повторно). Slug sanitize/уникальность — как при создании."""
    slug_field = fields.get("slug")
    if slug_field:
        course.slug = await _ensure_unique_slug(db, slugify(str(slug_field)), exclude_id=course.id)
    if "description" in fields:
        # rich-text: sanitize на записи; явный null (или вычищенное до пустоты)
        # = очистить описание.
        course.description = sanitize_markdown(fields["description"]) or None
    if fields.get("title") is not None:
        course.title = str(fields["title"])
    # Дедлайн (этап 2): ключ отсутствует = «не менять»; None = снять.
    if "deadline_at" in fields:
        course.deadline_at = fields["deadline_at"]  # type: ignore[assignment]
    # Обязательный «для всех сотрудников» (миграция 111): ключ прислан →
    # применяем (материализацию строк делает роутер на основном движке).
    if "for_all_staff" in fields:
        course.for_all_staff = bool(fields["for_all_staff"])
    # Категория (миграция 109): ключ отсутствует = «не менять»; None = снять.
    if "category_id" in fields:
        cat_id = cast("uuid.UUID | None", fields["category_id"])
        if cat_id is not None:
            await cats_svc.ensure_category_exists(db, cat_id)
        course.category_id = cat_id
    course.updated_at = datetime.now(UTC)
    await db.flush()
    return course


async def _tests_without_questions(db: AsyncSession, course_id: uuid.UUID) -> list[str]:
    """Заголовки тестов курса, в которых нет ни одного отвечаемого вопроса
    (вопрос без вариантов участнику недоступен — start_attempt их отфильтровывает)."""
    test_items = [i for i in await active_items(db, course_id) if i.type == "test"]
    if not test_items:
        return []
    answerable = set(
        (
            await db.execute(
                select(LearningQuestion.test_item_id)
                .join(
                    LearningQuestionOption,
                    LearningQuestionOption.question_id == LearningQuestion.id,
                )
                .where(LearningQuestion.test_item_id.in_([i.id for i in test_items]))
                .group_by(LearningQuestion.test_item_id)
            )
        )
        .scalars()
        .all()
    )
    return [i.title for i in test_items if i.id not in answerable]


async def set_published(
    db: AsyncSession, course: LearningCourse, *, published: bool
) -> LearningCourse:
    """publish: draft→published идемпотентно; unpublish: обратно в draft.

    Publish-gate (§6.1; ревью 2026-08-28 P1 + ревью 2026-08-30): курс обязан
    быть проходимым целиком — каждый материал имеет url или file_path,
    каждый тест имеет хотя бы один вопрос с вариантами. Иначе learner
    упирается в непроходимый элемент (409 на старте попытки), и 100% +
    сертификат становятся недостижимыми."""
    locked_course = await lock_course(db, course.id)
    if locked_course is None:
        raise _course_404()
    course = locked_course
    if published:
        problems: list[str] = []
        broken_materials = [
            i.title
            for i in await active_items(db, course.id)
            if i.type == "material" and not (i.url or i.file_path)
        ]
        if broken_materials:
            detail = f"У материала «{broken_materials[0]}» нет ни ссылки, ни PDF-файла"
            if len(broken_materials) > 1:
                detail += f" (и ещё {len(broken_materials) - 1} материалов без содержимого)"
            problems.append(detail)
        empty_tests = await _tests_without_questions(db, course.id)
        if empty_tests:
            detail = f"В тесте «{empty_tests[0]}» нет ни одного вопроса с вариантами"
            if len(empty_tests) > 1:
                detail += f" (и ещё {len(empty_tests) - 1} тестов без вопросов)"
            problems.append(detail)
        if problems:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="; ".join(problems))
    if published and course.status != "published":
        course.status = "published"
        course.published_at = datetime.now(UTC)
    elif not published and course.status != "draft":
        course.status = "draft"
    course.updated_at = datetime.now(UTC)
    await db.flush()
    return course


async def soft_delete_course(db: AsyncSession, course: LearningCourse) -> None:
    from sqlalchemy import update

    locked_course = await lock_course(db, course.id)
    if locked_course is None:
        raise _course_404()
    course = locked_course
    # Политика удаления курса (ревью 2026-08-28): soft-delete разрешён всегда,
    # в том числе при наличии попыток — курс исчезает из выдачи участников,
    # попытки/прогресс остаются в истории (§7). В отличие от удаления ТЕСТА
    # (гейт §15 в admin_courses.delete_item) здесь нет «сдачи в никуда»:
    # недоступный курс закрывает и доступ к своим попыткам.
    course.deleted_at = datetime.now(UTC)
    # Снятый с публикации курс исчезает из выдачи learner'ов автоматически
    # (фильтры deleted_at IS NULL / status='published').
    await db.execute(
        update(LearningCourse)
        .where(LearningCourse.id == course.id)
        .values(deleted_at=course.deleted_at, updated_at=course.deleted_at)
    )


async def list_courses(
    db: AsyncSession, *, q: str | None, limit: int, offset: int
) -> tuple[list[LearningCourse], int]:
    base = select(LearningCourse).where(LearningCourse.deleted_at.is_(None))
    count_q = (
        select(func.count()).select_from(LearningCourse).where(LearningCourse.deleted_at.is_(None))
    )
    if q:
        pattern = f"%{q.strip().lower()}%"
        cond = func.lower(LearningCourse.title).like(pattern) | func.lower(
            LearningCourse.slug
        ).like(pattern)
        base = base.where(cond)
        count_q = count_q.where(cond)
    total = (await db.execute(count_q)).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(LearningCourse.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


# ── элементы ─────────────────────────────────────────────────────────────────


async def active_items(db: AsyncSession, course_id: uuid.UUID) -> list[LearningCourseItem]:
    res = await db.execute(
        select(LearningCourseItem)
        .where(
            LearningCourseItem.course_id == course_id,
            LearningCourseItem.deleted_at.is_(None),
        )
        .order_by(LearningCourseItem.sort_order, LearningCourseItem.created_at)
    )
    return list(res.scalars().all())


async def add_item(
    db: AsyncSession,
    course_id: uuid.UUID,
    *,
    type_: str,
    title: str,
    url: str | None,
    description: str | None = None,
) -> LearningCourseItem:
    from app.models.learning import LearningTest

    course = await lock_course(db, course_id)
    if course is None:
        raise _course_404()
    if course.status == "published" and type_ == "material" and not url:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Снимите курс с публикации перед добавлением PDF-материала",
        )
    if course.status == "published" and type_ == "test":
        # Тест создаётся пустым (вопросы добавляются следом) — в опубликованном
        # курсе он был бы непроходим до наполнения (ревью 2026-08-30).
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Снимите курс с публикации перед добавлением теста",
        )
    items = await active_items(db, course_id)
    if type_ == "section":
        # Раздел (миграция 110): строка-заголовок. Контента не несёт, поэтому
        # допустим и в опубликованном курсе (publish-gate не задет); перенос
        # материала между разделами = перестановка строк списка.
        item = LearningCourseItem(
            course_id=course_id,
            type="section",
            title=title.strip(),
            sort_order=len(items),
        )
        db.add(item)
        await db.flush()
        return item
    item = LearningCourseItem(
        course_id=course_id,
        type=type_,
        title=title.strip(),
        # Описание только материалу (у теста — свои настройки в TestDrawer);
        # sanitize как у описания курса: в БД — чистый Markdown.
        description=sanitize_markdown(description) or None if type_ == "material" else None,
        url=url if type_ == "material" else None,
        sort_order=len(items),
    )
    db.add(item)
    await db.flush()
    if type_ == "test":
        # Тест существует целиком с настройками по умолчанию (§6.3): попытки
        # ссылаются FK на learning_tests, полуфабрикатов без строки быть не должно.
        db.add(
            LearningTest(
                item_id=item.id,
                pass_score=70,
                max_attempts=3,
                shuffle_answers=False,
                shuffle_questions=False,
            )
        )
        await db.flush()
    return item


async def reorder_items(
    db: AsyncSession, course_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    items = {i.id: i for i in await active_items(db, course_id)}
    if len(ordered_ids) != len(items) or any(i not in items for i in ordered_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Список должен содержать все активные элементы ровно один раз",
        )
    for pos, iid in enumerate(ordered_ids):
        items[iid].sort_order = pos
    await db.flush()


async def get_item(db: AsyncSession, item_id: uuid.UUID) -> LearningCourseItem | None:
    res = await db.execute(
        select(LearningCourseItem).where(
            LearningCourseItem.id == item_id, LearningCourseItem.deleted_at.is_(None)
        )
    )
    return res.scalar_one_or_none()


async def update_item(
    db: AsyncSession,
    item: LearningCourseItem,
    *,
    title: str | None,
    url: str | None,
    url_provided: bool = False,
    description: str | None = None,
    description_provided: bool = False,
) -> LearningCourseItem:
    """Правка элемента. ``url_provided``/``description_provided`` отличают
    «поле прислали» от «не трогать»: явный null у материала-ссылки очищает
    URL — но не в опубликованном курсе без PDF-файла (инвариант publish-gate
    §6.1: непроходимый материал); явный null у описания очищает описание."""
    if title is not None:
        item.title = title.strip()
    if description_provided:
        if item.type != "material":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Описание задаётся только материалу",
            )
        item.description = sanitize_markdown(description) or None
    if url_provided and url is None:
        if item.type != "material":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="URL задаётся только материалу"
            )
        course = await lock_course(db, item.course_id)
        if course is not None and course.status == "published" and not item.file_path:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "Снимите курс с публикации: после очистки URL "
                    "у материала не останется содержимого"
                ),
            )
        item.url = None
    elif url is not None:
        if item.type != "material":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="URL задаётся только материалу"
            )
        item.url = url
    item.updated_at = datetime.now(UTC)
    await db.flush()
    return item


async def soft_delete_item(db: AsyncSession, item: LearningCourseItem) -> None:
    item.deleted_at = datetime.now(UTC)
    item.updated_at = item.deleted_at
    await db.flush()


# ── участники ────────────────────────────────────────────────────────────────


def ensure_course_published(course: LearningCourse) -> None:
    """Зачисление возможно только на опубликованный курс: черновик невидим
    участнику (список «мои курсы» фильтрует published, прямая ссылка — 404),
    и письмо о зачислении вело сотрудника в никуда (прод-кейс 2026-09-02)."""
    if course.status != "published":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Курс ещё не опубликован — зачисление доступно после публикации",
        )


def course_link(*, course_slug: str, is_staff: bool) -> str:
    """Прямая ссылка на курс по §6.1 ТЗ: сотрудники — портал
    (``/learning/courses/<slug>``), внешние — learn-домен (``/courses/<slug>``,
    без префикса). Базы URL — те же, что у писем учёток (portal_base_url /
    learning_base_url из system.json)."""
    if is_staff:
        from app.core.system_config import load_system_settings

        base = load_system_settings().portal_base_url or learning_base_url()
        return f"{base}/learning/courses/{course_slug}"
    return f"{learning_base_url()}/courses/{course_slug}"


async def get_staff_identity(dba: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    """ФИО и email сотрудника для зачисления. Читает ``users`` — вызывать
    ТОЛЬКО с сессией основного движка: роль learning_app таблицу users не
    видит (§10.8), поэтому резолв личности живёт на границе роутера."""
    from app.models.user import User

    row = (
        await dba.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден")
    return row.full_name, row.email


async def get_external_identity(db: AsyncSession, account_id: uuid.UUID) -> tuple[str, str]:
    """ФИО и email внешней учётки (learning-таблица — читается её же ролью)."""
    acc = (
        await db.execute(
            select(LearningAccount).where(
                LearningAccount.id == account_id,
                LearningAccount.deleted_at.is_(None),
                LearningAccount.status == "active",
            )
        )
    ).scalar_one_or_none()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Внешняя учётка не найдена")
    return acc.full_name, acc.email


async def enroll_participant(
    db: AsyncSession,
    course: LearningCourse,
    *,
    user_id: uuid.UUID | None = None,
    learning_account_id: uuid.UUID | None = None,
    display_name: str,
    email: str,
    enrolled_by: uuid.UUID | None,
    notify: bool = True,
) -> LearningCourseParticipant:
    """Зачисление со снапшотом личности (миграция 103): письмо и отчёт
    прогресса не читают ``users`` — ограниченная DB-роль сохраняет гранты.
    Личность резолвится вызывающим кодом (get_staff_identity /
    get_external_identity) до вызова. ``notify=False`` — массовые покрытия
    «для всех сотрудников» (миграция 111), письма не шлём."""
    ensure_course_published(course)
    participant = LearningCourseParticipant(
        course_id=course.id,
        user_id=user_id,
        learning_account_id=learning_account_id,
        display_name=display_name,
        email=email,
        enrolled_by=enrolled_by,
    )
    db.add(participant)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Участник уже записан на курс"
        ) from exc

    # Письмо о зачислении — обоим типам (ТЗ §5.3 п.2); в той же транзакции.
    subject, text, html = emails.enrollment_letter(
        full_name=display_name,
        course_title=course.title,
        link=course_link(course_slug=course.slug, is_staff=user_id is not None),
    )
    if notify:
        await enqueue_outbox_email(
            db,
            kind="learning",
            to_email=email,
            subject=subject,
            body_html=html,
            body_text=text,
            related_resource_type="learning_course",
            related_resource_id=course.id,
        )
    return participant


async def enroll_participants_bulk(
    db: AsyncSession,
    dba: AsyncSession,
    course: LearningCourse,
    *,
    user_ids: list[uuid.UUID],
    enrolled_by: uuid.UUID | None,
) -> tuple[int, int, list[dict[str, str]]]:
    """Групповое зачисление сотрудников (этап 2, §15 «выборкой»).

    Дубли (уже зачисленные активные) пропускаются; личность — снапшотом
    (миграция 103) с батч-чтением ``users`` по основному движку на границе
    роутера; письма о зачислении — по одному на нового участника в той же
    транзакции. Возвращает ``(зачислено, пропущено_дублей, ошибки)``."""
    ensure_course_published(course)
    from app.models.user import User

    unique_ids = list(dict.fromkeys(user_ids))
    existing = set(
        (
            await db.execute(
                select(LearningCourseParticipant.user_id).where(
                    LearningCourseParticipant.course_id == course.id,
                    LearningCourseParticipant.deleted_at.is_(None),
                    LearningCourseParticipant.user_id.in_(unique_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    to_enroll = [uid for uid in unique_ids if uid not in existing]
    skipped = len(user_ids) - len(to_enroll)

    users = (
        (await dba.execute(select(User).where(User.id.in_(to_enroll), User.deleted_at.is_(None))))
        .scalars()
        .all()
        if to_enroll
        else []
    )
    by_id = {u.id: u for u in users}

    enrolled = 0
    errors: list[dict[str, str]] = []
    for uid in to_enroll:
        user = by_id.get(uid)
        if user is None:
            errors.append({"user_id": str(uid), "message": "Сотрудник не найден"})
            continue
        conflict = await _enroll_one_savepoint(
            db, course, user_id=uid, user=user, enrolled_by=enrolled_by
        )
        if conflict is None:
            enrolled += 1
        else:
            errors.append({"user_id": str(uid), "message": conflict})
    return enrolled, skipped, errors


async def _enroll_one_savepoint(
    db: AsyncSession,
    course: LearningCourse,
    *,
    user_id: uuid.UUID,
    user: Any,
    enrolled_by: uuid.UUID | None,
    notify: bool = True,
) -> str | None:
    """Одно зачисление внутри SAVEPOINT. Гонка с одиночным зачислением,
    вклинившимся после предварительного SELECT дублей, даёт IntegrityError
    только на «свою» строку (частичный уникальный индекс — арбитр, §12):
    savepoint откатывает её и письмо, батч продолжается, конфликт попадает
    в отчёт ошибок вместо 500 на commit роутера."""
    try:
        async with db.begin_nested():
            db.add(
                LearningCourseParticipant(
                    course_id=course.id,
                    user_id=user_id,
                    display_name=user.full_name,
                    email=user.email,
                    enrolled_by=enrolled_by,
                )
            )
            await db.flush()
            if not notify:
                return None
            subject, text, html = emails.enrollment_letter(
                full_name=user.full_name,
                course_title=course.title,
                link=course_link(course_slug=course.slug, is_staff=True),
            )
            await enqueue_outbox_email(
                db,
                kind="learning",
                to_email=user.email,
                subject=subject,
                body_html=html,
                body_text=text,
                related_resource_type="learning_course",
                related_resource_id=course.id,
            )
    except IntegrityError:
        return "Уже зачислен (параллельное зачисление)"
    return None


async def enroll_all_staff_missing(
    db: AsyncSession,
    dba: AsyncSession,
    course: LearningCourse,
    *,
    enrolled_by: uuid.UUID | None,
) -> int:
    """Материализация участников обязательного курса «для всех сотрудников»
    (миграция 111): всем активным сотрудникам без явной строки создаётся
    зачисление БЕЗ писем (массовое покрытие). Новые сотрудники доезжают
    set-based вставкой после Keycloak-синка; доступ и до материализации
    виртуальный (has_course_access). Возвращает число дозачисленных."""
    from app.models.user import User

    existing = {
        row[0]
        for row in (
            await db.execute(
                select(LearningCourseParticipant.user_id).where(
                    LearningCourseParticipant.course_id == course.id,
                    LearningCourseParticipant.deleted_at.is_(None),
                    LearningCourseParticipant.user_id.is_not(None),
                )
            )
        ).all()
    }
    users = (
        (await dba.execute(select(User).where(User.deleted_at.is_(None)).order_by(User.full_name)))
        .scalars()
        .all()
    )
    enrolled = 0
    for user in users:
        if user.id in existing:
            continue
        conflict = await _enroll_one_savepoint(
            db,
            course,
            user_id=user.id,
            user=user,
            enrolled_by=enrolled_by,
            notify=False,
        )
        if conflict is None:
            enrolled += 1
    return enrolled


async def unenroll_participant(
    db: AsyncSession, participant_id: uuid.UUID, course_id: uuid.UUID
) -> bool:
    res = await db.execute(
        select(LearningCourseParticipant).where(
            LearningCourseParticipant.id == participant_id,
            LearningCourseParticipant.course_id == course_id,
            LearningCourseParticipant.deleted_at.is_(None),
        )
    )
    participant = res.scalar_one_or_none()
    if not participant:
        return False
    participant.deleted_at = datetime.now(UTC)  # история попыток остаётся (§7)
    return True


# ── прогресс ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProgressRow:
    participant_id: uuid.UUID
    kind: str  # staff | external
    display_name: str
    email: str
    enrolled_at: datetime
    completed_items: frozenset[uuid.UUID]
    passed_tests: frozenset[uuid.UUID]
    has_certificate: bool = False


def _participant_key(
    *, user_id: uuid.UUID | None, learning_account_id: uuid.UUID | None
) -> tuple[str, uuid.UUID]:
    ident = user_id if user_id is not None else learning_account_id
    kind = "user" if user_id is not None else "acc"
    if ident is None:  # XOR-CHECK в БД исключает NULL с обеих сторон; страховка
        raise ValueError("participant without principal")
    return kind, ident


async def _collect_completed_materials(
    db: AsyncSession, material_ids: list[uuid.UUID]
) -> dict[tuple[str, uuid.UUID], set[uuid.UUID]]:
    """Отметки «ознакомлен» по участникам."""
    done: dict[tuple[str, uuid.UUID], set[uuid.UUID]] = {}
    if not material_ids:
        return done
    for pr in (
        (
            await db.execute(
                select(LearningItemProgress).where(LearningItemProgress.item_id.in_(material_ids))
            )
        )
        .scalars()
        .all()
    ):
        key = _participant_key(user_id=pr.user_id, learning_account_id=pr.learning_account_id)
        done.setdefault(key, set()).add(pr.item_id)
    return done


async def _collect_passed_tests(
    db: AsyncSession, test_ids: list[uuid.UUID]
) -> dict[tuple[str, uuid.UUID], set[uuid.UUID]]:
    """Пройденные тесты: правило «последний» — берём последнюю submitted-попытку
    каждого участника по каждому тесту (ТЗ §6.3) и смотрим её флаг passed."""
    passed: dict[tuple[str, uuid.UUID], set[uuid.UUID]] = {}
    if not test_ids:
        return passed
    attempts = (
        (
            await db.execute(
                select(LearningTestAttempt)
                .where(
                    LearningTestAttempt.test_item_id.in_(test_ids),
                    LearningTestAttempt.submitted_at.is_not(None),
                )
                .order_by(LearningTestAttempt.submitted_at)
            )
        )
        .scalars()
        .all()
    )
    last: dict[tuple[str, uuid.UUID, uuid.UUID], LearningTestAttempt] = {}
    for at in attempts:
        key = _participant_key(user_id=at.user_id, learning_account_id=at.learning_account_id)
        last[(key[0], key[1], at.test_item_id)] = at  # поздняя перезаписывает раннюю
    for (kind, pid, test_item), at in last.items():
        if at.passed and pid is not None:
            passed.setdefault((kind, pid), set()).add(test_item)
    return passed


def _build_progress_rows(
    parts: list[LearningCourseParticipant],
    done: dict[tuple[str, uuid.UUID], set[uuid.UUID]],
    passed: dict[tuple[str, uuid.UUID], set[uuid.UUID]],
    certified: frozenset[tuple[str, uuid.UUID]] | None = None,
) -> list[ProgressRow]:
    """Сопоставляет участникам личность из снапшота зачисления (миграция 103:
    чтение users под ролью learning_app недоступно) и агрегаты; сортировка
    по зачислению. Строки без снапшота (не должно быть после бэкфилла)
    пропускаются — как раньше пропускались исчезнувшие личности."""
    rows_out: list[ProgressRow] = []
    for p in sorted(parts, key=lambda x: x.enrolled_at):
        if not p.display_name:
            continue
        kind = "staff" if p.user_id is not None else "external"
        pid = p.user_id if p.user_id is not None else p.learning_account_id
        if pid is None:  # XOR-CHECK в БД исключает; страховка для mypy
            continue
        key = ("user" if kind == "staff" else "acc", pid)
        rows_out.append(
            ProgressRow(
                participant_id=p.id,
                kind=kind,
                display_name=p.display_name,
                email=p.email or "",
                enrolled_at=p.enrolled_at,
                completed_items=frozenset(done.get(key, set())),
                passed_tests=frozenset(passed.get(key, set())),
                has_certificate=certified is not None and key in certified,
            )
        )
    return rows_out


async def compute_progress(db: AsyncSession, course_id: uuid.UUID) -> tuple[int, list[ProgressRow]]:
    """Общая строка на участника с бейджем категории (§8 «бейдж сотрудник/внешний»).
    Разделы-заголовки (type='section') в прогрессе не участвуют."""
    items = await active_items(db, course_id)
    graded = [i for i in items if i.type != "section"]
    material_ids = [i.id for i in graded if i.type == "material"]
    test_ids = [i.id for i in graded if i.type == "test"]

    parts = list(
        (
            await db.execute(
                select(LearningCourseParticipant).where(
                    LearningCourseParticipant.course_id == course_id,
                    LearningCourseParticipant.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    done = await _collect_completed_materials(db, material_ids)
    passed = await _collect_passed_tests(db, test_ids)
    certified = await _collect_certified(db, course_id)
    return len(graded), _build_progress_rows(parts, done, passed, certified)


async def _collect_certified(
    db: AsyncSession, course_id: uuid.UUID
) -> frozenset[tuple[str, uuid.UUID]]:
    """Ключи участников, получивших сертификат курса (этап 2)."""
    rows = (
        await db.execute(
            select(LearningCertificate.user_id, LearningCertificate.learning_account_id).where(
                LearningCertificate.course_id == course_id
            )
        )
    ).all()
    certified: set[tuple[str, uuid.UUID]] = set()
    for uid, aid in rows:
        if uid is not None:
            certified.add(("user", uid))
        if aid is not None:
            certified.add(("acc", aid))
    return frozenset(certified)


def progress_to_api(course_id: uuid.UUID, total_items: int, rows: list[ProgressRow]) -> dict:
    participants = []
    for r in rows:
        completed = len(r.completed_items | r.passed_tests)
        participants.append(
            ParticipantOut(
                id=r.participant_id,
                participant_kind=r.kind,
                display_name=r.display_name,
                email=r.email,
                enrolled_at=r.enrolled_at,
                progress_completed=completed,
                progress_total=total_items,
                has_certificate=r.has_certificate,
            )
        )
    return {
        "course_id": str(course_id),
        "total_items": total_items,
        "participants": [p.model_dump(mode="json") for p in participants],
    }


# ── курсы глазами участника (сотрудник ИЛИ внешняя учётка) ───────────────────


async def active_participants(
    db: AsyncSession, course_id: uuid.UUID
) -> list[LearningCourseParticipant]:
    res = await db.execute(
        select(LearningCourseParticipant).where(
            LearningCourseParticipant.course_id == course_id,
            LearningCourseParticipant.deleted_at.is_(None),
        )
    )
    return list(res.scalars().all())


async def has_active_enrollment(
    db: AsyncSession, participant: LearningParticipant, course_id: uuid.UUID
) -> bool:
    res = await db.execute(
        select(LearningCourseParticipant.id)
        .where(
            LearningCourseParticipant.course_id == course_id,
            LearningCourseParticipant.deleted_at.is_(None),
            participant.matching(LearningCourseParticipant),
        )
        .limit(1)
    )
    return res.first() is not None


def _course_unavailable() -> HTTPException:
    # Одинаковый ответ для «не существует» / «не опубликован» / «не участник» —
    # знание ссылки само по себе доступа не даёт и перечисление бесполезно.
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Курс недоступен")


async def get_published_course_by_slug(db: AsyncSession, slug: str) -> LearningCourse:
    res = await db.execute(
        select(LearningCourse).where(
            LearningCourse.slug == slug,
            LearningCourse.deleted_at.is_(None),
            LearningCourse.status == "published",
        )
    )
    course = res.scalar_one_or_none()
    if course is None:
        raise _course_unavailable()
    return course


async def has_course_access(
    db: AsyncSession, participant: LearningParticipant, course: LearningCourse
) -> bool:
    """Явное зачисление ИЛИ обязательный «для всех сотрудников» (миграция 111):
    флаг распространяется только на сотрудников — внешние учётки зачисляются
    явно."""
    if participant.kind == KIND_USER and course.for_all_staff:
        return True
    return await has_active_enrollment(db, participant, course.id)


async def assert_participant_access(
    db: AsyncSession, participant: LearningParticipant, course: LearningCourse
) -> None:
    if not await has_course_access(db, participant, course):
        raise _course_unavailable()


def _completion_of_key(
    done: dict[tuple[str, uuid.UUID], set[uuid.UUID]],
    passed: dict[tuple[str, uuid.UUID], set[uuid.UUID]],
    key: tuple[str, uuid.UUID],
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    return done.get(key, set()), passed.get(key, set())


async def my_course_list(
    db: AsyncSession, participant: LearningParticipant
) -> list[tuple[LearningCourse, int, int, str | None, int | None]]:
    """Опубликованные активные курсы участника
    + (пройдено, всего, категория_название, категория_порядок).
    Разделы-заголовки (type='section') в прогрессе не участвуют."""
    enrolled = set(
        (
            await db.execute(
                select(LearningCourseParticipant.course_id).where(
                    LearningCourseParticipant.deleted_at.is_(None),
                    participant.matching(LearningCourseParticipant),
                )
            )
        )
        .scalars()
        .all()
    )
    # Обязательные «для всех сотрудников» (миграция 111): виртуальное
    # зачисление — курс виден сотруднику сразу, без материализованной строки.
    if participant.kind == KIND_USER:
        enrolled |= set(
            (
                await db.execute(
                    select(LearningCourse.id).where(
                        LearningCourse.for_all_staff.is_(True),
                        LearningCourse.deleted_at.is_(None),
                        LearningCourse.status == "published",
                    )
                )
            )
            .scalars()
            .all()
        )
    if not enrolled:
        return []
    rows = list(
        (
            await db.execute(
                select(
                    LearningCourse,
                    LearningCourseCategory.title,
                    LearningCourseCategory.sort_order,
                )
                .outerjoin(
                    LearningCourseCategory,
                    LearningCourse.category_id == LearningCourseCategory.id,
                )
                .where(
                    LearningCourse.id.in_(list(enrolled)),
                    LearningCourse.deleted_at.is_(None),
                    LearningCourse.status == "published",
                )
                .order_by(LearningCourse.published_at.desc().nullslast())
            )
        ).all()
    )
    if not rows:
        return []
    course_ids = [c.id for c, _cat_title, _cat_sort in rows]
    items = (
        (
            await db.execute(
                select(LearningCourseItem).where(
                    LearningCourseItem.course_id.in_(course_ids),
                    LearningCourseItem.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    material_ids = [i.id for i in items if i.type == "material"]
    test_ids = [i.id for i in items if i.type == "test"]
    done = await _collect_completed_materials(db, material_ids)
    passed = await _collect_passed_tests(db, test_ids)
    my_done, my_passed = _completion_of_key(done, passed, participant.key())

    total_by_course: dict[uuid.UUID, int] = {}
    completed_by_course: dict[uuid.UUID, int] = {}
    for it in items:
        if it.type == "section":
            continue
        total_by_course[it.course_id] = total_by_course.get(it.course_id, 0) + 1
        completed_flag = it.id in my_done or (it.type == "test" and it.id in my_passed)
        if completed_flag:
            completed_by_course[it.course_id] = completed_by_course.get(it.course_id, 0) + 1
    return [
        (
            c,
            completed_by_course.get(c.id, 0),
            total_by_course.get(c.id, 0),
            cat_title,
            cat_sort,
        )
        for c, cat_title, cat_sort in rows
    ]


async def course_for_participant(
    db: AsyncSession, participant: LearningParticipant, slug: str
) -> tuple[LearningCourse, list[MyCourseItem]]:
    """Карточка курса участнику: элементы с флагом пройденности."""
    course = await get_published_course_by_slug(db, slug)
    await assert_participant_access(db, participant, course)
    return course, await items_with_completion(db, course.id, participant)


@dataclass(frozen=True, slots=True)
class MyCourseItem:
    item: LearningCourseItem
    completed: bool


async def items_with_completion(
    db: AsyncSession, course_id: uuid.UUID, participant: LearningParticipant
) -> list[MyCourseItem]:
    """Элементы курса с флагом завершённости конкретного участника. Без гейтов
    публикации/доступа — их делает вызывающий (learner-роутер проверяет
    публикацию и доступ, админ-эндпоинт — роль методиста)."""
    items = await active_items(db, course_id)
    material_ids = [i.id for i in items if i.type == "material"]
    test_ids = [i.id for i in items if i.type == "test"]
    done = await _collect_completed_materials(db, material_ids)
    passed = await _collect_passed_tests(db, test_ids)
    my_done, my_passed = _completion_of_key(done, passed, participant.key())

    return [
        MyCourseItem(
            item=i,
            completed=i.id in my_done or (i.type == "test" and i.id in my_passed),
        )
        for i in items
    ]


@dataclass(frozen=True, slots=True)
class ParticipantItemStatus:
    """Строка детализации «как решён курс» (панель участников, методист)."""

    item_id: uuid.UUID
    title: str
    type: str  # 'material' | 'test'
    completed: bool
    test_passed: bool
    attempts_submitted: int


async def participant_items_status(
    db: AsyncSession, course_id: uuid.UUID, participant: LearningParticipant
) -> list[ParticipantItemStatus]:
    """Статус каждого элемента курса для участника + число отправленных попыток
    по тестам (для решения о сбросе лимита, §6.3). Прогресс считается по тем же
    правилам, что и compute_progress: материал — отметка «ознакомлен», тест —
    passed последней отправленной попытки."""
    items = await active_items(db, course_id)
    material_ids = [i.id for i in items if i.type == "material"]
    test_ids = [i.id for i in items if i.type == "test"]
    done = await _collect_completed_materials(db, material_ids)
    passed = await _collect_passed_tests(db, test_ids)
    my_done, my_passed = _completion_of_key(done, passed, participant.key())

    submitted: dict[uuid.UUID, int] = {}
    if test_ids:
        rows = (
            await db.execute(
                select(LearningTestAttempt.test_item_id, func.count())
                .where(
                    LearningTestAttempt.test_item_id.in_(test_ids),
                    participant.matching(LearningTestAttempt),
                    # лимит попыток считает только отправленные — тут то же правило
                    LearningTestAttempt.submitted_at.is_not(None),
                )
                .group_by(LearningTestAttempt.test_item_id)
            )
        ).all()
        submitted = {test_item_id: count for test_item_id, count in rows}

    return [
        ParticipantItemStatus(
            item_id=i.id,
            title=i.title,
            type=i.type,
            completed=i.id in my_done or (i.type == "test" and i.id in my_passed),
            test_passed=i.type == "test" and i.id in my_passed,
            attempts_submitted=submitted.get(i.id, 0),
        )
        # разделы-заголовки в детализации «как решён курс» не показываются
        for i in items
        if i.type != "section"
    ]


async def complete_material(
    db: AsyncSession, participant: LearningParticipant, item: LearningCourseItem
) -> bool:
    """Отметка «ознакомлен». Повторная отметка — не ошибка (идемпотентна)."""
    if item.type != "material":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Отмечается только материал"
        )
    row = LearningItemProgress(
        item_id=item.id,
        user_id=participant.user_id,
        learning_account_id=participant.learning_account_id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return False
    return True


__all__ = [
    "MATERIAL_MAX_BYTES",
    "MATERIAL_MIME",
    "MyCourseItem",
    "assert_participant_access",
    "complete_material",
    "compute_progress",
    "course_for_participant",
    "course_link",
    "create_course",
    "enroll_all_staff_missing",
    "enroll_participant",
    "get_external_identity",
    "get_item",
    "get_published_course_by_slug",
    "get_staff_identity",
    "has_active_enrollment",
    "has_course_access",
    "list_courses",
    "my_course_list",
    "progress_to_api",
    "reorder_items",
    "set_published",
    "slugify",
    "soft_delete_course",
    "soft_delete_item",
    "unenroll_participant",
    "update_course",
    "update_item",
]
