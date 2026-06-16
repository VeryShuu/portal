# Модуль «Email-инфраструктура»

> **Когда читать:** отправка писем, outbox, ретраи/DLQ, SMTP-настройки.
> **Ключевой код:** `./backend/app/services/email_outbox.py`, `./backend/app/worker/tasks/email_utils.py`, `./frontend/src/pages/admin/tabs/EmailOutboxTab.vue`.
> **ADR:** —. **См. также:** `./docs/db-schema.md`.

> Общая для всего портала схема гарантированной отправки email с persistent outbox-таблицей в PostgreSQL, управляемыми ретраями, классификацией ошибок и админ-панелью для ручного контроля. Обеспечивает надежную доставку уведомлений из модулей встреч (meetings), новостей (news), предложений в базу знаний (kb suggestions) и общих системных сообщений без риска потери данных при падениях Redis или воркеров.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/email_outbox.py`), SQLAlchemy, PostgreSQL, ARQ |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/admin/tabs/EmailOutboxTab.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/email_outbox.py`, `./backend/app/worker/tasks/email_utils.py`) |
| Хранилище | PostgreSQL (таблица `email_outbox`), локальный конфигурационный файл `/data/branding/email-settings.json` |
| Префикс API | `/api/v1/admin/email-outbox` |
| ACL-кэш | — |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Model | `./backend/app/models/email_outbox.py` | Модель SQLAlchemy для таблицы `email_outbox` |
| Migration | `./backend/migrations/versions/051_email_outbox.py` | Миграция базы данных для создания outbox-таблицы |
| Service | `./backend/app/services/email_outbox.py` | Слой бизнес-логики: enqueuing, claiming, marking status, rescheduling, cleaning |
| Worker Tasks | `./backend/app/worker/tasks/email_outbox.py` | Фоновые задачи ARQ: периодический процессинг outbox и очистка старых записей |
| Worker Helpers | `./backend/app/worker/tasks/email_utils.py` | Хелперы для работы со SMTP: загрузка настроек, отправка, классификация ошибок, backoff |
| Router | `./backend/app/api/email_outbox.py` | FastAPI роутер с эндпоинтами админ-панели |
| Frontend API | `./frontend/src/api/emailOutbox.ts` | Клиентские методы запросов к API |
| Frontend Keys | `./frontend/src/queries/keys.ts` | Ключи react-query для кэширования |
| Frontend UI | `./frontend/src/pages/admin/tabs/EmailOutboxTab.vue` | Панель администрирования очереди писем |

---

## 3. Модель данных

Таблица `email_outbox` хранит все исходящие сообщения и историю попыток их отправки.

Миграция: `./backend/migrations/versions/051_email_outbox.py`.
Модель: `./backend/app/models/email_outbox.py`.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `kind` | varchar(64) | Тип письма: `meeting`, `news`, `kb_suggestion`, `file_share`, `generic` |
| `to_email` | varchar(320) | Получатель |
| `subject` | varchar(998) | Тема письма |
| `body_html` | text | HTML-тело письма |
| `body_text` | text NULL | Текстовая fallback-версия |
| `payload` | jsonb | Произвольные данные (для встреч: `ical_b64`, `method`) |
| `status` | varchar(16) | Статус: `PENDING`, `SENDING`, `SENT`, `FAILED`, `DLQ`, `CANCELLED` |
| `attempts` | int | Счётчик фактически выполненных попыток |
| `max_attempts` | int | Лимит попыток (по умолчанию `OUTBOX_MAX_ATTEMPTS = 6`) |
| `next_attempt_at` | timestamptz | Время следующей запланированной попытки отправки |
| `last_error` | text | Описание последней ошибки |
| `last_error_type` | varchar(128) | Имя класса исключения |
| `last_error_class` | varchar(16) | Классификация ошибки (`transient`, `permanent`, `unknown`) |
| `related_resource_type` | varchar(64) | Тип связанного бизнес-объекта (`meeting_booking`, `news`, `kb_article`, и др.) |
| `related_resource_id` | UUID NULL | ID связанного бизнес-объекта |
| `created_by_user_id` | UUID NULL | Инициатор отправки |
| `created_at` | timestamptz | Время создания записи |
| `updated_at` | timestamptz | Время последнего обновления записи |
| `sent_at` | timestamptz NULL | Время фактической успешной отправки |

### Ограничения (Constraints)
- `ck_email_outbox_status` — CHECK-constraint, ограничивающий возможные значения статуса: `('PENDING', 'SENDING', 'SENT', 'FAILED', 'DLQ', 'CANCELLED')`.

### Индексы (Indexes)
- `idx_email_outbox_pending` — partial-индекс по `next_attempt_at WHERE status = 'PENDING'`. Позволяет диспетчеру быстро находить готовые к отправке письма.
- `idx_email_outbox_status_created` — составной индекс по `(status, created_at DESC)` для быстрой фильтрации и пагинации в админ-панели.
- `idx_email_outbox_to_email` — обычный индекс по `to_email` для поиска по получателю.
- `idx_email_outbox_resource` — составной индекс по `(related_resource_type, related_resource_id)` для быстрого поиска писем, связанных с конкретными объектами.

### Жизненный цикл статусов

```
PENDING ──[claim_pending]──> SENDING ──[success]──> SENT (sent_at=NOW)
                                 │
                     [err transient / unknown]
                                 ├─ attempts < max_attempts ──> PENDING (backoff + next_attempt_at)
                                 └─ attempts ≥ max_attempts ──> DLQ
                                 │
                          [err permanent]
                                 └─> DLQ
```

- **Ручной перезапуск (Admin Retry):** Переводит запись в статус `PENDING` со сбросом попыток (опционально) и установкой `next_attempt_at = NOW()`. Возможен из статусов `FAILED`, `DLQ`, `CANCELLED`, `SENT`, `PENDING`.
- **Ручная отмена (Admin Cancel):** Переводит запись в статус `CANCELLED`. Возможен только из статусов `PENDING`, `FAILED`, `DLQ`.

---

## 4. Модель прав (ACL)

- Все операции с очередью писем (просмотр списка, просмотр деталей конкретного письма, отмена отправки, принудительный повтор) доступны исключительно пользователям с административными правами.
- Проверка прав осуществляется в FastAPI роутере `./backend/app/api/email_outbox.py` с помощью зависимости `AdminDep`.
- На фронтенде вкладка админки «Очередь Email» доступна в рамках `VALID_TABS` только пользователям с доступом к админ-панели.

---

## 5. REST API

Все эндпоинты требуют авторизации администратора (`AdminDep`).
Префикс эндпоинтов: `/api/v1/admin/email-outbox`

| Метод | Путь | Права | Описание |
|---|---|---|---|
| `GET` | `/` | Admin | Список писем с фильтрацией по статусу, типу (`kind`), получателю (`to_email`), дате создания (`date_from`, `date_to`) и поисковому запросу `q`. Возвращает `{items, total, limit, offset, counts_30d}`. |
| `GET` | `/{id}` | Admin | Карточка письма (включая `body_html`, `body_text`, `payload`, `last_error`). |
| `POST` | `/{id}/retry` | Admin | Повторная отправка письма (переводит в `PENDING` с `next_attempt_at = NOW()`). Принимает query-параметр `reset_attempts` (по умолчанию `true`). |
| `POST` | `/{id}/cancel` | Admin | Отмена отправки (переводит в `CANCELLED`, допустимо только для `PENDING`, `DLQ`, `FAILED`). |
| `GET` | `/_/stats` | Admin | Статистика по статусам + время самого старого ожидающего письма `oldest_pending_at`. |

Контракты экспортируются в `./openapi.json` через `./backend/scripts/export_openapi.py`.

---

## 6. Диспетчер воркера (Dispatcher Worker)

В `./backend/app/worker/main.py` зарегистрированы две периодические задачи воркера ARQ:

1. **`process_email_outbox`** — выполняется каждые 10 секунд (cron `second={0,10,20,30,40,50}`).
   - Вызывает `claim_pending(session, limit=20)` для атомарного захвата записей в состоянии `PENDING` (используется конструкция `FOR UPDATE SKIP LOCKED`).
   - Если SMTP не сконфигурирован (пустой `host` в файле `/data/branding/email-settings.json`), логирует ошибку, переводит записи в `PENDING` с соответствующим backoff (класс ошибки — `transient`, `ConfigurationError`).
   - Для каждого письма собирает MIME-структуру с помощью `_build_mime(...)`.
   - Пытается отправить сообщение через `smtp_send(...)` (обёртка над `aiosmtplib.send`).
   - При успехе: `mark_sent(session, id)` (статус `SENT`, `sent_at=NOW`, `attempts += 1`).
   - При ошибке: `classify_smtp_error(...)` классифицирует её, затем `mark_failed(...)` рассчитывает время повтора через `compute_retry_defer(...)` и переводит письмо в `PENDING` с новым `next_attempt_at` либо отправляет в `DLQ`.

2. **`cleanup_email_outbox`** — выполняется раз в сутки в 04:15 (cron `hour=4, minute=15`).
   - Вызывает `cleanup_old_sent(session, older_than_days=30)` для безвозвратного удаления записей со статусом `SENT`, созданных более 30 дней назад.
   - Ошибочные записи (`FAILED`, `DLQ`) и отменённые (`CANCELLED`) **не удаляются автоматически** для возможности ручного разбора администратором.

### MIME-сборка и iCal
- `KIND_MEETING` → собирается как `multipart/mixed` с заголовком `Content-Class: urn:content-classes:calendarmessage`. Внутрь вкладывается `multipart/alternative`, содержащий HTML-тело и inline-календарь `text/calendar; method=REQUEST\|CANCEL`, декодированный из Base64 (`payload.ical_b64`).
- Остальные (`KIND_NEWS`, `KIND_FILE_SHARE`, `KIND_GENERIC`) → собираются как `multipart/alternative`, содержащие текстовую fallback-версию (если есть) и HTML-тело. Если в `payload.inline_images` есть вложения (напр. обложка новости), `KIND_NEWS` оборачивается в `multipart/related` с inline-картинками по `Content-ID`.

### Классификация ошибок и Backoff
Функции классификации и расчёта задержек находятся в `./backend/app/worker/tasks/email_utils.py`:
- **`classify_smtp_error(exc)`** возвращает класс ошибки:
  - `transient` (сетевые ошибки, таймауты, 4xx SMTP коды) → ретраить. Включает: `SMTPConnectError`, `SMTPConnectTimeoutError`, `SMTPServerDisconnected`, `SMTPHeloError`, `SMTPTimeoutError`, `TimeoutError`, `ConnectionError`, `ConnectionRefusedError`, `ConnectionResetError`, `OSError`, `SMTPNotSupported`.
  - `permanent` (ошибки авторизации, некорректный адрес, 5xx SMTP коды) → не ретраить, сразу в `DLQ`. Включает: `SMTPAuthenticationError`, `SMTPRecipientsRefused`, `SMTPSenderRefused`, `SMTPDataError`.
  - `unknown` (любые непредвиденные исключения) → ретраить с осторожным backoff.
- **`compute_retry_defer(job_try, error_class)`** рассчитывает задержку:
  - `transient`: 30, 60, 120, 240, 480, 960 секунд (cap 1800 сек / 30 мин) + 15% джиттер.
  - `unknown`: 15, 30, 60, 120, 240, 480 секунд (cap 1800 сек / 30 мин) + 15% джиттер.

---

## 7. Настройки SMTP

Настройки SMTP-сервера хранятся на диске в файле `/data/branding/email-settings.json`.
Загрузка и управление настройками реализованы в модуле `./backend/app/services/email_settings.py`:
- Чтение конфигурации осуществляется через `read_email_settings()`, возвращающий Pydantic-модель `EmailSettings`.
- Сохранение настроек производится атомарно через `save_email_settings(s)` с выставлением прав доступа `0o600` на файл конфигурации для безопасности пароля.
- Отправка тестового письма для проверки конфигурации реализована в функции `send_test_email(...)`.

### Параметры конфигурации
- `host` — адрес SMTP-сервера. Если не заполнен, отправка писем приостанавливается, они накапливаются в `PENDING`.
- `port` — порт сервера (по умолчанию `25`).
- `from_address` — адрес отправителя (по умолчанию `portal@company.local`).
- `username` — имя пользователя для авторизации.
- `password` — пароль (в API маскируется как `***`).
- `use_tls` — использовать TLS.
- `use_starttls` — использовать STARTTLS.

---

## 8. Интеграция с модулями (Producers)

Запись писем в outbox осуществляется через асинхронный метод `enqueue_outbox_email(...)` из `./backend/app/services/email_outbox.py`. Caller-функция обязана самостоятельно закоммитить транзакцию сессии (`db.commit()`), обеспечивая транзакционность бизнес-логики и отправки писем.

| Модуль | Файл & Метод | Как работает |
|---|---|---|
| **Meetings** | `./backend/app/services/meetings/notifications.py::enqueue_meeting_emails` | Вызывается роутами (`./backend/app/api/meetings/bookings.py`, `series.py`) **в той же сессии и до `db.commit()`**, что и бронирование — письма коммитятся атомарно с бизнес-операцией (outbox-инвариант). Создаёт записи в outbox для каждого приглашённого участника, организатора и `room.email`. iCal календарь кодируется в Base64 и сохраняется в `payload.ical_b64`. Standalone-обёртка `dispatch_meeting_emails` (своя сессия+транзакция) сохранена для legacy/ARQ-fallback. |
| **News (рассылка по кнопке)** | `./backend/app/services/news/email_share.py::share_news_by_email` | Ручная рассылка: редактор выбирает получателей и отправляет письмо о новости (тема `Новость: {title}`, `kind=KIND_NEWS`). Шаблон — `build_share_email_content` (брендированный, dark-safe, с inline-обложкой в `payload.inline_images`). Это **единственный** путь отправки email по новостям. |

### Унаследованные (Legacy) задачи
ARQ-задачи `send_meeting_email` (в `./backend/app/worker/tasks/meetings/email.py`) и `send_email_notification` (в `./backend/app/worker/tasks/notifications.py`) сохранены в качестве fallback-пути. Они также используют хелперы из `./backend/app/worker/tasks/email_utils.py` (классификацию ошибок, `arq.Retry(defer=...)`, `max_tries=6`, `job_timeout=60`), но не задействуют механизм outbox. Все новые модули должны отправлять письма исключительно через `enqueue_outbox_email(...)`.

---

## Безопасность

- **Защита учётных данных**: Пароль от SMTP-сервера хранится на диске с правами доступа `0o600` на конфигурационный файл `/data/branding/email-settings.json`. В API-ответах пароль заменяется маской `***` и никогда не выводится в логи.
- **Ограничения полей**: На уровне валидации и базы данных наложены жёсткие ограничения на длину полей: получатель `to_email` (до 320 символов), тема `subject` (до 998 символов).
- **Контроль нагрузки**: Использование батчинга (`DISPATCH_BATCH_SIZE = 20` за одну итерацию воркера) предотвращает перегрузку SMTP-сервера и исключает пиковые скачки потребления ресурсов.
- **Защита от MIME header injection**: значения заголовков `Subject`/`To`/`From` пропускаются через `_sanitize_header()` (`./backend/app/worker/tasks/email_outbox.py`), который схлопывает любые CR/LF в пробел. Источник `subject` — пользовательские данные из БД (`booking.title`, `news_title`); на политике `compat32` присвоение `msg["Subject"]=...` само по себе не фильтрует переводы строк, поэтому без санитизации возможна инъекция скрытых получателей (Bcc).

---

## События аудита

В модуле управления брендингом (`./backend/app/api/branding.py`) генерируются следующие события аудита (через эмиттер с пространством имён `"branding"`):
- Изменение SMTP-настроек: событие аудита с target `"email_settings"`.
- Отправка тестового письма: событие аудита с target `"email_test"`.

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./backend/tests/unit/test_email_outbox_service.py` | Тестирование методов сервиса `enqueue_outbox_email`, `claim_pending`, `mark_sent`, `mark_failed`, ручного перезапуска и очистки. |
| Unit | `./backend/tests/unit/test_worker_email_outbox.py` | Тестирование воркера: обработка очереди в штатном режиме, при отсутствии конфигурации SMTP и при возникновении SMTP-ошибок. |
| Unit | `./backend/tests/unit/test_meetings_worker_email.py` | Тестирование отправки приглашений на встречи. |
| Unit | `./backend/tests/unit/test_meetings_unlink_emails.py` | Тестирование отмены отправки писем при отмене/изменении встреч. |
| Frontend | `./frontend/tests/unit/email-tab.spec.ts` | Покрытие компонента вкладки очереди писем в админке `EmailOutboxTab.vue` (фильтры, отображение, действия retry/cancel). |

---

## Связанные документы

- `./docs/db-schema.md` — схема базы данных.
- `./docs/api-contracts.md` — контракты REST API.
- `./docs/roles-matrix.md` — матрица прав и доступа.
- `./docs/adr.md` — архитектурные решения.
