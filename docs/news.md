# Модуль «Новости»

> **Когда читать:** лента новостей, категории, обложки WebP/AVIF, галерея, вложения, inline-медиа, версионирование, экспорт HTML/MD/PDF, корзина, опросы, таргетинг, лайки (♥), комментарии, рассылка новости по email из справочника получателей.
> **Ключевой код:** `./backend/app/api/news/`, `./backend/app/api/news_categories.py`, `./backend/app/api/mailing_recipients.py`, `./backend/app/services/news/`, `./backend/app/services/news/email_share.py`, `./backend/app/services/mailing_recipients.py`, `./backend/app/worker/tasks/news.py`, `./backend/app/models/news.py`, `./backend/app/models/mailing_recipient.py`, `./frontend/src/pages/NewsListPage.vue`, `./frontend/src/pages/NewsDetailPage.vue`, `./frontend/src/pages/NewsFormPage.vue`, `./frontend/src/components/news/NewsCard.vue`, `./frontend/src/components/news/NewsLikeButton.vue`, `./frontend/src/components/news/NewsComments.vue`, `./frontend/src/components/news/NewsShareEmailModal.vue`, `./frontend/src/components/admin/MailingRecipientsSettings.vue`.
> **ADR:** —. **См. также:** `./docs/polls.md`, `./docs/notifications.md`, `./docs/audit.md`.

> Модуль «Новости» обеспечивает полный жизненный цикл корпоративных новостей на интранет-портале, включая черновики, отложенную публикацию, таргетирование на отделы и роли, вложения файлов, галереи изображений и опросы. Он предоставляет инструменты версионирования содержимого, экспорта в различные форматы и информирования пользователей.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/news/`, `./backend/app/api/news_categories.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/NewsListPage.vue`, `./frontend/src/pages/NewsDetailPage.vue`, `./frontend/src/pages/NewsFormPage.vue`, `./frontend/src/components/`) |
| Воркер | ARQ (`./backend/app/worker/tasks/news.py`, `./backend/app/worker/tasks/notifications.py`) |
| Хранилище | Локальная ФС `/data/news_media/{news_id}/`, `/data/settings/news_categories.json` |
| Префикс API | `/api/v1/news`, `/api/v1/news-categories` |
| ACL-кэш | Redis (дедупликация просмотров, идемпотентность создания) |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/news/` | Маршруты для новостей, медиа, опросов, экспорта, реакций (`./backend/app/api/news/reactions.py`) и комментариев (`./backend/app/api/news/comments.py`, `./backend/app/api/news/comments_repo.py`) |
| Router | `./backend/app/api/news_categories.py` | Эндпоинты для управления категориями новостей |
| Router | `./backend/app/api/mailing_recipients.py` | CRUD справочника получателей рассылки (`editor+` на чтение и мутации) |
| Service | `./backend/app/services/news/` | Сервисы бизнес-логики: CRUD (`./backend/app/services/news/crud.py`), обложки (`./backend/app/services/news/cover.py`), галерея (`./backend/app/services/news/gallery.py`), вложения (`./backend/app/services/news/attachments.py`), опросы (`./backend/app/services/news/poll/`), лайки (`./backend/app/services/news/likes.py`), рассылка по email (`./backend/app/services/news/email_share.py`) |
| Service | `./backend/app/services/mailing_recipients.py` | CRUD справочника + резолв `recipient_ids → email` для рассылки |
| Model | `./backend/app/models/news.py` | Описание SQLAlchemy моделей новостей, версий, вложений, изображений галереи, опросов, лайков (`NewsLike`) и комментариев (`NewsComment`) |
| Model | `./backend/app/models/mailing_recipient.py` | Модель `MailingRecipient` — получатель рассылки (миграция 071) |
| Schema | `./backend/app/schemas/news.py`, `./backend/app/schemas/news_poll.py`, `./backend/app/schemas/mailing_recipient.py` | Схемы валидации Pydantic |
| Frontend Share | `./frontend/src/components/news/NewsShareEmailModal.vue`, `./frontend/src/components/admin/MailingRecipientsSettings.vue` | Модалка рассылки (мульти-select из справочника + краткий текст) и управление справочником получателей (drawer на странице новостей) |
| Frontend Pages | `./frontend/src/pages/NewsListPage.vue`, `./frontend/src/pages/NewsDetailPage.vue`, `./frontend/src/pages/NewsFormPage.vue` | Страницы новостной ленты, чтения новости и формы редактирования |
| Frontend Components | `./frontend/src/components/news/` | Все компоненты модуля живут в `components/news/`: обложка (`NewsCoverUpload.vue`), галерея (`NewsGalleryPanel.vue`, `NewsGalleryViewer.vue`), вложения (`NewsAttachmentsPanel.vue`, `NewsAttachmentsViewer.vue`), карточка (`NewsCard.vue`), лайк (`NewsLikeButton.vue`), комментарии (`NewsComments.vue`, `NewsCommentItem.vue`), опросы (`poll/`, `poll-panel/`) |
| Frontend Form | `./frontend/src/components/news/NewsFormMainFields.vue`, `./frontend/src/components/news/NewsFormSettingsCard.vue` | Декомпозиция формы `NewsFormPage.vue`: главные поля (заголовок + RichEditor) и сайдбар-карточка настроек (обложка, статус, категории, закрепление, расписание публикации/архивации) |
| Frontend Composables | `./frontend/src/pages/composables/useNewsFormState.ts`, `useNewsFormOptions.ts`, `newsFormMappers.ts` | Состояние формы (модель, загрузка, autosave черновика, валидация, save/publish), опции (категории/статусы/лимиты), чистые мапперы (`isBodyEmpty`, ISO↔ms) |
| Frontend API | `./frontend/src/api/news.ts`, `./frontend/src/queries/news.ts` | Слой запросов к API и интеграция с TanStack Query |

---

## 3. Модель данных

Модели объявлены в файле `./backend/app/models/news.py`.

```
news
  id              uuid PK, gen_random_uuid()
  title           varchar(500)  NOT NULL
  body            text          NOT NULL  default ''
  body_tsvector   tsvector GENERATED ALWAYS AS STORED
                  to_tsvector('russian_hunspell', coalesce(title, '') || ' ' || coalesce(body, ''))
  status          varchar(20)   CHECK IN ('draft','published','archived')
  is_pinned       bool          NOT NULL  default false
  categories      varchar(100)[] NOT NULL default '{}'
  target_departments  varchar[]    NULL
  target_roles    varchar[]    NULL
  author_id       uuid          FK users.id ON DELETE SET NULL
  publish_at      timestamptz   NULL   -- отложенная публикация
  archive_at      timestamptz   NULL   -- отложенная архивация
  published_at    timestamptz   NULL
  cover_image     varchar(500)  NULL   -- относительный путь от /data/news_media/
  cover_focal_x   smallint      NULL   -- 0..100 (% по горизонтали; NULL = 50, центр)
  cover_focal_y   smallint      NULL   -- 0..100 (% по вертикали; NULL = 50, центр)
  cover_dominant_color varchar(7) NULL -- hex dominant color (#rrggbb)
  cover_variants  int[]         NULL   -- ширины сгенерированных webp/avif вариантов
  view_count      int           NOT NULL default 0
  like_count      int           NOT NULL default 0   -- ♥ денормализация (news_likes, миграция 068)
  comment_count   int           NOT NULL default 0   -- 💬 денормализация (news_comments, миграция 069)
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

news_likes  (миграция 068)
  id          uuid PK, gen_random_uuid()
  news_id     uuid FK news.id  ON DELETE CASCADE
  user_id     uuid FK users.id ON DELETE CASCADE
  created_at  timestamptz NOT NULL default NOW()

  UNIQUE (news_id, user_id)              -- один пользователь = один лайк
  INDEX idx_news_likes_user (user_id)

news_comments  (миграция 069)
  id          uuid PK, gen_random_uuid()
  news_id     uuid FK news.id  ON DELETE CASCADE
  author_id   uuid FK users.id ON DELETE SET NULL   -- NULL после hard-delete пользователя
  body        text NOT NULL
  deleted_at  timestamptz NULL                       -- soft-delete
  created_at  timestamptz NOT NULL default NOW()
  updated_at  timestamptz NOT NULL default NOW()

  INDEX idx_news_comments_news   (news_id, created_at)
  INDEX idx_news_comments_active (news_id) WHERE deleted_at IS NULL

-- Таблицы опросов (news_polls, news_poll_questions, news_poll_options, news_poll_voters, news_poll_votes) — см. подробнее в ./docs/polls.md
```

### Soft-delete (корзина)

- При перемещении новости в корзину через `DELETE /api/v1/news/{id}` устанавливается `deleted_at = NOW()`, а текущий `status` сохраняется в `previous_status`, сам `status` выставляется в `'archived'`.
- Восстановление (`POST /api/v1/news/{id}/restore`) возвращает новость из корзины: обнуляет `deleted_at`, восстанавливает статус из `previous_status`.
- Окончательное удаление (`DELETE /api/v1/news/{id}/purge`) физически удаляет запись из базы данных, зачищает соответствующую директорию на диске `/data/news_media/{news_id}/`, а также удаляет закладки пользователей (`bookmarks WHERE resource_type='news'`). Операция доступна только администраторам (`AdminDep`) для новостей, уже находящихся в корзине.

---

## 4. Модель прав (ACL)

Доступ к новостям разграничивается на основе роли пользователя:

| Роль | Права |
|---|---|
| `user` (любой авторизованный) | Чтение опубликованных новостей (с учётом таргетинга), просмотр вложений и галерей, скачивание вложений, участие в опросах, экспорт, лайк/снятие лайка, добавление комментариев, редактирование/удаление своих комментариев. |
| `editor` | Всё выше + создание, изменение, мягкое удаление новостей, управление вложениями, обложками, галереями, опросами и категориями, просмотр версий и черновиков, рассылка опубликованной новости по email и управление справочником получателей. |
| `admin` | Всё выше + доступ к корзине (`GET /api/v1/news/trash`), восстановление (`restore`), окончательное удаление (`purge`), удаление любых комментариев. |

### Таргетинг

Для обычных пользователей (`user`) видимость опубликованных новостей фильтруется по двум критериям (в `./backend/app/services/news/_helpers.py`):
1. **Подразделение (`target_departments`)**: если массив пуст или равен `NULL`, новость видна всем. Если заполнен, то у пользователя поле `department` должно совпадать с одним из значений в массиве.
2. **Роль (`target_roles`)**: если массив пуст или равен `NULL`, новость видна всем. Если заполнен, то у пользователя поле `role` должно совпадать с одним из значений в массиве.
3. Редакторы (`editor`) и администраторы (`admin`) игнорируют таргетинг и видят все новости.

### Проверка прав чтения (require_news_read_access)

Процедура `require_news_read_access` (в `./backend/app/api/news/_common.py`) гарантирует, что обычные пользователи (`user`) не могут запрашивать новости со статусом, отличным от `published` (черновики и архивные вызывают ошибку 403 Forbidden).

---

## 5. REST API

Базовый путь: `/api/v1`. Все конечные точки требуют авторизации.

### Новости (`./backend/app/api/news/routes.py`)

| Метод | Путь | Назначение | Права | Идемпотентность |
|---|---|---|---|---|
| GET | `/api/v1/news` | Список новостей (пагинация, поиск `q` через ILIKE, фильтрация) | CurrentUser | — |
| GET | `/api/v1/news/limits` | Получить лимит размера загружаемых файлов | CurrentUser | — |
| GET | `/api/v1/news/trash` | Список удалённых новостей в корзине | AdminDep | — |
| GET | `/api/v1/news/{news_id}` | Получить новость по ID (счётчик просмотров инкрементируется) | CurrentUser | — |
| POST | `/api/v1/news` | Создать новость | EditorDep | `Idempotency-Key` (кэш в Redis на 24 ч) |
| PUT | `/api/v1/news/{news_id}` | Обновить новость (создаёт `NewsVersion`) | EditorDep | — |
| PUT | `/api/v1/news/{news_id}/draft` | Автосохранение черновика (только если `status='draft'`) | EditorDep | — |
| DELETE | `/api/v1/news/{news_id}` | Переместить новость в корзину (soft-delete) | EditorDep | — |
| POST | `/api/v1/news/{news_id}/restore` | Восстановить новость из корзины | AdminDep | — |
| DELETE | `/api/v1/news/{news_id}/purge` | Окончательно удалить новость (hard-delete) | AdminDep | — |
| GET | `/api/v1/news/{news_id}/versions` | Просмотреть историю версий новости | EditorDep | — |
| POST | `/api/v1/news/{news_id}/share-email` | Разослать новость по email получателям из справочника (только `published`; rate-limit 10/min) | EditorDep | `Idempotency-Key` (кэш `{enqueued}` в Redis) |

- **Query-параметры `GET /api/v1/news`**: `page`, `page_size` (или `limit`), `offset`, `status` (`draft`/`published`/`archived`), `category`, `is_pinned`, `q` (FTS, макс. 200 символов).

### Медиа и вложения (`./backend/app/api/news/media.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| POST | `/api/v1/news/{news_id}/cover` | Загрузить обложку (генерация WebP + AVIF) | EditorDep |
| DELETE | `/api/v1/news/{news_id}/cover` | Удалить обложку | EditorDep |
| GET | `/api/v1/news/{news_id}/gallery` | Список изображений галереи | CurrentUser |
| POST | `/api/v1/news/{news_id}/gallery` | Загрузить изображение в галерею | EditorDep |
| PATCH | `/api/v1/news/{news_id}/gallery/reorder` | Изменить порядок сортировки галереи | EditorDep |
| DELETE | `/api/v1/news/{news_id}/gallery/{img_id}` | Удалить изображение из галереи | EditorDep |
| GET | `/api/v1/news/{news_id}/attachments` | Список вложенных файлов | CurrentUser |
| POST | `/api/v1/news/{news_id}/attachments` | Загрузить файл во вложения | EditorDep |
| GET | `/api/v1/news/{news_id}/attachments/{att_id}/download` | Скачать файл вложения | CurrentUser |
| DELETE | `/api/v1/news/{news_id}/attachments/{att_id}` | Удалить файл вложения | EditorDep |
| POST | `/api/v1/news/{news_id}/inline-media` | Загрузить инлайн-изображение в тело новости | EditorDep |
| GET | `/api/v1/news/{news_id}/inline-media/{filename}` | Раздача инлайн-медиа через Nginx `X-Accel-Redirect` | CurrentUser |

### Экспорт (`./backend/app/api/news/export.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news/{news_id}/export/html` | Экспорт новости в HTML (изображения в Base64) | CurrentUser |
| GET | `/api/v1/news/{news_id}/export/markdown` | Экспорт новости в Markdown | CurrentUser |
| GET | `/api/v1/news/{news_id}/export/pdf` | Экспорт новости в PDF (генерация через Playwright) | CurrentUser |

### Опросы (`./backend/app/api/news/poll.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news/{news_id}/poll` | Получить опрос новости и результаты | CurrentUser |
| POST | `/api/v1/news/{news_id}/poll` | Создать опрос для новости | EditorDep |
| PATCH | `/api/v1/news/{news_id}/poll` | Обновить параметры опроса | EditorDep |
| DELETE | `/api/v1/news/{news_id}/poll` | Удалить опрос новости | EditorDep |
| POST | `/api/v1/news/{news_id}/poll/close` | Принудительно закрыть опрос вручную | EditorDep |
| POST | `/api/v1/news/{news_id}/poll/reopen` | Переоткрыть опрос | EditorDep |
| POST | `/api/v1/news/{news_id}/poll/vote` | Проголосовать в опросе | CurrentUser |
| DELETE | `/api/v1/news/{news_id}/poll/vote` | Отозвать свой голос (если разрешено) | CurrentUser |
| GET | `/api/v1/news/{news_id}/poll/voters` | Список участников (для анонимных — только editor/admin) | CurrentUser |

### Реакции — лайки (`./backend/app/api/news/reactions.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| POST | `/api/v1/news/{news_id}/like` | Поставить лайк (идемпотентно) | CurrentUser |
| DELETE | `/api/v1/news/{news_id}/like` | Снять лайк (идемпотентно) | CurrentUser |

- Реакция — только «лайк» (♥, без дизлайка). Операции идемпотентны: повтор возвращает текущее состояние `{ like_count, liked_by_me }` без ошибки.
- Уважают `require_news_read_access` (таргетированная новость для пользователя без доступа → 404/403).
- Денормализованный `news.like_count` обновляется в той же транзакции; при снятии — через `GREATEST(0, like_count - 1)`.
- Поля `like_count`, `liked_by_me`, `comment_count` присутствуют в `NewsPublic` (в списке и детальной). `liked_by_me` вычисляется LEFT JOIN `news_likes` по текущему пользователю — без N+1.

### Комментарии (`./backend/app/api/news/comments.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news/{news_id}/comments` | Список комментариев (по возрастанию `created_at`, `?limit=20&offset=0`) | CurrentUser |
| POST | `/api/v1/news/{news_id}/comments` | Добавить комментарий (`body` 1..4000, `sanitize_markdown`) | CurrentUser |
| PATCH | `/api/v1/news/{news_id}/comments/{comment_id}` | Inline-редактирование своего комментария | Автор |
| DELETE | `/api/v1/news/{news_id}/comments/{comment_id}` | Мягкое удаление (`deleted_at`) | Автор или admin |

- Плоские комментарии (зеркало `kb_article_comments`) с добавленным inline-редактированием. Чтение/постинг — все с read-доступом к новости; edit — только автор; delete — автор или admin.
- Удалённый комментарий отдаётся как `is_deleted: true` без тела и автора.
- Денормализованный `news.comment_count` поддерживается в той же транзакции (инкремент при создании, `GREATEST(0, comment_count - 1)` при удалении).

### Категории (`./backend/app/api/news_categories.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/news-categories` | Получить список категорий с числом новостей | CurrentUser |
| POST | `/api/v1/news-categories` | Добавить новую категорию | EditorDep |
| PATCH | `/api/v1/news-categories/{name}/color` | Изменить цвет категории | EditorDep |
| PATCH | `/api/v1/news-categories/{name}` | Переименовать категорию (обновит и все новости) | EditorDep |
| DELETE | `/api/v1/news-categories/{name}` | Удалить категорию (удалит из всех новостей) | EditorDep |

### Справочник получателей рассылки (`./backend/app/api/mailing_recipients.py`)

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/mailing-recipients` | Список получателей (поиск `q` по имени/email, пагинация) | EditorDep |
| POST | `/api/v1/mailing-recipients` | Создать получателя | EditorDep |
| PUT | `/api/v1/mailing-recipients/{recipient_id}` | Обновить получателя (partial) | EditorDep |
| DELETE | `/api/v1/mailing-recipients/{recipient_id}` | Soft-delete получателя | EditorDep |

- Чтение списка тоже требует `editor+` — справочник используется только в модалке рассылки.
- `email` хранится/валидируется как `str` (regex `^[^@\s]+@[^@\s]+$`), не `EmailStr` (DNS-проверка ломается на `.local`).
- CI-уникальность email среди активных строк (частичный индекс `idx_mailing_recipients_email_ci_active`) → конфликт = `409`.

---

## 6. Специфика модуля

### Форма создания/редактирования (UX)

`NewsFormPage.vue` — тонкий wiring-слой (≈130 LOC) над под-компонентами `components/news/*` (конвенция «толстые страницы» из `AGENTS.md`); зеркалит редактор статьи KB (`KbArticleFormPage.vue`).

- **Layout «контент + сайдбар».** CSS Grid (`.form-grid`: `minmax(0,1fr)` + сайдбар 320px, на ≤1024px схлопывается в одну колонку). Слева — главные поля (`NewsFormMainFields`: заголовок + `RichEditor` + галерея/вложения/опрос), справа — карточка настроек (`NewsFormSettingsCard`: обложка, статус, категории, закрепление, расписание публикации/архивации, кнопки save-draft/publish).
- **Inline-валидация обязательных полей.** Через `NForm` + `rules`: `title` — `required`; `body` — кастомный валидатор `!isBodyEmpty(value)` (`isBodyEmpty` из `./frontend/src/pages/composables/newsFormMappers.ts` снимает HTML-теги и `&nbsp;`). Сабмит (`saveAsDraft`/`publish`) вызывает `validateForm()` и прерывается при ошибке.
- **Guard несохранённых изменений.** `useFormLeaveGuard` (`./frontend/src/composables/useFormLeaveGuard.ts`) на `onBeforeRouteLeave` показывает диалог Naive UI (`news.leave.*`), пока `isDirty` из `useNewsFormState`. Нативный `beforeunload`-промпт намеренно не включён.
- **Автофокус** на поле заголовка в режиме создания (`NewsFormMainFields`, проп `autofocus="!isEdit"`).
- **Autosave черновика.** `useNewsFormState` периодически (`AUTOSAVE_INTERVAL_MS = 30s`) сохраняет черновик через `PUT /api/v1/news/{id}/draft` (только для `status='draft'`).

### Обложка и адаптивные варианты

- При загрузке обложки в `./backend/app/services/news/cover.py` синхронно генерируются варианты WebP и AVIF с ширинами 400, 800, 1200 и 1600 пикселей (только те, которые не превышают ширину оригинального файла), качество сжатия 82.
- Доминантный цвет вычисляется сжатием изображения до размера 1×1 px.
- Обложка сохраняется на диске в `/data/news_media/{news_id}/cover.{ext}`, а сжатые варианты — как `cover-{w}.webp` и `cover-{w}.avif`. В ответе API передаются `cover_webp_srcset` и `cover_avif_srcset` для использования в `<picture>`.
- Если библиотека Pillow недоступна, оригинальный файл обложки используется в качестве fallback.
- **Точка фокуса (`cover_focal_x` / `cover_focal_y`).** Обложка не кадрируется на сервере — кадрирование делает CSS `object-fit: cover` + `object-position`. Точка фокуса задаётся в процентах (0–100; `NULL` = центр 50/50) и определяет, какая область фото остаётся видимой при обрезке в карточках (`NewsCard.vue`) и в шапке статьи (`NewsDetailPage.vue`). Хелпер `./frontend/src/utils/coverFocal.ts` (`clampFocalCoord`, `focalObjectPosition`) — единственный источник логики `object-position`. В `NewsCoverUpload.vue` точка задаётся drag-маркером поверх превью (pointer-события → проценты с клампом 0–100, стрелки клавиатуры для точной настройки); в режиме редактирования изменение дебаунсится и сохраняется через `PUT /news/{id}`.

### Галерея и вложения

- **Галерея**: изображения загружаются в `/data/news_media/{news_id}/gallery/{uuid}.{ext}`. Сортировка задается полем `sort_order`, автоинкрементируемым при добавлении. Порядок сортировки настраивается через PATCH-эндпоинт reorder.
- **Вложения**: файлы хранятся как `/data/news_media/{news_id}/attachments/{uuid}` (без расширения для исключения запуска небезопасного кода). Скачивание происходит через эндпоинт download, возвращающий `FileResponse` с заголовком `Content-Disposition`, содержащим оригинальное имя файла. Размер ограничивается настройкой `news_attachment_max_size_mb` (по умолчанию 50 МБ).

### Инлайн-медиа

- Изображения, вставляемые непосредственно в текст новости, сохраняются в директорию `/data/news_media/{news_id}/inline/{8hex}_{safe_name}`.
- Раздача файлов осуществляется через Nginx с использованием механизма `X-Accel-Redirect: /internal/news-media/{news_id}/inline/{filename}`.
- Имя файла проверяется регулярным выражением `[A-Za-z0-9][A-Za-z0-9._\-]{0,254}`. Лимит размера ограничен настройкой `kb_media_max_size_mb`.

### Версионирование

- При создании и при любом изменении ключевых полей (title, body и др.) новостей создается резервная копия `NewsVersion`. Номер текущей версии в `news.current_version` увеличивается на 1. История версий доступна только редакторам и администраторам.

### Опросы и фоновые задачи (Воркер)

- **Опросы**: Модуль поддерживает сложные опросы с несколькими вопросами, возможностью множественного выбора, обязательными вопросами и текстовыми полями для произвольных ответов.
- **Воркер (ARQ cron)**:
  - `publish_scheduled_news` (каждую минуту) — выполняет публикацию новостей, у которых `publish_at <= NOW()` и `status = 'draft'`. Дополнительно отправляет задание `notify_news_published` на рассылку in-app уведомлений (без email).
  - `archive_expired_news` (каждый час) — переводит новости в статус `'archived'`, если наступило время `archive_at <= NOW()`.
  - `close_expired_polls` (каждую минуту) — закрывает опросы, у которых `closes_at <= NOW()`.

### Уведомления о публикации

- При отложенной публикации (cron `publish_scheduled_news`) запускается ARQ-задача `notify_news_published` из `./backend/app/worker/tasks/notifications.py`:
  1. Выбираются пользователи в соответствии с таргетированием по `target_departments` и `target_roles` (фильтр `notify_inapp=true`).
  2. Отправляются SSE in-app уведомления (колокольчик) с использованием Redis через `notify_users_news_published`.
- **Email по новостям автоматически не отправляется.** Рассылка письма о новости выполняется только вручную через кнопку «поделиться» (см. раздел ниже).

### Рассылка новости по email (share-email)

Ручная адресная рассылка опубликованной новости из карточки (`./frontend/src/components/news/NewsShareEmailModal.vue`) — в отличие от авто-уведомлений при публикации, инициируется редактором и шлёт только выбранным получателям.

- **Только из справочника.** Клиент отправляет `recipient_ids: list[UUID]` (не сырые адреса); backend (`./backend/app/services/mailing_recipients.py::resolve_recipients`) резолвит их в email — подмена адреса в обход справочника невозможна (анти-спам/анти-фишинг). Ad-hoc-ввод адреса в UI запрещён.
- **Только `published`.** Для черновика/архива endpoint возвращает `409` (ссылка вела бы на недоступную получателю новость).
- **Краткий текст.** По умолчанию автоген из `body` (strip Markdown, обрезка ~300 символов в `build_news_excerpt`); редактор может переопределить (`message`, max 2000).
- **Транспорт.** `./backend/app/services/news/email_share.py::share_news_by_email` ставит по одной строке в `email_outbox` (`KIND_NEWS`) на получателя, каждую — в `session.begin_nested()` (SAVEPOINT), чтобы сбой одного INSERT не валил весь батч. Caller (route) делает `commit`. Новый SMTP-код не пишется — переиспользуется общий outbox.
- **Лимиты/защита.** Список — `min 1`, `max 100`; rate-limit `10/min`; опциональный `Idempotency-Key` (кэш `{enqueued}` в Redis). HTML-шаблон письма экранирует заголовок и текст.
- **Шаблон письма (`build_share_email_content`).** Чистая table-вёрстка 600px: брендовая полоса с названием портала (`branding.portal_name`, один раз — без дублирования «портал» в каждой строке; eyebrow показывает категорию новости или «Новость»), full-bleed обложка новости (кликабельна — ведёт на новость), заголовок, краткий текст, CTA-кнопка. Акцентный цвет полосы/eyebrow/кнопки — `branding.accent_color`. Тёмная тема контролируемая: `color-scheme: light dark` + `@media (prefers-color-scheme: dark)` оверрайды (классы `email-*`) вместо слепой инверсии клиентом. Футер отцентрован, есть строка о доступе только из офиса / через корпоративный VPN.
- **Обложка — inline-embed (CID), с фолбэком.** Чтобы картинка показывалась даже без доступа к порталу (VPN/офис), обложка ужимается в email-friendly JPEG (`_helpers.build_email_cover_jpeg`: lazy Pillow, EXIF-transpose, флаттенинг прозрачности на белый, ≤600px, q80) и вкладывается в письмо как inline-вложение (`payload.inline_images` → worker `_build_mime` собирает `multipart/related`, `Content-ID: <cover-{news_id}>`, `src="cid:..."`). Размер inline-картинки ограничен `_MAX_INLINE_COVER_BYTES` (512 KB) — при превышении/ошибке Pillow фолбэк на удалённый `<img src>` (`{portal_base_url}/media/news/{cover_image}?v=<updated_at>`). Байты дублируются по строкам `email_outbox` (по одной на получателя) — отсюда жёсткий cap.
- **Управление справочником.** Drawer на странице новостей (`?manage=mailingRecipients`, `./frontend/src/components/admin/MailingRecipientsSettings.vue`) + команда в Cmd+K — обе под `editor+`.

---

## Безопасность

- **Санитизация**: Содержимое новости (HTML/Markdown) проходит санитизацию при сохранении и экспорте (`sanitize_markdown` в `./backend/app/services/news/crud.py`, `sanitize_html` в `./backend/app/api/news/export.py`), предотвращая XSS.
- **Валидация файлов**: Имя файла инлайн-медиа строго валидируется регулярным выражением для предотвращения path traversal. Файлы вложений сохраняются под бессмысленными именами UUID без оригинального расширения, предотвращая несанкционированное исполнение загруженных скриптов.
- **Лимиты**: Размер загружаемых файлов вложений жестко ограничен на уровне потоковой загрузки (`news_attachment_max_size_mb`), а инлайн-изображений — (`kb_media_max_size_mb`). Максимальное количество категорий ограничено до 100.
- **Защита поиска**: Длина поискового запроса `q` жестко ограничена 200 символами.

---

## События аудита

Аудит ведется централизованно через вызов `push_audit_event` (обернутый в `emit_news_audit` в `./backend/app/api/news/_common.py`).

Записываются следующие события (`event_type`):
- `news.created` — создание новости.
- `news.updated` — изменение новости.
- `news.deleted` — мягкое удаление (в корзину).
- `news.restored` — восстановление из корзины.
- `news.purged` — окончательное удаление из БД и ФС.
- `news.cover_uploaded` — загрузка обложки.
- `news.cover_deleted` — удаление обложки.
- `news.gallery_image_deleted` — удаление картинки галереи.
- `news.attachment_deleted` — удаление вложения.
- `news.email_shared` — рассылка новости по email (в метаданных `requested`/`enqueued`).
- `mailing_recipients.created` / `mailing_recipients.updated` / `mailing_recipients.deleted` — изменения справочника получателей (`resource_type=mailing_recipient`).
- `poll.created` — создание опроса.
- `poll.updated` — изменение опроса.
- `poll.deleted` — удаление опроса.
- `poll.closed` — закрытие опроса.
- `poll.reopened` — переоткрытие опроса.

В метаданных сохраняются IP-адрес клиента (`ip_address`), идентификатор автора/редактора (`user_id`), email (`user_email`), тип ресурса (`resource_type`), ID ресурса (`resource_id`) и его название (`resource_title`).

---

## Тесты

Тестирование модуля покрывает API-энпоинты, логику базы данных, фоновые задачи и frontend-компоненты.

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./backend/tests/unit/test_news_service.py` | Базовые CRUD-операции новостей |
| Unit | `./backend/tests/unit/test_news_routes.py` | Конечные точки API и разграничение прав доступа |
| Unit | `./backend/tests/unit/test_news_categories.py` | Управление категориями новостей |
| Unit | `./backend/tests/unit/test_news_export.py` | Логика экспорта новостей в HTML/MD/PDF |
| Unit | `./backend/tests/unit/test_news_likes.py` | Лайки: идемпотентность, счётчик, таргетинг |
| Unit | `./backend/tests/unit/test_news_comments.py` | Комментарии: CRUD, права (автор/admin), soft-delete, счётчик |
| Unit | `./backend/tests/unit/test_news_email_share.py` | Рассылка: excerpt, HTML/text шаблон, per-recipient SAVEPOINT, изоляция сбоя |
| Unit | `./backend/tests/unit/test_mailing_recipients.py` | Справочник получателей: CRUD, CI-уникальность email, soft-delete, резолв ids |
| Unit | `./backend/tests/unit/test_worker_news_tasks.py` | Задачи автопубликации, архивации и закрытия опросов |
| Unit (Polls) | `./backend/tests/unit/test_news_poll_crud.py` | Создание, обновление и удаление опросов |
| Unit (Polls) | `./backend/tests/unit/test_news_poll_voting.py` | Процесс голосования и подсчет голосов |
| Unit (Polls) | `./backend/tests/unit/test_news_poll_queries.py` | Выборки опросов с результатами |
| Unit (Polls) | `./backend/tests/unit/test_news_poll_helpers.py` | Вспомогательные функции опросов |
| Integration | `./backend/tests/integration/test_news_db.py` | Проверка внешних ключей и триггеров полнотекстового поиска |
| Integration | `./backend/tests/integration/test_news_api.py` | Комплексные сценарии взаимодействия с API |
| Integration | `./backend/tests/integration/test_news_poll_service.py` | Интеграция службы опросов с БД |
| Frontend Unit | `./frontend/tests/unit/news-api.spec.ts` | Клиентские запросы к API новостей |
| Frontend Unit | `./frontend/tests/unit/queries-news.spec.ts` | TanStack Query хуки новостей |
| Frontend Unit | `./frontend/tests/unit/news-form-page.spec.ts` | Форма создания и редактирования новости |
| Frontend Unit | `./frontend/tests/unit/news-poll.spec.ts` | Отображение опроса и голосование во Vue |
| Frontend Unit | `./frontend/tests/unit/news-poll-panel.spec.ts` | Настройка опроса в форме редактирования |
| Frontend Unit | `./frontend/tests/unit/news-share-email-modal.spec.ts` | Модалка рассылки: опции получателей, prefill excerpt, валидация, отправка, 409 |
| Frontend Unit | `./frontend/tests/unit/mailing-recipients-api.spec.ts` | API-клиент справочника + `shareNewsEmail`, проброс 409 |

---

## Связанные документы

- `./docs/db-schema.md` — физическая схема базы данных.
- `./docs/api-contracts.md` — контракты и форматы обмена REST API.
- `./docs/roles-matrix.md` — матрица прав доступа.
- `./docs/polls.md` — детальное описание логики работы многовопросных опросов.
- `./docs/notifications.md` — подсистема SSE и email-уведомлений.
- `./docs/audit.md` — ведение логов аудита.
