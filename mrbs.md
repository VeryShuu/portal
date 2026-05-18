# Внедрение MRBS (бронирование переговорных) в Portal

> Анализ репозитория [VeryShuu/mrbs](https://github.com/VeryShuu/mrbs) и план интеграции его функционала в наш корпоративный портал.

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
│       ├── rooms.py            # CRUD комнат (admin)
│       ├── bookings.py         # CRUD бронирований
│       ├── series.py           # Series-level операции
│       ├── batch.py            # POST /bookings/batch
│       └── participants.py     # Поиск участников (прокси к Keycloak)
├── services/
│   └── meetings/
│       ├── __init__.py
│       ├── booking_service.py  # Порт MRBS booking.service.ts
│       ├── conflict.py         # Обработка IntegrityError → 409
│       ├── notifications.py    # iCal + diff-логика участников
│       └── ical_builder.py     # RFC 5545: METHOD, SEQUENCE, ATTENDEE
└── worker/
    └── tasks_meetings.py       # ARQ-задачи отправки писем
migrations/versions/
└── 018_meetings.py             # rooms, bookings, booking_rooms + EXCLUDE
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
GET    /meetings/bookings?room_id=&date=&start_date=&end_date=&limit=&offset=
POST   /meetings/bookings
GET    /meetings/bookings/{id}
PUT    /meetings/bookings/{id}                  (creator | admin)
DELETE /meetings/bookings/{id}                  (creator | admin)
POST   /meetings/bookings/batch                 (до 52 шт.)

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
  - `UID` = `{booking.id}@{COMPANY_DOMAIN}`
- Diff-логика на изменение состава (повторяем MRBS):
  - `added` → REQUEST новым
  - `removed` → CANCEL удалённым
  - `unchanged` → REQUEST с `SEQUENCE++` **только если** менялись неучастниковые поля
- `room.email` (общий ящик переговорной) — отдельный получатель

### 4.5. Frontend (Vue 3 + Naive UI + TanStack Query)

```
frontend/src/
├── pages/meetings/
│   ├── MeetingsPage.vue              # Календарь (день/неделя)
│   ├── MeetingsMobileListPage.vue    # Список (≤768px)
│   ├── MeetingFormDialog.vue         # Создание/редактирование
│   └── MeetingSeriesDialog.vue       # Редактирование серии
├── pages/admin/
│   └── MeetingRoomsAdminPage.vue     # CRUD комнат
├── components/meetings/
│   ├── RoomGrid.vue                  # Сетка: столбцы = комнаты, строки = время
│   ├── TimeSlot.vue                  # Клик/drag для создания
│   ├── BookingCard.vue
│   ├── ParticipantPicker.vue         # Autocomplete по Keycloak
│   └── RecurrenceEditor.vue          # daily / weekly / weekdays
├── queries/
│   └── meetings.ts                   # TanStack Query hooks (poll 60s)
├── api/
│   └── meetings.ts                   # Клиент к /api/v1/meetings/*
└── stores/
    └── meetings.ts                   # Настройки отображения (grid/list, окно времени)
```

### 4.6. Интеграция в портал

- **Меню** (`./frontend/src/components/AppLayout.vue`): пункт «Переговорные» между «Files» и «Links»
- **Роутер** (`./frontend/src/router.ts`):
  ```ts
  MEETINGS: '/meetings',
  MEETINGS_ROOMS: '/admin/meeting-rooms',
  ```
- **Виджет на главной** (`./frontend/src/pages/HomePage.vue`): «Мои ближайшие встречи» (5 шт., GET `/meetings/bookings?creator_id=me&start_date=today&limit=5`)
- **Системные настройки** (`system_settings`):
  - `meetings.calendar_start_hour` (default 8)
  - `meetings.calendar_end_hour` (default 19)
  - `meetings.max_batch_size` (default 52)
  - `meetings.timezone` — берётся из глобальной настройки портала
  - `meetings.company_name` — берётся из `branding.title`
- **i18n** (`./frontend/src/i18n/`): ru/en для всех новых строк
- **Уведомления**: при изменении встречи участники получают in-app toast через существующий SSE-стрим (`./backend/app/api/notifications.py`)
- **Аудит**: события `MEETING_CREATED`, `MEETING_UPDATED`, `MEETING_DELETED`, `ROOM_CREATED`, `ROOM_UPDATED`, `ROOM_DELETED`, `SERIES_UPDATED`, `SERIES_DELETED`

---

## 5. План работ

| Этап | Содержание | Оценка |
|---|---|---|
| **1. БД и модели** | Миграция `018_meetings.py` (rooms, bookings, booking_rooms, EXCLUDE constraint, `btree_gist`), SQLAlchemy-модели, Pydantic-схемы | 1–2 дня |
| **2. Backend CRUD** | `rooms.py`, `bookings.py` с фильтрами; `booking_service.py`; обработка `IntegrityError` → 409; интеграция с audit-логом; unit-тесты с testcontainers | 3–4 дня |
| **3. Серии и batch** | `series.py`, `batch.py`, повторение daily/weekly/weekdays | 2 дня |
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
| Письмо на ящик комнаты | **Не нужно** (у комнаты email-а нет) |

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
| Горизонт | **Максимум 1 месяц** вперёд |
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
- В iCal — `DTSTART;TZID=…` с правильной таймзоной комнаты

### 7.9. Атрибуты комнат

В v1 у комнаты только:
- `name` — название
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

**Поле `room.email` из MRBS исключено** (у комнаты не должно быть email согласно решению 7.4).

### 8.2. SSE для real-time (вместо polling MRBS)

В отличие от MRBS, у нас real-time обязателен. Используем существующий SSE-стрим (`./backend/app/api/notifications.py`):

- Новый тип события: `meeting_changed` с payload `{action, booking_id, room_ids, date}`
- При create/update/delete бронирования → backend публикует событие в Redis-стрим `notifications:meetings`
- Фронт на странице `/meetings` подписан на этот стрим → инвалидирует TanStack Query кэш для затронутой даты
- Polling-fallback каждые 60 сек оставляем для случаев, когда SSE недоступен

### 8.3. Серии: Outlook-style диалог

При сохранении изменения встречи, у которой `series_id != null`:

1. Если пользователь поменял что-либо — фронт показывает диалог: «Применить только к этой встрече / Применить ко всей серии».
2. «Только к этой» → `PUT /meetings/bookings/{id}` + бэкенд автоматически отвязывает от серии (`series_id = null`, `recurrence_rule = null`).
3. «Ко всей серии» → `PUT /meetings/series/{series_id}`.

При удалении — аналогично: «Удалить только эту / Удалить всю серию».

### 8.4. Multi-TZ конкретика

- Сетка календаря рендерится **в TZ комнаты** для каждого столбца отдельно (час «09:00» в столбце Москвы и в столбце Самары физически попадает в разные строки, потому что сетка строится по UTC, а слоты — общие 30-минутные интервалы)
- Решение для v1: сетка строится в **TZ пользователя** (берём из браузера); рядом с названиями комнат показываем `(GMT+3)` / `(GMT+4)`, если TZ комнаты отличается от TZ пользователя
- Это совпадает с поведением Outlook (показывает всё в локальной TZ пользователя)

### 8.5. Feature flag

В `./backend/app/core/modules_config.py` (рядом с `NextcloudModuleSettings`, `PhotosModuleSettings`):

```python
class MeetingsModuleSettings(BaseModel):
    enabled: bool = False
    calendar_start_hour: int = 8
    calendar_end_hour: int = 19
    audit_retention_days: int = 7
    max_recurrence_horizon_days: int = 31
    min_search_chars: int = 3
```

Эндпоинт `GET /modules` уже возвращает все модули → фронт скрывает пункт меню «Переговорные», если `meetings.enabled == false`.

### 8.6. Ротация аудита (7 дней)

Существующий механизм партиций (`audit_log`) — партиции по месяцам. Для retention 7 дней дополнительно вводим **отдельную таблицу `meetings_audit_log`** с TTL-cleanup через ARQ cron-задачу (раз в час удаляет записи старше 7 дней). Не смешиваем с глобальным `audit_log`, чтобы не ломать его retention.

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
| Drag-to-create | ❌ Не делаем |
| Вид «неделя/месяц» | ❌ Не делаем |
| Email на ящик комнаты | ❌ Не делаем |
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
| **1. БД и модели** | Миграция (rooms с `timezone`/`link`/`sort_order`, bookings с `organizer_name`/`recurrence_rule`, booking_rooms с денормализацией и EXCLUDE GIST), `btree_gist`, отдельная `meetings_audit_log` | 1–2 дня |
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

> Увеличение на 4–6 дней относительно первоначальной оценки связано с: multi-TZ (комнаты в разных городах), SSE real-time, диалог «эта/серия», отдельная audit-таблица с 7-дневным retention.

### 9.3. Обновлённые риски

| Риск | Митигация |
|---|---|
| Multi-TZ: путаница пользователя при просмотре комнаты другого офиса | Показывать `(GMT+N)` рядом с названием комнаты, если TZ отличается от браузера; всё в iCal с правильным `TZID` |
| SSE-соединение рвётся за nginx/reverse proxy | Использовать существующий механизм портала (уже работает для in-app уведомлений); polling fallback 60 сек |
| Серия 31 экземпляр × N комнат → много iCal-писем сразу | ARQ rate-limit на отправку (например, не более 50 писем/сек); группировка серии в одно письмо с `RRULE` (стандарт iCal) |
| Outlook путается с `RRULE` при импорте серии | Покрыть e2e-тестом на реальном Outlook (опционально — Apple Calendar) перед релизом |
| Удаление учётки организатора ломает фильтр «мои встречи» | `creator_id` остаётся `NULL`, `organizer_name` сохранён как текст; фильтр «мои» по `creator_id = current_user.id` |
| 7-дневный retention аудита может быть мало для расследований | Зафиксировать как осознанное решение заказчика; при необходимости легко увеличить через `MeetingsModuleSettings.audit_retention_days` |

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
