# Модуль «Файлы» (Пофайловый шеринг)

> **Когда читать:** при работе с пофайловым обменом, таблицей `file_shares`, drift-реконсиляцией и управлением доступа к отдельным файлам.
> **Ключевой код:** `./backend/app/api/files/shares.py`, `./backend/app/services/files_shares_persistence.py`, `./frontend/src/api/files.ts`.
> **ADR:** 032. **См. также:** `./docs/files.md`.

> Документация и техническое задание на функционал «поделиться отдельным файлом» внутри модуля «Файлы» (витрина над Nextcloud, см. `./docs/files.md`, ADR-032). Документ описывает модель данных, резолв прав, API, фронтенд, уведомления, персистентность и статус реализации. Дополнительно описана отдельная подзадача — отображение создателя в управлении доступом к папкам (по образцу Базы знаний).

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/files/shares.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/components/files/FilesShareModal.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/files.py`) — восстановление при синхронизации |
| Хранилище | Nextcloud через `portal-svc` (авторизация на стороне портала, персистентный бэкап в `/data/settings/files-shares.json`) |
| Префикс API | `/api/v1` |
| ACL-кэш | Redis, ключи `files_share:{user_id}:{folder_id}:{filename_hash}` (TTL 300с) |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/files/shares.py` | API управления шерами файлов |
| Router Helpers | `./backend/app/api/files/_share_notify.py` | Рассылка inside-app и email уведомлений |
| Router Helpers | `./backend/app/api/files/_share_drift.py` | Отслеживание изменений (переименование, перемещение, удаление) |
| Service | `./backend/app/services/files_acl.py` | Резолв доступа к файлам (`require_file_access`) |
| Service | `./backend/app/services/files_shares_persistence.py` | Синхронизация шар с файлом `/data/settings/files-shares.json` |
| Model | `./backend/app/models/files.py` | Описание модели `FileShare` |
| Schema | `./backend/app/schemas/files.py` | Pydantic-схемы шар файлов |
| Frontend API | `./frontend/src/api/files.ts` | API-запросы для шеринга файлов |
| Frontend Components | `./frontend/src/components/files/FilesShareModal.vue` | Модалка шеринга отдельного файла |
| Frontend Pages | `./frontend/src/pages/admin/tabs/FileSharesTab.vue` | Панель администрирования шар файлов |

---

## 3. Модель данных

### Таблица `file_shares` (миграция `063`)

| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `folder_id` | UUID FK → `file_folders.id` `ON DELETE CASCADE` | папка-контейнер файла |
| `filename` | `String(500)` | имя файла (после `sanitize_name`) |
| `nc_path` | `String(2000)` | денормализованный `folder.nc_path + '/' + filename` — для персистентности и реестра |
| `subject_type` | `String(10)` | `'user'` \| `'group'` (CHECK) |
| `subject_id` | `String(255)` | Keycloak user-id / group-path / `__all_users__` |
| `subject_name` | `String(255)` | отображаемое имя на момент выдачи |
| `permission` | `String(20)` | `'viewer'` \| `'editor'` (CHECK). **`manager` на файл не выдаётся** |
| `shared_by` | UUID FK → `users.id` `ON DELETE SET NULL` | кто поделился |
| `expires_at` | `DateTime(tz)` NULL | опциональный TTL; NULL = бессрочно |
| `created_at` | `DateTime(tz)` | |
| `revoked_at` | `DateTime(tz)` NULL | мягкий отзыв (история сохраняется для аудита/«моих шеров») |

**Ограничения:**
- `UniqueConstraint(folder_id, filename, subject_id)` — повторная выдача = upsert (обновляет `permission`/`subject_name`, снимает `revoked_at`).
- `CheckConstraint subject_type IN ('user','group')`.
- `CheckConstraint permission IN ('viewer','editor')`.
- Индексы: `idx_file_shares_folder_filename (folder_id, filename)`, `idx_file_shares_subject_id (subject_id)`, `idx_file_shares_subject_active (subject_id, revoked_at)`, `idx_file_shares_expires_at (expires_at)`.

> **Решение по `manager` на файл:** на файл выдаются только `viewer`/`editor`. Управление шарами файла — прерогатива менеджера папки, а не получателя.

---

## 4. Модель прав (ACL)

### Уровни на файл

| Уровень | Что разрешает |
|---|---|
| `viewer` | `GET /files/preview`, `GET /files/download`, открытие в Collabora **read-only** (`can_write=false`) |
| `editor` | всё из `viewer` + Collabora **read/write** (`can_write=true`). Скачивание входит в «редактирование» по решению заказчика |

`editor` на файл = «Collabora + скачивание». Удаление/перемещение/переименование файла шара **не даёт** — это операции владельца папки.

### Эффективный доступ к файлу = max(folder ACL, file share)

При запросе байтов файла резолвер берёт **лучшее** из двух источников:

1. **Folder ACL** — `resolve_folder_permission(user, folder)` (текущая логика: admin→manager, creator→manager, рекурсивный CTE вверх по дереву). Даёт доступ ко всем файлам папки.
2. **File share** — активная (`revoked_at IS NULL` и (`expires_at IS NULL` OR `expires_at > now`)) запись `file_shares` для `(folder_id, filename)` по любому из `subject_ids_for_user(user)` (включает `user.id`, `keycloak_id`, группы Keycloak, `__all_users__` — см. `./backend/app/services/acl_base.py`).

Итог: `effective = max_rank(folder_perm, file_share_perm)`. Если оба `None` → 403.

> **Группы в «Доступные мне»:** так как резолв шары идёт по `subject_ids_for_user` (включая группы пользователя), файл, расшаренный на группу, виден всем её участникам.

### Функции проверки доступа

`require_file_access(user, folder, filename, required, db, redis) -> str` в `./backend/app/services/files_acl.py`:
- вычисляет `folder_perm` (через существующий резолвер) и `file_share_perm` (новый запрос с кэшем);
- возвращает эффективный уровень или бросает 403.

Точки вызова (заменяют текущий `require_folder_permission(..., "viewer")` на `require_file_access(...)`):
- `./backend/app/api/files/download.py` → `download_file` (`viewer`), `preview_file` (`viewer`).
- `./backend/app/api/files/upload.py` → `open_in_collabora` (`viewer`, `can_write` = `editor`+).

Листинг папки (`./backend/app/api/files/folders.py`) НЕ меняется: шара даёт доступ к конкретному файлу, но папка в общем дереве у получателя не появляется (он попадает к файлу через раздел «Доступные мне»).

### Кэш

Ключ `files_share:{user_id}:{folder_id}:{filename_hash}` (TTL 300с, по аналогии с `files_acl:*`). Инвалидация при выдаче/отзыве/изменении шары и при удалении/перемещении/переименовании файла.

---

## 5. REST API

Все пути под `/api/v1`, тег `files`, защита `ModuleCheck`. Новый подмодуль `./backend/app/api/files/shares.py`, включается в агрегатор `./backend/app/api/files/__init__.py`.

### Управление шарами файла (менеджер папки)

| Метод | Путь | Право | Тело / параметры | Ответ |
|---|---|---|---|---|
| `POST` | `/files/folders/{folder_id}/files/{filename}/shares` | manager папки | `{subject_type, subject_id, subject_name, permission(viewer\|editor), expires_in_days?}` | `201 FileSharePublic` (upsert) |
| `GET` | `/files/folders/{folder_id}/files/{filename}/shares` | manager папки | — | `{items: FileSharePublic[]}` (активные) |
| `DELETE` | `/files/folders/{folder_id}/files/{filename}/shares/{share_id}` | manager папки | — | `204` (мягкий отзыв: `revoked_at = now`) |

`filename` передаётся URL-энкодом; на бэке `sanitize_name`. Существование файла в NC проверяется при создании шары (PROPFIND/HEAD) → 404, если файла нет.

### «Мои шеры» и «Доступные мне»

| Метод | Путь | Право | Ответ |
|---|---|---|---|
| `GET` | `/files/shares/my` | любой авторизованный | `{items: MyFileShare[]}` — что я (как `shared_by`) расшарил; активные |
| `GET` | `/files/shares/shared-with-me` | любой авторизованный | `{items: SharedFile[]}` — файлы, расшаренные мне (по `subject_ids_for_user`, активные, не просроченные) |

`SharedFile` содержит достаточно для открытия: `id, folder_id, filename, nc_path, folder_name, permission, shared_by_name, created_at, expires_at`. Эти эндпоинты возвращают данные для прямого `download/preview/open` (которые сами перепроверяют `require_file_access`).

### Реестр для администратора

| Метод | Путь | Право | Ответ |
|---|---|---|---|
| `GET` | `/files/admin/shares` | admin | пагинированный реестр всех шеров: `subject`, `permission`, `nc_path`, `folder_name`, `shared_by`, `created_at`, `expires_at`, `revoked_at`. Фильтры: по `subject_id`, по `folder_id`, `active_only`. |

### Pydantic-схемы (в `./backend/app/schemas/files.py`)

- `CreateFileShareRequest{subject_type, subject_id, subject_name, permission, expires_in_days?}`
- `FileSharePublic{id, folder_id, filename, subject_type, subject_id, subject_name, permission, shared_by, created_at, expires_at}`
- `FileShareList{items}`
- `MyFileShare{... + folder_name}`, `SharedFile{...}`

Subject-поиск переиспользует существующий `GET /files/users/search` (users + groups + «Все пользователи»).

---

## 6. Персистентность (переживание wipe БД)

Шары дублируются во внешний файл `/data/settings/files-shares.json`.
- Ключ = `nc_path` файла, значение = список записей `{subject_type, subject_id, subject_name, permission, expires_at}`.
- Реализовано в `./backend/app/services/files_shares_persistence.py` (atomic write через tempfile+`os.replace`, chmod 0600). Конкурентный доступ защищён двухуровнево (F4): per-process `asyncio.Lock` (fast-path) + межпроцессный `interprocess_lock` (`./backend/app/services/_persistence_lock.py`, `fcntl.flock` на `files-shares.lock`), который держится на весь цикл read-modify-write — параллельные воркеры не затирают правки друг друга.
- Запись — при каждом create/upsert/revoke шары.

**Восстановление.** На старте воркера (`startup_sync_nc_folders` в `./backend/app/worker/tasks/files.py`) после создания папки и восстановления folder-ACL — дополнительно восстановить шары файлов из `/data/settings/files-shares.json` для файлов, чей `nc_path` начинается с `folder.nc_path + '/'`. `INSERT ... ON CONFLICT DO NOTHING`, `shared_by=NULL`. Просроченные (`expires_at < now`) не восстанавливаются.

---

## 7. Фронтенд

### 7.1 Кнопка «Поделиться» на файле
В `./frontend/src/components/files/FilesTable.vue` (строка/контекстное меню файла) — действие «Поделиться», видимое только при `folder.permission === 'manager'` (или admin). Открывает модалку `./frontend/src/components/files/FilesShareModal.vue`:
- поиск получателя (`GET /files/users/search`) — user/group/«Все пользователи»;
- переключатель «Просмотр / Редактирование» (`viewer`/`editor`);
- опциональный TTL (нет / N дней);
- список текущих получателей файла (`GET .../shares`) с возможностью отозвать (✕);
- НЕТ опции «разрешить пересылку» (re-sharing отсутствует).

API-клиент: функции в `./frontend/src/api/files.ts` + обёртки в `./frontend/src/queries/files.ts`.

### 7.2 «С кем я поделился» / «Доступные мне»
- **Мои шеры:** вкладка на `./frontend/src/pages/FilesPage.vue` или в сайдбаре (`./frontend/src/components/files/FilesSidebar.vue`), данные из `/files/shares/my`. Показывает файл, получателя, уровень, дату/TTL, кнопку «отозвать».
- **Доступные мне:** отдельный псевдо-раздел в сайдбаре (`./frontend/src/components/files/FilesSidebar.vue`), данные из `/files/shares/shared-with-me`. Клик по файлу → открыть/скачать/Collabora через стандартные эндпоинты (право проверяется на бэке). Папка-контейнер в общем дереве не показывается.

### 7.3 Реестр администратора
Раздел в админ-части (`./frontend/src/pages/admin/tabs/FileSharesTab.vue`) — таблица из `/files/admin/shares` с фильтрами и пагинацией.

---

## 8. Уведомления получателю

- **Портал:** in-app уведомление при создании шары (существующий механизм нотификаций/SSE). Тип события `files.file_shared`.
- **Email:** письмо получателю (для групп — участникам/по правилам рассылки) через существующий механизм почты (`email_outbox`). Шаблон: «С вами поделились файлом „{filename}“ ({permission}) от {shared_by_name}», ссылка в раздел «Доступные мне».
- По умолчанию — in-app всем участникам, email — участникам, если это не «Все пользователи».

---

## 9. Подзадача: отображение создателя в управлении доступом к папкам

В модалке прав папки показывается **создатель папки** с бейджем «Создатель», без возможности менять/удалять его право.

**Эталон — БЗ:** `./backend/app/api/kb/permissions.py` (`_build_creator_entry`, `_merge_creator`) и `./frontend/src/components/KbPermissionsModal.vue` (`p.is_creator` → `n-tag` «Создатель»).

**Backend (`./backend/app/api/files/permissions.py`):**
- В `list_permissions` (`GET /files/folders/{id}/permissions`) добавлена запись создателя: по `folder.created_by` подтягивается `User`, отдается первым элементом с флагом `is_creator=true`, `permission='manager'`, `id=None`.
- Расширен `PermissionPublic` (или `PermissionEntry`) полями `email: str | None = None`, `is_creator: bool = False`, `id` сделан `Optional`.
- В `grant_permission`/`revoke_permission` — запрет менять/удалять право создателя (409: «Cannot modify/revoke creator's permission»).

**Frontend (`./frontend/src/components/files/FilesPermissionsModal.vue`):**
- Рендер строки создателя с `n-tag type="success"` «Создатель», скрытие селекта уровня и кнопки удаления при `is_creator`.
- тип `FilePermission` в `./frontend/src/api/files.ts` дополнен `email`, `is_creator`, `id: string | null`.

---

## 10. Краевые случаи и дрейф

| Случай | Поведение |
|---|---|
| Файл удалён/перемещён/переименован через портал | Отозвать/перенести связанные шары: при удалении — `revoked_at=now` + удалить из `/data/settings/files-shares.json`; при move/rename — обновить `folder_id`/`filename`/`nc_path` шар. Реализовано в `./backend/app/api/files/files_ops.py` через `./backend/app/api/files/_share_drift.py`. |
| Файл изменён напрямую в NC (мимо портала) | Шара остаётся по `nc_path`; если файла нет — `download/preview/open` вернут 404 от NC. |
| Удалена папка (soft-delete через портал) | F5: при `delete_folder` (`./backend/app/api/files/folders.py`) активные шары всего поддерева (корень + потомки, рекурсивный CTE) мягко отзываются `revoked_at=now` в той же транзакции, иначе у получателей в «Доступные мне» висели бы битые ссылки на удалённую папку. Кэш шар поддерева сбрасывается `invalidate_file_share_folder_cache`; из `/data/settings/files-shares.json` записи чистятся `drop_file_shares_under_prefix`. Списки «мои шеры»/«доступные мне» дополнительно фильтруют `FileFolder.deleted_at IS NULL` (defense-in-depth). При `hard=true` срабатывает `ON DELETE CASCADE`. |
| Получатель уже имеет доступ через folder ACL | Шара избыточна, но не вредит; `effective` берет max. |
| Шара на «Все пользователи» | Доступна всем; в UI можно предупреждать. |
| Просроченная шара | Не дает доступа (фильтр по `expires_at`); запись остается для аудита, пока не отозвана/не очищена. |
| Коллизия имён при move | `bulk-move` умеет переименование (`new_name`); шара следует за новым именем. |

---

## 11. Статус реализации

Все этапы технического задания полностью реализованы, протестированы и интегрированы в кодовую базу.

- [x] **Миграция + модель:** Создана таблица `file_shares` (миграция `063`) в `./backend/app/models/files.py`.
- [x] **Резолвер:** Метод `require_file_access` с кэшем и инвалидацией реализован в `./backend/app/services/files_acl.py`.
- [x] **API шар:** Реализованы эндпоинты в `./backend/app/api/files/shares.py` + Pydantic-схемы в `./backend/app/schemas/files.py`.
- [x] **Персистентность:** Реализован `./backend/app/services/files_shares_persistence.py` для синхронизации с `/data/settings/files-shares.json`, а также восстановление при запуске.
- [x] **Дрейф:** Обработка перемещений и удалений встроена в `./backend/app/api/files/files_ops.py` через функции из `./backend/app/api/files/_share_drift.py`.
- [x] **Фронтенд:** Создана модалка `./frontend/src/components/files/FilesShareModal.vue`, обновлены страницы `./frontend/src/pages/FilesPage.vue` и сайдбар `./frontend/src/components/files/FilesSidebar.vue`.
- [x] **Уведомления:** SSE и Email-рассылки реализованы в `./backend/app/api/files/_share_notify.py`.
- [x] **Подзадача «Создатель»:** Реализовано в `./backend/app/api/files/permissions.py` и модалке `./frontend/src/components/files/FilesPermissionsModal.vue`.

---

## Безопасность

- **Проверка прав:** Любые действия создания, просмотра или отзыва шар файлов требуют прав уровня `manager` на папку-контейнер. Получатели шары не могут передавать доступ дальше (re-sharing заблокирован).
- **Ограничение частоты запросов (Rate Limiting):** На эндпоинт создания шары установлен лимит `20/min`.
- **Санитизация:** Имя файла принудительно очищается через функцию `sanitize_name` перед любой обработкой и проверкой прав.

---

## События аудита

Реализована запись событий аудита через вызов `_emit_audit` (интегрирован с `push_audit_event`):
- `files.file_shared` — при создании новой шары на файл.
- `files.file_share_updated` — при обновлении существующей шары.
- `files.file_share_revoked` — при отзыве шары.

Метаданные событий включают: `folder_id`, `subject_id`, `permission`, `nc_path` и `share_id`.

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./backend/tests/unit/test_file_shares_acl.py` | Логика резолвера `require_file_access`, учет TTL, отзывов, кэширования и кэш-инвалидации |
| Unit | `./backend/tests/unit/test_files_shares_persistence.py` | Запись и чтение `/data/settings/files-shares.json`, атомарность, создание резервных копий |
| Unit | `./backend/tests/unit/test_files_permissions_creator.py` | Логика отображения создателя папки в правах доступа, мерджинг и запреты (409) на модификацию |

---

## Связанные документы

- `./docs/files.md` — Базовая архитектура файлового модуля
- `./docs/roles-matrix.md` — Матрица ролей и доступов портала
- `./docs/db-schema.md` — Схема базы данных
- `./docs/api-contracts.md` — Контракты REST API
