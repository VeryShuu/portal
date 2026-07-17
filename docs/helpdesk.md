# Модуль «Техническая поддержка» (Helpdesk)

> **Когда читать:** при работе с заявками, перепиской и вложениями тикетов; при изменении таблиц `helpdesk_*`; при правках IMAP-ingress, статус-машины, mailbox-settings, архива; при модификации мастер-флага `helpdesk` и агентов поддержки; при правках страниц/роутов/меню helpdesk.
> **Ключевой код:** `./backend/app/api/helpdesk/`, `./backend/app/services/helpdesk/` (вкл. `email_quote.py` — отсечение цитат), `./backend/app/models/helpdesk.py`, `./backend/app/worker/tasks/helpdesk.py`, `./frontend/src/pages/helpdesk/`, `./frontend/src/components/helpdesk/`.
> **ADR:** —. **См. также:** `./docs/wip/helpdesk.md` (исходное ТЗ), `./docs/email.md`, `./docs/api-contracts.md`, `./docs/db-schema.md`, `./docs/roles-matrix.md`.

> Замена OTRS внутри портала. Полный жизненный цикл заявки: приём из email (IMAP-polling support-ящика) или веб-формы → назначение ответственного → переписка с инициатором (двусторонний email-thread через `[#TKT-{number}]` в теме и `Message-ID`/`In-Reply-To`/`References`) → закрытие → архив. Вложения хранятся **локально** в `/data/helpdesk/TKT-{number}/` (по образцу feedback), Nextcloud не используется. Стартовое состояние модуля — выключен (`helpdesk.enabled=false`); включение = флаг в `modules.json` + заполненный `helpdesk_mailbox_settings`.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/helpdesk/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/helpdesk/`, `./frontend/src/components/helpdesk/`, admin-вкладка `./frontend/src/pages/admin/tabs/HelpdeskTab.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/helpdesk.py`): 6 cron-задач |
| Хранилище | БД (PostgreSQL) + локальная ФС `/data/helpdesk/TKT-{number}/` (вложения) |
| Префикс API | `/api/v1/helpdesk` |
| Email | transactional outbox `kind=helpdesk` (см. `./docs/email.md`) |
| Шифрование секрета | Fernet (`./backend/app/core/secret_crypto.py`), ключ из `SECRET_KEY` |
| Module gate | `modules.json → helpdesk.enabled`; при `false` весь API → 404, воркеры не работают |
| Развернуть как | следующий свободный модуль (после `signature`), см. `./backend/app/core/modules_config.py` |

### Возможности

- Создание заявки инициатором через веб-форму (`multipart/form-data` с вложениями) **или** автоматически из входящего письма на support-ящик.
- Статус-машина `new → open → pending → resolved → closed` с auto-reopen: из `resolved` — без окна, из `closed` — в течение `HELPDESK_REOPEN_WINDOW_DAYS` (7).
- Агентский инбокс с фильтрами (`status`, `assignee`, `unassigned`, `source`, `q`), взятие в работу (`take`), назначение (`assign`), ручная смена статуса, reopen.
- Внутренние заметки агентов (`visibility=internal`) — не видны инициатору, не уходят на email.
- Двусторонний email-thread: исходящие публичные ответы агентов уходят через outbox (`kind=helpdesk`) с каноническими заголовками; входящие матчятся по `In-Reply-To`/`References` + fallback по токену `[#TKT-{number}]` в теме.
- Гостевые заявители (email без аккаунта) создаются без `requester_user_id`; при появлении аккаунта с тем же email — авто-линкование (`link_guest_tickets` в OIDC-callback).
- Вложения: локальное streaming-хранилище (MIME через `python-magic`, path-traversal guard), скачивание через `StreamingResponse` (не `FileResponse`, не `X-Accel-Redirect`).
- Архивирование закрытых тикетов в партиционированную таблицу `helpdesk_tickets_archive` (jsonb-снимок) с TTL-очисткой файлов.
- In-app уведомления (агенты/инициатор/assignee) через общий `notifications`-движок.
- **Пользовательский UI** (Vue): список своих заявок + создание с вложениями + карточка с перепиской и ответом; агентский инбокс (фильтры, take) + карточка агента (assign/status/reopen/internal-заметки).
- **Admin UI**: переключатель модуля во вкладке «Модули» + отдельная вкладка «Техподдержка» (управление агентами с remote-search по сотрудникам, mailbox-settings с шифрованием и проверкой соединения).

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/helpdesk/__init__.py` | Сборка объединяющего роутера с module-gate `require_helpdesk_module`. |
| Router | `./backend/app/api/helpdesk/tickets.py` | CRUD заявок, переписка, assign/take/status/reopen, download вложений. Тонкий wiring-слой: бизнес-логика outbox-продюсеров — в `services/helpdesk/outbound.py`. |
| Router | `./backend/app/api/helpdesk/agents.py` | Admin CRUD агентов поддержки. |
| Router | `./backend/app/api/helpdesk/settings.py` | Admin mailbox-settings (singleton) + `POST /test`. |
| Router | `./backend/app/api/helpdesk/media.py` | Inline-картинки rich-редактора ответов: `POST /tickets/{id}/inline-media` (upload, streaming) → `{url, filename}`; `GET /tickets/{id}/inline-media/{file}` (serve через nginx `X-Accel-Redirect`). ACL: автор тикета ИЛИ агент/админ (`_is_helpdesk_agent` — мягкая проверка, без 403, т.к. не-агент-автор тоже имеет право). Файлы — `HELPDESK_FILES_DIR / "TKT-{number}" / "inline" / {uuid}_{name}`. |
| Router | `./backend/app/api/helpdesk/_common.py` | Сериализаторы (`ticket_to_out`/`ticket_to_agent_out`/`ticket_to_list_out`/`message_to_out`), `build_requester_profile`, ACL-фильтр `internal`. |
| Service | `./backend/app/services/helpdesk/outbound.py` | Исходящие email-продюсеры (outbox, `kind=helpdesk`): `enqueue_reply_outbound` (ответ агента + история), `enqueue_assigned_email` (назначение), `load_mailbox`/`load_user`/`support_domain`/`collect_ticket_references`. Без `db.commit` — outbox-инвариант (AGENTS.md): запись коммитится единым commit'ом с бизнес-операцией в роутере. |
| Service | `./backend/app/services/helpdesk/tickets.py` | Бизнес-логика тикетов: создание (инвариант первого сообщения), списки, assign/status/reopen, `link_guest_tickets`, `resolve_requester_user`. `assign_ticket` не коммитит (outbox-инвариант — единый commit в роутере). |
| Service | `./backend/app/services/helpdesk/messages.py` | Добавление ответов (requester/agent), генерация `email_message_id`, `normalize_message_bodies` (sanitize HTML через nh3 + деривация plain для email-треда — для rich-редактора). `add_agent_reply` не коммитит (outbox-инвариант — единый commit в роутере с outbox-записью). |
| Service | `./backend/app/services/helpdesk/lifecycle.py` | Чистая статус-машина (тестируется без БД). |
| Service | `./backend/app/services/helpdesk/threading.py` | Парсинг email-заголовков (Message-ID/References/токен темы), synthetic id, normalisation, `decode_mime_header` (RFC 2047). |
| Service | `./backend/app/services/helpdesk/email_quote.py` | Отсечение цитируемых писем во входящих ответах: маркер-разделитель в исходящих (`build_reply_marker_*`) + эвристический fallback (`strip_quoted_reply`/`strip_quoted_html`). |
| Service | `./backend/app/services/helpdesk/email_thread.py` | Сборка истории переписки для исходящего письма (`build_thread_history`): plain (email-цитатник) + html-блоки (через `email_template.render_history_block`), лимит `HISTORY_MAX_MESSAGES`, `internal`-заметки исключаются. Добавляется после ответа агента в `_try_enqueue_outbound` через шаблон `render_reply_email`. |
| Service | `./backend/app/services/helpdesk/email_template.py` | Единый HTML-шаблон исходящих helpdesk-писем: `render_reply_email` (ответ агента + история), `render_system_email` (назначение) и `render_new_ticket_agent_email` (уведомление агентам о новой заявке — аналог OTRS, единый стиль портала: «Поступила новая заявка» + блок контактов заявителя ФИО/Почта/Телефон/Внутренний номер из модели `User` + «Текст заявки:» в блоке-цитате + ссылка на портал; футер без призыва «ответьте на письмо», через outbox `kind=generic`) — жёстко зафиксированный шрифт Times New Roman 14px (единый размер во всём письме, иерархия через `font-weight`/`color`), компактная шапка (единый заголовок «#номер — тема» по центру — без статуса/исполнителя/обновления), контент на всю ширину письма (`width:100%`, без 600px-ограничения — как в OTRS), минималистичный таймлайн переписки (подпись «Исполнитель — »/«Специалист поддержки — » перед именем для специалиста, просто имя для заявителя; дата/время не выводятся — есть в письме; горизонтальные `<hr>`-разделители между сообщениями; без левых вертикальных полос/карточек/бейджей; заголовок «Предыдущие сообщения» убран — история идёт сразу за ответом), эвристическое приглушение email-подписей отправителей («↧ Подпись скрыта»), компактный блок вложений «📎 Вложения» с размерами, футер (призыв «Вы можете оставить комментарии по заявке ответив на это письмо» — по центру, жирный + ссылка на портал). Без reply-маркера: отсечение цитат при ответе — по заголовкам почтового клиента (как в OTRS). Inline-стили, совместимость с Outlook/Gmail/Apple Mail. |
| Service | `./backend/app/services/helpdesk/email_images.py` | Локализация картинок входящего письма при ingress (Zammad/Freshdesk-подход): inline `cid:` (`multipart/related`/`Content-ID`) и внешние `http(s)://` сохраняются в локальный FS как `HelpdeskAttachment`, `src` в `body_html` переписывается на относительный `/api/v1/helpdesk/attachments/{id}`. SSRF-guard (private/loopback/link-local blocked), httpx-выкачка с таймаутом и лимитом, best-effort. |
| Service | `./backend/app/services/helpdesk/ingress.py` | IMAP-фетчер: poll, anti-loop, matching, ingest, идемпотентность через `helpdesk_email_log`, `probe_imap_connection`. |
| Service | `./backend/app/services/helpdesk/attachments.py` | Локальное хранение вложений: upload (`UploadFile` web-путь) / `save_image_bytes` (байты — inline/remote при ingress) / resolve / download-path / cleanup. |
| Service | `./backend/app/services/helpdesk/archive.py` | Перенос closed → архив, cleanup файлов, read-only список/карточка архива. |
| Service | `./backend/app/services/helpdesk/archive_partitions.py` | Помесячные партиции `helpdesk_tickets_archive` (raw asyncpg, аналог `audit_partitions`). |
| Service | `./backend/app/services/helpdesk/notifications.py` | In-app уведомления по событиям (через `create_notification` + Redis SSE) + email-уведомление агентам о новой заявке (`notify_ticket_created_email`, через outbox `kind=generic`) + тела письма о назначении (`build_assigned_email_*`). |
| Service | `./backend/app/services/helpdesk/digest.py` | Ежедневная email-сводка агентам: расписание (`should_send_today`), сбор данных, построение тел, оркестрация отправки через outbox `kind=generic`. |
| Model | `./backend/app/models/helpdesk.py` | 8 моделей: `HelpdeskTicket`, `HelpdeskMessage`, `HelpdeskAttachment`, `HelpdeskAgent`, `HelpdeskEmailLog`, `HelpdeskMailboxSettings`, `HelpdeskDigestSettings`, `HelpdeskTicketArchive`. |
| Schema | `./backend/app/schemas/helpdesk.py` | Pydantic-схемы + StrEnum-наборы (`HelpdeskStatus`/`Source`/`Direction`/`Visibility`). |
| Worker | `./backend/app/worker/tasks/helpdesk.py` | 6 cron: poll, auto-close-resolved, archive, partition, cleanup, daily-digest. |
| Crypto | `./backend/app/core/secret_crypto.py` | `encrypt_secret`/`decrypt_secret` (Fernet, ключ из `SECRET_KEY`). |
| Migration | `./backend/migrations/versions/075_add_helpdesk.py` | 7 таблиц + первая партиция архива. |
| Migration | `./backend/migrations/versions/076_add_helpdesk_digest_settings.py` | Singleton `helpdesk_digest_settings` (расписание сводки) + seed. |
| Migration | `./backend/migrations/versions/077_add_helpdesk_attachments_inline_columns.py` | Колонки `is_inline`/`content_id` на `helpdesk_attachments` (schema-drift фикс: были в ORM-модели с 24a15bd, но БД-миграции не было → 500 на `selectinload(HelpdeskMessage.attachments)`). |
| Frontend API | `./frontend/src/api/helpdesk.ts` | Типы + вызовы (tickets/messages/inbox/attachments, agents, mailbox) с multipart-загрузкой через `apiUpload`. |
| Frontend Queries | `./frontend/src/queries/helpdesk.ts` | TanStack Query hooks + mutations (с инвалидацией ключей `helpdesk.*`). |
| Frontend Store | `./frontend/src/stores/auth.ts` | `isHelpdeskAgent` ref (из `bootstrap.is_helpdesk_agent`) — косметический, бэкендом не доверяется. |
| Frontend Router | `./frontend/src/router.ts` | 4 роута + guard `requiresHelpdeskAgent` + module-route gating. |
| Frontend Menu | `./frontend/src/composables/useAppMenu.ts` | Пункт «Поддержка» (всем, gated) + «Инбокс поддержки» (агентам). |
| Frontend Pages | `./frontend/src/pages/helpdesk/` | `HelpdeskMyTicketsPage`, `HelpdeskMyTicketDetailPage`, `HelpdeskAgentInboxPage`, `HelpdeskAgentTicketDetailPage`. |
| Frontend Components | `./frontend/src/components/helpdesk/` | `TicketStatusBadge`, `TicketMessageList`, `TicketReplyForm`, `TicketCreateModal`. |
| Admin Tab | `./frontend/src/pages/admin/tabs/HelpdeskTab.vue` | Вкладка админки: агенты + mailbox-settings. |
| Admin Components | `./frontend/src/components/admin/Helpdesk{AgentsManager,MailboxSettings}.vue` | Управление агентами (remote-search), mailbox-форма (write-only пароль, test). |

---

## 3. Модель данных

Модели — `./backend/app/models/helpdesk.py`. Миграция — `./backend/migrations/versions/075_add_helpdesk.py` (DDL написан вручную через `op.execute`, не autogenerate: `IDENTITY`, партиционирование, частичные индексы, `CHECK`). Полную авто-схему см. `./docs/db-schema.generated.md`.

### `helpdesk_tickets` — заявка

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `number` | `BigInteger` `IDENTITY ALWAYS` UNIQUE | Человекочитаемый `TKT-{number}` |
| `subject` | `String(500)` NOT NULL | Тема (для email-заявок — очищенная от `[#TKT-…]`) |
| `description` / `description_html` | `Text` / `Text` NULL | Копия первого сообщения (для быстрых списков) |
| `status` | `String(20)` NOT NULL default `'new'` | `new`/`open`/`pending`/`resolved`/`closed` |
| `source` | `String(20)` NOT NULL | `email`/`web` |
| `requester_user_id` | UUID NULL → `users.id` `SET NULL` | NULL для гостевых заявок |
| `requester_email` | `String(320)` NOT NULL | Всегда (для гостей и для отправки писем) |
| `requester_name` | `String(255)` NULL | Снимок имени: для web — `users.full_name`, для email — display-name из `From` (NULL при голом `user@host`). В списках резолвится через пользователя — см. «Отображаемое имя заявителя в списках» |
| `assignee_user_id` | UUID NULL → `users.id` `SET NULL` | Ответственный агент |
| `assigned_at` / `closed_at` | `TIMESTAMPTZ` NULL | Метки назначения/закрытия |
| `closed_by_user_id` | UUID NULL → `users.id` `SET NULL` | Кто закрыл (NULL для auto-close) |
| `last_activity_at` | `TIMESTAMPTZ` NOT NULL default `NOW()` | Обновляется при любом сообщении/изменении |
| `references_archived_ticket_number` | `BigInteger` NULL | Если тикет — продолжение архивного (не FK) |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | Метки |

Индексы: `status`; partial `assignee`/`requester`/`ref_archive` (WHERE NOT NULL); `LOWER(requester_email)`; `last_activity DESC`; partial `open_list` (status IN new/open/pending). `CHECK` на `status` и `source`.

### `helpdesk_messages` — сообщение переписки

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | Также используется как `message_uuid` в `Message-ID` |
| `ticket_id` | UUID NOT NULL → `helpdesk_tickets.id` `CASCADE` | |
| `author_user_id` | UUID NULL → `users.id` `SET NULL` | NULL для гостевых писем |
| `author_email` / `author_name` | `String(320)` NOT NULL / `String(255)` NULL | |
| `direction` | `String(10)` NOT NULL | `inbound` (от клиента) / `outbound` (от агента) |
| `visibility` | `String(10)` NOT NULL default `'public'` | `public` / `internal` (заметка агентов) |
| `body_text` / `body_html` | `Text` NOT NULL / `Text` NULL | HTML sanitized (`nh3`) |
| `source` | `String(20)` NOT NULL | `email` / `web` |
| `email_message_id` | `String(998)` NULL | RFC 5322 Message-ID (входящий и исходящий) |
| `in_reply_to` | `String(998)` NULL | |
| `created_at` | `TIMESTAMPTZ` | |

**Инвариант:** `internal`-сообщения никогда не отправляются по email и не возвращаются API инициатору. Частичный unique-индекс `uq_helpdesk_messages_email_msg_id` на `email_message_id` (WHERE NOT NULL) — защита от дублей при ingress.

### `helpdesk_attachments` — вложение (локальное хранение)

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | |
| `ticket_id` | UUID NOT NULL → `helpdesk_tickets.id` `CASCADE` | |
| `message_id` | UUID NULL → `helpdesk_messages.id` `CASCADE` | |
| `filename` | `String(500)` NOT NULL | Имя на диске: `{uuid}_{sanitized}` |
| `original_name` | `String(500)` NOT NULL | Исходное имя (для `Content-Disposition`) |
| `content_type` | `String(255)` NOT NULL | MIME через `python-magic` |
| `size_bytes` | `BigInteger` NOT NULL | |
| `is_inline` | `Boolean` NOT NULL default `FALSE` | Inline-картинка в теле (`cid:`-attach в письме) vs обычное вложение (`Content-Disposition: attachment`). Миграция `077`. |
| `content_id` | `String(320)` NULL | Content-ID inline-картинки (без угловых скобок); `NULL` для обычных вложений. Миграция `077`. |
| `uploaded_by_user_id` | UUID NULL → `users.id` `SET NULL` | |
| `created_at` | `TIMESTAMPTZ` | |

Файлы — в `/data/helpdesk/TKT-{number}/{filename}`. Path-traversal guard: `re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,254}", filename)`. Nextcloud **не** используется (см. §6).

### `helpdesk_agents` — агент поддержки

| Колонка | Тип | Примечание |
|---|---|---|
| `user_id` | UUID PK → `users.id` `CASCADE` | Членство = единственный источник прав агента |
| `added_by` | UUID NULL → `users.id` `SET NULL` | |
| `added_at` | `TIMESTAMPTZ` | |
| `notify_new` | `Boolean` NOT NULL default `TRUE` | Получать in-app о новых заявках |

**Отдельная сущность, не роль** `users.role` (агенты — операционная единица, меняется часто и независимо; как в OTRS/Zammad).

### `helpdesk_email_log` — идемпотентность IMAP-ingress

| Колонка | Тип | Примечание |
|---|---|---|
| `message_id` | `String(998)` PK | Message-ID или synthetic id входящего письма |
| `ticket_id` / `message_db_id` | UUID NULL → ... `SET NULL` | |
| `received_at` | `TIMESTAMPTZ` | |
| `status` | `String(20)` NOT NULL | `created` / `appended` / `skipped` / `error` |
| `error` | `Text` NULL | |

### `helpdesk_mailbox_settings` — singleton (id=1)

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | `SmallInteger` PK default 1 | `CHECK (id = 1)` |
| `imap_host` / `imap_port` / `imap_username` | `String(255)` / `Integer` default 993 / `String(255)` | |
| `imap_password_enc` | `Text` NOT NULL | Шифр Fernet (plaintext write-only) |
| `imap_use_ssl` | `Boolean` default `TRUE` | |
| `imap_folder` | `String(255)` default `'INBOX'` | |
| `poll_interval_seconds` | `Integer` default 60 | `CHECK BETWEEN 30 AND 600` |
| `delete_after_fetch` | `Boolean` default `FALSE` | |
| `support_address` | `String(320)` NOT NULL | Источник `support_domain` для `Message-ID`/`Reply-To` |
| `support_reply_to` | `String(320)` NULL | |
| `updated_by_user_id` | UUID NULL → `users.id` `SET NULL` | |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

Строка **не засевается** миграцией (`imap_password_enc NOT NULL`); создаётся первым `PUT /settings/mailbox` (с паролем). `GET` до `PUT` → `configured=false`.

### `helpdesk_digest_settings` — singleton (id=1)

Расписание ежедневной email-сводки по заявкам (миграция `076`). В отличие от `helpdesk_mailbox_settings`, строка **засевается сразу** (нет NOT NULL-колонок без DEFAULT), поэтому `GET /settings/digest` всегда возвращает реальные значения.

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | `SmallInteger` PK default 1 | `CHECK (id = 1)` |
| `enabled` | `Boolean` NOT NULL default `TRUE` | Вкл/выкл рассылки |
| `digest_hour` | `SmallInteger` NOT NULL default `8` | Час срабатывания (0–23) |
| `digest_minute` | `SmallInteger` NOT NULL default `0` | Минута (0–59) |
| `digest_schedule` | `String(16)` NOT NULL default `'weekdays'` | `weekdays` (пн–пт) / `daily` |
| `updated_by_user_id` | UUID NULL → `users.id` `SET NULL` | |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

CHECK: `digest_hour BETWEEN 0 AND 23`, `digest_minute BETWEEN 0 AND 59`, `digest_schedule IN ('weekdays','daily')`. Время — UTC воркера; cron запускается ежечасно, реальное срабатывание — `should_send_today` (см. §9.1).

### `helpdesk_tickets_archive` — архив (партиционированный)

`PARTITION BY RANGE (closed_at)`, composite PK `(id, closed_at)`, партиции помесячно (`helpdesk_tickets_archive_YYYY_mm`, создаёт `ensure_helpdesk_archive_partitions`). Хранит jsonb-снимок (`payload`: ticket + messages + attachments_meta). Read-only, без FK. Просмотр — только админам.

---

## 4. API

Префикс `/api/v1/helpdesk`. Все эндпоинты требуют авторизации и гейтируются `require_helpdesk_module` (404 при выключенном модуле). Порядок объявления в `tickets.py` важен: `/tickets/my*` → `/tickets` (агентский) → `/tickets/{id}`.

### Инициатор (`CurrentUser`)

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/tickets` | Создать заявку (`multipart/form-data`: `subject`, `description`, `files[]`). Rate-limit 5/мин. 201. |
| `GET` | `/tickets/my` | Свои заявки (`?status`, `?limit`, `?offset`). |
| `GET` | `/tickets/my/{id}` | Своя заявка с **публичными** сообщениями. |
| `POST` | `/tickets/my/{id}/messages` | Ответ (`Form`: `body_text`, `files[]`). Всегда `inbound`/`public`. Rate-limit 20/мин. 201. |
| `GET` | `/attachments/{id}` | Скачать вложение (`StreamingResponse`). ACL: автор/агент/админ. |

### Агент (`HelpdeskAgentDep`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/tickets` | Инбокс: фильтры `status`, `assignee`, `unassigned`, `source`, `q`, пагинация. |
| `GET` | `/tickets/{id}` | Карточка (`TicketAgentOut`, **все** сообщения + служебные поля). |
| `POST` | `/tickets/{id}/messages` | Ответ (`Form`: `body_text`, `body_html?`, `visibility`, `files[]`). `public` → `pending` + outbound email. 201. |
| `POST` | `/tickets/{id}/assign` | Назначить (`assignee_user_id`). |
| `POST` | `/tickets/{id}/take` | Взять на себя (409 если уже назначен). |
| `PATCH` | `/tickets/{id}/status` | Сменить статус (409 на запрещённый переход). |
| `POST` | `/tickets/{id}/reopen` | Reopen закрытой (409 из не-`closed`). |

### Админ (`AdminDep`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/agents` | Список агентов. |
| `POST` | `/agents` | Добавить (`user_id`, `notify_new`). 409 если уже агент. 201. |
| `PATCH` | `/agents/{user_id}` | Изменить `notify_new`. |
| `DELETE` | `/agents/{user_id}` | Удалить. 204. |
| `GET` | `/settings/mailbox` | Singleton (см. §7). |
| `PUT` | `/settings/mailbox` | Создать/обновить. |
| `POST` | `/settings/mailbox/test` | Проверка IMAP-соединения → `{ok, detail}`. |
| `GET` | `/settings/digest` | Singleton расписания сводки (`enabled`, `digest_hour`, `digest_minute`, `digest_schedule`). |
| `PUT` | `/settings/digest` | Обновить расписание. Аудит `helpdesk.digest_settings_changed`. |
| `GET` | `/archive` | Список архивных тикетов (`?q`, пагинация). |
| `GET` | `/archive/{id}` | Карточка из архива (read-only). |
| `GET` | `/email-log` | Лог входящих писем (отладка). |

Все мутации агентов/mailbox аудируются (`helpdesk.agent_*`, `helpdesk.mailbox_settings_changed`). Тикетные мутации — `helpdesk.message_added`/`assigned`/`status_changed`.

### Карточка тикета: `requester_profile`

В `TicketOut`/`TicketAgentOut` добавлено опциональное поле `requester_profile: RequesterProfileOut | None` — краткая «визитка» заявителя (email, отдел, должность, город, мобильный/внутренний телефоны). Показывается и агенту (`/tickets/{id}`), и инициатору (`/tickets/my/{id}` — это его собственные данные). На фронтенде рендерится в правом сайдбаре карточки тикета (`RequesterProfileCard` в `.ticket-layout__aside` — OTRS-образный двухколоночный layout: переписка слева, профиль справа; на узких экранах сворачивается в одну колонку).

**Профиль не хранится в БД тикета**, а собирается в рантайме из модели `User` (`build_requester_profile` в `_common.py`) — профильные данные меняются со временем, и в карточке всегда актуальная информация. Источник полей (как в `StaffCard.vue`/`staff_xlsx.py`):

| Поле `RequesterProfileOut` | Источник |
|---|---|
| `email` / `full_name` / `department` / `position` | нативные колонки `users` |
| `internal_phone` | нативная колонка `users.phone` |
| `city` | `users.attributes["city"]` (JSONB) |
| `mobile_phone` | `users.attributes["mobile"]` (JSONB) |

**Разрешение заявителя** (`resolve_requester_user` в `services/helpdesk/tickets.py`):
1. `requester_user_id` задан → eager-loaded `ticket.requester_user` (без доп. запроса; `fetch_ticket_for_agent` подгружает `selectinload(HelpdeskTicket.requester_user)`).
2. Гостевая email-заявка (`requester_user_id IS NULL`) → fallback-поиск сотрудника по `LOWER(users.email) = LOWER(requester_email)` среди не удалённых.
3. Не найден → `requester_profile = None` → блок профиля не отрисовывается (гость без аккаунта в портале).

В роутере профиль строится для всех эндпоинтов, возвращающих карточку: `create_ticket`, `get_my_ticket`, `get_ticket` и мутаций `assign`/`take`/`status`/`reopen`.

### Отображаемое имя заявителя в списках

Поле `requester_name` в тикете — **снимок** на момент создания: для веб-заявок оно всегда заполнено (`user.full_name`), а для email-заявок зависит от оформления заголовка `From` отправителем — голый `user@host` без display-name даёт `requester_name IS NULL`. Раньше список (`/tickets/my`, `/tickets`) отдавал этот снимок как есть, поэтому email-заявки без display-name показывались в инбоксе email'ом, хотя аккаунт заявителя известен (`requester_user_id`) и в карточке ФИО видно. Теперь `ticket_to_list_out` резолвит имя единообразно с карточкой (`_requester_display_name` в `_common.py`):

1. `requester_name` (снимок) заполнен → берётся он;
2. иначе `ticket.requester_user.full_name` (eager-loaded через `selectinload` в `list_my_tickets`/`list_agent_tickets`);
3. иначе `None` → фронт показывает `requester_email` (гость без аккаунта в портале).

---



## 5. Права и статус-машина

### ACL

- **Агентство** — `require_helpdesk_agent` (`./backend/app/api/deps.py`): **admin всегда проходит (суперсет)**, иначе `SELECT 1 FROM helpdesk_agents WHERE user_id = :uid` на каждый запрос; при отсутствии → 403. Это единственный источник прав; косметический флаг `is_helpdesk_agent` из `bootstrap` бэкендом **не доверяется** (обновляется только при полной реинициализации).
- **Module gate** — `require_helpdesk_module`: `load_modules_shared(redis)` → `modules.helpdesk.enabled`; `False` → 404 на всём роутере.
- **Requester** — чужой тикет = 404 (фильтр `requester_user_id` внутри `fetch_ticket_for_user`; не раскрывает существование). `internal`-сообщения отсекаются в mapper'е `ticket_to_out(requester_view=True)`.
- **Download** — автор тикета ИЛИ admin ИЛИ агент (`fetch_for_download`); иначе 404.

### Статус-машина (`./backend/app/services/helpdesk/lifecycle.py`)

```
            create (email/web)
                  │
                  ▼
                new ─────► pending  (первый публичный ответ агента)
   assign/take │           │
                ▼           │ client reply
              open ◄────────┘   (pending → open)
                │
   resolve      │
                ▼
            resolved ──► closed   (agent: close ИЛИ cron auto_close_resolved_tickets
                                   через HELPDESK_RESOLVED_AUTO_CLOSE_DAYS=7)
                │            │
   client reply │            │ reopen (agent) ИЛИ auto-reopen в окне
   (без окна)   │            │ HELPDESK_REOPEN_WINDOW_DAYS=7
                ▼            ▼
              open ◄────────┘
```

Константы переходов:
- `AGENT_SETTABLE_STATUSES = {open, pending, resolved, closed}` — то, что агент может выставить через `PATCH /status` (`new`/`archived` не входят).
- `REQUESTER_REOPEN_STATUSES = {pending, resolved}` — ответ клиента реопенит в `open` **без окна**.
- `closed → open` — только в течение `HELPDESK_REOPEN_WINDOW_DAYS` (7) после `closed_at`, либо вручную агентом (`POST /reopen`).
- После архивации reopen невозможен — входящий ответ создаёт **новый** тикет со ссылкой `references_archived_ticket_number`.

Запрещённые переходы → `IllegalTransitionError` → роутер возвращает **409** `{current_status, allowed, message}`.

---

## 6. Вложения (локальное хранение)

> Решение владельца проекта: helpdesk-вложения хранятся **локально**, не в Nextcloud. Образец — feedback (`/data/feedback/files/`).

- Папка тикета: `HELPDESK_FILES_DIR / f"TKT-{number}"` (по умолчанию `/data/helpdesk/TKT-{number}`).
- Имя на диске: `{uuid}_{sanitized_base}` (sanitized: только `[A-Za-z0-9._-]`, базовое имя без каталогов). Оригинальное имя — в `original_name` для `Content-Disposition` (RFC 5987).
- Upload — streaming через `stream_upload_to_path(...)` (`./backend/app/core/uploads.py`): MIME через `python-magic` по первым байтам (не доверять `Content-Type`), лимит одного файла `HELPDESK_MAX_ATTACHMENT_MB` (25), суммарный — `HELPDESK_MAX_TOTAL_INGRESS_MB` (50), allow-list `HELPDESK_ATTACHMENT_ALLOWED_MIMES`.
- **Email-ingress** (картинки + обычные вложения): при IMAP-фетче все картинки письма и `Content-Disposition: attachment`-части локализуются в локальный FS через `attachments.save_image_bytes` (источник — `bytes`, те же magic/лимиты/guard, что у web-upload). Картинки:
  - **Inline `cid:`** (`multipart/related`/`Content-ID`) — разбираются `email_images.extract_inline_parts`, бинарь сохраняется, `src` переписывается.
  - **Внешние `http(s)://`** — httpx-выкачка с SSRF-guard: `follow_redirects=False` + ручная обработка редиректов (до 5 hops) с **ре-валидацией каждого hop** через `is_safe_remote_url` + `_resolve_is_safe` (иначе редирект на 127.0.0.1 / 169.254.169.254 cloud-metadata bypass'ил бы первичную проверку); DNS-резолв через `asyncio.get_running_loop().getaddrinfo` (не блокирует event loop); private/loopback/link-local blocked; таймаут 10 c, лимит 25 MiB; content-type проверяется до сохранения. Best-effort: небезопасный/битый редирект → картинка остаётся как есть, не роняет ingest.
  - `src` в `body_html` переписывается на относительный `/api/v1/helpdesk/attachments/{id}` → подпадает под CSP `'self'` (**CSP менять не нужно**), нет утечки адреса получателя (tracking-pixels не срабатывают), нет mixed-content. Best-effort: одна битая/недоступная картинка не роняет ingest (остаётся как есть). См. `email_images.localize_images`.
- Download — `StreamingResponse` через `aiofiles` (chunked 1 MiB), заголовки `Content-Type`, `Content-Disposition` (RFC 5987), `X-Content-Type-Options: nosniff`. **НЕ** `FileResponse`, **НЕ** `X-Accel-Redirect` (для helpdesk явно запрещено — отличие от feedback).
- Удаление файлов — по CASCADE вместе с тикетом/сообщением (`delete_attachment_files`, best-effort). Полная очистка папки тикета — `delete_ticket_dir` (для archive-cleanup).

### Inline-картинки rich-редактора (ответы агента/заявителя)

Отдельный media-endpoint (`./backend/app/api/helpdesk/media.py`) — не `HelpdeskAttachment`, а отдельное хранилище для картинок, вставленных в текст ответа через TipTap-редактор (как `kb/media.py`). Отличается от вложений: файлы не привязаны к конкретному сообщению (создаются до него — агент грузит скриншот, ещё не отправив ответ), не имеют записи в `helpdesk_attachments`.

- **Upload** — `POST /tickets/{ticket_id}/inline-media` (multipart, поле `file`): streaming через `stream_upload_to_path`, allow-list `HELPDESK_INLINE_IMAGE_MIMES` (jpeg/png/gif/webp — без SVG, XSS через `<script>` в SVG), лимит `HELPDESK_MAX_ATTACHMENT_MB` (25). Возвращает `{url, filename}`; `url` — относительный `/api/v1/helpdesk/tickets/{ticket_id}/inline-media/{filename}`.
- **Serve** — `GET /tickets/{ticket_id}/inline-media/{filename}` → заголовок `X-Accel-Redirect: /internal/helpdesk-media/TKT-{number}/inline/{file}` (nginx location `alias /data/helpdesk/`). `no-store` + `nosniff` — картинки приватны (ACL по тикету).
- **ACL** (обязателен и для upload, и для serve): автор тикета (`requester_user_id == user.id`) ИЛИ helpdesk-агент/админ. Проверка — `_is_helpdesk_agent` (мягкая, без 403: не-агент-автор тоже имеет право грузить/смотреть свои картинки). Чужой тикет → 404 (не раскрываем существование).
- Папка: `HELPDESK_FILES_DIR / f"TKT-{number}" / "inline"` (отдельно от вложений тикета). Имя: `{uuid8}_{safe_name}`. Path-traversal guard как в kb.
- В HTML ответа картинка хранится как `<figure data-type="figure-image"><img src="/api/v1/..." alt="..."/><figcaption>...</figcaption></figure>` (TipTap `FigureImage`). При отображении в ленте проходит `sanitizeHelpdeskHtml` (фронт, DOMPurify) — профиль разрешает `figure`/`figcaption`/`img` + относительные URL (базовый `sanitizeHtml` их не пропускает).

---

## 7. Mailbox settings и шифрование

- **Singleton** (`id=1`): миграция **не** засевает строку (`imap_password_enc NOT NULL`). Создаётся первым `PUT /settings/mailbox` с паролем; `GET` до `PUT` → `HelpdeskMailboxSettingsOut(configured=False)`.
- **Пароль write-only**: в БД `imap_password_enc = encrypt_secret(password)` (Fernet, ключ детерминированно из `Settings.secret_key` через SHA-256 → urlsafe base64 — `./backend/app/core/secret_crypto.py`). В ответах только `imap_password_set: bool`, plaintext никогда не возвращается. При update пароль опционален (`None` = оставить прежний шифр); при create — обязателен (400 иначе).
- **`POST /settings/mailbox/test`** — `probe_imap_connection` (login + `SELECT folder`) возвращает `{ok, detail}`. Если singleton не настроен → 404.
- Детерминизм ключа важен: любой backend/worker с тем же `SECRET_KEY` расшифровывает секрет (распределённая отправка outbox несколькими воркерами).

---

## 8. Email-интеграция

### Inbound: IMAP-ingress (ТЗ §5.1)

Воркер `poll_helpdesk_mailbox` (cron каждые 30 c) с distributed lock `helpdesk:imap:poll_lock` (TTL 5 мин) и interval guard (реальный интервал — из `poll_interval_seconds`, через Redis `helpdesk:imap:last_poll_at`):

1. `SEARCH ALL` → для каждого UID `FETCH (RFC822)` → парсинг через `email.message_from_bytes`. **Фильтр по `\Seen` не применяется** — оператор читает ящик вручную (в т.ч. в почтовом клиенте), и `\Seen`-письма иначе выпадали бы из потока; дедупликация — на `helpdesk_email_log`. Заголовки `Subject`/`From` декодируются из RFC 2047 encoded-words (`=?charset?B?...?=` — типично для кириллических тем/имён в KOI8-R/Windows-1251) через `threading.decode_mime_header`; иначе тема тикета сохранялась бы нечитаемой (`=?koi8-r?B?zsUg...?=`).
2. **Anti-loop** (ТЗ §5.3): `From == support_address` или заголовки `Auto-Submitted: auto-*` / `Precedence: bulk/list/junk` / `X-Auto-Response-Suppress` → `status=skipped`, тикет не создаётся.
3. **Идемпотентность**: `Message-ID` (или synthetic id для писем без него) проверяется в `helpdesk_email_log`; повтор → `skipped`.
4. **Matching**: по `In-Reply-To`/`References` → `helpdesk_messages.email_message_id`; fallback по токену `[#TKT-{number}]` в теме; последний (опциональный) fallback — plus-маркер `+TKT-{number}` в адресе получателя (`Delivered-To`/`X-Original-To`/`To`). Нет матча → новый тикет (`source=email`). `[#TKT-N]` найден, но живого тикета нет (в архиве) → новый тикет с `references_archived_ticket_number=N`. **Безопасность:** для fallback'ов по subject/recipient-токену (угадываемый последовательный `number`) отправитель сверяется с `ticket.requester_email` (case-insensitive); при несовпадении создаётся новый тикет (защита от инъекции сообщения в чужой тикет). `References`-матч (секретный `Message-ID` исходящего) — без сверки отправителя.
5. **Инициатор**: `From` → нормализованный email → `LOWER(users.email)`; найден → `requester_user_id`, иначе гостевая заявка.
6. Тело: `text/plain` предпочитается, иначе деривация из sanitized `text/html` (`nh3`). **Отсечение цитаты** предыдущего письма — маркер-разделитель `REPLY_MARKER_TOKEN` + эвристика quoted-reply (см. ниже «Отсечение цитат во входящих ответах»). **Локализация картинок + обычные вложения** (`_localize_attachments_and_images`, см. §6): inline `cid:` (`multipart/related`/`Content-ID`) и внешние `http(s)://` сохраняются в локальный FS, `src` переписывается на `/api/v1/helpdesk/attachments/{id}`; `Content-Disposition: attachment`-части — через `save_image_bytes` (MIME/лимиты/path-traversal guard). Снимает CSP-блок http-картинок и битые `cid:` (раньше — MVP-заглушка без сохранения).
7. Статус: `pending`/`resolved` → `open` (без окна); `closed` → `open` в окне reopen (иначе без изменений); `new`/`open` — без изменений.
8. `helpdesk_email_log` (`created`/`appended`), пометить `\Seen` (и при `delete_after_fetch` — `STORE +FLAGS \Deleted` + `EXPUNGE` в конце цикла). Удаление применяется и для `skipped`-писем (уже видели/anti-loop), а не только для успешно созданных.

### Outbound: `kind=helpdesk` в outbox

- Константа `KIND_HELPDESK = "helpdesk"` (`./backend/app/services/email_outbox.py`).
- **Продюсеры** (`./backend/app/services/helpdesk/outbound.py`, все — без `db.commit`, по outbox-инварианту):
  - `enqueue_reply_outbound` — публичный ответ агента (вызов из `add_agent_message`, только при сконфигурированном mailbox + `support_domain`). `email_message_id` генерируется заранее (`_make_outbound_message_id`) и сохраняется в `helpdesk_messages.email_message_id` до enqueue (для threading).
  - `enqueue_assigned_email` — письмо о назначении (`assign`/`take`).
  - `enqueue_created_email` — письмо «заявка зарегистрирована» при создании тикета (корень треда: `references=[]`, `in_reply_to=None`, см. §9).
- **Outbox-инвариант** (AGENTS.md → Email outbox-pattern): `add_agent_reply`/`assign_ticket` не делают `db.commit()` — только `flush`. Роутер ставит outbox-запись в ту же транзакцию и делает **единый commit** (ответ агента + outbox-запись атомарны). Раньше commit был раздельным → сбой между ними терял письмо заявителю при сохранённом ответе. Сбой enqueue откатывает ответ (агент видит 500, повторяет) — сознательное соответствие инварианту. In-app уведомления — после commit, best-effort.
- **Единый читаемый шаблон письма** (`email_template.py` → `render_reply_email`): жёстко зафиксированный шрифт Times New Roman 14px (единый размер во всём письме, иерархия через `font-weight`/`color`, не через размеры), компактная шапка (единый заголовок «#номер — тема» по центру — без статуса/исполнителя/обновления; белый фон), контент на всю ширину письма (`width:100%`, без 600px-ограничения — как в OTRS), таймлайн-блок ответа агента (префикс «Исполнитель — »/«Специалист поддержки — » перед accent-именем), минималистичная история-таймлайн (подпись: для специалиста — префикс роли через дефис + accent-имя, для заявителя — просто имя в grey; дата/время не выводятся — есть в письме; горизонтальные `<hr>`-разделители на всю ширину письма между сообщениями; без заголовка «Предыдущие сообщения» — история идёт сразу за ответом; без левых вертикальных полос/карточек/бейджей/теней — различение участников только цветом имени и префиксом роли), эвристическое приглушение email-подписей отправителей (маркеры RFC 3676 `--`, «С уважением»/«Best regards», `<hr>`-разделители → компактный блок «↧ Подпись отправителя скрыта» — подпись в БД и веб-версии тикета остаётся полностью, отсекается только в письме), компактный блок вложений «📎 Вложения» с именами и размерами, футер (призыв «Вы можете оставить комментарии по заявке ответив на это письмо» — по центру письма, жирный + ссылка на портал). **Reply-маркер не ставится** (как в OTRS): отсечение цитат при ответе заявителя — по заголовкам почтового клиента (см. ниже «Отсечение цитат во входящих ответах»). Inline-стили. Письмо о назначении ответственного — через `render_system_email` (та же шапка/футер, без истории). Совместимость с Outlook Desktop/Web/Gmail/Apple Mail (только inline-стили, без CSS Grid/Flexbox).
- **Тело письма несёт историю переписки** после ответа агента: `body = {шапка} + {ответ агента} + {история} + {футер}`. История собирается в рантайме из публичных сообщений тикета (`build_thread_history` в `./backend/app/services/helpdesk/email_thread.py`, лимит `HISTORY_MAX_MESSAGES=20`, `internal`-заметки не входят) и оформляется в plain (email-цитатник `От …, {date}:\n> …`) и html (таймлайн-блоки через `render_history_block`). Тогда:
  - заявитель видит контекст прямо в почтовом клиенте (раньше письмо = голый ответ без истории);
  - при ответе его почтовый клиент цитирует весь блок, а `strip_quoted_reply`/`strip_quoted_html` (см. ниже «Отсечение цитат») отрезают процитированную историю/ответ по заголовкам цитаты (Outlook `From:/Sent:`, Gmail `wrote:`) → в ленте портала остаётся только чистый ответ заявителя — как в OTRS, без служебных маркеров в письме;
  - Сохраняемое в БД `HelpdeskMessage` **не мутируется** — история добавляется только к локальным копиям, передаваемым в `enqueue_outbox_email` (агент в ленте портала видит свой чистый ответ).
- **Dispatcher** `_build_helpdesk_mime` (`./backend/app/worker/tasks/email_outbox.py`) — async-ветка (читает вложения с диска через `aiofiles`, поэтому не влезает в синхронный `_build_mime`). Заголовки:
  - `Message-ID: <tkn-{ticket_number}-{message_uuid}@{support_domain}>` (из `payload.message_id_header`)
  - `In-Reply-To` / `References` (цепочка `email_message_id` предшествующих сообщений)
  - `Reply-To: {support_address}` — чистый настроенный адрес ящика (без plus-addressing). Матчинг входящих ответов идёт по `In-Reply-To`/`References`, токену `[#TKT-{number}]` в теме и опционально по plus-маркеру в адресе получателя — plus-маркер в `Reply-To` для этого не нужен и ранее ломал доставку на ящиках, где local-part ≠ `support` (например `portal@domain` → ответ на несуществующий `support+TKT-N@domain`).
  - `Subject: "[#TKT-{number}] {subject_original}"`
  - Все значения — через `_sanitize_header` (защита от header-injection).
  - Вложения: `multipart/mixed`, файлы с локального диска; содержимое **не** в JSONB payload (только метаданные).
  - При пустом/невалидном `support_domain` → `ValueError` → outbox mark_failed (RFC 5322 требует валидный домен).

> **Ограничение: inline-картинки rich-ответов в исходящем email.** Rich-ответ агента (через TipTap) может содержать картинки (`<img src="/api/v1/helpdesk/.../inline-media/...">`). В исходящем письме они остаются относительными ссылками — внешние почтовые клиенты (Outlook/Gmail) их **не отобразят** (нет доступа к внутреннему порталу). Заявитель видит полный rich-ответ с картинками **в веб-ленте портала**. Встраивание картинок в email через `cid:`-attach (`multipart/related`, `Content-ID`) — будущая работа: миграция `077` уже завела колонки `is_inline`/`content_id` на `helpdesk_attachments`, но бизнес-логика cid-встраивания в `_build_helpdesk_mime` пока не реализована. Заявитель-ответы (rich от инициатора) на email не уходят — они `inbound`, проблема касается только публичных ответов агента.

Полный разбор outbox — см. `./docs/email.md`.

### Отсечение цитат во входящих ответах (`email_quote.py`)

> Проблема: когда заявитель отвечает на письмо тикета через почтовый клиент (Outlook/Thunderbird/Gmail), клиент добавляет блок цитаты предыдущего сообщения (`From:`/`Sent:`/`To:`/`Subject:` + текст, либо `On … wrote:` и `>`-префиксы). Без отсечения весь блок попадает в `helpdesk_messages.body_text` и в ленте тикета ответ выглядит странно (вместе с предыдущим письмом).

Промышленный стандарт (Zammad/FreeScout/Help Scout/OTRS) — **отсечение по заголовкам цитаты**, которые сам почтовый клиент добавляет при ответе. Реализовано в `./backend/app/services/helpdesk/email_quote.py`:

1. **Наш маркер (defensive)**: `REPLY_MARKER_TOKEN = "Ответьте выше этой линии"`. В текущем шаблоне маркер **не ставится** (`render_reply_email` не вызывает `build_reply_marker_*`), но `strip_quoted_reply`/`strip_quoted_html` продолжают резать по нему, если он вдруг встретится — например, заявитель ответил на старое письмо из архива (когда маркер ещё ставился). Функции `build_reply_marker_*` сохранены для совместимости/тестов.
2. **Эвристика цитат (основной слой)** — `strip_quoted_reply`/`_html` распознаёт стандартные паттерны цитирования, проставляемые почтовыми клиентами:
   - Outlook (en): `From:/Sent:/To:/Subject:` блок + `-----Original Message-----`
   - Outlook (ru): `От:/Отправлено:/Кому:/Тема:` + `----- Исходное сообщение -----`
   - Gmail (en): `On … wrote:`
   - Gmail (ru): `… написал(а):`
   - HTML: quote-контейнеры с классами `gmail_quote`/`moz-cite-prefix`/`WordSection1/2`

**Точка вызова** — `_extract_bodies` (`ingress.py`): strip применяется к `plain` и `html` до санитизации, и повторно — к деривации plain ← html. Сырьё (неочищенное тело) **не сохраняется** — при `delete_after_fetch=false` оригинал доступен в почтовом ящике.

**Грабли:**
- Эвристика может обрезать легитимный текст, если ответ начинается со слов `От:`/`From:` или содержит `-----`. Поэтому паттерны привязаны к началу строки (`re.M`) и описывают именно заголовок блока цитаты (а не одиночное слово). Универсальный `<blockquote>` в HTML не трогается — это легитимное форматирование.

---

## 9. Уведомления

In-app через общий `notifications`-движок (`create_notification` + Redis SSE), best-effort (сбой не ломает бизнес-операцию — паттерн feedback). Агенты-получатели in-app выбираются по `helpdesk_agents` JOIN `users` (`notify_inapp`, `deleted_at IS NULL`), **не** по `User.role`.

| Событие | Получатели | In-app | Email |
|---|---|---|---|
| Новая заявка (email/web) | Агенты | ✅ (`notify_new` + `notify_inapp`) | ✅ агентам (`notify_new` + `notify_email`, через outbox `kind=generic`) |
| Новая заявка (email/web) | Инициатор | — | ✅ подтверждение «заявка зарегистрирована» (через outbox `kind=helpdesk`, при настроенном mailbox) |
| Взятие в работу / реассайн | Инициатор + новый агент (+ старый) | ✅ | ✅ инициатору (с ФИО ответственного, в теме `[#TKT-{number}]`) |
| Публичный ответ агента | Инициатор | ✅ | ✅ (это и есть «ответ», через outbox) |
| Сообщение от клиента | Текущий assignee (или все агенты) | ✅ | — |
| Статус → `resolved`/`closed` | Инициатор | ✅ | — |
| Internal note | Агенты | ✅ (не email) | — |
| Ежедневная сводка (cron) | Каждый агент (персонально) | — | ✅ через outbox `kind=generic` (не тред тикета) |

**Email заявителю «заявка зарегистрирована»** (`enqueue_created_email` в `outbound.py`, тела — `build_created_email_bodies` в `notifications.py`): при создании заявки (web-форма или IMAP-ingress) заявителю отправляется подтверждение приёма обращения — номер `[#TKT-{number}]`, «обращение принято, с вами свяжется специалист», инструкция для ответа. Через outbox `kind=helpdesk` (входит в email-тред тикета): токен `[#TKT-{number}]` в теме + `Message-ID` (корень треда, на него ссылаются будущие ответы) + `References`/`Reply-To` → ответ заявителя вернётся в тот же тикет. Для нового тикета `references` пуст (это первое письмо треда), `in_reply_to=None`. Ставится в **ту же транзакцию**, что и создание тикета+сообщения (outbox-инвариант AGENTS.md — письмо коммитится атомарно с заявкой). Тема `"[#TKT-{number}] Заявка зарегистрирована"`. Только при сконфигурированном mailbox (`support_domain`); без mailbox (web-only) — no-op (`_try_enqueue_created_email` — best-effort, лог warning). Срабатывает для всех новых тикетов (web через `create_ticket`, email через `ingress._ingest_message` при `new_status == "created"`), не для ответов на существующие.

**Email агентам о новой заявке** (`notify_ticket_created_email` в `notifications.py`, тела — `render_new_ticket_agent_email` в `email_template.py`): при создании заявки (web-форма или IMAP-ingress) всем активным агентам с `notify_new=True` **и** `User.notify_email=True` отправляется email-уведомление (аналог OTRS-письма «В службу технической поддержки поступила новая заявка», но в едином стиле портала). Через outbox `kind=generic` (как дайджест — **не** входит в email-тред тикета, не требует threading-заголовков и настроенного mailbox; SMTP-настройки общие → работает даже в web-only режиме helpdesk). Для каждого агента — отдельная outbox-запись (персональный `to_email`), единый `db.commit` в конце. Тема `"[#TKT-{number}] Новая заявка: {subject}"`. Тело (plain+html): «Поступила новая заявка» → блок контактов заявителя (ФИО, Почта, Телефон, Внутренний номер — из модели `User` через `resolve_requester_user`, тот же источник что и `requester_profile` в карточке тикета; `internal_phone` ← `users.phone`, `mobile_phone` ← `users.attributes["mobile"]`; пустые поля пропускаются; для гостевой заявки без аккаунта — имя/email из снимка тикета, без телефонов) → «Текст заявки:» (тело первого сообщения в блоке-цитате) → ссылка на агентскую карточку `{portal_base_url}/helpdesk/tickets/{id}`. Футер без призыва «ответьте на письмо» (агент работает через портал/инбокс; ответ на это письмо через общий SMTP-from без threading-заголовков создал бы путаницу в треде). Вызывается **после** commit бизнес-операции (best-effort: из роутера `create_ticket` через `_try_notify`, из `ingress._ingest_message` в собственном try/except — сбой не ломает создание заявки). Срабатывает только для **новых** тикетов (`new_status == "created"`), не для ответов на существующие.

**Email при назначении** (`_try_enqueue_assigned_email` в `tickets.py`, тела — `build_assigned_email_*` в `notifications.py`): при `assign`/`take`, только при сконфигурированном mailbox (`support_domain`). Письмо входит в email-тред тикета — тема `"[#TKT-{number}] Заявка принята в работу"`, заголовки `Message-ID`/`In-Reply-To`/`References`/`Reply-To` (формат как у публичных ответов, см. §8), чтобы ответ заявителя вернулся в тикет даже без живого `In-Reply-To` (Subject-token fallback). Тела (plain+html) с номером/темой заявки и ФИО ответственного, `html.escape` на пользовательские данные. Best-effort: сбой enqueue не ломает назначение (`_try_send`). Отправляется на `ticket.requester_email` (всегда заполнено, включая гостевые заявки).

### 9.1 Ежедневная сводка (`digest.py`)

Cron `send_helpdesk_digest` (см. §10) раз в день шлёт **каждому активному helpdesk-агенту** персональное email-письмо через outbox `kind=generic` (не `helpdesk` — дайджест не входит в email-тред конкретного тикета, не требует threading-заголовков и настроенного mailbox; SMTP-настройки общие).

**Состав письма** (две секции, пустые не выводятся):
1. **Ваши заявки в работе** — назначенные на агента, статусы `open`/`pending`: номер, тема, автор (ФИО или email заявителя), дней в работе (`NOW() - assigned_at`), абсолютная ссылка `{portal_base_url}/helpdesk/tickets/{id}`.
2. **Неназначенные заявки** — `assignee_user_id IS NULL`, статусы `new`/`open`/`pending`: общий блок (одинаковый во всех сводках, один запрос на всех), дней в работе от `created_at`.

**Правила:**
- Агент без личных тикетов **и** без неназначенных в системе — письмо не получает (не спамим пустых).
- `portal_base_url` — из `SystemSettings` (runtime, default `https://portal.company.local`); trailing-slash нормализуется.
- Пользовательские данные (тема/ФИО) — `html.escape` (XSS-защита).
- Тема фиксированная `"Ежедневная сводка заявок техподдержки"` (без `[#TKT-N]` токена).

**Расписание** (singleton `helpdesk_digest_settings`, §3): `enabled` + `digest_hour:digest_minute` + `digest_schedule` (`weekdays`=пн–пт / `daily`). ARQ cron не умеет менять расписание без рестарта → применяется проверенный helpdesk-паттерн: cron запускается **ежечасно**, реальное срабатывание — чистая функция `should_send_today` (час/минута/день недели совпадают). **Идемпотентность внутри дня** — Redis-ключ `DIGEST_LAST_SENT_KEY` (та же календарная дата → выход). **Distributed lock** `helpdesk:digest:lock` (TTL 5 мин) защищает от двойного запуска при нескольких воркерах.

> Frontend (Admin UI блока настроек дайджеста в `HelpdeskTab.vue`) — отдельная задача; backend API `GET/PUT /settings/digest` готов.

---

## 10. Архив и cron

Все cron гейтируются модулем (`modules.helpdesk.enabled`); при выключенном — выходят без работы.

| FQN | Расписание | run_at_startup | Назначение |
|---|---|---|---|
| `poll_helpdesk_mailbox` | `second={0,30}` | нет | IMAP-фетч (реальный интервал из БД, см. §8) |
| `auto_close_resolved_tickets` | `hour=3, minute=25` | нет | `resolved → closed` при `last_activity_at < NOW() - 7d` (`closed_by_user_id=NULL`, system) |
| `archive_closed_tickets_task` | `hour=3, minute=20` | нет | `closed` старше `HELPDESK_ARCHIVE_AFTER_DAYS` (14) → архив (jsonb + CASCADE) |
| `create_next_helpdesk_archive_partition` | `month=*, day=1, hour=2` | **да** | Помесячные партиции архива на 3 мес вперёд |
| `cleanup_helpdesk_attachments_task` | `hour=4, minute=0` | нет | Удаление папок тикетов, архивированных > `HELPDESK_ARCHIVE_FILES_TTL_DAYS` (180) назад |
| `send_helpdesk_digest` | `minute=0` (ежечасно) | нет | Ежедневная email-сводка агентам (реальное время — из `helpdesk_digest_settings`, см. §9.1) |

**Транзакции (cron):** воркеры открывают `async with AsyncSessionLocal() as db:` (`autocommit=False`) и **обязаны явно `db.commit()`** после изменений. `archive_closed_tickets` и `auto_close_resolved_tickets` коммитят в сервисе при наличии изменений; `poll_mailbox` делает `db.rollback()` в except-цикла UID (защита от session-poisoning: один битый UID не роняет батч), а успешный ingest коммитит сообщение + `helpdesk_email_log` единым commit (идемпотентность).

---

## 11. Константы (`./backend/app/core/constants.py`)

| Константа | Значение | Описание |
|---|---|---|
| `HELPDESK_MAX_ATTACHMENT_MB` | 25 | Максимум одного вложения |
| `HELPDESK_MAX_TOTAL_INGRESS_MB` | 50 | Максимум суммы вложений в письме |
| `HELPDESK_ARCHIVE_AFTER_DAYS` | 14 | Через сколько после `closed` → архив |
| `HELPDESK_ARCHIVE_FILES_TTL_DAYS` | 180 | Через сколько физически удаляются файлы архива |
| `HELPDESK_REOPEN_WINDOW_DAYS` | 7 | Окно auto-reopen из `closed` |
| `HELPDESK_RESOLVED_AUTO_CLOSE_DAYS` | 7 | Через сколько `resolved` без активности → `closed` |
| `HELPDESK_FILES_DIR` | `/data/helpdesk` | Корень локального хранилища вложений |
| `HELPDESK_ATTACHMENT_ALLOWED_MIMES` | frozenset(15) | Разрешённые MIME вложений (png/jpeg/pdf/docx/xlsx/…) |
| `HELPDESK_INLINE_IMAGE_MIMES` | frozenset(4) | Разрешённые MIME inline-картинок rich-редактора (jpeg/png/gif/webp — без SVG, без документов). Лимит — `HELPDESK_MAX_ATTACHMENT_MB`. |

> Константы, а не `SystemSettings`: операционные окна меняются редко, а перенос в `system_config` требует правок 3–4 Pydantic-классов + Admin UI + фронта. Перенос лимитов вложений в runtime-настройки — будущее улучшение.

---

## 12. Module gating

- `HelpdeskModuleSettings(enabled: bool = False)` — `./backend/app/core/modules_config.py`, поле `helpdesk` в `AllModuleSettings`.
- `PUT /api/v1/admin/modules/helpdesk` (`update_helpdesk_module`, AdminDep) — переключает флаг, аудит `modules.toggled`, `invalidate` кэша. Образец — `directories`.
- `bootstrap.is_helpdesk_agent` (bool, default False) — **косметический** флаг для меню/guard'ов фронта (admin=суперсет, иначе SELECT по `helpdesk_agents`); бэкендом не доверяется.

---

## 13. Гостевые заявители и линкование

- Письмо с email без аккаунта → тикет создаётся без `requester_user_id` (гостевая заявка, `requester_email`/`requester_name` из `From`).
- **`link_guest_tickets`** (`./backend/app/services/helpdesk/tickets.py`) — привязывает гостевые тикеты (`requester_user_id IS NULL`) по `LOWER(requester_email) = LOWER(users.email)` к только что материализованному аккаунту. Идемпотентно (повторные логины — no-op).
- **Точка вызова** — OIDC-callback (`./backend/app/api/auth/oidc.py`) после `_upsert_user`, до `db.commit()` (единственный флоу с появлением нового email; local-логин upsert'а не делает — там точки вызова нет). Best-effort: ошибка не ломает логин.

---

## 14. Frontend UI

### Роуты и guards (`./frontend/src/router.ts`)

| Path | Guard (`meta`) | Страница |
|---|---|---|
| `/helpdesk/my` | `requiresAuth` | `HelpdeskMyTicketsPage` — список своих заявок |
| `/helpdesk/my/:id` | `requiresAuth` | `HelpdeskMyTicketDetailPage` — карточка своей заявки |
| `/helpdesk` | `requiresHelpdeskAgent` | `HelpdeskAgentInboxPage` — агентский инбокс |
| `/helpdesk/tickets/:id` | `requiresHelpdeskAgent` | `HelpdeskAgentTicketDetailPage` — карточка агента |

- `requiresHelpdeskAgent` (в `requireRole`): пропускает `auth.isHelpdeskAgent || auth.isAdmin`, иначе редирект на `/helpdesk/my`. `isHelpdeskAgent` — ref из `bootstrap.is_helpdesk_agent` (косметический; бэкенд перепроверяет по БД).
- Module-gate: все `/helpdesk*` зарегистрированы в `MODULE_ROUTES` → при выключенном `helpdesk.enabled` редирект на home.

### Меню (`./frontend/src/composables/useAppMenu.ts`)

- «Поддержка» (`/helpdesk/my`) — всем авторизованным, виден только при `modules.helpdesk.enabled`.
- «Инбокс поддержки» (`/helpdesk`) — агентам/админам (при включённом модуле).
- Подсветка активного пункта: `/helpdesk/tickets/*` и `/helpdesk` → `helpdesk-inbox`; `/helpdesk/my*` → `helpdesk-my`.

### Страницы инициатора (FE-2)

- **`HelpdeskMyTicketsPage`**: список карточек, фильтр статусов, пагинация, кнопка «Создать заявку» → `TicketCreateModal` (subject + description + вложения, `multipart/form-data`). Загрузка через `fetchMyTickets`.
- **`HelpdeskMyTicketDetailPage`**: шапка (номер, тема, статус-бейдж), timeline сообщений (`TicketMessageList`), форма ответа (`TicketReplyForm`). Служебные поля (статус, ответственный, создана, обновление) и профиль заявителя — в правом сайдбаре (`TicketInfoCard` + `RequesterProfileCard`). Для закрытых — no-reply.

### Страницы агента (FE-3)

- **`HelpdeskAgentInboxPage`**: фильтры (`q`, `status`, `unassigned`), карточки тикетов, кнопка «Взять» на неназначенных (`takeTicket`).
- **`HelpdeskAgentTicketDetailPage`**: действия `take` / смена статуса (через select) / `reopen`; переключатель public/internal в форме ответа; email-метаданные сообщений (agent-mode в `TicketMessageList`).

### Общие компоненты (`./frontend/src/components/helpdesk/`)

| Компонент | Назначение |
|---|---|
| `TicketStatusBadge.vue` | Цветной бейдж статуса (i18n-лейбл). |
| `TicketDetailHeader.vue` | Общий хедер карточки тикета для агентской и инициаторской страниц. Компактная строка: `#номер` — тема — actions-slot (кнопки/переключатель статуса) справа (`margin-left:auto`). Статус-бейдж и source в шапке отсутствуют — они в `TicketInfoCard` (правый сайдбар). |
| `TicketInfoCard.vue` | Служебные поля тикета (Статус, Способ получения, Ответственный, Создана, Обновление) в правом сайдбаре (`ticket-layout__aside`), над `RequesterProfileCard`. Рендерится всегда; статус — через `TicketStatusBadge`; source — локализованный лейбл (`helpdesk.sources.{web,email}`); при отсутствии assignee — плейсхолдер «Не назначен». |
| `RequesterProfileCard.vue` | Краткая «визитка» заявителя (email, отдел, должность, город, мобильный/внутренний телефоны) из `ticket.requester_profile`; рендерится в правом сайдбаре карточки тикета (`ticket-layout__aside`, под `TicketInfoCard`); скрывается, если профиль не построен (гость без аккаунта в портале). |
| `TicketMessageList.vue` | Переписка в виде **чата с аватарами** (мессенджер-вид): каждое сообщение — `flex-row` с круглым аватаром (`n-avatar`, инициалы из ФИО/email local-part, детерминированный цвет из email) и пузырём (`max-width:75%`). `inbound` (от заявителя) — слева, `outbound` (от агента) — справа (`flex-direction:row-reverse`). Заголовок пузыря: имя автора + `internal`-тег (для заметок агентов) + source-тег (`email`/`web`) + (в agent-mode) email автора + дата. Тело — sanitized HTML (`DOMPurify`) или `pre-wrap` plain. Вложения — чипы-ссылки. `internal`-заметки — пунктирная янтарная рамка. Единый стиль для web и email-сообщений (после отсечения цитат email-ответы чистые). |
| `TicketReplyForm.vue` | **Rich-редактор** (TipTap, общий `RichEditor.vue` из новостей/КБ) + вложения + переключатель `visibility` (только agent-mode). Контент хранится как markdown (v-model), на submit рендерится в HTML (`markdown-it`, `mdUnsafe`) и эмитится как `body_html` (plain `body_text` деривит бэк). Inline-картинки грузятся через `:upload-endpoint="/api/v1/helpdesk/tickets/{ticketId}/inline-media"` (требует пропс `ticketId`). |
| `TicketCreateModal.vue` | Модалка создания заявки с вложениями. |

### Admin UI (FE-4)

- **ModulesTab**: карточка «Техподдержка» с переключателем (`useModulesState.onToggleHelpdesk` → `PUT /admin/modules/helpdesk`).
- **HelpdeskTab** (`/admin?tab=helpdesk`, группа `system`):
  - `HelpdeskAgentsManager` — список агентов, remote-search по сотрудникам (`fetchUsers`), переключатель `notify_new`, удаление.
  - `HelpdeskMailboxSettings` — singleton IMAP-форма (write-only пароль с индикатором «задан», кнопка «Проверить соединение»).

### Загрузка с вложениями и rich-контентом

Создание заявки и ответы — `multipart/form-data` через `apiUpload` (FormData). Поля формы: `subject`/`description`/`body_text` (+ `body_html`/`visibility` для агента) + `files[]`. **Ответы агента/заявителя** идут через rich-редактор (TipTap): фронт шлёт `body_html` (HTML из markdown), `body_text` опционален (бэк деривит через `normalize_message_bodies`, если пуст — `html_to_plain(sanitize_html(body_html))`). Бэк повторно sanitize'ит `body_html` (nh3) на запись — двойная защита (заявитель неконтролируемая сторона). **Создание заявки** (`TicketCreateModal`) — пока plain `description` + файлы (rich-редактор не подключён: `ticket_id` ещё не существует → media-endpoint недоступен). Скачивание вложения — прямой anchor `:href="/api/v1/helpdesk/attachments/{id}"` с `target="_blank"` (как feedback), бэкенд отдаёт `StreamingResponse`.

### i18n

Топ-уровневый объект `helpdesk.*` (статусы, действия, лейблы, ~40 ключей) + `nav.helpdesk`/`nav.helpdeskInbox`. **Готча:** `@` в i18n-строках (например `support@company.local`) ломает парсер vue-i18n (интерпретируется как linked-message) — экранировать через литерал `{'@'}`.

---

## 15. Развёртывание / включение

1. Миграция `075` (применяется автоматически при старте backend через `migrate.sh`).
2. Миграция `076` (расписание сводки, применяется автоматически).
3. Миграция `077` (колонки `is_inline`/`content_id` на `helpdesk_attachments` — schema-drift фикс; применяется автоматически).
4. Зависимости `aioimaplib` + `cryptography` — в `pyproject.toml` (требуется пересборка `backend` + `worker`).
5. Пересобрать `frontend` (новые страницы/роуты/меню/компоненты): `docker compose build frontend`.
6. Включить модуль: **Admin → Модули → «Техподдержка» → On** (или `PUT /api/v1/admin/modules/helpdesk` `{"enabled": true}`, или правка `/data/settings/modules.json`).
7. Для email-flow: **Admin → Система → «Техподдержка» → mailbox-форма** с IMAP-настройками и паролем (проверить кнопкой «Проверить соединение»).
8. Назначить агентов: **Admin → Система → «Техподдержка» → Агенты** (поиск по сотрудникам) или `POST /api/v1/helpdesk/agents`.
9. Локальная папка `/data/helpdesk/` должна быть доступна на запись (volume).
10. (Опц.) Сводка по умолчанию включена (будни 08:00 UTC). Настроить время/выключить — `PUT /api/v1/helpdesk/settings/digest`.

> Модуль работоспособен и без IMAP (web-only helpdesk): `helpdesk.enabled=true` без mailbox-настройки — заявки создаются и обрабатываются через портал, исходящие публичные ответы не отправляются на email (создаётся только сообщение).
