# Аудит портала — План работ

> **Создан:** 2026-07-26
> **Аудитор:** Senior Architect (ZCode)
> **Версия кода:** `da8d5f2` (main)
> **Масштаб аудита:** backend ~59k LOC Python · frontend ~85k LOC (Vue+TS) · 85 миграций · ~290 endpoints · 9 сервисов в docker-compose
> **Метод:** 5 параллельных экспертных субагентов (Security / Backend-architecture / DB-perf / Frontend / Infra) + личная cross-верификация каждой ключевой находки чтением кода
> **Предыдущие итерации:** `docs/code-audit.md` (4 раунда: 2026-06-06 → 2026-07-20). Все P0/P1 прошлых раундов закрыты — этот план содержит **только новые/подтверждённые** находки.
> **Статус:** 🟢 готов к работе. Берите задачи сверху вниз по этапам.

---

## TL;DR

Проект **выше среднего по индустрии** (качество 8/10, архитектура 8/10). Глобальный рефакторинг **не нужен**. Найдено **~40 реальных находок** после фильтрации ложных:

- **2 Critical** — оба в инфраструктуре/конфигурации (не в бизнес-коде)
- **12 High** — security (1), DB-perf (3), архитектура (4), инфра (4)
- **~22 Medium / Low**

Базовая гигиена образцовая: ruff/mypy/eslint/vue-tsc/bandit чисто, radon ≤ C, дубли ~2%, 0 `: any`/`@ts-ignore` во frontend.

**С чего начать:** Этап 1 (Quick Wins) — 11 задач за 1–2 дня закрывают 2 Critical, 5 High, большую часть Medium-инфра. Максимальный ROI без риска регрессии.

---

## Общие оценки

| Ось | Оценка | Комментарий |
|---|---|---|
| **Качество проекта** | **8/10** | Зрелая кодовая база. −1 балл за инфра-гигиену (Redis root, дефолты в `.env.example`) и за накопленный техдолг в helpdesk/email-подсистеме. |
| **Архитектурная зрелость** | **8/10** | Слоистость, outbox-pattern, ADR-037, partitioning — на месте. −1 балл за цикл worker→api, half-done `EventType` enum, God-модуль `keycloak_admin.py`, sync I/O в async. |

---

## Как работать с этим планом

### Статусы задач
- `[ ]` — todo (не начато)
- `[~]` — in-progress (в работе)
- `[x]` — done (готово, проверено)
- `[—]` — отклонено/не делаем (с обоснованием в Notes)

### Конвенция карточек
Каждая задача имеет **уникальный ID** (`[C1]`, `[H2]`, `[M14]`, `[L3]`) — используйте его в коммит-сообщениях и PR: `fix(security): [H1] SSRF in bookmarks favicon`. Карточка самодостаточна — её можно взять в работу без чтения всего файла.

### Порядок выполнения
1. **Этап 1 (Quick Wins)** — параллельно, любой порядка, низкий риск.
2. **Этап 2 (Medium)** — последовательно, с characterization-тестом первым.
3. **Этап 3 (Architectural)** — по согласованию с team, через feature-flag.
4. **Этап 4 (Long-term)** — плановые спринты, не срочно.

### Перед каждой задачей
1. Прочитай **карточку целиком** + раздел «Где» (открой указанные файлы:строки).
2. Прочитай `AGENTS.md` соответствующий раздел (модульный док если задача модульная).
3. Если задача DB/perf — сначала проведи `EXPLAIN ANALYZE` на проде, потом пиши фикс.
4. Если задача с UI-нюансом — согласуй с владельцем продукта (помечено ⚠️).

### После каждой задачи
1. Прогон: `cd backend && ./scripts/ci_lint.sh && pytest tests/unit`
2. Прогон: `cd frontend && npm run lint:check && npm run typecheck && npm run test:unit`
3. Обнови статус в карточке (`[x]`) + дату в «Истории изменений».
4. В коммит-сообщении укажи ID задачи.

---

## Дорожная карта (Roadmap)

### 🟢 Этап 1 — Quick Wins (1–2 дня, низкий риск)
XS-S правки, не требующие архитектурных решений. Параллелятся.

- **[C1]** `.env.example` дефолт-секреты + валидатор `Settings` · XS · критично · [ ] ⚠️прод
- **[C2]** Redis `user:` в compose · S · критично · [ ] ⚠️прод
- **[H2]** news ILIKE → FTS · XS · **[x] сделано**
- **[H5]** worker→api цикл · S · **[x] сделано**
- **[H10]** `redact_secrets_processor` расширить · XS · **[x] сделано**
- **[H11]** Pin GitHub Actions по SHA · S · **[x] сделано**
- **[H12]** Backup retention · S · [ ] ⚠️прод
- **[M5]** Drop redundant indexes · S · [ ] ⚠️прод
- **[M10]** Magic numbers → constants · XS · **[x] частично** (email_outbox; осталось: email_images, notifications)
- **[M15]** Dockerfile DRY · S · **[x] сделано**
- **[M16]** Compose volumes DRY · XS · **[—] отклонено**
- **[M19]** useModulesState watchers · XS · **[x] сделано**
- **[L8]** _role_prefix dead params · XS · **[x] сделано**
- **[L11]** docstring typo · XS · **[x] сделано**
- **[L12]** PollPanelVoting i18n fallback · XS · **[x] сделано**
- **[L15]** proxy_connect_timeout · XS · **[x] сделано**
- **[L17]** coverage-comment fork guard · XS · **[x] сделано**
- **[L18]** logging non-blocking · XS · **[—] отклонено**

### 🟡 Этап 2 — Средний рефакторинг (1–2 недели)
Требуют characterization-тестов, локализованы.

- **[H1]** SSRF favicon · M · **[x] сделано**
- **[H3]** audit metadata::text → jsonb GIN · S
- **[H8]** Silent except → `logger.debug`/`exc_info` · S
- **[H9]** PII-маскинг IP/телефоны · M
- **[M1]** Comments list/count consistency ⚠️ UX-согласование · S
- **[M2]** Keyset pagination audit/outbox · M
- **[M3]** Batch INSERT meetings outbox · M
- **[M4]** meetings bookings limit=100 · S
- **[M6]** Декомпозиция `_ingest_message` · M
- **[M9]** keycloak_admin God Module · M
- **[M14]** `HelpdeskAgentInboxPage.vue` → TanStack Query · M
- **[M12]** LinksTab.vue → composable · M
- **[M19]** `useModulesState` дублированный watcher · XS
- **[M20]** screenshot-service `/ready` · S
- **[M21]** gitleaks/trivy/ZAP pin versions · XS · **[x] сделано**
- **[M22]** `migrate_env_to_system_settings` race · S · **[x] сделано**

### 🟠 Этап 3 — Архитектурные изменения (3–6 недель)
Командное решение + rollout-стратегия.

- **[H4]** Async I/O фасад · M (12 модулей)
- **[H6]** `EventType` enum — довести или удалить ⚠️ decision · M/S
- **[H7]** enum для role/status/direction · M (~50 мест)
- **[M7]** helpdesk email/notification в Jinja2 · M
- **[M8]** generic `dataset_endpoint` analytics · S-M
- **[M11]** Service Locator → DI · M (11 модулей)
- **[M13]** frontend api/*.ts → generated types · M
- **[M17]** `secret_crypto` KDF + key-versioning · L

### 🔵 Этап 4 — Долгосрочные (квартал+)
К росту, не срочно.

- **[L2]** analytics Redis-кеш + daily-rollup
- **[M18]** nginx rate limiting
- **[L14]** digest-pinning всех base-образов
- **[L4]** distributed-lock на outbox watchdog
- **[L1-L18]** мелкие code smells

---

## Сводная таблица задач

| ID  | Приоритет | Категория | Задача | Сложн. | Этап | Статус |
|-----|-----------|-----------|--------|--------|------|--------|
| C1  | 🔴 Critical | Config/Sec | `.env.example` дефолт-секреты | XS | 1 | [ ] ⚠️ прод |
| C2  | 🔴 Critical | Docker/Sec | Redis от root | S | 1 | [ ] ⚠️ прод |
| H1  | 🟠 High | Security | SSRF favicon | M | 2 | [x] 2026-07-27 |
| H2  | 🟠 High | DB/Perf | news ILIKE → FTS | XS | 1 | [x] 2026-07-26 |
| H3  | 🟠 High | DB/Perf | audit metadata::text → jsonb GIN | S | 2 | [ ] |
| H4  | 🟠 High | Backend | Sync I/O в async | M | 3 | [ ] |
| H5  | 🟠 High | Architecture | worker→api цикл | S | 1 | [x] 2026-07-26 |
| H6  | 🟠 High | Architecture | EventType enum half-done | M/S | 3 | [ ] ⚠️ decision |
| H7  | 🟠 High | Code Smell | Primitive Obsession (строки) | M | 3 | [ ] |
| H8  | 🟠 High | Backend/Obs | silent except | S | 2 | [x] 2026-07-26 частично |
| H9  | 🟠 High | Logging | PII-маскинг | M | 2 | [ ] |
| H10 | 🟠 High | Logging | redact_secrets_processor | XS | 1 | [x] 2026-07-26 |
| H11 | 🟠 High | CI/CD | Pin Actions по SHA | S | 1 | [x] 2026-07-26 |
| H12 | 🟠 High | Infra | Backup retention | M | 1 | [ ] ⚠️ прод |
| M1  | 🟡 Medium | DB | Comments list/count ⚠️UX | S | 2 | [ ] ⚠️ decision |
| M2  | 🟡 Medium | Perf | OFFSET → keyset | M | 2 | [ ] |
| M3  | 🟡 Medium | Perf | Batch INSERT outbox | M | 2 | [ ] |
| M4  | 🟡 Medium | Perf | meetings limit=100 | S | 2 | [x] 2026-07-27 |
| M5  | 🟡 Medium | DB | Drop redundant indexes | S | 1 | [ ] ⚠️ прод |
| M6  | 🟡 Medium | Code Smell | `_ingest_message` Long Method | M | 2 | [ ] |
| M7  | 🟡 Medium | Code Smell | helpdesk email/notification sprawl | M | 3 | [ ] |
| M8  | 🟡 Medium | Code Smell | analytics boilerplate | S-M | 3 | [ ] |
| M9  | 🟡 Medium | Architecture | keycloak_admin God Module | M | 2 | [ ] |
| M10 | 🟡 Medium | Code Smell | Magic numbers | XS | 1 | [x] 2026-07-26 |
| M11 | 🟡 Medium | Architecture | Service Locator → DI | M | 3 | [ ] ⚠️ decision |
| M12 | 🟡 Medium | Frontend | LinksTab.vue composable | M | 2 | [ ] |
| M13 | 🟡 Medium | Frontend | api/*.ts → generated types | M | 3 | [ ] |
| M14 | 🟡 Medium | Frontend | HelpdeskAgentInboxPage → Query | M | 2 | [ ] |
| M15 | 🟡 Medium | Docker | Dockerfile DRY | S | 1 | [x] 2026-07-26 |
| M16 | 🟡 Medium | Docker | Compose volumes DRY | XS | 1 | [—] 2026-07-26 отклонено |
| M17 | 🟡 Medium | Config | secret_crypto KDF | L | 3 | [ ] ⚠️ прод |
| M18 | 🟡 Medium | Infra | nginx rate limiting | S | 4 | [ ] ⚠️ прод |
| M19 | 🟡 Medium | Frontend | useModulesState watchers | XS | 2 | [x] 2026-07-26 |
| M20 | 🟡 Medium | Docker | screenshot-service /ready | S | 2 | [x] 2026-07-26 |
| M21 | 🟡 Medium | CI/CD | gitleaks/trivy/ZAP pin | XS | 2 | [x] 2026-07-27 (ZAP добавлен) |
| M22 | 🟡 Medium | Config | migrate_env race | S | 2 | [x] 2026-07-26 |
| L1  | 🟢 Low | DB | миграции zero-downtime паттерн | XS | 4 | [ ] |
| L2  | 🟢 Low | Perf | analytics Redis-кеш | M | 4 | [ ] |
| L3  | 🟢 Low | Perf | search offset лимит | XS | 4 | [x] 2026-07-26 |
| L4  | 🟢 Low | DB | outbox watchdog lock | XS | 4 | [x] 2026-07-26 |
| L5  | 🟢 Low | Perf | news selectinload(poll) | XS | 4 | [—] 2026-07-26 false-positive |
| L6  | 🟢 Low | Code Smell | Pagination Deps | XS | 4 | [—] 2026-07-26 отклонено |
| L7  | 🟢 Low | Security | keycloak_admin allowlist | M | 4 | [ ] |
| L8  | 🟢 Low | Code Smell | _role_prefix dead params | XS | 4 | [x] 2026-07-26 |
| L9  | 🟢 Low | Code Smell | openpyxl Feature Envy | XS | 4 | [x] 2026-07-26 частично |
| L10 | 🟢 Low | Code Smell | CcRecipient Pydantic | S | 4 | [x] 2026-07-26 |
| L11 | 🟢 Low | Docs | опечатки в docstrings | XS | 4 | [x] 2026-07-26 |
| L12 | 🟢 Low | i18n | PollPanelVoting fallback | XS | 4 | [x] 2026-07-26 |
| L13 | 🟢 Low | Frontend | useFilesData type cast | S | 4 | [x] 2026-07-27 |
| L14 | 🟢 Low | Docker | digest pinning | S | 4 | [x] 2026-07-27 |
| L15 | 🟢 Low | Infra | proxy_connect_timeout | XS | 4 | [x] 2026-07-26 |
| L16 | 🟢 Low | Config | _get_fernet thread-safety | XS | 4 | [x] 2026-07-26 |
| L17 | 🟢 Low | CI/CD | coverage-comment fork guard | XS | 4 | [x] 2026-07-26 |
| L18 | 🟢 Low | Docker | logging non-blocking mode | XS | 4 | [—] 2026-07-26 отклонено |

### Условные обозначения статусов
- `[x]` — выполнено и проверено (тесты + lint зелёные)
- `[—]` — отклонено с обоснованием (см. карточку)
- `⚠️ прод` — требует действий на продакшене (см. раздел «Инструкция для продакшена»)
- `⚠️ decision` — требует решения команды перед реализацией

---

## 🔴 CRITICAL

### [C1] — `.env.example` содержит production-опасные дефолты `[verified]`
- **Категория:** Configuration / Security
- **Приоритет:** 🔴 Critical
- **Где:** `.env.example:39,53,58-59`; `backend/app/core/config.py:32`; `backend/app/core/bootstrap.py`
- **Что найдено:** `SECRET_KEY=change_me_32_chars_minimum_secret_key_here` (42 chars — проходит `min_length=32`, но публично известен), `LOCAL_AUTH_ENABLED=true` (открывает backdoor по умолчанию), `ADMIN_EMAIL=admin@company.local` + `ADMIN_PASSWORD=change_me_on_first_login` + `ADMIN_PASSWORD_RESET_ON_START=false`. Bootstrap создаёт этого admin'а валидным при первом старте.
- **Почему проблема:** Оператор, копирующий `.env.example` → `.env` без аккуратной правки, получает предсказуемый admin-account и публично известный `SECRET_KEY`. Через `SECRET_KEY` деривируется Fernet-ключ (`secret_crypto.py`) → компрометация всех helpdesk-mailbox паролей at-rest. Не уязвимость текущего прода, а **бора для новых деплоев**.
- **Последствия:** Полный admin-доступ злоумышленника из периметра; необратимая компрометация шифрования-at-rest.

#### План действий
- [ ] В `.env.example`:
  - [ ] `LOCAL_AUTH_ENABLED=false` (backdoor закрыт по умолчанию)
  - [ ] `ADMIN_EMAIL=` (пусто)
  - [ ] `ADMIN_PASSWORD=` (пусто)
  - [ ] `SECRET_KEY=<RUN: openssl rand -hex 48>` с инструкцией в комментарии
- [ ] В `backend/app/core/config.py` (`Settings`) добавить валидатор:
  - [ ] При `environment == "production"` — block-list для `SECRET_KEY` (значения из `.env.example`/`ci-*`)
  - [ ] При `environment == "production"` — `len(SECRET_KEY) >= 48`
  - [ ] При `environment == "production"` — reject если `ADMIN_PASSWORD == "change_me_on_first_login"`
- [ ] В `setup.sh::preflight()` для prod-профиля — отказ стартовать с дефолтными значениями (по аналогии с semver-lock ADR-047)
- [ ] Unit-тест: `tests/unit/test_config_validation.py` — каждый кейс валидатора

#### DoD
- [ ] `cp .env.example .env && docker compose up` на fresh-инсталляции в prod-профиле → отказ с понятной ошибкой
- [ ] Существующий prod-`.env` не затронут (наличие block-list не ломает валидные ключи)
- [ ] Тесты зелёные

- **Сложность:** XS
- **Риск регрессии:** Очень низкий — существующие проды не затронуты.
- **Ожидаемый эффект:** Защита новых деплоев от «забыл сменить дефолт».
- **Статус:** [ ] ⚠️ прод — см. раздел «Инструкция для продакшена»

---

### [C2] — Redis запускается от root в production `[verified]`
- **Категория:** Docker / Security
- **Приоритет:** 🔴 Critical
- **Где:** `docker-compose.yml:34-64` (сервис `redis`), образ `redis:7-alpine`
- **Что найдено:** У `redis` нет `user:`. Образ `redis:7-alpine` стартует процесс `redis-server` от `uid=0(root)` (ACL-файл монтируется в `/tmp/redis.acl` chmod 600 — root-owned). `no-new-privileges:true` не помогает (процесс уже root). Redis официально рекомендует запуск от unprivileged user.
- **Почему проблема:** Любая RCE в Redis (Lua sandbox escape, EVAL-инъекции, replica-exploits) → root внутри контейнера → утечка `REDIS_PASSWORD`, сессионных данных, idempotency-ключей; потенциал lateral movement по `portal_internal`.
- **Последствия:** Compromised Redis → compromised auth-сессии всего портала.

#### План действий
- [ ] Проверить UID redis-юзера: `docker run --rm redis:7-alpine id redis` (ожидается 999)
- [ ] Добавить в `docker-compose.yml` сервис `redis`: `user: "999:999"` (или `user: redis`)
- [ ] Проверить, что ACL-файл `/tmp/redis.acl` читается после дропа прав (если нет — пересоздать с правильным владельцем в entrypoint)
- [ ] Прогнать локально: `docker compose up redis && docker compose exec redis id` → ожидается `uid=999(redis)`

#### DoD
- [ ] `docker compose exec redis ps aux | head` показывает redis-server от uid≠0
- [ ] Healthcheck redis зелёный
- [ ] ACL-аутентификация работает (`docker compose exec redis redis-cli AUTH ... ` → OK)
- [ ] Приложение стартует, сессии работают

- **Сложность:** S
- **Риск регрессии:** Низкий. Стратегия: blue-green — проверить `id redis` в образе, поднять второй redis-контейнер с `user:`, прогнать healthcheck, переключить.
- **Ожидаемый эффект:** blast-radius компрометации Redis: root → unprivileged.
- **Статус:** [ ] ⚠️ прод — см. раздел «Инструкция для продакшена»

---

## 🟠 HIGH

### [H1] — SSRF через `GET /bookmarks/favicon` `[verified]`
- **Категория:** Security (SSRF)
- **Приоритет:** 🟠 High
- **Где:** `backend/app/api/bookmarks.py:58-135` (`_do_favicon_fetch`, `get_bookmark_favicon`)
- **Что найдено:** Эндпоинт принимает произвольный `?url=` от аутентифицированного юзера, проксирует на `{scheme}://{netloc}/favicon.ico` через `httpx.AsyncClient(follow_redirects=True, max_redirects=3)`. Проверяется только `scheme in (http,https)` и непустой `netloc`. **Нет проверки** на приватные диапазоны (10/8, 172.16/12, 192.168/16, 127/8, fc00::/7), loopback, link-local, **cloud-metadata `169.254.169.254`**, нет DNS-pinning (TOCTOU/DNS-rebinding). Кэш в Redis 7 дней → oracle-инструмент.
- **Почему проблема:** Контраст с `keycloak_admin.py:_is_unsafe_ip` и `screenshot-service` (где SSRF-фильтр уже есть) подтверждает — механизм в кодовой базе существует, но здесь не применён. Главный внешний SSRF-surface после периметра.
- **Последствия:** Reconnaissance интранета, утечка metadata-секретов в облаке, bypass network ACL, lateral movement.

#### План действий
- [x] Создать `backend/app/core/net_guard.py` — единый SSRF-guard (audit [H1]):
  - [x] `is_public_ip` / `is_safe_remote_url` — чистые функции (scheme + bare-IP + localhost; блок private/loopback/link-local/multicast/unspecified/reserved/cloud-metadata)
  - [x] `resolve_all_ips` / `assert_url_safe` — async DNS-резолв через `asyncio.get_running_loop().getaddrinfo` (требует все A/AAAA public)
  - [x] `resolve_stable_ip` — двойной резолв против DNS-rebinding (TOCTOU)
- [x] В `bookmarks.py:_do_favicon_fetch` — safe-fetcher по образцу `email_images._fetch_remote`:
  - [x] `follow_redirects=False` + ручной обход редиректов с re-валидацией каждого hop через `assert_url_safe` + `resolve_stable_ip`
  - [x] Возвращает `None` при SSRF-блокe (отличимо от network-error)
- [x] В `get_bookmark_favicon` — early SSRF-валидация на cache-MISS с negative-cache (ReDoS-защита)
- [x] Backward-compat shim: `email_images.is_safe_remote_url` / `_is_public_ip` → re-export из `net_guard` (консолидация в M9/отдельной задаче)
- [⚠️ отложено] Консолидация `keycloak_admin._is_unsafe_ip` → `net_guard` — задача **M9** (God Module, требует characterization-тестов keycloak test-endpoints). `keycloak_admin` использует **обратную** политику (private разрешены, Keycloak за VPN), так что прямой перенос невозможен без параметризации.
- [⚠️ отложено] Allowlist интранет-доменов — не понадобился (UX-влияние минимально, UI уже рендерит `<n-icon>LinkOutline</n-icon>` при 404)
- [x] Unit-тесты: приватные IP / loopback / cloud-metadata / IPv6 / public / DNS-rebinding / redirect-to-private (95 тестов: 55 в `test_net_guard.py` + 40 в `test_bookmarks_favicon.py`)

#### DoD
- [x] Тест: `GET /bookmarks/favicon?url=http://10.0.0.1/` → 404, fetcher не вызывается (`test_blocked_ranges_return_404_without_fetch`)
- [x] Тест: `GET /bookmarks/favicon?url=http://169.254.169.254/latest/meta-data/` → 404 (тот же параметризованный тест)
- [x] Тест: DNS-rebinding (mock resolve_stable_ip → None) → блокируется (`test_dns_rebinding_blocked_in_fetcher`)
- [x] Тест: redirect-to-private (302 → 127.0.0.1) → блокируется, второй httpx-запрос не уходит (`test_redirect_to_private_blocked`)
- [x] Легитимные public-домены продолжают работать (`test_legitimate_public_domain_still_works`)
- [x] `net_guard.py` используется в bookmarks и email_images (re-export). keycloak_admin оставлен до M9 (обратная политика)
- [x] Negative-cache SSRF-blocked URL (ReDoS-защита): `test_ssrf_block_writes_negative_cache`

- **Сложность:** M
- **Риск регрессии:** Средний — favicon для интранет-доменов внутри VPN (Nextcloud/Keycloak по private-IP) перестаёт работать → рендерится `<n-icon>LinkOutline</n-icon>` (UI-fallback уже был). Смягчение: allowlist можно добавить отдельной правкой если UX пострадает.
- **Ожидаемый эффект:** Закрытие главного внешнего SSRF-surface.
- **Статус:** [x] 2026-07-27 — выполнено. Новый модуль `app/core/net_guard.py` (~170 LOC: 5 функций + документация). `bookmarks._do_favicon_fetch` переписан: `follow_redirects=False` + ручной обход с re-валидацией hop'ов + double-resolve против DNS-rebinding. Early-check на cache-MISS с negative-cache (ReDoS-защита). Backward-compat shim в `email_images.py` (`is_safe_remote_url as is_safe_remote_url` re-export для `no_implicit_reexport`). 95 тестов (55 net_guard + 40 favicon, включая 9 параметризованных SSRF-range + redirect-to-private + DNS-rebinding + negative-cache). Консолидация `keycloak_admin` отложена к M9 (обратная политика private-IP). Верификация: ci_lint ✓ (698 файлов), 3895 unit-тестов ✓ (+69), 14 integration ✓ (bookmarks + helpdesk).


---

### [H2] — ILIKE-поиск вместо готового FTS на новостях `[verified]`
- **Категория:** Database / Performance
- **Приоритет:** 🟠 High
- **Где:** `backend/app/services/news/crud.py:55-59` (`get_news_list`); вызов из `api/news/routes.py:71-90` (`GET /news?q=`)
- **Что найдено:**
  ```python
  pattern = f"%{q}%"
  stmt = stmt.where(or_(News.title.ilike(pattern), News.body.ilike(pattern)))
  ```
  В таблице `news` уже есть GIN-индекс `idx_news_fts` на `body_tsvector` и конфигурация `russian_hunspell`. `ILIKE '%..%'` не использует GIN — всегда Seq Scan. В `api/search.py` тот же поиск уже через `plainto_tsquery('russian_hunspell', q)` — механизм есть, в list-endpoint'е просто не применили.
- **Почему проблема:** На малом объёме незаметно. При росте (>1k, активный поиск) — каждый запрос сканирует всю `news` включая огромное `body` (Markdown) → рост CPU/latency.
- **Последствия:** Деградация поиска новостей при росте.

#### План действий
- [ ] На проде: `EXPLAIN ANALYZE SELECT ... WHERE body ILIKE '%отчёт%'` → сохранить baseline
- [ ] Заменить в `services/news/crud.py:55-59`:
  ```python
  if q:
      tsq = func.websearch_to_tsquery("russian_hunspell", q)
      stmt = stmt.where(or_(
          News.body_tsvector.op("@@")(tsq),
          News.title.ilike(f"%{q}%"),  # title короткий, ILIKE допустим
      ))
  ```
- [ ] На проде: `EXPLAIN ANALYZE` с новой версией → сравнить с baseline
- [ ] Unit-тест: `tests/unit/test_news_search.py` — поиск по слову в body

#### DoD
- [ ] `EXPLAIN ANALYZE` показывает Bitmap Index Scan по `idx_news_fts` вместо Seq Scan
- [ ] Поиск находит новости по лемме (hunspell): «отчёты» находит «отчёт»
- [ ] Тест зелёный

- **Сложность:** XS
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** 10–100× на росте; бесплатная лемматизация.
- **Статус:** [x] 2026-07-26 — выполнено (services/news/crud.py:55-64)

---

### [H3] — `audit_log` metadata::text ILIKE игнорирует GIN-индекс
- **Категория:** Database / Performance
- **Приоритет:** 🟠 High
- **Где:** `backend/app/api/audit.py:60-65` (`_build_filters`); `audit_repo.py:39-44,58-67`
- **Что найдено:** Поиск по `audit_log`: `coalesce(metadata::text,'') ILIKE :q`. `metadata::text` — сериализация всей JSONB-строки. На партиционированной таблице это Seq Scan по каждой партиции. GIN-индекс `idx_audit_log_metadata_gin` (миграция 033) **уже создан**, но не используется.
- **Почему проблема:** `audit_log` — самая быстрорастущая таблица, retention 12 мес. За год 1–5 млн строк. На admin-Audit tab и CSV-экспорте до 100k строк → таймауты.
- **Последствия:** Таймауты на admin Audit tab при >500k строк.

#### План действий
- [ ] На проде: `EXPLAIN ANALYZE SELECT ... WHERE coalesce(metadata::text,'') ILIKE '%admin%'` → baseline
- [ ] Решение (выбрать одно):
  - **(A)** Для metadata — `metadata @? :jsonpath` или `metadata::jsonb @@ :jsonb_query` (использует GIN)
  - **(B)** Вынести ILIKE по `metadata::text` в опциональный флаг `?extended_search=true`, по умолчанию только `user_email`/`resource_title` (btree+trgm)
- [ ] На проде: `EXPLAIN ANALYZE` с новой версией
- [ ] Integration-тесты с разными `q`: email, title, metadata-поле, несуществующее

#### DoD
- [ ] `EXPLAIN ANALYZE` показывает GIN-scan вместо Seq Scan
- [ ] Поиск по metadata работает (согласовать с админами scope)
- [ ] Тесты зелёные

- **Сложность:** S
- **Риск регрессии:** Средний — сохранить гибкость admin-поиска.
- **Ожидаемый эффект:** −1 партиция Seq Scan на запрос; 5–50× на больших объёмах.
- **Статус:** [ ]

---

### [H4] — Синхронное файловое I/O в async-эндпоинтах
- **Категория:** Backend / Performance
- **Приоритет:** 🟠 High
- **Где:** 12+ мест:
  - `backend/app/api/keycloak_admin.py:138,146,150,160` (`_load_kc_settings`/`_save_kc_settings`)
  - `backend/app/api/system_settings/_tls.py:105`
  - `backend/app/services/files_acl_persistence.py:84-89`
  - `backend/app/services/files_shares_persistence.py:84-89`
  - `backend/app/core/system_config/_storage.py:45`
  - `backend/app/api/news_categories.py:83,117`
  - `backend/app/services/email_settings.py:56`
  - `backend/app/core/modules_config.py:147`
- **Что найдено:** В async-функциях вызываются синхронные `Path.write_bytes`/`read_text`/`os.chmod`/`json.load`/`json.dump`/`glob`/`rglob`. Самый показательный: `GET /admin/keycloak/settings` → `_load_kc_settings` → синхронно читает файл + парсит JSON, при legacy-миграции ещё `read_bytes`+`write_bytes`+`chmod`.
- **Почему проблема:** Sync disk/syscall блокирует event loop. На NFS/docker-volume латентность одной операции — десятки ms. При admin-запросах это замораживает обработку других запросов в воркере.
- **Последствия:** Periodic latency-spikes; труднодиагностируемая деградация (no traceback).

#### План действий
- [ ] Создать `backend/app/core/settings_storage.py` — async-фасад:
  - [ ] `async def read_json_atomic(path: Path) -> dict` (через `aiofiles` + `asyncio.to_thread(json.loads)`)
  - [ ] `async def write_json_atomic(path: Path, data: dict, *, mode: int = 0o600)`
  - [ ] `async def migrate_legacy(legacy: Path, current: Path)` для keycloak-settings
- [ ] Мигрировать каскадно (по одному модулю за PR):
  - [ ] PR1: `keycloak_admin.py` + system_config/_storage.py (высокая admin-нагрузка)
  - [ ] PR2: `news_categories.py` + `email_settings.py` + `modules_config.py`
  - [ ] PR3: `files_acl_persistence.py` + `files_shares_persistence.py` + `_tls.py`
- [ ] Каждый модуль: characterization-тест текущего поведения, миграция, тест снова зелёный

#### DoD
- [ ] 0 sync file-операций в async-path (grep `Path\.\(write\|read\)\|os\.chmod\|json\.\(load\|dump\)` в async-функциях)
- [ ] `mypy .` + `pytest tests/unit` зелёные после каждого PR
- [ ] Тест на `_save_kc_settings`: writes 0o600 mode

- **Сложность:** M
- **Риск регрессии:** Низкий — `to_thread` семантически эквивалентен. Стратегия: по одному модулю, characterization-тесты.
- **Ожидаемый эффект:** Устранение latency-spikes; единая точка atomic-write; −120 LOC дублирующихся try/except.
- **Статус:** [ ]

---

### [H5] — Циклическая зависимость worker → api `[verified]`
- **Категория:** Architecture
- **Приоритет:** 🟠 High
- **Где:** `backend/app/worker/tasks/photos/import_scan.py:74` — `from app.api.photos import folder_service`
- **Что найдено:** Worker-task импортирует `resolve_unique_fs_seg` из API-слоя. `folder_service` тянет `from app.api.photos._common`, который импортирует `fastapi.HTTPException`, redis/async-session deps, ACL-сервисы. Worker зависит от HTTP-слоя.
- **Почему проблема:** Инверсия зависимостей. Любое изменение в `api.photos._common` ломает worker. Worker тащит всю цепочку импортов (deps → keycloak → models → sse), удлиняя cold-start.
- **Последствия:** Circular import при росте; нельзя запускать worker в отдельном контейнере без FastAPI-deps.

#### План действий
- [ ] Создать `backend/app/services/photos_folder_naming.py`:
  - [ ] Перенести туда `resolve_unique_slug`, `resolve_unique_fs_seg` (чистые функции)
- [ ] В `backend/app/api/photos/folder_service.py` — импортировать из нового модуля
- [ ] В `backend/app/worker/tasks/photos/import_scan.py:74` — `from app.services.photos_folder_naming import resolve_unique_fs_seg`
- [ ] Проверить: `python -c "import app.worker.tasks.photos.import_scan"` — FastAPI не тянется

#### DoD
- [ ] `grep -r "from app.api" backend/app/worker/` → пусто (или обоснованные исключения)
- [ ] `python -c "import app.worker.tasks.photos.import_scan; import sys; assert 'fastapi' not in sys.modules"` → assert проходит
- [ ] `pytest tests/integration -k import_scan` зелёный

- **Сложность:** S
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** Worker не зависит от FastAPI/HTTP; isolation ↑; cold-start быстрее.
- **Статус:** [x] 2026-07-26 — выполнено (новый services/photos_folder_naming.py, folder_service.py re-export, import_scan.py:74)

---

### [H6] — `EventType` enum: заведён, но 0 call-сайтов `[verified]`
- **Категория:** Architecture / Code Smell (Speculative Generality)
- **Приоритет:** 🟠 High
- **Где:** `backend/app/services/audit_events.py:39` (класс `EventType`, ~80 members) vs. **147 call-сайтов** с литералами по `app/`
- **Что найдено:** Документация модуля сама признаёт: *"call sites are intentionally NOT mass-migrated to `EventType.XXX` ... the test will catch any new literal that isn't registered here."* Enum создан как источник истины, но фактически не используется — защита идёт через unit-тест.
- **Почему проблема:** Защита от typo держится на тесте, а не на типах. Поддержка ~80 members — мёртвая нагрузка. Enum отстаёт от реальности.
- **Последствия:** Энтропия, ~150 LOC мёртвого реестра, ложное чувство типобезопасности.

#### План действий ⚠️ требует решения команды
- [ ] **Decision required:** выбрать стратегию
  - **(A) Довести до конца** — каскадно заменить 147 литералов на `EventType.XXX` (mypy проверит). Сложность M.
  - **(B) Удалить enum** — `audit_events.py` превращается в список для документации без `StrEnum`. Сложность S.
- [ ] После решения — реализовать единым PR

#### DoD (вариант A)
- [ ] 0 литералов `event_type="..."` вне тестов
- [ ] `mypy .` зелёный
- [ ] `test_audit_events.py` проходит

#### DoD (вариант B)
- [ ] `EventType` удалён, документация сохранена как список
- [ ] `test_audit_events.py` адаптирован или удалён

- **Сложность:** M (A) / S (B)
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** Либо реальная типобезопасность, либо −150 LOC мёртвого кода.
- **Статус:** [ ] ⚠️ blocked on team decision

---

### [H7] — Primitive Obsession: role/status/direction как голые строки
- **Категория:** Code Smell
- **Приоритет:** 🟠 High
- **Где:** ~50 мест:
  - Роли: `deps.py:222,249`, `feedback_service.py:246`, `photos.py:243`, `folders.py:122`, `helpdesk/media.py:43`, `links.py:40` (26 мест)
  - Статусы helpdesk: `tickets.py:179,373`, `digest.py:54`, `archive.py:45`, `tickets.py:72,777`, `ingress.py:489-497`
  - `direction`: `ingress.py:515`, `tickets.py:85`, `messages.py:109,211`
  - `source`: `tickets.py:72,92`, `messages.py:112,214`, `ingress.py:518,624`
- **Что найдено:** В `schemas/helpdesk.py` уже есть `StrEnum`'ы `HelpdeskStatus`/`HelpdeskSource`/`HelpdeskDirection`, но service/api продолжают использовать литералы. Три параллельных источника: `_ACTIVE_STATUSES = ("new","open","pending")` в `tickets.py:179` vs `:373`, и `REQUESTER_REOPEN_STATUSES = frozenset({"pending"})` в `lifecycle.py`.
- **Почему проблема:** Typo `"opens"` вместо `"open"` проходит mypy/ruff, ломает логику silently. Shotgun Surgery при добавлении статуса. Рассинхрон правил между машиной состояний и SQL.
- **Последствия:** Регрессии при добавлении перехода/статуса.

#### План действий
- [ ] В `backend/app/core/constants.py` (или `models/enums.py`) определить enum'ы:
  ```python
  class UserRole(StrEnum): ADMIN = "admin"; EDITOR = "editor"; USER = "user"
  class TicketStatus(StrEnum): NEW = "new"; OPEN = "open"; PENDING = "pending"; CLOSED = "closed"
  class TicketDirection(StrEnum): INBOUND = "inbound"; OUTBOUND = "outbound"
  class TicketSource(StrEnum): EMAIL = "email"; WEB = "web"
  ```
- [ ] Заменить литералы поэтапно (по домену):
  - [ ] PR1: `lifecycle.py` + `tickets.py` (status/source/direction)
  - [ ] PR2: роли (deps.py + 26 мест)
  - [ ] PR3: helpdesk services (ingress/digest/archive/messages)
- [ ] В `lifecycle.py` использовать enum для `AGENT_SETTABLE_STATUSES`/`REQUESTER_REOPEN_STATUSES` — единый источник
- [ ] Между шагами: `pytest tests/unit/test_helpdesk_lifecycle.py` + `mypy .`

#### DoD
- [ ] `grep -rE '"(new|open|pending|closed|inbound|outbound|admin|editor|user)"' backend/app/ | grep -v test | grep -v schema` → пусто или обосновано
- [ ] `_ACTIVE_STATUSES` определён один раз через enum
- [ ] Все тесты зелёные

- **Сложность:** M
- **Риск регрессии:** Низкий-средний (StrEnum value-equal строке, backward-compatible). Стратегия: ввести enum, прогнать mypy.
- **Ожидаемый эффект:** Типобезопасность; единый источник истины; grep по типизированному символу.
- **Статус:** [ ]

---

### [H8] — Silent `except Exception` без логирования (~30 мест)
- **Категория:** Backend / Observability
- **Приоритет:** 🟠 High
- **Где:** Самые проблемные:
  - `services/helpdesk/ingress.py:181,191,194,930,942` — 5 `with suppress(Exception)` (глушат `expunge`/`logout`/`_safe_seen`/`_safe_delete`)
  - `services/helpdesk/tickets.py:48` `_try_enqueue_created_email` — теряет stacktrace
  - `services/photos_storage/metadata.py:37,46,78,87` — ошибки image-processing невидимы
  - `services/meetings/recurrence.py:24,151`, `ical_builder.py:15`
  - `services/files_shares_persistence.py:75,90`, `nextcloud/webdav/_client.py:180`
- **Что найдено:** ~30 мест с `except Exception:` без `logger.exception`/`exc_info=True`.
- **Почему проблема:** Silent failure = invisible tech-debt. Оператор видит проблему, но в логах пусто. В `_safe_logout`/`_safe_expunge` это не «чтобы не падало», а просто потеря diagnostics.
- **Последствия:** Невозможность диагностики.

#### План действий
- [ ] Где suppress сознательный — добавить `logger.debug` с контекстом (пол-строки)
- [ ] `tickets.py:48` `_try_enqueue_created_email` — заменить `error=str(exc)` на `exc_info=True`
- [ ] `metadata.py` — сузить: `except (OSError, ValueError, Image.UnidentifiedImageError): return None` + `logger.debug("photos.exif_skip", path=..., error=str(exc))`
- [ ] Включить ruff `BLE001` в `pyproject.toml` если отключён
- [ ] Прогнать `ruff check . --select BLE001` → классифицировать оставшиеся

#### DoD
- [ ] 0 `except Exception` без логирования в production-path (исключения — health-check/diagnostic с пометкой в комментарии)
- [ ] Каждый изменённый файл: unit-тест на путь ошибки (проверка лога через `caplog`)

- **Сложность:** S
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** ~30 мест observability-friendly.
- **Статус:** [x] 2026-07-26 — **частично**. Закрыты самые проблемные места из subagent-списка:
  - `services/helpdesk/ingress.py` — все 5 `with suppress(Exception)` заменены на try/except с логированием (rollback/expunge — debug, logout/`_safe_seen`/`_safe_delete` — warning; logout и mark_* влияют на IMAP-state сервера).
  - `services/helpdesk/tickets.py:48` `_try_enqueue_created_email` — добавлен `exc_info=True` (раньше терялся stacktrace).
  - `services/photos_storage/metadata.py` — все 4 silent except сужены до конкретных типов (`ImportError`, `(OSError, ValueError, Image.UnidentifiedImageError)`, `(UnicodeDecodeError, ValueError, TypeError)`, `ValueError`) + debug-логирование с контекстом (path/tag/raw_value).
  - Тест `test_compute_blurhash_exception_returns_none` обновлён под суженные типы (OSError вместо голого Exception).
  **Остаток** (~20 мест в `meetings/recurrence`, `files_shares_persistence`, `nextcloud/webdav/_client`, `keycloak_admin`, `health.py` и др.) — отдельная итерация. Включение ruff `BLE001` отложено (даст ~200 finding'ов по всему коду — нужен отдельный PR с классификацией каждый).

---

### [H9] — PII-маскинг покрывает только email
- **Категория:** Logging / Compliance (ФЗ-152)
- **Приоритет:** 🟠 High
- **Где:** `backend/app/core/logging.py:147-156` (`mask_pii_processor`), `:95` (`_EMAIL_RE`)
- **Что найдено:** PII-маскинг покрывает только email. IP-адреса (в `X-Real-IP`, audit), телефоны (`utils/phone.py`), ФИО (`full_name`) попадают в логи как есть. AGENTS.md §«Безопасность»: «Не логировать ... персональные данные».
- **Почему проблема:** Для ~300 сотрудников ФИО + телефон + email — ПДН (ФЗ-152). Оседают в Docker json-file, Loki, audit-таблицах.
- **Последствия:** Нарушение ФЗ-152, компрометация ПДН при утечке логов.

#### План действий
- [ ] IP-маскинг: regex `\b\d{1,3}(\.\d{1,3}){3}\b` → маска первых октетов (`10.0.X.X` или `***.***.X.X`)
- [ ] Телефоны — через механизм `utils/phone.py` (частичная маска `+7 (913) ***-**-23`)
- [ ] ФИО — добавить поля `full_name`/`display_name`/`first_name`/`last_name` в отдельный PII-ключ-список `_PII_VALUE_KEYS`
- [ ] Добавить dev-флаг `force_pii_masking: bool = True` (можно отключить для локальной отладки)
- [ ] Расширить `tests/unit/test_logging_processors.py` — каждый тип PII

#### DoD
- [ ] Тест: лог с IP `192.168.1.100` → замаскирован
- [ ] Тест: лог с телефоном `+7 (913) 555-12-34` → замаскирован
- [ ] Тест: лог с `full_name="Иванов Иван"` → замаскирован
- [ ] Тест: легитимные строки (URL, JSON-числа) НЕ искажаются

- **Сложность:** M
- **Риск регрессии:** Средний (регексы могут зацепить легитимные строки). Стратегия: вводить поэтапно (сначала IP), dev-флаг.
- **Ожидаемый эффект:** Соответствие AGENTS.md §«Безопасность».
- **Статус:** [ ]

---

### [H10] — `redact_secrets_processor` не покрывает ключи приложения
- **Категория:** Logging / Security
- **Приоритет:** 🟠 High
- **Где:** `backend/app/core/logging.py:29-48` (`SENSITIVE_KEY_SUBSTRINGS`)
- **Что найдено:** Список sensitive-подстрок неполон. Отсутствуют: `app_password`/`apppassword` (**Nextcloud `portal-svc` App Password — ключевой секрет портала**, ADR-032), `nc_password`, `mailbox_password` (helpdesk IMAP), `smtp_password`, `imap_password`, `private`, `client_id`.
- **Почему проблема:** `nc_service_app_password` хранится в `system.json` и логируется через `logger.info("system_settings.updated", **changes)` → утекает в открытый вид.
- **Последствия:** Nextcloud service-account compromise → доступ ко всем пользовательским файлам через WebDAV.

#### План действий
- [ ] Расширить `SENSITIVE_KEY_SUBSTRINGS` в `logging.py:29-48`:
  ```python
  SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
      # ...существующее...
      "app_password", "apppassword", "nc_password",
      "mailbox_password", "smtp_password", "imap_password",
      "private", "client_id", "realm_secret",
      "cert_key", "ssl_key", "private_key_data",
  )
  ```
- [ ] Integration-тест: снапшот лога при `system_settings.updated`, проверить что `nc_service_app_password` → `***REDACTED***`

#### DoD
- [ ] Тест: лог `{"nc_service_app_password": "secret"}` → `***REDACTED***`
- [ ] Тест: лог `{"mailbox_password": "..."}` → `***REDACTED***`
- [ ] Существующие ключи продолжают редактиться

- **Сложность:** XS
- **Риск регрессии:** Очень низкий (additive).
- **Ожидаемый эффект:** Покрытие реальных секретов портала.
- **Статус:** [x] 2026-07-26 — выполнено (logging.py:29-59)

---

### [H11] — Сторонние GitHub Actions не pinned по SHA
- **Категория:** CI/CD / Supply-chain
- **Приоритет:** 🟠 High
- **Где:** `.github/workflows/*.yml` — **56 floating refs** (`actions/checkout@v6`, `actions/setup-python@v6`, `actions/setup-node@v6`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`). При этом критичные (`docker/build-push-action`, `softprops/action-gh-release`, `irongut/CodeCoverageSummary@51cc3a...`, `marocchino/sticky-pull-request-comment@773744...`) **корректно SHA-pinned** — практика известна, но применяется выборочно.
- **Что найдено:** Floating `@vN` можно перезаписать компрометацией репо action'а. На job'ах с `packages: write`/`contents: write` это критично, но и `checkout`/`setup-python` выполняют arbitrary shell с доступом к `GITHUB_TOKEN`.
- **Почему проблема:** Supply-chain attack через compromised action → утечка CI-секретов, подмена публикуемых образов в GHCR.
- **Последствия:** Compromised CI → compromised prod images.

#### План действий
- [ ] Создать/обновить `.github/dependabot.yml` с `github-actions` ecosystem (если нет)
- [ ] Для каждого floating ref:
  - [ ] Найти текущий SHA: `gh api repos/actions/checkout/git/refs/tags/v6`
  - [ ] Заменить `@v6` → `@<sha> # v6.x.x`
- [ ] Альтернатива: настроить Dependabot preset `helpers:pinGitHubActionDigests`
- [ ] Верификация: `grep -rE "uses: [a-z]+/[a-z-]+@v[0-9]" .github/workflows/` → пусто

#### DoD
- [ ] 0 floating action refs (только SHA)
- [ ] Dependabot будет обновлять SHA через PR (проверить, что конфиг валиден)
- [ ] CI зелёный после изменений

- **Сложность:** S
- **Риск регрессии:** Очень низкий — SHA → тот же код.
- **Ожидаемый эффект:** Полная защита от supply-chain через floating tags.
- **Статус:** [x] 2026-07-26 — выполнено. Все 56 floating `@vN` refs в `ci.yml`/`nightly-flakes.yml`/`nightly-security.yml`/`security.yml` заменены на `@<sha> # vN`. SHA-ы получены через `gh api` (живые, не из таблицы аудита — 3 из 7 SHA в таблице оказались неверными: `setup-python`, `setup-node`, `codeql-action`; для `codeql-action@v4` сделан dereference annotated-tag-object → commit). Dependabot `github-actions` ecosystem уже был настроен — будет обновлять SHA через PR. Контейнерные pins (gitleaks/trivy из M21) не тронуты.

---

### [H12] — Нет стратегии retention/cleanup резервных копий БД
- **Категория:** Infrastructure / Reliability
- **Приоритет:** 🟠 High
- **Где:** `backups/` (накапливаются файлы), `setup.sh:1123` (`pg_backup()`)
- **Что найдено:** `pg_backup()` делает `pg_dump -Fc` в `backups/portal_<timestamp>.dump`, но нет cleanup'а. В каталоге уже 2 дампа — копятся бесконечно. Нет cron, нет rotation, нет проверки восстановления, **бэкапы на том же хосте**.
- **Почему проблема:** 1) Диск переполнится при росте БД. 2) Никто не делает `pg_restore` test → backup может быть silently broken. 3) При потере диска теряются и данные, и бэкапы.
- **Последствия:** Невозможность восстановления после отказа диска; переполнение FS.

#### План действий
- [ ] Создать `scripts/rotate-backups.sh` — хранить N=30 последних (или 30 дней), удалять старше
- [ ] Cron (через host или sidecar) — еженощно `pg_backup` + `rotate-backups`
- [ ] **Off-site copy:** `rclone`/`rsync` на отдельный носитель (NAS, MinIO, другой host)
- [ ] **Monthly drill:** `pg_restore` в staging + smoke-тест schema/data
- [ ] Документировать в `docs/deploy.md` (раздел Backup)

#### DoD
- [ ] Rotation-скрипт написан, протестирован вручную (создать 35 дампов, запустить, проверить что осталось 30)
- [ ] Cron настроен и мониторится
- [ ] Off-site copy протестирован (минимум один restore-drill на staging)
- [ ] Раздел в `docs/deploy.md` обновлён

- **Сложность:** M
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** Реализуемая стратегия восстановления; защита от потери хоста.
- **Статус:** [ ] ⚠️ прод — см. раздел «Инструкция для продакшена»

---

## 🟡 MEDIUM

### [M1] — Comments list/count рассинхрон ⚠️ UX-согласование `[verified]`
- **Категория:** Database
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/api/news/comments_repo.py:30-40` (`list_comments` без `deleted_at IS NULL`), `:20-27` (`count_active_comments` с фильтром); аналогично `kb/comments_repo.py`; consumer `api/news/comments.py:65-66`
- **Что найдено:** `count_active_comments` фильтрует `deleted_at IS NULL`, `list_comments` — нет. `_to_public` маскирует удалённые как `is_deleted=True`. При M удалённых OFFSET-страница вернёт меньше активных, чем `limit`. `total` (бейдж) не совпадает с реальным перебором.
- **⚠️ ВАЖНО:** Простое добавление `deleted_at IS NULL` в `list_comments` **сломает UX** (placeholder «[удалено]» пропадёт из ленты). Это **сознательное UX-решение**, не баг.

#### План действий ⚠️ согласовать с владельцем продукта
- [ ] **Decision required:** какое поведение хотим?
  - **(A)** Показывать placeholder «[удалено]» только в пределах текущей страницы (гибрид: fetch `(deleted_at IS NULL OR id IN (на_странице))`)
  - **(B)** Не показывать удалённые в ленте вообще (фильтр на SQL, убрать ветку `is_deleted` в DTO)
  - **(C)** Оставить как есть, но исправить только `total` (считать все, включая soft-deleted)
- [ ] После решения — реализовать + unit-тест на пагинацию с перемежающимися soft-deleted

#### DoD
- [ ] `total` совпадает с реальным числом возвращённых при переборе страниц
- [ ] Partial-индекс `idx_news_comments_active` используется (если выбрали B)
- [ ] Тест: 5 active + 3 deleted, limit=4 → корректная пагинация

- **Сложность:** S
- **Риск регрессии:** Средний (UX). Стратегия: согласовать с командой, feature-flag если надо.
- **Ожидаемый эффект:** Корректная пагинация, нет UI-«дыр».
- **Статус:** [ ] ⚠️ blocked on UX decision

---

### [M2] — OFFSET-pagination на растущих таблицах → keyset
- **Категория:** Performance
- **Приоритет:** 🟡 Medium
- **Где:**
  - `backend/app/api/audit.py:97` + `audit_repo.list_events`
  - `backend/app/api/helpdesk/tickets.py:440-451` (`list_agent_tickets`)
  - `backend/app/services/news/crud.py:76-77`
  - `backend/app/api/email_outbox_repo.py:32-44`
- **Что найдено:** Все list-endpoint'ы используют OFFSET. На `audit_log`/`email_outbox` (admin tabs, реально большие) `OFFSET 10000` + Seq-by-created_at = секунды.
- **Почему проблема:** Линейная деградация с глубиной.
- **Последствия:** Таймауты admin-tabs на больших таблицах.

#### План действий
- [ ] Для audit/outbox (фиксированная сортировка `created_at DESC, id DESC`):
  - [ ] Cursor = последний элемент текущей страницы
  - [ ] `WHERE (created_at, id) < (:last_ca, :last_id)`
  - [ ] Добавить опциональный `?cursor=` параметр, сохранить `?offset=` для backward-compat
- [ ] Для helpdesk/news (произвольная сортировка) — оставить OFFSET, но ограничить глубину (max 1000)
- [ ] Frontend: обновить пагинацию на cursor-режим для audit/outbox tabs

#### DoD
- [ ] Integration-тест: 10k строк, `OFFSET 10000` vs `cursor` → keyset в 10×+ быстрее
- [ ] Frontend audit/outbox tabs работают с cursor

- **Сложность:** M
- **Риск регрессии:** Средний (frontend). Стратегия: backward-compat `offset`, поэтапная миграция UI.
- **Ожидаемый эффект:** O(log N) вместо O(N) на audit/outbox.
- **Статус:** [ ]

---

### [M3] — Batch INSERT в `meetings/notifications.py` outbox
- **Категория:** Performance
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/services/meetings/notifications.py:52-149` (`_enqueue_all_recipients`, `_enqueue_updated_with_diff`)
- **Что найдено:** Цикл `for user in booking.invited_users: await _enqueue(...)` — каждый `_enqueue` делает отдельный `INSERT INTO email_outbox ... RETURNING id`. Для встречи с N участниками → N round-trip. Для серии из 10 инстансов × 20 участников = 200 INSERT в одном `enqueue_meeting_emails`.
- **Почему проблема:** Latency на `POST /meetings/bookings` растёт линейно с N.
- **Последствия:** Видимый «подвис» UI при создании большой серии.

#### План действий
- [ ] В `services/email_outbox.py` добавить `enqueue_outbox_email_batch(items: list[OutboxItem])` — один `executemany` или `INSERT ... VALUES (unnest)`
- [ ] В `_enqueue_all_recipients` собрать все items, вызвать batch-функцию один раз
- [ ] Сохранить outbox-инвариант (та же транзакция)
- [ ] Integration-тест: создание встречи с 50 участниками → 1 batch INSERT вместо 50

#### DoD
- [ ] Тест: 50 участников → ровно 1 INSERT-statement в outbox (через `query_graph` или caplog)
- [ ] Outbox-инвариант сохранён (commit в той же tx)

- **Сложность:** M
- **Риск регрессии:** Средний. Стратегия: characterization-тест текущего поведения первым.
- **Ожидаемый эффект:** −90% round-trip на больших встречах.
- **Статус:** [ ]

---

### [M4] — `meetings/bookings.py` limit=500 без keyset
- **Категория:** Performance
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/api/meetings/bookings.py:91` (`limit=500, ge=1, le=500`); `bookings_service/_queries.py:16-65`
- **Что найдено:** `GET /meetings/bookings` тянет до **500** бронирований, с `selectinload(MeetingBooking.rooms).selectinload(MeetingBookingRoom.room)`. Без date-фильтра — полный скан `meeting_bookings`. Для UI календаря (обычно день/неделя) избыточно.
- **Почему проблема:** `limit=500` без keyset + три selectinload'а → 500 строк × (1 + комнаты + rooms-lookup) = 1500+ строк в трёх SELECT.
- **Последствия:** Большой JSON на клиент, нагрузка на БД.

#### План действий
- [ ] Согласовать с frontend: реально нужен limit>100?
- [ ] Если нет — `limit=100` дефолт, `le=200` максимум
- [ ] Сделать `start_date`+`end_date` обязательными (или дефолт = текущий месяц)
- [ ] Keyset по `(start_time, id)`

#### DoD
- [ ] `GET /meetings/bookings?limit=500` → 422 или обрезан до max
- [ ] Frontend календарь работает с новым лимитом

- **Сложность:** S
- **Риск регрессии:** Низкий (frontend уже paginating).
- **Ожидаемый эффект:** Меньше данных на клиент, меньше load на БД.
- **Статус:** [x] 2026-07-27 — выполнено. `limit: int = Query(default=100, ge=1, le=BOOKINGS_LIMIT_MAX=200)`. Service-слой `_queries.py` clamp обновлён в lockstep через общую константу `BOOKINGS_LIMIT_MAX` (mirror паттерна `MY_BOOKINGS_LIMIT_MAX`). Разведка подтвердила: frontend **не шлёт `limit`** вообще (календарь передаёт только `date`) — снижение безопасно. ⚠️ План-пункты «сделать start_date+end_date обязательными» и «keyset по (start_time, id)» **отклонены**: frontend-календарь шлёт только `date`, forcing range сломал бы UI; keyset отложен к M2. Contract-тест `test_meetings_bookings_limit.py` проверяет Query FieldInfo (default/ge/le), clamp-тест усилен до проверки compiled SQL LIMIT.

---

### [M5] — Drop redundant non-partial indexes
- **Категория:** Database
- **Приоритет:** 🟡 Medium
- **Где:** схема (7 таблиц): `photos`, `news_comments`, `kb_article_comments`, `kb_sections`, `file_folders`, `kb_articles`, `users`, `news`
  - `idx_photos_folder_created (folder_id, created_at DESC)` vs `idx_photos_active (folder_id) WHERE deleted_at IS NULL`
  - `idx_news_status_published_at` (без deleted_at) vs `idx_news_active ... WHERE deleted_at IS NULL`
  - и др.
- **Что найдено:** Дублирующие индексы. Большинство list-запросов сразу фильтруют `deleted_at IS NULL` → non-partial бесполезен, но добавляет write-cost.
- **Почему проблема:** Лишний write на INSERT/UPDATE + место + planning cost.

#### План действий
- [ ] Для каждой пары — `EXPLAIN ANALYZE` реальных list-запросов → подтвердить, что non-partial не используется
- [ ] Миграция (zero-downtime): `DROP INDEX CONCURRENTLY idx_X;` для подтверждённых дубликатов
- [ ] Внимание: `idx_users_email_lower` НЕ удалять (используется в lookups), проверить отдельно

#### DoD
- [ ] Каждый drop подтверждён `EXPLAIN ANALYZE` (запрос не стал медленнее)
- [ ] Миграция `CREATE INDEX CONCURRENTLY` / `DROP INDEX CONCURRENTLY`
- [ ] Integration-тест list-endpoint'ов зелёный

- **Сложность:** S
- **Риск регрессии:** Низкий, но требует EXPLAIN ANALYZE каждого затронутого запроса.
- **Ожидаемый эффект:** Меньше writes, меньше planning time.
- **Статус:** [ ] ⚠️ прод — см. раздел «Инструкция для продакшена»

---

### [M6] — Декомпозиция `_ingest_message` (Long Method)
- **Категория:** Code Smell
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/services/helpdesk/ingress.py:583-722` (`_ingest_message` ~140 LOC), `:229-273` (`_process_uid`)
- **Что найдено:** `_ingest_message` делает за один проход: парсинг заголовков, матчинг тикета, поиск пользователя, экстракцию тел, санитацию, создание/апдейт тикета, построение сообщения, локализацию картинок, запись email-лога, отправку заявителю, commit, post-commit remote-локализацию, fan-out в 3 канала. Каждая ветка try/except, параметр `summary` мутируется из 4 мест.
- **Почему проблема:** Любая правка требует изменения этой функции. Тестировать весь монолит. Сложно увидеть инвариант outbox-коммита.
- **Последствия:** Регрессии при правках email-треда (как уже было 20.07.2026).

#### План действий
- [ ] **Сначала** characterization-тест на текущее поведение (snapshot input→output): тестовые IMAP-сообщения → проверка созданного ticket+message+outbox
- [ ] Разбить на шаги **без изменения семантики** (каждый — отдельный коммит, тест зелёный):
  - [ ] `_parse_and_match(db, msg, settings_row) -> MatchResult` (headers + ticket + requester + bodies)
  - [ ] `_persist_ticket_and_message(db, match, settings_row) -> PersistResult`
  - [ ] `_finalize_ingest(db, redis, ticket, message, ...) -> None` (commit + post-commit + notify)
- [ ] Оркестратор `_ingest_message` становится ~30-строчным wiring'ом
- [ ] Инвариант: `db.commit()` только в `_finalize_ingest`

#### DoD
- [ ] Characterization-тест зелёный до и после (поведение 1:1)
- [ ] `_ingest_message` ≤ 40 LOC
- [ ] Каждый шаг unit-тестируется отдельно

- **Сложность:** M
- **Риск регрессии:** Medium — критический путь email-ingress. Стратегия: characterization-тест первым, пошагово, без feature-flag (поведение неизменно).
- **Ожидаемый эффект:** `_ingest_message` ~30 LOC; unit-тестируемость шагов.
- **Статус:** [ ]

---

### [M7] — Helpdesk email/notification/image: 4 файла ~3000 LOC, дубли
- **Категория:** Code Smell
- **Приоритет:** 🟡 Medium
- **Где:**
  - `backend/app/services/helpdesk/email_template.py` (779)
  - `backend/app/services/helpdesk/notifications.py` (757)
  - `backend/app/services/helpdesk/email_images.py` (729)
  - `backend/app/worker/tasks/email_outbox.py` (649)
- **Что найдено:**
  1. Дубли `load_system_settings`: `email_template.py:496-503` (`_portal_timezone`), `:510-517` (`_portal_base_url`), `notifications.py:444-452` (`_build_ticket_url`) — три обёртки с одинаковым `try/except Exception: return "Europe/Moscow"`.
  2. Дубли agent-selection: `notifications.py:46-65` (`_select_agents_to_notify`) vs `:323-345` (`_load_agents_for_email`) — почти идентичные JOIN.
  3. Dead params: `email_template.py:194-205` `_role_prefix(*, is_outbound, is_assignee)` — оба параметра не используются.
  4. Hardcoded HTML/CSS: `email_template.py:44-57` палитра инлайнится в f-строки (~30 мест). Дубли в `notifications.py:246-253,291-300`.

#### План действий
- [ ] Создать `app/services/system_settings_runtime.py` → `get_portal_settings() -> PortalSettings` (timezone + base_url, один source)
- [ ] Слить `_select_agents_to_notify` + `_load_agents_for_email` в одну параметризованную `_load_active_agents(*, fields, require_inapp, require_email)`
- [ ] Удалить dead params `_role_prefix(is_outbound, is_assignee)` + call-sites `:281, :586`
- [ ] Вынести палитру+стили в Jinja2-шаблон `app/services/helpdesk/templates/system_email.html.j2`
- [ ] Слить `build_assigned_email_bodies` + `build_created_email_bodies` в общий builder
- [ ] Snapshot-тесты входящих писем (input→output html/plain) перед рефакторингом
- [ ] Feature-flag `HELPDESK_EMAIL_TEMPLATE_V2` для безопасного rollout

#### DoD
- [ ] Snapshot-тесты писем 1:1 (HTML + plain) до/после
- [ ] −400 LOC
- [ ] Feature-flag переключаемый через SystemSettings
- [ ] Прогон на staging со сравнением diff писем

- **Сложность:** M
- **Риск регрессии:** Medium — письма видны пользователям. Стратегия: snapshot-тесты + feature-flag + staging diff.
- **Ожидаемый эффект:** −400 LOC; единый источник брендинга; тестируемость.
- **Статус:** [ ]

---

### [M8] — `analytics.py`: дублирование List→Out mapping
- **Категория:** Code Smell (Divergent Change)
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/api/analytics.py:107-252` (8 эндпоинтов)
- **Что найдено:** Каждый эндпоинт повторяет паттерн `rows = await repo.fetch_X(...); return [XOut(...) for r in rows]`. Идентичная структура ~10-15 строк × 8 функций. `_EXPORT_COLUMNS` — пятый источник истины про поля.
- **Почему проблема:** Добавление нового dataset требует правок в 5 местах (schema, repo, api-endpoint, `_EXPORT_COLUMNS`, `_export_rows`). Shotgun Surgery.

#### План действий
- [ ] Завести generic `def dataset_endpoint(name, repo_fn, out_cls, columns): ...` декоратор
- [ ] Реестр datasets в одном dict
- [ ] 8 эндпоинтов → 1 generic + реестр
- [ ] Сохранить URL/contract

#### DoD
- [ ] Characterization-тесты на URL/output 8 эндпоинтов до/после
- [ ] −~120 LOC
- [ ] Добавление нового dataset = 1 строка в реестре

- **Сложность:** S-M
- **Риск регрессии:** Low.
- **Ожидаемый эффект:** −~120 LOC; extensible.
- **Статус:** [ ]

---

### [M9] — `keycloak_admin.py` God Module
- **Категория:** Architecture
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/api/keycloak_admin.py` (390 LOC, 5 обязанностей)
- **Что найдено:** Один роутер-файл содержит:
  - persistence (file-IO, legacy-миграция) `:133-173`
  - SSRF-валидация `:37-84`
  - HTTP-клиент к Keycloak (`test_oidc_connection`/`test_sync_connection`) `:234-374`
  - 5 Pydantic-моделей `:94-131`
  - логика миграции legacy `:135-144`
- **Почему проблема:** Роутер должен быть тонким wiring'ом (AGENTS.md явно). Здесь бизнес-логика, IO, HTTP-клиенты.
- **Последствия:** Сложно тестировать без FastAPI; SSRF-логика не переиспользуется; дубли `_validate_keycloak_url` vs `email_images.is_safe_remote_url`.

#### План действий
- [ ] `app/services/keycloak_settings_store.py` — `load_settings`, `save_settings`, `migrate_legacy`
- [ ] `app/core/net_guard.py` (см. [H1]) — SSRF-валидация, переиспользуется
- [ ] `app/services/keycloak/probe.py` — `test_oidc_connection`, `test_sync_connection`
- [ ] Роутер становится тонкой обёрткой: dependency-lookup → вызов сервиса → response

#### DoD
- [ ] −~150 LOC из роутера
- [ ] `net_guard.py` используется и здесь, и в bookmarks ([H1])
- [ ] Integration-тест на test-endpoints с моком Keycloak

- **Сложность:** M
- **Риск регрессии:** Low-medium. Стратегия: characterization-тесты contract'ов URL/payload.
- **Ожидаемый эффект:** Тестируемость без FastAPI; единый SSRF-validation.
- **Статус:** [ ]

---

### [M10] — Magic Numbers в воркере и storage
- **Категория:** Code Smell
- **Приоритет:** 🟡 Medium
- **Где:**
  - `backend/app/worker/tasks/email_outbox.py:45-46` — `DISPATCH_BATCH_SIZE = 20`, `STALE_SENDING_TIMEOUT_SECONDS = 600`
  - `backend/app/services/helpdesk/notifications.py:418` — `_truncate_preview(limit=500)`
  - `backend/app/services/helpdesk/email_images.py:46-56` — `_FETCH_TIMEOUT=10.0`, `_FETCH_MAX_BYTES=25*1024*1024`, `_MAX_IMAGES=50`
  - `backend/app/services/notifications.py:104` — `batch_size=500`
  - `backend/app/services/helpdesk/notifications.py:460-473` — `_MAX_LINK_BLOCKED_TLDS` (знание домена MAX Bot живёт в helpdesk)
- **Что найдено:** Константы раскиданы, часть в `core/constants.py`, часть инлайн. Magic numbers без обоснования.

#### План действий
- [ ] Перенести в `core/constants.py` (или `Settings` для tunable)
- [ ] `_MAX_LINK_BLOCKED_TLDS` → `app/services/max_messenger/_client.py` (рядом с владельцем)

#### DoD
- [ ] Все magic numbers либо в `constants.py`, либо в `Settings`, либо с комментарием-обоснованием
- [ ] Тюнинг через env для tunable

- **Сложность:** XS
- **Риск регрессии:** Low.
- **Ожидаемый эффект:** Тюнинг без redeploy; единое место magic-numbers.
- **Статус:** [x] 2026-07-26 — частично выполнено (email_outbox constants → core/constants.py). Остальные magic numbers (email_images, notifications) — в следующей итерации.

---

### [M11] — Hidden coupling через `get_settings()` singleton (Service Locator)
- **Категория:** Architecture
- **Приоритет:** 🟡 Medium
- **Где:** 11 модулей с module-level `_settings = get_settings()`:
  - `app/api/auth/_helpers.py:35`, `local.py:31`, `__init__.py:67`, `users/_common.py:13`
  - `app/services/photos_storage/thumbnails.py:24`
  - `app/middleware/session.py:19`
  - `app/services/keycloak/settings.py:17`, `tokens.py:11`, `jwks.py:16`, `__init__.py:69`
- **Что найдено:** Module-level `_settings = get_settings()` читает настройки ОДИН РАЗ при import. Service Locator anti-pattern.
- **Почему проблема:** Тест-изоляция (два теста с разными `_settings` нельзя запустить в одном процессе без `monkeypatch`). Латентный import side-effect. Невозможность DI.
- **Последствия:** Сложность тестирования, «магический» сбой при первом импорте в новой среде.

#### План действий ⚠️ крупный рефакторинг, командное решение
- [ ] **Decision required:** делать ли вообще (есть overhead)
- [ ] Если да — поэтапно (по одному модулю за PR):
  - [ ] `_settings` → FastAPI dependency (`Depends(get_settings)`) для endpoints
  - [ ] Для worker/non-FastAPI — через ARQ `ctx` или фабрику
  - [ ] Module-level кэш оставить только для read-only на всю жизнь процесса (`BASE_DIR` и т.п.)

#### DoD
- [ ] Тест-изоляция: два теста с разными settings в одном процессе работают
- [ ] `mypy .` зелёный после каждого PR

- **Сложность:** M
- **Риск регрессии:** Medium — легко ошибиться с DI. Стратегия: поэтапно, characterization-тесты.
- **Ожидаемый эффект:** Тестируемость ↑; явные зависимости.
- **Статус:** [ ] ⚠️ optional — командное решение

---

### [M12] — `LinksTab.vue`: composable НЕ выделен
- **Категория:** Frontend
- **Приоритет:** 🟡 Medium
- **Где:** `frontend/src/pages/admin/tabs/LinksTab.vue` (448 LOC, script setup ~277 LOC)
- **Что найдено:** Подтверждение FE-5/P2 из `docs/code-audit.md` — **composable НЕ выделен**. В одном `<script setup>` смешаны: TanStack Query, Pinia store, CRUD-логика (~80 LOC), форма-стейт, icon-upload с URL.revokeObjectURL (~30 LOC), поиск, `linkColumns` через `h()` (~80 LOC).
- **Почему проблема:** Порог 250 LOC из AGENTS.md превышен в 1.1×. Нет unit-тестов на hand-функции, дублирование icon-upload в `LinkCard.vue`. Риск утечки ObjectURL при быстрых open/close модалки.

#### План действий
- [ ] Сначала unit-тесты на `submit` (happy path + invalid URL + icon-remove flow)
- [ ] Выделить 3 единицы:
  - [ ] `composables/useLinkIconUpload.ts` — state `{ iconFile, iconPreview, iconRemoved }` + actions + `onScopeDispose` для revoke. Переиспользуется в LinkCard.vue
  - [ ] `composables/useLinkForm.ts` — state `{ linkForm, editingLink, savingLink, linkRules }` + actions
  - [ ] `components/admin/linkColumns.ts` — функция `buildLinkColumns({ onEdit, onDelete })`
- [ ] LinksTab остаётся wiring ~80 LOC
- [ ] Между шагами — mount-тест LinksTab

#### DoD
- [ ] LinksTab.vue ≤ 120 LOC
- [ ] Unit-тесты на `useLinkForm.submit` и `useLinkIconUpload` (включая revoke)
- [ ] `npm run test:unit` зелёный

- **Сложность:** M
- **Риск регрессии:** Medium (CRUD-пути). Стратегия: тесты первыми, по одной единице.
- **Ожидаемый эффект:** −~200 LOC из страницы; тестируемость; переиспользование.
- **Статус:** [ ]

---

### [M13] — Frontend `api/*.ts`: 13/15 модулей дублируют `types.gen.d.ts`
- **Категория:** Frontend / TypeScript
- **Приоритет:** 🟡 Medium
- **Где:** `frontend/src/api/news.ts:3-30`, `files.ts:3-89`, `users.ts`, `helpdesk.ts`, `meetings.ts` (используют только `photos.ts:2` и `kb.ts:3`)
- **Что найдено:** В проекте есть автогенерируемый `types.gen.d.ts` (702 KB, актуальный), но 13 из 15 api-модулей вручную переопределяют интерфейсы. Пример: `api/news.ts:3` `interface News { id, title, body, status, ... }` — 30+ полей, продублированных из `components['schemas']['NewsOut']`.
- **Почему проблема:** Ручные типы расходятся с бэкендом при каждом изменении OpenAPI. Любой дрифт → тихая type-неинформация. Нарушение ADR из AGENTS.md.

#### План действий
- [ ] По образцу `api/photos.ts:7-28` (`export type Photo = components['schemas']['PhotoPublic']`)
- [ ] Мигрировать по одному модулю за PR:
  - [ ] news.ts → `News = components['schemas']['NewsOut']`
  - [ ] files.ts → `NCItem`, `FileFolder`, etc.
  - [ ] users.ts, helpdesk.ts, meetings.ts, и т.д.
- [ ] После каждого — `npm run typecheck` + `diff` между старым interface и `components['schemas'][...]`

#### DoD
- [ ] Только 2 модуля (`photos.ts`, `kb.ts`) уже на generated types — добавить остальные 13
- [ ] `npm run typecheck` зелёный
- [ ] −~500 LOC дублированных интерфейсов

- **Сложность:** M (на модуль S, итого L)
- **Риск регрессии:** Низкий. Стратегия: один модуль за PR.
- **Ожидаемый эффект:** Single source of truth; автотипизация при backend-изменениях.
- **Статус:** [ ]

---

### [M14] — `HelpdeskAgentInboxPage.vue` обходит TanStack Query
- **Категория:** Frontend
- **Приоритет:** 🟡 Medium
- **Где:** `frontend/src/pages/helpdesk/HelpdeskAgentInboxPage.vue:147-330` (весь script setup)
- **Что найдено:** Страница обходит TanStack Query, хотя в `queries/helpdesk.ts:193` уже есть `useAgentTicketsQuery`. Здесь — 6 разрозненных `ref<>` для server state, 4 ручные `load*`-функции, дублирующиеся `loading`-флаги, прямые `fetchAgentTickets()`. Мутация `onTake` (313) вручную `loadAll()`, а не `qc.invalidateQueries`.
- **Почему проблема:** Единственная большая страница без data-fetching layer. Нет кеша, нет `staleTime`, нет инвалидации. После `takeTicket` на соседней вкладке inbox не обновится. BACK-button перерендерит список с нуля.
- **Последствия:** Видимый «флеш» для оператора поддержки, рассинхрон с другими helpdesk-страницами.

#### План действий
- [ ] Сначала characterization-тесты на 3 сценария (mount→load, onTake→reload, search→replace-list)
- [ ] Мигрировать блок за блоком (search → new → inWork) на существующие query-composable
- [ ] `state newItems/newTotal/newLoading` удалить → `newQ.data.value?.items`/`.total`/`.isLoading.value`
- [ ] `onTake` → `await takeTicket(id); qc.invalidateQueries({ queryKey: ['helpdesk', 'inbox'] })`
- [ ] Сохранить идентичный URL/scope-поведение
- [ ] `loadAll()` на top-level (строка 329) → `onMounted`

#### DoD
- [ ] 0 ручных `ref` для server state в этой странице
- [ ] Все данные через TanStack Query
- [ ] Back-navigation показывает кеш, refetchOnFocus работает
- [ ] Тесты зелёные

- **Сложность:** M
- **Риск регрессии:** Medium. Стратегия: characterization-тесты, поэтапная миграция.
- **Ожидаемый эффект:** Унификация data-layer; −~80 LOC ручного state.
- **Статус:** [ ]

---

### [M15] — Backend Dockerfile: дублирование apt-install между стадиями
- **Категория:** Docker
- **Приоритет:** 🟡 Medium
- **Где:** `backend/Dockerfile:31-54` (runtime-base) vs `:77-118` (production)
- **Что найдено:** Стадия `production` (FROM `python:3.12-slim`) повторяет ВЕСЬ блок apt-install из `runtime-base` + тот же `update-ca-certificates`. ~30 строк дублирования, синхронизируются вручную.
- **Почему проблема:** При добавлении нового runtime-пакета нужно не забыть добавить в оба места. Если забудут — `test` (extends runtime-base) работает, `production` падает в runtime.
- **Последствия:** Silent prod-only bug при расхождении.

#### План действий
- [ ] Сделать `production` `FROM runtime-base AS production` (а не FROM python:3.12-slim)
- [ ] Сертификаты Минцифры копировать в `runtime-base`
- [ ] Сравнить `docker history` / размер образов до/после
- [ ] Прогнать compose-smoke CI на новом образе

#### DoD
- [ ] apt-install написан один раз (в runtime-base)
- [ ] Размер production-образа ≤ прежнего
- [ ] compose-smoke CI зелёный

- **Сложность:** S
- **Риск регрессии:** Средний. Стратегия: сравнить docker history, compose-smoke CI.
- **Ожидаемый эффект:** DRY; единый runtime-слой.
- **Статус:** [x] 2026-07-26 — выполнено. `production` теперь `FROM runtime-base AS production` (раньше `FROM python:3.12-slim`), удалено 32 строки дублированного apt-install + ENV + apt-mirror + CA-cert. `apt-get install` runtime-пакетов и `update-ca-certificates` теперь ровно по одному разу (в `runtime-base`). Production-stage: 52 → 20 LOC. Образ успешно собирается, `app.main` импортируется, `gosu` доступен (entrypoint работает), CA-сертификаты Минцифры на месте.

---

### [M16] — Docker compose: дублирование 12 bind-mounts между backend и worker
- **Категория:** Docker
- **Приоритет:** 🟡 Medium
- **Где:** `docker-compose.yml:137-154` (backend), `:196-209` (worker)
- **Что найдено:** Backend и worker монтируют одинаковый набор 12+ директорий. 25+ строк дублированного YAML.
- **Почему проблема:** DRY-нарушение — при добавлении нового `/data/...` надо править 2 места (легко забыть, как было с helpdesk). Worker не обязан иметь write-доступ ко всему.
- **Последствия:** Silent data-misplacement; избыточные права worker'а.

#### План действий
- [ ] Через YAML anchor:
  ```yaml
  x-data-volumes: &data-volumes
    - ./upload_data/avatars:/data/avatars
    # ...
  services:
    backend:
      volumes: *data-volumes
    worker:
      volumes: *data-volumes
  ```
- [ ] Опционально: read-only флаги там, где сервис не пишет (`avatars` для worker)

#### DoD
- [ ] `docker inspect` volumes для backend и worker идентичны 1:1
- [ ] compose-smoke CI зелёный

- **Сложность:** XS
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** Поддерживаемость, единый source of truth.
- **Статус:** [—] 2026-07-26 — отклонено (см. раздел «Отклонённые задачи»)

---

### [M17] — `secret_crypto.py`: SHA-256 без KDF, нет ротации ключа
- **Категория:** Configuration / Security
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/core/secret_crypto.py:24-34,30-33`
- **Что найдено:**
  ```python
  secret = get_settings().secret_key.encode("utf-8")
  key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
  _fernet = Fernet(key)
  ```
  Не PBKDF2/scrypt/HKDF — обычный SHA-256 (одна итерация). Нет key-versioning — смена `SECRET_KEY` ломает расшифровку существующих секретов.
- **Почему проблема:** При компрометации `SECRET_KEY` attacker восстанавливает Fernet-ключ тривиально и расшифровывает все секреты (helpdesk-mailbox password) задним числом.
- **Последствия:** Необратимая компрометация at-rest секретов при утечке `SECRET_KEY`.

#### План действий ⚠️ высокий риск из-за миграции существующих шифр-текстов
- [ ] Заменить на HKDF или PBKDF2-HMAC-SHA256 с salt + high iterations:
  ```python
  from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
  kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=PORTAL_SALT, iterations=600_000)
  key = base64.urlsafe_b64encode(kdf.derive(secret))
  ```
- [ ] Ввести key-versioning: рядом с encrypted-secret хранить `key_version`
- [ ] Blue-green migration: `decrypt_v1` (legacy) + `decrypt_v2` (new), миграция при следующем update helpdesk-settings

#### DoD
- [ ] Существующие шифр-тексты расшифровываются (legacy path)
- [ ] Новые шифруются v2
- [ ] Тест: migration path covered

- **Сложность:** L (с key-versioning)
- **Риск регрессии:** Высокий — инвалидирует существующие шифр-тексты. Стратегия: blue-green, v1+v2并存, миграция.
- **Ожидаемый эффект:** Современная деривация; возможность ротации.
- **Статус:** [ ] ⚠️ прод + high risk — см. раздел «Инструкция для продакшена»

---

### [M18] — Nginx: нет rate limiting на уровне reverse-proxy
- **Категория:** Infrastructure
- **Приоритет:** 🟡 Medium
- **Где:** `system_data/nginx/nginx.conf`, `nginx/templates/https_server.conf.tmpl`, `nginx/templates/proxy_locations.conf.tmpl`
- **Что найдено:** Нет `limit_req_zone`/`limit_req`. Rate-limit только в приложении (`fastapi-limiter`), и только на специфичных endpoints (`/auth/local/login`). Остальные ~290 endpoints без лимита ни на nginx, ни на backend.
- **Почему проблема:** При DDoS на `/api/...` backend держит всю нагрузку. Auth-brute-force только на одном endpoint — `/auth/refresh`, `/auth/sso/callback` без лимита.
- **Последствия:** DoS backend'а, ускоренный brute-force.

#### План действий
- [ ] В `nginx.conf` http {}:
  ```nginx
  limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
  limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;
  ```
- [ ] В `proxy_locations.conf.tmpl`:
  ```nginx
  location /api/ { limit_req zone=api burst=200 nodelay; ... }
  location ~ ^/api/v1/auth/ { limit_req zone=auth burst=10 nodelay; ... }
  ```
- [ ] Стартовать с generous-лимитами, мониторить `nginx_http_requests_total`/429, опускать

#### DoD
- [ ] Nginx config reload без ошибок
- [ ] Мониторинг 429 добавлен в Grafana
- [ ] Легитимные клиенты не throttлятся (неделя наблюдений)

- **Сложность:** S
- **Риск регрессии:** Средний. Стратегия: generous burst, мониторить неделю.
- **Ожидаемый эффект:** Defence-in-depth для backend и auth.
- **Статус:** [ ] ⚠️ прод — нужен мониторинг 429 после ввода

---

### [M19] — `useModulesState.ts`: дублированный watcher
- **Категория:** Frontend
- **Приоритет:** 🟡 Medium
- **Где:** `frontend/src/composables/useModulesState.ts:93-107`
- **Что найдено:** Два одинаковых watcher'а (на `modulesData` и на `sysSettingsData`) с идентичным телом. Вложенные `watch(ncForm, ..., {deep:true})` могут зарегистрироваться дважды (гонка, если оба триггернулись до `ncLoaded=true`).
- **Почему проблема:** Избыточные watchers (до 2 deep-watcher на `ncForm`), потенциально `ncDirty=true` после save.

#### План действий
- [ ] Заменить на один watch:
  ```ts
  watch([modulesData, sysSettingsData], ([m, s]) => {
    if (!ncLoaded.value && m && s) {
      ncLoaded.value = true
      setupDirtyWatchers()  // вынести в отдельную функцию
    }
  }, { once: true })
  ```
- [ ] Тест: «загрузилось → изменил NC URL → ncDirty=true» и «сохранил → ncDirty=false»

#### DoD
- [ ] Один deep-watcher вместо потенциально двух
- [ ] Тесты зелёные

- **Сложность:** XS
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** Устранение гонки.
- **Статус:** [x] 2026-07-26 — выполнено (useModulesState.ts:93-115)

---

### [M20] — `screenshot-service` healthcheck на `/health` (не `/ready`)
- **Категория:** Docker
- **Приоритет:** 🟡 Medium
- **Где:** `docker-compose.yml:88` (healthcheck), `screenshot-service/main.py` (нет `/ready`)
- **Что найдено:** Healthcheck на `/health` (liveness — процесс жив), но AGENTS.md §«Чего НЕ делать»: «❌ Не использовать Docker healthcheck на `/health` (использовать `/ready`)». Backend/worker используют `/ready`. Screenshot-service не имеет `/ready`.
- **Почему проблема:** `/health` ≠ readiness (зависимости готовы). Контейнер считается healthy даже если Playwright/Chromium не запустились → backend получает 503 на `/pdf`, но compose не рестартует.

#### План действий
- [ ] Добавить `/ready` в screenshot-service: проверка что кешированный `Browser` не None
- [ ] Обновить healthcheck на `/ready`
- [ ] Или — задокументировать исключение в ADR (stateless-сервис)

#### DoD
- [ ] Healthcheck на `/ready`
- [ ] При сломанном Chromium healthcheck красный

- **Сложность:** S
- **Риск регрессии:** Низкий.
- **Ожидаемый эффект:** Реальная проверка готовности.
- **Статус:** [x] 2026-07-26 — выполнено: добавлен `/ready` endpoint в screenshot-service (проверка `app["browser"]` не None + `browser.is_connected()` для CDP), compose healthcheck переведён с `/health` на `/ready`. `/health` оставлен (liveness для ручной проверки).

---

### [M21] — gitleaks/trivy/ZAP на `:latest` в CI
- **Категория:** CI/CD
- **Приоритет:** 🟡 Medium
- **Где:** `.github/workflows/security.yml:36,100`, `nightly-security.yml:101`
- **Что найдено:** `ghcr.io/gitleaks/gitleaks:latest`, `ghcr.io/aquasecurity/trivy:latest`, ZAP `:stable`. Floating tags.
- **Почему проблема:** Невоспроизводимость (новые правила), supply-chain, false-negatives при регрессии сканера.

#### План действий
- [x] Pin gitleaks/trivy по semver: `gitleaks:v8.30.1`, `trivy:0.72.0` (security.yml)
- [x] Pin ZAP по **digest** (не semver) — ZAP не публикует свежие semver-теги: последний `2.15.0` — октябрь 2024, дальше только weekly-релизы через rolling `:stable`/`:latest`. Pin по semver заморозил бы правила на 2 года (хуже для безопасности). Digest-pin даёт воспроизводимость без заморозки правил — тот же паттерн, что `postgres:16@sha256:…`
- [x] Dependabot `docker` ecosystem обновит digest gitleaks/trivy через PR
- [⚠️] **Dependabot НЕ покрывает** digest ZAP (он не сканирует `docker pull` внутри workflow `run:`). Ручной bump по календарю — см. комментарий в `nightly-security.yml` (команда для получения свежего digest). В идеале — завести sidecar-CRON или issue-reminder.

#### DoD
- [x] 0 `:latest`/`:stable` без digest для сканеров (gitleaks/trivy по semver, ZAP по digest@sha256)
- [~] Dependabot обновляет gitleaks/trivy; ZAP — ручной bump (ограничение Dependabot)

- **Сложность:** XS
- **Риск регрессии:** Очень низкий.
- **Ожидаемый эффект:** Воспроизводимые сканирования.
- **Статус:** [x] 2026-07-27 — выполнено. gitleaks `v8.30.1` + trivy `0.72.0` pin по semver (security.yml, Batch 3); ZAP pin по digest `:stable@sha256:8d387b1a…` (nightly-security.yml, эта итерация — закрыт пропуск из Batch 3, где ZAP был забыт). Образ pull'ится по digest, YAML+bash-синтаксис валидны. Caveat: ZAP-digest не автообновляется (Dependabot не покрывает `docker pull` в `run:`), нужен ежемесячный ручной bump — команда в комментарии.


---

### [M22] — `migrate_env_to_system_settings` race при параллельном старте
- **Категория:** Configuration
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/worker/main.py:64` (`_migrate_env()` на module-import), `backend/app/main.py`
- **Что найдено:** При `docker compose up` параллельно стартуют backend, worker, migrations — каждый импортирует `app.worker.main`/`app.main`, каждый вызывает `_migrate_env()`, который пишет в `/data/settings/system.json` через `atomic_write`. Race: три процесса одновременно читают легаси env, пишут.
- **Почему проблема:** На first-boot — некорректный `system.json` (маловероятно, но возможно при partial write если процесс убит). Логирование ещё не настроено в backend.

#### План действий
- [x] File-lock через `fcntl.flock` на `/data/settings/.migration.lock` — выполнено (новый `_migration_lock.py`)
- [~] Перенести `_migrate_env()` внутрь `startup()` — **отклонено**: существующий комментарий в `app/main.py:16-18` требует, чтобы миграция шла ДО `load_system_settings()` (та читает мигрированные значения). Перенос в startup сломал бы invariant. flock один решает race.
- [x] Тест на fresh install в staging — covered 8 unit-тестами (включая 8-поточный race-test)

#### DoD
- [x] File-lock работает (8 потоков пишут ровно один раз — `test_concurrent_callers_write_exactly_once`)
- [x] `_migrate_env()` остался на module-level (invariant `before load_system_settings()` сохранён)
- [x] Fresh-install тест зелёный (8 тестов в `test_system_config_migration.py`)

- **Сложность:** S
- **Риск регрессии:** Medium — миграция срабатывает один раз. Стратегия: существующие проды уже мигрированы.
- **Ожидаемый эффект:** Гарантированно single-execution.
- **Статус:** [x] 2026-07-26 — выполнено. Новый `_migration_lock.py` (context manager `migration_lock()` на `fcntl.flock`: non-blocking fast-path → 200ms-poll до 30s → final blocking fallback). `migrate_env_to_system_settings()` теперь re-check'ает существование файла ВНУТРИ lock'а (waiter видит свежий файл от peer и возвращает False без записи). Helpers `_collect_legacy_env`/`_log_deprecated_if_present` для чистоты. 8 unit-тестов (4 spec + 1 idempotency + 3 direct lock tests + 1 race-test через ThreadPoolExecutor). `structlog.testing.capture_logs` вместо `caplog` (caplog не перехватывает structlog).

---

## 🟢 LOW

> Краткие карточки. Не срочные, к росту/наведению порядка.

### [L1] — Миграции 077/084: ADD COLUMN NOT NULL DEFAULT паттерн
- **Категория:** Database
- **Где:** `migrations/versions/084_*.py:38`, миграция 077
- **Что найдено:** `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT '...'`. Прокатило (PG11+ meta-op), но нарушает zero-downtime-конвенцию AGENTS.md.
- **Действие:** Зафиксировать в код-ревью правило: для больших таблиц строго `nullable=True` → backfill → `SET NOT NULL`. Хороший пример — миграция 058.
- **Сложность:** XS (процедурное) · **Статус:** [ ]

### [L2] — `analytics.py`: 9 round-trip к БД на дашборд
- **Категория:** Performance
- **Где:** `backend/app/api/analytics.py:47-104`
- **Что найдено:** 9 SQL на запрос, distinct-scan по партициям `audit_log`.
- **Действие:** Redis-кеш 5–15 мин + daily-rollup таблица (ARQ-таск) + объединить `fetch_daily_*` в один `GROUP BY day, event_type`.
- **Сложность:** M · **Статус:** [ ]

### [L3] — `search/aggregate.py`: global offset для мульти-поиска
- **Категория:** Performance
- **Где:** `backend/app/services/search/aggregate.py:113-119`
- **Что найдено:** Каждый подзапрос читает `offset+limit` строк, на выходе 20.
- **Действие:** Лимит `offset+limit ≤ 200` для global search; глубже — single-type search с keyset.
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (services/search/aggregate.py:58 — `fetch_limit = min(offset + limit, 200)`)

### [L4] — `email_outbox.requeue_stale_sending` без distributed-lock
- **Категория:** Database
- **Где:** `backend/app/services/email_outbox.py:130-156`
- **Что найдено:** Массовый UPDATE по `status='SENDING' AND updated_at < ...` без SKIP LOCKED. Race при рестарте пула воркеров.
- **Действие:** Redis SET NX EX (как в `worker/tasks/helpdesk.py`).
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (worker/tasks/email_outbox.py: добавлен `_acquire_lock`/`_release_lock` по образцу messenger_outbox, lock_key `email:outbox:dispatch:lock`, TTL 180s; покрыто 2 новыми unit-тестами: no-redis + lock-busy)

### [L5] — `news/crud.py:38`: `selectinload(News.poll)` в list-endpoint
- **Категория:** Performance
- **Где:** `backend/app/services/news/crud.py:38,85,192`
- **Что найдено:** Poll грузится даже когда list его не отображает. Каскад poll → questions → options = 3 доп. SELECT.
- **Действие:** Убрать `selectinload(News.poll)` из `get_news_list`. Если нужен индикатор «есть опрос» — добавить колонку-флаг.
- **Сложность:** XS · **Статус:** [—] 2026-07-26 — отклонено как false-positive: `NewsOut` имеет поле `has_poll: bool` (schemas/news.py:50) и validator `check_poll` (стр.56-61) обращается к `data.poll` для выставления has_poll. Убрать selectinload → `has_poll` всегда False в списке. Требует миграции (добавить колонку-флаг `has_poll` в таблицу `news`) — отложить к M5 / M8.

### [L6] — Дублирование пагинации Query-deps (12 мест)
- **Категория:** Code Smell
- **Где:** `api/helpdesk/tickets.py:225,425`, `news/comments.py:59`, `feedback/routes.py:57,102`, `kb/comments.py:35`, `kb/versions.py:32`, `kb/articles/_list.py:29`, `search.py:45`, `meetings/participants.py:23`, `helpdesk/users.py:35`
- **Что найдено:** `limit: int = Query(default=20, ge=1, le=100)`, `offset: int = Query(default=0, ge=0)` копируется.
- **Действие:** `PaginationDep = Annotated[PaginationParams, Depends()]`.
- **Сложность:** XS · **Статус:** [—] 2026-07-26 — отклонено. Фактический анализ показал 12+ разных конфигураций `limit` (default {5,8,20,50,100,500} × max {50,100,200,500,1000}), каждая обоснована контекстом endpoint'а (helpdesk ≠ photo ≠ staff). Единый `PaginationDep` с одним max не подходит; parameterised dependency через `Annotated[...]` усложнит читаемость vs явный `Query`. Реальная ценность появится только при переходе на cursor-pagination ([M2]) — тогда и пересмотреть.

### [L7] — `keycloak_admin._is_unsafe_ip` разрешает приватные диапазоны
- **Категория:** Security
- **Где:** `backend/app/api/keycloak_admin.py:37-55`
- **Что найдено:** Намеренно разрешает 10/8, 172.16/12, 192.168/16 для admin-test endpoint → admin-pivot.
- **Действие:** `keycloak_allowed_hosts` allowlist в SystemSettings + pin-DNS. Минимум — не выводить `discovery_error: str(exc)` наружу.
- **Сложность:** M · **Статус:** [ ]

### [L8] — `_role_prefix` dead-параметры
- **Категория:** Code Smell
- **Где:** `backend/app/services/helpdesk/email_template.py:194-205` + call-sites `:281, :586`
- **Что найдено:** Параметры `is_outbound`, `is_assignee` сохранены «для совместимости», не используются.
- **Действие:** Удалить параметры + call-sites.
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (email_template.py:194-205 + 2 call-сайта, попутно почищены неиспользуемые локальные `is_assignee`/`is_assignee_reply`)

### [L9] — Feature Envy: `directories.build_xlsx` + `analytics.py` openpyxl-стилизация
- **Категория:** Code Smell
- **Где:** `backend/app/services/directories.py:461-491`, `api/analytics.py:346-354`
- **Что найдено:** Сервисный слой работает с openpyxl.styles, хардкодит цвета.
- **Действие:** Вынести в `app/services/export/xlsx_helpers.py` (`style_header_row`, `freeze_header`).
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — частично: создан `services/export/xlsx_helpers.py` + `directories.build_xlsx` мигрирован. `analytics.py` оставлен осознанно — там другая визуальная палитра (plain bold vs corporate blue), DRY-объединение было бы regression.

### [L10] — Cc-формат `{email,name}` без Pydantic-модели
- **Категория:** Code Smell
- **Где:** `api/helpdesk/tickets.py:108-154`, `worker/tasks/email_outbox.py:533-553`
- **Что найдено:** Cc-нормализация в роутере, форматирование в заголовок в worker'е, формат через dict в JSONB.
- **Действие:** Ввести `CcRecipient(BaseModel)`.
- **Сложность:** S · **Статус:** [x] 2026-07-26 — выполнено: добавлен `CcRecipient` Pydantic (schemas/helpdesk.py), применён в producer'ах (`threading.extract_cc`, `_normalize_cc_emails`), в `add_agent_reply` (cc → model_dump для JSONB), consumer `_format_cc_header` поддерживает и CcRecipient, и dict (legacy JSONB). Тесты обновлены под CcRecipient-сравнения.

### [L11] — Опечатки/англицизмы в docstrings
- **Категория:** Docs
- **Где:** `backend/app/services/helpdesk/lifecycle.py:5-7`
- **Что найдено:** `"правилаreopen из closed по времени enforcement-яются здесь"`.
- **Действие:** Поправить: «правила reopen из closed по времени применяются здесь».
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (lifecycle.py:5-6)

### [L12] — `PollPanelVoting.vue`: мёртвый i18n fallback
- **Категория:** i18n
- **Где:** `frontend/src/components/news/poll-panel/PollPanelVoting.vue:242,249`
- **Что найдено:** `t('common.save', 'Сохранить')` — второй аргумент (fallback) никогда не сработает, ключ существует.
- **Действие:** Убрать второй аргумент: `t('common.save')`.
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (PollPanelVoting.vue:242,249 — оба `common.save` и `common.cancel`)

### [L13] — `useFilesData.ts`: `reactive({...refs}) as unknown as UseFilesData`
- **Категория:** Frontend
- **Где:** `frontend/src/composables/useFilesData.ts:132-153`
- **Что найдено:** Единственный double type-cast во frontend (кроме вынужденных TipTap). `reactive()` разворачивает refs, искажая тип.
- **Действие:** Убрать `reactive()`-обёртку, вернуть объект как есть, или изменить `UseFilesData` interface на `Ref<...>`.
- **Сложность:** S · **Статус:** [x] 2026-07-27 — выполнено. Double cast `as unknown as UseFilesData` → single cast `as UseFilesData` (TypeScript не может вывести ref-unwrapping `reactive()`, но runtime-форма структурно соответствует `UseFilesData`). Добавлен explanatory-комментарий. Все 4 consumer'а (`useFilesBulkOps`, `useFilesUpload`, `useFilesTree`, `useFilesPageController`) используют unwrapped-форму — runtime unchanged. `npm run typecheck` + `lint:check` зелёные. Единственные оставшиеся `as unknown as` во frontend — вынужденные (TipTap `FigureImage.ts`, `Intl.supportedValuesOf` feature-detection).

### [L14] — Floating image tags без digest
- **Категория:** Docker
- **Где:** `frontend/Dockerfile:30`, `nginx/Dockerfile:1`, `nginx/Dockerfile.config:1`, `monitoring/node-exporter-textfile/Dockerfile:12`
- **Что найдено:** `nginx:1.27-alpine`, `python:3.12-slim`, `node:24-alpine`, `redis:7-alpine`, `postgres:16` — все floating.
- **Действие:** Pin по digest для prod-образов (`nginx:1.27-alpine@sha256:...`), обновлять через Dependabot.
- **Сложность:** S · **Статус:** [x] 2026-07-27 — выполнено. 8 external base images pinned по digest: nginx:1.27-alpine, node:24-alpine, node:24-slim, python:3.12-slim, postgres:16, redis:7-alpine, alpine:3.20, mcr.microsoft.com/playwright/python:v1.44.0-jammy. Формат `image:tag@sha256:<full> # pinned 2026-07-27`. `portal-*` images в compose НЕ тронуты (semver-lock ADR-047). Dependabot `docker` ecosystem расширен: добавлен `/monitoring` + новый entry `/` для docker-compose.yml (redis). `nginx/Dockerfile.config` имеет sync-comment (Dependabot не сканирует нестандартное имя → bump вручную в lockstep с monitoring alpine:3.20).

### [L15] — Nginx: нет явного `proxy_connect_timeout`
- **Категория:** Infrastructure
- **Где:** `nginx/templates/proxy_locations.conf.tmpl:47-61`
- **Что найдено:** Указаны `proxy_read_timeout 300s`, `proxy_send_timeout 300s`, но `proxy_connect_timeout` default 60s.
- **Действие:** Добавить `proxy_connect_timeout 10s;` для `/api/`.
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (proxy_locations.conf.tmpl:57-61)

### [L16] — `secret_crypto._get_fernet()` module-level cache без thread-safety
- **Категория:** Configuration
- **Где:** `backend/app/core/secret_crypto.py:24-34`
- **Что найдено:** Глобальный mutable без lock. Теоретическая race при thread-pool.
- **Действие:** `functools.lru_cache` или инициализация в `lifespan` startup.
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (core/secret_crypto.py: `_build_fernet()` через `@lru_cache(maxsize=1)`, `rotate_key_cache()` → `cache_clear()`)

### [L17] — `coverage-comment` job без fork-guard
- **Категория:** CI/CD
- **Где:** `.github/workflows/ci.yml:292-337`
- **Что найдено:** `pull-requests: write` без `if: github.event.pull_request.head.repo.full_name == github.repository`.
- **Действие:** Добавить fork-guard + branch protection на main.
- **Сложность:** XS · **Статус:** [x] 2026-07-26 — выполнено (ci.yml:297 — добавлен fork-guard в `if`)

### [L18] — Docker logging driver без `mode: non-blocking`
- **Категория:** Docker
- **Где:** `docker-compose.yml:1-7` (`x-logging`)
- **Что найдено:** `json-file` без `mode: non-blocking` — subtle backpressure при verbose-логах.
- **Действие:** Добавить `mode: "non-blocking"`, `max-buffer-size: "4m"` для backend/worker.
- **Сложность:** XS · **Статус:** [—] 2026-07-26 — отклонено (см. раздел «Отклонённые задачи»)

---

## Сильные стороны (НЕ сломать при рефакторинге)

> Эти решения грамотные. Любой рефакторинг должен их сохранить.

### Backend
- **Bind-параметры во всём raw SQL** — SQL-injection закрыт. User-data никогда не интерполируется.
- **nh3/DOMPurify последовательно** — `sanitize_html`/`sanitize_markdown`/`clean_title` on-write во всех persistence-путях. DOMPurify на каждом `v-html`.
- **Path traversal закрыт** — `safe_join_within` + `sanitize_name` + regex-валидация filename.
- **IDOR закрыт** — везде `require_*_permission`/ownership-check.
- **JWT-валидация строгая** — alg whitelist (RS/ES, no `none`/`HS256`), `kid`-lookup с JWKS refresh, `azp`/`aud`/`iss`/`exp`.
- **Outbox-pattern эталонный** — `FOR UPDATE SKIP LOCKED`, retry/backoff/DLQ, SMTP вне tx.
- **Partitioning `audit_log`** — native PG16, индексы на каждой партиции, retention через DROP TABLE.
- **GiST exclusion constraint** для meeting-room conflicts (`booking_rooms_no_overlap`).
- **Partial-unique `LOWER(email) WHERE deleted_at IS NULL`** — корректный soft-delete + email-reuse.
- **CSRF strict-match** Origin/Referer с fail-closed + double-submit token.

### Frontend
- **0 `as any`/`@ts-ignore`/`@ts-nocheck`** во всём `src/` (проверено grep'ом).
- **TanStack Query консистентна** — keys, инвалидация, abort-контроллеры, staleTime.
- **Cleanup listeners/timers/AbortController/SSE везде** — memory leaks не найдено.
- **sanitize.ts с 4 профилями DOMPurify** — разный уровень строгости для разных контекстов.
- **SSE с reconnect+heartbeat+onScopeDispose** — образцовый.
- **Silent token refresh с visibility-детекцией**, SSO loop-protection, redirect-lock между вкладками.

### Инфраструктура
- **ADR-045/046/047** (GHCR + deploy-bundle + semver-lock) — зрелая стратегия релиза.
- **structlog `stdlib.LoggerFactory()`** — корректно.
- **Atomic_write через `os.replace()`** для system.json — нет partial-write race.
- **`permissions: contents: read` по умолчанию** в CI (least privilege).
- **`no-new-privileges:true`** на всех сервисах.
- **Resource limits** на прикладных сервисах (backend/worker/nginx/frontend/screenshot).
- **`server_tokens off`, CSP, HSTS, security headers** в nginx.
- **Defense-in-depth CI**: gitleaks + trivy + ZAP + CodeQL + radon + jscpd + func-cov threshold.
- **Backup-функция через `pg_dump -Fc`** с проверкой `PGDMP` magic.
- **HEALTHCHECK на `/ready`** для backend/worker (DB+Redis check).

---

## Дисклеймер / достоверность

- Находки с пометкой `[verified]` перепроверены лично чтением кода (C1, C2, H1, H2, H5, H6, M1 + automетрики ruff/radon/bandit/eslint/vue-tsc).
- Находки без `[verified]` получены от экспертных субагентов и логически обоснованы, но требуют финального подтверждения (особенно DB/perf — `EXPLAIN ANALYZE` до заведения задач).
- **Учтено:** проект в production, intranet/VPN-only (внешний периметр уже ограничен), ~300 пользователей (не все N+1 критичны сегодня, но отмечены для роста).
- **Не являются находками** (сознательные решения): ADR-045/046/047, outbox-pattern, soft-delete везде кроме `users`, partial-unique `LOWER(email)`, partitioning `audit_log`, dual-auth ADR-017, dpd-рамка от path traversal, nh3/DOMPurify последовательность, TipTap lazy-loading, SSE cleanup.
- Существующий `docs/code-audit.md` (4-я итерация) учтён: новые находки не дублируют уже закрытые F1-H6.
- **Финальная рекомендация:** Этап 1 (Quick Wins) — 11 задач за 1–2 дня закроют 2 Critical, 5 High, большую часть Medium-инфра. Это даёт максимальный ROI без риска регрессии. Этапы 2–4 планировать как отдельные спринты с characterization-тестами.

---

## История изменений

| Дата | Кто | Что сделано |
|---|---|---|
| 2026-07-26 | Senior Architect (ZCode) | Первичное создание плана. 40 находок, 4 этапа, все карточки с DoD. |
| 2026-07-26 | Senior Architect (ZCode) | **Batch 1+2 (безопасные правки):** H10, H5, H2, M10, M19, L8, L11, L12, L15, L17 — все протестированы (3803 backend + 2130 frontend unit-тестов зелёные, ruff/mypy/eslint/vue-tsc/i18n-чек чистые). Отклонено: M16, L18 (с обоснованием). Подробности — в карточках `[x]`/`[—]` ниже. |
| 2026-07-26 | Senior Architect (ZCode) | **Batch 3 (10-ка для след. сессии, частично):** L3, L4, L9 (частично), L16, M21 — выполнено и протестировано (3805 backend unit-тестов зелёные). L5 — отклонено как false-positive (has_poll validator зависит от News.poll). Оставшиеся 4 (L6, H8, M20, L10) — в план следующей сессии. |
| 2026-07-26 | Senior Architect (ZCode) | **Batch 4 (оставшаяся 4-ка):** M20 (screenshot /ready), L10 (CcRecipient Pydantic) — выполнено; H8 (silent except) — частично (metadata.py + tickets.py + ingress.py — самые проблемные места); L6 — отклонено (12 разных конфигураций limit, единый PaginationDep не подходит). 3805 backend unit-тестов зелёные, ruff/mypy чисто. |
| 2026-07-26 | Senior Architect (ZCode) | **Batch 5 (CI-фикс + Backend safety-net):** Сначала починен CI после Batch 3/4 (ruff I001 в test_photos_storage.py + регенерация tests.generated.md). Затем — 3 S-задачи параллельно через subagents: H11 (56 GitHub Actions pinned по SHA; 3 из 7 SHA в таблице аудита оказались неверными — subagent перепроверил через `gh api`), M15 (Dockerfile DRY — `production FROM runtime-base`, -32 LOC дублирования apt-install), M22 (`migration_lock()` через `fcntl.flock` + re-check файла внутри lock'а; перенос в startup() отклонён — нарушил бы invariant before-load_system_settings). ci_lint зелёный, 75 unit-тестов миграции прошли, образ собирается и работает. |
| 2026-07-27 | Reydan (ZCode) | **DoD-верификация аудита:** выборочно перепроверены все 19 задач `[x]` + 2 `[x] частично` — все подтверждены чтением кода (H2/H5/H10/H11/H8/M15/M19/M20/M21/M22/L3/L4/L9/L10/L15/L16/L8/L12). Найдено 1 несоответствие: **[M21] ZAP пропущен** в Batch 3 (в карточке перечислен, но `nightly-security.yml:101` остался `:stable`). Исправлено: ZAP pinned по digest `:stable@sha256:8d387b1a…` (ZAP не публикует свежие semver-теги — последний 2.15.0 октябрь 2024, дальше weekly-rolling; pin по semver заморозил бы правила на 2 года — выбран digest-pin по аналогии с `postgres:16@sha256:…`). Образ pull'ится, YAML/bash валидны. Caveat: Dependabot не покрывает `docker pull` в workflow `run:` → ZAP-digest обновляется ручным bump по календарю (команда в комментарии). Карточка M21 приведена в соответствие (раньше статус в таблице `[x]` расходился с телом карточки `[ ]`). Заодно по ходу починены 2 побочные CI-баги: inline-комментарии после `FROM` в 7 Dockerfile'ах (ломали BuildKit → падали nightly-flakes + Dependabot Docker) и `test-integration.sh` (не пробрасывал `SECRET_KEY` → alembic падал на `ValidationError`). |
| 2026-07-27 | Reydan (ZCode) | **[H1] SSRF через /bookmarks/favicon — выполнено.** Создан `backend/app/core/net_guard.py` (~170 LOC) — единый SSRF-guard: `is_public_ip` / `is_safe_remote_url` (чистые функции), `resolve_all_ips` / `assert_url_safe` (async DNS через `loop.getaddrinfo`), `resolve_stable_ip` (double-resolve против DNS-rebinding/TOCTOU). `bookmarks._do_favicon_fetch` переписан с `follow_redirects=True` (небезопасно) на `follow_redirects=False` + ручной обход редиректов с re-валидацией каждого hop через `assert_url_safe` + `resolve_stable_ip`. Early-валидация на cache-MISS с negative-cache (ReDoS-защита: иначе атакующий бомбит endpoint private-доменами, триггеря sync DNS). Backward-compat shim в `email_images.py` (`is_safe_remote_url as is_safe_remote_url` re-export для `no_implicit_reexport` в mypy) — полная консолидация отложена к M9 (keycloak_admin использует обратную политику private-IP для Keycloak за VPN). Политика: блокировать все private/loopback/link-local/multicast/unspecified/reserved/cloud-metadata (по audit DoD; интранет-домены по private-IP получают `<n-icon>LinkOutline</n-icon>` fallback — UI уже это делал). 95 новых тестов (55 `test_net_guard.py` + 40 в `test_bookmarks_favicon.py`, включая 9 параметризованных SSRF-range + redirect-to-private + DNS-rebinding + negative-cache). ci_lint ✓ (698 файлов), 3895 unit-тестов ✓ (+69), 14 integration ✓ (bookmarks + helpdesk email_images). Заодно исправлен latent-баг: `is_public_ip` в email_images пропускал multicast (224/4, ff00::/8 имеют `is_global=True`) — теперь явно блокируется. |
| 2026-07-27 | Reydan (ZCode) | **M22-fix (регрессия Batch 5) + M4/L13/L14-верификация + CI drift-починка.** (1) **M22-fix**: `migration_lock()` падал в CI на `mkdir /data/settings` (нет `/data` вне контейнера) → ломал `openapi drift check`, 1 unit-тест structlog, playwright E2E. Добавлен graceful-degradation (no-op lock при PermissionError/OSError) + fast-path в `_migrations.py` (возврат без FS-touches когда нет legacy env и нет файла). Тест переписан на `patch.object(logger, "warning")` (детерминирован вне зависимости от `cache_logger_on_first_use` и pytest-randomly порядка). (2) **M4**: `limit` 500→200 (default 100), общая константа `BOOKINGS_LIMIT_MAX=200` в `_types.py` (mirror `MY_BOOKINGS_LIMIT_MAX`), service-clamp в lockstep. Разведка подтвердила: frontend не шлёт `limit` — безопасно. (3) **L13**: `as unknown as` → single `as UseFilesData`. (4) **L14**: 8 base images pinned по digest + Dependabot `/monitoring` + `/` (compose redis). (5) **CI drift-починка**: регенерированы `openapi.json` (limit 500→200 contract) и `tests.generated.md` (+72 строк: M4 + H1 SSRF-тесты). ci_lint ✓ (698 файлов), 105 unit-тестов затронутых модулей ✓. |

---

## Инструкция для продакшена (задачи, требующие действий на проде)

> Эти задачи нельзя выполнить «молча» через CI/CD — они требуют координированных
> действий оператора продакшена. Текст ниже — готовый runbook.

### Перед началом
- Прочитать `docs/deploy.md` (ADR-045/046/047 — registry-pull, deploy-bundle, semver-lock).
- Создать резервную копию БД (`setup.sh` → backup) **перед** любым изменением.
- Проверить, что в `.env` продакшена стоят уже изменённые значения (не дефолты из `.env.example`).

### Очередность внедрения (предлагаемая)
1. **C1 (.env.example)** — безопасно для текущего прода (он не трогает существующий `.env`), но защищает новые деплои. Можно в любой момент.
2. **C2 (Redis user)** — требует рестарта redis-контейнера. Делать в maintenance window.
3. **M5 (drop redundant indexes)** — миграция `CONCURRENTLY`, без блокировок, но проверять нагрузку.
4. **H12 (backup retention)** — безопасно, добавляет только cron-job.
5. **M17 (secret_crypto KDF)** — самый рискованный, требует blue-green migration. Делать последним.

### Подробные runbook'и по каждой задаче

#### [C1] — `.env.example` дефолт-секреты
**Что меняется в коде:** `.env.example` получит пустые значения по умолчанию + `Settings` начнёт валидировать block-list для `SECRET_KEY`/`ADMIN_PASSWORD` в production-режиме.

**Что нужно сделать на проде:**
1. Убедиться, что в `/path/to/portal/.env`:
   - `SECRET_KEY` — не `change_me_32_chars_minimum_secret_key_here` (это просто проверить: `grep SECRET_KEY .env`)
   - `ADMIN_PASSWORD` — не `change_me_on_first_login`
   - Если да — сгенерировать новые: `openssl rand -hex 48` для SECRET_KEY; для admin-пароля — сменить через Admin UI после старта.
2. Применить обновлённый образ (стандартный `docker compose pull && docker compose up -d`).
3. Если валидатор `Settings` упадёт со словами «SECRET_KEY matches known default» — это значит, что прод использует дефолт. Срочно сменить и перезапустить.

**Откат:** вернуть старый `.env` + старый образ. Данные не затронуты.

#### [C2] — Redis от root
**Что меняется в коде:** в `docker-compose.yml` сервис `redis` получит `user: "999:999"` (UID redis-юзера в alpine-образе).

**Что нужно сделать на проде:**
1. Перед деплоем проверить UID: `docker run --rm redis:7-alpine id redis` → должно вывести `uid=999(redis) gid=999(redis)`. Если другое число — поменять в compose.
2. Проверить, кто владелец `/tmp/redis.acl` после старта: если root-owned и redis-юзер не может прочитать — нужно скорректировать entrypoint (детали — в карточке C2).
3. Деплой: `docker compose pull redis && docker compose up -d redis`.
4. Проверка: `docker compose exec redis id` → `uid=999(redis)`; `docker compose exec redis redis-cli -a $REDIS_PASSWORD ping` → `PONG`.
5. Проверить, что приложение работает (логин, любая операция с session_id).

**Откат:** убрать `user:` из compose, `docker compose up -d redis`. Данные не затронуты.

#### [M5] — Drop redundant indexes
**Что меняется в коде:** миграция с `DROP INDEX CONCURRENTLY` для подтверждённых дубликатов.

**⚠️ Важно:** до деплоя каждый drop должен быть подтверждён `EXPLAIN ANALYZE` на **прод-данных**, что non-partial индекс не используется реальными запросами.

**Что нужно сделать на проде:**
1. До деплоя: для каждой пары индексов прогнать `EXPLAIN ANALYZE` list-запросов (см. карточку M5). Если non-partial индекс используется — НЕ дропать.
2. Деплой стандартный (миграция применится автоматически при старте backend).
3. После: проверить `pg_stat_user_indexes` — индексы действительно отпали, новые запросы используют partial.
4. Мониторить производительность list-endpoint'ов 1-2 дня.

**Откат:** восстановить индекс миграцией `CREATE INDEX CONCURRENTLY`. Данные не затронуты.

#### [H12] — Backup retention
**Что меняется в коде:** добавится `scripts/rotate-backups.sh` + документация в `docs/deploy.md`.

**Что нужно сделать на проде:**
1. После деплоя: настроить cron на хосте (или через sidecar) ежесуточный запуск `pg_backup` + `rotate-backups.sh`.
2. Настроить off-site copy (`rsync`/`rclone` на отдельный носитель).
3. Провести первый restore-drill: `pg_restore` в staging + smoke-тест schema.
4. Установить ежемесячный drill в календарь.

**Откат:** отключить cron. Существующие бэкапы не тронуты.

#### [M17] — secret_crypto KDF
**⚠️ Самый рискованный.** Меняет деривацию Fernet-ключа → инвалидирует существующие шифр-тексты (helpdesk-mailbox password) без migration path.

**Что нужно сделать на проде (только при blue-green migration):**
1. Деплой v1+v2并存 (legacy decrypt + new encrypt).
2. Через Admin UI обновить helpdesk mailbox settings (любое сохранение) → пароль перешифруется v2.
3. После подтверждения, что все секреты v2 — деплой v3, удаляющего legacy path.

**Откат на любой стадии:** вернуть предыдущий образ. Если уже пошли v2-шифр-тексты — нужна ручная миграция.

---

## Отклонённые задачи (с обоснованием)

### [M16] — Compose volumes DRY через YAML anchor — ОТКЛОНЕНО
**Обоснование:** backend и worker share 13 общих volumes, но backend имеет 2 дополнительных (`nginx_reload`, `certs`). Конструкция `volumes: *data-volumes` + доп. элементы не парсится стандартным `yaml.safe_load` (parser error: expected <block end>, but found '<block sequence start>') и хрупко работает с compose merge-семантикой. Риск инцидента на проде при деплое превышает ценность убираемого дублирования (25 строк).

**Альтернатива:** можно реализовать через `extends` (compose v2) или отдельный `docker-compose.override.yml`, но это меняет UX оператора. Оставить как есть; при следующем добавлении `/data/...` каталога — просто быть внимательным (git diff покажет оба сервиса).

### [L18] — Docker logging non-blocking mode — ОТКЛОНЕНО
**Обоснование:** Global switch на `mode: non-blocking` создаст риск потери логов при переполнении буфера (4MB). Для production-форензики (расследование инцидентов) потеря логов хуже, чем редкое backpressure при verbose-логах. Все 9 сервисов используют один anchor `*default-logging`, поэтому частичное применение (только к backend/worker) усложнит конфиг без явной пользы.

**Альтернатива:** если backpressure станет реальной проблемой (видно по `docker logs` latency в мониторинге) — пересмотреть с тюнингом `max-buffer-size` и feature-flag. Сейчас не обосновано.
