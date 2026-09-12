"""Тесты курса: настройки и вопросы методиста + движок попыток (ТЗ §6.3).

Правила ТЗ: вопросы равновесные (итог = доля верных вопросов); multi
засчитывается только при полном совпадении набора (частично верный = 0);
лимит считается по отправленным попыткам (брошенная помечается abandoned
спустя 24 часа); правильные ответы участнику не отдаются; тест с любой
попыткой (даже начатой) неизменяем — снапшот хранит порядок показа, а
задание фиксируется замком правок; правится только копией элемента.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import (
    LearningCourse,
    LearningCourseItem,
    LearningCourseParticipant,
    LearningItemProgress,
    LearningQuestion,
    LearningQuestionOption,
    LearningTest,
    LearningTestAttempt,
)
from app.schemas.learning import LearnerOptionOut, LearnerQuestionOut
from app.services.learning.participant import LearningParticipant


def _now() -> datetime:
    return datetime.now(UTC)


async def get_test(db: AsyncSession, item_id: uuid.UUID) -> LearningTest | None:
    res = await db.execute(select(LearningTest).where(LearningTest.item_id == item_id))
    return res.scalar_one_or_none()


# ── неизменяемость теста (§15: после попыток правится только копией) ─────────


async def assert_test_editable(
    db: AsyncSession, test_item_id: uuid.UUID, *, denied: str = "Правка запрещена"
) -> None:
    """Замок §15: при наличии попыток конфигурация теста неизменяема.

    Ряд настроек ``learning_tests`` — общий замок с ``start_attempt``: обе
    операции сериализуются на ``FOR UPDATE`` одной строки, поэтому «нет
    попыток» проверяется под тем же локом, под которым попытка создаётся.
    Обычный SELECT гонкоопасен: старт попытки вклинивается между проверкой
    и правкой, и правка меняет уже начатый тест (ревью 2026-08-28, P1).

    :param denied: формулировка запрета в 409 (правка/удаление/...)."""

    await db.execute(
        select(LearningTest.item_id).where(LearningTest.item_id == test_item_id).with_for_update()
    )
    has_any_attempt = (
        await db.execute(
            select(LearningTestAttempt.id)
            .where(LearningTestAttempt.test_item_id == test_item_id)
            .limit(1)
        )
    ).first() is not None
    if not has_any_attempt:
        return
    await _flag_test_config_used(db, test_item_id)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"По тесту есть попытки — {denied}, правится только копией элемента",
    )


async def _flag_test_config_used(db: AsyncSession, test_item_id: uuid.UUID) -> None:
    """Маркер «тест уже использован попытками» на элементе курса."""
    await db.execute(
        update(LearningCourseItem)
        .where(LearningCourseItem.id == test_item_id)
        .values(test_config_used=True, updated_at=_now())
    )


def normalize_options(options: list[dict[str, Any]], *, multi: bool) -> None:
    """Валидация флагов правильности + sort_order строго по порядку ввода."""
    correct = sum(1 for o in options if o["is_correct"])
    if correct == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Нужен хотя бы один правильный вариант",
        )
    if not multi and correct > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="У вопроса с единственным ответом — ровно один правильный вариант",
        )
    for pos, o in enumerate(options):
        o["sort_order"] = pos


async def _replace_options(
    db: AsyncSession, question_id: uuid.UUID, options: list[dict[str, Any]]
) -> None:
    """Полная замена набора вариантов. Легитимно, потому что вызовы идут только
    под ``assert_test_editable``: до первой попытки на варианты ничто не
    ссылается (замок включает и начатые попытки)."""
    await db.execute(
        sa_delete(LearningQuestionOption).where(LearningQuestionOption.question_id == question_id)
    )
    for pos, o in enumerate(options):
        db.add(
            LearningQuestionOption(
                question_id=question_id,
                text=o["text"],
                is_correct=o["is_correct"],
                sort_order=pos,
            )
        )


# ── чтение вопросов ──────────────────────────────────────────────────────────


async def questions_with_options(
    db: AsyncSession, test_item_id: uuid.UUID, *, include_correct: bool
) -> list[tuple[LearningQuestion, list[LearningQuestionOption]]]:
    """Вопросы теста в служебном порядке (sort_order). Для участника
    ``include_correct=False`` — флаги правильности наружу не уходят."""
    q_rows = list(
        (
            await db.execute(
                select(LearningQuestion)
                .where(LearningQuestion.test_item_id == test_item_id)
                .order_by(LearningQuestion.sort_order, LearningQuestion.id)
            )
        )
        .scalars()
        .all()
    )
    if not q_rows:
        return []
    o_rows = list(
        (
            await db.execute(
                select(LearningQuestionOption)
                .where(LearningQuestionOption.question_id.in_([q.id for q in q_rows]))
                .order_by(LearningQuestionOption.sort_order, LearningQuestionOption.id)
            )
        )
        .scalars()
        .all()
    )
    by_question: dict[uuid.UUID, list[LearningQuestionOption]] = {}
    for o in o_rows:
        by_question.setdefault(o.question_id, []).append(o)
    pairs = [(q, by_question.get(q.id, [])) for q in q_rows]
    if include_correct:
        return pairs
    # Флаг обнуляется на объекте, который пойдёт в сериализацию участнику;
    # реальная скрытность обеспечивается отдельной learner-схемой ответов,
    # здесь дополнительная страховка от утечки is_correct наружу.
    for _, opts in pairs:
        for o in opts:
            o.is_correct = False
    return pairs


# ── настройки и вопросы (методист) ───────────────────────────────────────────


async def update_settings(
    db: AsyncSession,
    item: LearningCourseItem,
    *,
    pass_score: int | None,
    max_attempts: int | None,
    shuffle_questions: bool | None,
    shuffle_answers: bool | None,
    time_limit_minutes: int | None = None,
    time_limit_provided: bool = False,
) -> LearningTest:
    if item.type != "test":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Настройки есть только у теста"
        )
    await assert_test_editable(db, item.id)
    test = await get_test(db, item.id)
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    if pass_score is not None:
        test.pass_score = pass_score
    if max_attempts is not None:
        test.max_attempts = max_attempts
    if shuffle_questions is not None:
        test.shuffle_questions = shuffle_questions
    if shuffle_answers is not None:
        test.shuffle_answers = shuffle_answers
    if time_limit_provided:
        # Явно переданный None снимает ограничение (router использует
        # model_fields_set: отсутствующее поле «не менять»).
        test.time_limit_minutes = time_limit_minutes
    await db.execute(
        update(LearningCourseItem).where(LearningCourseItem.id == item.id).values(updated_at=_now())
    )
    await db.flush()
    return test


async def add_question(
    db: AsyncSession,
    item: LearningCourseItem,
    *,
    text: str,
    multi: bool,
    options: list[dict[str, Any]],
) -> LearningQuestion:
    if item.type != "test":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Вопросы добавляются тесту"
        )
    normalize_options(options, multi=multi)
    await assert_test_editable(db, item.id)
    position = (
        await db.execute(
            select(func.count())
            .select_from(LearningQuestion)
            .where(LearningQuestion.test_item_id == item.id)
        )
    ).scalar_one()
    question = LearningQuestion(
        test_item_id=item.id, text=text.strip(), multi=multi, sort_order=int(position)
    )
    db.add(question)
    await db.flush()
    await _replace_options(db, question.id, options)
    await db.flush()
    return question


async def add_questions_bulk(
    db: AsyncSession,
    item: LearningCourseItem,
    questions: list[dict[str, Any]],
) -> int:
    """Пакетное добавление вопросов из xlsx-импорта (этап 2, §13).

    Замок §15 проверяется ОДИН раз на пакет (а не на вопрос) — под тем же
    FOR UPDATE, что и одиночные правки. Вопросы продолжают нумерацию
    существующих; варианты вставляются тем же _replace_options. Возвращает
    число созданных вопросов."""
    if not questions:
        return 0
    if item.type != "test":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Вопросы добавляются тесту"
        )
    await assert_test_editable(db, item.id)
    position = int(
        (
            await db.execute(
                select(func.count())
                .select_from(LearningQuestion)
                .where(LearningQuestion.test_item_id == item.id)
            )
        ).scalar_one()
    )
    for offset, spec in enumerate(questions):
        multi = bool(spec["multi"])
        options = [{"text": o["text"], "is_correct": o["is_correct"]} for o in spec["options"]]
        normalize_options(options, multi=multi)
        question = LearningQuestion(
            test_item_id=item.id,
            text=str(spec["text"]).strip(),
            multi=multi,
            sort_order=position + offset,
        )
        db.add(question)
        await db.flush()
        await _replace_options(db, question.id, options)
    await db.flush()
    return len(questions)


async def get_question(db: AsyncSession, question_id: uuid.UUID) -> LearningQuestion | None:
    res = await db.execute(select(LearningQuestion).where(LearningQuestion.id == question_id))
    return res.scalar_one_or_none()


async def update_question(
    db: AsyncSession,
    question: LearningQuestion,
    *,
    text: str,
    multi: bool,
    options: list[dict[str, Any]],
) -> LearningQuestion:
    normalize_options(options, multi=multi)
    await assert_test_editable(db, question.test_item_id)
    question.text = text.strip()
    question.multi = multi
    await _replace_options(db, question.id, options)
    await db.flush()
    return question


async def delete_question(db: AsyncSession, question: LearningQuestion) -> None:
    # Варианты и вопрос физически удалять можно только до первой попытки
    # (замок включает и начатые): под замком на них ещё нет ссылок из снапшотов.
    await assert_test_editable(db, question.test_item_id)
    await db.execute(sa_delete(LearningQuestion).where(LearningQuestion.id == question.id))
    await db.execute(
        update(LearningCourseItem)
        .where(LearningCourseItem.id == question.test_item_id)
        .values(updated_at=_now())
    )


# ── движок попыток ───────────────────────────────────────────────────────────

ATTEMPT_ABANDON_AFTER = timedelta(hours=24)


def remaining_attempts(max_attempts: int, submitted_count: int) -> int | None:
    if max_attempts <= 0:  # 0 = неограниченно (§6.3)
        return None
    return max(max_attempts - submitted_count, 0)


async def mark_stale_abandoned(
    db: AsyncSession,
    participant: LearningParticipant,
    *,
    test_item_id: uuid.UUID | None = None,
) -> int:
    """Брошенные попытки → abandoned. Два критерия: открытая дольше 24ч (§6.3)
    ИЛИ просроченная по таймеру теста (§15) — иначе попытка, истёкшая по
    ``time_limit_minutes``, блокировала бы участника до общего 24-часового
    cutoff: повторный старт возвращал бы её же, а submit отклонял 409.
    Вызывается лениво при старте/листинге — cron-задания схема ТЗ не требует."""
    now = _now()
    cutoff = now - ATTEMPT_ABANDON_AFTER
    stale = or_(
        LearningTestAttempt.started_at < cutoff,
        and_(
            LearningTest.time_limit_minutes.is_not(None),
            LearningTestAttempt.started_at
            + func.make_interval(0, 0, 0, 0, 0, LearningTest.time_limit_minutes)
            < now,
        ),
    )
    stmt = (
        update(LearningTestAttempt)
        .where(
            participant.matching(LearningTestAttempt),
            LearningTestAttempt.submitted_at.is_(None),
            LearningTestAttempt.abandoned_at.is_(None),
            # JOIN-условие UPDATE..FROM: таймер берётся строго у СВОЕГО теста
            # (без него лимит чужого теста клеймит попытки всех остальных).
            LearningTest.item_id == LearningTestAttempt.test_item_id,
            stale,
        )
        .values(abandoned_at=now)
        .returning(LearningTestAttempt.id)
    )
    if test_item_id is not None:
        stmt = stmt.where(LearningTestAttempt.test_item_id == test_item_id)
    res = await db.execute(stmt)
    return len(res.scalars().all())


def _snapshot_for(
    test: LearningTest,
    pairs: Sequence[tuple[LearningQuestion, list[LearningQuestionOption]]],
) -> dict[str, Any]:
    """Снапшот порядка вопросов/вариантов (§15): по нему воспроизводим показ
    возобновлённой попытки точно таким же, каким был при старте."""
    order_q = list(pairs)
    if test.shuffle_questions:
        secrets.SystemRandom().shuffle(order_q)
    option_order: dict[str, list[str]] = {}
    ordered_qids: list[str] = []
    for q, opts in order_q:
        opts_l = list(opts)
        if test.shuffle_answers:
            secrets.SystemRandom().shuffle(opts_l)
        option_order[str(q.id)] = [str(o.id) for o in opts_l]
        ordered_qids.append(str(q.id))
    return {"version": 1, "order": ordered_qids, "option_order": option_order}


async def count_submitted(
    db: AsyncSession, participant: LearningParticipant, test_item_id: uuid.UUID
) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(LearningTestAttempt)
                .where(
                    participant.matching(LearningTestAttempt),
                    LearningTestAttempt.test_item_id == test_item_id,
                    LearningTestAttempt.submitted_at.is_not(None),
                )
            )
        ).scalar_one()
    )


async def start_attempt(
    db: AsyncSession,
    participant: LearningParticipant,
    *,
    item: LearningCourseItem,
    course_published: bool,
) -> tuple[LearningTestAttempt, bool]:
    """Начать (или возобновить открытую) попытку. Возвращает (попытка, создана).
    Гейты зачисления проверяет роут через courses_service; здесь — публикация
    курса, тип элемента и лимит."""

    if not course_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Курс недоступен")
    if item.type != "test":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Попытка существует только у теста"
        )

    # Сериализуем параллельные старты одной и той же попытки на строке настроек
    # теста: двойной расход лимита невозможен, пока оба запроса читают
    # FOR UPDATE один и тот же learning_tests.item_id.
    test = (
        await db.execute(
            select(LearningTest).where(LearningTest.item_id == item.id).with_for_update()
        )
    ).scalar_one_or_none()
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Тест не настроен")

    # Item был прочитан роутом до ожидания test-lock. Удаление могло получить
    # этот lock первым и закоммитить soft-delete, поэтому состояние перечитываем
    # уже внутри общей критической секции. Курс блокируем тем же row-lock,
    # которым сериализованы publish/unpublish/delete и добавление элементов.
    item_course_id = (
        await db.execute(
            select(LearningCourseItem.course_id).where(
                LearningCourseItem.id == item.id,
                LearningCourseItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if item_course_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Курс недоступен")

    course_state = (
        await db.execute(
            select(LearningCourse.status)
            .where(
                LearningCourse.id == item_course_id,
                LearningCourse.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if course_state != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Курс недоступен")

    has_enrollment = (
        await db.execute(
            select(LearningCourseParticipant.id)
            .where(
                LearningCourseParticipant.course_id == item_course_id,
                LearningCourseParticipant.deleted_at.is_(None),
                participant.matching(LearningCourseParticipant),
            )
            .limit(1)
        )
    ).first()
    if has_enrollment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Курс недоступен")

    await mark_stale_abandoned(db, participant, test_item_id=item.id)

    open_attempt = (
        await db.execute(
            select(LearningTestAttempt)
            .where(
                participant.matching(LearningTestAttempt),
                LearningTestAttempt.test_item_id == item.id,
                LearningTestAttempt.submitted_at.is_(None),
                LearningTestAttempt.abandoned_at.is_(None),
            )
            .order_by(LearningTestAttempt.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if open_attempt is not None:
        return open_attempt, False  # возобновляем начатое, лимит не расходуется

    answerable = [
        (q, opts)
        for q, opts in await questions_with_options(db, item.id, include_correct=True)
        if opts
    ]
    if not answerable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="В тесте нет ни одного вопроса с вариантами",
        )

    left = remaining_attempts(test.max_attempts, await count_submitted(db, participant, item.id))
    if left is not None and left <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Лимит попыток исчерпан")

    attempt = LearningTestAttempt(
        test_item_id=item.id,
        user_id=participant.user_id,
        learning_account_id=participant.learning_account_id,
        started_at=_now(),
        answers=_snapshot_for(test, answerable),
    )
    db.add(attempt)
    await db.flush()
    return attempt, True


async def _owned_attempt(
    db: AsyncSession, participant: LearningParticipant, attempt_id: uuid.UUID
) -> LearningTestAttempt:
    res = await db.execute(
        select(LearningTestAttempt).where(
            LearningTestAttempt.id == attempt_id,
            participant.matching(LearningTestAttempt),
        )
    )
    attempt = res.scalar_one_or_none()
    if attempt is None or attempt.abandoned_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Попытка не найдена")
    return attempt


async def get_attempt_for_participant(
    db: AsyncSession, participant: LearningParticipant, attempt_id: uuid.UUID
) -> LearningTestAttempt | None:
    try:
        return await _owned_attempt(db, participant, attempt_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return None
        raise


def attempt_questions_view(
    attempts_snapshot: dict[str, Any],
    pairs_all: list[tuple[LearningQuestion, list[LearningQuestionOption]]],
) -> list[LearnerQuestionOut]:
    """Вопросы открытой попытки в порядке снапшота, без флагов правильности.
    Вопрос/варианты, удалённые методистом после старта, из выдачи выпадают."""
    order_ids = [uuid.UUID(raw) for raw in attempts_snapshot.get("order") or []]
    option_order: dict[uuid.UUID, list[uuid.UUID]] = {
        uuid.UUID(key): [uuid.UUID(raw) for raw in values]
        for key, values in (attempts_snapshot.get("option_order") or {}).items()
    }
    question_by_id = {q.id: q for q, _ in pairs_all}
    option_by_id = {o.id: o for _, opts in pairs_all for o in opts}

    out: list[LearnerQuestionOut] = []
    for qid in order_ids:
        row = question_by_id.get(qid)
        if row is None:
            continue
        options = [
            LearnerOptionOut(id=option_by_id[oid].id, text=option_by_id[oid].text)
            for oid in option_order.get(qid, [])
            if oid in option_by_id
        ]
        if not options:
            continue
        out.append(LearnerQuestionOut(id=row.id, text=row.text, multi=row.multi, options=options))
    return out


async def get_attempt_questions(
    db: AsyncSession, attempt: LearningTestAttempt
) -> list[LearnerQuestionOut]:
    return attempt_questions_view(
        attempt.answers or {},
        await questions_with_options(db, attempt.test_item_id, include_correct=False),
    )


def _parse_snapshot_order(attempt: LearningTestAttempt) -> list[uuid.UUID]:
    """Порядок вопросов из снапшота попытки (answers JSONB)."""
    return [uuid.UUID(raw) for raw in (attempt.answers or {}).get("order") or []]


def _normalize_responses(responses: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """Ключи приходят и UUID-ами (pydantic-путь), и строками (прямые вызовы
    сервисов) — нормализуем к строкам единообразно."""
    return {str(q): [str(g) for g in given] for q, given in (responses or {}).items()}


def _validate_known_questions(order_ids: list[uuid.UUID], normalized: dict[str, list[str]]) -> None:
    known = {str(q) for q in order_ids}
    if set(normalized) - known:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Ответ содержит неизвестный вопрос"
        )


async def _correct_options_map(
    db: AsyncSession, question_ids: list[uuid.UUID]
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    rows = (
        (
            await db.execute(
                select(LearningQuestionOption).where(
                    LearningQuestionOption.question_id.in_(question_ids),
                    LearningQuestionOption.is_correct.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    correct_by_question: dict[uuid.UUID, frozenset[uuid.UUID]] = {}
    for o in rows:
        current = set(correct_by_question.get(o.question_id, frozenset()))
        current.add(o.id)
        correct_by_question[o.question_id] = frozenset(current)
    return correct_by_question


def _question_is_correct(
    qid: uuid.UUID,
    correct_by_question: dict[uuid.UUID, frozenset[uuid.UUID]],
    normalized: dict[str, list[str]],
) -> bool:
    wanted = correct_by_question.get(qid)
    given = normalized.get(str(qid)) or []
    if not wanted or not given:
        return False  # не отвеченный или удалённый — неверный
    return frozenset(uuid.UUID(g) for g in given) == wanted


def _score_responses(
    order_ids: list[uuid.UUID],
    correct_by_question: dict[uuid.UUID, frozenset[uuid.UUID]],
    normalized: dict[str, list[str]],
) -> int:
    """Равновесные вопросы по снапшоту: доля верных, 0–100."""
    if not order_ids:
        return 0
    answered = sum(
        1 for qid in order_ids if _question_is_correct(qid, correct_by_question, normalized)
    )
    return round(answered * 100 / len(order_ids))


async def submit_attempt(
    db: AsyncSession,
    participant: LearningParticipant,
    attempt_id: uuid.UUID,
    responses: dict[str, list[str]],
) -> tuple[LearningTestAttempt, int]:
    """Принять ответы, посчитать балл. Правильные варианты берём из БД:
    с момента первой попытки тест заблокирован для правок
    (``assert_test_editable``), поэтому БД совпадает со снапшотом попытки."""
    attempt = await _owned_attempt(db, participant, attempt_id)
    if attempt.submitted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Попытка уже отправлена")

    test = await get_test(db, attempt.test_item_id)
    if test is None:  # FK гарантирует строку; страховка для mypy
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Тест не найден")

    # Таймер попытки (этап 2, §15): серверный контроль времени — ДО разбора
    # ответов: просроченная попытка клеймится abandoned и отклоняется (409)
    # независимо от тела запроса. Повторный submit ответа не выдаёт.
    expires_at = attempt_expires_at(test, attempt)
    if expires_at is not None and _now() > expires_at:
        attempt.abandoned_at = _now()
        # Клеймо должно пережить отклик 409: роутер в этой ветке не делает
        # commit (исключение уходит в FastAPI), поэтому фиксируем здесь.
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Время на попытку истекло — начните новую",
        )

    order_ids = _parse_snapshot_order(attempt)
    normalized = _normalize_responses(responses)
    _validate_known_questions(order_ids, normalized)
    correct_by_question = await _correct_options_map(db, order_ids)

    score = _score_responses(order_ids, correct_by_question, normalized)
    attempt.score = score
    attempt.passed = score >= test.pass_score
    attempt.submitted_at = _now()
    attempt.answers = {
        **(attempt.answers or {}),
        "responses": normalized,
    }
    await _flag_test_config_used(db, attempt.test_item_id)
    await db.flush()
    return attempt, score


def attempt_expires_at(test: LearningTest, attempt: LearningTestAttempt) -> datetime | None:
    """Абсолютный край открытой попытки или None (лимит не задан)."""
    if test.time_limit_minutes is None:
        return None
    return attempt.started_at + timedelta(minutes=test.time_limit_minutes)


async def my_attempts(
    db: AsyncSession,
    participant: LearningParticipant,
    test_item_id: uuid.UUID,
) -> tuple[list[LearningTestAttempt], int, int | None]:
    """Все попытки участника по тесту + счётчики лимита (свежий abandoned
    помечается лениво перед выдачей)."""
    await mark_stale_abandoned(db, participant, test_item_id=test_item_id)
    rows = list(
        (
            await db.execute(
                select(LearningTestAttempt)
                .where(
                    participant.matching(LearningTestAttempt),
                    LearningTestAttempt.test_item_id == test_item_id,
                )
                .order_by(LearningTestAttempt.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    test = await get_test(db, test_item_id)
    max_attempts = test.max_attempts if test is not None else 0
    submitted = sum(1 for a in rows if a.submitted_at is not None)
    return rows, submitted, remaining_attempts(max_attempts, submitted)


async def reset_attempts(
    db: AsyncSession, participant: LearningParticipant, test_item_id: uuid.UUID
) -> int:
    """Сброс попыток теста участнику (методист, панель участников): удаляются
    все попытки (включая брошенные) и отметка прохождения — тест снова
    «Не пройден», лимит попыток обнулён. Попытки — факты без soft-delete;
    аудит сброса пишет роутер. Возвращает число удалённых попыток."""
    result = await db.execute(
        sa_delete(LearningTestAttempt).where(
            participant.matching(LearningTestAttempt),
            LearningTestAttempt.test_item_id == test_item_id,
        )
    )
    await db.execute(
        sa_delete(LearningItemProgress).where(
            participant.matching(LearningItemProgress),
            LearningItemProgress.item_id == test_item_id,
        )
    )
    return int(cast(CursorResult, result).rowcount or 0)


__all__ = [
    "ATTEMPT_ABANDON_AFTER",
    "add_question",
    "count_submitted",
    "delete_question",
    "get_attempt_for_participant",
    "get_attempt_questions",
    "get_question",
    "get_test",
    "mark_stale_abandoned",
    "my_attempts",
    "questions_with_options",
    "remaining_attempts",
    "reset_attempts",
    "start_attempt",
    "submit_attempt",
    "update_question",
    "update_settings",
]
