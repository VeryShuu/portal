# ТЗ: Система обратной связи (Feedback / Обращения)

## 1. Цель

Дать пользователям возможность сообщать об ошибках и оставлять замечания прямо из
интерфейса портала. Администратор получает уведомление, может просмотреть список
обращений и ответить пользователю. Пользователь видит свои заявки и получает
уведомление об ответе.

---

## 2. Роли

| Роль | Права |
|---|---|
| `reader`, `editor` | Создать обращение, просмотреть **свои** обращения и ответы |
| `admin` | Просмотреть **все** обращения, изменить статус, ответить |

---

## 3. База данных

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
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_feedback_user_id    ON feedback(user_id);
CREATE INDEX ix_feedback_status     ON feedback(status);
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

### 3.3 Alembic-миграция

Создать один файл миграции: `migrations/versions/XXXX_add_feedback.py`.
Обе таблицы создаются в одной миграции.

---

## 4. Backend

### 4.1 Структура файлов

```
backend/app/
├── models/
│   └── feedback.py          # ORM-модели Feedback, FeedbackReply
├── schemas/
│   └── feedback.py          # Pydantic-схемы (In/Out)
└── api/
    └── feedback.py          # FastAPI-роутер
```

Роутер регистрируется в `app/api/__init__.py`:

```python
from app.api.feedback import router as feedback_router
app.include_router(feedback_router, prefix="/api/v1")
```

### 4.2 ORM-модели (`models/feedback.py`)

**`Feedback`**

| Поле | Тип SQLAlchemy |
|---|---|
| `id` | `UUID`, PK, `gen_random_uuid()` |
| `user_id` | `UUID`, FK → `users.id`, nullable, SET NULL |
| `category` | `String(30)`, NOT NULL |
| `message` | `Text`, NOT NULL |
| `page_url` | `String(2000)`, nullable |
| `status` | `String(20)`, NOT NULL, default `"open"` |
| `created_at` | `DateTime(timezone=True)`, `NOW()` |
| `updated_at` | `DateTime(timezone=True)`, `NOW()` |

Relationship: `replies` → `FeedbackReply` (lazy="selectin" или подгружается отдельным запросом).

**`FeedbackReply`**

| Поле | Тип SQLAlchemy |
|---|---|
| `id` | `UUID`, PK, `gen_random_uuid()` |
| `feedback_id` | `UUID`, FK → `feedback.id`, CASCADE |
| `admin_id` | `UUID`, FK → `users.id`, nullable, SET NULL |
| `message` | `Text`, NOT NULL |
| `created_at` | `DateTime(timezone=True)`, `NOW()` |

### 4.3 Pydantic-схемы (`schemas/feedback.py`)

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
    message:  str = Field(min_length=10, max_length=5000)
    page_url: str | None = Field(default=None, max_length=2000)

class FeedbackReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

class FeedbackStatusIn(BaseModel):
    status: FeedbackStatus

class FeedbackReplyOut(BaseModel):
    id:         uuid.UUID
    admin_id:   uuid.UUID | None
    admin_name: str | None          # full_name администратора (JOIN)
    message:    str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FeedbackOut(BaseModel):
    id:         uuid.UUID
    category:   FeedbackCategory
    message:    str
    page_url:   str | None
    status:     FeedbackStatus
    created_at: datetime
    updated_at: datetime
    replies:    list[FeedbackReplyOut] = []

    model_config = ConfigDict(from_attributes=True)

class FeedbackListOut(BaseModel):
    items: list[FeedbackOut]
    total: int
```

### 4.4 API-эндпоинты (`api/feedback.py`)

Все эндпоинты требуют авторизации (`CurrentUser`).

#### Пользовательские

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/v1/feedback` | Создать обращение |
| `GET` | `/api/v1/feedback/my` | Список своих обращений |
| `GET` | `/api/v1/feedback/my/{feedback_id}` | Одно своё обращение с ответами |

**POST `/api/v1/feedback`**
- Body: `FeedbackIn`
- Сохраняет запись в БД (`user_id` из `CurrentUser`)
- После `commit()` — вызывает `notify_admins_new_feedback(...)` (см. п. 5)
- Возвращает `FeedbackOut` (201)

**GET `/api/v1/feedback/my`**
- Query: `status` (опц. фильтр), `limit`, `offset`
- WHERE `user_id = current_user.id`
- ORDER BY `created_at DESC`
- Возвращает `FeedbackListOut`

**GET `/api/v1/feedback/my/{feedback_id}`**
- WHERE `id = feedback_id AND user_id = current_user.id`
- Подгружает `replies` с `admin_name`
- 404 если не найдено или чужое

#### Административные (`AdminDep`)

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/v1/feedback` | Все обращения (с фильтрами) |
| `GET` | `/api/v1/feedback/{feedback_id}` | Одно обращение с ответами |
| `PATCH` | `/api/v1/feedback/{feedback_id}/status` | Изменить статус |
| `POST` | `/api/v1/feedback/{feedback_id}/reply` | Ответить пользователю |

**GET `/api/v1/feedback`**
- Query: `status`, `category`, `limit`, `offset`
- ORDER BY `created_at DESC`
- Возвращает `FeedbackListOut`

**PATCH `/api/v1/feedback/{feedback_id}/status`**
- Body: `FeedbackStatusIn`
- Обновляет `status` и `updated_at`
- Возвращает `FeedbackOut`

**POST `/api/v1/feedback/{feedback_id}/reply`**
- Body: `FeedbackReplyIn`
- Создаёт `FeedbackReply` (`admin_id` из текущего пользователя)
- Обновляет `updated_at` на `feedback`
- После `commit()` — вызывает `notify_user_feedback_reply(...)` (см. п. 5)
- Возвращает `FeedbackReplyOut` (201)

---

## 5. Уведомления (`services/notifications.py`)

Добавить две функции-хелпера по образцу существующих (`notify_suggestion_reviewed`,
`notify_users_news_published`).

### 5.1 `notify_admins_new_feedback`

```python
async def notify_admins_new_feedback(
    db: AsyncSession,
    redis: Redis,
    *,
    feedback_id: uuid.UUID,
    author_name: str,
    category: str,
) -> None:
```

- Выбирает всех пользователей с `role = 'admin'` и `notify_inapp = True`
- Для каждого создаёт уведомление:
  - `type`: `"feedback_new"`
  - `title`: `f"Новое обращение от {author_name}"`
  - `body`: человекочитаемая категория (`bug` → "Ошибка" и т.д.)
  - `link`: `f"/admin?tab=feedback"` — прямая ссылка на таб в админке
- Пакетная рассылка (batch 500, как `notify_users_news_published`)

### 5.2 `notify_user_feedback_reply`

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

- Проверяет `notify_inapp = True` у пользователя
- Создаёт уведомление:
  - `type`: `"feedback_reply"`
  - `title`: `f"Администратор ответил на ваше обращение"`
  - `body`: `f"Ответ от {admin_name}"`
  - `link`: `f"/my-feedback/{feedback_id}"`

---

## 6. Frontend

### 6.1 Структура файлов

```
frontend/src/
├── api/
│   └── feedback.ts                   # API-функции
├── components/
│   └── FeedbackModal.vue             # Плавающая кнопка + модальное окно
├── pages/
│   ├── MyFeedbackPage.vue            # Страница "Мои обращения"
│   └── admin/tabs/
│       └── FeedbackTab.vue           # Таб в админке
└── i18n/
    ├── ru.json                       # + ключи секции "feedback"
    └── en.json                       # + ключи секции "feedback"
```

### 6.2 `api/feedback.ts`

```typescript
export interface FeedbackIn {
  category: 'bug' | 'suggestion' | 'other'
  message: string
  page_url?: string
}

export interface FeedbackReplyIn {
  message: string
}

export interface FeedbackReplyOut {
  id: string
  admin_id: string | null
  admin_name: string | null
  message: string
  created_at: string
}

export interface FeedbackOut {
  id: string
  category: 'bug' | 'suggestion' | 'other'
  message: string
  page_url: string | null
  status: 'open' | 'in_progress' | 'closed'
  created_at: string
  updated_at: string
  replies: FeedbackReplyOut[]
}

export interface FeedbackListOut {
  items: FeedbackOut[]
  total: number
}

// Пользовательские
export const createFeedback = (data: FeedbackIn) =>
  $fetch<FeedbackOut>('/api/v1/feedback', { method: 'POST', body: data })

export const getMyFeedback = (params?: { status?: string; limit?: number; offset?: number }) =>
  $fetch<FeedbackListOut>('/api/v1/feedback/my', { params })

export const getMyFeedbackById = (id: string) =>
  $fetch<FeedbackOut>(`/api/v1/feedback/my/${id}`)

// Административные
export const getAllFeedback = (params?: { status?: string; category?: string; limit?: number; offset?: number }) =>
  $fetch<FeedbackListOut>('/api/v1/feedback', { params })

export const getFeedbackById = (id: string) =>
  $fetch<FeedbackOut>(`/api/v1/feedback/${id}`)

export const replyToFeedback = (id: string, data: FeedbackReplyIn) =>
  $fetch<FeedbackReplyOut>(`/api/v1/feedback/${id}/reply`, { method: 'POST', body: data })

export const updateFeedbackStatus = (id: string, status: string) =>
  $fetch<FeedbackOut>(`/api/v1/feedback/${id}/status`, { method: 'PATCH', body: { status } })
```

### 6.3 `FeedbackModal.vue`

Монтируется в `AppLayout.vue` рядом с `<GlobalSearch>` и `<OnboardingTour>`.

**Внешний вид:**
- Плавающая кнопка в правом нижнем углу (fixed, z-index выше контента).
  Иконка: сообщение/вопрос. Подпись: "Обратная связь".
- По клику открывается `NModal`.

**Форма внутри модального окна:**
- Заголовок: "Сообщить об ошибке или оставить замечание"
- `NSelect` — Категория:
  - `bug` → "Ошибка / не работает"
  - `suggestion` → "Предложение / пожелание"
  - `other` → "Другое"
- `NInput` (textarea, rows=5) — Описание (min 10, max 5000 символов)
- Флажок/скрытое поле: `page_url` — автоматически передаётся текущий `window.location.href`
- Кнопки: "Отправить" (primary) / "Отмена"

**Поведение:**
- После успешной отправки: `NMessage` ("Спасибо, обращение принято!"), форма сбрасывается, модал закрывается.
- При ошибке: показывает сообщение через `parseApiError`.
- Состояние загрузки: кнопка "Отправить" в `loading`.

### 6.4 `MyFeedbackPage.vue` (`/my-feedback`)

**Назначение:** Список всех обращений текущего пользователя с возможностью просмотреть ответы.

**Структура:**
- Заголовок страницы: "Мои обращения"
- Фильтр по статусу (tabs или select): Все / Открытые / В работе / Закрытые
- Список обращений в виде карточек (`NCard`):
  - Категория (тег-бейдж), дата, статус (цветной бейдж)
  - Первые 200 символов сообщения (с многоточием)
  - Количество ответов
  - Кликабельная карточка → раскрывает детали (expand inline или отдельная секция)
- В раскрытой детали:
  - Полный текст обращения
  - Раздел "Ответы администратора" — список ответов с именем и датой
  - Если ответов нет: "Ответ ещё не получен"
- Пагинация (limit 20)
- Пустое состояние: `EmptyState` с текстом "У вас ещё нет обращений"

**Навигация:** кнопка/пункт "Мои обращения" добавляется в боковое меню (`useAppMenu.ts`)
с иконкой и ссылкой на `/my-feedback`.

### 6.5 `FeedbackTab.vue` (таб в Admin-панели)

**Доступ:** только `admin`.

**Структура:**
- Фильтры вверху: статус (all/open/in_progress/closed), категория (all/bug/suggestion/other)
- Таблица (`NDataTable`) с колонками:
  - Дата, Категория, Пользователь (ФИО), Статус, Сообщение (первые 100 символов)
- Клик по строке открывает `NModal` с деталями:
  - Полное сообщение
  - URL страницы (если есть)
  - Выпадающий список смены статуса
  - Список ответов (с именем и датой)
  - Форма ответа: textarea + кнопка "Ответить"

**Добавить новый таб в `AdminPage.vue`:**
- Имя: "Обращения"
- Путь параметра `?tab=feedback`

---

## 7. Маршрутизация (`router.ts`)

Добавить маршрут:

```typescript
{
  path: '/my-feedback',
  name: 'my-feedback',
  component: () => import('./pages/MyFeedbackPage.vue'),
  meta: { requiresAuth: true },
}
```

---

## 8. Локализация (`i18n/ru.json`, `i18n/en.json`)

Добавить секцию `"feedback"` в оба файла:

**ru.json:**
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
    "feedbackReply": "Администратор ответил на ваше обращение"
  }
}
```

**en.json** — аналогичная структура на английском.

---

## 9. Порядок реализации

1. **Миграция БД** — создать `feedback` + `feedback_replies`
2. **Backend models** — `models/feedback.py`
3. **Backend schemas** — `schemas/feedback.py`
4. **Backend API** — `api/feedback.py`, зарегистрировать роутер
5. **Notification helpers** — дополнить `services/notifications.py`
6. **Frontend API** — `api/feedback.ts`
7. **FeedbackModal.vue** — компонент с плавающей кнопкой
8. **AppLayout.vue** — подключить `FeedbackModal`
9. **MyFeedbackPage.vue** — страница "Мои обращения"
10. **router.ts** — маршрут `/my-feedback`
11. **useAppMenu.ts** — пункт меню "Мои обращения"
12. **FeedbackTab.vue** — таб в админке
13. **AdminPage.vue** — зарегистрировать таб
14. **i18n** — добавить ключи в `ru.json` и `en.json`

---

## 10. Нотификации: тип → текст

| `type` | Кому | `title` | `link` |
|---|---|---|---|
| `feedback_new` | Всем `admin` | "Новое обращение от {ФИО}" | `/admin?tab=feedback` |
| `feedback_reply` | Автору обращения | "Администратор ответил на ваше обращение" | `/my-feedback/{id}` |

---

## 11. Ограничения и валидация

| Поле | Ограничение |
|---|---|
| `category` | Одно из: `bug`, `suggestion`, `other` |
| `message` | min 10, max 5000 символов |
| `page_url` | max 2000 символов, опциональное |
| `reply.message` | min 1, max 5000 символов |
| Статус | Одно из: `open`, `in_progress`, `closed` |

Rate limiting на `POST /api/v1/feedback`: 5 запросов в минуту на пользователя
(по аналогии с существующими лимитами через `FastAPILimiter`).

---

## 12. Что не входит в scope

- Email-уведомления (отдельная задача при необходимости)
- Вложения / скриншоты к обращению
- Публичный статус-трекер
- SLA / дедлайны
