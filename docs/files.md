# Модуль «Файлы»

> Витрина над Nextcloud для единого корпоративного файлового хранилища (~300 сотрудников). Реальные байты файлов и каталоги живут в Nextcloud, доступ к ним идёт через единственный сервисный аккаунт `portal-svc` по WebDAV (Basic Auth). Права доступа (кто что видит/редактирует) хранятся **только в БД портала** в виде per-folder ACL, а не в ACL Nextcloud. Портал ведёт «теневое» дерево папок и трекинг загруженных файлов. См. ADR-032.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/files/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia (`./frontend/src/pages/FilesPage.vue`, `./frontend/src/components/files/`) |
| Воркер | ARQ (`./backend/app/worker/tasks/files.py`) |
| Хранилище | Nextcloud WebDAV под корнем `PortalFiles/` (service account `portal-svc`) |
| Доступ к NC | Один service account, Basic Auth; путь `/remote.php/dav/files/portal-svc/` |
| ACL-кэш | Redis, ключи `files_acl:{user_id}:folder:{folder_id}` и `files_share:{user_id}:{folder_id}:{filename_hash}` (TTL 300с) |
| Бэкап ACL | `/data/settings/files-acl.json` (права папок) и `/data/settings/files-shares.json` (шары файлов) — переживают wipe PostgreSQL |
| Онлайн-редактор | Collabora Online (через federation share) |
| Связанные ADR | ADR-032 (service account, Вариант A) |

### Возможности

- Дерево папок неограниченной вложенности (до 20 уровней при резолве ACL) с soft-delete.
- Гранулярные права на папку (`viewer` / `editor` / `manager`) с наследованием вверх по дереву; subject = `user` или `group` (Keycloak) либо системная группа «Все пользователи».
- **Пофайловый шеринг**: адресная выдача доступа (`viewer` / `editor`) к одному файлу пользователю/группе/«Всем» без открытия всей папки; разделы «Мои шеры» / «Доступные мне», реестр для admin, in-app + email уведомления получателю.
- Просмотр содержимого папки = живой листинг Nextcloud WebDAV, обогащённый метаданными загрузки из БД (кто/когда залил, аватар).
- Загрузка файлов (несколько за раз) с потоковой передачей, лимитом размера и проверкой MIME-типа по содержимому (`python-magic`) против allowlist/blocklist.
- Скачивание (`attachment`) и inline-превью (изображения + PDF) с жёстким CSP-sandbox.
- Удаление файла, пакетное удаление и пакетное перемещение с in-flight-guard.
- Открытие офисных документов в Collabora Online (read/write по уровню прав).
- Импорт дерева папок из Nextcloud (ручной admin-эндпоинт + фоновый sync при старте воркера).
- Восстановление прав из `files-acl.json` при импорте/старте.

---

## 2. Структура кода

### Backend API (`./backend/app/api/files/`)

Монолитный роутер разбит на тематические подмодули; они агрегируются в один `router` в `./backend/app/api/files/__init__.py` (пути, методы и `operationId` сохранены — сверяется по OpenAPI-снапшоту).

| Файл | Назначение |
|---|---|
| `./backend/app/api/files/__init__.py` | Сборка агрегирующего `router` из подроутеров + back-compat реэкспорты. |
| `./backend/app/api/files/_common.py` | Общие хелперы: sanitize имён, guard «модуль включён», поиск папки или 404, построение breadcrumbs (рекурсивный CTE), нормализация WebDAV-href → DB-путь, ACL-фильтрация подпапок, обогащение метаданными из `file_items`. MIME allowlist/blocklist и whitelist превью. |
| `./backend/app/api/files/folders.py` | Дерево папок, детальный просмотр папки, CRUD папок. |
| `./backend/app/api/files/upload.py` | Загрузка файлов; открытие файла в Collabora. |
| `./backend/app/api/files/download.py` | Потоковое скачивание и inline-превью. |
| `./backend/app/api/files/files_ops.py` | Удаление файла, bulk-delete, bulk-move + in-flight-helpers (Redis SETNX). |
| `./backend/app/api/files/permissions.py` | CRUD ACL папки, переключатель наследования, поиск subjects через Keycloak; запись создателя (`is_creator`) в списке прав. |
| `./backend/app/api/files/shares.py` | Пофайловый шеринг: create/upsert/list/revoke шары, «мои шеры», «доступные мне», admin-реестр. |
| `./backend/app/api/files/_share_notify.py` | Уведомления получателю шары (in-app + email через `email_outbox`). |
| `./backend/app/api/files/_share_drift.py` | Дрейф шар при delete/move/rename файла (revoke/repoint + синк JSON). |
| `./backend/app/api/files/sync.py` | Ручной импорт дерева из Nextcloud (admin). |

### Сервисы

| Файл | Назначение |
|---|---|
| `./backend/app/services/files_acl.py` | Резолв прав на папку (с кэшем Redis), `require_folder_permission`, batch-резолв для дерева без N+1, инвалидация кэша по поддереву. Пофайловый резолв: `resolve_file_share_permission`, `require_file_access` (= `max(folder ACL, file share)`), инвалидация `files_share:*`. |
| `./backend/app/services/files_acl_persistence.py` | Персистентный JSON-бэкап ACL (`/data/settings/files-acl.json`), атомарная запись (tempfile + `os.replace`, chmod 0600). |
| `./backend/app/services/files_shares_persistence.py` | JSON-бэкап шар файлов (`/data/settings/files-shares.json`), ключ = `nc_path`; атомарная запись, `save/drop/rename/load_all`. |
| `./backend/app/services/nextcloud/service.py` | Фабрика `get_nc_service()` (синглтон с пере-сборкой по fingerprint настроек), Collabora-методы. |
| `./backend/app/services/nextcloud/webdav/_client.py` | WebDAV-клиент: `list_folder`, `create_folder`, `delete`, `move`, `download_stream`, `upload_stream`, `list_folders_recursive`, `href_to_db_nc_path`, health-check, `ensure_root`. |
| `./backend/app/services/nextcloud/collabora.py` | Получение WOPI/Collabora URL (напрямую и через federation share). |

### Воркер

| Файл | Назначение |
|---|---|
| `./backend/app/worker/tasks/files.py` | `startup_sync_nc_folders` — BFS-обход папок Nextcloud при старте воркера (cron, `run_at_startup`, задержка ~30с). Идемпотентен, защищён Redis-блокировкой (TTL 5 мин), восстанавливает права из `files-acl.json` и шары файлов из `files-shares.json` (`ON CONFLICT DO NOTHING`, просроченные пропускаются). |

### Frontend (`./frontend/src/`)

| Файл | Назначение |
|---|---|
| `./frontend/src/api/files.ts` | Типы и HTTP-клиент всех эндпоинтов + хелперы: `formatFileSize`, иконки (`fileIcon`/`fileIconEmoji`), классификаторы превью и Collabora-файлов, лимиты bulk. |
| `./frontend/src/queries/files.ts` | TanStack Query-обёртки. |
| `./frontend/src/stores/files.ts` | Pinia-стор состояния модуля. |
| `./frontend/src/composables/useFilesData.ts` | Данные текущей папки. |
| `./frontend/src/composables/useFilesTree.ts` | Дерево папок (сайдбар). |
| `./frontend/src/composables/useFilesSelection.ts` | Выбор файлов. |
| `./frontend/src/composables/useFilesBulkOps.ts` | Bulk-операции (delete/move/download). |
| `./frontend/src/composables/useFilesUpload.ts` | Очередь загрузки, drag-and-drop. |
| `./frontend/src/pages/FilesPage.vue` | Страница модуля. |
| `./frontend/src/components/files/` | Таблица, тулбар, сайдбар, breadcrumbs, bulk-bar, drop-zone, превью изображений, модалки создания папки / перемещения / прав / шеринга (`FilesShareModal.vue`), панель «Мои шеры / Доступные мне» (`FilesSharesPanel.vue`), admin-реестр (`FileSharesTab.vue`). |

---

## 3. Модель данных

Четыре таблицы (`./backend/app/models/files.py`, миграции `020_files`, `038_file_items`, `042_file_folder_inherit_permissions`, `063_file_shares`).

### `file_folders` — теневое дерево папок

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID PK | |
| `parent_id` | UUID FK `file_folders.id` (RESTRICT), nullable | Родитель; `NULL` — корень. |
| `name` | varchar(500) | Отображаемое имя. |
| `nc_path` | varchar(2000), UNIQUE | Путь относительно WebDAV-корня `portal-svc` (напр. `PortalFiles/HR/Docs`). Уникален. |
| `description` | text, nullable | |
| `inherit_permissions` | bool, default `true` | Наследовать ли права от родителя вверх по дереву. |
| `created_by` | UUID FK `users.id` (SET NULL), nullable | Создатель = автоматически `manager`. |
| `created_at` / `updated_at` | timestamptz | |
| `deleted_at` | timestamptz, nullable | Soft-delete. |

### `file_folder_permissions` — per-folder ACL

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID PK | |
| `folder_id` | UUID FK `file_folders.id` (CASCADE) | |
| `subject_type` | varchar(10), CHECK `user`/`group` | |
| `subject_id` | varchar(255), index | user-id или path/name группы (Keycloak). |
| `subject_name` | varchar(255) | Отображаемое имя subject. |
| `permission` | varchar(20), CHECK `viewer`/`editor`/`manager` | |
| `granted_by` | UUID FK `users.id` (SET NULL), nullable | |
| `created_at` | timestamptz | |

Уникальность: `(folder_id, subject_id)`.

### `file_items` — трекинг загруженных через портал файлов

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID PK | |
| `folder_id` | UUID FK `file_folders.id` (CASCADE), index | |
| `nc_path` | varchar(2000) | Полный путь = `folder.nc_path` + `/` + имя. |
| `name` | varchar(500) | |
| `size_bytes` | bigint, default 0 | |
| `mime_type` | varchar(255), nullable | Реальный MIME (по содержимому). |
| `uploaded_by` | UUID FK `users.id` (SET NULL), nullable | |
| `uploaded_at` | timestamptz | |
| `deleted_at` | timestamptz, nullable | Soft-delete. |

> Файлы, залитые **напрямую в Nextcloud** (минуя портал), записи в `file_items` не имеют — в листинге они показываются без метаданных «кто/когда загрузил».

### `file_shares` — пофайловые шары

| Поле | Тип | Назначение |
|---|---|---|
| `id` | UUID PK | |
| `folder_id` | UUID FK `file_folders.id` (CASCADE) | Папка-контейнер файла. |
| `filename` | varchar(500) | Имя файла (после `sanitize_name`). |
| `nc_path` | varchar(2000) | Денормализованный `folder.nc_path + '/' + filename` — для персистентности и реестра. |
| `subject_type` | varchar(10), CHECK `user`/`group` | |
| `subject_id` | varchar(255), index | user-id / group-path / `__all_users__` (Keycloak). |
| `subject_name` | varchar(255) | Отображаемое имя на момент выдачи. |
| `permission` | varchar(20), CHECK `viewer`/`editor` | `manager` на файл не выдаётся. |
| `shared_by` | UUID FK `users.id` (SET NULL), nullable | Кто поделился. |
| `expires_at` | timestamptz, nullable | Опциональный TTL; `NULL` — бессрочно. |
| `created_at` | timestamptz | |
| `revoked_at` | timestamptz, nullable | Мягкий отзыв (история сохраняется для аудита). |

Уникальность: `(folder_id, filename, subject_id)` — повторная выдача = upsert. Индексы: `(folder_id, filename)`, `subject_id`, `(subject_id, revoked_at)`, `expires_at`.

---

## 4. Модель прав (ACL)

Уровни: `viewer < editor < manager` (`./backend/app/services/files_acl.py`).

Алгоритм резолва права пользователя на папку:

1. Portal admin → `manager` (без запроса к БД).
2. `folder.created_by == user.id` → `manager`.
3. Иначе — рекурсивный CTE вверх по `parent_id`: собираются все предки (до 20 уровней), подъём останавливается на папке с `inherit_permissions = FALSE` (сама папка всегда учитывается). Среди записей `file_folder_permissions`, чей `subject_id` совпадает с любым из subject-id пользователя (его user-id + группы из Keycloak + системная «Все пользователи»), берётся максимальный уровень.
4. Нет совпадений → нет доступа (403).

Результат кэшируется в Redis (`files_acl:{user_id}:folder:{folder_id}`, TTL 300с; `"none"` — маркер отсутствия прав). `batch_resolve_folder_permissions` резолвит права для всего дерева одним SQL-запросом + `MGET`/pipeline в Redis (без N+1). Инвалидация (`invalidate_folder_cache`) рекурсивно чистит кэш по всему поддереву затронутой папки и вызывается при изменении прав, переименовании, удалении, смене флага наследования.

### Требуемые уровни по операциям

| Операция | Требуется |
|---|---|
| Просмотр дерева / содержимого | `viewer` на папке |
| Скачивание / превью / открытие в Collabora | `viewer` через `require_file_access` = `max(folder ACL, file share)` |
| Создание папки | роль `editor`/`admin` + `editor` на родителе |
| Загрузка, удаление файла, bulk-delete/move | `editor` |
| Переименование/удаление папки, управление правами, переключение наследования | `manager` |
| Поделиться файлом / отозвать / список шар файла | `manager` на папке (или admin) |
| `POST /files/sync` | роль `admin` |

### Эффективный доступ к байтам файла

Скачивание, превью и открытие в Collabora резолвятся через `require_file_access(user, folder, filename, required, db, redis)` (`./backend/app/services/files_acl.py`): берётся **максимум** из folder ACL (`resolve_folder_permission`) и активной пофайловой шары (`resolve_file_share_permission` — по `subject_ids_for_user`, `revoked_at IS NULL`, не просрочена). `can_write` в Collabora = эффективный уровень `editor+`. Результат шары кэшируется в Redis (`files_share:{user_id}:{folder_id}:{filename_hash}`, TTL 300с); инвалидация при выдаче/отзыве/изменении шары и при delete/move/rename файла. Файл, расшаренный на группу, виден всем её участникам; папка-контейнер в общем дереве у получателя не появляется (доступ — через раздел «Доступные мне»).

---

## 5. REST API (`/api/v1/files`)

Полные контракты с примерами тел запросов/ответов — в `./docs/api-contracts.md` §3.6. Все эндпоинты защищены guard «модуль включён» (иначе `503 Files module is disabled`).

| Метод | Путь | Права | Назначение |
|---|---|---|---|
| GET | `/files/tree` | viewer+ | Дерево доступных папок (`?parent_id=`). |
| GET | `/files/folders/{id}` | viewer+ | Метаданные папки + листинг NC + breadcrumbs (`nc_error=true` при недоступности NC). |
| POST | `/files/folders` | любой (корень) / editor+ на родителе | Создать папку (порядок «БД → NC» с компенсацией); создатель → manager. |
| PATCH | `/files/folders/{id}` | manager | Переименовать / изменить описание. |
| DELETE | `/files/folders/{id}` | manager | Soft-delete поддерева + удаление в NC (`?hard=`). |
| POST | `/files/folders/{id}/upload` | editor+ | Multipart-загрузка; `Idempotency-Key`; rate-limit 20/мин. |
| GET | `/files/download` | viewer+ | Streaming, `attachment`; rate-limit 60/мин (`?folder_id=&filename=`). |
| GET | `/files/preview` | viewer+ | Inline preview (whitelist MIME), CSP sandbox; rate-limit 60/мин. |
| DELETE | `/files/file` | editor+ | Удалить файл (`?folder_id=&filename=`). |
| POST | `/files/folders/{id}/bulk-delete` | editor+ | Пакетное удаление; rate-limit 3/мин; in-flight-guard. |
| POST | `/files/folders/{id}/bulk-move` | editor+ | Пакетное перемещение; rate-limit 3/мин; in-flight-guard. |
| POST | `/files/open` | viewer+ | URL для Collabora (`can_write` по уровню прав). |
| GET | `/files/folders/{id}/permissions` | manager | Список прав папки (создатель первым, `is_creator`). |
| POST | `/files/folders/{id}/permissions` | manager | Выдать/обновить право (+ бэкап в `files-acl.json`); создателя нельзя — 409. |
| DELETE | `/files/folders/{id}/permissions/{perm_id}` | manager | Отозвать право (+ бэкап); создателя нельзя — 409. |
| PATCH | `/files/folders/{id}/inheritance` | manager | Включить/выключить наследование прав. |
| POST | `/files/folders/{fid}/files/{filename}/shares` | manager папки | Поделиться файлом (upsert); rate-limit 20/мин; проверка наличия файла в NC. |
| GET | `/files/folders/{fid}/files/{filename}/shares` | manager папки | Активные шары файла. |
| DELETE | `/files/folders/{fid}/files/{filename}/shares/{sid}` | manager папки | Мягкий отзыв шары. |
| GET | `/files/shares/my` | любой авториз. | Мои шеры (что я выдал). |
| GET | `/files/shares/shared-with-me` | любой авториз. | Доступные мне файлы. |
| GET | `/files/admin/shares` | admin | Реестр всех шеров (фильтры + пагинация). |
| GET | `/files/users/search` | editor/admin | Поиск users/groups (Keycloak) для выдачи прав. |
| POST | `/files/sync` | admin | Импорт дерева из Nextcloud. |

---

## 6. Загрузка файлов

`POST /files/folders/{id}/upload` (`./backend/app/api/files/upload.py`):

1. Опциональный `Idempotency-Key` — кэш результата в Redis (`idem:upload:{user}:{key}`, TTL 24ч).
2. Требуется `editor` на папке. Rate-limit `20/мин/user`.
3. Для каждого файла: sanitize имени (защита от path traversal); проверка `Content-Length` против `max_upload_size_mb`; чтение первых 4 КБ и определение реального MIME через `python-magic`.
4. MIME должен быть в `_UPLOAD_MIME_ALLOWLIST` и не в `_BLOCKED_UPLOAD_MIME` (HTML/SVG/JS/исполняемые/скрипты заблокированы). Иначе файл → `failed` с `error="File type not allowed: ..."`.
5. Потоковая выгрузка в NC (`upload_stream`, чанки 64 КБ, повторная проверка лимита размера → `413`).
6. На каждый успешный файл — запись `file_items`.
7. **Один commit на всю группу**. При сбое commit — drift-аудит `files.upload_db_commit_drift`, файлы из `uploaded` переносятся в `failed` (NC-файлы остаются осиротевшими, устранит sync).

Ответ — `UploadResult { uploaded[], failed[] }`, по элементу на каждый файл.

---

## 7. Bulk-операции

`bulk-delete` / `bulk-move` (`./backend/app/api/files/files_ops.py`):

- Лимит `1 ≤ filenames ≤ 100` (`MAX_BULK_FILES`). Rate-limit `3/мин/user`.
- **In-flight guard**: Redis `SETNX bulk:inflight:{user_id}` (TTL 60с, `BULK_INFLIGHT_TTL`). Параллельный bulk → `409 bulk_in_progress`.
- Имена дедуплицируются и санитизируются; невалидные → `failed` с `error="invalid_name"`.
- **bulk-delete**: NC 404 трактуется как `success=true` (естественная идемпотентность). Один commit на всю группу + один аудит `files.bulk_deleted`.
- **bulk-move**: требует `editor` на src и target; `target == src` → `422 same_folder`; target обязан быть внутри `nc_files_root`. NC 412 → `name_conflict`, NC 404 → `not_found`. **Per-file commit** (частичный успех допустим). При сбое БД после успешного MOVE — warning + аудит `files.bulk_move_drift`, для пользователя файл считается перемещённым (дрейф устранит sync). Импортированным файлам без `file_items` создаётся запись с `uploaded_by = NULL`.

---

## 8. Согласованность БД ↔ Nextcloud

Две системы хранения (БД портала и NC) не имеют распределённых транзакций; используется паттерн «единый порядок + компенсация» (ADR-032):

- **Создание папки**: reserve в БД (`flush`, ловим unique-конфликт → 409) → создать в NC → `commit`. При ошибке NC — rollback БД. При ошибке commit после успеха NC — компенсирующее удаление папки в NC.
- **Переименование**: `commit` БД → `nc.move`. При ошибке NC — компенсация (возврат старого имени/пути в БД).
- **Удаление папки**: soft-delete поддерева в БД (`commit`) → `nc.delete`. При ошибке NC (кроме 404) — БД не откатывается, фиксируется дрейф-аудит `files.folder_delete_nc_drift`; устранит sync или повторное удаление.
- **Drift-сценарии** (осиротевшие файлы в NC, рассинхрон дерева) исцеляются идемпотентным sync'ом.

---

## 9. Синхронизация из Nextcloud

- **Ручной**: `POST /files/sync` (admin, `./backend/app/api/files/sync.py`) — `nc.list_folders_recursive(max_depth=30)`, для каждой отсутствующей в БД папки — `INSERT ... ON CONFLICT DO NOTHING`. Soft-deleted папки **не** восстанавливаются (считаются `skipped`). Права восстанавливаются из `files-acl.json`. Ответ — `NcSyncReport { created, skipped, errors[] }`.
- **Автоматический при старте**: `startup_sync_nc_folders` (`./backend/app/worker/tasks/files.py`) — то же, но запускается воркером (cron, `run_at_startup`, задержка ~30с для подъёма NC), под Redis-блокировкой `files:startup_sync_lock` (TTL 5 мин, освобождение через Lua-CAS).

---

## 10. Персистентность ACL

`./backend/app/services/files_acl_persistence.py` дублирует права в `/data/settings/files-acl.json` (ключ = `nc_path`, значение = список subject-прав). Файл пишется атомарно (tempfile + `os.replace`, chmod 0600, под `asyncio.Lock`). Цель — пережить полную очистку PostgreSQL: после wipe sync воссоздаёт дерево из NC и восстанавливает права из бэкапа. Запись вызывается при grant/revoke; удаление записи — при удалении папки (`drop_folder_perms`).

Аналогично шары файлов дублируются в `/data/settings/files-shares.json` (`./backend/app/services/files_shares_persistence.py`, ключ = `nc_path`, значение = список активных `{subject_type, subject_id, subject_name, permission, expires_at}`). Запись — при каждом create/upsert/revoke; восстановление — на старте воркера (`ON CONFLICT DO NOTHING`, `shared_by=NULL`, просроченные пропускаются).

---

## 11. Пофайловый шеринг

Адресная выдача доступа к одному файлу без открытия всей папки (`./backend/app/api/files/shares.py`, ТЗ `./docs/sharing.md`). Архитектура — Вариант A: права на файл проверяются и хранятся на стороне портала, в Nextcloud ничего не меняется.

- **Управление** (create/upsert, list, revoke) доступно только `manager` папки (или admin). Re-sharing получателем невозможен by design: `manager` на файл не выдаётся, а эндпоинты шеринга всегда требуют `manager` на папке. Файл адресуется `(folder_id, filename)`; повторная выдача — upsert по `(folder_id, filename, subject_id)`. При создании проверяется наличие файла в NC (`nc.file_exists` → 404). Rate-limit 20/мин.
- **Получатель** видит файл в разделе «Доступные мне» (`GET /files/shares/shared-with-me`, по `subject_ids_for_user`) и открывает/скачивает/редактирует через стандартные `download`/`preview`/`open` (право перепроверяет `require_file_access`). Раздел «Мои шеры» (`GET /files/shares/my`) показывает выданные пользователем шары. Admin видит полный реестр (`GET /files/admin/shares`).
- **Уведомления** (`./backend/app/api/files/_share_notify.py`): in-app всем участникам subject + email (`email_outbox`, `KIND_FILE_SHARE`), кроме шары на «Все пользователи» (только in-app).
- **Дрейф** (`./backend/app/api/files/_share_drift.py`, вызывается из `files_ops.py`): при удалении файла — `revoked_at=now` + удаление из `files-shares.json`; при move/rename — repoint `folder_id`/`filename`/`nc_path` активных шар + синк JSON. Удаление папки — `ON DELETE CASCADE` в БД + чистка JSON.
- **Аудит**: `files.file_shared`, `files.file_share_updated`, `files.file_share_revoked` (`metadata`: `subject_id`, `permission`, `nc_path`).

---

## 12. Подзадача: создатель в управлении доступом к папкам

В списке прав папки (`GET /files/folders/{id}/permissions`) первым элементом возвращается создатель папки (`folder.created_by`) с флагом `is_creator=true`, `permission="manager"`, `id=null` (по образцу Базы знаний — `_build_creator_entry`/`_merge_creator` в `./backend/app/api/files/permissions.py`). Если создатель уже присутствует как user в `file_folder_permissions` — записи дедуплицируются. Изменить/удалить право создателя нельзя (409). На фронте (`./frontend/src/components/files/FilesPermissionsModal.vue`) строка создателя помечается бейджем «Создатель» (`n-tag type="success"`), селект уровня и кнопка удаления скрыты.

---

## 13. Безопасность

- **Sanitize имён** (`_SAFE_NAME_RE`): запрещены управляющие символы, `/ \ : * ? " < > |`, `.`/`..`, длина ≤ 200; при загрузке отбрасывается путь (`rsplit('/')`/`'\\'`) — защита от traversal.
- **MIME-проверка по содержимому** (`python-magic`) с allowlist + явным blocklist для активного контента (HTML, SVG, JS, PHP, shell, исполняемые).
- **Превью**: только whitelist MIME (`image/png|jpeg|gif|webp|avif`, `application/pdf`); ответ с `Content-Security-Policy: sandbox; default-src 'none'` и `X-Content-Type-Options: nosniff`.
- **Лимит размера** загрузки — `max_upload_size_mb` (системная настройка), проверяется и по заголовку, и потоково (`413`).
- **Доступ к NC** — только service account `portal-svc`; JWT пользователя в NC не используется (ADR-032). Авторизация — исключительно ACL портала.
- Все мутации пишут аудит-события (`files.folder_created`, `files.file_uploaded`, `files.bulk_deleted`, `files.permission_granted`, дрейф-события и т. д.).

---

## 14. Связанные документы

- `./docs/adr.md` — ADR-032 (Nextcloud service account, Вариант A).
- `./docs/sharing.md` — ТЗ пофайлового шеринга.
- `./docs/api-contracts.md` §3.6 — полные REST-контракты модуля.
- `./docs/db-schema.md` — таблицы `file_folders`, `file_folder_permissions`, `file_items`, `file_shares`.
- `./docs/integration-keycloak-nextcloud.md` — настройка Keycloak realm и Nextcloud service account.
- `./docs/roles-matrix.md` — матрица ролей §3.6.
</content>
</invoke>
