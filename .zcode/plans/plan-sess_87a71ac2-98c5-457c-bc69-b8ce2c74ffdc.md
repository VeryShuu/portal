# План: два бага helpdesk

## Баг №1 — закрытая заявка остаётся в «В работе» (сотрудник)

**Корень:** `GET /helpdesk/tickets/my` и `count_my_tickets`/`list_my_tickets` не имеют фильтра «только активные». В отличие от агентского `GET /tickets`, где `active_only` уже есть и фильтрует `status IN ('new','open','pending')`. Симметризую.

### Backend
1. **`backend/app/services/helpdesk/tickets.py`** — добавить параметр `active_only: bool = False` в `count_my_tickets` (стр. 120–139) и `list_my_tickets` (стр. 184–219). Логика зеркальна `_agent_filter_conditions` (стр. 327–334):
   ```python
   if status_filter:
       conditions.append(HelpdeskTicket.status == status_filter)
   elif active_only:
       conditions.append(HelpdeskTicket.status.in_(_ACTIVE_STATUSES))
   ```
   Использую существующую константу `_ACTIVE_STATUSES = ("new","open","pending")` (стр. 145) — не дублирую.
   `elif` (а не `if`): конкретный `status_filter` точнее, как у агентов.

2. **`backend/app/api/helpdesk/tickets.py`** — в `list_my_tickets` (стр. 152–189) добавить `active_only: bool = Query(default=False)` и пробросить в оба вызова сервисного слоя (`count_my_tickets` + `list_my_tickets`). FastAPI автоматически маппит `active_only` ↔ query-параметр `active_only`.

### Frontend
3. **`frontend/src/api/helpdesk.ts`** — в `HelpdeskMyListParams` (стр. 97–105) добавить поле `activeOnly?: boolean`. В `fetchMyTickets` (стр. 114–116) сделать преобразование camelCase→snake_case (как уже сделано в `fetchAgentTickets` стр. 127–133):
   ```ts
   const { activeOnly, ...rest } = params
   const query: Record<string, unknown> = { ...rest }
   if (activeOnly) query.active_only = true
   return api<HelpdeskTicketList>('/helpdesk/tickets/my', { params: query })
   ```

4. **`frontend/src/pages/helpdesk/HelpdeskMyTicketsPage.vue`** — в `loadWaiting` (стр. 172) и `loadInWork` (стр. 189) добавить `activeOnly: true` к `fetchMyTickets({...})`. Закрытые тикеты уходят в архив (`HelpdeskMyArchivePage.vue` уже корректно фильтрует `status=closed`).

### Тесты
5. **`backend/tests/unit/test_helpdesk_tickets_service.py`** — добавить 2 characterize-теста рядом с существующими агентскими (`test_active_only_*`, стр. 124–155):
   - `count_my_tickets` с `active_only=True` → возвращает только new/open/pending (closed исключается)
   - `list_my_tickets` с `active_only=True` → то же для списка
   - `active_only=True` игнорируется при явном `status_filter="closed"` (для архива заявителя — симметрия с агентом)

## Баг №2 — кнопка «К инбоксу» в архиве агента

**Корень:** `HelpdeskArchivePage.vue` (стр. 7–13) — `<n-button tag="a" href="/helpdesk">` рендерится в сырой `<a>`, который делает полную перезагрузку страницы вместо SPA-роутинга. На sub-path/SSO-флоу это ломается. В файле уже импортированы `useRouter` (стр. 68, 76) — нужно только вызвать `router.push`.

### Frontend
6. **`frontend/src/pages/helpdesk/HelpdeskArchivePage.vue`** — заменить кнопку:
   ```vue
   <n-button quaternary @click="goToInbox">
     {{ t('helpdesk.backToInbox') }}
   </n-button>
   ```
   И добавить handler (по образцу `HelpdeskAgentTicketDetailPage.vue:204-206`):
   ```ts
   import { ROUTES } from '../../router'
   function goToInbox() {
     router.push(ROUTES.HELPDESK_INBOX)
   }
   ```
   Убираю атрибуты `tag="a"` и `href="/helpdesk"`.

## DoD (по AGENTS.md)
- [x] Backend-код + unit-тесты одновременно
- [ ] `ruff check . && mypy app` (backend)
- [ ] `pytest tests/unit` (backend) — особенно `test_helpdesk_tickets_service.py`
- [ ] `npm run lint:check && npm run typecheck && npm run test:unit` (frontend)
- [ ] API-контракт: `active_only` — новый опциональный query-param на `GET /tickets/my`, backward-compatible (default False), не ломает существующих клиентов. В `docs/api-contracts.md` правка опциональна (auto-gen `api-contracts.generated.md` обновится при `gen:types`), отмечу в handoff.

## Что НЕ меняю
- Не трогаю `tag="a" href` на других страницах helpdesk (по решению пользователя — только архив агента).
- Не добавляю per-row reopen на странице архива (кнопка — просто навигация).
- Не трогаю `HelpdeskMyArchivePage` (фильтр `status=closed` там уже корректный).
- Миграций нет (фильтр на уровне SQL-условий, схема не меняется).