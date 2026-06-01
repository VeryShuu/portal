# Модуль «Уведомления»

> **Когда читать:** in-app уведомления, SSE-стрим, отметка прочтения, продюсеры событий (новости, KB, обратная связь, файлы).
> **Ключевой код:** `backend/app/api/notifications.py`, `backend/app/services/notifications.py`, `backend/app/worker/tasks/notifications.py`, `frontend/src/stores/notifications.ts`.
> **ADR:** —

> Модуль доставляет персональные in-app уведомления через PostgreSQL + Redis Streams. API слой предоставляет CRUD над записями и SSE-эндпойнт (`/stream`), который мультиплексирует три Redis-потока: персональный (`notifications:{user_id}`), совещания (`notifications:meetings`) и фото (`notifications:photos`). Frontend подключается к стриму единожды и диспатчит typed `CustomEvent` для подписчиков других модулей.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/notifications.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia (`./frontend/src/stores/notifications.ts`), TanStack Query (`./frontend/src/queries/notifications.ts`) |
| Транспорт реалтайм | Redis Streams + SSE (`text/event-stream`) |
| Redis-потоки | `notifications:{user_id}` (персональный), `notifications:meetings` (встречи), `notifications:photos` (фото) |
| Лимиты соединений | Per-user и global — из `SystemSettings` (`sse_max_connections_per_user`, `sse_max_connections_global`); атомарный check-and-add через Lua |
| Права доступа | Все CRUD-эндпойнты требуют аутентифицированного пользователя (`CurrentUser`); пользователь видит только свои уведомления |

---

## 2. Модель данных

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

**Soft-delete:** не предусмотрен — строки удаляются физически через `DELETE /notifications/{id}`.

### Pydantic-схемы (`./backend/app/schemas/notification.py`)

- `NotificationOut` — поля: `id, user_id, type, title, body, link, is_read, created_at, read_at`.
- `NotificationListOut` — `items: list[NotificationOut]`, `total: int`, `unread_count: int`.

---

## 3. REST API

База: `/api/v1/notifications`. Все эндпойнты требуют аутентификацию (`portal_session` cookie).

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/notifications` | Список уведомлений текущего пользователя. Query params: `unread_only` (bool, default `false`), `limit` (1–200, default 50), `offset` (≥ 0). Возвращает `NotificationListOut`. | `CurrentUser` |
| GET | `/api/v1/notifications/unread-count` | Количество непрочитанных. Возвращает `{"unread_count": N}`. | `CurrentUser` |
| GET | `/api/v1/notifications/stream` | SSE-стрим: мультиплексирует три Redis-потока. `Content-Type: text/event-stream`. Поддерживает заголовок `Last-Event-ID`. | `CurrentUser` |
| POST | `/api/v1/notifications/{notification_id}/read` | Отметить одно уведомление прочитанным (`is_read=true`, `read_at=now`). Идемпотентен. Возвращает `{"ok": true}`. | `CurrentUser`, только свои |
| POST | `/api/v1/notifications/read-all` | Пометить все непрочитанные уведомления прочитанными одним UPDATE. Возвращает `{"ok": true}`. | `CurrentUser` |
| DELETE | `/api/v1/notifications/{notification_id}` | Физически удалить уведомление. Возвращает `204 No Content`. | `CurrentUser`, только свои |

---

## 4. Права и роли

- Фильтрация **всегда** по `Notification.user_id == current_user.id` — пользователь видит и управляет только своими уведомлениями.
- Нет ролевых ограничений внутри модуля; `admin` не имеет привилегированного доступа к чужим уведомлениям.
- Лимиты SSE-соединений настраиваются в системных настройках (`sse_max_connections_per_user`, `sse_max_connections_global`), читаются с кэшем 60 с через `load_system_settings_shared(redis)`.

---

## 5. Frontend

### Файлы

| Файл | Назначение |
|---|---|
| `./frontend/src/api/notifications.ts` | Тонкий REST-клиент: `fetchNotifications`, `fetchUnreadCount`, `markRead`, `markAllRead`, `deleteNotification`. Экспортирует интерфейсы `NotificationItem`, `NotificationListOut`. |
| `./frontend/src/stores/notifications.ts` | Pinia-стор. Управляет SSE-соединением, состоянием списка и счётчиком. Диспатчит `CustomEvent` для других модулей. |
| `./frontend/src/queries/notifications.ts` | TanStack Query обёртки: `useNotificationsQuery`, `useUnreadCountQuery`, `useMarkReadMutation`, `useMarkAllReadMutation`, `useDeleteNotificationMutation`. `staleTime: 30 000 ms`; `useUnreadCountQuery` дополнительно поллит раз в 60 с (`refetchInterval`). |

### SSE-клиент (`stores/notifications.ts`)

- SSE URL: `/api/v1/notifications/stream`, `withCredentials: true`.
- При наличии `lastEventId` добавляет его query param: `?lastEventId=...`.
- **Reconnect:** экспоненциальный backoff, базовая задержка 5 с, максимум 60 с.
- **Heartbeat:** если в течение 90 с не поступило ни одного события (включая keepalive-комментарий) — соединение переподключается.
- **Обрабатываемые события:**
  - `notification` → добавляет `NotificationItem` в начало списка, инкрементирует `unreadCount`.
  - `meeting_changed` → диспатчит `window` `CustomEvent('meetings:changed')`.
  - `photo_processed` → парсит `{photo_id, folder_id, blurhash}`, диспатчит `window` `CustomEvent('photos:processed', { detail })`.
- Защита от oversized payload: данные > 64 KiB отбрасываются.
- `init()` — загружает `unreadCount` и открывает SSE. `reset()` — закрывает SSE, очищает состояние (вызывается при logout).

---

## 6. Особенности и нюансы

### SSE-стрим (`_sse_generator`)

- При подключении сразу отдаёт `": connected\n\n"`.
- Читает три Redis-потока параллельно через `asyncio.gather` + `XREAD block=500ms` (персональный) и `block=0` (встречи, фото).
- **Composite Last-Event-ID** — строка `"personal_id|meetings_id|photos_id"`. Позволяет корректно возобновить все три потока после реконнекта. Клиент сохраняет последний `lastEventId` и передаёт его при переподключении.
- **Keepalive:** каждые 20 с отправляет `": keepalive\n\n"` и обновляет TTL своей записи в Redis (per-user и global sorted sets). Счётчик keepalive рассчитывается через `keepalive_counter * _SSE_POLL_INTERVAL >= 20`.
- **Продление сессии:** каждые 5 минут продлевает TTL cookie-сессии (`SESSION_TTL_SECONDS`) для долгоживущих SSE-соединений.
- **Экспоненциальный backoff** при ошибках `XREAD`: базовая задержка 0.5 с, максимум 30 с, плюс jitter ≤ 20%.
- **Лимиты соединений** проверяются атомарно через Lua-скрипт (`_LUA_CONN_ADD`) при открытии стрима. Скрипт удаляет устаревшие записи по score (timestamp), проверяет per-user и global лимиты, добавляет новую запись в оба Sorted Set с TTL expiry score. Результат: `1` — OK, `-1` — per-user лимит, `-2` — global лимит.
- При превышении лимита возвращается `429 Too Many Requests`.
- При недоступности Redis — `503 Service Unavailable`.
- При завершении (finally) убирает `connection_id` из `sse:conn:{user_id}` и `sse:global`.

### Типы уведомлений (`type`)

| Тип | Продюсер | Получатель |
|---|---|---|
| `news_published` | `notify_users_news_published` (ARQ task `notify_news_published`) | Все пользователи с `notify_inapp=true` + фильтр по department/role |
| `feedback_new` | `notify_admins_new_feedback` (feedback_service) | Все admins с `notify_inapp=true`, кроме автора обращения |
| `feedback_reply` | `notify_user_feedback_reply` (feedback_service) | Автор обращения (`notify_inapp=true`) |
| `feedback_closed` | `notify_user_feedback_status_changed` (feedback_service, только при `new_status == "closed"`) | Автор обращения (`notify_inapp=true`) |
| `suggestion_reviewed` | `notify_suggestion_reviewed` (kb/suggestions.py) | Автор правки (`notify_inapp=true`) |
| `files.file_shared` | `notify_file_shared` (files/_share_notify.py) | Все получатели шары с `notify_inapp=true`, кроме самого шарера |

### Продюсеры и паттерн publish-after-commit

Функция `create_notification` (сервис):
1. Создаёт запись `Notification` через `db.add` + `db.flush`.
2. Возвращает корутину `_publish` — замыкание над `_publish_to_stream`.

Вызывающий код:
1. Собирает все `_publish`-коллбэки.
2. Делает `await db.commit()`.
3. Только после коммита вызывает каждый `publish()` → `XADD` в Redis Stream.

Это гарантирует, что Redis-событие публикуется лишь после успешной записи в БД.

### Redis Stream (персональный)

- Ключ: `notifications:{user_id}`.
- `XADD … maxlen=200 ~` — хранит последние ≈200 событий.
- TTL ключа: 7 дней (`EXPIRE`).
- Payload: `{id, type, title, body, link, created_at}`.

### Email-уведомления (ARQ)

- ARQ-задача `notify_news_published` (воркер): рассылает email через `email_outbox` + триггерит in-app SSE через `notify_users_news_published`. Использует прямое asyncpg-соединение для батч-выборки получателей.
- ARQ-задача `notify_suggestion_reviewed_email` (воркер): записывает в `email_outbox` письмо автору правки.
- Email-отправка (`send_email_notification`) — управляемый retry через ARQ с экспоненциальным backoff; постоянные ошибки SMTP не ретраятся.
