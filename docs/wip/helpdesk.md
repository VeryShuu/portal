# ТЗ: Модуль технической поддержки (Helpdesk)

> ⚠️ **ИСТОРИЧЕСКИЙ ДОКУМЕНТ (ТЗ от 2026-06-30).** Модуль реализован и итерационно
> дорабатывался — этот файл фиксирует исходное ТЗ, на основе которого шла
> разработка, и **НЕ отражает текущее состояние кода**. Известные расхождения с
> реализацией (на момент 2026-07):
> - Статус-машина упрощена: статус `resolved` **упразднён** (миграция 079),
>   единый финал — `closed`. Соответственно cron `auto_close_resolved_tickets`
>   и константа `HELPDESK_RESOLVED_AUTO_CLOSE_DAYS` удалены.
> - Инбокс агента переработан в **двухблочный вид** (Новые / В работе) +
>   переключатель мои/все + отдельная страница архива `/helpdesk/archive`
>   (вместо плоского списка с radio-фильтрами).
> - Добавлены: rich-редактор TipTap для ответов, inline-картинки
>   (`/tickets/{id}/inline-media`), FTS-поиск (миграция 078), cid:-встраивание
>   картинок в исходящие письма, унифицированный префикс «Сообщение от — ».
>
> **Актуальная документация: [`docs/helpdesk.md`](../helpdesk.md).** Этот файл
> сохранён как исторический артефакт (исходное ТЗ, обоснования решений);
> использовать только в этом качестве, не как спецификацию API/БД/статус-машины.
>
> ---
>
> ✅ **Сверено с кодовой базой (review-pass).** Пути, имена функций и паттерны
> проверены по факту; расхождения с реальным кодом исправлены и помечены
> блоками ⚠️ «проверено по коду». Ключевые поправки: нумерация миграции
> (`075`, `down_revision='074'`, ручной `op.execute`), runtime-параметры —
> константы в `constants.py` (не `system_config`), async-сборка helpdesk-MIME
> в outbox (существующий `_build_mime` синхронный), отсутствие папки
> email-шаблонов (тела писем — инлайн), необходимость завести флаг
> `modules.helpdesk` и guard `requiresHelpdeskAgent`, отсутствие в зависимостях
> `cryptography`/`aioimaplib`.
>
> ✅ **Архитектурные решения зафиксированы (review-pass 2).** Открытые вопросы
> первого анализа разрешены по best practices helpdesk-систем (Zammad,
> FreeScout, OTRS, Request Tracker): reopen-window привязан только к `closed`
> (из `resolved` — безусловный reopen + cron `auto_close_resolved_tickets`),
> добавлена колонка `references_archived_ticket_number`, зафиксирован
> канонический формат `Message-ID`, описано стартовое состояние
> mailbox-settings, уточнена точка вызова `link_guest_tickets` (только OIDC,
> в local.py upsert'а нет) и реальный partition-хелпер (`ensure_partitions`).
> См. правки в §§ 1.3.3, 3.1, 3.6, 3.7, 4.2, 4.5, 5.1, 5.2, 7.2, 8, 9.3, 11.
>
> ✅ **Смена хранилища вложений (review-pass 3).** По решению владельца проекта
> helpdesk-вложения больше **не** хранятся в Nextcloud. Файлы лежат локально в
> `/data/helpdesk/TKT-{number}/{file}` — по образцу feedback
> (`/data/feedback/files/`). Upload — streaming через `stream_upload_to_path`
> (MIME через `python-magic`, path-traversal guard), download —
> `StreamingResponse` через `aiofiles` (НЕ `X-Accel-Redirect`, НЕ `FileResponse`,
> НЕ Nextcloud). Схема `helpdesk_attachments` вычищена от Nextcloud-полей
> (`storage_backend`/`storage_key` → `filename`/`original_name`). Миграция
> `075` ещё не в проде — правки in-place, новой миграции не нужно. Файлы
> удаляются с диска по CASCADE вместе с тикетом/сообщением. См. правки в
> §§ 1.3.2, 1.3.4, 3.3, 3.7, 4.5, 5.2, 12.1, 12.2.

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
3. **Outgoing-письма заголовки.** Каждое исходящее письмо тикета содержит
   канонический (фиксированный, не менять) набор заголовков:
   - `Message-ID: <tkn-{ticket_number}-{message_uuid}@{support_domain}>`,
     где `ticket_number` — bigint из `helpdesk_tickets.number`, `message_uuid`
     — `helpdesk_messages.id` (гарантия глобальной уникальности), а
     `support_domain` — доменная часть `support_address` (после `@`). RFC 5322
     требует валидный домен в msg-id: если `support_domain` пуст/невалиден —
     письмо не отправлять (outbox → `error`), не подставлять `localhost`.
   - `In-Reply-To` / `References`: цепочка `Message-ID` предшествующих
     сообщений тикета (берётся из `helpdesk_messages.email_message_id`).
   - `Reply-To: support+TKT-{ticket_number}@{support_domain}` (sub-addressing —
     запасной matching, если почтовик клиента оборвёт `In-Reply-To`).
   - `Subject: "[#TKT-{ticket_number}] {original_subject}"`.
   Этот формат — единственный источник matching’а входящих писем по
   `Message-ID` (см. §5.1); противоречивых шаблонов заводить нельзя.
4. **Идемпотентность ingress.** Для каждого письма сохраняется его
   `Message-ID` или synthetic id в таблице `helpdesk_email_log` с уникальным
   индексом — повторное скачивание того же письма не создаёт дубль.
5. **Статусная модель** (минимальный набор, проверенный практикой):
   `new` → `open` → `pending` → `resolved` → `closed`. Архивирование — это
   перенос в `helpdesk_tickets_archive`, а не значение поля `status`.
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

### 1.3 Зафиксированные решения для реализации

Эти решения обязательны для всех этапов и снимают неоднозначности для простой
модели-исполнителя.

1. **MVP web-first.** Сначала реализуется backend web-flow без IMAP и frontend,
   затем agent/admin backend, затем вложения/уведомления/outbound, затем IMAP и
   архив. Frontend реализуется отдельными этапами после зелёного backend.
2. **Вложения хранятся локально.** Пользовательские файлы helpdesk лежат в
   локальной папке `/data/helpdesk/TKT-{number}/{file}` — по образцу feedback
   (`/data/feedback/files/`, модель `FeedbackAttachment`). Nextcloud для
   helpdesk-вложений **не используется**. Имя файла на диске —
   `{uuid}_{sanitized}`, оригинальное имя сохраняется в `original_name`.
   Upload — streaming через `stream_upload_to_path(...)` из
   `./backend/app/core/uploads.py` (MIME через `python-magic` по первым байтам,
   не доверять `Content-Type` клиента), лимит — константа
   `HELPDESK_MAX_ATTACHMENT_MB` (default 25). Папка тикета — по
   человекочитаемому `TKT-{number}` (IDENTITY, стабилен для тикета).
3. **Pre-upload в MVP не используется.** Нет отдельного `upload_id` и таблицы
   временных upload’ов. До этапа вложений endpoints принимают JSON без файлов.
   На этапе вложений `POST /tickets` и `POST /tickets/*/messages` расширяются
   до `multipart/form-data` с полями формы и `files: list[UploadFile]`.
4. **Скачивание вложений — `StreamingResponse` из локального файла.** Читать
   файл с диска через `aiofiles` (chunked, `CHUNK_SIZE`), отдавать
   `StreamingResponse` с заголовками `Content-Type`, `Content-Disposition`
   (RFC 5987, хелпер `_rfc5987_filename` из `./backend/app/api/kb/_common.py`),
   `X-Content-Type-Options: nosniff`. **НЕ** использовать `FileResponse` и
   **НЕ** использовать `X-Accel-Redirect` (для helpdesk это явно запрещено —
   отличие от feedback, который идёт через nginx internal-redirect).
5. **Пароль IMAP шифруется отдельной утилитой.** На этапе settings создать
   `./backend/app/core/secret_crypto.py` с `encrypt_secret()` / `decrypt_secret()`.
   Ключ шифрования детерминированно получается из `Settings.secret_key`
   (поле существует, `min_length=32` — проверено в `./backend/app/core/config.py`)
   через SHA-256 → urlsafe base64 и используется с `cryptography.fernet.Fernet`.
   ⚠️ Пакет `cryptography` **сейчас отсутствует** в зависимостях backend
   (проверено по `./backend/pyproject.toml`) — на этапе settings его нужно
   добавить. В API пароль write-only; в ответах только `imap_password_set: bool`.
6. **Dynamic IMAP interval.** ARQ cron регистрируется статически раз в 30 секунд.
   Внутри задачи читается `poll_interval_seconds` из БД и проверяется Redis-key
   `helpdesk:imap:last_poll_at`; если интервал ещё не прошёл — задача выходит.
7. **Distributed lock для IMAP.** Перед polling брать Redis lock
   `helpdesk:imap:poll_lock` с TTL 5 минут. Если lock не получен — задача выходит.
8. **Письма без `Message-ID`.** Не падать. Для идемпотентности строить
   synthetic id: `<synthetic:{sha256(mailbox, uid, date, from, subject, size)}>`
   и писать его в `helpdesk_email_log.message_id` и `helpdesk_messages.email_message_id`.
9. **`archived` не является статусом основной таблицы.** В `helpdesk_tickets.status`
   допустимы только `new/open/pending/resolved/closed`. Архивный тикет удалён из
   основной таблицы и доступен только через `helpdesk_tickets_archive`.

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
    references_archived_ticket_number BIGINT,                         -- если тикет — продолжение архивного (см. §4.2); не FK (архив в партиционной таблице)
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
CREATE INDEX ix_helpdesk_tickets_ref_archive   ON helpdesk_tickets(references_archived_ticket_number)
                                                    WHERE references_archived_ticket_number IS NOT NULL;
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
    filename     VARCHAR(500) NOT NULL,        -- имя на диске: {uuid}_{sanitized}
    original_name VARCHAR(500) NOT NULL,       -- исходное имя (для Content-Disposition)
    content_type VARCHAR(255) NOT NULL,        -- MIME через python-magic
    size_bytes   BIGINT       NOT NULL,
    uploaded_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_helpdesk_attachments_ticket  ON helpdesk_attachments(ticket_id);
CREATE INDEX ix_helpdesk_attachments_message ON helpdesk_attachments(message_id);
```

Файлы — **локально** в `/data/helpdesk/TKT-{number}/{filename}` (Nextcloud не
используется — см. §1.3.2). Образец — feedback (`FeedbackAttachment`,
`/data/feedback/files/`). Для upload использовать `stream_upload_to_path(...)`
из `./backend/app/core/uploads.py` (streaming + лимит размера + MIME через
`python-magic`); path-traversal guard — `re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", filename)`.
При удалении тикета/сообщения (CASCADE) файлы удаляются с диска сервисом
(`unlink(missing_ok=True)`), асинхронных БД-триггеров нет.

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
    message_id      VARCHAR(998) PRIMARY KEY,        -- Message-ID или synthetic id входящего письма
    ticket_id       UUID REFERENCES helpdesk_tickets(id) ON DELETE SET NULL,
    message_db_id   UUID REFERENCES helpdesk_messages(id) ON DELETE SET NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          VARCHAR(20) NOT NULL,            -- 'created'|'appended'|'skipped'|'error'
    error           TEXT
);

CREATE INDEX ix_helpdesk_email_log_received ON helpdesk_email_log(received_at DESC);
```

### 3.6 `helpdesk_mailbox_settings`

Отдельная таблица для IMAP/SMTP-настроек helpdesk (single-row конфиг;
`id=1` в MVP), чтобы не смешивать модульный секретный конфиг с общими
системными настройками.

```sql
CREATE TABLE helpdesk_mailbox_settings (
    id                    SMALLINT PRIMARY KEY DEFAULT 1,
    imap_host             VARCHAR(255) NOT NULL,
    imap_port             INTEGER      NOT NULL DEFAULT 993,
    imap_username         VARCHAR(255) NOT NULL,
    imap_password_enc     TEXT         NOT NULL,            -- encrypted at rest
    imap_use_ssl          BOOLEAN      NOT NULL DEFAULT TRUE,
    imap_folder           VARCHAR(255) NOT NULL DEFAULT 'INBOX',
    poll_interval_seconds INTEGER      NOT NULL DEFAULT 60, -- min 30, max 600
    delete_after_fetch    BOOLEAN      NOT NULL DEFAULT FALSE,
    support_address       VARCHAR(320) NOT NULL,
    support_reply_to      VARCHAR(320),
    updated_by_user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_helpdesk_mailbox_singleton CHECK (id = 1),
    CONSTRAINT ck_helpdesk_mailbox_poll_interval
        CHECK (poll_interval_seconds BETWEEN 30 AND 600)
);
```

> **Стартовое состояние (best practice).** Миграция **не** засевает
> singleton-строку: `imap_password_enc NOT NULL` делает это невозможным без
> пароля. Строка создаётся при первом `PUT /settings/mailbox` (upsert).
> `GET` до первого `PUT` возвращает HTTP 200 с `configured: false`,
> `imap_password_set: false` и остальными полями по умолчанию (`null`) — UI
> показывает «ящик не настроен». `PUT`-семантика пароля (write-only): при
> обновлении `imap_password` опущен/`null` ⇒ оставить прежний шифр (не
> перезаписывать); при создании записи — поле обязательно. В ответах пароль
> никогда не возвращается, только `imap_password_set: bool`.

### 3.7 `helpdesk_tickets_archive`

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

Партиции создаются помесячно по образцу `audit_log`. Реальный хелпер —
`ensure_partitions(conn, months_ahead=3)` в
`./backend/app/services/audit_partitions.py` (принимает raw-`asyncpg.Connection`,
создаёт партиции на N месяцев вперёд через `FOR VALUES FROM (...)`); cron-обёртка —
`create_next_audit_partition` в `./backend/app/worker/tasks/audit.py`. Для архива
helpdesk заводится аналог `ensure_helpdesk_archive_partitions(conn, months_ahead)` +
cron `create_next_helpdesk_archive_partition` (см. §8). Партиционирование —
`PARTITION BY RANGE (closed_at)`, имя партиции — `helpdesk_tickets_archive_YYYY_mm`.

Файлы вложений физически **остаются** в локальной папке
`/data/helpdesk/TKT-{number}/` ещё N дней (настройка
`HELPDESK_ARCHIVE_FILES_TTL_DAYS`, default 180), после чего вся папка тикета
удаляется с диска cron’ом `cleanup_helpdesk_attachments` (см. §8). Nextcloud
для helpdesk-вложений не используется.

### 3.8 Alembic-миграция

Один файл `migrations/versions/075_add_helpdesk.py`, создающий все семь
таблиц + первую партицию архива на текущий месяц.

**Конвенция нумерации (проверено по факту):** миграции пронумерованы
последовательно (`...073`, `074`), `revision`/`down_revision` — короткие
строки (`revision: str = '075'`, `down_revision: str | None = '074'`).
Текущий head — `074_add_kb_url_to_service_links`, поэтому helpdesk-миграция
получает `revision='075'`, `down_revision='074'`. Перед написанием свериться
с фактическим head: `ls backend/migrations/versions | sort | tail -1`.

**Способ написания:** миграцию писать **вручную через `op.execute("""...""")`**
с DDL из §3, а **не** через `alembic revision --autogenerate`. Autogenerate не
поддерживает `GENERATED ALWAYS AS IDENTITY`, партиционирование
(`PARTITION BY RANGE`), частичные индексы (`... WHERE ...`) и `CHECK`-констрейнты
из этого ТЗ — он сгенерирует неполный/неверный результат. `downgrade()` —
`DROP TABLE ... CASCADE` в обратном порядке зависимостей.

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
├── models/helpdesk.py    # ORM: Ticket, Message, Attachment, Agent, EmailLog, MailboxSettings
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
└── worker/tasks/helpdesk.py  # cron: poll, auto_close_resolved, archive, partition, cleanup
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
              open ─────► pending  (после публичного ответа агента
                                     ждём клиента)
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
                   │ admin/agent: close  ИЛИ  cron auto_close_resolved_tickets
                   ▼                  (через HELPDESK_RESOLVED_AUTO_CLOSE_DAYS, default 7)
                closed
                   │ cron archive_closed_tickets (через HELPDESK_ARCHIVE_AFTER_DAYS, default 14)
                   ▼
               archived (запись в helpdesk_tickets_archive,
                         строка из helpdesk_tickets удаляется)

   reopen: resolved → open (любой ответ клиента, без окна)
           closed   → open (agent/admin ИЛИ auto-reopen в окне HELPDESK_REOPEN_WINDOW_DAYS, см. ниже)
```

#### 4.2.1 Строгие переходы статусов

| From | Действие | To | Кто может | Побочные эффекты |
|---|---|---|---|---|
| — | create email/web | `new` | requester/email ingress | создаётся первое public inbound-сообщение |
| `new` | assign/take | `open` | agent/admin | `assignee_user_id`, `assigned_at`, уведомления |
| `new` | первый public ответ агента | `pending` | agent/admin | если нет assignee — назначить текущего агента (+`assigned_at`), ждать клиента |
| `open` | public ответ агента | `pending` | agent/admin | email инициатору через outbox |
| `pending` | public ответ агента | `pending` | agent/admin | email инициатору через outbox |
| `pending` | ответ клиента email/web | `open` | requester/email ingress | уведомить assignee или всех agents |
| `resolved` | ответ клиента (веб/email) | `open` | requester/email ingress | auto-reopen без окна (ответ = «не подтверждено»); `closed_*` отсутствуют |
| `open`/`pending` | resolve | `resolved` | agent/admin | уведомить инициатора; старт отсчёта для auto-close |
| `resolved` | cron `auto_close_resolved_tickets` (нет активности ≥ `HELPDESK_RESOLVED_AUTO_CLOSE_DAYS`) | `closed` | worker | `closed_at=NOW()`, `closed_by_user_id=NULL` (system), уведомить инициатора |
| `resolved` | close (вручную) | `closed` | agent/admin | `closed_at`, `closed_by_user_id`, уведомить инициатора |
| `closed` | reopen | `open` | agent/admin или auto-reopen window | очистить `closed_at`/`closed_by_user_id` |
| `closed` | archive cron | archive table | worker | удалить из `helpdesk_tickets` после записи архива |

Запрещённые переходы возвращают `409 Conflict` с текущим статусом и разрешёнными
следующими действиями. `internal`-сообщения не меняют статус, но обновляют
`last_activity_at`.

**Auto-reopen (best-practice, привязка к `closed_at`).** Статусы разделяют два
семантических состояния, поэтому правила разные (отдельная колонка `resolved_at`
не нужна):
- `resolved` (работа сделана, ждём подтверждения клиента) → **любой** inbound-ответ
  клиента реопенит тикет в `open` **без временного окна**: ответ клиента — это и
  есть сигнал «не подтверждено». Чтобы статус `resolved` не висел бесконечно,
  cron `auto_close_resolved_tickets` переводит `resolved → closed` при
  `last_activity_at < NOW() - HELPDESK_RESOLVED_AUTO_CLOSE_DAYS` (default 7) —
  см. §8.
- `closed` → inbound-ответ клиента реопенит в `open` **только** в течение
  `HELPDESK_REOPEN_WINDOW_DAYS` (default 7) после `closed_at`. Ответственный
  получает in-app уведомление. В обоих случаях `closed_at`/`closed_by_user_id`
  очищаются, статус → `open`.
- После архивации reopen невозможен: inbound-ответ по архивному тикету создаёт
  **новый** тикет, в `references_archived_ticket_number` записывается номер
  архивного (см. §3.1), а тело первого сообщения упоминает «продолжение TKT-…».

### 4.3 Pydantic-схемы (краткий перечень)

- `TicketCreateIn` — `subject`, `description` (web; без attachments до этапа 4)
- `TicketOut` — публичная карточка для инициатора (без internal-сообщений)
- `TicketAgentOut` — расширенная для агентов (все сообщения, internal-флаги, email-log)
- `TicketListItemOut` — компактная для списков
- `MessageCreateIn` — `body_text`, `body_html?`, `visibility` (attachments
  добавляются на этапе 4 через `multipart/form-data`, не через `UploadId`)
- `MessageOut` — `id, author_*, direction, visibility, body_*, created_at,
  attachments`
- `TicketAssignIn` — `assignee_user_id: UUID`
- `TicketStatusIn` — `status: Literal["open","pending","resolved","closed"]`
- `AgentIn` — `user_id`, `notify_new`
- `HelpdeskMailboxSettingsIn` — `imap_host`, `imap_port`, `imap_username`,
  `imap_password` (plaintext, шифруется сервисом через `secret_crypto`; при
  обновлении опционален — `None` = «оставить прежний», при создании обязателен),
  `imap_use_ssl`, `imap_folder` (def `INBOX`), `poll_interval_seconds` (def 60),
  `delete_after_fetch` (def false), `support_address` (для `From` и как источник
  `{support_domain}` для `Message-ID`/`Reply-To`, см. §1.3.3), `support_reply_to`
  (для `Reply-To`; per-ticket подставляется `support+TKT-{number}@{support_domain}`).
- `HelpdeskMailboxSettingsOut` — все поля кроме пароля; `imap_password_set: bool`
  и `configured: bool` (false, если строка ещё не создана — см. §3.6). `GET`
  до первого `PUT` возвращает дефолт с `configured=false`.

### 4.3.1 Инвариант первого сообщения

Чтобы не было дублирования данных в таймлайне:

1. При создании тикета (и `source=web`, и `source=email`) **всегда** создаётся
   первая запись в `helpdesk_messages` (`direction=inbound`, `visibility=public`).
2. Поля `helpdesk_tickets.description` / `description_html` хранят копию
   первичного текста для быстрых списков/поиска и совместимости, но в UI
   таймлайн строится только по `helpdesk_messages`.
3. Для этого первого сообщения применяется тот же threading-контракт, что и
   для остальных (включая `email_message_id`, если источник email).

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
| `GET`   | `/attachments/{id}`      | Скачать вложение `StreamingResponse` из локального файла (ACL: автор заявки или агент) |

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
| `PUT`    | `/settings/mailbox`      | Обновить (пароль — write-only, шифруется через существующие crypto-утилиты backend) |
| `POST`   | `/settings/mailbox/test` | Тест IMAP-соединения (вернуть OK / детали ошибки) |
| `GET`    | `/archive`               | Список архивных тикетов (фильтры, пагинация) |
| `GET`    | `/archive/{id}`          | Карточка из архива (read-only) |
| `GET`    | `/email-log`             | Лог входящих писем (отладка) |

### 4.5 ACL правила

- Заявку могут видеть: `requester_user_id == current_user.id`, любой агент,
  любой админ.
- Гостевые заявки (без `requester_user_id`) — только агенты/админ. Если у
  гостя позже появится аккаунт с тем же email, сервис `link_guest_tickets`
  переписывает `requester_user_id`. **Точка вызова:** сразу после
  `_upsert_user(...)` в OIDC-callback (`./backend/app/api/auth/oidc.py:196`,
  до `db.commit()`) — это единственный флоу, где материализуется новый аккаунт.
  ⚠️ В локальном входе (`app/api/auth/local.py`) **upsert’а нет** (логин
  аутентифицирует уже существующего пользователя через `update … last_login_at`),
  поэтому там точку вызова не добавлять. Матчинг по `LOWER(requester_email) =
  LOWER(user.email)` среди тикетов с `requester_user_id IS NULL` (bind-параметр,
  не интерполяция). Идемпотентно: повторные логины — no-op.
- **Проверка агентства на бэкенде — всегда по БД, на каждый запрос** (как роли
  в `app/api/deps.py`): зависимость `require_helpdesk_agent(user, db)` делает
  `SELECT 1 FROM helpdesk_agents WHERE user_id = :uid`. Это **единственный**
  источник правды; флаг `is_helpdesk_agent` из `BootstrapOut` (§7.2) —
  косметический, для меню/guard’ов фронта, бэкендом не доверяется.
- `internal`-сообщения не возвращаются на `/tickets/my*`.
- Вложения: токен доступа в URL не используется; проверка через ACL карточки.
- Раздача вложений — через `StreamingResponse` из локального файла
  (`/data/helpdesk/TKT-{number}/{filename}`, читается через `aiofiles`),
  без `FileResponse` и без `X-Accel-Redirect`.

### 4.6 Rate limits

Использовать существующую инфраструктуру `fastapi-limiter` через
`Depends(RateLimiter(times=..., minutes=...))` (как в `./backend/app/api/feedback/routes.py`).
По умолчанию ключ лимита — **IP+path** (`real_ip_identifier` из
`./backend/app/core/limiter.py`, выставлен глобально), а не per-user: кастомный
identifier для тикетов не требуется (портал во внутренней сети за VPN).

- `POST /tickets` — `RateLimiter(times=5, minutes=1)` (анти-спам).
- `POST /tickets/my/{id}/messages` — `RateLimiter(times=20, minutes=1)`.
- На этапе вложений: upload в `POST /tickets` и `POST /tickets/*/messages` —
  `RateLimiter(times=30, minutes=1)`; max size одного файла — константа
  `HELPDESK_MAX_ATTACHMENT_MB` (см. §9.3).

---

## 5. Email-интеграция

### 5.1 Inbound: IMAP-фетчер

**Воркер:** `app/worker/tasks/helpdesk.py::poll_helpdesk_mailbox`.
ARQ cron регистрируется статически каждые 30 секунд; реальный интервал берётся
из `helpdesk_mailbox_settings.poll_interval_seconds` и применяется внутри задачи
через Redis `helpdesk:imap:last_poll_at`. Перед работой задача берёт Redis lock
`helpdesk:imap:poll_lock` с TTL 5 минут.

> **Регистрация (проверено по `./backend/app/worker/main.py`).** Функции
> добавляются в `WorkerSettings.functions = [...]`, расписания — в
> `WorkerSettings.cron_jobs = [...]` через `cron("app.worker.tasks.helpdesk.<fn>", ...)`
> (в `cron_jobs` используется именно FQN-строка — это локальное исключение из
> правила «короткое имя для `enqueue_job`», см. существующие записи). Расписания:
> `poll_helpdesk_mailbox` — `second={0,30}` (реальный интервал — внутри задачи,
> §5.1); `auto_close_resolved_tickets` — `hour=3, minute=25`;
> `archive_closed_tickets` — `hour=3, minute=20`;
> `create_next_helpdesk_archive_partition` — `month=None, day=1, hour=2, minute=0`
> (+`run_at_startup=True`, по образцу `create_next_audit_partition`);
> `cleanup_helpdesk_attachments` — раз в сутки (свой час). Перед регистрацией
> убедиться, что всё обёрнуто гейтингом модуля (см. §9.1, п.5).

Алгоритм:
1. Прочитать настройки из таблицы `helpdesk_mailbox_settings` (см. § 3.6).
2. Подключиться по IMAP (`aioimaplib`, зависимость добавляется в `./backend/pyproject.toml`), выбрать `imap_folder`.
3. `SEARCH UNSEEN` → список UID.
4. Для каждого UID:
   - `FETCH (RFC822)` → байты письма;
   - распарсить через `email.message_from_bytes(..., policy=default)`;
   - извлечь `Message-ID`; если отсутствует — построить synthetic id по § 1.3.
     Если id уже в `helpdesk_email_log` → пометить `\Seen` и пропустить
     (status=`skipped`).
   - Определить тикет:
     1. По `In-Reply-To` / `References` → ищем в
        `helpdesk_messages.email_message_id`.
     2. По токену `[#TKT-{number}]` в `Subject` (регулярка
        `\[#TKT-(\d+)\]`).
      3. Если ничего — **создать новый тикет** (status=`new`,
         `source=email`).
      4. ⚠️ Если `[#TKT-{number}]` найден, но живого тикета с таким `number`
         уже нет (он в архиве) — **создать новый тикет** с
         `references_archived_ticket_number = {number}` (§3.1, §4.2).
    - Матчинг `In-Reply-To`/`References` ведётся против
      `helpdesk_messages.email_message_id`; исходящий `Message-ID` (формат §1.3.3)
      сохраняется в это поле при отправке, входящий `Message-ID` письма —
      сохраняется в это же поле при приёме.
    - Определить инициатора: `From` → нормализовать email → искать в
     `users.email`. Если найден — `requester_user_id = users.id`. Иначе
     гостевой.
   - Извлечь текст: предпочесть `text/plain`, иначе из `text/html`
     (для `body_html` — `sanitize_html()` из `./backend/app/core/sanitize.py`;
     для `body_text` — деривация plain-текста из очищенного HTML). HTML тоже
     сохраняется (sanitized).
   - Извлечь вложения (`Content-Disposition: attachment`), проверить filename
     на path traversal, MIME — через `python-magic`, сохранить streaming в
     локальную папку `/data/helpdesk/TKT-{number}/` через
     `services/helpdesk/attachments.py`. Ограничение —
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

> **Где объявить kind.** В `./backend/app/services/email_outbox.py` рядом с
> `KIND_MEETING`/`KIND_NEWS`/`KIND_FILE_SHARE`/`KIND_GENERIC` добавить
> `KIND_HELPDESK = "helpdesk"`. `enqueue_outbox_email(...)` принимает `kind`
> строкой — менять сигнатуру не нужно.

В `payload` кладём:
```json
{
  "ticket_id": "uuid",
  "ticket_number": 123,
  "message_id_header": "<tkn-123-550e8400-e29b-41d4-a716-446655440000@company.local>",
  "in_reply_to": "<...>",
  "references": ["<...>", "..."],
  "reply_to": "support+TKT-123@company.local",
  "subject_original": "...",
  "support_domain": "company.local",
  "attachments": [{"filename": "...", "original_name": "...", "content_type": "..."}]
}
```
⚠️ `attachments[].filename` — это **имя на диске** (`{uuid}_{sanitized}`);
диспетчер собирает полный путь как `HELPDESK_FILES_DIR / f"TKT-{ticket_number}" / filename`
и читает файл с локального диска. Содержимое файлов **не** кладётся в JSONB
`payload` — только метаданные. `storage_backend`/`storage_key` больше нет
(локальное хранение).

Диспетчер `process_email_outbox` расширяется ветвью `kind == 'helpdesk'`:
собирает `multipart/mixed` (если есть вложения) или `multipart/alternative`,
проставляет заголовки `Message-ID`, `In-Reply-To`, `References`, `Reply-To`,
`Subject = "[#TKT-{number}] {subject_original}"`. Для вложений dispatcher
асинхронно читает файлы с локального диска (`aiofiles`) и прикладывает их к
MIME; не класть содержимое файлов в JSONB `payload`.

> ⚠️ **Готча (проверено по коду `./backend/app/worker/tasks/email_outbox.py`).**
> Существующий `_build_mime(row, cfg)` — **синхронная** функция, она вызывается
> в цикле как `msg = _build_mime(row, cfg)` перед `await smtp_send(msg, cfg)`.
> Чтение вложений с диска через `aiofiles` — асинхронное, поэтому helpdesk-ветку
> **нельзя** реализовать внутри синхронного `_build_mime`. Правильно: в цикле
> отправки сделать ветвление
> ```python
> if row["kind"] == KIND_HELPDESK:
>     msg = await _build_helpdesk_mime(row, cfg)   # async: читает вложения с диска через aiofiles
> else:
>     msg = _build_mime(row, cfg)                  # существующий sync-путь не трогаем
> ```
> `_build_helpdesk_mime` — новая async-функция в том же модуле; для каждого
> вложения открывает `aiofiles.open(disk_path, "rb")`, читает байты, добавляет
> `MIMEBase`-часть. Заголовки `Message-ID/In-Reply-To/References/Reply-To`
> существующий `_build_mime` сейчас **не** проставляет — их выставляет именно
> helpdesk-ветка. Значения header'ов прогонять через `_sanitize_header(...)`
> (защита от header-injection, см. тот же модуль).

`email_message_id` исходящего письма **генерируется заранее** на этапе
создания `helpdesk_messages` (до enqueue в outbox), сразу сохраняется в
`helpdesk_messages.email_message_id` и передаётся в `payload.message_id_header`.
Дополнительный callback `on_sent` не требуется.

### 5.3 Безопасность

- HTML входящих писем санитизируем через `sanitize_html()` из
  `./backend/app/core/sanitize.py` (allowlist тегов как в news/kb).
- DKIM/SPF/DMARC проверка — не реализуем, полагаемся на корпоративный
  Postfix (он уже фильтрует).
- Anti-loop: если `From` совпадает с `support_address` или письмо содержит
  `Auto-Submitted: auto-*`, `Precedence: bulk/list/junk`, или
  `X-Auto-Response-Suppress` — **не создаём** тикет/сообщение, лог
  `skipped`.

---

## 6. Уведомления

Все уведомления — единым паттерном через `services/notifications.py`
(`create_notification` + Redis SSE) + `email_outbox`.

> ⚠️ **HTML-тел писем нет в виде файлов-шаблонов.** В проекте **нет** папки
> `base_data/email_templates/` и нет Jinja-рендеринга: существующие продюсеры
> собирают тело письма **инлайн в Python** (см. `_build_html_body(...)` в
> `./backend/app/services/meetings/notifications.py` — f-строки + `html.escape`).
> Helpdesk делает так же: функции-сборщики тел в
> `./backend/app/services/helpdesk/notifications.py`, экранирование
> пользовательских данных через `html.escape` (или `sanitize_html`, если в теле
> допускается размеченный фрагмент переписки). Никаких новых файлов-шаблонов
> не создавать.

`create_notification(db, redis, *, user_id, type, title, body=None, link=None)`
возвращает callable «отправить SSE» — вызвать его после `db.commit()` (паттерн
как в существующих продюсерах). `enqueue_outbox_email(...)` вызывать с
`kind=KIND_HELPDESK` в той же транзакции, что и бизнес-операция (outbox).

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
│   └── HelpdeskAgentInboxPage.vue   # /helpdesk — агентский список (только агентам)
├── pages/admin/tabs/
│   └── HelpdeskTab.vue              # admin tab: агенты, IMAP, архив/email-log
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

Конвенция guard'ов проекта (проверено по `./frontend/src/router.ts`) — через
`meta`, а не именованные функции: `meta: { requiresAuth: true }`,
`meta: { requiresEditor: true }`, `meta: { requiresAdmin: true }`.

| Path | Guard (`meta`) |
|---|---|
| `/helpdesk/my` | `requiresAuth: true` |
| `/helpdesk/my/:id` | `requiresAuth: true` (карточка отдаёт только свои) |
| `/helpdesk/new` | `requiresAuth: true` (или модалка с любой страницы) |
| `/helpdesk` | `requiresHelpdeskAgent: true` (агент инбокс) |
| `/helpdesk/tickets/:id` | `requiresHelpdeskAgent: true` |
| `/admin?tab=helpdesk` | `requiresAdmin: true` через существующий AdminPage/tab UX |

> ⚠️ **Guard `requiresHelpdeskAgent` ещё не существует** — его нужно добавить:
> 1. В `beforeEach` в `./frontend/src/router.ts` — ветку: если
>    `to.meta.requiresHelpdeskAgent` и `!(auth.isHelpdeskAgent || auth.isAdmin)`
>    → редирект (например, на `/helpdesk/my` или 403), по образцу существующих
>    проверок `requiresAdmin`/`requiresEditor`.
> 2. В `./frontend/src/stores/auth.ts` — добавить реактивное поле
>    `isHelpdeskAgent` (рядом с `isEditor`/`isAdmin`). Оно вычисляется **не из
>    `user.role`** (это отдельный список агентов), а из ответа bootstrap —
>    флаг хранится в отдельном `ref` (не computed из `user`), заполняется в
>    `loadBootstrap()` (`data.is_helpdesk_agent`), очищается в `logout()`.
>    ⚠️ **Скоуп и устаревание:** флаг обновляется только при полной
>    реинициализации через `loadBootstrap()`. Пути `loadUser`/`fetchMe`
>    (`/auth/me`, `setUser`) его **не** обновляют и **не** сбрасывают —
>    значение persists с последнего bootstrap в рамках сессии. Это допустимо:
>    флаг **косметический** (меню/guard фронта), а **бэкенд всегда
>    перепроверяет членство в `helpdesk_agents` по БД на каждом запросе**
>    (`require_helpdesk_agent`, §4.5). Устаревание — только UX-эффект (агент
>    увидит меню на 1 перезагрузку позже / не-агент увидит меню, но получит
>    403), **никогда** не дыра в правах.

**Backend для флага.** Добавить `is_helpdesk_agent: bool` **полем верхнего
уровня в `BootstrapOut`** (в `./backend/app/api/bootstrap.py`), вычисляемым в
`bootstrap(...)` (наличие `current_user.id` в `helpdesk_agents`). Не класть его
в `UserMe` — это не атрибут пользователя, а признак членства в списке агентов.

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
- **Админка**: не создавать отдельную страницу настроек, если текущий
  `AdminPage.vue` уже использует вкладочную архитектуру. Helpdesk-настройки
  добавляются как admin tab/section в существующий admin UX; если нужен route,
  он должен быть согласован с текущим паттерном `?tab=<name>`. Вкладки внутри
  секции: `Agents`, `Mailbox`, `Archive`. На вкладке Mailbox кнопка
  «Проверить соединение» вызывает `/settings/mailbox/test`.

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
     CASCADE). Это осознанное исключение из общего soft-delete-подхода:
     историчность обеспечивается таблицей `helpdesk_tickets_archive`.
3. Партиции архива создаются автоматически: хелпер
   `ensure_helpdesk_archive_partitions(conn, months_ahead)` (аналог
   `ensure_partitions` из `audit_partitions.py`) + cron
   `create_next_helpdesk_archive_partition` (аналог
   `create_next_audit_partition`), оба через raw-`asyncpg`.

**Auto-close resolved (best-practice).** Отдельный cron
`auto_close_resolved_tickets` (`cron(hour=3, minute=25)`, рядом с остальными
ночными cron’ами): переводит `resolved → closed` для тикетов с
`last_activity_at < NOW() - HELPDESK_RESOLVED_AUTO_CLOSE_DAYS` (default 7),
ставит `closed_at=NOW()`, `closed_by_user_id=NULL` (system), шлёт уведомление
инициатору. Без этого статус `resolved` висел бы бесконечно и делал
«безусловный reopen из resolved» (§4.2) непредсказуемым для старых тикетов.

Отдельный cron `cleanup_helpdesk_attachments` (раз в сутки): удалить папку
тикетов `/data/helpdesk/TKT-{number}/` целиком (вместе со всеми файлами), если
тикет архивирован > `HELPDESK_ARCHIVE_FILES_TTL_DAYS` (default 180) дней назад.
Локальное хранение — см. §1.3.2.

Просмотр архива — только админам (`GET /api/v1/helpdesk/archive`).
Поиск по архиву — простой ILIKE по `subject` и `requester_email`
(FTS не нужен в MVP).

---

## 9. Конфигурация

### 9.1 Гейтинг модуля

Модуль включается через `/data/settings/modules.json` (как `meetings`/`directories`):

| Ключ | Default | Описание |
|---|---|---|
| `helpdesk.enabled` | `false` | Мастер-флаг модуля. При `false` роуты/меню helpdesk недоступны (404/hidden), воркеры ingress/archive не запускаются. |

После изменения флага обязательно вызывать `invalidate_modules_cache()`.

> ⚠️ **Флаг `helpdesk` нужно завести в схеме модулей — он сейчас не существует.**
> Минимальный набор правок (по образцу `directories`, проверено по коду):
> 1. `./backend/app/core/modules_config.py`: добавить
>    `class HelpdeskModuleSettings(BaseModel): enabled: bool = False` и поле
>    `helpdesk: HelpdeskModuleSettings = Field(default_factory=HelpdeskModuleSettings)`
>    в `AllModuleSettings`.
> 2. `./backend/app/api/modules.py`: добавить `HelpdeskModuleOut`, включить его
>    в `AllModuleSettingsOut`, прокинуть в **обе** сборки `AllModuleSettingsOut(...)`,
>    добавить в `__all__`; admin-эндпоинт `PUT /admin/modules/helpdesk`
>    (+`HelpdeskModuleIn`) — по образцу `update_directories_module`.
> 3. `./backend/app/api/bootstrap.py`: добавить `helpdesk` в `_DEFAULT_MODULES`
>    и в `_get_modules()`.
> 4. Гейт роутеров helpdesk — async-dependency по образцу
>    `_require_module_enabled` в `./backend/app/api/directories.py`
>    (`load_modules_shared(redis)` → `if not modules.helpdesk.enabled: 404`).
> 5. Воркеры ingress/archive: в начале задачи проверять `load_modules().helpdesk.enabled`
>    и выходить, если выключено.

### 9.2 Mailbox-конфиг

IMAP/SMTP-настройки helpdesk хранятся в таблице `helpdesk_mailbox_settings`
(см. § 3.6) и управляются через `/api/v1/helpdesk/settings/mailbox*`.
Пароль хранится в зашифрованном виде (`imap_password_enc`).

### 9.3 Runtime-параметры helpdesk

Операционные лимиты/окна задаются как **модульные константы** в
`./backend/app/core/constants.py` (UPPER_SNAKE, по образцу существующих
`IDEMPOTENCY_TTL`, `MAX_BULK_FILES`, `BULK_INFLIGHT_TTL`):

| Константа | Default | Описание |
|---|---|---|
| `HELPDESK_MAX_ATTACHMENT_MB` | `25` | Максимум одного вложения |
| `HELPDESK_MAX_TOTAL_INGRESS_MB` | `50` | Максимум суммы вложений в одном письме |
| `HELPDESK_ARCHIVE_AFTER_DAYS` | `14` | Через сколько после `closed` уходит в архив |
| `HELPDESK_ARCHIVE_FILES_TTL_DAYS` | `180` | Через сколько физически удаляются вложения архива |
| `HELPDESK_REOPEN_WINDOW_DAYS` | `7` | Окно auto-reopen из `closed` (только для `closed`; `resolved` реопенится без окна — §4.2) |
| `HELPDESK_RESOLVED_AUTO_CLOSE_DAYS` | `7` | Через сколько `resolved` без активности авто-закрывается в `closed` |

> **Почему константы, а не `system_config`.** Пакет `app/core/system_config/`
> — это фиксированная Pydantic-схема (`_SystemSettingsBase` + `SystemSettings`
> + `SystemSettingsIn` + `SystemSettingsPatch`) с **lowercase snake_case**
> полями (`kb_trash_retention_days` и т.п.); добавление туда нового параметра
> требует правок в 3–4 классах схемы **и** в Admin-UI/фронте. Это вне скоупа
> поэтапных промптов helpdesk и для простой модели — источник ошибок. Поэтому
> в MVP операционные окна — константы в `constants.py`. Перенос лимитов
> размера вложений в runtime-настройки Admin UI (`system_config`,
> lowercase-поля `helpdesk_max_attachment_mb` и т.д.) — осознанное **будущее
> улучшение**, не часть MVP (см. §13).

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
  `.assigned`, `.status_changed`, `.message_added`, `.auto_closed`,
  `.archived`, `.agent_added`, `.agent_removed`, `.mailbox_settings_changed`.
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
| **2. Web-flow backend** | `POST /tickets`, `GET /tickets/my*`, `POST messages` без файлов | ценность сразу |
| **3. Agents backend** | `helpdesk_agents`, agent/admin API, assign/take/status/reopen, ACL | основная функциональность |
| **4. Attachments + notifications + outbound** | Локальные вложения (`/data/helpdesk`), in-app/email, `kind=helpdesk` в outbox | двусторонний web-flow |
| **5. IMAP + settings + archive + gating** | IMAP polling, mailbox settings, archive cron, module gating | замена OTRS-flow |
| **FE-1. Frontend infra** | API client, queries, routes, menu, i18n | после backend 1–4 |
| **FE-2. UI инициатора** | список своих, создание, карточка, ответ | web-пользователи |
| **FE-3. Agent inbox** | agent list/detail/actions/internal notes | операторы поддержки |
| **FE-4. Admin settings** | agents, mailbox, archive/email-log в admin UX | эксплуатация |
| **9. Метрики, аудит, тесты** | Prometheus, audit_log, unit/integration/e2e | боевая готовность |

### 12.1 Готовые промпты для поэтапной реализации (для простой модели)

> Использовать строго по порядку: сначала Этап 1, затем 2, 3, 4, 5.
> Каждый следующий этап запускать только после зелёных проверок предыдущего.

#### Промпт: Этап 1 — БД + ORM + минимальные схемы

```text
Реализуй только Этап 1 helpdesk (без API-логики, без frontend, без IMAP-воркера).

Контекст:
- ТЗ: ./docs/wip/helpdesk.md
- Работать строго по разделам 3, 4.1, 4.3, 12.
- Нужна ровно база + модели + минимальные pydantic-схемы.

Сделай:
1) Alembic-миграцию:
   - файл: ./backend/migrations/versions/075_add_helpdesk.py
     (свериться с фактическим head: ls backend/migrations/versions | sort | tail -1;
      выставить revision='075', down_revision='074' или актуальный head)
   - писать вручную через op.execute("""...""") с DDL из §3; НЕ использовать
     alembic --autogenerate (не поддерживает IDENTITY/партиции/частичные индексы)
   - создать таблицы: helpdesk_tickets, helpdesk_messages, helpdesk_attachments,
     helpdesk_agents, helpdesk_email_log, helpdesk_mailbox_settings,
     helpdesk_tickets_archive + первую месячную партицию архива.
2) ORM-модели:
   - файл: ./backend/app/models/helpdesk.py
   - подключить импорт в ./backend/app/models/__init__.py
3) Минимальные схемы:
   - файл: ./backend/app/schemas/helpdesk.py
   - TicketCreateIn, TicketOut, TicketListItemOut, MessageCreateIn, MessageOut,
     TicketAssignIn, TicketStatusIn, AgentIn, HelpdeskMailboxSettingsIn.
   - В HelpdeskMailboxSettingsOut пароль не возвращать; только imap_password_set: bool.

Ограничения:
- Не добавляй API endpoints, сервисы и UI.
- Не добавляй временные решения.
- Соблюдай existing style проекта.

Проверки (обязательно выполнить и починить ошибки):
- cd ./backend && ruff check .
- cd ./backend && mypy app
- cd ./backend && pytest tests/unit

Результат:
- Покажи список изменённых файлов.
- Кратко опиши, что сделано.
- Покажи вывод проверок.
```

#### Промпт: Этап 2 — Web-only flow инициатора

```text
Реализуй только Этап 2 helpdesk (web-only для инициатора, без agent/admin, без IMAP).

Контекст:
- ТЗ: ./docs/wip/helpdesk.md
- Обязателен инвариант первого сообщения (см. 4.3.1).

Сделай backend:
1) Сервисный слой:
   - ./backend/app/services/helpdesk/tickets.py
   - ./backend/app/services/helpdesk/messages.py
2) Роутер инициатора:
   - ./backend/app/api/helpdesk/tickets.py
   - endpoints: POST /tickets, GET /tickets/my, GET /tickets/my/{id},
     POST /tickets/my/{id}/messages
   - на этом этапе endpoints принимают JSON без файлов
3) Регистрация роутеров:
   - ./backend/app/api/helpdesk/__init__.py
   - ./backend/app/api/__init__.py

Требования:
- При создании тикета всегда создавать первую запись в helpdesk_messages.
- В /tickets/my* не возвращать internal-сообщения.
- Пагинация list-эндпоинтов в формате {items,total,limit,offset}.

Тесты:
- Добавить unit-тесты в ./backend/tests/unit/helpdesk/
  (create/list/get/add-message + ACL «только свои»).

Проверки (обязательно):
- cd ./backend && ruff check .
- cd ./backend && mypy app
- cd ./backend && pytest tests/unit

Результат:
- Список файлов.
- Что реализовано.
- Вывод проверок.
```

#### Промпт: Этап 3 — Agents + inbox + статусы + ACL

```text
Реализуй только Этап 3 helpdesk (agent/admin backend + ACL), без IMAP и без frontend.

Контекст:
- ТЗ: ./docs/wip/helpdesk.md (разделы 2, 4.4, 4.5, 4.2)

Сделай:
1) Управление агентами (admin):
   - ./backend/app/api/helpdesk/agents.py
   - GET/POST/PATCH/DELETE /api/v1/helpdesk/agents*
2) Агентские endpoints:
   - в ./backend/app/api/helpdesk/tickets.py добавить:
     GET /tickets, GET /tickets/{id}, POST /tickets/{id}/messages,
     POST /tickets/{id}/assign, POST /tickets/{id}/take,
     PATCH /tickets/{id}/status, POST /tickets/{id}/reopen
3) ACL/deps для helpdesk-agent:
   - использовать существующие паттерны deps/auth в backend
4) Bootstrap:
   - добавить is_helpdesk_agent в ./backend/app/api/bootstrap.py

Требования:
- Статус-машина строго по ТЗ.
- internal visible только agent/admin.
- take работает только для unassigned.

Тесты:
- unit/integration минимум для assign/take/status/reopen + ACL.

Проверки (обязательно):
- cd ./backend && ruff check .
- cd ./backend && mypy app
- cd ./backend && pytest tests/unit

Результат:
- Список файлов.
- Что реализовано.
- Вывод проверок.
```

#### Промпт: Этап 4 — Вложения + уведомления + outbound email

```text
Реализуй только Этап 4 helpdesk: локальные вложения, notifications, outbound email.
IMAP ingress пока не делать.

Контекст:
- ТЗ: ./docs/wip/helpdesk.md (1.3, 3.3, 4.5, 5.2, 6)
- Паттерн хранения: локальная папка /data/helpdesk/TKT-{number}/{file} (по образцу
  feedback, /data/feedback/files/). Upload через stream_upload_to_path (streaming +
  python-magic MIME). Nextcloud НЕ используется.
- Download: StreamingResponse из локального файла через aiofiles, не FileResponse
  и не X-Accel-Redirect.

Сделай:
1) Attachments service/API:
   - ./backend/app/services/helpdesk/attachments.py
   - расширить POST /tickets и POST /tickets/*/messages до multipart/form-data с files
   - GET /attachments/{id}: ACL + StreamingResponse из локального файла
   - хранение metadata в helpdesk_attachments (filename/original_name), файл на диске
   - path-traversal guard: re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", filename)
   - файлы удаляются с диска при удалении тикета/сообщения (CASCADE)
2) Уведомления:
   - ./backend/app/services/helpdesk/notifications.py
   - in-app + enqueue email_outbox по событиям из ТЗ
3) Outbound email:
   - расширить email_outbox обработку kind=helpdesk
   - заголовки Message-ID/In-Reply-To/References/Reply-To/Subject
   - email_message_id генерируется заранее и сохраняется в helpdesk_messages
   - attachments читаются с локального диска (aiofiles) при сборке MIME; содержимое
     файлов не хранить в payload (только filename/original_name/content_type)

Тесты:
- unit: MIME сборка helpdesk outbound + ACL attachments + path-traversal guard.
- integration: upload/download локальные файлы (authorized/forbidden), CASCADE-удаление файлов.

Проверки (обязательно):
- cd ./backend && ruff check .
- cd ./backend && mypy app
- cd ./backend && pytest tests/unit

Результат:
- Список файлов.
- Что реализовано.
- Вывод проверок.
```

#### Промпт: Этап 5 — IMAP ingress + mailbox settings + архив + модульный гейтинг

```text
Реализуй только Этап 5 helpdesk: IMAP ingress, mailbox settings, archive cron, module gating.

Контекст:
- ТЗ: ./docs/wip/helpdesk.md (1.3, 5.1, 8, 9)
- Гейтинг только через modules.json: helpdesk.enabled
- Mailbox settings только из helpdesk_mailbox_settings
- Cron статический раз в 30 секунд; poll_interval_seconds применяется внутри задачи через Redis last_poll_at
- Перед polling обязателен Redis distributed lock helpdesk:imap:poll_lock

Сделай:
1) Добавить зависимости в ./backend/pyproject.toml:
   - aioimaplib (отсутствует)
   - cryptography (отсутствует — проверено; нужен для Fernet в secret_crypto.py)
2) Mailbox settings API + crypto:
   - ./backend/app/api/helpdesk/settings.py
   - GET/PUT /api/v1/helpdesk/settings/mailbox
   - POST /api/v1/helpdesk/settings/mailbox/test
   - ./backend/app/core/secret_crypto.py -> encrypt_secret/decrypt_secret по ТЗ 1.3
3) IMAP ingress:
   - ./backend/app/services/helpdesk/ingress.py
   - ./backend/app/services/helpdesk/threading.py
   - идемпотентность через helpdesk_email_log
   - письма без Message-ID обрабатывать synthetic id по ТЗ 1.3
   - anti-loop правила из 5.3 обязательны
4) Worker cron:
   - ./backend/app/worker/tasks/helpdesk.py
   - poll_helpdesk_mailbox + auto_close_resolved_tickets + archive_closed_tickets
     + create_next_helpdesk_archive_partition + cleanup_helpdesk_attachments
   - poll_helpdesk_mailbox использует Redis lock + last_poll_at interval guard
5) Archive service:
   - ./backend/app/services/helpdesk/archive.py
6) Module gating:
   - использовать ./backend/app/core/modules_config.py (helpdesk.enabled)
   - при выключенном модуле роуты/воркеры недоступны

Тесты:
- integration: ingress create/append/skip/error, threading by Message-ID + subject token,
  auto-reopen window, archive move + cleanup.

Проверки (обязательно):
- cd ./backend && ruff check .
- cd ./backend && mypy app
- cd ./backend && pytest tests/unit

Результат:
- Список файлов.
- Что реализовано.
- Вывод проверок.
```

Этап 5 (IMAP) можно временно пропустить — модуль будет работать как
веб-only helpdesk; включение IMAP — `helpdesk.enabled=true` +
заполненная запись в `helpdesk_mailbox_settings`.

### 12.1.1 Готовые промпты для frontend-этапов

Frontend запускать только после зелёных backend-этапов 1–4. Все user-facing
строки добавлять в `./frontend/src/i18n/ru.json` и `./frontend/src/i18n/en.json`.

#### Промпт: Этап FE-1 — API client + queries + routes

```text
Реализуй только frontend-инфраструктуру helpdesk, без сложного UI.

Контекст:
- ТЗ: ./docs/wip/helpdesk.md (7, 12.1.1)
- Backend endpoints уже реализованы и типы OpenAPI обновлены.

Сделай:
1) ./frontend/src/api/helpdesk.ts — typed API wrappers.
2) ./frontend/src/queries/helpdesk.ts — TanStack Query hooks + ключи в ./frontend/src/queries/keys.ts.
3) Роуты helpdesk в существующем Vue Router:
   - /helpdesk/my
   - /helpdesk/my/:id
   - /helpdesk
   - /helpdesk/tickets/:id
4) Добавь пункты меню в существующий app menu:
   - «Поддержка» всем авторизованным
   - «Инбокс поддержки» только is_helpdesk_agent/admin
5) i18n ru/en.

Ограничения:
- Не делать agent UI и admin UI.
- Не добавлять новые UI-библиотеки.

Проверки:
- cd ./frontend && npm run lint:check
- cd ./frontend && npm run typecheck
- cd ./frontend && npm run test:unit
- cd ./frontend && npm run i18n:check
```

#### Промпт: Этап FE-2 — UI инициатора

```text
Реализуй только UI инициатора helpdesk.

Сделай:
1) ./frontend/src/pages/HelpdeskMyTicketsPage.vue — список своих тикетов.
2) ./frontend/src/pages/HelpdeskTicketDetailPage.vue — карточка своей заявки.
3) ./frontend/src/components/helpdesk/TicketCreateModal.vue.
4) ./frontend/src/components/helpdesk/TicketListTable.vue.
5) ./frontend/src/components/helpdesk/TicketMessageList.vue.
6) ./frontend/src/components/helpdesk/TicketReplyForm.vue.
7) Unit-тесты на форму ответа, список сообщений и создание заявки.

Требования:
- internal-сообщения в UI инициатора не показывать даже если случайно пришли.
- Все строки через i18n.
- Attachments показывать только если backend этап 4 уже готов.

Проверки:
- cd ./frontend && npm run lint:check
- cd ./frontend && npm run typecheck
- cd ./frontend && npm run test:unit
- cd ./frontend && npm run i18n:check
```

#### Промпт: Этап FE-3 — Agent inbox

```text
Реализуй только agent UI helpdesk.

Сделай:
1) ./frontend/src/pages/HelpdeskAgentInboxPage.vue — agent inbox.
2) В ./frontend/src/pages/HelpdeskTicketDetailPage.vue добавить agent-mode:
   assign/take/status/reopen/internal note/email metadata.
3) Компоненты:
   - ./frontend/src/components/helpdesk/TicketAssignSelect.vue
   - ./frontend/src/components/helpdesk/TicketStatusBadge.vue
   - ./frontend/src/components/helpdesk/TicketAttachmentList.vue
4) Unit-тесты на agent actions и internal/public переключатель.

Требования:
- Agent UI доступен только is_helpdesk_agent/admin.
- take показывать только для unassigned.
- Все строки через i18n.

Проверки:
- cd ./frontend && npm run lint:check
- cd ./frontend && npm run typecheck
- cd ./frontend && npm run test:unit
- cd ./frontend && npm run i18n:check
```

#### Промпт: Этап FE-4 — Admin helpdesk settings

```text
Реализуй только admin UI helpdesk settings в существующей admin-архитектуре.

Сделай:
1) Helpdesk admin tab/section в существующем AdminPage UX, без отдельной
   новой admin-страницы, если текущий паттерн — tab через query.
2) Компоненты:
   - ./frontend/src/components/helpdesk/HelpdeskAgentsManager.vue
   - mailbox settings form с write-only password и imap_password_set indicator
   - archive/email-log viewer
3) Кнопка test mailbox вызывает /api/v1/helpdesk/settings/mailbox/test.
4) Unit-тесты на agents manager и mailbox form.

Проверки:
- cd ./frontend && npm run lint:check
- cd ./frontend && npm run typecheck
- cd ./frontend && npm run test:unit
- cd ./frontend && npm run i18n:check
```

### 12.2 Чеклист приёмки по этапам

#### Чеклист: Этап 1 (БД + ORM + схемы)

- [ ] Есть одна миграция `./backend/migrations/versions/075_add_helpdesk.py` (или со следующим свободным номером), написанная вручную через `op.execute`, с корректными `revision`/`down_revision` относительно текущего head.
- [ ] Созданы все 7 таблиц из ТЗ, включая `helpdesk_mailbox_settings` и `helpdesk_tickets_archive`.
- [ ] Создана первая партиция архива на текущий месяц.
- [ ] ORM-модели добавлены в `./backend/app/models/helpdesk.py` и подключены в `./backend/app/models/__init__.py`.
- [ ] Минимальные схемы добавлены в `./backend/app/schemas/helpdesk.py`.
- [ ] Проходят проверки: `ruff check`, `mypy app`, `pytest tests/unit`.

#### Чеклист: Этап 2 (Web-only инициатор)

- [ ] Реализованы endpoints: `POST /tickets`, `GET /tickets/my`, `GET /tickets/my/{id}`, `POST /tickets/my/{id}/messages`.
- [ ] При создании тикета всегда создаётся первое сообщение в `helpdesk_messages`.
- [ ] В `/tickets/my*` не возвращаются `internal`-сообщения.
- [ ] List-ответы имеют формат `{items,total,limit,offset}`.
- [ ] Есть unit-тесты на create/list/get/add-message и ACL «только свои».
- [ ] Проходят проверки: `ruff check`, `mypy app`, `pytest tests/unit`.

#### Чеклист: Этап 3 (Agents + inbox + ACL)

- [ ] Реализован admin CRUD агентов: `GET/POST/PATCH/DELETE /agents*`.
- [ ] Реализованы агентские endpoints: list/detail/message/assign/take/status/reopen.
- [ ] `take` работает только для `unassigned` тикетов.
- [ ] Статус-машина реализована строго по ТЗ, включая `reopen`.
- [ ] `internal`-сообщения доступны только agent/admin.
- [ ] Проверка агентства на бэкенде — через `require_helpdesk_agent` (SELECT в `helpdesk_agents`), не через флаг bootstrap.
- [ ] В `bootstrap` добавлен `is_helpdesk_agent`.
- [ ] Проходят проверки: `ruff check`, `mypy app`, `pytest tests/unit`.

#### Чеклист: Этап 4 (Вложения + уведомления + outbound)

- [ ] Вложения сохраняются локально в `/data/helpdesk/TKT-{number}/{file}` (Nextcloud не используется).
- [ ] Download вложений идёт через `StreamingResponse` из локального файла через `aiofiles` (не `FileResponse`, не `X-Accel-Redirect`).
- [ ] Path-traversal guard на `filename` (`re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", ...)`).
- [ ] Файлы удаляются с диска при удалении тикета/сообщения (CASCADE).
- [ ] Реализованы in-app + email уведомления по событиям из ТЗ.
- [ ] Outbound `kind=helpdesk` выставляет заголовки `Message-ID`, `In-Reply-To`, `References`, `Reply-To`.
- [ ] `email_message_id` генерируется заранее и сохраняется в `helpdesk_messages` до enqueue.
- [ ] Проходят проверки: `ruff check`, `mypy app`, `pytest tests/unit`.

#### Чеклист: Этап 5 (IMAP ingress + архив + гейтинг)

- [ ] В `./backend/pyproject.toml` добавлен `aioimaplib`.
- [ ] Если `cryptography` ещё не был зависимостью backend, он добавлен.
- [ ] Реализованы `./backend/app/core/secret_crypto.py` и write-only mailbox password.
- [ ] Реализованы admin endpoints `GET/PUT /settings/mailbox` и `POST /settings/mailbox/test`.
- [ ] Ingress читает mailbox-настройки только из `helpdesk_mailbox_settings`.
- [ ] `poll_interval_seconds` реализован через внутренний Redis interval guard, а не динамический ARQ cron.
- [ ] IMAP polling защищён Redis distributed lock.
- [ ] Идемпотентность входящих писем реализована через `helpdesk_email_log`.
- [ ] Threading поддерживает `In-Reply-To/References` + fallback по `[#TKT-{number}]`.
- [ ] Письма без `Message-ID` получают synthetic id и не ломают polling.
- [ ] Реализованы cron-задачи `poll_helpdesk_mailbox`, `auto_close_resolved_tickets`, `archive_closed_tickets`, `create_next_helpdesk_archive_partition`, `cleanup_helpdesk_attachments`.
- [ ] Гейтинг модуля реализован через `modules.json` (`helpdesk.enabled`).
- [ ] Есть integration-тесты на ingress/threading/auto-reopen (`resolved` без окна + `closed` в окне)/archive/cleanup.
- [ ] Проходят проверки: `ruff check`, `mypy app`, `pytest tests/unit`.

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
8. **Runtime-настройка лимитов размера вложений через Admin UI.** В MVP
   `HELPDESK_MAX_ATTACHMENT_MB` / `HELPDESK_MAX_TOTAL_INGRESS_MB` —
   константы (§9.3). Перенос в `system_config` (lowercase-поля во всех
   классах `_SystemSettingsBase`/`SystemSettings`/`SystemSettingsIn`/
   `SystemSettingsPatch` + Admin-UI + фронт) — отдельная задача, когда
   понадобится менять лимиты без передеплоя.
