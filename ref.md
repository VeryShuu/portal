# Аудит качества кода: Корпоративный портал — оставшиеся задачи

> Данный файл содержит **только** невыполненные пункты исходного аудита.
> Уже закрытые задачи (1.1.a, 1.1.b, 1.1.c, 1.1.d, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.11, 1.12, 1.13, 1.14, 1.15, 2.1.a, 2.1.b, 2.1.c, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 3.1, 3.2, 3.3, 3.7, 3.8, 3.9, 3.10, 3.12) удалены.
> Дата последнего обновления: 2026-05-09 (правка 14).

---

## Условные обозначения

| Значок | Смысл |
|--------|-------|
| 🔴 | Критично — требует исправления в первую очередь |
| 🟡 | Важно — создаёт риски при росте или изменениях |
| 🟢 | Незначительно — улучшение качества кода |
| **Сложность исправления:** | ●○○ Низкая / ●●○ Средняя / ●●● Высокая |

---

## 2. Клиентская часть (Frontend)

### 2.8 🟡 Два подхода к загрузке данных

vue-query (KbArticle/KbList/NewsDetail) vs ручные ref-флаги (FilesPage/NewsForm/UserProfileView).

**Как исправить:** выбрать vue-query везде. Сложность: ●●●

---

## 4. Сводная таблица оставшегося

| # | Проблема | Тип | Сложность | Приоритет |
|---|---|---|---|---|
| 2.8 | Два подхода к data fetching | Frontend | ●●● | 🟡 |

---

## Закрытые ранее (для истории)

| # | Проблема | Дата |
|---|---|---|
| 1.1.a | Рефакторинг main.py → middleware/ + core/bootstrap + core/lifespan + api/__init__ | 2026-05-08 |
| 1.1.b | Вынос nginx-конфигуратора из system_config.py → services/nginx_config.py + services/tls_status.py | 2026-05-08 |
| 1.2 | Дедуп PUT/PATCH в system_settings | 2026-05-08 |
| 1.5 | Дублирование cache-helper'ов в files_acl.py | 2026-05-08 |
| 1.6 | 12× «найти статью или 404» в kb_extra.py | 2026-05-08 |
| 1.8 | VIEW_DEDUP_TTL_SECONDS в трёх местах | 2026-05-08 |
| 1.13 | Atomic write для email-settings.json | 2026-05-08 |
| 1.14 | `_perm_gte` → public `perm_gte` | 2026-05-08 |
| 1.15 | Bare HTTP-коды → `status.HTTP_*` в kb_extra.py | 2026-05-08 |
| 2.2 | Прямая мутация Pinia (`links.ts`, `auth.ts` + actions) | 2026-05-08 |
| 2.4 | Хардкод русских строк в `KbListPage.vue` | 2026-05-08 |
| 2.5 | Нет обработки ошибок сети (`KbArticlePage`, `links.ts`) | 2026-05-08 |
| 3.3 | Исчерпание DB pool (`pool_size=8, max_overflow=10`) | 2026-05-08 |
| 2.7 | Дублирование `formatDate` → `utils/formatDate.ts` | 2026-05-08 |
| 2.9 | Module-level singleton useLayoutHeader → Pinia `useLayoutStore` | 2026-05-08 |
| 2.10 | Таймер debounce без cleanup в KbListPage → `onUnmounted` | 2026-05-08 |
| 2.12 | Магические числа в GlobalSearch → именованные константы | 2026-05-08 |
| 2.14 | Дублирование строк маршрутов → `ROUTES` константы в router.ts | 2026-05-08 |
| 2.15 | Двойной `<script>` в FilesPage.vue → `defineOptions` | 2026-05-08 |
| 2.6 | Клиентская фильтрация поиска новостей → серверный q-параметр | 2026-05-08 |
| 2.11 | Три способа confirm-диалога → единый `useConfirmDialog()` | 2026-05-08 |
| 2.13 | Динамические import в auth-store → задокументированы (cyclic deps) | 2026-05-08 |
| 3.12 | DATABASE_URL/REDIS_URL собираются в docker-compose.yml (убраны из .env.example) | 2026-05-08 |
| 3.8 | CSP убран из FastAPI middleware — единственный источник nginx | 2026-05-08 |
| 1.9 | Pydantic-схемы branding/kb_extra → `app/schemas/` (+ re-export для backward compat) | 2026-05-08 |
| 3.9 | `chown -R /data` только при первом старте через sentinel `/data/.chowned` | 2026-05-08 |
| ruff | Зачистка 7 pre-existing ошибок (RUF100/I001/E501/N814) — `ruff check .` чист | 2026-05-08 |
| 1.3 | Один commit на bulk upload (вместо commit на каждый файл) + drift-аудит при сбое DB-commit | 2026-05-08 |
| 1.4 | Единый порядок «БД → NC» с компенсацией: create (flush→NC→commit, NC-rollback при сбое commit), rename (commit→NC.move, DB-restore при сбое NC), delete (drift-audit при NC-fail) | 2026-05-08 |
| 1.1.c | Рефакторинг api/files.py (1577 стр.) → пакет api/files/ (_common, folders, upload, download, files_ops, permissions, sync). OpenAPI snapshot для /files/* идентичен (17 paths, 0 ops_changed). Integration-патчи перенаправлены на сабмодули. | 2026-05-08 |
| 2.1.c | Декомпозиция components/AppLayout.vue (779 → 159 строк): components/layout/ (AppSider, AppMobileDrawer, AppHeader, HeaderUserMenu, HeaderLangSwitcher, HeaderThemeToggle) + composables (useBreakpoints, useGlobalHotkeys, useAppMenu). HeaderNotificationsBell пропущен — NotificationsDropdown самодостаточен. typecheck/lint/i18n чисто; unit-tests 191/191. | 2026-05-08 |
| links-test | Обновлён tests/unit/links-store.spec.ts для соответствия фактическому поведению loadLinks() (errorLinks вместо reject). | 2026-05-08 |
| 2.1.b | Декомпозиция LinksAndBookmarksPage.vue (931 → 96 строк): components/links/ (LinkCard, LinkFormModal, BookmarkFormModal, ServiceLinksTab, BookmarksTab) + composables (useFavicon, useLinkIconUpload, useSortableGroups) + NormalizedItem → api/links.ts. Tabs используют defineExpose({ openAdd }), страница вызывает через template refs. typecheck/lint/i18n чисто; unit-tests 191/191. | 2026-05-08 |
| 3.2 | Reload nginx через polling → inotifywait: nginx/Dockerfile (alpine + inotify-tools), portal-nginx собирается из ./nginx, entrypoint.sh использует inotifywait -m -e create -e moved_to (polling как fallback). | 2026-05-08 |
| 3.10 | Статику отдаёт nginx (alias /data/avatars, /data/news_media, /data/link_icons) вместо FastAPI StaticFiles. Volume mounts в docker-compose, StaticFiles удалён из main.py (директории создаются для записи uploads). | 2026-05-08 |
| 2.3 | Прямые API-вызовы из BrandingTab.vue → store actions (uploadAsset/resetAsset/assetUrl в branding store). GlobalSearch.vue → composables/useGlobalSearch.ts (runGlobalSearch с Promise.allSettled). typecheck/lint/i18n чисто; unit-tests 191/191. | 2026-05-08 |
| 3.1 + 3.7 | Генерация nginx-конфигов вынесена из бэкенда в sidecar `nginx-config` (alpine + jq + envsubst + inotify-tools). Шаблоны в `nginx/templates/` (http_redirect, https_server, http_only_server, proxy_locations) — единый источник. Sidecar инотифицирует `/data/settings/system.json` и `/data/certs/`, рендерит `ssl_server.conf`/`allowlist.conf`/`limits.conf` в `/data/nginx-conf` и тачит reload-trigger. `services/nginx_config.py` 327→80 строк (остались `_build_nginx_csp` для тестов, `trigger_nginx_reload`, `_CERTS_DIR`); `_apply_settings`/TLS-эндпойнты больше не вызывают генератор. `system_data/nginx/entrypoint.sh` ждёт sidecar (health-gate в compose). ruff чист; unit-tests 42/42 для system_settings. | 2026-05-09 |
| 1.12 | Единый источник истины для runtime-конфига (ADR-037): `config.py::Settings` оставляет только bootstrap-параметры (БД/Redis/секреты/Keycloak/admin/screenshot/DB pool); 16 runtime-полей (portal_base_url, *_max_size_mb, allowed_cidr, log_*, sentry_dsn, prometheus_*, metrics_token, arq_max_jobs, nc_files_root, nc_service_username) удалены из Settings — читаются только из `system.json`. `migrate_env_to_system_settings()` однократно мигрирует легаси env→JSON при старте main/worker; повторный запуск с присутствующими env-переменными логирует warning `config.deprecated_env_vars_ignored`. Все call-sites очищены от fallback-цепочек `... or settings.X`. Тесты: `_stub_system_settings` autouse session fixture в conftest подменяет `_SYSTEM_SETTINGS_FILE` на tmp с тестовыми значениями; добавлены `TestEnvMigration` (4 теста) и `test_legacy_runtime_fields_removed` (regression guard). | 2026-05-09 |
| 1.1.d | Рефакторинг api/kb.py (1354 стр.) + api/kb_extra.py (1040 стр.) → пакет api/kb/ (_common, _frontmatter, sections, tags, articles, versions, comments, suggestions, feedback, permissions, media, attachments, export_import). Дубликат `_slugify` устранён (единый fallback="section"). kb_extra.py превращён в тонкий shim для backward-compat (реэкспорт из новых мест). api/__init__.py: kb_extra_router удалён, единственный kb_router. 43 пути, 0 ops_changed. ruff чист; unit-tests 815 passed, 5 skipped. | 2026-05-09 |
| 1.7 | N+1 в KB: `get_article` 5→2 запроса (users IN + feedback агрегат FILTER/MAX CASE); `get_sections` N→1 (batch_resolve_section_permissions, MGET + CTE ALL); `list_articles` N→1 (batch_resolve_article_permissions). Добавлены `batch_resolve_section_permissions` и `batch_resolve_article_permissions` в kb_acl.py по образцу batch_resolve_folder_permissions из files_acl.py. | 2026-05-09 |
| 1.11 | Бизнес-логика вынесена из роутеров: новый `services/kb.py` (record_article_view, set_article_tags); `services/news.py` расширен (upload_cover, delete_cover, upload_gallery_image, delete_gallery_image, upload_attachment, delete_attachment). `api/kb/articles.py` и `api/news.py` сведены к оркестрации HTTP + аудит. `api/kb/_common.py` очищен от tag-логики. | 2026-05-09 |
| 2.1.a | Декомпозиция pages/FilesPage.vue (1111 → 226 строк): components/files/ (FilesSidebar, FilesBreadcrumbs, FilesToolbar, FilesBulkBar, FilesTable, FilesDropZone, FilesCreateFolderModal, FilesMoveModal) + composables (useFilesTree, useFilesSelection, useFilesUpload, useFilesBulkOps, useCollabora) + stores/files.ts (useFilesStore) + utils/extractDroppedFiles.ts. Unit-тесты: extract-dropped-files.spec.ts (6 кейсов), files-store.spec.ts (14 кейсов). typecheck/lint чисто; unit-tests 211/211 (+20 новых). ТЗ: docs/tz-2.1.a-files-page-decomposition.md. | 2026-05-09 |
