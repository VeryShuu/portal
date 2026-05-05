# Code Review — Corporate Intranet Portal

Дата ревью: 2026-05-03  
Последнее обновление: 2026-05-08 (сессии 1–8; закрыто ~33 находки)  
Скоуп: глубокий ревью backend FastAPI + frontend Vue 3 + infra.

Маркировка тяжести:
- **[CRIT]** — безопасность/целостность данных, требует немедленной правки.
- **[HIGH]** — серьёзная проблема (производительность, корректность), требует приоритета.
- **[MED]** — улучшение качества/надёжности.
- **[LOW]** — стилистика, мелочи, документация.

---

## 1. Безопасность

### 1.11 [MED] Redis ACL: пароль вкладывается через `printf` без экранирования
- `.\docker-compose.yml:46`. Если пароль содержит пробел, `\n`, `>`, `<`, `&` — ACL-файл получится сломанным или Redis запустится с другим пользователем/правами. Нужно валидировать `REDIS_PASSWORD` на «безопасный» алфавит или использовать `--requirepass` через файл-секрет.

### 1.15 [LOW] CORS `allow_origins=[settings.portal_base_url]`
- `.\backend\app\main.py:181-186`. При пустом `portal_base_url` получится `[""]` — браузер просто не будет матчить, но кейс не покрыт явно (нет валидации в `Settings`).

---

## 2. Производительность

### 2.7 [MED] `search.global_search`: `_FETCH_MULTIPLIER = 5`
- `.\backend\app\api\search.py:23, 55`. На 4 типа поиска при `limit=20, offset=0` загружается 100 записей по каждому типу (4×100 = 400 строк) и фильтруется ACL в Python. На крупном массиве KB+News — это удар по БД и памяти. Нужен `ts_rank`-кьюри с join на ACL-вьюшку, либо подсчёт «accessible from start» через CTE.

### 2.9 [MED] `_modules_cache` — process-local TTL 60s + redis version-bump
- `.\backend\app\api\modules.py:95-130`. Между bump-version и экспирацией процессного кэша возможен короткий период stale (до next-fetch). Для критических флагов модулей (включить/выключить) лучше — pubsub-инвалидация.

### 2.15 [LOW] WebDAV `max_keepalive_connections=10`
- `.\backend\app\services\nextcloud\webdav.py`. На 300 параллельных пользователях с активной работой с файлами — узкое место.

---

## 3. Логирование, метрики, наблюдаемость

### 3.6 [MED] Worker heartbeat / liveness отсутствует
- В `WorkerSettings` (`.\backend\app\worker\main.py`) нет периодической записи в Redis, по которой можно мониторить «жив ли воркер». Healthcheck Docker — только `redis ping`, не проверяет, что ARQ-loop крутится.

### 3.7 [LOW] Cron `flush_audit_queue` каждые 2 секунды
- `.\backend\app\worker\main.py:101-136`. Рабочее решение, но добавляет шум в логи (на старте / при пустой очереди — DEBUG скип). Можно перейти на `XREAD blocking` или ARQ `defer_by`.

### 3.9 [LOW] `bind_request_context` без `user_id` в worker
- В `worker/main.py` `bind_request_context(job_id=..., function=..)` — но нет `user_id` корреляции. Logs от worker сложно сопоставить с инициатором.

---

## 4. Тесты

### 4.1 [HIGH] Нет E2E-теста на CSRF double-submit
- `.\backend\tests\security\test_csrf.py` — unit. Нужен сценарий «полная цепочка login → safe GET → mutating POST с/без header».

### 4.9 [MED] Нет теста на bookmarks-лимит при multi-worker
- Тест `test_links_bookmarks.py` не воспроизводит multi-process race при одновременном добавлении закладок несколькими процессами.

### 4.11 [LOW] Нет тестов для `_hydrate_custom_metrics`
- `.\backend\app\main.py:393-421`. Pickup из Redis-снапшота нигде не проверяется.

### 4.13 [MED] Нет фикстуры «два worker процесса» для multi-instance scenarios
- `tests/conftest.py` — фикстуры есть, но нет возможности тестировать multi-worker конкуренцию.

---

## 5. Архитектура и общие проблемы

### 5.2 [MED] Frontend `router.beforeEach`: `await modulesStore.load()` per-navigation
- `.\frontend\src\router.ts`. Проверка модулей при каждом переходе на `/files` или `/photos` — даже с кэшем, дополнительная задержка. Можно prefetch при старте App.

### 5.4 [LOW] Большие frontend-компоненты
- `FilesPage.vue` (27 KB), `KbListPage.vue` (22 KB), `NewsFormPage.vue` (21 KB), `GlobalSearch.vue` (19.8 KB) — кандидаты на разбиение.

### 5.5 [MED] `audit.log` (services) и `push_audit_event` — два пути
- Часть кода пишет напрямую в `audit_log`, другая — через Redis-очередь и батч-flush. При failover Redis события из `push_audit_event` теряются. Стоит унифицировать или явно документировать различие.

### 5.6 [LOW] Множество `from ... import X` внутри функций
- В `main.py`, `auth.py` и др. много локальных импортов. Большинство — оптимизация startup time, а не избежание циклов. Стоит переместить на верхний уровень.

### 5.15 [LOW] `photos.empty_trash` — батч 500 без yield/throttle
- Может надолго заблокировать единственный backend-инстанс. Для крупной корзины лучше поставить ARQ-задачу.

### 5.16 [MED] `nc_federation`: `lookup_initiator` — race с `delete_initiator`
- `.\backend\app\services\nc_federation.py`. Если NC дёргает endpoint после TTL-эвикции — 404. TTL должен быть задокументирован.

---

## 6. База данных и миграции

### 6.1 [MED] Нумерация миграций линейная (001..034), без branch'ей
- При большом релизе трудно мерджить параллельные ветки.

### 6.2 [LOW] `init.sql` — первые партиции `audit_log` могут не покрывать 3+ месяца вперёд
- Нужно проверить, что при старте в production партиции создаются достаточно вперёд.

### 6.4 [MED] `file_folders.parent_id` — проверить политику ON DELETE
- Каскадное удаление опасно; нужно убедиться что там RESTRICT (аналогично `kb_sections.parent_id` и `photo_folders.parent_id`).

### 6.5 [LOW] Проверить GIN-индексы на `body_tsvector` в миграциях 007/011
- Должны быть `USING gin`, а не btree.

### 6.6 [LOW] Миграции `022_fk_indexes` и `024_trgm_indexes` добавлены позже основных
- Намёк на отсутствие части индексов в production между 008 и 022. Нужно проверить, не пропущено ли ещё что-то.

---

## 7. Frontend

### 7.1 [LOW] `i18n/ru.json` 67 KB — большой бандл
- Стоит lazy-load или split по разделам.

### 7.2 [MED] `stores/notifications.ts` — отписка SSE
- Проверить отписку SSE при переходе между страницами/выходе, чтобы не оставались hanging connections.

---

## 8. Документация

### 8.4 [LOW] `docs/db-schema.md` устарел
- Содержит «миграции 001..024», фактически 034. Нужно синхронизировать.

### 8.5 [LOW] `requirements.md` помечен как «архив»
- Желательно перенести в `docs/archive/`, чтобы не путать новых разработчиков.

---

## 9. Quick wins

- `.\backend\app\api\auth.py:280-292` — снизить уровень логирования / маскировать email в логах.
- `.\docker-compose.yml:191` — заменить worker healthcheck на `redis-cli` или с защитой от отсутствия env.
- `.\docker-compose.yml:46` — валидировать `REDIS_PASSWORD` или выделить ACL-файл монтирование.

---

## 10. Открытые вопросы / нужны уточнения

1. **`_prepare_password` SHA→bcrypt**: исторический выбор или сознательный? Можно ли мигрировать на argon2?
2. **`audit.log` vs `push_audit_event`**: какая семантика гарантий ожидается для каждого вида события?
3. **bootstrap admin password reset**: должен ли флаг сбрасываться сам после применения?

---

## 12. Производительность (продолжение детального ревью)

### 12.2.8 [MED] `api/photos/zip_jobs.download_zip_job`: `FileResponse` вместо X-Accel-Redirect
- `.\backend\app\api\photos\zip_jobs.py:61-78`. Большой zip держит file descriptor в event loop; стоит сделать `X-Accel-Redirect` через nginx (если zip в `/data/photos/zips` экспонирован для `internal` location).

---

## 12.4 Логирование / наблюдаемость (продолжение)

### 12.4.1 [MED] `nc_federation.delete_temp_share`: best-effort, без алёрта
- `.\backend\app\services\nc_federation.py:135-156`. Если NC недоступен или вернул 5xx — лог `WARNING` и идём дальше. Share остаётся в NC. Нет ни ретрая, ни Sentry-alert. Нужен ARQ-job «cleanup orphan NC shares».

### 12.4.3 [LOW] `screenshot-service`: `--no-sandbox` логируется только при старте, нет напоминания в health
- Если сервис поднят без sandbox — это security degradation, незаметная после старта.

---

## 12.5 Архитектура (продолжение)

### 12.5.1 [MED] `worker/tasks/files.startup_sync_nc_folders`: Redis-lock TTL 5 минут
- Если worker рестартует чаще 5 минут (CI, healthcheck) — пропустит синхронизацию NC-папок до следующего успешного TTL.

### 12.5.3 [LOW] `services/nextcloud/collabora.py`: `display_name` не ограничен по длине
- Возможны очень длинные URL → 414 от NC.

### 12.5.4 [LOW] `screenshot-service`: `MAX_WIDTH/HEIGHT` через env, но нет min-валидации
- При `width=0` Playwright упадёт, ответ 500, не 400.

---

## 13. Nginx, core/*, init.sql, миграции, setup.sh

### 13.1.8 [MED] `entrypoint.sh`: trigger-loop с `sleep 5` — race-окно
- `.\system_data\nginx\entrypoint.sh:31-38`. Между генерацией `reload-trigger` и `nginx -s reload` проходит до 5 секунд. При параллельной правке settings UI оба триггера схлопываются в один reload.

### 13.1.9 [LOW] `entrypoint.sh`: cleanup-loop в subshell без trap
- При завершении nginx subshell остаётся zombie, пока контейнер не убьют SIGKILL.

### 13.2.4 [MED] `extract_user_data` берёт `phone`, `department`, `job_title` из claims
- `.\backend\app\core\security.py:128-138`. Если Keycloak realm не настроен на эти claims — все эти поля будут пустыми/None. Стоит логировать «undefined claim» хотя бы один раз на нового пользователя.

### 13.2.15 [LOW] `security.py`: `from app.services.keycloak import get_jwks` на module level
- `.\backend\app\core\security.py:11`. core зависит от services → циркулярный риск при добавлении сервисом импорта core.

### 13.3.9 [MED] `service_links.created_by ON DELETE SET NULL` — sso_link бесхозный
- `.\backend\migrations\versions\003_links_bookmarks.py:34-39`. После удаления автора link продолжает работать — это ок. Но нет owner для модификации (admin берёт на себя).

### 13.3.12 [MED] `init.sql`: при сбое hunspell-словарей — непонятная ошибка
- `.\backend\migrations\init.sql:11-12`. При сбое (нет файлов словаря) `CREATE TEXT SEARCH DICTIONARY` упадёт с непонятной ошибкой. Нет проверки наличия файлов перед созданием.

### 13.3.16 [LOW] `news_versions.editor_id SET NULL` без аудит-фикса
- При удалении пользователя теряется связь «кто редактировал версию».

### 13.4.4 [MED] `gen_secret` использует `openssl rand -hex 32` без seed-валидации
- `.\setup.sh:96-100`. Не критично в нашем случае, но отсутствует явная проверка источника энтропии.

### 13.4.7 [LOW] `check_services` не показывает, какой контейнер тормозит
- `.\setup.sh:476-509`. Оператор видит просто dot-progress без информации о конкретном контейнере.

### 13.4.8 [LOW] `setup.sh` хардкодит имена контейнеров
- `.\setup.sh:457-465`. Если `docker-compose.yml` переименует — `check_services` сломается. Лучше парсить из `docker compose ps`.

### 13.4.9 [LOW] `MODE_FILE=".portal-mode"` — проверить наличие в `.gitignore`
- `.\setup.sh:20`. Не подтверждено наличие в `.gitignore`.

### 13.4.10 [LOW] `setup.sh` всегда `ENVIRONMENT=production` в `.env`
- `.\setup.sh:215`. Для staging override меняет через docker-compose env, но `.env` всё равно `production`.

### 13.5.3 [MED] `AGENTS.md` декларирует «X-Real-IP клиент подделать не может»
- Условие верно ТОЛЬКО при наличии trusted reverse-proxy перед nginx. Следует уточнить формулировку.

### 13.5.4 [MED] Idempotency-Key покрытие в коде
- `AGENTS.md:163` декларирует ключи для `POST /news, /kb/articles, /files/upload, /notifications/send`. Нужно убедиться, что декораторы `@idempotent` стоят на всех четырёх.

### 13.5.5 [LOW] `AGENTS.md` декларирует `nginx/nginx.conf` как активный конфиг
- Реально активная конфигурация в `system_data/nginx/nginx.conf` (volume), а в `nginx/nginx.conf` — лишь шаблон.

---

## 14. Frontend (Vue 3) — детальное чтение

### 14.1.5 [LOW] `IframeEmbed.parseHTML` принимает любой `<iframe>` без origin-фильтра
- `.\frontend\src\components\editor\extensions\IframeEmbed.ts:39`. Origin-проверка делается только в render через `sanitizeHtmlAllowIframe`, но в редакторе пользователь увидит «рабочий» iframe с произвольным origin.

### 14.4.3 [LOW] `modules.isEnabled` возвращает `true` если data ещё не загружена
- `.\frontend\src\stores\modules.ts:26-29`. Optimistic-default → flash контента, потом редирект на `/home`.

### 14.6.12 [MED] Integration-тесты для rate-limited endpoints
- `conftest.py:_stub_fastapi_limiter` — глобальный no-op для unit-тестов. Нужны integration-тесты для `bookmarks`, `kb`, `news`, `users/local`, `links` (помимо уже покрытого `auth/local/login`).

### 14.6.13 [MED] `conftest.py:_fake_db` отдаёт MagicMock для `session.execute`
- `.\backend\tests\conftest.py:296-323`. Endpoints, инспектирующие `result.mappings().all()`, упадут с непонятной ошибкой. Тесты deps-уровня поверхностны.

### 14.6.14 [MED] Нет E2E-тестов на photos public-share TTL и revoke
- `.\frontend\src\pages\photos\PublicPhotoPage.vue`, `PublicFolderPage.vue`. Нет тестов истечения токена и его отзыва.

### 14.6.15 [LOW] Нет тестов на frontend `sanitize.ts`
- `.\frontend\src\utils\sanitize.ts`. Vitest tests не найдены для всех 3 функций (включая обходы `<iframe srcdoc=...>`, `<a href="javascript:">`).

### 14.7.1 [LOW] Нет проверок `aria-current` на активных пунктах меню
- `AppLayout.vue` использует «skip-link» корректно, но `aria-current` не проставляется.

---

## 15. Admin tabs (frontend) и LightboxModal

### 15.1.3 [MED] `download` атрибут на cross-origin URL не сработает
- `.\frontend\src\components\photos\LightboxModal.vue:43-49`. При CDN/external storage `download="filename"` молча игнорируется браузером. Надёжнее — `Content-Disposition: attachment` на сервере.

### 15.1.8 [LOW] `originalUrl(currentPhoto.id, true)` — magic boolean flag
- `.\frontend\src\components\photos\LightboxModal.vue:46`. `download=true` булеан без enum.

### 15.5.4 [MED] `ModulesTab` и `PhotosTab` — дублирование логики save
- `.\frontend\src\pages\admin\tabs\ModulesTab.vue:231-242`. PhotosTab дублирует часть логики, вызывая тот же endpoint — нет общего источника истины.

### 15.8.3 [MED] `_activeAuditFilters.user_id` без UUID-валидации
- AuditTab.vue. Произвольная строка уйдёт в URL — бэкенд получит 422, но пользователь не понимает почему.

### 15.12.1 [MED] `e?.response?.status === 409` — может не сработать с ofetch FetchError API
- UserAttributesTab.vue. У ofetch FetchError структура `error.status` / `error.data` / `error.response.status` — нужно проверить точно.

### 15.12.2 [LOW] Discovery-section без debounce
- UserAttributesTab.vue. Refresh может быть permission-нагрузкой; нет debounce/throttle.

---

## 16. ADR consistency vs реализация

### 16.1 [MED] ADR-018 (LocalLogin = `str` вместо `EmailStr`)
- `.\docs\adr.md:594-617`. ADR обосновывает SHA256-pre-hash, но в схеме `LocalLogin` поле `email: str` — потенциальный вектор для SQL-инъекции через длинные email-строки, если где-то нет escaping.

### 16.2 [HIGH] ADR-020 (Admin UI единая точка) + 60s cache → race при изменении из 2 окон
- `.\docs\adr.md` (ADR-020) + `.\backend\app\api\modules.py:95-130`. TTL 60s memory-cache не инвалидируется кросс-процессно — два админа видят разные состояния до minute-flip. В ADR-020 не оговорено.

### 16.5 [MED] ADR-031 (`materialized_path` slugs) — нет уникальности по `path` глобально
- `.\docs\adr.md:786-806`. `slug` уникален в пределах parent, но `path` — нет. При concurrent rename папок возможен дубликат `path`. Нужен unique index по `path`.

### 16.7 [MED] ADR-023 (SSE limit MAX=5) — без admin-настройки
- `.\docs\adr.md:621-646`. MAX=5 как константа. При 5 устройствах пользователя — упрётся в лимит. Должен быть в `system.json`.

### 16.8 [LOW] ADR-024 (SSRF-guard) — Azure/Oracle metadata endpoints не в списке
- При текущем on-prem deployment не актуально, но known-limitation для будущего.

### 16.9 [MED] ADR-025 (Double-Submit Cookie) — exempt paths включают `/auth/local/login`
- `.\docs\adr.md:686`. `auth/local/login` — это mutating POST без CSRF-защиты. ADR должен явно перечислить, какие slots защиты остаются (SameSite=Lax + Origin-check).

---

**Итого открытых находок**: ~46 пунктов.  
**Закрыто за сессии 1–8**: ~33 находки.  
**Высокой важности (открытых)**: 2 (4.1, 16.2).  
**Средней (открытых)**: ~22.  
**Низкой / стилистика (открытых)**: ~22.
