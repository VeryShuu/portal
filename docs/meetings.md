# Модуль «Переговорные» (Meetings)

> Документация модуля бронирования переговорных комнат портала. Реализация выполнена по мотивам [VeryShuu/mrbs](https://github.com/VeryShuu/mrbs) (доменная логика и UX), инфраструктурные слои — стек портала (FastAPI + SQLAlchemy + PostgreSQL + Vue 3 + Naive UI).
>
> Историческое название «MRBS» сохранено в разделах ниже как ссылка на первоисточник идей.

---

## 1. Что такое MRBS

MRBS — самостоятельное веб-приложение для бронирования переговорных комнат.

**Стек MRBS:**
- Next.js 16 (App Router) + TypeScript
- Prisma ORM + **SQLite**
- NextAuth.js 4 (Credentials + Keycloak)
- Tailwind CSS + Headless UI
- Zod, Vitest, Playwright
- Docker (multi-stage standalone)

Технологически он **несовместим** с нашим стеком (FastAPI + SQLAlchemy + PostgreSQL + Vue 3 + Naive UI), поэтому переиспользовать код напрямую нельзя — портируем **доменную логику и UX**, а инфраструктурные слои берём из портала.

---

## 2. Функциональность MRBS

### Ключевые возможности

| Возможность | Описание | Приоритет |
|---|---|---|
| Календарное бронирование | Сетка дня по комнатам с настраиваемым рабочим временем (`CALENDAR_START_HOUR`/`END_HOUR`) | **P0** |
| Мульти-комнатное событие | Одно бронирование одновременно на несколько комнат | **P0** |
| Серии (повторяющиеся встречи) | `seriesId`, batch API до 52 экземпляров (daily/weekly/weekdays) | P1 |
| Приглашение участников | Поиск по Keycloak, редактирование состава после создания | **P0** |
| Email-уведомления | iCal с `SEQUENCE`, diff-логика на изменения состава | **P0** |
| Конфликт-чек | Транзакционный с in-process мьютексом | **P0** |
| Аудит-лог | `AuditLog` + stdout, ротация по `AUDIT_RETENTION_DAYS` | — (есть в портале) |
| Ссылка на виртуальную комнату | `Room.link` (Zoom/Teams/Jitsi) | P1 |
| Мобильный вид | Сетка комнат **или** список всех мероприятий дня | P2 |
| Фоновое обновление | Каждые 60 сек без блокирующей загрузки | P1 |
| Rate limiting | Per-IP/per-username с поддержкой `TRUST_PROXY` | — (есть в портале) |

### Email-логика MRBS (diff-уведомления)

При **изменении состава участников**:
- Добавленные → получают `METHOD:REQUEST` (новое приглашение)
- Удалённые → получают `METHOD:CANCEL` (отмена)
- Неизменные → получают `METHOD:REQUEST` с `SEQUENCE++` **только если** менялись поля бронирования (время/комната/название/описание)

Это критично для корректного отображения в Outlook/Thunderbird/Apple Calendar.

### Доменная модель (Prisma)

```
Room (id, name, email, link, timestamps)
Booking (id, title, organizer, creatorId, description,
         startTime, endTime, invitedUsers (JSON),
         emailNotifications, seriesId, updateCount, timestamps)
BookingRoom (bookingId, roomId)  -- M2M
```

---

## 3. Что переиспользуем из портала

Перед началом работ важно: **большую часть инфраструктуры MRBS у нас уже есть**.

| Подсистема MRBS | Аналог в портале | Действие |
|---|---|---|
| NextAuth (Credentials + Keycloak) | `./backend/app/api/auth/` (OIDC + local) | **Переиспользовать** |
| `KeycloakUser` синхронизация | `./backend/app/services/keycloak/directory.py` | **Переиспользовать** |
| `EmailSettings` (SMTP) | Системные настройки + Postfix | **Переиспользовать** |
| `AuditLog` | Партиционированный `audit_log` (`./backend/migrations/versions/013_audit_log.py`) | **Переиспользовать** |
| `AuthSettings` | `./backend/app/api/system_settings.py` | **Переиспользовать** |
| `BackgroundSettings` | `branding` модуль | **Переиспользовать** |
| Rate-limit, CSP, шифрование секретов | Уже централизовано | **Переиспользовать** |
| In-app уведомления (toast/SSE) | `./backend/app/api/notifications.py` | **Добавить** дублирование на изменения встреч |
| Роли `user`/`admin` | `reader`/`editor`/`admin` (`./docs/roles-matrix.md`) | **Адаптировать** |

**Отбрасываем** (это слой NextAuth/Prisma/SQLite, нерелевантный для нас):
- Таблицы `Account`, `Session`, `VerificationToken`
- `KeycloakUser` (своя таблица в MRBS) — у нас уже есть кэш в `keycloak_admin`
- AES-GCM шифрование секретов в БД
- Backup SQLite, ротация `AuditLog` (PostgreSQL + партиции делают это иначе)

---

## 4. Архитектура внедрения

### 4.1. Backend — новый модуль `meetings`

```
backend/app/
├── models/
│   └── meetings.py             # Room, Booking, BookingRoom
├── schemas/
│   └── meetings.py             # Pydantic IN/OUT DTO
├── api/
│   └── meetings/
│       ├── __init__.py
│       ├── _mappers.py         # booking_to_out (общий маппер)
│       ├── rooms.py            # CRUD комнат (admin)
│       ├── bookings.py         # CRUD бронирований
│       ├── series.py           # Series-level операции
│       └── participants.py     # Поиск участников (прокси к Keycloak)
├── services/
│   └── meetings/
│       ├── __init__.py
│       ├── bookings_service.py # Создание/обновление/удаление/поиск бронирований
│       ├── rooms_service.py    # CRUD переговорных комнат
│       ├── series_service.py   # Операции над сериями
│       ├── notifications.py    # iCal + diff-логика участников + room.email
│       ├── ical_builder.py     # RFC 5545: METHOD, SEQUENCE, ATTENDEE
│       ├── dispatch.py         # schedule_email_dispatch (единый диспетчер)
│       ├── realtime.py         # SSE-публикация events
│       └── audit.py            # push_meetings_audit
└── worker/
    └── tasks/
        ├── email_utils.py      # общий хелпер (classify_smtp_error, compute_retry_defer, smtp_send)
        ├── email_outbox.py     # cron process_email_outbox / cleanup_email_outbox
        └── meetings/
            └── email.py        # ARQ-задача send_meeting_email (legacy fallback)
migrations/versions/
├── 048_meetings.py             # rooms, bookings, booking_rooms + EXCLUDE
├── 049_meeting_rooms_add_email.py  # добавление колонки email к meeting_rooms
└── 050_drop_meetings_audit_log.py  # удаление отдельной таблицы meetings_audit_log
```

### 4.2. База данных (PostgreSQL)

Отличия от Prisma-схемы MRBS, обусловленные нашим стеком:

| MRBS (SQLite/Prisma) | Portal (PostgreSQL/SQLAlchemy) |
|---|---|
| `id String @default(cuid())` | `id UUID DEFAULT gen_random_uuid()` |
| `invitedUsers String?` (TEXT JSON) | `invited_users JSONB` |
| `creatorId String?` (без FK) | `creator_id UUID REFERENCES users(id) ON DELETE SET NULL` |
| `seriesId String?` | `series_id UUID` |
| In-process `bookingMutex` | **EXCLUDE GIST constraint** на БД |

**Защита от пересечений на уровне БД:**

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE booking_rooms
  ADD COLUMN start_time TIMESTAMPTZ NOT NULL,
  ADD COLUMN end_time   TIMESTAMPTZ NOT NULL;

ALTER TABLE booking_rooms
  ADD CONSTRAINT booking_rooms_no_overlap
  EXCLUDE USING gist (
    room_id WITH =,
    tstzrange(start_time, end_time, '[)') WITH &&
  );
```

Альтернатива (если избегать денормализации): **advisory lock** на `room_id` в транзакции + ручная проверка пересечений. Это безопаснее для нескольких воркеров, чем JS-мьютекс MRBS.

**Индексы:**
- `(start_time, end_time)`
- `(series_id)`
- `(creator_id)`
- GIST на `tstzrange(start_time, end_time)` (для быстрых выборок по диапазону)

### 4.3. API (под OpenAPI портала, префикс `/api/v1/meetings`)

```
# Комнаты
GET    /meetings/rooms
POST   /meetings/rooms                          (admin)
GET    /meetings/rooms/{id}
PUT    /meetings/rooms/{id}                     (admin)
DELETE /meetings/rooms/{id}                     (admin)

# Бронирования
GET    /meetings/bookings?room_id=&date=&start_date=&end_date=&creator_id=&limit=&offset=
GET    /meetings/bookings/my?start_date=&limit=        # текущий пользователь (виджет)
POST   /meetings/bookings
GET    /meetings/bookings/{id}
PUT    /meetings/bookings/{id}                  (creator | admin)
DELETE /meetings/bookings/{id}                  (creator | admin)
# POST /meetings/bookings/batch — не реализован (см. Бэклог)

# Серии
PUT    /meetings/series/{series_id}             (creator | admin)
DELETE /meetings/series/{series_id}             (creator | admin)
GET    /meetings/series/{series_id}/count

# Участники
GET    /meetings/participants/search?q=         # прокси к Keycloak directory
```

**Все эндпоинты** — через `withMiddleware`-аналог портала (request-id, аудит, rate-limit, structlog).

### 4.4. Email + iCal

- ARQ-задача `send_meeting_invitation` (queue) — fire-and-forget с retry (в отличие от MRBS, где ретраев нет)
- iCal builder:
  - `METHOD:REQUEST` для create/update
  - `METHOD:CANCEL` для delete
  - `SEQUENCE` = `booking.update_count` (RFC 5545)
  - `ORGANIZER` = `booking.organizer`
  - `ATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE` для каждого участника
  - `UID`:
    - одиночная встреча → `{booking.id}@{COMPANY_DOMAIN}`
    - встреча из серии → `series-{series_id}@{COMPANY_DOMAIN}` (общий UID для всей серии, рассылается одно письмо с `RRULE`)
    - при отвязке инстанса от серии (`apply_to=this` для встречи из серии) — высылается CANCEL со старым `series-…@…` и REQUEST с новым `{booking.id}@…` (см. `notifications.dispatch_meeting_emails`)
- Diff-логика на изменение состава (повторяем MRBS):
  - `added` → REQUEST новым
  - `removed` → CANCEL удалённым
  - `unchanged` → REQUEST с `SEQUENCE++` **только если** менялись неучастниковые поля
- `room.email` — если задан у комнаты, добавляется как отдельный получатель iCal-уведомления при любом событии бронирования этой комнаты (create / update / delete)

### 4.5. Frontend (Vue 3 + Naive UI + TanStack Query)

```
frontend/src/
├── pages/meetings/
│   └── MeetingsPage.vue              # Календарь (день)
├── pages/admin/
│   └── MeetingRoomsAdminPage.vue     # CRUD комнат
├── components/meetings/
│   ├── RoomGrid.vue                  # Сетка: столбцы = комнаты, строки = время.
│   │                                  # Мобильный режим встроен в RoomGrid через
│   │                                  # @media + scroll-snap (одна комната на экран);
│   │                                  # отдельного RoomGridMobile.vue/MeetingsMobileListPage.vue нет.
│   ├── MeetingFormDialog.vue         # Создание/редактирование + диалог «эта/вся серия»
│   ├── BookingCard.vue
│   ├── ParticipantPicker.vue         # n-select multiple filterable remote
│   └── RecurrenceEditor.vue          # daily / weekly / weekdays / biweekly / monthly
├── stores/
│   └── notifications.ts              # SSE-листенер 'meeting_changed' → window-event 'meetings:changed'
├── queries/
│   └── meetings.ts                   # TanStack Query hooks (refetchInterval 60s — fallback к SSE)
└── api/
    └── meetings.ts                   # Клиент к /api/v1/meetings/*
```

### 4.6. Интеграция в портал

- **Меню** (`./frontend/src/composables/useAppMenu.ts`): пункт «Переговорные» в общем верхнеуровневом списке портала (специальной группы «Сервисы» в v1 нет), виден при `modulesStore.isEnabled('meetings')`
- **Роутер** (`./frontend/src/router.ts`):
  ```ts
  MEETINGS: '/meetings',
  MEETINGS_ROOMS: '/admin/meeting-rooms',
  ```
  Guard `requireModule` редиректит `/meetings` → `/`, если модуль выключен.
- **Виджет на главной** (`./frontend/src/pages/HomePage.vue`): «Мои ближайшие встречи» (5 шт., `GET /meetings/bookings/my?start_date=today&limit=5` — отдельный эндпоинт по аналогии с `/feedback/my`, без магической строки `creator_id=me`)
- **Админка модуля** (`./frontend/src/pages/admin/tabs/ModulesTab.vue`): секция «Переговорные» с переключателем `enabled`, полями `calendar_start_hour`, `calendar_end_hour`, `max_recurrence_horizon_days`, `min_search_chars` и кнопкой **«Управление комнатами»** → переход на `/admin/meeting-rooms` (`./frontend/src/pages/admin/MeetingRoomsAdminPage.vue`). Бэкенд: `PUT /api/v1/admin/modules/meetings` (`./backend/app/api/modules.py`).
- **Bootstrap** (`./backend/app/api/bootstrap.py`): `_get_modules()` обязан пробрасывать поле `meetings` в `AllModuleSettingsOut`, иначе валидация падает → fallback на `_DEFAULT_MODULES`, и все модули выглядят выключенными.
- **Системные настройки** (`system_settings`):
  - `meetings.calendar_start_hour` (default 8)
  - `meetings.calendar_end_hour` (default 19)
  - `meetings.max_batch_size` (default 52)
  - `meetings.timezone` — берётся из глобальной настройки портала
  - `meetings.company_name` — берётся из `branding.title`
- **i18n** (`./frontend/src/i18n/`): ru/en для всех новых строк, включая `admin.modules.meetings.*`
- **Уведомления**: при изменении встречи участники получают in-app toast через существующий SSE-стрим (`./backend/app/api/notifications.py`)
- **Аудит**: события `MEETING_CREATED`, `MEETING_UPDATED`, `MEETING_DELETED`, `ROOM_CREATED`, `ROOM_UPDATED`, `ROOM_DELETED`, `SERIES_UPDATED`, `SERIES_DELETED`

---

## 5. План работ

| Этап | Содержание | Оценка |
|---|---|---|
| **1. БД и модели** | Миграции `048_meetings.py` + `049_meeting_rooms_add_email.py` (rooms, bookings, booking_rooms, EXCLUDE constraint, `btree_gist`, `room.email`), SQLAlchemy-модели, Pydantic-схемы | 1–2 дня |
| **2. Backend CRUD** | `rooms.py`, `bookings.py` с фильтрами; `bookings_service.py`; обработка `IntegrityError` → 409; интеграция с audit-логом; unit-тесты с testcontainers | 3–4 дня |
| **3. Серии** | `series.py`, `series_service.py`, повторение daily/weekly/weekdays | 2 дня |
| **4. Email + iCal** | `ical_builder.py` (RFC 5545), ARQ-задача `send_meeting_email`, diff-логика, шаблоны Postfix | 2–3 дня |
| **5. Frontend** | `RoomGrid.vue`, drag-to-create, `MeetingFormDialog`, `ParticipantPicker`, mobile-list, TanStack Query, i18n | 4–5 дней |
| **6. Интеграция и тесты** | Меню, виджет на Home, Playwright e2e (создание/конфликт/серия/отмена/приглашение), k6 нагрузочный, документация в `./docs/` | 2–3 дня |

**Итого: 14–19 рабочих дней** (≈ 3–4 недели на 1 разработчика).

---

## 6. Технические риски

| Риск | Митигация |
|---|---|
| Race condition при одновременном бронировании из нескольких воркеров | EXCLUDE GIST constraint на БД (атомарно), а не in-process мьютекс как в MRBS |
| Outlook/Apple Calendar некорректно отображают обновления | Строго соблюдать `SEQUENCE` в iCal (увеличивать на каждое изменение), правильный `UID`, корректные `METHOD` |
| Спам почтового сервера при массовых батч-операциях | ARQ throttling + батчевание писем по получателю |
| Большие выборки на месяц по всем комнатам | Индекс GIST на `tstzrange`, лимит 500 в одном запросе (как в MRBS) |
| Миграция btree_gist требует прав суперюзера в PostgreSQL | Проверить deploy-инструкцию; при необходимости fallback на advisory lock |
| Часовые пояса (Europe/Moscow vs UTC) | Хранить в БД `TIMESTAMPTZ` (UTC), отдавать в API ISO 8601, на фронте конвертировать в локальный TZ |
| Конфликты с уже существующими событиями при импорте данных | Этот сценарий выходит за рамки v1; решается отдельной задачей миграции, если потребуется |

---

## 7. Согласованные решения (бизнес-уровень)

> Ответы получены от заказчика. Зафиксированы как требования к v1. MRBS-репозиторий в проде — берём его поведение за эталон там, где здесь нет явных отличий.

### 7.1. Доступ и роли

| Вопрос | Решение |
|---|---|
| Кто может бронировать | Любой авторизованный сотрудник портала |
| Кто видит чужие встречи | Все видят все встречи (название, время, организатор, участники) — приватного режима в v1 нет |
| Кто может править/удалять | Только организатор; администратор портала может править/удалять любую |
| Кто заводит/правит комнаты | Только администратор портала (отдельная роль «офис-менеджер» **не нужна**) |

### 7.2. Конфликты и целостность

| Вопрос | Решение |
|---|---|
| Двойное бронирование одной комнаты | Второй пользователь получает 409 с сообщением «Комната уже занята». Защита — на уровне БД (см. п. 4.2) |
| Удаление учётки организатора | Имя организатора сохраняется в `bookings.organizer_name` как текстовый снимок; `creator_id` → `NULL` через `ON DELETE SET NULL` |

### 7.3. Участники

| Вопрос | Решение |
|---|---|
| Откуда брать | Только сотрудники из Keycloak (внешних по email **нет** в v1) |
| Минимум символов для поиска | **3** |
| Что показывать | ФИО + email. Аватарки **не показываем** |
| Где искать | По имени, фамилии и email |

### 7.4. Email-уведомления

| Сценарий | Кому отправить |
|---|---|
| Создана встреча | Всем приглашённым |
| Изменены время / комната / тема / описание | Всем приглашённым |
| Удалена встреча | Всем приглашённым |
| Добавлен участник в существующую встречу | Только новому участнику (REQUEST) |
| Удалён участник из встречи | Только удалённому (CANCEL) |
| Напоминание за N минут до начала | **Не нужно** в v1 |
| Письмо на ящик комнаты | **Нужно** — если у комнаты задан `email`, при создании/изменении/удалении встречи отправляется `METHOD:REQUEST` / `METHOD:CANCEL` на этот адрес (уведомление ответственного) |

- Формат — **полноценное iCal-приглашение** (`text/calendar; method=REQUEST/CANCEL`), которое одной кнопкой добавляется в Outlook/Apple Calendar/календарь телефона
- Отправитель — общий портальный `from_email` из настроек SMTP портала
- Diff-логика на изменение состава — как в MRBS (см. п. 4.4)

### 7.5. Календарь и UI

| Параметр | Решение |
|---|---|
| Вид календаря | **Только день** (вид «неделя/месяц» — не в v1) |
| Шапка | Кнопка «Сегодня» (центр), стрелки навигации по датам, отображение даты + дня недели |
| Сетка | Столбцы = комнаты; строки = слоты по 30 мин; рабочее окно 08:00–19:00 (настраивается в админке) |
| Шапка комнаты | Название; если у комнаты есть ссылка на онлайн (Zoom-комната) — название отображается как **ссылка** (синий, подчёркнутый) — см. скриншот эталона |
| Текущее время | Красная горизонтальная линия через всю сетку |
| Создание встречи | **По клику** на пустой слот → открывается модальная форма (drag-to-create в v1 **нет**) |
| Цвет события | Светло-голубая плашка с тёмно-синим текстом (как в эталоне) |
| Обновление | **Мгновенное** через SSE (как только кто-то создал/изменил/удалил — у всех остальных моментально обновляется) |
| Мобильный вид | Та же дневная сетка, но горизонтальный скролл — **одна комната на экране** |

**Эталон UI** — см. скриншот, переданный заказчиком (день 18 мая, столбцы Zoom Gold / Zoom Silver / Zoom Vip / Москва 3 этаж / Москва 5 этаж / Мурманск / Санкт-Петербург / Сочи).

### 7.6. Повторы (серии)

| Параметр | Решение |
|---|---|
| Варианты повтора | Каждый день · Каждый рабочий день (пн–пт) · Каждую неделю · Каждые 2 недели · Каждый месяц |
| Сложные правила («2-й вторник месяца» и т.п.) | **Не нужно** в v1 |
| Горизонт | **Максимум 31 день** вперёд (`max_recurrence_horizon_days: 31`) |
| Изменение одной встречи в серии | При сохранении пользователю задаётся вопрос (как в Outlook): **«Применить только к этой встрече»** или **«Применить ко всей серии»** |

### 7.7. Виртуальные комнаты

| Параметр | Решение |
|---|---|
| Реализация | Постоянная ссылка у комнаты (`rooms.link`) — например, «Zoom Gold» содержит постоянный Zoom-URL |
| Где показывается | Шапка столбца в календаре — как кликабельная ссылка на название комнаты |
| Автогенерация уникальной ссылки на каждую встречу (Zoom API) | **Не нужно** в v1 |

### 7.8. Часовые пояса

- Офисы в разных городах (Москва, Санкт-Петербург, Мурманск, Сочи, и т.д.) — **multi-TZ обязателен**
- У каждой комнаты — собственный часовой пояс (`rooms.timezone`, например `Europe/Moscow`, `Europe/Samara`)
- В БД храним всё в `TIMESTAMPTZ` (UTC)
- На фронте при отображении сетки конкретной комнаты — конвертация в её локальный TZ; в шапке столбца — короткое обозначение TZ, если оно отличается от TZ браузера пользователя
- В iCal — `DTSTART;TZID=…` с таймзоной портала (`system_settings.timezone`), плюс полноценная секция `VTIMEZONE` для совместимости с Outlook/Apple Calendar (см. `ical_builder._build_vtimezone`). Сетка фронта при этом рендерится в TZ комнаты (`BookingCard.minutesInTz`), что согласуется с разделом 8.4: единый iCal в TZ портала, отображение в UI — в TZ комнаты

### 7.9. Атрибуты комнат

В v1 у комнаты только:
- `name` — название
- `email` — необязательный email ответственного за комнату; если задан — получает iCal-уведомления при создании/изменении/удалении встречи
- `link` — необязательная постоянная ссылка на онлайн-встречу
- `timezone` — IANA-таймзона
- `is_active` — soft-disable

**Не нужно** в v1: вместимость, этаж, адрес офиса, оборудование, фото.

### 7.10. История, нагрузка, миграция

| Вопрос | Решение |
|---|---|
| Хранение истории действий (аудит) | **7 дней** (короткая ротация — записи старше 7 дней автоматически удаляются) |
| Отчёты для руководства | **Не нужны** в v1 |
| Целевая нагрузка | До 50 одновременных пользователей |
| Миграция данных из старой системы | **Не нужна** |
| Двусторонняя синхронизация с Outlook | **Не нужна** в v1 |
| Уведомления в Telegram/Mattermost | **Не нужны** в v1 |
| Табло «занято/свободно» у входа | **Не нужно** в v1 |

### 7.11. Запуск и качество

| Вопрос | Решение |
|---|---|
| Feature flag (быстрое выключение модуля) | **Да** — переключатель `meetings.enabled` в `system_settings` (по аналогии с `./backend/app/api/modules.py`) |
| Тестирование email | Достаточно unit-теста с моком SMTP (без mailpit/mailhog) |
| Пилот / постепенный rollout | **Запуск сразу для всех сотрудников** |
| Обучение сотрудников | **Не требуется** — интерфейс должен быть самоочевидным |

---

## 8. Уточнения архитектуры по итогам решений

### 8.1. Изменения в БД (по сравнению с разделом 4.2)

```python
# models/meetings.py
class Room:
    id: UUID
    name: str            # unique
    email: str | None    # email ответственного за комнату; получает iCal-уведомления
    link: str | None     # постоянная ссылка на онлайн-встречу
    timezone: str        # IANA, default 'Europe/Moscow'
    is_active: bool      # default True
    sort_order: int      # для порядка столбцов в календаре
    created_at, updated_at

class Booking:
    id: UUID
    title: str
    organizer_name: str  # текстовый снимок (сохраняется после удаления учётки)
    creator_id: UUID | None  # FK → users.id ON DELETE SET NULL
    description: str | None
    start_time: datetime  # TIMESTAMPTZ (UTC)
    end_time: datetime    # TIMESTAMPTZ (UTC)
    invited_users: JSONB  # [{user_id, full_name, email}]
    series_id: UUID | None
    recurrence_rule: str | None  # RFC 5545 RRULE для серии (хранится на первой встрече)
    update_count: int     # SEQUENCE для iCal
    created_at, updated_at

class BookingRoom:
    booking_id: UUID
    room_id: UUID
    start_time: TIMESTAMPTZ  # денормализация для EXCLUDE constraint
    end_time:   TIMESTAMPTZ
    PRIMARY KEY (booking_id, room_id)
    EXCLUDE USING gist (room_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&)
```

**Поле `room.email`** — необязательное, хранит адрес ответственного за комнату. Если задано — включается в список получателей iCal-уведомлений наравне с приглашёнными участниками (см. решение 7.4).

### 8.2. SSE для real-time (вместо polling MRBS)

**Объяснение для нетехнических читателей.** Сейчас портал отправляет личные уведомления каждому пользователю по отдельности (например, «вам пришёл ответ»). Для переговорных нужно другое: когда кто-то создал или изменил встречу, все, кто в этот момент смотрит страницу переговорных, должны мгновенно увидеть изменение — без перезагрузки. Технически это работает так: страница переговорных дополнительно слушает **общий канал изменений бронирований** (поверх личного канала уведомлений). Один сигнал в канале — все пользователи на странице обновляют свой календарь. Это полностью аналогично тому, как в чатах «личные сообщения» и «сообщения в канале» приходят по одному соединению.

**Реализация.** Используем существующий SSE-стрим (`./backend/app/api/notifications.py`):

- Новый тип события: `meeting_changed` с payload `{action, booking_id, room_ids, date}`
- При create/update/delete бронирования → backend публикует событие в Redis-стрим `notifications:meetings` (один глобальный поток для всех)
- SSE-генератор в `notifications.py` читает **два потока параллельно** через `asyncio.gather`:
  - `notifications:{user_id}` — личные уведомления (как сейчас)
  - `notifications:meetings` — глобальный поток изменений бронирований
  Оба через `xread`, результаты мержатся в один SSE-поток клиенту.
- Фронт на странице `/meetings` слушает события `meeting_changed` → инвалидирует TanStack Query кэш для затронутой даты
- Polling-fallback каждые 60 сек включён по умолчанию (`refetchInterval: 60_000, refetchIntervalInBackground: false` в `useMeetingBookingsQuery` / `useMyMeetingBookingsQuery`) — закрывает «дыру» при потере SSE-канала

### 8.3. Серии: Outlook-style диалог

При сохранении изменения встречи, у которой `series_id != null`:

1. Если пользователь поменял что-либо — фронт показывает диалог: «Применить только к этой встрече / Применить ко всей серии».
2. «Только к этой» → `PUT /meetings/bookings/{id}` + бэкенд автоматически отвязывает от серии (`series_id = null`, `recurrence_rule = null`).
3. «Ко всей серии» → `PUT /meetings/series/{series_id}`.

При удалении — аналогично: «Удалить только эту / Удалить всю серию».

### 8.4. Multi-TZ конкретика

- Сетка календаря рендерится **в TZ комнаты** (`BookingCard.minutesInTz` + `RoomGrid.sortedRooms`): позиция карточки в столбце вычисляется через `Intl.DateTimeFormat({timeZone: room.timezone})`, поэтому «09:00» в столбце Москвы и Самары всегда соответствует локальным 09:00 этой комнаты.
- В шапке столбца, если TZ комнаты отличается от TZ браузера, показывается короткий маркер `GMT±N` (вычисляется через `shortTz` по текущему offset) и подсказка «время в TZ комнаты».
- iCal для всех комнат собирается в одной секции `VTIMEZONE` (TZ портала) — см. 8.6 и `ical_builder._build_vtimezone`; рассинхрон между сеткой (room TZ) и iCal (portal TZ) ожидаем и согласован с разделом 7.8.

### 8.5. Feature flag

В `./backend/app/core/modules_config.py` (рядом с `NextcloudModuleSettings`, `PhotosModuleSettings`):

```python
class MeetingsModuleSettings(BaseModel):
    enabled: bool = False
    calendar_start_hour: int = 8
    calendar_end_hour: int = 19
    max_recurrence_horizon_days: int = 31  # 31 день, см. expand_recurrence
    min_search_chars: int = 3  # читается из настроек, не захардкожен
```

Эндпоинты `GET /modules` и `GET /bootstrap` возвращают поле `meetings` — фронт (`useModulesStore`) скрывает пункт меню «Переговорные», если `meetings.enabled == false`, а guard роутера редиректит `/meetings` → `/`.

**Внимание:** `./backend/app/api/bootstrap.py:_get_modules()` обязан явно собирать `AllModuleSettingsOut(nextcloud=…, photos=…, meetings=…)` — пропуск любого поля приводит к `ValidationError`, который ловится `asyncio.gather(return_exceptions=True)` и подменяется на `_DEFAULT_MODULES` (все модули `enabled=False`).

Переключение модуля и редактирование числовых параметров — через админку: вкладка «Модули» → секция «Переговорные» (`./frontend/src/pages/admin/tabs/ModulesTab.vue`), кнопка «Управление комнатами» ведёт на `/admin/meeting-rooms`.

### 8.6. Аудит

Аудит модуля «Переговорные» пишется в **общую партиционированную таблицу `audit_log`** (см. `./backend/migrations/versions/013_audit_log.py`) с типизированными `action`-кодами (`MEETING_CREATED`, `MEETING_UPDATED`, `MEETING_DELETED`, `MEETING_SERIES_CREATED`, `SERIES_UPDATED`, `SERIES_DELETED`, `ROOM_CREATED`, `ROOM_UPDATED`, `ROOM_DELETED`).

Отдельной таблицы `meetings_audit_log` больше нет — она была удалена миграцией `./backend/migrations/versions/050_drop_meetings_audit_log.py` вместе с cron-задачей `cleanup_meetings_audit`. Поле `audit_retention_days` тоже удалено из `MeetingsModuleSettings` — retention управляется политикой глобального `audit_log`.

---

## 9. Обновлённые таблицы

### 9.1. Обновлённый приоритет функциональности

| Возможность | Решение по v1 |
|---|---|
| Календарное бронирование (день) | ✅ P0 |
| Мульти-комнатное событие | ✅ P0 |
| Серии с диалогом «эта / вся серия» | ✅ P0 |
| Приглашение участников (Keycloak) | ✅ P0 |
| iCal email-приглашения + diff-логика | ✅ P0 |
| EXCLUDE constraint на конфликты | ✅ P0 |
| SSE real-time обновления | ✅ P0 |
| Multi-TZ (комнаты в разных городах) | ✅ P0 |
| Ссылка на онлайн-комнату (постоянная) | ✅ P0 |
| Мобильный горизонтальный скролл | ✅ P0 |
| Feature flag | ✅ P0 |
| Email на ящик комнаты | ✅ Реализовано (см. 7.4) |
| Drag-to-create | ❌ Не делаем |
| Вид «неделя/месяц» | ❌ Не делаем |
| Напоминания за N минут | ❌ Не делаем |
| Внешние участники по email | ❌ Не делаем |
| Аватарки в поиске | ❌ Не делаем |
| Атрибуты комнаты (вместимость/этаж/фото) | ❌ Не делаем |
| Отчёты для руководства | ❌ Не делаем |
| Outlook 2-way sync, Telegram/Mattermost | ❌ Не делаем |
| Табло у входа в комнату | ❌ Не делаем |

### 9.2. Обновлённый план работ

| Этап | Содержание | Оценка |
|---|---|---|
| **1. БД и модели** | Миграция (rooms с `timezone`/`link`/`sort_order`, bookings с `organizer_name`/`recurrence_rule`, booking_rooms с денормализацией и EXCLUDE GIST), `btree_gist`. Аудит модуля пишется в общий `audit_log` (миграция `050_drop_meetings_audit_log.py` удалила отдельную таблицу `meetings_audit_log`) | 1–2 дня |
| **2. Backend CRUD** | `rooms.py` (admin), `bookings.py` (creator/admin), `participants.py` (поиск по Keycloak, min 3 символа), обработка `IntegrityError` → 409, аудит-события | 3–4 дня |
| **3. Серии и batch** | `series.py`, генерация экземпляров по RRULE (daily/weekdays/weekly/biweekly/monthly, max 31 день), логика «эта / вся серия» | 2 дня |
| **4. Email + iCal** | `ical_builder.py` (RFC 5545, TZID, SEQUENCE, METHOD), ARQ-задача `send_meeting_email` с retry, diff-логика, unit-тесты с mock SMTP | 2–3 дня |
| **5. SSE real-time** | Тип события `meeting_changed` в Redis-стриме, публикация из `booking_service`, фронт-подписка с инвалидацией кэша | 1 день |
| **6. Frontend — календарь** | `RoomGrid.vue` (CSS Grid), `BookingCard.vue`, текущее время (красная линия), кнопка «Сегодня», навигация по датам, клик на слот → форма | 3–4 дня |
| **7. Frontend — формы** | `MeetingFormDialog`, `ParticipantPicker` (3 символа, без аватарок), `RecurrenceEditor` (5 вариантов, max 31 день), диалог «эта / вся серия» | 2–3 дня |
| **8. Frontend — mobile** | Горизонтальный скролл с привязкой к одной комнате на экран (snap-scroll), tap-friendly слоты | 1–2 дня |
| **9. Feature flag + админка** | `MeetingsModuleSettings`, `MeetingRoomsAdminPage.vue` (CRUD комнат), скрытие меню при `enabled=false` | 1 день |
| **10. Интеграция и тесты** | Меню в `AppLayout`, виджет «Мои ближайшие» на Home, i18n ru/en, Playwright e2e (создание/конфликт/серия/диалог/iCal/SSE), документация в `./docs/` | 2–3 дня |

**Итого: 18–25 рабочих дней** (≈ 4–5 недель на 1 разработчика).

> Увеличение на 4–6 дней относительно первоначальной оценки связано с: multi-TZ (комнаты в разных городах), SSE real-time, диалог «эта/серия». Изначально планировалась отдельная `meetings_audit_log` с 7-дневным retention, но в итоге аудит модуля объединён с общей партиционированной таблицей `audit_log` (миграция 050).

### 9.3. Обновлённые риски

| Риск | Митигация |
|---|---|
| Multi-TZ: путаница пользователя при просмотре комнаты другого офиса | Сетка/карточки фронта рендерятся в TZ комнаты; рядом с названием — короткий маркер `GMT±N` (если отличается от браузера); iCal с правильным `TZID` + `VTIMEZONE` |
| SSE-соединение рвётся за nginx/reverse proxy | Использовать существующий механизм портала (уже работает для in-app уведомлений); polling fallback 60 сек |
| Серия 31 экземпляр × N комнат → много iCal-писем сразу | ARQ rate-limit на отправку (например, не более 50 писем/сек); группировка серии в одно письмо с `RRULE` (стандарт iCal) |
| Outlook путается с `RRULE` при импорте серии | Покрыть e2e-тестом на реальном Outlook (опционально — Apple Calendar) перед релизом |
| Удаление учётки организатора ломает фильтр «мои встречи» | `creator_id` остаётся `NULL`, `organizer_name` сохранён как текст; фильтр «мои» по `creator_id = current_user.id` |
| Retention аудита может быть мал для расследований | Аудит модуля пишется в общую партиционированную таблицу `audit_log`; retention управляется глобальной политикой `audit_log`. Отдельного `audit_retention_days` у модуля больше нет |

---

## 10. Открытые вопросы для согласования с разработкой

Эти пункты заказчику не нужны — это технические детали, которые нужно зафиксировать **внутри команды** перед стартом:

1. Установлено ли расширение `btree_gist` в проде PostgreSQL? Если нет — добавляем `CREATE EXTENSION` в миграцию (требует прав суперюзера, координируем с DevOps).
2. Используем библиотеку `icalendar` (PyPI) для построения iCal — добавить в `./backend/pyproject.toml`.
3. ARQ retry-policy для писем: 3 попытки с экспонентой 1/5/30 мин.
4. Подключаем `dateutil.rrule` для генерации экземпляров серии (он сильно проще, чем писать своё).
5. Какой UUID — `gen_random_uuid()` (как другие модели портала) или `uuid7` (упорядоченные)? Идём по умолчанию — `gen_random_uuid()`.
6. Имя из Keycloak в `organizer_name` — берём `name` или `username` при создании, snapshot.
7. Локализация интерфейса — ru + en (как остальной портал).

---

## 11. Что дальше

1. ✅ Согласовать с заказчиком — **выполнено** (раздел 7).
2. Закрыть технические открытые вопросы из раздела 10 внутри команды (≤ 1 день).
3. Завести тикеты по этапам из раздела 9.2.
4. Старт с этапа 1 (БД и модели).
5. После этапа 5 — промежуточная демо для заказчика (CRUD + UI без серий).
6. Релиз после этапа 10 с включённым feature flag для всех сотрудников.

---

## 12. Детальная спецификация для ИИ-агента

> Раздел разбивает разработку на **атомарные задачи** с точными путями файлов, сигнатурами, SQL, контрактами API и критериями приёмки. Каждая задача — самодостаточный коммит. Агент должен выполнять задачи **строго в указанном порядке** (есть зависимости).

### Принципы работы агента

- **Конвенции портала:** следовать стилю существующего кода. Не вводить новые библиотеки без явного указания в задаче. Перед изменением файла — прочитать соседние модули того же типа (ссылки даны в каждой задаче как «эталон»).
- **Тесты:** каждая backend-задача завершается прохождением `pytest backend/tests/test_meetings*.py -x`. Каждая frontend-задача — `npm --prefix frontend test -- meetings`.
- **Линтеры:** `ruff check backend/app/api/meetings backend/app/services/meetings backend/app/models/meetings.py` и `npm --prefix frontend run lint -- src/pages/meetings src/components/meetings` должны проходить **без warnings** после каждой задачи.
- **Миграции:** не редактировать существующие миграции. Только добавлять новые с уникальным номером.
- **Запрещено:** правки за пределами модуля `meetings`, кроме явно указанных файлов (`AppLayout.vue`, `router.ts`, `HomePage.vue`, `modules_config.py`, `main.py`).
- **Git:** один коммит на задачу. Сообщение в формате `feat(meetings): T-NNN <описание>` или `test(meetings): T-NNN …` / `fix(meetings): T-NNN …`.

---

### Этап 1 — БД и модели

#### T-001. Миграция Alembic `048_meetings`

**Файл:** `./backend/migrations/versions/048_meetings.py`
**Эталон:** `./backend/migrations/versions/014_photos.py`
**Зависимости:** на момент работы агента последняя миграция = `047_*`. Если в репозитории появилась более поздняя — взять её номер и сделать `down_revision = "<последняя>"`.

**Содержание:**

```python
revision = "048"
down_revision = "047"   # либо последняя на момент выполнения
```

В `upgrade()`:

1. `op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")`
2. Таблица `meeting_rooms`:
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `name VARCHAR(200) NOT NULL UNIQUE`
   - `link VARCHAR(2048) NULL`
   - `timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow'`
   - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
   - `sort_order INTEGER NOT NULL DEFAULT 0`
   - `created_at`, `updated_at` (TIMESTAMPTZ, default `NOW()`)
   - индексы: `idx_meeting_rooms_active`, `idx_meeting_rooms_sort`
3. Таблица `meeting_bookings`:
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `title VARCHAR(500) NOT NULL`
   - `organizer_name VARCHAR(255) NOT NULL`
   - `creator_id UUID NULL` → FK `users.id ON DELETE SET NULL`
   - `description TEXT NULL`
   - `start_time TIMESTAMPTZ NOT NULL`
   - `end_time TIMESTAMPTZ NOT NULL`
   - `invited_users JSONB NOT NULL DEFAULT '[]'::jsonb`
   - `series_id UUID NULL`
   - `recurrence_rule TEXT NULL`
   - `update_count INTEGER NOT NULL DEFAULT 0`
   - `created_at`, `updated_at`
   - `CHECK (end_time > start_time)`
   - индексы: `idx_meeting_bookings_time(start_time, end_time)`, `idx_meeting_bookings_series(series_id)`, `idx_meeting_bookings_creator(creator_id)`
4. Таблица `meeting_booking_rooms` (M2M + конфликт-чек):
   - `booking_id UUID NOT NULL` → FK `meeting_bookings.id ON DELETE CASCADE`
   - `room_id UUID NOT NULL` → FK `meeting_rooms.id ON DELETE RESTRICT`
   - `start_time TIMESTAMPTZ NOT NULL` (денормализация)
   - `end_time TIMESTAMPTZ NOT NULL`
   - `PRIMARY KEY (booking_id, room_id)`
   - `CONSTRAINT booking_rooms_no_overlap EXCLUDE USING gist (room_id WITH =, tstzrange(start_time, end_time, '[)') WITH &&)`
   - индексы: `idx_meeting_booking_rooms_room(room_id)`
5. Таблица `meetings_audit_log`:
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `action VARCHAR(64) NOT NULL`
   - `user_id UUID NULL`, `username VARCHAR(255)`, `user_email VARCHAR(320)`, `user_role VARCHAR(32)`
   - `resource_type VARCHAR(32) NULL`, `resource_id UUID NULL`, `resource_title VARCHAR(500) NULL`
   - `details JSONB NULL`
   - `ip_address INET NULL`, `user_agent TEXT NULL`
   - `timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - индексы: `(timestamp DESC)`, `(action, timestamp DESC)`, `(user_id, timestamp DESC)`

В `downgrade()` — обратное удаление в обратном порядке. `DROP EXTENSION btree_gist` **не делать** (может использоваться другими).

**Приёмка:**
- `cd backend && alembic upgrade head` проходит на чистой БД
- `alembic downgrade -1` проходит и удаляет все 4 таблицы
- В `psql`: `\d+ meeting_booking_rooms` показывает EXCLUDE constraint

#### T-002. SQLAlchemy-модели

**Файл:** `./backend/app/models/meetings.py`
**Эталон:** `./backend/app/models/links.py`, `./backend/app/models/photos.py`

Классы: `MeetingRoom`, `MeetingBooking`, `MeetingBookingRoom`, `MeetingsAuditLog`.

Поля строго соответствуют миграции T-001. Связи:
- `MeetingRoom.bookings: Mapped[list[MeetingBookingRoom]]`
- `MeetingBooking.rooms: Mapped[list[MeetingBookingRoom]]` (back_populates)
- `MeetingBooking.creator: Mapped["User"] | None`

В `./backend/app/models/__init__.py` добавить импорты новых моделей.

**Приёмка:** `python -c "from app.models.meetings import MeetingRoom, MeetingBooking; print('ok')"` из `./backend` отрабатывает без ошибок.

#### T-003. Pydantic-схемы

**Файл:** `./backend/app/schemas/meetings.py`

DTO:

```python
class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    link: str | None = Field(default=None, max_length=2048)
    timezone: str = Field(default="Europe/Moscow", max_length=64)
    sort_order: int = 0

class RoomUpdate(BaseModel):  # все поля Optional
class RoomOut(BaseModel):
    id: UUID; name: str; link: str | None; timezone: str
    is_active: bool; sort_order: int

class InvitedUser(BaseModel):
    user_id: str         # Keycloak user id
    full_name: str
    email: EmailStr

class BookingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    start_time: datetime  # UTC, должно быть >= now-5min
    end_time: datetime
    room_ids: list[UUID] = Field(min_length=1)
    invited_users: list[InvitedUser] = []
    recurrence: RecurrenceRule | None = None  # для серии

    @field_validator("end_time")
    def end_after_start(cls, v, info): ...

class RecurrenceRule(BaseModel):
    freq: Literal["DAILY", "WEEKDAYS", "WEEKLY", "BIWEEKLY", "MONTHLY"]
    until_date: date  # включительно, max start_date + 31 день

class BookingUpdate(BaseModel):  # все поля Optional, кроме apply_to
    apply_to: Literal["this", "series"] = "this"
    title: str | None = None
    # ... остальные поля BookingCreate как Optional

class BookingOut(BaseModel):
    id: UUID; title: str; organizer_name: str
    creator_id: UUID | None; description: str | None
    start_time: datetime; end_time: datetime
    rooms: list[RoomOut]
    invited_users: list[InvitedUser]
    series_id: UUID | None; recurrence_rule: str | None
    update_count: int; created_at: datetime; updated_at: datetime

class BookingDelete(BaseModel):
    apply_to: Literal["this", "series"] = "this"
```

**Валидаторы:**
- `end_time > start_time`
- `start_time` округлено до 5 мин
- `recurrence.until_date <= start_date + 31 day`
- `len(room_ids) == len(set(room_ids))` (без дублей)

**Приёмка:** валидаторы покрываются unit-тестами в `./backend/tests/unit/test_meetings_*.py` (минимум 6 кейсов: ok, конец раньше старта, серия > 31 день, пустой room_ids, дубли room_ids, invalid timezone).

---

### Этап 2 — Backend CRUD комнат

#### T-004. Роутер комнат

**Файл:** `./backend/app/api/meetings/__init__.py` (пустой `__all__`)
**Файл:** `./backend/app/api/meetings/rooms.py`
**Эталон:** `./backend/app/api/links.py`

```python
router = APIRouter(prefix="/meetings/rooms", tags=["meetings"])

@router.get("", response_model=list[RoomOut])
async def list_rooms(user: CurrentUser, db: DbDep,
                     include_inactive: bool = False) -> list[RoomOut]: ...

@router.post("", response_model=RoomOut, status_code=201)
async def create_room(payload: RoomCreate, admin: AdminDep, db: DbDep,
                      request: Request) -> RoomOut: ...

@router.get("/{room_id}", response_model=RoomOut)
async def get_room(room_id: UUID, user: CurrentUser, db: DbDep): ...

@router.put("/{room_id}", response_model=RoomOut)
async def update_room(room_id: UUID, payload: RoomUpdate, admin: AdminDep,
                      db: DbDep, request: Request): ...

@router.delete("/{room_id}", status_code=204)
async def delete_room(room_id: UUID, admin: AdminDep, db: DbDep,
                      request: Request): ...
```

**Бизнес-правила:**
- `list_rooms` — сортировка по `sort_order, name`
- `delete_room` — если есть будущие бронирования (`end_time > now()`), возвращает 409 с сообщением «У комнаты есть будущие бронирования»; иначе soft-delete (`is_active = false`)
- На каждую мутацию — `push_meetings_audit(action=ROOM_CREATED/UPDATED/DELETED, ...)` (см. T-006)
- Валидация `timezone` через `zoneinfo.ZoneInfo(tz)` — иначе 422

**Регистрация роутера:** в `./backend/app/main.py` добавить `app.include_router(meetings_rooms.router, prefix="/api/v1")`.

**Приёмка:** тесты в `./backend/tests/integration/test_meetings_rooms.py`:
- 200 list (user, admin)
- 403 create (user)
- 201 create (admin) + проверка БД
- 422 invalid timezone
- 409 delete с активными бронированиями
- 204 delete без бронирований

#### T-005. SQLAlchemy-сервис `rooms_service`

**Файл:** `./backend/app/services/meetings/__init__.py`
**Файл:** `./backend/app/services/meetings/rooms_service.py`

Функции: `list_active_rooms`, `get_room`, `create_room`, `update_room`, `soft_delete_room`, `has_future_bookings`.

#### T-006. Сервис аудита `meetings_audit`

**Файл:** `./backend/app/services/meetings/audit.py`

```python
async def push_meetings_audit(
    db: AsyncSession, *, action: str, user: User | None, request: Request | None,
    resource_type: str | None = None, resource_id: UUID | None = None,
    resource_title: str | None = None, details: dict | None = None,
) -> None: ...
```

**Список actions** (константы в `./backend/app/services/meetings/audit.py`):
```
ROOM_CREATED, ROOM_UPDATED, ROOM_DELETED
MEETING_CREATED, MEETING_UPDATED, MEETING_DELETED
MEETING_PARTICIPANT_ADDED, MEETING_PARTICIPANT_REMOVED
SERIES_UPDATED, SERIES_DELETED
EMAIL_SENT, EMAIL_FAILED
```

**ARQ cron-задача:** `cleanup_meetings_audit` — каждый час удаляет `WHERE timestamp < NOW() - INTERVAL '7 days'`. Зарегистрировать в `./backend/app/worker/` (эталон — существующие cron-задачи).

**Приёмка:** unit-тест проверяет, что `push_meetings_audit` пишет в БД и что cron-задача удаляет старые записи.

---

### Этап 3 — Backend CRUD бронирований

#### T-007. Сервис `bookings_service` — чтение

**Файл:** `./backend/app/services/meetings/bookings_service.py`

```python
async def list_bookings(
    db: AsyncSession, *,
    date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    room_id: UUID | None = None,
    creator_id: UUID | None = None,   # только для admin-фильтрации
    limit: int = 500, offset: int = 0,
) -> list[MeetingBooking]: ...

async def list_my_bookings(
    db: AsyncSession, *,
    user_id: UUID,
    start_date: date | None = None,
    limit: int = 5,
) -> list[MeetingBooking]: ...

async def get_booking(db: AsyncSession, booking_id: UUID) -> MeetingBooking | None: ...
```

**Поведение `list_bookings`:**
- `date` → диапазон `[date 00:00, date 23:59:59]` в UTC
- Если `date` задана — игнорировать `start_date/end_date`
- Загружать с `selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room)`
- Лимит максимум 500 (как в MRBS)
- Параметр `creator_id` — **только** реальный UUID (никаких магических строк типа `"me"`); используется админкой для фильтрации по автору

**Поведение `list_my_bookings`:**
- Фильтрует `creator_id == user_id`
- По умолчанию `start_date = today` (если не задано)
- Сортировка по `start_time ASC`
- Лимит до 50

#### T-008. Сервис `bookings_service` — создание

```python
class BookingConflict(Exception):
    def __init__(self, conflicts: list[ConflictInfo]): ...

@dataclass
class ConflictInfo:
    room_name: str; booking_title: str; start: datetime; end: datetime

async def create_booking(
    db: AsyncSession, *, payload: BookingCreate, user: User,
) -> MeetingBooking: ...
```

**Алгоритм:**
1. Проверить, что все `room_ids` существуют и `is_active = true` → иначе `NotFound`
2. Открыть транзакцию
3. Вставить `meeting_bookings` (organizer_name = `user.full_name or user.username`, creator_id = `user.id`, invited_users = JSON)
4. Вставить `meeting_booking_rooms` для каждой комнаты (с денормализованными `start_time/end_time`)
5. **Если** `IntegrityError` с constraint `booking_rooms_no_overlap`:
   - откатить транзакцию
   - запросить **детали** пересекающихся встреч (отдельным запросом) и поднять `BookingConflict(conflicts=...)`
6. На уровне роутера ловить `BookingConflict` → 409 с телом `{"code": "BOOKING_CONFLICT", "conflicts": [...]}`

**Транзакционная семантика:** использовать `SERIALIZABLE` для этой транзакции (либо advisory lock на `room_id` перед вставкой) — EXCLUDE constraint всё равно гарантирует целостность, но advisory lock уменьшит число `IntegrityError` под нагрузкой.

#### T-009. Сервис `bookings_service` — обновление и удаление

```python
async def update_booking(
    db: AsyncSession, *, booking_id: UUID, payload: BookingUpdate, user: User,
) -> tuple[MeetingBooking, BookingDiff]: ...

async def delete_booking(
    db: AsyncSession, *, booking_id: UUID, user: User,
) -> MeetingBooking: ...

@dataclass
class BookingDiff:
    added_users: list[InvitedUser]
    removed_users: list[InvitedUser]
    unchanged_users: list[InvitedUser]
    non_participant_changed: bool   # менялись поля кроме invited_users
```

**Права:** `creator_id == user.id` ИЛИ `user.role == "admin"` — иначе 403.

**Алгоритм update:**
1. Загрузить текущий booking; проверить права
2. Подсчитать `BookingDiff` (нужен для notification.service)
3. В транзакции:
   - Если меняются `start_time/end_time/room_ids` → удалить старые `meeting_booking_rooms`, вставить новые → возможен `IntegrityError` → 409
   - Инкрементировать `update_count` (это `SEQUENCE` для iCal)
   - Сохранить `invited_users` как JSON
4. Вернуть `(booking, diff)` для дальнейшего вызова email-сервиса

**Delete:** просто `DELETE` (CASCADE удалит `meeting_booking_rooms`).

#### T-010. Роутер бронирований

**Файл:** `./backend/app/api/meetings/bookings.py`

```python
router = APIRouter(prefix="/meetings/bookings", tags=["meetings"])

GET    ""                  → list_bookings(query: BookingListQuery)
GET    "/my"               → list_my_bookings(start_date, limit)  # CurrentUser
POST   ""                  → create_booking → 201
GET    "/{booking_id}"     → get_booking
PUT    "/{booking_id}"     → update_booking (apply_to=this)
DELETE "/{booking_id}"     → delete_booking (apply_to=this)
```

**Важно:** `/my` объявить **до** `/{booking_id}`, иначе FastAPI смэтчит `my` как `booking_id` и упадёт на UUID-валидации.

**После успешного create/update/delete:**
1. `push_meetings_audit(...)`
2. `await publish_meeting_event(redis, action, booking, room_ids, date)` (T-018)
3. `dispatch_meeting_emails(booking, diff, action)` (T-014) — fire-and-forget через ARQ

**Регистрация в `main.py`.**

**Тесты `./backend/tests/integration/test_meetings_bookings.py`** (минимум 15 кейсов):
- list по дате
- create ok
- create конфликт → 409 с деталями
- create несуществующая комната → 404
- create end <= start → 422
- update ok
- update другим юзером → 403
- update админом чужой → 200
- update со сменой времени → инкремент update_count
- delete своим → 204
- delete админом → 204
- delete чужим → 403
- список не возвращает > 500

---

### Этап 4 — Серии (T-011..T-013)

#### T-011. Генерация экземпляров серии

**Файл:** `./backend/app/services/meetings/recurrence.py`

```python
def expand_recurrence(
    start: datetime, end: datetime, rule: RecurrenceRule, tz: str,
) -> list[tuple[datetime, datetime]]: ...
```

Использует `dateutil.rrule`. Маппинг:
- `DAILY` → `rrulestr("FREQ=DAILY;UNTIL=…")`
- `WEEKDAYS` → `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`
- `WEEKLY` → `FREQ=WEEKLY;BYDAY=<weekday of start>`
- `BIWEEKLY` → `FREQ=WEEKLY;INTERVAL=2;BYDAY=…`
- `MONTHLY` → `FREQ=MONTHLY;BYMONTHDAY=<day>`

Возвращает список `(start_time, end_time)` экземпляров. Все в UTC.

**Лимит:** если результат > 31 экземпляр — ValidationError.

#### T-012. Создание серии

В `bookings_service.create_booking`, если `payload.recurrence` задано:
1. Сгенерировать через `expand_recurrence`
2. Создать `series_id = uuid4()`
3. Транзакция: вставить все экземпляры с одинаковым `series_id`
4. Первая встреча хранит `recurrence_rule = str(rrule)`
5. При IntegrityError на любом → откат **всей** серии + 409 с указанием конфликтного экземпляра

#### T-013. Series endpoints

**Файл:** `./backend/app/api/meetings/series.py`

```python
GET    "/meetings/series/{series_id}/count" → {"count": N}
PUT    "/meetings/series/{series_id}"      → update_series(payload: SeriesUpdate)
DELETE "/meetings/series/{series_id}"      → delete_series
```

**SeriesUpdate:** только поля, применимые ко всей серии (`title`, `description`, `invited_users`; **не** `start_time/end_time/room_ids`, так как они индивидуальны).

**Apply-to логика в `BookingUpdate.apply_to`:**
- `"this"` → классический update; если booking был в серии, **отвязываем** его: `series_id = NULL`, `recurrence_rule = NULL`
- `"series"` → роутер `bookings.py` делегирует в `series.py` `update_series(booking.series_id, ...)`

Аналогично для `BookingDelete.apply_to`.

**Тесты:** create серии, count, update series, delete series, отвязка одной встречи из серии при `apply_to=this`.

---

### Этап 5 — Email + iCal (T-014..T-016)

#### T-014. iCal builder

**Файл:** `./backend/app/services/meetings/ical_builder.py`
**Библиотека:** `icalendar` (добавить в `./backend/pyproject.toml`)

```python
def build_ical(
    booking: MeetingBooking,
    method: Literal["REQUEST", "CANCEL"],
    company_domain: str,
) -> bytes: ...
```

Атрибуты:
- `PRODID:-//Portal//Meetings//RU`
- `METHOD:{method}`
- `VEVENT`:
  - `UID:{booking.id}@{company_domain}`
  - `SEQUENCE:{booking.update_count}`
  - `DTSTAMP:{now UTC}`
  - `DTSTART;TZID={room.timezone}:{start_time в TZ комнаты}` (берётся **первая** комната)
  - `DTEND;TZID=...`
  - `SUMMARY:{title}`
  - `DESCRIPTION:{description, fallback пустая строка}`
  - `LOCATION:{ '; '.join(room.name for room in rooms) }`
  - `URL:{first room.link if exists}`
  - `ORGANIZER;CN={organizer_name}:mailto:{from_email}`
  - `ATTENDEE;CN={user.full_name};PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{user.email}` для каждого приглашённого
  - Если `booking.recurrence_rule` → `RRULE:{rule}`

**Тесты:** проверка распарса через `icalendar.Calendar.from_ical(...)` для всех `method` и наличия RRULE.

#### T-015. Email-сервис и diff-логика

**Файл:** `./backend/app/services/meetings/notifications.py`

```python
async def dispatch_meeting_emails(
    arq_pool: ArqRedis, *,
    booking: MeetingBooking, action: Literal["created", "updated", "cancelled"],
    diff: BookingDiff | None = None,
) -> None: ...
```

Алгоритм:
- `action == "created"` → REQUEST всем `booking.invited_users`
- `action == "cancelled"` → CANCEL всем `booking.invited_users`
- `action == "updated"`:
  - Для `diff.added` → REQUEST
  - Для `diff.removed` → CANCEL (на момент удаления участник уже отсутствует в `booking.invited_users`, поэтому хранится в diff)
  - Для `diff.unchanged` → REQUEST с `SEQUENCE = update_count` **только если** `diff.non_participant_changed`

Каждый получатель → строка в таблице `email_outbox` (`kind='meeting'`,
payload с base64-iCal). Отправку выполняет общий cron-диспетчер
`process_email_outbox` (см. `./docs/email.md`).

#### T-016. Outbox-запись + диспетчер

**Producer:** `./backend/app/services/meetings/notifications.py::dispatch_meeting_emails`
открывает свою `AsyncSession`, по каждому участнику и `room.email` вызывает
`enqueue_outbox_email(..., kind=KIND_MEETING, payload={"method": ..., "ical_b64": ...})`.

**Dispatcher:** `./backend/app/worker/tasks/email_outbox.py::process_email_outbox`
(cron каждые 10 с) забирает PENDING-строки, для `KIND_MEETING` строит
`multipart/mixed` + `Content-Class: urn:content-classes:calendarmessage` +
inline `text/calendar; method={REQUEST|CANCEL}; charset=UTF-8` и шлёт через
`aiosmtplib`. Ретраи / классификация ошибок / DLQ — см. `./docs/email.md`.

**Legacy ARQ-задача `send_meeting_email`** (`./backend/app/worker/tasks/meetings/email.py`)
сохранена как fallback и тоже использует общий `email_utils`
(`max_tries=6`, `job_timeout=60`, fail-fast на permanent ошибках).
Аудит-события `EMAIL_SENT` / `EMAIL_FAILED` пишутся ею; основная
видимость доставки — в админке «Очередь Email».

Зарегистрировать в `WorkerSettings.functions` в `./backend/app/worker/main.py` (эталон — существующие задачи).

**Тесты:** mock SMTP (smtplib.SMTP в pytest-mock), проверить корректность multipart структуры и наличие iCal-вложения.

---

### Этап 6 — Поиск участников + SSE (T-017, T-018)

#### T-017. Поиск участников

**Файл:** `./backend/app/api/meetings/participants.py`

```python
@router.get("/meetings/participants/search", response_model=list[InvitedUser])
async def search_participants(
    q: str = Query(min_length=3, max_length=100),
    limit: int = Query(default=20, le=50),
    user: CurrentUser,
) -> list[InvitedUser]: ...
```

Делегирует в `./backend/app/services/keycloak/directory.py` (готовый `search_users(q, max_results)`).

**Важно:** `search_users()` возвращает `list[dict[str, Any]]` — сырой Keycloak JSON, а не доменные объекты. Псевдокод вида `u.full_name` / `u.id` / `u.email` — это нотация, в реальности маппинг такой:

```python
results = await search_users(q, max_results=limit)
out: list[InvitedUser] = []
for u in results:
    email = u.get("email")
    if not email:
        continue   # отфильтровываем без email
    full_name = f"{u.get('firstName', '')} {u.get('lastName', '')}".strip() or u.get("username", "")
    out.append(InvitedUser(user_id=u["id"], full_name=full_name, email=email))
return out
```

**Тесты:** mock keycloak directory, проверка `min_length=3` → 422 при q="ab", фильтрация пользователей без email, fallback `firstName+lastName → username`, корректный проброс `u["id"]`.

#### T-018. SSE-публикация события

**Файл:** `./backend/app/services/meetings/realtime.py`

```python
MEETINGS_STREAM_KEY = "notifications:meetings"  # один глобальный поток для всех

async def publish_meeting_event(
    redis: Redis, *, action: Literal["created", "updated", "deleted"],
    booking_id: UUID, room_ids: list[UUID], date_str: str,
) -> None:
    await redis.xadd(MEETINGS_STREAM_KEY, {
        "type": "meeting_changed",
        "action": action,
        "booking_id": str(booking_id),
        "room_ids": json.dumps([str(r) for r in room_ids]),
        "date": date_str,
    }, maxlen=10000, approximate=True)
```

**Интеграция в SSE-генератор `./backend/app/api/notifications.py`:**
Генератор должен читать **два потока параллельно** через `asyncio.gather`:
- `notifications:{user_id}` — личный поток (уже существует)
- `notifications:meetings` — общий глобальный поток (новый)

Оба читаются через `xread` с `BLOCK`; результаты обоих `xread`-задач мержатся в один SSE-поток клиенту. События из `notifications:meetings` отдаются клиенту как `event: meeting_changed` с payload-полями из `xadd`. Эта модель — стандарт для чатов: «личные сообщения + сообщения канала по одному соединению».

**Тесты:**
- integration-тест с testcontainers Redis: `publish_meeting_event` → читаем через `xread` → проверяем поля
- SSE end-to-end тест: два клиента, один подписан → `publish_meeting_event` → оба получают `event: meeting_changed`, а личные уведомления продолжают приходить только в `notifications:{user_id}`.

---

### Этап 7 — Feature flag (T-019)

#### T-019. `MeetingsModuleSettings`

**Файл:** `./backend/app/core/modules_config.py` — добавить класс:

```python
class MeetingsModuleSettings(BaseModel):
    enabled: bool = False
    calendar_start_hour: int = Field(default=8, ge=0, le=23)
    calendar_end_hour: int = Field(default=19, ge=1, le=24)
    max_recurrence_horizon_days: int = Field(default=31, ge=1, le=365)
    min_search_chars: int = Field(default=3, ge=1, le=10)
```

В `AllModuleSettings` добавить поле `meetings: MeetingsModuleSettings = Field(default_factory=MeetingsModuleSettings)`.

В `./backend/app/api/modules.py` добавить `MeetingsModuleIn`, `MeetingsModuleOut`, и обновить `AllModuleSettingsOut` + endpoint `PUT /modules/meetings` (admin).

**Guard:** в `./backend/app/api/meetings/__init__.py` создан dependency `meetings_enabled_guard` и подключён через `MeetingsGuard = Depends(meetings_enabled_guard)` ко всем роутерам модуля: `rooms.py`, `bookings.py`, `series.py`, `participants.py`.

```python
async def meetings_enabled_guard(redis: RedisDep) -> None:
    settings = await load_modules_shared(redis)
    if not settings.meetings.enabled:
        raise HTTPException(404, "Meetings module disabled")
```

**Тесты:** при `enabled=false` все `/meetings/*` возвращают 404; при `enabled=true` — работают.

---

### Этап 8 — Frontend (T-020..T-027)

#### T-020. API-клиент

**Файл:** `./frontend/src/api/meetings.ts`
**Эталон:** `./frontend/src/api/links.ts`

Функции (используют общий `httpClient`):
```ts
listRooms(includeInactive?: boolean): Promise<Room[]>
createRoom, updateRoom, deleteRoom
listBookings(params: BookingListParams): Promise<Booking[]>
listMyBookings(params: { start_date?: string; limit?: number }): Promise<Booking[]>
getBooking(id), createBooking, updateBooking, deleteBooking
getSeriesCount(seriesId), updateSeries, deleteSeries
searchParticipants(q: string): Promise<InvitedUser[]>
```

Типы (Room, Booking, InvitedUser, RecurrenceFreq) — в `./frontend/src/api/meetings.ts` (отдельного `meetings.types.ts` нет).

#### T-021. TanStack Query hooks

**Файл:** `./frontend/src/queries/meetings.ts`

```ts
useRoomsQuery()
useBookingsByDateQuery(date: Ref<string>, options?)   // staleTime 30s
useBookingMutation()
useSeriesMutation()
useParticipantSearchQuery(q: Ref<string>, options?)   // enabled = q.value.length >= 3
```

#### T-022. SSE-листенер

Реализован внутри общего стора `./frontend/src/stores/notifications.ts`: при `meeting_changed` диспатчится window-событие `'meetings:changed'`. Подписчики (`MeetingsPage.vue`, `MeetingsWidget.vue`) ловят его через `window.addEventListener` и инвалидируют префикс `queryKeys.meetings.all` (точечная инвалидация по дате не делается — общий префикс охватывает всё). Отдельный composable `useMeetingsRealtime` не создавался.

#### T-023. Pinia-стор настроек

> Реализация: отдельный Pinia-стор `stores/meetings.ts` не заведён — состояние (`selectedDate`, индекс мобильной комнаты, окно времени) живёт внутри `MeetingsPage.vue`/`RoomGrid.vue` и берётся из `modulesStore.meetingsSettings` (`calendar_start_hour`, `calendar_end_hour`).

#### T-024. Компонент `RoomGrid.vue` (день)

**Файл:** `./frontend/src/components/meetings/RoomGrid.vue`

Структура:
- CSS Grid: первый столбец — время (по 30 мин), затем по столбцу на каждую активную комнату
- Шапка столбца: `<a v-if="room.link" :href="room.link" target="_blank">{{ room.name }}</a>` иначе просто текст; если `room.timezone != browserTz` → `(GMT+N)` рядом
- Слоты пустые — кликабельны → `emit('slot-click', { roomId, time })`
- События — абсолютно позиционированы внутри столбца комнаты, высота = (end - start) / 30min * slotHeight
- Красная горизонтальная линия = текущее время (обновляется раз в минуту через `useNow` composable)

**Props:**
```ts
defineProps<{
  rooms: Room[]
  bookings: Booking[]
  date: string
  startHour: number
  endHour: number
}>()
```

**События:** `@slot-click`, `@booking-click`.

#### T-025. `MeetingFormDialog.vue`

**Файл:** `./frontend/src/components/meetings/MeetingFormDialog.vue`

Поля:
- Название (text, required)
- Описание (textarea)
- Дата (date picker, default = текущая)
- Время начала / окончания (time picker, шаг 5 мин)
- Комнаты (multi-select из `useRoomsQuery`)
- Участники (`ParticipantPicker.vue`)
- Повтор (`RecurrenceEditor.vue`, опционально)

При редактировании в режиме `series_id != null`:
- При сохранении показывается диалог Naive UI: «Применить к этой встрече» / «Применить ко всей серии» (`apply_to`)
- При удалении — аналогично

#### T-026. `ParticipantPicker.vue`

**Файл:** `./frontend/src/components/meetings/ParticipantPicker.vue`

Naive UI `<n-select multiple filterable remote>`:
- `remote-method` → дебаунс 300ms, вызывает `searchParticipants(q)` если `q.length >= 3`
- Опция: `{label: full_name + ' <' + email + '>', value: user_id}`
- **Без аватарок**

#### T-027. `RecurrenceEditor.vue`

**Файл:** `./frontend/src/components/meetings/RecurrenceEditor.vue`

Radio:
- Не повторять (default)
- Каждый день
- Каждый рабочий день
- Каждую неделю в этот день
- Каждые 2 недели
- Каждый месяц

+ `n-date-picker` «Повторять до» (max = start_date + 31 день, валидация на фронте).

#### T-028. Страница `MeetingsPage.vue`

**Файл:** `./frontend/src/pages/meetings/MeetingsPage.vue`

Структура:
- Шапка: кнопка «Сегодня», стрелки даты, отображение даты (как в скриншоте)
- Десктоп и мобильный — единый `<RoomGrid />`; мобильный режим реализован тем же компонентом через `useBreakpoints().isMobile` + CSS `scroll-snap-type: x mandatory` (по комнате на экран). Отдельного `RoomGridMobile.vue` нет.
- Использует `useBookingsByDateQuery` + window-событие `'meetings:changed'` (из `stores/notifications.ts`) для инвалидации

#### T-029. Мобильный режим RoomGrid

Реализован внутри `RoomGrid.vue`: на ширине ≤767px включается `scroll-snap-type: x mandatory`, столбец комнаты занимает 100% ширины, под сеткой отрисовывается индикатор «N из M» с подсветкой активной комнаты (обновляется по scroll).

#### T-030. Админка комнат

**Файл:** `./frontend/src/pages/admin/MeetingRoomsAdminPage.vue`

Таблица с `n-data-table`: name, timezone, link, sort_order, is_active, действия (edit/delete). Диалог create/edit.

#### T-031. Виджет «Мои ближайшие встречи»

**Файл:** `./frontend/src/components/widgets/MeetingsWidget.vue` + интеграция в `./frontend/src/pages/HomePage.vue`.

Запрос: `listMyBookings({ start_date: today, limit: 5 })` → бьёт в `GET /meetings/bookings/my` (отдельный эндпоинт по образцу `/feedback/my`). Магической строки `creator_id=me` **нет**; админский фильтр `creator_id` принимает только реальный UUID.

#### T-032. Роутинг и меню

- `./frontend/src/router.ts`: добавить `MEETINGS: '/meetings'` и `MEETINGS_ROOMS: '/admin/meeting-rooms'`
- `./frontend/src/components/AppLayout.vue`: пункт меню «Переговорные» (только если модуль `meetings.enabled`)
- i18n ключи `meetings.*` в `./frontend/src/i18n/ru.json` и `en.json`

---

### Этап 9 — Тесты и финальная сборка

#### T-033. Playwright e2e

**Файлы:** unit — `./frontend/tests/unit/meetings-api.spec.ts`, `./frontend/tests/unit/queries-meetings.spec.ts`. Полноценного e2e `meetings.spec.ts` пока нет.

Сценарии:
1. **Логин → переход на /meetings** → сетка отрисована
2. **Создание бронирования**: клик на слот, заполнение формы, submit → появилось в сетке
3. **Конфликт**: попытка создать на занятом слоте → toast «Комната уже занята»
4. **Изменение времени** → запись смещается, проверка SSE-обновления во второй вкладке
5. **Серия**: создание серии на 5 дней, edit одной встречи → диалог → «только эта»
6. **Удаление серии** → диалог → «вся серия»
7. **Поиск участника**: ввод 2 символов → результата нет; 3 символа → есть
8. **Mobile**: viewport 375x800, horizontal swipe → следующая комната

#### T-034. k6 нагрузочный

**Файл:** `./load/meetings_load.js`

Сценарий: 50 VU, 1 минута:
- 60% GET /meetings/bookings?date=today
- 30% GET /meetings/rooms
- 10% POST /meetings/bookings (со случайным временем)

Критерий: p95 < 500ms, ошибок (5xx) < 0.1%.

#### T-035. Документация

Создать/обновить (как существующие в `./docs/`):
- `./docs/meetings.md` — пользовательский гайд (1 страница)
- Обновить `./docs/api-contracts.md` — добавить раздел Meetings
- Обновить `./docs/db-schema.md` — добавить таблицы meetings
- Обновить `./docs/roles-matrix.md` — права на `/meetings/*`

#### T-036. Финальная проверка

1. `cd backend && alembic upgrade head && pytest -x` — зелёное
2. `cd frontend && npm test && npm run test:e2e` — зелёное
3. `ruff check backend && npm --prefix frontend run lint` — без warnings
4. `mypy backend/app/services/meetings backend/app/api/meetings` — без ошибок
5. `docker-compose -f docker-compose.dev.yml up --build` → ручная проверка по чек-листу:
   - [ ] Меню «Переговорные» отображается
   - [ ] Можно создать комнату
   - [ ] Можно создать встречу
   - [ ] Конфликт даёт правильный 409
   - [ ] Email приходит (mailhog в dev)
   - [ ] iCal открывается в Outlook (тестировать вручную)
   - [ ] SSE: два браузера — изменение в одном видно в другом за < 2 сек
   - [ ] Mobile-вью на 375px — swipe работает
   - [ ] Feature flag в `/modules` → выключение скрывает меню

---

### Сводная карта зависимостей задач

```
T-001 (миграция)
  └─ T-002 (модели)
       ├─ T-003 (схемы)
       │    └─ T-004 (роутер rooms) ── T-005 (rooms_service)
       │                              └─ T-006 (audit)
       │
       ├─ T-007 (list bookings)
       ├─ T-008 (create) ── T-010 (роутер bookings)
       ├─ T-009 (update/delete) ──┘
       │
       ├─ T-011 (recurrence) ── T-012 (create series) ── T-013 (series endpoints)
       │
       ├─ T-014 (ical) ── T-015 (dispatch) ── T-016 (worker)
       ├─ T-017 (participants)
       ├─ T-018 (SSE)
       └─ T-019 (feature flag)

Backend готов → Frontend:
T-020 (api) ── T-021 (queries) ── T-022 (sse) ── T-023 (store)
            ├─ T-024 (RoomGrid)
            ├─ T-025 (FormDialog) ── T-026 (Picker) ── T-027 (Recurrence)
            ├─ T-028 (Page) ── T-029 (Mobile)
            ├─ T-030 (RoomsAdmin)
            ├─ T-031 (HomeWidget)
            └─ T-032 (router + menu)

Финал:
T-033 (e2e) ── T-034 (k6) ── T-035 (docs) ── T-036 (final check)
```

### Чек-лист «определение готовности» (DoD) каждой задачи

- [ ] Код написан строго в указанных файлах, без правок за пределами
- [ ] Тесты добавлены и проходят (`pytest -x` или `vitest`)
- [ ] `ruff check` / `eslint` без warnings
- [ ] Типы корректны (`mypy` / `tsc --noEmit`)
- [ ] Названия actions/событий совпадают со списком в T-006
- [ ] Git-коммит формата `feat(meetings): T-NNN …`
- [ ] Обновлены docstring/JSDoc в публичных функциях

---

> Такой уровень детализации обеспечивает: каждая задача = атомарный коммит, каждый шаг проверяем независимо, агент не может «уйти не туда» (явные границы файлов), есть критерии приёмки для авто-валидации.

---

## 10. Текущее состояние реализации

| Требование | Статус |
|---|---|
| БД: таблицы `meeting_rooms`, `meeting_bookings`, `meeting_booking_rooms`, EXCLUDE GIST | ✅ Готово (`048_meetings.py`) |
| `meeting_rooms.email` — поле для iCal-рассылки на ящик комнаты | ✅ Готово (`049_meeting_rooms_add_email.py`) |
| CRUD комнат (admin) | ✅ Готово |
| CRUD бронирований + конфликт-чек | ✅ Готово |
| Серии: create / update / delete | ✅ Готово |
| Email-уведомления iCal с diff-логикой (REQUEST/CANCEL/SEQUENCE) | ✅ Готово |
| Рассылка на `room.email` при любом событии бронирования | ✅ Готово |
| ARQ-задача `send_meeting_email` (legacy fallback) | ✅ Готово (`worker/tasks/meetings/email.py`) |
| Persistent outbox + админ-UI (`email_outbox` + `process_email_outbox`) | ✅ Готово (см. `./docs/email.md`) |
| Cleanup аудита `cleanup_meetings_audit` | ❌ Удалено (миграция `050_drop_meetings_audit_log.py`, BLK-01); retention теперь у общего `audit_log` |
| SSE in-app уведомления `meetings:changed` | ✅ Готово |
| Polling-fallback 60 с в `useMeetingBookingsQuery` / `useMyMeetingBookingsQuery` (MAJ-F01) | ✅ Готово |
| Виджет «Мои ближайшие» подписан на `meetings:changed` (MAJ-F02) | ✅ Готово |
| Аудит-лог MEETING_CREATED/UPDATED/DELETED, SERIES_UPDATED/DELETED | ✅ Готово |
| Аудит вызывается ПОСЛЕ `db.commit()` (MAJ-B05) | ✅ Готово |
| `apply_to=series` без `series_id` → 400 (MAJ-B04) | ✅ Готово |
| `invited_users` ограничен (`max_length=100`, MAJ-B07) | ✅ Готово |
| `min_search_chars` читается из `MeetingsModuleSettings` (MAJ-B08) | ✅ Готово |
| `update_count` (SEQUENCE) растёт только при изменении не-участниковых полей (BLK-04) | ✅ Готово (`non_participant_changed`) |
| Отвязка инстанса серии → CANCEL(old series UID) + REQUEST(new UID) (MAJ-B06) | ✅ Готово (`BookingDiff.old_series_uid` + `uid_override` в `ical_builder`) |
| EXCLUDE GIST конфликт обернут в SAVEPOINT (BLK-03) | ✅ Готово (`db.begin_nested()`) |
| iCal содержит полноценную секцию `VTIMEZONE` (BLK-05) | ✅ Готово (`ical_builder._build_vtimezone`) |
| Bulk-load бронирований в `series_service` (N+1, MAJ-B02) | ✅ Готово (`_load_bookings_bulk`) |
| Пересборка RRULE при изменении `start_time` серии (MAJ-B03) | ✅ Готово |
| TZ-aware фильтрация `list_bookings` по дате | ✅ Готово (параметр `tz`, портальный часовой пояс) |
| iCal использует TZ портала (не первой комнаты) | ✅ Готово |
| Фронт: `RoomGrid.vue`, `MeetingFormDialog.vue`, `MeetingSeriesDialog.vue` | ✅ Готово |
| Фронт: сетка/карточки рендерятся в TZ комнаты (MAJ-F07) | ✅ Готово (`minutesInTz`, `shortTz`) |
| Фронт: a11y — слоты `RoomGrid` доступны с клавиатуры (MAJ-F09) | ✅ Готово (`role="grid"`, tabindex, Enter/Space) |
| Фронт: `ParticipantPicker` на `n-select multiple filterable remote` (MAJ-F05) | ✅ Готово |
| Фронт: `mapMeetingsError` + структурный маркер `[START_TIME_IN_PAST]` (MAJ-F06) | ✅ Готово |
| Фронт: локаль-aware форматирование времени (MAJ-F03/F04, `dateLocale`) | ✅ Готово |
| Фронт: `useMeetingRoomsQuery` гейтится `enabled: modulesEnabled` (MAJ-F11) | ✅ Готово |
| Фронт: `RecurrenceEditor` собирает даты в локальной TZ (MAJ-F12) | ✅ Готово |
| Фронт: удаление через `useDeleteBookingMutation` + диалог «эта/вся» (BLK-06, MAJ-F08) | ✅ Готово |
| Фронт: PUT/DELETE серии через `useUpdateSeriesMutation` / `useDeleteSeriesMutation` (BLK-08) | ✅ Готово |
| Фронт: пагинация/фильтр/сортировка в админке комнат (MAJ-F10) | ✅ Готово |
| Фронт: валидация `end_time > start_time` на клиенте | ✅ Готово |
| Фронт: мобильный вид через CSS media query в `RoomGrid.vue` + snap-scroll + индикатор «N из M» (MIN-F09) | ✅ Готово |
| Виджет «Мои ближайшие встречи» на главной | ✅ Готово (`MeetingsWidget.vue`) |
| Поиск участников (`/meetings/participants/search`) | ✅ Готово |
| i18n: ключ `meetings.form.endTimeAfterStart` (BLK-07) | ✅ Готово (`ru.json` + `en.json`, проверка через `frontend/scripts/check-i18n.js`) |
| Регрессионные тесты TST-01..TST-06, TST-08 | ✅ Готово (`backend/tests/unit/test_meetings_*.py`, `backend/tests/integration/test_meetings_*.py`, `frontend/scripts/check-i18n.js`) |
| `POST /meetings/bookings/batch` (до 52 шт.) | ❌ Не реализован (Бэклог P1) |
| Frontend e2e тесты (Playwright, TST-07) | ❌ Не реализованы (Бэклог E2) |
| k6 нагрузочный скрипт | ❌ Не реализован (Бэклог E3) |
