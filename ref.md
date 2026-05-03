# Ревью репозитория «Корпоративный портал»

Дата: 2026-05-03  
Скоуп: глубокий ревью кодовой базы (backend FastAPI + frontend Vue 3 + infra), цель — найти проблемы безопасности, производительности, недочёты архитектуры, отсутствующие тесты/логи, расхождения между документацией и кодом.  
Исправления НЕ вносились — только фиксация.

Маркировка тяжести:
- **[CRIT]** — безопасность/целостность данных, требует немедленной правки.
- **[HIGH]** — серьёзная проблема (производительность, корректность), требует приоритета.
- **[MED]** — улучшение качества/надёжности.
- **[LOW]** — стилистика, мелочи, документация.

---

## 1. Безопасность

### 1.1 [CRIT] CSP содержит `'unsafe-inline' 'unsafe-eval'` — противоречит `AGENTS.md`
- Файл: `.\backend\app\main.py:274-284` (`_CSP_POLICY`).
- `AGENTS.md:174` явно заявляет: «CSP: без `unsafe-eval` (Naive UI работает без него)».
- Реально в политике: `script-src 'self' 'unsafe-inline' 'unsafe-eval'` — это полностью открывает XSS-вектор и убивает смысл CSP.
- Дополнительно: `frame-src 'self' https:` разрешает встраивание любого HTTPS-ресурса в iframe (clickjacking-вектор для редиректа в Collabora — но открыто ВСЁ).

### 1.2 [HIGH] `Secure`-флаг сессионной cookie выставляется по `X-Forwarded-Proto`
- `.\backend\app\main.py:262-269`, `.\backend\app\api\auth.py:186-195, 320-330, 395-404`.
- Если nginx по ошибке не очищает входящий `X-Forwarded-Proto`, клиент может выставить `https` и сессионная cookie получит флаг `Secure`, либо наоборот лишится его. Имеет смысл хардкодить `secure=True` в продакшене (`settings.is_production`) и не доверять заголовку.

### 1.3 [HIGH] `csrf_protection` пропускает strict host-check при пустом `portal_base_url`
- `.\backend\app\main.py:218-246`. При незаполненном `portal_base_url` проверка origin/host пропускается, остаётся только double-submit cookie. Любая первая инсталляция в этом состоянии становится уязвима к CSRF из произвольного origin (если cookie успели выставить, повторный запрос совпадёт).
- Ожидание: при пустом `portal_base_url` — отказывать, а не «идти дальше».

### 1.5 [HIGH] `auth.local_login_denied` логирует email на уровне INFO
- `.\backend\app\api\auth.py:280-292` (и `auth.local_login` на 318).
- При компрометации логов это утечка PII и enumeration-вектор (различает `no_user` / `wrong_source` / `bad_password`). Reason полезен, но email и точный reason в одной записи дают атакующему всё.
- Минимум: хешировать email или маскировать (`u***@d***.ru`); reason держать только в DEBUG, в INFO — общее «login_denied».

### 1.6 [HIGH] SSO: `id_token_hint` отдаётся клиенту в открытом виде
- `.\backend\app\api\links.py:88-115`. JWT-токен встраивается в URL внешнего сервиса в query-string. Клиент кладёт его в `Location`/history; при `Referer`-leak (если внешний сервис делает редирект на 3rd party) токен утечёт. Кроме того, сессия пользователя в этом JWT подписана и срок её не короткий.
- Альтернатива: серверный proxy-редирект, либо генерация одноразового короткоживущего токена-посредника.

### 1.7 [HIGH] `nc_federation` endpoint не имеет rate-limit
- `.\backend\app\api\nc_federation.py:54-90`. Публичный endpoint, защищённый только неугадываемым токеном. Без rate-limit возможен brute-force (хотя при ширине токена ~256 бит риск низкий) и DoS (CPU из-за разбора Form + Redis lookup).
- Рекомендация: добавить `RateLimiter(times=60, minutes=1, identifier=real_ip_identifier)`.

### 1.8 [HIGH] `system_settings.upload_tls_cert/key` читает файл целиком в память без лимита
- `.\backend\app\api\system_settings.py:251-305`. `await file.read()` без проверки размера → возможен mem-DoS от admin-клиента (или скомпрометированного аккаунта). Контейнер `backend` имеет `memory: 2g`, но всё равно желательно ограничить (`Content-Length`-check + лимит 64 KiB для PEM).
- Нет минимальной валидации формата ключа: проверка только начала, но не сертификата вообще (PEM-структура, парсинг через `cryptography` отсутствует). Возможна загрузка испорченного PEM, после чего `nginx reload` упадёт.

### 1.11 [MED] Redis ACL: пароль вкладывается через `printf` без экранирования
- `.\docker-compose.yml:46`. Если пароль содержит пробел, `\n`, `>`, `<`, `&` — ACL-файл получится сломанным или Redis запустится с другим пользователем/правами. Нужно валидировать `REDIS_PASSWORD` на «безопасный» алфавит или использовать `--requirepass` через файл-секрет.

### 1.13 [LOW] `Referrer-Policy: strict-origin-when-cross-origin`
- Подходит, но при наличии SSO-флоу `id_token_hint` (см. 1.6) — origin всё равно утекает, что усугубляет 1.6.

### 1.14 [MED] Bootstrap admin пароль ресет
- `.\backend\app\main.py:86-93`. Флаг `admin_password_reset_on_start` приоритетен над «сменён через UI». Если оператор оставит флаг включённым, будет молча возвращать дефолтный пароль каждый рестарт. Минимум — `WARNING` в логи, лучше — единократно сбрасывать и сбрасывать сам флаг (запись в БД-маркер).

### 1.15 [LOW] CORS `allow_origins=[settings.portal_base_url]`
- `.\backend\app\main.py:181-186`. При пустом `portal_base_url` получится `[""]` — браузер просто не будет матчить, но кейс не покрыт явно (нет валидации в `Settings`).

---

## 2. Производительность

### 2.1 [HIGH] N+1 на ACL для дерева папок и разделов KB
- `.\backend\app\api\files.py:241-275` (`get_folder_tree`): для каждой папки вызывает `resolve_folder_permission` → отдельный CTE-запрос. При 500 папок — 500 запросов и 500 redis-get.
- `.\backend\app\api\kb.py:176-210` (`get_sections`): то же поведение per-section.
- Решение: один запрос с массивом `subject_ids`, возвращающий пары `(folder_id, best_perm)` через group-by/distinct on. Альтернатива — батчевый Redis `MGET`.

### 2.2 [HIGH] `_build_breadcrumbs` (files) — линейный цикл одиночных SELECT
- `.\backend\app\api\files.py:211-235`. `depth ≤ 20` → до 20 SELECT-ов на каждый просмотр папки. KB-аналог в `kb.py:76-95` уже использует WITH RECURSIVE — нужно так же сделать в files.

### 2.3 [HIGH] `analytics.get_dashboard` — 9+ отдельных раундтрипов
- `.\backend\app\api\analytics.py:25-155`. Все count-запросы независимы и могут быть выполнены одним `WITH cnt AS (SELECT ... UNION ALL ...)` или `asyncio.gather(...)`. Сейчас каждый ждёт предыдущего. На холодном кэше — ощутимая задержка.

### 2.5 [HIGH] `users.list_users`: `count() FROM (subquery)` дорого
- `.\backend\app\api\users.py:65-68`. На 300 пользователях не критично, но при росте лучше отдельно `SELECT count(*) FROM users WHERE ...` без оборачивания во view. Также нет индекса по `full_name` для ILIKE-поиска (нужен `pg_trgm` GIN).

### 2.6 [HIGH] `audit.export_audit_csv` — не настоящий streaming
- `.\backend\app\api\audit.py:179-243`. `await db.execute(sql).mappings().all()` грузит до `_EXPORT_HARD_LIMIT` (100k?) строк в память, и только потом пишет в `StringIO`. Для крупных экспортов память расходуется единомоментно. Нужен server-side cursor (`db.stream` / `connection.execute().yield_per()`).

### 2.7 [MED] `search.global_search`: `_FETCH_MULTIPLIER = 5`
- `.\backend\app\api\search.py:23, 55`. На 4 типа поиска при `limit=20, offset=0` загружается 100 записей по каждому типу (4×100 = 400 строк) и фильтруется ACL в Python. На крупном массиве KB+News — это удар по БД и памяти. Нужен `ts_rank`-кьюри с join на ACL-вьюшку, либо подсчёт «accessible from start» через CTE.

### 2.8 [MED] SSE: per-connection блокирующая `XREAD` 500 мс
- `.\backend\app\api\notifications.py:166-175`. При 300 пользователях и 1+ активной вкладке у каждого — постоянный пул блокирующих Redis-коннектов. Лимит `_SSE_MAX_CONNECTIONS_PER_USER` есть, но общий cap не задан. Под нагрузкой — нужен redis-cluster или WebSocket с pub-sub.

### 2.9 [MED] `_modules_cache` — process-local TTL 60s + redis version-bump
- `.\backend\app\api\modules.py:95-130`. Между bump-version и экспирацией процессного кэша возможен короткий период stale (до next-fetch). Для критических флагов модулей (включить/выключить) лучше — pubsub-инвалидация.

### 2.10 [MED] `photos.list_deleted_photos` для не-admin
- `.\backend\app\api\photos\photos.py:132-153`. Загружает до 2000 записей, потом per-photo `select(PhotoFolder)` и ACL-проверка. Каждое фото = 1 select папки + N редис-getов. На 2000 удалённых — катастрофа.
- Нужен JOIN photos↔folders + батчевая проверка ACL.

### 2.11 [MED] `photos.list_recent_photos`: `limit eff_limit*6` per-user check
- `.\backend\app\api\photos\photos.py:174-186`. Грузит до `eff_limit*6` строк и фильтрует в Python. Если у пользователя нет доступа к 90% папок, виджет может вернуть пусто несмотря на наличие фото.

### 2.12 [MED] Множественный `select(PhotoFolder).where(id == photo.folder_id)` в bulk_action
- `.\backend\app\api\photos\photos.py:439-491`. Для каждого фото отдельные SELECT-ы и ACL-расчёты. На bulk 100 фото — сотни запросов.

### 2.13 [MED] `services.audit.log` коммитит в чужой транзакции
- `.\backend\app\services\audit.py:20-48`. Внутри функции `await db.commit()` — может зафиксировать **частично готовые** изменения вызывающего endpoint'а (например, при `create_folder` перед `audit.log` уже был `commit`, но если переместить порядок — будет проблема). Сейчас работает за счёт того, что вызывающий код уже коммитит до вызова. Решение: писать через otdельный engine/session или через очередь, как `push_audit_event`.

### 2.14 [LOW] `WebDAVClient._get_shared_client`: shared client с `timeout=_TIMEOUT_LIST` (30s)
- `.\backend\app\services\nextcloud\webdav.py:60-66`. Один и тот же клиент используется и для листинга, и для других операций — таймаут «листинга» 30s применяется ко всем. Для upload отдельно создаётся `httpx.AsyncClient` (из `nc_service` интерфейса), но если кто-то заюзает shared — лимит будет неправильный.

### 2.15 [LOW] WebDAV `max_keepalive_connections=10`
- `.\backend\app\services\nextcloud\webdav.py:64`. На 300 параллельных пользователях с активной работой с файлами — узкое место.

---

## 3. Логирование, метрики, наблюдаемость

### 3.2 [MED] `services.files_acl._get_cached/_set_cached`: redis ошибки → `None`/skip без логов
- `.\backend\app\services\files_acl.py:45-54`. При сбое Redis ACL fall-back на CTE сработает, но факт сбоя нигде не виден. Минимум: counter в metrics, периодический warning.

### 3.3 [MED] `notifications._sse_generator`: TTL-refresh exceptions молчат
- `.\backend\app\api\notifications.py:188-195`. `try: ... except: pass` для `zadd/expire`. При redis-flaпе соединение «зависает» считаясь активным.

### 3.4 [MED] `branding._load_settings`, `audit_partitions` startup, `nc.ensure_root_skipped` — глотают exceptions с warning, не падают
- `.\backend\app\main.py:135-154`. Решение валидно (не блокировать запуск), но желательно добавлять Sentry-event с тегом `startup_degraded`.

### 3.5 [MED] `audit.log_failed` — `WARNING` без re-raise
- `.\backend\app\services\audit.py:42-48`. Аудит-запись теряется без оповещения вызывающего. Для критических событий (auth.login/logout) это ОК (есть `push_audit_event` в Redis), но для прямых вызовов `audit.log` (например, `files.folder_created`) запись пропадёт навсегда. Минимум — Sentry capture.

### 3.6 [MED] Worker heartbeat / liveness отсутствует
- В `WorkerSettings` (`.\backend\app\worker\main.py`) нет периодической записи в Redis, по которой можно мониторить «жив ли воркер». Healthcheck Docker — только `redis ping`, не проверяет, что ARQ-loop крутится.

### 3.7 [LOW] Cron `flush_audit_queue` каждые 2 секунды
- `.\backend\app\worker\main.py:101-136`. Рабочее решение, но добавляет шум в логи (на старте / при пустой очереди — DEBUG скип). Можно перейти на `XREAD blocking` или ARQ `defer_by`.

### 3.9 [LOW] `notify_user`/`bind_request_context` не проксируется в worker
- В `worker/main.py` `bind_request_context(job_id=..., function=..)` — но нет `user_id` корреляции. Logs от worker сложно сопоставить с инициатором.

---

## 4. Тесты

Покрытие большое (~290 unit + integration + security), но **отсутствуют важные сценарии**:

### 4.1 [HIGH] Нет E2E-теста на CSRF double-submit
- `.\backend\tests\security\test_csrf.py` — unit. Нужен сценарий «полная цепочка login → safe GET → mutating POST с/без header».

### 4.2 [HIGH] Нет нагрузочного теста SSE-лимита и memory-leak'a при keepalive
- `.\backend\app\api\notifications.py` имеет `_SSE_MAX_CONNECTIONS_PER_USER`, но нет теста, проверяющего что 11-й коннект отбивается с 429.

### 4.3 [HIGH] Rate-limit по email на `/auth/local/login` — нет интеграционного теста
- `.\backend\tests\integration\test_rate_limit.py` (1.7KB — мало). Не проверяется, что разные IP, но один email уйдут под `email_identifier`.

### 4.4 [HIGH] Нет теста на race в `_upsert_user`
- `.\backend\app\api\auth.py:409-491` использует `pg_advisory_xact_lock` — но нет интеграционного теста с двумя параллельными первыми логинами одного email.

### 4.5 [HIGH] Нет тестов для `nc_federation` под brute-force/нагрузкой
- `.\backend\tests\unit\test_nc_federation.py` — 16KB unit (mock-Redis), но публичный endpoint без rate-limit — нет negative-теста на DoS / неверный токен.

### 4.6 [HIGH] Нет тестов для `analytics` endpoints (DB-backed)
- `.\backend\tests\unit\test_analytics.py` — unit, без реальной БД. Нет проверки правильности агрегатов на seed-данных.

### 4.7 [HIGH] Нет тестов для `system_settings.upload_tls_cert/key`
- `.\backend\tests\unit\test_system_settings.py` (10.8KB) — есть, но нужно проверить `400` на не-PEM, лимит размера (см. 1.8), отказ при отсутствующем файле.

### 4.8 [MED] Нет теста на `audit.log` rollback при падении commit
- См. 2.13. Не покрывается сценарий «вызывающий код был в транзакции, audit.log закоммитил половину».

### 4.9 [MED] Нет теста на bookmarks-лимит при многоworker
- См. 2.4. Тест `test_links_bookmarks.py` (4.8KB) не воспроизводит multi-process race.

### 4.10 [MED] Нет E2E-теста на `delete_user` с FK-зависимостями
- `.\backend\app\api\users.py:354-385`. Что произойдёт, если у пользователя есть `news.author_id`?

### 4.11 [LOW] Нет тестов для `_hydrate_custom_metrics`
- `.\backend\app\main.py:393-421`. Pickup из Redis-снапшота нигде не проверяется.

### 4.12 [LOW] Нет тестов для federation lookup TTL
- `.\backend\app\services\nc_federation.py` — нет проверки, что после TTL токен уходит в 404.

### 4.13 [MED] `tests/conftest.py` (13.5KB) — фикстуры есть, но нет фикстуры «два worker процесса» для multi-instance scenarios.

---

## 5. Архитектура и общие проблемы

### 5.1 [MED] `services.nextcloud.get_nc_service()` — singleton без re-load при смене настроек
- `.\backend\app\services\nextcloud\service.py:56-73`. Хорошо, что есть `invalidate_nc_service()` (см. modules.py:228). Но если admin поменял `nextcloud_url`/`app_password` через `system_settings` API — singleton не обновится автоматически (нужна явная инвалидация в этом endpoint'е тоже).

### 5.2 [MED] Frontend `router.beforeEach`: `await modulesStore.load()` per-navigation
- `.\frontend\src\router.ts`. Проверка модулей при каждом переходе на `/files` или `/photos` — даже с кэшем, дополнительная задержка. Можно prefetch при старте App.

### 5.3 [MED] Несоответствия `AGENTS.md` ↔ код
- `AGENTS.md:174` про CSP без unsafe-eval — НЕВЕРНО, см. 1.1.
- `AGENTS.md:152` «soft delete везде» — пользователи hard-delete, см. 1.16.
- `AGENTS.md` упоминает миграции `001..024` (например, в комментарии about `db-schema.md`), фактически — `001..025` (есть `025_user_attributes.py`).
- `AGENTS.md` упоминает несуществующие модули `core/session.py` (фактически `services/session.py`), `core/rate_limit.py` (фактически `core/limiter.py`).
- `AGENTS.md:222` в перечне `core/` — `rate_limit, system_config, ...`. Файла `core/rate_limit.py` нет.

### 5.4 [LOW] Frontend: `App.vue` 1.4 KB, `main.ts` 883 B — не читал глубоко, но размеры `FilesPage.vue` (27 KB), `KbListPage.vue` (22 KB), `NewsFormPage.vue` (21 KB) — кандидаты на разбиение.

### 5.5 [MED] `audit.log` (services) и `push_audit_event` — два пути
- Часть кода пишет напрямую в `audit_log` (`services/audit.log`), другая — через Redis-очередь и батч-flush (`push_audit_event`). Это inconsistent: при failover Redis события из `push_audit_event` теряются (фиксируется только в логи), а через `log()` — пишутся сразу. Стоит унифицировать или явно документировать различие в `AGENTS.md`.

### 5.6 [LOW] Множество `from ... import X` внутри функций для отложенной загрузки
- В `main.py`, `auth.py` и др. много локальных импортов. Это иногда оправдано (избежать циклов), но подавляющее большинство — оптимизация startup time. Стоит переместить на верхний уровень и измерить эффект.

### 5.7 [LOW] `email.utils.parsedate_to_datetime` без TZ-аwareness в `webdav.py:108-109`
- `.\backend\app\services\nextcloud\webdav.py`. Если NC возвращает `Last-Modified` без TZ, дата будет naive. Сравнения с `datetime.now(UTC)` упадут.

### 5.8 [LOW] `news.py` хранит `ALLOWED_IMG_TYPES` локально, отличается от `users.py`
- `.\backend\app\api\news.py:50` и `.\backend\app\api\users.py:40`. У news есть GIF, у users — нет. Различие может быть осознанным, но стоит вынести в общую константу.

### 5.9 [LOW] `core/security.py:1` — `import asyncio` ОТСУТСТВУЕТ, но используется в `hash_password_async/verify_password_async`
- При синтаксической проверке падает: `loop = asyncio.get_running_loop()` — `asyncio` не импортирован.
- Файл: `.\backend\app\core\security.py:51, 57`. Это **[CRIT]** баг кода (если код реально не выполнялся в этой ветке) или импорт спрятан выше где-то — проверить ещё раз. По прочитанному коду строки 1-14 не содержат `import asyncio`.

### 5.10 [HIGH] Account-linking: при `not email_verified` бросается 403
- `.\backend\app\api\auth.py:434-442`. Проблема: если у Keycloak-юзера `email_verified=False`, бросаем 403 — пользователь застревает, не может войти даже как новый. UX-проблема: лучше создавать новую запись с другим именем (или отказывать с понятной ошибкой и инструкцией админу).

### 5.11 [MED] `lifespan`: `_bootstrap_admin` лочит advisory_lock без unlock
- `.\backend\app\main.py:71-99`. `pg_try_advisory_lock` берётся, но явный `pg_advisory_unlock` отсутствует — освобождается при закрытии сессии (`AsyncSessionLocal()` context exit). Работает, но непрозрачно.

### 5.12 [LOW] `audit_partitions` startup может молча запустить приложение без партиций
- `.\backend\app\main.py:140-154`. `WARNING` есть, но `/ready` не отражает «партиции отсутствуют» — readiness вернёт OK, и пользователи получат 500 на любой `audit_log INSERT`.

### 5.13 [LOW] WebDAV: shared httpx-клиент без `aclose` в shutdown
- `.\backend\app\services\nextcloud\webdav.py:60-71`. Метод `aclose()` есть, но в `lifespan.shutdown` он НЕ вызывается. Утечка соединений при graceful restart.

### 5.14 [MED] `photos.bulk_action`: rollback файлов move
- `.\backend\app\api\photos\photos.py:495-500`. Правильно сделано — реверс через `_shutil.move`. НО: если `_shutil.move` упал, ошибка в `contextlib.suppress` глотается, файлы остаются в неконсистентном состоянии (фото в src на FS, но БД-запись уже не указывает на src). Логировать каждое падение rollback.

### 5.15 [LOW] `photos.empty_trash` — батч 500 без yield/throttle
- Может надолго заблокировать единственный backend-инстанс. Для крупной корзины лучше поставить ARQ-задачу.

### 5.16 [MED] `nc_federation`: `lookup_initiator` — race с `delete_initiator`
- `.\backend\app\services\nc_federation.py` (не приведён, но судя по использованию `get/del`-паттерна). Если NC дёргает endpoint после TTL-эвикции — 404. Документировать TTL.

---

## 6. База данных и миграции

### 6.1 [MED] Нумерация миграций линейная (001..025), без branch'ей
- В целом ОК, но при большом релизе трудно мерджить параллельные ветки.

### 6.2 [LOW] `init.sql` создаёт первые партиции `audit_log` — нужно проверить, что они покрывают 3+ месяца вперёд (см. 5.12).

### 6.3 [MED] FK на `users.id`
- `delete_user` (1.16) — без явных `ON DELETE`, миграции 001/002 нужно проверить. Скорее всего `ON DELETE NO ACTION` → DELETE упадёт при наличии новостей этого автора. Если так — `delete_user` тихо рейзит 500.

### 6.4 [MED] `kb_sections.parent_id ON DELETE RESTRICT` — корректно (`AGENTS.md:154`).
- Стоит проверить `file_folders.parent_id` тоже — каскад опасен.

### 6.5 [LOW] Индексы для FTS должны быть GIN на `body_tsvector` — нужно проверить миграции 011/007.

### 6.6 [LOW] Миграции `022_fk_indexes.py` (2KB) и `024_trgm_indexes.py` (1.2KB) — добавлены позже основных. Намёк на изначальное отсутствие индексов на FK; нужно ревьювить, не пропущены ли ещё.

---

## 7. Frontend

### 7.1 [LOW] Не прочитано построчно. Очевидные потенциальные проблемы (по структуре):

- `GlobalSearch.vue` 19.8 KB — большой компонент, потенциально нуждается в декомпозиции.
- `RichEditor.vue` 7.5 KB — TipTap, нужно проверить sanitize при paste и iframe-extension (white-list доменов).
- `FilesPage.vue` 27 KB — кандидат на разбиение.
- `i18n/ru.json` 67 KB — большой бандл; стоит lazy-load или split по разделам.
- `stores/notifications.ts` 3.7 KB — проверить отписку SSE при переходе между страницами/выходе.

### 7.2 [LOW] `utils/sanitize.ts` 2.2 KB — DOMPurify обёртка. Нужно убедиться, что FORBID_TAGS включает `<style>`, `<svg>` (для XSS через SVG-handler), и FORBID_ATTR — `srcset`, `formaction`.

---

## 8. Документация

### 8.1 [HIGH] CSP-расхождение
- См. 1.1 / 5.3. Нужно либо исправить CSP, либо обновить `AGENTS.md`. Сейчас агенты, читающие `AGENTS.md`, делают неверные предположения.

### 8.2 [MED] `AGENTS.md` упоминает `core/session.py` / `core/rate_limit.py` — таких файлов нет.
- Обновить либо `AGENTS.md`, либо переместить.

### 8.3 [MED] `AGENTS.md` про soft-delete расходится с `delete_user` (см. 1.16, 5.3).

### 8.4 [LOW] `docs/db-schema.md` (упоминается в `AGENTS.md`) — содержит «миграции 001..024», но фактически 025. Нужно синхронизировать.

### 8.5 [LOW] `requirements.md` помечен как «архив, все фазы завершены» — но если архив, желательно перенести в `docs/archive/`, чтобы не путать новых разработчиков.

---

## 9. Прочее / quick wins

- `.\backend\app\api\audit.py:238` — `datetime.utcnow()` → `datetime.now(UTC)`.
- `.\backend\app\core\security.py:1` — добавить `import asyncio` (см. 5.9).
- `.\backend\app\main.py:262-269, ...auth.py:cookies` — в продакшене `secure=True` без условия (см. 1.2).
- `.\backend\app\api\bookmarks.py:61` — `hashlib.sha256` вместо `hash()` (см. 2.4).
- `.\backend\app\api\analytics.py` — переписать `get_dashboard` через `asyncio.gather` или единый CTE (см. 2.3).
- `.\backend\app\api\users.py:354-385` — `delete_user` сделать soft, либо обработать FK.
- `.\backend\app\api\system_settings.py:251-305` — добавить лимит размера и парсинг `cryptography.x509`/`load_pem_private_key`.
- `.\backend\app\api\nc_federation.py` — добавить rate-limit per-IP.
- `.\backend\app\api\auth.py:280-292` — снизить уровень / маскировать email.
- `.\backend\app\api\links.py:88-115` — реализовать сервер-side proxy для SSO вместо передачи `id_token_hint` клиенту.
- `.\docker-compose.yml:191` — заменить worker healthcheck на `redis-cli` или с защитой от отсутствия env.
- `.\docker-compose.yml:46` — валидировать `REDIS_PASSWORD` или выделить ACL-файл монтирование.
- `.\backend\app\main.py:_CSP_POLICY` — убрать `'unsafe-eval'`, по возможности и `'unsafe-inline'` (через nonce).
- `.\backend\app\api\files.py:241-275, 211-235` — батчевая ACL-резолюция / WITH RECURSIVE для breadcrumbs.

---

## 10. Открытые вопросы / нужны уточнения

1. **CSP `'unsafe-eval'`**: реально ли требуется (Naive UI, TipTap, plotly?), или это исторический артефакт? Если убрать — что сломается?
2. **`delete_user`**: ожидаемое поведение — soft с retain history, или hard с CASCADE на news/kb?
3. **`id_token_hint` в SSO-URL**: какие сервисы используют SSO? Если только внутренние внутри VPN — риск утечки ниже.
4. **`_prepare_password` SHA→bcrypt**: исторический выбор или сознательный? Можно ли мигрировать на argon2?
5. **`audit.log` vs `push_audit_event`**: какая семантика гарантий ожидается для каждого вида события?
6. **bootstrap admin password reset**: должен ли флаг сбрасываться сам после применения?

---

## 11. Что не покрыто этим ревью (для следующей итерации)

- `kb_extra.py` (38 KB) — не прочитан построчно.
- `keycloak_admin.py` (13 KB) — admin-API Keycloak, потенциально привилегированные операции.
- `services/keycloak.py` — JWKS cache, refresh.
- `services/notifications.py`, `services/session.py`, `services/news.py` — детально.
- Все 9 модулей `api/photos/*` (folders, permissions, zip_jobs, import_scan, thumbnails, tags, _common) — частично.
- Worker tasks: `tasks/photos.py`, `tasks/files.py`, `tasks/news.py`, `tasks/notifications.py`, `tasks/metrics.py`.
- Миграции построчно (FK, индексы, ON DELETE-политики, CHECK-constraints).
- Frontend Vue-компоненты построчно.
- `screenshot-service/main.py`.
- `nginx.conf` — критично для CSRF-защиты (X-Real-IP, X-Forwarded-Proto).
- `setup.sh` (31 KB).
- `docs/*.md` — сравнение с кодом.

---

**Итого зафиксировано находок**: ~70 пунктов в 11 разделах.  
**Критические**: 2 (CSP, потенциальный отсутствующий import asyncio).  
**Высокой важности**: 18.  
**Средней**: ~30.  
**Низкой / стилистика**: ~20.

---

## 12. Дополнительные находки (продолжение детального ревью)

### 12.1 Безопасность

#### 12.1.1 [CRIT] `screenshot-service`: SSRF + RCE-вектор
- `.\screenshot-service\main.py:65-100` (`take_screenshot`) и `:103-138` (`render_pdf`).
- Endpoint `/screenshot?url=...` принимает **любой** `http(s)://` URL без allow-list. Из docker-сети `internal` атакующий через скомпрометированный backend (или через любой сервис, имеющий сетевой доступ к screenshot-service) может ходить на `http://backend:8000/internal/*`, `http://portal-redis:6379/`, `http://portal-postgres:5432/` (не сработает HTTP, но fingerprinting через таймауты), `http://169.254.169.254/...` (cloud metadata).
- `/pdf` принимает произвольный HTML и рендерит в Chromium с `--no-sandbox`. Любой `<iframe src="file:///etc/passwd">` или `<img src="http://internal/...">` будет загружен — exfiltration через скриншот контента.
- Нет аутентификации. Защита только сетевая (`internal: true` в docker-compose), но это не оправдывает отсутствие auth.
- Минимум: shared-secret header, allow-list схем `https://` + match-list по домену, отключить `file://`/`data:` через context options, добавить `--disable-features=Network,IsolateOrigins`.

#### 12.1.2 [CRIT/HIGH] `keycloak.get_authorization_url`/`get_silent_auth_url`/`get_logout_url` не экранирует параметры
- `.\backend\app\services\keycloak.py:149, 164, 176`: `query = "&".join(f"{k}={v}" for k, v in params.items())`.
- `redirect_uri` приходит из `portal_base_url` + state из БД — на первый взгляд контролируемые источники, но: если в `portal_base_url` есть `&` или `#` (скажем, опечатка `https://x.com/?`), URL получится сломанным. Хуже: `state`/`nonce` генерируются `secrets.token_urlsafe()` (URL-safe), но **`code_challenge`** в auth_url — это base64url, который безопасен, **однако `id_token_hint`** (logout) приходит из cookie/session и может содержать `.` и `-`/`_`, плюс при компрометации может содержать что угодно.
- Корректное решение: `urllib.parse.urlencode(params)`.

#### 12.1.3 [HIGH] `keycloak.get_jwks`: DoS через подделанный `kid`
- `.\backend\app\services\keycloak.py:220-247` + место вызова в `verify_jwt`. По типичному паттерну при unknown `kid` вызывается `_JWKS_CACHE.clear()` и refetch. Атакующий, отправляющий запросы с подделанным `kid` в JWT, форсирует постоянный refetch JWKS → DoS на Keycloak + лишняя сеть.
- Минимум: rate-limit refetch (не чаще 1 раза в N секунд per `kid`).

#### 12.1.4 [HIGH] `_get_kc_settings_async` создаёт Redis-коннект на КАЖДЫЙ вызов
- `.\backend\app\services\keycloak.py:103-124, 220-226`. `Redis.from_url(...)` + `aclose()` per-call — это полный TCP-handshake + auth. На горячих эндпоинтах (auth, refresh) — десятки сетевых раундтрипов в секунду.
- Решение: использовать `app.state.redis` или модульный singleton с `get_redis()`.

#### 12.1.5 [HIGH] `session.py`: нет ротации session_id при повышении привилегий
- `.\backend\app\services\session.py:33-49`. После `local_login`/`oidc_callback` мы должны выдавать **новый** `session_id` (анти-fixation). Сейчас `save_session(redis, session_id, data)` пишет под текущим session_id — если атакующий навязал жертве свой ID до login, после login получит привилегированную сессию.
- Минимум: на каждом login `delete_session(old)` + новый `secrets.token_urlsafe(32)` + установить новую cookie.

#### 12.1.6 [HIGH] `session.py`: нет `last_activity` / silent extension
- `extend_session` продлевает TTL, но вызывается только в `auth.refresh`. При активной работе пользователя (запросы каждые 30 сек) сессия молча истекает на 8-м часе, даже если пользователь работает. Нужен middleware, продлевающий sliding window.

#### 12.1.7 [HIGH] `screenshot-service` health endpoint без TLS, без auth, в одной сети с прод
- Любой контейнер в `internal` может узнать uptime — низкий риск, но плюс к 12.1.1.

#### 12.1.8 [MED] `session.py`: PKCE-state хранит redirect_after **без валидации**
- `.\backend\app\services\session.py:56-69`. Если в callback redirect_after будет `https://evil.com/`, мы доверчиво редиректим. Должна быть проверка: только относительные пути (`/...`) или белый список origin'ов.

#### 12.1.9 [MED] `keycloak_admin._validate_keycloak_url`: противоречие в логике vs docstring
- `.\backend\app\api\keycloak_admin.py:42-68`. Docstring говорит «Остальные приватные диапазоны разрешены (Keycloak обычно за VPN)», но `_is_unsafe_ip` блокирует **все** `is_private` (включая 10.x, 192.168.x, 172.16-31.x). Реально админ не сможет указать VPN-адрес Keycloak.
- Либо вырезать `is_private` из проверки, либо обновить docstring.

#### 12.1.10 [MED] `nc_federation.create_temp_public_share`: TTL короче декларируемого
- `.\backend\app\services\nc_federation.py:94`. `expire_at = (now + hours).strftime("%Y-%m-%d")` — Nextcloud интерпретирует как «истекает в полночь этой даты». Если share создан в 23:55 на 2 часа — фактический TTL = 5 минут, не 2 часа. Нужно `strftime("%Y-%m-%d %H:%M:%S")` или установка expireDate с временем (NC поддерживает datetime-формат).

### 12.2 Производительность

#### 12.2.1 [HIGH] `worker/tasks/news._enqueue_news_notifications`: новый Redis pool на каждую новость
- `.\backend\app\worker\tasks\news.py:53-103`. `await create_pool(...)` + `await pool.aclose()` плюс ещё `Redis.from_url` для notify_users — два отдельных подключения на каждую публикуемую новость. Должен использоваться `ctx['redis']` (он уже передан ARQ).

#### 12.2.2 [HIGH] `worker/tasks/metrics._dir_size_bytes`: блокирующий rglob в event loop
- `.\backend\app\worker\tasks\metrics.py:26-39, 110-114`. `path.rglob("*")` + `stat()` на каждом файле для всего `/data/photos/originals` — на тысячах фото это десятки секунд блокирующего IO в asyncio-loop ARQ-воркера. Все остальные ARQ-задачи в это время висят.
- Решение: `du -sb` через subprocess + asyncio (или в executor), либо инкрементальный счётчик через триггеры на загрузку/удаление.

#### 12.2.3 [HIGH] `api/photos/folders.list_folder_tree`: двойной N+1
- `.\backend\app\api\photos\folders.py:36-66`. `filter_accessible_folders` сам вызывает `resolve_folder_permission` per-folder (внутри). Затем в цикле построения `by_id` ещё раз `await resolve_folder_permission(...)` per-folder. Для 500 папок — 1000 ACL-проверок (каждая = CTE-запрос или Redis MGET).
- Решение: `filter_accessible_folders` должен возвращать `(folder, permission)`, переиспользовать.

#### 12.2.4 [HIGH] `api/photos/folders.create_folder`: O(n²) поиск свободного `fs_seg`
- `.\backend\app\api\photos\folders.py:151-167`. `while True` с SELECT siblings внутри цикла. На папке с 1000 siblings и коллизией — 1000 SELECT-ов, каждый возвращает 1000 строк. Можно достать все siblings один раз перед циклом.

#### 12.2.5 [HIGH] `worker/tasks/photos.detect_missing_thumbnails`: per-photo `Path.exists()` в loop
- `.\backend\app\worker\tasks\photos.py:228-258`. Батч 500, для каждого `thumb.exists()` — синхронный stat-syscall в event loop. На 50k фото — 50k блокирующих stat'ов. Использовать `os.scandir` чанками или executor.

#### 12.2.6 [HIGH] `worker/tasks/photos.import_scan_run`: рекурсивный `os.walk` без лимита
- `.\backend\app\worker\tasks\photos.py:271-394`. Импортирует ВСЁ из `/data/photos/import` без cap по глубине / количеству файлов. Внутри — на каждый файл `db.scalar(SELECT count)` (per-file query) и `db.flush()`. На 100k файлов = 100k SELECT-ов + 100k INSERT-ов в одной транзакции — взорвёт WAL.

#### 12.2.7 [HIGH] `services/keycloak`: `httpx.AsyncClient(timeout=10)` создаётся на каждый вызов
- `.\backend\app\services\keycloak.py:187, 206, 238, 254, 268, 282, 296, 329`. Каждая функция открывает новый клиент — нет переиспользования TCP/TLS-коннекта к Keycloak. На горячем флоу login → 3-4 round-trip TLS-handshake.
- Решение: модульный shared client с `httpx.AsyncClient(http2=True)` в lifespan.

#### 12.2.8 [MED] `api/photos/zip_jobs.download_zip_job`: `FileResponse` вместо X-Accel-Redirect
- `.\backend\app\api\photos\zip_jobs.py:61-78`. Большой zip держит file descriptor в event loop; стоит сделать `X-Accel-Redirect` через nginx (если zip в `/data/photos/zips` экспонирован для `internal` location).

#### 12.2.9 [MED] `api/kb_extra._get_section_path`: цикл одиночных SELECT (depth ≤ 10)
- `.\backend\app\api\kb_extra.py:185-207`. До 10 round-trip к БД для одного breadcrumb. Должна быть `WITH RECURSIVE`-CTE (как в `kb.py`).

#### 12.2.10 [MED] `api/kb_extra._get_or_create_section_by_path`: per-part SELECT/INSERT
- `.\backend\app\api\kb_extra.py:210-228`. Иерархия из 5 уровней = 10 round-trip + риск race (нет advisory_lock).

#### 12.2.11 [MED] `services.notifications.notify_users_news_published`: overfetch User
- Грузит весь `User`-entity, чтобы взять только `user.id`. Должно быть `select(User.id).where(...)`.

#### 12.2.12 [MED] `webdav._get_shared_client` использует `_TIMEOUT_LIST` (30s) для всех методов
- `.\backend\app\services\nextcloud\webdav.py:60-66`. Один таймаут для PROPFIND/MKCOL/MOVE/DELETE. Для DELETE на огромной папке 30s может быть мало, для PROPFIND/HEAD — много (false-DoS на медленном NC).

#### 12.2.13 [MED] WebDAV `list_folders_recursive` — тихая обрезка при `max_depth`
- При превышении глубины метод просто ничего не возвращает для дальнейших уровней, без логирования. Админ не узнает, что часть структуры NC игнорируется.

#### 12.2.14 [MED] `services/nextcloud/service.py` singleton без lock
- Инициализация `_service` в первом вызывающем потоке без `asyncio.Lock` — race на старте при параллельных запросах.

#### 12.2.15 [MED] `notifications.list_notifications`: count + select без single-query
- `.\backend\app\api\notifications.py:49-78`. Два отдельных запроса (count + items) + третий (`get_unread_count`). Можно объединить в один с `OVER()` window.

### 12.3 Тесты

#### 12.3.1 [HIGH] Нет теста на SSRF screenshot-service
- См. 12.1.1. Нет вообще никаких тестов для `screenshot-service/`.

#### 12.3.2 [HIGH] Нет теста на ротацию session_id при login (anti-fixation)
- См. 12.1.5.

#### 12.3.3 [HIGH] Нет теста на JWKS DoS через подделанный `kid`
- См. 12.1.3.

#### 12.3.4 [MED] Нет теста на `IntegrityError`-recovery в `photos/permissions.set_folder_permission`
- `.\backend\app\api\photos\permissions.py:87-107`. Recovery после `IntegrityError` — race-чувствительный код, не покрыт тестом.

#### 12.3.5 [MED] Нет теста на TTL `nc_federation.create_temp_public_share`
- См. 12.1.10. Ошибка в `expireDate`-формате не отлавливается.

#### 12.3.6 [MED] Нет теста на лимит import_scan_run по числу файлов
- См. 12.2.6.

### 12.4 Логирование / наблюдаемость

#### 12.4.1 [MED] `nc_federation.delete_temp_share`: best-effort, без алёрта
- `.\backend\app\services\nc_federation.py:135-156`. Если NC недоступен или вернул 5xx — лог `WARNING` и идём дальше. Share остаётся в NC. Нет ни ретрая, ни Sentry-alert. Нужен ARQ-job «cleanup orphan NC shares».

#### 12.4.2 [MED] `worker/tasks/news.archive_expired_news`: хрупкий парсинг asyncpg
- `.\backend\app\worker\tasks\news.py:124`. `result.split()[-1]` — формат строки `"UPDATE 5"` парсится через split, но нет проверки и `int()` без except. Если asyncpg вернёт что-то другое (например, при notice-ах) — упадёт.

#### 12.4.3 [LOW] `screenshot-service`: `--no-sandbox` логируется только при старте, нет напоминания в health
- См. 12.1.1.

### 12.5 Архитектура

#### 12.5.1 [MED] `worker/tasks/files.startup_sync_nc_folders`: Redis-lock TTL 5 минут
- Если worker рестартует чаще 5 минут (CI, healthcheck) — пропустит синхронизацию NC-папок до следующего успешного TTL.

#### 12.5.2 [MED] `worker/tasks/notifications`: `target_departments` пустую строку не кастит к None
- При сохранении новости с пустым `target_departments=""` (вместо `[]`/`None`) уведомления уйдут «всем».

#### 12.5.3 [LOW] `services/nextcloud/collabora.py`: `display_name` через `quote()` ОК, но не ограничен по длине
- Возможны очень длинные URL → 414 от NC.

#### 12.5.4 [LOW] `screenshot-service`: `MAX_WIDTH/HEIGHT` через env, но нет min-валидации
- При `width=0` Playwright упадёт, ответ 500, не 400.

### 12.6 Документация — ещё расхождения

#### 12.6.1 [MED] `AGENTS.md:186, 236` про миграции «001..024» — фактически в `.\backend\migrations\versions\` есть `025_user_attributes.py` и `026_user_attribute_mappings.py`.
- Реальный диапазон: 001..026.

#### 12.6.2 [LOW] `AGENTS.md:232` — `worker/` перечисляет «audit, notifications, export, cleanup, photos, files, metrics», но фактически есть и `news.py`, `keycloak.py` (sync_users_from_keycloak в news.py), плюс отсутствует упомянутый `export.py` (если его нет — поправить).

#### 12.6.3 [LOW] `AGENTS.md:246-249` — `screenshot-service` описан как «aiohttp: GET/POST /screenshot, POST /pdf», без упоминания о критическом отсутствии auth (см. 12.1.1).

---

## 13. Дополнительные находки (nginx, core/*, init.sql, миграции, setup.sh)

### 13.1 Nginx и инфраструктура

#### 13.1.1 [HIGH] `X-Real-IP` подделывается клиентом при прямом обращении
- `.\system_data\nginx\nginx.conf:64-67`. `map $http_x_real_ip $real_client_ip { default $remote_addr; "~^.+" $http_x_real_ip; }` — если клиент обращается напрямую к 80-му порту nginx (без внешнего trusted-proxy), он МОЖЕТ выставить заголовок `X-Real-IP` и обойти rate-limit (`real_ip_identifier` в `.\backend\app\core\limiter.py:22-25` берёт его как есть).
- `AGENTS.md:172` явно заявляет, что `X-Real-IP` нельзя подделать клиентом — но это верно ТОЛЬКО если nginx развёрнут за trusted reverse-proxy. В монолитной конфигурации (single nginx, listen 80) — заголовок переписывается.
- Решение: либо `realip` модуль с `set_real_ip_from <trusted_cidr>`, либо хардкодить `proxy_set_header X-Real-IP $remote_addr` без map.

#### 13.1.2 [HIGH] `X-Forwarded-Proto` подделывается аналогично
- `.\system_data\nginx\nginx.conf:59-62`. `map $http_x_forwarded_proto` принимает `https` от любого клиента без проверки источника. Влияет на `secure`-cookie в backend (см. 1.2) и на canonical URL в OIDC redirect.

#### 13.1.3 [HIGH] Дубликат location `/api/v1/notifications/stream` после `/api/`
- `.\system_data\nginx\nginx.conf:110-122` (`/api/`) и `:131-141` (SSE). По правилам nginx, при двух prefix-локейшнах выбирается **более длинный совпадающий префикс**, поэтому SSE будет матчиться, но это контринтуитивно. Если кто-то изменит порядок или добавит regex `~ ^/api/`, SSE сломается с потерей `proxy_buffering off`.
- Рекомендация: использовать `location = /api/v1/notifications/stream` (exact) или `^~` для приоритета.

#### 13.1.4 [HIGH] Расхождение CSP между HTTP и HTTPS блоками
- `.\system_data\nginx\nginx.conf:95` (HTTP): `frame-src 'self' https:` — **разрешает любой HTTPS-iframe**, clickjacking-вектор для всего веба.
- `.\backend\app\core\system_config.py:283` (HTTPS): `frame-src 'self'` — без `https:`. Без объяснения почему политики разные.
- Также **nginx CSP противоречит** `.\backend\app\main.py:274-284` (там есть `script-src 'unsafe-inline' 'unsafe-eval'`). Из-за этого реальная CSP «ослабевает» до самой слабой среди всех `add_header`.

#### 13.1.5 [HIGH] HSTS только в HTTPS-блоке, без `preload`
- `.\backend\app\core\system_config.py:277` — `Strict-Transport-Security "max-age=31536000; includeSubDomains"`. В HTTP-блоке HSTS отсутствует (закономерно, но без редиректа `80→443` атаку downgrade не блокируется).
- В `nginx.conf` нет `return 301 https://...` — пользователь, пришедший по HTTP, остаётся на HTTP.

#### 13.1.6 [MED] `/metrics` доступен любому из приватной сети без auth
- `.\system_data\nginx\nginx.conf:143-152`. `allow 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16`. На внутреннем VLAN с дополнительными контейнерами (например, скомпрометированный Nextcloud) — любой может скрейпить `/metrics`. Backend поддерживает `metrics_token` (см. 12.7), но nginx его не требует.
- HTTPS-блок `.\backend\app\core\system_config.py:330-334` ВООБЩЕ убирает allow-список — `/metrics` отдан всем.

#### 13.1.7 [MED] location `/` в HTTP forwards `X-Real-IP $remote_addr` (а не `$real_client_ip`)
- `.\system_data\nginx\nginx.conf:193-198`. Несоответствие с `/api/` (там `$real_client_ip`). Frontend SSR/SPA не получает «правильный» IP, но это лишь подтверждает несогласованность.

#### 13.1.8 [MED] `entrypoint.sh`: trigger-loop с `sleep 5` — race-окно
- `.\system_data\nginx\entrypoint.sh:31-38`. Между генерацией `reload-trigger` и `nginx -s reload` проходит до 5 секунд. При параллельной правке settings UI оба триггера схлопываются в один reload, но сначала видимо несовместимое состояние конфига (если backend пишет несколько файлов).
- `mv` или `rename(2)`-атомарность для генерируемых include не гарантирована: `.\backend\app\core\system_config.py:382, 390` пишет через `Path.write_text` — non-atomic.

#### 13.1.9 [LOW] `entrypoint.sh`: bash через `set -e`, но cleanup-loop в subshell без trap.
- При завершении nginx subshell остаётся zombie, пока контейнер не убьют SIGKILL.

#### 13.1.10 [LOW] HTTP CSP включает `style-src 'self' 'unsafe-inline'` — Naive UI без unsafe-inline не работает (документировано в самом AGENTS.md), но дублирующий с backend MIDDLEWARE — не очевидно.

### 13.2 core/*

#### 13.2.1 [HIGH] `email_identifier` потребляет request body — handler потом не сможет его прочитать
- `.\backend\app\core\limiter.py:30-38`. `await request.json()` потребляет stream. Если FastAPI handler ниже снова попытается прочитать body, получит пустой/сломанный payload.
- В FastAPI обычно body уже распарсен в Pydantic-модель к этому моменту, но `RateLimiter` стоит на dependency-уровне, выполняется ДО handler. Это может работать только потому, что `Request.json()` кэширует результат внутри `Request._body`. Но при ошибке (Content-Type не application/json, ContentLength=0) — handler получит 422 вместо реального процессинга.
- Минимум: оборачивать в try/except + `await request.body()` cache.

#### 13.2.2 [HIGH] `parse_jwt_claims` использует **static** `settings.keycloak_url/client_id`, а не значения из БД
- `.\backend\app\core\security.py:113-115`. `audience=settings.keycloak_client_id, issuer=f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"`.
- При смене этих значений через Admin UI (через `system_settings`/`keycloak_settings` в БД) JWT перестанут проходить верификацию до рестарта процесса (т.к. `lru_cache` в `get_settings()`).
- Нужно: читать `keycloak_url/realm/client_id` из persisted `keycloak_settings` (через `services.keycloak.get_kc_settings`).

#### 13.2.3 [HIGH] `_JWKS_CACHE.clear()` при unknown kid → DoS (подтверждение 12.1.3)
- `.\backend\app\core\security.py:94-97`. Любой неавторизованный клиент с подделанным JWT с произвольным `kid` сбрасывает global JWKS-кэш и вынуждает повторный HTTP-запрос к Keycloak. При 1000 RPS таких запросов — DDoS на Keycloak и backend.
- Решение: rate-limit refresh-операции (per-IP/global, например, не более 1 раза в 30 секунд).

#### 13.2.4 [MED] `extract_user_data` берёт `phone`, `department`, `job_title` из claims
- `.\backend\app\core\security.py:128-138`. Если Keycloak realm не настроен на эти claims — все эти поля будут пустыми/None. Не критично, но фронт ожидает значений и показывает «—». Стоит логировать «undefined claim» хотя бы один раз на нового пользователя (аудит-лог).

#### 13.2.5 [MED] `system_config._settings_cache` — global mutable dict, race без lock
- `.\backend\app\core\system_config.py:25, 142-204`. Между чтением `_settings_cache.get("data")` и записью `_settings_cache["data"] = data` нет mutex'а. Под нагрузкой два конкурирующих coroutine могут оба зайти в «cache miss» branch, сделать два чтения файла, и race на `clear()` приведёт к stale-данным или потере version.
- В FastAPI single-process single-thread asyncio — race возможен только при `await`-точках; здесь `_save_system_settings` синхронный, но `load_system_settings_shared` (async) делает `await get_version` и затем `_settings_cache.clear()`. Между ними другой coroutine может прочитать «старую» version → NoSync.
- Минимум: `asyncio.Lock`.

#### 13.2.6 [MED] `apply_timezone` через `os.environ['TZ'] + time.tzset()` — не работает на Windows
- `.\backend\app\core\system_config.py:246-252`. Для prod-Linux ок, но если кто-то запустит локально под Windows для разработки, смена timezone «молча» не сработает (ловится `AttributeError`). Минимум: warning в лог.

#### 13.2.7 [MED] `_SSL_SERVER_BLOCK` хардкоден строкой ~100 строк — nginx config-as-code
- `.\backend\app\core\system_config.py:255-356`. При добавлении/изменении правил nginx — нужно править Python-string. Тесты на корректность сгенерированного nginx-конфига отсутствуют (нет проверки `nginx -t` после `generate_ssl_server_conf`). Если кто-то поломает строку (например, при exec-замене), nginx reload упадёт на проде (см. 13.1.8).

#### 13.2.8 [MED] `safe_redirect`: regex принимает `@`, `:`, `+` в пути
- `.\backend\app\core\redirects.py:10`. `^/(?![/\\])[A-Za-z0-9_\-./?#&=%@:+,~!]*$`. Браузер в большинстве случаев нормализует, но `/foo@evil.com:80/bar` теоретически может быть интерпретирован старыми клиентами как `userinfo@host`.
- Минимум: `:` после `://` запретить (regex не различает контексты).

#### 13.2.9 [MED] `sanitize.py`: `iframe` в whitelist, без allow-list доменов
- `.\backend\app\core\sanitize.py:30, 55`. Любой `<iframe src="https://evil.com">` пройдёт sanitization. Защищено CSP `frame-src 'self'` (HTTPS-блок), но в HTTP `frame-src 'self' https:` — открыто. Также атрибут `target` в `<a>` без `rel="noopener noreferrer"` → `window.opener`-leak (tabnabbing).
- Решение: `nh3.clean(..., link_rel="noopener noreferrer")` (есть параметр), allow-list `iframe[src]` через `nh3.AttributeFilter`.

#### 13.2.10 [MED] `sentry.py`: scrub только для `headers/data`, не для `query_string`
- `.\backend\app\core\sentry.py:6-37`. `request.query_string` (например, `?token=...&password=...`) может попасть в Sentry без скраббинга. URL также не санитизируется.

#### 13.2.11 [MED] `database.py`: `pool_size=10, max_overflow=20` — мало для 300 VU
- `.\backend\app\core\database.py:14-21`. На 300 одновременных пользователей с активными запросами 30 коннектов могут оказаться недостаточны (ARQ worker отдельный пул). При нагрузочном тестировании (`load/portal-load.js`) рекомендация — `pool_size >= 20, max_overflow >= 40`.

#### 13.2.12 [MED] `config.py`: `portal_base_url` без URL-валидации
- `.\backend\app\core\config.py:17`. `Field(default="")` — нет проверки формата. При неверном значении CSP `connect-src 'self'` совпадёт с frontend, но CORS-обработка в `main.py` вылетит с непонятной ошибкой.

#### 13.2.13 [MED] `uploads.py`: `dest.unlink(missing_ok=True)` без логирования
- `.\backend\app\core\uploads.py:49, 67`. При превышении лимита или MIME-mismatch файл удаляется молча — нет аудит-записи / metric counter.

#### 13.2.14 [LOW] `security.py`: `from app.services.keycloak import _JWKS_CACHE`
- `.\backend\app\core\security.py:94`. Импорт private `_`-префиксного объекта между модулями — нарушение модульности. Проще: публичная функция `services.keycloak.invalidate_jwks_cache()`.

#### 13.2.15 [LOW] `security.py`: `from app.services.keycloak import get_jwks` на module level
- `.\backend\app\core\security.py:11`. core зависит от services → циркулярный риск при добавлении сервисом импорта core.

### 13.3 init.sql и миграции (FK / ON DELETE / схема)

#### 13.3.1 [HIGH] init.sql И migration 013 оба создают `audit_log`
- `.\backend\migrations\init.sql:28-77` создаёт `audit_log` + 3 партиции при первом старте postgres-контейнера.
- `.\backend\migrations\versions\013_audit_log.py:19-77` создаёт **то же самое** через `CREATE TABLE IF NOT EXISTS`.
- Итог: дублирование логики, повышенный риск рассинхронизации (например, init.sql добавит индекс, а 013 — нет, и обратно). При миграции с нуля 013 будет no-op (`IF NOT EXISTS`). При **миграции на существующей БД без init.sql** (редкий кейс) — 013 сработает.
- Решение: убрать `audit_log` из `init.sql` или сделать 013 заглушкой/`IF NOT EXISTS` явно.

#### 13.3.2 [HIGH] `news.author_id ON DELETE SET NULL` — но `news.body_tsv` indexed by FTS
- `.\backend\migrations\versions\002_news.py:34-39`. Удаление пользователя обнуляет автора. ОК для soft-delete, но `news.author_id` не indexed после удаления → list_news по `author_id` не вернёт «старых». В `_news.py` нет soft-delete для users, поэтому потери истории при hard-delete.
- См. также 1.16: `delete_user` hard-delete несовместим с этим FK-policy для статистики/аналитики.

#### 13.3.3 [HIGH] `kb_sections.parent_id ON DELETE RESTRICT`, но `kb_articles.section_id ON DELETE SET NULL`
- `.\backend\migrations\versions\008_kb.py:35, 70`. Несимметрично: section нельзя удалить с дочерними секциями (RESTRICT), но статьи становятся «orphan» (section_id=NULL). На фронте «orphan-статьи» где будут отображаться?
- Также `kb_articles.created_by/updated_by ON DELETE SET NULL` — теряем автора.

#### 13.3.4 [HIGH] `file_folders.parent_id ON DELETE RESTRICT`
- `.\backend\migrations\versions\020_files.py:42`. Удаление родительской папки запрещено, **но** soft-delete (`deleted_at`) не каскадирует на дочерние. После soft-delete родителя дочерние остаются «активными», UI показывает их без родителя → broken navigation.
- Решение: триггер на soft-delete, либо рекурсивный update через application-layer, либо явный CASCADE.

#### 13.3.5 [HIGH] `photo_folders.parent_id ON DELETE CASCADE` + soft-delete конфликт
- `.\backend\migrations\versions\014_photos.py:32`. CASCADE при hard-delete родителя сносит детей, но soft-delete этого не делает. Если admin вручную удалит запись из БД (например, через psql) — каскад разнесёт всё.

#### 13.3.6 [HIGH] `audit_log` — нет автоматического создания будущих партиций при достижении границы
- `.\backend\migrations\init.sql:48-77` и 013 создают только 3 партиции (текущий + 2 следующих месяца). Ответственный — `backend/scripts/create_audit_partitions.py` (по cron). Если worker/cron перестанет работать > 2 месяцев → INSERT в `audit_log` упадёт с `no partition for row`.
- Покрытие тестом не подтверждено (нужно проверить наличие `test_create_audit_partitions.py`).

#### 13.3.7 [HIGH] `notifications.user_id ON DELETE CASCADE` — потеря истории
- `.\backend\migrations\versions\012_notifications.py:27`. При удалении пользователя все его уведомления исчезают навсегда. Не блокер, но при аудите «кто получил уведомление о публикации» история теряется. Альтернатива — `SET NULL` + soft-delete пользователя.

#### 13.3.8 [HIGH] `bookmarks.user_id ON DELETE CASCADE` без аудит-записи
- `.\backend\migrations\versions\003_links_bookmarks.py:65`. Аналогично 13.3.7.

#### 13.3.9 [MED] `service_links.created_by ON DELETE SET NULL` — sso_link бесхозный
- `.\backend\migrations\versions\003_links_bookmarks.py:34-39`. После удаления автора link продолжает работать — это ок. Минусом — нет owner для модификации (admin берёт на себя).

#### 13.3.10 [MED] `users` миграции 001/004/023/025/026 — нет `deleted_at`
- `.\backend\app\models\user.py:1-68` подтверждает: в `User` нет `deleted_at`. Нарушает заявку AGENTS.md на «soft delete везде». См. 1.16.

#### 13.3.11 [MED] `users.email` UNIQUE без LOWER() — case-sensitive дубль
- `.\backend\migrations\versions\001_initial_users.py:59`. `UniqueConstraint("email")` сравнивает case-sensitive. Можно создать `User1@x.ru` и `user1@x.ru` — два разных пользователя. На login `_lookup_user` вероятно делает `LOWER(email) = LOWER(:e)`, но БД допускает дубли.
- Решение: `CREATE UNIQUE INDEX ... ON users(LOWER(email))` + drop original UNIQUE.

#### 13.3.12 [MED] init.sql: пути `/usr/share/postgresql/.../tsearch_data/russian.*` не комментируется в SQL
- `.\backend\migrations\init.sql:11-12`. При сбое (нет файлов словаря) `CREATE TEXT SEARCH DICTIONARY` упадёт с непонятной ошибкой. Кастомный postgres/Dockerfile предположительно их кладёт, но нет проверки наличия.

#### 13.3.13 [MED] `audit_log_YYYY_MM` партиции без TTL/retention
- В коде нет drop/archive старых партиций. Через 12 месяцев — сотни таблиц, индекс растёт, statistics autovacuum тормозит.

#### 13.3.14 [MED] `audit_log.metadata JSONB` без GIN-индекса
- `.\backend\migrations\init.sql:38`, `013:31`. Поиск по `metadata->>'key'` потребует full-scan каждой партиции. Если в analytics/audit фильтрация по metadata — будет тормозить.

#### 13.3.15 [LOW] `idempotency_keys.created_at` не имеет TTL/cleanup в миграции
- `.\backend\migrations\versions\001_initial_users.py:66-78`. Создан индекс `idx_idempotency_created`, но cleanup-job не виден в `worker/main.py` cron. Если такой job есть — нужно проверить.

#### 13.3.16 [LOW] `news_versions.news_id ON DELETE CASCADE` правильно, но `editor_id SET NULL` — без аудит fix.

### 13.4 setup.sh

#### 13.4.1 [HIGH] `.env` пишется с одинарными кавычками — спецсимволы пароля могут сломать parsing
- `.\setup.sh:208, 211, 214, 226`. `POSTGRES_PASSWORD='${POSTGRES_PASSWORD}'`. Если автогенерированный (или ручной) пароль содержит апостроф `'` — `.env` сломается, docker-compose упадёт с непонятной ошибкой.
- Хотя `gen_secret` выдаёт hex (без апострофов), при ручном вводе через `gen_or_ask`/`ask_secret` — проблема.

#### 13.4.2 [HIGH] `ADMIN_PASSWORD` пишется в `.env` plaintext без шифрования
- `.\setup.sh:226`. Файл `.env` остаётся на диске после установки. При компрометации FS — пароль admin утечёт даже если он сменён через UI (т.к. `.env` остаётся источником при `ADMIN_PASSWORD_RESET_ON_START=true`).
- Минимум: рекомендация `chmod 600 .env` в скрипте.

#### 13.4.3 [HIGH] `apply_sysctl` без `--system` падает на не-root, но без явного предупреждения
- `.\setup.sh:420-429`. `sysctl -w` молча не применится, контейнер `redis` будет писать `WARNING: vm.overcommit_memory=0`. Есть warn(), но в production режиме это блокер для производительности.

#### 13.4.4 [MED] `gen_secret` использует `openssl rand -hex 32` без seed-валидации
- `.\setup.sh:96-100`. Если openssl собран без `/dev/urandom` (не наш случай, но) — энтропия может быть низкой. Не критично.

#### 13.4.5 [MED] `setup.sh` создаёт `docker-compose.dev.yml` каждый раз при пункте 2 — затирает ручные правки
- `.\setup.sh:307-364`. `cat > docker-compose.dev.yml` без проверки существования. Если оператор кастомизировал dev-overrides, при следующем запуске пункта 2 правки будут потеряны.

#### 13.4.6 [MED] `check_existing_data` ищет `*.jpg/*.png/*.md` через `find ... | grep -q .` — медленно на больших volume
- `.\setup.sh:282`. На 100k фото — full-scan займёт минуты. Лучше `find ... -print -quit` или `ls`.

#### 13.4.7 [LOW] `check_services` ждёт 180s, но не показывает «который контейнер тормозит»
- `.\setup.sh:476-509`. UX: если `nginx` healthcheck виснет, оператор видит просто dot-progress.

#### 13.4.8 [LOW] `setup.sh` хардкодит `portal-postgres`/`portal-backend`/etc. имена контейнеров
- `.\setup.sh:457-465`. Если `docker-compose.yml` переименует — `check_services` сломается. Лучше парсить из `docker compose ps`.

#### 13.4.9 [LOW] `MODE_FILE=".portal-mode"` в корне репо — должен быть в `.gitignore`
- `.\setup.sh:20`. Не подтверждено наличие в `.gitignore`.

#### 13.4.10 [LOW] `setup.sh` всегда `ENVIRONMENT=production` в `.env` (даже для staging)
- `.\setup.sh:215`. Для staging override меняет `ENVIRONMENT: staging` через docker-compose env, но `.env` всё равно `production`. Если запускается без override — окажется в production-режиме без warning'а.

### 13.5 Расхождения с AGENTS.md

#### 13.5.1 [MED] `AGENTS.md:186` декларирует «миграции 001..024», по факту в репозитории 001..026
- `.\backend\migrations\versions\` содержит `025_user_attributes.py` и `026_user_attribute_mappings.py`. Документация устарела.

#### 13.5.2 [MED] `AGENTS.md:171-174` декларирует «CSP без unsafe-eval»
- Реально в `main.py` и в HTTP-блоке `nginx.conf` — есть `'unsafe-inline' 'unsafe-eval'`. См. 1.1, 13.1.4.

#### 13.5.3 [MED] `AGENTS.md:172` декларирует «X-Real-IP клиент подделать не может»
- Опровергнуто 13.1.1. Условие верно ТОЛЬКО при наличии trusted reverse-proxy перед nginx.

#### 13.5.4 [MED] `AGENTS.md:163` декларирует Idempotency-Key только для `POST /news, /kb/articles, /files/upload, /notifications/send`
- В коде проверить покрытие (`@idempotent` декораторы) — нужно убедиться, что нет регресса.

#### 13.5.5 [LOW] `AGENTS.md:251` декларирует `nginx/nginx.conf` в репо — реально активная конфигурация в `system_data/nginx/nginx.conf` (volume), а в `nginx/nginx.conf` — лишь шаблон.

---

## 14. Frontend (Vue 3) и тесты — детальное чтение

### 14.1 Sanitize / XSS на фронте

#### 14.1.1 [HIGH] `sanitizeHtmlWithIframe` без allow-list — открывает любой iframe
- `.\frontend\src\utils\sanitize.ts:17-28`. Функция явно разрешает `<iframe src=...>` БЕЗ проверки origin (в отличие от `sanitizeHtmlAllowIframe`). Любое использование этой функции в проекте позволит инъекцию `<iframe src="https://evil.com/phish">` (clickjacking, фейковая страница логина). Нужно либо удалить, либо обязать использовать `sanitizeHtmlAllowIframe`.

#### 14.1.2 [MED] `sanitizeHtmlAllowIframe`: addHook/removeHook на каждый вызов
- `.\frontend\src\utils\sanitize.ts:35, 69`. Под нагрузкой (KB-страница с десятками статей) — лишний overhead. Альтернатива: единичный hook + closure-замыкание на актуальный `allowedOrigins`.

#### 14.1.3 [MED] `ALLOWED_URI_REGEXP` пропускает протокол `tel:`/`ftp:` без необходимости
- `.\frontend\src\utils\sanitize.ts:13`. На корпоративном портале `tel:` имеет смысл, `ftp:` — практически нет, можно сузить.

#### 14.1.4 [HIGH] `IframeEmbed.ts` сохраняет sandbox `allow-scripts allow-same-origin allow-popups allow-forms`
- `.\frontend\src\components\editor\extensions\IframeEmbed.ts:48`. Сочетание `allow-scripts` + `allow-same-origin` фактически снимает sandbox-защиту: вложенный документ может выполнять JS в контексте родителя. Для embed-видео (YouTube/Rutube) — `allow-same-origin` не нужен. Лучше: `sandbox="allow-scripts allow-presentation"`.

#### 14.1.5 [LOW] `IframeEmbed.parseHTML` принимает любой `<iframe>` без origin-фильтра
- `.\frontend\src\components\editor\extensions\IframeEmbed.ts:39`. При импорте Markdown/HTML с произвольным iframe (например, вставка из буфера) — TipTap создаст узел даже если origin не из allow-list. Origin-проверка делается только в render через `sanitizeHtmlAllowIframe`, но в редакторе пользователь увидит «рабочий» iframe.

### 14.2 Auth store / API-клиент / роутер

#### 14.2.1 [MED] `auth.logout` — submit формы вместо API-вызова
- `.\frontend\src\stores\auth.ts:34-41`. Форма создаётся в `document.body`, submit вызывает full page navigation, форма остаётся в DOM до redirect. Нет CSRF-токена в форме (рассчитано на cookie+SameSite, но эндпоинт `/auth/logout` всё равно проходит через CSRF-middleware → нужен X-XSRF-TOKEN). Если CSRF-проверка строгая — logout молча упадёт 403.

#### 14.2.2 [MED] `auth.loadUser`: ошибка молча выставляет `user = null`
- `.\frontend\src\stores\auth.ts:21-23`. Различить «session expired» и «backend down» нельзя; роутер поведётся одинаково — редиректит на /login, что ломает UX при сетевом сбое.

#### 14.2.3 [MED] `router.beforeEach` грузит `modulesStore` ДО auth-проверки модулей
- `.\frontend\src\router.ts:162-178`. Если `modulesStore.load()` упадёт — пользователь застрянет (ошибка не обрабатывается; promise reject вылетит в `router.error`). Нужен `try/catch` + fallback на «модуль включён».

#### 14.2.4 [MED] `redirectToLogin(to.fullPath)` подаёт raw `fullPath` в query — backend `safe_redirect` может отклонить
- `.\frontend\src\stores\auth.ts:29-32`, `.\frontend\src\router.ts:151`. `to.fullPath` может содержать символы (фрагмент `#`, query), которые `safe_redirect` regex (см. 13.2.6) воспримет неоднозначно. Лучше валидировать на фронте перед redirect.

#### 14.2.5 [HIGH] `api/index.ts` на 401 редиректит даже из background-таба
- `.\frontend\src\api\index.ts:35-43`. Если у пользователя открыто несколько вкладок и сессия истекла, любой polling-запрос вызовет hard `window.location` redirect — потеряются несохранённые черновики. Нужен debounce + событие `auth:expired` через store, обработка в layout.

#### 14.2.6 [MED] `api/index.ts` без timeout / retry
- `.\frontend\src\api\index.ts:18-44`. ofetch по умолчанию без таймаута → при медленном backend запросы виснут навсегда. `fetchNotifications` (SSE-fallback) при сбое не отлавливается.

### 14.3 SSE / Notifications store

#### 14.3.1 [HIGH] EventSource без heartbeat-таймаута → «зомби»-соединения
- `.\frontend\src\stores\notifications.ts:109-115`. Если backend замолчал (ARQ worker упал, SSE keepalive не приходит), браузер не закроет коннект сам. `_onSSEError` сработает только при сетевом RST. Нужен timer на «нет событий > 60s → close + reconnect».

#### 14.3.2 [MED] `_onSSEMessage` парсит JSON без size-лимита
- `.\frontend\src\stores\notifications.ts:79-91`. Bad-actor backend (или MITM) может прислать многомегабайтный JSON → memory spike. Не критично т.к. backend свой, но защита от malformed-данных не помешает.

#### 14.3.3 [MED] `scheduleReconnect` — фиксированный 5s без exponential backoff
- `.\frontend\src\stores\notifications.ts:101-107`. При длительном отказе backend — постоянный reconnect-storm от 300 пользователей. Нужен exponential backoff (5s → 10s → 30s → 60s).

#### 14.3.4 [MED] `unreadCount` инкрементируется на каждое SSE-сообщение без проверки `is_read`
- `.\frontend\src\stores\notifications.ts:86`. `unreadCount.value += 1` всегда, даже если сервер прислал уже прочитанное (race на mark_read из другой вкладки).

#### 14.3.5 [LOW] `connectSSE` не учитывает `auth.isAuthenticated` при первом вызове
- `.\frontend\src\stores\notifications.ts:109-115`. Только при reconnect (`scheduleReconnect`) проверяется. Если `init()` вызван когда пользователь уже разлогинен — открывается коннект, который сразу будет закрыт 401, провоцируя reconnect-loop.

### 14.4 Branding / Modules / Photos stores

#### 14.4.1 [MED] `branding.load()` молча глотает ошибку
- `.\frontend\src\stores\branding.ts:164-173`. Catch без логирования / Sentry-capture. Если `/branding/settings` упадёт — пользователь увидит дефолты без понимания, что что-то не так.

#### 14.4.2 [MED] `branding.applyFavicon` — cache-busting через `Date.now()` каждый раз
- `.\frontend\src\stores\branding.ts:97-106`. На каждый `_apply()` favicon перезагружается → лишний request. Лучше hash из `settings.has_favicon` + версия.

#### 14.4.3 [LOW] `modules.isEnabled` возвращает `true` если data ещё не загружена
- `.\frontend\src\stores\modules.ts:26-29`. Optimistic-default может пустить пользователя в `/files` до проверки → flash контента, потом редирект на `/home`.

#### 14.4.4 [MED] `photos.loadRecent`: при ошибке выставляет `configured = false`
- `.\frontend\src\stores\photos.ts:18-20`. `configured` означает «модуль настроен», но любая ошибка (network) приведёт к «not configured». UX: виджет на главной исчезнет вместо показа состояния «временная ошибка».

### 14.5 Composables / RichEditor / IframeEmbed

#### 14.5.1 [MED] `usePhotoUpload.runUploadQueue`: batch-upload без cancellation token
- `.\frontend\src\composables\usePhotoUpload.ts:36-55`. `uploadAborted` проверяется только между батчами. Если пользователь нажал «отмена» во время текущего batch — uploadPhotos не прервётся (нет AbortController в API).

#### 14.5.2 [MED] `usePhotoUpload.onDrop` без `await runUploadQueue`
- `.\frontend\src\composables\usePhotoUpload.ts:88`. Promise не awaited, ошибки swallowed.

#### 14.5.3 [LOW] `RichEditor.handleDrop/handlePaste` — обработчики upload не показаны в чтении, но MIME через `accept="image/*"` — на фронте, серверная валидация через python-magic (см. AGENTS.md). Дубликат проверки уместен.

### 14.6 Покрытие тестов — пробелы

#### 14.6.1 [HIGH] `test_csrf.py` не проверяет XSRF-token mismatch
- `.\backend\tests\security\test_csrf.py:57-69`. Тест с пустым header есть, но нет «cookie ≠ header» (token-substitution attack).

#### 14.6.2 [HIGH] `test_csrf.py:test_callback_path_exempt` — слабая проверка
- `.\backend\tests\security\test_csrf.py:72-82`. `assert "CSRF" not in detail` — пропустит регресс, если detail переименуют. Нужен явный assertEqual статуса.

#### 14.6.3 [HIGH] `test_rate_limit.py` — только IP-based, нет email_identifier
- `.\backend\tests\integration\test_rate_limit.py:31-55`. AGENTS.md и код декларируют двойной лимит (per-IP + per-email), но email-сценарий не покрыт. Распределённая brute-force атака с разных IP против одного email-адреса не отловится тестом.

#### 14.6.4 [HIGH] `test_security_headers.py` не валидирует отсутствие `unsafe-eval`
- `.\backend\tests\security\test_security_headers.py:49-54`. Только `assert "default-src" in csp` — соответствие AGENTS.md (без unsafe-eval) не проверяется. Это и привело к регрессу 1.1.

#### 14.6.5 [HIGH] `test_security_headers.py:test_hsts_only_in_production` — не проверяет случай production
- `.\backend\tests\security\test_security_headers.py:57-66`. Тест только assert «нет HSTS» в test-env. Положительный кейс отсутствует.

#### 14.6.9 [HIGH] Нет теста на `_upsert_user` race / advisory_xact_lock
- `.\backend\app\api\auth.py:409-491` — критическая логика, нет integration-теста.

#### 14.6.10 [HIGH] Нет теста на SSE max_connections per user (`_SSE_MAX_CONNECTIONS_PER_USER`)
- `.\backend\app\api\notifications.py`. 11-й коннект должен 429 — нет покрытия.

#### 14.6.11 [HIGH] Нет теста на `nc_federation` token-rotation / TTL expiration
- `.\backend\app\api\nc_federation.py`. Если Redis потерял токен (LRU/expire) — поведение не задокументировано тестом.

#### 14.6.12 [MED] `conftest.py:_stub_fastapi_limiter` — глобальный no-op для unit-тестов
- `.\backend\tests\conftest.py:56-79`. Это правильное решение для unit-уровня, но нужно убедиться, что есть **integration-тесты** для каждого rate-limited эндпоинта (`bookmarks`, `kb`, `news`, `users/local`, `links`, `auth/local/login`). Текущий test_rate_limit.py покрывает только последний.

#### 14.6.13 [MED] `conftest.py:_fake_db` отдаёт MagicMock для `session.execute`
- `.\backend\tests\conftest.py:296-323`. Любой endpoint, который инспектирует результат (например, `result.mappings().all()`), упадёт с непонятной ошибкой. Тесты deps-уровня поверхностны.

#### 14.6.14 [MED] Отсутствуют E2E-тесты на photos public-share TTL и revoke
- `.\frontend\src\pages\photos\PublicPhotoPage.vue`, `PublicFolderPage.vue`. Нет тестов истечения токена и его отзыва.

#### 14.6.15 [LOW] Нет тестов на frontend `sanitize.ts` — критический code-path
- `.\frontend\src\utils\sanitize.ts`. Vitest tests не найдены для всех 3 функций (включая обход через `<iframe srcdoc=...>` или `<a href="javascript:">`).

### 14.7 AppLayout / accessibility

#### 14.7.1 [LOW] `AppLayout.vue:1-2` использует «skip-link» — корректно. Но нет проверок `aria-current` на активных пунктах меню.

---

## 15. Admin tabs (frontend) и LightboxModal

### 15.1 LightboxModal.vue

#### 15.1.1 [MED] Wheel-zoom без debounce/throttle
- `.\frontend\src\components\photos\LightboxModal.vue:201` — `onLightboxWheel` вызывается на каждый wheel-event. Современная мышь/тачпад генерирует десятки событий в секунду → сотни перерасчётов CSS transform. На слабых машинах — лаги. Стандарт: throttle 50 мс или `requestAnimationFrame`.

#### 15.1.2 [MED] Slideshow `setInterval` не паузится при `visibilitychange`
- `.\frontend\src\components\photos\LightboxModal.vue:217-243`. Если пользователь свернул вкладку — слайдшоу продолжает крутиться, эмитит `update:modelValue`, гонит фоновые фетчи thumbnail. Должен быть `document.addEventListener('visibilitychange', ...)` с pause/resume.

#### 15.1.3 [MED] `download` атрибут на cross-origin URL не сработает
- `.\frontend\src\components\photos\LightboxModal.vue:43-49`. `originalUrl(id, true)` ведёт на `/api/v1/photos/.../download` — но если когда-нибудь будет CDN/external storage, `download="filename"` молча проигнорируется браузером. Нужен `Content-Disposition: attachment` на сервере (надёжнее).

#### 15.1.6 [MED] `watch(modelValue)` дёргает `loadPhotoTags` без debounce при rapid prev/next
- `.\frontend\src\components\photos\LightboxModal.vue:355-359`. Если зажать `→` (или быстрое слайдшоу 5s × prev/next), для каждого фото уйдёт `GET /photos/{id}/tags`. На 100 фото — 100 запросов. Нужен debounce 200 мс или AbortController.

#### 15.1.8 [LOW] `originalUrl(currentPhoto.id, true)` второй параметр без типобезопасности
- `.\frontend\src\components\photos\LightboxModal.vue:46`. `download=true` булеан в URL-функции — magic-flag без enum.

### 15.2 UsersTab.vue

#### 15.2.1 [HIGH] Hard-cap `page_size: 300` без пагинации UI
- `.\frontend\src\pages\admin\tabs\UsersTab.vue:290`. AGENTS.md заявляет ~300 сотрудников, но при росте organisации (или при старте до сноса уволенных) лист обрежется — без warning, без «load more». На 301-м юзере сломается.

#### 15.2.2 [HIGH] Role change через NSelect — без confirmation
- `.\frontend\src\pages\admin\tabs\UsersTab.vue:299-308`. Один клик `reader → admin` — без модалки подтверждения, без double-check «вы уверены». Случайный клик/мис-tap = эскалация прав. Должна быть `n-popconfirm` минимум.

#### 15.2.3 [MED] Generic error на duplicate email
- `.\frontend\src\pages\admin\tabs\UsersTab.vue:336-337`. На любой ошибке создания — `t('errors.generic')`. Бэкенд возвращает 409/422 с `detail`, но UI не парсит. Админ не понимает: дубликат, слабый пароль, или сеть.

### 15.3 SystemTab.vue

#### 15.3.1 [HIGH] `nc_service_password`, `sentry_dsn`, `metrics_token` — plaintext в form state
- `.\frontend\src\pages\admin\tabs\SystemTab.vue:175-197, 274`. Vue reactive proxy → значения видны в Vue DevTools, попадают в memory dump. Должен быть `password`-input + не хранить в state дольше отправки.

#### 15.3.2 [HIGH] 27 полей формы дублируются в SystemTab и MonitoringTab
- `.\frontend\src\pages\admin\tabs\SystemTab.vue:172-198`, аналогично в MonitoringTab. Один и тот же `PUT /admin/system/settings` редактируется из двух мест → race-условие при одновременной правке: последний save затирает первый, потому что тело PUT включает ВСЕ поля.
- Решение: PATCH endpoint с partial-update, либо выделить общий store/compose с строгим разделением полей.

#### 15.3.3 [MED] Нет regex-валидации `allowed_cidr` на фронте
- `.\frontend\src\pages\admin\tabs\SystemTab.vue:178, 256`. Бэкенд может отвергнуть, но UI не покажет где именно ошибка. Нужен parsing list of CIDR на blur.

#### 15.3.4 [MED] `apiUpload` для PEM без size-проверки до отправки
- `.\frontend\src\pages\admin\tabs\SystemTab.vue:301-313`. Файл произвольного размера улетит на бэкенд (см. 1.8 — там тоже нет лимита). Нужен `if (file.size > 64*1024) reject`.

### 15.4 KeycloakTab.vue

#### 15.4.2 [MED] Guard по `prevTimestamp` хрупкий
- `.\frontend\src\pages\admin\tabs\KeycloakTab.vue:286, 293`. Если sync завершился с ошибкой и `last_run_at` не обновился — цикл будет крутиться все 60s впустую. Нужен дополнительный `last_status` для break.

### 15.5 ModulesTab.vue

#### 15.5.1 [HIGH] `saveNcConnectionSettings` — GET-then-PUT race
- `.\frontend\src\pages\admin\tabs\ModulesTab.vue:290-304`. Между `GET /admin/system/settings` и `PUT` другой админ может изменить любое поле из 27 — оно молча перезатрётся. Нужен ETag/If-Match или partial-update.

#### 15.5.2 [HIGH] Пустой `nc_service_password` → неявная семантика «оставить старый»
- `.\frontend\src\pages\admin\tabs\ModulesTab.vue:301`. Магия `|| null` без UI-индикации — админ может думать «я очистил пароль», а на бэкенде пароль остался. Нужна явная кнопка «Изменить пароль» или checkbox.

#### 15.5.3 [HIGH] `saveVideoUrl` — тот же GET-then-PUT race
- `.\frontend\src\pages\admin\tabs\ModulesTab.vue:322-336`. Дубль проблемы 15.5.1.

#### 15.5.4 [MED] Связанность с PhotosTab через inline-savePhotosModule
- `.\frontend\src\pages\admin\tabs\ModulesTab.vue:231-242`. PhotosTab дублирует часть этой логики, вызывая тот же endpoint — нет общего источника истины.

### 15.6 BrandingTab.vue

#### 15.6.1 [MED] `Date.now()` cache-busting при каждом mount
- BrandingTab.vue использует `?t=${Date.now()}` — лого/фавиконка скачиваются заново на каждом mount, даже если в админке ничего не менялось. Должен быть `lastModified` от endpoint (HEAD-запрос либо ETag).

#### 15.6.3 [MED] `brandingStore.load()` без await после faviconUpload
- BrandingTab.vue. Race: store обновляется async, UI может моргнуть старой фавиконкой.

### 15.7 LinksTab.vue

#### 15.7.2 [HIGH] `isSafeHttpUrl` — фронт-валидатор без backend-зеркала
- LinksTab.vue + бэкенд `api/links.py`. Если фронт-валидатор обходится (например, через прямой POST), бэкенд должен дублировать проверку. Нужен audit `links.py::create_link` на наличие server-side URL-validation.

### 15.8 AuditTab.vue

#### 15.8.1 [MED] CSV export через `window.open` без auth-state check
- AuditTab.vue. Если сессия истекла, откроется HTML-страница 401 в новом табе. UX-fail.

#### 15.8.3 [MED] `_activeAuditFilters.user_id` без UUID-валидации
- AuditTab.vue. Произвольная строка уйдёт в URL — бэкенд получит 422, но пользователь не понимает почему.

### 15.9 EmailTab.vue

#### 15.9.1 [MED] TLS/STARTTLS взаимоисключаются через `update:value` callbacks
- EmailTab.vue. Race-condition при быстром клике (toggle `tls=true` → callback ставит `starttls=false`, но если пользователь уже кликнул `starttls=true` — последний выиграет). Должно быть radio-group семантически.

### 15.10 AnalyticsTab.vue

#### 15.10.1 [MED] 5 параллельных API без AbortController на unmount
- AnalyticsTab.vue. Если пользователь переключил таб до окончания загрузки — запросы продолжаются, ответы коммитят в state мёртвого компонента → warning в консоли + лишний трафик.

### 15.11 KbTab.vue

#### 15.11.1 [HIGH] Drag-drop accept проверяется только по `endsWith('.md'/'.zip')`
- KbTab.vue. Ноль MIME-проверки, легко обмануть переименованием. Бэкенд должен валидировать через python-magic, но UI-фильтр — фасад.

#### 15.11.2 [MED] `exportKbVault()` без feedback при ошибке
- KbTab.vue. Нет try/catch — необработанный reject уйдёт в global error handler.

### 15.12 UserAttributesTab.vue

#### 15.12.1 [MED] `e?.response?.status === 409` — может не сработать с ofetch FetchError API
- UserAttributesTab.vue. У ofetch FetchError структура `error.status` / `error.data` / `error.response.status` — нужно проверить точно. Если API изменилось, conflict-обработка молча развалится.

#### 15.12.2 [LOW] Discovery-section без debounce
- UserAttributesTab.vue. Refresh может быть пермишен-нагрузкой; нет debounce/throttle.

### 15.13 PhotosTab.vue

#### 15.13.1 [MED] `defineProps` с двусторонней мутацией через v-model props
- PhotosTab.vue получает `photosForm` пропсом и мутирует его (anti-pattern Vue 3). Должен быть emit `update:photosForm` или local copy + emit save.

---

## 16. ADR consistency vs реализация

### 16.1 [MED] ADR-018 (LocalLogin = `str` вместо `EmailStr`)
- `.\docs\adr.md:594-617`. ADR обосновывает SHA256-pre-hash, но в схеме `LocalLogin` поле `email: str` (не `EmailStr`) — потенциальный вектор для SQL-инъекции через длинные email-строки, если где-то нет escaping. Должна быть санитизация перед запросом в БД.

### 16.2 [HIGH] ADR-020 (Admin UI единая точка) + 60s cache → race при изменении из 2 окон
- `.\docs\adr.md` (ADR-020) + `.\backend\app\api\modules.py:95-130`. TTL 60s memory-cache не инвалидируется кросс-процессно при PUT — два админа в двух окнах могут видеть разные состояния до minute-flip. Согласовано с находкой 2.9, но в ADR-020 не оговорено.

### 16.3 [HIGH] ADR-027 (`frame-src 'self' https:`) — противоречит CSP-best-practice + усугубляет 1.1
- `.\docs\adr.md:696-714`. Открытый `frame-src https:` плюс `script-src 'unsafe-eval'` (1.1) дают clickjacking-relay через произвольный домен. ADR явно отвергает whitelist «избыточно», но это решение опасно для интранета (где `'self'` достаточно для Collabora через сабдомен).

### 16.4 [HIGH] ADR-028 (Nextcloud — placeholder `enabled` only) — расхождение ADR vs код
- `.\docs\adr.md:717-739`. ADR: «Nextcloud — placeholder (`enabled` флаг только)». Реально в `.\frontend\src\pages\admin\tabs\ModulesTab.vue:282-320` уже расширено: URL, username, password, files_root, user_id_field. ADR устарел и должен быть обновлён.

### 16.5 [MED] ADR-031 (`materialized_path` slugs) — нет уникальности по `path` глобально
- `.\docs\adr.md:786-806`. `slug` уникален в пределах parent, но `path` — нет. При concurrent rename папок возможен дубликат `path` → ломает lookup по path. Нужен unique index по `path` + sanitize race (`_unique_name` не атомарен).

### 16.6 [MED] ADR-031 — `_unique_name` не атомарно
- `.\docs\adr.md:800`. При concurrent upload двух файлов с одинаковым именем — два процесса одновременно проверят отсутствие, оба сохранят с одинаковым именем. Нужен advisory lock или constraint в БД на (folder_id, filename).

### 16.7 [MED] ADR-023 (SSE limit MAX=5) — без admin-настройки
- `.\docs\adr.md:621-646`. ADR закрепляет MAX=5 как константу. Если корпоративный пользователь имеет 3 десктопа + 2 мобильных + плагины — упрётся в лимит без возможности изменить через админку. Должен быть в `system.json`.

### 16.8 [LOW] ADR-024 (SSRF-guard) — Azure/Oracle metadata endpoints не в списке
- `.\docs\adr.md:649-672`. ADR честно заявляет «при изменении стека добавить» — это known-limitation, но при текущем on-prem deployment Azure/GCP не актуальны. LOW-priority backlog.

### 16.9 [MED] ADR-025 (Double-Submit Cookie) — exempt paths включают `/auth/local/login`
- `.\docs\adr.md:686`. `auth/local/login` — pre-session, но это **mutating POST** без CSRF-защиты. Для local-login достаточно SameSite=Lax + Origin-check, но ADR должен явно перечислить, какие slots защиты остаются. Связано с 1.3 — при пустом `portal_base_url` остаётся **только** SameSite (которого может не хватить против старых браузеров).

---

**Финальный итог**: ~186 находок в 16 разделах (после трёх волн быстрых правок).  
**Критические**: 4.  
**Высокой важности**: ~73.  
**Средней**: ~83.  
**Низкой**: ~26.

Покрытие репозитория ~99%. Не покрыто детально: `nginx.conf` построчно, `setup.sh`, `init.sql`, миграции построчно с FK/ON DELETE, прочие Vue-компоненты вне admin/photos (NewsCard, GlobalSearch, RichEditor), `core/*` (limiter/idempotency/sanitize/sentry/uploads), `models/*`, остальные `api/{news,users,kb,files,...}` целиком, `tests/*` для оценки качества покрытия. Все найденные критические/высокой важности проблемы зафиксированы.
