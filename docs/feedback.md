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
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_feedback_category CHECK (category IN ('bug','suggestion','other')),
    CONSTRAINT ck_feedback_status   CHECK (status   IN ('open','in_progress','closed'))
);

CREATE INDEX ix_feedback_user_id    ON feedback(user_id);
CREATE INDEX ix_feedback_status     ON feedback(status);
-- DESC-индекс для сортировки списков по времени (PostgreSQL).
-- В Alembic создавать как: op.execute("CREATE INDEX ix_feedback_created_at ON feedback (created_at DESC)")
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
| `created_at` | `DateTime(timezone=True)`, `server_default=text("NOW()")` |
| `updated_at` | `DateTime(timezone=True)`, `server_default=text("NOW()")`, `onupdate=func.now()` |

> **Важно:** `updated_at` обязательно с `onupdate=func.now()` — иначе обновление статуса/добавление reply
> не сдвинет поле, и сортировка/фильтрация по «последней активности» не будет работать.
> Дополнительно при создании reply следует явно проставлять `feedback.updated_at = func.now()`
> (на случай если ORM не триггерит `onupdate` без изменения собственных полей).

Relationship: `replies` → `FeedbackReply` (`lazy="selectin"`, `order_by="FeedbackReply.created_at"`,
`cascade="all, delete-orphan"`).

Relationship `author` → `User` (через `user_id`, `lazy="joined"` либо явный JOIN — нужен для админских
ответов с полем `author_name`).

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
    """Схема для пользовательских эндпоинтов (`/feedback/my*`)."""
    id:         uuid.UUID
    category:   FeedbackCategory
    message:    str
    page_url:   str | None
    status:     FeedbackStatus
    created_at: datetime
    updated_at: datetime
    replies:    list[FeedbackReplyOut] = []

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

> **Безопасность контента:** поля `message`, `page_url`, `reply.message` рендерятся фронтом
> **только как plain text** (никаких Markdown/HTML). Дополнительная санитизация на бэке не требуется,
> но `page_url` валидируется отдельно (см. п. 11).

### 4.4 API-эндпоинты (`api/feedback.py`)

Все эндпоинты требуют авторизации (`CurrentUser`).

> **Порядок регистрации маршрутов критичен.** FastAPI матчит роуты по порядку объявления, поэтому
> в `api/feedback.py` сначала объявляются специфичные маршруты `/feedback/my` и `/feedback/my/{id}`,
> и только затем — административные `/feedback` и `/feedback/{id}`. Иначе путь `/feedback/my`
> будет перехвачен админским `/feedback/{feedback_id}` и вернёт 422 (UUID parsing).
>
> Рекомендуемый порядок объявления:
> 1. `POST /feedback`
> 2. `GET  /feedback/my`
> 3. `GET  /feedback/my/{feedback_id}`
> 4. `GET  /feedback`              (admin)
> 5. `GET  /feedback/{feedback_id}` (admin)
> 6. `PATCH /feedback/{feedback_id}/status`
> 7. `POST /feedback/{feedback_id}/reply`

#### Пользовательские

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/v1/feedback` | Создать обращение |
| `GET` | `/api/v1/feedback/my` | Список своих обращений |
| `GET` | `/api/v1/feedback/my/{feedback_id}` | Одно своё обращение с ответами |

**POST `/api/v1/feedback`**
- Body: `FeedbackIn`
- Rate limit: `Depends(RateLimiter(times=5, minutes=1))` (по `real_ip_identifier` — стандарт проекта)
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
- Query: `status`, `category`, `q` (опц., поиск по `message` через `ILIKE`), `limit` (def 20, max 100), `offset` (def 0)
- ORDER BY `created_at DESC`
- `total` считается отдельным `SELECT COUNT(*)`-запросом с теми же фильтрами (паттерн как в `api/news.py`)
- LEFT JOIN `users` для подгрузки `author_name`/`author_email` (использовать `selectinload(Feedback.author)` либо явный JOIN)
- Возвращает `FeedbackAdminListOut`

**GET `/api/v1/feedback/{feedback_id}`** (admin)
- Возвращает `FeedbackAdminOut` со всеми ответами (`replies` с `admin_name`)
- 404 если не найдено

**PATCH `/api/v1/feedback/{feedback_id}/status`**
- Body: `FeedbackStatusIn`
- Валидирует переход по машине состояний (см. п. 4.5)
- Обновляет `status` и `updated_at = func.now()`
- Если новый статус `closed` (и был не `closed`) — вызывает `notify_user_feedback_status_changed(...)`
- Возвращает `FeedbackAdminOut`

**POST `/api/v1/feedback/{feedback_id}/reply`**
- Body: `FeedbackReplyIn`
- Создаёт `FeedbackReply` (`admin_id` из текущего пользователя)
- Явно устанавливает `feedback.updated_at = func.now()`
- **Авто-переход статуса:** если `feedback.status == "open"` → переключить в `"in_progress"`
- После `commit()` — вызывает `notify_user_feedback_reply(...)` (см. п. 5)
- Возвращает `FeedbackReplyOut` (201) с заполненным `admin_name`

#### 4.5 Машина состояний

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

- **Авто-переходы:** первый reply от админа автоматически переводит `open → in_progress`.
- **Ручные переходы:** админ через PATCH может выставить любой из трёх статусов
  (включая повторное открытие закрытого тикета). Дополнительных ограничений нет.
- **Уведомления автору:** только при `→ closed`. Reply шлёт собственное уведомление и
  смену статуса не дублирует.

---

## 5. Уведомления (`services/notifications.py`)

Добавить **три** функции-хелпера по образцу существующих (`notify_suggestion_reviewed`,
`notify_users_news_published`).

> **Паттерн пакетной рассылки:** в `notify_users_news_published` каждое уведомление
> создаётся через `create_notification(...)` в цикле, ПОСЛЕ чего выполняется один
> `db.commit()`, и затем отдельным проходом запускаются `_publish` callbacks в Redis.
> Использовать ровно эту схему — она гарантирует консистентность БД и стрима.

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
    > Для работы deep-link `?tab=feedback` необходимо добавить в `AdminPage.vue` синхронизацию
    > `activeTab` с query-параметром `tab` (см. п. 6.6).
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
  - `link`: `f"/my-feedback?open={feedback_id}"`

### 5.3 `notify_user_feedback_status_changed`

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

- Вызывается **только при переходе в `closed`** (см. п. 4.5)
- Проверяет `notify_inapp = True` у пользователя
- Создаёт уведомление:
  - `type`: `"feedback_closed"`
  - `title`: `"Ваше обращение закрыто"`
  - `body`: `None`
  - `link`: `f"/my-feedback?open={feedback_id}"`

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

**Доступность:**
- Плавающая кнопка отображается **только авторизованным пользователям** (проверка
  через `useAuthStore().isAuthenticated`). Для гостей фича скрыта.
- На страницах публичной авторизации (`LoginPage`, `AuthCallbackPage`, `AuthErrorPage`,
  `AuthRedirectStub`) кнопка не показывается даже для авторизованных (по `route.name`).

**Внешний вид:**
- Плавающая кнопка в правом нижнем углу (fixed, z-index выше контента, но ниже модальных окон).
  Иконка: сообщение/вопрос. Подпись: "Обратная связь".
- На мобильных (≤768px) — только иконка без подписи.
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

**Deep-link / автораскрытие:**
- Маршрут единственный: `/my-feedback`. Идентификатор обращения передаётся через query —
  `/my-feedback?open={feedback_id}` (используется в нотификациях `feedback_reply`/`feedback_closed`).
- При наличии `?open=` страница автоматически:
  1. Подгружает обращение через `getMyFeedbackById(id)` (если его нет на текущей странице пагинации).
  2. Скроллит к карточке и раскрывает её детали.
  3. Если ID не найден / чужой — `NMessage.error("Обращение не найдено")` и query очищается.

**Удалённый автор/админ:**
- Если `admin_id IS NULL` или `admin_name === null` в reply — показывать «Удалённый администратор».
- Аналогично в админке для `author_name`.

**Навигация:** кнопка/пункт "Мои обращения" добавляется в боковое меню (`useAppMenu.ts`)
с иконкой и ссылкой на `/my-feedback`. Активный ключ — `'my-feedback'`,
матчится по `path.startsWith(ROUTES.MY_FEEDBACK)`. Соответствующий ключ
добавляется в `ROUTES` (`router.ts`).

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
- Имя таба: `feedback`
- Лейбл: `t('feedback.adminTab')` → "Обращения"
- Подключается через `defineAsyncComponent` (паттерн как у остальных табов).

### 6.6 Синхронизация табов админки с URL

В текущем `AdminPage.vue` `activeTab = ref('users')` без синхронизации с URL — это значит,
что нотификация со ссылкой `/admin?tab=feedback` НЕ откроет нужный таб автоматически.
Нужно добавить:

```typescript
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const VALID_TABS = ['users','email','system','keycloak','user-attributes',
                    'modules','analytics','audit','monitoring','feedback'] as const

const activeTab = ref(
  (typeof route.query.tab === 'string' && (VALID_TABS as readonly string[]).includes(route.query.tab))
    ? route.query.tab as string
    : 'users'
)

watch(activeTab, (val) => {
  router.replace({ query: { ...route.query, tab: val } })
})
watch(() => route.query.tab, (val) => {
  if (typeof val === 'string' && val !== activeTab.value && (VALID_TABS as readonly string[]).includes(val)) {
    activeTab.value = val
  }
})
```

Этот блок не относится напрямую к Feedback, но **обязателен** для работы deep-link
из нотификации `feedback_new`.

---

## 7. Маршрутизация (`router.ts`)

Добавить константу маршрута и сам маршрут:

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

Deep-link используется через query: `/my-feedback?open={feedback_id}`. Отдельный
маршрут `/my-feedback/:id` **не вводится** — это упрощает страницу (один компонент,
одно состояние) и согласуется с принципом single-list-with-detail-expand.

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
    "feedbackReply": "Администратор ответил на ваше обращение",
    "feedbackClosed": "Ваше обращение закрыто"
  },
  "deletedUser": "Удалённый пользователь",
  "deletedAdmin": "Удалённый администратор",
  "notFound": "Обращение не найдено"
}
```

**en.json:**
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

1. **Миграция БД** — создать `feedback` + `feedback_replies` (один файл `migrations/versions/XXX_add_feedback.py`)
2. **Backend models** — `models/feedback.py` + регистрация в `models/__init__.py`
3. **Backend schemas** — `schemas/feedback.py`
4. **Notification helpers** — дополнить `services/notifications.py` тремя функциями (см. п. 5)
5. **Backend API** — `api/feedback.py`, зарегистрировать роутер в `api/__init__.py`
   - Соблюсти порядок маршрутов (см. п. 4.4)
   - Подключить `RateLimiter` на POST `/feedback`
6. **Backend tests** — `tests/test_feedback.py`:
   - Создание обращения авторизованным/неавторизованным
   - Доступ к чужому обращению (404 для `/my/{id}`, 200 для админа)
   - Reply от админа: проверка авто-перехода `open → in_progress` и нотификации
   - PATCH status: переход в `closed` шлёт `notify_user_feedback_status_changed`
   - Rate limit: 6-й запрос за минуту → 429
   - 422 при невалидной категории/статусе/слишком короткому message
7. **Frontend API** — `api/feedback.ts`
8. **FeedbackModal.vue** — компонент с плавающей кнопкой
9. **AppLayout.vue** — подключить `FeedbackModal` (с условным рендером по auth)
10. **MyFeedbackPage.vue** — страница "Мои обращения" с поддержкой `?open=`
11. **router.ts** — маршрут `/my-feedback` + ключ `MY_FEEDBACK` в `ROUTES`
12. **useAppMenu.ts** — пункт меню "Мои обращения"
13. **AdminPage.vue** — добавить URL-sync для табов (см. п. 6.6) + зарегистрировать `FeedbackTab`
14. **FeedbackTab.vue** — таб в админке
15. **i18n** — добавить ключи в `ru.json` и `en.json` (полный JSON в п. 8)
16. **Manual smoke test** — пройти end-to-end: создать обращение → получить нотификацию админу →
    ответить → автор получает нотификацию → закрыть → автор получает нотификацию о закрытии

---

## 10. Нотификации: тип → текст

| `type` | Кому | `title` | `link` |
|---|---|---|---|
| `feedback_new` | Всем `admin` с `notify_inapp=true` | "Новое обращение от {ФИО}" | `/admin?tab=feedback` |
| `feedback_reply` | Автору обращения (если `notify_inapp=true`) | "Администратор ответил на ваше обращение" | `/my-feedback?open={id}` |
| `feedback_closed` | Автору обращения (если `notify_inapp=true`) | "Ваше обращение закрыто" | `/my-feedback?open={id}` |

---

## 11. Ограничения и валидация

| Поле | Ограничение |
|---|---|
| `category` | Одно из: `bug`, `suggestion`, `other` |
| `message` | min 10, max 5000 символов; обрезается `.strip()` перед валидацией |
| `page_url` | max 2000 символов, опциональное; см. валидацию ниже |
| `reply.message` | min 1, max 5000 символов; `.strip()` |
| Статус | Одно из: `open`, `in_progress`, `closed` |

**Валидация `page_url`** (Pydantic `field_validator`):
- Пустая строка → `None`.
- Допускаются только:
  - Относительные пути: начинаются с `/` и не с `//` (отсекает protocol-relative URLs).
  - Абсолютные URL со схемой `https://` (для будущей multi-domain поддержки).
- Запрещены: `javascript:`, `data:`, `vbscript:`, `file:`, `ftp:` и т.п.
- При нарушении — `ValueError("Invalid page_url")` → 422.

**Rate limiting:**
- `POST /api/v1/feedback`: `Depends(RateLimiter(times=5, minutes=1))` — по `real_ip_identifier`
  (стандарт проекта, см. `app/core/limiter.py`).
- `POST /api/v1/feedback/{id}/reply`: `Depends(RateLimiter(times=30, minutes=1))` —
  для админа, защита от случайных повторных кликов.

---

## 12. Что не входит в scope

- Email-уведомления (отдельная задача при необходимости)
- Вложения / скриншоты к обращению
- Публичный статус-трекер
- SLA / дедлайны
- Бейдж непрочитанных ответов в пункте меню «Мои обращения» (можно добавить отдельной задачей,
  потребует поля `last_read_at` на `feedback` или сравнения с `is_read` нотификаций)
- Markdown / rich text в сообщениях — рендер только plain text
- Возможность пользователя редактировать/удалять своё обращение
- Внутренние комментарии админов (видимые только админам)
- Назначение конкретного админа на обращение (assignment)
- Категоризация / метки сверх трёх базовых категорий

---

## 13. Изменения в существующих файлах (чек-лист)

| Файл | Изменение |
|---|---|
| `backend/app/api/__init__.py` | `app.include_router(feedback_router, prefix="/api/v1")` |
| `backend/app/models/__init__.py` | Импорт `Feedback`, `FeedbackReply` для регистрации в `Base.metadata` |
| `backend/app/services/notifications.py` | + 3 функции (см. п. 5) |
| `frontend/src/components/AppLayout.vue` | `<FeedbackModal v-if="auth.isAuthenticated && !isAuthRoute" />` |
| `frontend/src/router.ts` | Маршрут `/my-feedback` + `ROUTES.MY_FEEDBACK` |
| `frontend/src/composables/useAppMenu.ts` | Пункт меню «Мои обращения», ключ `'my-feedback'` |
| `frontend/src/pages/AdminPage.vue` | URL-sync табов (см. п. 6.6) + регистрация `FeedbackTab` |
| `frontend/src/i18n/ru.json` | Секция `feedback` |
| `frontend/src/i18n/en.json` | Секция `feedback` |
