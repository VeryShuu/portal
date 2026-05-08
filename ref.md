# Аудит качества кода: Корпоративный портал — оставшиеся задачи

> Данный файл содержит **только** невыполненные пункты исходного аудита.
> Уже закрытые задачи (1.1.a, 1.1.b, 1.1.c, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.13, 1.14, 1.15, 2.1.b, 2.1.c, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 3.2, 3.3, 3.8, 3.9, 3.10, 3.12) удалены.
> Дата последнего обновления: 2026-05-08 (правка 9).

---

## Условные обозначения

| Значок | Смысл |
|--------|-------|
| 🔴 | Критично — требует исправления в первую очередь |
| 🟡 | Важно — создаёт риски при росте или изменениях |
| 🟢 | Незначительно — улучшение качества кода |
| **Сложность исправления:** | ●○○ Низкая / ●●○ Средняя / ●●● Высокая |

---

## 1. Серверная часть (Backend)

### 1.1 🔴 «Монстр-файлы»

> Подзадача 1.1.d. Контракты API не меняются, проверка через openapi-снапшот.

#### 1.1.d 🔴 Объединение `api/kb.py` (1354) + `api/kb_extra.py` (1142) → пакет `api/kb/`

```
backend/app/api/kb/
├── __init__.py          # один router aggregator
├── _common.py           # _slugify, _get_breadcrumbs, _get_article_or_404, _article_to_public, _resolve_tags, _set_article_tags, _rfc5987_filename
├── _frontmatter.py
├── sections.py
├── articles.py
├── tags.py
├── versions.py
├── comments.py
├── suggestions.py
├── feedback.py
├── permissions.py
├── media.py
├── attachments.py
└── export_import.py
```

**Подводные камни:** удалить дубликат `_slugify`. Pydantic-схемы из `kb_extra.py` → `app/schemas/kb_extra.py` (пересекается с 1.9). В `main.py` объединить `kb_router` + `kb_extra_router`. Проверить уникальность operation_id.

**Сложность:** ●●● • **Риск:** высокий • **Оценка:** 16–24 ч

---

### 1.7 🟡 N+1 запросы при отображении статьи KB / списка разделов

Статья — 5 запросов (автор, редактор, лайки, дизлайки, оценка пользователя). Список разделов — отдельный запрос на каждую секцию.

**Как исправить:** объединить запросы с агрегацией; пакетная проверка прав по аналогии с files. Сложность: ●●○

---

### 1.11 🟡 Бизнес-логика смешана с обработчиками HTTP

Загрузка файлов (MIME, стриминг, аудит), теги статей, дедупликация просмотров — всё в роутерах.

**Как исправить:** перенести в `services/`. Сложность: ●●○

---

### 1.12 🟡 Два источника конфигурации: env и JSON

Параметры (upload limit, log level, NC URL и др.) объявлены и в `config.py`, и в `system_config.py`. При старте — ручное слияние.

**Как исправить:** один источник истины (либо JSON только, либо env только). Сложность: ●●●

---

## 2. Клиентская часть (Frontend)

### 2.1 🔴 «Монстр-компоненты»

> Подтверждено: `FilesPage.vue` 1116, `LinksAndBookmarksPage.vue` 931 строк. (`AppLayout.vue` декомпозирован — см. 2.1.c в закрытых.)

#### 2.1.a 🔴 Декомпозиция `pages/FilesPage.vue` (1116 строк)

```
pages/FilesPage.vue                       # ~250 строк: оркестратор
components/files/
├── FilesSidebar.vue
├── FilesBreadcrumbs.vue
├── FilesToolbar.vue
├── FilesTable.vue
├── FilesDropZone.vue
├── FilesCreateFolderModal.vue
├── FilesMoveModal.vue
├── FilesImagePreview.vue                 # уже существует
└── FilesPermissionsModal.vue             # уже существует
composables/
├── useFilesTree.ts
├── useFilesSelection.ts
├── useFilesUpload.ts
└── useFilesBulkOps.ts
```

**Подводные камни:** общее состояние → pinia-store `useFilesStore` (пересекается с 2.3). `extractDroppedFiles` (`webkitGetAsEntry`) — unit-тест. `openCollabora` → composable.

**Сложность:** ●●● • **Риск:** высокий • **Оценка:** 16–24 ч

---

**Порядок:** 2.1.a. **Суммарно:** 16–24 ч.

**Связки:** 2.1.a + 2.3.

---

### 2.8 🟡 Два подхода к загрузке данных

vue-query (KbArticle/KbList/NewsDetail) vs ручные ref-флаги (FilesPage/NewsForm/UserProfileView).

**Как исправить:** выбрать vue-query везде. Сложность: ●●●

---

## 3. Инфраструктура и развёртывание

### 3.1 🔴 Бэкенд генерирует конфиги nginx

`backend/app/services/nginx_config.py` генерирует server-блоки, CSP, IP-allowlist, SSL.

**Как исправить:** init-контейнер инфраструктуры; параметры через env. Сложность: ●●●

---

### 3.7 🟡 Nginx инициализируется в трёх несовместимых местах

`system_data/nginx/entrypoint.sh`, `backend/app/services/nginx_config.py`, `nginx.conf`.

**Как исправить:** единый шаблон. Сложность: ●●○

---

## 4. Сводная таблица оставшегося

| # | Проблема | Тип | Сложность | Приоритет |
|---|---|---|---|---|
| 1.1.d | api/kb*.py → пакет | Backend | ●●● | 🔴 |
| 1.7 | N+1 запросы в KB | Backend | ●●○ | 🟡 |
| 1.11 | Бизнес-логика в роутерах | Backend | ●●○ | 🟡 |
| 1.12 | Два источника конфигурации | Backend/Инфра | ●●● | 🟡 |
| 2.1.a | Декомпозиция FilesPage.vue | Frontend | ●●● | 🔴 |
| 2.8 | Два подхода к data fetching | Frontend | ●●● | 🟡 |
| 3.1 | Бэкенд генерирует конфиги nginx | Инфра | ●●● | 🔴 |
| 3.7 | Nginx-конфиг в трёх несовместимых местах | Инфра | ●●○ | 🟡 |

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
