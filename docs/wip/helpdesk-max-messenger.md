# Фича: Уведомления о новых заявках в мессенджере MAX

## Цель

Отправлять уведомления о новых заявках в helpdesk в один общий чат поддержки
в корпоративном мессенджере MAX (max.ru). Дублирует email-уведомления агентам:
если последний канал недоступен или агент не подписан, MAX-уведомление всё
равно дойдёт в чат, где дежурят агенты.

## Архитектура (одобренный план)

- **Доставка:** transactional outbox (`messenger_outbox`, зеркало `email_outbox`)
  с retry/backoff/DLQ и distributed lock — те же гарантии доставки что у email.
- **Канал:** один общий чат (chat_id вводит админ), не per-agent.
- **Контент:** №+тема+заявитель+источник+превью тела (500 символов) +
  inline-кнопка «Открыть на портале» (URL из `SystemSettings.portal_base_url`).
- **Активация:** singleton `helpdesk_max_bot_settings` (миграция 081),
  `enabled=False` по умолчанию. Включается в админке → Helpdesk-вкладка →
  третья секция. Токен write-only (Fernet через `SECRET_KEY`, как IMAP-пароль).
- **Bot API:** `https://platform-api2.max.ru` (старый `platform-api.max.ru`
  deprecated с 19.07.2026 = сегодня, не используем). Auth — голый токен в
  `Authorization` (без `Bearer`).

## Решения по ходу

- **2026-07-19:** MAX-канал — отдельная таблица `messenger_outbox`, а не новый
  `kind` в `email_outbox`. Причина: `email_outbox` жёстко завязан на SMTP/MIME
  (`to_email`, `subject`, `body_html`); универсализация сломала бы контракт.
  Поле `provider` в `messenger_outbox` зарезервировано для будущих Telegram/Slack.
- **2026-07-19:** Singleton-стиль `HelpdeskMaxBotSettings` (как `HelpdeskDigestSettings`),
  а не `HelpdeskMailboxSettings` (где есть состояние `configured` и обязательный
  пароль). Причина: MAX-канал опциональный (`enabled=False` по умолчанию),
  не должно быть состояния «сконфигурирован или нет» — только `enabled`.
- **2026-07-19:** Retry-классификация HTTP-ошибок (`classify_http_error`):
  429/5xx/timeout → transient (retry), 4xx → permanent (DLQ сразу). Это
  отличается от email (где `permanent` = 5xx SMTP). Обоснование: MAX 4xx
  это почти всегда неверный токен или chat_id (можно починить только в UI),
  а 5xx — серверная проблема MAX (попробуем позже).
- **2026-07-19:** `process_messenger_outbox` использует distributed lock, хотя
  `FOR UPDATE SKIP LOCKED` в `claim_pending` уже атомарна. Причина: rate-limit
  MAX API — параллельные вызовы от двух воркеров могут наломать дров с 429.
- **2026-07-19:** Если MAX-настройки изменились (`enabled=False` между созданием
  заявки и dispatch) — все записи возвращаются в очередь (transient). Не DLQ:
  фичу могут включить, и backlog отправится. Это отличается от «токена нет при
  enabled=True» (permanent — конфиг сломан).

## Чеклист (DoD)

- [x] Миграция 081 (messenger_outbox + helpdesk_max_bot_settings, singleton seed)
- [x] models/helpdesk.py: `HelpdeskMaxBotSettings`, `MessengerOutbox`
- [x] schemas/helpdesk.py: 3 новые схемы (In/Out/TestResult)
- [x] services/max_messenger/service.py: httpx singleton + send_message + get_me + classify_http_error
- [x] services/messenger_outbox.py: enqueue/claim/mark_*/cleanup
- [x] worker/tasks/messenger_outbox.py + cron-lock + регистрация в main.py
- [x] services/helpdesk/notifications.py: `notify_ticket_created_max`
- [x] api/helpdesk/settings.py: GET/PUT /max-bot + POST /max-bot/test
- [x] api/helpdesk/tickets.py + services/helpdesk/ingress.py: точки вызова
- [x] frontend: api/queries/keys + HelpdeskMaxBotSettings.vue + HelpdeskTab.vue
- [x] i18n ru/en (admin.helpdesk.max.*)
- [x] Backend unit-тесты (3563 passed, +93 новых)
- [x] Frontend queries-helpdesk (20 tests passed) + typecheck + lint + i18n green
- [x] docs/helpdesk.md (§8 расширение, §1.3 модели) + docs/wip/
- [ ] `docker compose build backend worker` + ручная проверка с реальным ботом MAX

## Грабли / контекст

- **TLS: Russian Trusted Root CA не в certifi** (19.07.2026, найдено в проде).
  MAX-сертификат `*.max.ru` подписан `Russian Trusted Sub CA` → `Russian
  Trusted Root CA` (Минцифры). Этот Root CA **не входит** ни в Mozilla CA
  Bundle (Debian `ca-certificates`), ни в `certifi` (который httpx использует
  по умолчанию). Симптом: `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify
  failed: unable to get local issuer certificate` при вызове MAX API.

  **Решение (две части, обе обязательны):**
  1. `backend/certs/russian_trusted_root_ca.crt` — сертификат Минцифры в репо.
     Устанавливается в Docker-образ через `update-ca-certificates` (см. Dockerfile
     stages `runtime-base` и `production`). ВАЖНО: расширение **должно быть
     `.crt`** — `update-ca-certificates` игнорирует `.pem`/`.cer`/README.
  2. В `services/max_messenger/_client.py` httpx-клиент создаётся с
     `verify=ssl.create_default_context()` — это заставляет httpx использовать
     системный trust store (`/etc/ssl/certs/ca-certificates.crt`), а не свой
     `certifi.where()`. Без этого системный CA-bundle игнорируется, даже если
     сертификат добавлен в образ.

  Промежуточные сертификаты (Sub CA) **не добавляем** — MAX отдаёт их в
  TLS-handshake, OpenSSL/httpx сами собирают chain `leaf → sub → root`.

  Это общий фикс: теперь любой российский TLS-endpoint (Госуслуги, Сбер и т.д.)
  с сертификатом Минцифры будет работать из контейнера автоматически.

- **Mypy vs SQLAlchemy `mapped_column`:** в `MessengerOutbox` колонка `text`
  shadow-ит импорт `text` из SQLAlchemy → mypy выдаёт `"str" not callable`
  на всех последующих `mapped_column`. Решено алиасом `from sqlalchemy import
  text as sql_text` и заменой всех 50 `text(...)` → `sql_text(...)`. Баг mypy
  + SQLAlchemy 2.x inference при разнесении на строки.
- **Pytest собирает endpoint-функцию `test_max_bot_connection`** как тест —
  pytest видит префикс `test_` и пытается вызвать endpoint как test-fixture.
  Решено алиасом при импорте `as max_bot_test_endpoint` (тот же паттерн что в
  `test_helpdesk_settings_test_endpoint.py:23`).
- **MAX-домен** — `platform-api2.max.ru` обязательно. Старый `platform-api.max.ru`
  был deprecated 19.07.2026 (= сегодня), миграция без предупреждения.
- **Inline-keyboard формат** — MAX API (уточнено по официальному TypeScript-
  клиенту `max-bot-api-client-ts/src/core/network/api/types/attachment.ts`):

  ```
  InlineKeyboardAttachment = {
      "type": "inline_keyboard",
      "payload": {"buttons": Button[][]}    # НЕ "rows"!
  }
  LinkButton = {"type": "link", "text": str, "url": str}    # НЕ "style"
  ```

  Изначально ошибочно использовал `rows` — MAX упал с `Field 'buttons' cannot
  be null` (запись ушла в DLQ). Правильное имя поля — `buttons`, кнопка-ссылка
  имеет `type: "link"` (а `style`/`intent` бывает только у callback-кнопок).
  Не совпадает с Telegram (`reply_markup.inline_keyboard`).

- **`format: "plain"` MAX не поддерживает** — парсер падает с «Can't deserialize
  body». Только `markdown` (по умолчанию) или `html`. В коде это учтено: default
  `format_="markdown"` в `_client.py`, и `format_map` в воркере фильтрует только
  `markdown`/`html`.

- **Бот должен быть участником чата** — MAX возвращает `404: chat not found`
  не только при неверном `chat_id`, но и если бот не добавлен в этот чат
  (даже если chat_id реальный). По состоянию на 19.07.2026 бот VeryBot
  (`user_id: 368856070`) ни в одном чате не состоит (`GET /chats` → пусто).
  **Это блокирующая задача для пользователя** перед первым тестом:
  1. Создать чат поддержки в MAX (или использовать существующий).
  2. Добавить туда бота VeryBot (`@id5190100088_bot`).
  3. Вызвать у бота `GET /chats` — увидеть появившийся чат и его `chatId`.
  4. Вставить этот `chatId` в админку → Техподдержка → «Уведомления в MAX».
  5. Нажать «Отправить тестовое сообщение» — придёт в чат.

  Endpoint `/max-bot/test` теперь даёт подсказку по HTTP-коду (404 → membership,
  401 → токен, 403 → права), а не общее «см. логи».
- **`portal_base_url` для inline-кнопки** — берётся из SystemSettings через
  `load_system_settings()`. Если пусто (edge-case в тестах) — fallback на
  относительный `/helpdesk/tickets/{id}` (MAX покажет как текст, но отправка
  не упадёт).
- **13 frontend-тестов `use-app-menu.spec.ts` падают** — это пред-существующая
  регрессия (проверено через `git stash`), не связана с MAX-интеграцией.

## Что НЕ делаем (осознанно)

- MAX-уведомления для других событий (ответы/статус/назначение) — вне скоупа.
- Входящие сообщения из MAX (reply в чате → ответ в тикете) — двусторонняя
  интеграция, отдельная фича.
- Несколько провайдеров (Telegram/Slack) — поле `provider` зарезервировано,
  реализован только `'max'`.
- `get_me`-кеш — `/test` вызывается редко, кешировать нечего.
