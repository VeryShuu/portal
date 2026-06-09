# Фича: Оценки (лайки) и комментарии к новостям

> **Когда читать:** возобновляешь незавершённую работу по лайкам/комментариям
> новостей — этот план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Удаляется после мёржа фичи.

## Цель

Добавить к новостям две социальные механики:
- **Лайк (♥, только положительная оценка, без дизлайка)** — один голос на
  пользователя, toggle. Виден и кликается **и в ленте (карточка), и на детальной
  странице новости**.
- **Комментарии** — плоский список (без веток), с аватаром/именем/относительным
  временем, редактированием и удалением своего (admin удаляет любой). Живут на
  детальной странице; **счётчик комментариев** показывается на карточке в ленте.

## Базовые решения (зафиксированы)

- **Лайк = hard-delete toggle** (строка `(news_id, user_id)` появляется/исчезает),
  по аналогии с `news_poll_voters` — это не контент, soft-delete не нужен.
  Исключение из правила «soft delete везде» оправдано прецедентом голосования.
- **Комментарий = soft-delete** (`deleted_at`), 1:1 копия паттерна
  `kb_article_comments` (`app/api/kb/comments.py`).
- **Денормализованные счётчики** `like_count` и `comment_count` на таблице `news`
  (прецедент — `news_poll_options.votes_count`): поддерживаются в той же
  транзакции, что и мутация. Это даёт дешёвый рендер ленты без агрегатов per-card.
- **`liked_by_me`** в ленте/детали считается LEFT JOIN-ом `news_likes` по
  текущему пользователю (агрегат отдельно от счётчика).
- Уровни доступа: чтение лайков/комментариев и постинг — **любой
  авторизованный** с read-доступом к новости (`require_news_read_access`).
  Редактировать комментарий — только автор; удалять — автор или admin.
- Комментарии: тело прогоняется через `sanitize_markdown` (как в KB), рендер —
  как обычный текст (markdown в комментариях НЕ рендерим, чтобы совпасть с KB).

## Открытые вопросы

- (нет) — модель оценок, размещение и набор фич согласованы с пользователем.

---

# Поэтапное ТЗ

> Порядок: backend сначала (миграции/контракты), затем frontend. Каждая фаза —
> самостоятельный коммит с зелёными `ruff + mypy + pytest tests/unit`.

## Фаза 1 — Backend: лайки

**Модель** (`app/models/news.py`):
- Новый класс `NewsLike`:
  - `id` UUID PK, `news_id` FK→`news.id` `ON DELETE CASCADE`,
    `user_id` FK→`users.id` `ON DELETE CASCADE`, `created_at`.
  - `UniqueConstraint("news_id", "user_id", name="uq_news_likes_news_user")`.
  - `Index("idx_news_likes_user", "user_id")` (FK-индекс).
- В `News`: колонка `like_count: int` (`Integer, NOT NULL, server_default="0"`).

**Миграция `068_news_likes.py`**:
- `CREATE TABLE news_likes (...)` + unique + индекс.
- `ALTER TABLE news ADD COLUMN like_count INTEGER NOT NULL DEFAULT 0`
  (новая колонка с DEFAULT — безопасно, бэкфилл не нужен).

**Схемы** (`app/schemas/news.py`):
- В `NewsPublic` добавить `like_count: int = 0` и `liked_by_me: bool = False`
  (оба с дефолтами, заполняются в сервисе/роуте, не из ORM-атрибутов напрямую).
- Новая `NewsLikeState(BaseModel)`: `{ like_count: int, liked_by_me: bool }`.

**Сервис** (`app/services/news/`):
- Новый модуль `app/services/news/likes.py`:
  - `async def like_news(db, *, news_id, user_id) -> NewsLikeState` — INSERT
    `ON CONFLICT DO NOTHING`; если вставлено — `news.like_count += 1`. Вернуть
    актуальное состояние.
  - `async def unlike_news(db, *, news_id, user_id) -> NewsLikeState` — DELETE;
    если удалено — `news.like_count -= 1` (с `GREATEST(0, ...)` защитой).
  - `async def get_like_state(db, *, news_id, user_id) -> NewsLikeState`.
- В `get_news_list` / `get_news_by_id` (`app/services/news/crud.py`/queries):
  подмешать `liked_by_me` (LEFT JOIN `news_likes` по `user_id`) — отдать
  роуту, который проставит поле в `NewsPublic`. `like_count` читается прямо из
  колонки.

**API** (`app/api/news/reactions.py`, регистрация в `app/api/news/__init__.py`):
- `POST /news/{news_id}/like` → 200 `NewsLikeState`. Проверка
  `require_news_read_access`. Идемпотентно (повторный лайк не плодит строк).
- `DELETE /news/{news_id}/like` → 200 `NewsLikeState`.
- Аудит **не** обязателен (не admin-mutating контент); не добавляем шум в
  `audit_log`. Rate-limit не требуется (toggle, дешёвый).

**Тесты** (`backend/tests/unit/`):
- like → счётчик +1, повторный like идемпотентен; unlike → −1, повторный
  unlike не уходит в минус; `liked_by_me` корректен для автора и стороннего;
  403 при отсутствии read-доступа к таргетированной новости.

## Фаза 2 — Backend: комментарии

**Модель** (`app/models/news.py`) — зеркало `KbArticleComment`:
- `NewsComment`: `id` PK, `news_id` FK→`news.id` `CASCADE`,
  `author_id` FK→`users.id` `SET NULL` (nullable), `body` Text NOT NULL,
  `deleted_at`, `created_at`, `updated_at`.
  - `Index("idx_news_comments_news", "news_id", "created_at")`,
  - `Index("idx_news_comments_active", "news_id", postgresql_where=text("deleted_at IS NULL"))`.
- В `News`: колонка `comment_count: int` (`NOT NULL, server_default="0"`) —
  считает **активные** (не удалённые) комментарии.

**Миграция `069_news_comments.py`**:
- `CREATE TABLE news_comments (...)` + индексы.
- `ALTER TABLE news ADD COLUMN comment_count INTEGER NOT NULL DEFAULT 0`.

**Схемы** (`app/schemas/news.py`):
- `NewsCommentAuthor` (= `id, full_name, avatar_url`) — можно переиспользовать
  идею `KbUserRef`.
- `NewsCommentPublic`: `{ id, news_id, body|null, is_deleted, created_at,
  updated_at, author|null }`.
- `NewsCommentList`: `{ items, total }`.
- `CreateNewsCommentRequest` / `UpdateNewsCommentRequest`:
  `body: str = Field(min_length=1, max_length=4000)`.
- В `NewsPublic` добавить `comment_count: int = 0`.

**Репозиторий + роуты** (`app/api/news/comments.py` + `comments_repo.py`,
зеркало `app/api/kb/comments*.py`):
- `GET /news/{news_id}/comments?limit&offset` → `NewsCommentList`
  (read-access; удалённые отдаются как `is_deleted=true`, `body=null`).
- `POST /news/{news_id}/comments` → 201 `NewsCommentPublic`. `sanitize_markdown`,
  `news.comment_count += 1` в той же транзакции.
- `PATCH /news/{news_id}/comments/{comment_id}` → 200 `NewsCommentPublic`.
  Только автор; нельзя редактировать удалённый (409); обновляет `updated_at`.
- `DELETE /news/{news_id}/comments/{comment_id}` → 204 (soft).
  Автор или admin; повторное удаление → 409; `news.comment_count -= 1`.
- Регистрация роутера в `app/api/news/__init__.py`.

**Тесты** (`backend/tests/unit/`):
- create → `comment_count` +1 и пункт в списке; edit чужого → 403; edit
  удалённого → 409; delete своего → soft + счётчик −1; delete admin'ом чужого →
  ok; delete чужого обычным юзером → 403; список отдаёт удалённые как
  `is_deleted`.

## Фаза 3 — Frontend: лайк (карточка + детальная)

**api** (`frontend/src/api/news.ts`):
- Типы `NewsLikeState`; функции `likeNews(id)`, `unlikeNews(id)`.
- В тип `News` добавить `like_count`, `liked_by_me`, `comment_count`
  (после `npm run gen:types` подтянутся из OpenAPI; ручной тип синхронизировать).

**queries** (`frontend/src/queries/news.ts`, ключи — `queries/keys.ts`):
- `useToggleNewsLikeMutation` — **оптимистичный** апдейт: на лету меняем
  `liked_by_me` и `like_count` в кэше `news.list(*)` и `news.detail(id)`,
  откат при ошибке, инвалидация в `onSettled`.

**Компонент** `frontend/src/components/news/NewsLikeButton.vue`:
- Props: `{ newsId, likeCount, liked, size? }`. Кнопка-пилюля: контур `♡` →
  залитое `♥` (фирменный `--color-brand-red`), счётчик рядом, анимация
  `scale`-пульса при лайке. Эмитит/вызывает мутацию.
- Гость/нет прав — кнопка disabled (или скрыта) — уточнить по
  `require_news_read_access` (для таргетированных новостей).

**Встраивание:**
- `components/news/NewsCard.vue` — в `.news-card__footer` (строка ~87): слева дата,
  справа `👁 view_count` · `💬 comment_count` · `<NewsLikeButton>`.
  **Критично:** на кнопке лайка `@click.stop`, иначе клик уйдёт в навигацию
  карточки (`@click="$emit('click', news.id)"` на `<article>`). `💬` —
  статичный счётчик, по клику карточка открывается как обычно.
- `pages/NewsDetailPage.vue` — `<NewsLikeButton>` в зоне `.article__actions`
  (или в `.article__meta` рядом с просмотрами, строка ~50).

## Фаза 4 — Frontend: комментарии (детальная)

**api** (`frontend/src/api/news.ts`): `fetchNewsComments`, `createNewsComment`,
`updateNewsComment`, `deleteNewsComment` + типы (зеркало `api/kb.ts`).

**queries** (`queries/news.ts` + `queries/keys.ts`): `useNewsCommentsQuery(id)`,
мутации create/update/delete с инвалидацией `news.comments(id)` и
`news.detail(id)` (для `comment_count`).

**Composable** `composables/useNewsComments.ts` — зеркало
`useKbArticleComments.ts`: `comments, total, submitting, newComment, submit,
edit, remove`.

**Компоненты** (`components/news/`):
- `NewsComments.vue` — секция: заголовок «Комментарии (N)», форма
  (аватар + textarea + «Отправить»), список.
- `NewsCommentItem.vue` — аватар (`avatar_url`), имя, **относительное время**
  (`2 ч назад`; см. утилиту форматирования — проверить наличие relative-format,
  иначе расширить `utils/formatDate.ts`), для своего/admin — `✎ изменить`
  (inline-textarea) и `✕ удалить`. Удалённый → `[комментарий удалён]`.
- Стиль карточек — как `KbArticleCommentsTab.vue` (`--color-surface` + border +
  `--radius-md`), но с аватаром слева.

**Встраивание:** в `pages/NewsDetailPage.vue` после
`<NewsAttachmentsViewer>` (внутри `<article>`).

## Фаза 5 — i18n, docs, финализация

**i18n** (`frontend/src/i18n/ru.json` мастер + `en.json`):
- `news.likes.like`, `news.likes.liked`, `news.likes.count`.
- `news.comments.title`, `.placeholder`, `.submit`, `.edit`, `.save`,
  `.deleted`, `.empty`, `.count`, `.confirmDelete`.
- Проверка: `npm run i18n:check`.

**docs:**
- `docs/db-schema.md` — таблицы `news_likes`, `news_comments`, колонки
  `news.like_count`, `news.comment_count`.
- `docs/api-contracts.md` — новые эндпоинты `/news/{id}/like`,
  `/news/{id}/comments*`.
- `docs/roles-matrix.md` — строки по аналогии с KB-комментариями (чтение —
  все; постинг/лайк — все авторизованные; edit — автор; delete — автор/admin).

**Прогон:**
- backend: `ruff check . && mypy app && pytest tests/unit`.
- frontend: `npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check`.
- Пересборка контейнеров без кэша при необходимости (миграции применяются
  автоматически при старте backend).

---

## Чеклист (DoD)

### Фаза 1 — лайки (backend)
- [x] модель `NewsLike` + колонка `news.like_count`
- [x] миграция `068_news_likes`
- [x] схемы `NewsLikeState` + поля в `NewsPublic`
- [x] сервис `services/news/likes.py` + `liked_by_me` в list/detail
- [x] API `POST/DELETE /news/{id}/like` + регистрация
- [x] unit-тесты

### Фаза 2 — комментарии (backend)
- [x] модель `NewsComment` + колонка `news.comment_count`
- [x] миграция `069_news_comments`
- [x] схемы (`NewsCommentPublic/List`, create/update)
- [x] репозиторий + роуты (`GET/POST/PATCH/DELETE`) + регистрация
- [x] unit-тесты

### Фаза 3 — лайк (frontend)
- [x] api-клиент + типы
- [x] `useToggleNewsLikeMutation` (оптимистичный)
- [x] `NewsLikeButton.vue`
- [x] встроен в `NewsCard.vue` (`@click.stop`) + `NewsDetailPage.vue`
- [x] `💬 comment_count` в футере карточки

### Фаза 4 — комментарии (frontend)
- [x] api-клиент + типы
- [x] queries + `useNewsComments.ts`
- [x] `NewsComments.vue` + `NewsCommentItem.vue`
- [x] встроен в `NewsDetailPage.vue`

### Фаза 5 — финал
- [x] i18n (ru + en) + `i18n:check`
- [x] docs (db-schema, api-contracts, roles-matrix)
- [x] lint + typecheck + tests pass (backend + frontend)

---

## Грабли / контекст

- **Навигация карточки:** вся `<article>` в `NewsCard.vue` — кликабельна
  (`@click` + `@keyup.enter`). Кнопка лайка обязана гасить событие
  (`@click.stop` + по возможности `@keyup.enter.stop`), иначе лайк = переход.
- **`liked_by_me` в списке:** не делать N+1; один LEFT JOIN `news_likes` по
  `current_user.id` в основном list-запросе.
- **Счётчики не уводить в минус:** unlike/удаление — через `GREATEST(0, count-1)`
  на уровне SQL, не доверять рассинхрону.
- **Таргетированные новости:** новость может быть ограничена
  `target_departments/target_roles` — лайк/коммент должны уважать
  `require_news_read_access`, иначе утечка факта существования новости.
- **gen:types:** фронтовые типы генерятся из `openapi.json`
  (`cd backend && python -m scripts.export_openapi`, затем `npm run gen:types`)
  — обновить после изменения схем, не править `types.gen.d.ts` руками.
- **relative-time:** перед Фазой 4 проверить, есть ли в `utils/formatDate.ts`
  относительный формат; если нет — добавить (не тащить новую библиотеку,
  стек зафиксирован).
- **Прецеденты для копирования 1:1:** лайк-счётчик — `news_poll_options.votes_count`
  (денормализация); комментарии — `app/api/kb/comments.py` +
  `comments_repo.py` + `KbArticleCommentsTab.vue` + `useKbArticleComments.ts`.
</content>
</invoke>
