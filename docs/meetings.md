# Модуль «Переговорные» (Meetings)

> **Когда читать:** бронирование комнат, серии, конфликт-чек, iCal-уведомления.
> **Ключевой код:** `./backend/app/api/meetings/`, `./backend/app/services/meetings/`, `./backend/app/models/meetings.py`, `./frontend/src/pages/meetings/MeetingsPage.vue`.
> **ADR:** —. **См. также:** `./docs/email.md`, `./docs/roles-matrix.md`.

> Документация модуля бронирования переговорных комнат портала. Реализация выполнена по мотивам [VeryShuu/mrbs](https://github.com/VeryShuu/mrbs) (доменная логика и UX), инфраструктурные слои — стек портала (FastAPI + SQLAlchemy + PostgreSQL + Vue 3 + Naive UI). Историческое название «MRBS» сохранено в разделах ниже как ссылка на первоисточник идей.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/meetings/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/meetings/MeetingsPage.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/meetings/email.py`) / cron `process_email_outbox` (`./backend/app/worker/tasks/email_outbox.py`) |
| Хранилище | PostgreSQL (таблицы `meeting_rooms`, `meeting_bookings`, `meeting_booking_rooms`) |
| Префикс API | `/api/v1` (зарегистрирован в `./backend/app/api/__init__.py`) |
| ACL-кэш | — |

### Контекст первоисточника (MRBS)
MRBS — самостоятельное веб-приложение для бронирования переговорных комнат.
**Стек MRBS:**
- Next.js 16 (App Router) + TypeScript
- Prisma ORM + **SQLite**
- NextAuth.js 4 (Credentials + Keycloak)
- Tailwind CSS + Headless UI
- Zod, Vitest, Playwright
- Docker (multi-stage standalone)

Технологически он **несовместим** с нашим стеком (FastAPI + SQLAlchemy + PostgreSQL + Vue 3 + Naive UI), поэтому переиспользовать код напрямую нельзя — портируем **доменную логику и UX**, а инфраструктурные слои берём из портала.

### Что переиспользуем из портала
Перед началом работ важно: **большую часть инфраструктуры MRBS у нас уже есть**.

| Подсистема MRBS | Аналог в портале | Действие |
|---|---|---|
| NextAuth (Credentials + Keycloak) | `./backend/app/api/auth/` (OIDC + local) | **Переиспользовать** |
| `KeycloakUser` синхронизация | `./backend/app/services/keycloak/directory.py` | **Переиспользовать** |
| `EmailSettings` (SMTP) | Системные настройки + Postfix | **Переиспользовать** |
| `AuditLog` | Партиционированный `audit_log` (`./backend/migrations/versions/013_audit_log.py`) | **Переиспользовать** |
| `AuthSettings` | `./backend/app/api/system_settings/` | **Переиспользовать** |
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

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/meetings/` | API-роутеры для комнат, бронирований, серий и поиска участников |
| Service | `./backend/app/services/meetings/` | Бизнес-логика, bookings_service, rooms_service, series_service, recurrence, ical_builder, notifications, realtime, audit |
| Model | `./backend/app/models/meetings.py` | SQLAlchemy-модели: `MeetingRoom`, `MeetingBooking`, `MeetingBookingRoom` |
| Schema | `./backend/app/schemas/meetings.py` | Pydantic-схемы (DTO) ввода-вывода |
| Frontend | `./frontend/src/pages/meetings/` | Страница дневного календаря переговорных |

### Детализированная структура файлов

```
backend/app/
├── models/
│   └── meetings.py             # MeetingRoom, MeetingBooking, MeetingBookingRoom
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
│       ├── bookings_service/   # Пакет: создание/обновление/удаление/поиск бронирований
│       │   ├── __init__.py
│       │   ├── _crud.py
│       │   ├── _helpers.py
│       │   ├── _queries.py
│       │   └── _types.py       # BookingConflict, BookingDiff
│       ├── rooms_service.py    # CRUD переговорных комнат
│       ├── series_service.py   # Операции над сериями
│       ├── recurrence.py       # expand_recurrence / build_rrule_string / parse_rrule_string
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

```
frontend/src/
├── pages/meetings/
│   ├── MeetingsPage.vue              # Календарь (день)
│   └── composables/
│       └── useMeetingsQuery.ts       # Логика навигации по датам + подписка на SSE
├── pages/admin/
│   └── MeetingRoomsAdminPage.vue     # CRUD комнат
├── components/meetings/
│   ├── RoomGrid.vue                  # Сетка: столбцы = комнаты, строки = время.
│   │                                  # Мобильный режим встроен в RoomGrid через
│   │                                  # @media + scroll-snap (одна комната на экран)
│   ├── MeetingsCalendar.vue          # Обёртка вокруг RoomGrid
│   ├── MeetingsFilters.vue           # Шапка: кнопка «Сегодня», стрелки, дата
│   ├── MeetingsList.vue              # Детальный просмотр / удаление бронирования
│   ├── MeetingFormDialog.vue         # Создание/редактирование + диалог «эта/вся серия»
│   ├── BookingCard.vue
│   ├── ParticipantPicker.vue         # n-select multiple filterable remote
│   ├── RecurrenceEditor.vue          # daily / weekly / weekdays / biweekly / monthly
│   └── meeting-form/                 # Под-компоненты формы (поля, участники, повтор)
├── stores/
│   └── notifications.ts              # SSE-листенер 'meeting_changed' → window-event 'meetings:changed'
├── queries/
│   └── meetings.ts                   # TanStack Query hooks (refetchInterval 60s — fallback к SSE)
└── api/
    └── meetings.ts                   # Клиент к /api/v1/meetings/*
```

---

## 3. Модель данных

Реализована в `./backend/app/models/meetings.py` со следующими отличиями от Prisma-схемы MRBS, обусловленными нашим стеком:

| MRBS (SQLite/Prisma) | Portal (PostgreSQL/SQLAlchemy) |
|---|---|
| `id String @default(cuid())` | `id UUID DEFAULT gen_random_uuid()` |
| `invitedUsers String?` (TEXT JSON) | `invited_users JSONB` |
| `creatorId String?` (без FK) | `creator_id UUID REFERENCES users(id) ON DELETE SET NULL` |
| `seriesId String?` | `series_id UUID` |
| In-process `bookingMutex` | **EXCLUDE GIST constraint** на БД + **SAVEPOINT (`begin_nested()`)** |

### Схема таблиц

```python
# ./backend/app/models/meetings.py
class MeetingRoom(Base):
    __tablename__ = "meeting_rooms"
    # Ограничения: уникальное имя, тип только 'physical' или 'virtual'
    id: UUID                          # PK, gen_random_uuid()
    name: str                         # unique, max_length=200
    kind: str                         # 'physical' | 'virtual', default 'physical'
    email: str | None                 # email ответственного за комнату (max_length=320)
    link: str | None                  # постоянная ссылка на онлайн-встречу (max_length=2048)
    timezone: str                     # IANA, default 'Europe/Moscow' (max_length=64)
    is_active: bool                   # default True
    sort_order: int                   # default 0, для порядка столбцов в календаре
    created_at, updated_at

class MeetingBooking(Base):
    __tablename__ = "meeting_bookings"
    id: UUID                          # PK, gen_random_uuid()
    title: str                        # max_length=500
    organizer_name: str               # текстовый снимок, max_length=255
    creator_id: UUID | None           # FK → users.id ON DELETE SET NULL
    description: str | None           # TEXT
    start_time: datetime              # TIMESTAMPTZ (UTC)
    end_time: datetime                # TIMESTAMPTZ (UTC)
    invited_users: JSONB              # [{user_id, full_name, email}]
    series_id: UUID | None            # UUID серии
    recurrence_rule: str | None       # RFC 5545 RRULE для серии (хранится на первой встрече)
    update_count: int                 # SEQUENCE для iCal, инкремент при не-участниковых изменениях
    created_at, updated_at

class MeetingBookingRoom(Base):
    __tablename__ = "meeting_booking_rooms"
    booking_id: UUID                  # PK, FK → meeting_bookings.id ON DELETE CASCADE
    room_id: UUID                     # PK, FK → meeting_rooms.id ON DELETE RESTRICT
    start_time: TIMESTAMPTZ           # денормализация для EXCLUDE constraint
    end_time:   TIMESTAMPTZ
```

**Защита от пересечений на уровне БД:**
```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE meeting_booking_rooms
  ADD CONSTRAINT booking_rooms_no_overlap
  EXCLUDE USING gist (
    room_id WITH =,
    tstzrange(start_time, end_time, '[)') WITH &&
  );
```
Для атомарной обработки конфликтов при бронировании под нагрузкой, транзакции создания/обновления оборачиваются в SAVEPOINT с использованием `db.begin_nested()`. При возникновении `IntegrityError` на ограничении `booking_rooms_no_overlap`, производится откат savepoint и запрашиваются детали конфликтующих встреч.

**Индексы:**
- `meeting_bookings(start_time, end_time)`
- `meeting_bookings(series_id)`
- `meeting_bookings(creator_id)`
- GIST на `tstzrange(start_time, end_time)` для фильтрации конфликтов.

---

## 4. Модель прав (ACL)

Реализация матрицы доступа в соответствии с согласованными бизнес-решениями (см. также `./docs/roles-matrix.md`):

| Операция | Минимальная роль | Ограничения и условия |
|---|---|---|
| Просмотр сетки и деталей бронирований | Любой сотрудник | Приватного режима в v1 нет. Все авторизованные видят все встречи (тема, время, организатор, участники) |
| Создание бронирования | Любой сотрудник | Любой авторизованный сотрудник портала может забронировать свободную активную комнату |
| Редактирование / Удаление встречи | Владелец / Admin | Править или удалять бронирование может только его создатель (`creator_id == user.id`) либо администратор портала |
| Создание / Редактирование / Удаление комнат | Admin | Управление справочником переговорных комнат доступно только администраторам. Роль «офис-менеджер» не требуется |

---

## 5. REST API

Эндпоинты зарегистрированы в `./backend/app/api/__init__.py` с префиксом `/api/v1` (а не в `./backend/app/main.py`). Все эндпоинты защищены через зависимость `MeetingsGuard` (`meetings_enabled_guard`), возвращающую 404 при отключённом модуле.

### Сводная таблица эндпоинтов

| Метод | Путь | Описание | Права |
|---|---|---|---|
| **GET** | `/meetings/rooms` | Получить список комнат | Любой сотрудник |
| **POST** | `/meetings/rooms` | Создать комнату | Администратор |
| **GET** | `/meetings/rooms/{id}` | Детали комнаты | Любой сотрудник |
| **PUT** | `/meetings/rooms/{id}` | Редактировать комнату | Администратор |
| **DELETE** | `/meetings/rooms/{id}` | Удалить комнату (soft-delete) | Администратор |
| **GET** | `/meetings/bookings` | Список бронирований за период | Любой сотрудник |
| **GET** | `/meetings/bookings/my` | Ближайшие встречи текущего пользователя | Любой сотрудник |
| **POST** | `/meetings/bookings` | Создать встречу (или серию) | Любой сотрудник |
| **GET** | `/meetings/bookings/{id}` | Детали встречи | Любой сотрудник |
| **PUT** | `/meetings/bookings/{id}` | Редактировать встречу (`apply_to` = "this"\|"series") | Создатель / Admin |
| **DELETE** | `/meetings/bookings/{id}` | Отменить встречу (`apply_to` = "this"\|"series") | Создатель / Admin |
| **GET** | `/meetings/series/{series_id}/count` | Число будущих встреч в серии | Любой сотрудник |
| **PUT** | `/meetings/series/{series_id}` | Обновить всю серию | Создатель / Admin |
| **DELETE** | `/meetings/series/{series_id}` | Удалить всю серию | Создатель / Admin |
| **GET** | `/meetings/participants/search` | Поиск участников по Keycloak Directory | Любой сотрудник |

---

## 6. Специфика модуля и бизнес-логика

### 6.1. Email-уведомления и iCal-логика

Модуль отправляет полноценные iCal-приглашения (RFC 5545) в формате `text/calendar; method=REQUEST/CANCEL`, которые автоматически обрабатываются Outlook/Apple Calendar/Thunderbird.

- **Служба отправки:** `dispatch_meeting_emails` в `./backend/app/services/meetings/notifications.py` записывает сообщения в таблицу `email_outbox` (с `kind='meeting'`). Обработку и непосредственную отправку выполняет cron-процесс `process_email_outbox` (`./backend/app/worker/tasks/email_outbox.py`). В качестве legacy fallback сохранена ARQ-задача `send_meeting_email` (`./backend/app/worker/tasks/meetings/email.py`).
- **Служба iCal:** `ical_builder.build_ical` генерирует байты iCal-файла.
  - Поле `UID` формируется как:
    - Одиночная встреча: `{booking.id}@{COMPANY_DOMAIN}`
    - Встреча из серии: `series-{series_id}@{COMPANY_DOMAIN}`
  - Поле `SEQUENCE` принимает значение `booking.update_count`. Инкрементируется только при изменении не-участниковых полей встречи (время, комната, описание, название).
  - Поля времени `DTSTART`/`DTEND` передаются в часовом поясе портала (`system_settings.timezone`), для максимальной совместимости с Outlook/Apple Calendar генерируется секция `VTIMEZONE`.
- **Diff-логика (повторяет поведение MRBS):**
  - Добавленные участники (`added`) → получают `METHOD:REQUEST`
  - Удалённые участники (`removed`) → получают `METHOD:CANCEL`
  - Неизменённые участники (`unchanged`) → получают `METHOD:REQUEST` с инкрементированным `SEQUENCE` **только если** изменились не-участниковые параметры.
- **Оповещение переговорной (`room.email`):** Если у комнаты заполнен `email`, данный адрес включается во все iCal-рассылки (как участник с типом `CUTYPE=RESOURCE`) при любых операциях (создание, изменение, удаление).
- **Отвязка инстанса от серии:** При изменении одной встречи из серии (`apply_to="this"`), встреча отвязывается (`series_id = NULL`). Почтовый сервис отсылает `METHOD:CANCEL` со старым `series-...` UID, и следом `METHOD:REQUEST` с новым `{booking.id}` UID всем участникам.

### 6.2. Серии и повторения встречи
- Поддерживаемые типы повторений: **Каждый день**, **Каждый рабочий день (пн-пт)**, **Каждую неделю**, **Каждые 2 недели**, **Каждый месяц** (только в диапазоне дат начала 1-28 для безопасного смещения).
- Для генерации экземпляров используется библиотека `dateutil.rrule`.
- **Горизонт повторений:** Максимальное число будущих встреч в серии ограничено константой и валидируется на уровне схемы (`max_recurrence_horizon_days` по умолчанию составляет 31 день вперёд).
- **Диалог Outlook-style:** При редактировании или удалении встречи из серии, пользователю предоставляется выбор через интерфейс: «Применить только к этой встрече» (`apply_to="this"`) или «Применить ко всей серии» (`apply_to="series"`).

### 6.3. Real-time обновление (SSE)
- Каждое изменение в сетке бронирований публикуется бэкендом в глобальный Redis-стрим `notifications:meetings` с типом `meeting_changed` и payload `{action, booking_id, room_ids, date}`.
- SSE-генератор в `./backend/app/api/notifications.py` параллельно слушает личный поток уведомлений пользователя `notifications:{user_id}` и глобальный поток `notifications:meetings`.
- Фронтенд подписывается на событие `meeting_changed` в `stores/notifications.ts`, генерирует событие окна `'meetings:changed'`, а composable `useMeetingsQuery.ts` ловит его и инвалидирует кэш TanStack Query.
- Дополнительно настроен 60-секундный polling-fallback (`refetchInterval: 60_000`) для компенсации обрывов веб-сокетов или SSE.

### 6.4. Часовые пояса (Multi-TZ)
- Каждой комнате сопоставлен свой часовой пояс (`room.timezone`).
- В базе данных время встреч сохраняется строго в UTC (`TIMESTAMPTZ`).
- На фронтенде сетка рендерится **в часовом поясе комнаты** (`BookingCard.minutesInTz` + `RoomGrid.sortedRooms`). Если таймзона комнаты отличается от таймзоны браузера пользователя, в шапке столбца отображается маркер смещения `(GMT±N)`.

### 6.5. Настройки модуля и Feature Flag
Настройки хранятся в `./data/settings/modules.json` и управляются через класс:
```python
# ./backend/app/core/modules_config.py
class MeetingsModuleSettings(BaseModel):
    enabled: bool = False
    calendar_start_hour: int = Field(default=8, ge=0, le=23)
    calendar_end_hour: int = Field(default=19, ge=1, le=24)
    max_recurrence_horizon_days: int = Field(default=31, ge=1, le=365)
    min_search_chars: int = Field(default=3, ge=1, le=10)
```
- **Важно:** Лимит количества приглашённых участников (`max_invitees`) **не вынесен** в настройки `MeetingsModuleSettings`, а захардкожен в Pydantic схеме `./backend/app/schemas/meetings.py` как `max_length=100` на поле `invited_users`.
- При выключенном модуле пункт «Переговорные» скрывается из меню, а роутер-гард перенаправляет пользователя на главную.

---

## 7. Риски и митигация

| Риск | Описание | Способ митигации |
|---|---|---|
| **Race condition при конкурентном бронировании** | Попытка забронировать одну и ту же комнату на один интервал времени из разных воркеров | **EXCLUDE GIST constraint** на уровне СУБД (атомарно). Транзакция защищена savepoint-оболочкой, возвращая чистый 409 статус вместо падения бэкенда. |
| **Рассинхронизация обновлений в Outlook** | Неверное отображение или дублирование встреч у участников при изменениях | Строгое соблюдение спецификации RFC 5545: инкремент `SEQUENCE` только при не-участниковых изменениях, использование стабильного UUID, высылка CANCEL + REQUEST при разделении серий. |
| **Обрывы SSE соединений** | Пользователи не видят изменения, внесённые коллегами в реальном времени | Интегрирован **polling-fallback на 60 секунд** (`refetchInterval`) в хуках TanStack Query. |
| **Удаление учётной записи организатора** | Нарушение целостности связей встреч в БД | Поле `creator_id` сбрасывается в `NULL` (`ON DELETE SET NULL`), а текстовое имя организатора сохраняется в `organizer_name` как исторический снимок. |
| **Почтовый спам при батч-операциях** | Нагрузка на SMTP сервер при создании длинных серий с множеством участников | Использование таблицы `email_outbox` в качестве буфера (persistent outbox). Письма отправляются асинхронно порциями. |

---

## 8. Первоисточник MRBS и согласованные решения

Ниже приведены требования, зафиксированные на бизнес-уровне при проектировании v1 модуля:

### Доступ и Роли
- Бронировать переговорные может абсолютно любой авторизованный сотрудник.
- Все пользователи имеют равные права на просмотр деталей любых встреч (приватность отсутствует).
- Удалить или изменить бронирование может только его создатель или администратор портала.
- Изменять перечень доступных комнат (создавать, архивировать) могут только администраторы.

### Участники
- Список приглашаемых участников запрашивается исключительно из Keycloak Directory (внешние адреса не поддерживаются).
- Поиск участников ведётся по имени, фамилии и email. Отображается ФИО + email. Аватарки отсутствуют.
- Минимальное число символов для поиска берётся из `min_search_chars` (по умолчанию 3).

### Календарь и сетка дня
- Доступен только вид дня (без сетки недели или месяца).
- Переговорные выводятся столбцами, строки соответствуют 30-минутным слотам. Рабочий день настраивается (`08:00 - 19:00`).
- Ссылка на виртуальную переговорную (Zoom/Teams) отображается как кликабельное имя комнаты в шапке столбца.
- Текущее время отображается красной горизонтальной чертой.
- Бронирование совершается по клику на пустой слот (drag-to-create в v1 отсутствует).
- На мобильных устройствах календарь адаптируется в горизонтальный скролл с привязкой по одной комнате на экран (snap-scroll) и индикатором «N из M».

---

## 9. Детальная спецификация для ИИ-агента

Разработка модуля велась поатомно на основе следующих технических спецификаций задач:

### T-001. Миграция Alembic `048_meetings`
**Файл:** `./backend/migrations/versions/048_meetings.py`  
В `upgrade()`:
1. `op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")`
2. Таблица `meeting_rooms`: `id UUID PK DEFAULT gen_random_uuid()`, `name VARCHAR(200) NOT NULL UNIQUE`, `link VARCHAR(2048) NULL`, `timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow'`, `is_active BOOLEAN NOT NULL DEFAULT TRUE`, `sort_order INTEGER NOT NULL DEFAULT 0`, `created_at`/`updated_at`.
3. Таблица `meeting_bookings`: `id UUID PK DEFAULT gen_random_uuid()`, `title VARCHAR(500) NOT NULL`, `organizer_name VARCHAR(255) NOT NULL`, `creator_id UUID NULL` (FK `users.id ON DELETE SET NULL`), `description TEXT NULL`, `start_time TIMESTAMPTZ NOT NULL`, `end_time TIMESTAMPTZ NOT NULL`, `invited_users JSONB NOT NULL DEFAULT '[]'::jsonb`, `series_id UUID NULL`, `recurrence_rule TEXT NULL`, `update_count INTEGER NOT NULL DEFAULT 0`, `created_at`/`updated_at`.
4. Таблица `meeting_booking_rooms`: `booking_id UUID`, `room_id UUID`, `start_time TIMESTAMPTZ`, `end_time TIMESTAMPTZ`. PK (`booking_id`, `room_id`). EXCLUDE GIST constraint `booking_rooms_no_overlap`.

### T-002. SQLAlchemy-модели
**Файл:** `./backend/app/models/meetings.py`  
Классы: `MeetingRoom`, `MeetingBooking`, `MeetingBookingRoom`. Связи: `MeetingRoom.bookings`, `MeetingBooking.rooms` (cascade delete-orphan), `MeetingBookingRoom.booking`, `MeetingBookingRoom.room`.

### T-003. Pydantic-схемы
**Файл:** `./backend/app/schemas/meetings.py`  
Классы: `RoomCreate`, `RoomUpdate`, `RoomOut`, `InvitedUser` (`user_id`, `full_name`, `email`), `RecurrenceRule` (`freq` DAILY/WEEKDAYS/WEEKLY/BIWEEKLY/MONTHLY, `until_date`), `BookingCreate` (`invited_users` ограничен `max_length=100`), `BookingUpdate`, `BookingDelete`, `BookingOut`, `SeriesUpdate`, `SeriesCountOut`. Валидация таймзоны по IANA справочнику. Валидация `end_time > start_time`.

### T-004. Роутер переговорных комнат
**Файл:** `./backend/app/api/meetings/rooms.py`  
Маршруты: `GET /meetings/rooms`, `POST /meetings/rooms` (admin), `GET /meetings/rooms/{room_id}`, `PUT /meetings/rooms/{room_id}` (admin), `DELETE /meetings/rooms/{room_id}` (admin, soft-delete).

### T-005. SQLAlchemy-сервис `rooms_service`
**Файл:** `./backend/app/services/meetings/rooms_service.py`  
Функции: `list_active_rooms`, `get_room`, `create_room`, `update_room`, `soft_delete_room`, `has_future_bookings`.

### T-006. Сервис аудита `meetings_audit`
**Файл:** `./backend/app/services/meetings/audit.py`  
Запись событий в общую партиционированную таблицу `audit_log`.

### T-007. Сервис `bookings_service` — чтение
**Файл:** `./backend/app/services/meetings/bookings_service/_queries.py`  
Функции: `list_bookings` (ограничение до 500 записей), `list_my_bookings`, `get_booking`.

### T-008. Сервис `bookings_service` — создание
**Файл:** `./backend/app/services/meetings/bookings_service/_crud.py`  
Функция `create_booking`. Валидация активности комнат. Обработка `IntegrityError` с savepoint `db.begin_nested()`.

### T-009. Сервис `bookings_service` — обновление и удаление
**Файл:** `./backend/app/services/meetings/bookings_service/_crud.py`  
Функции `update_booking` (подсчёт diff изменений, инкремент `update_count`), `delete_booking`.

### T-010. Роутер бронирований
**Файл:** `./backend/app/api/meetings/bookings.py`  
Маршруты: `GET /meetings/bookings`, `GET /meetings/bookings/my`, `POST /meetings/bookings`, `GET /meetings/bookings/{booking_id}`, `PUT /meetings/bookings/{booking_id}`, `DELETE /meetings/bookings/{booking_id}`.

### T-011. Генерация экземпляров серии
**Файл:** `./backend/app/services/meetings/recurrence.py`  
Функция `expand_recurrence`. Использование `dateutil.rrule` для разворачивания серии до 31 дня.

### T-012. Создание серии
Реализовано в `series_service.py`. Пакетная генерация и вставка инстансов с общим `series_id`.

### T-013. Series endpoints
**Файл:** `./backend/app/api/meetings/series.py`  
Маршруты: `GET /meetings/series/{series_id}/count`, `PUT /meetings/series/{series_id}`, `DELETE /meetings/series/{series_id}`.

### T-014. iCal builder
**Файл:** `./backend/app/services/meetings/ical_builder.py`  
Генерация байтов iCal через библиотеку `icalendar` с поддержкой `VTIMEZONE` и корректным выставлением `SEQUENCE`/`UID`.

### T-015. Email-сервис и diff-логика
**Файл:** `./backend/app/services/meetings/notifications.py`  
Функция `dispatch_meeting_emails`. Сравнение участников (added/removed/unchanged) и генерация соответствующих iCal REQUEST/CANCEL уведомлений.

### T-016. Outbox-запись + диспетчер
Запись в `email_outbox` с `kind='meeting'` и обработка в кроне `./backend/app/worker/tasks/email_outbox.py` с сборкой MIME-сообщения `multipart/mixed`.

### T-017. Поиск участников
**Файл:** `./backend/app/api/meetings/participants.py`  
Маршрут `GET /meetings/participants/search`. Валидация `min_search_chars` и проксирование запроса в Keycloak Admin Directory.

### T-018. SSE-публикация события
**Файл:** `./backend/app/services/meetings/realtime.py`  
Публикация событий в Redis канал `notifications:meetings` и поддержка параллельного чтения в `./backend/app/api/notifications.py`.

### T-019. `MeetingsModuleSettings`
**Файл:** `./backend/app/core/modules_config.py`  
Реализация Pydantic настроек модуля, интеграция в bootstrap сборщик и подключение `MeetingsGuard`.

### T-020. API-клиент фронтенда
**Файл:** `./frontend/src/api/meetings.ts`  
Реализация axios-запросов к бэкенду.

### T-021. TanStack Query hooks
**Файл:** `./frontend/src/queries/meetings.ts`  
Реализация хуков `useMeetingBookingsQuery`, `useMyMeetingBookingsQuery`, мутаций и инвалидации кэша.

### T-022. SSE-листенер
Интегрирован в `./frontend/src/stores/notifications.ts` для диспатча события `'meetings:changed'`.

### T-023. Pinia-стор настроек
Настройки календаря берутся из `modulesStore.meetingsSettings`.

### T-024. Компонент `RoomGrid.vue`
**Файл:** `./frontend/src/components/meetings/RoomGrid.vue`  
Рендеринг сетки по 30 минут, абсолютное позиционирование встреч с учётом TZ переговорной.

### T-025. `MeetingFormDialog.vue`
**Файл:** `./frontend/src/components/meetings/MeetingFormDialog.vue`  
Диалог создания и редактирования встречи со сбором участников и выбором режима применения изменений серии.

### T-026. `ParticipantPicker.vue`
**Файл:** `./frontend/src/components/meetings/ParticipantPicker.vue`  
Компонент автокомплита участников на базе Keycloak API.

### T-027. `RecurrenceEditor.vue`
**Файл:** `./frontend/src/components/meetings/RecurrenceEditor.vue`  
Выбор периодичности встреч с капой горизонта до 31 дня.

### T-028. Страница `MeetingsPage.vue`
**Файл:** `./frontend/src/pages/meetings/MeetingsPage.vue`  
Точка входа календаря, подписка на SSE события.

### T-029. Мобильный режим RoomGrid
Реализация `scroll-snap-type: x mandatory` в `./frontend/src/components/meetings/RoomGrid.vue` на экранах менее 768px.

### T-030. Админка комнат
**Файл:** `./frontend/src/pages/admin/MeetingRoomsAdminPage.vue`  
CRUD-таблица комнат для администраторов.

### T-031. Виджет «Мои ближайшие встречи»
**Файл:** `./frontend/src/components/widgets/MeetingsWidget.vue`  
Запрос к `/meetings/bookings/my` и размещение виджета на главной.

### T-032. Роутинг и меню
Добавление путей в `./frontend/src/router.ts` и пункта меню в `./frontend/src/components/AppLayout.vue`.

---

## 10. План и история разработки

| Этап | Содержание | Оценка |
|---|---|---|
| **1. БД и модели** | Миграции, SQLAlchemy-модели, btree_gist | 1–2 дня |
| **2. Backend CRUD** | Базовый CRUD комнат и бронирований, аудит | 3–4 дня |
| **3. Серии и повторы** | Логика recurrence, rrule, серии бронирований | 2 дня |
| **4. Почта и iCal** | Построение iCal файлов, diff-уведомления | 2–3 дня |
| **5. SSE обновления** | Pub/Sub механизм real-time обновлений сетки | 1 день |
| **6. Сетка календаря** | Компонент RoomGrid, поддержка Multi-TZ | 3–4 дня |
| **7. Формы и Picker** | Модальные формы, Keycloak поиск участников | 2–3 дня |
| **8. Mobile-вид** | Адаптивная CSS Grid верстка и snap-scroll | 1–2 дня |
| **9. Feature flag** | Настройки модуля, guard интеграция | 1 день |
| **10. Тесты и e2e** | Unit-тесты, Playwright e2e сценарии, k6 | 2–3 дня |

---

## 11. Текущее состояние реализации

| Требование / Функция | Статус | Комментарий |
|---|---|---|
| БД: таблицы комнат, бронирований, M2M, EXCLUDE GIST | ✅ Готово | См. `./backend/migrations/versions/048_meetings.py` |
| Поле `meeting_rooms.email` для iCal-уведомлений комнаты | ✅ Готово | См. `./backend/migrations/versions/049_meeting_rooms_add_email.py` |
| CRUD комнат (интерфейс администратора) | ✅ Готово | |
| CRUD бронирований + проверка на наложение | ✅ Готово | |
| Серии встреч: создание, удаление, редактирование | ✅ Готово | |
| iCal уведомления + diff-логика состава участников | ✅ Готово | |
| Рассылка iCal на `room.email` | ✅ Готово | |
| ARQ fallback задача `send_meeting_email` | ✅ Готово | См. `./backend/app/worker/tasks/meetings/email.py` |
| Email outbox очереди и обработчик крона | ✅ Готово | См. `./backend/app/worker/tasks/email_outbox.py` |
| SSE уведомления в реальном времени | ✅ Готово | Канал `notifications:meetings` |
| Polling-fallback (60 секунд) на клиенте | ✅ Готово | |
| Лог аудита в общей таблице `audit_log` | ✅ Готово | Отдельная таблица удалена миграцией `050` |
| Ограничение `invited_users` (max_length=100) | ✅ Готово | Настроено в Pydantic схеме |
| Настройки `min_search_chars` из конфига модуля | ✅ Готово | |
| Отвязка встречи от серии (CANCEL + REQUEST) | ✅ Готово | |
| EXCLUDE GIST обернут в SAVEPOINT (`begin_nested()`) | ✅ Готово | Предотвращает поломку сессии транзакции |
| Сетка фронтенда рендерится в TZ комнаты | ✅ Готово | |
| Поддержка a11y в сетке RoomGrid | ✅ Готово | `role="grid"`, tabindex, клавиатурная навигация |
| Локализация ru/en интерфейса | ✅ Готово | Ключи i18n |
| Регрессионные тесты backend/frontend | ✅ Готово | Проходят без ошибок |
| Пакетное бронирование `batch` до 52 шт. | ❌ В бэклоге | Бэклог P1 |
| Frontend e2e тесты (Playwright) | ❌ В бэклоге | Бэклог E2 |
| k6 нагрузочное тестирование | ❌ В бэклоге | Бэклог E3 |

---

## Безопасность

- **Валидация входящих данных:** Все строковые поля имеют строгие ограничения на длину (название встречи до 500 симв, описание неограничено, название комнаты до 200 симв) на уровне Pydantic-схем.
- **Предотвращение инъекций и переполнений:** Использование SQLAlchemy ORM типизации и UUID идентификаторов.
- **Разграничение прав доступа:** Проверки `user.role == "admin"` на мутации комнат и `creator_id == user.id` на изменение бронирований внедрены на уровне роутеров и сервисов.
- **Защита от DOS-атак на Keycloak:** Введено принудительное ограничение минимальной длины строки поиска участников `min_search_chars` (по умолчанию 3), валидируемое до обращения к Keycloak Directory API.

---

## События аудита

События аудита записываются в единую партиционированную таблицу `audit_log` портала (события модуля `meetings_audit_log` были удалены миграцией `./backend/migrations/versions/050_drop_meetings_audit_log.py`):

| Код события | Тип ресурса | Инициатор | Метаданные (details) |
|---|---|---|---|
| `ROOM_CREATED` | room | Admin | Идентификатор, название комнаты |
| `ROOM_UPDATED` | room | Admin | Идентификатор, изменённые поля |
| `ROOM_DELETED` | room | Admin | Идентификатор |
| `MEETING_CREATED` | booking | Сотрудник | Идентификатор, тема встречи, комната |
| `MEETING_UPDATED` | booking | Создатель / Admin | Идентификатор, изменённые поля (комната, время и т.д.) |
| `MEETING_DELETED` | booking | Создатель / Admin | Идентификатор встречи |
| `MEETING_SERIES_CREATED`| series | Сотрудник | ID серии, количество сгенерированных встреч |
| `SERIES_UPDATED` | series | Создатель / Admin | ID серии, количество затронутых встреч |
| `SERIES_DELETED` | series | Создатель / Admin | ID серии, количество удалённых встреч |

---

## Тесты

Для проверки корректности реализованы следующие тестовые наборы:

| Категория | Путь к тесту | Объект тестирования |
|---|---|---|
| **Unit (Backend)** | `./backend/tests/unit/test_meetings_ical.py` | Генерация iCal файлов (REQUEST, CANCEL) |
| **Unit (Backend)** | `./backend/tests/unit/test_meetings_recurrence.py` | Разворачивание серий по rrule |
| **Unit (Backend)** | `./backend/tests/unit/test_meetings_schemas.py` | Валидация DTO схем и таймзон |
| **Integration** | `./backend/tests/integration/test_meetings_rooms.py` | API управления комнатами |
| **Integration** | `./backend/tests/integration/test_meetings_bookings.py` | API бронирований и проверка конфликтов |
| **Integration** | `./backend/tests/integration/test_meetings_series.py` | API управления сериями встреч |
| **Frontend Unit** | `./frontend/tests/unit/meetings-page.spec.ts` | Рендеринг страницы календаря |
| **Frontend Unit** | `./frontend/tests/unit/meeting-form-dialog.spec.ts` | Валидация форм создания встреч |

---

## Связанные документы

- **Интеграция почты:** `./docs/email.md`
- **Матрица ролей и доступов:** `./docs/roles-matrix.md`
- **Архитектура базы данных:** `./docs/db-schema.md`
- **Описание REST контрактов:** `./docs/api-contracts.md`
