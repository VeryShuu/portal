# Аудит и поэтапный рефакторинг Portal

> **Когда читать:** перед началом нового этапа системного или модульного аудита,
> при возобновлении работы в новой сессии и перед подготовкой remediation PR.
> **Актуализация 2026-09-04:** статусы и открытые находки повторно сверены с
> `origin/main@a872f880`; исходный baseline 2026-09-01 сохранён как историческое
> доказательство. После passwordless-перехода (#212/#213) PA-024 имеет статус
> `SUPERSEDED`, PA-025 переформулирован без удалённого reset-token flow.
> **Статус:** этапы 0 и 1 завершены в доступном read-only/static scope;
> этап 2 идёт в режиме `READ_ONLY`. **Волна 2 remediation — СМЁРЖЕНА в main
> (#201, 2026-09-02):** PA-005/006/007/008/017/021/022/023 —
> `REMOTE_VERIFIED`; PA-013 `CLOSED`, PA-019 `ACCEPTED RISK` (решения
> владельца по PA-008/PA-019/PA-022/PA-023 — в «Волна 2 — итог»).
> **Этап 10, волна 1 — СМЁРЖЕНА в main (#189, 2026-09-02):**
> PA-002/003/004/020/025 и PA-009/014/018 — `REMOTE_VERIFIED`; PA-001 —
> `CLOSED`; PA-024 — `SUPERSEDED` после замены password recovery на passwordless.
> До `CLOSED` по применимым находкам волны — runtime-приёмка оператора
> (чек-лист в «Волна 1 — итог»).
> **Правила:** `../../AGENTS.md`, модульный роутер `../README.md`.

## Цель

Провести доказательный read-only аудит портала, последовательно проверить общие
платформенные контуры и каждый продуктовый модуль, после чего устранять только
подтверждённые проблемы небольшими проверяемыми изменениями.

Глобальный big-bang рефакторинг заранее не планируется. Единица работы — либо
один вертикальный модуль, либо один подтверждённый общий инвариант.

## Исходное состояние аудита (2026-09-01)

- Baseline аудита зафиксирован на `origin/main` при HEAD
  `2e662df32ce1523b2bb469516ead3223be95e442`.
- Checkout на момент старта — `fix/meetings-rsvp-digest-timezone` при
  `96fe4c2cfc7dddb585cac3db61c214cd3a4ee36c`, на один Meetings-коммит впереди
  baseline. Этот commit не входит в системные выводы до отдельной проверки.
- `.codebase-memory/artifact.json` указывает на baseline commit, но сообщает
  `0 nodes / 0 edges`; живой MCP-граф отвечает, однако его Branch node остался на
  `71dab398` (на 691 commit позади baseline). До переиндексации граф нельзя
  использовать как актуальное доказательство impact/callers/callees.
- Корневой `audit.md` актуализировался 2026-08-19 на старом commit `da8d5f2` и
  содержит расхождение между заявленными 9 и перечисленными 6 открытыми
  задачами. Это исторический backlog, а не подтверждение текущего состояния.
- Meetings-изменения были закоммичены пользователем в отдельной ветке и
  находились в PR #177. Они не смешивались с audit-документами.
- Реестр доказательств: `portal-audit-evidence.md`.
- Реестр находок: `portal-audit-findings.md`.

## Принятые решения

- 2026-09-01: используем гибридную схему — сквозной platform baseline, затем
  вертикальные аудиты модулей, периодические межмодульные сверки и финальная
  системная проверка.
- 2026-09-01: каждый аудит сначала полностью read-only. Исправления начинаются
  только после отчёта с подтверждёнными находками и отдельного разрешения.
- 2026-09-01: аудит модуля охватывает не каталог кода, а полный путь:
  документация/ADR → БД/миграции → ACL → сервис/API → worker/outbox/cache/
  интеграции → frontend/UI → тесты/CI → runtime/monitoring.
- 2026-09-01: агрегаторы `Search`, `Home` и `Analytics` проверяются после модулей,
  данные которых они собирают.
- 2026-09-01: рефакторинг не является самоцелью. Отсутствие подтверждённых
  проблем — допустимый результат этапа.

## Правила доказательности

### Статусы проверки

- `NOT_STARTED` — проверка не начата.
- `READ_ONLY` — идёт аудит, изменения запрещены.
- `UNVERIFIED` — есть гипотеза, но недостаточно доказательств.
- `CONFIRMED` — проблема воспроизводится и подтверждена кодом, тестом, runtime
  или несколькими независимыми источниками.
- `AUTHORIZED` — пользователь разрешил исправление с согласованным scope.
- `LOCAL_VERIFIED` — изменение прошло необходимые локальные проверки.
- `REMOTE_VERIFIED` — обязательные Forgejo jobs и их логи проверены, skips и
  retries объяснены.
- `CLOSED` — исправление и требуемая runtime/monitoring-проверка завершены;
  остаточный риск записан.
- `SUPERSEDED` — исходная проблема и её доказательства сохранены исторически,
  но соответствующий сценарий удалён или заменён более новой архитектурой;
  актуальный replacement-flow проверяется отдельно.

### Приоритеты находок

- `P0 Critical` — активная утечка, потеря данных, обход auth/ACL или авария.
  Требует немедленной эскалации и containment.
- `P1 High` — production blocker, существенный security/data-integrity риск или
  сломанный основной пользовательский сценарий.
- `P2 Medium` — подтверждённый дефект, заметный UX/performance риск или опасный
  технический долг.
- `P3 Low` — локальный UX, документация, cleanup или необязательная оптимизация.
- `UNVERIFIED` — не severity, а недостаток доказательств; такая гипотеза не
  попадает в remediation backlog как установленный дефект.

### Карточка находки

Каждая находка должна содержать:

- ID и модуль/общий контур;
- severity и confidence;
- проверенный commit/ref и дату;
- затронутые пользовательские/операционные сценарии;
- точный путь к коду, конфигурации или runtime-компоненту;
- доказательство и способ воспроизведения;
- существующую тестовую защиту и её ограничения;
- предлагаемый минимальный scope исправления;
- план проверки и остаточный риск.

## Универсальный чеклист модульного аудита

Для каждого модуля выполняется один и тот же вертикальный проход.

### 1. Контекст и контракты

- [ ] Зафиксировать проверяемый commit/ref и dirty state.
- [ ] Прочитать модульный документ, связанные ADR, `../api-contracts.md`,
      `../db-schema.md`, `../roles-matrix.md` и активный WIP-план.
- [ ] Сопоставить документацию с generated contracts и фактической
      регистрацией router/model/worker/frontend route.
- [ ] Зафиксировать runtime prerequisites и недоступные внешние системы.

### 2. Persistence и бизнес-инварианты

- [ ] Проверить модели, миграции, constraints, индексы и soft-delete/trash.
- [ ] Проследить transaction boundaries, конкурентные операции и rollback.
- [ ] Проверить идемпотентность, дедупликацию, pagination/count и cleanup.
- [ ] Для DB/performance-гипотез использовать реальный план запроса; не делать
      выводы об индексах только по статическому чтению.

### 3. Security и права

- [ ] Проверить ingress, principal/session, module gate и endpoint ACL.
- [ ] Проверить object-level ACL внутри service/query, а не только dependency
      на router.
- [ ] Проверить отрицательные сценарии: anonymous, чужой объект, revoked,
      expired, deleted, disabled module и смена роли.
- [ ] Проверить CSRF/CORS, upload/download, SSRF/CSP/sanitization, PII и секреты
      там, где применимо.

### 4. Полный runtime-путь

- [ ] Проследить UI → API → service → DB/внешнюю систему → worker/outbox/cache
      → итоговый UI/уведомление.
- [ ] Проверить retries, backoff, DLQ, watchdog, locks и восстановление после
      частичного сбоя.
- [ ] Проверить cache key, TTL, явную инвалидизацию и поведение при отказе Redis.
- [ ] Проверить согласованность с внешней системой и reconciliation.

### 5. Frontend и внешний вид

- [ ] Проверить реальные DOM и пользовательские сценарии, а не только build.
- [ ] Проверить desktop, 390 px и 320 px; светлую и тёмную темы.
- [ ] Проверить loading, empty, error, stale и disabled states.
- [ ] Проверить keyboard/focus, доступные имена, контраст, таблицы, drawers и
      вложенные dialogs.
- [ ] Проверить i18n, сохранность пользовательского ввода и понятность ошибок.

### 6. Тесты и CI

- [ ] Инвентаризировать unit, integration, security, frontend и E2E-покрытие.
- [ ] Убедиться, что важный тест вызывает production-код и проверяет наблюдаемый
      результат, а не повторяет реализацию в mock.
- [ ] Для критичных инвариантов применить counterexample или временную mutation:
      сломанный production-код должен сделать тест красным.
- [ ] Проверить skip/retry/flaky counts и причины пропусков.
- [ ] Проверить обязательные Forgejo jobs и их реальные логи, а не только общий
      зелёный статус.

### 7. Эксплуатация

- [ ] Проверить health/readiness и поведение при недоступности зависимости.
- [ ] Проверить структурированные логи, correlation context и отсутствие
      секретов/PII.
- [ ] Проверить метрики, alerts, dashboards и фактический путь доставки
      уведомления там, где это необходимо.
- [ ] Зафиксировать, что доказано статически, локально, в CI, staging или prod.

### Gate модуля

Модульный аудит завершён, только если все семь разделов проверены либо для
каждого непроверенного пункта явно записаны причина, риск и способ закрытия.
Результат этапа — отчёт с `CONFIRMED` и `UNVERIFIED`, без изменений кода.

## Этап 0 — Baseline и организация аудита

**Цель:** создать воспроизводимую точку отсчёта и не наследовать устаревшие
выводы как факты.

- [x] Зафиксировать актуальные local и remote refs, HEAD и dirty state.
- [x] Проверить свежесть codebase-memory graph относительно HEAD.
- [x] Инвентаризировать модули, docs/ADR, API, модели/миграции, роли, worker
      tasks, frontend routes, тестовые контуры и Forgejo workflows.
- [x] Повторно проверить каждую открытую карточку из `../../audit.md`; перенести
      только подтверждённые, остальные пометить `STALE` или `UNVERIFIED`.
- [x] Создать реестр доказательств: источник, commit, команда/URL, результат,
      дата и ограничения.
- [x] Зафиксировать baseline обязательных CI jobs, pass/skip/retry counts и
      условия легитимных skips.
- [x] Согласовать формат отдельных отчётов по этапам и место для findings ledger.

**Gate 0:** ref, scope, evidence register и ограничения зафиксированы; код,
конфигурация, БД и runtime не изменялись.

## Этап 1 — Сквозное платформенное ядро

**Цель:** проверить общие механизмы до модулей, чтобы не повторять одну ошибку
во всех вертикалях и не пропустить дефекты на стыках.

### 1A. Identity и HTTP security

- [x] Keycloak/local/learning principals, login/callback/logout/refresh.
- [x] Session lifecycle, revocation, fixation, cookie policy и разделение
      пространств сессий.
- [x] Roles, module gates, ACL dependencies и cache invalidation при смене прав.
- [x] Middleware order, CSRF, CORS, security headers, rate limiting и
      idempotency.

### 1B. Data и runtime infrastructure

- [x] DB sessions, transactions, migration discipline и restricted DB roles.
- [x] Redis locks/cache, fail-open/fail-closed решения и cleanup.
- [x] ARQ lifecycle, cron tasks, retries/timeouts и heartbeat.
- [x] Email/messenger outbox, audit queue, DLQ/watchdog и delivery guarantees.
- [x] Runtime settings, secret storage/rotation и отсутствие import-time
      опасных side effects.

### 1C. Контракты и delivery

- [x] OpenAPI, generated frontend types и generated docs drift.
- [x] Общие frontend API/query/router/layout/i18n/a11y patterns.
- [x] Nginx ingress, Docker health/readiness, deploy/rollback.
- [x] CI isolation, required contexts, coverage, skips/retries и security gates.
- [x] Logs → Loki, metrics → Prometheus, rules → Alertmanager, dashboards и
      notification delivery.

**Ограничение Gate 1:** галочки означают завершённый static/read-only проход и
записанное ограничение, а не live acceptance. Реальные browser/a11y состояния
проверяются в вертикалях; production DB/Redis, live Prometheus/Loki series,
Alertmanager delivery и failure injection не выполнялись. Подтверждено 23
findings: 5×P1, 16×P2, 2×P3; отдельно 2 `UNVERIFIED` и 1 `ACCEPTED RISK`.

**Gate 1:** общие инварианты, blockers и ограничения записаны. Неразрешённый
platform blocker останавливает аудит зависимого модуля либо явно ограничивает
достоверность его результата.

## Этап 2 — LMS: консолидация уже выполненных проверок

**Цель:** не начинать заново, а перепроверить и объединить существующие выводы
на актуальном main.

- [x] Прочитать полностью исторические WIP `learning.md` и
      `learning-course-layout.md`; начать сверку readiness с реализацией.
- [x] Учесть стабильный модульный документ `../learning.md` и passwordless-план
      `learning-passwordless.md`, появившиеся после исходного LMS-baseline.
- [ ] Разделить смерженные, открытые, устаревшие и непроверенные находки.
- [ ] Перепроверить learner identity, session namespace и текущий passwordless
      journey `login → email_outbox → verify → session`, включая expiry,
      одноразовость, attempts и anti-enumeration. Старый recovery-flow удалён;
      PA-024 переведён в `SUPERSEDED`.
- [ ] Перепроверить изоляцию БД под restricted `learning_app` role.
- [ ] Перепроверить public ingress/TLS/allowlist и отрицательные маршруты —
      PA-003 и PA-025 подтверждены, runtime negative routes ещё не проверены.
- [ ] Перепроверить API/UI contracts и пользовательские journey.
- [ ] Перепроверить responsive 390/320 px, dark mode, tables/drawers/dialogs.
- [ ] Перепроверить staging/release evidence и обязательные CI jobs — baseline
      jobs/log counts проверены; реальный public staging недоступен (PA-026).
- [ ] Сформировать единый LMS findings ledger до любых новых исправлений.

**Gate 2:** по каждой прежней LMS-находке есть актуальный статус и доказательство.

## Этап 3 — Files / Sharing / Nextcloud

**Цель:** проверить наиболее сложный внутренний storage/ACL-контур.

- [ ] Shadow tree БД ↔ Nextcloud и reconciliation.
- [ ] Folder ACL, file shares, expiry/revocation и invalidation.
- [ ] Upload/download/preview, MIME, размеры и безопасные имена.
- [ ] Bulk operations, partial failure, idempotency и cleanup.
- [ ] Worker/sync locks, retries и поведение при недоступности Nextcloud.
- [ ] Authenticated UI journeys, responsive/dark/a11y.
- [ ] Integration/E2E и runtime evidence.

**Gate 3:** DB, Nextcloud и UI согласованы либо все residual consistency risks
явно описаны.

## Этап 4 — Helpdesk / Email

**Цель:** проверить полный жизненный цикл заявки и сохранность переписки.

- [ ] Ticket state machine, ownership, concurrency и permissions.
- [ ] IMAP/MIME body selection, threads, forwards и подписи без потери контекста.
- [ ] Attachments, storage, archive visibility и cleanup.
- [ ] Email/outbox, notifications, retries/DLQ и duplicate delivery.
- [ ] HTML/plain rendering, branding и безопасное содержимое.
- [ ] Admin/agent/user UI, responsive/dark/a11y.
- [ ] Monitoring mailbox poller, stuck messages и delivery failures.

**Gate 4:** входящее письмо прослежено до заявки и исходящего ответа, включая
ошибки и восстановление.

## Межмодульная сверка A

После LMS, Files и Helpdesk:

- [ ] Сопоставить session/ACL/cache/outbox/storage-находки.
- [ ] Проверить, не является ли похожий симптом разными root causes.
- [ ] Выделить shared remediation только при доказанном общем runtime path.
- [ ] Проверить, что будущий общий фикс не меняет соседний модуль неявно.
- [ ] Обновить порядок P0/P1 и зависимостей remediation.

## Этап 5 — Meetings

**Цель:** проверить конкурентное бронирование и цепочку уведомлений.

- [ ] Exclusion constraints и гонки create/move/cancel.
- [ ] Recurring series, timezone/DST и изменение отдельных событий.
- [ ] Rooms/participants/permissions и external data.
- [ ] iCal/email, RSVP polling/digest, retries и дубликаты.
- [ ] Dialogs/drawers/tables, 390/320 px, dark mode и a11y.
- [ ] DB integration tests, worker tests и E2E journeys.

**Ограничение:** существующие пользовательские изменения в Meetings сохраняются
и не смешиваются с аудитом.

**Gate 5:** основные гонки и lifecycle-переходы подтверждены реальной БД и
наблюдаемым пользовательским результатом.

## Этап 6 — Контент: KB → Photos → News / Polls

### 6A. Knowledge Base

- [ ] Section/article ACL, inheritance и cache invalidation.
- [ ] Versions, comments, attachments, trash/purge и orphan cleanup.
- [ ] Markdown/HTML sanitation, links/media и export.

### 6B. Photos

- [ ] Folder ACL, upload pipeline, EXIF и storage paths.
- [ ] Thumbnail generation, retry/cleanup, trash и ZIP jobs.
- [ ] Галерея, lightbox, responsive/dark/a11y.

### 6C. News / Polls

- [ ] Draft/publish/archive/trash lifecycle, categories и permissions.
- [ ] Comments/likes/pagination/count и soft-deleted placeholders.
- [ ] Poll eligibility, anonymity, repeat voting и concurrency.
- [ ] Attachments/inline media/video, sanitizer/CSP и export.
- [ ] Notifications, worker jobs и frontend voting/locking behavior.

**Gate 6:** lifecycle, ACL, media и notification-инварианты проверены для всех
трёх вертикалей.

## Межмодульная сверка B

После Meetings и контентных модулей:

- [ ] Сопоставить lifecycle, soft-delete/trash и pagination patterns.
- [ ] Сопоставить ACL inheritance и invalidation.
- [ ] Сопоставить media/upload/sanitization и notifications.
- [ ] Проверить общий editor/rendering path.
- [ ] Уточнить regression surface и порядок remediation.

## Этап 7 — Identity consumers и корпоративные интеграции

### 7A. Users / Staff / User Attributes / Directories

- [ ] Source of truth, Keycloak sync и role transitions.
- [ ] Visibility/ACL, PII и поиск сотрудников.
- [ ] Attribute mappings, full-name source и неизвестные атрибуты.
- [ ] Directory object ACL, imports/exports и auditability.

### 7B. ERP / Directum / Matrix

- [ ] Matching/deduplication и границы транзакций импорта.
- [ ] Mailbox/OData polling, retries, idempotency и watchdog.
- [ ] Report delivery и отсутствие PII/секретов в логах.
- [ ] Matrix opt-in, MXID mapping, DM cache и delivery failures.
- [ ] Поведение при частично недоступной внешней системе.

**Gate 7:** источник идентичности проверен раньше всех его потребителей; каждая
интеграция имеет доказанный fail/recovery path.

## Этап 8 — Локальные и низкорисковые модули

Порядок: Links/Bookmarks → Signature → Feedback → Branding → Onboarding.

- [ ] Применить полный универсальный чеклист к каждому модулю.
- [ ] Проверить permissions, persistence/cache и failure behavior.
- [ ] Проверить rendering, i18n, responsive/dark/a11y.
- [ ] Не смешивать cosmetic cleanup с security/data fixes.

**Gate 8:** каждый модуль имеет отдельный краткий отчёт и список ограничений.

## Этап 9 — Агрегаторы: Search → Home → Analytics

**Цель:** проверить агрегаторы после стабилизации их источников.

- [ ] Search ranking, ACL propagation, stale index/cache и visibility leaks.
- [ ] Home widgets: fan-out, partial failures, loading/empty/error states.
- [ ] Analytics: expensive queries, cache correctness и data visibility.
- [ ] Проверить, что агрегатор не обходит module gate или object ACL источника.
- [ ] Проверить mobile/dark/a11y и деградацию отдельного источника.

**Gate 9:** результат агрегатора не раскрывает недоступные исходные сущности и
корректно переживает отказ одного источника.

## Межмодульная сверка C и remediation roadmap

Полный Gate C ещё не проходился: волны 1–2 были досрочными ограниченными
remediation-наборами для уже подтверждённых platform/LMS находок и выполнялись
по отдельному разрешению владельца. Они не означают завершение модульного аудита
или финальную дедупликацию всего backlog.

- [ ] Перепроверить все findings по evidence register.
- [ ] Удалить дубликаты и вернуть неподтверждённые предположения в `UNVERIFIED`.
- [ ] Отделить shared invariant fixes от module-specific fixes.
- [ ] Согласовать немедленные P0/P1 и плановые P2/P3.
- [ ] Для каждого исправления определить PR scope, тест до исправления,
      rollout/rollback и runtime acceptance.

**Gate C:** remediation backlog состоит только из подтверждённых находок с
понятным impact и проверяемым DoD.

## Этап 10 — Исправления

Этот этап не начинается автоматически после аудита.

### Правила PR

- [ ] Получено отдельное разрешение пользователя на конкретный scope.
- [ ] Один PR исправляет один модуль или один общий инвариант.
- [ ] Сначала characterization/regression test, затем минимальное исправление.
- [ ] Значимый рефакторинг выполняется поэтапно и обратимо.
- [ ] API/DB/ACL contracts меняются только после явного решения и с обновлением
      документации/generated artifacts.
- [ ] Не добавляются `continue-on-error`, безусловные skips или ослабление gates.
- [ ] Не выполняются merge, release, deploy, deletion или destructive DB actions
      без отдельного разрешения.
- [ ] Локальная проверка и remote CI фиксируются как разные уровни доказательств.

### Проверки изменения

- [ ] Targeted regression/characterization tests.
- [ ] Backend `./scripts/ci_lint.sh`, нужные unit/security/integration suites.
- [ ] Frontend lint, typecheck, unit и релевантный Playwright E2E.
- [ ] Diff coverage и mutation/counterexample для важного инварианта.
- [ ] `./scripts/check-drift.sh --fix`, затем `--check`, если затронуты
      API/модели/тесты/generated artifacts.
- [ ] Все required Forgejo jobs проверены по логам; skips/retries объяснены.
- [ ] Выполнена нужная staging/prod/runtime/monitoring acceptance либо явно
      записано, почему она остаётся за оператором.

### Волна 1 — итог (2026-09-02, смёржено #189)

**Состав:** #179 (PA-024+PA-025), #180 (PA-002), #181 (PA-020), #182 (PA-004),
#183 (PA-003), #184 (PA-014), #185 (PA-018), #186 (PA-009), #187 (журналы аудита).
Собраны merge-train'ом в #189: единственный раннер (`capacity: 1`) не позволял
перекатывать 9 полных прогонов serial. Атомарные коммиты каждого PR сохранены.
PA-001 закрыт отдельно (live-API правка branch protection, 21/21 contexts).

**Сопутствующая инфраструктура (2026-09-02):**
- #188 — бюджеты `timeout-minutes` (build/quality/types-drift 15→25, e2e 20→30),
  `npm@11` в deps-джобе (npm закрывает /quick audit endpoint) + ретраи аудита;
- #178 — исходные журналы аудита;
- bats-core v1.14.0 вендорен в `tests/setup/vendor/bats-core` (github-клон с
  раннера нестабилен); вендор — рантайм-only (dev-Dockerfile'ы валили trivy DS-0002);
- skip-бюджет unit 10→12 (`_DAILY_SKIP_CAPS`) — 2 новых nightly render-теста.

**Инцидент раннера 2026-09-02:** переполнение диска (`initdb: No space left on
device`) + сетевые деградации (npm ETIMEDOUT, github-клоны). Диагностика и
чистка — оператором; детали — E-0023 в evidence.

**Чек-лист runtime-приёмки оператора (перевод применимых находок волны в CLOSED):**
- [ ] PA-002: `.env` прода содержит `LEARNING_DB_PASSWORD`; learning-запросы
      идут от роли `learning_app` (`select current_user` в learning-сессии).
- [ ] PA-003: на реальном learn-host learner-пути отвечают, `/learning/admin/*`
      и `/learning/admins` — 404 до backend.
- [x] PA-024: `SUPERSEDED` — password recovery удалён в #212/#213; runtime reset
      journey больше неприменим. Текущий passwordless journey проверяется в
      рамках незавершённого этапа 2.
- [ ] PA-025: rendered Nginx корректен; `learning_base_url` остаётся HTTPS-only;
      ссылка зачисления открывается в браузере без HSTS-кэша.
- [ ] PA-004 (опционально): browser round-trip HTTP-bootstrap + HTTPS-прокси.
- [ ] PA-009 (опционально): поведение Compose при включённом NC без URL.

### Волна 2 — итог (2026-09-02, смёржено #201; PR #192–#200)

**Решения владельца (2026-09-02, зафиксированы до реализации):**
- PA-019 — **accepted risk**: пароль Grafana меняется оператором сразу при
  запуске; `GRAFANA_BIND=0.0.0.0` осознанный (сервис отображения). Кода нет.
- PA-008 — **жёсткий kill-switch**: public share-ссылки при выключении Photos
  умирают (guard на родительском роутере, 404 до auth/ACL).
- PA-022/PA-023 — минимальные честные варианты: restart-required маркировка
  (без runtime-apply); gauge + алерт + runbook (без autoheal).

**Состав волны:** PA-017 (generated-типы), PA-005 (check-drift --check),
PA-006 (инвентарь тестов), PA-007 (db-schema + drift-гейт; стек на PA-005),
PA-008 (Photos kill-switch), PA-021 (ARQ cron-метрики), PA-022 (честная
семантика настроек; стек-взаимодействие с PA-023 через monitoring.md),
PA-023 (gauge+алерт+runbook; стек на PA-022), журналы (этот файл+findings+
evidence). PA-013 закрыт без PR (переиндексация графа уже в main: MCP
`portal` на HEAD `918a226`, 27638 nodes).

**Сопутствующее:** required context
`CI / docs / db_schema drift check (pull_request)` добавлен в branch protection
live-API после первого зелёного прогона (прецедент PA-001); актуальная сверка
2026-09-04 подтвердила 22 required contexts.

**Очередь волны 3 (кандидаты):** PA-010 (Keycloak admin probe SSRF —
DNS-pinning, private ranges, недоверие discovery), PA-011 (versioned key
rotation), PA-012 (runbooks тестирования/CI), PA-015 (helpdesk email
duplication — по characterization-тестам), PA-026 (learn E2E через
rendered Nginx с negative routes). UNVERIFIED к воспроизведению: PA-U01
(EXPLAIN redundant indexes), PA-U03, PA-U04 (конкурентный submit).

## Этап 11 — Финальная системная проверка

- [ ] Повторить platform baseline после remediation.
- [ ] Проверить cross-module journeys: auth → ACL → mutation → DB/outbox/worker
      → cache → UI → notification/search/analytics.
- [ ] Проверить negative paths: unauthorized, revoked, expired, deleted,
      disabled module, failed worker, stale cache и unavailable integration.
- [ ] Проверить responsive 390/320 px, light/dark и a11y общих layouts.
- [ ] Выполнить runtime smoke и мониторинг полного пути.
- [ ] Проверить OpenAPI/types/docs/tests drift.
- [ ] Подготовить итог: закрыто, отклонено, отложено, `UNVERIFIED`, residual risk.

## Артефакты выполнения

- Этот файл — порядок этапов, gates и общий статус.
- Evidence register — commit/ref, команды, CI/runtime links, результаты и
  ограничения каждого доказательства.
- Краткий dossier для каждого модуля по универсальному чеклисту.
- Findings ledger с severity, confidence и связями между дубликатами.
- Отчёты межмодульных сверок A/B/C.
- Отдельные remediation PR с test/CI/runtime evidence.
- Финальный residual-risk report.

Конкретные файлы для evidence register, dossiers и findings ledger выбираются
на этапе 0, чтобы не плодить документы до начала фактического аудита.

## Общий Definition of Done

- [ ] Все этапы 0–11 завершены либо имеют явно записанное ограничение.
- [ ] Каждый модуль прошёл read-only аудит по всем семи разделам чеклиста.
- [ ] Все P0/P1 исправлены, изолированы или эскалированы владельцу с решением.
- [ ] Нет remediation без подтверждённой находки и regression-защиты.
- [ ] API, DB, роли, docs и generated contracts синхронизированы.
- [ ] CI pass/skip/retry counts подтверждены по job logs.
- [ ] Runtime health, logs, metrics и alerts проверены на затронутых путях.
- [ ] Пользовательские незакоммиченные изменения сохранены.
- [ ] Остаточный риск и следующий исполнимый шаг записаны.

## Текущий прогресс

| Этап | Статус | Результат |
|---|---|---|
| 0. Baseline | `EVIDENCE_COMPLETE` | Инвентарь, live Forgejo, старый backlog и WIP сверены; журналы созданы |
| 1. Platform core | `EVIDENCE_COMPLETE_STATIC` | 23 findings; runtime/browser ограничения записаны в evidence ledger |
| 2. LMS | `READ_ONLY` | Исходные recovery/TLS и CI findings сверены; PA-024 SUPERSEDED passwordless-архитектурой, PA-025 переформулирован, PA-026 остаётся CONFIRMED; текущий passwordless vertical audit продолжается |
| 3. Files / Sharing | `NOT_STARTED` | — |
| 4. Helpdesk / Email | `NOT_STARTED` | — |
| A. Межмодульная сверка | `NOT_STARTED` | — |
| 5. Meetings | `NOT_STARTED` | — |
| 6. KB / Photos / News / Polls | `NOT_STARTED` | — |
| B. Межмодульная сверка | `NOT_STARTED` | — |
| 7. Identity / Integrations | `NOT_STARTED` | — |
| 8. Локальные модули | `NOT_STARTED` | — |
| 9. Aggregators | `NOT_STARTED` | — |
| C. Remediation roadmap | `NOT_STARTED` | Полный межмодульный Gate C не проходился; волны 1–2 были отдельно разрешёнными досрочными наборами для подтверждённых находок |
| 10. Исправления | `WAVE_2_MERGED` | Волна 1: #189 (PA-002/003/004/020/025 + PA-009/014/018 REMOTE_VERIFIED), PA-001 CLOSED; PA-024 SUPERSEDED после #212/#213. Волна 2: #201 (+PR #192–#200): PA-005/006/007/008/017/021/022/023 REMOTE_VERIFIED; PA-013 CLOSED, PA-019 ACCEPTED RISK; branch protection 22/22 (+db_schema drift). Остались: PA-010/011/012/015/026 (P2), PA-016 (P3) |
| 11. Финальная проверка | `NOT_STARTED` | — |

## Handoff после каждого этапа

```text
СДЕЛАНО: scope/ref, проверенные слои, confirmed findings и evidence
В РАБОТЕ: конкретный этап/модуль/проверка и файл:строка
ДАЛЕЕ: первый исполнимый read-only шаг
ОТКРЫТЫЕ ВОПРОСЫ: решения, требующие пользователя
КОММИТ/PR: ветка, scope, проверки и remote status либо «не требуется»
ОГРАНИЧЕНИЯ: недоступный runtime, skips, stale refs, unverified prod evidence
```

## Грабли / контекст

- Похожий симптом в двух модулях не доказывает общий root cause.
- HTTP 200, строка в БД или зелёный aggregate CI не закрывают полный runtime path.
- Успешный local subset не равен полному CI и не доказывает staging/prod.
- Недоступный внешний сервис не превращает статическую проверку в runtime evidence.
- Агрегаторы нельзя полноценно проверить раньше их источников.
- Рефакторинг без characterization tests может закрепить незамеченную регрессию.
- Старые аудиты и WIP-планы используются как карта гипотез, но все выводы
  перепроверяются на актуальном ref.
