# Модуль «Уведомления»

> **Когда читать:** При реализации in-app уведомлений, SSE-стрима реалтайма, логики отметки прочтения и интеграции новых продюсеров событий (новости, база знаний, обратная связь, файлы).
> **Ключевой код:** `./backend/app/api/notifications.py`, `./backend/app/services/notifications.py`, `./backend/app/services/notifications_sse.py`, `./backend/app/worker/tasks/notifications.py`, `./frontend/src/api/notifications.ts`, `./frontend/src/stores/notifications.ts`, `./frontend/src/queries/notifications.ts`.
> **ADR:** — **См. также:** `./docs/db-schema.md`, `./docs/api-contracts.md`, `./docs/roles-matrix.md`.

> Модуль доставляет персональные in-app уведомления через PostgreSQL + Redis Streams. API слой предоставляет CRUD над записями и SSE-эндпойнт (`/api/v1/notifications/stream`), который мультиплексирует три Redis-потока: персональный (`notifications:{user_id}`), совещания (`notifications:meetings`) и фото (`notifications:photos`). Frontend подключается к стриму единожды и диспатчит typed `CustomEvent` для подписчиков других модулей.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/notifications.py`, `./backend/app/services/notifications_sse.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia (`./frontend/src/stores/notifications.ts`), TanStack Query (`./frontend/src/queries/notifications.ts`) |
| Воркер | ARQ (`./backend/app/worker/tasks/notifications.py`) |
| Хранилище | БД (PostgreSQL) + Redis (Streams, Sorted Sets для лимитов соединений) |
| Префикс API | `/api/v1/notifications` |
| ACL-кэш | Нет |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/notifications.py` | FastAPI эндпойнты списка, прочтения, удаления и SSE-стрима |
| Service | `./backend/app/services/notifications.py` | Бизнес-логика создания уведомлений, подсчёта непрочитанных, групповой рассылки |
| SSE Service | `./backend/app/services/notifications_sse.py` | Оркестрация SSE, Lua-лимиты соединений, heartbeat и продление сессий |
| Worker | `./backend/app/worker/tasks/notifications.py` | ARQ-задачи рассылки email-оповещений по событиям |
| Model | `./backend/app/models/notification.py` | SQLAlchemy-модель `Notification` |
| Schema | `./backend/app/schemas/notification.py` | Pydantic-схемы `NotificationOut` и `NotificationListOut` |
| Frontend API | `./frontend/src/api/notifications.ts` | REST-клиент для работы с API уведомлений |
| Frontend Store | `./frontend/src/stores/notifications.ts` | Pinia-стор управления SSE-соединением, списком и счётчиком |
| Frontend Queries | `./frontend/src/queries/notifications.ts` | TanStack Query хуки для реактивных запросов и мутаций |

---

## 3. Модель данных

### Таблица `notifications`

| Колонка | Тип | Nullable | Описание |
|---|---|---|---|
| `id` | `UUID` | нет (PK) | `gen_random_uuid()` |
| `user_id` | `UUID` | да (FK `users.id` `SET NULL`) | Владелец уведомления; `NULL` при удалении пользователя |
| `type` | `VARCHAR(80)` | нет | Тип события (см. список ниже) |
| `title` | `VARCHAR(500)` | нет | Заголовок |
| `body` | `TEXT` | да | Дополнительный текст |
| `link` | `VARCHAR(1000)` | да | Внутренняя ссылка (relative URL) |
| `is_read` | `BOOLEAN` | нет | По умолчанию `false` |
| `created_at` | `TIMESTAMPTZ` | нет | `NOW()` |
| `read_at` | `TIMESTAMPTZ` | да | Заполняется при отметке прочтения |

**Индексы:** `ix_notifications_user_id` на `user_id`.

**Soft-delete:** не предусмотрен — строки удаляются физически через `DELETE /api/v1/notifications/{id}`.

**См. также:** `./docs/db-schema.md`.

### Pydantic-схемы (`./backend/app/schemas/notification.py`)

- **`NotificationOut`**: поля: `id, user_id, type, title, body, link, is_read, created_at, read_at`.
- **`NotificationListOut`**: `items: list[NotificationOut]`, `total: int`, `unread_count: int`.

---

## 4. Модель прав (ACL)

- **Фильтрация по владельцу**: Выборка и модификация всегда ограничены условием `Notification.user_id == current_user.id` — пользователь имеет доступ только к собственным уведомлениям.
- **Ролевые ограничения**: Отсутствуют. Пользователи всех ролей (включая `admin`) имеют равные права в рамках своих уведомлений; администраторы не могут просматривать или изменять чужие уведомления.
- **Лимиты соединений**: Ограничения на SSE-соединения задаются в системных настройках (`sse_max_connections_per_user`, `sse_max_connections_global`), проверяются атомарно при подключении и кэшируются на 60 секунд.

**См. также:** `./docs/roles-matrix.md`.

---

## 5. REST API

Базовый префикс: `/api/v1/notifications`. Все эндпойнты требуют аутентификацию (куки `portal_session`).

| Метод | Путь | Назначение | Права | Идемпотентность |
|---|---|---|---|---|
| GET | `/api/v1/notifications` | Получить список уведомлений текущего пользователя. Поддерживает Query-параметры `unread_only` (bool, default `false`), `limit` (1–200, default 50), `offset` (≥ 0). Возвращает `NotificationListOut`. | `CurrentUser` | Да |
| GET | `/api/v1/notifications/unread-count` | Количество непрочитанных уведомлений. Возвращает `{"unread_count": N}`. | `CurrentUser` | Да |
| GET | `/api/v1/notifications/stream` | SSE-стрим: мультиплексирует три Redis-потока. Возвращает `text/event-stream`. Поддерживает заголовок `Last-Event-ID`. | `CurrentUser` | Да |
| POST | `/api/v1/notifications/{notification_id}/read` | Пометить одно уведомление прочитанным (`is_read=true`, `read_at=now`). Возвращает `{"ok": true}`. | `CurrentUser` (только свои) | Да |
| POST | `/api/v1/notifications/read-all` | Пометить все непрочитанные уведомления прочитанными одним UPDATE. Возвращает `{"ok": true}`. | `CurrentUser` | Да |
| DELETE | `/api/v1/notifications/{notification_id}` | Физическое удаление уведомления. Возвращает `204 No Content`. | `CurrentUser` (только свои) | Нет |

**См. также:** `./docs/api-contracts.md`.

---

## 6. Веб-реализация реалтайма (SSE)

Оркестрация реалтайм-вещания реализована в `./backend/app/services/notifications_sse.py`.

### SSE-стрим (`_sse_generator`)
- **Установление соединения**: При подключении сразу отдаёт `": connected\n\n"`.
- **Мультиплексирование**: Параллельно опрашивает три Redis-потока через `asyncio.gather` с `XREAD`: персональный (`notifications:{user_id}`) с блокировкой 500 мс, встречи (`notifications:meetings`) с блокировкой 0, и фото (`notifications:photos`) с блокировкой 0.
- **Composite Last-Event-ID**: Имеет формат `"personal_id|meetings_id|photos_id"`. Позволяет корректно восстановить чтение всех трёх потоков с нужных позиций после переподключения. Клиент сохраняет последний полученный `lastEventId` и передаёт его при реконнекте в query-параметре `?lastEventId=...` или заголовке.
- **Heartbeat (Keepalive)**: Каждые 20 секунд отправляет keepalive-комментарий `": keepalive\n\n"` и обновляет TTL своей записи в Redis. Счётчик keepalive проверяется по условию `keepalive_counter * _SSE_POLL_INTERVAL >= 20`.
- **Продление сессии**: Каждые 5 минут продлевает TTL сессионного куки (`SESSION_TTL_SECONDS`) для поддержания активности долгоживущих SSE-соединений.
- **Обработка ошибок**: При сбоях `XREAD` включается экспоненциальный backoff (базовая задержка 0.5 с, максимум 30 с) с добавлением случайного jitter ≤ 20%.
- **Лимиты соединений**: Проверяются атомарно с помощью Lua-скрипта (`_LUA_CONN_ADD`) при открытии стрима. Скрипт удаляет устаревшие соединения по score (timestamp), сверяет per-user и global лимиты, и добавляет новое соединение в Sorted Sets с TTL-скором. Результат выполнения:
  - `1` — Успешно добавлено.
  - `-1` — Превышен per-user лимит (возвращает `429 Too Many Requests`).
  - `-2` — Превышен global лимит (возвращает `429 Too Many Requests`).
- При недоступности Redis бросается `503 Service Unavailable`.
- В блоке `finally` происходит очистка: метод `_cleanup_connection` удаляет `connection_id` из `sse:conn:{user_id}` и `sse:global`.

### Frontend SSE-клиент (`./frontend/src/stores/notifications.ts`)
- SSE URL: `/api/v1/notifications/stream`, `withCredentials: true`.
- **Reconnect**: Экспоненциальный backoff (начальная задержка 5 с, максимум 60 с).
- **Heartbeat**: Если в течение 90 секунд не поступило ни одного события (включая keepalive), соединение принудительно пересоздаётся.
- **Защита payload**: События размером более 64 КиБ отбрасываются на уровне стора во избежание сбоев парсинга или переполнения памяти.
- **Обрабатываемые события**:
  - `notification` → добавляет `NotificationItem` в начало списка, инкрементирует `unreadCount`.
  - `meeting_changed` → диспатчит window `CustomEvent('meetings:changed')`.
  - `photo_processed` → парсит `{photo_id, folder_id, blurhash}`, диспатчит window `CustomEvent('photos:processed', { detail })`.
- При вызове `init()` загружается счётчик непрочитанных и открывается SSE. `reset()` закрывает SSE и сбрасывает состояние при выходе пользователя.

---

## 7. Типы уведомлений и их продюсеры

| Тип | Продюсер | Получатель |
|---|---|---|
| `news_published` | `notify_users_news_published` (`./backend/app/services/notifications.py` / ARQ задача `notify_news_published`) | Все пользователи с `notify_inapp=true` + фильтр по department/role |
| `feedback_new` | `notify_admins_new_feedback` (`./backend/app/services/notifications.py` / вызов из `./backend/app/api/feedback/feedback_service.py`) | Все администраторы с `notify_inapp=true`, кроме автора обращения |
| `feedback_reply` | `notify_user_feedback_reply` (`./backend/app/services/notifications.py` / вызов из `./backend/app/api/feedback/feedback_service.py`) | Автор обращения (`notify_inapp=true`) |
| `feedback_closed` | `notify_user_feedback_status_changed` (`./backend/app/services/notifications.py` / вызов из `./backend/app/api/feedback/feedback_service.py` при `new_status == "closed"`) | Автор обращения (`notify_inapp=true`) |
| `suggestion_reviewed` | `notify_suggestion_reviewed` (`./backend/app/services/notifications.py` / вызов из `./backend/app/api/kb/suggestions.py`) | Автор правки (`notify_inapp=true`) |
| `files.file_shared` | `notify_file_shared` (`./backend/app/api/files/_share_notify.py`) | Все получатели общего доступа с `notify_inapp=true`, кроме создателя ссылки |

---

## 8. Паттерн публикации publish-after-commit

Для обеспечения согласованности между БД и Redis Streams используется паттерн отложенной публикации:
1. Функция `create_notification` регистрирует запись `Notification` через `db.add` + `db.flush()`.
2. Она возвращает асинхронную функцию-замыкание `_publish`, которая инкапсулирует вызов `_publish_to_stream`.
3. Вызывающий код накапливает коллбэки `_publish` во время работы транзакции.
4. Выполняется `await db.commit()`.
5. Только после успешного коммита вызываются накопленные `publish()`, отправляя события в Redis через команду `XADD`.

Это предотвращает отправку уведомления в реалтайм до того, как запись о нём физически зафиксирована в СУБД.

---

## 9. Хранилище событий Redis Stream

Персональные уведомления временно кэшируются в Redis Streams для поддержки SSE-механизма:
- **Ключ**: `notifications:{user_id}`.
- **Хранение**: С ограничением максимальной длины `XADD ... maxlen=200 ~` (хранятся последние около 200 событий).
- **TTL ключа**: Устанавливается на 7 дней (`EXPIRE`) при каждой публикации.
- **Payload события**: `{id, type, title, body, link, created_at}`.

---

## 10. Фоновые задачи email-оповещений

Отправка email-уведомлений выполняется асинхронно через ARQ-воркер (код в `./backend/app/worker/tasks/notifications.py`):
- **Рассылка новостей (`notify_news_published`)**: Выполняет выборку получателей напрямую через `asyncpg` во избежание оверхеда ORM, формирует HTML/текст письма и ставит их в очередь отправки `email_outbox`, после чего инициирует in-app рассылку через `notify_users_news_published`.
- **Результаты рассмотрения правок (`notify_suggestion_reviewed_email`)**: Записывает письмо-уведомление с вердиктом (approve/reject) в очередь `email_outbox`.
- **Отправка писем (`send_email_notification`)**: Производит физическую отправку писем из очереди outbox через SMTP-соединение (`aiosmtplib`). Поддерживает интеллектуальный retry через ARQ с экспоненциальным backoff. Постоянные ошибки SMTP (код ответа 5xx) сразу считаются фатальными и не ретраятся.

---

## Безопасность

- **Валидация входных данных**: Запросы списков уведомлений валидируют параметры `limit` (значения строго от 1 до 200) и `offset` (неотрицательные числа).
- **Санитизация почтовых отправлений**: Все динамические строки (заголовки статей, новости) принудительно экранируются через функцию `_esc` (`html.escape` с параметром `quote=True`) перед встраиванием в HTML-шаблоны писем. Это исключает XSS-угрозы.
- **Ограничение размеров сообщений**: Frontend-клиент контролирует размер входящего SSE-фрейма. Сообщения, чей payload превышает 64 КиБ, отбрасываются на уровне стора во избежание сбоев парсинга или переполнения памяти вкладки браузера.
- **Что НЕ логируется**: В логи воркера и SSE-обработчиков запрещено выводить куки сессий, SMTP-пароли и другие конфиденциальные реквизиты авторизации.

---

## События аудита

Внутри модуля «Уведомления» вызовы функции `push_audit_event` отсутствуют. Логирование действий пользователей и отправка уведомлений фиксируются стандартным системным логгером.

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit (Backend) | `./backend/tests/unit/test_notifications.py` | Создание уведомлений, отложенную публикацию, групповую рассылку |
| Unit (Backend) | `./backend/tests/unit/test_notifications_routes.py` | REST-эндпойнты списка, прочтения, массового прочтения и удаления |
| Unit (Backend) | `./backend/tests/unit/test_notifications_sse_generator.py` | SSE-генератор, лимиты соединений, heartbeat, продление сессий, обработку сбоев |
| Unit (Backend) | `./backend/tests/unit/test_worker_notifications_tasks.py` | ARQ-задачи отправки писем, retry-логику, рендеринг email-шаблонов |
| Unit (Frontend) | `./frontend/tests/unit/notifications-api.spec.ts` | Клиентские методы работы с API уведомлений |
| Unit (Frontend) | `./frontend/tests/unit/notifications-store.spec.ts` | Поведение Pinia-стора, SSE-подключение, реконнект, heartbeat, обработку событий |
| Unit (Frontend) | `./frontend/tests/unit/queries-notifications.spec.ts` | Интеграцию с TanStack Query, инвалидацию кэшей после мутаций |

---

## Связанные документы

- `./docs/db-schema.md` — Схема базы данных
- `./docs/api-contracts.md` — Контракты REST API
- `./docs/roles-matrix.md` — Матрица ролей и доступов
- `./docs/testing.md` — Руководство по тестированию проекта
- `./docs/audit.md` — Подсистема аудита действий пользователей
- `./docs/sharing.md` — Модуль общего доступа к файлам
