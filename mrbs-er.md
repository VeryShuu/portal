# Модуль «Переговорные» — план устранения замечаний

> Документ для ИИ-агента (или разработчика), который будет закрывать долг по модулю `meetings` перед продакшеном.
>
> **Формат каждой задачи:**
> - **ID** — короткий идентификатор для трекинга (используй в коммитах: `fix(meetings): BLK-01 …`).
> - **Где ловится** — файл/строки/способ воспроизведения (как обнаружить регрессию).
> - **Что не так** — суть проблемы.
> - **Что сделать** — конкретные шаги.
> - **Сложность** — `S` (≤1 ч), `M` (1–4 ч), `L` (0.5–2 дня), `XL` (>2 дней).
> - **Приоритет** — `P0 (BLOCKER)`, `P1 (MAJOR)`, `P2 (MINOR)`, `P3 (DOC)`.
> - **Тест** — какой автотест добавить, чтобы регрессия не вернулась.
>
> Порядок выполнения: сначала все `P0`, затем `P1` (как минимум те, что видны пользователю), затем `P3` (синхронизация документации), и в последнюю очередь `P2`.

---

## Общие правила для агента

1. Перед стартом задачи прочитай связанные файлы целиком, а не только указанные строки.
2. Соблюдай существующие конвенции проекта (стек: FastAPI + SQLAlchemy + Alembic + ARQ + Vue 3 + Naive UI + TanStack Query + Pinia + structlog).
3. **Не** трогай несвязанный код, не делай попутный рефакторинг.
4. После каждой задачи: `pytest backend/tests/meetings -q` и `npm run lint && npm run typecheck` (или эквиваленты, см. `./README.md` / `./docs/`).
5. Для всех `P0`/`P1` добавляй регрессионный тест.
6. Для `P3` (документация) — никакого кода, только правки `./docs/meetings.md`.

---

## P0 — BLOCKER (8 задач, ~2–3 дня)

### BLK-01. Снести задачу `cleanup_meetings_audit` (таблица удалена миграцией 050)

- **Где ловится:**
  - `./backend/app/worker/tasks/meetings/cleanup.py:11-32`
  - регистрация в `./backend/app/worker/main.py:16,123,198`
  - модель/импорт `MeetingsAuditLog` в `./backend/app/models/meetings.py` (если остался)
  - воспроизведение: запустить ARQ-воркер с шедулером → `ImportError`/`ProgrammingError: relation "meetings_audit_log" does not exist`.
- **Что не так:** миграция `./backend/migrations/versions/050_drop_meetings_audit_log.py` дропнула таблицу `meetings_audit_log`, но cron-задача `cleanup_meetings_audit` каждый час пытается импортировать модель и сделать `DELETE` на этой таблице.
- **Что сделать:**
  1. Удалить файл `./backend/app/worker/tasks/meetings/cleanup.py`.
  2. Убрать импорт и регистрацию задачи из `./backend/app/worker/main.py` (CRON-список и WorkerSettings.functions).
  3. Удалить модель `MeetingsAuditLog` (если ещё есть) в `./backend/app/models/meetings.py`.
  4. Удалить поле `audit_retention_days` из `MeetingsModuleSettings` (`./backend/app/schemas/...` + `./backend/app/api/modules.py`).
  5. Убрать UI-поле из `./frontend/src/pages/admin/tabs/ModulesTab.vue` и соответствующие i18n-ключи (`admin.modules.meetings.audit_retention_days*`).
- **Сложность:** M.
- **Тест:** unit-тест `tests/worker/test_worker_settings.py` (проверить, что cron-функция отсутствует); e2e-тест на админ-страницу модулей (поле не отображается).

### BLK-02. `push_meetings_audit(db, …)` падает с TypeError в worker email-задаче

- **Где ловится:**
  - `./backend/app/worker/tasks/meetings/email.py:106-111, 127-135`
  - сигнатура: `./backend/app/services/meetings/audit.py:34`
  - воспроизведение: создать встречу → ARQ-воркер при отправке iCal-письма падает с `TypeError`.
- **Что не так:** `push_meetings_audit` — keyword-only, сам открывает `AsyncSessionLocal()`. Вызывается с позиционным `db`.
- **Что сделать:** убрать `db` из всех вызовов в `email.py`, передавать только `action=`, `user=`, `request=`, `entity_id=`, `payload=`.
- **Сложность:** S.
- **Тест:** integration-тест `tests/worker/test_meeting_email.py`: запустить task в InProcess-режиме и проверить, что аудит-запись появилась без TypeError.

### BLK-03. Сервисы делают `db.rollback()` на внешней сессии роутера

- **Где ловится:**
  - `./backend/app/services/meetings/bookings_service.py:284, 386`
  - `./backend/app/services/meetings/series_service.py:90, 219`
  - воспроизведение: integration-тест, который в одной сессии добавляет аудит-запись, затем вызывает create_booking → конфликт; убедиться, что аудит сохранён, а основной commit действительно прошёл/откатился ожидаемо.
- **Что не так:** `await db.rollback()` внутри сервиса откатывает всю транзакцию роутера. Последующий `commit()` ничего не пишет; ранее добавленные аудит-записи теряются.
- **Что сделать:**
  1. Обернуть INSERT в `async with db.begin_nested(): …` (SAVEPOINT).
  2. На `IntegrityError` откатывать только nested.
  3. `_get_conflict_details` выполнять либо на той же сессии после rollback nested, либо в отдельной короткой сессии (`async with AsyncSessionLocal() as ro:`).
- **Сложность:** L.
- **Тест:** добавить integration-тест на одновременный INSERT (EXCLUDE GIST → 409) с проверкой, что аудит-запись от предыдущей операции в той же транзакции сохранилась.

### BLK-04. SEQUENCE инкрементируется даже при изменении только участников

- **Где ловится:**
  - `./backend/app/services/meetings/bookings_service.py:380`
  - `./backend/app/services/meetings/series_service.py:115-237`
  - спецификация: `./docs/meetings.md:48,207` (раздел 2 «Email-логика MRBS»)
  - воспроизведение: создать встречу, добавить участника, посмотреть в iCal-теле `SEQUENCE`. Сейчас всегда +1, должно остаться прежним.
- **Что не так:** нарушение RFC 5545. Outlook/Apple Calendar получают «обновление» с тем же UID, что вызывает ложные нотификации.
- **Что сделать:**
  1. Завести булевый флаг `non_participant_changed`, сравнивая `title`, `description`, `start_time`, `end_time`, `room_ids` между old и new.
  2. `update_count += 1` только если `non_participant_changed`.
  3. В `notifications._build_diff` для `unchanged`-участников посылать REQUEST с новым SEQUENCE только при `non_participant_changed=True`.
- **Сложность:** M.
- **Тест:** unit-тест `tests/services/test_bookings_update_sequence.py`: добавление участника → SEQUENCE не меняется; изменение time → SEQUENCE +1.

### BLK-05. В iCal нет VTIMEZONE-компонента при наличии `TZID=`

- **Где ловится:**
  - `./backend/app/services/meetings/ical_builder.py:39-51, 73-74`
  - воспроизведение: открыть сгенерированный iCal в Outlook — увидите «без времени» или сдвиг.
- **Что не так:** `DTSTART;TZID=Europe/Moscow:…` без секции `BEGIN:VTIMEZONE…END:VTIMEZONE` — Outlook/Apple Calendar отображают некорректно.
- **Что сделать:** добавить `VTIMEZONE` через `icalendar.Timezone.from_tzinfo(zoneinfo.ZoneInfo(tz))` (или эквивалент через `vobject`/`tzical`). Включать в `cal.add_component(...)` ДО событий.
- **Сложность:** M.
- **Тест:** unit-тест `tests/services/test_ical_builder.py`: парсим результат через `icalendar.Calendar.from_ical`, проверяем наличие `VTIMEZONE` с тем же `TZID`, который указан в `DTSTART`.

### BLK-06. Удаление встречи из серии не спрашивает «эта / вся серия»

- **Где ловится:**
  - `./frontend/src/pages/meetings/MeetingsPage.vue:241-257` (`confirmDeleteBooking`)
  - спецификация: `./docs/meetings.md:357,469-473`
  - воспроизведение: создать серию из 5 встреч → открыть карточку любой → нажать «Удалить». Сейчас удаляется только одна без вопроса.
- **Что не так:** `deleteBooking(id)` вызывается без `apply_to`; для серий это удаляет один инстанс молча, ломая ожидание Outlook-стиля.
- **Что сделать:**
  1. Если `selectedBooking.series_id != null` — показать диалог с двумя кнопками: «Только эту встречу» / «Всю серию» (использовать `useDialog().create`).
  2. Для «всей серии» вызвать `useDeleteSeriesMutation(series_id)`.
  3. Для одиночной — `useDeleteBookingMutation(id, apply_to: 'this')`.
- **Сложность:** M.
- **Тест:** Playwright e2e `e2e/meetings/series-delete.spec.ts`.

### BLK-07. Отсутствует i18n-ключ `meetings.form.endTimeAfterStart`

- **Где ловится:**
  - `./frontend/src/components/meetings/MeetingFormDialog.vue:77`
  - воспроизведение: открыть форму создания, поставить end ≤ start → в подсказке появляется сырой ключ вместо текста.
- **Что не так:** ключ не определён ни в `./frontend/src/i18n/ru.json`, ни в `./frontend/src/i18n/en.json`.
- **Что сделать:** добавить пары переводов:
  - ru: «Время окончания должно быть позже начала»
  - en: «End time must be after start time»
- **Сложность:** S.
- **Тест:** unit-тест на i18n («все используемые в meetings.* ключи определены в обеих локалях»).

### BLK-08. PUT/DELETE серии на фронте идёт в неправильный endpoint

- **Где ловится:**
  - `./frontend/src/components/meetings/MeetingFormDialog.vue:361-373, 412-425`
  - спецификация: `./docs/meetings.md:184-185` (`PUT /meetings/series/{id}`, `DELETE /meetings/series/{id}`)
  - воспроизведение: открыть встречу серии → изменить название → выбрать «Применить ко всей серии» → сохранить. Сейчас уходит `PUT /meetings/bookings/{id}` с телом `{apply_to: 'series'}`. Бэкенд этого режима не поддерживает.
- **Что не так:** не используются готовые `useUpdateSeriesMutation` / `useDeleteSeriesMutation` (см. `./frontend/src/queries/meetings.ts`).
- **Что сделать:** в `onSubmit` и `onDelete` MeetingFormDialog добавить ветку `if (applyTo.value === 'series' && booking.series_id)`:
  - **update:** вызвать `updateSeries(series_id, { title, description, invited_users, room_ids? })`. Передавать только разрешённые сервером поля.
  - **delete:** вызвать `deleteSeries(series_id)`.
- **Сложность:** M.
- **Тест:** Playwright e2e + unit-тест компонента (моки api).

---

## P1 — MAJOR (~20 задач, ~5–7 дней)

### Backend

#### MAJ-B01. Валидация `end_time > start_time` в `BookingUpdate` пропускает одиночные обновления

- **Где ловится:** `./backend/app/schemas/meetings.py:115-140`.
- **Что не так:** `end_after_start` срабатывает только если переданы ОБА поля. Одиночное `start_time` → 409 (через IntegrityError CheckConstraint) вместо 422.
- **Что сделать:** в сервисе `update_booking` (`./backend/app/services/meetings/bookings_service.py`) после load existing объединять effective `start`/`end` и валидировать вручную → `HTTPException(422)`.
- **Сложность:** S. **Тест:** unit-тест с одним только `start_time`.

#### MAJ-B02. N+1 в `create_booking_series` / `update_series`

- **Где ловится:** `./backend/app/services/meetings/series_service.py:101-105, 232-237` — `_load_booking` в цикле.
- **Что сделать:** одним `SELECT … WHERE id IN (…) ` + `selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room)`.
- **Сложность:** M. **Тест:** counter SQL-запросов в unit-тесте серии из 31 экземпляра.

#### MAJ-B03. При изменении `start_time` серии не пересчитывается RRULE

- **Где ловится:** `./backend/app/services/meetings/series_service.py:155-170`.
- **Что не так:** RRULE содержит старые `BYDAY`/`BYMONTHDAY`; DTSTART и RRULE расходятся.
- **Что сделать:** пересобрать `recurrence_rule` через `build_rrule_string(new_first.start_time, freq, until_date)` после расчёта новых дат.
- **Сложность:** M. **Тест:** unit-тест серии, в которой переехал день недели первой встречи.

#### MAJ-B04. `apply_to=series`, но `series_id is None` — тихо обрабатывается как одиночное

- **Где ловится:** `./backend/app/api/meetings/bookings.py:221`.
- **Что сделать:** вернуть `400 Bad Request` («Booking is not part of a series»).
- **Сложность:** S. **Тест:** API-тест.

#### MAJ-B05. Аудит коммитится раньше основной операции

- **Где ловится:** `./backend/app/services/meetings/audit.py:63-87`.
- **Что не так:** при сбое EXCLUDE GIST в commit основной транзакции аудит уже сохранён → «выполненное» действие, которого не было.
- **Что сделать:** перенести вызов `push_meetings_audit(...)` ПОСЛЕ `await db.commit()` в API-слое, либо использовать ту же транзакцию (SAVEPOINT).
- **Сложность:** M. **Тест:** integration-тест с провокацией IntegrityError в commit.

#### MAJ-B06. При отвязке инстанса от серии UID меняется без CANCEL для старого

- **Где ловится:** `./backend/app/services/meetings/notifications.py:43-46, 60` + `bookings_service.py` (логика `series_id = None` при `apply_to=this`).
- **Что не так:** UID `series-…@…` → `{id}@…` без CANCEL — в календарях остаются «зомби»-встречи.
- **Что сделать:** при отвязке отправить два письма: CANCEL со старым UID + REQUEST с новым.
- **Сложность:** L. **Тест:** unit-тест на `notifications.dispatch_for_unlink`.

#### MAJ-B07. `invited_users` без верхней границы (DoS)

- **Где ловится:** `./backend/app/schemas/meetings.py:88-95`.
- **Что сделать:** `Field(..., max_length=settings.meetings.max_invitees, default_factory=list)` (например 100).
- **Сложность:** S. **Тест:** API-тест на 422 при превышении.

#### MAJ-B08. `min_search_chars` из настроек игнорируется

- **Где ловится:** `./backend/app/api/meetings/participants.py:668` — `Query(min_length=3)` захардкожен.
- **Что сделать:** читать `settings.meetings.min_search_chars`; валидировать вручную, отдавать 422 с понятным сообщением.
- **Сложность:** S. **Тест:** API-тест с настройкой 4.

### Frontend

#### MAJ-F01. Polling 60 s как fallback к SSE не реализован

- **Где ловится:** `./frontend/src/queries/meetings.ts:33-40, 42-48`.
- **Спецификация:** `./docs/meetings.md:463,519`.
- **Что сделать:** добавить `refetchInterval: 60_000, refetchIntervalInBackground: false` в `useMeetingBookingsQuery` и `useMyMeetingBookingsQuery`.
- **Сложность:** S. **Тест:** unit-тест на опции query.

#### MAJ-F02. Виджет «Мои ближайшие» не реагирует на SSE

- **Где ловится:** `./frontend/src/components/widgets/MeetingsWidget.vue`.
- **Что сделать:** в `onMounted` подписаться `window.addEventListener('meetings:changed', handler)`; handler → `qc.invalidateQueries({ queryKey: queryKeys.meetings.myBookings(...) })`. Отписаться в `onBeforeUnmount`.
- **Сложность:** S. **Тест:** unit-тест компонента.

#### MAJ-F03. Хардкод локали `ru-RU` в форматировании времени

- **Где ловится:**
  - `./frontend/src/components/meetings/BookingCard.vue:32`
  - `./frontend/src/pages/meetings/MeetingsPage.vue:264`
  - `./frontend/src/components/widgets/MeetingsWidget.vue:79`
- **Что сделать:** заменить на `const loc = useI18n().locale.value === 'ru' ? 'ru-RU' : 'en-GB'` (паттерн уже есть в `MeetingsPage.vue:184`).
- **Сложность:** S. **Тест:** snapshot-тест компонента с переключением локали.

#### MAJ-F04. `NDatePicker` без `dateLocale`

- **Где ловится:** `./frontend/src/components/meetings/MeetingFormDialog.vue:47-87`, `./frontend/src/components/meetings/RecurrenceEditor.vue:20-26`.
- **Что сделать:** обернуть страницу в `<NConfigProvider :date-locale="dateRuRU">` либо локально проставить `:date-locale` пропсом, переключая по `useI18n().locale.value`.
- **Сложность:** S. **Тест:** ручная проверка + snapshot.

#### MAJ-F05. ParticipantPicker: 422 глотается, dropdown держится через `setTimeout`-хак

- **Где ловится:** `./frontend/src/components/meetings/ParticipantPicker.vue:109-122, 131-135`.
- **Спецификация (доку обновить заодно):** `./docs/meetings.md:1300-1308` — обещан `n-select multiple filterable remote`.
- **Что сделать:**
  1. Переписать на `<n-select multiple filterable remote :loading :options @search="onSearch" />`, либо
  2. как минимум — `trim()` перед проверкой длины + явный click-outside listener (без `setTimeout(150)`); отображать ошибки.
  3. Удалить мёртвый `wrapperRef` (строка 35).
- **Сложность:** L. **Тест:** Playwright e2e.

#### MAJ-F06. Past-time ошибка определяется по подстроке `'past'`

- **Где ловится:** `./frontend/src/components/meetings/MeetingFormDialog.vue:393-405`.
- **Что сделать:** на бэке отдавать структурный код (`{ "code": "START_TIME_IN_PAST" }`); на фронте — `if (err.data?.code === 'START_TIME_IN_PAST')`. Завести `mapApiError(err)`.
- **Сложность:** M. **Тест:** unit-тест mapApiError + e2e.

#### MAJ-F07. Сетка/карточки используют TZ браузера, а не TZ комнаты

- **Где ловится:** `./frontend/src/components/meetings/BookingCard.vue:36-46`, `./frontend/src/components/meetings/RoomGrid.vue:127-177, 165-177`.
- **Спецификация:** `./docs/meetings.md:368-373`.
- **Что сделать:**
  - рендерить позиции карточек, используя `Intl.DateTimeFormat({timeZone: room.timezone})` для определения часа/минут;
  - `showTz` сравнивать через offset на текущий момент, форматировать как `GMT±N`;
  - в шапке столбца добавить подсказку «время в TZ комнаты».
- **Сложность:** L. **Тест:** unit-тест на BookingCard с разными TZ комнаты vs браузера.

#### MAJ-F08. Удаление из `MeetingsPage` минует mutation hook

- **Где ловится:** `./frontend/src/pages/meetings/MeetingsPage.vue:149, 250-254`.
- **Что сделать:** заменить прямой `deleteBooking()` на `useDeleteBookingMutation()`; единая обработка 403/409, loading-state.
- **Сложность:** S. **Тест:** unit-тест с моком api.

#### MAJ-F09. Слоты сетки недоступны с клавиатуры (a11y)

- **Где ловится:** `./frontend/src/components/meetings/RoomGrid.vue:48-77`.
- **Что сделать:** обернуть слот в `<button type="button" tabindex="0" :aria-label="…" />` или добавить `role="button"` + `tabindex="0"` + `@keydown.enter/space`. Контейнеру — `role="grid"` + `aria-label`.
- **Сложность:** M. **Тест:** Playwright a11y assertions.

#### MAJ-F10. Админка комнат: без пагинации/фильтра/сортировки

- **Где ловится:** `./frontend/src/pages/admin/MeetingRoomsAdminPage.vue:16-22, 221-270`.
- **Что сделать:** включить `pagination` в `NDataTable`, добавить переключатель «только активные», сортировку по `name`/`timezone`.
- **Сложность:** M. **Тест:** Playwright e2e.

#### MAJ-F11. `useMeetingRoomsQuery` стартует при выключенном модуле

- **Где ловится:** `./frontend/src/pages/meetings/MeetingsPage.vue:196-200`, `./frontend/src/components/meetings/MeetingFormDialog.vue`.
- **Что сделать:** прокинуть `enabled: modulesEnabled` в оба вызова.
- **Сложность:** S. **Тест:** unit-тест.

#### MAJ-F12. `RecurrenceEditor` ломает даты на TZ-границах

- **Где ловится:** `./frontend/src/components/meetings/RecurrenceEditor.vue:60-89`.
- **Что сделать:** строить даты через `new Date(yyyy, mm-1, dd)`; в `isDateDisabled` нормализовать к 00:00 локального дня.
- **Сложность:** S. **Тест:** unit-тест с TZ Asia/Kamchatka.

---

## P2 — MINOR (опционально перед релизом)

### Backend

| ID | Файл / строки | Кратко | Сложность |
|---|---|---|---|
| MIN-B01 | `./backend/app/api/meetings/bookings.py:85-114` | Нет ограничения диапазона дат в `list_bookings_endpoint` — добавить max-range 31–90 дней | S |
| MIN-B02 | `./backend/app/services/meetings/bookings_service.py:55-61, 96-106` | `end_date`-фильтр не включает встречи, пересекающие конец диапазона — заменить на overlap-условие | S |
| MIN-B03 | `./backend/app/services/meetings/bookings_service.py:119-140` | `list_my_bookings` не учитывает приглашённого пользователя; уточнить семантику и расширить (с GIN-индексом по `invited_users`) | M |
| MIN-B04 | `./backend/app/services/meetings/bookings_service.py:257-260` | `organizer_name` не ограничен в Pydantic (БД режет 255) — добавить `max_length=255` | S |
| MIN-B05 | `./backend/app/services/meetings/recurrence.py:71-75` | MONTHLY day>28 → 500 вместо 422; перенести валидацию в Pydantic | S |
| MIN-B06 | `./backend/app/services/meetings/recurrence.py:19-27` | `until_dt` строится в UTC, для МСК может обрезать последний день | S |
| MIN-B07 | `./backend/app/services/meetings/ical_builder.py:65-71` | У ATTENDEE нет `ROLE=REQ-PARTICIPANT`, `CUTYPE=INDIVIDUAL`; для room.email — `CUTYPE=RESOURCE` | S |
| MIN-B08 | `./backend/app/services/meetings/notifications.py:32-34` | `portal_base_url` парсится через `split("/")[0]` — заменить на `urlparse` | S |
| MIN-B09 | `./backend/app/api/meetings/bookings.py:118-192` | Дубль publish/audit-кода между create/update; вынести в helper | M |
| MIN-B10 | `./backend/app/services/meetings/rooms_service.py:50-53` | Race в `soft_delete_room` + `has_future_bookings`; использовать `SELECT … FOR UPDATE` или advisory lock | M |
| MIN-B11 | `./backend/app/models/meetings.py:48` | Нет CHECK-констрейнта на формат `email` (валидация только Pydantic) | S |

### Frontend

| ID | Файл / строки | Кратко | Сложность |
|---|---|---|---|
| MIN-F01 | `./frontend/src/components/meetings/BookingCard.vue:30-33`, `ParticipantPicker.vue:35` | Мёртвый код (`formatTime`, `wrapperRef`) — удалить | S |
| MIN-F02 | `./frontend/src/components/meetings/RoomGrid.vue:307,319`, `BookingCard.vue:55-78` | Хардкод HEX-цветов вместо CSS-переменных — ввести `--meetings-event-bg/-fg` | M |
| MIN-F03 | `./frontend/src/components/widgets/MeetingsWidget.vue:37-50` | Показывает только время без даты — добавить дату для не-сегодня | S |
| MIN-F04 | `./frontend/src/components/meetings/RoomGrid.vue:25-29` | Нет повторной сортировки комнат на фронте — отсортировать по `sort_order, name` | S |
| MIN-F05 | `./frontend/src/pages/meetings/MeetingsPage.vue:267-269` | `qc.invalidateQueries({ queryKey: queryKeys.meetings.all })` — лишний трафик; инвалидировать точечно `bookings`+`myBookings` | S |
| MIN-F06 | `./frontend/src/pages/admin/MeetingRoomsAdminPage.vue:151-159` | Хардкод 16 TZ — использовать `Intl.supportedValuesOf('timeZone')` | S |
| MIN-F07 | `./frontend/src/pages/admin/MeetingRoomsAdminPage.vue:146, 164` | Дефолт TZ зашит `Europe/Moscow` — брать из глобальной настройки портала | S |
| MIN-F08 | `./frontend/src/components/meetings/ParticipantPicker.vue:197-209` | Кнопка «×» без `:focus-visible` — добавить focus-стиль | S |
| MIN-F09 | `./frontend/src/components/meetings/RoomGrid.vue:322-326` | Мобильный режим без snap-scroll/индикатора «1 из N» (см. T-029) | M |
| MIN-F10 | `./frontend/src/pages/meetings/MeetingsPage.vue:241-257` | Текст подтверждения удаления без названия встречи — добавить | S |
| MIN-F11 | `./frontend/src/components/meetings/MeetingFormDialog.vue:6` | На ≤375px модалка может уходить за края — добавить scroll-внутрь | S |
| MIN-F12 | `./frontend/src/components/meetings/MeetingFormDialog.vue:47-87` | `tsToIso` не обнуляет секунды/мс — добавить нормализацию | S |

---

## P3 — DOC (синхронизация `./docs/meetings.md`)

Файл к правке: `./docs/meetings.md` (1485 строк). Правки ТОЛЬКО документации, без кода.

| ID | Где | Что исправить |
|---|---|---|
| DOC-01 | `./docs/meetings.md:328` vs `:526` vs `:1470` | Email на ящик комнаты: убрать строку «❌ Не делаем» из раздела 9.1; статус — реализовано |
| DOC-02 | `./docs/meetings.md:539` и раздел «4.6. Аудит» | Удалить упоминание отдельной таблицы `meetings_audit_log` (после миграции 050 — shared `audit_log`); добавить упоминание миграции `050_drop_meetings_audit_log.py` |
| DOC-03 | `./docs/meetings.md:218-219` vs `:1333-1335` | Противоречие mobile-режима: либо описать единый встроенный, либо отдельный `RoomGridMobile.vue`. Согласовать с фактом |
| DOC-04 | `./docs/meetings.md` раздел 4.5 | Убрать ссылки на несуществующие `MeetingsMobileListPage.vue`, `stores/meetings.ts`; актуализировать имена компонентов |
| DOC-05 | `./docs/meetings.md:373` vs `:1476` | iCal-TZ: оставить одну версию (TZ портала или TZ комнаты — по факту реализации) |
| DOC-06 | `./docs/meetings.md:356, 491` | «макс 1 месяц» → заменить на «31 день» (`max_recurrence_horizon_days: 31`) |
| DOC-07 | `./docs/meetings.md:463, 519` | Polling 60 s — либо реализовать (MAJ-F01), либо пометить «не реализован, опираемся только на SSE» |
| DOC-08 | `./docs/meetings.md:357, 469-473` | Описать фактический UX «эта/вся серия» (`n-radio-group` внутри формы) либо привести реализацию к Outlook-style popup |
| DOC-09 | `./docs/meetings.md:1244-1251` | Composable `useMeetingsRealtime` — описать фактическое поведение: инвалидируется префикс `meetings.all` (нет per-date точности) |
| DOC-10 | `./docs/meetings.md:1300-1308` (T-026) | Привести к фактической реализации (кастомный `n-input` + dropdown) ИЛИ запланировать рефакторинг (MAJ-F05) |
| DOC-11 | `./docs/meetings.md:1197-1204` (T-019) | Проверить и явно описать, что `meetings_enabled_guard` подключён ко ВСЕМ роутерам (rooms/bookings/series/participants) |
| DOC-12 | `./docs/meetings.md:238` | Меню «в группе Сервисы» vs фактическое расположение — описать как есть |
| DOC-13 | `./docs/meetings.md` раздел 10 | Зафиксировать удаление `audit_retention_days` после закрытия BLK-01 |
| DOC-14 | `./docs/meetings.md:200` | UID серий: документ говорит `{booking.id}@{COMPANY_DOMAIN}`, код — `series-{series_id}@…`. Описать оба случая + поведение при отвязке инстанса (BLK через MAJ-B06) |
| DOC-15 | `./docs/meetings.md` (раздел админки) | `min_search_chars` — описать как «зарезервировано, фактически = 3» (до закрытия MAJ-B08) |

---

## Пробелы в тестах (необходимо добавить)

Эти тесты должны быть написаны параллельно с фиксами; включить в CI:

1. **TST-01** — integration: одновременный INSERT двух пересекающихся броней → ровно один 409 (EXCLUDE GIST). *Покрывает: BLK-03.*
2. **TST-02** — worker test для `send_meeting_email` в InProcess-режиме без TypeError. *Покрывает: BLK-02.*
3. **TST-03** — отсутствие cron-функции `cleanup_meetings_audit` в `WorkerSettings`. *Покрывает: BLK-01.*
4. **TST-04** — отвязка инстанса серии: проверка пары CANCEL(old UID) + REQUEST(new UID). *Покрывает: MAJ-B06.*
5. **TST-05** — iCal-парсер находит `VTIMEZONE` с тем же `TZID`, что и в `DTSTART`. *Покрывает: BLK-05.*
6. **TST-06** — SEQUENCE не растёт при изменении только `invited_users`. *Покрывает: BLK-04.*
7. **TST-07** — E2E Playwright: создание/конфликт/серия (создание, редактирование «эта/вся», удаление «эта/вся»)/отмена/добавление приглашённого. *Покрывает: BLK-06, BLK-08.*
8. **TST-08** — unit на i18n: все ключи `meetings.*` присутствуют в `ru.json` и `en.json`. *Покрывает: BLK-07.*

---

## Ориентировочный план релиза

| Спринт | Задачи | Длительность |
|---|---|---|
| 1 (стабилизация) | Все P0 (BLK-01…BLK-08) + TST-01…TST-08 | 3–4 дня |
| 2 (UX/корректность) | P1 backend (MAJ-B01…MAJ-B08) | 3 дня |
| 3 (UX frontend) | P1 frontend (MAJ-F01…MAJ-F12) | 4 дня |
| 4 (документация) | Все P3 (DOC-01…DOC-15) | 0.5–1 день |
| 5 (полировка) | P2 (по остаточному принципу) | 2–3 дня |

**Итого до прод-готовности (P0+P1+P3):** ≈ 11–13 рабочих дней.

---

## Чеклист перед мерджем каждой задачи

- [ ] Описана причина изменения в commit message: `fix(meetings): <ID> — <кратко>`.
- [ ] Добавлен/обновлён регрессионный тест из таблицы выше.
- [ ] Пройдены `pytest backend/tests/meetings -q`, `npm run lint`, `npm run typecheck` (или эквиваленты).
- [ ] Если задача связана с iCal/email — проверено письмо в Outlook + Apple Calendar + Thunderbird (ручной QA).
- [ ] Если задача правит UX — приложен скриншот/видео в PR.
- [ ] Документация `./docs/meetings.md` синхронизирована (или создан follow-up `DOC-…`).
