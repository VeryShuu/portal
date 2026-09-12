# Portal audit — реестр находок

> **Статус:** этапы 0–1 завершены в static scope, этап 2 `READ_ONLY`.
> **Актуализация 2026-09-04:** открытые карточки и статусы повторно сверены с
> `origin/main@a872f880`. Исходные evidence/reproduction сохранены относительно
> baseline 2026-09-01. PA-024 переведён в `SUPERSEDED` после passwordless-
> перехода (#212/#213); PA-025 и PA-026 уточнены для текущей архитектуры.
> **Волна 1 remediation смёржена в main (#189, 2026-09-02):** PA-001 закрыт;
> PA-002/003/004/009/014/018/020/025 — `REMOTE_VERIFIED` (полный зелёный
> CI-прогон, мёрж). Перевод в `CLOSED` — после runtime-приёмки оператором
> (критерии — в карточках). PA-024 — `SUPERSEDED` после удаления password
> recovery в пользу passwordless-входа.
> **Волна 2 remediation смёржена в main (#201, 2026-09-02; PR #192–#200):**
> PA-005/006/007/008/017/021/022/023 — `REMOTE_VERIFIED` (полный зелёный
> CI-прогон обоих workflow); PA-013 — `CLOSED` (переиндексация); PA-019 —
> `ACCEPTED RISK` (решение владельца). Детали — карточки и «Волна 2 — итог».
> **Baseline:** `origin/main@2e662df32ce1523b2bb469516ead3223be95e442`.
> **Правило:** в этот файл попадают подтверждённые дефекты и явно отделённые
> гипотезы. Наличие карточки не разрешает исправление.
> Заголовок, impact и исходное evidence карточки описывают найденный baseline-
> дефект; каноническое текущее состояние задают поля «Статус», «Remediation» и
> «Актуализация», а также сводная таблица.

## Сводка

| ID | Severity | Статус | Контур | Кратко |
|---|---|---|---|---|
| PA-001 | P1 | CLOSED | CI policy | branch protection расширен с 19 до текущих 22 required contexts |
| PA-002 | P1 | REMOTE_VERIFIED | LMS / DB | fail-closed исправление смёржено; production role acceptance ещё не выполнена |
| PA-003 | P1 | REMOTE_VERIFIED | LMS / ingress | public allowlist смёржен; реальный learn-host ещё не проверен |
| PA-004 | P1 | REMOTE_VERIFIED | Auth / cookies | request-aware `Secure` policy смёржена; browser round-trip опционален |
| PA-020 | P1 | REMOTE_VERIFIED | HTTP / uploads | multipart исключён из pre-auth idempotency buffering; runtime load не выполнялся |
| PA-005 | P2 | REMOTE_VERIFIED | Local drift tooling | `check-drift.sh --check` теперь регенерирует во временной копии и ловит drift |
| PA-006 | P2 | REMOTE_VERIFIED | Test inventory | inventory теперь учитывает отдельные Vitest cases и Playwright aliases |
| PA-007 | P2 | REMOTE_VERIFIED | DB docs/contracts | DB schema generator и required drift gate добавлены |
| PA-008 | P2 | REMOTE_VERIFIED | Photos / modules | жёсткий module kill-switch добавлен, включая public shares |
| PA-009 | P2 | REMOTE_VERIFIED | Readiness / Files | enabled Nextcloud без URL теперь fail-closed |
| PA-010 | P2 | CONFIRMED | Keycloak admin | hostname/discovery probe оставляет SSRF и credential-forwarding surface |
| PA-011 | P2 | CONFIRMED | Secrets | отсутствует versioned key rotation для сохранённых ciphertext |
| PA-012 | P2 | CONFIRMED | Developer workflow | testing/CI runbooks противоречат фактическим test contours |
| PA-013 | P2 | CLOSED | Audit tooling | artifact сообщает current commit, live graph отстаёт на 691 commit |
| PA-014 | P2 | REMOTE_VERIFIED | News comments | `total` приведён к выдаче с deleted placeholders; отдельного runtime probe не было |
| PA-015 | P2 | CONFIRMED | Helpdesk maintainability | крупные email/notification helpers сохраняют дублирующие runtime/query paths |
| PA-016 | P3 | CONFIRMED | Documentation | root audit, API counts, DB migrations и WIP registry устарели |
| PA-017 | P3 | REMOTE_VERIFIED | Frontend contracts | Directum/Bootstrap clients переведены на generated schemas |
| PA-018 | P2 | REMOTE_VERIFIED | Audit queue | malformed записи изолируются в bounded quarantine и не блокируют очередь |
| PA-019 | P2 | ACCEPTED RISK | Monitoring auth | свежая Grafana публикуется в сеть с `admin/admin` без prod gate |
| PA-021 | P2 | REMOTE_VERIFIED | ARQ metrics | cron executions обёрнуты в общую job-метрику и failure alert |
| PA-022 | P2 | REMOTE_VERIFIED | Runtime settings | startup-only поля явно помечены как restart-required |
| PA-023 | P2 | REMOTE_VERIFIED | Readiness / Compose | добавлены health gauge, alert и runbook без обещания autoheal |
| PA-024 | P1 | SUPERSEDED | LMS / recovery | password recovery удалён; LMS перешёл на одноразовые коды входа |
| PA-025 | P1 | REMOTE_VERIFIED | LMS / TLS | public base URL ограничен HTTPS-origin; runtime TLS acceptance не выполнена |
| PA-026 | P2 | CONFIRMED | LMS / E2E | learn E2E обходит production Nginx и использует public origin для admin API |
| PA-U01 | — | UNVERIFIED | DB performance | старые кандидаты redundant indexes не подтверждены runtime-планами |
| PA-U02 | — | ACCEPTED RISK | Architecture | module-level `get_settings()` есть, но текущий failure mode не доказан |
| PA-U03 | — | UNVERIFIED | Secret crypto | необходимость password-style KDF для high-entropy `SECRET_KEY` не доказана |
| PA-U04 | — | UNVERIFIED | LMS / attempts | конкурентный submit может повторно применить stale ORM attempt |

## PA-001 — Два обязательных CI check фактически не обязательны

- **Severity:** P1.
- **Статус:** CONFIRMED → **CLOSED** (2026-09-02).
- **Remediation (2026-09-02):** branch protection обновлён live API — 21/21 required
  contexts (`CI / screenshot-service / pytest unit (pull_request)`,
  `CI / monitoring / config validation (pull_request)` добавлены). Enforcement
  наблюдался живьём: мёрж через API при красном контексте отвечал
  `405 Not all required status checks successful`.
- **Остаточный риск:** отдельная негативная проверка именно двух новых контекстов
  не выполнялась (механика идентична остальным); детали — E-0021.
- **Контур:** branch protection / release governance.
- **Impact:** PR может быть смержен при красном screenshot-service unit или
  monitoring configuration validation, несмотря на обязательность этих
  контуров в проектной политике.
- **Evidence:**
  - `AGENTS.md:228-241` заявляет 21 обязательный check и перечисляет оба;
  - `.forgejo/workflows/ci.yml:71-92` определяет
    `screenshot-service / pytest unit`;
  - `.forgejo/workflows/ci.yml:814-878` определяет
    `monitoring / config validation`;
  - live Forgejo branch protection содержит 19 contexts и не содержит эти два;
    `apply_to_admins=true`, `block_on_outdated_branch=true`.
- **Reproduction:** read-only Forgejo REST
  `GET /repos/mage/portal/branch_protections/main`.
- **Ограничение:** jobs выполняются в workflow; дефект именно в enforcement.
- **Минимальный remediation scope:** изменение branch protection, без правок
  workflow; только после отдельного разрешения пользователя.
- **Verification:** повторный live API read и отрицательная проверка на тестовом
  failing commit/контексте.

## PA-002 — LMS DB isolation fail-open без обязательного секрета

- **Severity:** P1.
- **Статус:** **REMOTE_VERIFIED**; наличие секрета и restricted role path на prod
  не проверены.
- **Remediation (2026-09-02):** PR #180, смёржено через #189 — fail-closed в
  `Settings._validate_production_secrets` + preflight в `setup.sh` + тесты.
  **До CLOSED:** прод-деплой с `LEARNING_DB_PASSWORD` в `.env`; контроль, что
  learning-запросы идут от роли `learning_app` (`select current_user`).
- **Контур:** LMS / database privilege boundary / deploy.
- **Impact:** если оператор пропустит `LEARNING_DB_PASSWORD`, все зависимости
  `LearningDbDep` молча используют основной привилегированный pool вместо роли
  `learning_app`. Ошибка конфигурации не останавливает production.
- **Evidence:**
  - `backend/app/core/config.py:97-101` — пустое значение разрешено;
  - `backend/app/core/config.py:169-198` — production validator не требует пароль;
  - `backend/app/core/database.py:47-59,75` — `None` выбирает
    `AsyncSessionLocal`;
  - `backend/app/core/database.py:90-99` — только warning при первом запросе;
  - `setup.sh:1502-1549` — prod preflight не включает этот ключ в mandatory;
  - migrations 102/103 создают и ограничивают роль `learning_app`.
- **Ограничение:** production `.env` и реальные grants не читались; finding
  относится к подтверждённому fail-open поведению приложения.
- **Минимальный remediation scope:** fail-closed production validation + preflight
  + negative tests; API/DB contract отдельно не меняется.
- **Verification:** production Settings test, setup Bats, запуск restricted-role
  integration path и отрицательная попытка чтения штатных таблиц.

## PA-003 — Public LMS ingress шире заявленного allowlist

- **Severity:** P1.
- **Статус:** **REMOTE_VERIFIED**; runtime negative-проверка реального learn-host
  ещё не выполнена.
- **Remediation (2026-09-02):** PR #183, смёржено через #189 — allowlist
  (`= /learning/meta`, `/learning/me/`, auth-regex; остальное 404),
  рендер-тесты + bats + `nginx -t`. **До CLOSED:** runtime negative-проверка
  реального learn-host после деплоя (learner 200, admin — 404 до backend).
- **Контур:** public Nginx / LMS.
- **Impact:** публичный learn-host проксирует административные learning endpoints,
  хотя документация и комментарий обещают learner-only API. Backend auth остаётся
  последней защитой вместо двух независимых границ.
- **Evidence:**
  - `nginx/templates/learn_server.conf.tmpl:71-85` — prefix location
    `/api/v1/learning/`;
  - `backend/app/api/learning/__init__.py:17-25` — под тем же prefix собраны
    learner, admin, methodist и meta routers;
  - административные prefixes:
    `admin_courses.py:56-58`, `admin_routes.py:31-33`,
    `methodists.py:27-29`;
  - negative ingress test, запрещающий admin paths через learn-host, не найден.
- **Ограничение:** rendered Nginx и реальный public host не проверялись.
- **Минимальный remediation scope:** explicit exact/regex learner allowlist и
  обязательные negative Nginx tests.
- **Verification:** real rendered config: learner/auth routes доступны, admin и
  весь portal API возвращают Nginx 404 до backend.

## PA-004 — Cookie `Secure` регрессировала относительно ADR-021

- **Severity:** P1.
- **Статус:** **REMOTE_VERIFIED**; browser round-trip через реальные proxy
  опционально остаётся за оператором.
- **Remediation (2026-09-02):** PR #182, смёржено через #189 —
  `app/core/cookies.py::request_is_secure` (X-Forwarded-Proto), все 8 точек
  выдачи переведены, characterization-матрица HTTP/HTTPS для каждой.
  **До CLOSED (опционально):** browser round-trip через HTTP-bootstrap и
  HTTPS-прокси с реальными `Set-Cookie`.
- **Контур:** auth/session/CSRF; затрагивает все модули.
- **Impact:** production HTTP bootstrap получает `Secure` cookies, которые браузер
  не возвращает по HTTP; staging/non-production HTTPS получает cookies без
  `Secure`. Поведение зависит от environment, а не фактического протокола.
- **Evidence:**
  - `docs/adr.md:582-611` требует `X-Forwarded-Proto` для обеих выдач session;
  - local session/marker: `backend/app/api/auth/local.py:113-133`;
  - OIDC session/marker и SSO loop:
    `backend/app/api/auth/_helpers.py:75-84,132-155`;
  - refresh: `backend/app/api/auth/me.py:161-170`;
  - XSRF: `backend/app/middleware/csrf.py:116-131`;
  - learner session: `backend/app/services/learning/accounts_service.py:245-255`,
    вызывается из `backend/app/api/learning/auth_routes.py:55-84`;
  - все перечисленные выдачи используют `get_settings().is_production`;
  - contract tests по `X-Forwarded-Proto` для этих cookies не найдены.
- **Минимальный remediation scope:** единый request-aware cookie policy и
  characterization tests для HTTP/HTTPS × production/staging.
- **Verification:** реальные `Set-Cookie` headers и browser round-trip через
  HTTP bootstrap и HTTPS reverse proxy.

## PA-005 — `check-drift.sh --check` даёт ложнозелёный результат

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**.
- **Remediation (2026-09-02, волна 2):** `--check` регенерирует каждый
  артефакт во временную копию и сравнивает с рабочим деревом (дерево
  восстанавливается); отсутствие node_modules и pytest — честный exit 2;
  python/pytest берутся из `backend/.venv-ci` (урок #58); stderr регенерации
  не глушится. Верификация в scratch-клоне: чистое дерево exit 0; docstring
  эндпоинта без регена → exit 1 с diff; устаревший tests.generated.md →
  exit 1; нет node_modules → exit 2.
- **Контур:** локальная подготовка PR; remote CI jobs регенерируют корректно.
- **Impact:** чистый checkout со stale committed OpenAPI/types/tests inventory
  проходит локальную команду, объявленную эквивалентом CI. При отсутствии
  `frontend/node_modules` types check ещё и молча пропускается.
- **Evidence:**
  - описание режима: `scripts/check-drift.sh:14-17`;
  - генерация выполняется только в `--fix`: строки `73-77`, `99-103`, `123-132`;
  - `--check` проверяет только существующий `git diff`: `79`, `105`, `134`;
  - отсутствие node_modules пропускает types: `96-98`;
  - remote jobs регенерируют перед diff:
    `.forgejo/workflows/ci.yml:702-734,953-980,1373-1403`.
- **Severity rationale:** merge gates сами по себе не обойдены, поэтому P2, а не P1.
- **Verification:** в scratch checkout изменить production schema/test без
  generated artifact; `--check` обязан падать.

## PA-006 — Test inventory drift gate не защищает отдельные test cases

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**.
- **Remediation (2026-09-02, волна 2):** Vitest-секция строится через
  `vitest list` (2718 полных ID вместо имён файлов); Playwright-паттерн
  собирает alias-импорты (`import { test as setup }` → `setup('...')`) —
  setup-кейс auth.setup.ts теперь в инвентаре (раньше комментарий ошибочно
  утверждал обратное); CI-джоба получила node-setup + npm ci, timeout 15→25.
  Контрпример: переименование vitest-теста меняет инвентарь.
- **Контур:** docs/tests.generated.md и его required CI gate.
- **Impact:** удаление отдельного Vitest test из существующего файла не меняет
  inventory; Playwright aliases/multiline forms пропускаются. Зелёный drift job
  доказывает список файлов/ограниченный regex, а не заявленный список tests.
- **Evidence:**
  - backend использует collect-only: `scripts/list_tests.sh:24-34`;
  - Vitest использует только `find` filenames: `41-45`;
  - Playwright извлекается regex: `57-69`;
  - `frontend/tests/e2e/auth.setup.ts:13-20` использует alias `setup(...)`, а
    соответствующий case отсутствует в generated list;
  - `docs/testing.md:649` описывает реальный Vitest list.
- **Ограничение:** сами Vitest/Playwright suites запускаются другими jobs;
  дефект относится к completeness/drift inventory.

## PA-007 — Generated DB schema неполна и не защищена CI

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**.
- **Remediation (2026-09-02, волна 2):** генератор импортирует `app.models`
  целиком (83 таблицы, все 12 learning_*); вывод детерминизирован (timestamp
  убран, constraints отсортированы — table.constraints это set, repr(Computed)
  без адресов объектов); check-drift.sh — 4-й артефакт; новая CI-джоба
  `docs / db_schema drift check`. Контрпример: stale-док → --check exit 1;
  три прогона генерации байт-в-байт. Required context добавлен в branch
  protection live-API после первого зелёного прогона; live-сверка 2026-09-04
  подтвердила 22 required contexts.
- **Контур:** DB contracts / все persistence-модули.
- **Impact:** обязательная generated-документация не отражает актуальную схему;
  аудиторы и разработчики могут принять устаревший contract за source of truth.
- **Evidence:**
  - `docs/db-schema.generated.md` датирована 2026-08-05 и не содержит
    `learning_*`;
  - `backend/app/models/learning.py:35-403` содержит 12 learning tables;
  - импорт всех `app.models` даёт 83 metadata tables;
  - `backend/scripts/generate_db_schema_doc.py:26-34` импортирует ограниченный
    ручной список model modules и не импортирует learning;
  - `scripts/check-drift.sh:5-12` и CI drift jobs охватывают только OpenAPI,
    frontend types и tests inventory.
- **Ограничение:** это не доказательство drift production DB; finding про
  generator/committed contract.

## PA-008 — Photos module switch не является master kill-switch

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**.
- **Remediation (2026-09-02, волна 2):** продуктовое решение владельца —
  **жёсткий kill-switch**: public share-ссылки переживать выключение не
  должны. PhotosGuard на родительском /photos-роутере (404 до auth/ACL);
  тесты: публичный токен 404, админ-роут 404 до auth, enabled → 401 от auth;
  mutation-проверка (без guard тесты красные); docs/photos.md §9 дополнен.
  Fail-open повреждённого modules.json остаётся глобальным поведением
  (изменение затронуло бы все модули) — остаточный риск записан.
- **Контур:** Photos / module configuration / public shares.
- **Impact:** выключение Photos скрывает UI и блокирует лишь часть операций, но
  folder/ACL/share/public/media endpoints остаются зарегистрированными. При
  повреждённом `modules.json` Photos fail-open в `enabled=True`.
- **Evidence:**
  - docs обещают API+UI disable: `docs/photos.md:459-478`;
  - parent router без gate: `backend/app/api/photos/__init__.py:15-25`;
  - folder routes без enabled check: `folders.py:111-166`;
  - share creation без enabled check: `sharing.py:64-105`;
  - defaults/fallback: `backend/app/core/modules_config.py:39-59,113-130`;
  - глобальный disabled-route test не найден.
- **Ограничение:** пока не решено продуктово, должны ли уже выданные public share
  links переживать административное выключение модуля.

## PA-009 — Enabled Nextcloud может быть ложнозелёным в readiness

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**; staging-проверка Nextcloud-конфигурации
  опционально остаётся за оператором.
- **Remediation (2026-09-02):** PR #186, смёржено через #189 — unconfigured при
  включённом модуле выставляет `failed=True` → 503 (fail-closed), warning-лог,
  тесты. **До CLOSED (опционально):** наблюдение поведения Compose на staging.
- **Контур:** Files / readiness / deployment.
- **Impact:** при включённом Nextcloud и пустом URL backend `/ready` возвращает
  `200`, а Compose считает backend и зависящий Nginx healthy, хотя основной Files
  integration не настроен.
- **Evidence:**
  - `backend/app/api/health.py:54-69` ставит `unconfigured`, но не `failed=True`;
  - ответ вычисляется на `90-94`;
  - `docs/monitoring.md:48-52` обещает 503 для Nextcloud failure;
  - пустой URL достижим через system settings;
  - `docker-compose.yml:203-219,369-381` связывает health с `/ready`.
- **Ограничение:** текущая production-конфигурация не проверялась.

## PA-010 — Keycloak admin probe оставляет SSRF/credential-forwarding surface

- **Severity:** P2.
- **Статус:** CONFIRMED static weakness, повторно сверено 2026-09-04;
  runtime exploit не воспроизводился.
- **Контур:** Keycloak admin configuration.
- **Impact:** административный probe принимает hostname без DNS pinning,
  разрешает private ranges и доверяет discovery-provided `token_endpoint`, куда
  отправляет client credentials. Ошибки/фрагменты ответов возвращаются наружу.
- **Evidence:**
  - `backend/app/core/net_guard.py:53-102`;
  - `backend/app/services/keycloak/admin_store.py:79-91`;
  - `backend/app/services/keycloak/probe.py:26-74,79-148`;
  - `backend/app/api/keycloak_admin.py:126-160` требует admin.
- **Risk boundary:** не anonymous; нужен admin control/compromise или злонамеренный
  upstream discovery.

## PA-011 — Нет совместимой ротации ключей сохранённых секретов

- **Severity:** P2.
- **Статус:** CONFIRMED, повторно сверено 2026-09-04.
- **Контур:** интеграционные secrets.
- **Impact:** изменение `SECRET_KEY` делает ранее сохранённые Fernet ciphertext
  нечитаемыми; нет key version/fallback decrypt path.
- **Evidence:** `backend/app/core/secret_crypto.py:26-55`; текущие tests проверяют
  roundtrip/cache, но не migration между ключами.
- **Уточнение:** прежняя формулировка «SHA-256 вместо PBKDF — слабость» не принята
  как доказанная: production secret должен быть high-entropy, а не паролем.

## PA-012 — Runbooks тестирования и CI противоречат фактическим контурам

- **Severity:** P2.
- **Статус:** CONFIRMED documentation/operations defect, повторно сверено
  2026-09-04.
- **Impact:** оператор или разработчик может непреднамеренно пропустить security
  или testcontainers contour либо получить неожиданную Docker-зависимость.
- **Основные расхождения:**
  - общий `pytest tests/integration` смешивает DSN и testcontainers files;
  - актуальный DSN helper исключает две migration suites, а docs описывают три;
  - default `run-testcontainers-tests.sh` запускает только migrations, хотя
    docs/AGENTS обещают также local auth/learning role;
  - `run_pytest_unit.sh` запускает только unit, но docs называют unit+security;
  - `docs/testing.md` устарел по active PR integration/E2E, screenshot deps,
    coverage thresholds, release/deploy и nightly ZAP;
  - merged coverage назван informational, но required diff-coverage имеет его
    hard `needs`, поэтому он косвенно merge-blocking.
- **Evidence:** `backend/scripts/run_pytest_integration.sh:18-22`,
  `scripts/run-testcontainers-tests.sh:57-65`,
  `backend/scripts/run_pytest_unit.sh:1-4`, соответствующие разделы
  `docs/testing.md:241-263,631-746`, `.forgejo/workflows/ci.yml`.

## PA-013 — Codebase-memory freshness metadata не соответствует live graph

- **Severity:** P2.
- **Статус:** CONFIRMED → **CLOSED** (2026-09-02).
- **Remediation:** живой граф переиндексирован 2026-09-02: MCP `portal` на
  HEAD `918a226` (27638 nodes / 140348 edges, status ready); `artifact.json`
  коммитится на тот же commit. Проверка свежести по artifact+MCP `index_status`
  совпадает — расхождение «artifact говорит current, live отстаёт на 691»
  устранено. Отдельного remediation-PR не требует (артефакт уже в main).
- **Impact:** проверка только artifact commit ошибочно разрешает использовать
  устаревший graph для impact analysis.
- **Evidence:**
  - artifact: baseline commit, `nodes=0`, `edges=0`;
  - live schema непуста;
  - live Branch node — `main@71dab398`, на 691 commit позади baseline.
- **Ограничение:** переиндексация является mutation артефакта и в audit-only фазе
  не выполнялась.

## PA-014 — News comments `total` расходится с перебором страниц

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED** для News; старая KB-часть исходной гипотезы
  была `STALE`.
- **Remediation (2026-09-02):** PR #184, смёржено через #189 — `count_comments`
  без фильтра deleted (1:1 с KB), регрессия по скомпилированному SQL. Остаточного
  риска нет; CLOSED по факту мёржа не заявляется только из-за отсутствия
  отдельной runtime-проверки; поэтому канонический статус остаётся
  `REMOTE_VERIFIED`, а не `CLOSED`.
- **Контур:** News comments pagination.
- **Impact:** list сохраняет deleted placeholders, а count считает только active;
  UI получает `total`, не соответствующий фактической выдаче.
- **Evidence:** `backend/app/api/news/comments_repo.py:20-39`, consumer
  `backend/app/api/news/comments.py:65-80`. KB count/list уже оба включают deleted:
  `backend/app/api/kb/comments_repo.py:18-33`.
- **Test gap:** mixed soft-deleted pagination counterexample не найден.

## PA-015 — Helpdesk email/notification code сохраняет подтверждённые дубли

- **Severity:** P2.
- **Статус:** CONFIRMED structural debt, повторно сверено 2026-09-04;
  пользовательский дефект не доказан.
- **Контур:** Helpdesk/email maintainability.
- **Impact:** несколько loader/runtime wrappers увеличивают риск рассинхронного
  изменения branding/recipients/settings.
- **Evidence:** duplicate agent loaders в
  `backend/app/services/helpdesk/notifications.py:54,346`; runtime URL/timezone
  wrappers в `email_template.py:488-507` и `notifications.py:613`; четыре
  связанные реализации выросли до 3369 LOC.
- **Ограничение:** историческая цель `-400 LOC`, Jinja2 и feature flag — варианты
  дизайна, а не подтверждённые требования.

## PA-016 — Обязательные документы и WIP registry устарели

- **Severity:** P3.
- **Статус:** CONFIRMED, повторно сверено 2026-09-04.
- **Impact:** новый аудит может наследовать неверный scope/status.
- **Evidence:**
  - `../../audit.md` одновременно заявляет 9 и 6 open tasks и относится к
    старому `da8d5f2`;
  - `AGENTS.md` содержит 319/401 против текущих 393/493 и заявляет 95 миграций
    при фактической цепочке 001–115;
  - `docs/db-schema.md` в заголовке заявляет цепочку 001–112, перечисляет
    113–114, но ещё не включает migration 115;
  - `docs/README.md` всё ещё называет GitHub в MCP setup;
  - `docs/wip/` содержит завершённые или полностью несинхронизированные планы
    (`monitoring-v2`, `homepage-redesign`, `helpdesk-archive-visibility`,
    `absence-presence`, `erp-sync`).
- **Ограничение:** исторические WIP всё ещё полезны как evidence; удалять их без
  отдельного решения нельзя.

## PA-017 — Generated frontend type migration снова неполна

- **Severity:** P3.
- **Статус:** **REMOTE_VERIFIED**; исходно был подтверждён contract-drift surface,
  а не фактический mismatch данных.
- **Remediation (2026-09-02, волна 2):** `api/directum.ts` — алиасы
  `components['schemas']['Directum*']`; DirectumRun = Omit+уточнения
  (литералы status/triggered_by, типизированный report-blob, схемы которого
  нет в OpenAPI); `api/bootstrap.ts` = `BootstrapOut & { user: UserMe }`,
  GalleryLinks = GalleryLinksOut (has_*/allowed_iframe_origins уже в
  BrandingSettingsOut); DirectumSettings.vue — `?? null` для optional-полей
  generated-схемы. Typecheck/lint/vitest зелёные.
- **Контур:** frontend API clients.
- **Evidence:** `frontend/src/api/directum.ts:11-89` вручную дублирует имеющиеся
  generated `Directum*` schemas; `frontend/src/api/bootstrap.ts:6-29` вручную
  описывает имеющийся `BootstrapOut`.
- **Impact:** будущий backend contract drift не обязан становиться TypeScript
  ошибкой в этих клиентах.

## PA-018 — Poison record блокирует всю очередь аудита

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**; живой Redis не инспектировался.
- **Remediation (2026-09-02):** PR #185, смёржено через #189 — позаписное
  декодирование, bounded quarantine (`audit_quarantine`, ltrim 1000) + error-лог
  с sample; characterization malformed+valid. Остаток: живой Redis не
  инспектировался (poison-записей в проде не наблюдалось и не утверждается).
- **Контур:** audit log / Redis-to-PostgreSQL delivery.
- **Impact:** одна невалидная JSON-запись в `audit_processing` приводит к ошибке
  каждого последующего запуска `flush_audit_queue`. Запись не удаляется и не
  переносится в dead-letter, поэтому валидные события за ней перестают доходить
  до PostgreSQL до ручного вмешательства в Redis.
- **Evidence:**
  - `backend/app/worker/tasks/audit.py:63-74` всегда сначала повторно читает весь
    `audit_processing`, затем декодирует batch одним list comprehension;
  - исключение попадает в общий handler `:105-107`, который пишет лог и повторно
    бросает исключение, но не изолирует malformed item;
  - удаление processing-list выполняется только после успешной вставки на
    `:103-104`;
  - `backend/tests/unit/test_worker_tasks.py:56-154` проверяет lock, empty,
    валидную вставку и release lock при исключении, но не recovery после
    malformed payload.
- **Risk boundary:** штатные producers сериализуют JSON; poison record требует
  ошибки/несовместимости producer, повреждения Redis или сторонней записи. Это
  не доказательство уже потерянных production-событий.
- **Минимальный remediation scope:** per-record validation с quarantine/DLQ,
  счётчиком и алертом; валидные записи batch не должны блокироваться одной
  невалидной.
- **Verification:** characterization test с malformed + valid records и второй
  flush; malformed остаётся диагностируемой, valid сохраняется ровно один раз.

## PA-019 — Grafana по умолчанию доступна в сети с `admin/admin`

- **Severity:** P2.
- **Статус:** CONFIRMED → **ACCEPTED RISK** (решение владельца, 2026-09-02).
- **Обоснование владельца:** смена admin-пароля Grafana — обязательный шаг
  при запуске и делается оператором сразу; `GRAFANA_BIND=0.0.0.0` —
  осознанный выбор: Grafana — сервис отображения, loopback-бинд лишает его
  смысла. Risk boundary из карточки (риск — только окно между первым стартом
  на свежем volume и первым входом оператора) принимается. Remediation-кода
  не требует; если политика изменится — вернуться к fail-closed preflight
  (отвергать дефолтный пароль в prod-профиле).
- **Контур:** monitoring / administrative UI / fresh deployment.
- **Impact:** на свежем `grafana-data` Grafana слушает все интерфейсы и принимает
  общеизвестные credentials до первого входа. Любой пользователь внутренней
  сети/VPN, успевший войти раньше оператора, может занять admin-account и получить
  доступ к observability data/configuration.
- **Evidence:**
  - `monitoring/docker-compose.monitoring.yml:130-156` задаёт
    `GF_SECURITY_ADMIN_USER=admin`, `GF_SECURITY_ADMIN_PASSWORD=admin` и
    `GRAFANA_BIND=0.0.0.0` по умолчанию;
  - `.env.example:153-170` сохраняет эти production-достижимые defaults;
  - `setup.sh:1982,2164-2167` после старта публикует сетевой URL и прямо сообщает
    `admin/admin`;
  - production preflight не проверяет `GRAFANA_ADMIN_PASSWORD`/`GRAFANA_BIND`.
- **Risk boundary:** overlay опционален, портал intranet/VPN-only; риск относится
  прежде всего к первому запуску на новом volume. На существующем volume env-
  пароль уже не меняет сохранённую учётку.
- **Минимальный remediation scope:** production fail-closed для default password
  либо loopback default до явной настройки; generated random bootstrap secret
  должен передаваться оператору без записи в git/log.
- **Verification:** fresh-volume deploy с production profile не публикует Grafana
  с default credentials; negative login и bind check до ручного enablement.

## PA-020 — Idempotency middleware превращает streaming upload в RAM buffer

- **Severity:** P1.
- **Статус:** **REMOTE_VERIFIED**; нагрузочный runtime-запрос не выполнялся.
- **Remediation (2026-09-02):** PR #181, смёржено через #189 — префикс
  `/files/folders/` удалён из захвата (у upload собственный user-scoped
  idempotency после auth); multipart и тела >10 МБ не буферизуются
  (pass-through + warning). Остаток: параллельный oversize-контрпример
  с замером RSS не выполнялся (unit-контракты покрыты).
- **Контур:** HTTP middleware / Files upload / availability.
- **Impact:** любой запрос с `Idempotency-Key` к Files upload полностью читается
  middleware в `bytes` до auth, ACL и endpoint rate-limit. Несколько параллельных
  больших запросов из внутренней сети/VPN могут исчерпать память backend workers;
  штатная потоковая проверка размера начинает работать только после буферизации.
- **Evidence:**
  - `backend/app/middleware/idempotency.py:22,138-159` включает весь prefix
    `/api/v1/files/folders/` и вызывает `_read_body` до downstream app;
  - `_read_body` на `:217-228` конкатенирует все ASGI chunks в один `bytes`;
  - upload route совпадает с prefix:
    `backend/app/api/files/upload.py:196-207`;
  - auth/ACL/rate-limit являются dependencies route и выполняются лишь после
    middleware; потоковый per-file limit читается на `upload.py:214-224`;
  - `SystemSettings.max_upload_size_mb` по умолчанию 100 и допускает до 1024:
    `backend/app/core/system_config/_schemas.py:78`;
  - этот upload дополнительно имеет собственный user-scoped idempotency cache на
    `upload.py:209-212,232-238`, то есть broad middleware для него не обязателен;
  - idempotency tests используют малые JSON bodies; large multipart/streaming
    counterexample не найден.
- **Risk boundary:** Nginx ограничивает полный request body системным лимитом и
  портал закрыт intranet/VPN; это снижает внешний exposure, но не устраняет
  до-auth memory amplification.
- **Минимальный remediation scope:** исключить multipart upload из generic body-
  fingerprint middleware и сохранить отдельную user-scoped upload idempotency;
  общий middleware должен иметь жёсткий ранний body/header limit.
- **Verification:** ASGI streaming test доказывает, что upload не читается
  middleware до auth/limit; параллельный oversize counterexample не увеличивает
  resident memory пропорционально полному body.

## PA-021 — ARQ cron executions не попадают в job-метрики

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**; live Prometheus series не проверялись.
- **Remediation (2026-09-02, волна 2):** `tracked_cron()` в worker/main.py —
  обёртка track_arq_job при сохранении имени регистрации `cron:<fqn>`
  (реестр/уникальность ARQ не меняются); 42 декларации переведены;
  refresh_custom_metrics/worker_heartbeat исключены (сами сборщики).
  Верификация: контракт-тест «каждая cron-задача обёрнута», реальное
  исполнение обёртки пишет started/succeeded/failed/duration в
  arq:metrics:job*; mutation (raw cron для flush_audit_queue) красит реестр.
  Scheduled-прогоны пишут те же серии, что ручные enqueue → существующий
  PortalArqJobFailures теперь их покрывает.
- **Контур:** worker observability / cron / alerts.
- **Impact:** `portal_arq_jobs_total` и duration отражают вручную enqueue'd
  wrapped functions, но не штатные scheduled executions. Падения audit flush,
  email/messenger dispatch, Helpdesk poller, ERP sync и других cron-задач не
  способны активировать общий `PortalArqJobFailures`; оператор получает
  неполную картину успешности фоновой обработки.
- **Evidence:**
  - `backend/app/worker/main.py:180-226` регистрирует wrapped functions, а
    `:227-510` отдельно создаёт 42 `cron("app.worker...")` из raw coroutine;
  - ARQ 0.28.0 присваивает строковому cron имя `cron:<FQN>` и хранит raw
    `CronJob.coroutine`; `Worker.run_cron` enqueue'ит именно `cron_job.name`;
  - следовательно, plain-name wrapper и `cron:<FQN>` — разные registry entries,
    а scheduled job вызывает raw coroutine без `track_arq_job`;
  - восемь cron-функций вообще отсутствуют в plain functions list, остальные
    34 имеют wrapper только для отдельного plain-name enqueue;
  - `backend/app/worker/tasks/metrics.py:60-118` является единственным writer
    `arq:metrics:jobs`/`job_ms`;
  - `docs/adr.md:1342` и `docs/monitoring.md:139-159` описывают эти метрики как
    покрытие ARQ-задач; `monitoring/alerts/portal.yml:368-376` строит failure
    alert только на них;
  - registry tests проверяют состав/расписание и имя wrapper, но не то, что
    реальный cron execution увеличивает метрики.
- **Ограничение:** отдельные contour-specific alerts (queue depth, heartbeat,
  outbox gauges, watchdog) частично компенсируют слепую зону; delivery failure
  в production не утверждается.
- **Минимальный remediation scope:** регистрировать cron с instrumented
  coroutine либо перенести instrumentation в общие ARQ hooks, сохранив исключения
  для самих metrics/heartbeat tasks.
- **Verification:** тест через реальный `Worker.run_cron`/job execution должен
  увеличить `started` и terminal status для scheduled function; failure обязан
  появиться в Prometheus series, достаточной для alert expression.

## PA-022 — Monitoring settings частично не являются runtime

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**; выбранное решение честно маркирует
  startup-only поля, runtime apply не добавлялся.
- **Remediation (2026-09-02, волна 2):** минимальный честный вариант (решение
  владельца — без межпроцессного runtime-apply): UI-подсказка log_level
  дополнена worker-оговоркой (остальные поля уже были маркированы честно);
  docs/monitoring.md §5 — матрица «поле × backend/worker: сразу/рестарт»;
  ADR-037 — уточнение к пункту Runtime; api-contracts.md — квалифицированное
  обещание вместо безусловного «без рестарта». Успешный PATCH теперь явно
  задокументирован как «сохранено», не «применено».
- **Контур:** Admin UI → system.json → backend/worker runtime.
- **Impact:** администратор получает успешное сохранение настроек и ожидает
  немедленное применение, но фактическое состояние процессов остаётся прежним.
  Это способно оставить `/metrics` включённым/выключенным не по UI, не изменить
  worker concurrency и сохранить старый формат/уровень worker-логов до restart.
- **Evidence:**
  - ADR-037 `docs/adr.md:1038-1043` и API contract
    `docs/api-contracts.md:1915-1970` обещают runtime JSON без restart;
  - Admin UI редактирует `prometheus_metrics_enabled`, `log_level`,
    `log_force_json`, `log_slow_request_ms`, `arq_max_jobs`:
    `frontend/src/pages/admin/tabs/MonitoringTab.vue:21-108,212-241`;
  - `/metrics` middleware ставится условно один раз при construction:
    `backend/app/middleware/__init__.py:31-53`;
  - backend/worker JSON renderer выбирается только при startup:
    `backend/app/main.py:20-27`, `backend/app/worker/main.py:73-81`;
  - worker concurrency фиксируется class attribute при import:
    `backend/app/worker/main.py:173-176`;
  - update side-effects в `backend/app/api/system_settings/_settings.py:50-70`
    обрабатывают только backend log level, timezone и Nextcloud cache; отдельный
    worker не уведомляется;
  - `log_slow_request_ms` читается на каждом запросе
    (`backend/app/middleware/logging.py:72-75`), а metrics token — на каждом
    scrape, поэтому дефект относится не ко всем runtime fields.
- **Ограничение:** процессы не перезапускались и UI не мутировался; вывод следует
  из отсутствия динамического apply path.
- **Минимальный remediation scope:** либо реализовать межпроцессное runtime apply
  с явной семантикой, либо честно пометить restart-required поля и организовать
  безопасный controlled restart; успешный API response должен отражать outcome.
- **Verification:** изменить каждое поле через API и проверить observable state
  backend + worker без restart, затем после restart; UI должен показывать
  pending/restart-required там, где hot apply невозможен.

## PA-023 — На backend readiness нет автоматической реакции

- **Severity:** P2.
- **Статус:** **REMOTE_VERIFIED**; live alert delivery и failure injection не
  выполнялись.
- **Remediation (2026-09-02, волна 2):** выбрана честная модель (решение
  владельца): gauge `portal_backend_ready` (ставится самим /ready) закрывает
  слепую зону «жив, но нездоров» (up{job}=1 не различает); алерт
  `PortalBackendUnhealthy` (==0, for 3m, critical); ADR-015 дополнен
  уточнением о фактической семантике и осознанном отсутствии авто-реакции
  (одиночный инстанс: исключение не повышает доступность); runbook
  «Backend unhealthy» в docs/monitoring.md §5. Тесты: /ready 200 → gauge 1,
  503 → gauge 0. Failure injection остаётся за оператором (runtime-приёмка).
- **Контур:** Docker Compose / backend health / Nginx routing.
- **Impact:** `/ready` корректно может перевести backend в `unhealthy`, но процесс
  продолжает работать и Nginx продолжает направлять ему трафик. Заявленный
  автоматический restart/exclusion отсутствует; восстановление и деградация
  зависят от поведения отдельных DB/Redis/Nextcloud clients и ручной реакции.
- **Evidence:**
  - `docker-compose.yml:164-220` задаёт backend `restart: unless-stopped` и
    healthcheck на `/ready`;
  - Nginx использует startup `depends_on: backend: service_healthy` на
    `docker-compose.yml:375-381`, затем статический upstream
    `backend:8000` (`nginx/templates/proxy_locations.conf.tmpl:2`);
  - нет watcher/autoheal/LB, читающего Docker health status;
  - ADR-015 `docs/adr.md:378-390` обещает, что Docker перезапустит контейнер или
    LB исключит его;
  - Docker restart policy применяется при остановке/exit контейнера, а Compose
    `service_healthy` — условие startup dependency, не runtime eviction
    ([Docker restart policy](https://docs.docker.com/engine/containers/start-containers-automatically/),
    [Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/)).
- **Risk boundary:** single-instance портал не имеет резервного backend, поэтому
  простое исключение всё равно не обеспечит доступность; некоторые зависимости
  самостоятельно восстанавливают соединения. Finding не утверждает, что restart
  всегда является правильной реакцией — только что заявленная реакция отсутствует.
- **Минимальный remediation scope:** определить честную модель: liveness для
  restart, readiness для наблюдаемого admission/LB либо явный alert/runbook;
  убрать ложное обещание автоматического healing.
- **Verification:** принудительный read-only-compatible failure injection в
  staging: `/ready` 503, inspect health, PID/start time и Nginx response path;
  затем проверить выбранную реакцию и восстановление.

## PA-024 — Ссылка восстановления LMS не открывает форму сброса

- **Severity:** P1.
- **Статус:** **SUPERSEDED** (2026-09-04): исходный дефект исправлялся в #179,
  но сам password-recovery flow затем удалён passwordless-переходом #212/#213.
- **Remediation (2026-09-02):** PR #179, смёржено через #189 — билдер пишет
  канонический `/reset`, в learn-роутере функциональный алиас `/reset-password`
  → `/reset` (query сохраняется) для писем до деплоя; сквозные тесты письма и
  алиаса.
- **Актуализация (2026-09-04):** миграция 114 удаляет
  `learning_password_resets` и парольные поля; API теперь реализует
  `login → verify`, а `/forgot`, `/reset` и `/reset-password` перенаправляются
  на login. Старый runtime reset-чеклист неприменим. Новый passwordless journey
  остаётся предметом этапа 2 и не считается автоматически проверенным этой
  карточкой.
- **Исходный baseline:** `origin/main@2e662df3`, 2026-09-01.
- **Исторический контур:** внешний LMS learner / forgot-password journey.
- **Исторический impact:** письмо после штатного `forgot` содержало ссылку
  `/reset-password?token=...`, но learn-приложение регистрирует форму только на
  `/reset`. Catch-all перенаправляет неизвестный путь к списку курсов, поэтому
  пользователь не попадает на форму и не может применить одноразовый токен.
- **Историческое evidence:**
  - email builder: `backend/app/services/learning/emails.py:66-84`;
  - зарегистрированный route: `frontend/src/learn/router.ts:24-29`;
  - форма действительно читает token из query и вызывает reset API:
    `frontend/src/learn/pages/LearnResetPage.vue:82-99`;
  - catch-all неизвестных путей ведёт в `learning`:
    `frontend/src/learn/router.ts:45-46`;
  - backend unit test закрепляет `/reset-password`, а frontend unit/E2E
    проверяют `/reset` отдельно; теста email-link → router → form нет.
- **Reproduction:** построить письмо через `password_reset_link`, открыть его URL
  в `createLearnRouter`; route name будет не `learn-reset`, token до формы не
  дойдёт. Реальное письмо не отправлялось и токен в БД не создавался.
- **Текущее evidence:** `backend/migrations/versions/114_drop_learning_password_relics.py`,
  `backend/app/api/learning/auth_routes.py`, `frontend/src/learn/router.ts:18-22`.
- **Остаточный scope:** не исправление PA-024, а отдельная проверка текущего
  passwordless flow и production Nginx topology в рамках этапа 2/PA-026.

## PA-025 — `learning_base_url` допускает небезопасный HTTP

- **Severity:** P1.
- **Статус:** **REMOTE_VERIFIED**; production value, rendered Nginx и реальный
  TLS/browser path не проверены.
- **Remediation (2026-09-02):** PR #179, смёржено через #189 — строгий
  HTTPS-origin валидатор на записи (`SystemSettingsIn/Patch`), хранимая модель
  осталась мягкой (жёсткий reject при загрузке ронял бы все настройки на
  дефолты), fail-closed рендер (`render-config.sh`: не-HTTPS → контур
  disabled). **До CLOSED:** проверка rendered Nginx и ссылки зачисления в
  браузере без HSTS-кэша.
- **Исходный baseline:** `origin/main@2e662df3`, 2026-09-01.
- **Актуализация (2026-09-04):** reset-токены удалены вместе с password recovery,
  поэтому исходный token-leak impact больше неприменим. `learning_base_url`
  продолжает формировать публичные ссылки курсов/зачисления и входной TLS-контур;
  HTTPS-only invariant и runtime acceptance сохраняются.
- **Контур:** LMS public ingress / course and enrollment links.
- **Исторический impact:** администратор мог сохранить явный
  `http://learn...`; значение попадало в ссылки, включая reset-токен в query,
  до HTTPS redirect. Эта часть риска устранена как валидатором, так и последующим
  удалением password recovery.
- **Исходное evidence:**
  - validator лишь добавляет `https://`, когда scheme отсутствует, но не
    запрещает явный HTTP или иной scheme:
    `backend/app/core/system_config/_schemas.py:113-125`;
  - runtime setting сохраняется через Admin API:
    `backend/app/api/system_settings/_settings.py:126-155`;
  - email/reset links использовали значение напрямую:
    `backend/app/services/learning/accounts_service.py:44-49,368-370` и
    `backend/app/services/learning/emails.py:66-76`;
  - renderer принимает и `https://`, и `http://`, затем создаёт HTTPS-блок и
    redirect: `nginx/render-config.sh:151-190`,
    `nginx/templates/learn_server.conf.tmpl:12-25`;
  - unit test проверяет только normalization без scheme; отрицательного теста
    на HTTP/credentials/path/query нет.
- **Risk boundary:** HSTS может защитить ранее посещавший этот host браузер, но
  не является гарантией первого перехода. Реальная настройка production и TLS
  chain не проверялись.
- **Текущее evidence:** `_validate_https_learning_base` отклоняет non-HTTPS,
  credentials, path, query и fragment; `courses_service.py` использует base URL
  для ссылок курсов. Passwordless login email содержит код, а не URL.
- **Verification:** Admin API отвергает non-origin/non-HTTPS варианты; ссылка
  зачисления содержит канонический HTTPS origin; rendered Nginx и browser
  переход проверены на новом профиле без HSTS cache.

## PA-026 — Learn E2E проверяет не production ingress topology

- **Severity:** P2.
- **Статус:** CONFIRMED test-architecture gap; remote baseline job inspected,
  текущая topology статически перепроверена 2026-09-04.
- **Проверено:** исходно `origin/main@2e662df3`, Forgejo run 1205/job 20356,
  2026-09-01; статически перепроверено на `origin/main@a872f880`, 2026-09-04.
- **Контур:** LMS public ingress / browser regression protection.
- **Impact:** обязательный E2E может быть зелёным при сломанном Nginx allowlist,
  TLS/redirect или SPA fallback. Более того, setup/cleanup learner suite намеренно
  вызывает административные LMS endpoints через learn-origin — поведение,
  которое production boundary должна запрещать. Это по-прежнему скрывает
  регрессии allowlist из PA-003.
- **Evidence:**
  - CI запускает `vite preview` как отдельный learn web server, не Nginx:
    `frontend/playwright.config.ts:23-26,92-116`,
    `.forgejo/workflows/ci.yml:1175-1201`;
  - preview proxy без allowlist отправляет весь `/api` в backend:
    `frontend/vite.config.learn.ts:44-53`;
  - learner E2E на том же learn-origin создаёт/публикует/удаляет курс и создаёт
    учётку через `/learning/admin/*`:
    `frontend/tests/e2e/learn-learner.spec.ts:54-96,159-168`;
  - remote E2E job: 80 passed, 0 skipped, 0 flaky/retried; зелёный результат
    сосуществовал с PA-003/PA-024 именно из-за topology gap;
  - текущий learner E2E читает passwordless-код напрямую из `email_outbox`, но
    продолжает запускаться через Vite preview и выполнять admin setup через
    learn-origin.
- **Risk boundary:** suite полезно проверяет production build, learner UI/API и
  browser states; finding не обесценивает эти проверки. Не доказано, что
  production Nginx сейчас развёрнут или доступен извне.
- **Минимальный remediation scope:** разделить data seeding (direct backend/DB
  fixture вне public origin) и learner journey; хотя бы один required suite
  должен идти через реально rendered Nginx learn server с exact negative routes,
  TLS/Host и SPA fallback.
- **Verification:** через learn-host learner/meta/auth доступны, admin/portal API
  получают Nginx 404 без backend hit; passwordless login/verify и SPA fallback
  проходят через rendered Nginx. В логе явно фиксируются pass/skip/retry counts.

## Неподтверждённые и принятые риски

### PA-U01 — Redundant indexes

- **Статус:** UNVERIFIED.
- Кандидаты в моделях существуют, но performance/write impact не доказан без
  production-like `EXPLAIN ANALYZE` и `pg_stat_user_indexes`.
- Не переносить в remediation backlog как подтверждённый дефект.

### PA-U02 — Module-level `get_settings()`

- **Статус:** ACCEPTED RISK.
- Pattern подтверждён и встречается шире старой карточки, но конкретный текущий
  failure mode тест-изоляции не воспроизведён. Предыдущее решение — отложить DI
  migration до реальной боли.

### PA-U03 — KDF для `SECRET_KEY`

- **Статус:** UNVERIFIED.
- Для high-entropy server secret простой SHA-256 сам по себе не доказывает
  практическую слабость. Подтверждённая проблема вынесена отдельно в PA-011:
  separation/versioning/rotation.

### PA-U04 — Конкурентный submit одной попытки

- **Статус:** UNVERIFIED, требует controlled DB counterexample.
- Два запроса сначала читают attempt без lock
  (`backend/app/api/learning/me_routes.py:368-378`), затем сериализуются на
  course row. Второй request уже держит stale ORM instance; повторный SELECT в
  `tests_service.submit_attempt` не содержит `FOR UPDATE`/`populate_existing`.
  Возможный результат — второй submit не увидит `submitted_at` первого и
  перезапишет ответы/score вместо 409.
- Последовательный test существует, но две независимые sessions и одновременный
  submit не покрыты. До воспроизведения не считать установленным дефектом и не
  включать в remediation backlog.
- Способ закрытия: controlled integration test с двумя sessions, наблюдаемым
  lock wait и разными ответами; второй запрос обязан получить 409, сохранённый
  результат обязан принадлежать первому.

## Coverage плана, требующий явного dossier

Это не product findings, а уточнение дальнейшего аудита:

- Notifications/SSE должны получить отдельный dossier, а не проверяться только
  как часть News/KB/Meetings.
- Audit log/admin export/partition lifecycle должны получить отдельный dossier.
- Email outbox и Messenger outbox проверяются один раз как shared infrastructure,
  а в модулях проверяются только producer/consumer contracts.
- ERP absences/current presence явно включаются в identity/integrations stage.
- Bootstrap, system settings, modules, health и Keycloak admin фиксируются как
  отдельные platform surfaces этапа 1.
