"""Users data access layer."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, delete, func, or_, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.staff_order import StaffDepartmentOrder
from app.models.user import User
from app.utils.keyboard_layout import layout_variants


def _build_list_conditions(
    q: str | None,
    department: str | None,
    office: str | None = None,
    *,
    include_hidden: bool = True,
) -> list[Any]:
    conditions: list[Any] = [User.deleted_at.is_(None)]
    if not include_hidden:
        conditions.append(User.staff_hidden.is_(False))
    if q:
        clauses: list[Any] = []
        for variant in layout_variants(q):
            pattern = f"%{variant}%"
            clauses.append(
                User.full_name.ilike(pattern)
                | User.email.ilike(pattern)
                | User.position.ilike(pattern)
                | User.phone.ilike(pattern)
                | User.attributes["internal_phone"].astext.ilike(pattern)
                | User.attributes["mobile"].astext.ilike(pattern)
            )
        if clauses:
            conditions.append(or_(*clauses))
    if department:
        conditions.append(User.department == department)
    if office:
        conditions.append(User.attributes["city"].astext == office)
    return conditions


def _build_order(sort: str) -> tuple[Any, ...]:
    if sort == "department":
        return (User.department.asc().nullslast(), User.full_name.asc())
    if sort == "staff_custom":
        # Order by department's custom sort_order (NULLS LAST → end alphabetically),
        # then department name, then user's per-department sort_order
        # (NULLS LAST → end alphabetically), then full_name.
        return (
            StaffDepartmentOrder.sort_order.asc().nullslast(),
            User.department.asc().nullslast(),
            User.staff_sort_order.asc().nullslast(),
            User.full_name.asc(),
        )
    return (User.full_name.asc(),)


def _select_users(sort: str) -> Select[tuple[User]]:
    stmt = select(User)
    if sort == "staff_custom":
        stmt = stmt.outerjoin(
            StaffDepartmentOrder,
            StaffDepartmentOrder.department == User.department,
        )
    return stmt


async def count_users(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    office: str | None = None,
    include_hidden: bool = True,
) -> int:
    conditions = _build_list_conditions(q, department, office, include_hidden=include_hidden)
    res = await db.execute(select(func.count(User.id)).where(*conditions))
    return int(res.scalar_one())


async def list_users_page(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    page: int,
    page_size: int,
    office: str | None = None,
    sort: str = "full_name",
    include_hidden: bool = True,
) -> Sequence[User]:
    conditions = _build_list_conditions(q, department, office, include_hidden=include_hidden)
    stmt = (
        _select_users(sort)
        .where(*conditions)
        .order_by(*_build_order(sort))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def list_birthdays(
    db: AsyncSession,
    *,
    week_start: date,
    week_end: date,
) -> Sequence[User]:
    """Именинники текущей недели (включительно ``[week_start, week_end]``).

    Фильтр по ``(month, day)`` дня рождения: перечисляем пары (месяц, день) для
    каждого дня недели и ищем совпадение. Это корректно для любой недели — в том
    числе переходящей через Новый год (29.12–04.01): мы сравниваем конкретные
    дни, а не «день года» (DOY ломается на границе года). 29 февраля в
    невисокосном году просто не входит ни в одну неделю — именинник не теряется,
    а попадает в неделю 1 марта → … нет, 29.02 обрабатывается отдельно см. ниже.

    Условия: не удалён, ``birth_date`` задан, не скрыт (``staff_hidden``).
    Сортировка: хронологически в пределах недели (месяц, день), затем ФИО.
    """
    # Множество (month, day) для всех дней недели включительно.
    md_pairs: list[tuple[int, int]] = []
    cur = week_start
    while cur <= week_end:
        md_pairs.append((cur.month, cur.day))
        cur += timedelta(days=1)

    birth_month = func.extract("month", User.birth_date)
    birth_day = func.extract("day", User.birth_date)

    stmt = (
        select(User)
        .where(
            User.deleted_at.is_(None),
            User.birth_date.isnot(None),
            User.staff_hidden.is_(False),
            tuple_(birth_month, birth_day).in_(md_pairs),
        )
        .order_by(birth_month.asc(), birth_day.asc(), User.full_name.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def list_departments(db: AsyncSession, *, ordered: bool = False) -> list[str]:
    res = await db.execute(
        select(User.department)
        .where(
            User.deleted_at.is_(None),
            User.department.isnot(None),
            func.length(func.trim(User.department)) > 0,
        )
        .distinct()
        .order_by(User.department.asc())
    )
    items = [row for row in res.scalars().all() if row and row.strip()]
    if not ordered:
        return items

    order_res = await db.execute(
        select(StaffDepartmentOrder.department, StaffDepartmentOrder.sort_order).order_by(
            StaffDepartmentOrder.sort_order.asc()
        )
    )
    order_map = {dept: idx for dept, idx in order_res.all()}

    def sort_key(d: str) -> tuple[int, int, str]:
        if d in order_map:
            return (0, order_map[d], d)
        return (1, 0, d)

    items.sort(key=sort_key)
    return items


async def list_offices(db: AsyncSession) -> list[str]:
    office_expr = User.attributes["city"].astext
    res = await db.execute(
        select(office_expr)
        .where(
            User.deleted_at.is_(None),
            office_expr.isnot(None),
            func.length(func.trim(office_expr)) > 0,
        )
        .distinct()
        .order_by(office_expr.asc())
    )
    return [row for row in res.scalars().all() if row and row.strip()]


async def stream_users(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    office: str | None,
    sort: str,
    include_hidden: bool = True,
) -> AsyncIterator[User]:
    conditions = _build_list_conditions(q, department, office, include_hidden=include_hidden)
    stmt = (
        _select_users(sort)
        .where(*conditions)
        .order_by(*_build_order(sort))
        .execution_options(yield_per=500)
    )
    res = await db.stream(stmt)
    async for partition in res.scalars().partitions(500):
        for user in partition:
            yield user


async def fetch_active_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    return res.scalar_one_or_none()


async def fetch_user_any(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def find_active_by_email(db: AsyncSession, email: str) -> User | None:
    res = await db.execute(
        select(User).where(
            func.lower(User.email) == email.lower(),
            User.deleted_at.is_(None),
        )
    )
    return res.scalar_one_or_none()


async def find_active_by_emails(db: AsyncSession, emails_lower: set[str]) -> dict[str, User]:
    """Bulk email lookup → ``{lower(email): User}``.

    Использует partial-unique индекс ``idx_users_email_ci_active``. Пустой вход
    возвращает пустой словарь (не выполняет запрос).
    """
    if not emails_lower:
        return {}
    res = await db.execute(
        select(User).where(
            func.lower(User.email).in_(emails_lower),
            User.deleted_at.is_(None),
        )
    )
    return {u.email.lower(): u for u in res.scalars()}


def _normalize_name_token(token: str) -> str:
    """Нормализация слова ФИО для CI-матча: нижний регистр + ё→е.

    «Артём» и «Артем» должны совпадать независимо от того, какая форма
    использована в запросе и в БД.
    """
    return token.strip().lower().replace("ё", "е")


def _name_column_normalized() -> Any:
    """``full_name``, приведённый к нижнему регистру с заменой ё→е.

    Применяется к обоим операндам сравнения, чтобы «Артем» (запрос) находил
    «Артём» (в БД) и наоборот.
    """
    return func.replace(func.lower(User.full_name), "ё", "е")


def _split_name_words(token: str) -> list[str]:
    """Разбить ФИО на значимые слова (≥3 символов), отбросив короткие инициалы.

    «Артем Богославский» → ['артем', 'богославский'].
    «Б. П.» → [] (короткие не идут на строгий матч; используется fallback).
    Порог ≥3 защищает от ложных совпадений при префиксном матче (дву-буквенное
    «ан» не должно цеплять половину имён).
    """
    out: list[str] = []
    for word in token.split():
        norm = _normalize_name_token(word).strip(".-")
        if len(norm) >= 3:
            out.append(norm)
    return out


def _word_in_full_name_conditions(word: str) -> Any:
    """Условие: ``word`` есть в ``full_name`` как ПРЕФИС слова (любой раскладки).

    Префикс-внутри-слова: «третьяков» находит «третьякова» (падежное окончание),
    «богославский» — «богославскому». Граница слова — начало строки или пробел,
    поэтому «артем» НЕ цепляет «полиартемов» (нет пробела перед). Учитываются
    варианты раскладки клавиатуры (ЙЦУКЕН↔QWERTY) и ё↔е на обоих операндах.
    """
    col = _name_column_normalized()
    clauses = []
    for variant in layout_variants(word):
        norm = _normalize_name_token(variant)
        # Первое слово начинается с norm ИЛИ слово после пробела начинается с norm.
        # «%» в конце допускает продолжение (окончания), но граница слева — пробел/начало.
        clauses.append(col.ilike(f"{norm}%"))
        clauses.append(col.ilike(f"% {norm}%"))
    return or_(*clauses)


def _full_name_word_match_conditions(token: str) -> list[Any]:
    """Условия матчатинга ФИО по словам в любом порядке.

    Все значимые слова запроса должны присутствовать в ``full_name`` (как
    префиксы слов). Порядок слов не важен: «Артем Богославский» найдёт
    «Богославский Артем Петрович».
    """
    words = _split_name_words(token)
    if not words:
        # Запрос из одних инициалов/мусора — fallback на подстрочный матч
        # всей строки, иначе ничего не найдём.
        return _full_name_substring_conditions(token)
    # Каждое слово — обязательно (AND).
    return [and_(*[_word_in_full_name_conditions(w) for w in words])]


def _full_name_exact_conditions(token: str) -> list[Any]:
    """CI точное совпадение ``full_name`` (с вариантами раскладки клавиатуры)."""
    clauses = [func.lower(User.full_name) == v.lower() for v in layout_variants(token)]
    return [or_(*clauses)]


def _full_name_substring_conditions(token: str) -> list[Any]:
    """CI подстрочный матч ``full_name`` (с вариантами раскладки клавиатуры)."""
    clauses = [User.full_name.ilike(f"%{v}%") for v in layout_variants(token)]
    return [or_(*clauses)]


async def find_by_full_name_exact(db: AsyncSession, token: str) -> list[User]:
    """Точные (CI, с раскладкой) совпадения по ``full_name`` среди активных."""
    res = await db.execute(
        select(User).where(
            User.deleted_at.is_(None),
            *_full_name_exact_conditions(token),
        )
    )
    return list(res.scalars().unique())


async def find_by_full_name_substring(
    db: AsyncSession, token: str, *, limit: int = 5
) -> list[User]:
    """Подстрочные (CI, с раскладкой) совпадения по ``full_name`` среди активных.

    Ограничен ``limit`` — используется для подбора кандидатов при отсутствии
    точного совпадения.
    """
    res = await db.execute(
        select(User)
        .where(User.deleted_at.is_(None), *_full_name_substring_conditions(token))
        .limit(limit)
    )
    return list(res.scalars().unique())


async def find_by_full_name_words(db: AsyncSession, token: str, *, limit: int = 10) -> list[User]:
    """Матчатинг ФИО по словам в любом порядке (с раскладкой и ё↔е).

    Все значимые слова запроса должны быть префиксами слов в ``full_name``.
    «Артем Богославский» найдёт «Богославский Артем Петрович» и
    «Богославский Артем» (другой порядок, с отчеством/без). Ранжирование по
    близости длины — короткие ФИО (ближе к запросу) идут раньше.
    """
    res = await db.execute(
        select(User)
        .where(User.deleted_at.is_(None), *_full_name_word_match_conditions(token))
        .order_by(func.char_length(User.full_name).asc())
        .limit(limit)
    )
    return list(res.scalars().unique())


async def update_user_fields(db: AsyncSession, user_id: uuid.UUID, values: dict) -> None:
    await db.execute(update(User).where(User.id == user_id).values(**values))


async def insert_local_user(
    db: AsyncSession,
    *,
    email: str,
    full_name: str,
    password_hash: str,
    role: str,
) -> User:
    now = datetime.now(UTC)
    stmt = (
        pg_insert(User)
        .values(
            email=email,
            full_name=full_name,
            auth_source="local",
            password_hash=password_hash,
            role=role,
            updated_at=now,
        )
        .returning(User)
    )
    res = await db.execute(stmt)
    return res.scalars().one()


async def count_news_versions_for_editor(db: AsyncSession, user_id: uuid.UUID) -> int:
    val = await db.scalar(
        text("SELECT COUNT(*) FROM news_versions WHERE editor_id = :uid"),
        {"uid": user_id},
    )
    return int(val or 0)


async def soft_delete_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    await db.execute(update(User).where(User.id == user_id).values(deleted_at=now, updated_at=now))


# ─────────────────────── staff directory order/visibility ──────────────────


async def fetch_department_order(db: AsyncSession) -> list[str]:
    res = await db.execute(
        select(StaffDepartmentOrder.department).order_by(StaffDepartmentOrder.sort_order.asc())
    )
    return [row for row in res.scalars().all()]


async def fetch_hidden_user_ids(db: AsyncSession) -> list[uuid.UUID]:
    res = await db.execute(
        select(User.id).where(
            User.deleted_at.is_(None),
            User.staff_hidden.is_(True),
        )
    )
    return [row for row in res.scalars().all()]


async def replace_department_order(db: AsyncSession, departments: list[str]) -> None:
    await db.execute(delete(StaffDepartmentOrder))
    if departments:
        await db.execute(
            pg_insert(StaffDepartmentOrder).values(
                [{"department": dept, "sort_order": idx} for idx, dept in enumerate(departments)]
            )
        )


async def apply_user_sort_orders(db: AsyncSession, items: list[tuple[uuid.UUID, int]]) -> None:
    """Полная замена per-user `staff_sort_order`.

    Семантика — `set`, а не `merge`:
    - пользователям, отсутствующим в ``items``, выставляется ``staff_sort_order=NULL``
      (через единичный UPDATE с исключением `items` по id, чтобы не переписывать
      строки, у которых значение и так станет верным сразу после батч-апдейта);
    - пользователям из ``items`` значение применяется одним батч-UPDATE через
      `CASE WHEN ... END`. Дубликаты ``id`` должны быть отсеяны на роуте.

    Вызывать строго внутри транзакции — функция сама не коммитит.
    """
    mapping: dict[uuid.UUID, int] = {}
    for user_id, sort_order in items:
        mapping[user_id] = sort_order

    reset_stmt = update(User).where(
        User.deleted_at.is_(None),
        User.staff_sort_order.isnot(None),
    )
    if mapping:
        reset_stmt = reset_stmt.where(User.id.notin_(list(mapping.keys())))
    await db.execute(reset_stmt.values(staff_sort_order=None))

    if not mapping:
        return
    await db.execute(
        update(User)
        .where(User.id.in_(list(mapping.keys())), User.deleted_at.is_(None))
        .values(staff_sort_order=case(mapping, value=User.id, else_=None))
    )


async def apply_hidden_user_ids(db: AsyncSession, hidden_ids: list[uuid.UUID]) -> None:
    await db.execute(
        update(User)
        .where(User.deleted_at.is_(None), User.staff_hidden.is_(True))
        .values(staff_hidden=False)
    )
    if hidden_ids:
        await db.execute(
            update(User)
            .where(User.id.in_(hidden_ids), User.deleted_at.is_(None))
            .values(staff_hidden=True)
        )
