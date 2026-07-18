# План: архив + двухблочный вид + unread для пользователя helpdesk

## Контекст

Сейчас у пользователя (`/helpdesk/my`) — плоский одностраничный список своих заявок с radio-фильтром статусов, без архива, без подсветки обновлений. У агентов всё это уже есть. Задача — довести пользовательский UI до симметрии с агентским.

**Решения (подтверждены пользователем):**
1. Архив — **отдельной страницей** `/helpdesk/my/archive` (как `/helpdesk/archive` у агентов)
2. Деление — **неназначенные / назначенные** (по наличию `assignee_user_id`, не по статусу)
3. Unread для пользователя — **ответы агентов** (`direction=outbound, visibility=public` после `last_seen_at`)

---

## 1. Backend: параметризация unread + requester-фильтры

### 1.1 `services/helpdesk/reads.py` — параметризация направления
Сейчас `has_unread_requester_messages` и `enrich_with_unread` захардкожены на `direction='inbound'` (для агентов — ответы заявителя). Для заявителя нужно `direction='outbound'` (ответы агентов).

**Подход:** добавить опциональный параметр `direction: str = INBOUND_DIRECTION` в обе функции. Имена функций **не меняем** (контракт агентского пути стабилен), но они станут generic. Вызов в `list_all_tickets` остаётся как есть (по умолчанию `inbound`).

Константы (уже есть): `INBOUND_DIRECTION = "inbound"`, добавить `OUTBOUND_DIRECTION = "outbound"`.

### 1.2 `services/helpdesk/tickets.py` — фильтры для двухблочного вида
Расширить `list_my_tickets` / `count_my_tickets` параметрами `unassigned: bool = False` / `assigned: bool = False` (по образцу `_agent_filter_conditions:271-277`). Логика: `unassigned` → `assignee_user_id.is_(None)`, `assigned` → `.is_not(None)`. Взаимоисключающие через `elif` (как у агентов).

Это даст фронту возможность слать `?unassigned=true` и `?assigned=true` для двух блоков.

### 1.3 `api/helpdesk/tickets.py` — requester read-endpoint + обогащение unread

**Новый endpoint** `POST /tickets/my/{ticket_id}/read`:
- `user: CurrentUser` (не HelpdeskAgentDep)
- `fetch_ticket_for_user` (ACL: только свои → 404 если чужой)
- `reads_service.mark_ticket_seen(db, ticket_id, user_id=user.id)`
- `db.commit()`
- возврат `MarkTicketReadOut`

**Обогащение `list_my_tickets` (GET /tickets/my):** после выборки вызвать `enrich_with_unread(db, tickets=items, user_id=user.id, direction="outbound")` и передать map в `ticket_to_list_out(i, unread=...)`. Один запрос на весь список (защита от N+1).

**Расширение query-параметров** `GET /tickets/my`: добавить `unassigned: bool`, `assigned: bool` (пробрасываются в `list_my_tickets`/`count_my_tickets`).

---

## 2. Frontend: новый роут + 2 страницы + правки

### 2.1 `router.ts` — новый роут `helpdesk-my-archive`
```ts
{ path: '/helpdesk/my/archive', name: 'helpdesk-my-archive',
  component: () => import('./pages/helpdesk/HelpdeskMyArchivePage.vue'),
  meta: { requiresAuth: true } }  // не requiresHelpdeskAgent — доступ всем
```
Константа `HELPDESK_MY_ARCHIVE: '/helpdesk/my/archive'`.

### 2.2 Новая страница `HelpdeskMyArchivePage.vue` (по образцу `HelpdeskArchivePage.vue`)
- Шапка: заголовок + кнопка «К моим заявкам» → `/helpdesk/my`
- Фильтр: поиск `q` (если добавлю на бэкенде; иначе без поиска — `fetchMyTickets({status:'closed'})`)
- `TicketListItem` (user-mode) — переиспользуется как есть
- Пагинация

**Search `q` для my-archive:** у `GET /tickets/my` сейчас нет `q`. Добавлю минимально — проброс в `list_my_tickets` (по образцу агентского FTS через `_agent_filter_conditions`, но для my-фильтра). Если это усложнит — отложу search в my-archive, оставив только список closed. В плане заложу добавление `q` для симметрии.

### 2.3 `HelpdeskMyTicketsPage.vue` — двухблочный вид (переписать)
По образцу `HelpdeskAgentInboxPage.vue`:
- Шапка: заголовок + кнопка «Архив» (на `/helpdesk/my/archive`) + кнопка «Создать заявку»
- **Блок «Ожидают принятия»** (вверху): `fetchMyTickets({unassigned: true, limit, offset})` — свои тикеты без агента
- **Блок «В работе»** (ниже): `fetchMyTickets({assigned: true, limit, offset})` — свои тикеты с назначенным специалистом
- Отдельная пагинация по блокам (как у агентов)
- `TicketListItem` (user-mode) — без кнопки Take, с unread-dot (если бэкенд прислал `unread:true`)
- Поиск `q` (если добавлю) — схлопывает блоки в плоский список

Шапку таблицы (5 колонок) оставляю как есть — она уже корректная для user-mode.

### 2.4 `api/helpdesk.ts` — новые функции + типы
- Расширить `HelpdeskMyListParams`: `unassigned?: boolean`, `assigned?: boolean`, `q?: string`
- `fetchMyTickets` — пробрасывает новые параметры
- `markMyTicketRead(id)` — `POST /helpdesk/tickets/my/{id}/read`

### 2.5 `HelpdeskMyTicketDetailPage.vue` — вызов markMyTicketRead
В `load()` после успешного `fetchMyTicket` вызвать `markMyTicketRead(ticketId)` best-effort (по образцу `HelpdeskAgentTicketDetailPage.vue:140`).

### 2.6 i18n (`ru.json` + `en.json`) — новые ключи `helpdesk.*`
- `sectionWaiting` = «Ожидают принятия» / «Awaiting assignment» (блок неназначенных)
- `sectionMyInWork` = «В работе у специалиста» / «In progress» (блок назначенных)
- `myArchiveTitle` = «Архив моих заявок» / «My archived tickets»
- Переиспользуются: `archive`, `backToList`, `searchPlaceholder`, `hasUnread`, `noTickets`, колонки таблицы

---

## 3. Тесты

### 3.1 Backend unit (`tests/unit/test_helpdesk_reads.py` — расширить)
- `enrich_with_unread` с `direction="outbound"` → находит ответы агентов, не находит ответы заявителя
- `has_unread_requester_messages` осталась `inbound` (регрессия агентов)

### 3.2 Backend unit (`test_helpdesk_tickets_service.py` — расширить)
- `list_my_tickets` с `unassigned=True` → только тикеты без assignee
- `list_my_tickets` с `assigned=True` → только с assignee
- `count_my_tickets` — те же фильтры

### 3.3 Frontend unit
- `HelpdeskMyTicketsPage` — рендер двух блоков, кнопки «Архив», навигация
- `HelpdeskMyArchivePage` — рендер списка closed, кнопка «Назад»

---

## 4. Документация — `docs/helpdesk.md`
- §4 API — `POST /tickets/my/{id}/read`, новые query-параметры `/tickets/my`
- §14 Frontend UI — двухблочный вид my-tickets, my-archive, unread для заявителя

---

## DoD

- [ ] `reads.py`: параметр `direction` в `has_unread_requester_messages` + `enrich_with_unread`
- [ ] `tickets.py` (service): `unassigned`/`assigned` в `list_my_tickets`/`count_my_tickets`
- [ ] `tickets.py` (api): `POST /tickets/my/{id}/read`, обогащение unread в `list_my_tickets`, query-params `unassigned`/`assigned`
- [ ] `router.ts`: роут `helpdesk-my-archive`
- [ ] `HelpdeskMyArchivePage.vue` (новая)
- [ ] `HelpdeskMyTicketsPage.vue` — двухблочный вид + кнопка «Архив»
- [ ] `api/helpdesk.ts`: расширить `HelpdeskMyListParams` + `markMyTicketRead`
- [ ] `HelpdeskMyTicketDetailPage.vue`: вызов `markMyTicketRead`
- [ ] i18n ru/en
- [ ] Backend unit-тесты (reads direction, my-filters)
- [ ] Frontend unit-тесты
- [ ] `docs/helpdesk.md` §4, §14
- [ ] ruff + mypy + pytest + frontend checks → green

---

## Что НЕ делаем (осознанно)

- ❌ **Не делаем «Прочитать всё»** для пользователя — вне скоупа (как и у агентов)
- ❌ **Не меняем имена существующих функций** `reads.py` — параметризация через опциональный `direction`, агентский путь стабилен
- ❌ **Не добавляем my-archive в меню** — пользователь идёт через кнопку «Архив» в шапке «Мои заявки» (как агент через «Инбокс»). Отдельный пункт меню — перегрузка для обычного юзера
- ❌ **Не делаем mine/all переключатель** в my-archive — все тикеты свои, делить не по чему (в отличие от агентского архива)

---

## Риски / замечания

- **`list_my_tickets` с `unassigned=true`** — у заявителя «неназначенные» = тикеты, где ещё нет агента. Это осмысленное деление (пользователь видит «заявка принята, ждём специалиста» vs «специалист назначен, в работе»). Нюанс: тикет может быть `new` + неназначенный, или `open` + назначенный — статус и assignee ортогональны. Деление по assignee (а не по status) даёт то, что хочет пользователь («когда мной займутся»).
- **Параметризация `reads.py`** — добавление опционального `direction` минимально меняет сигнатуру. Существующие вызовы (`list_all_tickets`) передают только `tickets`/`user_id`, дефолт `direction=INBOUND_DIRECTION` сохраняет поведение. Регресс-тесты подтвердят.
- **Unread для заявителя и агента на одном тикете** — таблица `HelpdeskTicketRead` хранит `(ticket_id, user_id)` без указания «кто этот user». Если пользователь одновременно агент (видит тикет с двух сторон), его `last_seen_at` будет один — но unread для агентского просмотра (inbound) и пользовательского (outbound) считается разными SQL-запросами с разным `direction`. Это нормально: один `last_seen_at` на пару, но разные контракты «что считать непрочитанным».