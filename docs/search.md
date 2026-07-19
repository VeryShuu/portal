# Модуль «Глобальный поиск»

> **Когда читать:** при реализации или изменении логики полнотекстового или триграммного поиска (по базе знаний, новостям, сервисным ссылкам, сотрудникам, записям справочников), доработке палитры `Cmd+K` на фронтенде или оптимизации поисковых запросов.
> **Ключевой код:** `./backend/app/api/search.py`, `./backend/app/services/search/aggregate.py`, `./backend/app/services/search/entities.py`, `./backend/app/services/search/filters.py`, `./frontend/src/components/GlobalSearch.vue`, `./frontend/src/composables/useGlobalSearch.ts`, `./frontend/src/composables/useGlobalSearchResults.ts`, `./frontend/src/composables/useGlobalSearchCommands.ts`, `./frontend/src/composables/useSearchNavigation.ts`, `./frontend/src/composables/useSearchRecent.ts`.
> **ADR:** Лимитирование запросов для `/search` и `/search/suggest` зафиксировано в `./docs/adr.md` (раздел rate-limits Phase 3.5). **См. также:** `./docs/db-schema.md`, `./docs/api-contracts.md`, `./docs/roles-matrix.md`.

> Единая точка полнотекстового и триграммного поиска по сущностям корпоративного портала: статьям базы знаний (KB), новостям, внешним ссылкам, сотрудникам и записям справочников. Полнотекстовый поиск (FTS) использует словарь `russian_hunspell` для статей и новостей, а заголовки ранжируются с помощью триграммного сходства `pg_trgm`. Поиск по остальным сущностям выполняется через регистронезависимое сравнение `ILIKE` с автоматическим экранированием спецсимволов. При запросе всех типов одновременно бэкенд параллельно выполняет запросы к БД с использованием отдельных сессий и оркестрацией `asyncio.gather`.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/search.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Naive UI (`./frontend/src/components/GlobalSearch.vue`, `./frontend/src/composables/`) |
| Префикс API | `/api/v1/search` |
| FTS-словарь | `russian_hunspell` (кастомный словарь PostgreSQL в `./postgres/hunspell/`) |
| Trigram-поиск | Расширение `pg_trgm` в PostgreSQL, оператор `%` |
| Rate-limit | `GET /search` — 60 запр./мин на пользователя; `GET /search/suggest` — 120 запр./мин на пользователя |
| Авторизация | `CurrentUser` (JWT-сессия) — все эндпойнты требуют аутентификации |

### Сущности поиска

| Тип (`type`) | Модель | Метод поиска | Ссылка на сущность (URL) |
|---|---|---|---|
| `article` | `KbArticle` | FTS по `body_tsvector` + pg_trgm по `title` | `/kb/articles/{id}` |
| `news` | `News` | FTS по `body_tsvector` + pg_trgm по `title` | `/news/{id}` |
| `link` | `ServiceLink` | `ILIKE` по `title` и `description` | `ServiceLink.url` |
| `user` | `User` | `ILIKE` по `full_name`, `email`, `department`, `position` | `/users/{id}` |
| `directory_entry` | `ObjectDirectoryEntry` | `ILIKE` по `name` | `/staff?tab={slug}` |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/search.py` | FastAPI роутер: валидация параметров, диспетчеризация (single-type vs multi-type), проверка активности модуля справочников |
| Service (Aggregate) | `./backend/app/services/search/aggregate.py` | Оркестрация: параллельный multi-type запуск, слияние/сортировка, typeahead suggest |
| Service (Entities) | `./backend/app/services/search/entities.py` | SQL-запросы поиска для каждой отдельной сущности, маппинг в схемы |
| Service (Filters) | `./backend/app/services/search/filters.py` | Общие SQLAlchemy-предикаты для single/multi-type, экранирование LIKE |
| Frontend Component | `./frontend/src/components/GlobalSearch.vue` | Модальное окно глобального поиска (Cmd+K палитра), command-режим |
| Frontend Composable | `./frontend/src/composables/useGlobalSearch.ts` | Агрегатор внешних запросов к API новостей, поиска и пользователей |
| Frontend Composable | `./frontend/src/composables/useGlobalSearchResults.ts` | Реактивное состояние результатов, дебаунс (250 ms), `AbortController` для отмены |
| Frontend Composable | `./frontend/src/composables/useGlobalSearchCommands.ts` | Локальные команды палитры (со звуковым/визуальным переключением тем, выходом и т.д.) |
| Frontend Composable | `./frontend/src/composables/useSearchNavigation.ts` | Управление фокусом клавиатуры (`↑`/`↓`/`Enter`) по плоскому списку результатов |
| Frontend Composable | `./frontend/src/composables/useSearchRecent.ts` | Сохранение и загрузка истории недавних запросов в `localStorage` |

---

## 3. Модель данных

Полнотекстовый и триграммный поиск опирается на индексы СУБД PostgreSQL. Подробная схема таблиц описана в `./docs/db-schema.md`.

### Используемые индексы

| Таблица | Поле | Тип индекса / Описание |
|---|---|---|
| `kb_articles` | `body_tsvector` | GIN по полнотекстовому полю с конфигурацией `russian_hunspell` |
| `kb_articles` | `title` | GIN через `pg_trgm` (`title gin_trgm_ops`) |
| `news` | `body_tsvector` | GIN по полнотекстовому полю с конфигурацией `russian_hunspell` |
| `news` | `title` | GIN через `pg_trgm` (`title gin_trgm_ops`) |
| `service_links` | `title`, `description` | Обычный `ILIKE` поиск без FTS-индексов |
| `users` | `full_name`, `email` | Обычный `ILIKE` поиск по текстовым полям |
| `object_directory_entries` | `name` | Обычный `ILIKE` поиск в рамках включенных справочников |

Каждая сущность возвращает результаты в формате `SearchResultItem`, которые затем упаковываются в `SearchResponse`.

---

## 4. Модель прав (ACL)

Доступ к результатам поиска строго разграничен в зависимости от роли пользователя. Сводная матрица прав зафиксирована в `./docs/roles-matrix.md`.

- **База знаний (`article`)**: 
  - Проверка прав выполняется на уровне базы данных с помощью функции `apply_article_visibility(stmt, user, session)` из пакета `./backend/app/services/kb_acl/`.
  - Фильтрация выполняется с помощью рекурсивного CTE по правам разделов (`kb_section_permissions`) и статей (`kb_article_permissions`).
  - Для эндпойнта `/search/suggest` применяется облегченный фильтр на Python `filter_accessible_articles(user, articles, db, redis)`.
- **Новости (`news`)**:
  - Члены ролей `editor` и `admin` видят все новости.
  - Для остальных ролей применяется условие `news_targeting_conditions(user)`: новость доступна, если список `target_departments` пуст или содержит отдел пользователя, И `target_roles` пуст или содержит роль пользователя.
- **Справочники (`directory_entry`)**:
  - Доступны только записи из включенных (`ObjectDirectory.enabled == True`) и не удаленных справочников. При поиске проверяется глобальный статус модуля `directories` на бэкенде.
- **Сервисные ссылки и пользователи (`link`, `user`)**:
  - Доступны всем авторизованным пользователям без дополнительных ограничений.

---

## 5. REST API

Все эндпойнты требуют авторизации и возвращают данные согласно `./docs/api-contracts.md`.

### Список эндпойнтов

| Метод | Путь | Назначение | Ограничение (Rate-limit) | Права |
|---|---|---|---|---|
| GET | `/api/v1/search` | Глобальный поиск по сущностям | 60 запросов / мин на пользователя | Любой авторизованный пользователь |
| GET | `/api/v1/search/suggest` | Быстрые подсказки typeahead | 120 запросов / мин на пользователя | Любой авторизованный пользователь |

### Параметры `GET /api/v1/search`

| Параметр | Тип | Обязательный | По умолчанию | Описание |
|---|---|---|---|---|
| `q` | string | Да | — | Строка запроса (1–200 символов) |
| `type` | string | Нет | — | Фильтр по типу: `article`, `news`, `link`, `user`, `directory_entry` |
| `limit` | integer | Нет | 20 | Лимит записей на страницу (1–50) |
| `offset` | integer | Нет | 0 | Смещение пагинации (≥ 0) |
| `from_date` | datetime | Нет | — | Минимальная дата создания (только для `article`, `news`) |
| `to_date` | datetime | Нет | — | Максимальная дата создания (только для `article`, `news`) |
| `author_id` | UUID | Нет | — | ID автора публикации (только для `article`, `news`) |
| `department` | string | Нет | — | Фильтр по отделу (только для `news`, `user`) |

### Формат ответа `SearchResponse`

```json
{
  "items": [
    {
      "type": "article",
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "title": "Инструкция по настройке VPN",
      "snippet": "Для подключения к корпоративной сети используйте **VPN**-клиент...",
      "url": "/kb/articles/3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "created_at": "2026-06-05T12:00:00Z"
    }
  ],
  "total": 1,
  "query": "VPN"
}
```

- Поле `snippet` генерируется через `ts_headline` с маркерами выделения `**` для `article` и `news`. Для `link` в качестве snippet используется `description`. Для `user` — строка в формате `"{Должность} · {Отдел}"`. Для `directory_entry` — русское название справочника `label_ru`.

---

## 6. Механизм поиска (Single-type vs Multi-type)

В зависимости от того, передан ли фильтр `type` в параметрах запроса `/api/v1/search`, бэкенд использует разные подходы к исполнению:

### Single-type (Поиск по конкретному типу)
Используется request-scoped сессия `DbDep`. Результаты извлекаются с поддержкой полноценной пагинации (`limit` и `offset`) и ранжируются по релевантности:
- Для статей и новостей сортировка идет по убыванию релевантности полнотекстового индекса: `ts_rank(body_tsvector, tsquery) DESC`.
- Для остальных типов (пользователи, ссылки, справочники) сортировка идет по убыванию даты создания `created_at DESC` (за исключением случаев, когда порядок сортировки не задан явно).

### Multi-type (Агрегированный поиск по всем типам)
Применяется при отсутствии параметра `type` (или если запрашивается более одного типа одновременно):
1. **Раздельные сессии**: Так как один `AsyncSession` не поддерживает конкурентное выполнение запросов в FastAPI, оркестратор `run_multi_search` создает независимые сессии для каждой сущности с помощью `SessionFactoryDep`.
2. **Параллельное выполнение**: Запросы выполняются конкурентно с помощью `asyncio.gather`.
3. **Ограничение выборки**: Каждая ветка запрашивает порцию данных размером `offset + limit` с сортировкой по дате создания (`created_at DESC`).
4. **Слияние и срез на сервере**: Полученные списки объединяются в памяти на стороне Python, сортируются по `created_at DESC` (с использованием минимальной даты `1970-01-01` в качестве дефолта для записей без даты), после чего применяется срез `[offset : offset + limit]`.
5. **Подсчет total**: Поле `total` в ответе является арифметической суммой `total` всех запущенных веток поиска.

### Безопасность LIKE-запросов (`escape_like`)
Все параметры поиска, использующие операторы `ILIKE` (поиск по ссылкам, пользователям и справочникам), предварительно обрабатываются функцией `escape_like` из `./backend/app/services/search/filters.py`, которая экранирует служебные символы `\`, `%` и `_` для предотвращения wildcard-инъекций.

### Быстрые подсказки (Typeahead Suggest)
Запрос `/api/v1/search/suggest` возвращает не более 10 уникальных предложений:
1. Сначала извлекаются до 10 наиболее похожих статей базы знаний (KB) с ранжированием по триграммному сходству `func.similarity(KbArticle.title, q).desc()`.
2. Список фильтруется на доступность пользователю через `filter_accessible_articles`, оставляя максимум 5 статей.
3. Добираются до 5 новостей, подходящих под триграммный фильтр и настройки таргетинга новостей.
4. Результаты дедуплицируются и возвращаются в `SuggestResponse`.

---

## 7. Frontend и Cmd+K палитра

Глобальный поиск реализован в виде всплывающей палитры (компонент `./frontend/src/components/GlobalSearch.vue`), вызываемой по хоткею `Ctrl+K` или `Cmd+K` (или через событие `open-global-search`).

### Источники данных и интеграция

В палитре комбинируются серверный поиск и локальная фильтрация:

| Источник | Поведение на клиенте | Ссылка на код / Метод |
|---|---|---|
| **Новости** | Серверный поиск (лимит 6) | `fetchNewsList` с фильтром `status=published` |
| **Ссылки** | Локальная фильтрация in-memory по кэшу | `linksStore.links` (до 6 совпадений) |
| **Закладки** | Локальная фильтрация in-memory по кэшу | `linksStore.bookmarks` (до 6 совпадений) |
| **KB-статьи** | Серверный поиск (лимит 6) | `/api/v1/search?limit=6`, фильтр на `type === 'article'` |
| **Сотрудники** | Серверный поиск (лимит 5) | `fetchUsers` |

При первом открытии палитры вызывается `ensureCatalogLoaded()`, лениво загружающий справочники ссылок и закладок в Pinia-хранилище `linksStore`.

### Режимы работы

- **Пустой ввод**: Отображает историю недавних поисковых запросов пользователя (до 8 элементов), сохраненную в `localStorage` под ключом `gs-recent` через composable `./frontend/src/composables/useSearchRecent.ts`.
- **Обычный поиск**: Запуск поиска происходит с дебаунсом в 250 мс. При вводе новых символов предыдущие незавершенные запросы немедленно отменяются через `AbortController` во избежание гонки ответов (race conditions).
- **Командный режим (`>`)**: Если строка начинается с символа `>`, поиск по серверам приостанавливается. Включается локальное меню навигации по разделам, позволяющее быстро переключать тему оформления (светлая/темная), переходить в настройки, выходить из системы или создавать новости.

### Клавиатурная навигация

Composable `./frontend/src/composables/useSearchNavigation.ts` объединяет все активные группы результатов в один плоский список и обеспечивает бесшовную навигацию кнопками `↑` и `↓`, открытие активного элемента по `Enter` и закрытие по `Esc`.

---

## Безопасность

- **Защита от SQL-инъекций**: Достигается использованием ORM SQLAlchemy и принудительным экранированием спецсимволов LIKE с помощью функции `escape_like` из `./backend/app/services/search/filters.py`.
- **Ограничение частоты запросов (Rate Limiting)**: Эндпойнты `/search` (60/мин) и `/search/suggest` (120/мин) ограничены на уровне FastAPI с помощью Redis-бэкенда `fastapi_limiter.depends.RateLimiter`.
- **Валидация длины ввода**: Поисковый запрос валидируется средствами FastAPI Query: для поиска — от 1 до 200 символов, для подсказок — от 1 до 100 символов.
- **Фильтрация ACL на уровне SQL**: Доступ к защищенным статьям базы знаний и таргетированным новостям фильтруется непосредственно внутри SQL-запросов, предотвращая утечку метаданных или сниппетов неавторизованным лицам.

---

## События аудита

Модуль глобального поиска не порождает событий аудита (`push_audit_event`), так как является исключительно read-only инструментом.

---

## Тесты

В репозитории реализованы юнит- и интеграционные тесты для проверки корректности поиска и фильтрации прав.

| Тип | Путь | Покрывает |
|---|---|---|
| Unit (Backend) | `./backend/tests/unit/test_search.py` | Валидация аргументов роутов, логика suggest, дедупликация подсказок, корректность применения ACL, сортировка multi-type и экранирование LIKE |
| Integration (Backend) | `./backend/tests/integration/test_kb_search.py` | Полнотекстовое совпадение FTS, триграммные опечатки через pg_trgm, русская морфология hunspell, сокрытие soft-deleted статей |
| Unit (Frontend) | `./frontend/tests/unit/global-search-smoke.spec.ts` | Рендеринг модального окна, инпут, хоткеи, вызов AbortController, история localStorage, командный режим `>` |

---

## Связанные документы

- `./docs/db-schema.md` — физическая схема таблиц, GIN-индексы
- `./docs/api-contracts.md` — контракты эндпойнтов поиска
- `./docs/roles-matrix.md` — уровни доступа пользователей
- `./docs/adr.md` — архитектурные решения по лимитированию запросов (Phase 3.5)
