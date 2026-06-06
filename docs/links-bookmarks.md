# Модуль «Ссылки и закладки»

> **Когда читать:** корпоративные сервисные ярлыки, личные закладки пользователей, SSO-редирект, id_token_hint, проксирование favicon, кэширование в Redis, pg_advisory_xact_lock.
> **Ключевой код:** `./backend/app/api/links.py`, `./backend/app/api/bookmarks.py`, `./backend/app/models/links.py`, `./backend/app/schemas/links.py`, `./frontend/src/pages/LinksAndBookmarksPage.vue`, `./frontend/src/components/links/ServiceLinksTab.vue`, `./frontend/src/components/links/BookmarksTab.vue`, `./frontend/src/pages/admin/tabs/LinksTab.vue`, `./frontend/src/stores/links.ts`, `./frontend/src/api/links.ts`.
> **ADR:** Упоминается в `./docs/adr.md` (в контексте ADR-017 и блокировки reorder через pg_advisory_xact_lock).

> Модуль обеспечивает работу с корпоративными ярлыками (ссылками) и персональными закладками пользователей. Корпоративные ярлыки настраиваются администраторами и поддерживают SSO-редирект, в то время как личные закладки позволяют пользователям создавать свой приватный набор ссылок с автоматическим кэшированием favicon сайтов и ручной сортировкой (drag-and-drop).

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/links.py`, `./backend/app/api/bookmarks.py`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/LinksAndBookmarksPage.vue`) |
| Хранилище | Локальная ФС под `/data/link_icons` (только оригиналы и оптимизированные WebP-иконки ярлыков) |
| Префикс API | `/api/v1/links`, `/api/v1/bookmarks` |

### Возможности
- **Корпоративные ярлыки (ServiceLink)**: глобальные ссылки на сервисы, управляемые администраторами. Поддерживают распределение по категориям, ручную сортировку (reorder), загрузку и оптимизацию кастомных иконок, скрытие отдельных ярлыков пользователями (preferences) и безопасный серверный SSO-редирект с передачей OIDC-токена (`id_token_hint`).
- **Личные закладки (Bookmark)**: индивидуальный набор ссылок каждого пользователя (лимит до 100 закладок). Поддерживают распределение по группам (`group_name`), ручную сортировку перетаскиванием (Drag-and-Drop) с защитой от race-condition на бэкенде через рекомендательные блокировки, а также автоматическое проксирование и кэширование favicon целевых сайтов в Redis.

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/links.py` | API-роутер для работы с корпоративными ярлыками |
| Router | `./backend/app/api/bookmarks.py` | API-роутер для работы с личными закладками пользователей |
| Service | `./backend/app/services/link_icon.py` | Валидация, оптимизация (WebP, до 128px) и сохранение кастомных иконок ярлыков |
| Service | `./backend/app/services/links_crud.py` | Бизнес-логика создания, обновления, удаления и упорядочивания ярлыков |
| Service | `./backend/app/services/links_query.py` | Фильтрация, построение SQL-условий и выборка ярлыков из БД |
| Service | `./backend/app/services/links_sso.py` | Серверная сборка безопасных SSO URL с передачей `id_token_hint` |
| Model | `./backend/app/models/links.py` | Описание SQLAlchemy-моделей `ServiceLink` и `Bookmark` |
| Schema | `./backend/app/schemas/links.py` | Схемы Pydantic для валидации входных/выходных данных ярлыков и закладок |
| Frontend Page | `./frontend/src/pages/LinksAndBookmarksPage.vue` | Единая страница с вкладками корпоративных ярлыков и личных закладок |
| Frontend Tab | `./frontend/src/components/links/ServiceLinksTab.vue` | Вкладка со списком корпоративных ярлыков |
| Frontend Tab | `./frontend/src/components/links/BookmarksTab.vue` | Вкладка личных закладок с поддержкой drag-and-drop |
| Frontend Admin | `./frontend/src/pages/admin/tabs/LinksTab.vue` | Панель управления ярлыками для администраторов |
| Pinia Store | `./frontend/src/stores/links.ts` | Стор Pinia для управления состоянием ярлыков и закладок |
| Frontend API | `./frontend/src/api/links.ts` | API-клиент для отправки запросов к эндпоинтам links/bookmarks |

---

## 3. Модель данных

### Таблица `service_links`
Хранит информацию о глобальных ярлыках сервисов. Ссылка на модель: `ServiceLink` в `./backend/app/models/links.py`.

- **`id`**: `UUID` — Уникальный идентификатор ярлыка (PK, server default: `gen_random_uuid()`).
- **`title`**: `VARCHAR(200)` — Название ярлыка (non-nullable).
- **`url`**: `VARCHAR(2048)` — Целевой URL-адрес (non-nullable, валидируется по схеме http/https).
- **`icon_url`**: `VARCHAR(2048)` — Ссылка на загруженное изображение иконки (nullable).
- **`description`**: `VARCHAR(500)` — Краткое описание сервиса (nullable).
- **`category`**: `VARCHAR(100)` — Категория ярлыка для группировки в интерфейсе (nullable).
- **`sort_order`**: `INTEGER` — Порядковый номер сортировки ярлыка (non-nullable, default: `0`).
- **`supports_sso`**: `BOOLEAN` — Флаг поддержки Single Sign-On (non-nullable, default: `False`).
- **`is_active`**: `BOOLEAN` — Флаг активности ярлыка (non-nullable, default: `True`). Неактивные ярлыки скрыты от обычных пользователей.
- **`created_by`**: `UUID` — Идентификатор администратора, создавшего ярлык (nullable, FK: `users.id` с `ondelete="SET NULL"`).
- **`created_at`**: `TIMESTAMP WITH TIME ZONE` — Дата и время создания (non-nullable, server default: `NOW()`).
- **`updated_at`**: `TIMESTAMP WITH TIME ZONE` — Дата и время обновления (non-nullable, server default: `NOW()`, обновляется при изменениях).

**Индексы таблицы `service_links`**:
- **`idx_service_links_category`**: индекс по колонке `category`.
- **`idx_service_links_sort`**: индекс по колонке `sort_order`.
- **`idx_service_links_active`**: индекс по колонке `is_active`.

### Таблица `bookmarks`
Хранит персональные закладки пользователей. Ссылка на модель: `Bookmark` в `./backend/app/models/links.py`.

- **`id`**: `UUID` — Уникальный идентификатор закладки (PK, server default: `gen_random_uuid()`).
- **`user_id`**: `UUID` — Владелец закладки (nullable, FK: `users.id` с `ondelete="SET NULL"`).
- **`title`**: `VARCHAR(300)` — Название закладки (non-nullable).
- **`url`**: `VARCHAR(2048)` — Целевой URL-адрес (non-nullable, валидируется по схеме http/https).
- **`resource_type`**: `VARCHAR(50)` — Тип связанного ресурса, если закладка создана из внутреннего модуля (nullable).
- **`resource_id`**: `VARCHAR(100)` — Идентификатор связанного внутреннего ресурса (nullable).
- **`group_name`**: `VARCHAR(100)` — Произвольное название группы для группировки в интерфейсе (nullable).
- **`sort_order`**: `INTEGER` — Порядковый номер сортировки внутри списка закладок пользователя (non-nullable, default: `0`).
- **`created_at`**: `TIMESTAMP WITH TIME ZONE` — Дата и время создания закладки (non-nullable, server default: `NOW()`).

**Индексы таблицы `bookmarks`**:
- **`idx_bookmarks_user_id`**: индекс по колонке `user_id`.
- **`idx_bookmarks_user_sort`**: индекс по колонкам `user_id`, `sort_order`.
- **`idx_bookmarks_resource`**: индекс по колонкам `resource_type`, `resource_id`.

---

## 4. Модель прав (ACL)

Доступ к операциям разграничен на основе ролевой модели портала:
- **Корпоративные ярлыки**:
  - Чтение списка ярлыков и переход по ним доступны всем авторизованным пользователям (`CurrentUser`). При этом обычные пользователи видят только активные ярлыки (`is_active=True`), а также могут скрывать отдельные ярлыки из своего личного отображения (их ID записываются в поле `hidden_link_ids` настроек профиля пользователя `user.preferences`).
  - Управление ярлыками (создание, обновление, удаление, сортировка, загрузка и удаление иконок) разрешено исключительно администраторам (проверяется зависимостью `EditorDep` на бэкенде, которая валидирует роль `admin`).
- **Персональные закладки**:
  - Полностью изолированы между пользователями. Каждый пользователь имеет доступ только к своим собственным закладкам.
  - При попытке удаления или изменения порядка закладок, бэкенд строго валидирует принадлежность закладок текущему пользователю (`Bookmark.user_id == user.id`), возвращая `403 Forbidden` или `404 Not Found` в случае несовпадения.

---

## 5. REST API

Все эндпоинты, кроме публичных, требуют авторизации (кука `portal_session`). Базовый префикс всех роутеров — `/api/v1`.

### 5.1. Корпоративные ярлыки (роутер `links` в `./backend/app/api/links.py`)

| Метод | Путь | Описание | Ограничение прав |
|---|---|---|---|
| **GET** | `/links` | Список ярлыков с учетом скрытых пользователем | `CurrentUser` |
| **POST** | `/links` | Создать новый ярлык | `admin` (`EditorDep`) |
| **PATCH**| `/links/reorder` | Массовое изменение порядка сортировки ярлыков | `admin` (`EditorDep`) |
| **GET** | `/links/{link_id}` | Получить метаданные конкретного ярлыка | `CurrentUser` |
| **PUT** | `/links/{link_id}` | Обновить ярлык | `admin` (`EditorDep`) |
| **DELETE**| `/links/{link_id}` | Удалить ярлык (и файлы его иконки) | `admin` (`EditorDep`) |
| **POST** | `/links/{link_id}/icon` | Загрузить файл изображения иконки ярлыка | `admin` (`EditorDep`) |
| **DELETE**| `/links/{link_id}/icon` | Удалить иконку ярлыка | `admin` (`EditorDep`) |
| **GET** | `/links/{link_id}/sso-redirect` | Серверный SSO-редирект с передачей `id_token_hint` в Location (единственный способ перехода с SSO) | `CurrentUser` |

### 5.2. Личные закладки (роутер `bookmarks` в `./backend/app/api/bookmarks.py`)

| Метод | Путь | Описание | Ограничение прав |
|---|---|---|---|
| **GET** | `/bookmarks` | Получить список закладок текущего пользователя | `CurrentUser` |
| **POST** | `/bookmarks` | Создать личную закладку (лимит 100 на пользователя) | `CurrentUser` |
| **PATCH**| `/bookmarks/reorder` | Изменить порядок сортировки закладок пользователя | `CurrentUser` |
| **DELETE**| `/bookmarks/{bookmark_id}` | Удалить закладку по её идентификатору | `CurrentUser` |
| **GET** | `/bookmarks/favicon` | Проксировать и закешировать favicon стороннего сайта | `CurrentUser` |

---

## 6. Особенности реализации

### 6.1. Серверный SSO-редирект
Для корпоративных ярлыков с включенным флагом `supports_sso` используется безопасная схема авторизации:
1. Вместо того чтобы отдавать токен авторизации (`id_token`) на клиент или генерировать ссылку на фронтенде, фронтенд инициирует открытие серверного эндпоинта редиректа через `${BASE_URL}/links/${link.id}/sso-redirect`.
2. Бэкенд извлекает идентификатор сессии пользователя из куки `portal_session`, запрашивает сессионные данные из Redis и достает сохраненный `id_token`.
3. Если токен существует, бэкенд формирует URL целевого сервиса, добавляя токен в query-параметр `id_token_hint` (с использованием `urlencode`).
4. Сервер возвращает HTTP-ответ `302 Found` с заголовком `Location`, содержащим итоговый URL с токеном.
5. Это исключает попадание чувствительного токена в JavaScript-память клиента, консоль разработчика и историю переходов браузера на стороне портала.

### 6.2. Проксирование и кэширование favicon
Для отображения иконок личных закладок пользователя используется специальный прокси-сервер (`/api/v1/bookmarks/favicon`), защищающий приватность пользователей и ускоряющий загрузку:
- Чтобы не выполнять прямые запросы с браузера клиента на сторонние ресурсы (что раскрывало бы IP-адрес пользователя внешним сайтам), иконки скачиваются сервером.
- Бэкенд запрашивает `/favicon.ico` целевого домена с таймаутом `5.0` секунд и юзер-агентом `Mozilla/5.0 (compatible; PortalBot/1.0)`.
- **Успешный кэш**: результат сохраняется в Redis на **7 дней** (`_FAVICON_CACHE_TTL_SUCCESS = 7 * 24 * 3600`) в виде JSON-объекта, содержащего MIME-тип и Base64-строку тела ответа.
- **Негативный кэш (Negative Cache)**: если сайт недоступен, вернул ошибку или если размер иконки превысил лимит в **500 КБ**, сервер кэширует признак ошибки на **24 часа** (`_FAVICON_CACHE_TTL_FAILURE = 24 * 3600`), предотвращая повторные долгие запросы к неработающим ресурсам.
- На фронтенде каждая карточка закладки отображает favicon из кэша. Если иконка не найдена или возвращена ошибка, изображение скрывается по событию `@error`, а карточке назначается один из 7 пастельных фонов (вычисляется хэшированием URL-адреса) и стандартная векторная иконка `LinkOutline`.

### 6.3. Защита от Race-Conditions при изменении закладок
Для предотвращения рассинхронизации порядка сортировки (`sort_order`) и обхода жесткого лимита в 100 закладок при одновременных параллельных POST-запросах, в `./backend/app/api/bookmarks.py` используется рекомендательная транзакционная блокировка PostgreSQL:
1. Хэш ID пользователя приводится к значению знакового 32-битного целого числа:
   ```python
   user_lock_key = int.from_bytes(hashlib.sha256(user.id.bytes).digest()[:4], "big", signed=True)
   ```
2. Перед выполнением проверок лимита и расчетом `sort_order` бэкенд накладывает xact-блокировку:
   ```sql
   SELECT pg_advisory_xact_lock(:ns, :k)
   ```
   где в качестве пространства имен используется фиксированный префикс `0x424F4F4B` ('BOOK').
3. Блокировка автоматически и безопасно освобождается СУБД в момент завершения текущей транзакции (`db.commit()`), гарантируя строгую последовательность операций в рамках одного аккаунта.

### 6.4. Оптимизация иконок ярлыков
При загрузке кастомных иконок для корпоративных ярлыков бэкенд производит их автоматическую нормализацию и оптимизацию:
- Загрузка разрешена только для определенного набора MIME-типов: `image/jpeg`, `image/png`, `image/webp`, `image/svg+xml`, `image/x-icon`, `image/vnd.microsoft.icon`.
- Векторные иконки (`.svg`) и файлы формата `.ico` сохраняются и раздаются в оригинальном виде без изменений.
- Растровые изображения (`.jpg`, `.png`, `.webp`) в ленивом режиме (через библиотеку PIL) поворачиваются в соответствии с EXIF (`ImageOps.exif_transpose`), масштабируются методом Ланцоша под максимальный квадрат **128x128 пикселей** (константа `_LINK_ICON_TARGET_PX` в `./backend/app/services/link_icon.py`) и сохраняются в формате **WebP** с качеством `85` и методом компрессии `6`. Прежние файлы иного формата удаляются с диска, а в базу записывается ссылка на оптимизированный WebP-ресурс.

---

## Безопасность

- **Санитизация**: все URL-адреса, добавляемые пользователями или администраторами, строго валидируются на бэкенде через схемы Pydantic на соответствие протоколам `http`/`https` (проверяется функцией `_validate_http_https_url` в `./backend/app/schemas/links.py`). На фронтенде для прямых (не SSO) переходов используется вспомогательная функция `isSafeHttpUrl`.
- **SSO-токены**: `id_token` не передается на клиент в теле ответа, а внедряется сервером через HTTP-ответ `302 Found` с заголовком `Location`, предотвращая утечку OIDC-токенов в JS-память, веб-историю и консоль разработчика.
- **Favicon-проксирование**: скачивание иконок сайтов сервером вместо прямого обращения браузера защищает IP-адреса пользователей от логирования внешними сайтами. Предусмотрен лимит размера скачиваемых иконок в **500 КБ** и таймаут **5.0 секунд**.

---

## События аудита

Аудит операций с ярлыками выполняется через вызов `_emit_link_audit(...)` в `./backend/app/api/links.py`. События пишутся в Redis через эмиттер `link` со следующими `event_type`:
- **`links.created`**: при создании ярлыка администратором.
- **`links.updated`**: при обновлении ярлыка или загрузке/удалении его иконки (с указанием измененных полей в `metadata["fields"]`).
- **`links.deleted`**: при удалении ярлыка.
- **`links.reordered`**: при изменении порядка сортировки ярлыков (с указанием общего количества элементов в `metadata["count"]`).

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit (Backend) | `./backend/tests/unit/test_links_api.py` | Unit-тесты для API корпоративных ярлыков |
| Unit (Backend) | `./backend/tests/unit/test_links_bookmarks.py` | Тестирование бизнес-логики и связи моделей |
| Unit (Backend) | `./backend/tests/unit/test_bookmarks.py` | Unit-тесты для API личных закладок |
| Unit (Backend) | `./backend/tests/unit/test_bookmarks_favicon.py` | Тестирование проксирования и кэширования favicon |
| Integration (Backend) | `./backend/tests/integration/test_bookmarks_race.py` | Интеграционный тест защиты от race condition с pg_advisory_xact_lock |
| Frontend Unit | `./frontend/tests/unit/links-api.spec.ts` | Покрытие API-методов для ссылок и закладок |
| Frontend Unit | `./frontend/tests/unit/links-store.spec.ts` | Тестирование стора Pinia `links` |
| Frontend Unit | `./frontend/tests/unit/link-visuals.spec.ts` | Проверка отрисовки иконок и пастельного фона |
| Frontend Unit | `./frontend/tests/unit/editor-link-dialog.spec.ts` | Тестирование диалогового окна выбора ссылок в редакторе |

---

## Связанные документы

- `./docs/db-schema.md` — схема базы данных
- `./docs/api-contracts.md` — контракты REST API
- `./docs/roles-matrix.md` — ролевая модель и уровни доступа
- `./docs/adr.md` — технические решения (ADR-017)
