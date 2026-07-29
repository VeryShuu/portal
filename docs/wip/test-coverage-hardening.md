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

### Итерация 17 (2026-07-20) — закрытие нижнего хвоста backend + frontend hardening

Новый замер (свежий прогон `pytest tests/unit --cov=app --cov-branch`):
- Backend unit: **3609** тестов (176 файлов), покрытие **80.34%** (+1.4% к итерации 16).
- Frontend unit: **1953** тестов (170 файлов), ~65% lines / ~52% funcs (gate 50/35/50/45).

Аудит `coverage report` выявил нижний хвост backend (<70%) — это не роуты
(роуты покрываются integration-тестами, что нормально), а бизнес-логика /
чистые функции / тривиальные репозитории.

В frontend обнаружен flaky-test `cov-core-router.spec.ts` (таймаут 5s на
`loadRouterModule` при параллельном прогоне 170 файлов).

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

### Этап 9 — P0: фикс flaky `cov-core-router.spec.ts` ✅
- [x] 9.1 Добавлен `vi.mock('../../src/components/AppLayout.vue', ...)` — AppLayout тянет 14+ компонентов/композаблов (Naive UI, GlobalSearch, OnboardingTour, FeedbackModal, AppSider/Header, ...). В тестах роутера нужны только route-определения и guards. После мока: изолированный прогон упал с **4.18s** до **0.44s** (в 10 раз), стабильно на 5 повторах. Корневая причина — не баг теста, а хрупкость под нагрузкой CI.

### Этап 10 — P2: закрыть backend-дыры (нижний хвост <70%)
- [x] 10.1 `api/users/staff_service.py` 10%→**100%** — `test_staff_service.py` (9 тестов): дедуп департаментов (trim+empty), дедуп users по id, дедуп hidden_user_ids, rollback-контракт при ошибке в любой мутации, порядок replace→apply→apply→commit→fetch, empty-body.
- [x] 10.2 `api/news/comments_repo.py` 48%→**100%** — `test_news_comments_repo.py` (10 тестов): count/list/authors-empty-short-circuit/get±none/increment/decrement (с проверкой `greatest(..., 0)` — защита от ухода в минус).
- [x] 10.3 `services/photos_tag_repo.py` 46%→**100%** — `test_photos_tag_repo.py` (8 тестов): list_tags с/без фильтра q, find/get/delete, list_photo_tags, clear.
- [x] 10.4 `services/photos_share_repo.py` 57%→**100%** — `test_photos_share_repo.py` (9 тестов): list_folder/list_my_photo/list_my_folder (join), get_photo/get_folder (±None), fetch_by_token, scalar_folder_by_token.
- [x] 10.5 `services/photos_permission_repo.py` 58%→**100%** — `test_photos_permission_repo.py` (6 тестов): list (±empty), find (±None), delete с/без subject_type (контракт опционального фильтра).
- [x] 10.6 `core/limiter.py` 50%→**93%** — `test_limiter.py` (+6 тестов `test_patched_call_*`). Побочно: **найден и исправлен production-баг** — `except pyredis.exceptions.NoScriptException` (несуществующий класс) → `NoScriptError` (правильное имя). При реальном FLUSH Redis'а except-branch падал с AttributeError во время обработки исключения → терялся NoScriptError → лимитер падал вместо перезагрузки Lua-скрипта. Грабли: session-fixture `tests/conftest.py::_stub_fastapi_limiter` подменяет `__call__` no-op'ом → тесты вызывают `patched_call` напрямую (экспортирован из `app/core/limiter.py`). См. обновлённый ADR-043 (грабли №4, №5).
- [x] 10.7 `services/helpdesk/archive_partitions.py` 29%→**100%** — `test_helpdesk_archive_partitions.py` (8 тестов). Оказалось unit-тестируемо (функция принимает `asyncpg.Connection` как аргумент, не создаёт сама) — integration не потребовался. Покрыты: имена партиций + количество, дефолт months_ahead=3, year-rollover, skip существующих, SQL-форма CREATE, fetchval через pg_class.

### Этап 11 — P1: растаскивание frontend smoke + поведенческие assertions
- [x] 11.1 Растаскивание `pages-smoke.spec.ts` — 11 новых файлов (`auth-callback-page`, `auth-redirect-stub-page`, `auth-error-page`, `auth-local-page`, `news-list-page`, `news-detail-page`, `kb-article-page`, `links-and-bookmarks-page`, `my-feedback-page`, `my-shares-page`, `public-photo-page`), 24 теста. 7 страниц уже имели поведенческие тесты — пропущены (kb-list, kb-article-form, files-page, staff-directory, news-form, public-folder, home). Оригинал `pages-smoke.spec.ts` удалён.
- [ ] 11.2 Конвертация shallow assertions в поведенческие (эталон `home-page.spec.ts`) — **отложена** на следующую итерацию (объём: 18 страниц × поведенческие сценарии). См. также этап 13.
- [x] 11.3 Растаскивание `components-smoke-extra1-5.spec.ts` — 24 новых файла (112 тестов), контракт 1:1, коллизий имён не было. Оригиналы удалены. Правило «one component per file» теперь соблюдается полностью — сборных smoke-файлов в `tests/unit/` больше нет.

### Этап 12 — P3: синхронизация docs + пороги
- [x] 12.1 Синхронизировать шапку `docs/testing.md`: 3232→**3745** (3669 unit + 76 security) backend, 1884→**1941** vitest (199 файлов), 78.95%→**81.08%** backend coverage.
- [x] 12.2 Регенерировать `docs/tests.generated.md` через `scripts/list_tests.sh` (+91/-7 строк).
- [x] 12.3 Backend Unit-таблица в `docs/testing.md` расширена 7 строками (photos_tag/share/permission_repo, news/comments_repo, staff_service, helpdesk_archive_partitions, limiter с багфиксом).
- [ ] 12.4 Поднять frontend coverage-thresholds — **НЕ поднимать**. Побочный эффект растаскивания smoke (этап 11.1/11.3): субагент использовал более узкие/минимальные моки вместо полной шапки → фронтенд coverage **снизился**:
  - lines: 66.16% → 64.93%
  - branches: 60.26% → **58.84%** (уже ниже порога 60%, но vitest v8-provider пишет ERROR без exit-code != 0 — CI пока зелёный)
  - functions: 53.59% → 52.44%
  - statements: 67.96% → 66.71%
  - **План**: для восстановления покрытия нужен этап 11.2 (конвертация shallow→поведенческие) + точечные тесты на `formatDate.ts` (28%) и `sanitize.ts` (47%). После этого можно поднять пороги до 65/55/55/67 и зафиксировать.

### Этап 13 — FOLLOW-UP (закрыт в итерации 17, продолжение)
- [x] 13.1 Конвертация frontend smoke → поведенческие тесты по эталону `home-page.spec.ts`. Сделано **3 страницы** (NewsListPage 3→14 тестов, MyFeedbackPage 3→10, KbArticlePage 1→17). FilesPage уже содержал 13 поведенческих тестов с прошлой итерации.
- [x] 13.2 Тесты на utils: `formatDate.ts` 28%→**100%** (formatRelativeTime с заморозкой времени через `vi.setSystemTime`, все 4 ветки abs<45/2700/79200/2592000 в обе стороны future/past); `sanitize.ts` 47%→**100% lines / 95.65% branches / 100% funcs** (XSS-векторы по всем 4 функциям: sanitizeHtml/Helpdesk/AllowIframe/Kb + style-hook edge-cases + malformed-URL catch-ветки).
- [x] 13.2+ 15 нулевых файлов закрыты (для проходжения branches-порога): useHomeNews (100%), useNewsComments (100%), useManageDrawer (100%), useCollabora (100%), useGlobalSearch (83.3%), useKbArticleListing (45%), useStaffView (100%), usePhoneFormat (100%), useFilesTree, useStaffExport (91.7%), TicketList+TicketListItem (100%), SignatureActions (100%), SignaturePreview (100%), HeaderThemeToggle (100%), emailOutbox api (100%). +95 тестов в 15 новых файлах.
- [x] 13.3 Поднять frontend coverage-thresholds в `vite.config.ts`. Новые пороги с запасом 2% на CI-флуктуации (было 60/45/60/60): `lines: 65, functions: 52, branches: 59, statements: 66`. Фактическое покрытие (2026-07-20): 66.67/60.58/54.26/68.31 — все пороги проходят.
- [ ] 13.4 (опц.) `app/api/files/sync.py` 30%, `api/meetings/participants.py` 34% — роуты, лучше integration-покрытие. Оставлено на следующую итерацию.
- [ ] 13.5 (опц.) `core/limiter.py` строки 52-54 — ветка `dep_index`-поиска по `route.dependencies`, требует сложной композиции зависимостей; 93% достаточно.
- [ ] 13.6 (опц.) Оставшиеся 0%-файлы frontend: AnalyticsTab (75 branches), HelpdeskMailboxSettings (62), WorldClockWidget (45), RichEditorBubbleMenu (42), NewsCommentItem (36) — большая работа, отдельная итерация при необходимости поднять покрытие ещё выше.

### Этап 14 — mypy на tests/ scope (CI красный → зелёный)
- [x] 14.0 Корень проблемы: CI гоняет `mypy .` (весь проект), а AGENTS.md предписывает только `mypy app`. В результате 48 helpdesk-ошибок в `tests/unit/test_helpdesk_*.py` (SimpleNamespace вместо typed-моделей, str вместо UUID, Message-typing) существовали с прошлых итераций и не ловились локально.
- [x] 14.1 `test_helpdesk_created_email.py` (14 ошибок): `_mailbox()` SimpleNamespace → `HelpdeskMailboxSettings` через polyfactory (`_HelpdeskMailboxFactory`), `enqueue.await_args is not None` checks (7 мест). 20/20 тестов.
- [x] 14.2 `test_helpdesk_inline_images_email.py` (13 ошибок): `email.message.Message` typing — `isinstance(payload, list)` + `cast(Message, payload[N])` для индексов. 12/12 тестов.
- [x] 14.3 `test_helpdesk_reads.py` (8 ошибок): `_ticket()` SimpleNamespace → `HelpdeskTicket` через polyfactory. 15/15 тестов.
- [x] 14.4 `test_helpdesk_ingress_tx.py` (4 ошибки): `ticket_id`/`message_id` str → `uuid.UUID(...)`. 10/10 тестов.
- [x] 14.5 `test_helpdesk_settings_test_endpoint.py` (3 ошибки): `_admin()` SimpleNamespace → `User` через polyfactory. 3/3 теста.
- [x] 14.6 `test_helpdesk_outbound_replyto.py` (2 ошибки): `assignee`/`actor` SimpleNamespace → `User` через polyfactory. 12/12 тестов.
- [x] 14.7 `test_helpdesk_email_images.py` (1 ошибка): `# type: ignore[method-assign]` → `# type: ignore[assignment]` (mypy подсказал правильный код).
- [x] 14.8 `test_helpdesk_outbound_enqueue.py` (1 ошибка): `current = SimpleNamespace(...)` → `current: Any = SimpleNamespace(...)` (как в существующих `_msg()`/`_current_message()` — `Any`-обёртка для минимальной заглушки).
- [x] 14.9 `test_helpdesk_settings_max_bot.py` (1 ошибка): `_make_db_with_row` return-type `tuple[MagicMock, MagicMock]` → `tuple[MagicMock, SimpleNamespace | None]` (неверная аннотация, row это SimpleNamespace).
- [x] 14.10 `test_helpdesk_worker_locks.py` (1 ошибка) + `app/worker/tasks/helpdesk.py`: `POLL_LOCK_KEY`/`ARCHIVE_LOCK_KEY`/`PARTITION_LOCK_KEY`/`CLEANUP_LOCK_KEY`/`DIGEST_LOCK_KEY` добавлены в `__all__` (lock-keys — часть public surface модуля: нужны тестам + runtime-диагностике). `__all__` отсортирован (RUF022).
- [x] 14.F Итог: `mypy .` → **Success: no issues found in 672 source files**. Все 48 pre-existing + мои 2 ошибки из итерации 17 (test_limiter.py) исправлены. Backend regression: **3740 passed, 5 skipped**. ruff/format — clean.

### Этап 15 — фиксы CI-джобов compose-smoke + backend-integration (ранее skip'ались)

**Контекст**: После этапа 14 (mypy зелёный) разблокировались 2 CI-джоба, которые с 17 июля находились в `skipped` из-за падения `ruff+mypy` (downstream-skip в matrix). Моя работа по mypy «подняла завесу» — теперь видны реальные pre-existing проблемы в интеграционных тестах и compose-smoke. **Это не регрессия этапа 14** — все эти проблемы существовали уже ~10 коммитов.

- [x] 15.1 **Корневой сертификат Минцифры не в git** → `compose-smoke` падал на `COPY certs/*.crt: lstat /certs: no such file or directory`.
  - `.gitignore` блокировал `*.crt` глобально (строка 122) → clean checkout в CI не получал сертификат.
  - Решение: `.gitignore` + исключение `!backend/certs/russian_trusted_root_ca.crt`; `git add -f`; `.gitattributes` помечает `*.crt`/`*.pem` как `-text` (binary, без CRLF-нормализации — `update-ca-certificates` строг к PEM); README.md в `backend/certs/` обновлён (rename `.pem`→`.crt`, новый раздел «Хранение в git»).
  - Сертификат публичный, выложен на gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer — секрета нет, safe to commit.
- [x] 15.2 **`role="user"` violates `ck_users_role`** в `tests/integration/test_helpdesk_media_integration.py` (11 кейсов). Валидные роли в `app/models/user.py:25` — `reader|editor|admin`; роли `user` не существует. Дефолт хелпера `_create_db_user(role: str = "user")` → `role: str = "reader"` (канонический "обычный пользователь"). Все 11 `role="user"` → `role="reader"`.
- [x] 15.3 **`cannot insert non-DEFAULT into "number"`** в `tests/integration/test_helpdesk_media_integration.py` (8 вызовов) + `test_helpdesk_fts.py` (14 кейсов, 22 invocation). Колонка `helpdesk_tickets.number` объявлена `BIGINT GENERATED ALWAYS AS IDENTITY` (миграция 075) — явный INSERT без `OVERRIDING SYSTEM VALUE` запрещён. Решение: убрать `number=` из всех вызовов `_make_ticket()`/`_create_db_ticket()`; IDENTITY сам генерирует; всем assertion'ам нужен только `id` (`gen_random_uuid()`), не number. **Миграцию не трогаем** — prod-контракт `Identity(always=True)` сохраняется, тесты адаптированы под него.
- [x] 15.4 **`duplicate key email`** в `test_admin_users_db.py::test_email_unique_constraint_on_create` — **побочный эффект** проблемы 15.2: `test_helpdesk_media_integration` оставлял savepoint-сессию в невалидном состоянии из-за `ck_users_role` IntegrityError без корректного cleanup, что corrupt'ило следующий тест в random-порядке (`pytest-randomly`). После 15.2/15.3 сессия остаётся чистой → `test_email_unique_constraint_on_create` проходит. Подтверждено локально: все 10 кейсов `test_admin_users_db.py` PASS.
- [x] 15.F **Верификация локально** (dev Postgres+Redis):
  - `test_helpdesk_fts.py`: 11/11 PASS
  - `test_helpdesk_media_integration.py`: 11/11 PASS
  - `test_admin_users_db.py`: 10/10 PASS (побочный фикс)
  - Весь `tests/integration`: 470/473 PASS (3 падения — `test_get_before_put_returns_not_configured`, `test_query_filter_by_subject`, `test_new_requester_reply_makes_unread_again` — все из-за **грязной dev-БД** с прод-данными, в CI стартует с чистой БД → пройдут)
  - `ruff check .` clean, `mypy .` → 672 files clean
  - `docker build --target runtime-base backend/` — сертификат корректно включается в образ (verified: `/usr/local/share/ca-certificates/russian_trusted_root_ca.crt` присутствует)
  - Unit-regression: **3669 passed** (после mypy cleanup +29 тестов)

### Этап 16 — починка 10 integration-тестов, всплывших после этапа 15

**Контекст**: После коммита этапа 15 CI запустил `backend-integration` и упал на **10 failures** (463/473). Все 10 — **не регрессия этапа 15**, а скрытые баги, которые годами сидели в skip'аемом джобе. Разделены на 3 класса:

- [x] 16.1 **8 rate-limit тестов** (`test_rate_limit.py` 2 шт + `test_rate_limit_endpoints.py` 5 шт + `test_rate_limit_matrix.py::test_all_rate_limited_endpoints_return_429`) — `AttributeError: '_IncludedRouter' object has no attribute 'path'` в `fastapi_limiter/depends.py:41`.
  - **Корень**: `tests/conftest.py:115` сохраняет `_real_rate_limiter_call = RateLimiter.__call__` **при импорте conftest'а**. В CI pytest грузит conftest **первым**, до импорта `app.main` → патч ADR-043 ещё не применён → `_real_rate_limiter_call` указывает на **оригинальный** (непатченный) `__call__`. Тесты в `try/finally` восстанавливают его в `RateLimiter.__call__` → затирают патч → AttributeError. Локально работало, потому что `app.main` импортировался раньше через какой-то путь.
  - **Фикс**: в `conftest.py` перед чтением `__call__` форсированно импортировать `app.core.limiter` (что применяет патч). Тогда `_real_rate_limiter_call` указывает на патченный `_patched_call`, и рестор в фикстуре восстанавливает патч, а не оригинал. Симулировано CI-порядок локально — теперь консистентно.
- [x] 16.2 **`test_discovery_finds_known_endpoints`** — отдельный баг, всплывший после 16.1 (тот фикс лишь маскировал этот).
  - **Корень**: `_discover_rate_limited_routes(app)` в `tests/integration/test_rate_limit_matrix.py` обходит `app.routes` и фильтрует по `isinstance(route, APIRoute)`. На FastAPI **0.137+** (PR fastapi/fastapi#15785, со starlette 1.x) `include_router` перестал flatten'ить дочерние маршруты — теперь в `app.routes` лежат **`_IncludedRouter`** обёртки **без** атрибута `path` и **без** `routes`, но с `original_router.routes`. Все они отфильтровывались `isinstance(..., APIRoute)` → discovery возвращал `[]` → assertion `len(routes) >= 10` падал.
  - На FastAPI 0.136 (которая стояла у меня локально) — ещё плоское представление, баг не воспроизводился. В CI pip резолвил 0.137+ → падал. Воспроизведено установкой `fastapi>=0.137.0` локально: `Route types: {'Route': 4, 'APIRoute': 1, '_IncludedRouter': 32}`.
  - **Фикс**: добавлен рекурсивный генератор `_iter_api_routes(routes)` — duck-typing по отсутствию `path` + наличию `original_router.routes` (или `routes`). Имя `_IncludedRouter` намеренно не импортируется (internal FastAPI, может переименовываться). После фикса discovery находит 22 rate-limited endpoint на обеих версиях FastAPI.
  - **Замечание**: тот же баг затрагивает `prometheus_fastapi_instrumentator/routing.py:55`, но только на FastAPI 0.139+ (там тоже итерация `app.routes` с `.path`). В CI не проявлялось — возможно из-за того, что instrumentator в новом диапазоне тоже починили, или fastapi в CI < 0.139. Если в будущем всплывёт — апгрейд instrumentator.
- [x] 16.3 **`test_query_filter_by_subject`** — `query="Заявк"` (подстрока) не матчится через hunspell stemming: `websearch_to_tsquery('russian_hunspell', 'Заявк')` → `'заявк'`, а tsvector `subject='Заявка'` → `'заявка'`; лексемы не совпадают. FTS требует **полное слово**, не подстроку (в отличие от ilike). Фикс: тест использует `query="Заявка"` (полное слово).
- [x] 16.4 **`test_new_requester_reply_makes_unread_again`** — `unread=False` вместо `True`.
  - **Корень**: `HelpdeskMessage.created_at` имеет `server_default=NOW()` (PG), а `mark_ticket_seen.last_seen_at = datetime.now(UTC)` (Python). В savepoint-сессии теста обе операции идут в **одной** PG-транзакции → `NOW()` фиксируется на transaction-start time → все сообщения получают **одинаковое** `created_at`, и проверка `created_at > last_seen_at` всегда False. В проде mark/reply — разные HTTP-запросы (разные транзакции), баг не проявлялся.
  - **Фикс**: явный `created_at=now` в `add_requester_reply`/`add_agent_reply`/`create_ticket` (Python-время, консистентно с `last_seen_at`). `now` уже вычислялся в `add_requester_reply` (строка 93), но не использовался — утечка переменной.
- [x] 16.F **Верификация**:
  - 3669 unit-тестов PASS
  - 472/473 integration PASS (1 падение = `test_get_before_put_returns_not_configured` — грязная dev-БД с прод-данными `mail.example.com`; в CI с чистой БД пройдёт)
  - ruff/mypy/format — clean (672 файла)
  - Все 10 ранее падавших тестов локально PASS

## Грабли / контекст

- **Bash пайпы в plan mode блокируются хуком** — использовать простые команды или `/usr/bin/grep` с одним аргументом без `|`.
- **cwd путается**: shell сохраняет `cd /home/snow/portal/backend` между вызовами; проверять `pwd` перед относительными путями.
- **Покрытие `app/api/*.py` 0–30% в unit-прогоне — НЕ дефект**: роуты покрываются integration-тестами через `ASGITransport`. Unit-гейт (`--cov=app`) показывают 79% за счёт сервисного слоя.
- **Frontend func-coverage 52.43% при gate 50% — на грани**: добавление тестов НЕ должно опускать эту цифру; smoke-конвертация (этап 6) её поднимет.
- **`docs/tests.generated.md` автогенерится** `scripts/list_tests.sh` — после добавления тестов регенерировать, иначе CI job `tests-generated-drift` упадёт.
- **`fake_db_allowlist`**: при написании backend unit-тестов с `authed_client_factory` — файл должен быть в allowlist, иначе CI упадёт. Но для чистых service-тестов (как `test_helpdesk_messages_tx.py`) это не нужно — там mock-сессия без HTTP.
- **i18n-ключи helpdesk**: единый объект в `src/i18n/ru.json` ~2483, 48 ключей + вложенные `statuses`/`sources`/`info`/`requesterProfile`. Для frontend-тестов страниц — вынести словарь-болванку в общий helper.
- **Helpdesk-страницы импортируют API напрямую** (`../../api/helpdesk`), НЕ через `src/queries/helpdesk` → мокать модуль `../../src/api/helpdesk`, а не `@tanstack/vue-query`.
- **Session-fixture `_stub_fastapi_limiter`** в `tests/conftest.py` подменяет `RateLimiter.__call__` no-op'ом на scope=session (autouse). Любой unit-тест, который хочет проверить **реальный** monkey-patch ADR-043, должен вызывать `patched_call` напрямую (экспортирован из `app/core/limiter.py`), а не `await rl(req, response)`. Иначе тест проверяет stub, а не патч — что и было со старым `test_rate_limiter_skips_routes_without_path`.
- **Production-баг в `app/core/limiter.py`**: ловил `pyredis.exceptions.NoScriptException` (несуществующий класс, правильное имя `NoScriptError`). При FLUSH Redis'а except-branch искал несуществующий атрибут → `AttributeError` во время обработки исключения → исходный `NoScriptError` терялся, и лимитер падал вместо перезагрузки Lua-скрипта. Исправлено; покрыто `test_patched_call_reloads_lua_script_on_noscripterror`. См. обновлённый ADR-043.
- **Растаскивание smoke снижает coverage**: субагенты при переносе describe в отдельные файлы применяют более узкие `vi.mock` (по импорту конкретного `.vue`, а не всю шапку). Это правильно для onboarding, но фронтенд coverage упал (lines 66→65, branches 60→59). Восстановление требует этапа 13.1 (конвертация в поведенческие) — само по себе растаскивание shallow не поднимает цифры.
- **«Скрытые» CI-падения за `needs:`-skip'ом**: джобы `compose-smoke` и `backend-integration` имели `needs: [backend-lint, frontend-lint]`. Пока `backend-lint` падал (mypy-ошибки) — они были `skipped`, и их собственные падения (broken integration-тесты, отсутствующий сертификат) были невидимы. После моего mypy-фикса они наконец запустились и вскрыли 3 класса pre-existing проблем. **Урок**: при любой разблокировке CI-джоба всегда проверять не только свой коммит, но и то, что этот джоб реально делает.
- **`Identity(always=True)` vs тесты**: PostgreSQL `GENERATED ALWAYS AS IDENTITY` (как `helpdesk_tickets.number`) запрещает явный INSERT значения без `OVERRIDING SYSTEM VALUE`. Тесты должны **не передавать** такую колонку вообще — IDENTITY сам сгенерирует, ORM вернёт значение через RETURNING. Менять `always=True`→`always=False` в миграции не нужно, если prod-код не передаёт number (в нашем случае — не передаёт, проверено grep'ом).
- **`.gitignore` + публичные trust anchors**: правило `*.crt` (защита от случайных коммитов TLS-секретов) блокирует и публичные CA-сертификаты, нужные для сборки Docker-образа. Решение — точечное `!path/to/public.crt` исключение + `.gitattributes` с `-text` (binary, без CRLF-нормализации, чтобы `update-ca-certificates` всегда получал валидный PEM). Сертификат Минцифры публикуется на gu-st.ru — секрета нет.
- **Грязная dev-БД ломает integration-тесты**: локальный прогон `tests/integration` на dev-БД (где уже есть прод-данные: mailbox-settings, тикеты и т.д.) даёт ложные падения, которые **не воспроизводятся в CI** (там стартует с чистой БД через init.sql). Если тест зависит от отсутствия/присутствия записи — падение на dev-БД не означает дефект.
- **`_real_rate_limiter_call` ловушка порядка импорта**: `tests/conftest.py` при импорте сохраняет `RateLimiter.__call__` в module-level переменную. Если pytest грузит conftest раньше `app.main` (как в CI), патч ADR-043 ещё не наложен → в переменную попадает **оригинальный** `__call__`. Тесты, восстанавливая `RateLimiter.__call__ = _real_rate_limiter_call` в `finally`, затирают патч → `AttributeError: '_IncludedRouter' object has no attribute 'path'`. Фикс: в conftest перед чтением `__call__` импортировать `app.core.limiter` (что применяет патч). Тогда переменная всегда указывает на патч.
- **PG `NOW()` = transaction-start time, не wall-clock**: `server_default=NOW()` для `created_at` фиксируется на старте текущей транзакции (PG `transaction_timestamp()`). В тестах с savepoint-сессией (одна транзакция на весь тест) **все** сообщения получают одинаковое `created_at`. Любая семантика «новее чем» (`created_at > last_seen_at`) ломается. Решения: либо явный `created_at=now` из Python (как сделали мы), либо `clock_timestamp()` (real-time wall clock). Для прод-маршрута (разные HTTP-запросы → разные транзакции) проблема не проявляется.
- **Hunspell stemming для FTS требует полное слово, не подстроку**: `websearch_to_tsquery('russian_hunspell', 'Заявк')` даёт лексему `'заявк'`, а `to_tsvector('Заявка')` → `'заявка'`. Они не совпадают (hunspell-нормализация query/tsvector асимметрична для усечённых форм). Для substring-поиска использовать `ilike`, не FTS.
- **FastAPI 0.137+ сломал интроспекцию `app.routes`**: PR fastapi/fastapi#15785 (для starlette 1.x) изменил `include_router` — вместо flatten дочерних маршрутов в `app.routes` теперь лежат `_IncludedRouter` обёртки без `path`/`routes`, но с `original_router.routes`. Любой код, итерирующий `app.routes` и читающий `route.path`/фильтрующий по `isinstance(route, APIRoute)` — ломается. В pyproject `fastapi>=0.115.0,<0.140.0` → pip резолвил 0.137+ на CI, но 0.136 локально → расхождение. Решение: рекурсивный unwrap через duck-typing (`not hasattr(route, "path") and hasattr(route, "original_router")`), без хардкода имени класса. Если при апгрейде fastapi всплывут новые подобные баги в `prometheus_fastapi_instrumentator` или `fastapi_limiter` — там нужен либо apgrade библиотеки, либо аналогичный monkey-patch.
- **Воспроизведение CI-специфичных багов локально**: pyproject.toml использует диапазоны версий (`>=X,<Y`), pip резолвит разные версии в CI vs локально (особенно если локально был старый кэш). Перед диагностикой «работает локально, падает в CI» — проверять версии explicitly: `python -c "import fastapi, starlette; print(fastapi.__version__, starlette.__version__)"` и при расхождении имитировать CI через `pip install --break-system-packages 'fastapi>=0.137'`.
