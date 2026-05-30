# ТЗ: Модуль технической поддержки (Helpdesk)

> Замена OTRS внутри портала. Полный жизненный цикл заявки: приём из email или
> веб-формы → назначение ответственного → переписка с инициатором → закрытие → архив.
> Документ оформлен в стиле существующих ТЗ (`./docs/feedback.md`, `./docs/email.md`).

---

## 1. Цель и общие практики

### 1.1 Цель

Дать сотрудникам компании единое окно подачи и обработки заявок в техподдержку,
заменив OTRS. Заявки поступают на специальный почтовый ящик (например,
`support@company.local`) или создаются прямо в портале, обрабатываются
ответственными сотрудниками, переписка ведётся как через портал, так и по email
(полный двусторонний email-thread).

### 1.2 Общие практики (по итогу анализа OTRS, Zammad, FreeScout, GLPI, osTicket)

1. **Email-ingress по IMAP polling.** Воркер ходит на support-mailbox каждые
   30–60 c, забирает непрочитанные письма (`UNSEEN`), парсит их и помечает
   `\Seen`. После успешной обработки — `\Deleted` опционально (через настройку).
2. **Email-threading через `Message-ID` + токен `[#TKT-123]` в теме.**
   Это два независимых способа сопоставить входящее письмо с существующим
   тикетом. `Message-ID` — основной (RFC 5322), токен в теме — fallback на
   случай, если почтовик пользователя оборвал `In-Reply-To` / `References`.
3. **Outgoing-письма заголовки.** Каждое исходящее письмо тикета содержит:
   `Message-ID: <ticket-{id}-msg-{uuid}@portal>`, `References: <...>`,
   `Reply-To: support+TKT-{number}@company.local` (sub-addressing — для
   надёжного matching), тема `[#TKT-{number}] {subject}`.
4. **Идемпотентность ingress.** Для каждого письма сохраняется его
   `Message-ID` в таблице `helpdesk_email_log` с уникальным индексом —
   повторное скачивание того же письма не создаёт дубль.
5. **Статусная модель** (минимальный набор, проверенный практикой):
   `new` → `open` (assigned) → `pending` (ждём ответа клиента) → `resolved`
   → `closed` → `archived`. Возможен `reopen` (closed → open).
6. **Гостевые заявители.** Если письмо пришло с email, не привязанного к
   аккаунту портала, тикет создаётся с `requester_email`/`requester_name` без
   `requester_user_id`. При появлении пользователя с таким email — заявки
   автоматически линкуются.
7. **Архивирование.** Старые закрытые тикеты выносятся в отдельную таблицу
   `helpdesk_tickets_archive` (партиционированную по месяцам закрытия),
   чтобы основная таблица `helpdesk_tickets` оставалась компактной.
8. **In-app + email** для всех уведомлений (создание, назначение, новое
   сообщение, закрытие) — единый паттерн через `services/notifications.py` и
   `email_outbox`.

---

## 2. Роли и доступ

Используется существующая модель ролей портала (см. `./docs/roles-matrix.md`).
**Новая роль не вводится** — список ответственных настраивается отдельной
сущностью «агенты поддержки» (`helpdesk_agents`), редактируемой админом.

| Роль | Права |
|---|---|
| `reader`, `editor` | Создать заявку через веб-форму, просматривать **свои** заявки и переписку. |
| `helpdesk_agent` (флаг в `helpdesk_agents`) | Видеть все заявки, брать в работу, отвечать, менять статус, оставлять внутренние заметки. Это **не** роль `users.role`, а отдельный список. |
| `admin` | Всё, что агент + управление списком агентов, настройка mailbox, IMAP-конфиг, категорий, реассайн в обход правил, очистка архива. |

**Почему отдельная таблица, а не роль:** агенты — это операционная единица,
которая может меняться часто и независимо от ролей портала; в OTRS/Zammad
точно так же — agents отдельная сущность.

---

## 3. База данных

### 3.1 `helpdesk_tickets`

```sql
CREATE TABLE helpdesk_tickets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    number              BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,  -- человекочитаемый TKT-{number}
    subject             VARCHAR(500) NOT NULL,
    description         TEXT         NOT NULL,                       -- первичный текст (тело первого письма / форма)
    description_html    TEXT,                                        -- HTML-вариант, если был в письме (sanitized)
    status              VARCHAR(20)  NOT NULL DEFAULT 'new',
                                                                     -- 'new'|'open'|'pending'|'resolved'|'closed'
    source              VARCHAR(20)  NOT NULL,                       -- 'email'|'web'
    requester_user_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
    requester_email     VARCHAR(320) NOT NULL,                       -- всегда заполняется (для гостей и для отправки писем)
    requester_name      VARCHAR(255),                                -- из From-заголовка или из users.full_name
    assignee_user_id    UUID         REFERENCES users(id) ON DELETE SET NULL,
    assigned_at         TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ,
    closed_by_user_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
    last_activity_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),          -- обновляется при любом сообщении/изменении
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_helpdesk_status
        CHECK (status IN ('new','open','pending','resolved','closed')),
    CONSTRAINT ck_helpdesk_source
        CHECK (source IN ('email','web'))
);

CREATE INDEX ix_helpdesk_tickets_status        ON helpdesk_tickets(status);
CREATE INDEX ix_helpdesk_tickets_assignee      ON helpdesk_tickets(assignee_user_id)
                                                    WHERE assignee_user_id IS NOT NULL;
CREATE INDEX ix_helpdesk_tickets_requester     ON helpdesk_tickets(requester_user_id)
                                                    WHERE requester_user_id IS NOT NULL;
CREATE INDEX ix_helpdesk_tickets_email         ON helpdesk_tickets(LOWER(requester_email));
CREATE INDEX ix_helpdesk_tickets_last_activity ON helpdesk_tickets(last_activity_at DESC);
CREATE INDEX ix_helpdesk_tickets_open_list     ON helpdesk_tickets(status, last_activity_at DESC)
                                                    WHERE status IN ('new','open','pending');
```

### 3.2 `helpdesk_messages`

Сообщения переписки — и публичные (видны клиенту), и внутренние заметки.

```sql
CREATE TABLE helpdesk_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id       UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
    author_user_id  UUID REFERENCES users(id) ON DELETE SET NULL,   -- NULL для гостевых писем
    author_email    VARCHAR(320) NOT NULL,                          -- всегда (для гостей)
    author_name     VARCHAR(255),
    direction       VARCHAR(10)  NOT NULL,                          -- 'inbound' (от клиента) | 'outbound' (от агента)
    visibility      VARCHAR(10)  NOT NULL DEFAULT 'public',         -- 'public' | 'internal' (заметка агентов)
    body_text       TEXT NOT NULL,
    body_html       TEXT,                                            -- если есть; sanitized
    source          VARCHAR(20) NOT NULL,                            -- 'email' | 'web'
    email_message_id VARCHAR(998),                                   -- RFC 5322 Message-ID (для входящих и исходящих)
    in_reply_to     VARCHAR(998),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_helpdesk_messages_direction
        CHECK (direction IN ('inbound','outbound')),
    CONSTRAINT ck_helpdesk_messages_visibility
        CHECK (visibility IN ('public','internal')),
    CONSTRAINT ck_helpdesk_messages_source
        CHECK (source IN ('email','web'))
);

CREATE UNIQUE INDEX uq_helpdesk_messages_email_msg_id
    ON helpdesk_messages(email_message_id)
    WHERE email_message_id IS NOT NULL;
CREATE INDEX ix_helpdesk_messages_ticket ON helpdesk_messages(ticket_id, created_at);
```

**Инвариант:** `internal`-сообщения никогда не отправляются по email и
никогда не возвращаются API инициатору заявки.

### 3.3 `helpdesk_attachments`

```sql
CREATE TABLE helpdesk_attachments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id    UUID NOT NULL REFERENCES helpdesk_tickets(id) ON DELETE CASCADE,
    message_id   UUID REFERENCES helpdesk_messages(id) ON DELETE CASCADE,
    filename     VARCHAR(500) NOT NULL,
    content_type VARCHAR(255) NOT NULL,
    size_bytes   BIGINT       NOT NULL,
    storage_key  VARCHAR(500) NOT NULL,        -- относительный путь в /upload_data/helpdesk/<ticket_id>/<uuid>
    uploaded_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_helpdesk_attachments_ticket  ON helpdesk_attachments(ticket_id);
CREATE INDEX ix_helpdesk_attachments_message ON helpdesk_attachments(message_id);
```

Файлы — на локальном диске (`/upload_data/helpdesk/<ticket_id>/...`),
по аналогии с news/kb-вложениями (см. `./backend/app/core/uploads.py`).

### 3.4 `helpdesk_agents`

```sql
CREATE TABLE helpdesk_agents (
    user_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    added_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notify_new  BOOLEAN NOT NULL DEFAULT TRUE        -- получать уведомление о новой заявке
);
```

### 3.5 `helpdesk_email_log`

Идемпотентность IMAP-ingress.

```sql
CREATE TABLE helpdesk_email_log (
    message_id      VARCHAR(998) PRIMARY KEY,        -- Message-ID входящего письма
    ticket_id       UUID REFERENCES helpdesk_tickets(id) ON DELETE SET NULL,
    message_db_id   UUID REFERENCES helpdesk_messages(id) ON DELETE SET NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          VARCHAR(20) NOT NULL,            -- 'created'|'appended'|'skipped'|'error'
    error           TEXT
);

CREATE INDEX ix_helpdesk_email_log_received ON helpdesk_email_log(received_at DESC);
```

### 3.6 `helpdesk_tickets_archive`

Партиционированная по `closed_at` (по месяцам) копия закрытых тикетов
вместе с их сообщениями (как jsonb), для разгрузки основной таблицы.

```sql
CREATE TABLE helpdesk_tickets_archive (
    id              UUID NOT NULL,
    number          BIGINT NOT NULL,
    subject         VARCHAR(500) NOT NULL,
    requester_email VARCHAR(320) NOT NULL,
    requester_user_id UUID,
    assignee_user_id  UUID,
    opened_at       TIMESTAMPTZ NOT NULL,
    closed_at       TIMESTAMPTZ NOT NULL,
    closed_by_user_id UUID,
    payload         JSONB NOT NULL,        -- {ticket: {...}, messages: [...], attachments_meta: [...]}
    archived_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, closed_at)
) PARTITION BY RANGE (closed_at);
```

Партиции создаются помесячно (по образцу `audit_log`, см.
`./backend/app/services/audit_partitions.py`).

Файлы вложений физически **остаются** в `/upload_data/helpdesk/<ticket_id>/`
ещё N дней (настройка `HELPDESK_ARCHIVE_FILES_TTL_DAYS`, default 180),
после чего удаляются.

### 3.7 Alembic-миграция

Один файл `migrations/versions/XXX_add_helpdesk.py`, создающий все шесть
таблиц + первую партицию архива на текущий месяц.

---

## 4. Backend

### 4.1 Структура файлов

```
backend/app/
├── api/helpdesk/
│   ├── __init__.py
│   ├── tickets.py        # CRUD заявок, переписка
│   ├── agents.py         # admin: управление списком агентов
│   └── settings.py       # admin: IMAP/SMTP-настройки модуля
├── models/helpdesk.py    # ORM: Ticket, Message, Attachment, Agent, EmailLog
├── schemas/helpdesk.py   # Pydantic-схемы
├── services/helpdesk/
│   ├── __init__.py
│   ├── tickets.py        # бизнес-логика тикетов, переходы статусов
│   ├── messages.py       # добавление сообщений (+ обновление last_activity_at)
│   ├── threading.py      # парсинг Message-ID/References/токена темы
│   ├── ingress.py        # IMAP-фетчер + парсинг MIME
│   ├── outbound.py       # сборка исходящих писем (headers + body)
│   ├── attachments.py    # сохранение/раздача файлов
│   ├── archive.py        # перенос closed → archive
│   └── notifications.py  # in-app/email уведомления
└── worker/tasks/helpdesk.py  # cron: poll_helpdesk_mailbox, archive_closed_tickets
```

Роутеры регистрируются в `app/api/__init__.py` с префиксом
`/api/v1/helpdesk`.

### 4.2 Жизненный цикл заявки (статус-машина)

```
            create (email/web)
                  │
                  ▼
                ┌─── new ───┐
   assign agent │           │ first agent reply
                ▼           ▼
              open ─────► open  (status=open после первого ответа агента
                                  и/или назначения)
                  │
   agent reply   │   client reply
       └────────►│◄────────┐
                  │         │
                  ▼         │
              pending ──────┘   (ждём клиента; client reply → open)
                  │
   agent: resolve │
                  ▼
              resolved        (агент закрыл работу, ждём подтверждения)
                  │ admin/agent: close
                  ▼
               closed
                  │ cron archive_closed_tickets (через HELPDESK_ARCHIVE_AFTER_DAYS, default 14)
                  ▼
              archived (запись в helpdesk_tickets_archive,
                        строка из helpdesk_tickets удаляется)

   reopen: closed → open  (только agent/admin или auto-reopen, см. ниже)
```

**Auto-reopen.** Если в течение `HELPDESK_REOPEN_WINDOW_DAYS` (default 7)
после `closed_at` приходит inbound-сообщение по этому тикету (email-thread),
тикет автоматически реоупенится в статус `open`, ответственный получает
in-app уведомление. После архивации reopen невозможен — создаётся новый
тикет с `references_archived_ticket_number` в первом сообщении.

### 4.3 Pydantic-схемы (краткий перечень)

- `TicketCreateIn` — `subject`, `description`, `attachments: list[UploadId]?` (web)
- `TicketOut` — публичная карточка для инициатора (без internal-сообщений)
- `TicketAgentOut` — расширенная для агентов (все сообщения, internal-флаги, email-log)
- `TicketListItemOut` — компактная для списков
- `MessageCreateIn` — `body_text`, `body_html?`, `visibility`,
  `attachments: list[UploadId]?`
- `MessageOut` — `id, author_*, direction, visibility, body_*, created_at,
  attachments`
- `TicketAssignIn` — `assignee_user_id: UUID`
- `TicketStatusIn` — `status: Literal["open","pending","resolved","closed"]`
- `AgentIn` — `user_id`, `notify_new`
- `HelpdeskMailboxSettingsIn` — `imap_host`, `imap_port`, `imap_username`,
  `imap_password` (encrypted), `imap_use_ssl`, `imap_folder` (def `INBOX`),
  `poll_interval_seconds` (def 60), `delete_after_fetch` (def false),
  `support_address` (для From), `support_reply_to` (для Reply-To, может
  включать sub-addressing `support+TKT-{number}@...`).

### 4.4 API endpoints

Префикс `/api/v1/helpdesk`. Все требуют авторизации (`CurrentUser`), кроме
явно указанных.

> **Порядок объявления** (важно, см. `./docs/feedback.md` § 4.4):
> сначала `/tickets/my*`, потом `/tickets` (агентский), потом `/tickets/{id}`.

#### Инициатор (reader+/editor+)

| Метод | Путь | Описание |
|---|---|---|
| `POST`  | `/tickets`               | Создать заявку через веб-форму |
| `GET`   | `/tickets/my`            | Список своих (фильтр `status`, пагинация) |
| `GET`   | `/tickets/my/{id}`       | Своя заявка с публичными сообщениями |
| `POST`  | `/tickets/my/{id}/messages` | Добавить ответ (всегда `direction=inbound`, `visibility=public`) |
| `POST`  | `/tickets/uploads`       | Pre-upload вложения (возвращает `upload_id`) |
| `GET`   | `/attachments/{id}`      | Скачать вложение (ACL: автор заявки или агент) |

#### Агент (флаг `helpdesk_agents`)

| Метод | Путь | Описание |
|---|---|---|
| `GET`   | `/tickets`                       | Все тикеты, фильтры: `status`, `assignee`, `q`, `unassigned=true`, `source` |
| `GET`   | `/tickets/{id}`                  | Карточка с агентским view (все сообщения + email-log) |
| `POST`  | `/tickets/{id}/messages`         | Ответ (`direction=outbound`); поле `visibility=public|internal`; если public — кладём в `email_outbox` (см. § 5) |
| `POST`  | `/tickets/{id}/assign`           | Назначить ответственного (`assignee_user_id`); агент может назначить себя или другого агента; авто-перевод `new → open`, фикс `assigned_at` |
| `POST`  | `/tickets/{id}/take`             | Сокращение для `assign` на текущего пользователя (только если `assignee_user_id IS NULL`) |
| `PATCH` | `/tickets/{id}/status`           | Сменить статус по машине состояний |
| `POST`  | `/tickets/{id}/reopen`           | Реоупен закрытого (если ещё не в архиве) |

#### Админ

| Метод | Путь | Описание |
|---|---|---|
| `GET`    | `/agents`                | Список агентов |
| `POST`   | `/agents`                | Добавить агента |
| `PATCH`  | `/agents/{user_id}`      | Изменить `notify_new` |
| `DELETE` | `/agents/{user_id}`      | Удалить агента |
| `GET`    | `/settings/mailbox`      | Текущие IMAP/SMTP-настройки модуля |
| `PUT`    | `/settings/mailbox`      | Обновить (пароль — write-only, шифруется как в `system_settings`) |
| `POST`   | `/settings/mailbox/test` | Тест IMAP-соединения (вернуть OK / детали ошибки) |
| `GET`    | `/archive`               | Список архивных тикетов (фильтры, пагинация) |
| `GET`    | `/archive/{id}`          | Карточка из архива (read-only) |
| `GET`    | `/email-log`             | Лог входящих писем (отладка) |

### 4.5 ACL правила

- Заявку могут видеть: `requester_user_id == current_user.id`, любой агент,
  любой админ.
- Гостевые заявки (без `requester_user_id`) — только агенты/админ. Если у
  гостя позже появится аккаунт с тем же email, сервис `link_guest_tickets`
  (вызывается при первом логине пользователя) переписывает
  `requester_user_id`.
- `internal`-сообщения не возвращаются на `/tickets/my*`.
- Вложения: токен доступа в URL не используется; проверка через ACL карточки.

### 4.6 Rate limits

- `POST /tickets` — 5/мин/пользователь (анти-спам).
- `POST /tickets/my/{id}/messages` — 20/мин/пользователь.
- `POST /tickets/uploads` — 30/мин/пользователь, max size файла из
  `MAX_UPLOAD_SIZE_MB` (как в news).

---

## 5. Email-интеграция

### 5.1 Inbound: IMAP-фетчер

**Воркер:** `app/worker/tasks/helpdesk.py::poll_helpdesk_mailbox`,
ARQ cron каждые `poll_interval_seconds` (default 60 c, минимум 30, max 600).

Алгоритм:
1. Прочитать настройки из `helpdesk_mailbox_settings` (см. § 4.3).
2. Подключиться по IMAP (`aioimaplib`), выбрать `imap_folder`.
3. `SEARCH UNSEEN` → список UID.
4. Для каждого UID:
   - `FETCH (RFC822)` → байты письма;
   - распарсить через `email.message_from_bytes(..., policy=default)`;
   - извлечь `Message-ID`. Если он уже в `helpdesk_email_log` → пометить
     `\Seen` и пропустить (status=`skipped`).
   - Определить тикет:
     1. По `In-Reply-To` / `References` → ищем в
        `helpdesk_messages.email_message_id`.
     2. По токену `[#TKT-{number}]` в `Subject` (регулярка
        `\[#TKT-(\d+)\]`).
     3. Если ничего — **создать новый тикет** (status=`new`,
        `source=email`).
   - Определить инициатора: `From` → нормализовать email → искать в
     `users.email`. Если найден — `requester_user_id = users.id`. Иначе
     гостевой.
   - Извлечь текст: предпочесть `text/plain`, иначе из `text/html`
     (sanitize → text). HTML тоже сохраняется (sanitized).
   - Извлечь вложения (`Content-Disposition: attachment`),
     сохранить через `services/helpdesk/attachments.py` в
     `/upload_data/helpdesk/<ticket_id>/`. Ограничение —
     `HELPDESK_MAX_ATTACHMENT_MB` (default 25), суммарно —
     `HELPDESK_MAX_TOTAL_INGRESS_MB` (default 50).
   - Создать `helpdesk_messages` (direction=`inbound`, visibility=`public`).
   - Обновить `last_activity_at`, при необходимости (`pending` → `open`,
     `closed → open` в окне reopen) сменить статус.
   - Триггер уведомлений (см. § 6).
   - Записать в `helpdesk_email_log` (status=`created` или `appended`).
   - Пометить письмо `\Seen` (и `\Deleted`, если включено
     `delete_after_fetch`).
5. Все ошибки парсинга — пишем в лог + `helpdesk_email_log.status='error'`,
   письмо помечаем `\Seen`, но не удаляем.

### 5.2 Outbound: исходящие письма

Идём через существующий `email_outbox` (см. `./docs/email.md`), добавляется
новый `kind = 'helpdesk'`.

В `payload` кладём:
```json
{
  "ticket_id": "uuid",
  "ticket_number": 123,
  "message_id_header": "<ticket-123-msg-uuid@portal>",
  "in_reply_to": "<...>",
  "references": ["<...>", "..."],
  "reply_to": "support+TKT-123@company.local",
  "attachments": [{"storage_key": "...", "filename": "...", "content_type": "..."}]
}
```

Диспетчер `process_email_outbox` расширяется ветвью `kind == 'helpdesk'`:
собирает `multipart/mixed` (если есть вложения) или `multipart/alternative`,
проставляет заголовки `Message-ID`, `In-Reply-To`, `References`, `Reply-To`,
`Subject = "[#TKT-{number}] {original_subject}"`.

После успешной отправки `email_message_id` исходящего письма
**сохраняется в `helpdesk_messages.email_message_id`** через callback
`on_sent` (новая точка расширения в outbox-диспетчере) или через `payload →
related_resource_*` + post-processing.

### 5.3 Безопасность

- HTML входящих писем санитизируем через существующий
  `app/core/sanitize.py` (allowlist тегов как в news/kb).
- DKIM/SPF/DMARC проверка — не реализуем, полагаемся на корпоративный
  Postfix (он уже фильтрует).
- Anti-loop: если `From` совпадает с `support_address` или письмо содержит
  `Auto-Submitted: auto-*`, `Precedence: bulk/list/junk`, или
  `X-Auto-Response-Suppress` — **не создаём** тикет/сообщение, лог
  `skipped`.

---

## 6. Уведомления

Все уведомления — единым паттерном через `services/notifications.py`
(`create_notification` + Redis SSE) + `email_outbox`. Шаблоны лежат в
`base_data/email_templates/helpdesk/*.html` (новая папка по аналогии с
существующими).

| Событие | Получатели | In-app | Email |
|---|---|---|---|
| Новая заявка (email или web) | Все агенты с `notify_new=true` | ✅ | ✅ |
| Заявка взята в работу / реассайн | Инициатор + новый агент + старый агент (если был) | ✅ | ✅ инициатору (с ФИО ответственного), ✅ новому агенту |
| Новое публичное сообщение от агента | Инициатор | ✅ | ✅ (это и есть «ответ») |
| Новое сообщение от клиента (email/web) | Текущий ответственный (или все агенты, если не назначен) | ✅ | ✅ |
| Статус → `resolved` | Инициатор | ✅ | ✅ |
| Статус → `closed` | Инициатор | ✅ | ✅ (с уведомлением о возможности reopen в течение N дней) |
| Auto-reopen | Ответственный | ✅ | ✅ |
| Internal note | Только агенты (in-app) | ✅ | ❌ |

Шаблон уведомления инициатору при взятии в работу обязательно содержит:
`"Ваша заявка №{number} «{subject}» взята в работу. Ответственный: {assignee.full_name}."`.

---

## 7. Frontend

### 7.1 Структура

```
frontend/src/
├── api/helpdesk.ts                  # типы + HTTP-вызовы
├── queries/helpdesk.ts              # TanStack Query-хуки
├── pages/
│   ├── HelpdeskMyTicketsPage.vue    # /helpdesk/my — список своих
│   ├── HelpdeskTicketDetailPage.vue # /helpdesk/tickets/:id — карточка (видна и инициатору, и агенту, с разным UI)
│   ├── HelpdeskAgentInboxPage.vue   # /helpdesk — агентский список (только агентам)
│   └── admin/HelpdeskSettingsPage.vue  # /admin/helpdesk — агенты, IMAP, архив
├── components/helpdesk/
│   ├── TicketCreateModal.vue
│   ├── TicketListTable.vue
│   ├── TicketMessageList.vue
│   ├── TicketReplyForm.vue          # с переключателем public/internal для агентов
│   ├── TicketAssignSelect.vue
│   ├── TicketStatusBadge.vue
│   ├── TicketAttachmentList.vue
│   └── HelpdeskAgentsManager.vue
└── stores/helpdesk.ts (если потребуется — например, для фильтров инбокса)
```

### 7.2 Маршруты (Vue Router)

| Path | Guard |
|---|---|
| `/helpdesk/my` | `requireAuth` |
| `/helpdesk/my/:id` | `requireAuth` (но карточка отдаёт только свои) |
| `/helpdesk/new` | `requireAuth` (или модалка с любой страницы) |
| `/helpdesk` | `requireAgentOrAdmin` (агент инбокс) |
| `/helpdesk/tickets/:id` | `requireAgentOrAdmin` |
| `/admin/helpdesk` | `requireAdmin` |

Флаг «является ли пользователь агентом» прокидывается в `auth store` через
`bootstrap` (см. `./backend/app/api/bootstrap.py`) — добавить поле
`is_helpdesk_agent: bool` в ответ.

### 7.3 UI-фичи

- **Список своих** (`MyTicketsPage`): таблица с номером, темой, статусом,
  ответственным, временем последнего сообщения. Фильтр `status`.
- **Карточка** (детальная): шапка (номер, тема, статус, инициатор,
  ответственный), таймлайн сообщений (свои/агента/системные «взял в
  работу», «закрыто»), форма ответа с вложениями.
- **Агентский инбокс**: фильтры `unassigned`, `assigned to me`, `status`,
  поиск по теме/тексту/email. Кнопка «Взять» на нераспределённых.
- **Карточка для агента**: дополнительно — кнопки `Assign`, `Status`,
  `Reopen`, переключатель `internal note`, отображение email-метаданных
  (Message-ID, From) для каждого сообщения, список вложений с превью.
- **Админка**: вкладки `Agents`, `Mailbox`, `Archive`. На вкладке Mailbox
  кнопка «Проверить соединение» вызывает `/settings/mailbox/test`.

### 7.4 Уведомления и точка входа в шапке

В существующий `NotificationsDropdown.vue` добавить тип `helpdesk_*`
(маршрутизация по клику ведёт на карточку тикета).

В главное меню (`useAppMenu.ts`) добавить пункт «Поддержка» (виден всем,
ведёт на `/helpdesk/my`) и пункт «Инбокс поддержки» (только агентам/админу).

---

## 8. Архивирование

ARQ cron `archive_closed_tickets` (default `cron(hour=3, minute=20)`):

1. Найти тикеты со статусом `closed` и `closed_at < NOW() - INTERVAL
   '{HELPDESK_ARCHIVE_AFTER_DAYS} days'` (default 14).
2. Для каждого:
   - Прочитать ticket + все messages + meta вложений.
   - Сериализовать в jsonb и вставить в `helpdesk_tickets_archive`
     (партиция по `closed_at`).
   - Удалить строку из `helpdesk_tickets` (сообщения и вложения уйдут по
     CASCADE).
3. Партиции архива создаются автоматически (`ensure_partition_for(date)`,
   по образцу `audit_partitions`).

Отдельный cron `cleanup_helpdesk_attachments` (раз в сутки):
удалить файлы из `/upload_data/helpdesk/<ticket_id>/`, у которых тикет
архивирован > `HELPDESK_ARCHIVE_FILES_TTL_DAYS` (default 180) дней назад.

Просмотр архива — только админам (`GET /api/v1/helpdesk/archive`).
Поиск по архиву — простой ILIKE по `subject` и `requester_email`
(FTS не нужен в MVP).

---

## 9. Конфигурация (env / system_settings)

Все настройки — в существующей таблице `system_settings` (см.
`./backend/app/core/system_config.py`), новые ключи:

| Ключ | Default | Описание |
|---|---|---|
| `HELPDESK_ENABLED` | `false` | Включает модуль (роуты, меню, воркеры) |
| `HELPDESK_SUPPORT_ADDRESS` | — | From-адрес для исходящих (`support@company.local`) |
| `HELPDESK_SUPPORT_REPLY_TO_PATTERN` | `support+TKT-{number}@company.local` | Reply-To с sub-addressing |
| `HELPDESK_IMAP_HOST` / `_PORT` / `_USERNAME` / `_PASSWORD` / `_USE_SSL` / `_FOLDER` | — | IMAP credentials |
| `HELPDESK_IMAP_POLL_INTERVAL_SECONDS` | `60` | Период polling |
| `HELPDESK_IMAP_DELETE_AFTER_FETCH` | `false` | Удалять письмо с сервера после обработки |
| `HELPDESK_MAX_ATTACHMENT_MB` | `25` | Максимум одного вложения |
| `HELPDESK_MAX_TOTAL_INGRESS_MB` | `50` | Максимум суммы вложений в одном письме |
| `HELPDESK_ARCHIVE_AFTER_DAYS` | `14` | Через сколько после `closed` уходит в архив |
| `HELPDESK_ARCHIVE_FILES_TTL_DAYS` | `180` | Через сколько физически удаляются вложения архива |
| `HELPDESK_REOPEN_WINDOW_DAYS` | `7` | Окно auto-reopen после закрытия |

---

## 10. Тестирование

Расширяем существующую тест-инфраструктуру (см. `./docs/testing.md`).

### Backend

- **Unit** (`backend/tests/unit/helpdesk/`):
  - `threading.py`: тесты парсинга `Message-ID`/`References`/токена темы;
  - `outbound.py`: сборка MIME с правильными заголовками;
  - статус-машина: все валидные/невалидные переходы;
  - ACL: инициатор не видит internal-сообщения и чужие тикеты.
- **Integration** (`backend/tests/integration/helpdesk/`):
  - polling: testcontainers-IMAP (например, `greenmail` через docker) —
    шлём письмо → проверяем создание тикета и messages;
  - threading: ответ на тикет → matching по `In-Reply-To`;
  - гостевой → создание заявки без `user_id`, последующий `link_guest_tickets`;
  - архивирование: тикет старше N дней попадает в архив, файлы удаляются после TTL;
  - end-to-end: web-create → агент `take` → reply → user reply → close → archive.
- **Security**:
  - HTML-санитизация входящих писем (XSS-векторы);
  - rate limit на `POST /tickets`;
  - вложения: запрет path traversal в `filename`;
  - запрет на чтение чужих вложений (`GET /attachments/{id}`).

### Frontend

- **Unit (vitest)**: компоненты `TicketReplyForm`, `TicketStatusBadge`,
  `TicketListTable` (рендеринг по props, переключение internal/public).
- **E2E (playwright)**: полный сценарий «создание → ответ агента → ответ
  клиента → закрытие».

---

## 11. Метрики, аудит, наблюдаемость

- **audit_log**: пишем события `helpdesk.ticket.created`,
  `.assigned`, `.status_changed`, `.message_added`, `.archived`,
  `.agent_added`, `.agent_removed`, `.mailbox_settings_changed`.
- **Prometheus** (см. `./backend/app/core/metrics.py`):
  - `helpdesk_tickets_total{status}` — gauge;
  - `helpdesk_ingress_messages_total{result}` — counter
    (`created`/`appended`/`skipped`/`error`);
  - `helpdesk_imap_poll_duration_seconds` — histogram;
  - `helpdesk_outbound_messages_total{result}` — counter.
- **Логи** (structlog): каждое поллирование IMAP пишет summary
  (fetched=N, created=N, appended=N, errors=N).

---

## 12. Этапы реализации

| Этап | Содержание | Готовность |
|---|---|---|
| **1. БД + модели** | Миграция, ORM, минимальные Pydantic-схемы | независимо |
| **2. Web-flow** | `POST /tickets`, `GET /tickets/my*`, `POST messages`, базовый UI инициатора | ценность сразу |
| **3. Агенты + инбокс** | `helpdesk_agents`, агентские API, агентский UI, assign/take/status | основная функциональность |
| **4. Уведомления** | in-app + email через outbox, шаблоны | ценность сразу |
| **5. Email ingress (IMAP)** | воркер + threading + ingress-логика + админ-настройки + log | замена OTRS-flow |
| **6. Email outbound** | расширение outbox-диспетчера ветвью `kind=helpdesk`, заголовки, sub-addressing | двусторонний thread |
| **7. Вложения** | upload + ingress-attachments + раздача | полный функциональный паритет с OTRS |
| **8. Архив** | таблица + партиции + cron + админ-вьюер | очистка основной таблицы |
| **9. Метрики, аудит, тесты** | Prometheus, audit_log, unit/integration/e2e | боевая готовность |

Этап 5 (IMAP) можно временно пропустить — модуль будет работать как
веб-only helpdesk; включение IMAP — переключение `HELPDESK_ENABLED` +
`HELPDESK_IMAP_*`.

---

## 13. Открытые вопросы / решения, которые могут потребовать уточнения позже

1. **Категории и приоритеты** — в MVP не вводим; можно добавить
   опционально в этапе 9 (минорно — поля `category VARCHAR(50)` и
   `priority VARCHAR(20)` + фильтры).
2. **SLA-таймеры** — в MVP не вводим (требует отдельной таблицы политик
   и алёртов); вынесем во вторую итерацию.
3. **Шаблоны ответов агентов (canned responses)** — отложено.
4. **Слияние тикетов (merge)** — отложено (часто нужно, но не критично).
5. **Multi-mailbox** (несколько support-ящиков с разной маршрутизацией) —
   отложено; в MVP один ящик.
6. **OTRS-импорт исторических заявок** — отдельный скрипт, не часть
   основного MVP; формат миграции уточнить, когда понадобится.
7. **Удаление inbound-писем с IMAP-сервера** (`delete_after_fetch`) —
   решение оставлено за админом, default `false` (сохраняем письма в
   ящике для backup).
