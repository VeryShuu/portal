# Справочники объектов (вкладки в /staff)

> **Когда читать:** «справочник судов/складов/гаражей», таблицы `object_directories` / `object_directory_entries` / `object_entry_contacts`, конструктор полей/каналов, экспорт CSV/XLSX/PDF, мастер-флаг `directories`.
> **Ключевой код:** `app/api/directories.py`, `app/services/directories.py`, `frontend/src/pages/staff/DirectoryTab.vue`.
> **ADR:** —. **См. также:** `staff-directory-spec.md`, `search.md`, `db-schema.md`, `roles-matrix.md`.

Универсальный движок справочников объектов с контактами. Один и тот же
движок обслуживает любые «перечни объектов компании»: первый кейс — **«Флот»**
(электронная замена бумажного «ПЕРЕЧНЯ СУДОВ КОМПАНИИ»: суда с
IMO/позывным/MMSI и каналами связи V-SAT/Iridium/Inmarsat/email/mobile в
разрезе ролей), но та же структура переиспользуется под «Склады», «Гаражи»,
«Здания» и т.д.

Раздел НЕ является отдельным модулем-страницей: справочники встраиваются
**вкладками в существующий раздел `/staff`** (`?tab=<slug>`) рядом с вкладкой
«Сотрудники».

---

## 1. Концепция и доступ

- **Тип справочника** (= вкладка) создаёт и настраивает admin/editor: задаёт
  название вкладки, иконку, **схему полей идентификации** (`field_schema`) и
  **набор каналов связи** (`channels`). «Флот» — предзаполненный тип (сид в
  миграции), не хардкод.
- **Объект** (судно/склад/…) имеет имя, привязку к папке раздела `/files`
  (`folder_id` → `file_folders`), значения полей (`attributes`), заметку и
  список контактов.
- **Контакт** — строка «роль × канал × значение» (например «Мостик · V-SAT
  (доб.): 262»). Контакты только отображаются и копируются — без `tel:`/`mailto:`.

| Действие | Кто может |
|---|---|
| Просмотр вкладок, объектов, контактов, экспорт | любой авторизованный |
| Создание/изменение/удаление типов, объектов, контактов | `editor` / `admin` |

Подробности по правам — `./docs/roles-matrix.md`.

### Двухуровневый гейтинг видимости

1. **Мастер-флаг модуля** `modules.json → directories.enabled` (как у
   `meetings`/`photos`). Выключен → весь раздел `/api/v1/directories/*`
   отвечает `404`, вкладки-справочники в `/staff` не показываются, тип
   `directory_entry` исключается из глобального поиска.
2. **Per-type `enabled`** на самом типе. Выключенный тип скрыт для обычных
   пользователей (его вкладка не отображается, объекты `404`), но остаётся
   видимым и управляемым для `editor`/`admin` (`list_directories(include_disabled=True)`).

---

## 2. Модель данных

3 таблицы (миграция `./backend/migrations/versions/064_object_directories.py`;
привязка к папке `/files` — `065_directory_entry_folder.py`,
модели — `./backend/app/models/object_directory.py`). Схема полей и набор
каналов хранятся как **JSONB на типе-справочнике** — низкая кардинальность,
редко меняются, добавление поля не требует миграции; валидация — на уровне
Pydantic (Literal), не БД-enum.

### `object_directories` — ТИП справочника (= вкладка)

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `slug` | `String(50)` UNIQUE | `fleet`, `warehouses`… (якорь вкладки `?tab=<slug>`) |
| `label_ru` | `String(100)` NOT NULL | название вкладки (рус) |
| `label_en` | `String(100)` NULL | название вкладки (англ) |
| `icon` | `String(50)` NULL | имя иконки |
| `description` | `String(500)` NULL | подсказка |
| `field_schema` | JSONB NOT NULL default `[]` | определения полей идентификации |
| `channels` | JSONB NOT NULL default `[]` | доступные каналы связи |
| `enabled` | `Boolean` NOT NULL default TRUE | показывать вкладку (per-type флаг) |
| `sort_order` | `Integer` NOT NULL default 0 | порядок вкладок |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |
| `deleted_at` | `TIMESTAMPTZ` NULL | soft-delete (тип) |

Индекс: `idx_object_directories_sort (sort_order)`.

Элемент `field_schema` (по образцу `UserAttributeMapping`):
```json
{ "key": "imo", "label_ru": "IMO", "label_en": "IMO",
  "type": "text", "required": false, "sort_order": 0 }
```
`type ∈ {text, number, email, url, multiline}` (Pydantic `Literal`). `key`
матчит `^[a-z][a-z0-9_]*$`, ключи уникальны в пределах типа.

Элемент `channels`:
```json
{ "key": "inmarsat", "label_ru": "Inmarsat", "label_en": "Inmarsat",
  "sort_order": 2 }
```

### `object_directory_entries` — ОБЪЕКТ

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | |
| `directory_id` | UUID FK→`object_directories.id` ON DELETE CASCADE | тип |
| `name` | `String(200)` NOT NULL | «Академик Казанин» / «Склад №3» |
| `folder_id` | UUID FK→`file_folders.id` ON DELETE SET NULL | привязанная папка раздела `/files` |
| `attributes` | JSONB NOT NULL default `{}` | значения полей: `{"imo":"9489481",…}` |
| `note` | `String(1000)` NULL | заметка |
| `sort_order` | `Integer` NOT NULL default 0 | |
| `created_by` | UUID FK→`users.id` ON DELETE SET NULL | |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |
| `deleted_at` | `TIMESTAMPTZ` NULL | soft-delete |

Индексы: `idx_ode_directory (directory_id, sort_order)`, `idx_ode_active (deleted_at)`,
`idx_ode_folder (folder_id)`.

### `object_entry_contacts` — роль × канал × значение

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | |
| `entry_id` | UUID FK→`object_directory_entries.id` ON DELETE CASCADE | |
| `role` | `String(100)` NULL | свободная строка: «Мостик», «Капитан»… |
| `channel` | `String(50)` NOT NULL | `key` из `directory.channels` |
| `label` | `String(200)` NULL | доп. подпись |
| `value` | `String(255)` NOT NULL | сам номер/почта/добавочный |
| `sort_order` | `Integer` NOT NULL default 0 | |

Индекс: `idx_oec_entry (entry_id, sort_order)`. E-mail хранится как
`String(255)`, **НЕ `EmailStr`** (DNS-проверка ломается на `.local`/корпоративных
доменах — известная грабля проекта).

> Контакты объекта **перезаписываются целиком** при `PATCH .../entries/{id}`
> с полем `contacts` (delete-orphan + пересоздание), а не диффятся по одному.

### Миграция и сид

`064` создаёт 3 таблицы + индексы и сидит тип **`fleet`** («Флот») с готовой
`field_schema` (IMO / позывной / MMSI / V-SAT основной / порядок набора) и
`channels` (V-SAT доб. / Iridium / Inmarsat / E-mail / Mobile), плюс
демонстрационный объект «Академик Казанин» с его контактами. Применяется
автоматически при старте backend (`migrate.sh`).

---

## 3. Backend

| Файл | Содержимое |
|---|---|
| `./backend/app/models/object_directory.py` | `ObjectDirectory`, `ObjectDirectoryEntry`, `ObjectEntryContact` |
| `./backend/app/schemas/object_directory.py` | Pydantic-схемы типов/полей/каналов/объектов/контактов + валидаторы (slug/key паттерны, уникальность ключей) |
| `./backend/app/services/directories.py` | бизнес-логика: CRUD типов/объектов, валидация `attributes` против `field_schema` и `channel` против `channels`, проверка существования `folder_id`, поиск по `name`, билдеры экспорта (CSV / XLSX / HTML-для-PDF) |
| `./backend/app/api/directories.py` | роутер; регистрация в `./backend/app/api/__init__.py` |
| `./backend/app/services/search/entities.py` | `search_directory_entries` (Cmd+K, по `name`) |
| `./backend/app/core/modules_config.py` | `DirectoriesModuleSettings(enabled=False)` + поле в `AllModuleSettings` |

### Эндпоинты (`/api/v1/directories`, тег `directories`)

**Типы** (мутации — `EditorDep`):

| Метод | Путь | Право | Назначение |
|---|---|---|---|
| `GET` | `/directories` | любой авторизованный | список типов; для editor/admin включает выключенные (`DirectoryList{items,total}`) |
| `POST` | `/directories` | editor | создать тип; `409` при дубле `slug` |
| `PATCH` | `/directories/{directory_id}` | editor | обновить тип (включая `field_schema`/`channels`) |
| `DELETE` | `/directories/{directory_id}` | editor | soft-delete типа |

**Объекты:**

| Метод | Путь | Право | Назначение |
|---|---|---|---|
| `GET` | `/directories/{slug}/entries` | любой авторизованный | `{items,total,limit,offset}`; `?q=` (только по `name`), `limit≤500`, сортировка по `sort_order, name` |
| `GET` | `/directories/{slug}/entries/{entry_id}` | любой авторизованный | объект с контактами |
| `POST` | `/directories/{slug}/entries` | editor | создать объект (валидация `attributes`/`channels`) |
| `PATCH` | `/directories/{slug}/entries/reorder` | editor | массово переписать `sort_order` (`{items:[{id,sort_order}]}`); `404`, если хоть один `id` не принадлежит активным объектам типа; `204` |
| `PATCH` | `/directories/{slug}/entries/{entry_id}` | editor | обновить объект; `contacts` перезаписываются целиком |
| `DELETE` | `/directories/{slug}/entries/{entry_id}` | editor | soft-delete объекта |
| `GET` | `/directories/{slug}/export?format=csv\|xlsx\|pdf` | любой авторизованный | выгрузка объектов типа |

`POST`/`PATCH` объекта принимают опц. `folder_id` (UUID существующей,
не-удалённой папки `/files`; иначе `422`).

Каждая мутация после успешного commit эмитит аудит-событие через
`make_audit_emitter("directory")` (`resource_type=directory`): события
`directories.type_created/updated/deleted`,
`directories.entry_created/updated/deleted`, `directories.entries_reordered`.

Полные контракты — `./docs/api-contracts.md` / `./docs/api-contracts.generated.md`.

### Валидация `attributes` и `channels`

`validate_attributes(field_schema, attributes)` (`services/directories.py`):
- отклоняет ключи, не объявленные в `field_schema` → `422`;
- требует непустого значения для `required`-полей → `422`;
- по `type`: `number` (парсится как float, допускается запятая), `email`
  (наличие `@` не в краях), `url` (`http://`/`https://`); `text`/`multiline`
  без доп. проверок;
- нормализует все значения в trimmed-строки.

`validate_channels(channels, contacts)` — каждый `contact.channel` обязан
присутствовать в `directory.channels`, иначе `422`.

### Привязка папки `/files`

У объекта нет внешней ссылки и аватара: вместо них — `folder_id` (FK на
`file_folders`, `ON DELETE SET NULL`). На фронте папка выбирается через
`n-tree-select` (дерево из `useFolderTreeQuery`); карточка показывает имя
папки (`folder_name`, eager-load relationship) ссылкой-роутером на
`/files?folder=<id>` (раздел `/files` читает `?folder=` в `onMounted` и
выделяет папку). Сервис проверяет, что переданный `folder_id` указывает на
существующую не-удалённую папку, иначе `422`.

### Экспорт

`build_export_table()` строит общие `(headers, rows)`: колонки = «Название» +
поля `field_schema` (по `sort_order`) + «Контакты» (свёрнуты в одну строку
`роль · канал: значение; …`) + «Заметка». На их основе:
- **CSV** — `;`-разделитель + UTF-8 BOM (чтобы Excel корректно открыл кириллицу);
- **XLSX** — `openpyxl` (зависимость уже в `pyproject.toml`, по образцу
  `app/api/users/staff_xlsx.py`): стилизованный заголовок, перенос текста,
  freeze-panes;
- **PDF** — HTML-таблица (`build_export_html`) → `render_pdf()` → внешний
  **`screenshot-service`** (`POST /pdf`). WeasyPrint/Playwright в backend НЕ
  тянутся.

Имя файла — `{slug}-{YYYY-MM-DD}.{ext}`. Экспорт доступен любому авторизованному.

### Глобальный поиск (Cmd+K)

Тип результата — `directory_entry`. `search_directory_entries` ищет объекты
**только по `name`** (значения `attributes` НЕ индексируются), и только в
типах, которые `enabled` и не удалены. URL результата —
`/staff?tab={slug}`. Если мастер-флаг `directories` выключен, тип
`directory_entry` исключается из поиска (`./backend/app/api/search.py`).
Подробнее — `./docs/search.md`.

---

## 4. Frontend (встраивание в /staff)

`/staff` получает верхний таб-бар (`n-tabs`, синхронизирован с `?tab=<slug>`):
первая вкладка **«Сотрудники»** (существующая логика без изменений), далее — по
вкладке на каждый `enabled` тип-справочник. Список типов грузится
`useDirectoriesQuery` только когда модуль включён.

| Файл | Содержимое |
|---|---|
| `./frontend/src/pages/StaffDirectoryPage.vue` | таб-бар + переключение `?tab=`; страница остаётся тонким wiring-слоем |
| `./frontend/src/pages/staff/DirectoryTab.vue` | вкладка одного типа: поиск (debounce 300мс), грид карточек, drag-and-drop переупорядочивание (`sortablejs`, editor/admin, отключено при активном поиске), экспорт-дропдаун, drawer’ы создания/настройки |
| `./frontend/src/api/directories.ts` | типизированный клиент + `buildEntriesExportUrl` |
| `./frontend/src/queries/directories.ts` | TanStack Query composables (ключи в `queries/keys.ts`) |
| `./frontend/src/components/directories/EntryCard.vue` | карточка объекта: поля `field_schema`, контакты по ролям, router-ссылка на привязанную папку `/files`, кнопка «редактировать» |
| `./frontend/src/components/directories/EntryContactList.vue` | группировка контактов по ролям, кнопка «скопировать» |
| `./frontend/src/components/admin/EntryEditDrawer.vue` | редактор объекта: динамическая форма по `field_schema` + контакты (editor/admin) |
| `./frontend/src/components/admin/DirectorySettings.vue` | конструктор типа (поля/каналы/название/иконка), drawer `?manage=directory` |
| `./frontend/src/pages/admin/tabs/ModulesTab.vue` | мастер-переключатель модуля (как `meetings`/`photos`) |
| `./frontend/src/stores/modules.ts` | `directories: { enabled }` в `ModuleSettingsResponse` + `isEnabled('directories')` |

UI-режим — **карточки + поиск**. Кнопки «Экспорт CSV / XLSX / PDF» —
дропдауном вверху вкладки (`window.location.assign` на export-URL).
Конструктор типа и редактор объекта открываются drawer’ом (`?manage=*` через
`composables/useManageDrawer.ts`, как в `LinksAndBookmarksPage`/`NewsListPage`).
Все строки — через `t()`; ключи синхронны в `i18n/ru.json` (мастер) и `en.json`.

---

## 5. Грабли / контекст

- **Прецедент конструктора полей** — `UserAttributeMapping`
  (`./backend/app/models/user_attribute_mapping.py`) + фронт
  `useUserAttributeSchemaQuery`. Структура `field_schema` повторяет его
  (`key`, `label_ru/en`, `sort_order`), не изобретать заново.
- **`attributes`/`channels` — JSONB на типе**, валидация на уровне Pydantic
  (`Literal` для `type`), не БД-enum: добавление поля не требует миграции.
- **EmailStr НЕ использовать** для значений контактов и email-полей (DNS на
  `.local`); хранить как обычные строки, валидировать наличием `@`.
- **Аватар** — streaming (`AsyncIterator[bytes]`), MIME через python-magic,
  хранить в `/data` (НЕ Nextcloud). Каталог раздаётся nginx как `link_icons`.
- **PDF-экспорт** — только через `screenshot-service` (`POST /pdf`). WeasyPrint
  запрещён, Playwright в backend не тянуть.
- **Контакты перезаписываются целиком** при обновлении объекта (delete-orphan),
  частичного диффа нет.
- **Поиск — только по `name`.** Значения `attributes` (IMO/MMSI…) не индексируются.
- **`/staff` — «толстая» страница** (логика сотрудников вынесена в композаблы
  `useStaffFilters/Edit/View/Export`). Новые вкладки — отдельные компоненты;
  страница остаётся wiring-слоем, существующую логику не ломать.
- **Двухуровневый гейтинг**: путать мастер-флаг (`modules.json`, весь раздел
  404) и per-type `enabled` (скрытие конкретной вкладки) нельзя.

---

## 6. Тесты

- **Unit** (`./backend/tests/unit/`): валидация `attributes` против
  `field_schema` (типы/required/лишние ключи), `channel ∈ channels`, билдеры
  CSV/XLSX.
- **Integration** (`./backend/tests/integration/test_directories_db.py`,
  Testcontainers): миграция + сид `fleet`, list-пагинация, soft-delete, RBAC
  (editor создаёт — viewer `403`), мастер-флаг-off → `404`, per-type `enabled`,
  аудит, поиск по `name`, reorder (`sort_order` массово + `404` на чужой `id`).
- **Frontend** (`./frontend/tests/unit/`): `entry-contact-list`, `entry-card`,
  `directory-tab`, `entry-edit-drawer`, `directory-settings` — группировка/копирование
  контактов, рендер полей и router-ссылки на привязанную папку, debounce-поиск
  и экспорт, сборка payload (create vs update), конструктор типа.

Команды — см. `./docs/testing.md` и `./AGENTS.md` (раздел «Команды разработки»).
