# Модуль «Фотогалерея»

> **Когда читать:** фото/папки, per-folder ACL, миниатюры WebP/AVIF, ZIP, корзина, SSE.
> **Ключевой код:** `app/api/photos/`, `app/services/photos_*.py`, `app/models/photos.py`, `frontend/src/pages/photos/`.
> **ADR:** 030, 031.

> Собственный модуль портала. Иерархия папок с per-folder ACL (viewer / uploader / manager), хранение оригиналов на локальной ФС, метаданные в PostgreSQL, миниатюры (WebP + AVIF) и blurhash-плейсхолдеры генерируются в фоне через ARQ-воркер. Готовность фото пушится клиенту по SSE; в гриде показываются только обработанные снимки.

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
- Thumbnails 5 размеров (200/400/600/1000/1600), формат WebP всегда + AVIF только для размеров `≥ PHOTOS_AVIF_MIN_SIZE` (по умолчанию 1000).
- Blurhash-плейсхолдер (4×3 components) считается на 200.webp; UI рисует его на `<canvas>` и плавно сменяет реальной картинкой через 220 ms fade-in.
- Реалтайм-уведомление о готовности фото по SSE (`event: photo_processed`) через общий поток `/api/v1/notifications/stream`. Грид и виджет автоматически обновляются (debounce 400 ms).
- Авто-исцеление рассинхрона БД↔диск: cron каждые 5 минут перевыкладывает в очередь фото с отсутствующими thumbnails или зависшие в `processed=false`.

---

## 2. Структура кода

### Backend (`./backend/app/api/photos/`)

| Файл | Назначение |
|---|---|
| `./backend/app/api/photos/__init__.py` | Сборка `photos_router` из подроутеров. |
| `./backend/app/api/photos/_common.py` | Общие хелперы (`_would_create_cycle`, `_enqueue_processing`, `_module_settings`, логгер). Сериализаторы вынесены в `./backend/app/services/photos_serializers.py`. |
| `./backend/app/api/photos/folders.py` | CRUD дерева папок, tree-эндпойнт, soft-delete/restore. |
| `./backend/app/api/photos/folder_service.py` | Сервисный слой папок (валидация, права, инвалидация ACL-кэша). |
| `./backend/app/api/photos/photos.py` | CRUD фото, upload, корзина, восстановление, purge, bulk-операции. |
| `./backend/app/api/photos/photo_service/` | Сервисный слой фото. Пакет декомпозирован: `_queries.py` (листинги, статистика), `_move.py` (перемещение фото), `_bulk.py` (bulk delete/move), `_upload.py` (pipeline загрузки, `perform_upload` на 6 узких функций). |
| `./backend/app/api/photos/thumbnails.py` | Раздача thumbnails (WebP/AVIF) и оригиналов через `X-Accel-Redirect`. При отсутствии файла возвращает `503 Retry-After: 3` (WebP/AVIF) либо `404` с `X-Thumb-Status: no-avif`, если WebP уже есть, а AVIF не был сгенерирован. Никогда не запускает PIL в API-процессе — только enqueue в arq. |
| `./backend/app/api/photos/sharing.py` | Создание/отзыв токенов на фото и папки (private endpoints). |
| `./backend/app/api/photos/public_views.py` | Публичные эндпойнты просмотра/скачивания по токену (фото и папки). Выделено из `sharing.py`. |
| `./backend/app/api/photos/permissions.py` | Управление ACL папки + поиск subjects (users/groups) через Keycloak. |
| `./backend/app/api/photos/tags.py` | CRUD тегов + назначение тегов на фото. |
| `./backend/app/api/photos/zip_jobs.py` | Постановка ZIP-задач и выдача готовых архивов. |
| `./backend/app/api/photos/import_scan.py` | Постановка задач сканирования импорт-директории. |

### Сервисы

| Файл | Назначение |
|---|---|
| `./backend/app/services/photos_storage.py` | Работа с ФС: пути, sanitize filename, EXIF, генерация thumbnails (WebP всегда; AVIF только для размеров ≥ `AVIF_MIN_SIZE`), `compute_blurhash()` из 200.webp, удаление файлов. |
| `./backend/app/services/photos_acl.py` | Резолв прав по папке/фото с рекурсивным CTE, кэширование в Redis, инвалидация. |
| `./backend/app/services/photos_realtime.py` | Публикация `photo_processed` в общий Redis-стрим `notifications:photos`. Читается SSE-эндпойнтом `/api/v1/notifications/stream`. |
| `./backend/app/services/photos_folder_repo.py` | DB-репозиторий для папок: выборки, рекурсивные CTE, soft-delete (перенесено из `api/photos/`). |
| `./backend/app/services/photos_photo_repo.py` | DB-репозиторий для фото (выборки с пагинацией, deleted, recent, storage stats; перенесено из `api/photos/`). |
| `./backend/app/services/photos_serializers.py` | Чистые сериализаторы ORM→Pydantic (`folder_to_public`, `photo_to_public`). Используется и API, и сервисами. |
| `./backend/app/services/photos_trash.py` | Оркестратор корзины (ACL + транзакции + аудит). Делегирует FS-операции и узкие DB-запросы выделенным модулям. Используется напрямую из `folders.py`, `photos.py`, `photo_service.py` без lazy-import. |
| `./backend/app/services/photos_trash_repo.py` | DB-репозиторий для trash-сценариев (выборки expired/all-trashed, низкоуровневые delete). |
| `./backend/app/services/photos_trash_files.py` | FS-операции корзины (удаление оригиналов, thumbnails, `rmtree` папок). |

### Модели и схемы

- `./backend/app/models/photos.py` — SQLAlchemy ORM: `PhotoFolder`, `PhotoFolderPermission`, `Photo`, `PhotoZipJob`, `PhotoShareToken`, `PhotoTag`, `PhotoTagAssignment`, `PhotoFolderShareToken`.
- `./backend/app/schemas/photos.py` — Pydantic-схемы запросов/ответов.

### Воркер (`./backend/app/worker/tasks/photos/`)

| Файл | Задачи |
|---|---|
| `./backend/app/worker/tasks/photos/processing.py` | `process_photo_upload` — генерация thumbnails (WebP всех размеров + AVIF для больших), вычисление blurhash, извлечение EXIF, атомарный UPDATE (`processed=true, blurhash=…`), публикация SSE-события `photo_processed`. `detect_missing_thumbnails` — cron-задача авто-исцеления: реквьюит фото с пропавшими файлами и зависшие `processed=false` старше 2 минут. |
| `./backend/app/worker/tasks/photos/zip_jobs.py` | `generate_folder_zip` — упаковка папки в ZIP. |
| `./backend/app/worker/tasks/photos/import_scan.py` | `import_scan_run` — сканирование `/data/photos/import`. Постановка ARQ-задач переехала после внешнего commit'а (#15). |
| `./backend/app/worker/tasks/photos/cleanup.py` | `cleanup_deleted_photos`, `cleanup_zip_jobs` (cron) и `empty_photo_trash` (по запросу) — окончательное удаление soft-deleted фото и истёкших ZIP-архивов. |

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
| `./frontend/src/components/photos/PhotosGridBase.vue` | Базовая сетка с режимами loading/empty/grid. Принимает `photos`, `loading`, `cellClass`, рендерит каждую ячейку через слот `#cell`. Используется в `PhotosGrid`, `PhotoTrashView`, `PublicFolderPage` (#24, дедупликация). |
| `./frontend/src/components/photos/PhotosGrid.vue` | Сетка для основной галереи: drop-zone, multi-select, load-more, удаление. Делегирует рендер ячеек в `PhotosGridBase` + `PhotoThumb`. |
| `./frontend/src/components/photos/PhotoThumb.vue` | Универсальная плитка: рисует blurhash на `<canvas>` 32×32 (CSS blur 8px + scale 1.1) пока реальное изображение не загрузилось, затем 220 ms fade-in. AVIF-источник в `<picture>` рендерится только при `useAvif` (требуется размер ≥ 1000), иначе webp. Если blurhash ещё нет — shimmer-градиент. |
| `./frontend/src/components/photos/PhotosUploadQueue.vue` | Очередь загрузки с прогрессом. |
| `./frontend/src/components/photos/LightboxBase.vue` | Базовый контейнер lightbox: overlay, клавиатурные обработчики, slot для содержимого. Используется внутри `LightboxModal`. |
| `./frontend/src/components/photos/LightboxModal.vue` | Контейнер lightbox: состояние, навигация по фото, обработка клавиатуры. |
| `./frontend/src/components/photos/PhotoLightboxViewer.vue` | Внутренний просмотрщик фото внутри lightbox (рендер изображения, зум). |
| `./frontend/src/components/photos/LightboxToolbar.vue` | Панель инструментов lightbox (скачать, поделиться, удалить, теги). |
| `./frontend/src/components/photos/LightboxTagsEditor.vue` | Редактор тегов внутри lightbox. |
| `./frontend/src/components/photos/SharePhotoModal.vue` | Модалка создания публичной ссылки на отдельное фото. |
| `./frontend/src/components/photos/ShareFolderModal.vue` | Модалка создания публичной ссылки на папку. |
| `./frontend/src/components/photos/PhotoPermissionsModal.vue` | Модалка управления ACL папки. |
| `./frontend/src/components/photos/PhotoTrashView.vue` | Просмотр корзины (фото + папки). Сетка фото построена на `PhotosGridBase` + `PhotoThumb`. |
| `./frontend/src/api/photos.ts` | Тонкий клиент REST API. |
| `./frontend/src/stores/photos.ts` | Pinia-стор для виджета recent. `installRealtime()` подписывается на `window` event `photos:processed` и обновляет ленту с дебаунсом 500 ms. |
| `./frontend/src/stores/notifications.ts` | SSE-клиент. Слушает `event: photo_processed`, диспатчит `window` CustomEvent `photos:processed` с `{ photo_id, folder_id, blurhash }`. |
| `./frontend/src/composables/usePhotoListing.ts` | Загрузка/пагинация фото в текущей папке. Слушает `photos:processed` для текущей папки и инвалидирует react-query кэш с дебаунсом 400 ms. |
| `./frontend/src/composables/usePhotoUpload.ts` | Очередь и upload через `XMLHttpRequest`. |
| `./frontend/src/composables/usePhotoSelection.ts` | Множественный выбор. |
| `./frontend/src/composables/usePhotoFolderActions.ts` | Действия над папкой (create/rename/delete/move). |
| `./frontend/src/composables/usePhotoFolderSelection.ts` | Состояние выбранной папки. |
| `./frontend/src/composables/useLightboxPhotoTags.ts` | Теги в lightbox. |
| `./frontend/src/composables/useLightboxShare.ts` | Создание public-ссылок из lightbox. |
| `./frontend/src/composables/useLightboxSlideshow.ts` | Управление слайд-шоу в lightbox (таймер, автопереключение). |
| `./frontend/src/composables/useLightboxView.ts` | Зум и поворот изображения внутри lightbox. |

---

## 3. Модель данных

```
photo_folders
  id, parent_id, name, slug, path, fs_path, description,
  cover_photo_id, created_by, created_at, updated_at, deleted_at,
  storage_kind ('originals'|'import'), storage_root        -- миграция 057
  UNIQUE (parent_id, slug)
  INDEX (path)
  INDEX active (parent_id) WHERE deleted_at IS NULL
  CHECK (storage_kind IN ('originals','import'))

photo_folder_permissions
  id, folder_id, subject_type ('user'|'group'), subject_id, subject_name,
  permission ('viewer'|'uploader'|'manager'), granted_by, created_at
  UNIQUE (folder_id, subject_type, subject_id)             -- миграция 056

photos
  id, folder_id, filename, original_name, size_bytes, mime_type,
  width, height, taken_at, exif (jsonb), description,
  inherit_permissions, processed, blurhash (varchar 64, nullable),  -- миграция 060
  uploaded_by, created_at, deleted_at
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

### storage_kind (миграция 057)

- `storage_kind = 'originals'` (по умолчанию) — обычная папка под `/data/photos/originals/{fs_path}`.
- `storage_kind = 'import'` — папка-«окно» в drop-зону `/data/photos/import` (либо альтернативный `storage_root`). Используется для массового импорта без upload через `POST /photos/import/scan`. Поведение перемещения файлов и thumbnails здесь отличается — см. `./backend/app/services/photos_storage.py`.

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
| DELETE | `/folders/{folder_id}/purge` | Физическое удаление папки из корзины вместе со всеми потомками (manager). |

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
| GET | `/thumbnail/{photo_id}/{size}?format=webp\|avif` | Размер ∈ `{200,400,600,1000,1600}`. Если файла нет — `503 Retry-After: 3` + `X-Thumb-Status: pending` (задача поставлена в arq, в API-процессе PIL не запускается). Для AVIF при наличии WebP — `404 X-Thumb-Status: no-avif` (AVIF опционален). |
| GET | `/original/{photo_id}?download=0\|1` | Раздача через `X-Accel-Redirect`. |

> **Грид и счётчики показывают все активные фото, включая `processed=false`.** Это касается `GET /folders/{id}/photos`, `GET /folders/{id}` (`photos_count`), `GET /public-folder/{token}/info` и `/public-folder/{token}/photos`. Для необработанных фото фронт рендерит шиммер-плейсхолдер или blurhash (если уже посчитан), а полноценный thumbnail подменяется по SSE-событию `photos.processed`. Виджет «Недавние» (`fetch_recent_photos_with_folders`) — единственное исключение, он по-прежнему фильтрует `processed=true`, чтобы не показывать пустые плитки.

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
- Качество WebP/AVIF: `THUMB_QUALITY = 85`, `WEBP_METHOD = 4` (компромисс скорость↔размер).
- AVIF генерируется только для размеров `≥ AVIF_MIN_SIZE` (env `PHOTOS_AVIF_MIN_SIZE`, по умолчанию `1000`). Можно глобально отключить через `PHOTOS_GENERATE_AVIF=0`.
- Генерация исключительно в ARQ-задаче `process_photo_upload`. **API-процесс никогда не запускает PIL** — это позволяет переживать пакетные загрузки без OOM. Если файла нет — возвращаем `503 Retry-After` и ставим задачу.
- Blurhash считается на 200.webp (4×3 components) и сохраняется в `photos.blurhash`; используется фронтом для мгновенного плейсхолдера.

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
| `process_photo_upload` | После upload, при `GET /thumbnail` для отсутствующего файла, из cron `detect_missing_thumbnails`. `timeout=300s`, `max_tries=5`. | Генерация thumbnails (WebP 5 размеров + AVIF для `≥1000`), вычисление blurhash на 200.webp, EXIF (опц. strip GPS), атомарный UPDATE `processed=true, blurhash=…`, публикация SSE `photo_processed` в Redis-стрим `notifications:photos`. |
| `detect_missing_thumbnails` | cron каждые 5 минут | Авто-исцеление БД↔диск: реквьюит фото с пропавшим `200.webp` (сбрасывает `processed=false`) и зависшие `processed=false` старше 2 минут. Использует уникальный `_job_id` с timestamp, чтобы обходить arq-дедуп failed-результатов. |
| `generate_folder_zip` | `POST /folders/{id}/zip` | Стримит ZIP в `/data/photos/zips/{job_id}.zip`. |
| `import_scan_run` | `POST /import/scan` | Импорт из `/data/photos/import` в указанную папку. ARQ-задачи enqueue-ятся только после успешного outer commit'а батча (#15). |
| `cleanup_deleted_photos` / `cleanup_zip_jobs` | cron | Чистка просроченных soft-deleted фото / истёкших ZIP-архивов. |
| `empty_photo_trash` | `POST /trash/empty` | Удаляет файлы и строки soft-deleted фото + просроченные ZIP. |

### Realtime поток `photo_processed`

```
worker.process_photo_upload
  → photos_realtime.publish_photo_processed(redis, photo_id, folder_id, blurhash)
  → XADD notifications:photos {type, photo_id, folder_id, blurhash}  maxlen ~5000

api.notifications.stream (SSE)
  → XREAD по 3 ключам: notifications:{user_id}, meetings, photos
  → composite Last-Event-ID = "personal|meetings|photos"
  → emit  event: photo_processed   data: {photo_id, folder_id, blurhash}

frontend.stores.notifications
  → addEventListener('photo_processed') → window CustomEvent 'photos:processed'

frontend.composables.usePhotoListing  — invalidateQueries(folder, debounce 400ms)
frontend.stores.photos                — loadRecent(debounce 500ms)
```

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

### Env-переменные (не в `modules.json`)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `PHOTOS_GENERATE_AVIF` | `1` | `0/false` отключает генерацию AVIF полностью. |
| `PHOTOS_AVIF_MIN_SIZE` | `1000` | Минимальный размер thumbnail, для которого генерится AVIF. Фронт скрывает AVIF-`<source>` при размерах меньше этого. |

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

### Backend (`./backend/tests/unit/`)

- `test_photos_acl.py` — резолв прав, рекурсивный CTE, кэш.
- `test_photos_permissions.py` — API эндпоинтов прав, в т.ч. UNIQUE по `(folder_id, subject_type, subject_id)`.
- `test_photos_sharing.py` — public-токены фото и папок.
- `test_photos_storage.py` — пути, sanitize, генерация thumbnails, EXIF/GPS strip.
- `test_worker_photos_tasks.py` — `process_photo_upload`, `build_zip_job`, `import_scan_job`, `empty_photo_trash`. После декомпозиции `TrashService` (#7) сюда же входят smoke-кейсы для leaf-методов (`soft_delete_*`, `restore_*`, `purge_*`) и orchestrator'ов (`purge_expired`, `empty_trash`, `empty_trash_for_user`) — leaf проверяются без `db.commit()` (#B-3), orchestrator'ы — с per-iteration commit/rollback.

### Frontend (`./frontend/tests/unit/`, `./frontend/tests/e2e/`)

- Unit: `photos-store.spec.ts`, `photos-api.spec.ts`, `photos-components-smoke.spec.ts` (smoke по grid/lightbox-компонентам после унификации #F-1), `photo-decomposition.spec.ts`, `queries-photos.spec.ts`, плюс composables (`usePhotoUpload`, `usePhotoListing`, `usePhotoSelection`).
- E2E: `./frontend/tests/e2e/photos.spec.ts` — сценарий загрузки, просмотра, share, удаления.

---

## 10. Связанные документы

- ADR-030, ADR-031 — см. `./docs/adr.md`.
- API-контракты — см. `./docs/api-contracts.md` (раздел `/photos`).
- Схема БД — см. `./docs/db-schema.md`.
- Матрица ролей — см. `./docs/roles-matrix.md`.

---

## 11. Архитектура показа миниатюр (актуальная редизайн-итерация)

### Проблема, которую решали

При пакетной загрузке 40+ фотографий клиент массово запрашивал thumbnails. Предыдущая реализация генерировала PIL-миниатюры **on-the-fly прямо в HTTP-обработчике** (5 размеров WebP + AVIF с `method=6`). Это вело к OOM-kill uvicorn-воркеров и каскадным 502/503/`ERR_INCOMPLETE_CHUNKED_ENCODING`. После reload часть фотографий оставалась серыми навсегда — рассинхрон между `processed=true` в БД и отсутствующими файлами на диске.

### Принципы новой архитектуры

1. **API никогда не делает CPU-тяжёлую работу.** Все генерации — в arq-воркере. На отсутствующий файл API отвечает `503 Retry-After`.
2. **Мгновенный визуальный отклик** через blurhash — 4×3 components (~28 байт base83), декодируется на канвасе 32×32 за <1 ms, размывается CSS-фильтром.
3. **Push, не poll.** Готовность фото пушится по уже существующему SSE-каналу `/api/v1/notifications/stream` (добавлен третий поток `notifications:photos`). Никаких HEAD-проб, никаких ретраев на клиенте.
4. **Грид показывает фото мгновенно.** Листинг и счётчики возвращают и `processed=false`; пока worker не закончил, фронт рисует blurhash либо шиммер-плейсхолдер. Готовый thumbnail подменяется по SSE без перезагрузки страницы. Исключение — виджет «Недавние», там по-прежнему отображаются только готовые фото.
5. **Идемпотентная обработка.** `process_photo_upload` пропускает уже сгенерированные thumbnails (`200.webp` существует) и пересчитывает только недостающие куски (blurhash, EXIF). Повторные ретраи cron'а или arq не запускают PIL заново.
6. **Авто-исцеление с дедупом.** Cron каждые 5 минут сверяет БД и диск: фото с `processed=false`, но с готовыми thumb'ами просто помечается `processed=true` без перерасчёта; фото с битым диском — реквьюится. `_job_id` бакетируется по 5-минутному окну, поэтому очередь не пухнет — не более одного дубликата на фото в окно.
7. **Cap на CPU.** Семафор `_THUMB_GEN_SEMAPHORE=2` ограничивает количество одновременных PIL-операций в worker-процессе, чтобы при `ARQ_MAX_JOBS=10` 5K×3K JPEG'и не задушили GIL и не уходили в timeout.

### Поток данных (upload → render)

```
1. POST /folders/{id}/upload      → INSERT photos (processed=false, blurhash=null)
                                  → enqueue process_photo_upload (timeout=300s, max_tries=5)
                                  → API возвращает 201 немедленно

2. worker.process_photo_upload    → generate_thumbnails (5 webp + avif для ≥1000)
                                  → compute_blurhash(200.webp)  -> 4×3 = ~28 байт
                                  → UPDATE processed=true, blurhash=…
                                  → XADD notifications:photos {photo_id, folder_id, blurhash}

3. SSE /notifications/stream      → XREAD notifications:photos
                                  → emit  event: photo_processed

4. frontend.notifications         → window dispatch 'photos:processed'
   frontend.usePhotoListing       → invalidateQueries(folder, debounce 400ms)
   frontend.PhotoThumb            → <canvas blurhash> → fade-in <img> через 220ms
```

### Принятые компромиссы

- **AVIF только для ≥1000.** На сеточных миниатюрах выигрыш по размеру не оправдывает CPU. Фронт условно скрывает `<source type="image/avif">` для размеров меньше — иначе браузер выбирает AVIF-источник и при 404 не падает на следующий `<source>`.
- **WEBP_METHOD=4** вместо `6`. Разница в размере <5%, кодирование в 2–3 раза быстрее.
- **Cutoff cron 2 минуты.** Достаточно времени, чтобы свежая задача успела отработать; недостаточно, чтобы пользователь долго смотрел на пустой грид.

### Изменения по файлам (краткий список)

Backend:
- `./backend/migrations/versions/060_photos_blurhash.py` — `ALTER TABLE photos ADD COLUMN blurhash VARCHAR(64)`.
- `./backend/app/models/photos.py:131` — Mapped `blurhash`.
- `./backend/app/schemas/photos.py:76,93` — `PhotoPublic`/`PhotoPublicAnon`.
- `./backend/app/api/photos/_common.py:87,105` — сериализация `blurhash`.
- `./backend/app/services/photos_storage.py` — `compute_blurhash()`, `AVIF_MIN_SIZE`, `WEBP_METHOD=4`.
- `./backend/app/services/photos_realtime.py` — новый файл, `PHOTOS_STREAM_KEY`, `publish_photo_processed()`.
- `./backend/app/worker/tasks/photos/processing.py` — пайплайн (thumbs → blurhash → atomic UPDATE → SSE), `detect_missing_thumbnails` с авто-сбросом `processed=false`, cutoff 2 мин, уникальный `_job_id`.
- `./backend/app/worker/main.py:113,182-186` — `process_photo_upload` `timeout=300, max_tries=5`; cron `detect_missing_thumbnails` каждые 5 минут.
- `./backend/app/services/photos_photo_repo.py` — фильтр `Photo.processed.is_(True)` в `fetch_recent_photos_with_folders` (виджет «Недавние»); листинг папки и счётчики фильтр по `processed` не применяют.
- `./backend/app/api/photos/public_views.py` — публичный просмотр папки и фото (выделено из `sharing.py`); `processed` в листинге не фильтруется.
- `./backend/app/api/photos/thumbnails.py` — 503/Retry-After вместо on-the-fly PIL; AVIF 404 + `X-Thumb-Status: no-avif` при наличии WebP.
- `./backend/app/api/notifications.py:181-276` — SSE читает третий стрим `notifications:photos`, composite Last-Event-ID `personal|meetings|photos`.
- `./backend/pyproject.toml` — зависимость `blurhash>=1.1.4`.

Frontend:
- `./frontend/src/components/photos/PhotoThumb.vue` — новый универсальный компонент: blurhash canvas + fade-in, условный AVIF source.
- `./frontend/src/components/photos/PhotosGrid.vue`, `./frontend/src/components/widgets/PhotosWidget.vue` — переключены на `PhotoThumb`, прокидывают `blurhash`.
- `./frontend/src/stores/notifications.ts` — listener `photo_processed`.
- `./frontend/src/stores/photos.ts` — `installRealtime()` для виджета recent.
- `./frontend/src/composables/usePhotoListing.ts` — `invalidateQueries` по SSE-событию.
- `./frontend/src/api/photos.ts` — убран `thumbStatusUrl` (концепция отменена).
- `./frontend/package.json`, `./frontend/package-lock.json` — `blurhash ^2.0.5`.

### Развёртывание

```bash
docker compose run --rm migrations alembic upgrade head   # миграция 060
docker compose build backend worker frontend
docker compose up -d backend worker frontend
```

После рестарта worker'а cron `detect_missing_thumbnails` в течение ≤5 минут подберёт все необработанные/потерянные фото из ранее загруженных батчей.
