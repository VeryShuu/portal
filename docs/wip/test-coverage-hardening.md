# Фича: Закрытие пробелов в тестовом покрытии

> **Когда читать:** возобновляешь незавершённую многосессионную задачу — этот
> план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Создаётся, как только ясно, что задача не закроется за одну сессию; удаляется
> после мёржа фичи (чтобы `wip/` отражал только активную работу).

## Цель

Закрыть точечные пробелы в тестовом покрытии, выявленные аудитом 2026-07-11:
helpdesk-модули бэкенда (молодой модуль миграции 075), 4 helpdesk-страницы
фронта без тестов (0%), конвертация ~150 поверхностных smoke-assertions в
поведенческие, parametrize-рефакторинг ACL-тестов, углубление CSRF-тестов,
i18n-проверки, синхронизация `docs/testing.md` с актуальными цифрами.

Эта итерация **отдельна** от `remediation-plan.md` (его пункты 10/15 закрыты,
но helpdesk появился позже).

Базовые цифры аудита (2026-07-11):
- Backend: **3232** unit+security тестов (gate 75%), покрытие **78.95%**.
- Backend integration: **440** тестов (real PG+Redis).
- Frontend: **1884** Vitest-тестов, покрытие **65.19% lines / 60.04% branches / 52.43% funcs** (gate 50/35/50).

## Решения по ходу

- **2026-07-11**:Helpdesk — только unit-моки (по образцу `test_helpdesk_messages_tx.py`), integration на реальной PG оставлены как будущая задача (план уже есть в `tests.generated.md`).
- **2026-07-11**:Smoke-конвертация — pages-smoke растаскиваем в отдельные файлы + конвертируем в поведенческие по эталону `home-page.spec.ts`; components-smoke-extra1-5 добираем точечно (формы/модалы), не растаскиваем.
- **2026-07-11**:UI-переключателя языков (LanguageSwitcher) нет → тестируем конфиг `i18n/index.ts` + парность ключей ru↔en, а не поведение переключения.
- **2026-07-11**:parametrize для `perm_gte` в обоих ACL-файлах — контракт 1:1, число test-cases сохраняется (16). Фактически: files_acl 6→8 (добавлены editor/editor + manager/viewer для полноты), kb_acl 10→10 (1:1).

## Чеклист (DoD)

### Этап 1 — Backend helpdesk unit-тесты
- [x] 1.1 `services/helpdesk/messages.py` 67%→**94%** — 7 новых тестов в `test_helpdesk_messages_tx.py` (`add_requester_reply` reopen-логика + commit-контракт, `_eager_load_attachments` ветка fresh-is-not-None, `fetch_ticket_with_messages` found/missing). Грабли: реальный `HelpdeskMessage` требует ORM-совместимые элементы в `attachments` — SimpleNamespace падает с `_sa_instance_state`, для unit взят пустой список.
- [x] 1.2 `services/mailing_recipients.py` 52%→**97%** — 18 новых тестов в `test_mailing_recipients.py` (`_escape_like` parametrize, `list_recipients` фильтр/пагинация/total через side_effect count+select, `get_recipient_or_404` 404, `update_recipient` IntegrityError→409 + sorted changes, `soft_delete_recipient`).
- [x] 1.3 `services/helpdesk/notifications.py` 41%→**99%** — новый `test_helpdesk_notifications.py` (16 тестов): `_select_agents_to_notify` (exclude/require_notify_new), `_fan_out` (commit-до-publish контракт, empty), `notify_ticket_created`, `notify_ticket_assigned` (requester≠actor, assignee≠actor, edge-cases), `notify_agent_reply`, `notify_requester_reply` (assignee vs все агенты), `notify_status_changed` (closed→reopen-окно в body). Грабли: `_fan_out` мокается через `patch.object`, чтобы тестировать только логику получателей.
- [x] 1.4 `services/helpdesk/tickets.py` 29%→**99%** — новый `test_helpdesk_tickets_service.py` (32 теста): `_agent_filter_conditions` (7 сценариев), `resolve_requester_user` (3 ветки), `reopen_ticket` (IllegalTransitionError + happy), `change_status` (closed-fields + illegal target), `assign_ticket` (new→open vs reassign), count/list/fetch (user+agent), `link_guest_tickets` (match/case-insensitive/empty), `create_ticket` (инвариант первого сообщения + attachments). Грабли: (1) `new→closed` **разрешён** lifecycle (спам-краевой случай) → для IllegalTransition нужен невалидный target; (2) `link_guest_tickets` вызывает `scalars().all()` **без** `.unique()` → отдельный хелпер `_db_returning_scalars_all_plain`.
- [x] 1.5 `worker/tasks/helpdesk.py` 41%→**92%** — расширено `test_helpdesk_worker_poll.py` (+18 тестов): `_module_enabled` (on/off), `poll_helpdesk_mailbox` (no-redis, not_configured, lock_held), `auto_close_resolved_tickets` (disabled/no-ids-no-commit/with-ids-commit), `send_helpdesk_digest` (not_configured/schedule_mismatch/already_sent/lock_held/happy-path), archive+cleanup обёртки. Грабли: (1) `should_send_today(now, *, ...)` — `now` позиционный, lambda должна быть `lambda now, **kw`; (2) `POLL_LOCK_KEY = "helpdesk:imap:poll_lock"` (не "poll_lock"); (3) строки 181-188 (`create_next_helpdesk_archive_partition`, asyncpg) оставлены — требуют реального PG.

### Этап 2 — Backend meetings/series_service.py 37%→**87%**
- [x] 2.1 `_recompute_canonical_rrule` (чистая) — no-delta/no-rrule no-op + delta-shift
- [x] 2.2 `create_booking_series` happy path (2 инстанса, flush, reload) — `IntegrityError`→`BookingConflict` оставлен для integration (строки 107-110)
- [x] 2.3 `_apply_series_update_to_booking` — title/desc/invited/time-change/rooms-snapshot/no-changes (5 тестов)
- [x] 2.4 `update_series` happy path — owner title-update + room_ids verify
- [x] 2.5 `_load_bookings_bulk` не-empty путь + чистые helpers (`_ensure_series_editable`, `_resolve_new_invited`, `_has_non_participant_change`, `_compute_series_deltas`)
- Грабли: (1) `InvitedUser` требует `user_id`/`full_name`/`email` (не только user_id); (2) `_load_bookings_bulk` вызывает `.scalars().unique().all()` → отдельный хелпер `_scalars_unique_all_result`; (3) conflict-ветки (`_raise_series_conflict`, IntegrityError в update) оставлены для integration.

### Этап 3 — Backend parametrize ACL
- [x] 3.1 `test_files_acl.py`: 6 функций `test_perm_gte_*` → 1 parametrize с 8 комбинациями (исходные 6 + добавлены editor/editor, manager/viewer для полноты матрицы). Чистый рефакторинг, покрытие не изменилось, число test-cases выросло на 2.
- [x] 3.2 `test_kb_acl.py`: класс `TestPermGte` 10 функций → 1 parametrize (контракт 1:1, те же 10 комбинаций).

### Этап 4 — Backend CSRF-тесты ✅
- [x] 4.1 `test_logout_exempt_from_csrf` — POST /auth/logout без Origin не 403
- [x] 4.2 `test_collabora_federation_exempt` — /ocs/v2.php/.../federation exempt
- [x] 4.3 `test_origin_only_path_skips_double_submit` — local/login без XSRF-TOKEN проходит
- [x] 4.4 `test_referer_used_when_no_origin` — Referer фолбэк проходит Origin-check
- [x] 4.5 `test_origin_scheme_mismatch_blocked` — https Origin при http base_url → 403
- [x] 4.6 `test_xsrf_cookie_auto_issued_on_safe_request` — GET выдаёт XSRF-TOKEN cookie

### Этап 5 — Frontend helpdesk-страницы (0%→покрыты) ✅
- [x] 5.1 `helpdesk-my-tickets-page.spec.ts` (7 тестов) — заголовок/кнопка, empty-state, список, goToTicket→router.push, error, create-modal, pagination-args
- [x] 5.2 `helpdesk-my-ticket-detail-page.spec.ts` (7 тестов) — load по route.params.id, форма ответа для открытого/алерт для закрытого, onReply+reload, goBack, error-handling
- [x] 5.3 `helpdesk-agent-inbox-page.spec.ts` (8 тестов) — фильтры/empty/список, goToTicket, onTake (success+reload/error), pagination/unassigned/q args, error
- [x] 5.4 `helpdesk-agent-ticket-detail-page.spec.ts` (10 тестов) — load, Take vs n-select (assignee), onTake/onStatusChange/onReopen, visibility Reopen-кнопки, onReply с visibility, goBack, error
- Грабли: (1) naive-ui `NAlert` stub должен рендерить slot через `<slot />` (не `$slots.default()` — роняет render); (2) страницы импортируют API напрямую из `../../src/api/helpdesk` (не через queries) → мокать именно этот модуль; (3) `useMessage` мокается через `naive-ui` factory (возвращает `{ error, success }`); (4) 4 страницы = 32 теста, ESLint + typecheck чистые, полная frontend-регресс 1916 passed.

### Этап 6 — Frontend разнос smoke + поведенческие assertions
- [ ] 6.1 Растаскивание `pages-smoke.spec.ts` (20 describe → отдельные файлы)
- [ ] 6.2 Конвертация shallow assertions в поведенческие (эталон `home-page.spec.ts`)
- [ ] 6.3 components-smoke-extra1-5: добить emit/click/props в формах/модалах

### Этап 7 — Frontend i18n-тесты ✅
- [x] 7.1 `i18n-config.spec.ts` (6 тестов) — mode=composition, дефолт ru, fallback ru, оба message-объекта, loadLocale no-op, общий набор доменов ru↔en
- [x] 7.2 парность ключей ru↔en — **уже покрывается** CI-скриптом `npm run i18n:check` (`scripts/check-i18n.js`), дублировать vitest-тестом бессмысленно (DRY)

### Этап 8 — docs/testing.md ✅
- [x] 8.1 Шапка: цифры тестов/покрытия обновлены (3232→3350 unit+sec, 1884→1922 vitest, 78.95%/65.19%)
- [x] 8.2 Добавить helpdesk backend-модули в Backend Unit-таблицу (7 строк: messages/notifications/tickets/worker/mailing/meetings)
- [x] 8.3 Добавить helpdesk-страницы в Frontend Unit-таблицу (5 строк: 4 страницы + i18n-config)
- [x] 8.4 Добавить CSRF-сценарии в Security-таблицу (обновлено описание test_csrf.py — 14 тестов)
- [x] 8.5 Обновить «Известные ограничения» (worker tasks: добавлен helpdesk.py 92%, обновлены %)
- [x] 8.6 Дата/итерация → «июль 2026 — итерация 16 (test-coverage audit & hardening)»

## Грабли / контекст

- **Bash пайпы в plan mode блокируются хуком** — использовать простые команды или `/usr/bin/grep` с одним аргументом без `|`.
- **cwd путается**: shell сохраняет `cd /home/snow/portal/backend` между вызовами; проверять `pwd` перед относительными путями.
- **Покрытие `app/api/*.py` 0–30% в unit-прогоне — НЕ дефект**: роуты покрываются integration-тестами через `ASGITransport`. Unit-гейт (`--cov=app`) показывают 79% за счёт сервисного слоя.
- **Frontend func-coverage 52.43% при gate 50% — на грани**: добавление тестов НЕ должно опускать эту цифру; smoke-конвертация (этап 6) её поднимет.
- **`docs/tests.generated.md` автогенерится** `scripts/list_tests.sh` — после добавления тестов регенерировать, иначе CI job `tests-generated-drift` упадёт.
- **`fake_db_allowlist`**: при написании backend unit-тестов с `authed_client_factory` — файл должен быть в allowlist, иначе CI упадёт. Но для чистых service-тестов (как `test_helpdesk_messages_tx.py`) это не нужно — там mock-сессия без HTTP.
- **i18n-ключи helpdesk**: единый объект в `src/i18n/ru.json` ~2483, 48 ключей + вложенные `statuses`/`sources`/`info`/`requesterProfile`. Для frontend-тестов страниц — вынести словарь-болванку в общий helper.
- **Helpdesk-страницы импортируют API напрямую** (`../../api/helpdesk`), НЕ через `src/queries/helpdesk` → мокать модуль `../../src/api/helpdesk`, а не `@tanstack/vue-query`.
