# Фича: Audit Batch 3 — M8 + M3 + M2 + M12 + M14

## Цель
Закрыть 5 активных задач из `audit.md` за одну сессию: 2 frontend-рефакторинга (M12, M14) +
3 backend-задачи (M8 generic analytics, M3 batch INSERT outbox, M2 keyset pagination).

## Решения по ходу
- 2026-08-02: M9 заменена на M2 — разведка показала что M9 это 2-3 PR (двойное чтение JSON двумя
  модулями с разными типами, SSRF-параметризация затронет bookmarks/email_images). M2 тоже M, но
  self-contained.
- 2026-08-02: Разведка M14 выявила, что `useAgentInboxQuery` и `useTakeTicketMutation` УЖЕ существуют
  (`queries/helpdesk.ts:190-196,255-266`) — страница их просто не использует. Задача = rewiring.
- 2026-08-02: Разведка M12 выявила, что `useLinkIconUpload.ts` УЖЕ готов и идентичен inline-коду.
  Задача сводится к выносу `useLinkForm` + `useLinkColumns` + подключению готового composable.
- 2026-08-02: Разведка M2 — оба репо уже используют `ORDER BY created_at DESC, id DESC` (нужно для
  keyset). НО индекса `(created_at DESC, id DESC)` НЕТ ни на audit_log, ни на email_outbox → нужна
  миграция (иначе keyset = тот же Seq Scan, фикса бессмысленна).

## Чеклист (DoD)

### M12 — LinksTab.vue → composables
- [x] `composables/useLinkForm.ts` — state `{ linkForm, editingLink, savingLink, linkRules }` + actions (openAdd/openEdit/submitLink/openDeleteLink)
- [x] `composables/useLinkColumns.ts` — `buildLinkColumns({ onEdit, onDelete })` (образец useUsersTableColumns)
- [x] LinksTab.vue использует `useLinkIconUpload` (уже готов) вместо inline-дубликата
- [x] LinksTab.vue ≤ ~120 LOC script setup (было 279)
- [x] Unit-тесты на submitLink (happy + invalid) + useLinkColumns
- [x] `npm run lint:check && typecheck && test:unit` зелёные

### M14 — HelpdeskAgentInboxPage → TanStack Query
- [x] 0 ручных `ref` для server state (newItems/newTotal/newLoading/inWork*/search*) → query.data
- [x] `onTake` → `useTakeTicketMutation` + qc.invalidateQueries (вместо ручного loadAll)
- [x] loadNew/loadInWork/loadSearch → useAgentInboxQuery (3 экземпляра с разными params)
- [x] URL/scope-поведение идентично (search mode, localStorage scope, auth-bootstrap watch)
- [x] Существующие 10 characterization-тестов адаптированы под Query-mocks
- [x] `npm run lint:check && typecheck && test:unit` зелёные

### M8 — generic dataset_endpoint для analytics
- [x] `dataset_endpoint(name, repo_fn, out_cls, columns)` decorator/registry
- [x] 8 dataset-эндпоинтов → generic + реестр (без изменения URL/contract)
- [x] `_EXPORT_COLUMNS` + `_export_rows` объединены в реестр
- [x] −~120 LOC
- [x] Существующие 24 unit-теста зелёные (characterization) + новый тест «add dataset = 1 строка»

### M3 — Batch INSERT в meetings outbox
- [x] `enqueue_outbox_email_batch(items: list[OutboxItem])` в email_outbox.py (один multi-row INSERT)
- [x] `_enqueue_all_recipients` / `_enqueue_updated_with_diff` → batch (один INSERT на ветку)
- [x] Outbox-инвариант сохранён (commit в той же tx, не открывает свою сессию)
- [x] Characterization-тест: 50 участников → 1 INSERT-statement (через session.execute.call_count)
- [x] Существующие 11+32 теста meetings notifications зелёные

### M2 — keyset pagination для audit/outbox
- [x] Миграция 085: CREATE INDEX CONCURRENTLY (created_at DESC, id DESC) на audit_log + email_outbox
- [x] Backend: опциональный `?cursor=` (base64-encode `created_at|id`), backward-compat offset
- [x] Response: добавить `next_cursor`/`has_more`, не ломая `{items,total,limit,offset}`
- [x] Frontend AuditTab + EmailOutboxTab: hybrid page→cursor map (сохранить page-based UI)
- [x] Integration-тест: 10k строк, OFFSET 10000 vs cursor → keyset быстрее
- [x] openapi.json регенерирован (cursor в 2 endpoints)

### Общее
- [x] `backend/scripts/ci_lint.sh` зелёный
- [x] `pytest tests/unit` зелёный
- [x] frontend `lint:check && typecheck && test:unit && i18n:check` зелёные
- [x] Регенерированы tests.generated.md, openapi.json, api-contracts.generated.md (если нужно)
- [x] audit.md: 5 карточек `[x]` + запись в «Истории изменений»

## Грабли / контекст
- AGENTS.md: ruff/mypy/radon в CI зафискированы на == — проверять через `backend/scripts/ci_lint.sh`,
  не локальными версиями.
- M14: characterization-тесты mock'ают `api/helpdesk`, а не `@tanstack/vue-query` — при миграции
  надо переключить mock-стратегию (образец `queries-helpdesk.spec.ts:201-249`).
- M2: партиционированный audit_log — CREATE INDEX на parent автоматически развернётся на партиции,
  но нужен CONCURRENTLY per-migration (zero-downtime).
- main защищена — только через PR + 16 обязательных чеков. Коммитит/мёрджит пользователь.
