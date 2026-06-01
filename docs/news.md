# Модуль «Новости»

> **Когда читать:** лента новостей, категории, обложки WebP/AVIF, галерея, вложения, inline-медиа, версионирование, экспорт HTML/MD/PDF, корзина, опросы, таргетинг.
> **Ключевой код:** `app/api/news/`, `app/api/news_categories.py`, `app/services/news/`, `app/worker/tasks/news.py`, `frontend/src/pages/News*.vue`, `frontend/src/components/News*.vue`.
> **ADR:** —

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/news/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/News*.vue`, `./frontend/src/components/News*.vue`) |
| Воркер | ARQ (`./backend/app/worker/tasks/news.py`) |
| Хранилище медиа | Локальная ФС `/data/news_media/{news_id}/` |
| Категории | JSON-файл `/data/settings/news_categories.json` |
| Идемпотентность | `Idempotency-Key` заголовок для `POST /news` (TTL 86400 с в Redis) |
| Счётчик просмотров | Дедупликация через Redis `view:news:{id}:{user_id}` (TTL 3600 с) |

### Возможности

- Три статуса новости: `draft` / `published` / `archived`; переходы вручную и по расписанию.
- Таргетинг по подразделению (`target_departments`) и роли (`target_roles`): новость видят только совпадающие пользователи; пустые массивы = для всех.
- Закрепление (`is_pinned`), поиск по заголовку и телу (`q`, ILIKE), фильтрация по категории, статусу, закреплённости.
- Обложка с responsive-вариантами (WebP + AVIF, ширины 400/800/1200/1600 px), dominant color, focal point.
- Галерея изображений с пользовательской сортировкой.
- Произвольные вложения (любой MIME, лимит задаётся через `news_attachment_max_size_mb`).
- Inline-медиа (изображения в теле новости через Rich Editor), раздача через nginx `X-Accel-Redirect`.
- Версионирование: каждое изменение сохраняется как `NewsVersion`; история доступна редакторам.
- Экспорт в HTML, Markdown и PDF (Playwright-based screenshot-service).
- Soft-delete (корзина) + hard-delete (purge, с зачисткой ФС и закладок).
- Опросы (`NewsPoll`) — подробнее в `docs/polls.md`.
- Уведомления при публикации: in-app SSE + email-рассылка (с учётом таргетинга).

---

## 2. Модель данных

```
news
  id              uuid PK, gen_random_uuid()
  title           varchar(500)  NOT NULL
  body            text          NOT NULL  default ''
  body_tsvector   tsvector GENERATED ALWAYS AS STORED
                  to_tsvector('russian_hunspell', coalesce(title, '') || ' ' || coalesce(body, ''))
  status          varchar(20)   CHECK IN ('draft','published','archived')
  is_pinned       bool          NOT NULL  default false
  categories      text[]        NOT NULL  default '{}'
  target_departments  text[]    NULL
  target_roles    text[]        NULL
  author_id       uuid          FK users.id ON DELETE SET NULL
  publish_at      timestamptz   NULL   -- отложенная публикация
  archive_at      timestamptz   NULL   -- отложенная архивация
  published_at    timestamptz   NULL
  cover_image     varchar(500)  NULL   -- относительный путь от /data/news_media/
  cover_focal_point varchar(16) NULL   -- 'top'|'center'|'bottom'
  cover_dominant_color varchar(7) NULL -- hex dominant color (#rrggbb)
  cover_variants  int[]         NULL   -- ширины сгенерированных webp/avif вариантов
  view_count      int           NOT NULL default 0
  current_version int           NOT NULL default 1
  deleted_at      timestamptz   NULL   -- soft-delete
  previous_status varchar(20)   NULL   -- восстанавливается при restore
  created_at      timestamptz   NOT NULL
  updated_at      timestamptz   NOT NULL

  INDEX idx_news_status_published_at (status, publish_at)
  INDEX idx_news_author (author_id)
  INDEX idx_news_fts (body_tsvector) USING gin
  INDEX idx_news_active (status, publish_at) WHERE deleted_at IS NULL

news_versions
  id          uuid PK
  news_id     uuid FK news.id ON DELETE CASCADE
  version     int  NOT NULL
  title       varchar(500)
  body        text
  editor_id   uuid FK users.id ON DELETE SET NULL
  created_at  timestamptz

  INDEX idx_news_versions_news_id (news_id)

news_gallery_images
  id            uuid PK
  news_id       uuid FK news.id ON DELETE CASCADE
  filename      varchar(500)  -- {uuid}.{ext}
  original_name varchar(500)
  sort_order    int  NOT NULL default 0
  file_size     int  NULL
  created_at    timestamptz

  INDEX idx_gallery_news_id_sort (news_id, sort_order)

news_attachments
  id            uuid PK
  news_id       uuid FK news.id ON DELETE CASCADE
  filename      varchar(500)  -- {uuid} (без расширения)
  original_name varchar(500)
  mime_type     varchar(255)  NULL
  file_size     int           NULL
  created_at    timestamptz

  INDEX idx_attachments_news_id (news_id)

-- Poll-таблицы (news_polls, news_poll_questions, news_poll_options,
--               news_poll_voters, news_poll_votes) — см. docs/polls.md
```

### Soft-delete

- `news.deleted_at IS NOT NULL` — новость в корзине.
- При удалении текущий `status` сохраняется в `previous_status`, сам `status` выставляется в `archived`.
- Restore восстанавливает `previous_status` и обнуляет `deleted_at`.
- Purge: физически удаляет строку, всю директорию `/data/news_media/{news_id}/`, а также закладки (`bookmarks WHERE resource_type='news'`). Доступен только для уже soft-deleted новостей (admin).

---

## 3. REST API

База: `/api/v1`. Все endpoints требуют авторизованного пользователя.

### Основные операции (`routes.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news` | Список новостей (пагинация, фильтры по status/category/is_pinned/q) | CurrentUser |
| GET | `/api/v1/news/limits` | Лимит загрузки файлов (`news_attachment_max_size_mb`) | CurrentUser |
| GET | `/api/v1/news/trash` | Корзина: список soft-deleted новостей с автором | AdminDep |
| GET | `/api/v1/news/{news_id}` | Получить новость; инкремент просмотров (дедупл. 1 ч) | CurrentUser |
| POST | `/api/v1/news` | Создать новость; поддерживает `Idempotency-Key` | EditorDep |
| PUT | `/api/v1/news/{news_id}` | Обновить новость | EditorDep |
| PUT | `/api/v1/news/{news_id}/draft` | Автосохранение черновика (только `status='draft'`) | EditorDep |
| DELETE | `/api/v1/news/{news_id}` | Soft-delete (перемещение в корзину) | EditorDep |
| POST | `/api/v1/news/{news_id}/restore` | Восстановить из корзины | AdminDep |
| DELETE | `/api/v1/news/{news_id}/purge` | Hard-delete (только для soft-deleted) | AdminDep |
| GET | `/api/v1/news/{news_id}/versions` | История версий | EditorDep |

**Query-параметры `GET /news`:** `page`, `page_size` (alias `limit`), `offset`, `status` (`draft`/`published`/`archived`), `category`, `is_pinned`, `q` (поиск по заголовку и телу через ILIKE, max 200 символов).

### Медиа (`media.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| POST | `/api/v1/news/{news_id}/cover` | Загрузить обложку (JPEG/PNG/WebP/GIF) | EditorDep |
| DELETE | `/api/v1/news/{news_id}/cover` | Удалить обложку | EditorDep |
| GET | `/api/v1/news/{news_id}/gallery` | Список изображений галереи | CurrentUser |
| POST | `/api/v1/news/{news_id}/gallery` | Загрузить фото в галерею | EditorDep |
| PATCH | `/api/v1/news/{news_id}/gallery/reorder` | Изменить порядок галереи | EditorDep |
| DELETE | `/api/v1/news/{news_id}/gallery/{img_id}` | Удалить фото из галереи | EditorDep |
| GET | `/api/v1/news/{news_id}/attachments` | Список вложений | CurrentUser |
| POST | `/api/v1/news/{news_id}/attachments` | Загрузить вложение (любой MIME) | EditorDep |
| GET | `/api/v1/news/{news_id}/attachments/{att_id}/download` | Скачать вложение | CurrentUser |
| DELETE | `/api/v1/news/{news_id}/attachments/{att_id}` | Удалить вложение | EditorDep |
| POST | `/api/v1/news/{news_id}/inline-media` | Загрузить inline-изображение (JPEG/PNG/GIF/WebP) | EditorDep |
| GET | `/api/v1/news/{news_id}/inline-media/{filename}` | Раздача inline-изображения (`X-Accel-Redirect`) | CurrentUser |

### Экспорт (`export.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news/{news_id}/export/html` | Экспорт в HTML с инлайн-изображениями | CurrentUser |
| GET | `/api/v1/news/{news_id}/export/markdown` | Экспорт в Markdown | CurrentUser |
| GET | `/api/v1/news/{news_id}/export/pdf` | Экспорт в PDF (Playwright) | CurrentUser |

### Опросы (`poll.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news/{news_id}/poll` | Получить опрос с результатами | CurrentUser |
| POST | `/api/v1/news/{news_id}/poll` | Создать опрос | EditorDep |
| PATCH | `/api/v1/news/{news_id}/poll` | Обновить опрос | EditorDep |
| DELETE | `/api/v1/news/{news_id}/poll` | Удалить опрос | EditorDep |
| POST | `/api/v1/news/{news_id}/poll/close` | Закрыть опрос вручную | EditorDep |
| POST | `/api/v1/news/{news_id}/poll/reopen` | Переоткрыть опрос | EditorDep |
| POST | `/api/v1/news/{news_id}/poll/vote` | Проголосовать | CurrentUser |
| DELETE | `/api/v1/news/{news_id}/poll/vote` | Отозвать голос (`allow_revote=true`) | CurrentUser |
| GET | `/api/v1/news/{news_id}/poll/voters` | Список проголосовавших; для анонимных опросов — только editor/admin | CurrentUser |

### Категории (`news_categories.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news-categories` | Список категорий с числом новостей | CurrentUser |
| POST | `/api/v1/news-categories` | Добавить категорию | EditorDep |
| PATCH | `/api/v1/news-categories/{name}/color` | Обновить цвет категории | EditorDep |
| PATCH | `/api/v1/news-categories/{name}` | Переименовать (обновляет и все новости) | EditorDep |
| DELETE | `/api/v1/news-categories/{name}` | Удалить (удаляет из всех новостей через `array_remove`) | EditorDep |

---

## 4. Права и роли

| Роль | Что может |
|---|---|
| `user` (любой авторизованный) | Читать `published` новости (с учётом таргетинга), смотреть галерею и вложения, просматривать и скачивать медиа, голосовать в опросах, экспортировать. |
| `editor` | Всё выше + читать `draft`/`archived`, создавать/редактировать/удалять новости, управлять медиа, вложениями, категориями, опросами. |
| `admin` | Всё выше + корзина (`GET /trash`), восстановление (`restore`), hard-delete (`purge`). |

**Таргетинг (только для `user`):** новость показывается, если `target_departments` пуст или содержит отдел пользователя **И** `target_roles` пуст или содержит роль пользователя. Редакторы и администраторы таргетинг игнорируют.

**Idempotency-Key:** при `POST /news` заголовок `Idempotency-Key: <value>` кэширует ответ в Redis под ключом `idem:news:{editor_id}:{key}` на 24 ч; повторный запрос возвращает тот же `NewsPublic` без создания дубля.

**Доступ к черновикам/архивным:** `require_news_read_access` пропускает только `editor`/`admin`; остальные получают 403.

---

## 5. Frontend

### Страницы

| Файл | Назначение |
|---|---|
| `./frontend/src/pages/NewsListPage.vue` | Лента новостей: фильтры (chip-ы по статусу, категориям, закреплённым), поиск, корзина (для editor). |
| `./frontend/src/pages/NewsDetailPage.vue` | Просмотр новости: тело (Rich Content), галерея, вложения, опрос, кнопки экспорта. |
| `./frontend/src/pages/NewsFormPage.vue` | Создание и редактирование: Rich Editor с inline-upload, боковая панель (обложка, настройки, таргетинг, статус, даты), галерея, вложения, опрос. |

### Компоненты

| Файл | Назначение |
|---|---|
| `./frontend/src/components/NewsCard.vue` | Карточка новости в ленте (обложка с srcset, категории, статус, счётчик просмотров). |
| `./frontend/src/components/NewsCoverUpload.vue` | Загрузка/смена/удаление обложки с предпросмотром и выбором focal point. |
| `./frontend/src/components/NewsGalleryPanel.vue` | Редактирование галереи (загрузка, сортировка drag-and-drop, удаление). |
| `./frontend/src/components/NewsGalleryViewer.vue` | Просмотр галереи (lightbox). |
| `./frontend/src/components/NewsAttachmentsPanel.vue` | Управление вложениями (загрузка, удаление). |
| `./frontend/src/components/NewsAttachmentsViewer.vue` | Просмотр/скачивание вложений. |
| `./frontend/src/components/news/poll/NewsPoll.vue` | Отображение и голосование в опросе. |
| `./frontend/src/components/news/poll-panel/NewsPollPanel.vue` | Панель управления опросом в форме редактирования. |

### Data layer

| Файл | Назначение |
|---|---|
| `./frontend/src/api/news.ts` | Тонкий REST-клиент (fetch-обёртки для всех endpoints). |
| `./frontend/src/queries/news.ts` | TanStack Query хуки: `useNewsListQuery`, `useNewsDetailQuery`, `useNewsGalleryQuery`, `useNewsAttachmentsQuery`, `useNewsCategoriesQuery`, `useNewsPollQuery`, мутации CRUD, галереи, вложений, опросов. |

---

## 6. Особенности и нюансы

### Обложка и responsive-варианты

При загрузке обложки синхронно (в `asyncio.to_thread`) генерируются WebP + AVIF варианты шириной 400/800/1200/1600 px (только те, что ≤ оригиналу), качество 82. Если Pillow недоступен — original используется как fallback. Dominant color вычисляется путём resize до 1×1 px. Ответ `NewsPublic` содержит `cover_webp_srcset` и `cover_avif_srcset` для `<picture>`. Файлы: `/data/news_media/{news_id}/cover.{ext}`, `/data/news_media/{news_id}/cover-{w}.webp`, `/data/news_media/{news_id}/cover-{w}.avif`.

### Галерея

Изображения хранятся в `/data/news_media/{news_id}/gallery/{uuid}.{ext}`. Сортировка по `sort_order` (auto-increment при добавлении). URL формируется на клиенте: `/media/news/{news_id}/gallery/{filename}` (nginx static). Допустимые MIME: `image/jpeg`, `image/png`, `image/webp`, `image/gif`.

### Вложения

Хранятся в `/data/news_media/{news_id}/attachments/{uuid}` (без расширения). Скачивание через `/api/v1/news/{news_id}/attachments/{att_id}/download` — FastAPI `FileResponse` с `original_name` в заголовке. Лимит размера: `news_attachment_max_size_mb` (по умолчанию 50 МБ, конфигурируется в system settings).

### Inline-медиа

Загружаются в `/data/news_media/{news_id}/inline/{8hex}_{safe_name}`. Раздаются через `X-Accel-Redirect: /internal/news-media/{news_id}/inline/{filename}` (nginx internal). Имя файла проверяется regex `[A-Za-z0-9][A-Za-z0-9._\-]{0,254}`. Лимит размера: `kb_media_max_size_mb`.

### Версионирование

Каждый `create_news` и каждый `update_news` с изменёнными полями создаёт запись `NewsVersion` (`news_id`, `version`, `title`, `body`, `editor_id`). `news.current_version` инкрементируется при каждом изменении. Автосохранение черновика (`PUT /{id}/draft`) также создаёт версию. История версий доступна через `GET /{id}/versions` (только editor+).

### Экспорт

- **HTML / Markdown**: формируются синхронно; изображения (обложка, галерея, inline) читаются с диска и кодируются в base64 data URI (лимит 10 МБ на изображение). Для PDF используется сжатие через PIL (`max_dim=1200`, `quality=72`).
- **PDF**: вызывает `app.core.pdf.render_pdf(html)` — Playwright-based renderer. При сбое возвращает `503 Service Unavailable`.
- Заголовок `Content-Disposition` содержит `filename=` в ASCII-fallback и `filename*=UTF-8''…` для полного имени.

### Корзина / soft-delete

- `DELETE /news/{id}` — soft-delete: `deleted_at = NOW()`, `status = 'archived'`, `previous_status` сохранён.
- `GET /news/trash` — только admin; возвращает `NewsWithAuthor` (включает данные автора и `previous_status`).
- `POST /news/{id}/restore` — только admin; восстанавливает `previous_status`, сбрасывает `deleted_at`.
- `DELETE /news/{id}/purge` — только admin, только для уже soft-deleted; удаляет строку БД, директорию ФС, закладки.

### Категории

- Хранятся в JSON-файле `/data/settings/news_categories.json` как `[{name, color}]`.
- Поддерживается legacy-формат (плоский список строк), читается для обратной совместимости.
- Максимум 100 категорий. Цвет по умолчанию: `#6B7AE8`.
- `ensure_category_exists(name)` вызывается при создании/обновлении новости — автоматически добавляет новую категорию если её нет.
- При переименовании/удалении категории выполняется `array_replace`/`array_remove` по всем новостям в БД.
- Счётчик `news_count` вычисляется через `unnest(categories)` по активным (не удалённым) новостям.

### Воркер (ARQ cron-задачи)

| Задача | Расписание | Действие |
|---|---|---|
| `publish_scheduled_news` | каждую минуту (second=0) | `UPDATE news SET status='published' WHERE status='draft' AND publish_at <= NOW()`; ставит в очередь `notify_news_published`. |
| `archive_expired_news` | каждый час (minute=0, second=30) | `UPDATE news SET status='archived' WHERE status='published' AND archive_at <= NOW()`. |
| `close_expired_polls` | каждую минуту (second=15) | `UPDATE news_polls SET closed_at=NOW() WHERE closes_at <= NOW() AND closed_at IS NULL`. |

### Уведомления о публикации

При авто-публикации (`publish_scheduled_news`) ставится ARQ-задача `notify_news_published`, которая:
1. Фильтрует пользователей по `target_departments` / `target_roles`.
2. Записывает email-уведомления в `email_outbox` (KIND_NEWS) для пользователей с `notify_email=true`.
3. Вызывает `notify_users_news_published` — in-app SSE через общий Redis-стрим уведомлений.
