# План: полное удаление «Внутренней заметки» (`visibility=internal`) из helpdesk

**Подход:** полное удаление во всех слоях (DB-колонка, enum, API-поле, код, UI, тесты, доки). Обоснование — `AGENTS.md` запрещает костыли/мёртвый код; в БД 0 заметок (29 сообщений, все `public`), миграция безопасна. Новая alembic-миграция **084**.

> ⚠️ Ключевая зависимость: после `DROP COLUMN visibility` **любая** ссылка на `m.visibility` / `HelpdeskMessage.visibility` упадёт в рантайме (SQL + Python). Поэтому вычистить надо _все_ ссылки — план ниже покрывает их полный список из аудита.

---

## Backend

### 1. Модель — `backend/app/models/helpdesk.py`
- Удалить поле `visibility` (стр. 193–195).
- Почистить docstring класса `HelpdeskMessage` (стр. 161–164) — убрать «or internal (agent-only note)».
- Почистить docstring `HelpdeskTicketRead` (стр. 598–601) — убрать упоминания `internal`-заметок.

### 2. Схемы — `backend/app/schemas/helpdesk.py`
- Удалить enum `HelpdeskVisibility` (стр. 40–42).
- Удалить поле `visibility` из `MessageCreateIn` (стр. 232) + docstring (стр. 219–221).
- Удалить поле `visibility` из `MessageOut` (стр. 253).
- Почистить docstrings `TicketOut` (стр. 139) и `TicketAgentOut` (стр. 157–159).

### 3. Сериализаторы — `backend/app/api/helpdesk/_common.py`
- Удалить `_public_messages` (стр. 39–41) + импорт `HelpdeskVisibility` (стр. 21).
- Убрать `visibility` из `message_to_out` (стр. 94).
- Упростить `ticket_to_out` (стр. 196–198) — убрать параметр `requester_view` и фильтр; всегда `list(ticket.messages)`.
- Упростить `ticket_to_agent_out` (стр. 276–277) — убрать «включая internal» в docstring.
- Поправить docstring модуля (стр. 3–7) — убрать секцию про ACL-фильтр internal.

### 4. Роутер — `backend/app/api/helpdesk/tickets.py`
- Удалить Form-параметр `visibility` (стр. 569).
- Убрать `visibility=HelpdeskVisibility(visibility)` из `MessageCreateIn` (стр. 587).
- Убрать ветвление `if payload.visibility == HelpdeskVisibility.public` (стр. 612, 627) — outbox + notify выполняются всегда (при сконфигурированном mailbox).
- Audit metadata: убрать `"visibility": message.visibility` (стр. 641).
- Поправить summary эндпоинта (стр. 560) — убрать `(public/internal)`.
- Проверить вызовы `ticket_to_out(...)` в файле — убрать аргумент `requester_view=...` (если передаётся).

### 5. Сервисы
- **`services/helpdesk/messages.py`**:
  - `add_agent_reply`: убрать `is_public` (стр. 205), упростить — `email_message_id` генерируется при наличии `support_domain`; `cc` сохраняется как есть; авто-назначение + смена статуса (`agent_outbound_reply`) — всегда. Почистить docstring (стр. 178–201) про internal-режим.
  - `add_requester_reply`: хардкод `visibility="public"` (стр. 110) убрать из конструктора.
  - Убрать импорт `HelpdeskVisibility` (стр. 26).
- **`services/helpdesk/email_thread.py`**: убрать фильтр `m.visibility != "internal"` (стр. 63) + docstring.
- **`services/helpdesk/reads.py`** (⚠️ критично — SQL упадёт после DROP COLUMN):
  - Убрать `HelpdeskMessage.visibility == PUBLIC_VISIBILITY` из `has_unread_requester_messages` (стр. 130) и `enrich_with_unread` (стр. 187).
  - Удалить константу `PUBLIC_VISIBILITY` (стр. 42).
  - Почистить docstrings (стр. 8–14, 36–39, 104–108) про internal.
- **`services/helpdesk/tickets.py`**: убрать хардкод `visibility="public"` (стр. 86); почистить docstrings (стр. 5, 270, 417).
- **`services/helpdesk/outbound.py`**: убрать комментарий (стр. 187).
- **`services/helpdesk/archive.py`**: убрать `"visibility": m.visibility` (стр. 95) из JSONB-payload; почистить docstring (стр. 98).
- **`services/helpdesk/ingress.py`**: убрать аргумент `visibility="public"` (стр. 516) из конструктора.

### 6. Миграция — `backend/migrations/versions/084_drop_helpdesk_visibility.py` (новая)
- `down_revision = "083"` (последняя).
- `upgrade()`: `DROP INDEX/CONSTRAINT ck_helpdesk_messages_visibility` (с `IF EXISTS` — безопасно), затем `DROP COLUMN visibility` (с `IF EXISTS`).
- `downgrade()`: восстановить колонку + CHECK (для полноты; downgrades редки, но по конвенции Alembic обязателен).
- DDL — через `op.execute()` (как в `075`), не autogenerate.

### 7. Backend-тесты (удалить/упростить)
- `tests/integration/test_helpdesk_tickets.py`: упростить фильтр (стр. 87 → `full.messages`); удалить `test_internal_note_does_not_make_unread` (стр. 421–450).
- `tests/integration/test_helpdesk_agents.py`: удалить `test_internal_note_does_not_change_status` (стр. 232–252).
- `tests/integration/test_helpdesk_fts.py`: удалить `test_internal_note_is_searched` (стр. 188–205).
- `tests/unit/test_helpdesk_schemas.py`: убрать импорт `HelpdeskVisibility` (стр. 24); упростить `test_defaults_to_public` (стр. 70–72); удалить `test_internal_allowed` (стр. 74–76) и `test_visibility_values` (стр. 142–143).
- `tests/unit/test_helpdesk_email_thread.py`: удалить `test_only_internal_notes_excluded` (стр. 59–64); убрать `visibility="internal"` из хелперов если есть.
- `tests/unit/test_helpdesk_messages_tx.py`: убрать импорт (стр. 29); удалить `test_internal_note_does_not_commit` (стр. 100–109).
- `tests/unit/test_helpdesk_outbound_enqueue.py`: удалить `test_internal_notes_excluded_from_history` (стр. 159–175).
- `tests/unit/test_helpdesk_api_common.py`: удалить класс `TestPublicAclFilter` (стр. 63–93); в `TestMessageMapper.test_basic_mapping` убрать `visibility` (стр. 98–101).
- `tests/unit/test_helpdesk_models.py`: убрать assertion про `visibility` (стр. 108), переименовать тест (стр. 105).

---

## Frontend

### 1. `frontend/src/api/helpdesk.ts`
- Удалить тип `HelpdeskVisibility` (стр. 8).
- Удалить поле `visibility` из `HelpdeskMessage` (стр. 13).
- Удалить поле `visibility?` из `HelpdeskMessageCreateDto` (стр. 197).
- Убрать `fd.append('visibility', ...)` из `replyAgentTicket` (стр. 228).

### 2. `frontend/src/components/helpdesk/TicketReplyForm.vue`
- Удалить `<n-radio-group v-if="agentMode" ...>` (стр. 45–57).
- Убрать `NRadioGroup, NRadioButton` из импорта (стр. 74) — оставить `NCheckbox` (нужен для Cc).
- Убрать `visibility` из типа emit-payload (стр. 98) и из вызова `emit('submit', ...)` (стр. 160).
- Удалить `ref visibility` (стр. 109).
- Удалить CSS `.ticket-reply__visibility` (стр. 201–203).
- ⚠️ **`agentMode` prop НЕ трогать** — он нужен для блока Cc «Ответить всем».

### 3. `frontend/src/components/helpdesk/TicketMessageList.vue`
- Удалить `<n-tag v-if="msg.visibility === 'internal'">` (стр. 27–35).
- Убрать `if (msg.visibility === 'internal') cls.push(...)` из `bubbleClass` (стр. 176).
- Удалить стиль `.chat-bubble--internal` (стр. 275–279).
- В правиле `.chat-bubble__note, .chat-bubble__src` (стр. 294) убрать селектор `__note`, оставив `__src`.
- ⚠️ `agentMode` prop — оставить.

### 4. Страницы
- `HelpdeskAgentTicketDetailPage.vue`: убрать `visibility` из типа `onReply` (стр. 191) и из вызова `replyAgentTicket` (стр. 199). `agent-mode` props — оставить.
- `HelpdeskMyTicketDetailPage.vue`: убрать `visibility` из типа `onReply` (стр. 105).

### 5. i18n — `ru.json` + `en.json`
- Удалить ключи `visibilityPublic`, `visibilityInternal`, `internalNote` (стр. 2535–2537 в обоих файлах).

### 6. Тесты frontend
- `tests/unit/helpdesk-ticket-message-list.spec.ts`: убрать `internalNote` из i18n-моков (стр. 16, 23); `visibility` из `baseMsg` (стр. 33); удалить кейс «shows internal-note tag» (стр. 116–122).
- `tests/unit/helpdesk-agent-ticket-detail-page.spec.ts`: убрать `visibility: 'public'` из stub-emit (стр. 98) и обновить ожидание `replyAgentTicketMock` (стр. 220–234).
- `tests/unit/helpdesk-my-ticket-detail-page.spec.ts`: убрать `visibility: 'public'` из stub-emit (стр. 78).
- `tests/unit/helpdesk-api-cc.spec.ts`: убрать `visibility: 'public'` из DTO (стр. 27, 37, 44).
- `tests/unit/queries-helpdesk.spec.ts`: убрать `visibility` из DTO (стр. 222).

### 7. `types.gen.d.ts` — НЕ править руками
- Перегенерируется через `npm run gen:types` из обновлённого `openapi.json`.

---

## Документация

### Править руками:
- **`docs/helpdesk.md`**: убрать все упоминания internal-заметок (стр. 30, 37, 51, 58, 126, 135, 228, 300, 364, 380, 476, 531, 688, 698, 699, 711) — строку про «Внутренние заметки агентов» целиком, упоминания `visibility` в таблице `helpdesk_messages`, поле `visibility` в Form-параметрах ответа, таблицу нотификаций, фронтенд-описание.
- **`docs/api-contracts.md`** (стр. 3186): убрать `visibility` из Form-параметров `POST /tickets/{id}/messages`.
- **`docs/db-schema.md`** (стр. 1362): убрать `visibility` из описания `helpdesk_messages`.

### Регенерировать (`backend/scripts/`):
- `docs/api-contracts.generated.md` — `python -m scripts.generate_api_contracts_doc`.
- `docs/db-schema.generated.md` — `python -m scripts.generate_db_schema_doc`.
- `docs/tests.generated.md` — соответствующим скриптом (если есть).
- `openapi.json` — `python -m scripts.export_openapi`.

---

## Порядок выполнения
1. Backend-код (модель → схемы → сериализаторы → роутер → сервисы).
2. Новая миграция `084`.
3. Backend-тесты (удалить/упростить) → прогон `ruff check . --fix && mypy app && pytest tests/unit && pytest tests/integration -m integration` (integration — с Docker).
4. Frontend (api → компоненты → страницы → i18n → тесты).
5. Регенерация: `openapi.json` → `types.gen.d.ts` → docs.generated.md.
6. Документация (helpdesk.md, api-contracts.md, db-schema.md).
7. Финальная проверка: `ruff && mypy && pytest` (backend) + `lint:check && typecheck && test:unit && i18n:check` (frontend).

## Хэндофф (в конец сессии)
После прогона всех проверок — выдать готовый текст коммит-сообщения:
`refactor(helpdesk): удалить функционал «Внутренняя заметка» (visibility=internal)`
Не коммитить/пушить — это делает пользователь.

## Риски / внимание
- ⚠️ После `DROP COLUMN` любая ссылка на `m.visibility` падает в рантайме — план покрывает _все_ найденные ссылки (аудит был thorough). Перед прогоном тестов — `grep -rn "visibility" backend/app/services/helpdesk backend/app/api/helpdesk backend/app/models/helpdesk.py backend/app/schemas/helpdesk.py` для финального контроля.
- `agentMode` prop на фронте НЕ удалять (управляет Cc, не только заметками).
- `types.gen.d.ts` править только через `npm run gen:types`, не руками.
- Integration-тесты требуют Docker (`pytest -m integration`).