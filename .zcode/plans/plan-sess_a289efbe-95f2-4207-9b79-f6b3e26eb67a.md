# План: MAX-мессенджер как канал уведомлений helpdesk

## Контекст

Пользователь просит настроить уведомления о **новых заявках в helpdesk** в мессенджере **MAX (max.ru)** — российский корпоративный мессенджер от VK/Сбер. MAX Bot API: `https://platform-api2.max.ru` (домен `platform-api.max.ru` deprecated с 19.07.2026 = сегодня), auth через заголовок `Authorization: <bot_token>` (без `Bearer`), `POST /messages?chat_id=<int64>` с телом `{text, format, attachments, notify}`, есть `/me` для проверки бота и inline-кнопки через `attachments` типа `inline_keyboard`.

**Решения (подтверждены пользователем):**
1. **Доставка** — outbox-pattern с retry/backoff/DLQ (зеркало `email_outbox`). Надёжно, retry при временной недоступности MAX API.
2. **chat_id** — ручной ввод администратором.
3. **Контент** — №+тема+заявитель+превью описания+inline-кнопка «Открыть на портале».
4. **Активация** — в админке, Helpdesk-вкладка, singleton-настройки `helpdesk_max_bot_settings` с флагом `enabled`.

Образцы в репозитории: `notify_ticket_created_email` (`services/helpdesk/notifications.py:342`), `email_outbox` (`services/email_outbox.py:38` + `worker/tasks/email_outbox.py:44`), `HelpdeskMailboxSettings` (`models/helpdesk.py:326` + `api/helpdesk/settings.py:62` + admin `HelpdeskMailboxSettings.vue`), `HelpdeskDigestSettings` (`models/helpdesk.py:394`, миграция `076` как образец singleton с seed), httpx singleton из `services/keycloak/http_client.py`.

---

## 1. Миграция 081: две новые таблицы

`backend/migrations/versions/081_add_messenger_outbox_and_max_bot_settings.py` (по образцу 076, ручной DDL через `op.execute` + `IF NOT EXISTS` для идемпотентности).

### `messenger_outbox` (зеркало `email_outbox`)
Поля: `id UUID PK`, `provider VARCHAR(32) NOT NULL` ('max'), `chat_id VARCHAR(64) NOT NULL`, `text TEXT NOT NULL`, `payload JSONB NOT NULL DEFAULT '{}'` (attachments, metadata), `status VARCHAR(16) DEFAULT 'PENDING'`, `attempts INT DEFAULT 0`, `max_attempts INT DEFAULT 6`, `next_attempt_at TIMESTAMPTZ DEFAULT NOW()`, `last_error_type VARCHAR(128)`, `last_error_class VARCHAR(16)`, `last_error TEXT`, `sent_at TIMESTAMPTZ`, `related_resource_type VARCHAR(64)`, `related_resource_id UUID`, `created_by_user_id UUID`, `created_at/updated_at TIMESTAMPTZ`.
Индексы: `ix_messenger_outbox_pending ON (next_attempt_at) WHERE status='PENDING'`, `ix_messenger_outbox_stale ON (updated_at) WHERE status='SENDING'`.

### `helpdesk_max_bot_settings` (singleton, по образцу `helpdesk_digest_settings` — все колонки nullable/DEFAULT, строка засевается миграцией, `enabled=False`)
Поля: `id SMALLINT PK DEFAULT 1`, `enabled BOOLEAN DEFAULT FALSE`, `bot_token_enc TEXT` (nullable, шифр через secret_crypto), `chat_id VARCHAR(64)` (nullable), `created_at/updated_at`, `updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL`. `CONSTRAINT ck_helpdesk_max_bot_singleton CHECK (id = 1)`. `INSERT INTO ... (id) VALUES (1) ON CONFLICT DO NOTHING`.

---

## 2. Backend: model + schema

### `models/helpdesk.py` — две новые модели
- `HelpdeskMaxBotSettings(Base)`: singleton `id=1`, поля зеркально миграции. `bot_token_enc: Mapped[str | None]` (nullable, write-only). Relationship `updated_by: User | None`.
- `MessengerOutbox(Base)`: ORM-модель для метаданных; CRUD идёт через raw SQL (как `email_outbox`), модель нужна только для type-согласованности.

### `schemas/helpdesk.py` — 3 новые схемы (по образцу `HelpdeskMailboxSettingsIn/Out`)
- `HelpdeskMaxBotSettingsIn`: `enabled: bool`, `bot_token: str | None = None` (write-only), `chat_id: str | None`. Валидатор: если `enabled=True`, оба поля обязательны.
- `HelpdeskMaxBotSettingsOut`: `configured: bool`, `enabled: bool`, `bot_token_set: bool`, `chat_id: str | None`, `updated_at`.
- `HelpdeskMaxBotTestResult`: `ok: bool`, `detail: str | None`, `error: str | None`.

---

## 3. Backend service: `app/services/max_messenger/service.py`

По образцу `services/keycloak/http_client.py` (lifespan singleton) + `services/nextcloud/webdav/_client.py` (именованные таймауты).

- Константы: `_MAX_BASE_URL = "https://platform-api2.max.ru"`, `_TIMEOUT = httpx.Timeout(10.0, connect=5.0)`.
- `init_max_http_client()` / `close_max_http_client()` — модульные функции для FastAPI lifespan (как `init_kc_http_client`).
- `send_message(*, bot_token, chat_id, text, attachments=None, format_="markdown")`: POST `/messages` с `params={"chat_id": chat_id}`, JSON-body, заголовок `Authorization: <token>`. `r.raise_for_status()`. MAX API отдаёт JSON-ошибки с `code`/`message`.
- `get_me(bot_token) -> dict`: `GET /me`, для `POST /test`.
- `_classify_http_error(exc) -> ErrorClass`: transient (Timeout/Network/429/5xx), permanent (4xx кроме 429), unknown (прочее). Используется в воркере.

---

## 4. Backend service: `app/services/messenger_outbox.py`

Зеркало `services/email_outbox.py` с адаптацией под messenger-формат (без `subject`/`body_html`, вместо них `text` + `payload` для attachments).

- Константы: `PROVIDER_MAX = "max"`, `STATUS_*` (те же что у email_outbox).
- `enqueue_messenger_message(session, *, provider, chat_id, text, payload=None, related_resource_type=None, related_resource_id=None, created_by_user_id=None, max_attempts=OUTBOX_MAX_ATTEMPTS) -> uuid.UUID` — INSERT RETURNING id.
- `claim_pending`, `mark_sent`, `mark_failed`, `requeue_stale_sending`, `reschedule_for_retry`, `cancel`, `cleanup_old_sent` — точные копии email-аналогов. В `mark_failed` используется общий `compute_retry_defer` из `email_utils.py` (DRY).

---

## 5. Backend worker: `app/worker/tasks/messenger_outbox.py`

Зеркало `worker/tasks/email_outbox.py:44` (`process_email_outbox`):

- `process_messenger_outbox(ctx) -> int`: watchdog → claim → для каждой записи: загрузить `HelpdeskMaxBotSettings`, расшифровать токен, вызвать `send_message`. Ошибка → `mark_failed` (через `_classify_http_error`), успех → `mark_sent`.
- `cleanup_messenger_outbox(ctx)` — удаление SENT старше 30 дней.
- Distributed lock по образцу `tasks/helpdesk.py:_acquire_lock` (key `helpdesk:cron-lock:messenger-outbox`).

### Регистрация в `worker/main.py`
- Импорты `process_messenger_outbox`, `cleanup_messenger_outbox`.
- `functions += [process_messenger_outbox, cleanup_messenger_outbox]`.
- Cron: `cron("...process_messenger_outbox", second={0,15,30,45}, run_at_startup=True)` + `cron("...cleanup_messenger_outbox", hour=4, minute=20, second=0)`.

---

## 6. Backend: `notify_ticket_created_max` в `services/helpdesk/notifications.py`

Зеркало `notify_ticket_created_email:342`, но цель — **один общий чат**:
- Загрузить `HelpdeskMaxBotSettings` singleton. Если `enabled=False` или `bot_token_enc IS NULL` или `chat_id` пустой → `return 0`.
- Резолвить `resolve_requester_user(db, ticket=ticket)` для ФИО/почты.
- Собрать текст: `🆕 Новая заявка #TKT-{number}\n\nТема: {subject}\nЗаявитель: {requester}\nИсточник: {source_ru}\n\n{preview}` (preview = первые 500 символов `first_message.body_text`).
- Собрать inline-кнопку через attachments: `[{"type": "inline_keyboard", "payload": {"rows": [[{"text": "Открыть на портале", "url": f"{base}/helpdesk/tickets/{ticket.id}", "style": "primary"}]]}}]`. URL из `SystemSettings.portal_base_url` (fallback — относительный).
- `await enqueue_messenger_message(db, provider=PROVIDER_MAX, chat_id=settings.chat_id, text=text, payload={"attachments": attachments}, related_resource_type="helpdesk_ticket", related_resource_id=ticket.id)` → `await db.commit()` → `return 1`.

---

## 7. Backend API: `app/api/helpdesk/settings.py`

Добавить секцию (по образцу `mailbox` 57–147):

- `GET /helpdesk/settings/max-bot` → `HelpdeskMaxBotSettingsOut`. Singleton создаётся через fallback `_load_singleton` (как `_load_digest_singleton`).
- `PUT /helpdesk/settings/max-bot` → обновляет singleton. `bot_token` write-only. Если `enabled=True` и нет токена/chat_id → 400. После commit → `push_audit_event(redis, event_type="helpdesk.max_bot_settings_changed", ...)`.
- `POST /helpdesk/settings/max-bot/test` → загружает singleton, расшифровывает токен, дёргает `max_messenger.get_me(token)`. Defense-in-depth маскировка `str(exc)` (как `test_mailbox_connection:139`). Успех → `{"ok": True, "detail": f"Bot: {me.get('name', '?')}"}`.

---

## 8. Backend: точки вызова (зеркало email)

- `api/helpdesk/tickets.py:128-134` — рядом с `_try_notify(notify_ticket_created_email)` добавить `_try_notify(notify_ticket_created_max(db, ticket=ticket, first_message=first_message), context="ticket_created_max")`.
- `services/helpdesk/ingress.py:627-635` — рядом с блоком `notify_ticket_created_email` добавить аналогичный try/except `notify_ticket_created_max`.

---

## 9. Frontend: api/queries + admin-компонент

### `frontend/src/api/helpdesk.ts` (по образцу mailbox 286–335)
- Типы: `HelpdeskMaxBotSettingsOut`, `HelpdeskMaxBotSettingsIn`, `HelpdeskMaxBotTestResult`.
- Функции: `fetchHelpdeskMaxBot()`, `putHelpdeskMaxBot(dto)`, `testHelpdeskMaxBot()`.

### `frontend/src/queries/helpdesk.ts` (по образцу `useHelpdeskMailboxQuery:39`)
- `useHelpdeskMaxBotQuery()`, `usePutHelpdeskMaxBotMutation()`. Ключ `['helpdesk', 'max-bot']` (добавить в `queries/keys.ts`).

### `frontend/src/components/admin/HelpdeskMaxBotSettings.vue` (новый, по образцу `HelpdeskMailboxSettings.vue`)
- Поля: `enabled` (n-switch), `bot_token` (n-input type=password, write-only с плейсхолдером «оставить прежний»), `chat_id` (n-input).
- Кнопки «Сохранить» + «Тест» (как mailbox). Блок `testResult` с `kc-test-result` стилем.

### `frontend/src/pages/admin/tabs/HelpdeskTab.vue` — третья секция
```vue
<div class="helpdesk-section">
  <div class="branding-section__title">{{ t('admin.helpdesk.max.title') }}</div>
  <div class="branding-section__hint">{{ t('admin.helpdesk.max.hint') }}</div>
  <HelpdeskMaxBotSettings />
</div>
```

---

## 10. i18n (`ru.json` + `en.json`)

Новые ключи в группе `admin.helpdesk.max.*`: `title`, `hint`, `botToken`, `botTokenPlaceholder`, `botTokenKeep`, `chatId`, `chatIdPlaceholder`, `chatIdHint` (где брать ID), `enabled`, `test`, `testOk`, `testFail`, `tokenRequired`, `notConfigured`. Мастер — `ru.json`, синхронно `en.json`.

---

## 11. Тесты

### Backend unit (`tests/unit/`)
- **`test_messenger_outbox_service.py`** (новый, по образцу `test_email_outbox_service.py`): enqueue/claim/mark_sent/mark_failed (transient/permanent/exhausted)/requeue_stale_sending/reschedule_for_retry/cancel/cleanup_old_sent.
- **`test_worker_messenger_outbox.py`** (новый): `process_messenger_outbox` с замоканным `send_message` — happy path, transient→retry, permanent→DLQ, settings disabled→mark_failed.
- **`test_max_messenger_service.py`** (новый): httpx-мок (respx или AsyncMock transport): `send_message` success/4xx/5xx; `_classify_http_error`.
- **`test_helpdesk_notifications.py`** — расширить классом `TestNotifyTicketCreatedMax` (по образцу `TestNotifyTicketCreatedEmail:366`): disabled→0, enabled→1 enqueue с `provider='max'`, текст содержит #TKT и тему, payload содержит inline-keyboard URL, related_resource_id.
- **`test_helpdesk_settings_max_bot.py`** (новый): GET/PUT/write-only/`enabled=True` без токена→400/audit-event/`POST /test` маскировка.

### Frontend unit
- **`HelpdeskMaxBotSettings.spec.ts`** (по образцу mailbox): рендер/dirty/save/test/write-only плейсхолдер.

---

## 12. Документация

### `docs/helpdesk.md` — расширение
- §8 «Уведомления»: «MAX-мессенджер как канал оповещений». Какие заявки уходят, куда, как включить, что в теле, что при сбое (outbox retry→DLQ).
- §1.3 (Data model): таблицы `messenger_outbox`, `helpdesk_max_bot_settings`.
- Ссылки на `https://dev.max.ru/docs-api`.

### `docs/wip/helpdesk-max-messenger.md` — план фичи (handoff, по структуре AGENTS.md)

---

## DoD

- [ ] Миграция 081 (messenger_outbox + helpdesk_max_bot_settings, singleton seed)
- [ ] models/helpdesk.py: `HelpdeskMaxBotSettings`, `MessengerOutbox`
- [ ] schemas/helpdesk.py: 3 новые схемы
- [ ] services/max_messenger/service.py
- [ ] services/messenger_outbox.py
- [ ] worker/tasks/messenger_outbox.py + cron-locks
- [ ] worker/main.py: cron-регистрация
- [ ] services/helpdesk/notifications.py: `notify_ticket_created_max`
- [ ] api/helpdesk/settings.py: GET/PUT /max-bot + POST /max-bot/test
- [ ] api/helpdesk/tickets.py + services/helpdesk/ingress.py: точки вызова
- [ ] frontend: api/queries/keys + HelpdeskMaxBotSettings.vue + HelpdeskTab.vue
- [ ] i18n ru/en
- [ ] Backend unit-тесты
- [ ] Frontend unit-тесты
- [ ] docs/helpdesk.md + docs/wip/helpdesk-max-messenger.md
- [ ] `docker compose build backend worker` → ruff + mypy + pytest green
- [ ] npm lint + typecheck + test:unit + i18n:check green
- [ ] Ручная проверка с реальным ботом MAX

---

## Что НЕ делаем (осознанно)

- ❌ **MAX-уведомления для других событий** (ответы/статус/назначение) — вне скоупа, заказчик просил только новые заявки. Архитектура (provider + payload) позволяет расширить позже.
- ❌ **Входящие сообщения из MAX** (reply в чате → ответ в тикете) — двусторонняя интеграция, отдельная фича. Сейчас только outbound.
- ❌ **Несколько провайдеров** (Telegram, Slack) — поле `provider` зарезервировано, реализован только `'max'`.
- ❌ **SystemSettings для бота** — нет `POST /test`, что критично для первичной настройки.
- ❌ **Дублирование retry/backoff-логики** — общий `compute_retry_defer` в `email_utils.py`, импортируется в `messenger_outbox`.
- ❌ **`get_me`-кеш** — `/test` вызывается редко, кешировать нечего.

---

## Риски / замечания

- **Дедлайн миграции домена 19.07.2026** — сегодня. Используем сразу `platform-api2.max.ru`, без легаси.
- **Inline-keyboard формат** — MAX API: `attachments=[{"type": "inline_keyboard", "payload": {"rows": [[{text, url, style}]]}}]`. Если формат не совпадёт — fallback: только текст + URL в теле сообщения. Покрыть тестом на сборку attachments.
- **`portal_base_url` для inline-кнопки** — есть в `SystemSettings`. Если пусто — fallback на относительный путь.
- **Secret-key детерминизм** — `bot_token_enc` через `secret_crypto` (тот же Fernet из `SECRET_KEY`). Уже используется для IMAP-пароля, проверенный паттерн.
- **Rate limit MAX API** — наш объём (новые заявки) единицы в час, лимиты не проблема. Outbox retry/backoff защитит от transient 429.
- **Distributed lock для cron** — `process_messenger_outbox` каждые 15с; lock предотвратит двойную обработку при нескольких воркерах.
- **Не падать при отсутствии настроек** — `notify_ticket_created_max` graceful no-op, не ломает существующие тесты helpdesk.