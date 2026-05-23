# Модуль «Фотогалерея»

> Собственный модуль портала. Иерархия папок с per-folder ACL (viewer / uploader / manager), хранение оригиналов на локальной ФС, метаданные в PostgreSQL, миниатюры (WebP + AVIF) генерируются в фоне через ARQ-воркер.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/photos/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/photos/`, `./frontend/src/components/photos/`) |
| Воркер | ARQ (`./backend/app/worker/tasks/photos/`) |
| Хранилище | Локальная ФС под `/data/photos/{originals,thumbs,zips,import}` |
| Раздача файлов | nginx `X-Accel-Redirect` (internal locations) |
| ACL-кэш | Redis, версионированные ключи `photo_acl:{user_id}:{folder_id}:v{N}` + счётчик `photo_acl_ver:{folder_id}` |
| Связанные ADR | ADR-030 (модель данных), ADR-031 (воркер и thumbnails) |

### Возможности

- Дерево папок неограниченной вложенности с soft-delete и корзиной.
- Гранулярные права на папку (viewer / uploader / manager) с наследованием от родителя; subject = `user` или `group` (Keycloak).
- Загрузка одиночная и пакетная, drag-and-drop, очередь загрузки, EXIF-парсинг, опциональный strip GPS.
- Bulk-операции (move / delete / restore / tag).
- Теги (управляются глобально, привязка many-to-many).
- Публичные ссылки на отдельное фото и на папку (с TTL).
- ZIP-выгрузка папки через фоновую задачу.
- Сканирование импорт-директории `/data/photos/import` для массового импорта без upload.
- Thumbnails 5 размеров (200/400/600/1000/1600), формат WebP + опционально AVIF.

---

## 2. Структура кода

### Backend (`./backend/app/api/photos/`)

| Файл | Назначение |
|---|---|
| `./backend/app/api/photos/__init__.py` | Сборка `photos_router` из подроутеров. |
| `./backend/app/api/photos/_common.py` | Общие хелперы (`_folder_to_public`, `_photo_to_public`, `_would_create_cycle`, `_enqueue_processing`, `_module_settings`, логгер). |
| `./backend/app/api/photos/folders.py` | CRUD дерева папок, tree-эндпойнт, soft-delete/restore. |
| `./backend/app/api/photos/folder_repo.py` | DB-репозиторий для папок: выборки, рекурсивные CTE, soft-delete. |
| `./backend/app/api/photos/folder_service.py` | Сервисный слой папок (валидация, права, инвалидация ACL-кэша). |
| `./backend/app/api/photos/photos.py` | CRUD фото, upload, корзина, восстановление, purge, bulk-операции. |
| `./backend/app/api/photos/photo_repo.py` | DB-репозиторий для фото (выборки с пагинацией, deleted, recent, storage stats). |
| `./backend/app/api/photos/photo_service.py` | Сервисный слой фото (загрузка, удаление, восстановление, bulk, recent). |
| `./backend/app/api/photos/thumbnails.py` | Раздача thumbnails (WebP/AVIF) и оригиналов через `X-Accel-Redirect`. |
| `./backend/app/api/photos/sharing.py` | Public-ссылки: создание/отзыв токенов, публичные эндпойнты просмотра и скачивания. |
| `./backend/app/api/photos/permissions.py` | Управление ACL папки + поиск subjects (users/groups) через Keycloak. |
| `./backend/app/api/photos/tags.py` | CRUD тегов + назначение тегов на фото. |
| `./backend/app/api/photos/zip_jobs.py` | Постановка ZIP-задач и выдача готовых архивов. |
| `./backend/app/api/photos/import_scan.py` | Постановка задач сканирования импорт-директории. |

### Сервисы

| Файл | Назначение |
|---|---|
| `./backend/app/services/photos_storage.py` | Работа с ФС: пути, sanitize filename, EXIF, генерация thumbnails (WebP+AVIF), удаление файлов. |
| `./backend/app/services/photos_acl.py` | Резолв прав по папке/фото с рекурсивным CTE, кэширование в Redis, инвалидация. |

### Модели и схемы

- `./backend/app/models/photos.py` — SQLAlchemy ORM: `PhotoFolder`, `PhotoFolderPermission`, `Photo`, `PhotoZipJob`, `PhotoShareToken`, `PhotoTag`, `PhotoTagAssignment`, `PhotoFolderShareToken`.
- `./backend/app/schemas/photos.py` — Pydantic-схемы запросов/ответов.

### Воркер (`./backend/app/worker/tasks/photos/`)

| Файл | Задачи |
|---|---|
| `./backend/app/worker/tasks/photos/processing.py` | `process_photo_upload` — извлечение EXIF, генерация thumbnails, выставление `processed=true`. |
| `./backend/app/worker/tasks/photos/zip_jobs.py` | `build_zip_job` — упаковка папки в ZIP. |
| `./backend/app/worker/tasks/photos/import_scan.py` | `import_scan_job` — сканирование `/data/photos/import`. |
| `./backend/app/worker/tasks/photos/cleanup.py` | `empty_photo_trash` — окончательное удаление soft-deleted фото и истёкших ZIP-архивов. |

### Frontend

| Файл | Назначение |
|---|---|
| `./frontend/src/pages/photos/PhotosIndexPage.vue` | Главная страница галереи (дерево + сетка фото + lightbox). |
| `./frontend/src/pages/photos/MySharesPage.vue` | Список собственных public-ссылок. |
| `./frontend/src/pages/photos/PublicPhotoPage.vue` | Публичный просмотр одного фото по токену. |
| `./frontend/src/pages/photos/PublicFolderPage.vue` | Публичный просмотр папки по токену. |
| `./frontend/src/components/photos/PhotosSidebar.vue` | Дерево папок. |
| `./frontend/src/components/photos/FolderNode.vue` | Узел дерева. |
| `./frontend/src/components/photos/PhotosFolderHeader.vue` | Заголовок текущей папки + действия. |
| `./frontend/src/components/photos/PhotosGrid.vue` | Сетка миниатюр с пагинацией и выбором. |
| `./frontend/src/components/photos/PhotosUploadQueue.vue` | Очередь загрузки с прогрессом. |
| `./frontend/src/components/photos/LightboxModal.vue` | Просмотр фото full-screen, навигация, share. |
| `./frontend/src/components/photos/PhotoPermissionsModal.vue` | Модалка управления ACL папки. |
| `./frontend/src/components/photos/PhotoTrashView.vue` | Просмотр корзины. |
| `./frontend/src/api/photos.ts` | Тонкий клиент REST API. |
| `./frontend/src/stores/photos.ts` | Pinia-стор с состоянием дерева и выбора. |
| `./frontend/src/composables/usePhotoListing.ts` | Загрузка/пагинация фото в текущей папке. |
| `./frontend/src/composables/usePhotoUpload.ts` | Очередь и upload через `XMLHttpRequest`. |
| `./frontend/src/composables/usePhotoSelection.ts` | Множественный выбор. |
| `./frontend/src/composables/usePhotoFolderActions.ts` | Действия над папкой (create/rename/delete/move). |
| `./frontend/src/composables/usePhotoFolderSelection.ts` | Состояние выбранной папки. |
| `./frontend/src/composables/useLightboxPhotoTags.ts` | Теги в lightbox. |
| `./frontend/src/composables/useLightboxShare.ts` | Создание public-ссылок из lightbox. |

---

## 3. Модель данных

```
photo_folders
  id, parent_id, name, slug, path, fs_path, description,
  cover_photo_id, created_by, created_at, updated_at, deleted_at
  UNIQUE (parent_id, slug)
  INDEX active (parent_id) WHERE deleted_at IS NULL

photo_folder_permissions
  id, folder_id, subject_type ('user'|'group'), subject_id, subject_name,
  permission ('viewer'|'uploader'|'manager'), granted_by, created_at
  UNIQUE (folder_id, subject_id)

photos
  id, folder_id, filename, original_name, size_bytes, mime_type,
  width, height, taken_at, exif (jsonb), description,
  inherit_permissions, processed, uploaded_by, created_at, deleted_at
  INDEX (folder_id, created_at DESC)
  INDEX (taken_at DESC NULLS LAST)
  INDEX active (folder_id) WHERE deleted_at IS NULL

photo_zip_jobs        (id, folder_id, user_id, status, file_path, error, created_at, expires_at)
photo_share_tokens    (id, photo_id, token, created_by, created_at, expires_at, revoked_at)
photo_folder_share_tokens (id, folder_id, token, created_by, created_at, expires_at, revoked_at)
photo_tags            (id, name UNIQUE, slug UNIQUE, created_at)
photo_tag_assignments (photo_id, tag_id) -- M2M
```

### Soft-delete

- `photo_folders.deleted_at` и `photos.deleted_at` — мягкое удаление.
- Корзина: окно 30 дней (см. `photo_service.list_deleted_photos`).
- Окончательное удаление: `POST /photos/trash/empty` ставит задачу `empty_photo_trash`, физически удаляющую файлы и строки.

---

## 4. ACL

### Уровни

`viewer < uploader < manager`

- **viewer** — может видеть содержимое папки и скачивать.
- **uploader** — может загружать, удалять/восстанавливать свои фото.
- **manager** — полный контроль папкой, в т.ч. правами и удалением.

### Алгоритм резолва (`./backend/app/services/photos_acl.py`)

Для папки:
1. `user.role == 'admin'` → `manager`.
2. `folder.created_by == user.id` → `manager`.
3. Версия папки: читаем `photo_acl_ver:{folder_id}` (если отсутствует — `0`).
4. Кэш Redis `photo_acl:{user_id}:{folder_id}:v{N}` (TTL по умолчанию). При изменении прав счётчик инкрементится — старые ключи автоматически "протухают" и не используются (отдельный invalidate не нужен, TTL подчистит).
5. Рекурсивный CTE: поднимаемся по `parent_id` до корня, ищем запись в `photo_folder_permissions` для любого `subject_id` пользователя (user-id + group-ids из Keycloak) — берём максимальный уровень.

Для фото:
1. admin → `manager`.
2. `uploaded_by == user.id` → `manager`.
3. Иначе резолв прав родительской папки.

### Инвалидация кэша

- При изменении прав папки / move / soft-delete — `invalidate_folder_cache(redis, folder_id, db)` инкрементит `photo_acl_ver:{folder_id}` и аналогичные ключи всех потомков (рекурсивный CTE по `deleted_at IS NULL`). Одного вызова на корневой `folder_id` достаточно.
- При изменении состава групп пользователя — `invalidate_user_cache(redis, user_id)` удаляет все `photo_acl:{user_id}:*` ключи (вызывается из Keycloak-sync).

---

## 5. REST API

База: `/api/v1/photos`. Все требуют `CurrentUser`, кроме `/public/*` и `/public-folder/*`.

### Папки

| Метод | Путь | Описание |
|---|---|---|
| GET | `/folders/tree` | Полное дерево с правами текущего пользователя. |
| GET | `/folders/deleted` | Soft-deleted папки (manager+). |
| GET | `/folders/{folder_id}` | Деталь папки. |
| POST | `/folders` | Создать (uploader на родителя или admin). |
| PATCH | `/folders/{folder_id}` | Переименовать / описание / cover / move (manager). |
| DELETE | `/folders/{folder_id}` | Soft-delete (manager). |
| POST | `/folders/{folder_id}/restore` | Восстановить. |

### Фото

| Метод | Путь | Описание |
|---|---|---|
| GET | `/folders/{folder_id}/photos` | Пагинированный список (`page`, `per_page` ≤ 200). |
| GET | `/deleted` | Удалённые (с учётом прав). |
| GET | `/recent` | Лента последних доступных фото для виджета. |
| GET | `/storage-stats` | Топ папок по объёму (admin). |
| GET | `/{photo_id}` | Метаданные. |
| PATCH | `/{photo_id}` | Описание / folder (move). |
| DELETE | `/{photo_id}` | Soft-delete. |
| POST | `/{photo_id}/restore` | Восстановить. |
| DELETE | `/{photo_id}/purge` | Физическое удаление (admin / автор после soft-delete). |
| POST | `/trash/empty` | Очистить корзину (admin). Возвращает 202 + `{"status":"queued"}`. |
| POST | `/bulk` | Bulk-операции (move/delete/restore/tag). |
| POST | `/folders/{folder_id}/upload` | Загрузка файлов (multipart, rate-limit 60/min). |

### Thumbnails и оригиналы

| Метод | Путь | Описание |
|---|---|---|
| GET | `/thumbnail/{photo_id}/{size}?format=webp\|avif` | Размер ∈ `{200,400,600,1000,1600}`. |
| GET | `/original/{photo_id}?download=0\|1` | Раздача через `X-Accel-Redirect`. |

### Sharing (public)

| Метод | Путь | Описание |
|---|---|---|
| POST | `/{photo_id}/share` | Создать токен на фото (TTL в днях). |
| POST | `/folders/{folder_id}/share` | Создать токен на папку. |
| GET | `/folders/{folder_id}/shares` | Активные токены папки. |
| GET | `/my-shares` | Свои токены: `{photo_tokens, folder_tokens}`. |
| DELETE | `/my-shares/photo/{token_id}` | Отзыв. |
| DELETE | `/my-shares/folder/{token_id}` | Отзыв. |
| GET | `/public/{token}/info` | Метаданные фото. |
| GET | `/public/{token}/thumbnail/{size}?format=webp\|avif` | Thumb. |
| GET | `/public/{token}/file?download=0\|1` | Оригинал. |
| GET | `/public-folder/{token}/info` | Метаданные папки. |
| GET | `/public-folder/{token}/photos` | Пагинированный список. |
| GET | `/public-folder/{token}/thumbnail/{photo_id}/{size}?format=webp\|avif` | Thumb. |

### Права

| Метод | Путь | Описание |
|---|---|---|
| GET | `/users/search?q=` | Поиск subjects (Keycloak users + groups). |
| GET | `/folders/{folder_id}/permissions` | Список ACL папки. |
| POST | `/folders/{folder_id}/permissions` | Дать право (manager). |
| DELETE | `/folders/{folder_id}/permissions/{subject_id}` | Отозвать. |

### Теги

| Метод | Путь |
|---|---|
| GET | `/tags` |
| POST | `/tags` |
| DELETE | `/tags/{tag_id}` |
| GET | `/{photo_id}/tags` |
| PATCH | `/{photo_id}/tags` |

### ZIP и импорт

| Метод | Путь | Описание |
|---|---|---|
| POST | `/folders/{folder_id}/zip` | Постановка ZIP-задачи. |
| GET | `/zip-jobs/{job_id}` | Статус. |
| GET | `/zip-jobs/{job_id}/download` | Скачать готовый ZIP (`X-Accel-Redirect`). |
| POST | `/import/scan` | Сканировать `/data/photos/import` (admin). |
| GET | `/import/scan/status/{job_id}` | Статус задачи импорта. |

---

## 6. Хранилище ФС

Корни (см. `./backend/app/services/photos_storage.py`):

```
/data/photos/
  originals/{fs_path}/{filename}      — исходные файлы
  thumbs/{photo_id}/{size}.webp       — миниатюры WebP (200/400/600/1000/1600)
  thumbs/{photo_id}/{size}.avif       — миниатюры AVIF (опционально)
  import/                             — drop-зона для массового импорта
  zips/{job_id}.zip                   — готовые архивы
```

### Sanitize и валидация

- `sanitize_filename()` — NFKD + ASCII only, `_SAFE_NAME` для остальных символов, длина ≤ 180 (sha256-суффикс).
- `_ALLOWED_EXT`: `jpg, jpeg, png, webp, heic, heif, gif, tif, tiff`.
- Path validation — все операции проверяются на принадлежность `_ALLOWED_ROOTS`.

### Thumbnails

- Константа `THUMB_SIZES = (200, 400, 600, 1000, 1600)` — единственный источник правды. Используется и в `thumbnails.py`, и в `sharing.py`.
- Качество WebP/AVIF: `THUMB_QUALITY = 85`.
- Генерация — синхронный код в потоке через `asyncio.to_thread` либо в ARQ-задаче `process_photo_upload`.
- Fallback в эндпойнтах: если thumb отсутствует — генерируется on-the-fly и помечается `processed=true`.

### nginx

Раздача через `X-Accel-Redirect` на внутренние локации:

```
/internal/photos-originals/...
/internal/photos-thumbs/...
/internal/photos-zips/...
```

---

## 7. Воркер

ARQ-задачи (`./backend/app/worker/tasks/photos/`):

| Задача | Триггер | Действие |
|---|---|---|
| `process_photo_upload` | После upload | EXIF (опц. strip GPS), thumbnails (WebP+AVIF), `processed=true`. |
| `build_zip_job` | `POST /folders/{id}/zip` | Стримит ZIP в `/data/photos/zips/{job_id}.zip`. |
| `import_scan_job` | `POST /import/scan` | Импорт из `/data/photos/import` в указанную папку. |
| `empty_photo_trash` | `POST /trash/empty` | Удаляет файлы и строки soft-deleted фото + просроченные ZIP. |

Аудит-события (`./backend/app/services/audit.py`) публикуются для ключевых операций. Формат имени — `photos.<resource>_<action>`:

| Событие | Эмиттер |
|---|---|
| `photos.photo_uploaded` | `photo_service.perform_upload` |
| `photos.photo_deleted` | `DELETE /photos/{id}` |
| `photos.photo_restored` | `POST /photos/{id}/restore` |
| `photos.photo_purged` | `DELETE /photos/{id}/purge` |
| `photos.trash_empty_requested` | `POST /photos/trash/empty` |
| `photos.trash_emptied` | worker `empty_photo_trash` |
| `photos.folder_created` | `POST /photos/folders` |
| `photos.folder_deleted` | `DELETE /photos/folders/{id}` |
| `photos.folder_restored` | `POST /photos/folders/{id}/restore` |
| `photos.folder_purged` | `DELETE /photos/folders/{id}/purge` |
| `photos.share_created` | `POST /photos/{id}/share` |
| `photos.share_revoked` | `DELETE /photos/my-shares/photo/{token_id}` |
| `photos.folder_share_created` | `POST /photos/folders/{id}/share` |
| `photos.folder_share_revoked` | `DELETE /photos/my-shares/folder/{token_id}` |
| `photos.permission_granted` | `POST /photos/folders/{id}/permissions` |
| `photos.permission_revoked` | `DELETE /photos/folders/{id}/permissions/{subject_id}` |

---

## 8. Конфигурация модуля

`PhotosModuleSettings` (`./backend/app/core/modules_config.py:42`):

| Поле | По умолчанию | Описание |
|---|---|---|
| `enabled` | `True` | Включает модуль и его UI. |
| `widget_limit` | `8` | Размер ленты `/recent` для дашборда. |
| `max_size_mb` | `50` | Лимит размера одного файла. |
| `allowed_mime` | `image/jpeg,png,webp,heic,heif,gif` | Допустимые MIME при upload. |
| `strip_gps` | `True` | Удалять GPS из EXIF при upload. |

Управление: `Администрирование → Система → Модули → Фотогалерея`. Тумблер сохраняет `photos.enabled` в `modules.json`.

### Видимость пункта меню в сайдбаре

Логика в `./frontend/src/composables/useAppMenu.ts:110`:

```
Показывать «Фотогалерея», если:
  modulesStore.isEnabled('photos')                                — внутренний модуль включён, или
  photoGalleryMode === 'internal'                                 — legacy-режим internal, или
  photoGalleryMode === 'external' && photoGalleryUrl              — legacy-режим external со ссылкой
```

При включённом модуле клик ведёт на внутренний `ROUTES.PHOTOS` (`./frontend/src/composables/useAppMenu.ts:155`).

> **Историческая заметка.** Поля `photo_gallery_url` / `photo_gallery_mode` / `photo_gallery_new_tab` в `system_settings` существуют для совместимости с внешними галереями (например, размещённая отдельно фотогалерея). Эти настройки **не связаны** с тумблером модуля — они задают альтернативный таргет пункта меню. При включённом собственном модуле они игнорируются.

---

## 9. Тесты

### Backend (`./backend/tests/api/`, `./backend/tests/worker/`)

- `test_photos_acl.py`
- `test_photos_folders.py`
- `test_photos_sharing.py`
- `test_photos_thumbnails.py`
- `test_photos_zip_jobs.py`
- `tests/worker/test_photos_tasks.py`

### Frontend (`./frontend/src/__tests__/`, `./frontend/tests/e2e/`)

- Unit: composables (`usePhotoUpload`, `usePhotoListing`, `usePhotoSelection`), `PhotosGrid.spec.ts`.
- E2E: `photos.spec.ts` — сценарий загрузки, просмотра, share, удаления.

---

## 10. Связанные документы

- ADR-030, ADR-031 — см. `./docs/adr.md`.
- API-контракты — см. `./docs/api-contracts.md` (раздел `/photos`).
- Схема БД — см. `./docs/db-schema.md`.
- Матрица ролей — см. `./docs/roles-matrix.md`.
