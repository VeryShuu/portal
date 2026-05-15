# ТЗ: Страница «Справочник сотрудников»

## 1. Контекст и цель

Требуется добавить отдельную вкладку в навигации портала с корпоративным справочником сотрудников — аналог страницы https://ab.mage.ru.

**Референс (ab.mage.ru):** плоская таблица всех активных сотрудников, **сгруппированная по отделам**, с колонками: ФИО, Должность, Внутренний (телефон), Мобильный (телефон), E-mail, Офис, Отдел. Без аватаров, без статусов присутствия, без пагинации (всё на одной странице, ~300 записей). Поиск выполняется средствами браузера (Ctrl+F).

**Наш справочник** должен повторить функциональность референса и добавить:
- Поиск по ФИО/email/должности с дебаунсом
- Фильтр по отделу и офису
- Альтернативное отображение «Карточки» для удобства просмотра
- Клик по строке/карточке → переход на `/users/:id`

---

## 2. Анализ существующей кодовой базы

### 2.1 Что уже есть и не требует изменений

| Компонент | Файл | Назначение |
|---|---|---|
| API-эндпоинт | `./backend/app/api/users/routes.py` | `GET /users` — список с пагинацией, поиском (`q`) и фильтром по отделу |
| Репозиторий | `./backend/app/api/users/users_repo.py` | `list_users_page()` сортирует по `full_name`, `count_users()` |
| Модель БД | `./backend/app/models/user.py` | Поля: `full_name`, `department`, `position`, `phone`, `email`, `avatar_url`, `presence_status`, `attributes` (JSONB) |
| Pydantic-схема | `./backend/app/schemas/user.py` | `UserPublic` содержит все нужные поля |
| Frontend API | `./frontend/src/api/users.ts` | `fetchUsers(params)` принимает `{q, department, page, page_size}` |
| Профиль сотрудника | `./frontend/src/pages/UserProfileView.vue` | Маршрут `/users/:id` |
| Атрибуты профиля | `./frontend/src/api/userAttributeMappings.ts` | `fetchAttributeSchema()` возвращает список enabled-атрибутов с `attr_key`, `label_ru`, `label_en`, `sort_order` |
| Хук схемы атрибутов | `./frontend/src/queries/users.ts` | `useUserAttributeSchemaQuery()` — уже реализован |
| Query-ключи | `./frontend/src/queries/keys.ts` | В `users` уже есть `all`, `detail`, `attributeSchema`, `keycloakGroups` |
| i18n | `./frontend/src/i18n/ru.json`, `./frontend/src/i18n/en.json` | Ключи `users.fields.*`, `users.title`, `users.notFound` |
| Skeleton/Empty | `./frontend/src/components/SkeletonCard.vue`, `./frontend/src/components/EmptyState.vue` | Готовые компоненты |
| Debounce | `./frontend/src/composables/useDebounceFn.ts` | Используется для поиска |

### 2.2 Что требует добавления

| Компонент | Файл | Действие |
|---|---|---|
| Бэкенд — репозиторий | `./backend/app/api/users/users_repo.py` | Добавить `list_departments()`, `list_offices()`, `stream_users()`; расширить `_build_list_conditions` (поиск по `position` + `attributes->>'internal_phone'`, фильтр `office`), `list_users_page` (`office`, `sort`), `count_users` (`office`) |
| Бэкенд — роуты | `./backend/app/api/users/routes.py` | Добавить `GET /users/departments`, `GET /users/offices`, `GET /users/export`; расширить `GET /users` параметрами `office`, `sort` |
| Frontend API | `./frontend/src/api/users.ts` | Добавить `fetchUserDepartments()`, `fetchUserOffices()`, `buildUsersExportUrl()`; расширить `fetchUsers` параметрами `office`, `sort` |
| Composable | `./frontend/src/composables/useHighlight.ts` | Создать утилиту подсветки совпадений с экранированием HTML |
| Query-ключи | `./frontend/src/queries/keys.ts` | Добавить `users.list`, `users.departments`, `users.offices` |
| Query-хуки | `./frontend/src/queries/users.ts` | Добавить `useStaffListQuery`, `useUserDepartmentsQuery`, `useUserOfficesQuery` |
| Роутер | `./frontend/src/router.ts` | Добавить `ROUTES.STAFF` и маршрут `/staff` |
| Меню | `./frontend/src/composables/useAppMenu.ts` | Добавить пункт «Справочник» в группу `g-services` |
| Страница | `./frontend/src/pages/StaffDirectoryPage.vue` | Создать страницу |
| Компонент строки | `./frontend/src/components/StaffRow.vue` | Строка таблицы (выделить для переиспользования и тестируемости) |
| Компонент карточки | `./frontend/src/components/StaffCard.vue` | Карточка сетки |
| i18n | `./frontend/src/i18n/ru.json`, `./frontend/src/i18n/en.json` | Добавить `nav.staff`, `staff.*` |
| БД seed | Через админку «Атрибуты профиля» | Создать атрибуты `internal_phone` и `office` (выполняется вручную после деплоя) |

---

## 3. Требования к бэкенду

### 3.1 Новый эндпоинт `GET /users/departments`

**Назначение:** отсортированный список уникальных отделов всех активных пользователей. Используется для dropdown-фильтра.

**Авторизация:** `CurrentUser` (любая аутентифицированная роль).

**Ответ:**
```json
{ "items": ["Административный отдел", "Бухгалтерия", "Отдел ИТ"] }
```

**Реализация (`./backend/app/api/users/users_repo.py`):**
```python
async def list_departments(db: AsyncSession) -> list[str]:
    res = await db.execute(
        select(User.department)
        .where(
            User.deleted_at.is_(None),
            User.department.isnot(None),
            func.length(func.trim(User.department)) > 0,
        )
        .distinct()
        .order_by(User.department.asc())
    )
    return [row for row in res.scalars().all() if row and row.strip()]
```

### 3.2 Новый эндпоинт `GET /users/offices`

**Назначение:** уникальные значения офисов для фильтра. Берутся из `users.attributes->>'office'`.

**Ответ:** `{ "items": ["Московский офис АО 'МАГЭ'", "Мурманский офис АО 'МАГЭ'"] }`

**Реализация:**
```python
async def list_offices(db: AsyncSession) -> list[str]:
    office_expr = User.attributes["office"].astext
    res = await db.execute(
        select(office_expr)
        .where(
            User.deleted_at.is_(None),
            office_expr.isnot(None),
            func.length(func.trim(office_expr)) > 0,
        )
        .distinct()
        .order_by(office_expr.asc())
    )
    return [row for row in res.scalars().all() if row and row.strip()]
```

### 3.3 Расширение `GET /users`

Добавить параметры:

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `office` | `str \| None` | `None` | Точная фильтрация по `attributes->>'office'` |
| `sort` | `Literal["full_name", "department"]` | `"full_name"` | `department` = сортировка по `(department NULLS LAST, full_name)` |

Также расширить поиск `q` — добавить ILIKE по `position` и по внутреннему телефону (`attributes->>'internal_phone'`). Поиск по внутреннему номеру важен — пользователи часто ищут по короткому номеру вида «312».

**Изменения в `_build_list_conditions`:**
```python
def _build_list_conditions(
    q: str | None, department: str | None, office: str | None
) -> list[Any]:
    conditions: list[Any] = [User.deleted_at.is_(None)]
    if q:
        pattern = f"%{q}%"
        conditions.append(
            User.full_name.ilike(pattern)
            | User.email.ilike(pattern)
            | User.position.ilike(pattern)
            | User.attributes["internal_phone"].astext.ilike(pattern)
        )
    if department:
        conditions.append(User.department == department)
    if office:
        conditions.append(User.attributes["office"].astext == office)
    return conditions
```

**Изменения в `list_users_page`:**
```python
async def list_users_page(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    office: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> Sequence[User]:
    conditions = _build_list_conditions(q, department, office)
    if sort == "department":
        order = (User.department.asc().nullslast(), User.full_name.asc())
    else:
        order = (User.full_name.asc(),)
    stmt = (
        select(User)
        .where(*conditions)
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await db.execute(stmt)
    return res.scalars().all()
```

`count_users` принимает те же `q`, `department`, `office`.

### 3.4 Порядок маршрутов в `routes.py`

**Критично:** `/users/departments`, `/users/offices` и `/users/me` объявляются **до** `/users/{user_id}`, иначе FastAPI попытается распарсить строку как UUID и вернёт 422.

```python
@router.get("/departments", response_model=DepartmentList, summary="Список отделов")
async def list_departments_route(db: DbDep, _: CurrentUser) -> DepartmentList:
    items = await users_repo.list_departments(db)
    return DepartmentList(items=items)


@router.get("/offices", response_model=OfficeList, summary="Список офисов")
async def list_offices_route(db: DbDep, _: CurrentUser) -> OfficeList:
    items = await users_repo.list_offices(db)
    return OfficeList(items=items)
```

Новые схемы в `./backend/app/schemas/user.py`:
```python
class DepartmentList(BaseModel):
    items: list[str]


class OfficeList(BaseModel):
    items: list[str]
```

### 3.5 Новый эндпоинт `GET /users/export`

**Назначение:** выгрузка текущего отфильтрованного списка сотрудников в CSV. Кнопка «Экспорт» на странице справочника передаёт те же параметры, что и обычный список (`q`, `department`, `office`, `sort`), но **без пагинации**.

**Авторизация:** `CurrentUser` (любая аутентифицированная роль).

**Query-параметры:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `q` | `str \| None` | `None` | См. `GET /users` |
| `department` | `str \| None` | `None` | То же |
| `office` | `str \| None` | `None` | То же |
| `sort` | `Literal["full_name", "department"]` | `"department"` | По умолчанию для экспорта — по отделу |
| `format` | `Literal["csv"]` | `"csv"` | Заложено как enum для будущего `xlsx`, но в v1 поддерживаем только CSV |

**Ответ:** `text/csv; charset=utf-8` со стримингом (`StreamingResponse`), заголовок `Content-Disposition: attachment; filename=staff-YYYY-MM-DD.csv`.

**Колонки CSV (в порядке):** `full_name, position, department, office, internal_phone, mobile_phone, email`.

**Реализация (`./backend/app/api/users/users_repo.py`):**
```python
async def stream_users(
    db: AsyncSession,
    *,
    q: str | None,
    department: str | None,
    office: str | None,
    sort: str,
) -> AsyncIterator[User]:
    conditions = _build_list_conditions(q, department, office)
    if sort == "department":
        order = (User.department.asc().nullslast(), User.full_name.asc())
    else:
        order = (User.full_name.asc(),)
    stmt = select(User).where(*conditions).order_by(*order).execution_options(
        yield_per=500
    )
    res = await db.stream(stmt)
    async for partition in res.scalars().partitions(500):
        for user in partition:
            yield user
```

**Реализация роута (`./backend/app/api/users/routes.py`):**
```python
import csv
import io
from datetime import date

from fastapi.responses import StreamingResponse


@router.get("/export", summary="Экспорт справочника в CSV")
async def export_users(
    db: DbDep,
    _: CurrentUser,
    q: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None),
    office: str | None = Query(default=None),
    sort: str = Query(default="department", pattern="^(full_name|department)$"),
    format: str = Query(default="csv", pattern="^csv$"),
) -> StreamingResponse:
    headers = [
        "full_name", "position", "department", "office",
        "internal_phone", "mobile_phone", "email",
    ]

    async def generate():
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        # BOM для корректного открытия в Excel
        yield "\ufeff" + buf.getvalue()
        buf.seek(0); buf.truncate(0)
        async for user in users_repo.stream_users(
            db, q=q, department=department, office=office, sort=sort
        ):
            writer.writerow([
                user.full_name or "",
                user.position or "",
                user.department or "",
                (user.attributes or {}).get("office", ""),
                (user.attributes or {}).get("internal_phone", ""),
                user.phone or "",
                user.email or "",
            ])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    filename = f"staff-{date.today().isoformat()}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**Размещение:** маршрут объявить **до** `/{user_id}` (вместе с `/departments`, `/offices`).

### 3.6 Существующая модель БД — без изменений

Поля «Внутренний телефон» и «Офис» хранятся в `users.attributes` (JSONB) с ключами `internal_phone` и `office`. Никакие колонки не добавляются.

Заполнение: либо через Keycloak-синхронизацию, либо через админ-API `PATCH /users/admin/{user_id}/profile`. Если требуется ручное редактирование `attributes` через админку — добавить поле `attributes: dict[str, Any] | None = None` в `AdminPatchProfileRequest` и пробросить в `users_service.admin_patch_profile` (опционально, выходит за рамки этой задачи).

### 3.7 Тесты бэкенда

В `./backend/tests/` (если каталог существует — следовать существующим паттернам, иначе пропустить):
- `GET /users/departments` без авторизации → 401
- `GET /users/departments` с авторизацией → 200, отсортированный список без дубликатов и пустых строк
- `GET /users/offices` аналогично, читает из `attributes->>'office'`
- `GET /users?office=X` фильтрует по атрибуту
- `GET /users?sort=department` возвращает отсортированный по отделу список
- `GET /users?q=...` ищет в т.ч. по `position` и `attributes->>'internal_phone'`
- `GET /users/export` без авторизации → 401
- `GET /users/export` возвращает `text/csv`, `Content-Disposition: attachment`, BOM в начале, корректные строки с фильтром по `department`

---

## 4. Требования к фронтенду

### 4.1 Роутер (`./frontend/src/router.ts`)

В объект `ROUTES` добавить:
```ts
STAFF: '/staff',
```

В дерево дочерних маршрутов под `AppLayout`:
```ts
{
  path: ROUTES.STAFF,
  name: 'staff',
  component: () => import('./pages/StaffDirectoryPage.vue'),
  meta: { title: 'nav.staff' },
},
```

### 4.2 Навигационное меню (`./frontend/src/composables/useAppMenu.ts`)

Импорт иконки рядом с существующими импортами `@vicons/ionicons5`:
```ts
import { PeopleOutline } from '@vicons/ionicons5'
```

В группу `g-services` (между «Ссылки» и «Фотогалерея»):
```ts
{ label: renderNavLabel(t('nav.staff'), 'staff'), key: 'staff', icon: renderIcon(PeopleOutline) }
```

В `activeKey` computed:
```ts
if (path.startsWith(ROUTES.STAFF)) return 'staff'
```

В `defaultTitle`-map:
```ts
staff: t('nav.staff'),
```

В `routeMap`:
```ts
staff: ROUTES.STAFF,
```

### 4.3 Frontend API (`./frontend/src/api/users.ts`)

Расширить `fetchUsers`:
```ts
export async function fetchUsers(
  params?: {
    q?: string
    department?: string
    office?: string
    sort?: 'full_name' | 'department'
    page?: number
    page_size?: number
  },
  options?: { signal?: AbortSignal },
): Promise<PaginatedResponse<UserPublic>> {
  return api<PaginatedResponse<UserPublic>>('/users', { params, signal: options?.signal })
}
```

Добавить:
```ts
export async function fetchUserDepartments(): Promise<{ items: string[] }> {
  return api<{ items: string[] }>('/users/departments')
}

export async function fetchUserOffices(): Promise<{ items: string[] }> {
  return api<{ items: string[] }>('/users/offices')
}

export function buildUsersExportUrl(params?: {
  q?: string
  department?: string
  office?: string
  sort?: 'full_name' | 'department'
}): string {
  const search = new URLSearchParams()
  if (params?.q) search.set('q', params.q)
  if (params?.department) search.set('department', params.department)
  if (params?.office) search.set('office', params.office)
  if (params?.sort) search.set('sort', params.sort)
  search.set('format', 'csv')
  const qs = search.toString()
  return `/api/users/export${qs ? `?${qs}` : ''}`
}
```

> Используем построитель URL вместо `fetch`, чтобы скачивание шло через нативный `<a download>` — это корректно стримит файл и работает с куки/Auth-заголовком сессии без выкачивания в память. Если в проекте API использует другой префикс (`/api/v1/` и т.п.) — взять из существующих хелперов в `./frontend/src/api/index.ts`.

### 4.4 Query-ключи (`./frontend/src/queries/keys.ts`)

В объект `users` добавить:
```ts
list: (params?: Record<string, unknown>) => ['users', 'list', params ?? {}] as const,
departments: () => ['users', 'departments'] as const,
offices: () => ['users', 'offices'] as const,
```

### 4.5 Query-хуки (`./frontend/src/queries/users.ts`)

Добавить (рядом с существующим `useUserAttributeSchemaQuery`):
```ts
import { keepPreviousData } from '@tanstack/vue-query'
import { fetchUsers, fetchUserDepartments, fetchUserOffices } from '../api/users'

export function useStaffListQuery(
  params: MaybeRefOrGetter<{
    q?: string
    department?: string
    office?: string
    sort?: 'full_name' | 'department'
    page?: number
    page_size?: number
  }>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.users.list(toValue(params))),
    queryFn: ({ signal }) => fetchUsers(toValue(params), { signal }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
}

export function useUserDepartmentsQuery() {
  return useQuery({
    queryKey: queryKeys.users.departments(),
    queryFn: fetchUserDepartments,
    staleTime: 300_000,
  })
}

export function useUserOfficesQuery() {
  return useQuery({
    queryKey: queryKeys.users.offices(),
    queryFn: fetchUserOffices,
    staleTime: 300_000,
  })
}
```

### 4.6 Страница `StaffDirectoryPage.vue`

#### URL и заголовок
- **URL:** `/staff`
- **Заголовок страницы (h1):** `t('staff.title')` = «Справочник сотрудников»
- **Подзаголовок:** `t('staff.pageSub')`
- **Счётчик:** `t('staff.total', { count: total })` справа от заголовка

#### Верхняя панель фильтров (sticky под шапкой)

Слева направо:
1. `n-input` — поиск (placeholder `t('staff.searchPlaceholder')`, иконка лупы, clearable). **Дебаунс 300мс** через `useDebounceFn`. Параметр `q` запроса.
2. `n-select` — отдел: `t('staff.filterDepartment')`. Опции: `[{ label: t('staff.filterAll'), value: null }, ...departments]`. Параметр `department`.
3. `n-select` — офис: `t('staff.filterOffice')`. Аналогично. Параметр `office`.
4. `n-button text` — `t('staff.resetFilters')`. Виден, только если активен хотя бы один фильтр. Сбрасывает `q`, `department`, `office`, `page = 1`.
5. `n-button-group` — переключатель режима отображения (`n-tooltip` на каждой кнопке):
   - `ListOutline` (по умолчанию) — режим «Таблица»
   - `GridOutline` — режим «Карточки»
6. `n-button` (secondary, иконка `DownloadOutline`) — `t('staff.export')`. Открывает `<a :href="buildUsersExportUrl({ q, department, office, sort })" download>` через `window.location.assign(...)`. Браузер запускает скачивание; индикатор загрузки в кнопке на время `fetch HEAD` опционально.
7. `n-button` (text, иконка `PrintOutline`) — `t('staff.print')`. Вызывает `window.print()`. Видна только в режиме «Таблица».

Состояние фильтров и режима хранится:
- `q`, `department`, `office`, `page` — в URL query (`useRoute`/`useRouter`), чтобы ссылки были шарящимися и работала кнопка «Назад»
- `view`, `sort` — в `localStorage` под ключом `staff:view` и `staff:sort`

При смене любого фильтра `page` сбрасывается в 1.

#### Основная область — два режима

**Режим «Таблица» (`view: 'table'`, по умолчанию):**

Используется `n-data-table` с колонками:

| Ключ | Заголовок | Содержимое | Сорт | Адаптив |
|---|---|---|---|---|
| `full_name` | `staff.fields.fullName` | ФИО (clickable → `/users/:id`) | да (`sort=full_name`) | всегда |
| `position` | `staff.fields.position` | Должность | — | скрывается на `<sm` |
| `internal_phone` | `staff.fields.internalPhone` | `attributes.internal_phone` (моноширинный) | — | скрывается на `<md` |
| `phone` | `staff.fields.mobilePhone` | `phone` поля User, `<a href="tel:">` | — | всегда |
| `email` | `staff.fields.email` | `<a href="mailto:">` | — | всегда |
| `office` | `staff.fields.office` | `attributes.office` | — | скрывается на `<lg` |
| `department` | `staff.fields.department` | Отдел | да (`sort=department`) | скрывается на `<md` |

**Группировка по отделам:** если `sort = 'department'` (по умолчанию для таблицы) и `department`-фильтр пуст — рендерить **строку-заголовок отдела** перед каждой группой строк (sticky внутри таблицы). Реализация: рендерить вручную через `n-table` + `<tbody>` + `<tr class="group-header">`, либо через кастомную обёртку, т.к. `n-data-table` не поддерживает row groups из коробки. **Простейший вариант:** обычный `<table>` со sticky `<thead>` и группирующими `<tr>`.

Заголовок группы содержит: название отдела + бейдж с количеством сотрудников.

**Режим «Карточки» (`view: 'grid'`):**

CSS-grid: `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;`

Карточка содержит:
- Аватар (`n-avatar`, круглый, 48px, инициалы при отсутствии `avatar_url`)
- ФИО (жирный, кликабельный → `/users/:id`)
- Должность (серый, 1 строка с `text-overflow: ellipsis`)
- Тег с отделом (`n-tag` size=small)
- Список контактов (иконка + значение, кликабельные `tel:` / `mailto:`):
  - Внутренний телефон (`attributes.internal_phone`) — иконка `CallOutline`
  - Мобильный (`phone`) — иконка `PhonePortraitOutline`
  - Email — иконка `MailOutline`
  - Офис (`attributes.office`) — иконка `LocationOutline`

Если в `useUserAttributeSchemaQuery` есть **дополнительные** атрибуты, кроме `internal_phone` и `office`, со значением у пользователя — показать их под основными контактами в формате `label_ru: value`. Сортировка по `sort_order`.

#### Загрузка данных

Запрос `useStaffListQuery({ q, department, office, sort, page, page_size: 100 })`:
- `page_size = 100` (фиксировано)
- При первой загрузке — **`SkeletonCard.vue`** ×6 (grid) или 8 строк-скелетонов (table)
- При смене фильтров — `placeholderData: keepPreviousData` показывает предыдущие данные + лёгкий полупрозрачный оверлей с `n-spin`
- Если `total === 0` — `EmptyState.vue` с `t('staff.empty')` / `t('staff.emptyHint')`

#### Пагинация

`n-pagination` внизу страницы, видна если `total > page_size`. `pageSlot=7`, `showSizePicker=false`. Параметр `page` синхронизирован с URL.

При активной группировке по отделам пагинация **остаётся** — это страничная порция, отсортированная по отделу; группы могут разрезаться между страницами, что приемлемо (как в любых табличных списках).

#### Дополнительно

- `presence_status` **не отображается** в первой версии (нет в референсе). Поле остаётся в `UserPublic`, но игнорируется UI-страницы.
- Доступ: страница доступна всем аутентифицированным (`requiresAuth: true` через существующий guard в роутере, без role-checks).
- Аналитика: при открытии страницы вызвать существующий хелпер логирования просмотра (если такой используется на других страницах — посмотреть `HomePage.vue`/`KbListPage.vue`; если паттерна нет — пропустить).

#### Адаптив

- На `<md` (≤768px): таблица превращается в режим «Карточки» автоматически (через `useBreakpoints`); переключатель режима скрывается, активен только grid.
- На `<sm` (≤480px): фильтры схлопываются в одну колонку (vertical stack).

### 4.7 Локализация

**`./frontend/src/i18n/ru.json`** — добавить:
```json
"nav": {
  "staff": "Справочник"
},
"staff": {
  "title": "Справочник сотрудников",
  "pageSub": "Контакты и информация о сотрудниках компании",
  "searchPlaceholder": "Поиск по имени, должности или email…",
  "filterDepartment": "Отдел",
  "filterOffice": "Офис",
  "filterAll": "Все",
  "resetFilters": "Сбросить",
  "viewTable": "Таблица",
  "viewGrid": "Карточки",
  "export": "Экспорт CSV",
  "print": "Печать",
  "printPartial": "Печатается только текущая страница. Для полной выгрузки используйте «Экспорт».",
  "copy": "Копировать",
  "copied": "Скопировано: {label}",
  "copyFailed": "Не удалось скопировать",
  "empty": "Сотрудники не найдены",
  "emptyHint": "Попробуйте изменить параметры поиска или сбросить фильтры",
  "total": "Всего: {count}",
  "groupCount": "{count} чел.",
  "fields": {
    "fullName": "ФИО",
    "position": "Должность",
    "internalPhone": "Внутренний",
    "mobilePhone": "Мобильный",
    "email": "E-mail",
    "office": "Офис",
    "department": "Отдел"
  }
}
```

**`./frontend/src/i18n/en.json`** — добавить:
```json
"nav": {
  "staff": "Directory"
},
"staff": {
  "title": "Staff Directory",
  "pageSub": "Company employee contacts and information",
  "searchPlaceholder": "Search by name, position or email…",
  "filterDepartment": "Department",
  "filterOffice": "Office",
  "filterAll": "All",
  "resetFilters": "Reset",
  "viewTable": "Table",
  "viewGrid": "Cards",
  "export": "Export CSV",
  "print": "Print",
  "printPartial": "Only the current page will be printed. Use Export for the full list.",
  "copy": "Copy",
  "copied": "Copied: {label}",
  "copyFailed": "Failed to copy",
  "empty": "No employees found",
  "emptyHint": "Try changing search parameters or resetting filters",
  "total": "Total: {count}",
  "groupCount": "{count} ppl.",
  "fields": {
    "fullName": "Name",
    "position": "Position",
    "internalPhone": "Ext.",
    "mobilePhone": "Mobile",
    "email": "Email",
    "office": "Office",
    "department": "Department"
  }
}
```

Существующие ключи `users.fields.*` не дублировать — таблица справочника использует свой неймспейс `staff.fields.*` для гибкости (короткие заголовки).

### 4.8 Дополнительный функционал v1

#### 4.8.1 Копирование контактов в один клик

В режимах **«Таблица»** и **«Карточки»**: рядом с email/мобильным/внутренним телефоном — иконка-кнопка `CopyOutline` (16px, появляется на hover ячейки/строки контакта; на тач-устройствах видна всегда).

```ts
async function copyValue(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value)
    message.success(t('staff.copied', { label }))
  } catch {
    message.error(t('staff.copyFailed'))
  }
}
```

Значение копируется как есть (без `tel:`/`mailto:`). После клика — `n-message` тост на 1.5 сек: «Скопировано: E-mail» / «Скопировано: телефон» и т.п. `message`-инстанс берётся через `useMessage()` (Naive UI).

Клик по самой иконке копирования **не должен** триггерить навигацию на профиль (`event.stopPropagation()` на обработчике).

#### 4.8.2 Подсветка совпадений (highlight)

При активном поисковом запросе (`q` непустой) — подсвечивать совпадения в полях `full_name`, `email`, `position`, `attributes.internal_phone` через `<mark>` с фирменным фоном.

Реализация — composable `useHighlight.ts` (либо локальная утилита внутри страницы):

```ts
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

const ESCAPE_HTML: Record<string, string> = {
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, c => ESCAPE_HTML[c])
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function useHighlight(query: MaybeRefOrGetter<string | undefined>) {
  return (text: string | null | undefined): string => {
    const safe = escapeHtml(text ?? '')
    const q = toValue(query)?.trim()
    if (!q) return safe
    const re = new RegExp(`(${escapeRegex(escapeHtml(q))})`, 'gi')
    return safe.replace(re, '<mark class="staff-hl">$1</mark>')
  }
}
```

В шаблоне: `<span v-html="hl(user.full_name)" />`. **Обязательно** экранировать пользовательский ввод через `escapeHtml` перед регэкспом и перед вставкой — без этого XSS.

CSS:
```css
.staff-hl {
  background: var(--n-color-warning-suppl, #fff3a3);
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
}
```

#### 4.8.3 Печать справочника

CSS-блок `@media print` на странице (scoped в `StaffDirectoryPage.vue`):

```css
@media print {
  /* скрываем шапку портала, меню, фильтры, переключатель режимов, пагинацию */
  :global(.app-header),
  :global(.app-sidebar),
  .staff-filters,
  .staff-pagination,
  .staff-view-switch,
  .staff-actions {
    display: none !important;
  }

  /* всегда печатаем в табличном виде */
  .staff-grid { display: none !important; }
  .staff-table { display: table !important; width: 100%; }

  .staff-group-header {
    background: #f0f0f0 !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  a { color: inherit; text-decoration: none; }
  /* убираем колонки, которые скрываются на mobile, чтобы влезло в A4 portrait */
  /* (опционально — оставить все, если печать в landscape) */
}
```

Перед печатью на странице нужно:
- Загрузить **всю** текущую страницу данных (если активна пагинация — вывести предупреждение «Печатается только текущая страница; для полной выгрузки используйте Экспорт»). Простейший вариант: `n-message.info` при клике на «Печать» если `total > page_size`.
- Проверить что заголовки групп отделов отображаются и не разрезаются между страницами: `.staff-group-header { break-after: avoid; page-break-after: avoid; }`, `.staff-row { break-inside: avoid; page-break-inside: avoid; }`.

Селекторы `.app-header`, `.app-sidebar` уточнить из реального layout (`./frontend/src/components/AppLayout.vue` и `./frontend/src/components/layout/`).

### 4.9 Тесты фронтенда

Опционально, если в проекте настроен Vitest/Vue Test Utils:
- `StaffDirectoryPage.vue`: рендер таблицы по фейковым данным, фильтрация, дебаунс, переключение режима, навигация по клику
- `useStaffListQuery`: проверка передачи параметров

Если тестового фреймворка нет — пропустить.

---

## 5. Дополнительные поля (`internal_phone`, `office`)

Эти поля хранятся в `users.attributes` (JSONB). Для отображения в справочнике:

1. **Сидинг (выполняется один раз вручную после деплоя):**
   - Открыть админку → раздел «Атрибуты профиля»
   - Создать `internal_phone` (label_ru: «Внутренний телефон», label_en: «Extension», sort_order: 10, enabled: true)
   - Создать `office` (label_ru: «Офис», label_en: «Office», sort_order: 20, enabled: true)
2. **Источники данных:**
   - При синхронизации с Keycloak значения попадают в `users.attributes` автоматически (если в Keycloak есть атрибуты с такими же ключами)
   - Локальные пользователи: значения проставляются через `PATCH /users/admin/{user_id}/profile` (требует расширения `AdminPatchProfileRequest` полем `attributes` — **отдельная задача, в эту не входит**)
3. **Отображение в UI:**
   - В таблице: колонки «Внутренний» и «Офис» читают `user.attributes.internal_phone` и `user.attributes.office` напрямую, отображая пустую строку если значение отсутствует
   - В карточках: контакты с пустым значением скрываются
   - **Прочие** атрибуты (помимо `internal_phone` и `office`) показываются в режиме «Карточки» только если вернулись из `useUserAttributeSchemaQuery` и имеют значение у сотрудника. В режиме таблицы прочие атрибуты не показываются (фиксированный набор колонок).

---

## 6. Производительность

- `GET /users/departments` и `GET /users/offices` кэшируются на фронте `staleTime: 5 минут`. Бэкенд-кэш не нужен (запрос лёгкий, `DISTINCT` по индексируемому полю).
- Если в будущем потребуется — добавить **purpose-built индекс**:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_users_department_active
    ON users (department) WHERE deleted_at IS NULL;
  CREATE INDEX IF NOT EXISTS idx_users_attr_office
    ON users ((attributes->>'office')) WHERE deleted_at IS NULL;
  ```
  Эти индексы — отдельная миграция; в первую версию не включаем.
- Фронт: `placeholderData: keepPreviousData` исключает «прыжки» UI при смене фильтра.
- При очень больших списках (>1000) рассмотреть виртуализацию через `n-virtual-list` — **не входит в текущую задачу**.

---

## 7. Порядок реализации (для AI-агента)

```
1. Backend
   1.1  schemas/user.py      — добавить DepartmentList, OfficeList
   1.2  users_repo.py        — list_departments(), list_offices(), stream_users(), расширить _build_list_conditions
                              (q ищет также по position и attributes->>'internal_phone'; добавлен параметр office),
                              расширить list_users_page (office, sort), count_users (office)
   1.3  routes.py            — GET /users/departments, /users/offices, /users/export — все ДО /{user_id};
                              добавить query-параметры office, sort в GET /users
   1.4  (опц.) tests         — pytest на новые эндпоинты, включая /export и поиск по internal_phone

2. Frontend API + queries
   2.1  api/users.ts         — fetchUserDepartments, fetchUserOffices, buildUsersExportUrl; расширить fetchUsers
   2.2  queries/keys.ts      — users.list, users.departments, users.offices
   2.3  queries/users.ts     — useStaffListQuery, useUserDepartmentsQuery, useUserOfficesQuery
   2.4  composables/useHighlight.ts — утилита подсветки совпадений (с экранированием)

3. Роутинг и меню
   3.1  router.ts                 — ROUTES.STAFF + маршрут
   3.2  composables/useAppMenu.ts — пункт меню, activeKey, defaultTitle, routeMap, импорт иконки

4. UI
   4.1  components/StaffRow.vue        — строка таблицы (с подсветкой и кнопками копирования)
   4.2  components/StaffCard.vue       — карточка сетки (с подсветкой и кнопками копирования)
   4.3  pages/StaffDirectoryPage.vue   — страница (фильтры, режимы, группировка, пагинация,
                                         кнопки «Экспорт» и «Печать», @media print CSS)

5. Локализация
   5.1  i18n/ru.json — nav.staff, staff.* (включая export/print/copy/copied/copyFailed)
   5.2  i18n/en.json — то же

6. Сидинг (после мерджа, вручную)
   6.1  Создать атрибуты internal_phone и office в админке
```

После реализации запустить:
```bash
# backend
cd backend && uv run pytest -q   # если тесты есть
cd backend && uv run ruff check .

# frontend
cd frontend && npm run lint
cd frontend && npm run typecheck
cd frontend && npm run build
```

---

## 8. Что не меняется

- Модель БД `users` (никаких миграций по схеме)
- Существующая логика синхронизации Keycloak
- Страница `/users/:id` (`UserProfileView.vue`)
- Права доступа: страница доступна всем аутентифицированным; админских ролей не требуется
- Маршрут `/users/me`, `/users/{user_id}` и прочие подмаршруты — порядок объявления остаётся, новые `/departments` и `/offices` вставляются перед `/{user_id}`

---

## 9. Решения по открытым вопросам (зафиксированы)

| Вопрос | Решение |
|---|---|
| Какие атрибуты показывать на карточке | Фиксированный набор: `internal_phone`, `office`. Прочие enabled-атрибуты — дополнительно в режиме «Карточки» |
| `presence_status` | Не отображается в v1 (отсутствует в референсе) |
| Сортировка по умолчанию | `full_name` для grid, `department` для table (с группировкой) |
| Группировка по отделам | Включена в первую версию как стандартное поведение режима «Таблица» |
| Тесты | Backend pytest — желательно; frontend — опционально |
| Состояние фильтров | `q/department/office/page` → URL query; `view/sort` → localStorage |
| Адаптив | На `<md` принудительно режим «Карточки» |

---

## 10. Оценка трудоёмкости

| Задача | Оценка |
|---|---|
| Backend: `/departments`, `/offices`, расширение `/users` (+ схемы) | ~1.5 ч |
| Backend: `/users/export` (CSV-стрим) | ~1 ч |
| Backend: pytest | ~1 ч |
| Frontend API + query-хуки + `useHighlight` | ~1.5 ч |
| Роутер + меню + i18n | ~1 ч |
| `StaffDirectoryPage.vue` + `StaffRow`/`StaffCard` (фильтры, группировка, режимы, адаптив) | ~5–7 ч |
| Доп. функционал: копирование, подсветка, печать (`@media print`), кнопка экспорта | ~1.5 ч |
| Сидинг атрибутов (вручную) | ~10 мин |
| **Итого** | **~12–14 ч** |
