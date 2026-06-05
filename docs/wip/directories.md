# Фича: Справочники объектов (вкладки в /staff)

> ✅ **Статус: реализовано** (ветка `feat/object-directories`). Backend
> (модели/схемы/сервис/роутер/миграция `064` + сид `fleet`), frontend
> (таб-бар в `/staff`, карточки, конструктор типа, редактор объекта),
> мастер-флаг модуля, поиск (Cmd+K), экспорт CSV/XLSX/PDF, i18n (ru+en),
> docs (`db-schema`/`api-contracts`/`roles-matrix`/`AGENTS.md`). Тесты,
> lint, typecheck — зелёные. Этот план удаляется после мёржа задачи
> (конвенция `AGENTS.md`).

> Универсальный движок справочников объектов с контактами. Первый кейс —
> «Флот» (электронная замена бумажного «ПЕРЕЧНЯ СУДОВ КОМПАНИИ»): объекты с
> идентификацией (IMO/позывной/MMSI…) и каналами связи (V-SAT,
> Iridium/Inmarsat, e-mail, мобильный) в разрезе ролей. Тот же движок
> переиспользуется под «Склады», «Гаражи», «Здания» — структура одинаковая.

---

## Цель

Дать всем сотрудникам единое окно для поиска контактов объектов компании
(суда, склады, гаражи…), заменив бумажные/Excel-перечни. Админ сам заводит
**типы справочников** и их структуру (поля + каналы связи) без участия
разработчика. Просмотр — все авторизованные; редактирование — admin+editor.

---

## Решения по ходу (согласовано с пользователем)

- **2026-06-04**: НЕ отдельный модуль. Справочники встраиваются **вкладками
  в существующий раздел `/staff`**: вкладка `Сотрудники` (текущая) + N
  вкладок-справочников, названия задаются админом в настройках.
- **2026-06-04**: **универсальный движок** — админ создаёт типы (Флот,
  Склады, Гаражи). «Флот» — предзаполненный тип, не хардкод.
- **2026-06-04**: **Вариант A — полный конструктор полей** идентификации.
  Переиспользуем существующий паттерн `UserAttributeMapping`
  (`app/models/user_attribute_mapping.py`: `field_key`, `label_ru/label_en`,
  `sort_order`, `enabled`) — он уже доказал себя на странице сотрудников.
- **2026-06-04**: **каналы связи настраиваются под тип** (у судов
  V-SAT/Iridium/Inmarsat, у складов — тел/email).
- **2026-06-04**: объект имеет **аватарку** (одно фото, локально `/data`) и
  **ссылку на папку в `/files`** (НЕ новая файловая сущность, просто URL).
- **2026-06-04**: **архива нет** — только soft-delete (`deleted_at`).
- **2026-06-04**: объекты находятся в **глобальном поиске (Cmd+K)**.
- **2026-06-04**: доступ — читают все авторизованные, мутируют admin+editor
  (`Depends(require_role("editor"))`); контакты — только отображение +
  копирование (без `tel:`/`mailto:`).
- **2026-06-04**: экспорт **CSV + PDF + XLSX** сразу. PDF — через существующий
  `screenshot-service` (`POST /pdf`). XLSX — переиспользуем подход
  `app/api/users/staff_xlsx.py` (`openpyxl>=3.1.0` уже в `pyproject.toml`,
  НЕ новая зависимость).
- **2026-06-04**: **выключаемость — как у переговорных (`meetings`)**:
  мастер-переключатель всей фичи в Администрировании (`modules.json` →
  `DirectoriesModuleSettings.enabled`, рендерится в `ModulesTab.vue`).
  Детальные настройки типов — кнопкой-шестерёнкой **внутри раздела** (drawer).
  Видимость отдельной вкладки — флаг `object_directories.enabled` (per-type).
- **2026-06-04**: **типы создаёт admin+editor** (как и объекты внутри) —
  единый уровень `require_role("editor")` на все мутации.
- **2026-06-04**: **видимость — все**: каждый авторизованный видит все
  включённые типы-вкладки. Ограничений по ролям/отделам нет.
- **2026-06-04**: **поиск — только по `name`** (Cmd+K и `?q=`). Значения
  `attributes` (IMO/MMSI…) НЕ индексируются.

---

## Модель данных

3 таблицы (UUID PK, soft-delete где нужно, `created_by`/`created_at`/`updated_at`
по аналогу `app/models/links.py::ServiceLink`). Схема полей и набор каналов
хранятся как JSONB на самом типе-справочнике — низкая кардинальность,
редко меняются, не требуют миграции при добавлении поля.

### `object_directories` — ТИП справочника (= вкладка в /staff)

| колонка | тип | примечание |
|---|---|---|
| `id` | UUID PK | |
| `slug` | `String(50)` UNIQUE | `fleet`, `warehouses`… (для URL/якоря вкладки) |
| `label_ru` | `String(100)` NOT NULL | название вкладки (рус) — задаёт админ |
| `label_en` | `String(100)` NULL | название вкладки (англ) |
| `icon` | `String(50)` NULL | имя иконки |
| `description` | `String(500)` NULL | подсказка |
| `field_schema` | JSONB NOT NULL default `[]` | определения полей идентификации (см. ниже) |
| `channels` | JSONB NOT NULL default `[]` | доступные каналы связи (см. ниже) |
| `enabled` | `Boolean` NOT NULL default true | показывать вкладку |
| `sort_order` | `Integer` NOT NULL default 0 | порядок вкладок |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

`field_schema` (Вариант A, элемент массива — по образцу `UserAttributeMapping`):
```json
{ "key": "imo", "label_ru": "IMO", "label_en": "IMO",
  "type": "text", "required": false, "sort_order": 0 }
```
`type ∈ {text, number, email, url, multiline}` (Pydantic Literal, расширяемо).

`channels` (элемент массива):
```json
{ "key": "inmarsat", "label_ru": "Inmarsat", "label_en": "Inmarsat",
  "sort_order": 2 }
```

### `object_directory_entries` — ОБЪЕКТ (судно / склад / гараж)

| колонка | тип | примечание |
|---|---|---|
| `id` | UUID PK | |
| `directory_id` | UUID FK→`object_directories.id` ON DELETE CASCADE | тип |
| `name` | `String(200)` NOT NULL | «Академик Казанин» / «Склад №3» |
| `avatar_path` | `String(500)` NULL | фото объекта (локально `/data/...`) |
| `folder_url` | `String(2048)` NULL | ссылка на папку в `/files` |
| `attributes` | JSONB NOT NULL default `{}` | значения полей: `{"imo":"9489481","mmsi":"273411580"}` |
| `note` | `String(1000)` NULL | заметка (напр. «при наборе из России: …») |
| `sort_order` | `Integer` NOT NULL default 0 | |
| `created_by` | UUID FK→`users.id` ON DELETE SET NULL | |
| `created_at`/`updated_at` | `TIMESTAMPTZ` | |
| `deleted_at` | `TIMESTAMPTZ` NULL | soft-delete |

Индексы: `idx_ode_directory (directory_id, sort_order)`,
`idx_ode_active (deleted_at)`. Поиск — по `name` + значениям `attributes`
(JSONB); для typeahead при росте — `pg_trgm` по `name`.

### `object_entry_contacts` — роль × канал × значение

| колонка | тип | примечание |
|---|---|---|
| `id` | UUID PK | |
| `entry_id` | UUID FK→`object_directory_entries.id` ON DELETE CASCADE | |
| `role` | `String(100)` NULL | свободная строка: «Мостик», «Капитан», «ВЦ» |
| `channel` | `String(50)` NOT NULL | `key` из `directory.channels` |
| `label` | `String(200)` NULL | доп. подпись (напр. «Inmarsat 427312475») |
| `value` | `String(255)` NOT NULL | сам номер/почта/добавочный |
| `sort_order` | `Integer` NOT NULL default 0 | |

Индекс: `idx_oec_entry (entry_id, sort_order)`.
E-mail хранить как `String(255)`, НЕ `EmailStr` (DNS-проверка ломается на
`.local`/корпоративных доменах — известная грабля проекта).

### Маппинг бумажной таблицы (тип «Флот», объект «Академик Казанин»)

- `object_directories`: slug=`fleet`, label_ru=«Флот»,
  field_schema=[IMO, callsign, MMSI, vsat_main, dial_note],
  channels=[vsat_ext, iridium, inmarsat, email, mobile].
- `object_directory_entries`: name=«Академик Казанин»,
  attributes={imo:«9489481», callsign:«UBXQ6», mmsi:«273411580»,
  vsat_main:«+7(8152) 400-580», dial_note:«при наборе из России: 8 10 8(8167)…»}.
- `object_entry_contacts`: (Мостик,vsat_ext,262), (Мостик,email,akz_bridge@mage.ru),
  (Капитан,vsat_ext,261), (Нач.рейса,vsat_ext,263), (Навигаторы,email,akznav@mage.ru),
  (—,iridium,+8 (8167) 710-56-09), (—,inmarsat,427312475 / 427312474),
  (—,mobile,+7(911) 313-07-11).

### Миграция

`backend/migrations/versions/064_object_directories.py` (после `063_file_shares`).
Создаёт 3 таблицы + индексы и **сидит тип `fleet`** с готовой схемой полей и
каналов. Применяется автоматически при старте backend (`migrate.sh`).

---

## Backend

| Файл | Содержимое |
|---|---|
| `app/models/object_directory.py` | `ObjectDirectory`, `ObjectDirectoryEntry`, `ObjectEntryContact` |
| `app/schemas/object_directory.py` | Pydantic: типы, поля (`field_schema`), каналы, объекты, контакты; list-конверт `{items,total,limit,offset}` |
| `app/services/directories.py` | бизнес-логика: CRUD типов/объектов/контактов, валидация `attributes` против `field_schema`, поиск, сборка CSV/HTML/XLSX экспорта |
| `app/api/directories.py` | роутер; регистрация в `app/api/__init__.py` |
| `app/api/search.py` | добавить объекты в глобальный поиск (Cmd+K) — по `name` |
| `app/core/modules_config.py` | `DirectoriesModuleSettings(enabled=False)` (мастер-флаг) + поле в `AllModuleSettings` |

### Эндпоинты (`/api/v1/directories`)

Типы (admin/editor мутируют):
- `GET /directories` — список типов (вкладок), `enabled` для меню.
- `POST /directories`, `PATCH /directories/{id}`, `DELETE /directories/{id}`
  (soft) — управление типами + их `field_schema`/`channels`. audit.

Объекты:
- `GET /directories/{slug}/entries` — `{items,total,limit,offset}`, поиск `?q=`
  (только по `name`), сортировка по `sort_order`. Все авторизованные.
- `GET /directories/{slug}/entries/{id}` — объект с контактами.
- `POST/PATCH/DELETE .../entries[/{id}]` — мутации, `require_role("editor")`,
  валидация `attributes` против `field_schema`, `push_audit_event` после commit.
- `POST .../entries/{id}/avatar` — загрузка фото (streaming, python-magic для
  MIME, как в photos). Хранение `/data/...`.
- `GET /directories/{slug}/export?format=csv|pdf|xlsx` — выгрузка.

> Гейтинг двухуровневый: мастер-флаг `modules.json` выключен → весь раздел
> справочников 404/скрыт; отдельный тип с `enabled=false` → его вкладка скрыта.
> Типы тоже мутируются `require_role("editor")` (admin+editor).

### Тесты (обязательно вместе с кодом)

- unit: валидация `attributes` против `field_schema` (типы, required, лишние
  ключи), `channel ∈ directory.channels`, сборка CSV.
- integration (Testcontainers): миграция + сид `fleet`, list-пагинация,
  soft-delete, RBAC (editor создаёт, viewer 403), флаг-off → 404, audit,
  поиск по attributes, загрузка/валидация аватарки.

---

## Frontend (встраивание в /staff)

`/staff` получает верхний таб-бар: первая вкладка **«Сотрудники»** (текущая
`StaffDirectoryPage` без изменений логики), далее — по вкладке на каждый
`enabled` тип-справочник (название из `label_ru/label_en`).

| Файл | Содержимое |
|---|---|
| `pages/StaffDirectoryPage.vue` | обернуть текущее содержимое в первую вкладку; добавить таб-бар (`?tab=<slug>`) |
| `pages/staff/DirectoryTab.vue` | список объектов выбранного типа + поиск + карточки (тонкий wiring) |
| `api/directories.ts` | типизированный клиент |
| `queries/directories.ts` (+ `keys.ts`) | TanStack Query composables |
| `components/directories/EntryCard.vue` | карточка объекта: аватар + поля (`field_schema`) + контакты по ролям + ссылка на папку `/files` |
| `components/directories/EntryContactList.vue` | группировка контактов, кнопка «скопировать» |
| `components/admin/EntryEditDrawer.vue` | редактирование объекта (динамическая форма по `field_schema` + контакты), admin/editor |
| `components/admin/DirectorySettings.vue` | конструктор типа: поля (`field_schema`), каналы (`channels`), название вкладки, иконка — открывается шестерёнкой (`?manage=directory`) |
| `pages/admin/tabs/ModulesTab.vue` | мастер-переключатель фичи (как `meetings`/`photos`) |
| `stores/modules.ts` | добавить `directories` в `ModuleSettingsResponse` + `isEnabled` union |
| `i18n/ru.json` + `en.json` | все строки через `t()` |

UI режим — **карточки + поиск**. Кнопки «Экспорт CSV / PDF / XLSX» вверху вкладки.
Конструктор полей и настройки типа — через drawer (`?manage=*`,
`composables/useManageDrawer.ts`), как в `LinksAndBookmarksPage`/`NewsListPage`.
Динамическая форма редактора объекта рендерится по `field_schema` типа.

---

## Чеклист (DoD)

- [x] миграция `064_object_directories.py` (3 таблицы + индексы + сид `fleet`)
- [x] модели `app/models/object_directory.py`
- [x] схемы `app/schemas/object_directory.py` (+ валидаторы field_schema/channels)
- [x] сервис `app/services/directories.py` (CRUD + валидация attributes + поиск + экспорт)
- [x] роутер `app/api/directories.py` + регистрация в `__init__.py`
- [x] интеграция в `app/api/search.py` (Cmd+K, по `name`)
- [x] мастер-флаг `DirectoriesModuleSettings` в `modules_config.py` + `api/modules.py` DTO + per-type `enabled`
- [x] загрузка аватарки (streaming + python-magic + `/data`)
- [x] экспорт CSV + PDF + XLSX (XLSX по образцу `staff_xlsx.py`)
- [x] unit-тесты (валидация attributes/channels, CSV/XLSX)
- [x] integration-тесты (RBAC editor на типы и объекты, пагинация, soft-delete, мастер-флаг-off→404, per-type enabled, audit, поиск по name, аватар)
- [x] frontend: таб-бар в `StaffDirectoryPage` + `DirectoryTab`
- [x] frontend: api/query/`EntryCard`/`EntryContactList`
- [x] frontend: `EntryEditDrawer` (динамическая форма) + `DirectorySettings` (конструктор)
- [x] frontend: мастер-тоггл в `ModulesTab.vue` + `directories` в `stores/modules.ts`
- [x] i18n (ru + en), `npm run i18n:check`
- [x] lint + typecheck + tests pass (backend и frontend)
- [x] обновить `docs/db-schema.md`, `docs/api-contracts.md`, `docs/roles-matrix.md`
- [x] упомянуть фичу в `AGENTS.md`

---

## Грабли / контекст

- **Прецедент конструктора полей** — `UserAttributeMapping`
  (`app/models/user_attribute_mapping.py`) + фронт
  `useUserAttributeSchemaQuery`. Повторять его структуру (`key`, `label_ru/en`,
  `sort_order`, `enabled`), не изобретать заново.
- **XLSX уже доступен**: `openpyxl>=3.1.0` в `pyproject.toml`, пример —
  `app/api/users/staff_xlsx.py`. Если решим включить XLSX-экспорт — это НЕ
  новая зависимость.
- **Экспорт PDF** — только через `screenshot-service` (`POST /pdf`).
  WeasyPrint запрещён. Playwright в backend не тянуть.
- **EmailStr** — НЕ использовать для значений контактов (DNS на `.local`).
- **`attributes`/`channels` — JSONB на типе**, валидация на уровне Pydantic
  (Literal для `type`/`channel`), не БД-enum: добавление поля без миграции.
- **Загрузка аватарки** — streaming (`AsyncIterator[bytes]`), MIME через
  python-magic (не Content-Type клиента), хранить в `/data` (НЕ Nextcloud).
- **Audit** — каждая мутация → `push_audit_event` после commit.
- **/staff уже «толстая» страница** — содержимое сотрудников вынесено в
  композаблы (`useStaffFilters/Edit/View/Export`). При добавлении таб-бара не
  ломать существующую логику: новые вкладки — отдельные компоненты, страница
  остаётся wiring-слоем.

---

## Открытые вопросы

Все ключевые вопросы закрыты (см. «Решения по ходу» от 2026-06-04):

1. ✅ Фича-флаг — гибрид: мастер в `modules.json` (как `meetings`) + per-type `enabled`.
2. ✅ XLSX — включаем сразу (зависимость уже есть).
3. ✅ Права на типы — admin+editor (как и объекты).
4. ✅ Видимость — все авторизованные видят все включённые типы.
5. ✅ Поиск — только по `name`.

Мелкие решения — по ходу реализации (Idempotency-Key на `POST`, формат
`slug`-генерации, иконки для вкладок).
