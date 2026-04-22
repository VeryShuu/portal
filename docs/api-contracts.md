# API Contracts

> Корпоративный интранет-портал
> Base URL: `/api/v1/`
> Auth: HTTPOnly cookie `portal_session` (server-side session в Redis; см. раздел «Аутентификация»)
> Format: JSON, UTF-8
> Последнее обновление: апрель 2026 (после Phase 2.1 — добавлена локальная аутентификация)

> **Источники аутентификации.** Портал поддерживает два источника:
> 1. **Keycloak SSO** — основной (Authorization Code + PKCE). Пользователь синхронизируется при первом логине.
> 2. **Local** — email + пароль (bcrypt). Используется для bootstrap первого admin и аварийного входа без Keycloak.
>
> В обоих случаях создаётся серверная сессия в Redis, идентификатор которой кладётся в HTTPOnly cookie `portal_session` (`Secure` в production, `SameSite=Lax`). JWT в куку **не кладётся** — он лежит только в Redis-сессии Keycloak-источника. Для смены источника у одного email доступен механизм account-linking (см. ADR в `docs/adr.md`).

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

### Static media files

| Path | Purpose | Caching |
|------|---------|---------|
| `/media/avatars/{filename}` | User avatars | 7 days |
| `/media/news/{filename}` | News cover images | 7 days |

Static files served by Nginx with proxy_pass to backend FastAPI StaticFiles mount. Access requires authentication (session cookie).

### Rate limits (per user, Redis)

| Endpoint | Лимит |
|----------|-------|
| `POST /auth/local/login` | 5 / 15 мин / IP (по `X-Real-IP`) |
| `GET /search` | 30 / мин / user |
| `POST /files/upload` | 10 / мин / user |
| Экспорт PDF/DOCX | 5 / мин / user |
| Остальные | 300 / мин / user |

---

## Аутентификация

### GET /api/v1/auth/config `[public]`
Возвращает фичефлаги для страницы логина (нужен фронтенду, чтобы понять, показывать ли форму local-входа).
```json
→ 200 {
  "local_auth_enabled": true,
  "keycloak_enabled": true
}
```

### GET /api/v1/auth/login
Редирект на Keycloak (Authorization Code + PKCE). Query: `?redirect=/path` — куда вернуться после логина.
```
→ 302 Location: https://auth.company.local/realms/corporate/protocol/openid-connect/auth?...
```

### GET /api/v1/auth/callback
OIDC callback. Обменивает `code` на токены, апсёртит пользователя, создаёт серверную сессию и ставит cookie.
```
→ 302 Location: /  (или redirect_after из state)
   Set-Cookie: portal_session=<opaque>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=28800
```
Audit: `auth.login` с `metadata.source = "keycloak"`.

### POST /api/v1/auth/local/login `[public, rate-limited]`
Локальный вход для аккаунтов с `auth_source = "local"` (например bootstrap-admin). Лимит: **5 попыток / 15 минут / IP** (по `X-Real-IP`).
```json
← { "email": "admin@company.local", "password": "..." }
→ 200 { "ok": true, "user_id": "uuid" }
   Set-Cookie: portal_session=<opaque>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=28800
→ 401 { "detail": "Invalid email or password" }   # унифицированный ответ для всех ошибок (нет user enumeration)
→ 403 { "detail": "Local authentication is disabled" }   # если LOCAL_AUTH_ENABLED=false
```
Audit: `auth.login` с `metadata.source = "local"` (успех) или `auth.local_login_denied` в логах (отказ — без аудит-события, чтобы не засорять).

### POST /api/v1/auth/logout `[reader+]`
Уничтожает сессию в Redis, удаляет cookie. Для Keycloak-сессий редиректит на Keycloak SLO front-channel; для local — сразу на `/login`.
```
→ 302 Location: /login   (local)
→ 302 Location: https://auth.../logout?id_token_hint=...&post_logout_redirect_uri=...   (keycloak)
   Set-Cookie: portal_session=; Max-Age=0; Path=/
```
Audit: `auth.logout` с `metadata.source = "local" | "keycloak"`.

### GET /api/v1/auth/logout `[public]`
Front-channel SLO endpoint, который Keycloak вызывает в скрытом iframe при выходе из другого сервиса. Тихо удаляет сессию, редиректит на `/login`.

### POST /api/v1/auth/refresh `[reader+]`
Тихое обновление access_token в Keycloak-сессии. Для local-сессий не применимо (вернёт 401 «No refresh token»).
```json
→ 200 { "ok": true }
→ 401 { "detail": "No refresh token" | "Refresh failed" }
```

### GET /api/v1/auth/me `[reader+]`
```json
→ 200 {
  "id": "uuid",
  "email": "ivan@company.local",
  "full_name": "Иван Петров",
  "department": "IT",
  "position": "Backend Developer",
  "phone": "+7 999 123-45-67",
  "role": "editor",
  "auth_source": "keycloak",        // "keycloak" | "local"
  "presence_status": "office",
  "avatar_url": "/media/avatars/<uuid>.jpg",
  "notify_email": true,
  "notify_inapp": true,
  "lang": "ru",
  "preferences": { "hidden_link_ids": [] }
}
```

---

## Пользователи

### GET /api/v1/users `[reader+]`
Список сотрудников.
```
?q=иван&department=IT&page=1&page_size=50
```
```json
→ 200 {
  "items": [{ "id": "uuid", "full_name": "...", "department": "...", "position": "...", "avatar_url": "...", "presence_status": "office" }],
  "total": 42
}
```

### GET /api/v1/users/{id} `[reader+]`
```json
→ 200 { /* полный профиль, аналог /auth/me */ }
→ 404 { "detail": "User not found" }
```

### PATCH /api/v1/users/me/profile `[reader+]`
Обновление статуса присутствия, языка интерфейса и настроек уведомлений.
```json
← {
  "presence_status": "office",   // "office" | "remote" | "vacation" — опционально
  "lang": "ru",                  // "ru" | "en" — опционально
  "notify_email": true,          // опционально
  "notify_inapp": true           // опционально
}
→ 200 { /* полный UserMe */ }
→ 422 { "detail": "Invalid presence_status" }
```

### POST /api/v1/users/me/avatar `[reader+]`
Загрузка аватара (multipart/form-data, max 5 МБ, JPEG/PNG/WebP). Файл сохраняется в `/data/avatars/<user_id>.<ext>`, URL — `/media/avatars/<filename>`.
```
→ 200 { /* UserMe с обновлённым avatar_url */ }
→ 422 { "detail": "Unsupported image type" }
→ 413 { "detail": "Avatar too large (max 5 MB)" }
```

### PATCH /api/v1/users/me/preferences `[reader+]`
Обновление персонализации (только поля, которые НЕ покрыты `/me/profile`). Хранится в `users.preferences JSONB`.
```json
← { "hidden_link_ids": ["uuid1", "uuid2"] }
→ 200 { /* UserMe с обновлёнными preferences */ }
```

### PATCH /api/v1/users/me/password `[reader+, only auth_source=local]`
Смена собственного пароля. Доступна только пользователям с `auth_source = "local"`.
```json
← { "current_password": "...", "new_password": "..." }      // new ≥ 8 символов
→ 200 { "ok": true }
→ 401 { "detail": "Current password is incorrect" }
→ 403 { "detail": "Password management is only available for local accounts" }
```

### POST /api/v1/users/admin/sync `[admin]`
Ручная синхронизация пользователей из Keycloak Admin API (запускается в ARQ-воркере).
```json
→ 200 { "job_id": "...", "status": "queued" }
```

### POST /api/v1/users/admin/local `[admin, only LOCAL_AUTH_ENABLED]`
Создание локального пользователя (email + пароль).
```json
← {
  "email": "user@company.local",
  "full_name": "Имя Фамилия",
  "password": "...",          // ≥ 8 символов
  "role": "reader"            // reader | editor | admin
}
→ 201 { /* UserPublic */ }
→ 403 { "detail": "Local authentication is disabled" }
→ 409 { "detail": "Email already registered" }
```

### PATCH /api/v1/users/admin/{user_id}/role `[admin]`
Изменение роли. Для Keycloak-аккаунтов вступит в силу при следующем upsert (новый логин/refresh).
```json
← { "role": "editor" }
→ 200 { /* UserPublic */ }
→ 422 { "detail": "Invalid role" }
→ 404 { "detail": "User not found" }
```

### PATCH /api/v1/users/admin/{user_id}/password `[admin, only target.auth_source=local]`
Сброс пароля локальному пользователю.
```json
← { "new_password": "..." }    // ≥ 8 символов
→ 200 { "ok": true }
→ 403 { "detail": "Password reset is only available for local accounts" }
→ 404 { "detail": "User not found" }
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
?status=published&page=1&page_size=20
```
> **Реализовано в коде**: `?status` (draft/published/archived — draft/archived требуют editor+), `?page`, `?page_size`.
> `?category` и `?is_pinned` задокументированы, но ещё не реализованы (см. P2-36).
```json
→ 200 {
  "items": [{ "id": "uuid", "title": "...", "category": "it", "is_pinned": false, "publish_at": "...", "view_count": 10, "cover_image_url": "/media/news/uuid.jpg", "created_by": {...} }],
  "total": 5
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
→ 200 {
  "id": "uuid",
  "title": "...",
  "body": "# Markdown...",
  "category": "company",
  "is_pinned": false,
  "publish_at": "...",
  "archive_at": "...",
  "view_count": 42,
  "cover_image_url": "/media/news/uuid.jpg",
  "created_by": { ... },
  "updated_by": { ... },
  "created_at": "...",
  "updated_at": "..."
}
```

### PUT /api/v1/news/{id} `[editor+]`
```json
← { "title": "...", "body": "...", "change_comment": "..." }
→ 200 { ... }
```

### PUT /api/v1/news/{id}/draft `[editor+]`
Автосохранение черновика. Принимает тот же `UpdateNewsRequest`, что и `PUT /news/{id}`,
но работает только если `news.status == 'draft'` (иначе 409). Возвращает обновлённый `NewsPublic`.
```json
← { "title": "...", "body": "...", "category": null, "target_departments": [], ... }
→ 200 { /* NewsPublic */ }
→ 409 { "detail": "Only drafts can be auto-saved this way" }
```

### DELETE /api/v1/news/{id} `[admin]`
Soft delete.
```
→ 204
```

### POST /api/v1/news/{id}/cover `[editor+]`
Загрузка обложки новости (multipart/form-data, поле `file`). Форматы: JPEG, PNG, WebP, GIF. Максимум 10 МБ. Файл сохраняется в `/data/news_media/{news_id}.{ext}`, URL — `/media/news/{filename}`.
```
→ 200 { /* NewsPublic с обновлённым cover_image_url */ }
→ 422 { "detail": "Unsupported image type" }
→ 413 { "detail": "Cover image too large (max 10 MB)" }
```

### DELETE /api/v1/news/{id}/cover `[editor+]`
Удаление обложки новости.
```
→ 200 { /* NewsPublic с cover_image_url: null */ }
```

### GET /api/v1/news/{id}/versions `[editor+]`
```
?limit=20&offset=0  → 200 { "items": [...], ... }
```

---

### Галерея новости (миграция 006)

Таблица `news_gallery_images`. Файлы лежат в `/data/news_media/{news_id}/gallery/{uuid}.{ext}`. Максимум на файл — `NEWS_ATTACHMENT_MAX_SIZE_MB` (env, 50 МБ по умолчанию). Форматы: JPEG, PNG, WebP, GIF.

#### GET /api/v1/news/{id}/gallery `[reader+]`
Для опубликованных новостей доступно всем; черновики видят только editor/admin.
```json
→ 200 [
  { "id": "uuid", "filename": "uuid.jpg", "original_name": "IMG_1.jpg", "sort_order": 0, "file_size": 204800, "created_at": "..." }
]
→ 403 / 404
```

#### POST /api/v1/news/{id}/gallery `[editor+]`
Загрузка одного изображения (multipart/form-data, поле `file`). `sort_order` присваивается автоматически в конец списка.
```
→ 201 { /* GalleryImagePublic */ }
→ 413 { "detail": "File too large (max 50 MB)" }
→ 422 { "detail": "Unsupported image type. Use JPEG, PNG, WebP or GIF" }
```

#### PATCH /api/v1/news/{id}/gallery/reorder `[editor+]`
Drag-and-drop сортировка.
```json
← [{ "id": "uuid", "sort_order": 0 }, { "id": "uuid", "sort_order": 1 }]
→ 200 [ /* обновлённый порядок GalleryImagePublic[] */ ]
```

#### DELETE /api/v1/news/{id}/gallery/{img_id} `[editor+]`
Удаляет файл с диска и запись из БД.
```
→ 204
→ 404 { "detail": "Image not found" }
```

---

### Вложения новости (миграция 006)

Таблица `news_attachments`. Файлы: `/data/news_media/{news_id}/attachments/{uuid}` (без расширения). Любые типы файлов, максимум — `NEWS_ATTACHMENT_MAX_SIZE_MB`.

#### GET /api/v1/news/{id}/attachments `[reader+]`
Черновики — только editor/admin.
```json
→ 200 [
  { "id": "uuid", "news_id": "uuid", "filename": "uuid", "original_name": "report.pdf", "mime_type": "application/pdf", "file_size": 102400, "download_url": "/api/v1/news/{news_id}/attachments/{id}/download", "created_at": "..." }
]
```

#### POST /api/v1/news/{id}/attachments `[editor+]`
Загрузка файла (multipart/form-data).
```
→ 201 { /* AttachmentPublic */ }
→ 413 { "detail": "File too large (max 50 MB)" }
```

#### GET /api/v1/news/{id}/attachments/{att_id}/download `[reader+]`
Скачивание с оригинальным именем. Используется RFC 5987 (`filename*=UTF-8''...`) для кириллицы.
```
→ 200 Content-Type: <mime_type or application/octet-stream>
      Content-Disposition: attachment; filename="..."; filename*=UTF-8''...
→ 403 / 404
```

#### DELETE /api/v1/news/{id}/attachments/{att_id} `[editor+]`
```
→ 204
```

---

### Экспорт новости

Все три форматта возвращают standalone-файл: обложка, картинки из тела (Markdown `![...]()`) и галерея встраиваются как `data:` URI (base64). `Content-Disposition` по RFC 5987 для кириллических заголовков.

#### GET /api/v1/news/{id}/export/html `[reader+]`
```
→ 200 Content-Type: text/html; charset=utf-8
      Content-Disposition: attachment; filename*=UTF-8''<title>.html
```

#### GET /api/v1/news/{id}/export/markdown `[reader+]`
Markdown с инлайном media (base64).
```
→ 200 Content-Type: text/markdown; charset=utf-8
      Content-Disposition: attachment; filename*=UTF-8''<title>.md
```

#### GET /api/v1/news/{id}/export/pdf `[reader+]`
Playwright/Chromium `page.pdf()`. Rate limit: 5/мин/user (запланировано).
```
→ 200 Content-Type: application/pdf
      Content-Disposition: attachment; filename*=UTF-8''<title>.pdf
```

---

## Файлы (Nextcloud proxy)

> ⚠️ **Статус на апрель 2026:** модуль ЗАБЛОКИРОВАН. Реализуется после миграции Nextcloud → Keycloak OIDC и фиксации `NC_USER_ID_FIELD` (см. `docs/adr.md` ADR-002, Step 9 плана).

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

### GET /api/v1/links/{id}/sso-url `[reader+]`
Возвращает URL для перехода. Если `supports_sso=true` и в текущей сессии есть `id_token` — к URL добавляется query-параметр `id_token_hint`. Если `supports_sso=false` — `{url}` без SSO-флага.
```json
→ 200 { "url": "https://gitlab.company.local?id_token_hint=eyJhbGc...", "sso": true }
→ 404
```

---

## Закладки

> Поля DTO приведены в соответствие с реализацией (миграция 003): `title`, `url`, `sort_order`.
> Старые имена `resource_title`/`resource_url`/`order_index` больше не используются.

### GET /api/v1/bookmarks `[reader+]`
```json
→ 200 [
  {
    "id": "uuid",
    "title": "Docker guide",
    "url": "/kb/articles/uuid",
    "icon_url": null,
    "group_name": "Разработка",
    "sort_order": 0,
    "created_at": "..."
  }
]
```

### POST /api/v1/bookmarks `[reader+]`
```json
← { "title": "...", "url": "...", "icon_url": null, "group_name": "Разработка" }
→ 201 { /* Bookmark */ }
→ 409 { "detail": "Already bookmarked" }
```

### DELETE /api/v1/bookmarks/{id} `[reader+]`
```
→ 204
```

### PATCH /api/v1/bookmarks/reorder `[reader+]`
Drag-and-drop сортировка. Использует `pg_advisory_xact_lock(hash(user_id))`.
```json
← [{ "id": "uuid", "sort_order": 0 }, { "id": "uuid", "sort_order": 1 }]
→ 200 [ /* обновлённый Bookmark[] в новом порядке */ ]
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

> P2-34: проверка `nextcloud` будет добавлена после разблокировки Phase 5.
> На текущий момент проверяются только Postgres и Redis; статусы — `"ok"` или `"error"`.

```json
→ 200 {
  "status": "ok",
  "checks": { "postgres": "ok", "redis": "ok" }
}
→ 503 {
  "status": "error",
  "checks": { "postgres": "ok", "redis": "error" }
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
