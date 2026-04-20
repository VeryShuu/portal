# API Contracts

> Корпоративный интранет-портал
> Base URL: `/api/v1/`
> Auth: HTTPOnly cookie `access_token` (Keycloak JWT)
> Format: JSON, UTF-8
> Последнее обновление: апрель 2026

---

## Соглашения

### Пагинация (обязательна везде)

**Запрос:**
```
GET /api/v1/users?limit=20&offset=40
```

**Ответ:**
```json
{
  "items": [...],
  "total": 300,
  "limit": 20,
  "offset": 40
}
```

| Параметр | Default | Max |
|----------|---------|-----|
| `limit` | 20 | 100 |
| `offset` | 0 | — |

### Idempotency (критичные POST)

```
POST /api/v1/news
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

Применяется к: `POST /news`, `POST /kb/articles`, `POST /files/upload`, `POST /notifications/send`.

Ответ middleware при повторе: `{"id": "uuid"}` + оригинальный status_code.

Каждый endpoint в whitelist **обязан** выставлять `X-Resource-Id: {uuid}` в ответе.

### Soft delete

Удалённые записи имеют `deleted_at != NULL`. Обычные запросы их не возвращают. Admin видит через `?include_deleted=true`.

### Версионирование

Текущая версия: `v1`. Breaking changes → `v2`. `v1` поддерживается ≥ 6 месяцев после выхода `v2`.

### Роли

| Роль | Обозначение |
|------|------------|
| Все авторизованные | `[reader+]` |
| Редакторы и выше | `[editor+]` |
| Только администраторы | `[admin]` |

### Rate limits (per user, Redis)

| Endpoint | Лимит |
|----------|-------|
| `POST /auth/login` | 5 / мин / IP |
| `GET /search` | 30 / мин / user |
| `POST /files/upload` | 10 / мин / user |
| Экспорт PDF/DOCX | 5 / мин / user |
| Остальные | 300 / мин / user |

---

## Аутентификация

### GET /api/v1/auth/login
Редирект на Keycloak. Query param `?next=/some/path` для redirect после логина.
```
→ 302 Location: https://auth.company.local/realms/corporate/protocol/openid-connect/auth?...
```

### GET /api/v1/auth/callback
OIDC callback. Устанавливает HTTPOnly + Secure + SameSite=Strict cookies.
```
→ 302 Location: /  (или ?next= из state)
   Set-Cookie: access_token=...; HttpOnly; Secure; SameSite=Strict; Path=/
```

### POST /api/v1/auth/logout
Ревокация токенов, очистка cookies, SLO через Keycloak front-channel.
```json
→ 200 {}
```

### GET /api/v1/auth/me `[reader+]`
```json
→ 200 {
  "id": "uuid",
  "keycloak_id": "uuid",
  "email": "ivan@company.local",
  "full_name": "Иван Петров",
  "department": "IT",
  "position": "Backend Developer",
  "phone": "+7 999 123-45-67",
  "role": "editor",
  "presence_status": "office",
  "avatar_url": "/static/avatars/uuid.jpg",
  "notify_email": true,
  "notify_inapp": true,
  "lang": "ru"
}
```

---

## Пользователи

### GET /api/v1/users `[reader+]`
Список сотрудников.
```
?q=иван&department=IT&limit=20&offset=0
```
```json
→ 200 {
  "items": [{ "id": "uuid", "full_name": "...", "department": "...", "position": "...", "avatar_url": "...", "presence_status": "office" }],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### GET /api/v1/users/{id} `[reader+]`
```json
→ 200 { /* полный профиль, аналог /auth/me */ }
→ 404 { "detail": "User not found" }
```

### PATCH /api/v1/users/me/profile `[reader+]`
Обновление аватара и статуса присутствия.
```json
← { "presence_status": "remote" }
→ 200 { /* обновлённый профиль */ }
```
Загрузка аватара: `POST /api/v1/users/me/avatar` (multipart/form-data, max 2 МБ, JPEG/PNG/WebP).

### PATCH /api/v1/users/me/preferences `[reader+]`
```json
← { "notify_email": false, "notify_inapp": true, "lang": "en" }
→ 200 {}
```

### POST /api/v1/admin/users/sync `[admin]`
Ручная синхронизация всех пользователей из Keycloak (вызывает Keycloak Admin API → обновляет `users`).
```json
→ 202 { "task_id": "uuid", "message": "Синхронизация запущена в фоне" }
```

### PATCH /api/v1/admin/users/{id}/role `[admin]`
Изменение роли пользователя. Вступает в силу при следующем обновлении токена (≤ 15 мин).
```json
← { "role": "editor" }
→ 200 { "id": "uuid", "email": "ivan@company.local", "full_name": "Иван Петров", "role": "editor" }
→ 400 { "detail": "Недопустимая роль. Допустимые значения: reader, editor, admin" }
→ 404 { "detail": "User not found" }
```

### PATCH /api/v1/users/me/preferences `[reader+]`
Обновление персональных настроек (скрытые ярлыки и др.). Хранится в `users.preferences JSONB`.
```json
← { "hidden_link_ids": ["uuid1", "uuid2"] }
→ 200 { "hidden_link_ids": ["uuid1", "uuid2"] }
```

---

## База знаний (KB)

### GET /api/v1/kb/sections `[reader+]`
Дерево разделов.
```json
→ 200 {
  "items": [{
    "id": "uuid",
    "title": "Onboarding",
    "slug": "onboarding",
    "parent_id": null,
    "order_index": 0,
    "children": [{ "id": "uuid", "title": "Первый день", ... }]
  }]
}
```

### POST /api/v1/kb/sections `[editor+]`
```json
← { "title": "Новый раздел", "parent_id": "uuid|null", "description": "...", "order_index": 0 }
→ 201 { "id": "uuid", ... }
   X-Resource-Id: uuid
```

### DELETE /api/v1/kb/sections/{id} `[admin]`
```
?force=true  — удаление с дочерними разделами и статьями (логируется в audit)
```
```
→ 204  (успешно)
→ 409  { "detail": "Раздел содержит дочерние элементы. Используйте ?force=true" }
```

---

### GET /api/v1/kb/articles `[reader+]`
```
?section_id=uuid&tag=python&status=published&q=docker&limit=20&offset=0
```
```json
→ 200 {
  "items": [{
    "id": "uuid",
    "title": "...",
    "section_id": "uuid",
    "status": "published",
    "created_by": { "id": "uuid", "full_name": "..." },
    "published_at": "2026-04-01T10:00:00Z",
    "view_count": 42,
    "tags": ["docker", "devops"],
    "version": 3
  }],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

### POST /api/v1/kb/articles `[editor+]`
```json
← {
  "section_id": "uuid",
  "title": "Заголовок",
  "body": "# Markdown content",
  "status": "draft",
  "tags": ["tag1"]
}
→ 201 { "id": "uuid", "version": 1, ... }
   X-Resource-Id: uuid
   Idempotency-Key обязателен
```

### GET /api/v1/kb/articles/{id} `[reader+]`
Возвращает статью + инкрементирует `view_count` (дедупликация 1/час/user через Redis).
```json
→ 200 {
  "id": "uuid",
  "title": "...",
  "body": "# Markdown...",
  "section_id": "uuid",
  "breadcrumbs": [{ "id": "uuid", "title": "Root" }, { "id": "uuid", "title": "Sub" }],
  "tags": [...],
  "version": 3,
  "view_count": 42,
  "created_by": { ... },
  "updated_by": { ... },
  "published_at": "...",
  "updated_at": "..."
}
→ 404 / 403
```

### PUT /api/v1/kb/articles/{id} `[editor+]`
```json
← {
  "title": "Обновлённый заголовок",
  "body": "# Новый контент",
  "version": 3,            ← обязателен для оптимистичной блокировки
  "change_comment": "Исправлена опечатка"
}
→ 200 { "version": 4, ... }
→ 409 {
    "detail": "Статья изменена другим пользователем",
    "current_version": 4,
    "your_version": 3
  }
```

### PUT /api/v1/kb/articles/{id}/draft `[editor+]`
Автосохранение черновика (идемпотентен, Idempotency-Key не нужен).
```json
← { "draft_title": "...", "draft_body": "# ..." }
→ 200 { "draft_saved_at": "2026-04-19T14:32:00Z" }
```

### DELETE /api/v1/kb/articles/{id} `[admin]`
Soft delete (`deleted_at = NOW()`).
```
→ 204
→ 404
```

### POST /api/v1/kb/articles/{id}/restore `[admin]`
Восстановление soft-deleted статьи.
```
→ 200 { "id": "uuid", "deleted_at": null, ... }
```

### GET /api/v1/kb/articles/{id}/versions `[reader+]`
```
?limit=20&offset=0
```
```json
→ 200 {
  "items": [{ "version_number": 3, "changed_by": {...}, "change_comment": "...", "created_at": "..." }],
  "total": 5, ...
}
```

### POST /api/v1/kb/articles/{id}/versions/{n}/restore `[editor+]`
Откат к версии N (создаёт новую версию N+1 с телом из N).
```json
→ 200 { "version": 4, ... }
```

### POST /api/v1/kb/articles/{id}/export/pdf `[reader+]`
Rate limit: 5/мин/user.
```
→ 200 Content-Type: application/pdf
      Content-Disposition: attachment; filename="article.pdf"
```

### POST /api/v1/kb/articles/{id}/export/docx `[reader+]`
Rate limit: 5/мин/user.
```
→ 200 Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
      Content-Disposition: attachment; filename="article.docx"
```

### GET /api/v1/kb/articles/{id}/comments `[reader+]`
```
?limit=20&offset=0
```
```json
→ 200 {
  "items": [{ "id": "uuid", "author": {...}, "body": "...", "created_at": "...", "updated_at": "..." }],
  ...
}
```

### POST /api/v1/kb/articles/{id}/comments `[reader+]`
```json
← { "body": "Текст комментария" }
→ 201 { "id": "uuid", ... }
```

### POST /api/v1/kb/articles/{id}/suggest `[reader+]`
«Предложить правку» — создаёт черновик статьи с body пользователя, уведомляет редактора.
```json
← { "body": "# Исправленный Markdown...", "comment": "Исправил опечатки" }
→ 202 { "suggestion_id": "uuid", "message": "Правка отправлена на рассмотрение" }
```

---

## Новости

### GET /api/v1/news `[reader+]`
Автоматический таргетинг по `department` и `role` из JWT.
```
?status=published&category=it&is_pinned=true&limit=20&offset=0
```
```json
→ 200 {
  "items": [{ "id": "uuid", "title": "...", "category": "it", "is_pinned": false, "publish_at": "...", "view_count": 10, "created_by": {...} }],
  "total": 5, ...
}
```

### POST /api/v1/news `[editor+]`
```json
← {
  "title": "Заголовок новости",
  "body": "# Markdown...",
  "category": "company",
  "status": "draft",
  "publish_at": "2026-05-01T09:00:00Z",
  "archive_at": "2026-06-01T00:00:00Z",
  "target_departments": ["IT", "HR"],
  "target_roles": null
}
→ 201 { "id": "uuid", ... }
   X-Resource-Id: uuid
   Idempotency-Key обязателен
```

### GET /api/v1/news/{id} `[reader+]`
```json
→ 200 { /* полная новость + view_count инкремент */ }
```

### PUT /api/v1/news/{id} `[editor+]`
```json
← { "title": "...", "body": "...", "change_comment": "..." }
→ 200 { ... }
```

### PUT /api/v1/news/{id}/draft `[editor+]`
Автосохранение черновика.
```json
← { "draft_title": "...", "draft_body": "..." }
→ 200 { "draft_saved_at": "..." }
```

### DELETE /api/v1/news/{id} `[admin]`
Soft delete.
```
→ 204
```

### GET /api/v1/news/{id}/versions `[editor+]`
```
?limit=20&offset=0  → 200 { "items": [...], ... }
```

---

## Файлы (Nextcloud proxy)

Все операции выполняются от имени пользователя через его Bearer JWT → Nextcloud ACL.

### GET /api/v1/files `[reader+]`
```
?path=/MyFolder&limit=20&offset=0
```
```json
→ 200 {
  "items": [{
    "name": "document.docx",
    "path": "/MyFolder/document.docx",
    "type": "file",
    "size": 204800,
    "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "modified_at": "2026-04-01T10:00:00Z",
    "etag": "abc123"
  }],
  "total": 5, ...
}
→ 403  Нет доступа к папке (ACL Nextcloud)
→ 404  Папка не найдена
```

### GET /api/v1/files/{path:path}/open `[reader+]`
Открыть файл. PDF отображается inline; Office-файлы → URL Nextcloud/Collabora (новая вкладка).
```json
→ 200 {
  "type": "inline",            // или "nextcloud_tab"
  "url": "https://nextcloud.company.local/apps/files/?dir=/...",
  "mime": "application/pdf"
}
```

### GET /api/v1/files/{path:path}/download `[reader+]`
Скачивание через WebDAV streaming. PDF открывается как `Content-Disposition: inline`.
```
→ 200 Content-Type: <mime>
      Content-Disposition: inline / attachment
      (streaming response, таймаут: None)
→ 403 / 404
```

### POST /api/v1/files/upload `[reader+]`
Загрузка файла в Nextcloud (multipart/form-data).
Rate limit: 10/мин/user. Максимальный размер файла: `MAX_UPLOAD_SIZE_MB` из `.env` (по умолчанию 100 МБ).
Применяется двойным ограничением: Nginx `client_max_body_size` + FastAPI middleware (413 если превышено).
```
← multipart/form-data: file + target_path=/MyFolder/
→ 201 { "path": "/MyFolder/document.docx", "size": 204800 }
   X-Resource-Id: /MyFolder/document.docx
   Idempotency-Key обязателен
→ 403  Нет прав на запись
→ 413  Файл превышает MAX_UPLOAD_SIZE_MB
```

### POST /api/v1/files/{path:path}/share `[reader+]`
Создать sharing-ссылку через Nextcloud OCS API.
```json
← {
  "share_type": 3,              // 3 = public link
  "permissions": 1,             // 1=read, 17=read+upload
  "expire_days": 7,             // TTL в днях (минимум в OCS = 1 день)
  "password": "optional"
}
→ 201 {
  "share_url": "https://nextcloud.company.local/s/abc123",
  "token": "abc123",
  "expire_date": "2026-04-26"
}
```

---

## Поиск

### GET /api/v1/search `[reader+]`

Единый поиск по KB-статьям, новостям, файлам Nextcloud, ярлыкам.

```
?q=docker&type=article&from=2026-01-01&to=2026-04-30&author=uuid&limit=20&offset=0
```

| Параметр | Описание |
|---------|---------|
| `q` | Поисковый запрос (обязателен, мин. 2 символа) |
| `type` | `article`, `news`, `file`, `link` — фильтр по типу |
| `from` / `to` | Диапазон дат создания |
| `author` | UUID пользователя |

```json
→ 200 {
  "items": [{
    "type": "article",
    "id": "uuid",
    "title": "Настройка Docker",
    "snippet": "...установить <em>docker</em> compose...",
    "url": "/kb/articles/uuid",
    "author": { "id": "uuid", "full_name": "..." },
    "created_at": "2026-03-01T00:00:00Z",
    "score": 0.95
  }],
  "total": 12,
  "limit": 20,
  "offset": 0
}
```

### GET /api/v1/search/suggest `[reader+]`
Автодополнение (typeahead). Debounce 300мс на фронте.
```
?q=dock
```
```json
→ 200 {
  "suggestions": [
    { "type": "article", "title": "Docker Compose guide", "url": "/kb/articles/uuid" },
    { "type": "news",    "title": "Докер обновлён до 26", "url": "/news/uuid" }
  ]
}
```

---

## Ярлыки

### GET /api/v1/links `[reader+]`
```json
→ 200 {
  "items": [{
    "id": "uuid",
    "title": "GitLab",
    "url": "https://gitlab.company.local",
    "icon_url": "/static/icons/gitlab.svg",
    "category": "dev",
    "supports_sso": true,
    "order_index": 0
  }]
}
```

### POST /api/v1/links `[admin]`
```json
← { "title": "Jira", "url": "https://jira.company.local", "category": "dev", "supports_sso": true, "icon_url": "...", "order_index": 1 }
→ 201 { "id": "uuid", ... }
```

### PUT /api/v1/links/{id} `[admin]`
```json
← { "title": "...", "is_active": false }
→ 200 { ... }
```

### DELETE /api/v1/links/{id} `[admin]`
```
→ 204
```

---

## Закладки

### GET /api/v1/bookmarks `[reader+]`
```json
→ 200 {
  "items": [{
    "id": "uuid",
    "resource_type": "article",
    "resource_id": "uuid",
    "resource_title": "Docker guide",
    "resource_url": "/kb/articles/uuid",
    "group_name": "Разработка",
    "order_index": 0
  }]
}
```

### POST /api/v1/bookmarks `[reader+]`
```json
← { "resource_type": "article", "resource_id": "uuid", "resource_title": "...", "resource_url": "...", "group_name": "Разработка" }
→ 201 { "id": "uuid", ... }
→ 409 { "detail": "Уже в закладках" }
```

### DELETE /api/v1/bookmarks/{id} `[reader+]`
```
→ 204
```

### PATCH /api/v1/bookmarks/reorder `[reader+]`
Drag-and-drop сортировка.
```json
← { "items": [{ "id": "uuid", "order_index": 0 }, { "id": "uuid", "order_index": 1 }] }
→ 200 {}
```

---

## Уведомления

### GET /api/v1/notifications `[reader+]`
```
?is_read=false&limit=20&offset=0
```
```json
→ 200 {
  "items": [{ "id": "uuid", "type": "new_news", "title": "Новость: IT обновление", "link": "/news/uuid", "is_read": false, "created_at": "..." }],
  "total": 3, ...
}
```

### POST /api/v1/notifications/{id}/read `[reader+]`
```
→ 200 {}
```

### POST /api/v1/notifications/read-all `[reader+]`
```
→ 200 { "marked_count": 5 }
```

### GET /api/v1/notifications/stream `[reader+]`
Server-Sent Events. Клиент передаёт `Last-Event-ID` для event replay при реконнекте.
```
→ 200 Content-Type: text/event-stream

id: 1714512345678-0
data: {"type": "new_news", "title": "IT обновление", "link": "/news/uuid"}

id: 1714512346000-0
data: {"type": "article_updated", "title": "Docker guide обновлён", "link": "/kb/uuid"}
```

---

## Аналитика

Все endpoints `[admin]`.

### GET /api/v1/analytics/dashboard
```json
→ 200 {
  "mau": 245,
  "dau": 89,
  "top_articles": [{ "id": "uuid", "title": "...", "view_count": 342 }],
  "activity_by_hour": [{ "hour": 9, "count": 120 }, ...],
  "activity_by_department": [{ "department": "IT", "count": 520 }, ...]
}
```

### GET /api/v1/analytics/top-articles
```
?period=week&limit=10
```

### GET /api/v1/analytics/top-files
Из `audit_log WHERE event_type = 'download_file'`.
```
?period=month&limit=10
```

### GET /api/v1/analytics/departments
```json
→ 200 { "items": [{ "department": "IT", "active_users": 45, "articles_viewed": 320 }] }
```

---

## Аудит

Все endpoints `[admin]`.

### GET /api/v1/audit
```
?user_id=uuid&event_type=download_file&from=2026-04-01&to=2026-04-30&limit=50&offset=0
```
```json
→ 200 {
  "items": [{
    "id": 12345,
    "event_type": "download_file",
    "user_id": "uuid",
    "user_email": "ivan@company.local",
    "resource_type": "file",
    "resource_id": "/Finance/report.xlsx",
    "ip_address": "10.0.1.42",
    "created_at": "2026-04-19T11:23:00Z"
  }],
  "total": 1500, ...
}
```

### GET /api/v1/audit/export.csv `[admin]`
```
?user_id=uuid&event_type=...&from=...&to=...
→ 200 Content-Type: text/csv
      Content-Disposition: attachment; filename="audit_2026-04.csv"
```

---

## Health & Metrics

### GET /health
Жив ли процесс. Всегда 200 (если процесс запущен).
```json
→ 200 { "status": "ok" }
```

### GET /ready
Готов ли к трафику. Проверяет все зависимости. **Используется в Docker healthcheck.**
```json
→ 200 {
  "status": "ok",
  "checks": { "db": "ok", "redis": "ok", "nextcloud": "ok" }
}
→ 503 {
  "status": "degraded",
  "checks": { "db": "ok", "redis": "error", "nextcloud": "ok" }
}
```
Таймаут каждой проверки: 3 сек.

### GET /metrics
Prometheus метрики. Доступен только из внутренней сети (Nginx IP-restrict).
```
→ 200 Content-Type: text/plain; version=0.0.4
# HELP http_requests_total ...
```

---

## Шаблоны документов (v2 — не реализуется в v1)

> ⚠️ Модуль отложен до v2. Endpoint'ы ниже — проектные, не реализуются.

- `GET /api/v1/templates` — список шаблонов из Nextcloud `/Templates/`
- `POST /api/v1/templates/{id}/instantiate` — копировать шаблон в user-space + автоподстановка ФИО/Должности/Даты

---

## Коды ошибок

| HTTP | Когда |
|------|-------|
| 400 | Невалидные данные запроса (Pydantic validation) |
| 401 | Не аутентифицирован (нет/просрочен токен) |
| 403 | Нет прав (роль) или ACL Nextcloud запрещает |
| 404 | Ресурс не найден (или soft-deleted без `include_deleted`) |
| 409 | Конфликт версий (оптимистичная блокировка) / уже существует |
| 429 | Rate limit exceeded |
| 503 | Сервис недоступен (зависимость упала) |

Формат ошибки:
```json
{
  "detail": "Описание ошибки",
  "code": "OPTIONAL_ERROR_CODE"
}
```
