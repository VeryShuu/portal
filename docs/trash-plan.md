# ТЗ: Корзина и полное удаление контента

## Цели

1. Дать администратору возможность **физически (hard) удалить** новости — со всеми связанными данными и файлами на диске. Удаление выполняется **только вручную**, без шедулера.
2. Добавить отдельный раздел **«Корзина»** в главном меню рядом с пунктом «Администрирование» (видно только администратору). Раздел собирает весь soft-удалённый контент. На первом этапе — только новости, с заделом под расширение (KB, фото и т.д.).
3. Привести восстановление к корректному поведению: запись возвращается **в том же состоянии**, в каком была до удаления (включая статус).

## Ограничения и решения

- **Hard-delete** разрешён только для записей, у которых уже выставлен `deleted_at` (двухступенчатость: сначала «Удалить» → запись попадает в Корзину, затем «Удалить навсегда»).
- Для подтверждения опасных действий используется обычный `n-popconfirm` (без ввода заголовка).
- Доступ ко всем операциям Корзины и к `purge` — только роль `admin`.
- При hard-delete **закладки** (`bookmarks`) на удаляемую новость зачищаются явным `DELETE`, т.к. FK на `news.id` там нет.
- Аудит-события (`audit_events`) не удаляются — это лог.
- Уведомления об удаляемой новости очищать не требуется (если в `notifications` есть `news_id` без FK — оставляем как есть; при необходимости дочистим в follow-up).

---

## Принятые технические решения

### 1. Порядок роутов в `./backend/app/api/news.py`

`GET /news/trash` регистрируется **до** `GET /news/{news_id}`. FastAPI матчит роуты по порядку регистрации: если `/{news_id}` окажется раньше, строка `"trash"` будет распознана как `uuid.UUID` → 422 Unprocessable Entity. Прецедент уже есть: `GET /news/limits` (строка 96) стоит перед `GET /news/{news_id}` (строка 102) по той же причине.

### 2. Схема ответа для `GET /news/trash` — `TrashNewsList` с `NewsWithAuthor`

Стандартная `NewsList` использует `NewsPublic`, в котором есть только `author_id: uuid.UUID | None` — имя автора недоступно. Для колонки «Автор» в таблице Корзины это неприемлемо (показывался бы UUID).

Решение — заводим **`TrashNewsList`** (`items: list[NewsWithAuthor]`) и возвращаем его из `GET /news/trash`. `NewsWithAuthor` уже расширяет `NewsPublic` полем `author: NewsAuthor | None` (с `full_name`). Это обоснованное отступление от ТЗ («тот же, что у обычного листинга»).

### 3. Типы для `./frontend/src/api/news.ts` пишутся вручную

`news.ts` не импортирует `types.gen.d.ts` (в отличие от `kb.ts` и `photos.ts`). Новые интерфейсы `NewsTrashItem` и `TrashNewsList` добавляются в `news.ts` вручную. Регенерация `types.gen.d.ts` через `npm run gen:types` для задач этого ТЗ **не требуется** и выполняется отдельно после деплоя бэка (скрипт требует запущенного сервера).

---

## Backend

### 1. Модель и миграция

`./backend/app/models/news.py`:

- Добавить колонку:
  ```python
  previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
  ```
  Используется для запоминания статуса (`draft` / `published` / `archived`) на момент soft-delete, чтобы корректно восстановить.

Новая миграция alembic `./backend/migrations/versions/043_news_previous_status.py`:

- `op.add_column('news', sa.Column('previous_status', sa.String(20), nullable=True))`
- `downgrade`: `op.drop_column('news', 'previous_status')`

### 2. Сервис `./backend/app/services/news.py`

- **`delete_news(db, news)`** — изменить:
  ```python
  news.previous_status = news.status
  news.deleted_at = datetime.now(UTC)
  news.status = "archived"
  await db.commit()
  ```

- **`get_news_by_id(db, news_id, *, include_deleted=False)`** — добавить флаг. При `include_deleted=True` снять условие `deleted_at IS NULL` (нужно для restore/purge).

- **`get_trash_news(db, *, page, page_size) -> tuple[list[News], int]`** — выборка `News.deleted_at.is_not(None)`, сортировка по `deleted_at DESC`. Без таргетинга и без ограничений по статусу.

- **`restore_news(db, news) -> News`** (вынести логику из API):
  - `news.deleted_at = None`
  - если `news.previous_status` задан — вернуть `news.status = news.previous_status`, обнулить `previous_status`. Если по какой-то причине пусто (старые записи) — оставить текущий `status`.
  - commit + refresh.

- **`purge_news(db, news) -> None`**:
  1. Удалить каталог медиа: `shutil.rmtree(_NEWS_MEDIA_DIR / str(news.id), ignore_errors=True)`.
  2. Зачистить закладки:
     ```python
     await db.execute(
         text("DELETE FROM bookmarks WHERE resource_type='news' AND resource_id = :rid"),
         {"rid": news.id},
     )
     ```
  3. `await db.delete(news)` — каскад уберёт `news_versions`, `news_gallery_images`, `news_attachments`.
  4. `await db.commit()`.
  5. Логировать `news.purged` через structlog.

### 3. API `./backend/app/api/news.py`

- **Изменить `restore_news`**:
  - Вместо ручной выборки и присваивания `deleted_at = None` — вызвать `news_svc.get_news_by_id(db, news_id, include_deleted=True)` и `news_svc.restore_news(db, news)`.
  - Сохранить аудит-событие `news.restored`.

- **Новый эндпоинт** (разместить до `GET /{news_id}`):
  ```
  GET /api/v1/news/trash
  ```
  - Только `admin` (через `AdminDep`).
  - Параметры: `page: int = 1`, `page_size: int = 20`.
  - Ответ: `TrashNewsList` (`items: list[NewsWithAuthor]`, `total: int`) — см. «Принятые технические решения» п. 2.

- **Новый эндпоинт**:
  ```
  DELETE /api/v1/news/{news_id}/purge
  ```
  - Только `admin`. Статус `204 No Content`.
  - Логика:
    - получить запись с `include_deleted=True`;
    - если `news is None` → `404`;
    - если `news.deleted_at is None` → `400 "News is not deleted"` (purge только для soft-удалённых);
    - вызвать `news_svc.purge_news(db, news)`;
    - аудит-событие `news.purged` с `resource_title=news.title`.

### 4. Схемы `./backend/app/schemas/news.py`

- Добавить в `NewsPublic`: `deleted_at: datetime | None` и `previous_status: str | None`.
- Добавить класс:
  ```python
  class TrashNewsList(BaseModel):
      items: list[NewsWithAuthor]
      total: int
  ```

---

## Frontend

### 1. Роутинг и меню

`./frontend/src/router.ts`:

- Добавить константу `TRASH: '/trash'` в `ROUTES`.
- Зарегистрировать роут (внутри `AppLayout` children):
  ```ts
  {
    path: ROUTES.TRASH,
    name: 'trash',
    component: () => import('./pages/TrashPage.vue'),
    meta: { requiresAdmin: true },
  }
  ```

`./frontend/src/composables/useAppMenu.ts`:

- В `activeKey`: `if (path.startsWith(ROUTES.TRASH)) return 'trash'`.
- В `defaultTitle.map`: `trash: t('nav.trash')`.
- В группе `g-account`, **после** пункта `admin` (только при `auth.isAdmin`), добавить:
  ```ts
  { label: renderNavLabel(t('nav.trash'), 'trash'), key: 'trash', icon: renderIcon(TrashBinOutline) }
  ```
  Иконка `TrashBinOutline` из `@vicons/ionicons5`.
- В `routeMap`: `trash: ROUTES.TRASH`.

### 2. Страница `./frontend/src/pages/TrashPage.vue`

- Контейнер с табами `n-tabs`. Первый таб — **«Новости»**, рендерит `<TrashNewsTab />`.
- Структура задумана как расширяемая: новые типы контента (KB-статьи, фото) добавляются как отдельные табы.
- Заголовок страницы — через `useLayoutHeader`.

### 3. Компонент `./frontend/src/components/trash/TrashNewsTab.vue`

- Таблица `n-data-table`, столбцы:
  - **Заголовок** (без ссылки на старте — просто текст).
  - **Автор** (`item.author?.full_name` — доступно благодаря `NewsWithAuthor` в ответе).
  - **Статус до удаления** (`previous_status`).
  - **Удалено** (`deleted_at`, форматирование через i18n).
  - **Действия**: две кнопки.
    - «Восстановить» (`RefreshOutline`) → `n-popconfirm` → `restoreNews(id)` → перезагрузить список.
    - «Удалить навсегда» (`TrashBinOutline`, `type="error"`) → `n-popconfirm` → `purgeNews(id)` → перезагрузить список.
- Пагинация (page/page_size, как в обычном `NewsListPage`).
- Пустое состояние через `<EmptyState />`.

### 4. API клиент `./frontend/src/api/news.ts`

Добавить интерфейсы и функции (типы пишутся вручную — см. «Принятые технические решения» п. 3):

```ts
export interface NewsAuthorPublic {
  id: string
  full_name: string
  department: string | null
  avatar_url: string | null
}

export interface NewsTrashItem extends News {
  deleted_at: string
  previous_status: string | null
  author: NewsAuthorPublic | null
}

export interface TrashNewsList {
  items: NewsTrashItem[]
  total: number
}

export async function listTrashNews(params?: { page?: number; page_size?: number }): Promise<TrashNewsList>
export async function restoreNews(id: string): Promise<News>
export async function purgeNews(id: string): Promise<void>
```

Регенерация `./frontend/src/api/types.gen.d.ts` через `npm run gen:types` **не требуется** в рамках этой задачи.

### 5. Локализация

`./frontend/src/i18n/ru.json` и `./frontend/src/i18n/en.json`:

- `nav.trash`: «Корзина» / «Trash».
- `trash.title`, `trash.empty`, `trash.tabs.news`.
- `trash.news.columns.title`, `trash.news.columns.author`, `trash.news.columns.previousStatus`, `trash.news.columns.deletedAt`, `trash.news.columns.actions`.
- `trash.actions.restore`, `trash.actions.purge`.
- `trash.confirm.restore`, `trash.confirm.purge` (текст для `n-popconfirm`).
- `trash.toast.restored`, `trash.toast.purged`, `trash.toast.error`.

### 6. Кнопки в существующих местах

- `./frontend/src/pages/NewsDetailPage.vue` и `NewsListPage.vue` — **не трогаем**: «Удалить» там остаётся soft-удалением, восстановление и hard-delete живут только в Корзине.

---

## Аудит и безопасность

- Все три операции (`delete`, `restore`, `purge`) пишут в audit:
  - `news.deleted` (уже есть);
  - `news.restored` (уже есть);
  - `news.purged` (новое) — с `resource_id`, `resource_title`, `user_id`, `user_email`, `ip_address`.
- `purge` и `restore`, и листинг `/trash` — только `admin` (через `AdminDep` на бэке + `meta.requiresAdmin` на фронте + `auth.isAdmin` в меню).
- На фронте кнопка «Удалить навсегда» оформлена как `type="error"` + `n-popconfirm` с явным текстом «Это действие необратимо».

---

## Тестирование

### Backend (pytest)

- `delete_news` сохраняет `previous_status` и проставляет `deleted_at`, `status='archived'`.
- `restore_news` возвращает `status` из `previous_status` и сбрасывает `previous_status`/`deleted_at`. Для записи без `previous_status` — статус не меняется.
- `purge_news`:
  - удаляет файлы (создать тестовую структуру каталогов и проверить отсутствие после вызова);
  - удаляет строку `news`;
  - удаляет строки `news_versions`, `news_gallery_images`, `news_attachments` (cascade);
  - удаляет связанные `bookmarks` (`resource_type='news'`).
- API:
  - `DELETE /news/{id}/purge` без soft-delete → 400.
  - `DELETE /news/{id}/purge` под не-админом → 403.
  - `GET /news/trash` под не-админом → 403; под админом — возвращает только soft-удалённые.

### Frontend

- Smoke: меню «Корзина» видно только под админом; страница открывается; пустое состояние показывается; восстановление/удаление обновляют список.

---

## План работ (порядок коммитов)

1. **Migration + model**: `previous_status` в `news`, миграция 043.
2. **Service layer**: обновить `delete_news`, добавить `restore_news`, `purge_news`, `get_trash_news`, флаг `include_deleted` в `get_news_by_id`.
3. **Schemas**: добавить `deleted_at`, `previous_status` в `NewsPublic`; добавить `TrashNewsList`.
4. **API**: новый `GET /news/trash` (до `/{news_id}`), новый `DELETE /news/{id}/purge`, рефакторинг `restore_news` под сервис.
5. **Frontend**: роут `/trash`, пункт меню «Корзина», страница `TrashPage` + компонент `TrashNewsTab`, методы API + интерфейсы, локализация.
6. **Тесты** (бэк) + ручной smoke (фронт).

---

## Расширение (вне scope первой итерации)

- Аналогичный таб для **KB-статей** (`./backend/app/models/kb.py`: `articles`, `sections` уже soft-deletable).
- Таб для **фото** (`Photo.deleted_at`) — с учётом существующего шедулера `cleanup_deleted_photos` (его, возможно, отключить или согласовать поведение «вручную»).
- Массовые операции в Корзине (выделение нескольких → восстановить/удалить навсегда).
- Регенерация `./frontend/src/api/types.gen.d.ts` через `npm run gen:types` после деплоя бэка (если `news.ts` перейдёт на автогенерируемые типы).
