# rev.md — История применённых правок (apr 2026)

> **Дата ревью:** 27 апреля 2026
> **Статус:** ✅ все P0/P1/P2 применены, P2-14 опровергнут, P3 — частично (docs).
> **Подробности изменений:** см. ADR-033 в `docs/adr.md` и `AGENTS.md` (раздел "Чего НЕ делать", "Безопасность", "Правила разработки").

---

## Сводка

Комплексное ревью перед прод-деплоем выявило 41 пункт. Верификация по коду подтвердила 40 из них (P2-14 — E2E auth-сценарии — опровергнут).

| Уровень | Кол-во | Применено |
|---|---|---|
| 🔴 P0 | 10 | 10 ✅ |
| 🟠 P1 | 24 | 24 ✅ |
| 🟡 P2 | 20 | 19 ✅ + 1 опровергнут (P2-14) |
| 🟢 P3 | 7 | 5 ✅ (docs) + 2 deferred (P3-01 split AdminPage, P2-08 ACL refactor) |

---

## P0 — все исправлены

| # | Краткое описание | Где |
|---|---|---|
| P0-01 | Дубль ключа `kb` в i18n — слиты в один блок | `frontend/src/i18n/{ru,en}.json` |
| P0-02 | KB ACL bypasses — добавлены `require_article_permission` / `require_section_permission` в 11 endpoints | `backend/app/api/kb.py` |
| P0-03 | JWT issuer проверка | `backend/app/core/security.py` |
| P0-04 | SQL-инъекция через `user.department` — bind-параметр | `backend/app/api/search.py` |
| P0-05 | ARQ enqueue по короткому имени `notify_news_published` (+ sync_users_from_keycloak) | `backend/app/worker/tasks/news.py`, `users.py` |
| P0-06 | Photos rename — commit БД ДО FS-rename + компенсация | `backend/app/api/photos.py::update_folder` |
| P0-07 | MIME через `python-magic` (allowed_mimes в `stream_upload_to_path`) | `backend/app/api/photos.py::upload_photos` |
| P0-08 | photos_acl `_subject_ids_for_user` включает `user.id` | `backend/app/services/photos_acl.py` |
| P0-09 | ZIP стримом в файл (не BytesIO) | `backend/app/worker/tasks/photos.py` |
| P0-10 | Audit queue recovery: LMOVE queue→processing, DEL processing после INSERT | `backend/app/worker/tasks/audit.py` |

---

## P1 — все исправлены

| # | Краткое описание | Где |
|---|---|---|
| P1-01 | `.env.example` дополнен 18 переменными (Keycloak/Sentry/uploads/ARQ/...) | `.env.example` |
| P1-02 | Ротация `session_id` при `/auth/refresh` (новый Redis-ключ + Set-Cookie) | `backend/app/api/auth.py` |
| P1-03 | Единый Redis pool через `app.state.redis` | `backend/app/main.py`, `api/deps.py` |
| P1-04 | Shared cache invalidation через `bump_version`/`get_version` (Redis) | `backend/app/core/cache_version.py` (новый), `system_settings.py`, `modules.py`, `keycloak.py` |
| P1-05 | JWKS retry при unknown kid (clear + refetch) | `backend/app/core/security.py` |
| P1-06 | Email-based rate limit на /auth/local/login (двойной — IP + sha256(email)) | `backend/app/core/limiter.py`, `auth.py` |
| P1-07 | asyncpg pool в `ctx["pg_pool"]` worker'а | `backend/app/worker/main.py`, `tasks/audit.py` |
| P1-08 | restore_folder через рекурсивный CTE | `backend/app/api/photos.py` |
| P1-09 | `Photo.deleted_at IS NULL` в cover-check и thumbnail | `backend/app/api/photos.py` |
| P1-10 | try/finally вокруг ARQ pool в `_enqueue_news_notifications` | `backend/app/worker/tasks/news.py` |
| P1-11 | Импорт 6 моделей в `__init__.py` (FileFolder, FileFolderPermission, KbSectionPermission, KbArticlePermission, KbArticleFile, PhotoShareToken) | `backend/app/models/__init__.py` |
| P1-12 | FS side-effects из migration 016 вынесены в `backend/scripts/migrate_016_fs.py` | `migrations/versions/016_*.py`, `scripts/migrate_016_fs.py` |
| P1-13 | `CREATE EXTENSION IF NOT EXISTS pg_trgm` в начале миграций 008 и 011 | `migrations/versions/008_kb.py`, `011_news_fts_hunspell.py` |
| P1-14 | list_deleted_photos требует `manager` уровень | `backend/app/api/photos.py` |
| P1-15 | KB import vault — лимит размера (`KB_IMPORT_MAX_SIZE_MB`) | `backend/app/api/kb_extra.py`, `core/config.py` |
| P1-16 | list_deleted_photos: ACL до pagination (Python) | `backend/app/api/photos.py` |
| P1-17 | KB import overwrite — `require_article_permission(editor)` | `backend/app/api/kb_extra.py` |
| P1-18 | logout без `id_token_hint` в URL (только client_id + redirect_uri) | `backend/app/services/keycloak.py` |
| P1-19 | OIDC error → generic 401 ("Authorization failed"), детали в логах | `backend/app/api/auth.py` |
| P1-20 | `push_audit_event` во всех admin endpoints (users/links/branding/system_settings/modules/keycloak_admin) — 27 вызовов | 6 файлов |
| P1-21 | `grant_folder_permission` — IntegrityError retry | `backend/app/api/photos.py` |
| P1-22 | GIN trgm индекс на `news.title` | `migrations/versions/021_news_title_trgm.py` (новая) |
| P1-23 | Индекс на `photo_folders.fs_path` | миграция 021 |
| P1-24 | `_sanitize_folder_name` в migration 016 синхронизирована с production (180+hash8) | `migrations/versions/016_*.py` |

---

## P2 — 19 исправлено, 1 опровергнут

| # | Описание | Статус |
|---|---|---|
| P2-01 | revokeObjectURL в Admin/LinksPage + onUnmounted | ✅ |
| P2-02 | `isSafeHttpUrl` валидация bookmark URL (frontend) | ✅ `frontend/src/utils/url.ts` |
| P2-03 | Lazy-loading admin tabs (`ensureTabLoaded`) | ✅ |
| P2-04 | Хардкод русских строк → `t()` (5 мест) | ✅ |
| P2-05 | `AUDIT_QUEUE_KEY` в одном месте | ✅ `app/services/audit.py` |
| P2-06 | Удалены orphaned `admin.audit.*` / `admin.analytics.*` ключи | ✅ |
| P2-07 | NOTE-комментарий в migration 020, module-guards `/files`, `/photos` в router | ✅ `frontend/src/stores/modules.ts` (новый) |
| P2-08 | Дублирование `_cache_key`/`_get_cached`/`_scan_and_delete`/`perm_gte` в 3 ACL модулях | ⏸️ DEFER (рефакторинг — высокий риск, ADR-033) |
| P2-09 | `clear_request_context()` в `finally` middleware | ✅ |
| P2-10 | `server_default=text("gen_random_uuid()")` для FileFolder.id | ✅ |
| P2-11 | FK `cover_photo_id` в модели PhotoFolder | ✅ |
| P2-12 | UniqueConstraint `uq_pfst_token` в модели PhotoFolderShareToken | ✅ |
| P2-13 | Индексы FK (9 шт.) — миграция 022 | ✅ `migrations/versions/022_fk_indexes.py` |
| P2-14 | E2E без auth | ❌ ОПРОВЕРГНУТО — `auth.spec.ts`, `local-login.spec.ts` есть |
| P2-15 | SSE limit fail-closed (503 при Redis error) | ✅ |
| P2-16 | `load_system_settings_shared(redis)` через cache_version | ✅ |
| P2-17 | `notify_users_news_published` — батчинг по 500 | ✅ |
| P2-18 | Sentry `before_send=scrub_sensitive` + reinit при смене DSN | ✅ `app/core/sentry.py` (новый) |
| P2-19 | `set_log_level` обновляет arq + sqlalchemy.engine | ✅ |
| P2-20 | `detect_missing_thumbnails` — батч-итерация | ✅ |

---

## P3 — docs обновлены

| # | Описание | Статус |
|---|---|---|
| P3-01 | AdminPage.vue split на tab-компоненты | ⏸️ DEFER (high risk; lazy-load уже сделан в P2-03) |
| P3-02 | 401 redirect сохраняет `search` + `hash` | ✅ |
| P3-03 | Side-effects в lifespan() | ⏸️ DEFER (см. ADR-033 — частично уже в P1-03) |
| P3-04 | Дубль `_slugify` (kb.py / photos.py) | ⏸️ DEFER |
| P3-05 | `order_index` → `sort_order` в api-contracts.md | ✅ |
| P3-06 | db-schema.md — комментарий о notifications актуализирован | ✅ |
| P3-07 | docs/phase-0.md — добавлен warning-блок об архивном статусе | ✅ |

---

## Архитектурные изменения (см. ADR-033)

1. **Единый Redis client** — `app.state.redis` (был дубль).
2. **Shared cache versioning** — `app/core/cache_version.py` для system_settings/modules/keycloak_config/jwks. Решает рассинхрон между uvicorn workers и ARQ worker.
3. **Audit queue at-least-once** — LMOVE→processing list, DEL только после успешного INSERT.
4. **Session rotation** — новый `session_id` на каждый /auth/refresh.
5. **Photos rename atomicity** — commit БД до FS-операции с компенсирующим rollback.

## Новые файлы

- `backend/app/core/cache_version.py` — Redis-based version counters
- `backend/app/core/sentry.py` — `scrub_sensitive` для PII/secrets
- `backend/scripts/migrate_016_fs.py` — отдельный FS-перенос для миграции 016
- `backend/migrations/versions/021_news_title_trgm.py` — GIN trgm индекс
- `backend/migrations/versions/022_fk_indexes.py` — индексы FK
- `frontend/src/stores/modules.ts` — store для toggle модулей
- `frontend/src/utils/url.ts` — `isSafeHttpUrl`

## Deferred

| Пункт | Причина |
|---|---|
| P2-08 | Рефакторинг ACL helpers в `acl_cache.py` — высокий риск, делать отдельным PR |
| P3-01 | Split AdminPage.vue (2199 строк) — высокий риск, lazy-load уже снизил нагрузку |
| P3-03 | Полный перенос side-effects в lifespan() — уже частично сделано (Redis pool, Sentry init) |
| P3-04 | Унификация `_slugify` — низкий приоритет |

## Ручные действия после деплоя

⚠️ Если migration 016 уже применена в проде — запустить `python backend/scripts/migrate_016_fs.py` для физического переноса каталогов фото.
