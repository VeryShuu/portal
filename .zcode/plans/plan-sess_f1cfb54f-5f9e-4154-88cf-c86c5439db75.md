# План: Убрать статус `resolved` — оставить только `closed` как финальный

## Решения (согласованы)
- Удалить статус `resolved` полностью. Статус-машина: `new → open → pending → closed`.
- `closed` = единый финал (агент завершил работу = тикет уходит в архив).
- **Reopen из `closed`** — окно 7 дней (`HELPDESK_REOPEN_WINDOW_DAYS`, без изменений). После — новый тикет. Двухфазное закрытие (resolved → ждём подтверждения → closed) исчезает сознательно.
- Существующие `resolved`-тикеты в БД → **data-миграция в `closed`** (обязательно, иначе зависнут: archive игнорирует не-closed).

---

## Реализация

### Бэкенд

**1. Миграция `079_drop_helpdesk_resolved.py`** (новая, hand-written `op.execute`)
```sql
-- Data-migration: resolved → closed. closed_at = last_activity_at (чтобы честно
-- ушёл в архив по HELPDESK_ARCHIVE_AFTER_DAYS, а не "прожил" лишние дни).
UPDATE helpdesk_tickets
SET status='closed',
    closed_at=COALESCE(closed_at, last_activity_at),
    closed_by_user_id=COALESCE(closed_by_user_id, NULL)
WHERE status='resolved';
-- CHECK-констрейнт: убрать 'resolved' из допустимых значений.
ALTER TABLE helpdesk_tickets DROP CONSTRAINT ck_helpdesk_status;
ALTER TABLE helpdesk_tickets ADD CONSTRAINT ck_helpdesk_status
    CHECK (status IN ('new','open','pending','closed'));
```
Идемпотентно (UPDATE 0 строк — норма, IF NOT EXISTS на constraint).

**2. Lifecycle** (`services/helpdesk/lifecycle.py`):
- `AGENT_SETTABLE_STATUSES` — убрать `resolved` → `{open, pending, closed}`
- `REQUESTER_REOPEN_STATUSES` — убрать `resolved` → `{pending}`
- `ALL_STATUSES` — убрать `resolved` → `{new, open, pending, closed}`
- Docstring'и `agent_set_status`/`requester_reply` — переписать без resolved

**3. Константы** (`core/constants.py`): удалить `HELPDESK_RESOLVED_AUTO_CLOSE_DAYS`.

**4. Схемы** (`schemas/helpdesk.py`):
- `HelpdeskStatus` enum — убрать `resolved = "resolved"`
- `TicketStatusIn.status` Literal — убрать `"resolved"`

**5. Cron** (`worker/tasks/helpdesk.py`):
- Удалить функцию `auto_close_resolved_tickets` целиком
- Убрать из `__all__`, импорт `HELPDESK_RESOLVED_AUTO_CLOSE_DAYS`

**6. Worker main** (`worker/main.py`):
- Убрать импорт `auto_close_resolved_tickets`
- Убрать из `functions=[...]`
- Убрать `cron(...)` расписание (hour=3, minute=25)

**7. Сервисы**:
- `messages.py`: `_REQUESTER_REOPEN_STATUSES` — убрать `resolved` (локальная копия!)
- `tickets.py`: обновить комментарий `active_only` (логика корректна, только текст)
- `notifications.py`: docstring `notify_status_changed` — `closed` вместо `resolved/closed`
- `ingress.py`: без правок (импорт `REQUESTER_REOPEN_STATUSES` из lifecycle — подхватит)

**8. Роутер** (`api/helpdesk/tickets.py`):
- `_TICKET_STATUSES` — убрать `resolved`
- `change_ticket_status`: `if payload.status in {"resolved", "closed"}` → `if payload.status == "closed"`

**9. Модель** (`models/helpdesk.py`): docstring статус-машины без resolved.

### Фронтенд

**10. i18n** (`ru.json`/`en.json`): удалить `helpdesk.statuses.resolved`.

**11. Типы**: `api/helpdesk.ts` (`HelpdeskStatus`, `TicketStatusIn`), `queries/helpdesk.ts` — убрать `'resolved'` из union'ов. `types.gen.d.ts` перегенерируется.

**12. Компоненты/страницы**:
- `TicketStatusBadge.vue` — убрать `case 'resolved'`
- `HelpdeskMyTicketsPage.vue` — убрать radio-фильтр resolved
- `HelpdeskAgentTicketDetailPage.vue` — убрать опцию resolved из `statusOptions`, тип `onStatusChange`
- **`HelpdeskArchivePage.vue`** — упростить: убрать фильтр resolved, убрать `Promise.all`+мерж (теперь только `status: 'closed'`, один запрос)
- `HelpdeskAgentInboxPage.vue` — комментарий (логика без изменений)

### Тесты (~12 файлов)
- `test_helpdesk_lifecycle.py` — убрать `resolved` из parametrize, удалить `test_to_resolved`, `test_to_closed` использует `open→closed`
- `test_helpdesk_schemas.py` — убрать `resolved` из parametrize
- `test_helpdesk_worker_poll.py` — удалить тесты `auto_close_resolved_tickets`
- `test_helpdesk_notifications.py` — удалить/переименовать `test_resolved_*`
- `test_helpdesk_messages_tx.py` — убрать `resolved` из parametrize reopen
- `test_helpdesk_tickets_service.py`, `test_helpdesk_api_common.py` — убрать resolved
- `test_helpdesk_archive.py` — комментарий
- integration: `test_helpdesk_tickets.py`, `test_helpdesk_agents.py` — удалить resolved-тесты

### Дока
- `docs/helpdesk.md` (~15 мест): статус-машина/диаграмма, `AGENT_SETTABLE_STATUSES`, cron-таблица (убрать `auto_close_resolved`), константы, archive (только closed), ingress-шаг
- `docs/wip/helpdesk.md` (ТЗ) — синхронизировать (или пометить историческим)

## Порядок деплоя (важно!)
1. Миграция 079 выполняется **при старте backend** (через `migrate.sh`) — она переведёт resolved→closed **до** того, как новый код начнёт работать. Это безопасно: старый код ещё пишет resolved → миграция их закроет → новый код (в том же образе) уже не пишет resolved.
2. Пересборка `backend` + `worker` (cron-расписание убрано) + `frontend`.

## DoD
- [ ] миграция 079 (data + constraint)
- [ ] бэкенд: lifecycle/constants/schemas/cron/worker/services/router/model
- [ ] фронт: i18n/типы/компоненты/ArchivePage(упрощение)
- [ ] тесты: правка/удаление resolved-ассертов
- [ ] дока helpdesk.md
- [ ] `ruff` + `mypy` + `pytest tests/unit`; фронт `lint`/`typecheck`/`test:unit`/`i18n`
- [ ] пересборка backend + worker + frontend; verify на БД (нет resolved-строк)

## Риски / грабли
- **Локальная копия `_REQUESTER_REOPEN_STATUSES` в messages.py** — не импорт из lifecycle, править отдельно (иначе resolved останется реопениться из email-ответов).
- **`types.gen.d.ts`** автогенерится из OpenAPI — после правки схемы регенерируется (`npm run gen:types`).
- **Cron в 3 местах worker/main.py** (импорт, functions, cron_jobs) — убрать синхронно, иначе ImportError/KeyError при старте worker.
- **archive.py игнорирует не-closed** — data-миграция обязательна, иначе зависшие resolved не архивируются.
- **`HelpdeskArchivePage.vue`** — не просто убрать кнопку, а переделать логику (один запрос вместо мержа).