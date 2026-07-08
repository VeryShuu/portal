# Фича: Helpdesk — production-readiness фиксы (review remediation)

## Цель
Устранить дефекты, выявленные код-ревью модуля helpdesk перед выводом в прод:
3 CRITICAL (транзакционная дисциплина), 2 MAJOR (безопасность), 1 MAJOR (рефакторинг) + minor качества кода.

## Решения по ходу
- 2026-07-08: scope = полный (#1–#6 + minor), согласовано с владельцем.
- 2026-07-08: SSRF (#4) — best-effort: follow_redirects=False + ручная обработка с re-валидацией каждого hop. Битая redirect-картинка остаётся как есть, не роняет ingest.
- 2026-07-08: Инъекция в чужой тикет (#5) — сверка sender_email↔requester_email для subject/recipient-token fallback'ов; при несовпадении → новый тикет. References-матч (секрет Message-ID) — без сверки.
- 2026-07-08: Outbox-инвариант (#3) меняет UX: сбой enqueue откатывает ответ агента (раньше ответ сохранялся, письмо терялось). Соответствует AGENTS.md (outbox в той же транзакции, что бизнес-операция).

## Чеклист (DoD)

### Фаза 1 — CRITICAL: транзакции
- [x] #1 Архивация: `db.commit()` в `archive_closed_tickets` + unit-тест `commit.assert_awaited_once()`
- [x] #2 Ingress: `db.rollback()` в except-цикла UID + единый commit сообщения+лога
- [x] #3 Outbox-инвариант: единый commit (agent reply + outbox row); assign/take аналогично

### Фаза 2 — MAJOR: безопасность
- [x] #4 SSRF: `follow_redirects=False`, ручные hops с re-валидацией, async `getaddrinfo`
- [x] #5 Сверка sender↔requester для subject/recipient fallback'ов

### Фаза 3 — MAJOR: рефакторинг
- [x] #6 Вынос `enqueue_reply_outbound`/`enqueue_assigned_email`/helpers в `services/helpdesk/outbound.py`

### Фаза 4 — minor
- [x] Локальные импорты → уровень модуля (attachments.py, notifications.py)
- [x] Мёртвый код: `change_status` try/except, `_AUTO_HEADERS`, `archive` параметр `poll_mailbox`
- [x] `_Suppress` → `contextlib.suppress` (worker + ingress)
- [x] Enum check упростить (messages.py)
- [x] Docstring `_make_outbound_message_id`
- [x] Helper `html_to_plain` (дедуплицировать re.sub)
- [x] Публичный `strip_subject_token` в threading.py

### Фаза 5 — проверка
- [x] `ruff check .` (clean) + `mypy app` (Success: no issues) + `pytest tests/unit` (3162 passed)
- [x] `pytest tests/integration -k helpdesk` (53 passed; 1 fail — `test_get_before_put_returns_not_configured` из-за загрязнения БД `mail.mage.ru`, не связано с фиксом)
- [x] `npm run lint:check` (0 errors) + `npm run typecheck` (ok) + `npm run i18n:check` (ok)
- [x] `docs/helpdesk.md` обновлён (§2 outbound.py, §6 SSRF, §8 matching+outbox, §10 archive tx)

## Грабли / контекст
- **Savepoint-модель `real_db_session`:** commit в тестовой сессии продвигает savepoint, не фиксирует в БД → интеграционные тесты маскируют отсутствие commit. Полагаться на unit-тесты `commit.assert_awaited()` (паттерн `test_audit.py`/`test_kb_service.py`).
- **`enqueue_outbox_email` НЕ коммитит** (докстринг требует caller'а). Meetings/news/file-share — единый commit бизнес+outbox. Helpdesk нарушал — фикс #3 приводит к паттерну.
- **ARQ worker redis без `decode_responses`** → значения как bytes. В helpdesk.py уже есть guard `isinstance(last, bytes)`. Не трогаем.
- **"Двойной префикс #TKT"** из ревью — НЕ баг: `ticket_number`=`TKT-123`, `#{...}`→`#TKT-123`. Не трогаем.
- **`change_status` no-op try/except** — в SERVICE `tickets.py:313`, не в роутере (ревью неточно).
- **#3 контракт:** `add_agent_reply` вызывается только из одного роутера (`add_agent_message`). Проверить grep'ом при реализации.
