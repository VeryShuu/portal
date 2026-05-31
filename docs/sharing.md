# ТЗ: Пофайловый шеринг в модуле «Файлы»

> Техническое задание на функционал «поделиться отдельным файлом» внутри модуля Файлы (витрина над Nextcloud, см. `./docs/files.md`, ADR-032). Документ описывает модель данных, резолв прав, API, фронтенд, уведомления, персистентность и план реализации. Дополнительно описана отдельная подзадача — отображение создателя в управлении доступом к папкам (по образцу Базы знаний).

---

## 1. Контекст и проблема

### Сценарий пользователя

Сотрудник отдела кадров (HR) ведёт папку `Отдел кадров` с 4 подпапками, внутри — файлы. Ему нужно дать сотруднику бухгалтерии доступ **к одному конкретному файлу** в подпапке, не открывая всю папку/подпапку.

Требования с точки зрения ролей:

| Роль | Потребность |
|---|---|
| HR-сотрудник (даёт доступ) | Кнопка «Поделиться» на файле → вбить ФИО/группу → выбрать «просмотр» или «редактирование». Без знания механики ACL. Потом видеть список «С кем я поделился». |
| Бухгалтер (получает доступ) | Видеть у себя раздел «Доступные мне» с файлом, открыть/скачать/(ред.) — без доступа к остальным файлам папки. |
| Администратор | Не ковыряться в правах ради одного файла, но видеть реестр всех шеров (кто/кому/что) + аудит. |

### Почему текущая модель не покрывает

Сейчас права гранулярны **только на уровне папки** (`file_folder_permissions`, `viewer/editor/manager`, наследование вверх по дереву — см. `./backend/app/services/files_acl.py`). Чтобы дать доступ к одному файлу, пришлось бы либо открывать всю папку, либо городить под каждый файл отдельную подпапку. Нужен механизм прав **на уровне отдельного файла**.

---

## 2. Архитектурное решение (Вариант A — ACL на слое портала)

**Принцип:** все операции с байтами файла (`download`, `preview`, `open` в Collabora, в перспективе — удаление/перемещение) проходят через эндпоинты портала под единственным сервисным аккаунтом `portal-svc`. Поэтому права на файл **проверяются и хранятся на стороне портала**, в Nextcloud ничего не меняется (ни NC-шары, ни NC-ACL). Это полностью согласуется с ADR-032 (Вариант A: единый service account, права в БД портала).

**Идентификация файла.** Файл адресуется как `(folder_id, filename)` → канонический `nc_path = folder.nc_path + '/' + sanitize_name(filename)`. `nc_path` файла — стабильный ключ шары (как и для папок в `files-acl.json`). У файла нет собственного UUID в дереве; `file_items` лишь трекает загрузки и не обязателен (файлы, залитые мимо портала, записи не имеют). Поэтому шара ссылается на `folder_id + filename`, а `nc_path` хранится денормализованно для персистентности и реконструкции.

**Прецедент.** Похожий механизм share-токенов уже есть в фото (`./backend/app/api/photos/sharing.py`): таблицы токенов, `my-shares`, отзыв, TTL, аудит. Здесь — НЕ публичные токены, а адресные внутренние шары (конкретным user/group), поэтому модель ближе к `file_folder_permissions`, но на файл.

---

## 3. Модель данных

### Новая таблица `file_shares` (миграция `0XX`)

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
- Индексы: `(folder_id, filename)`, `subject_id`, `(subject_id, revoked_at)` (для «доступные мне»), `expires_at` (очистка).

> **Решение по `manager` на файл:** на файл выдаются только `viewer`/`editor`. Управление шарами файла — прерогатива менеджера папки (см. §5), а не получателя.

---

## 4. Семантика прав

### Уровни на файл

| Уровень | Что разрешает |
|---|---|
| `viewer` | `GET /files/preview`, `GET /files/download`, открытие в Collabora **read-only** (`can_write=false`) |
| `editor` | всё из `viewer` + Collabora **read/write** (`can_write=true`). Скачивание входит в «редактирование» по решению заказчика |

`editor` на файл = «Collabora + скачивание» (подтверждено заказчиком). Удаление/перемещение/переименование файла шара **не даёт** — это операции владельца папки.

### Эффективный доступ к файлу = max(folder ACL, file share)

При запросе байтов файла резолвер берёт **лучшее** из двух источников:

1. **Folder ACL** — `resolve_folder_permission(user, folder)` (текущая логика: admin→manager, creator→manager, рекурсивный CTE вверх по дереву). Даёт доступ ко всем файлам папки.
2. **File share** — активная (`revoked_at IS NULL` и (`expires_at IS NULL` OR `expires_at > now`)) запись `file_shares` для `(folder_id, filename)` по любому из `subject_ids_for_user(user)` (включает `user.id`, `keycloak_id`, группы Keycloak, `__all_users__` — см. `./backend/app/services/acl_base.py`).

Итог: `effective = max_rank(folder_perm, file_share_perm)`. Если оба `None` → 403.

> **Группы в «Доступные мне»:** так как резолв шары идёт по `subject_ids_for_user` (включая группы пользователя), файл, расшаренный на группу, виден всем её участникам (подтверждено заказчиком).

### Новый хелпер

`require_file_access(user, folder, filename, required, db, redis) -> str` в `./backend/app/services/files_acl.py`:
- вычисляет `folder_perm` (через существующий резолвер) и `file_share_perm` (новый запрос с кэшем);
- возвращает эффективный уровень или бросает 403.

Точки вызова (заменить текущий `require_folder_permission(..., "viewer")` на `require_file_access(...)`):
- `./backend/app/api/files/download.py` → `download_file` (`viewer`), `preview_file` (`viewer`).
- `./backend/app/api/files/upload.py` → `open_in_collabora` (`viewer`, `can_write` = `editor`+).

Листинг папки (`folders.py`) НЕ меняется: шара даёт доступ к конкретному файлу, но папка в общем дереве у получателя не появляется (он попадает к файлу через раздел «Доступные мне», см. §6).

### Кэш

Ключ `files_share:{user_id}:{folder_id}:{filename_hash}` (TTL 300с, по аналогии с `files_acl:*`). Инвалидация при выдаче/отзыве/изменении шары и при удалении/перемещении/переименовании файла. Допускается простой вариант — инвалидация всех `files_share:*` по subject при изменении (точечная предпочтительнее).

---

## 5. Правила доступа к управлению шарами

| Действие | Кто может |
|---|---|
| Поделиться файлом (создать/изменить шару) | **Только `manager` на папке** этого файла (или admin). **Не `editor`.** |
| Посмотреть «С кем поделились этим файлом» | `manager` папки + admin |
| Отозвать шару файла | `manager` папки + admin (и сам автор шары, если он ещё manager) |
| Re-sharing (получатель делится дальше) | **Запрещён и недоступен в принципе** — у получателя нет UI и нет права; эндпоинт шеринга всегда требует `manager` на папке |

> Это **переопределяет** ранее предложенный «editor+». Делиться могут только менеджеры папки (подтверждено заказчиком). Поскольку `manager` на файл не выдаётся, получатель файла никогда не получит право шерить — re-sharing невозможен by design.

TTL: опциональный, аналогично фото — рантайм-капа из настроек модуля (`files.max_share_ttl_days`, если решим добавить; иначе без капы). Просроченные шары не удаляются немедленно, но не дают доступа; фоновая очистка — опционально.

---

## 6. API

Все пути под `/api/v1`, тег `files`, защита `ModuleCheck`. Новый подмодуль `./backend/app/api/files/shares.py`, включается в агрегатор `./backend/app/api/files/__init__.py`.

### Управление шарами файла (менеджер папки)

| Метод | Путь | Право | Тело / параметры | Ответ |
|---|---|---|---|---|
| `POST` | `/files/folders/{folder_id}/files/{filename}/shares` | manager папки | `{subject_type, subject_id, subject_name, permission(viewer\|editor), expires_in_days?}` | `201 FileSharePublic` (upsert) |
| `GET` | `/files/folders/{folder_id}/files/{filename}/shares` | manager папки | — | `{items: FileSharePublic[]}` (активные) |
| `DELETE` | `/files/folders/{folder_id}/files/{filename}/shares/{share_id}` | manager папки | — | `204` (мягкий отзыв: `revoked_at = now`) |

`filename` передаётся URL-энкодом; на бэке `sanitize_name`. Существование файла в NC проверяется при создании шары (PROPFIND/HEAD) → 404, если файла нет.

Rate-limit на создание шары: по образцу прочих write-операций (например `20/min`). Идемпотентность — через `UniqueConstraint` (upsert).

### «Мои шеры» и «Доступные мне»

| Метод | Путь | Право | Ответ |
|---|---|---|---|
| `GET` | `/files/shares/my` | любой авторизованный | `{items: MyFileShare[]}` — что я (как `shared_by`) расшарил; активные |
| `GET` | `/files/shares/shared-with-me` | любой авторизованный | `{items: SharedFile[]}` — файлы, расшаренные мне (по `subject_ids_for_user`, активные, не просроченные) |

`SharedFile` содержит достаточно для открытия: `folder_id, filename, nc_path, folder_name, permission, shared_by_name, mime_type?, size_bytes?, created_at, expires_at`. Эти эндпоинты возвращают данные для прямого `download/preview/open` (которые сами перепроверяют `require_file_access`).

### Реестр для администратора

| Метод | Путь | Право | Ответ |
|---|---|---|---|
| `GET` | `/files/admin/shares` | admin | пагинированный реестр всех шеров: `subject`, `permission`, `nc_path`, `folder_name`, `shared_by`, `created_at`, `expires_at`, `revoked_at`. Фильтры: по `subject_id`, по `folder_id`, `active_only`. |

Аудит (через `push_audit_event`, как в `permissions.py`): события `files.file_shared`, `files.file_share_revoked`, `files.file_share_updated` (с `metadata`: `subject_id`, `permission`, `nc_path`). Реестр для admin = таблица `file_shares`; аудит-лента = существующий механизм аудита.

### Pydantic-схемы (в `./backend/app/schemas/files.py`)

- `CreateFileShareRequest{subject_type, subject_id, subject_name, permission, expires_in_days?}`
- `FileSharePublic{id, folder_id, filename, subject_type, subject_id, subject_name, permission, shared_by, created_at, expires_at}`
- `FileShareList{items}`
- `MyFileShare{... + folder_name}`, `SharedFile{...}` (см. выше)

Subject-поиск переиспользует существующий `GET /files/users/search` (users + groups + «Все пользователи»).

---

## 7. Персистентность (переживание wipe БД)

Шары **дублируются в файл** по образцу `files-acl.json` (подтверждено заказчиком). Варианты:

- **(предпочтительно)** отдельный файл `/data/settings/files-shares.json`, ключ = `nc_path` файла, значение = список записей `{subject_type, subject_id, subject_name, permission, expires_at}`. Новый модуль `./backend/app/services/files_shares_persistence.py` по аналогии с `files_acl_persistence.py` (atomic write через tempfile+`os.replace`, chmod 0600, `asyncio.Lock`).

Запись — при каждом create/upsert/revoke шары (как `save_folder_perms` в `permissions.py`).

**Восстановление.** На старте воркера (`startup_sync_nc_folders`, `./backend/app/worker/tasks/files.py`) после создания папки и восстановления folder-ACL — дополнительно восстановить шары файлов из `files-shares.json` для файлов, чей `nc_path` начинается с `folder.nc_path + '/'`. `INSERT ... ON CONFLICT DO NOTHING`, `shared_by=NULL`. Просроченные (`expires_at < now`) не восстанавливаем.

---

## 8. Фронтенд

### 8.1 Кнопка «Поделиться» на файле

В `./frontend/src/components/files/FilesTable.vue` (строка/контекстное меню файла) — действие «Поделиться», видимое только при `folder.permission === 'manager'` (или admin). Открывает новую модалку `FilesShareModal.vue`:

- поиск получателя (`GET /files/users/search`) — user/group/«Все пользователи»;
- переключатель «Просмотр / Редактирование» (`viewer`/`editor`);
- опциональный TTL (нет / N дней);
- список текущих получателей файла (`GET .../shares`) с возможностью отозвать (✕);
- НЕТ опции «разрешить пересылку» (re-sharing отсутствует).

API-клиент: добавить функции в `./frontend/src/api/files.ts` + обёртки в `./frontend/src/queries/files.ts`.

### 8.2 «С кем я поделился» / «Доступные мне»

- **Мои шеры:** вкладка/раздел на `./frontend/src/pages/FilesPage.vue` или в сайдбаре (`FilesSidebar.vue`), данные из `/files/shares/my`. Показывает файл, получателя, уровень, дату/TTL, кнопку «отозвать».
- **Доступные мне:** отдельный псевдо-раздел в сайдбаре (как «Избранное»), данные из `/files/shares/shared-with-me`. Клик по файлу → открыть/скачать/Collabora через стандартные эндпоинты (право проверяется на бэке). Папка-контейнер в общем дереве не показывается.

### 8.3 Реестр администратора

Раздел в админ-части (рядом с прочими admin-инструментами файлов) — таблица из `/files/admin/shares` с фильтрами и пагинацией.

### 8.4 Уведомления получателю

- **Портал:** in-app уведомление при создании шары (существующий механизм нотификаций/SSE). Тип события `files.file_shared`.
- **Email:** письмо получателю (для групп — участникам/по правилам рассылки) через существующий механизм почты (`email_outbox`). Шаблон: «С вами поделились файлом „{filename}“ ({permission}) от {shared_by_name}», ссылка в раздел «Доступные мне».

> Детализация рассылки на группу (всем участникам vs. только in-app) уточняется на этапе реализации; по умолчанию — in-app всем участникам, email — участникам, если это не «Все пользователи».

---

## 9. Подзадача: отображение создателя в управлении доступом к папкам

Отдельный, независимый функционал (как в Базе знаний, см. скрин в задаче). В модалке прав папки показать **создателя папки** с бейджем «Создатель», без возможности менять/удалять его право.

**Эталон — БЗ:** `./backend/app/api/kb/permissions.py` (`_build_creator_entry`, `_merge_creator`) и `./frontend/src/components/KbPermissionsModal.vue` (`p.is_creator` → `n-tag` «Создатель», скрытие `n-select`/кнопки удаления).

**Backend (`./backend/app/api/files/permissions.py`):**
- В `list_permissions` (`GET /files/folders/{id}/permissions`) добавить запись создателя: по `folder.created_by` подтянуть `User`, отдать первым элементом с флагом `is_creator=true`, `permission='manager'`, `id=None`.
- Расширить `PermissionPublic` (или новую `PermissionEntry`) полями `email: str | None = None`, `is_creator: bool = False`, сделать `id` Optional — **по образцу `PermissionEntry` из `./backend/app/schemas/kb_extra.py`**.
- В `grant_permission`/`revoke_permission` — запрет менять/удалять право создателя (409, как в KB: «Cannot modify/revoke creator's permission»).

**Frontend (`./frontend/src/components/files/FilesPermissionsModal.vue`):**
- Рендер строки создателя с `n-tag type="success"` «Создатель», скрытие селекта уровня и кнопки удаления при `is_creator`.
- Тип `FilePermission` в `./frontend/src/api/files.ts` дополнить `email`, `is_creator`, `id: string | null`.
- i18n-ключ `files.permissions.creator` (рус. «Создатель») — добавить в локали по образцу `kb.permissions.creator`.

> Не ломать форму ответа для существующих клиентов: новые поля имеют дефолты; запись создателя дедуплицируется (если создатель уже есть в `file_folder_permissions` как user — мерджим, как `_merge_creator` в KB).

---

## 10. Краевые случаи и дрейф

| Случай | Поведение |
|---|---|
| Файл удалён/перемещён/переименован через портал | Отозвать/перенести связанные шары: при удалении — `revoked_at=now` + удалить из `files-shares.json`; при move/rename — обновить `folder_id`/`filename`/`nc_path` шар. (`files_ops.py`, `bulk-move`/`delete`.) |
| Файл изменён напрямую в NC (мимо портала) | Шара остаётся по `nc_path`; если файла нет — `download/preview/open` вернут 404 от NC. Допустимо. |
| Удалена папка | `ON DELETE CASCADE` уберёт шары из БД; из `files-shares.json` — чистить при portal-side удалении папки (как `drop_folder_perms`). |
| Получатель уже имеет доступ через folder ACL | Шара избыточна, но не вредит; `effective` берёт max. |
| Шара на «Все пользователи» | Технически возможна; в UI можно предупреждать («файл станет доступен всем»). |
| Просроченная шара | Не даёт доступа (фильтр по `expires_at`); запись остаётся для аудита, пока не отозвана/не очищена. |
| Коллизия имён при move | `bulk-move` уже умеет переименование (`new_name`); шара должна следовать за новым именем. |

---

## 11. План реализации (поэтапно)

1. **Миграция + модель.** `file_shares` (`./backend/app/models/files.py` + новая миграция `0XX`).
2. **Резолвер.** `require_file_access` + кэш + инвалидация в `./backend/app/services/files_acl.py`; переключить `download/preview/open` на него.
3. **API шар.** `./backend/app/api/files/shares.py` (create/list/revoke, my, shared-with-me, admin) + схемы + включение в агрегатор + аудит.
4. **Персистентность.** `./backend/app/services/files_shares_persistence.py` + запись из эндпоинтов + восстановление в воркере.
5. **Дрейф.** Обновление/отзыв шар в `files_ops.py` (delete/move/rename).
6. **Фронтенд.** `FilesShareModal.vue`, кнопка в `FilesTable.vue`, разделы «Мои шеры»/«Доступные мне», admin-реестр, API/queries.
7. **Уведомления.** in-app + email на создание шары.
8. **Подзадача «Создатель».** backend `permissions.py` + схема + `FilesPermissionsModal.vue` + i18n (можно делать независимо/первым — мелкий и изолированный).
9. **Тесты + регенерация авто-доков** (`openapi.json`, `*.generated.md`), обновление `./docs/files.md`, `./docs/api-contracts.md` §3.6, `./docs/roles-matrix.md`.

---

## 12. Тестирование

- **Unit (ACL):** `require_file_access` — max(folder, share); просрочка; отзыв; группа/`__all_users__`; admin; creator.
- **API:** create/list/revoke только manager (editor/viewer → 403); upsert; 404 на несуществующий файл; `my`/`shared-with-me`; admin-реестр; TTL-капа.
- **Персистентность:** запись/чтение `files-shares.json`, восстановление в `startup_sync` (`ON CONFLICT DO NOTHING`, пропуск просроченных), atomic-write.
- **Дрейф:** delete/move/rename файла → корректное состояние шар.
- **Подзадача:** `list_permissions` отдаёт создателя первым с `is_creator`; запрет 409 на изменение/удаление; дедуп.
- **Frontend:** видимость кнопки «Поделиться» только для manager; модалка; разделы; рендер бейджа «Создатель».

---

## 13. Вне рамок / открытые вопросы

- **Публичные ссылки на файл** (без авторизации, по токену) — НЕ в этом ТЗ (есть прецедент в фото, можно добавить отдельно).
- **`manager` на файл / делегирование шеринга получателю** — сознательно исключено (re-sharing запрещён).
- **Капа TTL** (`files.max_share_ttl_days`) — добавлять ли настройку модуля: уточнить (по умолчанию без капы).
- **Рассылка email на группу** — всем участникам или дайджест: уточнить на этапе реализации.
