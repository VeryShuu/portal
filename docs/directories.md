# Модуль «Справочники объектов»

> **Когда читать:** при работе со справочниками судов, складов, гаражей; при изменении таблиц `object_directories`, `object_directory_entries`, `object_entry_contacts`; при модификации конструктора полей и каналов, экспорта в форматы CSV/XLSX/PDF и управления мастер-флагом `directories`.
> **Ключевой код:** `./backend/app/api/directories.py`, `./backend/app/services/directories.py`, `./frontend/src/pages/staff/DirectoryTab.vue`.
> **ADR:** —. **См. также:** `./docs/staff-directory-spec.md`, `./docs/search.md`, `./docs/db-schema.md`, `./docs/roles-matrix.md`.

> Универсальный движок справочников объектов с контактами. Один и тот же движок обслуживает любые «перечни объектов компании»: первый кейс — **«Флот»** (электронная замена бумажного перечня судов компании с IMO/позывным/MMSI и каналами связи V-SAT/Iridium/Inmarsat/email/mobile в разрезе ролей), но та же структура переиспользуется под «Склады», «Гаражи», «Здания» и т.д. Раздел не является отдельным модулем-страницей: справочники встраиваются вкладками в существующий раздел `/staff` (`?tab=<slug>`) рядом с вкладкой «Сотрудники».

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/directories.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/StaffDirectoryPage.vue`, `./frontend/src/pages/staff/DirectoryTab.vue`) |
| Воркер | — |
| Хранилище | База данных (PostgreSQL), внешние папки в `./backend/app/models/files.py` (привязка `folder_id` к `/files`) |
| Префикс API | `/api/v1/directories` |
| ACL-кэш | Redis (используется для проверки настроек модулей из `./backend/app/core/modules_config.py`) |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/directories.py` | Эндпоинты управления типами справочников и объектами |
| Service | `./backend/app/services/directories.py` | Бизнес-логика: CRUD, валидация полей/каналов, генерация экспорта |
| Model | `./backend/app/models/object_directory.py` | SQLAlchemy-модели: `ObjectDirectory`, `ObjectDirectoryEntry`, `ObjectEntryContact` |
| Schema | `./backend/app/schemas/object_directory.py` | Pydantic-схемы валидации запросов и ответов |
| Search | `./backend/app/services/search/entities.py` | Глобальный поиск объектов по имени (`search_directory_entries`) |
| Frontend Page | `./frontend/src/pages/StaffDirectoryPage.vue` | Встраивание таб-бара и вкладок в раздел `/staff` |
| Frontend Tab | `./frontend/src/pages/staff/DirectoryTab.vue` | Грид карточек одного типа, поиск, DND-сортировка, экспорт |
| Frontend API | `./frontend/src/api/directories.ts` | API-клиент и методы экспорта |
| Frontend Queries | `./frontend/src/queries/directories.ts` | TanStack Query composables для запросов и мутаций |
| Components | `./frontend/src/components/directories/` | Карточка объекта (`EntryCard.vue`), список контактов (`EntryContactList.vue`) |
| Admin Drawers | `./frontend/src/components/admin/` | Редактор объекта (`EntryEditDrawer.vue`), конструктор типа (`DirectorySettings.vue`) |

---

## 3. Модель данных

Модели данных хранятся в `./backend/app/models/object_directory.py`. Схема полей (`field_schema`) и набор каналов (`channels`) хранятся как JSONB на типе-справочнике — это обеспечивает гибкость без необходимости проведения частых миграций.

### `object_directories` — тип справочника (вкладка)

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | Сгенерированный UUID |
| `slug` | `String(50)` UNIQUE | Идентификатор типа (например, `fleet`, `warehouses`, используется в `?tab=<slug>`) |
| `label_ru` | `String(100)` NOT NULL | Название вкладки на русском |
| `label_en` | `String(100)` NULL | Название вкладки на английском |
| `icon` | `String(50)` NULL | Имя иконки |
| `description` | `String(500)` NULL | Подсказка/описание |
| `field_schema` | JSONB NOT NULL default `[]` | Определения полей идентификации |
| `channels` | JSONB NOT NULL default `[]` | Доступные каналы связи |
| `enabled` | `Boolean` NOT NULL default TRUE | Флаг видимости вкладки |
| `sort_order` | `Integer` NOT NULL default 0 | Порядок сортировки вкладок |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | Временные метки создания и обновления |
| `deleted_at` | `TIMESTAMPTZ` NULL | Мягкое удаление типа |

- **Индекс**: `idx_object_directories_sort` на `(sort_order)`.

Элемент `field_schema` (по образцу `UserAttributeMapping` из `./backend/app/models/user_attribute_mapping.py`):
```json
{
  "key": "imo",
  "label_ru": "IMO",
  "label_en": "IMO",
  "type": "text",
  "required": false,
  "sort_order": 0
}
```
Допустимые типы полей: `text`, `number`, `email`, `url`, `multiline`. Ключ `key` должен удовлетворять регулярному выражению `^[a-z][a-z0-9_]*$` и быть уникальным в пределах типа справочника.

Элемент `channels`:
```json
{
  "key": "inmarsat",
  "label_ru": "Inmarsat",
  "label_en": "Inmarsat",
  "sort_order": 2
}
```

### `object_directory_entries` — объект справочника

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | Идентификатор объекта |
| `directory_id` | UUID FK | Ссылка на `object_directories.id` ON DELETE CASCADE |
| `name` | `String(200)` NOT NULL | Название объекта (например, «Академик Казанин») |
| `folder_id` | UUID FK | Ссылка на папку в `./backend/app/models/files.py` (ON DELETE SET NULL) |
| `attributes` | JSONB NOT NULL default `{}` | Значения полей согласно `field_schema` |
| `note` | `String(1000)` NULL | Заметка |
| `sort_order` | `Integer` NOT NULL default 0 | Порядок сортировки внутри типа |
| `created_by` | UUID FK | Создатель объекта (ссылка на `users.id` ON DELETE SET NULL) |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | Временные метки |
| `deleted_at` | `TIMESTAMPTZ` NULL | Мягкое удаление |

- **Индексы**:
  - `idx_ode_directory` на `(directory_id, sort_order)`
  - `idx_ode_active` на `(deleted_at)`
  - `idx_ode_folder` на `(folder_id)`

### `object_entry_contacts` — контакты объекта (роль × канал × значение)

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | UUID PK | Идентификатор контакта |
| `entry_id` | UUID FK | Ссылка на `object_directory_entries.id` ON DELETE CASCADE |
| `role` | `String(100)` NULL | Свободная строка роли (например, «Капитан», «Мостик») |
| `channel` | `String(50)` NOT NULL | Ключ канала связи из `directory.channels` |
| `label` | `String(200)` NULL | Дополнительная подпись |
| `value` | `String(255)` NOT NULL | Телефон/email/номер/значение контакта |
| `sort_order` | `Integer` NOT NULL default 0 | Порядок сортировки контактов |

- **Индекс**: `idx_oec_entry` на `(entry_id, sort_order)`.

> При обновлении объекта через `PATCH` контакты перезаписываются целиком (delete-orphan + пересоздание), частичного диффа нет.

### Миграции и сиды

- Миграция `./backend/migrations/versions/064_object_directories.py` создает три таблицы и сидит предустановленный тип справочника `fleet` («Флот») со схемой полей (IMO, позывной, MMSI и др.), каналами связи, а также тестовым объектом «Академик Казанин» с его контактами.
- Миграция `./backend/migrations/versions/065_directory_entry_folder.py` добавляет колонку `folder_id` для привязки к разделу `/files`. Применяются автоматически при старте бэкенда через `./backend/migrate.sh`.

---

## 4. Модель прав (ACL)

Доступ к справочникам регулируется правами пользователя и мастер-флагом модуля. Подробности по правам описаны в `./docs/roles-matrix.md`.

| Действие | Роль |
|---|---|
| Просмотр вкладок, объектов, контактов, экспорт | Любой авторизованный пользователь |
| Создание / изменение / удаление типов, объектов, контактов | `editor` / `admin` |

### Двухуровневый гейтинг видимости

1. **Мастер-флаг модуля**: Настраивается в `/data/settings/modules.json` -> `directories.enabled` (определен в `./backend/app/core/modules_config.py`). Если выключен, все запросы к `/api/v1/directories/*` отдают `404`, вкладки в интерфейсе скрываются, а сущности `directory_entry` исключаются из глобального поиска.
2. **Per-type `enabled`**: Флаг активности на самом типе справочника. Выключенный тип скрыт для обычных пользователей (его вкладка не отображается, объекты отдают `404`), но виден и доступен для управления ролям `editor` и `admin` (`list_directories(include_disabled=True)`).

---

## 5. REST API

Все эндпоинты зарегистрированы в `./backend/app/api/directories.py` под тегом `directories`. Подробные контракты описаны в `./docs/api-contracts.md` и `./docs/api-contracts.generated.md`.

### Справочники (типы)
- `GET /directories` (Любой авторизованный): Список активных типов (для `editor`/`admin` возвращает и выключенные). Схема ответа: `DirectoryList`.
- `POST /directories` (`editor`/`admin`): Создание типа справочника. Возвращает `409` при дублировании `slug`.
- `PATCH /directories/{directory_id}` (`editor`/`admin`): Частичное обновление типа справочника (включая схему полей и каналов).
- `DELETE /directories/{directory_id}` (`editor`/`admin`): Мягкое удаление типа.

### Объекты справочников
- `GET /directories/{slug}/entries` (Любой авторизованный): Получить список объектов типа. Поддерживает пагинацию (`limit`, `offset`), поиск по имени `?q=` (только по названию объекта `name`), лимит выдачи до 500 записей. Сортировка по `sort_order` и `name`.
- `GET /directories/{slug}/entries/{entry_id}` (Любой авторизованный): Детальная информация об объекте вместе с контактами.
- `POST /directories/{slug}/entries` (`editor`/`admin`): Создание объекта с валидацией атрибутов и каналов.
- `PATCH /directories/{slug}/entries/{entry_id}` (`editor`/`admin`): Обновление объекта (контакты перезаписываются целиком).
- `DELETE /directories/{slug}/entries/{entry_id}` (`editor`/`admin`): Мягкое удаление объекта.
- `PATCH /directories/{slug}/entries/reorder` (`editor`/`admin`): Массовое переопределение порядка `sort_order` объектов. Принимает `{items: [{id, sort_order}]}`. Возвращает `404`, если хотя бы один `id` не принадлежит активным объектам типа.
- `GET /directories/{slug}/export` (Любой авторизованный): Выгрузка объектов справочника. Параметр `format` принимает `csv`, `xlsx` или `pdf`.

> Каждая успешная мутация справочника или его объектов после коммита в базу данных отправляет событие аудита через функцию `make_audit_emitter("directory")` с указанием `resource_type=directory`.

---

## 6. Валидация и привязка файлов

### Валидация атрибутов и каналов

Бизнес-логика валидации реализована в `./backend/app/services/directories.py`:
- `validate_attributes(field_schema, attributes)`:
  - Отклоняет любые ключи атрибутов, которые не объявлены в `field_schema` (`422 Unprocessable Content`).
  - Проверяет заполнение обязательных полей (`required=True`), иначе `422`.
  - Валидирует типы данных:
    - `number`: Проверяет возможность приведения к типу `float` (запятая заменяется на точку).
    - `email`: Простая проверка на наличие символа `@` не в краях строки.
    - `url`: Проверяет наличие префикса `http://` или `https://`.
    - `text` / `multiline`: Принимаются без дополнительных проверок.
  - Нормализует все строковые значения, обрезая пробелы по краям (trimmed).
- `validate_channels(channels, contacts)`:
  - Проверяет, что каждый переданный `contact.channel` объявлен в списке `channels` типа справочника, иначе `422`.

### Привязка к разделу файлов
У объекта нет аватара или внешних ссылок, вместо них используется `folder_id` (ссылка на папку в таблице `file_folders`). При создании или обновлении объекта сервис проверяет, существует ли указанная папка и не удалена ли она, иначе выбрасывает `422`. На фронтенде папка выбирается через компонент `n-tree-select` на основе дерева из `useFolderTreeQuery`. В карточке объекта отображается имя папки `folder_name` (подгружается через eager relationship) со ссылкой на `/files?folder=<folder_id>`, обрабатываемой при монтировании файлового менеджера.

---

## 7. Экспорт

Функция `build_export_table()` в `./backend/app/services/directories.py` строит общую таблицу в виде заголовков и строк, где поля выстраиваются по `sort_order` из `field_schema`, контакты свертываются в одну строчку вида `роль · канал: значение; ...`, а также добавляется заметка. На её основе генерируются файлы:
- **CSV**: Использует разделитель `;` и кодируется с UTF-8 BOM (`\ufeff`), что позволяет Excel корректно отображать кириллицу.
- **XLSX**: Генерируется с помощью библиотеки `openpyxl` (зависимость прописана в `./pyproject.toml`). Таблица стилизуется (заголовок синего цвета с белым текстом, автоперенос строк, зафиксированная верхняя строка `freeze_panes="A2"`).
- **PDF**: Экспортируется через генерацию HTML-таблицы (`build_export_html`) с последующей отправкой HTML-строки в отдельный внешний микросервис `screenshot-service` через `POST /pdf` (функция `render_pdf` из `./backend/app/core/pdf.py`). Playwright или WeasyPrint на бэкенде напрямую не используются.

Имя экспортируемого файла имеет вид `{slug}-{YYYY-MM-DD}.{ext}`. Экспорт доступен любому авторизованному пользователю.

---

## 8. Глобальный поиск (Cmd+K)

Справочники интегрированы в систему глобального поиска (описана в `./docs/search.md` и `./backend/app/api/search.py`):
- Тип результата поиска: `directory_entry`.
- Функция поиска `./backend/app/services/search/entities.py` -> `search_directory_entries` осуществляет поиск **только по названию объекта `name`** (значения атрибутов из `attributes` НЕ индексируются).
- Поиск производится только среди включенных (`enabled=True`) и не удаленных типов справочников.
- Результаты поиска ведут на `/staff?tab={slug}`.
- Если мастер-флаг модуля `directories` выключен, сущности `directory_entry` полностью исключаются из глобального поиска.

---

## Безопасность

- **Валидация форматов**: Валидация форматов полей и контактов происходит на уровне Pydantic-схем в `./backend/app/schemas/object_directory.py`. Паттерны: `slug` матчит регулярное выражение `^[a-z][a-z0-9_-]*$`, `key` матчит `^[a-z][a-z0-9_]*$`.
- **Избегание `EmailStr`**: Для хранения email-адресов в полях атрибутов и контактов используется обычный тип `String(255)`, а не Pydantic-тип `EmailStr`, так как DNS-валидация ломается на внутренних `.local` корпоративных доменах. Валидация выполняется через простую проверку наличия символа `@`.
- **Доступ к медиа**: у объектов нет аватаров (фича убрана миграцией `065_directory_entry_folder`) — вместо них используется привязка `folder_id` к модулю «Файлы» (см. §«Привязка к разделу файлов»).

---

## События аудита

События пишутся с `resource_type=directory` через хелпер `make_audit_emitter("directory")`.

| Событие | Инициатор | Описание | Метаданные |
|---|---|---|---|
| `directories.type_created` | `editor` / `admin` | Создание типа справочника | — |
| `directories.type_updated` | `editor` / `admin` | Обновление настроек типа | `{"fields": ["list_of_changed_fields"]}` |
| `directories.type_deleted` | `editor` / `admin` | Мягкое удаление типа | — |
| `directories.entry_created` | `editor` / `admin` | Создание нового объекта | `{"directory": "slug"}` |
| `directories.entry_updated` | `editor` / `admin` | Обновление полей/контактов объекта | `{"directory": "slug", "fields": ["changed_fields"]}` |
| `directories.entry_deleted` | `editor` / `admin` | Мягкое удаление объекта | `{"directory": "slug"}` |
| `directories.entries_reordered`| `editor` / `admin` | Изменение порядка объектов | `{"directory": "slug", "count": 10}` |

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./backend/tests/unit/test_directories_service.py` | Валидация `attributes` против `field_schema` (типы, required, неизвестные ключи), проверка каналов связи `channel ∈ channels`, генерация таблиц CSV/XLSX |
| Integration | `./backend/tests/integration/test_directories_db.py` | Тестирование миграции базы данных, сид справочника `fleet`, пагинация, мягкое удаление, разграничение прав доступа (RBAC), поведение мастер-флага и флага `enabled`, аудит, поиск по `name`, массовый reorder |
| Frontend | `./frontend/tests/unit/directory-tab.spec.ts` | Компонент вкладки: рендеринг карточек, поиск, группировка, экспорт |
| Frontend | `./frontend/tests/unit/directory-settings.spec.ts` | Компонент конструктора типа: создание и настройка полей/каналов |
| Frontend | `./frontend/tests/unit/staff-directory-page.spec.ts` | Страница разделов: интеграция вкладок, переключение табов, интеграция с TanStack Query |

Команды для запуска тестов и проверки стиля описаны в `./docs/testing.md` и `./AGENTS.md`.

---

## Связанные документы

- `./docs/staff-directory-spec.md` — Детальная спецификация интерфейса справочников
- `./docs/db-schema.md` — Общая схема базы данных портала
- `./docs/roles-matrix.md` — Матрица прав доступа и ролевая модель
- `./docs/search.md` — Архитектура и принципы глобального поиска
- `./docs/api-contracts.md` / `./docs/api-contracts.generated.md` — Контракты веб-интерфейсов API
- `./docs/testing.md` — Справка по запуску тестов и линтеров
