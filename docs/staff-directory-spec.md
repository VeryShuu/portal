# Модуль «Справочник сотрудников»

> **Когда читать:** справочник `/staff`, отделы, режим карточек, порядок сотрудников.
> **Ключевой код:** `./backend/app/models/staff_order.py`, `./backend/app/api/users/`, `./frontend/src/composables/useStaffEdit.ts`.
> **ADR:** —. **См. также:** `./docs/_TEMPLATE.md`.

> Корпоративный справочник всех активных сотрудников портала. Предоставляет плоскую таблицу, сгруппированную по отделам, альтернативный режим «Карточки», фильтрацию по городам и отделам, поиск, экспорт в CSV и печатную версию в XLSX. Для администраторов реализован визуальный режим редактирования с drag-and-drop сортировкой отделов/сотрудников и скрытием пользователей.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/users/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/StaffDirectoryPage.vue`) |
| Воркер | — (синхронизация пользователей происходит через фоновый воркер Keycloak) |
| Хранилище | Только база данных |
| Префикс API | `/api/v1/users` |
| ACL-кэш | Redis (используется для кэширования системных настроек) |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/users/routes_staff.py` | Эндпоинты справочника, экспорта и администрирования порядка |
| Router | `./backend/app/api/users/routes_me.py` | Личный профиль (`/me`), пароли, предпочтения и аватар |
| Router | `./backend/app/api/users/routes_admin.py` | Администрирование пользователей и ручной запуск синхронизации |
| Service | `./backend/app/api/users/staff_service.py` | Бизнес-логика PUT-сохранения порядка (`apply_staff_order`) |
| Service | `./backend/app/services/full_name_source.py` | Разрешение источника ФИО пользователя по маппингам атрибутов |
| Model | `./backend/app/models/user.py` | SQLAlchemy-модель `User` (поля `staff_sort_order`, `staff_hidden`) |
| Model | `./backend/app/models/staff_order.py` | SQLAlchemy-модель `StaffDepartmentOrder` (порядок отделов) |
| Model | `./backend/app/models/user_attribute_mapping.py` | SQLAlchemy-модель `UserAttributeMapping` (маппинг Keycloak-атрибутов) |
| Schema | `./backend/app/schemas/user.py` | Pydantic-схемы для запросов/ответов по пользователям |
| Frontend Page | `./frontend/src/pages/StaffDirectoryPage.vue` | Тонкий оркестратор страницы справочника |
| Frontend Tab | `./frontend/src/pages/staff/DirectoryTab.vue` | Вкладка кастомного справочника из модуля `directories` |
| Frontend Component | `./frontend/src/components/staff/StaffFilters.vue` | Верхняя sticky-панель управления и фильтрации |
| Frontend Component | `./frontend/src/components/staff/StaffTableView.vue` | Табличное отображение сотрудников |
| Frontend Component | `./frontend/src/components/staff/StaffGridView.vue` | Сетка карточек сотрудников |
| Frontend Component | `./frontend/src/components/staff/StaffEditView.vue` | Панель редактирования (списки Drag-and-Drop) |
| Frontend Component | `./frontend/src/components/StaffRow.vue` | Строка таблицы сотрудников |
| Frontend Component | `./frontend/src/components/StaffCard.vue` | Карточка сотрудника с контактной информацией |
| Frontend Composable | `./frontend/src/composables/useStaffFilters.ts` | Синхронизация фильтров с URL, debounce поиска |
| Frontend Composable | `./frontend/src/composables/useStaffEdit.ts` | Логика администрирования (Drag-and-Drop, скрытие) |
| Frontend Composable | `./frontend/src/composables/useStaffView.ts` | Управление переключением табличного/карточного вида и адаптивностью |
| Frontend Composable | `./frontend/src/composables/useStaffExport.ts` | Управление экспортом в CSV и XLSX (печатная форма) |
| Frontend Composable | `./frontend/src/composables/useStaffLeaveGuard.ts` | Guard (`beforeRouteLeave` + `beforeunload`) при несохраненных изменениях |
| Frontend Composable | `./frontend/src/composables/usePhoneFormat.ts` | Извлечение и форматирование внутреннего телефона по regex |
| Frontend Composable | `./frontend/src/composables/useHighlight.ts` | Безопасная XSS-safe подсветка результатов поиска |

---

## 3. Модель данных

### 3.1 Модель `User` (`./backend/app/models/user.py`)
Расширена полями:
- `staff_sort_order: int | None` — Позиция сотрудника внутри своего отдела в справочнике. `NULL` означает, что пользователь идет в конец списка (по алфавиту).
- `staff_hidden: bool` — Помечает сотрудника как скрытого из справочника (но видимого на страницах профиля, поиска по порталу и т.д.).

### 3.2 Модель `StaffDepartmentOrder` (`./backend/app/models/staff_order.py`)
Таблица `staff_department_orders`:
- `department: text (Primary Key)` — Имя отдела.
- `sort_order: int` — Глобальный порядковый номер отдела, определяющий его позицию.

### 3.3 Маппинг ФИО (`./backend/app/models/user_attribute_mapping.py`)
Таблица `user_attribute_mappings` имеет поле `is_full_name_source: bool`. При значении `True` имя поля Keycloak-атрибута используется как основной источник для переопределения `users.full_name` при OIDC-авторизации или синхронизации.

### 3.4 Индексы и миграции
- Индекс `idx_users_staff_sort_order ON users (department, staff_sort_order) WHERE deleted_at IS NULL` ускоряет получение пользователей при кастомной сортировке.
- Миграция: `./backend/migrations/versions/044_staff_directory_order.py`.

---

## 4. Модель прав (ACL)

- **Просмотр справочника**: разрешен любому авторизованному пользователю (`CurrentUser`).
- **Скрытые пользователи**: параметр `include_hidden=True` в `GET /users` разрешён **только** для роли `admin` (иначе 403). При этом **явный параметр влияет только при `sort=staff_custom`**: если запрошена сортировка `full_name` или `department`, скрытые пользователи включаются в выдачу **всегда** (`effective_include_hidden = True`), т.к. осмысленная сортировка по ФИО/отделу требует полного списка — без скрытых он был бы фрагментированным. Логика — `./backend/app/api/users/routes_staff.py`.
- **Редактирование порядка и скрытие**: роуты `GET /users/admin/staff-order` и `PUT /users/admin/staff-order` защищены зависимостью `AdminDep` (доступно только пользователям с `role=admin`).

---

## 5. REST API

Все эндпоинты зарегистрированы на общем префиксе `/users` в `./backend/app/api/users/__init__.py`.

### 5.1 Список сотрудников: `GET /users`
- **Доступ**: `CurrentUser`
- **Параметры**:
  - `q`: поисковый запрос (поиск по `full_name`, `email`, `position`, `phone`, `internal_phone` и `mobile`).
  - `department`: точная фильтрация по названию отдела.
  - `office`: точная фильтрация по `city` (из `attributes`).
  - `sort`: `full_name` \| `department` \| `staff_custom`.
  - `include_hidden`: явно запросить скрытых пользователей (только admin, иначе 403). **Влияет лишь при `sort=staff_custom`** — при `sort ∈ {full_name, department}` скрытые включаются всегда (см. §«Модель прав»).
  - `page` / `page_size`: пагинация (лимит `page_size` увеличен до `1000` для админ-панели).
- **Сортировка `staff_custom`**:
  - `LEFT JOIN staff_department_orders ON dept = User.department`
  - Сортируется по: `staff_department_orders.sort_order ASC NULLS LAST`, `User.department ASC NULLS LAST`, `User.staff_sort_order ASC NULLS LAST`, `User.full_name ASC`.

### 5.2 Список отделов: `GET /users/departments`
- **Доступ**: `CurrentUser`
- **Параметры**:
  - `ordered: bool` (по умолчанию `false`). При `true` сначала идут отделы с приоритетом из `staff_department_orders` по их `sort_order`, затем новые отделы в алфавитном порядке.

### 5.3 Список офисов/городов: `GET /users/offices`
- **Доступ**: `CurrentUser`
- **Описание**: Выдает уникальный непустой список городов из `users.attributes->>'city'`.

### 5.4 Экспорт данных: `GET /users/export`
- **Доступ**: `CurrentUser`
- **Параметры**: те же, что и у `GET /users` (включая `format` = `csv` \| `xlsx`).
- **Описание**: Скачивание справочника в CSV или печатной формы в XLSX.

### 5.5 Админка: `GET /users/admin/staff-order`
- **Доступ**: `AdminDep`
- **Ответ**: `StaffOrderState` `{ departments: string[], hidden_user_ids: string[] }`.

### 5.6 Админка: `PUT /users/admin/staff-order`
- **Доступ**: `AdminDep`
- **Тело**: `StaffOrderUpdate` `{ departments: string[], users: { id: string, sort_order: number }[], hidden_user_ids: string[] }`
- **Описание**: Атомарное обновление порядка отделов, пользователей внутри отделов и флагов скрытия.

### 5.7 Профиль: `GET /users/{user_id}`
- **Доступ**: `CurrentUser`
- **Описание**: Получение карточки пользователя по его UUID.

---

## 6. Интеграция с модулем «Вкладки» (Directories)

Если в системе активирован модуль `directories` (проверяется через `modules.isEnabled('directories')`), на странице `./frontend/src/pages/StaffDirectoryPage.vue` рендерятся вкладки:
- Первая вкладка всегда **Сотрудники** (`STAFF_TAB`), отображающая стандартный интерфейс справочника.
- Последующие вкладки загружаются динамически по API из `useDirectoriesQuery`.
- При переключении вкладки URL дополняется параметром `?tab=slug`.
- Активная кастомная вкладка делегирует рендеринг компоненту `./frontend/src/pages/staff/DirectoryTab.vue`, который реализует поиск, экспорт, создание и редактирование кастомных сущностей этого справочника.

---

## 7. Источник ФИО (Full Name Source)

Для решения задачи синхронизации имен пользователей из Keycloak используется специальный сервис `./backend/app/services/full_name_source.py`:
- Настройка `is_full_name_source` в маппинге атрибутов указывает системе, какое поле Keycloak считать каноническим именем.
- Функция `resolve_full_name(default, kc_attrs, attr_key)` вычленяет строковое значение атрибута (или первый элемент массива) и возвращает его в качестве `full_name` пользователя при OIDC-авторизации или бэкграунд-синхронизации.

---

## 8. Специфика реализации бэкенда

### 8.1 Экспорт в CSV (`format=csv`)
- Стриминг через `StreamingResponse` и асинхронный генератор `users_repo.stream_users` с пачками по `500` записей.
- Выдача начинается с UTF-8 BOM (`\ufeff`) для автоматической корректной кодировки в Microsoft Excel.
- Поля: `full_name, position, department, office, internal_phone, mobile_phone, email`.
- Защита от **CSV-injection**: все строки, начинающиеся на `=, +, -, @, \t, \r`, экранируются префиксом `'` функцией `_csv_safe(v)` перед выдачей.

### 8.2 Печатная XLSX-версия (`format=xlsx`)
- Генерация XLSX-файла в памяти с помощью библиотеки `openpyxl` (`./backend/app/api/users/staff_xlsx.py`).
- Оформление полностью имитирует бумажный бланк компании: заголовок в шапке, закрепленные верхние строки (`freeze_panes`), повторение шапки таблицы на каждой печатной странице (`print_title_rows = "4:4"`).
- Сквозная нумерация строк `№` начинается заново для каждого нового отдела.
- Ландшафтная ориентация страницы и автоматический масштаб `fitToWidth=1` гарантируют корректную распечатку на листах А4.

### 8.3 Атомарная транзакция сохранения порядка
Бизнес-логика в `./backend/app/api/users/staff_service.py` выполняет `PUT /users/admin/staff-order` в единой транзакции:
1. `replace_department_order` — полная перезапись таблицы порядка отделов.
2. `apply_user_sort_orders` — сброс старого порядка сотрудников (`NULL`) и запуск **одного батч-обновления через SQL-конструкцию `CASE WHEN`** для всех переданных пользователей, минимизируя нагрузку на базу данных.
3. `apply_hidden_user_ids` — сброс старых скрытых пользователей и установка `staff_hidden = true` для переданного списка ID.
4. В случае любого исключения срабатывает автоматический `db.rollback()`.

---

## 9. Специфика реализации фронтенда

### 9.1 Тонкий оркестратор и разделение логики
Страница `./frontend/src/pages/StaffDirectoryPage.vue` разгружена от логики и занимает минимальный объем за счет выноса кода в специализированные composables:
- **`useStaffFilters`** (`./frontend/src/composables/useStaffFilters.ts`) — двусторонняя синхронизация поисковой строки, отделов, офисов и пагинации с URL-параметрами, а также дебаунс поиска в `300мс` через `useDebounceFn`. При изменении любого фильтра страница сбрасывается на `1`.
- **`useStaffView`** (`./frontend/src/composables/useStaffView.ts`) — сохраняет выбранный режим («Таблица» / «Карточки») в `localStorage` по ключу `staff:view`. На мобильных экранах жестко форсирует отображение в виде карточек. Сортировка по умолчанию всегда зафиксирована на `staff_custom`.
- **`useStaffExport`** (`./frontend/src/composables/useStaffExport.ts`) — инициирует загрузку CSV-экспорта или печатного XLSX-файла посредством прямого изменения `window.location.assign(...)` с URL, собранным через `buildUsersExportUrl`.
- **`useStaffLeaveGuard`** (`./frontend/src/composables/useStaffLeaveGuard.ts`) — тонкая обёртка над общим `useFormLeaveGuard` (`./frontend/src/composables/useFormLeaveGuard.ts`, `guardBeforeUnload: true`): регистрирует хук `onBeforeRouteLeave` и слушатель события `beforeunload`, предохраняя администратора от случайной потери несохраненных изменений в режиме сортировки при переходе на другие страницы портала или закрытии вкладки.

### 9.2 Режим редактирования и SortableJS
Режим сортировки обеспечивается composable-модулем `useStaffEdit.ts`:
- Загружает всех пользователей компании одним запросом с `page_size = 1000`.
- Функция `buildGroupsFromList` группирует их во внутреннее реактивное состояние `editGroups`.
- Инициализация `SortableJS` происходит **строго один раз** при открытии режима (`bindSortables()`).
- В обработчике `onEnd` перемещенный DOM-элемент **принудительно возвращается на свою исходную позицию**, предоставляя Vue.js право самостоятельно отрендерить обновленный массив `editGroups`. Это полностью решает проблему рекурсивных пересозданий инстансов.
- Логика перемещения пользователей между отделами динамически изменяет свойство `user.department` перетаскиваемого пользователя в интерфейсе, но реальное изменение отдела пользователя в БД заблокировано (ограничение синхронизации Keycloak).
- Кнопка-«глаз» вызывает тоггл `toggleUserHidden` и помечает локальное состояние `dirty`.

### 9.3 Форматирование номеров (`usePhoneFormat`)
- Composable `./frontend/src/composables/usePhoneFormat.ts` извлекает отображаемый внутренний телефон из `user.phone` с помощью регулярного выражения `phone_extract_regex` из системных настроек.
- Если регулярное выражение не задано или не находит совпадений, возвращается исходная строка.
- Ссылки `href="tel:..."` всегда ведут на оригинальный сырой телефон без применения regex, чтобы не ломать звонки из браузера.

### 9.4 Подсветка поисковых совпадений (`useHighlight`)
- Composable `./frontend/src/composables/useHighlight.ts` осуществляет XSS-безопасную подсветку совпадений.
- На первом этапе входящая строка полностью экранируется от HTML-тегов, затем все вхождения поискового запроса оборачиваются в теги `<mark class="staff-hl">` с сохранением регистра исходных символов.

### 9.5 Копирование контактов
- В `./frontend/src/components/StaffRow.vue` и `./frontend/src/components/StaffCard.vue` около email и номеров телефонов рендерится кнопка `CopyOutline`, появляющаяся при наведении курсора.
- Клик по кнопке вызывает копирование значения через `navigator.clipboard.writeText`, выводит всплывающее уведомление `n-message.success` и блокирует всплытие события (`@click.stop`), препятствуя ложному переходу в профиль сотрудника.

---

## Безопасность

1. **Защита от XSS**: Весь вывод поисковых совпадений на фронтенде обрабатывается через утилиту `useHighlight`, экранирующую любые HTML-сущности и скрипты перед встраиванием в DOM через `v-html`.
2. **Защита от CSV-injection (OWASP)**: Все экспортируемые в CSV строковые значения ячеек проходят бэкенд-фильтрацию `_csv_safe`, что блокирует запуск вредоносных формул в Excel при открытии выгрузок.
3. **ACL Контроль на бэкенде**: Попытки запросить скрытых пользователей (`include_hidden=True`) фильтруются на уровне API-контроллера. Роль пользователя проверяется строго на бэкенде, исключая возможность обхода ограничений фронтенда.

---

## События аудита

- Действия администратора по изменению порядка отделов и пользователей (`PUT /users/admin/staff-order`) **не вызывают** запись в журнал аудита портала (данное действие не логируется).
- Стандартные действия по администрированию конкретного пользователя (обновление роли, удаление, смена пароля админом) вызывают стандартную генерацию событий аудита типа `user` через хелпер `_emit_audit` в `./backend/app/api/users/users_admin_service.py`.

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit (Бэкенд) | `./backend/tests/unit/test_staff_directory.py` | Авторизация эндпоинтов, контракты ответов, валидация параметров сортировки и форматов, защита от коллизий UUID-путей, экранирование CSV-injection, ACL-доступ к скрытым записям |
| Unit (Бэкенд) | `./backend/tests/unit/test_phone.py` | Валидация утилиты форматирования `apply_phone_regex` с корректными, ошибочными и пустыми значениями регулярных выражений |
| Integration (Бэкенд) | `./backend/tests/integration/test_staff_directory_db.py` | Взаимодействие с базой данных PostgreSQL: получение списков отделов, городов, фильтрация, батч-обновление порядка пользователей, сброс скрытых флагов |
| Unit (Фронтенд) | `./frontend/tests/unit/use-highlight.spec.ts` | Валидация composable подсветки: XSS-безопасность, обработка HTML-сущностей, fuzz-тестирование опасных скриптов в строке поиска |
| Unit (Фронтенд) | `./frontend/tests/unit/users-api.spec.ts` | Корректность сборки URL экспорта справочника с различными query-параметрами |
| Unit (Фронтенд) | `./frontend/tests/unit/staff-edit.spec.ts` | Логика администрирования в `useStaffEdit`: инициализация состояния, группировка, сохранение payload и переключение видимости |
| Unit (Фронтенд) | `./frontend/tests/unit/staff-filters.spec.ts` | Фильтрация в `useStaffFilters`: debounce-задержка, сброс пагинации и URL-синхронизация |

---

## Связанные документы

- `./docs/_TEMPLATE.md` — Шаблон структуры документации модулей портала
- `./docs/user-attributes.md` — Документация модуля кастомных атрибутов пользователей
