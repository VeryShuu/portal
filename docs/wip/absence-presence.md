# Фича: единый статус присутствия из ERP + кольцо аватарки (`current_status`)

> **Когда читать:** возобновляешь незавершённую многосессионную задачу — этот
> план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Удаляется после мёржа фичи (чтобы `wip/` отражал только активную работу).

## Цель

Заменить древний ручной `users.presence_status` (`office`/`remote`/`vacation`)
единым **вычисляемым** статусом `current_status` на основе ERP-импорта
отсутствий (`erp_absences`). Источник истины — только ERP; ручной выбор убран.
Статус отображается **кольцом вокруг аватарки** во всех местах портала.

4 категории (маппинг из 7 ERP-kinds):
- `working` 🟢 зелёный — нет активной absence
- `vacation` 🟡 жёлтый — `vacation_main`/`vacation_extra`/`unpaid_leave`/`day_off_paid`/`day_off_unpaid`
- `sick` 🔴 красный — `sick`
- `business_trip` 🟣 фиолетовый — `business_trip`

Приоритет при пересечении нескольких absence: `sick` > `vacation` > `business_trip`.

## Решения по ходу

- **2026-08-05**: источник истины — ТОЛЬКО ERP. Ручная смена статуса убирается
  целиком (колонка `presence_status` дропается). «Удалёнка» (`remote`) убрана —
  такого бизнес-концепта у заказчика нет.
- **2026-08-05**: палитра — жёлтый=отпуск/отгул (по запросу заказчика, расходится
  с Teams-конвенцией «фиолетовый=OOO», но принято осознанно).
- **2026-08-05**: данные денормализованы в 2 колонки на `users`
  (`current_status`, `current_status_until`) — чтобы не было N+1 JOIN в списках.
  Все `users_repo` SELECT'ы тянут `select(User)` целиком → подхватят бесплатно.
- **2026-08-05**: `TicketMessageList.vue` пропущен (DTO сообщения без user_id) —
  отдельная будущая задача.

## Чеклист (DoD)

### Backend
- [ ] миграция 093 (add `current_status`/`current_status_until`, backfill, drop `presence_status`)
- [ ] модель User: убрать `presence_status` + CHECK, добавить новые колонки + CHECK
- [ ] `app/services/erp_sync/absences_status.py` (kind→category, recompute_current_status)
- [ ] интеграция recompute в `absences_importer.py` (old_user_ids + after flush)
- [ ] cron `worker/tasks/presence_status.py` + регистрация в `worker/main.py`
- [ ] schemas: UserPublic/UserMe — current_status; Birthday/NewsAuthorPublic — current_status
- [ ] убрать presence_status из PatchProfileRequest / me.py / users_me_service.py
- [ ] тесты: механический fix ~33 + новые unit/integration на recompute

### Frontend
- [ ] API типы: users.ts, auth.ts, news.ts — current_status
- [ ] новый компонент `components/UserAvatar.vue` (ring + initials + tooltip)
- [ ] tokens.css — секция Presence ring
- [ ] i18n ru/en — секция users.presence
- [ ] замена 7 мест на `<UserAvatar>` (StaffCard, ProfileHero, DepartmentColleagues,
      BirthdaysWidget, HeaderUserMenu, NewsCommentItem, NewsComments)
- [ ] убрать селектор статуса в ProfilePreferencesCard.vue
- [ ] текстовая пометка отсутствия в StaffTableView/StaffRow (табличный режим)
- [ ] тесты: fix fixtures + новый user-avatar.spec.ts

### Docs / регенерация
- [ ] db-schema.md (curated) — блок users
- [ ] регенерация: openapi.json, types.gen.d.ts, tests.generated.md,
      db-schema.generated.md, api-contracts.generated.md
- [ ] ci_lint + pytest unit green; frontend lint/typecheck/vitest/i18n green
- [ ] PR + 16 checks green

## Грабли / контекст

- **«Исчезнувший» сотрудник**: перед `DELETE FROM erp_absences WHERE source='erp_sync'`
  обязательно собрать `old_user_ids`, иначе после удаления строки пользователь
  навсегда останется в `vacation`. `recompute_current_status(db, old ∪ new)`.
- **Backfill SQL** в миграции 093: один UPDATE с CTE + DISTINCT ON (user_id),
  опирается на `ix_erp_absences_dates`.
- **`Birthday`/`NewsAuthorPublic` DTO** изначально не содержали статуса —
  добавлен бэкенд-добор (F1/B6).
- **raw-SQL INSERT в тестах** (`test_analytics_db.py`, `test_bookmarks_race.py`):
  колонку надо убрать И из списка колонок, И из VALUES.
- **`test_migrations.py:154`**: `presence_status` в `expected_columns` → заменить
  на `current_status`.
