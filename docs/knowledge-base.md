# Модуль «База знаний»

> **Когда читать:** разделы/статьи KB, per-section ACL, FTS, вложения, версионирование.
> **Ключевой код:** `./backend/app/api/kb/`, `./backend/app/services/kb_acl/`, `./backend/app/models/kb.py`, `./frontend/src/pages/Kb*.vue`.
> **ADR:** 005, 006, 008, 009, 010. **См. также:** `./docs/adr.md`.

> Собственный модуль портала. Иерархия разделов с per-section ACL (viewer / editor / manager), статьи с версионированием и полнотекстовым поиском, вложения и inline-медиа, импорт/экспорт Markdown/ZIP/PDF/DOCX, предложения правок, комментарии, фидбек. Backend — FastAPI + SQLAlchemy + PostgreSQL, Frontend — Vue 3 + TanStack Query + Naive UI.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/kb/`), SQLAlchemy, PostgreSQL (FTS через `russian_hunspell`) |
| Frontend | Vue 3 + TanStack Query + Naive UI (`./frontend/src/pages/Kb*.vue`, `./frontend/src/components/Kb*.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/kb.py`) (задачи `purge_kb_trash`, `cleanup_kb_orphan_dirs`) |
| Хранилище | Локальная ФС: пути из конфигурации (`kb_files_dir`, `kb_media_dir`) |
| Префикс API | `/api/v1/kb` |
| ACL-кэш | Redis, ключи `kb_acl:{user_id}:{resource}:{resource_id}` (TTL из `acl_base.ACL_TTL`) |
| Связанные ADR | ADR-005 (TipTap), ADR-006 (PDF), ADR-008 (Markdown), ADR-009 (version), ADR-010 (RESTRICT) |

### Возможности

- Дерево разделов неограниченной вложенности с soft-delete.
- Гранулярные права на раздел и на статью (viewer / editor / manager) с наследованием от родителя; subject = `user` или `group` (Keycloak).
- Статьи со статусами `draft / published / archived`, полнотекстовым поиском и счётчиком просмотров (дедупликация через Redis).
- Полная история версий: каждое сохранение создаёт снимок; откат к любой версии; diff между любыми двумя версиями.
- Оптимистичная блокировка параллельного редактирования (поле `version`, 409 Conflict при коллизии), включая автосохранение черновика.
- Вложения (файлы) и inline-медиа (картинки в теле статьи).
- Комментарии и предложения правок (suggestions).
- Теги (глобальные, many-to-many, ≤ 20 на статью).
- Фидбек «полезно / не полезно» (один голос на пользователя).
- Импорт одиночного Markdown-файла и ZIP-vault-архива (с защитой от zip-bomb и path traversal).
- Экспорт статьи в Markdown, PDF, DOCX; экспорт раздела и полного vault в ZIP.

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/kb/` | Эндпоинты разделов, статей, вложений, комментариев, правок, прав доступа, импорта/экспорта |
| Service | `./backend/app/services/kb.py`, `./backend/app/services/kb_acl/` | Бизнес-логика, полнотекстовый поиск, дерево разделов, очистка корзины, импорт/экспорт |
| Model | `./backend/app/models/kb.py` | SQLAlchemy ORM модели базы знаний |
| Schema | `./backend/app/schemas/kb.py`, `./backend/app/schemas/kb_extra.py` | Pydantic-схемы запросов и ответов API, валидация |
| Worker | `./backend/app/worker/tasks/kb.py` | Фоновые задачи периодического удаления просроченных статей и сиротских директорий |
| Frontend | `./frontend/src/pages/Kb*.vue`, `./frontend/src/components/Kb*.vue` | Страницы и компоненты интерфейса базы знаний |
| API Client | `./frontend/src/api/kb.ts` | REST-клиент |
| Queries | `./frontend/src/queries/kb.ts`, `./frontend/src/composables/` | TanStack Query хуки и реактивные composables |

### Детализация backend-структуры

| Файл | Назначение |
|---|---|
| `./backend/app/api/kb/__init__.py` | Сборка `router` из подроутеров. |
| `./backend/app/api/kb/_common.py` | Общие хелперы (`_article_to_public`, `_get_article_or_404`, `_get_breadcrumbs`, `_slugify`, `_rfc5987_filename`, `build_users_map`, `user_ref`). |
| `./backend/app/services/kb_markdown.py` | YAML front-matter: парсинг, генерация, `_get_or_create_section_by_path` (с `pg_advisory_xact_lock`), `_zip_section`. |
| `./backend/app/api/kb/_pdf_export.py` | HTML rendering для PDF-экспорта статьи (`render_article_html_for_pdf`) — инлайнит inline-медиа как data-URI. |
| `./backend/app/api/kb/_docx_export.py` | DOCX-рендер статьи (`render_article_docx`) — Markdown→DOCX со встраиванием inline-картинок (WebP конвертируется в PNG через Pillow, ширина капится). |
| `./backend/app/api/kb/_kb_media.py` | Хелперы для KB-медиа при экспорте: `kb_media_path`, `kb_media_data_uri`, `inline_kb_media_as_data_uris` (data-URI для headless-рендера PDF) и `KB_MEDIA_URL_RE` (резолв пути для DOCX). |
| `./backend/app/api/kb/sections.py` | CRUD дерева разделов, batch-резолв прав, soft-delete. |
| `./backend/app/api/kb/articles/__init__.py` | Пакет articles: re-экспорт символов для совместимости с `mock.patch`. |
| `./backend/app/api/kb/articles/_list.py` | `GET /kb/articles` — список с фильтрами, поиском, пагинацией. |
| `./backend/app/api/kb/articles/_crud.py` | Создание, чтение, обновление статьи, автосохранение черновика. |
| `./backend/app/api/kb/articles/_trash.py` | Soft-delete, окончательное удаление (purge), восстановление статьи. |
| `./backend/app/api/kb/versions.py` | История версий (список без тел, детальный GET с телом), откат, diff (лимит 500 000 символов, `run_in_executor`). |
| `./backend/app/api/kb/comments.py` | CRUD комментариев статьи. |
| `./backend/app/api/kb/suggestions.py` | Предложения правок: создание, просмотр, рецензирование (approve/reject). |
| `./backend/app/api/kb/feedback.py` | Оценка статьи «полезно / нет». |
| `./backend/app/api/kb/attachments.py` | Файловые вложения: загрузка, список, удаление, скачивание (X-Accel-Redirect + аудит через Redis SET NX EX). |
| `./backend/app/api/kb/media.py` | Inline-картинки: загрузка с проверкой расширения и MIME, раздача через X-Accel-Redirect. |
| `./backend/app/api/kb/tags.py` | Список тегов (только используемые, отсортированные по имени). |
| `./backend/app/api/kb/permissions.py` | Управление ACL разделов и статей, переключение `inherit_permissions`, поиск subjects через Keycloak. |
| `./backend/app/api/kb/export_import.py` | Экспорт (MD, ZIP, vault.zip, PDF, DOCX) и импорт (одиночный MD, ZIP-vault с защитой от zip-bomb и path traversal, SAVEPOINT на каждую статью). |
| `./backend/app/api/kb/trash.py` | Корзина (admin): список soft-deleted статей с размерами файлов/медиа, восстановление, окончательное удаление одной статьи, bulk-очистка (всё / просроченные). |

### Сервисы

| Файл | Назначение |
|---|---|
| `./backend/app/services/kb_acl/_common.py` | Константы, ранг прав, ключи Redis, обёртки над `acl_base`. |
| `./backend/app/services/kb_acl/resolve.py` | Точечный резолв прав раздела/статьи с рекурсивным CTE и Redis-кэшем. |
| `./backend/app/services/kb_acl/visibility.py` | SQL push-down фильтрация видимости статей для `list_articles` (корректный `total`). |
| `./backend/app/services/kb_acl/invalidation.py` | Инвалидация кэша по поддереву разделов (рекурсивный CTE) и связанных статей. |
| `./backend/app/services/kb_acl/batch.py` | Batch-резолв прав списков разделов/статей (Redis MGET + один CTE-запрос на cache-miss). |
| `./backend/app/services/kb.py` | `record_article_view` (Redis SET NX EX для дедупликации), `set_article_tags`. |
| `./backend/app/services/kb_import.py` | Вспомогательные функции импорта статей и архивов. |
| `./backend/app/services/kb_export.py` | Вспомогательные функции экспорта статей (MD, ZIP, PDF, DOCX). |
| `./backend/app/services/kb_trash.py` | Hard-delete: `purge_article`, `purge_articles_bulk`, `purge_all_trash`, `purge_expired_articles`, `cleanup_orphan_dirs`, `remove_article_dirs`, `try_remove_empty_article_dir`. Все bulk-операции работают чанками `PURGE_BATCH_SIZE=100` (один DELETE+commit на чанк) с параллельным `rmtree` через `asyncio.Semaphore(8)`. |
| `./backend/app/services/kb_tree.py` | SQL-константы для обхода дерева разделов: `KB_SECTIONS_DESCENDANTS_SQL` (поддерево), `KB_SECTIONS_ANCESTORS_SQL` (предки). |
| `./backend/app/worker/tasks/kb.py` | Фоновые задачи `purge_kb_trash` (purge soft-deleted статей старше `kb_trash_retention_days`) и `cleanup_kb_orphan_dirs` (сироты на ФС). |

### Модели и схемы

- `./backend/app/models/kb.py` — SQLAlchemy ORM: `KbSection`, `KbSectionPermission`, `KbArticle`, `KbArticleVersion`, `KbArticlePermission`, `KbArticleTag`, `KbTag`, `KbArticleComment`, `KbSuggestion`, `KbArticleFeedback`, `KbArticleFile`.
- `./backend/app/schemas/kb.py` — Pydantic-схемы запросов/ответов, включая валидацию тегов (≤ 20 штук, ≤ 100 символов каждый).
- `./backend/app/schemas/kb_extra.py` — Pydantic-схемы для расширенного API: `PermissionEntry`, `SetPermissionRequest`, `InheritRequest`, `KbFilePublic`, `MediaUploadResponse`, `UserSearchResult`, `DiffResponse`, `ImportReport`.

### Frontend

| Файл | Назначение |
|---|---|
| `./frontend/src/pages/KbListPage.vue` | Список статей с деревом разделов и фильтрами. |
| `./frontend/src/pages/KbArticlePage.vue` | Просмотр статьи: тело, теги, комментарии, версии, вложения, фидбек. |
| `./frontend/src/pages/KbArticleFormPage.vue` | Форма создания/редактирования статьи: оркестрация (layout «контент + сайдбар настроек», inline-валидация, guard несохранённых изменений, восстановление черновика). |
| `./frontend/src/components/kb/article-form/ArticleMetaSection.vue` | Поле заголовка статьи (крупный инпут, автофокус в режиме создания, статус валидации). |
| `./frontend/src/components/kb/article-form/ArticleContentSection.vue` | Поле содержимого (RichEditor) со статусом валидации. |
| `./frontend/src/components/kb/article-form/ArticleSettingsSection.vue` | Карточка настроек в сайдбаре: статус, раздел, теги, комментарий к правке. |
| `./frontend/src/components/kb/article-form/ArticleAttachmentsSection.vue` | Карточка вложений в сайдбаре (обёртка над `KbAttachmentsPanel`, только в режиме редактирования). |
| `./frontend/src/pages/KbPlaceholderPage.vue` | Заглушка для ненастроенного раздела. |
| `./frontend/src/pages/KbTrashPage.vue` | Корзина базы знаний (admin): таблица soft-deleted статей с действиями Restore/Purge, bulk-очистка (всё/просроченные), ссылка на настройку retention. |
| `./frontend/src/components/KbSectionTree.vue` | Дерево разделов. |
| `./frontend/src/components/KbSectionFormModal.vue` | Модалка создания/редактирования раздела. |
| `./frontend/src/components/KbSectionMoveModal.vue` | Модалка перемещения раздела. |
| `./frontend/src/components/KbArticleCard.vue` | Карточка статьи в сетке. |
| `./frontend/src/components/KbArticleListRow.vue` | Строка статьи в табличном виде. |
| `./frontend/src/components/KbArticleHeader.vue` | Шапка статьи (хлебные крошки, статус, кнопки). |
| `./frontend/src/components/KbArticleVersionsTab.vue` | Вкладка истории версий. |
| `./frontend/src/components/KbVersionDiffModal.vue` | Модалка сравнения версий. |
| `./frontend/src/components/KbArticleCommentsTab.vue` | Вкладка комментариев. |
| `./frontend/src/components/KbArticleSuggestTab.vue` | Вкладка предложений правок. |
| `./frontend/src/components/KbArticleFeedback.vue` | Блок оценки «полезно / нет». |
| `./frontend/src/components/KbAttachmentsPanel.vue` | Панель вложений (загрузка кнопкой + drag-and-drop в карточку, dropzone-оверлей). |
| `./frontend/src/components/KbPermissionsModal.vue` | Модалка управления ACL. |
| `./frontend/src/components/KbImportModal.vue` | Модалка импорта MD/ZIP. |
| `./frontend/src/components/KbListToolbar.vue` | Тулбар списка статей. |
| `./frontend/src/components/KbListArticles.vue` | Компонент списка статей. |
| `./frontend/src/components/KbListPageActions.vue` | Действия на странице списка (создание, импорт). |
| `./frontend/src/components/KbListSidebar.vue` | Боковая панель списка (дерево разделов). |
| `./frontend/src/components/editor/extensions/index.ts` | Подключение расширений TipTap (Callout, Details, AlignedNodes, IframeEmbed). |
| `./frontend/src/components/editor/extensions/IframeEmbed.ts` | Расширение TipTap для iframe с белым списком доменов и строгим sandbox. |
| `./frontend/src/components/editor/extensions/Callout.ts` | Расширение «выноска». |
| `./frontend/src/components/editor/extensions/Details.ts` | Расширение сворачиваемый блок `<details>`. |
| `./frontend/src/components/editor/useEditorImageUpload.ts` | Загрузка картинок в редакторе. |
| `./frontend/src/components/editor/useEditorVideoDialog.ts` | Диалог вставки iframe/видео. |
| `./frontend/src/api/kb.ts` | REST-клиент; типы запросов генерируются из OpenAPI-схемы (`npm run gen:types`). |
| `./frontend/src/queries/kb.ts` | TanStack Query хуки (единый источник правды для кэша). |
| `./frontend/src/composables/useKbSections.ts` | Работа с деревом разделов. |
| `./frontend/src/composables/useKbArticleListing.ts` | Загрузка/пагинация/фильтрация списка статей (сброс страницы при смене фильтра). |
| `./frontend/src/composables/useKbArticleComments.ts` | Комментарии через TanStack Query. |
| `./frontend/src/composables/useKbArticleVersions.ts` | История версий через TanStack Query. |
| `./frontend/src/pages/composables/useArticleFormState.ts` | Состояние формы статьи: модель, опции статусов/разделов, локальный черновик (autosave в localStorage + восстановление). |

### Редактор статьи (UX формы)

`KbArticleFormPage.vue` — тонкий wiring-слой над под-компонентами `components/kb/article-form/*` (по конвенции «толстые страницы» из `AGENTS.md`):

- **Layout «контент + сайдбар».** CSS Grid (`.editor-layout`: `minmax(0,1fr)` + сайдбар ~320px, на узких экранах схлопывается в одну колонку). Слева — заголовок и содержимое (`.editor-main`), справа — карточки настроек и вложений (`.editor-aside`). Зеркалит раскладку формы новостей (`NewsFormPage.vue`).
  > ⚠️ Важно: для раскладки используется **обычный CSS Grid, а не `NGrid`/`NGi`**. `NGrid` рендерит только прямых детей с `type.__GRID_ITEM__ === true` и не «проваливается» в кастомные компоненты-обёртки — оборачивание `NGi` в свой компонент приводит к молчаливо пустой форме. Регрессионный тест — `kb-article-form-render.spec.ts` (монтируется с реальным Naive UI).
- **Inline-валидация обязательных полей.** `title`/`body` подсвечиваются (`validation-status="error"` + feedback) только после первой попытки сабмита (`showValidation`). `bodyInvalid` использует `isBodyEmpty()` (strip HTML).
- **Guard несохранённых изменений.** Грязное состояние отслеживает общий `useDirtyTracker` (`./frontend/src/composables/useDirtyTracker.ts`) — сравнивает snapshot формы с baseline (`markPristine()` после загрузки и перед навигацией после сохранения); диалог при уходе показывает общий `useFormLeaveGuard` (`./frontend/src/composables/useFormLeaveGuard.ts`, `onBeforeRouteLeave` + опциональный `beforeunload`), i18n-ключи `kb.leave.*`. Те же composables использует форма новостей (`NewsFormPage.vue`) и сортировка `/staff` (`useStaffLeaveGuard` — тонкая обёртка над `useFormLeaveGuard`). Отдельно `useArticleFormState` пишет локальный черновик по `beforeunload` (другая задача — восстановление, не предупреждение).
- **Автофокус** на поле заголовка в режиме создания (`ArticleMetaSection`, `autofocus`-проп).
- **Drag-and-drop вложений** в карточку «Прикреплённые файлы» (`KbAttachmentsPanel`) через общий `useFileDropzone` (`./frontend/src/composables/useFileDropzone.ts`, dropzone-оверлей + подсветка только при перетаскивании файлов), наряду с загрузкой кнопкой. На странице просмотра статьи (`KbArticlePage.vue`) панель монтируется в read-only (`:can-upload="false"`) — без загрузки и drag-and-drop.
- **Внутренний скролл редактора.** Высота тулбара/контента TipTap регулируется внутри `RichEditor.vue` (`.editor-content` `max-height: var(--editor-content-max-height, 60vh); overflow-y:auto`), чтобы тулбар не «уезжал» за экран на длинных статьях. `position:sticky` не используется: у `.n-layout` Naive UI всегда `overflow:hidden`, что ломает sticky при оконном скролле.

---

## 3. Модель данных

```
kb_sections
  id, parent_id, title, slug, description, sort_order,
  inherit_permissions, created_by, created_at, deleted_at
  UNIQUE (parent_id, slug)
  FK parent_id → kb_sections.id ON DELETE RESTRICT        -- ADR-010
  INDEX active (parent_id) WHERE deleted_at IS NULL

kb_section_permissions
  id, section_id, subject_type ('user'|'group'), subject_id, subject_name,
  permission ('viewer'|'editor'|'manager'), granted_by, created_at
  UNIQUE (section_id, subject_id)

kb_articles
  id, section_id, title (≤500), body (NOT NULL, default ''),
  inherit_permissions, body_tsvector (GIN, computed, russian_hunspell),
  status ('draft'|'published'|'archived'), version, view_count,
  created_by, updated_by, published_at, created_at, updated_at, deleted_at
  INDEX (section_id) WHERE deleted_at IS NULL
  INDEX GIN (body_tsvector)

kb_article_permissions
  id, article_id, subject_type, subject_id, subject_name,
  permission ('viewer'|'editor'|'manager'), granted_by, created_at
  UNIQUE (article_id, subject_id)

kb_article_versions
  id, article_id, version, title, body (NOT NULL),
  changed_by, change_comment, created_at
  UNIQUE (article_id, version)

kb_article_comments
  id, article_id, author_id, body, created_at, updated_at, deleted_at

kb_suggestions
  id, article_id, author_id, body, comment,
  status ('pending'|'approved'|'rejected'), reviewed_by, reviewed_at, created_at

kb_article_feedback
  id, article_id, user_id, is_helpful, created_at
  UNIQUE (article_id, user_id)

kb_tags            (id, name UNIQUE, slug UNIQUE)
kb_article_tags    (article_id, tag_id) -- M2M, UNIQUE (article_id, tag_id)
kb_article_files   (id, article_id, filename, original_name, size_bytes, mime_type, uploaded_by, created_at)
```

### Soft-delete и purge

`kb_sections.deleted_at` и `kb_articles.deleted_at` — мягкое удаление. Восстановление доступно только admin. Раздел нельзя удалить, если у него есть непустые дочерние разделы или активные статьи.

Hard-delete (purge) статьи:
- Эндпоинт `POST /kb/articles/{id}/purge` (admin) — `purge_article` в `./backend/app/services/kb_trash.py` удаляет запись (FK CASCADE приберёт `kb_article_files`, `kb_article_versions`, комментарии, suggestions, теги, фидбек) и удаляет каталоги вложений и медиа статьи с диска.
- Эндпоинт `POST /kb/trash/purge-all` — bulk-purge всей корзины или только просроченных статей. Под капотом `purge_all_trash` / `purge_expired_articles` из `./backend/app/services/kb_trash.py` идут чанками по 100 (один `DELETE … WHERE id IN (…)` + commit на чанк), затем параллельный `rmtree` каталогов с ограничением concurrency = 8. Не грузит весь список id в память.
- Фоновая задача `purge_kb_trash` в `./backend/app/worker/tasks/kb.py` (cron, ежедневно 04:30) — удаляет статьи с `deleted_at < now() - kb_trash_retention_days` (по умолчанию 30, настройка `kb_trash_retention_days` в `system_settings`, `0` — отключить). Использует тот же чанковый `purge_expired_articles` из `./backend/app/services/kb_trash.py`.
- Фоновая задача `cleanup_kb_orphan_dirs` в `./backend/app/worker/tasks/kb.py` (cron, ежедневно 04:45) — удаляет каталоги в `kb_files_dir` / `kb_media_dir`, для которых не существует записи статьи (даже soft-deleted). Корни приводятся к `Path.resolve()`, каждая entry дополнительно проверяется на принадлежность root — symlinks наружу пропускаются с warn-логом.
- При удалении единичного вложения (`DELETE /kb/articles/{id}/files/{file_id}`) пустой каталог статьи дочищается через `try_remove_empty_article_dir` в `./backend/app/services/kb_trash.py`.
- Restore и одиночный purge инвалидируют Redis-кэш ACL статьи (`invalidate_article_cache` из `./backend/app/services/kb_acl/invalidation.py`) — после возврата статьи из корзины пользователь сразу видит актуальные права раздела, а не отрабатывают устаревшие записи.

### Версии

Каждое обновление статьи (`PUT /kb/articles/{id}`) и автосохранение черновика (`PUT /kb/articles/{id}/draft`) атомарно создают снимок текущего состояния в `kb_article_versions` перед применением изменений. `body NOT NULL` — пустое тело хранится как пустая строка, а не NULL. Откат к текущей активной версии запрещён (400). Откат к архивной версии сам становится новой версией.

---

## 4. Модель прав (ACL)

### Уровни

`viewer < editor < manager`

- **viewer** — читать статьи и скачивать вложения.
- **editor** — создавать/редактировать статьи и разделы, загружать файлы.
- **manager** — полный контроль: права, удаление, восстановление.

### Алгоритм резолва (`./backend/app/services/kb_acl/resolve.py`)

Для раздела:
1. `user.role == 'admin'` → `manager`.
2. `section.created_by == user.id` → `manager`.
3. Кэш Redis `kb_acl:{user_id}:section:{section_id}` (TTL из `acl_base.ACL_TTL`).
4. Рекурсивный CTE: поднимаемся по `parent_id`, останавливаясь на разделах с `inherit_permissions = FALSE`; ищем запись в `kb_section_permissions` для любого `subject_id` пользователя (user-id + group-ids из Keycloak) — берём максимальный уровень.

Для статьи:
1. admin → `manager`.
2. `article.created_by == user.id` → `manager`.
3. Кэш Redis `kb_acl:{user_id}:article:{article_id}`.
4. Если `inherit_permissions = FALSE` — ищем в `kb_article_permissions`.
5. Если `inherit_permissions = TRUE` и статья прикреплена к разделу — резолв родительского раздела. Иначе — прямые права статьи.

### Batch-резолв

`batch_resolve_section_permissions` (используется в `GET /kb/sections` и экспорте): Redis MGET по всем ключам → один рекурсивный CTE-запрос на cache-miss секции → запись результатов через pipeline.

### Инвалидация кэша

`invalidate_section_cache(redis, section_id, db)` в `./backend/app/services/kb_acl/invalidation.py` — рекурсивный CTE по поддереву (`inherit_permissions = TRUE`), сканирует и удаляет `kb_acl:*:section:{id}` для каждого потомка, а также `kb_acl:*:article:{id}` для статей с `inherit_permissions = TRUE` в этих разделах. Вызывается при изменении прав, переносе раздела, смене флага `inherit_permissions`.

---

## 5. REST API

База: `/api/v1/kb`. Все эндпойнты требуют `CurrentUser`.

### Разделы

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/sections` | Полное дерево с фильтрацией по ACL. |
| POST | `/kb/sections` | Создать раздел (корневой — любой; вложенный — editor на родителя или admin); создатель → manager. |
| PUT | `/kb/sections/{id}` | Переименовать / описание / sort_order / переместить (editor). Инвалидирует кэш поддерева при переносе. |
| DELETE | `/kb/sections/{id}` | Soft-delete (manager). Запрещено при наличии дочерних разделов или статей. |
| GET | `/kb/sections/{id}/permissions` | Список ACL раздела (manager). |
| POST | `/kb/sections/{id}/permissions` | Выдать право (manager). Upsert по `(section_id, subject_id)`. |
| DELETE | `/kb/sections/{id}/permissions/{subject_id}` | Отозвать право (manager). |
| PATCH | `/kb/sections/{id}/inherit` | Переключить `inherit_permissions`; при отключении копирует права родителя; инвалидирует всё поддерево. |
| GET | `/kb/sections/{id}/export/zip` | Экспортировать раздел в ZIP-архив (vault-формат). |
| GET | `/kb/export/vault.zip` | Полный экспорт всех доступных разделов. |

### Статьи

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/articles` | Список с пагинацией (`limit` ≤ 100), фильтр по section, tag, status, q (FTS). Поддерживает `Idempotency-Key` при POST. |
| POST | `/kb/articles` | Создать статью (`draft` или `published`). Теги ≤ 20. |
| GET | `/kb/articles/{id}` | Метаданные + тело + breadcrumbs + фидбек-счётчики. Инкрементит `view_count` (дедупликация через Redis SET NX EX). |
| PUT | `/kb/articles/{id}` | Обновить (оптимистичная блокировка по `version`). `section_id` принимает `null` — статья выходит из раздела. |
| PUT | `/kb/articles/{id}/draft` | Автосохранение черновика (проверяет `version`, создаёт снимок). |
| DELETE | `/kb/articles/{id}` | Soft-delete (автор или admin). |
| POST | `/kb/articles/{id}/purge` | Полное удаление статьи (admin): запись из БД (cascade на версии/комментарии/файловые метаданные) + удаление каталогов `kb_files_dir/<id>` и `kb_media_dir/<id>` с диска. |
| POST | `/kb/articles/{id}/restore` | Восстановить (admin). |
| GET | `/kb/articles/{id}/permissions` | ACL статьи (manager). |
| POST | `/kb/articles/{id}/permissions` | Выдать право (manager). |
| DELETE | `/kb/articles/{id}/permissions/{subject_id}` | Отозвать (manager). |
| PATCH | `/kb/articles/{id}/inherit` | Переключить `inherit_permissions`; при отключении копирует права раздела. |
| GET | `/kb/articles/{id}/export/md` | Экспорт в Markdown с YAML front-matter. |
| GET | `/kb/articles/{id}/export/pdf` | Экспорт в PDF (Playwright/Chromium — ADR-006). |
| GET | `/kb/articles/{id}/export/docx` | Экспорт в DOCX. |

### Корзина (admin)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/trash/articles` | Список soft-deleted статей (пагинация) с заголовками разделов, авторами, числом и суммарным размером вложений (из `kb_article_files`) и счётчиком просроченных по retention. Размер inline-медиа в листинге не считается. |
| POST | `/kb/trash/articles/{id}/restore` | Восстановить статью из корзины. |
| POST | `/kb/trash/articles/{id}/purge` | Полное удаление одной статьи из корзины (БД cascade + удаление каталогов с диска). |
| POST | `/kb/trash/purge-all?older_than_days=` | Bulk-очистка чанками по 100 (БД + диск, параллельный `rmtree`): без параметра — удалить ВСЕ статьи из корзины; с параметром — только те, у которых `deleted_at < now() - older_than_days`. Возвращает `{ purged: N }`. |

### Версии

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/articles/{id}/versions` | Список версий — только метаданные, `body` не возвращается (отложена через `defer`). Пагинация. |
| GET | `/kb/articles/{id}/versions/{n}` | Детали версии с телом (`body`). |
| POST | `/kb/articles/{id}/versions/{n}/restore` | Откат к версии N (создаёт новую версию). Откат к текущей версии запрещён (400). |
| GET | `/kb/articles/{id}/versions/{v1}/diff/{v2}` | Unified diff двух версий. Лимит 500 000 символов каждая; вычисление в `run_in_executor`. |

### Комментарии, предложения правок, фидбек

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/articles/{id}/comments` | Список комментариев (viewer). |
| POST | `/kb/articles/{id}/comments` | Добавить комментарий (viewer). |
| DELETE | `/kb/articles/{id}/comments/{comment_id}` | Удалить (автор или manager). |
| POST | `/kb/articles/{id}/suggest` | Предложить правку (viewer). |
| GET | `/kb/articles/{id}/suggestions` | Список предложений правок (editor). |
| POST | `/kb/suggestions/{suggestion_id}/review` | Принять/отклонить правку (editor). |
| POST | `/kb/articles/{id}/feedback` | Оценить статью (viewer). Upsert по `(article_id, user_id)`. |

### Вложения и медиа

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/articles/{id}/files` | Список вложений (viewer). |
| POST | `/kb/articles/{id}/files` | Загрузить файл (editor). MIME проверяется по белому списку. |
| DELETE | `/kb/articles/{id}/files/{file_id}` | Удалить (автор загрузки, editor или admin). |
| GET | `/kb/files/{article_id}/{filename}` | Скачать через `X-Accel-Redirect`. Аудит через Redis SET NX EX 300. |
| POST | `/kb/articles/{id}/media` | Загрузить inline-картинку (editor). Проверка расширения (.jpg/.jpeg/.png/.gif/.webp) и MIME. |
| GET | `/kb/media/{article_id}/{filename}` | Раздать через `X-Accel-Redirect`. |

### Теги, поиск subjects

| Метод | Путь | Описание |
|---|---|---|
| GET | `/kb/tags` | Список используемых тегов. |
| GET | `/kb/users/search?q=` | Поиск subjects для ACL (Keycloak users + groups + системная группа «Все пользователи»). |

### Импорт

| Метод | Путь | Описание |
|---|---|---|
| POST | `/kb/articles/import` | Импортировать одиночный `.md`-файл (стратегия: `skip`/`overwrite`/`create_new`). |
| POST | `/kb/import/vault` | Импортировать ZIP-архив (≤ 1000 файлов; распакованный размер ≤ 5× лимита; проверка path traversal; SAVEPOINT на каждую статью). |

---

## 6. Хранилище файлов

Пути определяются конфигурацией (`./backend/app/core/config.py`), не хардкодом:

```
{kb_files_dir}/{article_id}/{uuid_prefix}_{safe_name}   -- вложения
{kb_media_dir}/{article_id}/{uuid_prefix}_{safe_name}   -- inline-медиа
```

Оба каталога раздаются через `X-Accel-Redirect`:
- `/internal/kb-files/{article_id}/{filename}` — вложения.
- `/internal/kb-media/{article_id}/{filename}` — медиа.

Заголовок `X-Content-Type-Options: nosniff` выставляется для обоих видов файлов.

Для медиа MIME-тип определяется по расширению файла (`.jpg`/`.jpeg` → `image/jpeg`, `.png`, `.gif`, `.webp`), а не по заголовку запроса.

---

## Безопасность

**Заголовок статьи.** При создании (`POST`), обновлении (`PUT`) и автосохранении (`PUT /draft`) заголовок одинаково обрабатывается через `clean_title()` в `./backend/app/core/sanitize.py` — text-only, весь HTML удаляется.

**Тело статьи.** Хранится как Markdown (ADR-008), перед записью проходит `sanitize_markdown()` в `./backend/app/core/sanitize.py`.

**iframe в редакторе.** `./frontend/src/components/editor/extensions/IframeEmbed.ts` ограничивает список разрешённых доменов (YouTube, Rutube, корпоративные хостинги) и устанавливает строгий атрибут `sandbox`.

**Теги.** Валидация в `./backend/app/schemas/kb.py`: не более 20 тегов на статью, каждый — не длиннее 100 символов. Проверяется при создании и обновлении статьи, а также при ZIP-импорте.

**Вложения (MIME white-list).** `./backend/app/api/kb/attachments.py` содержит `SAFE_MIME_TYPES` (изображения, документы, архивы, JSON). Если определённый тип не входит в список, сохраняется `application/octet-stream`.

**Inline-медиа.** `./backend/app/api/kb/media.py`: двойная проверка — расширение файла (`.jpg`/`.jpeg`/`.png`/`.gif`/`.webp`) и MIME (`ALLOWED_IMAGE_MIMES`). Несоответствие → 400.

**ZIP-импорт (`./backend/app/api/kb/export_import.py`).**
- Лимит файлов в архиве: 1 000.
- Лимит распакованного размера: 5 × `kb_import_max_size_mb` (защита от zip-bomb).
- Проверка каждого имени файла: отклоняются абсолютные пути, `..`, `\`, управляющие символы.
- Каждая статья обрабатывается в `async with db.begin_nested()` (SAVEPOINT); ошибка в одной статье не откатывает остальные.

**Аудит скачиваний.** В `./backend/app/api/kb/attachments.py` событие `kb.file_download` записывается не чаще одного раза в 5 минут на пользователя на файл: `redis.set(key, "1", ex=300, nx=True)`.

**Просмотры статей.** `record_article_view` в `./backend/app/services/kb.py` использует `redis.set(view_key, "1", ex=VIEW_DEDUP_TTL_SECONDS, nx=True)` — счётчик атомарно инкрементируется только при первом визите за период.

---

## События аудита

| Событие | Эмиттер |
|---|---|
| `kb.article_created` | `POST /kb/articles` |
| `kb.article_updated` | `PUT /kb/articles/{id}` |
| `kb.article_deleted` | `DELETE /kb/articles/{id}` |
| `kb.article_purged` | `POST /kb/articles/{id}/purge`, `POST /kb/trash/articles/{id}/purge` |
| `kb.article_restored` | `POST /kb/trash/articles/{id}/restore` |
| `kb.trash_purged` | `POST /kb/trash/purge-all` |
| `kb.section_deleted` | `DELETE /kb/sections/{id}` |
| `kb.permission_grant` | `POST /kb/sections/{id}/permissions`, `POST /kb/articles/{id}/permissions` |
| `kb.permission_revoke` | `DELETE /kb/sections/{id}/permissions/{subject_id}`, `DELETE /kb/articles/{id}/permissions/{subject_id}` |
| `kb.file_upload` | `POST /kb/articles/{id}/files` |
| `kb.file_download` | `GET /kb/files/{article_id}/{filename}` (агрегация через Redis SET NX EX 300) |
| `kb.article_exported_md` | `GET /kb/articles/{id}/export/md` |
| `kb.article_exported_pdf` | `GET /kb/articles/{id}/export/pdf` |
| `kb.article_exported_docx` | `GET /kb/articles/{id}/export/docx` |

---

## Тесты

### Backend (`./backend/tests/`)

- `./backend/tests/unit/test_kb_acl.py` — резолв прав, рекурсивный CTE, Redis-кэш, сброс кэша по поддереву.
- `./backend/tests/unit/test_kb_articles.py` — CRUD статей, оптимистичная блокировка (409), параллельное редактирование.
- `./backend/tests/unit/test_kb_versions.py` — история версий, откат, откат к версии с пустым телом, запрет отката к текущей.
- `./backend/tests/unit/test_kb_export_import.py` — импорт MD, ZIP с zip-bomb, path traversal, «битый» YAML.
- `./backend/tests/unit/test_kb_sections.py` — дерево разделов, soft-delete, RESTRICT при наличии дочерних.
- `./backend/tests/unit/test_kb_comments_suggestions.py` — комментарии, предложения правок, рецензирование.
- `./backend/tests/unit/test_kb_service.py` — `record_article_view`, `set_article_tags`.
- `./backend/tests/unit/test_kb_markdown.py` — sanitize, clean_title.
- `./backend/tests/unit/test_kb_attachments.py` — загрузка, список, удаление вложений, MIME white-list.
- `./backend/tests/unit/test_kb_permissions.py` — управление ACL разделов и статей.
- `./backend/tests/unit/test_kb_tags.py` — список тегов.
- `./backend/tests/unit/test_kb_trash.py` — корзина: список, restore, purge.
- `./backend/tests/unit/test_kb_worker_tasks.py` — Тесты фоновых задач `purge_kb_trash` и `cleanup_kb_orphan_dirs`.
- `./backend/tests/integration/test_kb_acl_integration.py` — сброс кэша при изменении наследования прав.
- `./backend/tests/integration/test_kb_media_integration.py` — загрузка и раздача медиа.
- `./backend/tests/integration/test_kb_search.py` — полнотекстовый поиск (FTS).
- `./backend/tests/integration/test_kb_trash_service.py` — bulk-purge, cleanup_orphan_dirs.

### Frontend (`./frontend/tests/`)

- `./frontend/tests/unit/kb-api.spec.ts` — REST-клиент.
- `./frontend/tests/unit/kb-article-form-page.spec.ts` — форма создания/редактирования статьи (валидация, guard несохранённых изменений, сабмит).
- `./frontend/tests/unit/kb-article-form-render.spec.ts` — регрессия: форма реально рендерит поля при монтировании с настоящим Naive UI (защита от «NGrid проглатывает кастомные секции»).
- `./frontend/tests/unit/queries-kb.spec.ts` — TanStack Query хуки.
- `./frontend/tests/unit/kb-components-smoke.spec.ts` — smoke-тест компонентов.
- `./frontend/tests/unit/kb-list-page.spec.ts` — тесты страницы списка статей.
- `./frontend/tests/e2e/kb-acl.spec.ts` — сценарии прав доступа.
- `./frontend/tests/e2e/kb-media.spec.ts` — загрузка и просмотр медиа.

---

## Связанные документы

- ADR-005, ADR-006, ADR-008, ADR-009, ADR-010 — см. `./docs/adr.md`.
- API-контракты — см. `./docs/api-contracts.md` (раздел `/kb`).
- Схема БД — см. `./docs/db-schema.md` (таблицы `kb_*`).
- Матрица ролей — см. `./docs/roles-matrix.md` (раздел KB).
- Тестирование — см. `./docs/testing.md`.
- История рефакторинга — см. `./kb-ref.md`.
