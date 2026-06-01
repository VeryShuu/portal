# Модуль «Глобальный поиск»

> **Когда читать:** поиск по KB, новостям, ссылкам, пользователям, Cmd+K палитра, typeahead, FTS + pg_trgm.
> **Ключевой код:** `backend/app/api/search.py`, `frontend/src/components/GlobalSearch.vue`, `frontend/src/composables/useGlobalSearch*.ts`, `frontend/src/composables/useSearchNavigation.ts`.
> **ADR:** rate-limit для `/search` и `/search/suggest` зафиксирован в `docs/adr.md` (раздел rate-limits Phase 3.5).

> Единая точка полнотекстового поиска по четырём сущностям портала. Статьи KB и новости индексируются PostgreSQL FTS (словарь `russian_hunspell`), заголовки подхватываются pg_trgm. Ссылки и пользователи — через `ILIKE`. При запросе всех типов одновременно бэкенд исполняет четыре запроса параллельно через `asyncio.gather` с отдельными сессиями. Cmd+K палитра в браузере дополнительно ищет ссылки и закладки локально (in-memory).

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/search.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Naive UI (`./frontend/src/components/GlobalSearch.vue`, `./frontend/src/composables/`) |
| Префикс API | `/api/v1/search` |
| FTS-словарь | `russian_hunspell` (custom PostgreSQL dictionary в `./postgres/hunspell/`) |
| Trigram-поиск | `pg_trgm` расширение PostgreSQL, оператор `%` |
| Rate-limit | `GET /search` — 60/мин/user; `GET /search/suggest` — 120/мин/user |
| Авторизация | `CurrentUser` (JWT-сессия) — все эндпойнты требуют аутентификации |

### Сущности поиска

| Тип (`type`) | Модель | Метод поиска |
|---|---|---|
| `article` | `KbArticle` | FTS по `body_tsvector` + pg_trgm по `title` |
| `news` | `News` | FTS по `body_tsvector` + pg_trgm по `title` |
| `link` | `ServiceLink` | `ILIKE` по `title` и `description` |
| `user` | `User` | `ILIKE` по `full_name`, `email`, `department`, `position` |

---

## 2. REST API

### Эндпойнты

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/search` | Глобальный поиск по одному или всем типам сущностей | Любой авторизованный пользователь |
| GET | `/api/v1/search/suggest` | Typeahead-подсказки по заголовкам KB-статей и новостей | Любой авторизованный пользователь |

### `GET /api/v1/search` — Глобальный поиск

**Параметры запроса:**

| Параметр | Тип | Обязательный | Ограничения | Описание |
|---|---|---|---|---|
| `q` | string | да | 1–200 символов | Поисковый запрос |
| `type` | string | нет | `article` \| `news` \| `link` \| `user` | Фильтр по типу; если не задан — ищет по всем четырём |
| `limit` | integer | нет | 1–50, по умолчанию 20 | Размер страницы |
| `offset` | integer | нет | ≥ 0, по умолчанию 0 | Смещение для пагинации |
| `from_date` | datetime | нет | — | Нижняя граница `created_at` (применяется к `article`, `news`) |
| `to_date` | datetime | нет | — | Верхняя граница `created_at` (применяется к `article`, `news`) |
| `author_id` | UUID | нет | — | Для `article` — `created_by`, для `news` — `author_id` |
| `department` | string | нет | — | Для `news` — `target_departments` содержит значение; для `user` — `ILIKE` по `department` |

**Ответ `SearchResponse`:**

```json
{
  "items": [
    {
      "type": "article",
      "id": "uuid",
      "title": "Заголовок статьи",
      "snippet": "...фрагмент с **выделением** слов...",
      "url": "/kb/articles/{id}",
      "created_at": "2024-01-15T10:00:00Z",
      "author": null
    }
  ],
  "total": 42,
  "query": "ваш запрос"
}
```

Поле `snippet` для `article` и `news` содержит `ts_headline` с маркерами `**` вокруг совпавших слов (опции: `MaxWords=20, MinWords=10`). Для `link` — `description`. Для `user` — строка вида `"Должность · Отдел"`.

### `GET /api/v1/search/suggest` — Typeahead-подсказки

**Параметры запроса:**

| Параметр | Тип | Обязательный | Ограничения | Описание |
|---|---|---|---|---|
| `q` | string | да | 1–100 символов | Начало поискового запроса |

**Ответ `SuggestResponse`:**

```json
{
  "suggestions": ["Название статьи", "Заголовок новости", ...]
}
```

Возвращает не более 10 уникальных строк. Источники: заголовки KB-статей (до 5, после ACL-фильтрации) + заголовки новостей (до 5, с таргетингом). Результаты ранжируются по `func.similarity(title, q).desc()` (pg_trgm).

---

## 3. Механизм поиска

### Индексирование

| Поле | Индекс | Созданный типом |
|---|---|---|
| `kb_articles.body_tsvector` | GIN-индекс, конфиг `russian_hunspell` | Миграция (хранимое tsvector-поле) |
| `news.body_tsvector` | GIN-индекс, конфиг `russian_hunspell` | Миграция (хранимое tsvector-поле) |
| `kb_articles.title` | GIN/GiST через `pg_trgm` | `CREATE INDEX ... USING GIN (title gin_trgm_ops)` |
| `news.title` | GIN/GiST через `pg_trgm` | `CREATE INDEX ... USING GIN (title gin_trgm_ops)` |

### Логика поиска по типу

#### `article` (KB-статья)

- Условие поиска: `body_tsvector @@ plainto_tsquery('russian_hunspell', q) OR title % q`
- Фиксированные фильтры: `deleted_at IS NULL` и `status = 'published'`
- ACL-фильтрация: `apply_article_visibility(stmt, user, session)` — SQL push-down через рекурсивный CTE по `kb_section_permissions` и `kb_article_permissions`
- **Single-type**: ранжирование по `ts_rank(body_tsvector, tsquery) DESC`, поддержка `offset`/`limit`
- **Multi-type**: сортировка по `created_at DESC`, без ts_rank, затем слияние на Python

#### `news` (Новость)

- Условие поиска: `body_tsvector @@ plainto_tsquery('russian_hunspell', q) OR title % q`
- Фиксированные фильтры: `deleted_at IS NULL` и `status = 'published'`
- ACL-фильтрация (для роли, отличной от `editor`/`admin`): `news_targeting_conditions(user)` — `target_departments` пуст ИЛИ содержит отдел пользователя, `target_roles` пуст ИЛИ содержит роль пользователя
- **Single-type**: ранжирование по `ts_rank(body_tsvector, tsquery) DESC`
- **Multi-type**: сортировка по `created_at DESC`

#### `link` (Сервисная ссылка)

- Условие поиска: `title ILIKE '%q%' OR description ILIKE '%q%'` (escape `\`)
- Фиксированный фильтр: `is_active = TRUE`
- ACL: нет — все активные ссылки доступны всем авторизованным пользователям
- **Single-type**: без явной сортировки; **Multi-type**: `created_at DESC`

#### `user` (Пользователь)

- Условие поиска: `ILIKE '%q%'` по полям `full_name`, `email`, `department`, `position`
- ACL: нет — справочник пользователей доступен всем
- Дополнительный фильтр `department`: добавляет `User.department ILIKE '%dept%'` поверх основного условия
- **Single-type**: без явной сортировки; **Multi-type**: `created_at DESC`

### Параллельное исполнение (multi-type)

При запросе без `type` (все 4 типа) каждая ветка выполняется в собственном `AsyncSession` (через `SessionFactoryDep`), все четыре запроса запускаются одновременно через `asyncio.gather`. После сбора результаты мёржатся и сортируются по `created_at DESC`. Счётчик `total` — сумма `total` всех веток.

При single-type используется request-scoped `db`-сессия и поддерживается правильная пагинация (`offset` + `limit`) с сортировкой по релевантности (`ts_rank`).

---

## 4. Frontend

### Cmd+K палитра (`GlobalSearch.vue`)

| Файл | Назначение |
|---|---|
| `./frontend/src/components/GlobalSearch.vue` | Корневой компонент модального окна поиска (Naive UI `n-modal`, 640px). |
| `./frontend/src/composables/useGlobalSearch.ts` | Агрегатор: вызывает news API + `/search` (без параметра `type`) + users API через `Promise.allSettled`. KB-результаты фильтруются на клиенте до `type=article`. |
| `./frontend/src/composables/useGlobalSearchResults.ts` | Реактивное состояние результатов; дебаунс 250 ms, `AbortController` для отмены инфлайт-запросов. |
| `./frontend/src/composables/useGlobalSearchCommands.ts` | Command-режим (префикс `>`): навигация по разделам, создание новостей, управление модулями, смена темы, выход. |
| `./frontend/src/composables/useSearchNavigation.ts` | Клавиатурная навигация `↑`/`↓`/`Enter`/`Esc` по плоскому списку результатов всех групп. |
| `./frontend/src/composables/useSearchRecent.ts` | История запросов в `localStorage` (ключ `gs-recent`, до 8 элементов). |
| `./frontend/src/composables/useGlobalHotkeys.ts` | Глобальные хоткеи: `Ctrl/Cmd+K` и window-событие `open-global-search`. |
| `./frontend/src/components/search/SearchResultGroup.vue` | Переиспользуемая группа результатов с заголовком. |
| `./frontend/src/api/kb.ts` | `globalSearch(q, params)` → `GET /api/v1/search`; `searchSuggest(q)` → `GET /api/v1/search/suggest`. |

### Источники данных в палитре

| Группа | Источник | Лимит | Метод |
|---|---|---|---|
| Новости | `GET /api/v1/news?q=…&status=published` | 6 | Server |
| Ссылки | `linksStore.links` (in-memory) | 6 | Client-side filter |
| Закладки | `linksStore.bookmarks` (in-memory) | 6 | Client-side filter |
| KB-статьи | `GET /api/v1/search?q=…&limit=6` (без `type`; фильтр до `article` на клиенте) | 6 | Server |
| Сотрудники | `GET /api/v1/users?q=…` | 5 | Server |

Ссылки и закладки фильтруются локально по уже загруженному каталогу (`linksStore`), поэтому они появляются мгновенно без сетевого запроса. `ensureCatalogLoaded()` вызывается при открытии палитры.

### Поведение

- **Пустой запрос** — показывается история (`useSearchRecent`, до 8 последних запросов из `localStorage`).
- **`>` + текст** — включается command-режим: фильтрация навигационных команд по тексту. Контент-поиск в этом режиме не выполняется.
- **Обычный запрос** — дебаунс 250 ms, затем параллельно: news API + search API + users API. Предыдущий запрос отменяется (`AbortController`). Ссылки/закладки фильтруются синхронно.
- **Выбор результата** — сохраняет запрос в историю (`saveRecent`), выполняет навигацию (`router.push`) или открывает внешнюю ссылку (`window.open`).
- **Typeahead** — endpoint `/suggest` не используется в основной Cmd+K палитре; он предназначен для отдельных компонентов (> TODO: уточнить, где именно используется `searchSuggest` на фронте).

---

## 5. Особенности и нюансы

### Ранжирование зависит от типа запроса

При `type=article` или `type=news` результаты сортируются по `ts_rank` (полнотекстовая релевантность). При multi-type-запросе ранжирование заменяется сортировкой по `created_at DESC` — нет единой метрики релевантности между разнородными сущностями.

### ACL для статей KB

`apply_article_visibility` добавляет условие на уровне SQL (subquery / JOIN), поэтому `COUNT(*)` для пагинации выполняется уже с учётом прав. В `/suggest` используется более дешёвый Python-фильтр `filter_accessible_articles` (запрашивает 10 кандидатов, фильтрует до 5).

### Таргетинг новостей

Для ролей `editor` и `admin` таргетинг пропускается — они видят все опубликованные новости. Для остальных применяется `news_targeting_conditions`: новость показывается только если `target_departments` пуст ИЛИ включает отдел пользователя, И `target_roles` пуст ИЛИ включает роль.

### Сессии и конкурентность

Один `AsyncSession` (DbDep) держит одно соединение и не поддерживает concurrent-execute. Multi-type поиск открывает 4 отдельные сессии через `SessionFactoryDep` и закрывает их после завершения `gather`.

### `_escape_like`

Запросы для `ILIKE` (ссылки, пользователи) прогоняются через `_escape_like`, которая экранирует `\`, `%`, `_` — защита от SQL wildcard-инъекций.

### Фрагмент (`snippet`) и маркеры

`ts_headline` возвращает текст с парами `**...**` вокруг совпавших лексем. Фронт отвечает за рендеринг этих маркеров (выделение жирным или подсветку).

### Пагинация при multi-type

При запросе без `type` сервер выбирает `offset + limit` записей из каждой ветки, мёржит и сортирует по `created_at`, затем применяет Python-срез `[offset : offset + limit]`. Это означает, что `total` отражает сумму counts всех веток, а не точное число объединённых результатов после дедупликации.
