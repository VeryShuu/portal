# Модуль «Техническая поддержка» (Helpdesk)

> **Когда читать:** при работе с заявками, перепиской и вложениями тикетов; при изменении таблиц `helpdesk_*`; при правках IMAP-ingress, статус-машины, mailbox-settings, архива; при модификации мастер-флага `helpdesk` и агентов поддержки; при правках страниц/роутов/меню helpdesk.
> **Ключевой код:** `./backend/app/api/helpdesk/`, `./backend/app/services/helpdesk/` (вкл. `email_quote.py` — отсечение цитат), `./backend/app/models/helpdesk.py`, `./backend/app/worker/tasks/helpdesk.py`, `./frontend/src/pages/helpdesk/`, `./frontend/src/components/helpdesk/`.
> **ADR:** —. **См. также:** `./docs/email.md`, `./docs/api-contracts.md`, `./docs/db-schema.md`, `./docs/roles-matrix.md`.

> Замена OTRS внутри портала. Полный жизненный цикл заявки: приём из email (IMAP-polling support-ящика) или веб-формы → назначение ответственного → переписка с инициатором (двусторонний email-thread через `[#TKT-{number}]` в теме и `Message-ID`/`In-Reply-To`/`References`) → закрытие → архив. Вложения хранятся **локально** в `/data/helpdesk/TKT-{number}/` (по образцу feedback), Nextcloud не используется. Стартовое состояние модуля — выключен (`helpdesk.enabled=false`); включение = флаг в `modules.json` + заполненный `helpdesk_mailbox_settings`.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/helpdesk/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/helpdesk/`, `./frontend/src/components/helpdesk/`, admin-вкладка `./frontend/src/pages/admin/tabs/HelpdeskTab.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/helpdesk.py`): 5 cron-задач |
| Хранилище | БД (PostgreSQL) + локальная ФС `/data/helpdesk/TKT-{number}/` (вложения) |
| Префикс API | `/api/v1/helpdesk` |
| Email | transactional outbox `kind=helpdesk` (см. `./docs/email.md`) |
| Шифрование секрета | Fernet (`./backend/app/core/secret_crypto.py`), ключ из `SECRET_KEY` |
| Module gate | `modules.json → helpdesk.enabled`; при `false` весь API → 404, воркеры не работают |
| Развернуть как | следующий свободный модуль (после `signature`), см. `./backend/app/core/modules_config.py` |

### Возможности

- Создание заявки инициатором через веб-форму (`multipart/form-data` с вложениями) **или** автоматически из входящего письма на support-ящик.
- Статус-машина `new → open → pending → closed` с auto-reopen из `closed` — в течение `HELPDESK_REOPEN_WINDOW_DAYS` (7). `closed` = единый финал (агент завершил работу → архив); статус `resolved` упразднён (миграция `079`).
- Агентский инбокс с фильтрами (`status`, `assignee`, `unassigned`, `source`, `q`), взятие в работу (`take`), назначение (`assign`), ручная смена статуса, reopen.
- Двусторонний email-thread: исходящие публичные ответы агентов уходят через outbox (`kind=helpdesk`) с каноническими заголовками; входящие матчятся по `In-Reply-To`/`References` + fallback по токену `[#TKT-{number}]` в теме.
- **Email Cc — «ответить всем»** (миграция `083`): заявитель ставит в копию сотрудников при подаче заявки по почте → поддержка видит всех участников (`participants` в карточке агента) и может ответить всем (чекбокс «Ответить всем» + редактируемый список Cc в форме ответа). Cc хранится на уровне сообщения; участники тикета агрегируются в рантайме. В веб-версии создания заявки Cc нет.
- Гостевые заявители (email без аккаунта) создаются без `requester_user_id`; при появлении аккаунта с тем же email — авто-линкование (`link_guest_tickets` в OIDC-callback).
- Вложения: локальное streaming-хранилище (MIME через `python-magic`, path-traversal guard), скачивание через `StreamingResponse` (не `FileResponse`, не `X-Accel-Redirect`).
- Архивирование закрытых тикетов в партиционированную таблицу `helpdesk_tickets_archive` (jsonb-снимок) с TTL-очисткой файлов.
- In-app уведомления (агенты/инициатор/assignee) через общий `notifications`-движок.
- **Пользовательский UI** (Vue): список своих заявок + создание с вложениями + карточка с перепиской и ответом; агентский инбокс (фильтры, take) + карточка агента (assign/status/reopen).
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
| Router | `./backend/app/api/helpdesk/_common.py` | Сериализаторы (`ticket_to_out`/`ticket_to_agent_out`/`ticket_to_list_out`/`message_to_out`), `build_requester_profile`. |
| Service | `./backend/app/services/helpdesk/outbound.py` | Исходящие email-продюсеры (outbox, `kind=helpdesk`): `enqueue_reply_outbound` (ответ агента + история), `enqueue_assigned_email` (назначение), `enqueue_created_email` (заявка зарегистрирована) + `load_mailbox`/`load_user`/`support_domain`/`reply_to_address` (явный `support_reply_to`, иначе `support_address`)/`collect_ticket_references`/`_sanitize_references` (CRLF-strip в продюсере — defense-in-depth, worker стрипает повторно). Без `db.commit` — outbox-инвариант (AGENTS.md): запись коммитится единым commit'ом с бизнес-операцией в роутере. |
| Service | `./backend/app/services/helpdesk/tickets.py` | Бизнес-логика тикетов: создание (инвариант первого сообщения), списки, assign/status/reopen, `link_guest_tickets`, `resolve_requester_user`. `assign_ticket` не коммитит (outbox-инвариант — единый commit в роутере). |
| Service | `./backend/app/services/helpdesk/messages.py` | Добавление ответов (requester/agent), генерация `email_message_id`, `normalize_message_bodies` (sanitize HTML через nh3 + деривация plain для email-треда — для rich-редактора). `add_agent_reply` не коммитит (outbox-инвариант — единый commit в роутере с outbox-записью). |
| Service | `./backend/app/services/helpdesk/lifecycle.py` | Чистая статус-машина (тестируется без БД). |
| Service | `./backend/app/services/helpdesk/threading.py` | Парсинг email-заголовков (Message-ID/References/токен темы), synthetic id, normalisation, `decode_mime_header` (RFC 2047). |
| Service | `./backend/app/services/helpdesk/email_quote.py` | Отсечение цитируемых писем во входящих ответах: маркер-разделитель в исходящих (`build_reply_marker_*`) + эвристический fallback (`strip_quoted_reply`/`strip_quoted_html`). |
| Service | `./backend/app/services/helpdesk/email_thread.py` | Сборка истории переписки для исходящего письма (`build_thread_history`): plain (email-цитатник) + html-блоки (через `email_template.render_history_block`), лимит `HISTORY_MAX_MESSAGES`. Добавляется после ответа агента в `_try_enqueue_outbound` через шаблон `render_reply_email`. |
| Service | `./backend/app/services/helpdesk/email_template.py` | Единый HTML-шаблон исходящих helpdesk-писем: `render_reply_email` (ответ агента + история), `render_system_email` (назначение) и `render_new_ticket_agent_email` (уведомление агентам о новой заявке — аналог OTRS, единый стиль портала: «Поступила новая заявка» + блок контактов заявителя ФИО/Почта/Телефон/Внутренний номер из модели `User` + «Текст заявки:» в блоке-цитате + ссылка на портал; футер без призыва «ответьте на письмо», через outbox `kind=generic`) — жёстко зафиксированный шрифт Times New Roman 14px (единый размер во всём письме, иерархия через `font-weight`/`color`), компактная шапка (единый заголовок «#номер — тема» по центру — без статуса/исполнителя/обновления), контент на всю ширину письма (`width:100%`, без 600px-ограничения — как в OTRS), минималистичный таймлайн переписки (подпись «Сообщение от — {ФИО}» единая для всех — и агента, и заявителя; дата/время не выводятся — есть в письме; горизонтальные `<hr>`-разделители между сообщениями; без левых вертикальных полос/карточек/бейджей; заголовок «Предыдущие сообщения» убран — история идёт сразу за ответом), эвристическое приглушение email-подписей отправителей («↧ Подпись скрыта»), компактный блок вложений «📎 Вложения» с размерами, футер (призыв «Вы можете оставить комментарии по заявке ответив на это письмо» — по центру, жирный + ссылка на портал). Без reply-маркера: отсечение цитат при ответе — по заголовкам почтового клиента (как в OTRS). Inline-стили, совместимость с Outlook/Gmail/Apple Mail. |
| Service | `./backend/app/services/helpdesk/email_images.py` | Локализация картинок входящего письма при ingress (Zammad/Freshdesk-подход): inline `cid:` (`multipart/related`/`Content-ID`) и внешние `http(s)://` сохраняются в локальный FS как `HelpdeskAttachment`, `src` в `body_html` переписывается на относительный `/api/v1/helpdesk/attachments/{id}`. SSRF-guard (private/loopback/link-local blocked), httpx-выкачка с таймаутом и лимитом, best-effort. |
| Service | `./backend/app/services/helpdesk/ingress.py` | IMAP-фетчер: poll, anti-loop, matching, ingest, идемпотентность через `helpdesk_email_log`, `probe_imap_connection`. |
| Service | `./backend/app/services/helpdesk/attachments.py` | Локальное хранение вложений: upload (`UploadFile` web-путь) / `save_image_bytes` (байты — inline/remote при ingress) / resolve / download-path / cleanup. |
| Service | `./backend/app/services/helpdesk/archive.py` | Перенос closed → архив, cleanup файлов, read-only список/карточка архива. |
| Service | `./backend/app/services/helpdesk/archive_partitions.py` | Помесячные партиции `helpdesk_tickets_archive` (raw asyncpg, аналог `audit_partitions`). |
| Service | `./backend/app/services/helpdesk/notifications.py` | In-app уведомления по событиям (через `create_notification` + Redis SSE) + email-уведомление агентам о новой заявке (`notify_ticket_created_email`, через outbox `kind=generic`) + тела письма о назначении (`build_assigned_email_*`). |
| Service | `./backend/app/services/helpdesk/digest.py` | Ежедневная email-сводка агентам: расписание (`should_send_today`), сбор данных, построение тел, оркестрация отправки через outbox `kind=generic`. |
| Service | `./backend/app/services/helpdesk/reads.py` | Per-agent read-state (миграция 080): `mark_ticket_seen` (UPSERT `last_seen_at`, без commit), `has_unread_requester_messages` (EXISTS публичного inbound-сообщения новее `last_seen_at`), `enrich_with_unread` (один запрос для всего списка инбокса → map `{ticket_id: bool}`, защита от N+1). |
| Model | `./backend/app/models/helpdesk.py` | 9 моделей: `HelpdeskTicket`, `HelpdeskMessage`, `HelpdeskAttachment`, `HelpdeskAgent`, `HelpdeskEmailLog`, `HelpdeskMailboxSettings`, `HelpdeskDigestSettings`, `HelpdeskTicketArchive`, `HelpdeskTicketRead`. |
| Schema | `./backend/app/schemas/helpdesk.py` | Pydantic-схемы + StrEnum-наборы (`HelpdeskStatus`/`Source`/`Direction`/`Visibility`). |
| Worker | `./backend/app/worker/tasks/helpdesk.py` | 5 cron: poll, archive, partition, cleanup, daily-digest. |
| Crypto | `./backend/app/core/secret_crypto.py` | `encrypt_secret`/`decrypt_secret` (Fernet, ключ из `SECRET_KEY`). |
| Migration | `./backend/migrations/versions/075_add_helpdesk.py` | 7 таблиц + первая партиция архива. |
| Migration | `./backend/migrations/versions/076_add_helpdesk_digest_settings.py` | Singleton `helpdesk_digest_settings` (расписание сводки) + seed. |
| Migration | `./backend/migrations/versions/077_add_helpdesk_attachments_inline_columns.py` | Колонки `is_inline`/`content_id` на `helpdesk_attachments` (schema-drift фикс: были в ORM-модели с 24a15bd, но БД-миграции не было → 500 на `selectinload(HelpdeskMessage.attachments)`). |
| Migration | `./backend/migrations/versions/078_add_helpdesk_fts.py` | Полнотекстовый поиск: `search_tsvector` (tickets, over subject+description) + `body_tsvector` (messages, over body_text) — generated STORED tsvector + GIN-индексы. Заменяет `ilike` в агентском инбоксе на `websearch_to_tsquery('russian_hunspell')`, см. §4. |
| Migration | `./backend/migrations/versions/079_drop_helpdesk_resolved.py` | Упразднён статус `resolved`: data-mig `resolved → closed` + CHECK без `resolved` (единый финал — `closed`). |
| Migration | `./backend/migrations/versions/080_add_helpdesk_ticket_reads.py` | Marker-таблица `helpdesk_ticket_reads(ticket_id, user_id, last_seen_at)` для подсветки непрочитанных заявок в инбоксе агента. UNIQUE `(ticket_id, user_id)` для UPSERT, CASCADE на обеих FK — cleanup-cron не нужен. |
| Frontend API | `./frontend/src/api/helpdesk.ts` | Типы + вызовы (tickets/messages/inbox/attachments, agents, mailbox) с multipart-загрузкой через `apiUpload`. |
| Frontend Queries | `./frontend/src/queries/helpdesk.ts` | TanStack Query hooks + mutations (с инвалидацией ключей `helpdesk.*`). |
| Frontend Store | `./frontend/src/stores/auth.ts` | `isHelpdeskAgent` ref (из `bootstrap.is_helpdesk_agent`) — косметический, бэкендом не доверяется. |
| Frontend Router | `./frontend/src/router.ts` | 4 роута + guard `requiresHelpdeskAgent` + module-route gating. |
| Frontend Menu | `./frontend/src/composables/useAppMenu.ts` | Пункт «Поддержка» (всем, gated) + «Инбокс поддержки» (агентам). |
| Frontend Pages | `./frontend/src/pages/helpdesk/` | `HelpdeskMyTicketsPage` (двухблочный вид: ожидают / в работе), `HelpdeskMyArchivePage` (отдельный роут `/helpdesk/my/archive`), `HelpdeskMyTicketDetailPage`, `HelpdeskAgentInboxPage` (двухблочный вид + переключатель мои/все), `HelpdeskAgentTicketDetailPage`, `HelpdeskArchivePage` (отдельный роут `/helpdesk/archive`). |
| Frontend Components | `./frontend/src/components/helpdesk/` | `TicketStatusBadge`, `TicketMessageList`, `TicketReplyForm` (rich-редактор TipTap), `TicketCreateModal`, `TicketList`/`TicketListItem` (таблица инбокса/архива), `TicketInfoCard`, `TicketDetailHeader`, `RequesterProfileCard`. |
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
| `status` | `String(20)` NOT NULL default `'new'` | `new`/`open`/`pending`/`closed` |
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
| `search_tsvector` | `TSVECTOR` NULL | Generated STORED: `to_tsvector('russian_hunspell', subject \|\| description)` (миграция `078`). Поиск инбокса — `search_tsvector @@ websearch_to_tsquery(...)`, GIN `idx_helpdesk_tickets_fts`. |

Индексы: `status`; partial `assignee`/`requester`/`ref_archive` (WHERE NOT NULL); `LOWER(requester_email)`; `last_activity DESC`; partial `open_list` (status IN new/open/pending); GIN `idx_helpdesk_tickets_fts` (FTS). `CHECK` на `status` и `source`.

### `helpdesk_messages` — сообщение переписки

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | Также используется как `message_uuid` в `Message-ID` |
| `ticket_id` | UUID NOT NULL → `helpdesk_tickets.id` `CASCADE` | |
| `author_user_id` | UUID NULL → `users.id` `SET NULL` | NULL для гостевых писем |
| `author_email` / `author_name` | `String(320)` NOT NULL / `String(255)` NULL | |
| `direction` | `String(10)` NOT NULL | `inbound` (от клиента) / `outbound` (от агента) |
| `body_text` / `body_html` | `Text` NOT NULL / `Text` NULL | HTML sanitized (`nh3`) |
| `body_tsvector` | `TSVECTOR` NULL | Generated STORED: `to_tsvector('russian_hunspell', body_text)` (миграция `078`). Поиск по телам ответов — EXISTS-подзапрос `body_tsvector @@ websearch_to_tsquery(...)`, GIN `idx_helpdesk_messages_fts`. |
| `source` | `String(20)` NOT NULL | `email` / `web` |
| `email_message_id` | `String(998)` NULL | RFC 5322 Message-ID (входящий и исходящий) |
| `in_reply_to` | `String(998)` NULL | |
| `cc` | `JSONB` NULL | Адресаты в копии письма (миграция `083`): `[{"email":"a@x","name":"Иван"}]`. Для inbound — из заголовка `Cc` входящего письма (`threading.extract_cc`); для outbound — из формы ответа агента (чекбокс «Ответить всем»). `None` для старых сообщений и ответов без копии. Участники тикета «в сборе» НЕ хранятся — агрегируются в рантайме в сериализаторе карточки. |
| `created_at` | `TIMESTAMPTZ` | |

**Инвариант:** частичный unique-индекс `uq_helpdesk_messages_email_msg_id` на `email_message_id` (WHERE NOT NULL) — защита от дублей при ingress.

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

### `helpdesk_ticket_reads` — marker «непрочитано» в инбоксе агента (миграция 080)

Per-agent read-state: одна строка на пару `(ticket_id, user_id)` с `last_seen_at` (timestamp последнего открытия карточки тикета агентом). Marker-таблица по образцу `news_likes`/`kb_article_feedback` (композитный UNIQUE), архитектурно ближе к Zammad/FreeScout (`conversation_user` pivot), чем к OTRS (per-article `ticket_flag` — избыточно для наших объёмов).

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `ticket_id` | UUID NOT NULL → `helpdesk_tickets.id` `CASCADE` | |
| `user_id` | UUID NOT NULL → `users.id` `CASCADE` | |
| `last_seen_at` | `TIMESTAMPTZ` NOT NULL default `NOW()` | Когда агент последний раз открывал карточку |
| `created_at` | `TIMESTAMPTZ` | Первое открытие |

Индексы: `uq_helpdesk_ticket_reads_ticket_user` (UNIQUE на `(ticket_id, user_id)` — UPSERT-цель), `ix_helpdesk_ticket_reads_user` (lookup «все мои read-states» для обогащения инбокса). `ON DELETE CASCADE` на обеих FK → cleanup-cron не нужен (архивация/удаление тикета или аккаунта чистит автоматически).

**Контракт «непрочитанности»** (`services/helpdesk/reads.py`): тикет непрочитан для агента, если существует входящее сообщение (`direction='inbound'` — ответ заявителя) с `created_at > COALESCE(last_seen_at, '-infinity')`. Если строки read нет → `-infinity` (т.е. **любой** ответ заявителя делает тикет непрочитанным, даже месячной давности — агент его действительно не открывал в этом UI). Ответы других агентов (`direction='outbound'`) и свои собственные НЕ считаются.

**Точка «прочитано»** — открытие карточки тикета агентом: `POST /tickets/{id}/read` → `mark_ticket_seen` (UPSERT `last_seen_at = NOW()`). Не требует audit (read-state — бизнес-состояние, не мутация, как `notifications.read`) и rate-limit (доступ только `HelpdeskAgentDep`).

### `helpdesk_max_bot_settings` — singleton (id=1, миграция 081)

Конфигурация MAX-бота для оповещений о новых заявках в один общий чат поддержки (max.ru). По образцу `helpdesk_digest_settings`: все колонки nullable/DEFAULT, строка засевается миграцией сразу, `enabled=False` по умолчанию (канал выключен, пока админ не активирует его в Helpdesk-вкладке).

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | SMALLINT PK DEFAULT 1, `CHECK (id=1)` | Singleton |
| `enabled` | BOOLEAN NOT NULL default `FALSE` | Канал включён |
| `bot_token_enc` | TEXT, nullable | Шифр токена бота (Fernet из `SECRET_KEY`, как `imap_password_enc`); plaintext не возвращается API (write-only) |
| `chat_id` | VARCHAR(64), nullable | ID чата поддержки (ручной ввод админом; берётся у GetID-бота MAX или через `GET /chats` Bot API) |
| `updated_by_user_id` | UUID → `users.id` `SET NULL` | Кто последний менял |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

Канал готов к отправке, когда `enabled=True AND bot_token_enc IS NOT NULL AND chat_id IS NOT NULL` (флаг `configured` в API-ответе).

### `messenger_outbox` — transactional outbox для мессенджеров (миграция 081)

Полный аналог `email_outbox` для не-email каналов. Поле `provider` зарезервировано для будущих провайдеров (Telegram/Slack); сейчас используется только `'max'`. CRUD идёт через raw SQL в `services/messenger_outbox.py` (FOR UPDATE SKIP LOCKED, retry/backoff/DLQ), ORM-модель в `models/helpdesk.py` существует только для типизации.

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `provider` | VARCHAR(32) NOT NULL, `CHECK IN ('max')` | Провайдер (зарезервировано) |
| `chat_id` | VARCHAR(64) NOT NULL | Куда отправлять |
| `text` | TEXT NOT NULL | Тело сообщения |
| `payload` | JSONB NOT NULL default `'{}'` | attachments + формат (для MAX: `{"attachments": [inline_keyboard], "format": "markdown"}`) |
| `status` | VARCHAR(16) default `'PENDING'` | `PENDING/SENDING/SENT/FAILED/DLQ/CANCELLED` |
| `attempts` / `max_attempts` | INTEGER | Счётчик попыток / лимит (по умолчанию 6) |
| `next_attempt_at` | `TIMESTAMPTZ` default `NOW()` | Когда воркер возьмёт запись (для retry/backoff) |
| `last_error_type` / `last_error_class` / `last_error` | VARCHAR/TEXT | Диагностика последней ошибки |
| `sent_at` | `TIMESTAMPTZ`, nullable | Время успешной отправки |
| `related_resource_type` / `related_resource_id` | VARCHAR/UUID | Связь с бизнес-сущностью (`helpdesk_ticket` + id) |
| `created_by_user_id` | UUID, nullable | Кто создал (для audit) |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

Индексы: `ix_messenger_outbox_pending ON (next_attempt_at) WHERE status='PENDING'` (claim-очередь), `ix_messenger_outbox_stale ON (updated_at) WHERE status='SENDING'` (watchdog для «зависших» SENDING). Воркер `process_messenger_outbox` (cron каждые 15с, distributed lock) → `cleanup_messenger_outbox` (cron 4:20, удаление SENT старше 30 дней).

Retry-классификация (отличается от email): 429/5xx/timeout → transient (retry), 4xx (auth/not-found) → permanent (DLQ сразу, чинить в UI).

---

## 4. API

Префикс `/api/v1/helpdesk`. Все эндпоинты требуют авторизации и гейтируются `require_helpdesk_module` (404 при выключенном модуле). Порядок объявления в `tickets.py` важен: `/tickets/my*` → `/tickets` (агентский) → `/tickets/{id}`.

### Инициатор (`CurrentUser`)

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/tickets` | Создать заявку (`multipart/form-data`: `subject`, `description?`, `description_html?`, `files[]`). С 2026-07: rich-редактор TipTap — `description_html` (sanitized nh3), `description` (plain) optional и деривируется из HTML для FTS/email-plain/list, если пуст; валидация «plain ИЛИ html непуст». Обратно-совместим: старые клиенты (только `description`) работают, `description_html` остаётся `None`. Rate-limit 5/мин. 201. |
| `GET` | `/tickets/my` | Свои заявки (`?status`, `?unassigned`, `?assigned`, `?limit`, `?offset`). Каждая строка содержит `unread: bool` — есть ли публичные ответы агентов новее `last_seen_at` (заявительский контракт, `direction='outbound'` в `enrich_with_unread`). `unassigned=true` — только тикеты без агента (блок «ожидают принятия»); `assigned=true` — только назначенные (блок «в работе у специалиста»). Взаимоисключающие. |
| `GET` | `/tickets/my/counts` | Лёгкий count: `{active: N}` — свои тикеты в статусах new/open/pending (для бейджа в меню «Поддержка»). Один `count(*)`, без join'ов. Дешевле list-endpoint'а при polling 60 c. |
| `GET` | `/tickets/my/{id}` | Своя заявка с **публичными** сообщениями. |
| `POST` | `/tickets/my/{id}/read` | Отметить свой тикет прочитанным (снять подсветку ответов агентов) — UPSERT `last_seen_at=NOW()`. ACL: только свои (404 для чужих). Без audit/rate-limit. Зеркало агентского `POST /tickets/{id}/read`. |
| `POST` | `/tickets/my/{id}/messages` | Ответ (`Form`: `body_text`, `files[]`). Всегда `inbound`/`public`. Rate-limit 20/мин. 201. |
| `GET` | `/attachments/{id}` | Скачать вложение (`StreamingResponse`). ACL: автор/агент/админ. |
| `POST` | `/draft-attachments` | Draft inline-картинка для формы **создания** заявки (`multipart`: `file`, растровые jpeg/png/gif/webp). Возвращает `{url, filename}` — URL `/draft-attachments/{id}` вставляется в `description_html` rich-редактором. При `create_ticket` бэкенд backfill'ит: переносит файл в `TKT-{number}/inline/`, переписывает `src` на постоянный `/tickets/{id}/inline-media/{name}`, создаёт inline-`HelpdeskAttachment`, удаляет draft-строку (атомарно в той же транзакции). ACL: только владелец. Лимит `HELPDESK_DRAFT_MAX_PER_USER` (20) активных/юзер; TTL `HELPDESK_DRAFT_TTL_HOURS` (24ч) — cron `cleanup_expired_drafts` удаляет orphan-черновики (юзер закрыл форму, не отправив). Rate-limit 20/мин. |
| `GET` | `/draft-attachments/{id}` | Раздать draft-картинку (nginx `X-Accel-Redirect` в `/internal/helpdesk-media/drafts/usr-{user_id}/`). ACL: только владелец, иначе 404 (не раскрываем существование). |

### Агент (`HelpdeskAgentDep`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/tickets` | Инбокс: фильтры `status`, `assignee`, `unassigned`, `source`, `active_only` (new/open/pending — для двухблочного вида), `q` (полнотекстовый — см. ниже), пагинация. Каждая строка содержит `unread: bool` (есть ли непрочитанные ответы заявителя для этого агента — см. §3 `helpdesk_ticket_reads`); считается одним запросом на весь список (`enrich_with_unread`). |
| `GET` | `/tickets/counts` | Лёгкий count: `{active: N}` — тикеты, назначенные этому агенту, в статусах new/open/pending (для бейджа в меню «Инбокс поддержки»). «Моя нагрузка», не объём очереди: неназначенные не считаются. Один `count(*)`. |
| `GET` | `/tickets/assignable-agents` | Список активных helpdesk-агентов для списка смены ответственного в карточке тикета (`AgentOptionListOut`: `user_id` + `full_name` + `email`, без флагов `notify_new` — PII-минимизация). Доступ — любой агент (`HelpdeskAgentDep`), не только админ: смена ответственного доступна всем агентам. JOIN `users` с `deleted_at IS NULL` (уволенные исключены). Сортировка по ФИО. |
| `GET` | `/users/search` | Поиск пользователя по справочнику (Keycloak) для CC-селектора «Ответить всем» (`?q=`, `?limit=20`). Возвращает `[{user_id, full_name, email}]` (`HelpdeskUserOption`); пользователи без email (сервисные аккаунты Keycloak) отфильтрованы. `<3 символов` → `[]` (не 422 — не ломать empty-state `n-select` на фронте). Симметрично `meetings/participants/search`, но helpdesk-принадлежный (gated `require_helpdesk_module`, не `MeetingsGuard` — поиск работает и при выключенном модуле meetings). Фронт (`CcRecipientPicker`) добавляет synthetic «external»-опцию для email'ов не из справочника. |
| `GET` | `/tickets/{id}` | Карточка (`TicketAgentOut`, **все** сообщения + служебные поля + `participants` — requester ∪ Cc всех сообщений ∪ авторы сообщений, агрегация в рантайме, миграция `083`). |
| `POST` | `/tickets/{id}/messages` | Ответ (`Form`: `body_text`, `body_html?`, `cc[]?`, `files[]`) → `pending` + outbound email. `cc` (опц., повторяющееся Form-поле) — адресаты в копии для «Ответить всем» (миграция `083`); бэк нормализует (lowercase, дедуп, отсечение `support_address`/агента/requester), лимит 20 (422 свыше). 201. |
| `POST` | `/tickets/{id}/assign` | Назначить (`assignee_user_id`). **Реассайн разрешён** — предыдущий assignee заменяется; операция доступна любому агенту (не только админу). Таргет обязан быть активным helpdesk-агентом с живым аккаунтом, иначе 404 `Agent not found` (не раскрываем детали членства — единый ответ «not found» для пользовательского id). Audit-метаданные помечают смену: `reassigned=true` + `previous_assignee_user_id` (отличает от первичного назначения через `take`). Уведомления (in-app + email инициатору) — те же, что у `take` (§9). |
| `POST` | `/tickets/{id}/take` | Взять на себя (409 если уже назначен). |
| `PATCH` | `/tickets/{id}/status` | Сменить статус (409 на запрещённый переход). |
| `POST` | `/tickets/{id}/reopen` | Reopen закрытой (409 из не-`closed`). |
| `POST` | `/tickets/{id}/read` | Отметить тикет прочитанным — UPSERT `last_seen_at=NOW()` для пары `(ticket, agent)`, снимает подсветку в инбоксе. Вызывается карточкой тикета при открытии. Идемпотентно (повторное открытие = no-op). Без audit/rate-limit (read-state — бизнес-состояние). 200 `{ok, ticket_id, last_seen_at}`. |

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
| `GET` | `/settings/max-bot` | Singleton MAX-бота (`enabled`, `bot_token_set`, `chat_id`, `configured`). Строка засевается миграцией 081, всегда существует. |
| `PUT` | `/settings/max-bot` | Обновить. Токен write-only (`bot_token` пусто = прежний шифр). При `enabled=True` требует токен + chat_id, иначе 400. Аудит `helpdesk.max_bot_settings_changed`. |
| `POST` | `/settings/max-bot/test` | Отправляет реальное тестовое сообщение в чат через MAX Bot API (end-to-end: проверяет и токен, и права бота в чате, и сам chat_id). На успех — `{"ok": true, "detail": "Test message sent to chat <id>. Check MAX."}`; на неудачу — маскированная ошибка с подсказкой по HTTP-коду MAX (404 → бот не участник чата, 401 → токен, 403 → права). |

> **Архив в UI** показывается отдельной страницей `/helpdesk/archive` (роут `helpdesk-archive`), которая ходит через общий `GET /tickets?status=closed` (живые закрытые тикеты, не партиционированная таблица). Эндпоинтов `/archive*` и `/email-log` **нет** — service-функции `fetch_archive_list`/`fetch_archive_item` зарезервированы, но не обвязаны роутером (будущее: просмотр тикетов, попавших в `helpdesk_tickets_archive` после `HELPDESK_ARCHIVE_AFTER_DAYS`).

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

### Полнотекстовый поиск в инбоксе (`q`)

Параметр `q` в `GET /tickets` (агентский инбокс) — **полнотекстовый** (миграция `078`), не substring `ilike`. Заменяет прежний `ilike` по `subject`/`description`/`requester_email`, который не находил словоформы и не искал по телам ответов.

- **Конфигурация** — `websearch_to_tsquery('russian_hunspell', q)` (единый для портала regconfig, как в KB-статьях/новостях). Поддерживает морфологию (hunspell + stemming: «доступ» находит «доступа»/«доступом»), регистронезависимость, латиницу в русском тексте (VPN/Outlook).
- **Операторы websearch** (как в Google): `"точная фраза"`, `OR`, `-исключение`. Устойчив к мусору (не падает на спецсимволах, в отличие от `to_tsquery`).
- **Где ищет** (`_agent_filter_conditions`, OR-комбинация):
  1. `subject` + `description` тикета — через `search_tsvector @@ websearch_to_tsquery(...)` (GIN `idx_helpdesk_tickets_fts`);
  2. **тела ответов** (`helpdesk_messages.body_text`) — EXISTS-подзапрос `body_tsvector @@ websearch_to_tsquery(...)` (GIN `idx_helpdesk_messages_fts`). Находит «мы же решали такое полгода назад» по содержимому переписки;
  3. `requester_email` — `ilike` (адреса плохо матчатся tsquery: `@`/точки/домены не нормализуются).
- **Сортировка** — без изменений, `last_activity_at DESC` (FTS только фильтрует, не ранжирует по `ts_rank` — привычно для инбокса, свежие сверху).
- Generated STORED tsvector-колонки вычисляются БД автоматически при вставке/обновлении `subject`/`description`/`body_text` — триггеров и ручного обновления нет.
- **Не входит**: глобальный поиск портала (Cmd-K) helpdesk не подключён (фронт `useGlobalSearch` идёт тремя отдельными запросами; подключение тикетов в палитру — отдельная UI-задача); поиск по архиву (`helpdesk_tickets_archive`, jsonb-снимок).

---



## 5. Права и статус-машина

### ACL

- **Агентство** — `require_helpdesk_agent` (`./backend/app/api/deps.py`): **admin всегда проходит (суперсет)**, иначе `SELECT 1 FROM helpdesk_agents WHERE user_id = :uid` на каждый запрос; при отсутствии → 403. Это единственный источник прав; косметический флаг `is_helpdesk_agent` из `bootstrap` бэкендом **не доверяется** (обновляется только при полной реинициализации).
- **Module gate** — `require_helpdesk_module`: `load_modules_shared(redis)` → `modules.helpdesk.enabled`; `False` → 404 на всём роутере.
- **Requester** — чужой тикет = 404 (фильтр `requester_user_id` внутри `fetch_ticket_for_user`; не раскрывает существование).
- **Download** — автор тикета ИЛИ admin ИЛИ агент (`fetch_for_download`); иначе 404.
- **Смена ответственного (`POST /tickets/{id}/assign`)** — доступна **любому helpdesk-агенту** (не только админу/текущему assignee): операция «передать заявку коллеге». Таргет (`assignee_user_id`) обязан быть **активным helpdesk-агентом** с живым аккаунтом (`helpdesk_agents` JOIN `users` WHERE `deleted_at IS NULL`), иначе 404 `Agent not found` — нельзя передать заявку не-агенту или уволенному сотруднику. Валидация — `is_active_helpdesk_agent` в сервисе; 404 (не 400/422) — единый ответ «not found» для пользовательского id, как и в других lookup'ах helpdesk. Список доступных таргетов — `GET /tickets/assignable-agents` (агентский endpoint).

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
   close        │ (агент завершил работу; админ — закрыть спам из new)
                ▼
              closed
                │
                │ reopen (agent) ИЛИ auto-reopen ответом клиента в окне
                │ HELPDESK_REOPEN_WINDOW_DAYS=7 (после — новый тикет)
                ▼
              open
```

`closed` — единый финальный статус (агент завершил → архив по `HELPDESK_ARCHIVE_AFTER_DAYS`). Статус `resolved` упразднён (миграция `079`): двухфазное закрытие (resolved → ждём подтверждения → closed) убрано — теперь один шаг. Reopen из `closed` — окно 7 дней, после истечения входящий ответ создаёт новый тикет.

Константы переходов:
- `AGENT_SETTABLE_STATUSES = {open, pending, closed}` — то, что агент может выставить через `PATCH /status` (`new`/`archived` не входят).
- `REQUESTER_REOPEN_STATUSES = {pending}` — ответ клиента реопенит в `open` **без окна**.
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
- **`POST /settings/mailbox/test`** — `probe_imap_connection` (login + `SELECT folder`) возвращает `{ok, detail}`. При исключении — `{ok: false, error: "IMAP connection failed (see server logs for details)"}`: голый `str(exc)` больше не отдаётся наружу (aioimaplib в traceback иногда включает команду с паролем). Полный traceback остаётся в server-log через `logger.exception`. Если singleton не настроен → 404.
- Детерминизм ключа важен: любой backend/worker с тем же `SECRET_KEY` расшифровывает секрет (распределённая отправка outbox несколькими воркерами).

---

## 8. Email-интеграция

### Inbound: IMAP-ingress (ТЗ §5.1)

Воркер `poll_helpdesk_mailbox` (cron каждые 30 c) с distributed lock `helpdesk:imap:poll_lock` (TTL 5 мин) и interval guard (реальный интервал — из `poll_interval_seconds`, через Redis `helpdesk:imap:last_poll_at`):

1. `SEARCH ALL` → для каждого UID `FETCH (RFC822)` → парсинг через `email.message_from_bytes`. **Фильтр по `\Seen` не применяется** — оператор читает ящик вручную (в т.ч. в почтовом клиенте), и `\Seen`-письма иначе выпадали бы из потока; дедупликация — на `helpdesk_email_log`. Заголовки `Subject`/`From` декодируются из RFC 2047 encoded-words (`=?charset?B?...?=` — типично для кириллических тем/имён в KOI8-R/Windows-1251) через `threading.decode_mime_header`; иначе тема тикета сохранялась бы нечитаемой (`=?koi8-r?B?zsUg...?=`).
2. **Anti-loop** (ТЗ §5.3): `From == support_address` или заголовки `Auto-Submitted: auto-*` / `Precedence: bulk/list/junk` / `X-Auto-Response-Suppress` → `status=skipped`, тикет не создаётся.
3. **Идемпотентность**: `Message-ID` (или synthetic id для писем без него) проверяется в `helpdesk_email_log`; повтор → `skipped`.
4. **Matching**: по `In-Reply-To`/`References` → `helpdesk_messages.email_message_id`; fallback по токену `[#TKT-{number}]` в теме; последний (опциональный) fallback — plus-маркер `+TKT-{number}` в адресе получателя (`Delivered-To`/`X-Original-To`/`To`). Нет матча → новый тикет (`source=email`). `[#TKT-N]` найден, но живого тикета нет (в архиве) → новый тикет с `references_archived_ticket_number=N`. **Безопасность:** для fallback'ов по subject/recipient-токену (угадываемый последовательный `number`) отправитель сверяется с `ticket.requester_email` (case-insensitive); при несовпадении создаётся новый тикет (защита от инъекции сообщения в чужой тикет). `References`-матч (секретный `Message-ID` исходящего) — без сверки отправителя. **PII в логах:** при несовпадении отправителя логируется маскированный email (``u***@domain``, `_email_domain`) — полное значение хранится в БД/почте, но не в info-логах (защита от попадания адресов в access-логи/агрегатор логов).
5. **Инициатор**: `From` → нормализованный email → `LOWER(users.email)`; найден → `requester_user_id`, иначе гостевая заявка. **Cc** (миграция `083`): заголовок `Cc` парсится `threading.extract_cc` → `[{"email","name"}]` сохраняется в `helpdesk_messages.cc`. Из списка выкидывается `support_address` (иначе ответ «всем» уйдёт в собственный ящик → петля/дубль). `Bcc` не парсится (невидим получателю по RFC 5322). Участники тикета «в сборе» (`participants`) агрегируются в рантайме в сериализаторе карточки — не хранятся в БД.
6. Тело: `text/plain` предпочитается, иначе деривация из sanitized `text/html` (`nh3`). **Отсечение цитаты** предыдущего письма — маркер-разделитель `REPLY_MARKER_TOKEN` + эвристика quoted-reply (см. ниже «Отсечение цитат во входящих ответах»). **Локализация картинок + обычные вложения** (`_localize_attachments_and_images`, см. §6): inline `cid:` (`multipart/related`/`Content-ID`) и внешние `http(s)://` сохраняются в локальный FS, `src` переписывается на `/api/v1/helpdesk/attachments/{id}`; `Content-Disposition: attachment`-части — через `save_image_bytes` (MIME/лимиты/path-traversal guard). Снимает CSP-блок http-картинок и битые `cid:` (раньше — MVP-заглушка без сохранения).
7. Статус: `pending` → `open` (без окна); `closed` → `open` в окне reopen (иначе без изменений); `new`/`open` — без изменений.
8. `helpdesk_email_log` (`created`/`appended`), пометить `\Seen` (и при `delete_after_fetch` — `STORE +FLAGS \Deleted` + `EXPUNGE` в конце цикла). Удаление применяется и для `skipped`-писем (уже видели/anti-loop), а не только для успешно созданных.

### Outbound: `kind=helpdesk` в outbox

- Константа `KIND_HELPDESK = "helpdesk"` (`./backend/app/services/email_outbox.py`).
- **Продюсеры** (`./backend/app/services/helpdesk/outbound.py`, все — без `db.commit`, по outbox-инварианту):
  - `enqueue_reply_outbound` — публичный ответ агента (вызов из `add_agent_message`, только при сконфигурированном mailbox + `support_domain`). `email_message_id` генерируется заранее (`_make_outbound_message_id`) и сохраняется в `helpdesk_messages.email_message_id` до enqueue (для threading).
  - `enqueue_assigned_email` — письмо о назначении (`assign`/`take`).
  - `enqueue_created_email` — письмо «заявка зарегистрирована» при создании тикета (корень треда: `references=[]`, `in_reply_to=None`, см. §9).
- **Outbox-инвариант** (AGENTS.md → Email outbox-pattern): `add_agent_reply`/`assign_ticket` не делают `db.commit()` — только `flush`. Роутер ставит outbox-запись в ту же транзакцию и делает **единый commit** (ответ агента + outbox-запись атомарны). Раньше commit был раздельным → сбой между ними терял письмо заявителю при сохранённом ответе. Сбой enqueue откатывает ответ (агент видит 500, повторяет) — сознательное соответствие инварианту. In-app уведомления — после commit, best-effort.
- **Единый читаемый шаблон письма** (`email_template.py` → `render_reply_email`): жёстко зафиксированный шрифт Times New Roman 14px (единый размер во всём письме, иерархия через `font-weight`/`color`, не через размеры), компактная шапка (единый заголовок «#номер — тема» по центру — без статуса/исполнителя/обновления; белый фон), контент на всю ширину письма (`width:100%`, без 600px-ограничения — как в OTRS), таймлайн-блок ответа агента (префикс «Сообщение от — » перед accent-именем), минималистичная история-таймлайн (подпись «Сообщение от — {ФИО}» единая для всех участников — и агента, и заявителя; агент — accent-именем, заявитель — grey-именем; дата/время не выводятся — есть в письме; горизонтальные `<hr>`-разделители на всю ширину письма между сообщениями; без заголовка «Предыдущие сообщения» — история идёт сразу за ответом; без левых вертикальных полос/карточек/бейджей/теней — различение участников только цветом имени), эвристическое приглушение email-подписей отправителей (маркеры RFC 3676 `--`, «С уважением»/«Best regards», `<hr>`-разделители → компактный блок «↧ Подпись отправителя скрыта» — подпись в БД и веб-версии тикета остаётся полностью, отсекается только в письме), компактный блок вложений «📎 Вложения» с именами и размерами, футер (призыв «Вы можете оставить комментарии по заявке ответив на это письмо» — по центру письма, жирный + ссылка на портал). **Reply-маркер не ставится** (как в OTRS): отсечение цитат при ответе заявителя — по заголовкам почтового клиента (см. ниже «Отсечение цитат во входящих ответах»). Inline-стили. Письмо о назначении ответственного — через `render_system_email` (та же шапка/футер, без истории). Совместимость с Outlook Desktop/Web/Gmail/Apple Mail (только inline-стили, без CSS Grid/Flexbox).
- **Тело письма несёт историю переписки** после ответа агента: `body = {шапка} + {ответ агента} + {история} + {футер}`. История собирается в рантайме из сообщений тикета (`build_thread_history` в `./backend/app/services/helpdesk/email_thread.py`, лимит `HISTORY_MAX_MESSAGES=20`) и оформляется в plain (email-цитатник `От …, {date}:\n> …`) и html (таймлайн-блоки через `render_history_block`). Тогда:
  - заявитель видит контекст прямо в почтовом клиенте (раньше письмо = голый ответ без истории);
  - при ответе его почтовый клиент цитирует весь блок, а `strip_quoted_reply`/`strip_quoted_html` (см. ниже «Отсечение цитат») отрезают процитированную историю/ответ по заголовкам цитаты (Outlook `From:/Sent:`, Gmail `wrote:`) → в ленте портала остаётся только чистый ответ заявителя — как в OTRS, без служебных маркеров в письме;
  - Сохраняемое в БД `HelpdeskMessage` **не мутируется** — история добавляется только к локальным копиям, передаваемым в `enqueue_outbox_email` (агент в ленте портала видит свой чистый ответ).
- **Dispatcher** `_build_helpdesk_mime` (`./backend/app/worker/tasks/email_outbox.py`) — async-ветка (читает вложения с диска через `aiofiles`, поэтому не влезает в синхронный `_build_mime`). Заголовки:
  - `Message-ID: <tkn-{ticket_number}-{message_uuid}@{support_domain}>` (из `payload.message_id_header`)
  - `In-Reply-To` / `References` (цепочка `email_message_id` предшествующих сообщений)
  - `Reply-To: {reply_to_address}` — **явный `support_reply_to` (если задан админом в mailbox-настройках), иначе `support_address`** (базовый ящик поддержки). Раньше `support_reply_to` сохранялся в БД, но игнорировался во всех продюсерах — поле было мёртвым, введённое админом значение терялось. Матчинг входящих ответов идёт по `In-Reply-To`/`References`, токену `[#TKT-{number}]` в теме и опционально по plus-маркеру в адресе получателя — plus-маркер в `Reply-To` для этого не нужен и ранее ломал доставку на ящиках, где local-part ≠ `support` (например `portal@domain` → ответ на несуществующий `support+TKT-N@domain`).
  - `Subject: "[#TKT-{number}] {subject_original}"`
  - `Cc: Name <a@x>, b@y` — **только если агент включил чекбокс «Ответить всем»** в форме ответа (миграция `083`). Берётся из `message.cc` (→ `payload["cc"]`), форматируется через `email.utils.formataddr`. Threading не меняется: `In-Reply-To`/`References`/`Reply-To` без изменений; ответ Cc-получателя по Reply-All вернётся в тот же тикет по references. Отсутствие `cc` в payload → заголовок не ставится.
  - Все значения — через `_sanitize_header` (защита от header-injection). Продюсер (`outbound.py`) тоже санирует `references`/`in_reply_to`/`subject`/`to_email`/`reply_to`/`cc` (каждый email + name) через `_sanitize_header_field`/`_sanitize_references`/`_sanitize_cc_participants` (defense-in-depth — на случай нового продюсера или изменения worker'а).
  - Вложения: `multipart/mixed`, файлы с локального диска; содержимое **не** в JSONB payload (только метаданные).
  - **Inline-картинки rich-ответов** (`_embed_helpdesk_inline_images`): `<img src="/api/v1/.../inline-media/...">` в `body_html` встраиваются как `cid:`-attach (`multipart/related`, `Content-ID`) — заявитель видит картинки в почтовом клиенте. См. блок ниже.
  - **Картинки из истории переписки** (`_embed_helpdesk_attachment_images`): локализованные email-attachments (входящие письма заявителя с inline `cid:`/внешними `http(s)://` картинками, сохранённые через `email_images.py` при ingress) ссылаются в `body_html` на `/api/v1/helpdesk/attachments/{id}` — этот endpoint **требует session-cookie**, а почтовый клиент его не передаёт. Функция одним DB-запросом подтягивает метаданные (`SELECT id, filename, content_type WHERE id IN (...)`), фильтрует по `image/*` (PDF/DOCX пропускаются — они пойдут как обычные attachment), читает файлы с диска и переписывает `src` на `cid:` — заявитель видит картинки в почтовом клиенте. Поддерживаемые форматы те же: jpeg/png/gif/webp. Best-effort: отсутствующие в БД id / нечитаемые файлы → `src` остаётся (веб-лента портала картинку видит).
  - При пустом/невалидном `support_domain` → `ValueError` → outbox mark_failed (RFC 5322 требует валидный домен).

> **Inline-картинки rich-ответов в исходящем email (`cid:`-attach).** Rich-ответ агента (через TipTap) может содержать картинки (`<img src="/api/v1/helpdesk/.../inline-media/...">`). При сборке MIME (`_embed_helpdesk_inline_images` в `email_outbox.py`) такие картинки **встраиваются в письмо** как `cid:`-attach (`multipart/related`, `Content-ID`): файлы читаются с диска (`HELPDESK_FILES_DIR / TKT-{n} / inline / {file}`), `src` в HTML переписывается на `cid:{token}`, тело оборачивается в `multipart/related` (или `multipart/mixed > related`, если есть обычные вложения). Заявитель видит картинки **прямо в почтовом клиенте** — без доступа к порталу, как в OTRS/Zammad. Поддерживаемые форматы: jpeg/png/gif/webp. Best-effort: если файл не найден/не читается (например, удалён к моменту отправки) — `src` остаётся относительным (в веб-ленте портала картинка всё равно видна), письмо не роняется. Колонки `is_inline`/`content_id` на `helpdesk_attachments` (миграция `077`) зарезервированы для будущей привязки картинок к сообщению (сейчас inline-media — отдельное хранилище без записи в `helpdesk_attachments`).

> **Картинки из истории переписки в исходящем email (`cid:`-attach).** Письмо-ответ агента несёт не только сам ответ, но и историю (`build_thread_history` — публичные сообщения тикета). Картинки в истории бывают двух видов: (a) rich-картинки агента — обрабатываются `_embed_helpdesk_inline_images`; (b) локализованные email-attachments от заявителя — `_embed_helpdesk_attachment_images`. Второй случай: входящее письмо заявителя с inline `cid:`-картинкой (Outlook) или внешней `http(s)://` (Gmail) при ingress локализуется через `email_images.py` → сохраняется в `helpdesk_attachments` → `src` переписывается на `/api/v1/helpdesk/attachments/{id}`. Этот URL в веб-ленте портала работает (session-cookie есть), но **в почтовом клиенте — нет**: `/attachments/{id}` требует аутентификации, почтовик cookie не передаёт → картинка не грузится. Фикс: при сборке MIME `_embed_helpdesk_attachment_images` одним DB-запросом подтягивает метаданные по всем найденным id, фильтрует по `image/*` (PDF/DOCX пропускаются — они в `<img>` всё равно не отрендерятся), читает файлы с диска и встраивает как `cid:`-attach (как rich-картинки). Best-effort: отсутствующий в БД id / нечитаемый файл / неподдерживаемый формат (svg) → `src` остаётся URL (веб-лента видит картинку, письмо не роняется).

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

| Событие | Получатели | In-app | Email | MAX-мессенджер |
|---|---|---|---|---|
| Новая заявка (email/web) | Агенты | ✅ (`notify_new` + `notify_inapp`) | ✅ агентам (`notify_new` + `notify_email`, через outbox `kind=generic`) | ✅ в общий чат (`notify_ticket_created_max`, через `messenger_outbox`; §9.1) |
| Новая заявка (email/web) | Инициатор | — | ✅ подтверждение «заявка зарегистрирована» (через outbox `kind=helpdesk`, при настроенном mailbox) | — |
| Взятие в работу / реассайн | Инициатор + новый агент (+ старый) | ✅ | ✅ инициатору (с ФИО ответственного, в теме `[#TKT-{number}]`) | — |
| Публичный ответ агента | Инициатор | ✅ | ✅ (это и есть «ответ», через outbox) | — |
| Сообщение от клиента | Текущий assignee (или все агенты) | ✅ | — | — |
| Статус → `closed` | Инициатор | ✅ | — | — |
| Internal note | Агенты | ✅ (не email) | — | — |
| Ежедневная сводка (cron) | Каждый агент (персонально) | — | ✅ через outbox `kind=generic` (не тред тикета) | — |

**Email заявителю «заявка зарегистрирована»** (`enqueue_created_email` в `outbound.py`, тела — `build_created_email_bodies` в `notifications.py`): при создании заявки (web-форма или IMAP-ingress) заявителю отправляется подтверждение приёма обращения — номер `[#TKT-{number}]`, «обращение принято, с вами свяжется специалист», инструкция для ответа. Через outbox `kind=helpdesk` (входит в email-тред тикета): токен `[#TKT-{number}]` в теме + `Message-ID` (корень треда, на него ссылаются будущие ответы) + `References`/`Reply-To` → ответ заявителя вернётся в тот же тикет. Для нового тикета `references` пуст (это первое письмо треда), `in_reply_to=None`. Ставится в **ту же транзакцию**, что и создание тикета+сообщения (outbox-инвариант AGENTS.md — письмо коммитится атомарно с заявкой). Тема `"[#TKT-{number}] Заявка зарегистрирована"`. Только при сконфигурированном mailbox (`support_domain`); без mailbox (web-only) — no-op (`_try_enqueue_created_email` — best-effort, лог warning). Срабатывает для всех новых тикетов (web через `create_ticket`, email через `ingress._ingest_message` при `new_status == "created"`), не для ответов на существующие.

**Email агентам о новой заявке** (`notify_ticket_created_email` в `notifications.py`, тела — `render_new_ticket_agent_email` в `email_template.py`): при создании заявки (web-форма или IMAP-ingress) всем активным агентам с `notify_new=True` **и** `User.notify_email=True` отправляется email-уведомление (аналог OTRS-письма «В службу технической поддержки поступила новая заявка», но в едином стиле портала). Через outbox `kind=generic` (как дайджест — **не** входит в email-тред тикета, не требует threading-заголовков и настроенного mailbox; SMTP-настройки общие → работает даже в web-only режиме helpdesk). Для каждого агента — отдельная outbox-запись (персональный `to_email`), единый `db.commit` в конце. Тема `"[#TKT-{number}] Новая заявка: {subject}"`. Тело (plain+html): «Поступила новая заявка» → блок контактов заявителя (ФИО, Почта, Телефон, Внутренний номер — из модели `User` через `resolve_requester_user`, тот же источник что и `requester_profile` в карточке тикета; `internal_phone` ← `users.phone`, `mobile_phone` ← `users.attributes["mobile"]`; пустые поля пропускаются; для гостевой заявки без аккаунта — имя/email из снимка тикета, без телефонов) → «Текст заявки:» (тело первого сообщения в блоке-цитате) → ссылка на агентскую карточку `{portal_base_url}/helpdesk/tickets/{id}`. Футер без призыва «ответьте на письмо» (агент работает через портал/инбокс; ответ на это письмо через общий SMTP-from без threading-заголовков создал бы путаницу в треде). Вызывается **после** commit бизнес-операции (best-effort: из роутера `create_ticket` через `_try_notify`, из `ingress._ingest_message` в собственном try/except — сбой не ломает создание заявки). Срабатывает только для **новых** тикетов (`new_status == "created"`), не для ответов на существующие.

**Email при назначении** (`_try_enqueue_assigned_email` в `tickets.py`, тела — `build_assigned_email_*` в `notifications.py`): при `assign`/`take`, только при сконфигурированном mailbox (`support_domain`). Письмо входит в email-тред тикета — тема `"[#TKT-{number}] Заявка принята в работу"`, заголовки `Message-ID`/`In-Reply-To`/`References`/`Reply-To` (формат как у публичных ответов, см. §8), чтобы ответ заявителя вернулся в тикет даже без живого `In-Reply-To` (Subject-token fallback). Тела (plain+html) с номером/темой заявки и ФИО ответственного, `html.escape` на пользовательские данные. Best-effort: сбой enqueue не ломает назначение (`_try_send`). Отправляется на `ticket.requester_email` (всегда заполнено, включая гостевые заявки).

**Смена ответственного агентом (UI reassign)** — `notify_ticket_assigned` + `enqueue_assigned_email` вызываются одинаково и для первичного назначения (`take`), и для реассайна (`POST /tickets/{id}/assign`): уведомления идут инициатору (email + in-app с ФИО нового ответственного) и новому агенту (in-app). Это сознательно: с точки зрения получателя нет разницы, пришла заявка впервые или передана от коллеги — контекст «заявка #N, ответственный X» одинаковый. Список таргетов для смены — `GET /tickets/assignable-agents` (агентский endpoint, PII-минимизированный: `user_id`/`full_name`/`email` без флагов `notify_new`); на фронте рендерится **простым списком в popover** (без поиска — агентов поддержки обычно ~5 человек). Таргет валидируется как активный helpdesk-агент (404 иначе, см. §5). Audit-лог отличает `take` (`took=true`) от реассайна (`reassigned=true` + `previous_assignee_user_id`).

### 9.1 MAX-messenger уведомления (`notify_ticket_created_max`)

Оповещения о новых заявках в один общий чат поддержки в мессенджере MAX (max.ru, корпоративный мессенджер от VK/Сбер). Дублирует email-уведомление агентам: если последний недоступен или агент не подписан на email, MAX-сообщение всё равно дойдёт в чат, где дежурят агенты. Используется Bot API `https://platform-api2.max.ru` (домен `platform-api.max.ru` deprecated с 19.07.2026).

**Активация:** админка → Helpdesk-вкладка → третья секция «Уведомления в MAX». Singleton `helpdesk_max_bot_settings` (миграция 081), `enabled=False` по умолчанию. Перед включением админ вводит токен бота (write-only, шифруется через Fernet из `SECRET_KEY`), ID чата поддержки (берётся у GetID-бота MAX или через `GET /chats` Bot API) и ставит `enabled=True`. Кнопка «Тест» дёргает `GET /me` для проверки бота (defence-in-depth: ошибки маскируются, чтобы не утекли в ответ/логи части токена).

**Когда срабатывает:** только для **новых** заявок (web через `create_ticket`, email через `ingress._ingest_message` при `new_status == "created"`). Не для ответов/смены статуса/назначения (вне скоупа). Best-effort: вызывается **после** commit бизнес-операции (из роутера `_try_notify`, из ingress в собственном try/except), сбой не ломает создание заявки. Если `enabled=False` или нет токена/chat_id → graceful no-op (`return 0`).

**Доставка** — transactional outbox (`messenger_outbox`, `provider='max'`), полный аналог `email_outbox` с retry/backoff/DLQ. Воркер `process_messenger_outbox` (cron каждые 15с, distributed lock `messenger:outbox:dispatch:lock`, batch 20). Retry-классификация (`classify_http_error` в `services/max_messenger/_client.py`): 429/5xx/timeout → transient (retry с экспоненциальным backoff), 4xx (auth/not-found/bad-request) → permanent (DLQ сразу, чинить в UI). Cleanup-cron `cleanup_messenger_outbox` (4:20 nightly) удаляет SENT старше 30 дней.

**Контент сообщения** (markdown):
```
🆕 Новая заявка #TKT-123

Тема: <subject>
Заявитель: <ФИО или email — из User через resolve_requester_user, fallback на снимок тикета>
Источник: веб / email

<превью тела первого сообщения, обрезанное до 500 символов>
```

Inline-кнопка «Открыть на портале» (attachment `inline_keyboard`): ссылка на `{portal_base_url}/helpdesk/tickets/{id}`. Если `portal_base_url` не задан — fallback на относительный путь (MAX покажет как текст, отправка не упадёт).

**Грабли:**
- **TLS: Russian Trusted Root CA** (Минцифры). Сертификат `*.max.ru` подписан через `Russian Trusted Sub CA` → `Russian Trusted Root CA`. Этот Root CA **не входит** ни в Mozilla CA Bundle Debian, ни в `certifi` (который httpx использует по умолчанию). Решено в две части: (1) сертификат Минцифры лежит в `backend/certs/russian_trusted_root_ca.crt` и устанавливается в образ через `update-ca-certificates` (см. Dockerfile stages `runtime-base` и `production`); (2) httpx-клиент в `services/max_messenger/_client.py` создаётся с `verify=ssl.create_default_context()` — это заставляет httpx использовать системный trust store, а не свой `certifi`. Без второй части системный CA-bundle игнорируется, даже если сертификат добавлен в образ. Промежуточные сертификаты (Sub CA) **не добавляем** — MAX отдаёт их в TLS-handshake.
- **Формат inline-keyboard** (согласно официальному `max-bot-api-client-ts/src/core/network/api/types/attachment.ts`): `attachments=[{"type": "inline_keyboard", "payload": {"buttons": Button[][]}}]`. Поле называется **`buttons`** (НЕ `rows`); кнопка-ссылка: `{"type": "link", "text": str, "url": str}` (`style`/`intent` бывает только у callback-кнопок).
- **`format: "plain"` MAX не поддерживает** — парсер падает с «Can't deserialize body». Только `markdown` (по умолчанию) или `html`. В коде это учтено: default `format_="markdown"` в `_client.py`, `format_map` в воркере фильтрует только `markdown`/`html`.
- **Бот должен быть участником чата** — MAX возвращает `404: chat not found` не только при неверном `chat_id`, но и если бот не добавлен в этот чат. Endpoint `/max-bot/test` даёт подсказку по HTTP-коду: 404 → membership, 401 → токен, 403 → права.
- Авторизация: заголовок `Authorization: <bot_token>` **без** префикса `Bearer` (как в большинстве Bot API).
- Outbox (`messenger_outbox`) — отдельная таблица, а не новый `kind` в `email_outbox`: последний жёстко завязан на SMTP/MIME (`to_email`, `subject`, `body_html`), универсализация сломала бы контракт.

### 9.2 Ежедневная сводка (`digest.py`)

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

Все cron гейтируются модулем (`modules.helpdesk.enabled`); при выключенном — выходят без работы. **Все cron берут distributed lock** (Redis `SET NX EX`, release через Lua с проверкой токена): защита от двойного запуска при нескольких воркерах.

| FQN | Расписание | run_at_startup | Lock (key / TTL) | Назначение |
|---|---|---|---|---|
| `poll_helpdesk_mailbox` | `second={0,30}` | нет | `helpdesk:imap:poll_lock` / 5 мин | IMAP-фетч (реальный интервал из БД, см. §8) |
| `archive_closed_tickets_task` | `hour=3, minute=20` | нет | `helpdesk:archive:lock` / 10 мин | `closed` старше `HELPDESK_ARCHIVE_AFTER_DAYS` (14) → архив (jsonb + CASCADE) |
| `create_next_helpdesk_archive_partition` | `month=*, day=1, hour=2` | **да** | `helpdesk:partition:lock` / 2 мин | Помесячные партиции архива на 3 мес вперёд |
| `cleanup_helpdesk_attachments_task` | `hour=4, minute=0` | нет | `helpdesk:cleanup:lock` / 10 мин | Удаление папок тикетов, архивированных > `HELPDESK_ARCHIVE_FILES_TTL_DAYS` (180) назад |
| `send_helpdesk_digest` | `minute=0` (ежечасно) | нет | `helpdesk:digest:lock` / 5 мин | Ежедневная email-сводка агентам (реальное время — из `helpdesk_digest_settings`, см. §9.1) |

> Раньше только `poll_helpdesk_mailbox` и `send_helpdesk_digest` брали локи; archive/partition/cleanup были без защиты → при двух воркерах `archive_closed_tickets` дублировал работу (`SELECT` без `FOR UPDATE SKIP LOCKED`, оба выбирали одни и те же `closed`-тикеты до commit). Теперь локи продублированы на всё archive-семейство через общий хелпер `_acquire_lock`/`_release_lock` в `worker/tasks/helpdesk.py`.

**Транзакции (cron):** воркеры открывают `async with AsyncSessionLocal() as db:` (`autocommit=False`) и **обязаны явно `db.commit()`** после изменений. `archive_closed_tickets` коммитит в сервисе при наличии изменений; `poll_mailbox` делает `db.rollback()` в except-цикла UID (защита от session-poisoning: один битый UID не роняет батч), а успешный ingest коммитит сообщение + `helpdesk_email_log` единым commit (идемпотентность).

---

## 11. Константы (`./backend/app/core/constants.py`)

| Константа | Значение | Описание |
|---|---|---|
| `HELPDESK_MAX_ATTACHMENT_MB` | 25 | Максимум одного вложения |
| `HELPDESK_MAX_TOTAL_INGRESS_MB` | 50 | Максимум суммы вложений в письме |
| `HELPDESK_ARCHIVE_AFTER_DAYS` | 14 | Через сколько после `closed` → архив |
| `HELPDESK_ARCHIVE_FILES_TTL_DAYS` | 180 | Через сколько физически удаляются файлы архива |
| `HELPDESK_REOPEN_WINDOW_DAYS` | 7 | Окно auto-reopen из `closed` |
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
| `/helpdesk/my` | `requiresAuth` | `HelpdeskMyTicketsPage` — список своих заявок (двухблочный вид) |
| `/helpdesk/my/archive` | `requiresAuth` | `HelpdeskMyArchivePage` — архив закрытых заявок пользователя |
| `/helpdesk/my/:id` | `requiresAuth` | `HelpdeskMyTicketDetailPage` — карточка своей заявки |
| `/helpdesk` | `requiresHelpdeskAgent` | `HelpdeskAgentInboxPage` — агентский инбокс |
| `/helpdesk/tickets/:id` | `requiresHelpdeskAgent` | `HelpdeskAgentTicketDetailPage` — карточка агента |

> **Порядок объявления важен:** `/helpdesk/my/archive` идёт **до** `/helpdesk/my/:id` — иначе Vue Router свяжет `archive` как path-param `:id`.

- `requiresHelpdeskAgent` (в `requireRole`): пропускает `auth.isHelpdeskAgent || auth.isAdmin`, иначе редирект на `/helpdesk/my`. `isHelpdeskAgent` — ref из `bootstrap.is_helpdesk_agent` (косметический; бэкенд перепроверяет по БД).
- Module-gate: все `/helpdesk*` зарегистрированы в `MODULE_ROUTES` → при выключенном `helpdesk.enabled` редирект на home.

### Меню (`./frontend/src/composables/useAppMenu.ts`)

- «Поддержка» (`/helpdesk/my`) — всем авторизованным, виден только при `modules.helpdesk.enabled`.
- «Инбокс поддержки» (`/helpdesk`) — агентам/админам (при включённом модуле).
- Подсветка активного пункта: `/helpdesk/tickets/*` и `/helpdesk` → `helpdesk-inbox`; `/helpdesk/my*` → `helpdesk-my`.
- **Серый счётчик-бейдж** рядом с лейблом (через `renderNavLabelWithCount`): у «Поддержки» — число своих открытых заявок (new/open/pending, `GET /tickets/my/counts`), у «Инбокса» — число назначенных агенту (`GET /tickets/counts`). Polling 60 c + автообновление после мутаций (create/reply/assign/take/status/reopen инвалидируют query-ключ). При `count=0` бейдж скрывается. Стиль — `.menu-count-badge` в `global.css`: серый pill 11px, в свёрнутом сайдбаре скрыт. Запросы кондиционально отключаются при выключенном модуле/не-агенте (`enabled`).

### Страницы инициатора (FE-2)

- **`HelpdeskMyTicketsPage`**: **двухблочный вид** (по образцу `HelpdeskAgentInboxPage`):
  - **Верхний блок «Ожидают принятия»** — свои тикеты без назначенного агента (`fetchMyTickets({unassigned: true})`). Помогает ответить на «когда мной займутся».
  - **Нижний блок «В работе у специалиста»** — тикеты с назначенным агентом (`fetchMyTickets({assigned: true})`).
  - Отдельная пагинация по блокам. Шапка страницы: кнопка «Архив» (на `/helpdesk/my/archive`) + «Создать заявку» (`TicketCreateModal`).
  - **Подсветка непрочитанного**: каждая строка с `unread=true` (есть публичные ответы агентов новее `last_seen_at`) подсвечивается красной точкой + фоном (единый язык с агентским инбоксом, `TicketListItem`).
- **`HelpdeskMyArchivePage`** (`/helpdesk/my/archive`, `requiresAuth`): архив закрытых тикетов пользователя — `fetchMyTickets({status: 'closed'})`. Без переключателя mine/all (все тикеты свои). Кнопка «К моим заявкам» — возврат на `/helpdesk/my`.
- **`HelpdeskMyTicketDetailPage`**: шапка (номер, тема, статус-бейдж), timeline сообщений (`TicketMessageList`), форма ответа (`TicketReplyForm`). Служебные поля (статус, ответственный, создана, обновление) и профиль заявителя — в правом сайдбаре (`TicketInfoCard` + `RequesterProfileCard`). Для закрытых — no-reply. При открытии — `markMyTicketRead` (снять подсветку ответов агентов в «Мои заявки», best-effort).

### Страницы агента (FE-3)

- **`HelpdeskAgentInboxPage`**: **двухблочный вид** (не плоский список):
  - **Верхний блок «Новые заявки»** — неназначенные + `status=new` (`?status=new&unassigned=true`). Пагинация по 20. Кнопка «Взять» (`takeTicket`) на каждой.
  - **Нижний блок «В работе»** — тикеты агента, активные статусы (`?active_only=true&assignee=<me>`). Переключатель **«Только мои» (по умолчанию) ↔ «Все назначенные»** (`assigned=true` — без неназначенных); выбор сохраняется в `localStorage` (`helpdesk.inbox.scope`). Пагинация.
  - **Поиск (`q`)** — при активном запросе два блока схлопываются в один плоский список (FTS по всем тикетам), заголовок «Результаты поиска».
  - **Архив** — отдельная страница `/helpdesk/archive` (роут `helpdesk-archive`, guard `requiresHelpdeskAgent`), кнопка «Архив» в шапке инбокса. Показывает только `status=closed` (один запрос), переключатель мои/все, поиск (FTS), пагинация.
  - Удалены: radio «Все»/«Новые», чекбокс «Только неназначенные» (стали самостоятельными блоками).
  - Список вынесен в компонент `TicketList.vue` (шапка таблицы + `TicketListItem`), переиспользуется всеми тремя блоками.
  - **Подсветка непрочитанных** (миграция 080): каждая строка инбокса приходит с бэка с полем `unread: bool` (один запрос `enrich_with_unread` на весь список — без N+1). `unread=true` для тикетов, у которых есть публичные входящие сообщения (ответы заявителя) новее, чем `last_seen_at` агента — то, что пришло за ночь и ещё не открывалось. Визуально: красная точка `--color-brand-red` перед `#номером` + полупрозрачный фон строки + жирный subject (единый язык с `NotificationsDropdown`). `unread=undefined` (для не-агентских списков, например `/tickets/my` у заявителя) — рендерится как прочитанное. Снятие подсветки — при открытии карточки: `HelpdeskAgentTicketDetailPage.load()` вызывает `markTicketRead(ticketId)` (best-effort, не блокирует UI).
- **`HelpdeskAgentTicketDetailPage`**: действия `take` / смена статуса (через select) / `reopen`; email-метаданные сообщений (agent-mode в `TicketMessageList`). При открытии — `markTicketRead` (снять подсветку в инбоксе, см. выше).

### Общие компоненты (`./frontend/src/components/helpdesk/`)

| Компонент | Назначение |
|---|---|
| `TicketStatusBadge.vue` | Цветной бейдж статуса (i18n-лейбл). |
| `TicketDetailHeader.vue` | Общий хедер карточки тикета для агентской и инициаторской страниц. Компактная строка: `#номер` — тема — actions-slot (кнопки/переключатель статуса) справа (`margin-left:auto`). Статус-бейдж и source в шапке отсутствуют — они в `TicketInfoCard` (правый сайдбар). |
| `TicketInfoCard.vue` | Служебные поля тикета (Статус, Способ получения, Ответственный, Создана, Обновление) в правом сайдбаре (`ticket-layout__aside`), над `RequesterProfileCard`. Рендерится всегда; статус — через `TicketStatusBadge`; source — локализованный лейбл (`helpdesk.sources.{web,email}`); при отсутствии assignee — плейсхолдер «Не назначен». **Prop `editable`** (по умолчанию `false`): при `true` (агентская карточка) поле «Ответственный» становится кликабельным триггером → `n-popover` с **простым списком** активных helpdesk-агентов (без поиска/`n-select` — агентов поддержки обычно ~5 человек, поиск избыточен). Список — `useAssignableAgentsQuery`, подгружается лениво при открытии popover'а. Текущий агент помечается суффиксом «(вы)»; текущий assignee помечен галочкой `✓` и отключён (`disabled` — нельзя сменить на того, кто уже назначен). Клик по строке сразу применяет смену (`useAssignTicketMutation`) — без отдельной кнопки «Применить». Успех → toast «Ответственный изменён» + инвалидация `agentTicket(id)`/`inbox`/`agentTicketCounts`. При 404 «Agent not found» (таргет устарел — уволен/убран из агентов) → `message.error` + рефетч списка. На странице заявителя (`HelpdeskMyTicketDetailPage`) `editable=false` — поле read-only. |
| `RequesterProfileCard.vue` | Краткая «визитка» заявителя (email, отдел, должность, город, мобильный/внутренний телефоны) из `ticket.requester_profile`; рендерится в правом сайдбаре карточки тикета (`ticket-layout__aside`, под `TicketInfoCard`); скрывается, если профиль не построен (гость без аккаунта в портале). |
| `TicketMessageList.vue` | Переписка в виде **чата с аватарами** (мессенджер-вид): каждое сообщение — `flex-row` с круглым аватаром (`n-avatar`, инициалы из ФИО/email local-part, детерминированный цвет из email) и пузырём (`max-width:75%`). `inbound` (от заявителя) — слева, `outbound` (от агента) — справа (`flex-direction:row-reverse`). Заголовок пузыря: имя автора + source-тег (`email`/`web`) + (в agent-mode) email автора + дата. Тело — sanitized HTML (`DOMPurify`) или `pre-wrap` plain. Вложения — чипы-ссылки. Единый стиль для web и email-сообщений (после отсечения цитат email-ответы чистые). |
| `TicketReplyForm.vue` | **Rich-редактор** (TipTap, общий `RichEditor.vue` из новостей/КБ) + вложения + блок «Ответить всем» (Cc, только agent-mode). Контент хранится как markdown (v-model), на submit рендерится в HTML (`markdown-it`, `mdUnsafe`) и эмитится как `body_html` (plain `body_text` деривит бэк). Inline-картинки грузятся через `:upload-endpoint="/api/v1/helpdesk/tickets/{ticketId}/inline-media"` (требует пропс `ticketId`). |
| `TicketCreateModal.vue` | Модалка создания заявки с вложениями. |

### Admin UI (FE-4)

- **ModulesTab**: карточка «Техподдержка» с переключателем (`useModulesState.onToggleHelpdesk` → `PUT /admin/modules/helpdesk`).
- **HelpdeskTab** (`/admin?tab=helpdesk`, группа `system`):
  - `HelpdeskAgentsManager` — список агентов, remote-search по сотрудникам (`fetchUsers`), переключатель `notify_new`, удаление.
  - `HelpdeskMailboxSettings` — singleton IMAP-форма (write-only пароль с индикатором «задан», кнопка «Проверить соединение»).

### Загрузка с вложениями и rich-контентом

Создание заявки и ответы — `multipart/form-data` через `apiUpload` (FormData). Поля формы: `subject`/`description`/`description_html` (создание) или `body_text`/`body_html` (ответ агента) + `files[]`. **Создание заявки и ответы** идут через rich-редактор (TipTap): фронт рендерит markdown в HTML (`mdUnsafe`, как news/kb) и шлёт `description_html`/`body_html`, `description`/`body_text` опционален (бэк деривит через `normalize_message_bodies`, если пуст — `html_to_plain(sanitize_html(html))`). Бэк повторно sanitize'ит HTML (nh3) на запись — двойная защита (заявитель неконтролируемая сторона). **Inline-картинки в тексте** поддерживаются и при создании заявки, и в ответах:

- **Ответы** (`ticket_id` уже есть): `POST /tickets/{id}/inline-media` → файл в `TKT-{number}/inline/`, URL `/tickets/{id}/inline-media/{name}` в `body_html`.
- **Создание заявки** (нет `ticket_id` до сохранения): `POST /draft-attachments` → draft-файл в `/data/helpdesk/drafts/usr-{user_id}/`, draft-URL в `description_html`. При `create_ticket` бэкенд **backfill'ит**: переносит файл в `TKT-{number}/inline/`, переписывает `src` на `/tickets/{id}/inline-media/{name}`, создаёт inline-`HelpdeskAttachment`, удаляет draft-строку (атомарно в транзакции создания). Orphan-черновики (юзер закрыл форму) чистит cron `cleanup_expired_drafts` (TTL 24ч, лимит 20/юзер).

Обычные (не-inline) вложения прикрепляются отдельным блоком `n-upload` (`files[]` в форме). Скачивание вложения — прямой anchor `:href="/api/v1/helpdesk/attachments/{id}"` с `target="_blank"` (как feedback), бэкенд отдаёт `StreamingResponse`.

### i18n

Топ-уровневый объект `helpdesk.*` (статусы, действия, лейблы, ~40 ключей) + `nav.helpdesk`/`nav.helpdeskInbox`. **Готча:** `@` в i18n-строках (например `support@company.local`) ломает парсер vue-i18n (интерпретируется как linked-message) — экранировать через литерал `{'@'}`.

---

## 15. Развёртывание / включение

1. Миграция `075` (применяется автоматически при старте backend через `migrate.sh`).
2. Миграция `076` (расписание сводки, применяется автоматически).
3. Миграция `077` (колонки `is_inline`/`content_id` на `helpdesk_attachments` — schema-drift фикс; применяется автоматически).
4. Миграция `078` (полнотекстовый поиск: `search_tsvector`/`body_tsvector` tsvector + GIN — применяется автоматически; zero-downtime, generated STORED колонки заполняются атомарно).
5. Миграция `079` (упразднён статус `resolved`: data-mig resolved→closed + CHECK без `resolved`; применяется автоматически).
6. Миграция `080` (marker-таблица `helpdesk_ticket_reads` для подсветки непрочитанных заявок в инбоксе агента; zero-downtime — новая таблица, без блокировок; backfill не нужен — отсутствие строки = «никогда не видел» = логичный дефолт).
7. Миграция `083` (email Cc — «ответить всем»: колонка `cc` JSONB на `helpdesk_messages`; zero-downtime — nullable-колонка без DEFAULT, обратная совместимость — старые сообщения читаются как `None`/`[]`; применяется автоматически).
8. Зависимости `aioimaplib` + `cryptography` — в `pyproject.toml` (требуется пересборка `backend` + `worker`).
8. Пересобрать `frontend` (новые страницы/роуты/меню/компоненты): `docker compose build frontend`.
9. **Volume nginx → helpdesk** (для inline-картинок rich-редактора): nginx раздаёт картинки через `X-Accel-Redirect` и должен иметь доступ к `/data/helpdesk/` (`:ro`, как kb/feedback/photos). В `docker-compose.yml` секция `nginx.volumes` должна содержать `- ./upload_data/helpdesk:/data/helpdesk:ro`. Раньше это было не нужно (вложения раздавались `StreamingResponse` из backend), с inline-media — обязательно. После правки: `docker compose up -d nginx`.
10. Включить модуль: **Admin → Модули → «Техподдержка» → On** (или `PUT /api/v1/admin/modules/helpdesk` `{"enabled": true}`, или правка `/data/settings/modules.json`).
11. Для email-flow: **Admin → Система → «Техподдержка» → mailbox-форма** с IMAP-настройками и паролем (проверить кнопкой «Проверить соединение»).
12. Назначить агентов: **Admin → Система → «Техподдержка» → Агенты** (поиск по сотрудникам) или `POST /api/v1/helpdesk/agents`.
13. Локальная папка `/data/helpdesk/` должна быть доступна на запись (volume) для backend/worker и на чтение для nginx (см. п. 9).
14. (Опц.) Сводка по умолчанию включена (будни 08:00 UTC). Настроить время/выключить — `PUT /api/v1/helpdesk/settings/digest` (Admin UI для расписания сводки пока отсутствует — настраивается через API).

> Модуль работоспособен и без IMAP (web-only helpdesk): `helpdesk.enabled=true` без mailbox-настройки — заявки создаются и обрабатываются через портал, исходящие публичные ответы не отправляются на email (создаётся только сообщение).
