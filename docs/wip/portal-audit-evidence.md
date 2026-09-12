# Portal audit — реестр доказательств

> **Назначение:** воспроизводимый журнал источников аудита. Записывает, что и на
> каком ref действительно проверено; не заменяет реестр находок.
> **Связанные документы:** `portal-modular-audit.md`,
> `portal-audit-findings.md`.
> **Последняя актуализация:** 2026-09-04, статическая сверка
> `origin/main@a872f880` и live Forgejo; исходные записи 2026-09-01/02 сохранены
> как исторические срезы, а не переписаны задним числом.

## Правила

- Секреты, токены и содержимое `.env` в журнал не записываются.
- `static`, `local`, `remote CI`, `staging` и `prod` — разные уровни
  доказательств.
- Зелёный aggregate не считается доказательством без job counts и причин skips.
- Недоступный runtime записывается как ограничение, а не как успешная проверка.

## E-0001 — Git baseline

- **Дата:** 2026-09-01.
- **Метод:** `git status`, `git log`, `git rev-list`, `git diff`,
  `git ls-remote`.
- **Baseline:** `origin/main@2e662df32ce1523b2bb469516ead3223be95e442`
  (`v1.12.0`).
- **Checkout:** `fix/meetings-rsvp-digest-timezone@96fe4c2cfc7dddb585cac3db61c214cd3a4ee36c`.
- **Разница:** один commit; изменены только RSVP digest, его unit-тесты и
  `docs/tests.generated.md`.
- **Рабочее дерево до журналов аудита:** untracked
  `docs/wip/portal-modular-audit.md`; пользовательский код чист.
- **Вывод:** системный аудит ведётся по baseline `origin/main`; Meetings commit
  не используется как доказательство состояния main.

## E-0002 — Codebase-memory

- **Дата:** 2026-09-01.
- **Artifact:** `.codebase-memory/artifact.json` указывает на baseline commit,
  `indexed_at=2026-09-01T13:31:22Z`, но metadata содержит `nodes=0`, `edges=0`.
- **Live MCP:** `get_graph_schema(project=portal)` отвечает непустой схемой;
  `query_graph` возвращает Branch `main@71dab398037afbed9019e68f517245ea6c464cc9`.
- **Git comparison:** live Branch node на 691 commit позади baseline.
- **Вывод:** artifact и live graph расходятся; граф нельзя считать актуальным
  источником impact/callers/callees до переиндексации.
- **Ограничение:** переиндексация не выполнялась, поскольку текущая фаза — только
  аудит без изменения артефактов.

## E-0003 — Статический inventory

- **Дата:** 2026-09-01.
- **Источники:** `docs/README.md`, `backend/app/api/__init__.py`,
  `backend/app/worker/main.py`, `frontend/src/router.ts`,
  `frontend/src/learn/router.ts`, `backend/app/core/modules_config.py`.
- **Результат:** 37 backend routers; отдельный learner router; 9 runtime-gated
  модулей; 39 instrumented worker functions плюс metrics/heartbeat и 42 cron
  declarations.
- **Тестовый inventory:** 330 backend test files; 272 Vitest spec files;
  13 Playwright `.spec.ts` плюс `auth.setup.ts`; 2 screenshot-service test files.
- **Ограничение:** количества получены статически/из committed inventory;
  локальная полная коллекция тестов в этой фазе не запускалась.

## E-0004 — OpenAPI inventory

- **Дата:** 2026-09-01.
- **Источник:** committed `openapi.json`, подсчёт HTTP operation keys.
- **Результат:** 383 paths / 480 operations.
- **Сравнение:** `AGENTS.md` заявляет 319 paths / 401 operations.

## E-0005 — Live branch protection

- **Дата:** 2026-09-01.
- **Источник:** Forgejo REST
  `GET /api/v1/repos/mage/portal/branch_protections/main`; токен применялся
  только в заголовке и не выводился.
- **Результат:** `enable_status_check=true`, `apply_to_admins=true`,
  `block_on_outdated_branch=true`, `required_approvals=0`, 19 required contexts.
- **Сравнение:** workflow содержит jobs
  `screenshot-service / pytest unit` и `monitoring / config validation`, но их
  pull-request contexts отсутствуют в required list. `AGENTS.md` заявляет 21
  обязательный check и включает оба.

## E-0006 — Remote CI baseline main

- **Дата:** 2026-09-01.
- **Commit:** `2e662df32ce1523b2bb469516ead3223be95e442`.
- **CI API run 1205:** 27 success / 3 skipped. Skips: PR-only diff coverage,
  PR summary comment и deploy bundle.
- **Security API run 1206:** 2 success / 3 skipped. Skips: weekly gitleaks и два
  dormant CodeQL jobs.
- **Вывод:** наблюдавшиеся main runs завершились успешно; это исторический
  remote-CI baseline, не доказательство staging/prod runtime.

## E-0007 — Current Meetings PR remote CI

- **Дата:** 2026-09-01.
- **PR:** #177, commit `96fe4c2cfc7dddb585cac3db61c214cd3a4ee36c`.
- **Первый CI attempt (API run 1209):** не зелёный. Frontend lint/build и quality
  jobs достигли 15-минутного runner deadline; лог содержит
  `context deadline exceeded`, а не code assertion.
- **Security API run 1210:** 2 success / 3 expected skips.
- **Успевшие проверки:** backend unit/security 5036 passed / 10 skipped;
  integration 693 passed / 2 skipped; Vitest 2717 passed; screenshot 36 passed;
  Playwright 79 passed / 1 flaky / 0 skipped; backend merged coverage 85%;
  backend diff coverage 100% на 10 строках.
- **Последнее наблюдение:** replacement runs 1211/1212 ещё не были завершены.
- **Вывод:** PR #177 нельзя называть remote-green; runner timeout пока является
  единичным наблюдением, а не подтверждённым дефектом кода.

## E-0008 — Старый audit backlog

- **Дата:** 2026-09-01.
- **Источник:** `../../audit.md` и актуальный код.
- **Результат:** header заявляет 9 открытых задач, TL;DR перечисляет 6;
  snapshot относится к `da8d5f2` и количественно устарел.
- **Revalidation:** M1 остаётся только для News, KB-часть stale; M5 требует
  runtime `EXPLAIN/pg_stat` и остаётся `UNVERIFIED`; M7 structural duplication
  подтверждена; M11 — подтверждённый pattern, но согласованный deferred risk;
  M17 подтверждён как отсутствие key rotation, KDF-формулировка не доказана;
  L7 статически подтверждён, runtime exploit chain не проверен; M13 снова имеет
  ручные API-типы в новых клиентах.

## E-0009 — Runtime ограничения текущего прохода

- Production PostgreSQL grants и наличие `LEARNING_DB_PASSWORD` не проверялись.
- Rendered production Nginx и реальный learn-host не проверялись.
- Live Redis/session/cache state не изменялся и не инспектировался.
- Monitoring overlay, targets, series, rules, dashboards и доставка алертов в
  этом проходе не проверялись.
- Ни один локальный build/test не запускался; использованы static evidence и
  read-only Forgejo API/job logs.

## E-0010 — Audit queue poison-record path

- **Дата:** 2026-09-01.
- **Источник:** `backend/app/worker/tasks/audit.py` и существующие unit tests.
- **Результат:** `audit_processing` имеет recovery-first семантику, но весь list
  декодируется до записи в PostgreSQL. Любая malformed JSON-запись вызывает
  исключение до удаления processing-list и поэтому повторно ломает каждый flush.
- **Test gap:** существующий exception test проверяет только release lock; смеси
  malformed + valid и quarantine/recovery test нет.
- **Ограничение:** Redis/runtime не мутировались; наличие poison record в живой
  очереди не утверждается.

## E-0011 — Monitoring defaults и статическая alert-chain

- **Дата:** 2026-09-01.
- **Источники:** `docs/monitoring.md`, `monitoring/README.md`, monitoring compose,
  Prometheus/Loki/Alertmanager configs, rules, `setup.sh` и CI workflow.
- **Rule chain:** Prometheus монтирует portal/recording rules и направляет алерты
  в Alertmanager; Loki ruler использует tenant-dir `fake` и тот же Alertmanager;
  setup smoke проверяет targets, оба набора rules и свежую Loki ingestion.
- **Validation boundary:** CI синтаксически проверяет Prometheus, Alertmanager,
  Loki и Alloy, но monitoring job не входит в branch protection (PA-001).
- **Security result:** Grafana defaults одновременно дают network bind
  `0.0.0.0:3001` и fresh-volume credentials `admin/admin`; production preflight
  не требует override. Prometheus, Alertmanager, Loki и Alloy по умолчанию
  публикуются только на loopback.
- **Ограничение:** overlay не запускался, live series/rule states и реальная
  доставка email/Matrix не проверялись.

## E-0012 — Middleware order и idempotency upload path

- **Дата:** 2026-09-01.
- **Источники:** middleware registration, idempotency ASGI middleware, Files
  upload route, system settings schema и существующие tests.
- **Порядок:** idempotency является внутренним middleware, но всё равно выполняет
  полное чтение body до route dependencies (auth, ACL, rate-limit).
- **Результат:** generic prefix `/api/v1/files/folders/` захватывает multipart
  upload; `_read_body` собирает весь body в памяти. Лимит загрузки — 100 МБ по
  умолчанию, schema допускает 1024 МБ. Route уже содержит отдельный user-scoped
  idempotency cache.
- **Test gap:** нет большого multipart/streaming counterexample на уровне
  middleware; текущие tests используют малые JSON requests.
- **Ограничение:** нагрузочный/oversize запрос не отправлялся, RSS процесса не
  измерялся; finding основан на детерминированной ASGI семантике.

## E-0013 — ARQ registry против job instrumentation

- **Дата:** 2026-09-01.
- **Версия:** локальное CI-окружение содержит ARQ 0.28.0; dependency declaration
  разрешает `arq>=0.26.0`.
- **Метод:** статическая сверка `WorkerSettings`, исходников установленного ARQ
  (`cron`, `Worker.__init__`, `Worker.run_cron`) и writers Redis job metrics.
- **Результат:** 42 cron records enqueue'ятся как `cron:<FQN>` и исполняют raw
  coroutine. 34 одноимённых tasks также имеют plain-name wrapper, но это другая
  registry entry; 8 cron functions wrapper не имеют вовсе. Scheduled executions
  не вызывают `track_arq_job`.
- **Test gap:** registry snapshots подтверждают наличие и расписание, unit tests
  проверяют декоратор отдельно; end-to-end cron → metrics contract отсутствует.
- **Ограничение:** живые Redis hashes/Prometheus series не инспектировались.

## E-0014 — Runtime settings apply matrix

- **Дата:** 2026-09-01.
- **Источники:** ADR-037/API contract, MonitoringTab, settings update handler,
  middleware construction, backend/worker startup и request logging.
- **Hot apply подтверждён статически:** backend `log_level`, timezone,
  Nextcloud client invalidation; `log_slow_request_ms` и metrics token читаются
  динамически.
- **Startup-only подтверждён статически:** наличие `/metrics`, JSON renderer,
  `WorkerSettings.max_jobs`; worker log level не получает backend-process update.
- **Contract result:** UI/API сохраняют обе группы одинаково и документация не
  маркирует startup-only/restart-required поля.
- **Ограничение:** системные настройки не изменялись; межпроцессный runtime test
  не выполнялся.

## E-0015 — Compose readiness semantics

- **Дата:** 2026-09-01.
- **Источники:** compose, Nginx templates, ADR-015 и официальная документация
  Docker по restart policies/startup order.
- **Результат:** backend `/ready` управляет Docker health status; restart policy
  требует остановки контейнера, а `depends_on: service_healthy` применяется при
  startup. Runtime health watcher/LB eviction в topology отсутствует.
- **Ограничение:** dependency failure не инъектировался, контейнеры не
  перезапускались; проверена статическая deployment semantics.

## E-0016 — Gate 1 platform closure

- **Дата:** 2026-09-01.
- **Scope:** identity/HTTP security, data/runtime infrastructure, contracts,
  frontend transport/router, ingress/deploy/CI и observability.
- **Результат:** 23 confirmed findings: 5 P1, 16 P2, 2 P3; дополнительно два
  `UNVERIFIED` и один `ACCEPTED RISK`. Код, config, DB и runtime не менялись.
- **Ключевые ограничения:** production grants/secrets, live Redis/DB state,
  browser/responsive/a11y, Prometheus/Loki series, Alertmanager delivery и
  failure injection не проверялись.
- **Gate decision:** platform static gate закрыт; зависимые этапы разрешены
  только как read-only аудит с явной ссылкой на нерешённые PA-001–PA-004 и
  PA-020 там, где они ограничивают доказательство.

## E-0017 — LMS contract baseline

- **Дата:** 2026-09-01.
- **Baseline:** `origin/main@2e662df32ce1523b2bb469516ead3223be95e442`;
  текущий Meetings commit исключён из LMS-выводов.
- **Документы:** `docs/README.md` не содержит отдельного стабильного LMS-дока;
  обязательный контекст находится в `docs/wip/learning.md` и
  `docs/wip/learning-course-layout.md`, оба прочитаны полностью до code review.
- **Contract result:** основной WIP объявляет код этапа 1 полностью завершённым и
  оставляет только production actions, но актуальный static audit уже
  подтверждает platform/LMS blockers PA-002–PA-004 и PA-024–PA-025.
- **Ограничение:** журнал WIP содержит исторические состояния множества веток;
  записи сами по себе не принимались за доказательство текущего кода.

## E-0018 — LMS recovery и public URL chain

- **Дата:** 2026-09-01.
- **Путь:** forgot API → `request_password_reset` → outbox email builder → URL →
  learn router → reset page → `/auth/learning/reset`.
- **Результат:** email создаёт `/reset-password`, router обслуживает `/reset`;
  сквозной journey разорван (PA-024). Существующие backend/frontend tests
  проверяют две несовместимые половины отдельно.
- **TLS result:** `learning_base_url` допускает явный HTTP, значение напрямую
  входит в reset URL, а renderer одновременно создаёт HTTPS contour и HTTP
  redirect (PA-025).
- **Ограничение:** email/outbox/Redis/DB не мутировались, письмо не отправлялось;
  реальный DNS/TLS и browser HSTS state не проверялись.

## E-0019 — Baseline LMS CI/browser evidence

- **Дата:** 2026-09-01.
- **Forgejo:** commit status baseline — success, 30 contexts. Run 1205 E2E job
  20356: 80 passed, 0 skipped, 0 flaky/retried; Vitest job 20343: 272 files,
  2717 passed; integration job 20345: 693 passed, 2 expected nightly skips.
- **Topology:** learn project использует production Vite build + direct Vite
  preview proxy. Реальный Nginx learn server, Host/TLS, public allowlist и SPA
  fallback в этом job не участвуют; admin setup идёт через learn-origin.
- **Local runtime:** существующий dev stack healthy, но `learning_base_url=null`;
  rendered `learn_server.conf` корректно disabled, поэтому честное live browser
  evidence public contour получить нельзя.
- **Tool limitation:** обязательный `agent-browser` workflow не запущен — CLI
  отсутствует в среде. Подмена прямым Vite URL не использовалась как production
  доказательство.
- **Вывод:** remote green подтверждает suites/build, но не закрывает PA-003,
  PA-024, PA-025 и приводит к отдельной PA-026.

## E-0020 — LMS restricted-role runtime probe

- **Дата:** 2026-09-01.
- **Контур:** уже поднятый local dev stack; только read-only SQL.
- **Результат:** роль `learning_app` существует и имеет RW на все 12 текущих
  `learning_*` tables, только INSERT на `email_outbox`; лишних table grants в
  `information_schema.role_table_grants` не обнаружено.
- **Application path:** `LEARNING_DB_PASSWORD` внутри backend отсутствует,
  `LearningSessionLocal` фактически подключается как основной `portal` user.
  Это ожидаемо разрешено для dev, но живым counterexample подтверждает механизм
  fail-open из PA-002; production состояние по этому dev probe не выводится.
- **Transaction:** единственный `select current_user`, session завершилась
  ROLLBACK; данные/роль/grants не менялись, пароль не печатался.
- **Дополнительная гипотеза:** конкурентный submit attempt выделен как PA-U04;
  DB-mutation для воспроизведения в текущем read-only этапе не выполнялась.

## E-0021 — Branch protection: PA-001 закрыт (live API)

- **Дата:** 2026-09-01 (изменение), 2026-09-02 (верификация).
- **Метод:** Forgejo REST `GET/PATCH /repos/mage/portal/branch_protections/main`;
  токен только в заголовке, не логировался.
- **Результат:** 21/21 required contexts — добавлены
  `CI / screenshot-service / pytest unit (pull_request)` и
  `CI / monitoring / config validation (pull_request)`; обратное чтение
  подтвердило. Механизм enforcement наблюдался живьём: попытка мёржа через API
  при красном контексте отвечала `405 Not all required status checks successful`.
- **Ограничение:** отдельная негативная проверка именно двух новых контекстов
  (failing screenshot-unit / monitoring-validation блокирует мёрж) не
  выполнялась — механика идентична остальным контекстам.
- **Статус PA-001:** `CLOSED`.

## E-0022 — Волна 1 remediation: merge-train #189

- **Дата:** 2026-09-02.
- **Метод:** локальные merge'ы веток #179–#187 в порядке создания
  (`chore/audit-wave1-integration`), локальные гейты на объединённом дереве,
  полный Forgejo CI, merge через API (HTTP 200), закрытие #179–#187.
- **Локальные гейты:** полные unit+security 5068 passed / exit 0 (точная CI-
  команда, `COVERAGE_FILE=.coverage.unit -n auto`); coverage 77.99% на
  `--cov-report=xml`; `ci_lint.sh` (ruff+mypy) ✅; drift ✅; FE
  lint/typecheck/vitest ✅; bats 11/11 ✅; `nginx -t` rendered learn conf ✅;
  diff-coverage отдельных PR 92–100%.
- **Remote CI:** финальный прогон ветки `a117d7e` — 22 success statuses /
  0 pending / 0 failure; на тот момент branch protection требовал 21 context,
  22-й (`docs / db_schema drift check`) стал обязательным только в волне 2.
  Затем выполнен merge. CI прошлого коммита
  вскрывал реальные дефекты (см. E-0023) — устранены в тех же коммитах.
- **Конфликты train:** bats-тесты PA-025+PA-003 — оставлены оба;
  `tests.generated.md` — финальный реген; аудит-доки #187 vs #178 — версии
  #187 (надмножество со статусами).
- **Ограничение:** runtime-приёмка оператора (чек-лист в modular-audit) не
  выполнена — находки волны в статусе `REMOTE_VERIFIED`, не `CLOSED`.

## E-0023 — Инцидент CI-раннера 2026-09-02 и инфра-ответ

- **Симптомы (в хронологии):** 15-минутные `context deadline exceeded` на
  npm-install джобах; npm audit `400 Invalid package tree` (закрываемый /quick
  endpoint; после `npm@11` — `read ETIMEDOUT` до bulk-endpoint); e2e
  `initdb: No space left on device`; unit «5068 passed → exit 1 → No data to
  combine»; bats `could not read Username for 'https://github.com'`.
- **Диагностика:** точная CI-команда юнита локально зелёная на том же дереве;
  изолирующий эксперимент (docs-ветка без union-изменений) показал: unit ✅ /
  bats ❌ у всех → юнит-фейл специфичен для дерева; в его логе — настоящий
  корень: **гейт skip-бюджета** (`_DAILY_SKIP_CAPS`: 12 > 10) валит прогон
  после всех тестов, «No data to combine» — каскад.
- **Лечение оператором:** `docker system prune` на машине раннера (сняло
  initdb/e2e-часть).
- **Фиксы в репо (в #189 и #188):**
  - `_DAILY_SKIP_CAPS` unit 10→12 (осознанно, 2 новых nightly render-теста);
  - bats-core v1.14.0 вендорен (`tests/setup/vendor/bats-core`, рантайм-only —
    dev-Dockerfile'ы вендора валили trivy DS-0002);
  - #188: `timeout-minutes` 15→25 (build/quality/types-drift), 20→30 (e2e);
    `npm@11` перед audit; ретраи audit на ETIMEDOUT/Bad Request (гейт HIGH+
    сохранён).

## E-0024 — Состояние PR-очереди после волны 1

- **Дата:** 2026-09-02.
- **Метод:** Forgejo REST (pulls/issues/actions), локальный git.
- **Результат:** смёржены #178 (журналы аудита), #188 (инфра), #189 (волна 1);
  #179–#187 закрыты как реализованные (контент в main через #189); открытых PR
  нет. main = `bb13d8a`.
- **Реестр соответствия:** PA-001→live API; PA-024/025→#179; PA-002→#180;
  PA-020→#181; PA-004→#182; PA-003→#183; PA-014→#184; PA-018→#185;
  PA-009→#186; журналы→#187; всё — через #189.
- **Ограничение:** статусы `REMOTE_VERIFIED`; перевод в `CLOSED` — чек-лист
  оператора (modular-audit, «Волна 1 — итог»).

## E-0025 — Волна 2 remediation: решения владельца и merge-train

- **Дата:** 2026-09-02.
- **Решения владельца (AskUserQuestion, зафиксированы до реализации):**
  состав волны — «ядро очереди»; PA-019 — accepted risk (пароль меняется при
  старте, bind 0.0.0.0 осознанный); PA-008 — жёсткий kill-switch (share-ссылки
  умирают); PA-022/PA-023 — минимальные честные варианты.
- **PA-013 (закрыт без PR):** MCP `index_status(project=portal)` — branch
  main, head_sha `918a226`, 27638 nodes / 140348 edges, ready; `artifact.json`
  коммитится на тот же HEAD. Ограничение audit-фазы (переиндексация =
  mutation) снято вне волны.
- **Локальные гейты (на объединённом дереве train):** полные unit+security,
  `ci_lint.sh` (ruff+mypy), `check-drift.sh --check` (4 артефакта), FE
  lint/typecheck/vitest, shellcheck, bats — результаты в merge-train PR.
  Integration/e2e — в CI (DSN-стек и Playwright).
- **Верификационные контрпримеры:** PA-005 (docstring без регена → exit 1;
  нет node_modules → exit 2), PA-006 (переименование vitest-теста меняет
  инвентарь; setup-alias в списке), PA-007 (stale-док → exit 1; 3 регена
  байт-в-байт), PA-008 (mutation без guard → тесты красные), PA-021
  (raw cron → контракт-тест красный; исполнение обёртки пишет метрики),
  PA-023 (/ready 200→gauge 1, 503→gauge 0).
- **Remote CI:** очередь из 20 лишних прогонов задачных веток отменена через
  Actions API (`POST /actions/runs/{id}/cancel`, 204) — единственный раннер
  (capacity:1); финальные прогоны train: ci 1311/1313 — success, security
  1314 — success (первая попытка security была отменена ошибочно → Failure
  в статусах коммита; перезапуск пустым коммитом). `docs / db_schema drift
  check (pull_request)` — success на head train, добавлен в branch
  protection (21→22 contexts, live-API PATCH, обратное чтение подтверждено).
- **Мёрж:** `POST /pulls/201/merge` — HTTP 200; #192–#200 закрыты как
  реализованные (контент в main через #201).
- **Ограничение:** runtime-приёмка (PortalBackendUnhealthy в живом
  Prometheus, поведение Compose с выключенным Photos на staging) — за
  оператором; находки волны — `REMOTE_VERIFIED`.

## E-0026 — Актуализация журналов после passwordless LMS

- **Дата:** 2026-09-04.
- **Ref:** `origin/main@a872f880`; audit-файлы последний раз обновлялись в
  `5286d23f`, на 57 commits раньше текущего checkout.
- **Метод:** read-only `git log/status`, статическая сверка OpenAPI, миграций,
  LMS router/API/E2E и test runbooks; Forgejo REST для PR, commit statuses и
  branch protection. Токен использовался только в заголовке и не выводился.
- **Forgejo result:** #178, #189 и #201 смёржены. Heads волн `a117d7e` и
  `d7c67dc` имеют по 22 `success` и 8 ожидаемых `skipped`; текущая защита main —
  22 required contexts, `apply_to_admins=true`,
  `block_on_outdated_branch=true`.
- **LMS architecture drift:** #212/#213 заменили password recovery на
  `login → email code → verify → session`; миграция 114 удалила таблицу
  `learning_password_resets` и парольные поля, старые frontend reset routes
  перенаправляют на login. Поэтому PA-024 → `SUPERSEDED`; его старый runtime
  acceptance больше неприменим.
- **PA-025:** HTTPS-only remediation остаётся применимым к public origin и
  ссылкам курсов, но reset-token impact стал историческим. Runtime TLS/Nginx
  acceptance не выполнялся, статус остаётся `REMOTE_VERIFIED`.
- **PA-026:** текущий Playwright learn project всё ещё использует Vite preview,
  preview proxy пропускает весь `/api`, а learner suite выполняет admin setup
  через learn-origin. Finding повторно подтверждён статически.
- **Открытый backlog:** PA-010/011/012/015/016/026 повторно подтверждены
  статически; PA-U01/U03/U04 остаются `UNVERIFIED`.
- **Documentation drift:** текущий `openapi.json` содержит 393 paths / 493
  operations; migration chain дошёл до 115. Это обновляет evidence PA-016, но
  не исправляет сами обязательные документы вне audit scope.
- **Ограничения:** production/staging, live PostgreSQL/Redis, browser journey,
  Prometheus/Loki/Alertmanager и failure injection в этом проходе не проверялись.
  Полный модульный аудит остаётся незавершённым.
