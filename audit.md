# Аудит портала — План работ (открытые задачи)

> **Создан:** 2026-07-26 · **Актуализирован:** 2026-08-19
> **Аудитор:** Senior Architect (ZCode)
> **Версия кода на момент аудита:** `da8d5f2` (main)
> **Масштаб аудита:** backend ~59k LOC Python · frontend ~85k LOC (Vue+TS) · ~290 endpoints · 9 сервисов в docker-compose
> **Метод:** 5 параллельных экспертных субагентов (Security / Backend-architecture / DB-perf / Frontend / Infra) + cross-верификация каждой ключевой находки чтением кода
> **Предыдущие итерации:** 4 раунда аудита 2026-06-06 → 2026-07-20 (файл `docs/code-audit.md` удалён 2026-08-19 при чистке; все P0/P1 тех раундов закрыты, история — в git).
> **Статус:** 🟡 **9 открытых задач**. Выполненные карточки (40 шт.) удалены 2026-08-19 после верификации; [H12] бэкапы сняты с плана в тот же день (администрируются оператором вне репо) — сводка в «Истории изменений».

---

## TL;DR

Проект **выше среднего по индустрии** (качество 8/10, архитектура 8/10). Глобальный рефакторинг **не нужен**.

Из 54 находок аудита 2026-07-26: **43 закрыто**, **4 отклонены** (M16, L5, L6, L18 — обоснования в конце), **1 снята с плана** ([H12] бэкапы — зона оператора, вне репо), **6 открыто**:

- **1 с действиями на проде** (код-часть минимальна): [M5] drop redundant indexes
- **1 решение утверждено, ждёт реализации**: [M1] счётчик комментариев (вариант C — чинить только `total`)
- **1 решение отложено**: [M11] Service Locator → DI
- **По готовности**: [M7] helpdesk email/notification Jinja2, [M17] secret_crypto KDF (⚠️ прод, blue-green), [L7] keycloak allowlist

**Спринт batch-5 — завершён 2026-08-19** (M18 rate limiting + L2 кеш дашборда + M13: все 22 api-модуля на generated types). План удалён по завершении (история — в git).

---

## Как работать с этим планом

### Статусы задач
- `[ ]` — todo (не начато)
- `[~]` — in-progress (в работе)
- `[x]` — done (готово, проверено)
- `[—]` — отклонено/не делаем (с обоснованием)

### Конвенция карточек
Каждая задача имеет **уникальный ID** (`[H12]`, `[M14]`, `[L3]`) — используйте его в коммит-сообщениях и PR: `fix(infra): [H12] backup rotation`. Карточка самодостаточна — её можно взять в работу без чтения всего файла.

### Перед каждой задачей
1. Прочитай **карточку целиком** + раздел «Где» (открой указанные файлы:строки).
2. Прочитай `AGENTS.md` соответствующий раздел (модульный док если задача модульная).
3. Если задача DB/perf — сначала проведи `EXPLAIN ANALYZE` на проде, потом пиши фикс.
4. Если задача с UI-нюансом — согласуй с владельцем продукта (помечено ⚠️).

### После каждой задачи
1. Прогон: `cd backend && ./scripts/ci_lint.sh && pytest tests/unit`
2. Прогон: `cd frontend && npm run lint:check && npm run typecheck && npm run test:unit`
3. Прогон: `./scripts/check-drift.sh` (если менялись API/типы/состав тестов)
4. Обнови статус в карточке (`[x]`) + дату в «Истории изменений».
5. В коммит-сообщении укажи ID задачи.

---

## Дорожная карта (Roadmap)

### 🟢 Этап 1 — действия на проде (низкий риск, высокий эффект)
- **[M5]** Drop redundant indexes · S · [ ] ⚠️прод

### 🟡 Этап 2 — требуется решение
- **[M1]** Comments: `total` считать все включая soft-deleted (решение C, 2026-08-19) · S · [ ]

### 🟠 Этап 3 — рефакторинг (characterization-тесты первыми)
- **[M7]** helpdesk email/notification в Jinja2 · M · [ ]
- **[M11]** Service Locator → DI · M · [ ] ⚠️decision
- **[M13]** frontend `api/*.ts` → generated types · M · **[x] 2026-08-19** (все 22 модуля)
- **[M17]** `secret_crypto` KDF + key-versioning · L · [ ] ⚠️прод

### 🔵 Этап 4 — к росту, не срочно
- **[M18]** nginx rate limiting · S · **[x] 2026-08-19** (прод-наблюдение недели — на операторе)
- **[L2]** analytics Redis-кеш + daily-rollup · M · **[x] 2026-08-19**
- **[L7]** keycloak_admin allowlist · M · [ ]

---

## Сводная таблица открытых задач

| ID  | Приоритет | Категория | Задача | Сложн. | Этап | Статус |
|-----|-----------|-----------|--------|--------|------|--------|
| M1  | 🟡 Medium | DB | Comments: total считать все (решение C) | S | 2 | [ ] |
| M5  | 🟡 Medium | DB | Drop redundant indexes | S | 1 | [ ] ⚠️ прод |
| M7  | 🟡 Medium | Code Smell | helpdesk email/notification в Jinja2 | M | 3 | [ ] |
| M11 | 🟡 Medium | Architecture | Service Locator → DI | M | 3 | [ ] ⚠️ decision (отложено) |
| M13 | 🟡 Medium | Frontend | api/*.ts → generated types | M | 3 | [x] 2026-08-19 (все 22 модуля; news/files/helpdesk — вторым заходом) |
| M17 | 🟡 Medium | Config | secret_crypto KDF | L | 3 | [ ] ⚠️ прод |
| M18 | 🟡 Medium | Infra | nginx rate limiting | S | 4 | [x] 2026-08-19 (прод-наблюдение — оператор) |
| L2  | 🟢 Low | Perf | analytics Redis-кеш | M | 4 | [x] 2026-08-19 |
| L7  | 🟢 Low | Security | keycloak_admin allowlist | M | 4 | [ ] |

### Условные обозначения статусов
- `⚠️ прод` — требует действий на продакшене (см. раздел «Инструкция для продакшена»)
- `⚠️ decision` — требует решения команды перед реализацией

---

## 🟡 MEDIUM

### [M1] — Comments list/count рассинхрон `[verified]` — решение C принято 2026-08-19
- **Категория:** Database
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/api/news/comments_repo.py:30-40` (`list_comments` без `deleted_at IS NULL`), `:20-27` (`count_active_comments` с фильтром); аналогично `kb/comments_repo.py`; consumer `api/news/comments.py:65-66`
- **Что найдено:** `count_active_comments` фильтрует `deleted_at IS NULL`, `list_comments` — нет. `_to_public` маскирует удалённые как `is_deleted=True`. При M удалённых OFFSET-страница вернёт меньше активных, чем `limit`. `total` (бейдж) не совпадает с реальным перебором.
- **⚠️ ВАЖНО:** Простое добавление `deleted_at IS NULL` в `list_comments` **сломает UX** (placeholder «[удалено]» пропадёт из ленты). Это **сознательное UX-решение**, не баг.

#### Решение владельца продукта (2026-08-19): вариант C
Лента не меняется (placeholder «[удалено]» остаётся как есть), чинится только `total` — считает все комментарии, включая soft-deleted. Минимальный риск, UX неизменен.

#### План действий
- [ ] `count_active_comments` в `news/comments_repo.py` и `kb/comments_repo.py` → считать без фильтра `deleted_at IS NULL` (total = перебор `list_comments`)
- [ ] Unit-тест на пагинацию с перемежающимися soft-deleted (5 active + 3 deleted, limit=4 → total совпадает с перебором)

#### DoD
- [ ] `total` совпадает с реальным числом возвращённых при переборе страниц
- [ ] Тест: 5 active + 3 deleted, limit=4 → корректная пагинация

- **Сложность:** S
- **Риск регрессии:** Средний (UX). Стратегия: согласовать с командой, feature-flag если надо.
- **Ожидаемый эффект:** Корректная пагинация, нет UI-«дыр».

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
  3. Hardcoded HTML/CSS: `email_template.py:44-57` палитра инлайнится в f-строки (~30 мест). Дубли в `notifications.py:246-253,291-300`.
- **Почему проблема:** Shotgun surgery при каждом изменении брендинга/письма; дублированная логика рассинхронизируется.
- **Примечание 2026-08-19:** dead params `_role_prefix` уже удалены (L8, 2026-07-26). Остальные пункты актуальны.

#### План действий
- [ ] Создать `app/services/system_settings_runtime.py` → `get_portal_settings() -> PortalSettings` (timezone + base_url, один source)
- [ ] Слить `_select_agents_to_notify` + `_load_agents_for_email` в одну параметризованную `_load_active_agents(*, fields, require_inapp, require_email)`
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

---

### [M11] — Hidden coupling через `get_settings()` singleton (Service Locator)
- **Категория:** Architecture
- **Приоритет:** 🟡 Medium
- **Где:** модули с module-level инициализацией (примеры: `app/api/auth/_helpers.py:35`, `app/services/keycloak/settings.py:17`; полный список в оригинальной карточке — 11 модулей)
- **Что найдено:** Module-level `settings = get_settings()` читает настройки ОДИН РАЗ при import. Service Locator anti-pattern.
- **Почему проблема:** Тест-изоляция (два теста с разными settings нельзя запустить в одном процессе без `monkeypatch`). Латентный import side-effect. Невозможность DI.
- **Последствия:** Сложность тестирования, «магический» сбой при первом импорте в новой среде.

#### План действий ⚠️ крупный рефакторинг, командное решение
> **2026-08-19:** решение отложено владельцем — вернуться, когда тест-изоляция станет реальной болью. Статус-кво работает.

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

---

### [M13] — Frontend `api/*.ts`: 13/15 модулей дублируют `types.gen.d.ts`
- **Категория:** Frontend / TypeScript
- **Приоритет:** 🟡 Medium
- **Где:** `frontend/src/api/news.ts:3-30`, `files.ts:3-89`, `users.ts`, `helpdesk.ts`, `meetings.ts` (используют только `photos.ts:2` и `kb.ts:3`)
- **Что найдено:** В проекте есть автогенерируемый `types.gen.d.ts` (актуальный), но 13 из 15 api-модулей вручную переопределяют интерфейсы. Пример: `api/news.ts:3` `interface News { ... }` — 30+ полей, продублированных из `components['schemas']['NewsOut']`.
- **Почему проблема:** Ручные типы расходятся с бэкендом при каждом изменении OpenAPI. Любой дрифт → тихая type-неинформация.
- **Верифицировано 2026-08-19:** `api/news.ts:4` — по-прежнему ручной `interface News`. Задача актуальна.

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
- **Статус:** [x] 2026-08-19 (batch-5, два захода). Разведка: реальный масштаб больше карточки — **22 модуля / ~217 интерфейсов** (не 13). **Заход 1** (17 модулей, ~101 интерфейс): audit, auth, notifications, matrixBot, emailOutbox, messengerOutbox, mailingRecipients, userAttributeMappings, kb, links, signature, feedback, analytics, users, directories, meetings, erpSync — 3 параллельных субагента, паттерн photos.ts (прямые алиасы + `Omit<...> & {...}` сужения). **Заход 2** (3 крупнейших): news 33/36, files 24/25, helpdesk 25/26 — enum-unions helpdesk сверены со StrEnum бэкенда; union-типы выводятся из схем (`Schema['field']`). Честно оставлены ручными (с комментариями «нет в OpenAPI»): response-типы audit/outbox/mailbox-test (эндпоинты без Pydantic response-model — кандидат на backend-задачу), report-интерфейсы erpSync (JSONB), poll-voters (`{[key:string]: unknown}[]`), multipart form-модели helpdesk (UploadFile в схемах = string[]), query-param unions, UI-типы. Потребители поправлены минимально (~8 файлов, коалесценции `?? null` и guards). Тесты: +11 spec на изменённые строки (diff-cover frontend 100%).

---

### [M17] — `secret_crypto.py`: SHA-256 без KDF, нет ротации ключа
- **Категория:** Configuration / Security
- **Приоритет:** 🟡 Medium
- **Где:** `backend/app/core/secret_crypto.py`
- **Что найдено:**
  ```python
  secret = get_settings().secret_key.encode("utf-8")
  key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
  _fernet = Fernet(key)
  ```
  Не PBKDF2/scrypt/HKDF — обычный SHA-256 (одна итерация). Нет key-versioning — смена `SECRET_KEY` ломает расшифровку существующих секретов.
- **Почему проблема:** При компрометации `SECRET_KEY` attacker восстанавливает Fernet-ключ тривиально и расшифровывает все секреты (helpdesk-mailbox password) задним числом.
- **Последствия:** Необратимая компрометация at-rest секретов при утечке `SECRET_KEY`.
- **Верифицировано 2026-08-19:** деривация по-прежнему `sha256(secret)` без KDF. Задача актуальна. (Thread-safety `lru_cache` — закрыта ранее, L16.)

#### План действий ⚠️ высокий риск из-за миграции существующих шифр-текстов
- [ ] Заменить на HKDF или PBKDF2-HMAC-SHA256 с salt + high iterations
- [ ] Ввести key-versioning: рядом с encrypted-secret хранить `key_version`
- [ ] Blue-green migration: `decrypt_v1` (legacy) + `decrypt_v2` (new), миграция при следующем update helpdesk-settings

#### DoD
- [ ] Существующие шифр-тексты расшифровываются (legacy path)
- [ ] Новые шифруются v2
- [ ] Тест: migration path covered

- **Сложность:** L (с key-versioning)
- **Риск регрессии:** Высокий — инвалидирует существующие шифр-тексты. Стратегия: blue-green, v1+v2 сосуществуют, миграция.
- **Ожидаемый эффект:** Современная деривация; возможность ротации.

---

### [M18] — Nginx: нет rate limiting на уровне reverse-proxy
- **Категория:** Infrastructure
- **Приоритет:** 🟡 Medium
- **Где:** `system_data/nginx/nginx.conf`, `nginx/templates/https_server.conf.tmpl`, `nginx/templates/proxy_locations.conf.tmpl`
- **Что найдено:** Нет `limit_req_zone`/`limit_req`. Rate-limit только в приложении (`fastapi-limiter`), и только на специфичных endpoints (`/auth/local/login`). Остальные ~290 endpoints без лимита ни на nginx, ни на backend.
- **Почему проблема:** При DDoS на `/api/...` backend держит всю нагрузку. Auth-brute-force только на одном endpoint — `/auth/refresh`, `/auth/sso/callback` без лимита.
- **Последствия:** DoS backend'а, ускоренный brute-force.
- **Верифицировано 2026-08-19:** `limit_req` отсутствует в шаблонах nginx. Задача актуальна.

#### План действий
- [x] В `nginx.conf` http {} — зоны + `limit_req_status 429;` (дефолтный 503 путался бы с backend-ошибками):
  ```nginx
  limit_req_zone $binary_remote_addr zone=api:10m  rate=30r/s;
  limit_req_zone $binary_remote_addr zone=auth:10m rate=30r/m;  # НЕ 5r/m — см. ниже
  limit_req_status 429;
  ```
- [x] В `proxy_locations.conf.tmpl` — `limit_req zone=api burst=200 nodelay` в `location /api/`; новый regex-location `~ ^/api/v1/auth/` с `limit_req zone=auth burst=20 nodelay` (regex выигрывает у prefix — auth-пути попадают в свою зону)
- [x] Стартовали с generous-лимитами; мониторинг 429 — панель Grafana (Loki) + алерт `NginxRateLimit429`
- [x] **Отклонение от карточки:** auth `5r/m burst=10` → **`30r/m burst=20`**. Причина: фронт делает silent-refresh каждые **4 минуты из каждой вкладки** (`stores/auth.ts:14`) — при восстановлении 10+ вкладок браузера `5r/m` отрубал бы легитимные refresh → разлогины. 30 r/m всё равно режет лавину brute-force (app-level лимит `/auth/local/login` и так жёстче — 5/15мин IP).

#### DoD
- [x] `nginx -t` — syntax ok (живой dev-стек, конфиг применён)
- [x] Live-тест: 25 подряд POST на auth-путь → первые прошли до backend, хвост отрублен nginx'ом **429**; 429 подтверждены в access-логе (JSON `status:429`) → данные для Loki/Grafana идут
- [x] Мониторинг 429: панель «Rate-limit: отказы 429» в дашборде Portal — Infrastructure (Loki `{compose_service="nginx"} | json | status="429"`) + Loki-ruler алерт `NginxRateLimit429` (>100 за 5 мин, warning → email админам)
- [ ] Легитимные клиенты не throttлятся — **неделя наблюдений на проде (оператор)**: панель + алерт; если 429 у честных пользователей — поднять burst/опустить rate в `system_data/nginx/nginx.conf`

- **Сложность:** S
- **Риск регрессии:** Средний. Стратегия: generous burst, мониторить неделю.
- **Ожидаемый эффект:** Defence-in-depth для backend и auth.
- **Статус:** [x] 2026-08-19 — код-часть выполнена (зоны api/auth + 429-статус + Grafana-панель + Loki-алерт + docs/monitoring.md). ⚠️ прод-часть: неделя наблюдения за 429 после деплоя.

---

## 🟢 LOW

> Краткие карточки. Не срочные, к росту/наведению порядка.

### [L2] — `analytics.py`: 9 round-trip к БД на дашборд — ✅ закрыт 2026-08-19 (batch-5)
- **Категория:** Performance
- **Где:** `backend/app/api/analytics.py` (`get_dashboard`)
- **Что найдено:** 5 SQL на каждый запрос дашборда (scalars-CTE + 4 daily-серии), включая distinct-scan по партициям `audit_log`.
- **Сделано (2026-08-19):** Redis-кеш всего ответа `GET /analytics/dashboard`, ключ `analytics:dashboard:v1:{days}`, TTL 600с (`ANALYTICS_DASHBOARD_CACHE_TTL_SECONDS` в `core/constants.py`). Cache-hit → 0 SQL; Redis-сбой не роняет эндпоинт (transparent-degrade + debug-лог). 5 unit-тестов (`test_analytics_cache.py`): hit/miss/TTL/ключ-по-days/отказ-read/отказ-write.
- **Осознанно отложено:** объединение 4 daily-запросов в один `GROUP BY` (разные источники — большой CTE, отдельная задача при росте); daily-rollup-таблица (кеш снимает нагрузку целиком при cache-hit — rollup неактуален на ~300 пользователях).
- **Сложность:** M · **Статус:** [x] 2026-08-19

### [L7] — `keycloak_admin._is_unsafe_ip` разрешает приватные диапазоны
- **Категория:** Security
- **Где:** `backend/app/services/keycloak/admin_store.py` (после M9-рефакторинга; ранее `api/keycloak_admin.py:37-55`)
- **Что найдено:** Намеренно разрешает 10/8, 172.16/12, 192.168/16 для admin-test endpoint → admin-pivot.
- **Действие:** `keycloak_allowed_hosts` allowlist в SystemSettings + pin-DNS. Минимум — не выводить `discovery_error: str(exc)` наружу.
- **Сложность:** M · **Статус:** [ ]

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
- **ADR-045/046/047** (Registry + deploy-bundle + semver-lock) — зрелая стратегия релиза.
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

- Открытые карточки `[verified]` перепроверены чтением кода; остальные — из субагент-экспертизы с логическим обоснованием (DB/perf — требуют `EXPLAIN ANALYZE` до заведения задач).
- **Учтено:** проект в production, intranet/VPN-only (внешний периметр уже ограничен), ~300 пользователей (не все N+1 критичны сегодня, но отмечены для роста).
- **Не являются находками** (сознательные решения): ADR-045/046/047, outbox-pattern, soft-delete везде кроме `users`, partial-unique `LOWER(email)`, partitioning `audit_log`, dual-auth ADR-017, защита от path traversal, nh3/DOMPurify последовательность, TipTap lazy-loading, SSE cleanup.

---

## Инструкция для продакшена (задачи, требующие действий на проде)

> Эти задачи нельзя выполнить «молча» через CI/CD — они требуют координированных
> действий оператора продакшена. Текст ниже — готовый runbook.

### Перед началом
- Прочитать `docs/deploy.md` (ADR-045/046/047 — registry-pull, deploy-bundle, semver-lock).
- Создать резервную копию БД (`setup.sh` → backup) **перед** любым изменением.
- Проверить, что в `.env` продакшена стоят уже изменённые значения (не дефолты из `.env.example`).

### Очередность внедрения (предлагаемая)
1. **M5 (drop redundant indexes)** — миграция `CONCURRENTLY`, без блокировок, но проверять нагрузку.
2. **M18 (nginx rate limiting)** — код готов (2026-08-19); осталась неделя наблюдения за 429 после деплоя.
3. **M17 (secret_crypto KDF)** — самый рискованный, требует blue-green migration. Делать последним.

### Незакрытая прод-верификация ранее выполненных задач
- **[C2] Redis от root (закрыт 2026-07-28):** после деплоя проверить `docker compose exec redis sh -c 'cat /proc/1/status | grep Uid'` → `999`, healthcheck зелёный, сессии работают.
- **[C1] дефолт-секреты (закрыт 2026-07-28):** убедиться, что prod-`.env` имеет валидный `SECRET_KEY` (≥48 символов, не дефолт) и `ADMIN_PASSWORD` ≠ `change_me_on_first_login`.

### Подробные runbook'и по каждой задаче

#### [M5] — Drop redundant indexes
**Что меняется в коде:** миграция с `DROP INDEX CONCURRENTLY` для подтверждённых дубликатов.

**⚠️ Важно:** до деплоя каждый drop должен быть подтверждён `EXPLAIN ANALYZE` на **прод-данных**, что non-partial индекс не используется реальными запросами.

**Что нужно сделать на проде:**
1. До деплоя: для каждой пары индексов прогнать `EXPLAIN ANALYZE` list-запросов (см. карточку M5). Если non-partial индекс используется — НЕ дропать.
2. Деплой стандартный (миграция применится автоматически при старте backend).
3. После: проверить `pg_stat_user_indexes` — индексы действительно отпали, новые запросы используют partial.
4. Мониторить производительность list-endpoint'ов 1-2 дня.

**Откат:** восстановить индекс миграцией `CREATE INDEX CONCURRENTLY`. Данные не затронуты.

#### [M17] — secret_crypto KDF
**⚠️ Самый рискованный.** Меняет деривацию Fernet-ключа → инвалидирует существующие шифр-тексты (helpdesk-mailbox password) без migration path.

**Что нужно сделать на проде (только при blue-green migration):**
1. Деплой v1+v2 сосуществуют (legacy decrypt + new encrypt).
2. Через Admin UI обновить helpdesk mailbox settings (любое сохранение) → пароль перешифруется v2.
3. После подтверждения, что все секреты v2 — деплой v3, удаляющего legacy path.

**Откат на любой стадии:** вернуть предыдущий образ. Если уже пошли v2-шифр-тексты — нужна ручная миграция.

#### [M18] — nginx rate limiting — код готов (2026-08-19)
**Что уже в коде:** зоны `api` (30 r/s, burst 200) и `auth` (30 r/m, burst 20), `limit_req_status 429`, панель Grafana + алерт `NginxRateLimit429`.

**Что нужно сделать на проде:**
1. Деплой стандартный (пересборка `portal-nginx-config` в CI + `docker compose pull && up -d`).
2. Проверить: `docker compose exec nginx nginx -t` → ok; алерт-правило появилось: `curl -s http://localhost:3100/loki/api/v1/rules`.
3. Неделя наблюдения: дашборд Portal — Infrastructure, панель «Rate-limit: отказы 429».
4. Если 429 у легитимных пользователей (не атака) — поднять burst / опустить rate в `system_data/nginx/nginx.conf`.

**Откат:** закомментировать `limit_req`-строки в `nginx/templates/proxy_locations.conf.tmpl` (зоны в nginx.conf безвредны), redeploy sidecar. Данные не затронуты.

---

## Отклонённые задачи (с обоснованием — НЕ переоткрывать без новых данных)

### [M16] — Compose volumes DRY через YAML anchor — ОТКЛОНЕНО (2026-07-26)
**Обоснование:** backend и worker share 13 общих volumes, но backend имеет 2 дополнительных (`nginx_reload`, `certs`). Конструкция `volumes: *data-volumes` + доп. элементы не парсится стандартным `yaml.safe_load` и хрупко работает с compose merge-семантикой. Риск инцидента на проде при деплое превышает ценность убираемого дублирования (25 строк).
**Альтернатива:** `extends` (compose v2) или `docker-compose.override.yml`, но это меняет UX оператора. При добавлении нового `/data/...` — просто быть внимательным (git diff покажет оба сервиса).

### [L18] — Docker logging non-blocking mode — ОТКЛОНЕНО (2026-07-26)
**Обоснование:** Global switch на `mode: non-blocking` создаст риск потери логов при переполнении буфера (4MB). Для production-форензики потеря логов хуже, чем редкое backpressure при verbose-логах. Все 9 сервисов используют один anchor `*default-logging`, частичное применение усложнит конфиг без явной пользы.
**Альтернатива:** если backpressure станет реальной проблемой (видно по `docker logs` latency) — пересмотреть с тюнингом `max-buffer-size`.

### [L5] — selectinload(News.poll) в list-endpoint — ОТКЛОНЕНО как false-positive (2026-07-26)
**Обоснование:** `NewsOut.has_poll` (validator `check_poll`) обращается к `data.poll` — убрать selectinload → `has_poll` всегда False в списке. Требует миграции колонки-флага — отложено.

### [L6] — Единый PaginationDep для 12 мест — ОТКЛОНЕНО (2026-07-26)
**Обоснование:** 12+ разных конфигураций `limit` (default {5,8,20,50,100,500} × max {50,100,200,500,1000}), каждая обоснована контекстом endpoint'а. Единый `PaginationDep` не подходит. Пересмотреть при переходе на cursor-pagination.

---

## История изменений

> Полные детальные записи сессий — в git-истории (коммиты `refactor(audit): ...`).
> Выполненные карточки удалены из файла 2026-08-19; ниже — сводка.

| Дата | Что сделано |
|---|---|
| 2026-07-26 | Первичное создание плана: 54 находки (2 Critical, 12 High, 22 Medium, 18 Low), 4 этапа. **Batch 1+2:** H10, H5, H2, M10 (частично), M19, M15, L8, L11, L12, L15, L17, L3, L4, L9 (частично), L16, M21, M20, L10, M22; H8 (частично). Отклонены: M16, L18, L5, L6. |
| 2026-07-27 | DoD-верификация всех `[x]` на тот момент; найден и закрыт пропуск M21 (ZAP digest-pin); **[H1] SSRF favicon** — создан `net_guard.py`, bookmarks переписан (95 тестов); **[M4]** limit 500→200; **[L13]** type-cast; **[L14]** 8 base images digest-pinned. |
| 2026-07-28 | **Спринт 1: C1 + C2 + H3.** C1 — `.env.example` без дефолт-секретов + production-валидатор `Settings` + preflight-gate. C2 — redis от uid=999 (entrypoint chown + `su redis`; итерация: `user:` ломал CI из-за root-owned volume). H3 — `extended_search` опция вместо jsonpath (jsonpath `like_regex` не индексируется GIN — разведка). Полная re-верификация всех 28 задач `[x]` — 0 реальных регрессий. |
| 2026-07-29 | **Спринт 2: H9 + окончание H8.** H9 — IP-маскинг в логах (телефон/ФИО отсутствуют в логах — задача сужена M→S). H8 — классификация ~58 `except Exception`, закрыты категории A+B. |
| 2026-08-02 | **Спринт 3 (batch-3, PR #62): M12 + M14 + M8 + M3 + M2.** Frontend-рефакторинги (composables + TanStack Query), analytics-реестр `_DATASETS`, batch-INSERT meetings outbox, keyset-pagination (миграция 091 + `_cursor_pagination.py` + `useCursorPager`). |
| 2026-08-09 | **Re-верификация H4/H6/H7 после отзыва внешнего аудитора** — найден и исправлен баг карточки H7 (`UserRole.USER="user"` не существует, реальная роль `reader`). **Batch-4 (PR #97): H6** (`EventType` → `KNOWN_EVENT_TYPES` frozenset), **H4** (TTL-кеш news_categories/email_settings + DRY `atomic_write` + `_tls.py` to_thread), **H7** (консолидация enum-источников + `UserRole(StrEnum)` + замена литералов, 15 файлов), **M6** (декомпозиция `_ingest_message` 143→19 LOC), **M9** (`keycloak_admin` 394→181 LOC, вынесены admin_store/probe), **L1** (PR-шаблон с zero-downtime чекпоинтом). |
| 2026-08-19 | **Чистка плана:** верифицированы и удалены 40 выполненных карточек + 3 устаревших файла (`docs/code-audit.md` — 4 раунда 2026-06→07, всё закрыто; `docs/wip/audit-batch-3.md`, `docs/wip/audit-batch-4.md` — планы смёрженных PR #62/#97). Осталось 10 открытых задач. ⚠️ Находка: артефакт **L1** (`.github/PULL_REQUEST_TEMPLATE.md`) удалён при миграции GitHub→Forgejo Actions (PR #1) — zero-downtime чекпоинт пропал из review-процесса; кандидат на восстановление в `.forgejo/PULL_REQUEST_TEMPLATE.md` (Forgejo поддерживает). Прод-верификация M13/M17/M18 выполнена (задачи подтверждённо открыты). |
| 2026-08-19 | **[H12] снята с плана** — резервное копирование (ротация, off-site copy, restore-drill) администрируется оператором вне репозитория, это не кодовая задача. Открытых задач: 9. |
| 2026-08-19 | **Решения по M1/M11 + выбор спринта batch-5.** M1 — вариант C (total считает все включая soft-deleted, лента без изменений; реализация маленькая, ждёт очереди). M11 — решение отложено. Спринт batch-5: M18 + M13 + L2, план — `docs/wip/audit-batch-5.md`. |
| 2026-08-19 | **[M18] выполнено** (batch-5): зоны `api` 30r/s burst 200 + `auth` 30r/m burst 20 (отклонение от 5r/m карточки — silent-refresh каждые 4 мин/вкладку), `limit_req_status 429`, live-тест на dev-стеке (хвост бомбы → 429 в access-логе). Мониторинг: Grafana-панель + Loki-алерт `NginxRateLimit429` + docs/monitoring.md. ⚠️ неделя прод-наблюдения — оператор. |
| 2026-08-19 | **[L2] + [M13 частично] выполнены** (batch-5). L2: Redis-кеш `GET /analytics/dashboard` (ключ по days, TTL 600с, transparent-degrade при Redis-сбое), 5 unit-тестов; объединение daily-SQL и rollup отложены осознанно. M13: реальный масштаб 22 модуля/~217 интерфейсов; мигрировано 17 модулей (~101 интерфейс, 3 субагента), честно оставлены типы без OpenAPI-схем (audit/outbox response без Pydantic-model, erpSync reports-JSONB, query-params, UI-формы). Остаток: news/files/helpdesk. Проверки: backend ci_lint ✓ + 4648 unit ✓ + diff-cover 100%; frontend typecheck/lint/i18n ✓ + 2457 unit ✓ + diff-cover 80%; check-drift ✓ (tests.generated.md регенерирован). |
| 2026-08-19 | **CI-фикс PR #76:** `backend/pytest integration` упал — integration-тесты зовут `get_dashboard(db, days=...)` напрямую, redis стал обязательным параметром. Фикс: `Annotated[Redis \| None, Depends(get_redis)] = None` (DI-путь неизменен, прямой вызов прозрачно без кеша) + забытый импорт `Annotated`. После фикса все 17 чеков зелёные. |
| 2026-08-19 | **[M13 завершён — второй заход]:** news 33/36, files 24/25, helpdesk 25/26 (+9 честно оставленных: poll-voters untyped, mailbox-test untyped dict, multipart-формы helpdesk). enum-unions helpdesk сверены с backend StrEnum. +11 spec (diff-cover frontend 15/15 = 100%). **batch-5 закрыт полностью: M18 + L2 + M13.** Открытых задач аудита: 6 (M5, M1, M7, M11, M17, L7). |
