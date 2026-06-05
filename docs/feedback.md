# Модуль «Обратная связь» (Feedback)

> **Когда читать:** при работе с модулем обратной связи / обращениями пользователей.
> **Ключевой код:** `./backend/app/api/feedback/`, `./backend/app/models/feedback.py`, `./frontend/src/pages/MyFeedbackPage.vue`, `./frontend/src/pages/admin/tabs/FeedbackTab.vue`.
> **ADR:** —. **См. также:** `./docs/roles-matrix.md`, `./docs/api-contracts.md`, `./docs/db-schema.md`.

> Дать пользователям возможность сообщать об ошибках и оставлять замечания прямо из интерфейса портала. Администратор получает уведомление, может просмотреть список обращений и ответить пользователю. Пользователь видит свои заявки и получает уведомление об ответе.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/feedback/`), SQLAlchemy, PostgreSQL |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/MyFeedbackPage.vue`, `./frontend/src/pages/admin/tabs/FeedbackTab.vue`) |
| Воркер | — |
| Хранилище | Локальная ФС (`/data/feedback/files`) |
| Префикс API | `/api/v1/feedback` |
| ACL-кэш | — |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Router | `./backend/app/api/feedback/routes.py` | FastAPI роутер с описанием конечных точек и лимитов |
| Repo | `./backend/app/api/feedback/feedback_repo.py` | Низкоуровневые SQL-запросы к БД (выборки, подсчеты) |
| Service | `./backend/app/api/feedback/feedback_service.py` | Бизнес-логика обращений, управление статусами, вложениями |
| Model | `./backend/app/models/feedback.py` | Описание SQLAlchemy моделей (`Feedback`, `FeedbackReply`, `FeedbackAttachment`) |
| Schema | `./backend/app/schemas/feedback.py` | Pydantic-схемы сериализации входных и выходных данных |
| Common | `./backend/app/api/feedback/_common.py` | Вспомогательные хелперы маппинга схем, логгер, константы |
| Frontend Pages | `./frontend/src/pages/MyFeedbackPage.vue` | Страница "Мои обращения" пользователя с глубокими ссылками |
| Frontend Tab | `./frontend/src/pages/admin/tabs/FeedbackTab.vue` | Таб "Обращения" в панели администратора |
| Frontend Components | `./frontend/src/components/FeedbackModal.vue` | Плавающая кнопка и модальное окно создания тикета |
| Frontend Components | `./frontend/src/components/FeedbackAttachmentList.vue` | Вспомогательный компонент списка прикреплённых файлов |
| Frontend API | `./frontend/src/api/feedback.ts` | Клиентские API-запросы (методы Axios/Fetch) |

---

## 3. Модель данных

### 3.1 Таблица `feedback`

```sql
CREATE TABLE feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    category    VARCHAR(30)  NOT NULL,  -- 'bug' | 'suggestion' | 'other'
    message     TEXT         NOT NULL,
    page_url    VARCHAR(2000),          -- URL страницы, откуда отправлено (опц.)
    status      VARCHAR(20)  NOT NULL DEFAULT 'open',
                                        -- 'open' | 'in_progress' | 'closed'
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_feedback_category CHECK (category IN ('bug','suggestion','other')),
    CONSTRAINT ck_feedback_status   CHECK (status   IN ('open','in_progress','closed'))
);

CREATE INDEX ix_feedback_user_id    ON feedback(user_id);
CREATE INDEX ix_feedback_status     ON feedback(status);
-- DESC-индекс для сортировки списков по времени (PostgreSQL).
CREATE INDEX ix_feedback_created_at ON feedback(created_at DESC);
```

### 3.2 Таблица `feedback_replies`

```sql
CREATE TABLE feedback_replies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
    admin_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    message     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_feedback_replies_feedback_id ON feedback_replies(feedback_id);
```

### 3.3 Таблица `feedback_attachments`

```sql
CREATE TABLE feedback_attachments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id   UUID NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
    filename      VARCHAR(500) NOT NULL,
    original_name VARCHAR(500) NOT NULL,
    size_bytes    BIGINT NOT NULL,
    mime_type     VARCHAR(255),
    uploaded_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_feedback_attachments_feedback_id ON feedback_attachments(feedback_id);
```

### 3.4 Alembic-миграции

В отличие от первоначального ТЗ, создание таблиц разделено на две миграции в каталоге `./backend/migrations/versions/`:
1. `./backend/migrations/versions/040_add_feedback.py` — создание таблиц `feedback` и `feedback_replies`.
2. `./backend/migrations/versions/041_add_feedback_attachments.py` — создание таблицы `feedback_attachments`.

---

## 4. Модель прав (ACL)

Доступ к обращениям разграничен по ролям пользователей:

| Роль | Права |
|---|---|
| `reader`, `editor` | Создание обращения (`POST /feedback`), просмотр **своих** обращений и ответов (`GET /feedback/my`, `GET /feedback/my/{id}`), управление собственными вложениями (если тикет не закрыт) |
| `admin` | Просмотр **всех** обращений (`GET /feedback`, `GET /feedback/{id}`), изменение статуса (`PATCH /feedback/{id}/status`), ответ пользователю (`POST /feedback/{id}/reply`), полное управление любыми вложениями |

---

## 5. REST API

Все эндпоинты требуют обязательной авторизации (`CurrentUser` / `AdminDep`).

### 5.1 Порядок объявления маршрутов
В коде `./backend/app/api/feedback/routes.py` порядок объявления маршрутов критичен для правильной работы роутинга FastAPI:
1. `POST /feedback`
2. `GET  /feedback/my`
3. `GET  /feedback/my/{feedback_id}`
4. `GET  /feedback` (admin)
5. `GET  /feedback/{feedback_id}` (admin)
6. `PATCH /feedback/{feedback_id}/status`
7. `POST /feedback/{feedback_id}/reply`
8. `POST /feedback/{feedback_id}/attachments`
9. `GET  /feedback/{feedback_id}/attachments/{attachment_id}`
10. `DELETE /feedback/{feedback_id}/attachments/{attachment_id}`

### 5.2 Описание конечных точек

| Метод | Путь | Роли | Описание |
|---|---|---|---|
| `POST` | `/api/v1/feedback` | Любой пользователь | Создать обращение. Лимит: 5 запросов/мин. Вызывает `notify_admins_new_feedback`. |
| `GET` | `/api/v1/feedback/my` | Любой пользователь | Список своих обращений (фильтр `status`, пагинация, `created_at DESC`). |
| `GET` | `/api/v1/feedback/my/{feedback_id}` | Автор обращения | Одно своё обращение с ответами и вложениями. 404 если чужое. |
| `GET` | `/api/v1/feedback` | `admin` | Список всех обращений (фильтры `status`, `category`, поиск `q` по тексту, пагинация). |
| `GET` | `/api/v1/feedback/{feedback_id}` | `admin` | Одно обращение с ответами, вложениями и данными автора (`author_name`, `author_email`). |
| `PATCH` | `/api/v1/feedback/{feedback_id}/status` | `admin` | Изменение статуса. При закрытии отправляет `notify_user_feedback_status_changed`. |
| `POST` | `/api/v1/feedback/{feedback_id}/reply` | `admin` | Добавить ответ. Авто-переключает статус `open` → `in_progress`. Шлет `notify_user_feedback_reply`. Лимит: 30 запросов/мин. |
| `POST` | `/api/v1/feedback/{feedback_id}/attachments` | Автор или `admin` | Прикрепить файл. Лимит: 20 запросов/мин. Макс. 5 вложений, до 10 МБ на файл. Недоступно на закрытом тикете для не-админов. |
| `GET` | `/api/v1/feedback/{feedback_id}/attachments/{attachment_id}` | Автор или `admin` | Скачать файл через внутренний редирект Nginx (`X-Accel-Redirect` в `/internal/feedback-files/...`). |
| `DELETE` | `/api/v1/feedback/{feedback_id}/attachments/{attachment_id}` | Загрузивший или `admin` | Удалить вложение. Недоступно на закрытом тикете для не-админов. |

### 5.3 Pydantic-схемы (`./backend/app/schemas/feedback.py`)

```python
class FeedbackCategory(str, Enum):
    bug        = "bug"
    suggestion = "suggestion"
    other      = "other"

class FeedbackStatus(str, Enum):
    open        = "open"
    in_progress = "in_progress"
    closed      = "closed"

class FeedbackIn(BaseModel):
    category: FeedbackCategory
    message:  str = Field(default="", max_length=5000)  # strip() через field_validator
    page_url: str | None = Field(default=None, max_length=2000)

class FeedbackReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

class FeedbackStatusIn(BaseModel):
    status: FeedbackStatus

class FeedbackAttachmentOut(BaseModel):
    id:            uuid.UUID
    original_name: str
    size_bytes:    int
    mime_type:     str | None
    created_at:    datetime
    download_url:  str            # /api/v1/feedback/{feedback_id}/attachments/{id}

    model_config = ConfigDict(from_attributes=True)

class FeedbackReplyOut(BaseModel):
    id:         uuid.UUID
    admin_id:   uuid.UUID | None
    admin_name: str | None          # full_name администратора (JOIN)
    message:    str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FeedbackOut(BaseModel):
    """Схема для пользовательских эндпоинтов (`/feedback/my*`)."""
    id:          uuid.UUID
    category:    FeedbackCategory
    message:     str
    page_url:    str | None
    status:      FeedbackStatus
    created_at:  datetime
    updated_at:  datetime
    replies:     list[FeedbackReplyOut] = []
    attachments: list[FeedbackAttachmentOut] = []

    model_config = ConfigDict(from_attributes=True)

class FeedbackAdminOut(FeedbackOut):
    """Расширенная схема для админских эндпоинтов: содержит данные автора."""
    user_id:      uuid.UUID | None
    author_name:  str | None      # full_name автора или None, если пользователь удалён
    author_email: str | None      # email автора (для связи), None если удалён

class FeedbackListOut(BaseModel):
    items: list[FeedbackOut]
    total: int

class FeedbackAdminListOut(BaseModel):
    items: list[FeedbackAdminOut]
    total: int
```

---

## 6. Логика работы и Машина состояний

### 6.1 Машина состояний

```
                ┌──── reply от admin (авто) ────┐
                ▼                                │
   open ──────────────► in_progress ────────► closed
    │                       │                    │
    │                       │                    │
    └───────────────────────┴── PATCH /status ───┘
       (admin может вручную перевести в любой статус,
        включая re-open: closed → open / in_progress)
```

- **Авто-переходы**: Первый ответ от администратора (`add_reply`) автоматически переводит статус обращения `open` → `in_progress`.
- **Ручные переходы**: Администратор через `PATCH /status` может вручную выставить любой статус (включая повторное открытие из `closed`).
- **Обновление активности**: Поле `updated_at` модели `Feedback` обновляется при любых изменениях статуса или добавлении ответов (`onupdate=func.now()` и явная установка в коде).

### 6.2 Система уведомлений (`./backend/app/services/notifications.py`)

Рассылка уведомлений выполняется пакетно по паттерну: создание записей `create_notification` в цикле, один `db.commit()`, затем публикация событий в Redis.

#### 6.2.1 `notify_admins_new_feedback`
```python
async def notify_admins_new_feedback(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    author_id: uuid.UUID | None,
    author_name: str,
    category: str,
) -> int:
```
- Получатели: все пользователи с ролью `admin` и `notify_inapp = True`, исключая автора обращения.
- `type`: `"feedback_new"`
- `title`: `f"Новое обращение от {author_name}"`
- `body`: "Ошибка" (`bug`), "Предложение" (`suggestion`), "Другое" (`other`)
- `link`: `f"/admin?tab=feedback"`

#### 6.2.2 `notify_user_feedback_reply`
```python
async def notify_user_feedback_reply(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    user_id: uuid.UUID,
    admin_name: str,
) -> None:
```
- Получатель: автор обращения (если `notify_inapp = True` и `author_id != admin_id`).
- `type`: `"feedback_reply"`
- `title`: `"Администратор ответил на ваше обращение"`
- `body`: `f"Ответ от {admin_name}"`
- `link`: `f"/my-feedback?open={feedback_id}"`

#### 6.2.3 `notify_user_feedback_status_changed`
```python
async def notify_user_feedback_status_changed(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    user_id: uuid.UUID,
    new_status: str,
) -> None:
```
- Вызывается **только при переходе в статус `closed`**.
- Получатель: автор обращения (при `notify_inapp = True`).
- `type`: `"feedback_closed"`
- `title`: `"Ваше обращение закрыто"`
- `body`: `None`
- `link`: `f"/my-feedback?open={feedback_id}"`

---

## 7. Фронтенд-реализация

### 7.1 Структура файлов

```
frontend/src/
├── api/
│   └── feedback.ts                   # API-клиент (интерфейсы и функции)
├── components/
│   ├── FeedbackModal.vue             # Плавающая кнопка формы + модальное окно
│   └── FeedbackAttachmentList.vue     # Вспомогательный компонент для вложений
└── pages/
    ├── MyFeedbackPage.vue            # Страница "Мои обращения"
    └── admin/tabs/
        └── FeedbackTab.vue           # Вкладка администрирования обращений
```

### 7.2 API-клиент (`./frontend/src/api/feedback.ts`)

Определяет интерфейсы (`FeedbackIn`, `FeedbackReplyIn`, `FeedbackOut`, `FeedbackAdminOut` и др.) и экспортирует методы:
- `createFeedback(data: FeedbackIn)` -> `POST /feedback`
- `getMyFeedback(params)` -> `GET /feedback/my`
- `getMyFeedbackById(id)` -> `GET /feedback/my/{id}`
- `getAllFeedback(params)` -> `GET /feedback` (admin)
- `getFeedbackById(id)` -> `GET /feedback/{id}` (admin)
- `replyToFeedback(id, data)` -> `POST /feedback/{id}/reply`
- `updateFeedbackStatus(id, status)` -> `PATCH /feedback/{id}/status`
- `uploadFeedbackAttachment(id, file)` -> `POST /feedback/{id}/attachments`
- `deleteFeedbackAttachment(feedbackId, attachmentId)` -> `DELETE /feedback/{feedbackId}/attachments/{attachmentId}`

### 7.3 Кнопка и модальное окно обратной связи (`./frontend/src/components/FeedbackModal.vue`)
- Монтируется в глобальный layout (`./frontend/src/components/AppLayout.vue`).
- Отображается **только авторизованным пользователям** (`isAuthenticated = true`).
- Скрыта на публичных страницах авторизации (по `route.name`).
- На мобильных устройствах (≤768px) показывается только круглая иконка. По клику открывает `NModal` с формой выбора категории (`bug`, `suggestion`, `other`), полем ввода сообщения (min 10, max 5000 символов). Значение `page_url` заполняется автоматически из `window.location.href`.

### 7.4 Страница "Мои обращения" (`./frontend/src/pages/MyFeedbackPage.vue`)
- Доступна по адресу `/my-feedback` для авторизованных пользователей.
- Выводит список обращений пользователя в виде карточек `NCard` с фильтрами по статусам и пагинацией.
- При раскрытии карточки подгружает и отображает переписку с админами и прикрепленные вложения.
- **Deep-linking (автораскрытие)**: При переходе по ссылке `/my-feedback?open={feedback_id}` (из нотификаций):
  1. Автоматически запрашивает обращение через `getMyFeedbackById` (если его нет в текущем списке пагинации).
  2. Скроллит интерфейс к карточке и разворачивает её детали.
  3. Если обращение не найдено или чужое — выводит ошибку и сбрасывает query-параметр.

### 7.5 Вкладка администрирования (`./frontend/src/pages/admin/tabs/FeedbackTab.vue`)
- Зарегистрирована в `./frontend/src/pages/AdminPage.vue` во вкладке-группе `logs`.
- Доступна только администраторам.
- Содержит таблицу `NDataTable` всех обращений с возможностью фильтрации по категории и статусу, поиском `q` (по тексту сообщений через `ILIKE`).
- По клику открывает модальное окно с полным содержанием тикета, `page_url`, вложениями, селектором статуса и формой быстрого ответа.

### 7.6 Маршрутизация (`./frontend/src/router.ts`)

```typescript
// в объект ROUTES
MY_FEEDBACK: '/my-feedback',

// в массив routes
{
  path: '/my-feedback',
  name: 'my-feedback',
  component: () => import('./pages/MyFeedbackPage.vue'),
  meta: { requiresAuth: true },
}
```

---

## 8. Локализация (i18n)

### 8.1 Локализация для `./frontend/src/i18n/ru.json`
```json
"feedback": {
  "button": "Обратная связь",
  "modalTitle": "Сообщить об ошибке или оставить замечание",
  "categoryLabel": "Категория",
  "categories": {
    "bug": "Ошибка / не работает",
    "suggestion": "Предложение / пожелание",
    "other": "Другое"
  },
  "messageLabel": "Описание",
  "messagePlaceholder": "Опишите проблему или пожелание подробнее...",
  "submit": "Отправить",
  "cancel": "Отмена",
  "successMessage": "Спасибо, обращение принято!",
  "myTickets": "Мои обращения",
  "myTicketsTitle": "Мои обращения",
  "noTickets": "У вас ещё нет обращений",
  "statusLabel": "Статус",
  "statuses": {
    "open": "Открыто",
    "in_progress": "В работе",
    "closed": "Закрыто"
  },
  "repliesSection": "Ответы администратора",
  "noRepliesYet": "Ответ ещё не получен",
  "adminTab": "Обращения",
  "replyPlaceholder": "Ваш ответ...",
  "replyButton": "Ответить",
  "changeStatus": "Изменить статус",
  "filterAll": "Все",
  "pageUrl": "Страница",
  "notifications": {
    "newFeedback": "Новое обращение от {name}",
    "feedbackReply": "Администратор ответил на ваше обращение",
    "feedbackClosed": "Ваше обращение закрыто"
  },
  "deletedUser": "Удалённый пользователь",
  "deletedAdmin": "Удалённый администратор",
  "notFound": "Обращение не найдено"
}
```

### 8.2 Локализация для `./frontend/src/i18n/en.json`
```json
"feedback": {
  "button": "Feedback",
  "modalTitle": "Report a bug or leave a suggestion",
  "categoryLabel": "Category",
  "categories": {
    "bug": "Bug / not working",
    "suggestion": "Suggestion / wish",
    "other": "Other"
  },
  "messageLabel": "Description",
  "messagePlaceholder": "Describe the issue or suggestion in detail...",
  "submit": "Submit",
  "cancel": "Cancel",
  "successMessage": "Thank you, your feedback has been received!",
  "myTickets": "My feedback",
  "myTicketsTitle": "My feedback",
  "noTickets": "You have no feedback yet",
  "statusLabel": "Status",
  "statuses": {
    "open": "Open",
    "in_progress": "In progress",
    "closed": "Closed"
  },
  "repliesSection": "Administrator replies",
  "noRepliesYet": "No reply yet",
  "adminTab": "Feedback",
  "replyPlaceholder": "Your reply...",
  "replyButton": "Reply",
  "changeStatus": "Change status",
  "filterAll": "All",
  "pageUrl": "Page",
  "notifications": {
    "newFeedback": "New feedback from {name}",
    "feedbackReply": "Administrator replied to your feedback",
    "feedbackClosed": "Your feedback has been closed"
  },
  "deletedUser": "Deleted user",
  "deletedAdmin": "Deleted administrator",
  "notFound": "Feedback not found"
}
```

---

## 9. Порядок реализации

Исторический чек-лист этапов разработки:
1. **Миграция БД** — создание таблиц обращений и ответов (`040_add_feedback.py`), затем вложений (`041_add_feedback_attachments.py`).
2. **Backend models** — `./backend/app/models/feedback.py`, регистрация в `./backend/app/models/__init__.py`.
3. **Backend schemas** — `./backend/app/schemas/feedback.py`.
4. **Notification helpers** — добавление 3-х функций в `./backend/app/services/notifications.py`.
5. **Backend API** — реализация роутера в `./backend/app/api/feedback/routes.py`, регистрация в `./backend/app/api/__init__.py`.
6. **Backend tests** — тесты `./backend/tests/unit/test_feedback_service.py` и `./backend/tests/unit/test_feedback_schema.py`.
7. **Frontend API** — `./frontend/src/api/feedback.ts`.
8. **FeedbackModal.vue** — плавающая кнопка и форма.
9. **AppLayout.vue** — подключение `FeedbackModal` с условием рендера.
10. **MyFeedbackPage.vue** — страница с глубокими ссылками.
11. **router.ts** — регистрация путей.
12. **useAppMenu.ts** — интеграция в меню.
13. **AdminPage.vue** — интеграция таба и синхронизация URL.
14. **FeedbackTab.vue** — админский таб в группе `logs`.
15. **i18n** — интеграция переводов.

---

## Безопасность

- **Санитизация и отображение**: поля `message`, `page_url`, `reply.message` на фронтенде рендерятся **исключительно как plain text** (без поддержки HTML/Markdown), что предотвращает XSS-уязвимости. Дополнительная фильтрация на бэкенде не требуется.
- **Валидация `page_url`**: в Pydantic-схеме `FeedbackIn` выполняется строгая проверка через `_validate_page_url`:
  - Допускаются только относительные пути (начинаются с `/` и не с `//`) и абсолютные HTTPS URL (`https://...`).
  - Строго запрещены другие схемы (`http:`, `javascript:`, `data:`, `file:`, `ftp:` и др.).
  - Любое нарушение вызывает `ValueError("Invalid page_url")` → 422 Unprocessable Entity.
- **Ограничения вложений**:
  - Ограничение размера: максимум 10 МБ на файл (`FEEDBACK_ATTACHMENT_MAX_SIZE`).
  - Ограничение количества: максимум 5 вложений на тикет (`FEEDBACK_ATTACHMENT_MAX_PER_TICKET`).
  - Белые списки MIME-типов: разрешены только безопасные типы изображений, PDF, txt, ZIP (`FEEDBACK_ATTACHMENT_ALLOWED_MIMES`).
  - На закрытый тикет загружать или удалять вложения пользователям запрещено (разрешено только админам).
- **Rate limiting (Защита от перегрузки)**:
  - `POST /api/v1/feedback`: `Depends(RateLimiter(times=5, minutes=1))` по `real_ip_identifier` (защита от спама тикетами).
  - `POST /api/v1/feedback/{id}/reply`: `Depends(RateLimiter(times=30, minutes=1))` для защиты от случайных дабл-кликов админов.
  - `POST /api/v1/feedback/{id}/attachments`: `Depends(RateLimiter(times=20, minutes=1))` для защиты дискового пространства.

---

## События аудита

События `push_audit_event(...)` в рамках данного модуля **не регистрируются** (модуль обратной связи не содержит критических изменений настроек системы или данных учетных записей).

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit (Backend) | `./backend/tests/unit/test_feedback_service.py` | Покрытие бизнес-логики `feedback_service.py` и репозитория `feedback_repo.py`: создание, обновление статусов, добавление ответов, загрузка и удаление вложений, валидация прав доступа. |
| Unit (Backend) | `./backend/tests/unit/test_feedback_schema.py` | Покрытие Pydantic-схем: тримминг сообщений, валидация и фильтрация `page_url`, проверка ограничений длины. |
| Unit (Frontend) | `./frontend/tests/unit/feedback-api.spec.ts` | Покрытие клиентских API-запросов и типизации. |

---

## Связанные документы

- `./docs/db-schema.md` — схема базы данных проекта.
- `./docs/api-contracts.md` — контракты взаимодействия API.
- `./docs/roles-matrix.md` — матрица ролей и доступов.

---

## Изменения в существующих файлах (чек-лист)

| Файл | Изменение |
|---|---|
| `./backend/app/api/__init__.py` | Подключение роутера: `app.include_router(feedback_router, prefix="/api/v1")` |
| `./backend/app/models/__init__.py` | Импорт `Feedback`, `FeedbackReply`, `FeedbackAttachment` для авто-регистрации в метаданных SQLAlchemy |
| `./backend/app/services/notifications.py` | Реализация 3 функций-хелперов пакетных уведомлений (`notify_admins_new_feedback`, `notify_user_feedback_reply`, `notify_user_feedback_status_changed`) |
| `./frontend/src/components/AppLayout.vue` | Подключение модального окна `<FeedbackModal v-if="auth.isAuthenticated && !isAuthRoute" />` |
| `./frontend/src/router.ts` | Регистрация маршрута `/my-feedback` и константы `ROUTES.MY_FEEDBACK` |
| `./frontend/src/composables/useAppMenu.ts` | Добавление пункта бокового меню "Мои обращения" с иконкой и ключом `'my-feedback'` |
| `./frontend/src/pages/AdminPage.vue` | Регистрация `FeedbackTab` во вкладке-группе `logs` |
| `./frontend/src/i18n/ru.json` | Секция переводов `feedback` |
| `./frontend/src/i18n/en.json` | Секция переводов `feedback` |
