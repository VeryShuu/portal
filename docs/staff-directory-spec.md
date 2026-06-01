# Документация: Модуль «Справочник сотрудников»

> **Когда читать:** справочник `/staff`, отделы, режим карточек, порядок сотрудников.
> **Ключевой код:** `app/models/staff_order.py`, `app/api/users/`, `frontend/src/composables/useStaffEdit.ts`.
> **ADR:** —.

Раздел отражает **текущее состояние реализации** модуля справочника сотрудников
(маршрут `/staff`) и служит точкой опоры для дальнейших доработок.

---

## 1. Назначение

Корпоративный справочник всех активных сотрудников портала (аналог `ab.mage.ru`):
- плоская таблица, сгруппированная по отделам;
- альтернативный режим «Карточки»;
- поиск, фильтр по отделу/офису, экспорт в CSV, печатная версия (готовый
  XLSX-справочник, сгруппированный по отделам, с шапкой и оформлением для печати);
- клик по строке/карточке → переход на `/users/:id`;
- **режим редактирования (только для админа):** drag-and-drop порядка отделов
  и сотрудников внутри отделов, скрытие выбранных пользователей из справочника.

Доступ:
- просмотр — любой аутентифицированный пользователь (`CurrentUser`);
- редактирование порядка/скрытий — только `role=admin`.

Порядок и список скрытых, заданные админом, видны **всем пользователям**
(сохраняются в БД).

---

## 2. Карта модуля

### 2.1 Бэкенд

| Файл | Что добавлено / изменено |
|---|---|
| `./backend/app/schemas/user.py` | Схемы `DepartmentList`, `OfficeList` (`{ items: list[str] }`); поля `staff_sort_order`, `staff_hidden` в `UserPublic`; новые схемы `StaffOrderUserItem`, `StaffOrderUpdate`, `StaffOrderState` |
| `./backend/app/api/users/users_repo.py` | `list_departments(ordered=…)`, `list_offices()`, `stream_users()`, `_build_order(sort)`, `_select_users(sort)`; параметры `office`, `sort`, `include_hidden` в `list_users_page` / `count_users` / `stream_users`; расширен `_build_list_conditions`; новые helpers `fetch_department_order`, `fetch_hidden_user_ids`, `replace_department_order`, `apply_user_sort_orders` (**один батч-`UPDATE` через `CASE WHEN`**), `apply_hidden_user_ids` |
| `./backend/app/api/users/__init__.py` | Общий `router = APIRouter(prefix="/users", tags=["users"])`; импорт под-модулей `routes_admin`, `routes_me`, `routes_staff` в порядке, гарантирующем регистрацию literal-путей **до** `/{user_id}` |
| `./backend/app/api/users/routes_staff.py` | Справочник: `GET /users`, `/departments`, `/offices`, `/export` (CSV + XLSX), `GET /{user_id}`, админские `GET/PUT /admin/staff-order`. Хелпер `_csv_safe(v)` для защиты от CSV-injection. **403** при `include_hidden=true` от не-админа (вместо тихого сброса). XLSX-генерация делегируется в `staff_xlsx.py` (`export_users_xlsx`); бизнес-логика PUT делегируется в `staff_service.py` (`apply_staff_order`). |
| `./backend/app/api/users/staff_service.py` | Бизнес-логика `PUT /admin/staff-order`: `apply_staff_order` — атомарная замена порядка отделов / пользователей / скрытых, транзакция через `try/except` + `db.rollback()`. |
| `./backend/app/api/users/staff_xlsx.py` | Генератор XLSX `export_users_xlsx(...)` через `openpyxl` (печатная версия справочника: заголовок, шапка, группировка по отделам, freeze panes, landscape A4, `fitToWidth=1`). |
| `./backend/app/api/users/routes_me.py` | `/me`, `PATCH /me/profile`, `PATCH /me/preferences`, `POST /me/avatar`, `PATCH /me/password` |
| `./backend/app/api/users/routes_admin.py` | `POST /admin/sync`, `PATCH /admin/{id}/role`, `POST /admin/local`, `GET /admin/{id}/groups`, `PATCH /admin/{id}/profile`, `DELETE /admin/{id}`, `PATCH /admin/{id}/password` |
| `./backend/app/utils/phone.py` | Общая утилита `apply_phone_regex(phone, pattern)` — вынесена из `routes_staff.py`; используется в CSV- и XLSX-экспорте |
| `./backend/pyproject.toml` | Добавлена зависимость `openpyxl>=3.1.0` (для XLSX-экспорта печатной версии справочника) |
| `./backend/app/api/system_settings/_public.py` | Схема `StaffSettingsOut` (`{ phone_extract_regex: str }`); `GET /portal/staff-settings` |
| `./backend/app/core/system_config.py` | Поле `phone_extract_regex: str` в `_SystemSettingsBase` (с regex-валидатором) |
| `./backend/app/models/user.py` | Поля `staff_sort_order: int \| None`, `staff_hidden: bool` |
| `./backend/app/models/staff_order.py` | Новая модель `StaffDepartmentOrder` (таблица `staff_department_orders`) |
| `./backend/app/models/__init__.py` | Регистрация `StaffDepartmentOrder` |
| `./backend/migrations/versions/044_staff_directory_order.py` | Миграция: `users.staff_sort_order`, `users.staff_hidden`, таблица `staff_department_orders`, индекс `idx_users_staff_sort_order` |

### 2.2 Фронтенд

| Файл | Что добавлено / изменено |
|---|---|
| `./frontend/src/api/users.ts` | `fetchUserDepartments(ordered)`, `fetchUserOffices`, `buildUsersExportUrl` (с параметром `format: 'csv' \| 'xlsx'`); параметры `office`/`sort`/`include_hidden` в `fetchUsers`; `staff_sort_order`/`staff_hidden` в `UserPublic`; типы `StaffOrderState`, `StaffOrderUpdate`; функции `fetchStaffOrder`, `saveStaffOrder` |
| `./frontend/src/queries/keys.ts` | `users.list(params)`, `users.departments(ordered)`, `users.offices()`; `portal.staffSettings()` (ключ `users.staffOrder()` удалён) |
| `./frontend/src/queries/users.ts` | `useStaffListQuery` (с `keepPreviousData`), `useUserDepartmentsQuery({ ordered })`, `useUserOfficesQuery`, `useStaffSettingsQuery`. (`useStaffOrderQuery` удалён как мёртвый) |
| `./frontend/src/composables/useHighlight.ts` | XSS-safe утилита подсветки совпадений (`<mark class="staff-hl">`) |
| `./frontend/src/composables/usePhoneFormat.ts` | Утилита форматирования телефонов через `phone_extract_regex` из настроек портала |
| `./frontend/src/composables/useStaffFilters.ts` | **(новое)** Composable URL ↔ refs: `searchInput`, `q`, `departmentFilter`, `officeFilter`, `page`, `hasActiveFilters`, `onSearchInput` (debounce 300мс), `onFilterChange`, `resetFilters`, `onPageChange`, `syncToUrl`, watch `route.query` для back/forward |
| `./frontend/src/composables/useStaffEdit.ts` | **(новое)** Composable edit-mode: `editMode`, `editGroups`, `dirty`, `saving`, `entering` (отдельно от `saving`), `enterEdit`, `cancelEdit` (с `useDialog().warning` при `dirty`), `saveEdit`, `toggleUserHidden`, `bindSortables`/`destroySortables`, `buildGroupsFromList`. `bindSortables` вызывается **один раз** на входе в edit; в `onEnd` DOM возвращается в исходное состояние и мутируется `editGroups` (без re-bind). Проверка `oldIdx===newIdx && fromIdx===toIdx` для юзеров — не помечаем `dirty` |
| `./frontend/src/router.ts` | `ROUTES.STAFF = '/staff'` |
| `./frontend/src/composables/useAppMenu.ts` | Пункт «Справочник» в группе `g-services`, `activeKey`/`defaultTitle`/`routeMap` |
| `./frontend/src/pages/StaffDirectoryPage.vue` | **(рефакторинг)** Тонкий оркестратор (~380 строк): Vue Query setup, computed `tableGroups`/`total`, сборка `StaffFilters` + view-компонентов. Логика поделена на composables и view-компоненты |
| `./frontend/src/components/staff/StaffFilters.vue` | **(новое)** Верхняя панель: input + 2 select + reset + view-switch + actions (edit/export/print/cancel/save). Кнопка «Печатная версия» доступна в обоих режимах (table/grid), с тултипом-подсказкой `staff.printHint`. Эмитит события `update:*`, `reset`, `set-view`, `enter-edit`, `export`, `print`, `cancel-edit`, `save-edit` |
| `./frontend/src/components/staff/StaffTableView.vue` | **(новое)** Read-only таблица + группировка по отделам, скелетоны загрузки |
| `./frontend/src/components/staff/StaffGridView.vue` | **(новое)** Read-only сетка карточек |
| `./frontend/src/components/staff/StaffEditView.vue` | **(новое)** Edit-mode разметка (drag-drop списки групп/юзеров). Эмитит `root-ready` с `HTMLElement` для `editRootRef` |
| `./frontend/src/components/StaffRow.vue` | Строка таблицы (с подсветкой, форматированием телефона, копированием, переходом на профиль). Добавлено: `tabindex="0"`, `role="link"`, `@keydown.enter`; в `goToProfile` пропуск навигации при непустом `window.getSelection()` |
| `./frontend/src/components/StaffCard.vue` | Карточка сетки (avatar/initials, контакты, доп. атрибуты из схемы, форматирование телефона). Тег отдела ограничен по ширине (max-width + ellipsis через `:deep(.n-tag__content)`), полное имя — в `title=` |
| `./frontend/src/components/profile/ProfileInfoCard.vue` | Лейбл `users.fields.phone` теперь = «Внутренний телефон» |
| `./frontend/src/i18n/ru.json`, `./frontend/src/i18n/en.json` | `nav.staff`, `staff.*`, `staff.edit.*`, обновлён `users.fields.phone`. Новое: `staff.print` = «Печатная версия», `staff.printHint` (тултип) |

### 2.3 Тесты

| Файл | Назначение |
|---|---|
| `./backend/tests/unit/test_staff_directory.py` | 401/200 для эндпоинтов, валидация `sort`/`format` (`csv\|xlsx`; `pdf` → 422), проброс `office`/`sort`, контракт CSV, защита от UUID-коллизии маршрутов, **CSV-injection regression** (`=`/`+`/`-`/`@` → префикс `'`), **403** при `include_hidden=true` от не-админа, **200** при `include_hidden=true` от админа |
| `./backend/tests/unit/test_phone.py` | **(новое)** Юнит-тесты `apply_phone_regex`: regex с группой, без группы, невалидный regex (не бросает), пустой phone, пустой pattern |
| `./backend/tests/integration/test_staff_directory_db.py` | Реальная БД: `list_departments` (distinct/exclude blank), `list_offices`, фильтр `office`, поиск по `position`/телефону, `sort=department` (NULLS LAST), `stream_users`; **новое:** `apply_user_sort_orders` (батч-UPDATE для 100 юзеров, корректность; пустой payload; дедупликация), `replace_department_order` (идемпотентность, дедупликация), `apply_hidden_user_ids` (сброс предыдущих скрытых) |
| `./frontend/tests/unit/use-highlight.spec.ts` | Экранирование HTML/regex, реактивность к `ref`, **новое:** fuzz-тесты XSS-пейлоадов (`<script>`, `onerror=`, `"><svg>`, JNDI), multiline, HTML-сущности |
| `./frontend/tests/unit/users-api.spec.ts` | `buildUsersExportUrl` — формат, кодирование, обязательный `format=csv` |
| `./frontend/tests/unit/staff-edit.spec.ts` | **(новое)** `useStaffEdit`: `enterEdit` строит группы из мок-данных, `saveEdit` отправляет корректный payload (departments/users/hidden_user_ids), `toggleUserHidden` переключает и помечает `dirty` |
| `./frontend/tests/unit/staff-filters.spec.ts` | **(новое)** `useStaffFilters`: debounce 300мс, сброс `page=1` при изменении фильтра, `resetFilters`, инициализация из URL |

---

## 3. Бэкенд

### 3.1 `GET /users/departments`

Список уникальных непустых отделов всех активных пользователей. Используется
для dropdown-фильтра и для построения порядка отделов в админ-режиме.

**Параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `ordered` | `bool` | `false` | Если `true` — сначала отделы из `staff_department_orders` (в порядке `sort_order`), потом «новые» отделы алфавитно; иначе — алфавитно весь список |

**Реализация:** `list_departments(db, *, ordered=False)` в
`./backend/app/api/users/users_repo.py`:
1. `SELECT DISTINCT department … WHERE deleted_at IS NULL AND length(trim(department))>0 ORDER BY department ASC`.
2. Если `ordered=True` — поверх алфавитного списка применяется ключ сортировки
   с приоритетом `staff_department_orders.sort_order`.

**Ответ:** `{ "items": ["Административный отдел", "Бухгалтерия", …] }`.

### 3.2 `GET /users/offices`

То же, но из `users.attributes->>'city'`.

### 3.3 Расширение `GET /users`

Добавленные query-параметры:

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `office` | `str \| None` | `None` | Точная фильтрация по `attributes->>'city'` |
| `sort` | `Literal["full_name","department","staff_custom"]` | `"full_name"` | См. ниже |
| `include_hidden` | `bool` | `false` | Включить пользователей с `staff_hidden=true`. Применяется **только** для `sort=staff_custom`; для всех остальных значений `sort` скрытие игнорируется (т.е. пользователь всегда виден). Разрешено **только админу** — для не-админа эндпоинт возвращает **403** (`Only admins can request hidden users`). |
| `page_size` | `int` | `50` | `ge=1, le=1000` (cap увеличен с 500 для поддержки админ-режима, который грузит весь список одним запросом). |

**Семантика сортировок:**
- `full_name` → `(full_name ASC)`.
- `department` → `(department ASC NULLS LAST, full_name ASC)`.
- `staff_custom` → `LEFT JOIN staff_department_orders ON dept = User.department`,
  затем `(staff_department_orders.sort_order ASC NULLS LAST, User.department ASC NULLS LAST, User.staff_sort_order ASC NULLS LAST, User.full_name ASC)`.
  То есть: отделы без явного порядка уходят в конец и сортируются по имени;
  пользователи без `staff_sort_order` внутри отдела — в конец и тоже по имени.

Поиск `q` (ILIKE-pattern) проверяется по полям:
- `full_name`, `email`, `position`,
- `phone` — текущая колонка User (хранит **внутренний** номер),
- `attributes->>'internal_phone'` — наследие схемы атрибутов,
- `attributes->>'mobile'` — мобильный телефон (ключ Keycloak).

> **Важно:** в текущих данных `users.phone` фактически содержит **внутренний** номер
> (источник — Keycloak). Мобильный номер хранится в `attributes.mobile`.

### 3.4 Порядок маршрутов и декомпозиция файлов

С версии после рефакторинга роуты разнесены на три файла, но **прикрепляются
к единому `router`** в `./backend/app/api/users/__init__.py`:

```python
router = APIRouter(prefix="/users", tags=["users"])

from . import routes_admin, routes_me, routes_staff  # noqa: E402,F401
```

Порядок импорта критичен: `routes_admin` и `routes_me` регистрируют свои
literal-сегменты **до** того, как `routes_staff` зарегистрирует `/{user_id}`.
Внутри `routes_staff.py` literal-маршруты (`/departments`, `/offices`,
`/export`, `/admin/staff-order`) также объявлены **до** `/{user_id}` —
иначе FastAPI попытается распарсить literal-сегмент как UUID и вернёт 422.

Регрессионные тесты на коллизию: `./backend/tests/unit/test_staff_directory.py::TestListDepartments::test_route_does_not_collide_with_user_id`
(и аналогичные для других маршрутов).

### 3.5 `GET /users/export` — CSV / XLSX

Единая ручка для двух форматов выгрузки. Выбор формата — query-параметр
`format` с regex-валидацией `^(csv|xlsx)$` (значение по умолчанию `csv`).

**Параметры:** те же, что у `GET /users` (`q`, `department`, `office`, `sort`),
плюс `format`. По умолчанию `sort="department"`. При `sort != "staff_custom"`
стрим/выгрузка включают скрытых (`include_hidden=True`); при
`sort == "staff_custom"` — скрытые исключены (экспорт «как видит пользователь»).

#### 3.5.1 CSV (`format=csv`)

Стриминг (`StreamingResponse` + асинхронный генератор `users_repo.stream_users`,
`yield_per=500`, `partitions(500)`).

**Ответ:** `text/csv; charset=utf-8`, заголовок
`Content-Disposition: attachment; filename="staff-YYYY-MM-DD.csv"`. Тело
начинается с UTF-8 BOM (`\ufeff`) для корректного открытия в Excel.

**Колонки CSV (порядок):**

```
full_name, position, department, office, internal_phone, mobile_phone, email
```

При этом:
- `internal_phone` ← `apply_phone_regex(user.phone, phone_extract_regex)` — значение из `user.phone`, прогнанное через regex форматирования телефона из системных настроек (если regex не задан — берётся `user.phone` as-is)
- `mobile_phone` ← `attrs.get("mobile", "")` (ключ Keycloak: `mobile`)
- `office` ← `attrs.get("city", "")` (ключ Keycloak: `city`)

Все значения, перед записью в CSV, проходят через `_csv_safe(v)`: если строка
начинается с `=`, `+`, `-`, `@`, `\t` или `\r` — она префиксуется одиночной
кавычкой `'`. Защита от **CSV-injection** при открытии файла в Excel
(см. OWASP). Регрессионный тест: `test_staff_directory.py::test_csv_injection_prefixed`.

Хелпер `apply_phone_regex(phone, pattern)` вынесен в `./backend/app/utils/phone.py`:
выполняет `re.search(pattern, phone)`, возвращает первую группу захвата
(или весь match, если групп нет); при пустом или некорректном regex возвращает
строку без изменений. Покрыт тестами в `./backend/tests/unit/test_phone.py`.

#### 3.5.2 XLSX (`format=xlsx`) — печатная версия справочника

Используется кнопкой «Печатная версия» на фронтенде вместо браузерной печати
страницы. Цель — готовый PDF-подобный документ, который можно распечатать и
положить на стол. Внешний вид воспроизводит образец `Справочник АО МАГЭ.xlsx`
(лист «СВОД»).

**Реализация:** функция `export_users_xlsx(...)` в
`./backend/app/api/users/staff_xlsx.py`, библиотека `openpyxl`. Файл строится
в памяти (`io.BytesIO`) и отдаётся одним `Response` (не `StreamingResponse`,
т.к. `openpyxl` не поддерживает истинный стриминг zip-архива).

Источник данных — тот же `users_repo.stream_users(...)` с теми же фильтрами и
правилом скрытых, что и в CSV-ветке (передаются те же `q`, `department`,
`office`, `sort`).

**Ответ:**
- `media_type`: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition: attachment; filename="staff-YYYY-MM-DD.xlsx"`

**Структура листа** (`title="Справочник"`):

1. Row 1 (merged `A1:G1`): заголовок «Справочник сотрудников АО "МАГЭ"», 14pt bold, по центру.
2. Row 2 (merged `A2:G2`): подзаголовок «Сформирован: DD.MM.YYYY», курсив, серый.
3. Row 4: шапка таблицы, белый шрифт на синем (`#305496`):
   ```
   №, Ф.И.О., Должность, Внутр., Мобильный, E-mail, Город
   ```
4. Далее — чередование:
   - **строка-разделитель отдела** (merged `A..G`, светло-голубой фон `#D9E1F2`, bold);
   - строки сотрудников этого отдела с номером `№` внутри отдела начиная с 1.

**Оформление и печать:**
- ширины колонок: `5, 36, 44, 10, 18, 30, 16`;
- `freeze_panes` — на первой строке данных (шапка зафиксирована при прокрутке);
- `print_title_rows = "4:4"` — шапка повторяется на каждой печатной странице;
- ландшафтная ориентация A4, узкие поля (0.4 / 0.5 дюйма),
  `fitToWidth=1`, `fitToHeight=0` — таблица гарантированно вписывается по ширине;
- бордеры (`Side(style="thin", color="BFBFBF")`) на всех ячейках данных.

**Значения:** те же правила, что в CSV, минус CSV-injection префикс (для XLSX
не актуально — `openpyxl` сам экранирует формулы при чтении):
- `Внутр.` ← `apply_phone_regex(user.phone, phone_extract_regex)`;
- `Мобильный` ← `attributes.mobile`;
- `Город` ← `attributes.city`.

> **Нумерация `№`** — сквозная внутри **каждого** отдела (сбрасывается на новом
> отделе), что соответствует образцу и облегчает чтение «бумажной» версии.

### 3.6 `GET /portal/staff-settings`

Публичный (без `CurrentUser`) эндпоинт, возвращающий настройки портала,
необходимые для фронтенда справочника.

**Реализация:** в `./backend/app/api/system_settings.py`, модель ответа `StaffSettingsOut`.

**Ответ:**
```json
{ "phone_extract_regex": "..." }
```

| Поле | Тип | Описание |
|---|---|---|
| `phone_extract_regex` | `str` | Regex для извлечения нужного вида номера из `user.phone`. Пустая строка — форматирование отключено |

`phone_extract_regex` хранится в системных настройках (`/data/settings/system.json`),
редактируется через **Админ-панель → Системные настройки**. Значение кешируется
через `load_system_settings_shared(redis)`.

### 3.7 Админ-эндпоинты порядка/скрытий

#### `GET /users/admin/staff-order`

Доступ: `AdminDep` (`role=admin`).

**Ответ (`StaffOrderState`):**
```json
{
  "departments": ["Администрация", "Бухгалтерия", …],
  "hidden_user_ids": ["uuid1", "uuid2", …]
}
```

- `departments` — отделы, для которых задан явный порядок (по возрастанию
  `staff_department_orders.sort_order`).
- `hidden_user_ids` — `id` всех активных (`deleted_at IS NULL`) пользователей
  с `staff_hidden=true`.

#### `PUT /users/admin/staff-order`

Доступ: `AdminDep` (`role=admin`).

**Тело (`StaffOrderUpdate`):**
```json
{
  "departments": ["Администрация", "Бухгалтерия", "Производство"],
  "users": [
    { "id": "uuid-A", "sort_order": 0 },
    { "id": "uuid-B", "sort_order": 1 },
    …
  ],
  "hidden_user_ids": ["uuid-X", "uuid-Y"]
}
```

Поведение — **атомарная полная замена** (все шаги в одной транзакции, при
ошибке — `db.rollback()`):
1. `replace_department_order(departments)` — `DELETE FROM staff_department_orders`
   + `INSERT` с присвоением `sort_order = idx`. Дубликаты и пустые строки
   отсеиваются на роуте, сохраняется первое вхождение.
2. `apply_user_sort_orders(users)` — сначала `UPDATE users SET staff_sort_order=NULL WHERE deleted_at IS NULL AND staff_sort_order IS NOT NULL AND id NOT IN (...)` (сброс пользователей, отсутствующих в payload), затем **один батч-UPDATE через `CASE WHEN`**:
   ```sql
   UPDATE users
      SET staff_sort_order = CASE id
        WHEN <uuid1> THEN 0
        WHEN <uuid2> THEN 1
        ...
      END
    WHERE id IN (<uuid1>, <uuid2>, ...) AND deleted_at IS NULL
   ```
   Дубликаты `id` отсеиваются на роуте (первое вхождение). На 1000 юзеров
   выполняется **2 SQL-statement** (сброс + батч), а не 1001 как раньше.
3. `apply_hidden_user_ids(hidden_user_ids)` — сначала `UPDATE users SET staff_hidden=false`
   для всех ранее скрытых, затем `UPDATE … SET staff_hidden=true WHERE id IN (...)`.
4. `db.commit()` (в `try`); при исключении — `db.rollback()` и проброс `HTTPException`.
5. Возвращается актуальный `StaffOrderState` (повторное чтение из БД).

> **Важно:** `users.sort_order` в payload — это позиция **внутри отдела**.
> Бэкенд не знает о группировке — он просто пишет полученное число; именно
> группировка через `staff_custom`-сортировку даёт визуальный «по отделам».
> Поэтому фронтенд обязан нумеровать пользователей внутри каждого отдела с нуля.

### 3.8 БД — миграция 044

Файл: `./backend/migrations/versions/044_staff_directory_order.py` (revision `044`,
down_revision `043`).

Добавляет:
- `users.staff_sort_order INTEGER NULL` — позиция пользователя внутри отдела
  в `/staff`. `NULL` = в конец (алфавитно).
- `users.staff_hidden BOOLEAN NOT NULL DEFAULT false` — скрыть из `/staff`
  (но оставить видимым везде остальном: `/users/:id`, поиск, проч.).
- Таблица `staff_department_orders (department TEXT PRIMARY KEY, sort_order INTEGER NOT NULL)`
  — глобальный порядок отделов.
- Индекс `idx_users_staff_sort_order ON users (department, staff_sort_order) WHERE deleted_at IS NULL`.

Поля `internal_phone`, `city`, `mobile` по-прежнему живут в `users.attributes`
(JSONB) — миграцию по этим полям не делаем.

---

## 4. Фронтенд

### 4.1 Роутер и меню

- `./frontend/src/router.ts`: `ROUTES.STAFF = '/staff'`, маршрут с `name: 'staff'`,
  `meta.title = 'nav.staff'`, ленивый импорт `StaffDirectoryPage.vue`.
- `./frontend/src/composables/useAppMenu.ts`: пункт «Справочник» с иконкой
  `PeopleOutline` в группе `g-services` (между «Ссылки» и «Фотогалерея»),
  `activeKey` подхватывается по префиксу `ROUTES.STAFF`.

### 4.2 API-обёртки (`./frontend/src/api/users.ts`)

```ts
fetchUsers({ q, department, office, sort, page, page_size, include_hidden }, { signal })
fetchUserDepartments({ ordered }?): Promise<{ items: string[] }>
fetchUserOffices(): Promise<{ items: string[] }>
buildUsersExportUrl({ q, department, office, sort, format }): string
// format: 'csv' | 'xlsx' (по умолчанию 'csv')

fetchStaffOrder(): Promise<StaffOrderState>
saveStaffOrder(body: StaffOrderUpdate): Promise<StaffOrderState>
```

Типы:
```ts
interface StaffOrderState  { departments: string[]; hidden_user_ids: string[] }
interface StaffOrderUpdate { departments: string[]; users: { id: string; sort_order: number }[]; hidden_user_ids: string[] }
```

`UserPublic` дополнен:
```ts
staff_sort_order?: number | null
staff_hidden?: boolean
```

`buildUsersExportUrl` использует `BASE_URL` из `./frontend/src/api/index.ts`
(по умолчанию `/api/v1`), добавляет `format` (по умолчанию `csv`, явный
`xlsx` — для кнопки «Печатная версия»), пропускает пустые параметры.
Используется через `window.location.assign(...)` в кнопках «Экспорт» и
«Печатная версия».

### 4.3 Vue Query

- `useStaffListQuery(params)` — `staleTime: 60_000`, `placeholderData: keepPreviousData`.
- `useUserDepartmentsQuery({ ordered })` — `staleTime: 300_000`; ключ зависит от `ordered`.
- `useUserOfficesQuery()` — `staleTime: 300_000`.
- `useStaffSettingsQuery()` — `staleTime: 300_000`; ключ `queryKeys.portal.staffSettings()`.
- Ключи списков: `queryKeys.users.list(...)`, `.departments(ordered)`, `.offices()`.

> Ранее существовавший `useStaffOrderQuery` и ключ `users.staffOrder()` удалены
> как мёртвый код — admin staff-order загружается прямым вызовом `fetchUsers({ sort: 'staff_custom', include_hidden: true, page_size: 1000 })` в `useStaffEdit.enterEdit()`. Публичные функции `fetchStaffOrder` / `saveStaffOrder`
> в `api/users.ts` сохранены (последняя используется при `saveEdit`).

### 4.4 Страница `StaffDirectoryPage.vue` (после рефакторинга)

Страница превращена в **тонкий оркестратор (~380 строк)**. Вся бизнес-логика
вынесена в composables (`useStaffFilters`, `useStaffEdit`), а разметка — в
view-компоненты (`StaffFilters`, `StaffTableView`, `StaffGridView`,
`StaffEditView`). До рефакторинга страница занимала ~998 строк и совмещала
URL-синхронизацию, edit-mode и DOM-разметку в одном файле.

#### Структура

```
StaffDirectoryPage.vue
├── useStaffFilters()       — URL ↔ state (q, department, office, page)
├── useStaffEdit({ editRootRef }) — edit-mode + sortablejs
├── useStaffListQuery, useUserDepartmentsQuery, useUserOfficesQuery
├── <StaffFilters>          — верхняя панель (input/select/buttons)
├── <StaffTableView>        — read-only таблица + группировка
├── <StaffGridView>         — read-only сетка карточек
└── <StaffEditView>         — edit-mode разметка (DnD-списки)
```

#### Состояние

- В URL query: `q`, `department`, `office`, `page` (управляется
  `useStaffFilters.syncToUrl()` + watch на `route.query` для back/forward).
- В `localStorage`: `staff:view` (`'table' | 'grid'`).
- На `<md` (мобильный) `effectiveView` всегда `'grid'` (через `useBreakpoints`),
  переключатель режимов скрыт.
- Сортировка `sort=staff_custom` всегда — **выбора сортировки в UI больше нет**
  (старый ключ `staff:sort` в `localStorage` не используется и не читается).

#### Верхняя панель (sticky)

1. `n-input` поиска с дебаунсом 300мс (`useDebounceFn`).
2. `n-select` отдела (опции из `useUserDepartmentsQuery({ ordered: true })`).
3. `n-select` города (опции из `useUserOfficesQuery`).
4. «Сбросить» (видна, если активен любой фильтр).
5. Переключатель режима «Таблица / Карточки» (только desktop).
6. Кнопка **Редактировать порядок** — видна **только для `auth.isAdmin`**;
   входит в edit-mode (см. 4.5).
7. Кнопка **Экспорт CSV** (`window.location.assign(buildUsersExportUrl({ sort: 'staff_custom' }))`).
8. Кнопка **Печатная версия** — скачивает готовый XLSX-справочник
   (`window.location.assign(buildUsersExportUrl({ sort: 'staff_custom', format: 'xlsx' }))`),
   текущие фильтры (`q`, `department`, `office`) пробрасываются в URL.
   Доступна в обоих режимах (table/grid). Тултип — `staff.printHint`.
   Браузерная печать страницы (`window.print()`) **больше не используется**:
   она давала шумный вывод и не подходила для «бумажного» справочника, поэтому
   заменена на серверную сборку XLSX (см. 3.5.2).

В edit-mode фильтры/поиск/переключатель режима/экспорт/печать **скрыты или
заблокированы**, вместо них показываются «Отменить» и «Сохранить».

При смене любого фильтра — `page` сбрасывается в 1.

#### Таблица (текущие колонки)

| Заголовок | Источник | Адаптив |
|---|---|---|
| ФИО (`staff.fields.fullName`) | `user.full_name` | всегда |
| Должность (`staff.fields.position`) | `user.position` | скрывается на ≤480px |
| Внутренний (`staff.fields.internalPhone`) | **`formatPhone(user.phone)`** (см. раздел 6) | скрывается на ≤768px |
| Мобильный (`staff.fields.mobilePhone`) | `attributes.mobile` | всегда |
| E-mail (`staff.fields.email`) | `user.email` | всегда |
| Город (`staff.fields.office`) | `attributes.city` | скрывается на ≤1024px |

> Колонка «Отдел» из таблицы **удалена** — отдел показан только в виде
> заголовка группы. Сортировки кликом по заголовкам нет — порядок задаётся
> админом (`sort=staff_custom`).

**Группировка:** при пустом `department`-фильтре строки разбиваются на блоки
`<tbody>` с заголовком группы (`<tr.staff-group-header>`) перед каждым отделом.
Заголовок группы:
- занимает `colspan="6"`,
- центрирован (`text-align: center`),
- содержит **только название отдела** (без счётчика «N чел.»).

При активном `department`-фильтре группировка не применяется (плоский список).

#### Карточки

CSS-grid `repeat(auto-fill, minmax(280px, 1fr))`. На карточке: аватар (или
инициалы), ФИО, должность, тег с отделом, контакты с иконками
(`CallOutline` → внутренний = `formatPhone(user.phone)`, `PhonePortraitOutline` → мобильный
= `attributes.mobile`, `MailOutline` → email, `LocationOutline` → город = `attributes.city`).
Дополнительно — другие enabled-атрибуты из `useUserAttributeSchemaQuery`,
кроме зарезервированных (`internal_phone`, `city`, `mobile`).

#### Загрузка / пустое состояние

- Первая загрузка: `SkeletonCard` ×6 (grid) или 8 строк-скелетонов с
  `colspan="6"` (table).
- Последующие — оверлей через CSS-класс `is-fetching`, данные от
  `keepPreviousData`.
- Пустой результат — `EmptyState variant="search"` с `staff.empty` /
  `staff.emptyHint`.

#### Пагинация

`n-pagination` снизу при `total > pageSize` (PAGE_SIZE = 100). В edit-mode
пагинация скрыта.

#### Печать

`@media print` в `<style>` страницы скрывает `.app-header`, `.app-sidebar`,
`.staff-filters`, `.staff-pagination`, `.staff-view-switch`, `.staff-actions`;
скрывает grid и принудительно показывает таблицу; добавляет `break-inside: avoid`
для строк и `break-after: avoid` для заголовка группы.

### 4.5 Режим редактирования (admin-only) — composable `useStaffEdit`

Активируется кнопкой **«Редактировать порядок»** (видна только при
`auth.isAdmin`). Вся логика вынесена в composable
`./frontend/src/composables/useStaffEdit.ts`. Страница только передаёт
`editRootRef` (через событие `root-ready` от `StaffEditView`) и связывает
методы с кнопками `StaffFilters`.

#### API composable

```ts
useStaffEdit({ editRootRef }): {
  editMode, editGroups, dirty, saving, entering,
  enterEdit, cancelEdit, saveEdit, toggleUserHidden,
  bindSortables, destroySortables, buildGroupsFromList,
}
```

- `entering` (отдельный ref от `saving`) — true пока идёт первый `fetchUsers`
  в `enterEdit()`. До рефакторинга оба состояния были перегружены в одном
  `saving`-ref, что приводило к ложным состояниям loading-индикатора.

#### Загрузка данных

При входе в режим:
1. `enterEdit()` зовёт `fetchUsers({ sort: 'staff_custom', include_hidden: true, page: 1, page_size: 1000 })`
   — получаем **все** активные пользователи в текущем «администраторском»
   порядке, включая скрытых.
2. Список группируется по `department` функцией `buildGroupsFromList`
   (порядок групп = порядок первого появления отдела в списке, который уже
   учитывает `staff_department_orders.sort_order`).
3. `editGroups: Ref<{ department: string; users: UserPublic[] }[]>` — локальная
   мутируемая модель состояния.
4. `editMode = true`, **`bindSortables()` вызывается один раз** после
   `await nextTick()`.

> Cap `page_size` на бэкенде поднят до **1000**, чтобы один запрос покрывал
> типичную численность компании. Если станет тесно — потребуется явная
> пагинация в edit-mode (или специальный неразделённый эндпоинт).

#### UI в edit-mode

- Фильтры/поиск/переключатель режима/экспорт/печать **заблокированы или скрыты**.
- Подсказка `staff.edit.hint` с пояснением.
- Каждая группа отдела — карточка с заголовком и handle `ReorderThreeOutline`
  (drag-handle для перетаскивания всего отдела).
- Внутри отдела `<ul.staff-edit__user-list>` со строками-сотрудниками; у каждой
  строки слева handle `ReorderTwoOutline` (для перетаскивания пользователя),
  ФИО + должность, badge «Скрыт» (если `staff_hidden`), кнопка-«глаз»
  (`EyeOutline` / `EyeOffOutline`) для тоггла скрытия.
- В верхней панели: «Сохранить» (disabled пока `!dirty`, индикатор `loading`),
  «Отменить», метка «Есть несохранённые изменения» (`staff.edit.unsaved`)
  при `dirty`.

#### Drag-and-drop (sortablejs)

Используется библиотека `sortablejs` (уже установлена). Создаются два рода
инстансов:

1. **Отделы** — на корневом `editRootRef`, `handle: '.drag-handle--dept'`,
   `draggable: '.staff-edit__group'`. По `onEnd` `editGroups` пересобирается
   (`splice` старого индекса → `splice` нового), `dirty = true`.
2. **Пользователи** — по одному инстансу на каждый
   `<ul.staff-edit__user-list>`, объединены в общую `group: 'staff-users'`,
   что позволяет перетаскивать пользователя **между отделами**.
   - При интра-групповом перемещении меняется только порядок внутри
     `editGroups[idx].users`.
   - При меж-групповом — у пользователя обновляется `user.department` на имя
     целевого отдела (для UI). На сервер отправляется `(id, sort_order)`,
     а `department` фактически уже привязан в БД и подменён не будет — здесь
     UI-side состояние остаётся актуальным до перезагрузки данных. **Реальное
     изменение `department` пользователя через эту операцию НЕ происходит**;
     это известное ограничение (см. раздел 7).

**Ключевое улучшение после рефакторинга:** `bindSortables()` вызывается
**только один раз** при входе в режим (раньше — после каждой перестановки,
что вызывало рекурсивное пересоздание инстансов). В `onEnd` сначала
**возвращаем DOM-элемент на исходную позицию** (через `removeChild` +
`insertBefore`), а Vue ререндерит правильное состояние через мутацию
`editGroups`. Sortable-инстансы при этом остаются живыми.

Добавлена проверка `oldIdx === newIdx && fromIdx === toIdx` в обработчике
перемещения пользователя — false-positive drop (пользователь брошен на ту же
позицию) не помечает `dirty`.

#### Скрытие пользователя

Кнопка-«глаз» в строке вызывает `toggleUserHidden(userId)`, который иммутабельно
переключает `staff_hidden` у пользователя в `editGroups`. `dirty = true`.

#### Сохранение / отмена

- **Сохранить (`saveEdit`):**
  - `departments` = непустые имена отделов в текущем порядке.
  - `users` = `flatMap` по группам, с пересчётом `sort_order = idx` внутри
    каждой группы (нумерация от 0 в каждой группе).
  - `hidden_user_ids` = `id` всех пользователей с `staff_hidden=true`.
  - `PUT /users/admin/staff-order` с этим payload.
  - На успехе: `n-message.success(staff.edit.saved)`, `editMode=false`,
    `queryClient.invalidateQueries({ queryKey: queryKeys.users.all })`.
  - На ошибке: `n-message.error(staff.edit.saveError)`.
- **Отменить (`cancelEdit`):**
  - Если `dirty === false` — мгновенный выход (`finalizeExit`).
  - Если `dirty === true` — показываем `useDialog().warning` с
    `staff.edit.unsaved` / `staff.edit.discard` / `common.cancel`. Пока
    пользователь не подтвердит «Отбросить» — режим не выходит. Раньше
    `cancelEdit` молча терял изменения.
  - При выходе `editGroups` сбрасывается в `[]`, sortable-инстансы
    уничтожаются.

#### Скрытые пользователи в read-only

В `sort=staff_custom` бэкенд **всегда** исключает `staff_hidden=true`
(параметр `include_hidden=true` от не-админа возвращает **403**, а у админа
в обычном режиме просмотра не передаётся). Скрытые остаются видимыми в:
- любом другом `sort` (`full_name`, `department`),
- профиле `/users/:id`,
- результатах поиска через другие модули,
- CSV-экспорте при `sort != 'staff_custom'` (для `staff_custom` — тоже
  исключены, чтобы выгрузка совпадала с тем, что видит пользователь).

### 4.6 i18n

Неймспейс `staff.*` (`./frontend/src/i18n/{ru,en}.json`). Содержит
`title`, `pageSub`, `searchPlaceholder`, `filterDepartment`, `filterOffice`,
`filterAll`, `resetFilters`, `viewTable`/`viewGrid`, `export`, `print`,
`printPartial`, `copy`/`copied`/`copyFailed`, `empty`/`emptyHint`, `total`,
`groupCount` (хранится в i18n, в UI больше не используется),
`fields.{fullName,position,internalPhone,mobilePhone,email,office,department}`.

Подсекция `staff.edit.*`:
`enter`, `exit`, `save`, `saved`, `saveError`, `discard`, `hint`,
`dragDept`, `dragUser`, `hide`, `show`, `hiddenBadge`, `unsaved`.

Также в `users.fields.phone` подменено на «Внутренний телефон» / «Internal phone»
для согласованности с карточкой профиля
(`./frontend/src/components/profile/ProfileInfoCard.vue`).

### 4.7 Форматирование телефонов (`usePhoneFormat`)

Composable `./frontend/src/composables/usePhoneFormat.ts`. Используется в
`StaffRow.vue` и `StaffCard.vue` для отображения `user.phone` (внутреннего номера).

```ts
const { formatPhone } = usePhoneFormat()
formatPhone(phone: string | null | undefined): string
```

Алгоритм:
1. Если `phone` пуст — вернуть `''`.
2. Получить `phone_extract_regex` из `useStaffSettingsQuery()`.
3. Если regex задан — выполнить `new RegExp(pattern).exec(phone)`:
   - есть совпадение → вернуть первую группу захвата (`m[1]`) или весь match (`m[0]`);
   - некорректный regex или нет совпадения → вернуть `phone` без изменений.
4. Если regex не задан — вернуть `phone` без изменений.

> `href="tel:..."` всегда содержит **сырой** `user.phone` (без форматирования),
> чтобы вызов по клику работал корректно. `formatPhone` применяется только к
> отображаемому тексту.

**Настройка regex:** Админ-панель → Системные настройки → поле
«Regex извлечения телефона». Валидация — при сохранении на бэкенде
(`_SystemSettingsBase._validate_phone_extract_regex`). Пример: `(\d{3,5})` —
вычленяет короткий внутренний номер из полного телефонного номера.

### 4.8 Подсветка (`useHighlight`)

Composable `useHighlight(MaybeRefOrGetter<string|null|undefined>)` возвращает
`(text) => htmlString`. Алгоритм:
1. Экранировать HTML текста.
2. Если `query` пуст после `trim()` — вернуть как есть.
3. Иначе — собрать regex (i, g) из escape-HTML(escape-regex(query)) и
   обернуть совпадения в `<mark class="staff-hl">…</mark>`.

CSS `.staff-hl` определён в `StaffDirectoryPage.vue` (жёлтая подсветка).

### 4.9 Копирование контактов

Кнопка `CopyOutline` рядом с email/телефонами в строке и карточке. Появляется
по hover (на touch — всегда видна). Использует `navigator.clipboard.writeText`,
показывает `n-message.success` с локализованным лейблом и подавляет всплытие
клика (чтобы не уйти на профиль).

---

## 5. Тестирование

### 5.1 Backend (unit, без БД)

```bash
cd backend && python3 -m pytest tests/unit/test_staff_directory.py tests/unit/test_phone.py -q
```

Покрывает: 401 без auth для всех новых эндпоинтов; 200 + контракт; фильтрация
None/blank в `list_departments`; защита от UUID-коллизии маршрутов; валидация
`sort`/`format`; CSV содержит BOM, корректный `Content-Disposition` и колонки;
параметры `office`/`sort`/`q` пробрасываются в репозиторий; **CSV-injection
regression** (значения с префиксом `=/+/-/@` экранируются); **403** при
`include_hidden=true` от не-админа, **200** — от админа. `test_phone.py`
покрывает `apply_phone_regex` (regex с группой / без группы / невалидный /
пустые входы).

### 5.2 Backend (integration, реальная БД)

```bash
INTEGRATION_DB=true cd backend && python3 -m pytest \
    tests/integration/test_staff_directory_db.py -q
```

Требует Postgres и переменную `INTEGRATION_DB=true`. Использует SAVEPOINT-
изоляцию из `./backend/tests/integration/conftest.py`.

### 5.3 Frontend (vitest)

```bash
cd frontend && npx vitest run \
    tests/unit/use-highlight.spec.ts \
    tests/unit/users-api.spec.ts \
    tests/unit/staff-edit.spec.ts \
    tests/unit/staff-filters.spec.ts
```

Покрытие:
- `use-highlight.spec.ts` — экранирование HTML/regex, реактивность к `ref`,
  fuzz-тесты XSS-пейлоадов (`<script>`, `onerror=`, `"><svg>`, JNDI),
  multiline, HTML-сущности.
- `users-api.spec.ts` — `buildUsersExportUrl`: формат, кодирование,
  обязательный `format=csv`.
- `staff-edit.spec.ts` — `useStaffEdit`: `enterEdit` строит группы из
  мок-данных, `saveEdit` отправляет корректный payload
  (`departments`/`users`/`hidden_user_ids`), `toggleUserHidden`
  переключает и помечает `dirty`.
- `staff-filters.spec.ts` — `useStaffFilters`: debounce 300мс, сброс
  `page=1` при изменении фильтра, `resetFilters`, инициализация из URL.

### 5.4 Линтеры / типы

```bash
cd backend && python3 -m ruff check .
cd frontend && npx vue-tsc --noEmit
cd frontend && npx eslint src tests
```

---

## 6. Известные особенности данных

- В текущей БД `users.phone` фактически содержит **внутренний** номер
  (источник — Keycloak). Поэтому колонка «Внутренний» в UI и поле
  `internal_phone` в CSV-экспорте читаются именно из `user.phone`.
- Отображаемый вид номера форматируется через `phone_extract_regex` (см. раздел 4.7).
  Настраивается через Admin UI без деплоя.
- Колонка «Мобильный» / поле `mobile_phone` в CSV читаются из `users.attributes->>'mobile'`
  (ключ Keycloak). Поле заполнено там, где в Keycloak задан атрибут `mobile`.
- Колонка «Город» / поле `office` в CSV читаются из `users.attributes->>'city'`
  (ключ Keycloak). Соответствует полю «Город» в профиле пользователя.
- Поиск `q` ILIKE покрывает: `full_name`, `email`, `position`, `user.phone`,
  `attributes.internal_phone`, `attributes.mobile` — работает и по короткому
  внутреннему номеру (типа «312»), и по мобильному.
- `users.staff_sort_order` — позиция **внутри отдела**; глобально не уникальна.
  При смене отдела (через Keycloak-синхронизацию или drag-and-drop)
  `staff_sort_order` остаётся прежним числом, но интерпретируется уже в новом
  отделе — поэтому после смены отдела рекомендуется пересохранить порядок.
- `staff_department_orders` — независимая таблица; если отдел исчезнет из БД
  пользователей, его запись в `staff_department_orders` останется «висеть»,
  но не повлияет на вывод (LEFT JOIN). При желании можно периодически чистить
  GC-задачей (не реализовано).

---

## 7. Что осталось / возможные доработки

- **Перенос между отделами через drag-and-drop:** в edit-mode UI разрешает
  тащить пользователя в другой отдел, но `PUT /users/admin/staff-order`
  не меняет `users.department`. Сейчас визуально пользователь окажется в
  целевом отделе только до перезагрузки страницы; после рефреша он вернётся
  в свой исходный отдел (потому что `staff_custom` группирует по `department`
  из БД). Чтобы реализовать честный перенос — расширить `StaffOrderUpdate`
  полем `department_overrides: { user_id: department }` и применять `UPDATE users SET department=...`
  в `PUT`-эндпоинте (или зафиксировать ограничение в UI и не разрешать
  меж-групповой drag).
- **Пагинация в edit-mode:** сейчас грузим до 1000 пользователей одним
  запросом. При компании >1000 человек потребуется или поднять cap, или
  сделать постраничное редактирование (последнее усложнит drag-and-drop
  между страницами).
- **Конкурентные сохранения:** `PUT /users/admin/staff-order` не использует
  optimistic-locking. Если два админа редактируют одновременно — выиграет
  тот, кто сохранил последним. Можно добавить ETag/`updated_at`.
- **Очистка `staff_department_orders`:** периодическая задача удаления
  записей для отделов, которых нет в `users.department`.
- **Админ-редактирование `attributes`:** добавить поле `attributes` в
  `AdminPatchProfileRequest` и пробросить в `users_service.admin_patch_profile`,
  чтобы заполнять `internal_phone` / `city` / `mobile` локально без Keycloak.
- **Сидинг атрибутов:** через админку «Атрибуты профиля» убедиться, что
  записи `city` (Город) и `mobile` (Мобильный телефон) созданы с корректными
  `label_ru`/`label_en` и `enabled=true`. В справочнике `city` и `mobile`
  зарезервированы (вынесены в явные колонки/поля) и в блок «прочих
  атрибутов» не попадают.
- **Индексы:** при росте таблицы — дополнительные частичные индексы:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_users_department_active
    ON users (department) WHERE deleted_at IS NULL;
  CREATE INDEX IF NOT EXISTS idx_users_attr_city
    ON users ((attributes->>'city')) WHERE deleted_at IS NULL;
  ```
- **Виртуализация** табличного режима для очень больших списков
  (`n-virtual-list`).
- **XLSX-экспорт:** параметр `format` уже задан как enum — расширить регекс
  и добавить ветку с `openpyxl`/`xlsxwriter`.
- **UI-доработки** из аудита `./sprav.md` (sticky-заголовки отделов с
  collapse, цветные инициалы, тег города в строке таблицы, hover-actions
  для звонка/копирования, плавающий save-bar в edit-mode, поиск в edit-mode,
  массовые действия, чипы активных фильтров, view в URL и пр.).
- **`beforeRouteLeave`-guard в edit-mode:** в текущей реализации `cancelEdit`
  ловит выход кнопкой «Отменить» через диалог, но переход по другому
  маршруту/закрытие вкладки изменения теряет. Нужен `onBeforeRouteLeave` +
  `beforeunload`.

---

## 8. Что НЕ меняется

- Логика синхронизации Keycloak (`department`, `attributes` приходят оттуда).
- Страница `/users/:id` (`UserProfileView.vue`) — кроме лейбла «Внутренний
  телефон» в `ProfileInfoCard.vue`. Скрытые в `/staff` пользователи здесь
  по-прежнему видны.
- Права просмотра `/staff`: страница доступна всем аутентифицированным;
  админская роль нужна только для редактирования порядка/скрытий.
- Маршруты `/users/me`, `/users/{user_id}` и прочие подмаршруты — порядок
  объявления остаётся; новые `/departments`, `/offices`, `/export`,
  `/admin/staff-order` объявлены перед `/{user_id}`.
