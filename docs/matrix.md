# Модуль «Корпоративный чат» (Matrix — персональные уведомления)

> **Когда читать:** при работе с уведомлениями в Matrix (Synapse+MAS); при изменении `matrix_bot_settings` / провайдера `matrix` в `messenger_outbox`; при правках клиента `matrix_messenger`, воркера-диспетчера, вкладок админки «Корпоративный чат»/«Очередь мессенджеров», переключателя в профиле; при подключении новых продюсеров чат-уведомлений; при настройке/диагностике бота на сервере Matrix.
> **Ключевой код:** `./backend/app/services/matrix_messenger/` (`_client.py` — CS API, `dm.py` — DmResolver), `./backend/app/api/matrix_bot.py`, `./backend/app/api/messenger_outbox.py` (+`_repo.py`), `./backend/app/models/matrix_bot.py`, `./backend/app/worker/tasks/messenger_outbox.py`, `./frontend/src/components/admin/MatrixBotSettings.vue`, `./frontend/src/pages/admin/tabs/{MatrixTab,MessengerOutboxTab}.vue`, `./frontend/src/components/profile/{ProfilePreferencesCard,AdminChatNotificationsCard}.vue`.
> **ADR:** —. **См. также:** `./docs/email.md` (паттерн outbox), `./docs/helpdesk.md` §MAX-messenger (соседний провайдер), `./docs/api-contracts.md`, `./docs/db-schema.md` (миграция 097).

> Персональные уведомления сотрудникам в корпоративный чат на базе **Matrix Synapse + MAS** (Matrix Authentication Service). Бот портала пишет в личные диалоги (DM); MXID сотрудника вычисляется из email. Реализован **движок** (настройки, доставка, логи, opt-in переключатель) — продюсеры конкретных событий (helpdesk/встречи/новости) подключаются поверх отдельными задачами. Доставка — общий transactional outbox `messenger_outbox` (второй провайдер рядом с MAX, миграция 081); паттерн ретраев/DLQ идентичен `email_outbox`.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`/admin/matrix-bot`, `/admin/messenger-outbox`, `/users/me/preferences`, `/users/admin/{id}/notification-preferences`) |
| Клиент | `httpx` singleton → Matrix Client-Server API v3 (Synapse) |
| Воркер | ARQ `process_messenger_outbox` (каждые 15с) — общий для max+matrix, группировка по провайдеру |
| Хранилище | БД: `matrix_bot_settings` (singleton), `messenger_outbox` (provider='matrix'), `users.preferences` JSONB (opt-in) |
| Префикс API | `/api/v1/admin/*`, `/api/v1/users/*` |
| Шифрование секрета | `access_token_enc` — Fernet (`app/core/secret_crypto.py`), ключ из `SECRET_KEY` |
| Module gate | нет (не модуль `modules.json` — канал доставки, как email) |
| Админка | Группа «Уведомления» (URL-ключ `email` — UI-only лейбл): вкладки `?tab=matrix` и `?tab=messenger-outbox` |

### Ключевые решения (кратко)

- **MXID-конвенция из email**, без поля в профиле: `borzihin.vs@mage.ru` → `@borzihin.vs:matrix.mage.ru` (localpart в lowercase + `server_name` из настроек). Все аккаунты растут из одного Keycloak, email есть у каждого. Исключение — локальный админ (его MXID может не совпадать): в тест-кнопке адресат задаётся вручную.
- **Strictly personal DM** — общего чата/fallback нет (согласовано).
- **Opt-in, дефолт выключен**: сотрудник включает себе в профиле; админ — в профиле любого сотрудника. Продюсеры enqueue'ят только включившим.
- **Только портал → Matrix**: двустороннее (команды из чата) не планируется — appservice/polling не закладывались.
- **Токен вместо пароля** (паттерн [baibot]): аккаунт бота регистрируется **без пароля** (вход по паролю невозможен — желаемое), аутентификация — long-lived compatibility-токен `mct_...`, выданный `mas-cli manage issue-compatibility-token` (пишется прямо в БД MAS, логин-флоу не участвуют → работает при полностью отключённом password-login).

## 2. Сервер Matrix: что сделал админ (выполнено 2026-08-16)

Прод-конфигурация: Synapse + MAS, server_name `matrix.mage.ru`, бот `@portal-bot:matrix.mage.ru`. Контейнер MAS — `mas` (команды через `docker exec -it mas mas-cli ...`).

```bash
# 1. Аккаунт бота БЕЗ ПАРОЛЯ. register-user не требует --password: MAS
#    предупредит «user will not be able to log in» — для бота это желаемое.
docker exec -it mas mas-cli manage register-user portal-bot --display-name "Portal Bot" --yes

# 2. Long-lived токен (mct_...). device_id — ПОЗИЦИОННЫЙ аргумент, не флаг.
docker exec -it mas mas-cli manage issue-compatibility-token portal-bot portal-notify
```

Токен внесён в админку (портал хранит только Fernet-шифр; пароля у бота нет).
Отзыв токена: `mas-cli manage kill-sessions portal-bot` → портал начнёт получать
401 `M_UNKNOWN_TOKEN` (классифицируется permanent, строки уйдут в DLQ).

**Снятие rate-limit с бота** (однократно): дефолт Synapse ~0.17 msg/s задушит
массовую рассылку. Любым admin-токеном:

```bash
POST /_synapse/admin/v1/users/@portal-bot:matrix.mage.ru/override_ratelimit
{"messages_per_second": 0, "burst_count": 0}
```

**Проверка**: админка → Уведомления → Корпоративный чат → «Отправить тестовое
сообщение» (получатель: MXID/email/логин; пусто — сам админ по конвенции).
Сквозная доставка подтверждена на проде 2026-08-16.

## 3. Модель данных (миграция 097)

| Объект | Назначение |
|---|---|
| `matrix_bot_settings` | Singleton (`CHECK id=1`): `enabled`, `homeserver_url` (API endpoint Synapse — FQDN или внутренний адрес), `server_name` (server-часть MXID, default `matrix.mage.ru`), `access_token_enc` (Fernet), `bot_user_id`, `updated_by_user_id`. Сеется с `enabled=false`. ORM: `app/models/matrix_bot.py`; CRUD в `app/api/matrix_bot.py` (как `helpdesk_max_bot_settings`). |
| `messenger_outbox` | Общая очередь мессенджеров: CHECK `provider IN ('max','matrix')` (097), keyset-индекс `(created_at DESC, id DESC)` для админ-списка. Для matrix-строк: `chat_id` = **MXID получателя** (в логах видно человека), `text` = plain-body, `payload.formatted_body` = опциональный HTML. |
| `users.preferences` | Ключ `chat_notifications_enabled: bool` (JSONB, миграция не нужна). Фиксированный набор ключей в `PatchPreferencesRequest`; админский доступ — отдельная схема `AdminPatchPreferencesRequest` (только флаги уведомлений, без служебных ключей). |

## 4. Клиент `app/services/matrix_messenger/`

Транспорт (`_client.py`, httpx singleton, системный SSL-контекст — видит
сертификаты, добавленные через `update-ca-certificates`, важно для внутреннего CA):

- `whoami(homeserver_url, access_token)` — `GET /account/whoami`, проверка токена без побочных эффектов.
- `send_message(..., room_id, txn_id, body, formatted_body=None)` — `PUT /rooms/{roomId}/send/m.room.message/{txnId}`, `m.text` (НЕ `m.notice` — тот suppress'ит уведомления клиентов), `format=org.matrix.custom.html` (whitelist тегов; `body` обязателен как plain-fallback). **`txn_id` = UUID outbox-строки**: идемпотентность на стороне Synapse — ретрай с тем же txnId вернёт тот же `event_id`, дублей не бывает.
- `create_dm(...)` — `POST /createRoom` `{is_direct, invite:[mxid], preset: trusted_private_chat}`.
- `get_direct_rooms` / `set_direct_room` — account data `m.direct` бота: карта «MXID → [room_id, …]» (стандартное хранилище DM, его же ведут клиенты → бот переиспользует чаты, созданные пользователем вручную). 404 `M_NOT_FOUND` = карты ещё нет → `{}`.
- `matrix_id_for_user(email, server_name)` — конвенция (localpart lowercase).
- `MatrixApiError(status_code, errcode)` + `classify_http_error`: **transient** — 429 `M_LIMIT_EXCEEDED` (defer из Retry-After-политики outbox), 5xx, таймауты/сеть; **permanent** — 401 `M_UNKNOWN_TOKEN` (токен отозван), 403 `M_FORBIDDEN`, 400 (в т.ч. invite несуществующего локального юзера — конвенция не гарантирует, что аккаунт существует в Matrix); unknown — прочее.

`DmResolver` (`dm.py`) — батч-кэш «MXID → комната»: ленивая загрузка `m.direct` → есть комната? используем : `create_dm` + запись карты обратно best-effort (провал записи кэша не фейлит отправку — при следующем батче создастся новая комната, старая останется приглашённой).

## 5. Диспетчеризация (воркер)

`process_messenger_outbox` (каждые 15с, distributed lock `messenger:outbox:dispatch:lock`):
watchdog зависших SENDING → `claim_pending` (FOR UPDATE SKIP LOCKED, батч 20) →
**группировка по провайдеру** → каждая группа своими настройками и клиентом:

- `_dispatch_max` — как раньше (helpdesk_max_bot_settings, общий чат);
- `_dispatch_matrix` — валидация настроек (выключен → transient; нет токена/url/bot_user_id или не расшифровывается → permanent) → `DmResolver` → `send_message(txn_id=UUID строки)`.

Сбой одного провайдера не мешает другому (изоляция групп). Персональная
рассылка ~300 получателям упирается в rate-limit Synapse — снят на сервере
(см. §2), но 429-обработка реализована на всякий случай.

Куда смотреть при проблемах: админка → «Очередь мессенджеров» (счётчики
статусов, DLQ-алерт, фильтры, детали/повторить/отменить); метрики
`portal_messenger_outbox_pending/_dlq/_sending_stale` (Grafana).

## 6. API и фронтенд

| Endpoint | Назначение |
|---|---|
| `GET/PUT /admin/matrix-bot` | Singleton настроек; токен write-only (пусто = прежний шифр); `enabled=true` требует токен+homeserver_url+server_name+bot_user_id (400 иначе). Audit `matrix.bot_settings_changed`. |
| `POST /admin/matrix-bot/test` | Энд-ту-энд: whoami (синхронная проверка токена; 401 → перевыпустить) → сообщение **через messenger_outbox** (настоящий путь доставки, видно в «Очереди мессенджеров»; придёт в течение ~30с). Body `{"target": ...}`: MXID как есть / email → конвенция / localpart → `@localpart:server`; пусто → MXID админа. Ошибки доставки (несуществующий MXID и т.п.) — в очереди, `last_error`. |
| `GET /admin/messenger-outbox` (+`/{id}`, `/{id}/retry`, `/{id}/cancel`) | Логи общей очереди (max+matrix): фильтры status/provider/chat_id/q/даты, keyset-пагинация, `counts_30d`. Зеркало email-outbox. |
| `GET/PATCH /users/admin/{id}/notification-preferences` | Флаги уведомлений сотрудника для админ-профиля. Audit `user.notification_preferences_updated`. |
| `PATCH /users/me/preferences` | Self-ключ `chat_notifications_enabled`. |

Фронтенд: группа админки `email` → UI-лейбл «Уведомления» (ключи/URL не
менялись); вкладки «Корпоративный чат» (`MatrixTab` + `MatrixBotSettings`) и
«Очередь мессенджеров» (`MessengerOutboxTab`). Профиль:
`ProfilePreferencesCard` (self; chat-флаг через `patchMyPreferences`, email/inapp
— колонки через `patchMyProfile` — две точки записи, одна кнопка Save) и
`AdminChatNotificationsCard` (admin, чужой профиль). i18n ru+en; `@` в
MXID-примерах экранирован литералом `{'@'}` (спецсинтаксис vue-i18n).

## 7. Подключение продюсеров (следующие задачи)

Продюсер = enqueue в той же транзакции, что и бизнес-операция:

```python
from app.services.messenger_outbox import PROVIDER_MATRIX, enqueue_messenger_message

if bool(user.preferences.get("chat_notifications_enabled")):  # гейт opt-in
    await enqueue_messenger_message(
        db,  # commit на caller'е — outbox-инвариант
        provider=PROVIDER_MATRIX,
        chat_id=matrix_id_for_user(user.email, settings.server_name),  # MXID
        text="plain-фоллбек",
        payload={"formatted_body": "<b>HTML из whitelist'а</b>"},
        related_resource_type="meeting_booking", related_resource_id=booking.id,
    )
```

`chat_id` фиксирует MXID на момент события; `txn_id` = UUID строки (генерит
воркер); ретраи/backoff/DLQ — движок.

## 8. Грабли

- **`@` в i18n-строках** — спецсинтаксис linked-сообщений vue-i18n → экранировать `{'@'}` (иначе падает сборка i18n на CI).
- **`m.notice` не использовать** — клиенты не показывают уведомления для него.
- **`body` обязателен** всегда (plain-fallback); HTML — только whitelist тегов, `style` запрещён.
- **Несуществующий MXID** (аккаунта нет на homeserver) → createRoom 400 → permanent (не крутить ретраи); opt-in переключатель в основном нивелирует.
- **Непринятый invite** (сотрудник ни разу не заходил в Matrix) — отправка формально успешна, не ошибка.
- **`chat_id` matrix-строк — MXID, не room_id**: комнату резолвит воркер (кэш m.direct), админ в логах видит человека.
- **`homeserver_url` со схемой** http(s):// — валидируется схемой `MatrixBotSettingsIn` (как `portal_base_url`).
- **Токен долгоживущий и непривилегированный**: флаг `--yes-i-want-to-grant-synapse-admin-privileges` боту НЕ выдавать; PAT в MAS пока не реализованы (issue element-hq/matrix-authentication-service#4492) — compatibility-токен текущий официальный путь (тот же у baibot).
- **MAS-CLI**: `device_id` у `issue-compatibility-token` — позиционный аргумент (`portal-bot portal-notify`), НЕ `--device-id`.
- **vt-тесты**: не мокать .vue-модули вкладок AdminPage через `vi.mock` (VTU опрашивает `__isTeleport` у типа → module-proxy бросает; на медленном CI — unhandled rejection). Использовать `shallow`-mount.

## 9. История

- **PR #54** (2026-08-16) — движок целиком: миграция 097, клиент, воркер, API, админка, профиль, тесты (backend diff-cover 94%, frontend 84%).
- **PR #55** — инструкция: регистрация бота без пароля; device_id — позиционный аргумент.
- **PR #56** — ручной получатель тестового уведомления (локальный админ с другим MXID).
- 2026-08-16 — сквозная проверка на проде: тестовое сообщение доставлено.
