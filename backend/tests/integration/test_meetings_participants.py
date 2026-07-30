"""Integration-тесты bulk-resolve участников встречи.

Эндпоинт ``POST /api/v1/meetings/participants/resolve`` резолвит список
ФИО/email в участников (``InvitedUser``) по таблице ``users`` БД.

Покрытие:
- точный резолв по email и по ФИО;
- неразрешённый email → внешний участник (``source=external``);
- неоднозначное ФИО → ``ambiguous`` с кандидатами;
- неразрешённое ФИО → ``unresolved``;
- раскладка клавиатуры (``Bdfyjd`` ↔ ``Иванов``);
- токенизация по запятым/переносам/табам + дедуп;
- ограничения (пустой список → 422, >50 записей → 422);
- ``user_id`` = ``keycloak_id`` (как у single-search), fallback на БД id.

Требует INTEGRATION_DB=true. Сессия изолирована SAVEPOINT/ROLLBACK.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.api.meetings.participants import resolve_participants
from app.models.user import User
from app.schemas.meetings import ResolveParticipantsRequest

pytestmark = pytest.mark.asyncio


async def _create(session, **overrides) -> User:
    defaults = dict(
        # example.com — RFC 2606 reserved, проходит EmailStr-валидацию
        # (важно: резолв маппит найденного сотрудника в InvitedUser(email=EmailStr)).
        email=f"staff-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test User",
        role="reader",
        auth_source="local",
        presence_status="office",
        notify_email=True,
        notify_inapp=True,
        lang="ru",
        preferences={},
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    await session.flush()
    return user


# ── резолв по email ─────────────────────────────────────────────────────────


async def test_resolve_by_emails_exact(real_db_session, real_user):
    """Три пользователя по email → три resolved."""
    marker = uuid.uuid4().hex[:6]
    u1 = await _create(real_db_session, email=f"a-{marker}@example.com", full_name=f"Анна {marker}")
    u2 = await _create(
        real_db_session, email=f"b-{marker}@example.com", full_name=f"Борис {marker}"
    )
    u3 = await _create(real_db_session, email=f"c-{marker}@example.com", full_name=f"Вера {marker}")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[u1.email, u2.email, u3.email]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.unresolved == []
    assert resp.ambiguous == []
    assert {u.email for u in resp.resolved} == {u1.email, u2.email, u3.email}
    assert all(u.source == "keycloak" for u in resp.resolved)


async def test_resolve_unresolved_email_becomes_external(real_db_session, real_user):
    """Неизвестный email → внешний участник (``source=external``, ``user_id=ext:…``)."""
    marker = uuid.uuid4().hex[:6]
    email = f"contractor-{marker}@partner.com"

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[email]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.unresolved == []
    assert resp.ambiguous == []
    assert len(resp.resolved) == 1
    ext = resp.resolved[0]
    assert ext.source == "external"
    assert ext.email == email
    assert ext.user_id == f"ext:{email.lower()}"


async def test_resolve_email_case_insensitive(real_db_session, real_user):
    """Email ищется case-insensitive (``A@X.ru`` находит ``a@x.ru``)."""
    marker = uuid.uuid4().hex[:6]
    u = await _create(
        real_db_session, email=f"name-{marker}@example.com", full_name=f"Имя {marker}"
    )
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[u.email.upper()]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].email == u.email


# ── резолв по ФИО ───────────────────────────────────────────────────────────


async def test_resolve_by_full_name_exact(real_db_session, real_user):
    """Точное ФИО → resolved."""
    marker = uuid.uuid4().hex[:6]
    name = f"Сидоров Сидор {marker}"
    u = await _create(real_db_session, full_name=name)
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[name]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.unresolved == []
    assert resp.ambiguous == []
    assert len(resp.resolved) == 1
    assert resp.resolved[0].full_name == name
    assert resp.resolved[0].email == u.email


# ── матчатинг ФИО по словам (любой порядок, отчества, ё↔е, падежи) ────────────


async def test_resolve_name_words_different_order(real_db_session, real_user):
    """Порядок слов не важен: «Артем Богославский» находит «Богославский Артем»."""
    marker = uuid.uuid4().hex[:6]
    # В БД — фамилия вперёд; запрос — имя вперёд (как в письме со встречи).
    surname = f"Богославский{marker}"
    name = f"{surname} Артем Петрович"
    u = await _create(real_db_session, full_name=name)
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Артем {surname}"]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.unresolved == []
    assert len(resp.resolved) == 1
    assert resp.resolved[0].email == u.email


async def test_resolve_name_words_with_patronymic(real_db_session, real_user):
    """Запрос без отчества находит ФИО с отчеством (слова-подмножество)."""
    marker = uuid.uuid4().hex[:6]
    surname = f"Ратникова{marker}"
    u = await _create(real_db_session, full_name=f"{surname} Алла Ивановна")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Алла {surname}"]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].email == u.email


async def test_resolve_name_words_surname_first_query(real_db_session, real_user):
    """Обратный случай: запрос «Фамилия Имя» при ФИО «Имя Фамилия Отчество»."""
    marker = uuid.uuid4().hex[:6]
    surname = f"Жилин{marker}"
    u = await _create(real_db_session, full_name=f"Федор {surname} Алексеевич")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"{surname} Федор"]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].email == u.email


async def test_resolve_name_words_yo_vs_ye(real_db_session, real_user):
    """«Артём» (запрос с ё) находит «Артем» (в БД с е), и наоборот."""
    marker = uuid.uuid4().hex[:6]
    surname = f"Литвачук{marker}"
    # В БД — «е», запрос — «ё».
    u = await _create(real_db_session, full_name=f"Артем {surname}")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Артём {surname}"]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].email == u.email


async def test_resolve_name_words_case_insensitive_and_case_endings(real_db_session, real_user):
    """Регистр и падежные окончания не мешают: префиксный матч слов.

    Запрос «виктория третьяков» находит «ВИКТОРИЯ Третьякова»: «третьяков» —
    префикс слова «третьякова» (им. → род. падеж). Маркер — отдельным «отчеством»,
    чтобы фамилия в запросе/БД была реальной (без склейки, ломающей префикс).
    """
    marker = uuid.uuid4().hex[:6]  # изоляция тест-данных через отдельное «отчество»
    u = await _create(real_db_session, full_name=f"ВИКТОРИЯ Третьякова {marker}")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"виктория третьяков {marker}"]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].email == u.email


async def test_resolve_name_words_partial_word_not_matched(real_db_session, real_user):
    """Короткое слово-фрагмент в середине чужого слова не матчится.

    «артем» не должен цеплять «полиартем» (word-boundary-guard).
    """
    marker = uuid.uuid4().hex[:6]
    # Имя-ловушка: содержит «артем» как подстроку, но не отдельным словом.
    await _create(real_db_session, full_name=f"Полиартемов {marker}")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Артем {marker}"]),
        db=real_db_session,
        user=real_user,
    )

    # Нет сотрудника с отдельным словом «Артем» → unresolved.
    assert resp.resolved == []
    assert len(resp.unresolved) == 1


async def test_resolve_name_words_two_candidates_ambiguous(real_db_session, real_user):
    """Два сотрудника с совпадающими словами → ambiguous (выбор пользователем)."""
    marker = uuid.uuid4().hex[:6]
    surname = f"Андреев{marker}"
    # Два Андрея Андреева (разные отчества).
    await _create(
        real_db_session,
        full_name=f"Андрей {surname} Петрович",
        email=f"a1-{marker}@example.com",
    )
    await _create(
        real_db_session,
        full_name=f"Андрей {surname} Семёнович",
        email=f"a2-{marker}@example.com",
    )
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Андрей {surname}"]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.resolved == []
    assert len(resp.ambiguous) == 1
    assert {c.email for c in resp.ambiguous[0].candidates} == {
        f"a1-{marker}@example.com",
        f"a2-{marker}@example.com",
    }


async def test_resolve_name_ranking_prefers_shortest(real_db_session, real_user):
    """При >1 совпадении короткое ФИО (ближе к запросу) идёт первым кандидатом.

    Два сотрудника с совпадающими словами, но разной длины (отчества разной
    длины) → ambiguous; ни один не точный. Ранжирование по длине ставит
    короткое ФИО первым кандидатом.
    """
    marker = uuid.uuid4().hex[:6]
    surname = f"Базилев{marker}"
    u_short = await _create(
        real_db_session,
        full_name=f"Сергей {surname} Петр",  # короче
        email=f"short-{marker}@example.com",
    )
    await _create(
        real_db_session,
        full_name=f"Сергей {surname} Петрович Алексеевич",  # длиннее
        email=f"long-{marker}@example.com",
    )
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Сергей {surname}"]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.ambiguous) == 1
    # Короткое ФИО (ближе к запросу по длине) — первый кандидат.
    assert resp.ambiguous[0].candidates[0].email == u_short.email


async def test_resolve_ambiguous_full_name(real_db_session, real_user):
    """Два одинаковых ФИО → ``ambiguous`` с двумя кандидатами."""
    marker = uuid.uuid4().hex[:6]
    name = f"Иван Иванов {marker}"
    u1 = await _create(
        real_db_session,
        full_name=name,
        email=f"ivan1-{marker}@example.com",
        department="IT",
        position="Dev",
    )
    u2 = await _create(
        real_db_session,
        full_name=name,
        email=f"ivan2-{marker}@example.com",
        department="HR",
        position="Manager",
    )
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[name]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.resolved == []
    assert resp.unresolved == []
    assert len(resp.ambiguous) == 1
    item = resp.ambiguous[0]
    assert item.query == name
    assert {c.email for c in item.candidates} == {u1.email, u2.email}
    # кандидаты несут department/position для выбора пользователем
    depts = {c.department for c in item.candidates}
    assert depts == {"IT", "HR"}


async def test_resolve_unresolved_name(real_db_session, real_user):
    """Несуществующее ФИО → ``unresolved``."""
    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[f"Несуществующий Человек {uuid.uuid4().hex[:8]}"]),
        db=real_db_session,
        user=real_user,
    )

    assert resp.resolved == []
    assert resp.ambiguous == []
    assert len(resp.unresolved) == 1


async def test_resolve_layout_variants(real_db_session, real_user):
    """EN-раскладка находит ФИО, набранное в RU (``Bdfyjd Bdfy`` → ``Иванов Иван``).

    Пользователь вводит ФИО кириллицей, забыв переключить раскладку, — получаются
    латинские буквы. ``layout_variants`` восстанавливает исходное ФИО для матча.

    В запросе только ФИО (без маркера): маркер из hex-цифр исказил бы обратный
    перевод раскладки. Изоляция данных — SAVEPOINT-rollback между тестами.
    """
    name = "Иванов Иван"
    u = await _create(real_db_session, full_name=name)
    await real_db_session.flush()

    # "Иванов Иван", набранное в EN-раскладке (QWERTY) без переключения языка.
    from app.utils.keyboard_layout import ru_to_en

    name_en = ru_to_en(name)
    assert name_en != name  # sanity: перевод действительно другой

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[name_en]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].full_name == name
    assert resp.resolved[0].email == u.email


# ── токенизация и дедуп ──────────────────────────────────────────────────────


async def test_resolve_split_separators(real_db_session, real_user):
    """Один элемент с разными разделителями → несколько токенов."""
    marker = uuid.uuid4().hex[:6]
    u1 = await _create(real_db_session, email=f"a-{marker}@example.com", full_name=f"Ааа {marker}")
    u2 = await _create(real_db_session, email=f"b-{marker}@example.com", full_name=f"Ббб {marker}")
    name3 = f"Ввв {marker}"
    await _create(real_db_session, full_name=name3)
    await real_db_session.flush()

    blob = f"{u1.email}, {u2.email};\n{name3}\t"

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[blob]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 3
    # все три сотрудника найдены (третий — по ФИО, у него дефолтный email)
    resolved_names = {u.full_name for u in resp.resolved}
    resolved_emails = {u.email for u in resp.resolved}
    assert u1.email in resolved_emails
    assert u2.email in resolved_emails
    assert name3 in resolved_names


async def test_resolve_dedup(real_db_session, real_user):
    """Повторяющиеся email и ФИО не дают дублей."""
    marker = uuid.uuid4().hex[:6]
    u = await _create(real_db_session, email=f"d-{marker}@example.com", full_name=f"Дедуп {marker}")
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(
            queries=[u.email, u.email, u.full_name, u.full_name.upper()]
        ),
        db=real_db_session,
        user=real_user,
    )

    emails = [r.email for r in resp.resolved if r.source == "keycloak"]
    assert len(emails) == 1
    assert emails[0] == u.email


async def test_resolve_mixed_email_and_name(real_db_session, real_user):
    """Смесь email и ФИО в одном запросе резолвится корректно."""
    marker = uuid.uuid4().hex[:6]
    u_email = await _create(
        real_db_session, email=f"mix-{marker}@example.com", full_name=f"Микс {marker}"
    )
    name = f"Смесь {marker}"
    u_name = await _create(real_db_session, full_name=name)
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[u_email.email, name]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 2
    assert {u.email for u in resp.resolved} == {u_email.email, u_name.email}


# ── ограничения ──────────────────────────────────────────────────────────────


async def test_resolve_empty(real_db_session, real_user):
    """Пустой список (после токенизации) → 422."""
    with pytest.raises(Exception) as exc_info:
        await resolve_participants(
            data=ResolveParticipantsRequest(queries=["   , \n\t"]),
            db=real_db_session,
            user=real_user,
        )
    assert exc_info.value.status_code == 422
    assert "max" not in str(exc_info.value.detail).lower()


async def test_resolve_too_many_entries(real_db_session, real_user):
    """>50 записей в одном элементе после токенизации → 422 (``_BULK_MAX_TOKENS``)."""
    # 51 запись, упакованная в один элемент (Pydantic max_length=50 на список
    # элементов её пропустит — элемент один; сработает проверка числа токенов).
    blob = ",".join(f"user{i}@x-{uuid.uuid4().hex[:6]}.com" for i in range(51))
    with pytest.raises(Exception) as exc_info:
        await resolve_participants(
            data=ResolveParticipantsRequest(queries=[blob]),
            db=real_db_session,
            user=real_user,
        )
    assert exc_info.value.status_code == 422


# ── user_id источник ─────────────────────────────────────────────────────────


async def test_resolve_user_id_uses_keycloak_id(real_db_session, real_user):
    """``user_id`` = ``keycloak_id`` (как у single-search), fallback на БД id."""
    marker = uuid.uuid4().hex[:6]
    kc_id = str(uuid.uuid4())  # VARCHAR(36) — ровно UUID, как из Keycloak
    u = await _create(
        real_db_session,
        email=f"kc-{marker}@example.com",
        full_name=f"Кейклоак {marker}",
        keycloak_id=kc_id,
    )
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[u.email]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].user_id == kc_id


async def test_resolve_user_without_keycloak_id_falls_back_to_db_id(real_db_session, real_user):
    """Пользователь без ``keycloak_id`` (local-auth) → ``user_id`` = БД id как строка."""
    marker = uuid.uuid4().hex[:6]
    u = await _create(
        real_db_session,
        email=f"local-{marker}@example.com",
        full_name=f"Локальный {marker}",
        keycloak_id=None,
    )
    await real_db_session.flush()

    resp = await resolve_participants(
        data=ResolveParticipantsRequest(queries=[u.email]),
        db=real_db_session,
        user=real_user,
    )

    assert len(resp.resolved) == 1
    assert resp.resolved[0].user_id == str(u.id)
