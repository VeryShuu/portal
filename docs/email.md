# Email-инфраструктура портала

> **Когда читать:** отправка писем, outbox, ретраи/DLQ, SMTP-настройки.
> **Ключевой код:** `app/services/email_outbox.py`, `app/worker/tasks/email_utils.py`, `frontend/src/pages/admin/tabs/EmailOutboxTab.vue`.
> **ADR:** —.

Общая для всего портала схема отправки email с persistent outbox-таблицей,
управляемыми ретраями, классификацией ошибок и админ-UI для ручного контроля.

Используется всеми модулями, которые шлют письма: meetings, news,
kb_suggestion, generic-уведомления.

---

## 1. Архитектура

```
бизнес-операция (booking / news / kb suggestion)
        │  (в той же или соседней транзакции)
        ▼
INSERT INTO email_outbox  (status=PENDING)
        │
        ▼
cron `process_email_outbox` каждые 10 с
   ├─ claim_pending() ── FOR UPDATE SKIP LOCKED → SENDING
   ├─ build MIME (meeting → multipart/mixed + iCal; generic → multipart/alternative)
   ├─ aiosmtplib.send()
   │     ├─ success → mark_sent (SENT, sent_at=NOW)
   │     └─ failure → classify_smtp_error()
   │           ├─ permanent / attempts >= max  → DLQ
   │           └─ transient / unknown           → PENDING + next_attempt_at += backoff
   ▼
Админ-UI (вкладка «Очередь Email»):
   статусы, ошибки, ручной retry / cancel, DLQ-алёрт
```

**Ключевая инвариантность:** запись в `email_outbox` создаётся **в той же
сессии**, что бизнес-объект (или сразу после его commit в фоновой задаче),
поэтому потеря писем при падении Redis / воркера невозможна. Любой провал
остаётся видимым админу.

---

## 2. Таблица `email_outbox`

Миграция: `./backend/migrations/versions/051_email_outbox.py`.
Модель: `./backend/app/models/email_outbox.py`.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `kind` | varchar(64) | `meeting` / `news` / `kb_suggestion` / `file_share` / `generic` |
| `to_email` | varchar(320) | получатель |
| `subject` | varchar(998) | тема |
| `body_html` | text | HTML-тело |
| `body_text` | text NULL | text/plain fallback |
| `payload` | jsonb | произвольные данные (для meeting: `ical_b64`, `method`) |
| `status` | varchar(16) | `PENDING / SENDING / SENT / FAILED / DLQ / CANCELLED` (CHECK) |
| `attempts` | int | счётчик фактических попыток |
| `max_attempts` | int | по умолчанию `OUTBOX_MAX_ATTEMPTS=6` |
| `next_attempt_at` | timestamptz | когда диспетчер заберёт строку |
| `last_error` / `last_error_type` / `last_error_class` | text/varchar | последняя ошибка + её класс |
| `related_resource_type` / `related_resource_id` | varchar / UUID | связка с бизнес-объектом (`meeting_booking`, `news`, `kb_article`) |
| `created_by_user_id` | UUID NULL | инициатор |
| `created_at` / `updated_at` / `sent_at` | timestamptz | временны́е метки |

**Индексы:**
- `idx_email_outbox_pending` — partial по `next_attempt_at WHERE status='PENDING'`
  (используется диспетчером).
- `idx_email_outbox_status_created` — для админ-UI.
- `idx_email_outbox_to_email`, `idx_email_outbox_resource` — для поиска.

**Жизненный цикл статусов:**

```
PENDING ─claim→ SENDING ─ok→ SENT
                       └─err transient/unknown→ PENDING (backoff)
                       └─err permanent / attempts ≥ max → DLQ
admin retry: FAILED|DLQ|CANCELLED|SENT|PENDING → PENDING (next_attempt_at=NOW)
admin cancel: PENDING|FAILED|DLQ → CANCELLED
```

---

## 3. Общий хелпер: `app/worker/tasks/email_utils.py`

Единственная точка чтения SMTP-настроек и классификации ошибок.

```python
from app.worker.tasks.email_utils import (
    JOB_TIMEOUT_SECONDS, MAX_TRIES, OUTBOX_MAX_ATTEMPTS,
    classify_smtp_error, compute_retry_defer,
    load_smtp_config, smtp_send,
)
```

- `load_smtp_config()` — `/data/branding/email-settings.json` (host, port,
  from_address, username, password, use_tls, use_starttls).
- `smtp_send(msg, cfg)` — обёртка над `aiosmtplib.send(...)` с готовыми
  kwargs (включая `start_tls` / `use_tls` / auth).
- `classify_smtp_error(exc)` → `transient | permanent | unknown`:
  - `transient`: `SMTPConnectError`, `SMTPConnectTimeoutError`,
    `SMTPServerDisconnected`, `SMTPHeloError`, `SMTPTimeoutError`,
    `TimeoutError`, `ConnectionError`, `ConnectionRefusedError`,
    `ConnectionResetError`, `OSError`, `SMTPNotSupported`, **4xx SMTP-коды**.
  - `permanent`: `SMTPAuthenticationError`, `SMTPRecipientsRefused`,
    `SMTPSenderRefused`, `SMTPDataError`, **5xx SMTP-коды**.
  - `unknown` — всё прочее, тоже ретраится, но с более коротким окном.
- `compute_retry_defer(job_try, error_class)` — экспоненциальный backoff
  + 15% jitter, cap 30 минут.
  - `transient`: 30, 60, 120, 240, 480, 960 с (capped 1800).
  - `unknown`: 15, 30, 60, 120, 240, 480 с (capped 1800).
  - `permanent` → 0 (не должен вызываться, fail-fast).
- Константы: `MAX_TRIES=6` (для ARQ-задач), `JOB_TIMEOUT_SECONDS=60`,
  `OUTBOX_MAX_ATTEMPTS=6` (для outbox-строк).

---

## 4. Запись писем: `app/services/email_outbox.py`

```python
from app.services.email_outbox import (
    KIND_MEETING, KIND_NEWS, KIND_KB_SUGGESTION, KIND_GENERIC,
    enqueue_outbox_email,
    encode_ical_bytes,  # для meeting payload
)

await enqueue_outbox_email(
    session,
    kind=KIND_NEWS,
    to_email=user.email,
    subject="...",
    body_html="...",
    body_text="...",
    payload={...},                       # опционально
    related_resource_type="news",
    related_resource_id=news_uuid,
)
```

**Важно:** caller отвечает за `commit` — это и есть outbox-pattern.
Если бизнес-транзакция rollback’нется, письмо в outbox тоже не появится.

Для встреч в payload кладётся `{"method": "REQUEST"|"CANCEL", "ical_b64": "..."}`;
диспетчер декодирует и собирает MIME с inline `text/calendar`.

Прочие функции сервиса (используются только диспетчером и админ-API):
- `claim_pending(session, limit)` — захват пачки PENDING (SKIP LOCKED).
- `mark_sent(session, id)`, `mark_failed(session, id, ..., current_attempts, max_attempts)`.
- `reschedule_for_retry(session, id, reset_attempts=True)` — ручной retry.
- `cancel(session, id)`.
- `cleanup_old_sent(session, older_than_days=30)`.

---

## 5. Диспетчер: `app/worker/tasks/email_outbox.py`

Две ARQ-задачи зарегистрированы в `./backend/app/worker/main.py`:

- **`process_email_outbox`** — `cron(second={0,10,20,30,40,50}, run_at_startup=True)`.
  Каждые 10 с забирает до `DISPATCH_BATCH_SIZE=20` PENDING-строк, шлёт через
  `aiosmtplib`, обновляет статус. На 50 писем/день — гигантский запас.

- **`cleanup_email_outbox`** — `cron(hour=4, minute=15)`. Удаляет SENT
  старше 30 дней.

MIME-сборка различается по `kind`:
- `KIND_MEETING` → `multipart/mixed` + `Content-Class: urn:content-classes:calendarmessage` + inline `text/calendar; method=REQUEST|CANCEL`.
- остальные → `multipart/alternative` (text + html).

Если SMTP не сконфигурирован (нет `host`) — выставляется
`error_class=transient` (ConfigurationError) и письмо остаётся в очереди.

---

## 6. Producer-стороны

| Модуль | Файл | Что происходит |
|---|---|---|
| Meetings | `./backend/app/services/meetings/notifications.py::dispatch_meeting_emails` | Шедулится через `schedule_email_dispatch` (BackgroundTask, отдельная сессия), пишет в outbox по строке на участника и `room.email`, iCal — base64 в payload. |
| News | `./backend/app/worker/tasks/notifications.py::notify_news_published` | ARQ-задача собирает получателей, открывает `AsyncSession`, пишет в outbox по строке на пользователя; параллельно публикует in-app SSE. |
| KB suggestions | `./backend/app/worker/tasks/notifications.py::notify_suggestion_reviewed_email` | Одна строка в outbox с темой approve/reject. |
| Прочее (`send_email_notification`) | `./backend/app/worker/tasks/notifications.py` | Legacy ARQ-задача — оставлена как fallback, но новые caller’ы должны писать в outbox. |

**Legacy ARQ-задачи `send_meeting_email` и `send_email_notification`** также
используют общий `email_utils` (классификация ошибок, `arq.Retry(defer=...)`,
`max_tries=6`, `job_timeout=60`), но основной путь теперь — outbox.

---

## 7. Admin API

`./backend/app/api/email_outbox.py`, префикс `/api/v1/admin/email-outbox`,
все endpoint’ы требуют админскую роль (`AdminDep`).

| Метод + путь | Назначение |
|---|---|
| `GET /admin/email-outbox` | список (фильтры: `status`, `kind`, `to_email`, `q`, `date_from`, `date_to`, `limit`, `offset`); ответ `{items, total, limit, offset, counts_30d}` |
| `GET /admin/email-outbox/{id}` | карточка письма (body_html, payload, last_error) |
| `POST /admin/email-outbox/{id}/retry?reset_attempts=true` | переставить в PENDING с `next_attempt_at=NOW()` |
| `POST /admin/email-outbox/{id}/cancel` | CANCELLED (только из PENDING/FAILED/DLQ) |
| `GET /admin/email-outbox/_/stats` | сводка по статусам + `oldest_pending_at` |

Контракты экспортируются в `openapi.json` через `backend/scripts/export_openapi.py`.

---

## 8. Frontend

- API-клиент: `./frontend/src/api/emailOutbox.ts`.
- Query-ключи: `./frontend/src/queries/keys.ts` (`emailOutbox`,
  `emailOutboxItem`, `emailOutboxStats`).
- Вкладка админки: `./frontend/src/pages/admin/tabs/EmailOutboxTab.vue`,
  подключена в `./frontend/src/pages/AdminPage.vue` (lazy-import,
  `VALID_TABS` включает `email-outbox`).
- i18n-ключи: `admin.tabs.emailOutbox`, `admin.emailOutbox.*` в
  `./frontend/src/i18n/ru.json` и `./frontend/src/i18n/en.json`.

UI-фичи:
- Status-бэйджи с цветами (DLQ — красный, FAILED — жёлтый, SENT — зелёный).
- Прометейный DLQ-алёрт над таблицей при `DLQ > 0`.
- Фильтры по `status / kind / to_email / search`.
- Модалка детального просмотра с last_error и HTML письма (`<details>`).
- Действия retry / cancel (с проверкой допустимости по статусу).

---

## 9. SMTP-настройки

Источник истины: `/data/branding/email-settings.json` (читается
`load_smtp_config()`). Редактирование — Admin UI → «Email».

Поля: `host`, `port`, `from_address`, `username`, `password`,
`use_tls`, `use_starttls`.

При пустом `host` диспетчер логирует
`email_outbox.dispatch.smtp_not_configured` и оставляет письма в PENDING
(класс ошибки — `transient`).

---

## 10. Эксплуатация

**Здоровье очереди**

```sql
SELECT status, count(*) FROM email_outbox GROUP BY status;
SELECT MIN(next_attempt_at) FROM email_outbox WHERE status = 'PENDING';
```

или `GET /api/v1/admin/email-outbox/_/stats`.

**Что должно тревожить:**
- `DLQ > 0` (UI показывает алёрт явно).
- `oldest_pending_at` отстаёт от `NOW()` больше чем на ~минуту при работающем воркере.
- Растущий `attempts` без перехода в SENT — обычно проблема SMTP.

**Объёмы**

При проектном уровне ~50 писем/день батч из 20 за 10 с обрабатывает любой
всплеск с огромным запасом. При росте нагрузки можно поднять
`DISPATCH_BATCH_SIZE` или участить cron.

**Очистка**

`cleanup_email_outbox` удаляет SENT > 30 дней раз в сутки. FAILED/DLQ
остаются для разбора вручную (через UI cancel или retry).

---

## 11. Тестирование

Минимальный набор юнит-тестов покрывает:
- `classify_smtp_error` — таблица соответствий типов и SMTP-кодов.
- `compute_retry_defer` — границы (cap 30 мин), джиттер ≤ 15%.
- `enqueue_outbox_email` + `claim_pending` — корректный лок и переход
  в SENDING.
- `mark_failed` — DLQ при permanent / attempts ≥ max, PENDING + defer иначе.
- `process_email_outbox` — happy / SMTP not configured / SMTP error.

Integration-тесты (Testcontainers) проверяют end-to-end путь
booking → outbox → диспетчер → SMTP-мок.
