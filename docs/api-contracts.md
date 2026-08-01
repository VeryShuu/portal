# API Contracts

> **Когда читать:** добавляешь/меняешь REST-endpoint.
> **Ключевой код:** `app/api/`, `app/schemas/`; auth-зависимости — `app/api/deps.py`.
> **ADR:** 032, 035.

> **Auto-generated companion:** `./docs/api-contracts.generated.md` — produced by `./backend/scripts/generate_api_contracts_doc.py`.  
> Run `cd backend && python3 -m scripts.generate_api_contracts_doc --openapi-json ../openapi.json` to refresh (or omit `--openapi-json` to re-import the app directly).  
> This curated file contains narrative context and examples; the generated file reflects the current OpenAPI spec.

> Корпоративный интранет-портал
> Base URL: `/api/v1/`
> Auth: HTTPOnly cookie `portal_session` (server-side session в Redis; см. раздел «Аутентификация»)
> Format: JSON, UTF-8
> Последнее обновление: июль 2026 (v1.13) — к v1.5 добавлены **Helpdesk**
> (заявки/IMAP/тикеты/агенты/settings — см. отдельный раздел ниже и
> [`./helpdesk.md`](./helpdesk.md) §4), **MAX-messenger оповещения** о новых
> заявках, `mailing_recipients` + `POST /news/{id}/share-email`, лайки/комментарии
> новостей (068/069), справочники объектов (`/directories`), пофайловый шеринг
> (`/files/.../shares`), `last_auth_method` в `/auth/config` (ADR-036 п.7),
> `kb_url` на service_links. Все фазы 0–5 + Helpdesk/MAX реализованы.

## Оглавление

- [Соглашения](#соглашения)
- [Аутентификация](#аутентификация)
- [Bootstrap](#bootstrap)
- [Пользователи](#пользователи)
- [Маппинг атрибутов пользователей](#маппинг-атрибутов-пользователей)
- [База знаний (KB)](#база-знаний-kb)
- [Новости](#новости)
- [Категории новостей](#категории-новостей)
- [Справочник получателей рассылки](#справочник-получателей-рассылки)
- [Поиск](#поиск)
- [Ярлыки](#ярлыки)
- [Закладки](#закладки)
- [Уведомления](#уведомления)
- [Аналитика](#аналитика)
- [Аудит](#аудит)
- [Health & Metrics](#health--metrics)
- [Оформление портала (Branding)](#оформление-портала-branding)
- [Настройки Email (SMTP)](#настройки-email-smtp-adminemail-settings)
- [Системные настройки](#системные-настройки-adminsystem)
- [TLS-сертификат](#tls-сертификат-adminsystemtls)
- [Настройки Keycloak](#настройки-keycloak-adminkeycloak)
- [Фотогалерея (собственный модуль)](#фотогалерея-собственный-модуль)
- [Модули (Admin UI)](#модули-admin-ui)
- [Файлы (Phase 5)](#36-файлы-phase-5--nextcloud-service-account-adr-032)
- [Справочники объектов](#справочники-объектов-apiv1directories)
- [Техподдержка (Helpdesk)](#техподдержка-helpdesk)
- [Email-outbox (admin)](#email-outbox-admin)
- [Шаблоны документов (v2)](#шаблоны-документов-v2--не-реализуется-в-v1)
- [Коды ошибок](#коды-ошибок)

> **Источники аутентификации.** Портал поддерживает два источника:
> 1. **Keycloak SSO** — основной (Authorization Code + PKCE). Пользователь синхронизируется при первом логине.
> 2. **Local** — email + пароль (bcrypt). Используется для bootstrap первого admin и аварийного входа без Keycloak.
>
> В обоих случаях создаётся серверная сессия в Redis, идентификатор которой кладётся в HTTPOnly cookie `portal_session` (`Secure` только при HTTPS — определяется по заголовку `X-Forwarded-Proto` от nginx, `SameSite=Lax`). JWT в куку **не кладётся** — он лежит только в Redis-сессии Keycloak-источника. Для смены источника у одного email доступен механизм account-linking (см. ADR в `docs/adr.md`).

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

Применяется к: `POST /news`, `POST /kb/articles`, `POST /files/folders` и вложенным `POST /files/folders/**` (создание папки, upload, bulk-операции).

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
| `POST /auth/refresh` | 30 / мин / user |
| `GET /search` | 60 / мин / user |
| `GET /search/suggest` | 120 / мин / user |
| `PATCH /users/me/password` | 10 / 15 мин / user |
| `PATCH /users/admin/{id}/password` | 20 / 15 мин / admin |
| `POST /files/folders/{id}/upload` | 20 / мин / user |
| `GET /files/download`, `GET /files/preview` | 60 / мин / user |
| `POST /files/folders/{id}/bulk-delete`, `.../bulk-move` | 3 / мин / user |
| Экспорт PDF/DOCX | 5 / мин / user |
| Остальные | без явного лимита (CSRF + Origin) |

---

## Аутентификация

### GET /api/v1/auth/config `[public]`
Возвращает фичефлаги для страницы логина (нужен фронтенду, чтобы понять, показывать ли форму local-входа) и маркер последнего способа входа для UX-корректного re-login на холодном старте (ADR-036 п.7).
```json
→ 200 {
  "local_auth_enabled": true,
  "keycloak_enabled": true,
  "last_auth_method": "local"   // "local" | "keycloak" | null (cookie portal_auth_method)
}
```

Поле `last_auth_method` читается из долгоживущей (30 дней, `HttpOnly=False`) cookie
`portal_auth_method`, которую бэкенд ставит/обновляет при каждом успешном login
(`local.local_login` → `"local"`, OIDC callback → `"keycloak"`) и намеренно не
удаляет при logout. Фронт инициализирует из неё внутренний `_sessionAuthSource`
на холодном старте, чтобы при истечении Redis-сессии local-юзер ушёл на форму
`/auth/local`, а не на Keycloak SSO. Если cookie нет (новое устройство) → `null`
→ дефолт `'keycloak'`. Содержимое — только маркер, без PII.

### GET /api/v1/auth/login
Редирект на Keycloak (Authorization Code + PKCE). Query: `?redirect=/path` — куда вернуться после логина.
```
→ 302 Location: https://auth.company.local/realms/corporate/protocol/openid-connect/auth?...
```

### GET /api/v1/auth/callback
OIDC callback. Обменивает `code` на токены, апсёртит пользователя, создаёт серверную сессию и ставит cookie.
```
→ 302 Location: /  (или redirect_after из state)
   Set-Cookie: portal_session=<opaque>; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800
   # Secure добавляется только если X-Forwarded-Proto: https (т.е. если nginx работает по TLS)
```
Audit: `auth.login` с `metadata.source = "keycloak"`.

### POST /api/v1/auth/local/login `[public, rate-limited]`
Локальный вход для аккаунтов с `auth_source = "local"` (например bootstrap-admin). Лимит: **5 попыток / 15 минут / IP** (по `X-Real-IP`).
```json
← { "email": "admin@company.local", "password": "..." }
→ 200 { "ok": true, "user_id": "uuid" }
   Set-Cookie: portal_session=<opaque>; HttpOnly; SameSite=Lax; Path=/; Max-Age=28800
   # Secure добавляется только если X-Forwarded-Proto: https
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
При успехе ротирует `session_id` (старая запись в Redis удаляется) и переустанавливает cookie `portal_session` с `max_age = 8h`.
```json
→ 200 { "ok": true }
→ 401 { "detail": "No refresh token" | "Refresh failed" }
```

**Клиентское использование** (см. ADR-035):
- Auth-store запускает `setInterval` каждые **4 минуты** после успешного `loadUser()` и дёргает этот endpoint в фоне (silent refresh). Запас перед типичным KC Access Token Lifespan = 5 мин.
- HTTP-клиент `api()` в `frontend/src/api/index.ts` ловит 401 на любом запросе, один раз вызывает `/auth/refresh` (через singleton-promise — параллельные 401-ы коалесцируются в один refresh) и повторяет исходный запрос. Если refresh упал — редирект на `/login` с `?redirect=`.

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

## Bootstrap

### GET /api/v1/bootstrap

**Назначение:** Агрегированный запрос начальной загрузки приложения — возвращает данные текущего пользователя, настройки брендинга, список активных модулей и количество непрочитанных уведомлений за один запрос.

**Auth:** требуется сессия (возвращает 401 если не аутентифицирован)

**Response 200:**
```json
{
  "user": { /* UserOut */ },
  "branding": { /* BrandingSettings */ },
  "modules": { /* ModulesConfig */ },
  "gallery_links": { /* GalleryLinksOut */ },
  "unread_count": 0
}
```

### GET /api/v1/portal/gallery-links `[reader+]`
Ссылки на фотогалерею и видеогалерею из системных настроек. Используется виджетом на главной странице.
```json
→ 200 {
  "photo_gallery_url": "https://photos.company.local",
  "photo_gallery_mode": "internal",
  "photo_gallery_new_tab": false,
  "video_gallery_url": null
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

### GET /api/v1/users/me `[reader+]`
Текущий аутентифицированный пользователь (алиас `/auth/me` с той же схемой `UserMe`).
```json
→ 200 { /* UserMe — идентично /auth/me */ }
```

### GET /api/v1/users/admin/{user_id}/groups `[admin]`
Список Keycloak-групп пользователя из поля `keycloak_groups`.
```json
→ 200 { "groups": ["/corp/it", "/corp/dev"] }
→ 404 { "detail": "User not found" }
```

### PATCH /api/v1/users/admin/{user_id}/profile `[admin, only target.auth_source=local]`
Редактирование профильных полей локального пользователя. Все поля опциональны;
`birth_date`/`gender` (миграция 087) также редактируются вручную, но следующий
импорт ERP перетрёт их значения (источник истины — ERP).
```json
← {
  "full_name": "Иван Петров",
  "department": "IT",
  "position": "Backend Developer",
  "phone": "+7 999 123-45-67",
  "birth_date": "1990-05-15",
  "gender": "male"
}
→ 200 { /* UserPublic */ }
→ 403 { "detail": "Profile editing is only available for local accounts" }
→ 404 { "detail": "User not found" }
```

### DELETE /api/v1/users/admin/{user_id} `[admin]`
Soft-delete пользователя. Нельзя удалить собственный аккаунт. Инвалидирует все активные сессии пользователя.
```
→ 204
→ 400 { "detail": "Cannot delete your own account" }
→ 404 { "detail": "User not found" }
```

---

## Маппинг атрибутов пользователей

Позволяет отображать произвольные Keycloak-атрибуты (`users.attributes JSONB`) в карточке пользователя.

### GET /api/v1/user-attribute-mappings/schema `[reader+]`
Публичная схема включённых атрибутов — используется страницей профиля пользователя.
```json
→ 200 {
  "items": [
    { "attr_key": "telegram", "label_ru": "Telegram", "label_en": "Telegram", "sort_order": 0 }
  ]
}
```

### GET /api/v1/user-attribute-mappings `[admin]`
Полный список маппингов (включая отключённые).
```json
→ 200 {
  "items": [
    {
      "id": "uuid",
      "attr_key": "telegram",
      "label_ru": "Telegram",
      "label_en": "Telegram",
      "sort_order": 0,
      "enabled": true,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 3
}
```

### GET /api/v1/user-attribute-mappings/discover `[admin]`
Найти ключи атрибутов из `users.attributes` JSONB, которые ещё не замаплены (исключает нативные поля email, full_name, department, position, phone и т.д.).
```json
→ 200 {
  "items": [
    { "attr_key": "telegram", "sample": "@ivan", "occurrences": 42 }
  ]
}
```

### POST /api/v1/user-attribute-mappings `[admin]`
Создать маппинг.
```json
← {
  "attr_key": "telegram",
  "label_ru": "Telegram",
  "label_en": "Telegram",
  "sort_order": 0,
  "enabled": true
}
→ 201 { /* UserAttributeMappingPublic */ }
→ 409 { "detail": "Mapping with this attr_key already exists" }
→ 400 { "detail": "Attribute '...' is already represented by a native user field..." }
```

### PUT /api/v1/user-attribute-mappings/{mapping_id} `[admin]`
Обновить маппинг (поддерживает частичное обновление через exclude_unset).
```json
← { "label_ru": "Телеграм", "sort_order": 1, "enabled": false }
→ 200 { /* UserAttributeMappingPublic */ }
→ 404 { "detail": "Mapping not found" }
```

### DELETE /api/v1/user-attribute-mappings/{mapping_id} `[admin]`
Удалить маппинг. Атрибут в `users.attributes` не затрагивается.
```
→ 204
→ 404 { "detail": "Mapping not found" }
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
    "sort_order": 0,
    "children": [{ "id": "uuid", "title": "Первый день", ... }]
  }]
}
```

### POST /api/v1/kb/sections `[editor+]`
```json
← { "title": "Новый раздел", "parent_id": "uuid|null", "description": "...", "sort_order": 0 }
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
← { "title": "...", "body": "# ...", "version": 3 }   ← version обязателен (оптимистичная блокировка)
→ 200 { /* KbArticlePublic */ }
→ 409 { "detail": "Статья изменена другим пользователем" }
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

### GET /api/v1/kb/articles/{id}/suggestions `[editor+]`
Список правок (suggestions) на статью.
```json
→ 200 {
  "items": [{ "id": "uuid", "body": "...", "comment": "...", "status": "pending",
              "author": { "id": "uuid", "full_name": "..." }, "created_at": "..." }],
  "total": 3
}
```

### POST /api/v1/kb/suggestions/{id}/review `[editor+]`
Одобрить или отклонить правку.
```json
← { "action": "approve" }   // "approve" | "reject"
→ 200 { "id": "uuid", "status": "approved", "reviewed_at": "..." }
```
При `action: approve` — тело правки применяется к статье (создаётся новая версия).

### DELETE /api/v1/kb/articles/{id}/comments/{comment_id} `[reader+ (author only) | admin]`
Soft delete комментария.
```
→ 204
→ 403  (не автор и не admin)
→ 404
```

### POST /api/v1/kb/articles/{id}/feedback `[reader+]`
Оценить полезность статьи (upsert — повторный вызов меняет оценку).
```json
← { "is_helpful": true }
→ 200 { "helpful_count": 10, "not_helpful_count": 2, "user_feedback": true }
```

### PUT /api/v1/kb/sections/{id} `[editor+]`
Обновить раздел (заголовок, описание, порядок, родительский раздел).
```json
← { "title": "Новое название", "sort_order": 2 }
→ 200 { "id": "uuid", "title": "Новое название", ... }
```

---

### Права доступа к разделам KB (миграция 009_kb_acl)

> Права KB — отдельная система от ролей портала (`users.role`). Manager раздела или portal admin могут управлять доступом. Пользователи видят только те разделы/статьи, к которым есть хотя бы viewer-право.

#### GET /api/v1/kb/sections/{id}/permissions `[kb_manager | admin]`
Список субъектов с правами на раздел.
```json
→ 200 [
  {
    "id": "uuid",
    "subject_type": "user",
    "subject_id": "keycloak-uuid",
    "subject_name": "Иванов Иван",
    "email": "ivan@company.local",
    "permission": "editor",
    "granted_by": { "id": "uuid", "full_name": "..." },
    "created_at": "..."
  }
]
→ 403  (нет прав manager на этот раздел)
```

#### POST /api/v1/kb/sections/{id}/permissions `[kb_manager | admin]`
Добавить или обновить право (`UPSERT` по `subject_id`).
```json
← {
  "subject_type": "user",
  "subject_id": "keycloak-uuid",
  "subject_name": "Иванов Иван",
  "permission": "editor"
}
→ 201 { /* SectionPermission */ }
→ 403
```

#### DELETE /api/v1/kb/sections/{id}/permissions/{subject_id} `[kb_manager | admin]`
```
→ 204
→ 403 / 404
```

#### GET /api/v1/kb/users/search `[editor+]`
Поиск пользователей и групп из Keycloak для picker управления правами.
```
?q=ивано&limit=20
```
```json
→ 200 {
  "users": [
    { "subject_type": "user", "subject_id": "uuid", "subject_name": "Иванов Иван", "email": "ivan@company.local" }
  ],
  "groups": [
    { "subject_type": "group", "subject_id": "group-uuid", "subject_name": "IT-отдел" }
  ]
}
```

---

### Права доступа к статьям KB

#### GET /api/v1/kb/articles/{id}/permissions `[kb_manager | admin]`
Список прав на статью. Актуально только при `inherit_permissions = false`.
```json
→ 200 [ /* ArticlePermission[] */ ]
```

#### POST /api/v1/kb/articles/{id}/permissions `[kb_manager | admin]`
```json
← { "subject_type": "user", "subject_id": "...", "subject_name": "...", "permission": "viewer" }
→ 201 { /* ArticlePermission */ }
```

#### DELETE /api/v1/kb/articles/{id}/permissions/{subject_id} `[kb_manager | admin]`
```
→ 204
```

#### PATCH /api/v1/kb/articles/{id}/inherit `[kb_manager | admin]`
Переключить наследование прав. При переключении на `false` — текущие права раздела копируются как стартовая точка.
```json
← { "inherit_permissions": false }
→ 200 { "id": "uuid", "inherit_permissions": false, ... }
```

---

### Медиа KB (изображения в тело статьи)

> Изображения хранятся в `/data/kb/media/{article_id}/{uuid}.{ext}`. Отдача через Nginx internal redirect. Максимум: `KB_MEDIA_MAX_SIZE_MB` (env).

#### POST /api/v1/kb/articles/{id}/media `[kb_editor | admin]`
Загрузка изображения для вставки в тело статьи (multipart/form-data, поле `file`). Форматы: JPEG, PNG, WebP, GIF.
```json
→ 201 { "url": "/kb/media/{article_id}/{uuid}.jpg" }
→ 413 { "detail": "Image too large" }
→ 422 { "detail": "Unsupported image type" }
```

#### POST /api/v1/kb/articles/{id}/media/remote `[kb_editor | admin]`
Re-host внешней картинки в локальное хранилище. Используется редактором при
paste/drop картинки с внешнего URL (тег `<img src>` из буфера при «Копировать
изображение» / Ctrl+C на картинке со страницы): сервер скачивает её
(SSRF-guard: блок private/loopback/cloud-metadata IP, двойной DNS-резолв против
DNS-rebinding, ручной обход редиректов с ре-валидацией каждого hop) и сохраняет
локально, чтобы статья не зависела от стороннего URL. Контракт ответа идентичен
file-upload.
```json
← { "url": "https://example.com/photo.png" }
→ 201 { "url": "/kb/media/{article_id}/{uuid}.png", "filename": "..." }
→ 413 { "detail": "Image too large" }
→ 422 { "detail": "Could not fetch the image" }
```

#### GET /kb/media/{article_id}/{filename}
Отдача медиа-файла через Nginx `X-Accel-Redirect`. Требует аутентификации и viewer-права на статью.
```
→ 200 Content-Type: image/jpeg
→ 403 / 404
```

---

### Вложения KB

> Файлы хранятся в `/data/kb/files/{article_id}/{uuid}`. Максимум: `KB_ATTACHMENT_MAX_SIZE_MB`.

#### GET /api/v1/kb/articles/{id}/files `[kb_viewer+]`
```json
→ 200 [
  {
    "id": "uuid",
    "original_name": "spec.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 102400,
    "uploaded_by": { "id": "uuid", "full_name": "..." },
    "created_at": "...",
    "download_url": "/api/v1/kb/articles/{id}/files/{file_id}/download"
  }
]
```

#### POST /api/v1/kb/articles/{id}/files `[kb_editor | admin]`
Загрузка вложения (multipart/form-data, поле `file`).
```
→ 201 { /* KbFilePublic */ }
→ 403
→ 413 { "detail": "File too large" }
```

#### GET /api/v1/kb/files/{article_id}/{filename} `[kb_viewer+]`
```
→ 200 Content-Type: <mime>
      Content-Disposition: attachment; filename*=UTF-8''<filename>
→ 403 / 404
```

#### DELETE /api/v1/kb/articles/{id}/files/{file_id} `[kb_editor (автор файла) | admin]`
```
→ 204
→ 403 / 404
```

---

### Экспорт KB

#### GET /api/v1/kb/articles/{id}/export/md `[kb_viewer+]`
Статья как `.md` файл с YAML frontmatter.
```yaml
---
title: "Настройка Docker"
tags: [docker, devops]
section: "DevOps / Контейнеры"
author: "Иванов Иван"
created: "2026-04-01T10:00:00Z"
updated: "2026-04-19T14:00:00Z"
---
# Настройка Docker
...
```
```
→ 200 Content-Type: text/markdown; charset=utf-8
      Content-Disposition: attachment; filename*=UTF-8''<title>.md
→ 403
```

#### GET /api/v1/kb/sections/{id}/export/zip `[kb_viewer+]`
Раздел как ZIP: подпапки по иерархии + `_attachments/{article_slug}/`. Генерируется в памяти (`io.BytesIO`), не сохраняется на диск.
```
→ 200 Content-Type: application/zip
      Content-Disposition: attachment; filename*=UTF-8''<section_title>.zip
```

#### GET /api/v1/kb/export/vault.zip `[reader+]`
Вся KB как ZIP, совместимый с Obsidian vault (только разделы/статьи с viewer-правами текущего пользователя). Изображения — в `_assets/`.
```
→ 200 Content-Type: application/zip
      Content-Disposition: attachment; filename="kb-vault.zip"
```

---

### Импорт KB

#### POST /api/v1/kb/articles/import `[editor+]`
Принимает `.md` файл. Парсит YAML frontmatter, создаёт или обновляет статью. Секцию создаёт если не существует.
```
← multipart/form-data: file (.md)
```
```json
→ 201 {
  "created": 1,
  "updated": 0,
  "skipped": 0,
  "errors": []
}
→ 422 { "detail": "Invalid Markdown or missing title in frontmatter" }
```

#### POST /api/v1/kb/import/vault `[editor+]`
Принимает ZIP (Obsidian vault). Рекурсивно создаёт разделы по структуре папок.
```
?strategy=skip|overwrite|create_new    (default: skip)
← multipart/form-data: file (.zip)
```
```json
→ 201 {
  "created": 12,
  "updated": 3,
  "skipped": 2,
  "errors": ["attachments/large_file.docx: exceeds KB_ATTACHMENT_MAX_SIZE_MB"]
}
→ 413 { "detail": "Archive too large" }
```

---

### Diff версий KB

#### GET /api/v1/kb/articles/{id}/versions/{v1}/diff/{v2} `[kb_viewer+]`
Построчный diff Markdown между двумя версиями (`difflib.unified_diff`).
```json
→ 200 {
  "v1": 2,
  "v2": 3,
  "stats": { "added": 5, "removed": 2 },
  "hunks": [
    {
      "header": "@@ -10,4 +10,7 @@",
      "lines": [
        { "type": "context", "content": " общий контекст" },
        { "type": "removed", "content": "-старая строка" },
        { "type": "added",   "content": "+новая строка" }
      ]
    }
  ]
}
→ 404  (версия не найдена)
→ 403
```

---

### GET /api/v1/kb/tags `[reader+]`

**Назначение:** Список всех тегов KB с количеством статей.

**Auth:** reader+

**Response 200:**
```json
[{ "id": "uuid", "name": "string", "articles_count": 0 }]
```

---

## Новости

### GET /api/v1/news `[reader+]`
Автоматический таргетинг по `department` и `role` из JWT.
```
?status=published&page=1&page_size=20
```
> **Реализовано в коде**: `?status` (draft/published/archived — draft/archived требуют editor+), `?page`, `?page_size`, `?category` (фильтр по одной категории, строка), `?is_pinned` (bool).
```json
→ 200 {
  "items": [{ "id": "uuid", "title": "...", "categories": ["it"], "is_pinned": false, "publish_at": "...", "view_count": 10, "cover_image_url": "/media/news/uuid.jpg", "created_by": {...} }],
  "total": 5
}
```

### POST /api/v1/news `[editor+]`
```json
← {
  "title": "Заголовок новости",
  "body": "# Markdown...",
  "categories": ["company"],
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
  "categories": ["company"],
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
← { "title": "...", "body": "...", "categories": [], "target_departments": [], ... }
→ 200 { /* NewsPublic */ }
→ 409 { "detail": "Only drafts can be auto-saved this way" }
```

### DELETE /api/v1/news/{id} `[editor+]`
Soft delete.
```
→ 204
```

### POST /api/v1/news/{id}/restore `[admin]`

**Назначение:** Восстановление soft-deleted новости.

**Auth:** [admin]

**Response 200:** `{ "id": "uuid", ... }` — NewsOut восстановленной новости

### GET /api/v1/news/limits `[reader+]`

**Назначение:** Возвращает максимальный размер файла для новостного модуля (из системной настройки).

**Auth:** reader+

**Response 200:**
```json
{
  "news_attachment_max_size_mb": 50
}
```

### POST /api/v1/news/{id}/cover `[editor+]`
Загрузка обложки новости (multipart/form-data, поле `file`). Форматы: JPEG, PNG, WebP, GIF. Максимальный размер определяется системной настройкой `news_attachment_max_size_mb`.
```
→ 200 { /* NewsPublic с обновлённым cover_image_url */ }
→ 422 { "detail": "Unsupported image type. Use JPEG, PNG, WebP or GIF" }
→ 413 { "detail": "File too large (max ... bytes)" }
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

### Реакции новости (лайки, миграция 068)

Реакция — только «лайк» (♥, без дизлайка). Идемпотентна: повтор POST/DELETE
возвращает текущее состояние без ошибки. Уважает `require_news_read_access`
(таргетированная новость для гостя без доступа → 404). Денормализованный
счётчик `news.like_count` обновляется в той же транзакции.

#### POST /api/v1/news/{id}/like `[reader+]`
Поставить лайк (идемпотентно).
```json
→ 200 { "like_count": 13, "liked_by_me": true }
→ 404 { "detail": "News not found" }
```

#### DELETE /api/v1/news/{id}/like `[reader+]`
Снять лайк (идемпотентно). Счётчик — через `GREATEST(0, count-1)`.
```json
→ 200 { "like_count": 12, "liked_by_me": false }
→ 404 { "detail": "News not found" }
```

> Поля `like_count`, `liked_by_me`, `comment_count` присутствуют в `NewsPublic`
> (в списке и детальной). `liked_by_me` вычисляется LEFT JOIN по текущему
> пользователю — без N+1.

---

### Комментарии новости (миграция 069)

Плоские комментарии (зеркало `kb_article_comments`) с inline-редактированием.
Чтение/постинг — все с read-доступом к новости; edit — только автор; delete —
автор или admin. Удалённый отдаётся как `is_deleted: true` без тела/автора.
Денормализованный `news.comment_count` поддерживается в транзакции.

#### GET /api/v1/news/{id}/comments `[reader+]`
Список (по возрастанию `created_at`). `?limit=20&offset=0`.
```json
→ 200 {
  "items": [
    {
      "id": "uuid", "news_id": "uuid", "body": "Текст", "is_deleted": false,
      "created_at": "...", "updated_at": "...",
      "author": { "id": "uuid", "full_name": "Иван Петров", "department": "IT", "avatar_url": null }
    }
  ],
  "total": 1
}
```

#### POST /api/v1/news/{id}/comments `[reader+]`
Добавить. `body`: 1..4000, санитизация Markdown (`sanitize_markdown`).
```json
← { "body": "Мой комментарий" }
→ 201 { /* NewsCommentPublic */ }
→ 404 { "detail": "News not found" }
```

#### PATCH /api/v1/news/{id}/comments/{comment_id} `[author]`
Редактировать своё (inline). `body`: 1..4000.
```json
← { "body": "Исправленный текст" }
→ 200 { /* NewsCommentPublic */ }
→ 403 { "detail": "Insufficient permissions" }   // не автор
→ 404 { "detail": "Comment not found" }
→ 409 { "detail": "Comment deleted" }
```

#### DELETE /api/v1/news/{id}/comments/{comment_id} `[author | admin]`
Мягкое удаление (`deleted_at`), счётчик −1.
```json
→ 204
→ 403 { "detail": "Insufficient permissions" }   // не автор и не admin
→ 404 { "detail": "Comment not found" }
→ 409 { "detail": "Already deleted" }
```

### POST /api/v1/news/{id}/share-email `[editor+, rate-limited 10/min]`
Разослать новость по email получателям **строго из справочника**
`mailing-recipients`. Клиент шлёт `recipient_ids` (не сырые адреса), backend
сам резолвит email — подмена адреса в обход справочника невозможна. Только для
`status="published"`. Письма ставятся в `email_outbox` (`kind=news`), по одной
строке на получателя; ответ — число поставленных в очередь. Поддерживает
`Idempotency-Key` (хранит `{ "enqueued": N }`).
```json
← {
  "recipient_ids": ["uuid", "uuid"],   // min 1, max 100; все должны быть активны
  "message": "Краткий текст…"          // optional, max 2000; null/пусто → автоген из body
}
→ 200 { "enqueued": 2 }
→ 404 { "detail": "News not found" }
→ 404 { "detail": "Unknown recipient(s): <id>" }   // любой id неизвестен/удалён
→ 409 { "detail": "Only published news can be shared by email" }
→ 422 { /* recipient_ids пуст или > 100 */ }
```

---

## Категории новостей

Категории хранятся в `/data/settings/news_categories.json`. При удалении категории она удаляется и из всех новостей через SQL `array_remove()`. Максимум 100 категорий.

### GET /api/v1/news-categories `[reader+]`
Список категорий с количеством опубликованных новостей.
```json
→ 200 {
  "items": [
    { "name": "Компания", "color": "#6B7AE8", "news_count": 12 },
    { "name": "IT", "color": "#E87A6B", "news_count": 5 }
  ]
}
```

### POST /api/v1/news-categories `[editor+]`
Создать категорию. `color` — hex 6-значный, по умолчанию `#6B7AE8`.
```json
← { "name": "Новая категория", "color": "#E87A6B" }
→ 201 { "items": [ /* CategoriesResponse */ ] }
→ 409 { "detail": "Category already exists" }
→ 400 { "detail": "Too many categories" }
```

### PATCH /api/v1/news-categories/{name}/color `[editor+]`
Обновить цвет категории. `name` — точное имя категории (URL-encoded).
```json
← { "color": "#AABBCC" }
→ 200 { "items": [ /* CategoriesResponse */ ] }
→ 404 { "detail": "Category not found" }
```

### DELETE /api/v1/news-categories/{name} `[editor+]`
Удалить категорию из реестра и из поля `categories` всех новостей.
```
→ 200 { "items": [ /* оставшиеся категории */ ] }
→ 404 { "detail": "Category not found" }
```

---

## Справочник получателей рассылки

Курируемая адресная книга для фичи «Сделать рассылку» (см.
`POST /news/{id}/share-email`). Управление — `editor`/`admin`; чтение списка
(для дропдауна в модалке рассылки) тоже требует `editor+`. Хранится в таблице
`mailing_recipients` (миграция 071, soft-delete, CI-уникальность email среди
активных). Все мутации пишут `audit_log` (`resource_type=mailing_recipient`).

### GET /api/v1/mailing-recipients `[editor+]`
Список активных получателей. `?q=<имя|email>&limit=100&offset=0`.
```json
→ 200 {
  "items": [
    { "id": "uuid", "name": "Иван Петров", "email": "ivan@example.com",
      "label": "IT-отдел", "created_at": "...", "updated_at": "..." }
  ],
  "total": 1, "limit": 100, "offset": 0
}
```

### POST /api/v1/mailing-recipients `[editor+]`
Создать получателя. `email` валидируется как `str` (regex `^[^@\s]+@[^@\s]+$`),
не `EmailStr` (см. AGENTS.md).
```json
← { "name": "Иван Петров", "email": "ivan@example.com", "label": "IT-отдел" }
→ 201 { /* MailingRecipientPublic */ }
→ 409 { "detail": "Recipient with this email already exists" }
→ 422 { /* email не прошёл валидацию */ }
```

### PUT /api/v1/mailing-recipients/{recipient_id} `[editor+]`
Обновить получателя (partial: любое из `name`/`email`/`label`).
```json
← { "label": "Бухгалтерия" }
→ 200 { /* MailingRecipientPublic */ }
→ 404 { "detail": "Recipient not found" }
→ 409 { "detail": "Recipient with this email already exists" }
```

### DELETE /api/v1/mailing-recipients/{recipient_id} `[editor+]`
Мягкое удаление (`deleted_at`). Удалённый адрес недоступен для выбора и резолва.
```
→ 204
→ 404 { "detail": "Recipient not found" }
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
← { "title": "Jira", "url": "https://jira.company.local", "category": "dev", "supports_sso": true, "icon_url": "...", "order_index": 1, "kb_url": "https://portal.company.local/kb/articles/uuid" }
→ 201 { "id": "uuid", ... }
```

`kb_url` (опц., миграция 074) — ссылка на KB-статью с инструкцией к сервису;
показывается в карточке ярлыка. `show_on_home` (070) — показывать ли ярлык в
виджете «Сервисы» на главной.

### PUT /api/v1/links/{id} `[admin]`
```json
← { "title": "...", "is_active": false }
→ 200 { ... }
```

### DELETE /api/v1/links/{id} `[admin]`
```
→ 204
```

### GET /api/v1/links/{link_id}/sso-redirect `[reader+]`
Серверный SSO-редирект: добавляет `id_token_hint` из текущей сессии к URL ярлыка и возвращает 302. Токен передаётся только в заголовке `Location` сервера и не попадает в тело ответа / JS-память. Единственный способ перехода с SSO (устаревший `GET /links/{id}/sso-url`, отдававший токен в JSON, удалён — A1).
```
→ 302 Location: https://gitlab.company.local?id_token_hint=eyJhbGc...
→ 404
```

### PATCH /api/v1/links/reorder `[editor+]`
Изменить порядок ярлыков.
```json
← { "items": [{ "id": "uuid", "sort_order": 0 }, { "id": "uuid", "sort_order": 1 }] }
→ 204
→ 404 { "detail": "One or more links not found" }
```

### POST /api/v1/links/{link_id}/icon `[admin]`
Загрузить кастомную иконку ярлыка (multipart/form-data, поле `file`). Форматы: JPEG, PNG, WebP, SVG, ICO, GIF, BMP. Максимум 500 КБ. Файл сохраняется в `/data/link_icons/{link_id}.{ext}`, URL — `/media/link_icons/{link_id}.{ext}`.
```
→ 200 { /* ServiceLinkPublic с обновлённым icon_url */ }
→ 413 Файл слишком большой
→ 422 Неподдерживаемый тип
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
→ 204
```

### GET /api/v1/bookmarks/favicon `[reader+]`
Прокси-загрузка favicon целевого домена с кэшированием в Redis (7 дней для успешных ответов, 1 день для ошибок). Query: `?url=https://example.com`. Возвращает бинарные данные иконки напрямую.
```
→ 200 Content-Type: image/x-icon (или image/png, image/svg+xml и т.д.)
→ 404 Favicon недоступен
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

### GET /api/v1/notifications/unread-count `[reader+]`
Быстрый счётчик непрочитанных (используется в bootstrap и polling-опросе).
```json
→ 200 { "unread_count": 3 }
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
  "generated_at": "2026-04-30T17:00:00+00:00",
  "users": {
    "total": 300,
    "active_30d": 245,
    "active_1h": 12,
    "new_30d": 5
  },
  "content": {
    "news_published_30d": 8,
    "kb_articles_published_30d": 3
  },
  "activity": {
    "audit_events_24h": 1200,
    "logins_24h": 89
  },
  "series": {
    "daily_logins_14d": [{ "day": "2026-04-16", "count": 45 }],
    "daily_publications_14d": [{ "day": "2026-04-16", "count": 2 }]
  }
}
```

### GET /api/v1/analytics/top-articles
```
?days=30&limit=20
```
```json
→ 200 [{ "id": "uuid", "title": "...", "section_title": "Onboarding", "view_count": 342, "published_at": "...", "updated_at": "..." }]
```

### GET /api/v1/analytics/top-news
```
?days=30&limit=20
```
```json
→ 200 [{ "id": "uuid", "title": "...", "view_count": 120, "published_at": "..." }]
```

### GET /api/v1/analytics/top-files
Из `audit_log` по событиям скачивания файлов, фото, экспорта KB.
```
?days=30&limit=20
```
```json
→ 200 [{ "resource_id": "uuid", "title": "report.xlsx", "downloads": 45, "last_download": "..." }]
```

### GET /api/v1/analytics/departments
```
?days=30
```
```json
→ 200 [{ "department": "IT", "total_users": 50, "active_users": 45, "events": 320 }]
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

### GET /api/v1/audit/event-types `[admin]`
Уникальные типы событий за последние 90 дней — для фильтра в UI.
```json
→ 200 ["auth.login", "news.created", "kb.article_updated", ...]
```

### GET /api/v1/audit/queue/depth `[admin]`
Текущая глубина очереди аудита в Redis (`audit_queue` + `audit_processing`).
```json
→ 200 { "pending": 3, "processing": 0 }
→ 503 { "detail": "audit_queue_unavailable" }
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

> Phase 5 реализована. Если модуль `nextcloud` включён, проверяется также `nextcloud` (GET `/status.php`). Статусы — `"ok"` или `"error"`.

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

## Оформление портала (Branding)

> Настройки хранятся в `/data/branding/` на volume. Файлы (логотип, favicon, фон) хранятся на диске, текстовые настройки — в `settings.json`. Максимальный размер файла — 2 МБ.

### GET /branding/settings
Получить все настройки оформления. Доступен всем без авторизации.

```
→ 200
{
  "portal_name": "Корпоративный портал",
  "portal_tagline": "Единая точка входа",
  "accent_color": "#d8262c",
  "welcome_subtitle": "",
  "banner_enabled": false,
  "banner_text": "",
  "banner_type": "info",
  "banner_expires_at": null
}
```

Поля `banner_type`: `info` | `warning` | `error` | `success`.  
`banner_expires_at` — ISO 8601 datetime или `null` (показывать всегда).

---

### PUT /admin/branding/settings
Сохранить настройки. Только `admin`.

```
PUT /api/v1/admin/branding/settings
Body: BrandingSettings (все поля, см. GET /branding/settings)

→ 200 BrandingSettings
→ 422 Невалидный accent_color или banner_type
```

---

### GET|HEAD /branding/logo
Получить логотип портала (бинарный файл). 404 если не загружен — фронт использует SVG-дефолт.
HEAD используется фронтендом для проверки наличия файла без скачивания тела.

```
→ 200 image/png | image/jpeg | image/svg+xml | image/webp
  Cache-Control: public, max-age=300
→ 404 { "detail": "No custom logo set" }
```

### POST /admin/branding/logo
Загрузить логотип. Только `admin`. Форматы: PNG, JPEG, SVG, WebP. Максимум 2 МБ.

```
POST multipart/form-data; file=<binary>
→ 200 { "url": "/api/v1/branding/logo" }
→ 413 Файл > 2 МБ
→ 422 Неподдерживаемый формат
```

### DELETE /admin/branding/logo
Сбросить логотип к встроенному SVG-дефолту.

```
→ 200 { "detail": "Logo reset to default" }
```

---

### GET|HEAD /branding/favicon
Получить favicon портала. Кэш 1 час. 404 если не загружен — браузер использует дефолт.
HEAD используется фронтендом для проверки наличия перед динамическим добавлением `<link rel="icon">`.

```
→ 200 image/x-icon | image/png | image/svg+xml | ...
  Cache-Control: public, max-age=3600
→ 404
```

### POST /admin/branding/favicon
Загрузить favicon. Форматы: ICO, PNG, JPEG, SVG, WebP. Только `admin`.

```
→ 200 { "url": "/api/v1/branding/favicon" }
```

### DELETE /admin/branding/favicon
```
→ 200 { "detail": "Favicon reset to default" }
```

---

### GET|HEAD /branding/login-bg
Получить изображение фона страницы входа. 404 если не загружен.
HEAD используется `LoginPage.vue` для проверки наличия фона без скачивания файла.

```
→ 200 image/jpeg | image/png | ...
  Cache-Control: public, max-age=3600
→ 404
```

### POST /admin/branding/login-bg
Загрузить фон страницы входа. Форматы: PNG, JPEG, SVG, WebP. Только `admin`.

```
→ 200 { "url": "/api/v1/branding/login-bg" }
```

### DELETE /admin/branding/login-bg
```
→ 200 { "detail": "Login background reset to default" }
```

---

## Настройки Email (SMTP) (`/admin/email-settings`)

> Настройки SMTP персистируются в `/data/branding/email-settings.json` и читаются ARQ-worker'ом при отправке писем. Применяются без рестарта. Только `admin`.

### GET /admin/email-settings `[admin]`
Получить текущие настройки SMTP.

```
→ 200 {
  "host": "smtp.company.local",
  "port": 587,
  "from_address": "portal@company.local",
  "username": "portal",
  "password_set": true,
  "use_tls": false,
  "use_starttls": true
}
```

Поле `password_set: bool` — показывает наличие пароля, значение не раскрывается.

---

### PUT /admin/email-settings `[admin]`
Обновить настройки SMTP.

```
PUT /api/v1/admin/email-settings
Body: {
  "host": "smtp.company.local",
  "port": 587,
  "from_address": "portal@company.local",
  "username": "portal",
  "password": "new_secret",      // null или "***" — оставить без изменений, "" — очистить
  "use_tls": false,
  "use_starttls": true
}

→ 200 EmailSettingsOut (см. GET)
→ 422 Невалидный порт (должен быть 1..65535)
```

---

### POST /admin/email-settings/test `[admin]`
Отправить тестовое письмо по текущим настройкам SMTP.

```
POST /api/v1/admin/email-settings/test
Body: { "to": "me@company.local" }

→ 200 { "status": "ok", "detail": "Test email delivered" }
→ 502 { "status": "error", "detail": "SMTP connect failed: ..." }
```

---

## Системные настройки (`/admin/system`)

> Все endpoints требуют роли `admin`. Настройки персистируются в `/data/settings/system.json` и применяются без рестарта контейнеров.

### GET /admin/system/settings `[admin]`
Получить текущие системные настройки.

```
→ 200 {
  "portal_base_url": "https://portal.company.local",
  "nextcloud_url": "https://nextcloud.company.local",
  "nc_user_id_field": "preferred_username",
  "nc_service_app_password_set": true,
  "max_upload_size_mb": 100,
  "allowed_cidr": "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
  "prometheus_metrics_enabled": true,
  "news_attachment_max_size_mb": 50,
  "kb_media_max_size_mb": 20,
  "kb_attachment_max_size_mb": 50,
  "log_level": "INFO"
}
```

Поле `nc_service_app_password_set: bool` — показывает, задан ли пароль, но не возвращает его значение.

---

### PUT /admin/system/settings `[admin]`
Обновить системные настройки. При изменении `max_upload_size_mb` или `allowed_cidr` — автоматически перегенерируются конфиги Nginx (`limits.conf`, `allowlist.conf`) и триггерится reload без рестарта контейнера.

```
PUT /api/v1/admin/system/settings
Body: {
  "portal_base_url": "https://portal.company.local",
  "nextcloud_url": "https://nextcloud.company.local",
  "nc_user_id_field": "preferred_username",        // preferred_username | sub
  "nc_service_app_password": "new_value",           // null или "***" — оставить без изменений
  "max_upload_size_mb": 100,
  "allowed_cidr": "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
  "prometheus_metrics_enabled": true,
  "news_attachment_max_size_mb": 50,
  "kb_media_max_size_mb": 20,
  "kb_attachment_max_size_mb": 50,
  "log_level": "INFO"                              // DEBUG|INFO|WARNING|ERROR|CRITICAL
}

→ 200 SystemSettingsOut (см. GET)
→ 422 Невалидный log_level, невалидный CIDR в allowed_cidr или выход за пределы диапазонов
```

> **Валидация CIDR:** каждый элемент `allowed_cidr` (через запятую) парсится через `ipaddress.ip_network()`. Невалидная запись → 422 без сохранения, Nginx-конфиг не перегенерируется.

---

### POST /admin/system/nginx/reload `[admin]`
Принудительно перегенерировать конфиги Nginx из текущих настроек и триггерить reload.

```
→ 200 { "status": "reload_triggered" }
```

### GET /api/v1/admin/system/nextcloud/status `[admin]`
Проверить доступность и корректность настроек Nextcloud: URL, аутентификация сервисного аккаунта, WebDAV.
```json
→ 200 {
  "ok": true,
  "configured": true,
  "server_reachable": true,
  "nc_version": "28.0.3",
  "auth_ok": true,
  "webdav_ok": true,
  "details": ""
}
```
Если URL или пароль сервисного аккаунта не заданы — `configured: false`, остальные поля `false`.

---

## TLS-сертификат (`/admin/system/tls`)

> Сертификат и ключ хранятся в `/data/certs/` (volume `./system_data/certs`). После загрузки автоматически триггерится reload Nginx.

### GET /admin/system/tls/status `[admin]`
Получить статус текущего TLS-сертификата.

```
→ 200 {
  "cert_exists": true,
  "key_exists": true,
  "cert_expires_at": "Apr 23 00:00:00 2026 GMT",
  "cert_subject": "CN = portal.company.local, O = Company"
}
```

---

### POST /admin/system/tls/cert `[admin]`
Загрузить TLS-сертификат в формате PEM.

```
POST multipart/form-data; file=<certificate.pem>

→ 200 { "status": "ok" }
→ 400 Неверный формат (ожидается -----BEGIN CERTIFICATE-----)
```

---

### POST /admin/system/tls/key `[admin]`
Загрузить приватный ключ в формате PEM.

```
POST multipart/form-data; file=<private.key>

→ 200 { "status": "ok" }
→ 400 Неверный формат (ожидается -----BEGIN ... PRIVATE KEY-----)
```

---

### DELETE /admin/system/tls/cert `[admin]`
Удалить текущий сертификат.

```
→ 200 { "status": "ok" }
```

### DELETE /admin/system/tls/key `[admin]`
Удалить текущий ключ.

```
→ 200 { "status": "ok" }
```

---

## Настройки Keycloak (`/admin/keycloak`)

> Настройки персистируются в `/data/secrets/keycloak-settings.json` (`chmod 0600`). При первом чтении автоматически мигрируются из устаревшего `/data/branding/keycloak-settings.json`. Используются два отдельных клиента: OIDC-клиент (авторизация пользователей) и sync-клиент (синхронизация справочника).

### GET /admin/keycloak/settings `[admin]`
Получить текущие настройки Keycloak.

```
→ 200 {
  "keycloak_url": "https://sso.company.local",
  "keycloak_realm": "company",
  "oidc_client_id": "portal",
  "oidc_client_secret_set": true,
  "sync_client_id": "portal-sync",
  "sync_client_secret_set": true
}
```

Поля `*_secret_set: bool` — показывают наличие секрета, значение не раскрывается.

---

### PUT /admin/keycloak/settings `[admin]`
Обновить настройки Keycloak. Изменения применяются немедленно (кэш сервиса сбрасывается).

```
PUT /api/v1/admin/keycloak/settings
Body: {
  "keycloak_url": "https://sso.company.local",
  "keycloak_realm": "company",
  "oidc_client_id": "portal",
  "oidc_client_secret": "new_secret",     // null или "***" — оставить без изменений
  "sync_client_id": "portal-sync",
  "sync_client_secret": "new_secret"      // "" — очистить; null/"***" — без изменений
}

→ 200 KeycloakSettingsOut (см. GET)
```

> **Настройка sync-клиента в Keycloak:**  
> 1. Создать клиент `portal-sync` (Client authentication: On, Service accounts roles: On)  
> 2. Service account → Assign role → `realm-management → view-users`  
> 3. Скопировать Client Secret → вставить в поле `sync_client_secret`  
> ⚠️ Не использовать учётную запись администратора Keycloak — только сервисный аккаунт с минимальными правами.

---

### POST /admin/keycloak/test/oidc `[admin]`
Проверить подключение OIDC-клиента: discovery-endpoint + client_credentials токен.

```
→ 200 {
  "discovery_url": "https://sso.company.local/realms/company/.well-known/openid-configuration",
  "discovery_ok": true,
  "token_endpoint": "https://sso.company.local/realms/company/protocol/openid-connect/token",
  "issuer": "https://sso.company.local/realms/company",
  "token_ok": true
}
```

При ошибке: `"discovery_ok": false, "discovery_error": "..."` или `"token_ok": false, "token_error": "..."`.

---

### POST /admin/keycloak/test/sync `[admin]`
Проверить подключение sync-клиента: получить токен и запросить 1 пользователя из Admin API.

```
→ 200 {
  "token_ok": true,
  "users_ok": true,
  "users_note": "Получено 1 пользователей (тест)"
}
```

При ошибке 403: сообщение «убедитесь, что сервисному аккаунту назначена роль realm-management → view-users».

---

### GET /admin/keycloak/sync/status `[admin]`
Получить статус последней синхронизации пользователей (из Redis `kc:sync_last_run`).

```
→ 200 {
  "last_run_at": "2026-04-23T19:30:00Z",
  "last_count": 287,
  "last_status": "ok"
}
// Если синхронизация ещё не запускалась:
→ 200 { "last_run_at": null, "last_count": null, "last_status": null }
```

---

## Фотогалерея (собственный модуль)

> Реализация: иерархия папок (`photo_folders`), per-folder ACL (`photo_folder_permissions`, уровни `viewer` / `uploader` / `manager` с наследованием вверх по дереву), фото (`photos`) с локальным хранением оригиналов и пяти размеров WebP/AVIF-thumbnail'ов (200/400/600/1000/1600). Отдача файлов — через Nginx `X-Accel-Redirect`. Модуль управляется через Admin UI → Модули → Фотогалерея (см. `PUT /admin/modules/photos`).
>
> Семантика прав: portal admin → manager на любом уровне; создатель папки / uploader фото → manager на ресурсе; иначе — наибольший из применимых grant'ов на самой папке или её предках по дереву.

### GET /photos/folders/tree `[reader+]`

Дерево всех папок, к которым у пользователя есть хотя бы `viewer`. Возвращает корни с вложенными `children`.

```
→ 200 {
  "items": [
    {
      "id": "uuid",
      "parent_id": null,
      "name": "Корпоративные мероприятия",
      "slug": "korporativnye-meropriyatiya",
      "path": "korporativnye-meropriyatiya",
      "permission": "viewer",
      "children": [ { "id": "...", "name": "2026", ... } ]
    }
  ]
}
```

---

### GET /photos/folders/{folder_id} `[viewer+]`

Метаданные папки + счётчики (`photos_count`, `children_count`) и вычисленное право (`permission`).

```
→ 200 FolderPublic
→ 403 No access
→ 404 Folder not found
```

---

### POST /photos/folders `[manager-of-parent | admin]`

Создание папки. Корневую папку (`parent_id = null`) может создать только `admin`. Дочернюю — пользователь с `manager` на родителе.

```json
{ "parent_id": "uuid|null", "name": "2026", "description": "..." }
```
```
→ 201 FolderPublic
→ 403 Only admin can create root folders / Insufficient photos permissions
```

`slug` генерируется автоматически (NFKD ASCII), коллизии разрешаются суффиксом `-2`, `-3`, …

---

### PATCH /photos/folders/{folder_id} `[manager]`

Обновление `name`, `description`, `cover_photo_id` (последняя должна принадлежать этой же папке).

```
→ 200 FolderPublic
→ 400 Cover photo must belong to this folder
→ 403 / 404
```

---

### DELETE /photos/folders/{folder_id} `[manager]`

Soft-delete (`deleted_at = now()`). Каскад на дочерние ресурсы — на уровне FK `ON DELETE CASCADE` для жёсткого удаления; для soft-delete дети остаются, но недоступны через дерево, т.к. родитель скрыт.

```
→ 204
```

---

### GET /photos/folders/{folder_id}/photos `[viewer+]`

Постраничный список фото в папке. Параметры: `page` (≥1), `per_page` (1..200, default 50), `sort` ∈ {`created_at`, `taken_at`, `original_name`}.

```
→ 200 { "items": [PhotoPublic], "total": int, "page": int, "per_page": int }
```

---

### POST /photos/folders/{folder_id}/upload `[uploader+]`

`multipart/form-data` с одним или несколькими `files`. Лимит размера и whitelist MIME — из настроек модуля (`max_size_mb`, `allowed_mime`).

```
→ 200 { "items": [ { "filename": "...", "photo_id": "uuid|null", "ok": bool, "error": "..." } ] }
→ 503 Photos module disabled
→ 403 Insufficient photos permissions
→ 404 Folder not found
```

После успешного INSERT каждой записи — enqueue ARQ-задачи `process_photo_upload` (генерация WebP-thumbnail'ов, парсинг EXIF, обновление `width/height/taken_at/processed=true`).

---

### GET /photos/{photo_id} `[viewer+]`

Метаданные фото (включая EXIF, если обработано).

```
→ 200 PhotoPublic
→ 403 / 404
```

---

### PATCH /photos/{photo_id} `[uploader+]`

Изменение `description` и/или перенос в другую папку (`folder_id`). Перенос требует `uploader` на целевой папке.

```
→ 200 PhotoPublic
→ 403 / 404
```

---

### DELETE /photos/{photo_id} `[uploaded_by | manager-of-folder | admin]`

Soft-delete. Автор фото может удалить своё; иначе требуется `manager` на папке.

```
→ 204
```

---

### GET /photos/recent `[reader+]`

Последние фото, доступные пользователю по ACL (отфильтровано после выборки). Параметр `limit` ≤ `widget_limit` модуля.

```
→ 200 [PhotoPublic, ...]   // [] если модуль отключён
```

Используется виджетом `PhotosWidget` на главной.

---

### GET /photos/thumbnail/{photo_id}/{size} `[viewer+]`

Размер: `200` | `400` | `600` | `1000` | `1600`. Параметр query `format=webp|avif` (default `webp`). Backend проверяет ACL и отдаёт `X-Accel-Redirect: /internal/photos-thumbs/{id}/{size}.{webp|avif}`. Если thumbnail отсутствует — генерируется on-the-fly и помечается `processed=true`.

```
→ 200 (Nginx) Content-Type: image/webp | image/avif
              Cache-Control: public, max-age=604800, immutable
→ 403 / 404
```

---

### GET /photos/original/{photo_id} `[viewer+]`

Отдаёт оригинальный файл через `X-Accel-Redirect: /internal/photos-originals/{materialized_path}/{filename}` с заголовком `Content-Disposition: inline` (или `attachment` при `?download=1`).

Параметры query:
- `download` (`0` | `1`, default `0`) — если `1`, ответ помечается `attachment` (имя файла в `Content-Disposition` через RFC 5987 на основе `original_name`).

```
→ 200 Content-Type: <mime>
       Cache-Control: no-store
       X-Content-Type-Options: nosniff
       Content-Disposition: inline|attachment; filename="..."; filename*=UTF-8''...
→ 403 / 404
```

---

### POST /photos/{photo_id}/share `[uploader+]`

Создаёт публичную ссылку (token-based, не требует авторизации) для конкретной фотографии. Запись пишется в `photo_share_tokens`. Аудит: `photos.share_created`.

```json
{ "expires_in_days": 7 }   // 1..365 или null (без срока)
```
```
→ 201 {
  "id": "uuid",
  "photo_id": "uuid",
  "token": "url-safe base64 (~43 символа)",
  "url": "https://portal.example.com/p/<token>",
  "created_at": "...",
  "expires_at": "..." | null
}
→ 403 Insufficient photos permissions
→ 404 Photo not found
```

`token` — `secrets.token_urlsafe(32)`. Отзыв — через установку `revoked_at`.

---

### GET /photos/public/{token}/info `[public]`

Метаданные фото без `uploaded_by`. Используется страницей `/p/{token}`.

```
→ 200 PhotoPublic   // uploaded_by всегда null
→ 404 Link not found
→ 410 Link expired
```

---

### GET /photos/public/{token}/thumbnail/{size} `[public]`

Публичный thumbnail. Размер: `200` | `400` | `600` | `1000` | `1600`, опциональный `?format=webp|avif`. Если файла нет — синхронно генерируется из оригинала. Затем `X-Accel-Redirect: /internal/photos-thumbs/{photo_id}/{size}.{webp|avif}`.

```
→ 200 (Nginx) Content-Type: image/webp | image/avif
              Cache-Control: public, max-age=3600
→ 404 / 410
```

---

### GET /photos/public/{token}/file `[public]`

Публичный оригинал. Поддерживает `?download=0|1` (см. `/photos/original/{id}`).

```
→ 200 Content-Type: <mime>
→ 404 / 410
```

---

### GET /photos/folders/{folder_id}/permissions `[manager]`

Список grant'ов на папке (без рекурсии).

```
→ 200 { "items": [PermissionPublic] }
```

---

### POST /photos/folders/{folder_id}/permissions `[manager]`

Создание / обновление гранта. Уникальная тройка `(folder_id, subject_type, subject_id)` — миграция 056 добавила `subject_type` в UNIQUE, поэтому один `subject_id` может иметь раздельные права как `user` и как `group`.

```json
{ "subject_type": "user|group", "subject_id": "...", "subject_name": "Иванов И.И.", "permission": "viewer|uploader|manager" }
```
```
→ 201 PermissionPublic
→ 403 / 404
```

После записи — инвалидация кэша: `INCR photo_acl_ver:{folder_id}` (рекурсивно по всем потомкам) — старые ключи `photo_acl:{user_id}:{folder_id}:v{N}` автоматически «протухают» по TTL 300s, отдельный SCAN+DELETE не выполняется. `SCAN+DELETE` по шаблону `photo_acl:{user_id}:*` вызывается только из `invalidate_user_cache` (при изменении состава групп). Audit: `photos.permission_granted`.

---

### DELETE /photos/folders/{folder_id}/permissions/{subject_id} `[manager]`

Удаление гранта.

```
→ 204
```

---

### POST /photos/folders/{folder_id}/share `[manager]`

Создать публичную ссылку на папку. Хранится в `photo_folder_share_tokens`.

```json
{ "expires_in_days": 30 }
```
```
→ 201 FolderShareLinkPublic { id, folder_id, token, created_at, expires_at, public_url }
→ 403 / 404
```

---

### GET /photos/folders/{folder_id}/shares `[manager]`

Список активных публичных ссылок на папку.

```
→ 200 [ FolderShareLinkPublic ]
```

---

### GET /photos/folders/deleted `[admin]`

Список soft-deleted папок (для корзины).

```
→ 200 [ FolderPublic ]
```

---

### POST /photos/folders/{folder_id}/restore `[manager]`

Восстановить soft-deleted папку.

```
→ 200 FolderPublic
→ 404
```

---

### GET /photos/deleted `[reader+]`

Список soft-deleted фотографий текущего пользователя (+ admin видит все).

```
→ 200 PhotoList { items, total, page, per_page }
```

---

### POST /photos/{photo_id}/restore `[uploader+]`

Восстановить soft-deleted фото. Автор или `manager` папки.

```
→ 200 PhotoPublic
→ 403 / 404
```

---

### DELETE /photos/{photo_id}/purge `[admin]`

Жёсткое удаление фото и файлов с диска.

```
→ 204
→ 403 / 404
```

---

### POST /photos/trash/empty `[admin]`

Очистить всю корзину (фото и папки старше порога). Возвращает счётчики удалённых.

```
→ 200 { "photos_deleted": N, "folders_deleted": M }
```

---

### POST /photos/bulk `[uploader+]`

Групповые операции над несколькими фотографиями.

```json
{
  "action": "move|delete|tag",
  "photo_ids": ["uuid1", "uuid2"],
  "target_folder_id": "uuid",   // для move
  "tag_ids": ["uuid"]           // для tag
}
```
```
→ 200 BulkActionResponse { succeeded: N, failed: N, errors: [...] }
→ 403 / 422
```

---

### GET /photos/tags `[reader+]`

Список всех тегов фотогалереи.

```
→ 200 TagList { items: [ { id, name, slug } ] }
```

---

### POST /photos/tags `[editor+]`

Создать тег.

```json
{ "name": "Корпоратив" }
```
```
→ 201 TagPublic { id, name, slug, created_at }
→ 409 Уже существует
```

---

### DELETE /photos/tags/{tag_id} `[admin]`

Удалить тег (каскадно убирается из всех фото).

```
→ 204
```

---

### GET /photos/{photo_id}/tags `[viewer+]`

Теги конкретного фото.

```
→ 200 [ TagPublic ]
```

---

### PATCH /photos/{photo_id}/tags `[uploader+]`

Заменить теги фото (полная перезапись).

```json
{ "tag_ids": ["uuid1", "uuid2"] }
```
```
→ 200 [ TagPublic ]
→ 403 / 404
```

---

### GET /photos/storage-stats `[admin]`

Статистика использования дискового пространства по папкам.

```
→ 200 { "total_bytes": N, "folders": [ { "id", "name", "photo_count", "size_bytes" } ] }
```

---

### POST /photos/folders/{folder_id}/zip `[viewer+]`

Создать ARQ-задачу на генерацию ZIP-архива папки.

```
→ 201 ZipJobPublic { id, folder_id, status, created_at, expires_at }
```

---

### GET /photos/zip-jobs/{job_id} `[viewer+]`

Статус ZIP-задачи (`pending` / `running` / `done` / `error`). Polling с интервалом 2 сек.

```
→ 200 ZipJobPublic
→ 404
```

---

### GET /photos/zip-jobs/{job_id}/download `[viewer+]`

Скачать готовый ZIP-архив. Доступно только при `status=done`.

```
→ 200 Content-Type: application/zip
       Content-Disposition: attachment; filename*=UTF-8''...
→ 404 / 425 (задача ещё не готова)
```

---

### POST /photos/import/scan `[admin]`

Сканировать каталог `/data/photos/import/` и поставить файлы в ARQ-очередь для thumbnail-генерации.

```
→ 200 { "queued": N, "skipped": N }
```

---

### GET /photos/my-shares `[reader+]`

Список активных публичных ссылок текущего пользователя (и на фото, и на папки).

```
→ 200 MySharesResponse { photo_shares: [ ShareLinkPublic ], folder_shares: [ FolderShareLinkPublic ] }
```

---

### DELETE /photos/my-shares/photo/{token_id} `[reader+]`

Отозвать публичную ссылку на фото (только автор или admin).

```
→ 204
```

---

### DELETE /photos/my-shares/folder/{token_id} `[reader+]`

Отозвать публичную ссылку на папку (только автор или admin).

```
→ 204
```

---

### GET /photos/public-folder/{token}/info `[public]`

Информация о папке по публичному токену (без auth).

```
→ 200 { folder_id, name, description, photo_count }
→ 404 / 410
```

---

### GET /photos/public-folder/{token}/photos `[public]`

Список фотографий папки по публичному токену. Поддерживает пагинацию `?page=&per_page=`.

```
→ 200 PhotoList
→ 404 / 410
```

---

### GET /photos/public-folder/{token}/thumbnail/{photo_id}/{size} `[public]`

Thumbnail фото в публичной папке (без auth). `size` in `200|400|600|1000|1600`.

```
→ 200 (Nginx X-Accel-Redirect) Content-Type: image/webp
       Cache-Control: public, max-age=3600
→ 404 / 410
```

---

## Модули (Admin UI)

> Настройки внешних модулей (Nextcloud, Photos). Хранятся в `/data/settings/modules.json` (chmod 0600). TTL-кэш в памяти — 60 сек.

### GET /api/v1/modules `[reader+]`
Публичный список включённых модулей — для фронтенда (скрыть/показать разделы меню).
```json
→ 200 {
  "nextcloud": { "enabled": true },
  "photos": { "enabled": true }
}
```

### GET /admin/modules `[admin]`

Получить настройки всех модулей.

```
→ 200 {
  "nextcloud": { "enabled": false },
  "photos": {
    "enabled": true,
    "widget_limit": 8,
    "max_size_mb": 50,
    "allowed_mime": ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/gif"],
    "strip_gps": true
  }
}
```

---

### PUT /admin/modules/photos `[admin]`

```json
{
  "enabled": true,
  "widget_limit": 8,
  "max_size_mb": 50,
  "allowed_mime": ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"],
  "strip_gps": true
}
```

Пустой `allowed_mime` (или отсутствующий) сохраняет текущий список (не очищает). Все остальные поля перезаписываются.

```
→ 200 PhotosModuleOut
→ 422 Validation error
```

После сохранения — атомарная запись `/data/settings/modules.json` (через `tempfile + os.replace`, `chmod 0600`) и сброс TTL-кэша + локальных кэшей зависимых модулей.

---

### PUT /admin/modules/nextcloud `[admin]`

```json
{ "enabled": true }
```

```
→ 200 { "enabled": true }
```

---

### PUT /admin/modules/directories `[admin]`

Мастер-переключатель раздела «Справочники объектов» (вкладки в `/staff`). Когда `enabled=false` — весь раздел `/api/v1/directories/*` возвращает 404, объекты исключаются из глобального поиска, вкладки скрыты.

```json
{ "enabled": true }
```

```
→ 200 { "enabled": true }
→ 422 Validation error
```

После сохранения — атомарная запись `/data/settings/modules.json` + сброс TTL-кэша модулей.

---

### PUT /admin/modules/erp_sync `[admin]`

Мастер-переключатель модуля ERP-синхронизации дней рождения и пола сотрудников
(миграция 087). Когда `enabled=false` — весь контур `/api/v1/erp-sync/*` и
cron-поллинг ящика отключены (404). Сам импорт (pipeline, mailbox-poll, отчёты)
появится в PR2; в PR1 toggled-флаг + поля `users.birth_date`/`gender` уже
доступны для ручного редактирования.

```json
{ "enabled": true }
```

```
→ 200 { "enabled": true }
→ 422 Validation error
```

После сохранения — атомарная запись `/data/settings/modules.json` + сброс TTL-кэша модулей.

---

## §3.5b ERP-синхронизация (дни рождения и пол)

> Импорт `birth_date`/`gender` из ERP-выгрузки (1С). Полностью — в
> [`./erp-sync.md`](./erp-sync.md). Все endpoints гейтируются модулем
> `erp_sync.enabled` + `AdminDep`.

### GET /api/v1/erp-sync/settings `[admin]`
Текущие настройки ящика (singleton). Пароль write-only (`imap_password_set`).
```json
→ 200 {
  "enabled": true,
  "imap_host": "mail.company.local", "imap_port": 993, "imap_use_ssl": true,
  "imap_username": "erp@company.local", "imap_password_set": true,
  "imap_folder": "INBOX",
  "poll_interval_seconds": 900, "expected_interval_days": 4,
  "notify_emails": null,
  "poll_enabled": true,
  "mail_subject_filter": "Сотрудники",
  "mail_sender_filter": "erp@company.local",
  "mail_attachment_filter": null,
  "delete_after_fetch": false
}
```

### PUT /api/v1/erp-sync/settings `[admin]`
Обновление настроек. `imap_password` — write-only (пусто = оставить прежний
шифр). `poll_enabled` — отдельный флаг авто-поллинга (двойной гейтинг с
`modules.erp_sync.enabled`). Фильтры — CI-подстроки для общего ящика.
```json
← { /* ErpSyncSettingsIn */ }
→ 200 { /* ErpSyncSettingsOut */ }
```

### POST /api/v1/erp-sync/test `[admin]`
Проверка IMAP-подключения (login + select folder). Маскирует исключения
(aioimaplib echo'ит пароль в некоторых).
```json
→ 200 { "ok": true }
→ 200 { "ok": false, "error": "IMAP не настроен (host/username/password)." }
```

### POST /api/v1/erp-sync/run `[admin]`
Mailbox-trigger: ставит ARQ-задачу `run_erp_sync(triggered_by=manual)`.
Импорт выполнится в воркере немедленно (не ждать cron). Требует настроенный IMAP.
```json
→ 200 { "status": "queued", "job_id": "erp_sync:run:<admin_id>" }
→ 400 { "detail": "IMAP mailbox is not configured" }
→ 503 { "detail": "Task queue unavailable" }
```

### POST /api/v1/erp-sync/import-file `[admin]`
Multipart-upload файла → синхронный импорт через общий `run_import`. Не требует
mailbox — для первичной настройки/диагностики. `message_id=null` (каждый upload
новый). Лимит 50 MiB.
```json
← multipart: file=<report.xlsx>
→ 200 { "status": "processed", "run_id": 42 }
→ 400 { "detail": "Неподдерживаемый формат..." }
→ 413 { "detail": "Файл слишком большой..." }
```

### GET /api/v1/erp-sync/runs `[admin]`
Пагинированный список последних импортов (новые первыми). `report` (JSONB)
возвращается как есть — разделы changed/unmatched/ambiguous/conflicts/errors.
```
?limit=20&offset=0
→ 200 { "items": [ ErpSyncRunOut ], "total": 42 }
```

### GET /api/v1/erp-sync/runs/{run_id} `[admin]`
Один run с полным отчётом.
```
→ 200 { /* ErpSyncRunOut */ }
→ 404 { "detail": "Run not found" }
```

---

## §3.6 Файлы (Phase 5 — Nextcloud service account, ADR-032)

> Все операции через service account `portal-svc` (Basic Auth). Права — только в БД портала.
>
> **Уровни прав:** на папку — `viewer`/`editor`/`manager` (`file_folder_permissions`, наследование вверх по дереву). Дополнительно на **отдельный файл** можно выдать шару `viewer`/`editor` (`file_shares`, см. «Пофайловый шеринг» ниже). Эффективный доступ к байтам файла = `max(folder ACL, file share)` — резолвер `require_file_access`. `manager` на файл не выдаётся; re-sharing получателем невозможен by design.

### GET /api/v1/files/tree `[viewer+]`

Дерево папок, доступных пользователю (рекурсивно). Query: `?parent_id=<uuid>` (опционально).

```json
→ 200 {
  "items": [
    {
      "id": "uuid",
      "parent_id": null,
      "name": "HR",
      "nc_path": "HR",
      "permission": "viewer",
      "inherit_permissions": true,
      "children": [
        { "id": "uuid2", "parent_id": "uuid", "name": "Docs", "nc_path": "HR/Docs", "permission": "editor", "inherit_permissions": true, "children": [] }
      ]
    }
  ]
}
```

### GET /api/v1/files/folders/{id} `[viewer+]`

Содержимое папки: метаданные папки + список файлов из Nextcloud WebDAV + хлебные крошки.

```json
→ 200 {
  "folder": { "id": "uuid", "parent_id": null, "name": "HR", "nc_path": "HR", "description": null, "permission": "editor", "inherit_permissions": true, "children_count": 0, "created_at": "...", "updated_at": "..." },
  "items": [
    { "name": "report.pdf", "nc_path": "HR/report.pdf", "is_dir": false, "size_bytes": 12345, "mime_type": "application/pdf", "last_modified": "...", "etag": "abc", "uploaded_at": "...", "uploaded_by": { "id": "uuid", "full_name": "Иванов Иван", "avatar_url": null } }
  ],
  "breadcrumbs": [],
  "nc_error": false
}
```

### POST /api/v1/files/folders `[editor+]`

```json
{ "name": "HR", "parent_id": null, "description": "HR documents" }
→ 201 { "id": "uuid", "name": "HR", "nc_path": "HR", ... }
```

### PATCH /api/v1/files/folders/{id} `[manager]`

```json
{ "name": "Human Resources", "description": "Updated" }
→ 200 { ...FileFolderPublic }
```

### DELETE /api/v1/files/folders/{id} `[manager]`

Soft delete + удаление из Nextcloud WebDAV. Query: `?hard=false` (только soft).

```
→ 204
```

### POST /api/v1/files/folders/{id}/upload `[editor+]`

Multipart file upload (несколько файлов). Rate-limit: `20/мин/user`. Поддерживает заголовок `Idempotency-Key` (результат кэшируется в Redis на 24ч).

MIME определяется по содержимому (`python-magic`) и проверяется против allowlist + явного blocklist (HTML/SVG/JS/исполняемые/скрипты отклоняются). Лимит размера — системная настройка `max_upload_size_mb`. Один commit на всю группу: при сбое БД залитые файлы переходят в `failed` (drift-аудит).

```json
→ 200 {
  "uploaded": [{ "name": "file.pdf", "nc_path": "HR/file.pdf", "size_bytes": 1024, "success": true, "error": null }],
  "failed": [{ "name": "evil.svg", "nc_path": "HR/evil.svg", "size_bytes": 0, "success": false, "error": "File type not allowed: image/svg+xml" }]
}
```

### GET /api/v1/files/download `[viewer+ | file share]`

Streaming download. Query: `?folder_id=<uuid>&filename=<имя_файла>`. Доступ резолвится через `require_file_access` = `max(folder ACL, file share)`.

```
→ 200 StreamingResponse (Content-Disposition: attachment; filename*=UTF-8''...)
→ 404 Файл не найден
→ 502 Ошибка Nextcloud
```

### GET /api/v1/files/preview `[viewer+ | file share]`

Inline preview (PDF, изображения). Query: `?folder_id=<uuid>&filename=<имя_файла>`. Доступ резолвится через `require_file_access` = `max(folder ACL, file share)`.
Разрешённые MIME: `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/avif`, `application/pdf`.

```
→ 200 StreamingResponse (Content-Disposition: inline; Content-Security-Policy: sandbox)
→ 415 Тип файла не поддерживается для preview
→ 502 Ошибка Nextcloud
```

### DELETE /api/v1/files/file `[editor+]`

Query: `?folder_id=<uuid>&filename=<имя_файла>`.

```
→ 204
```

### POST /api/v1/files/folders/{id}/bulk-delete `[editor+]`

Массовое удаление файлов из папки. **Естественно идемпотентен** — `Idempotency-Key` не используется (повтор → NC 404 → success).

- Лимиты: `1 ≤ filenames ≤ 100`. Rate-limit: `3/min` per user.
- In-flight guard: Redis SETNX `bulk:inflight:{user_id}` (TTL 60s). Параллельный bulk → 409 `bulk_in_progress`.
- Невалидные имена (traversal/нулевые символы и пр.) → попадают в `failed` с `error="invalid_name"`, остальные обрабатываются.
- NC 404 трактуется как `success=true` (файла уже нет).
- Один аудит-event `files.bulk_deleted` с `metadata = { folder_id, count_total, count_deleted, count_failed, nc_404_count, db_commit_failed }`.

```json
{ "filenames": ["a.txt", "b.pdf"] }
→ 200 {
  "deleted": [{ "name": "a.txt", "success": true, "error": null }],
  "failed":  [{ "name": "b.pdf", "success": false, "error": "nc_error:502" }]
}
→ 409 { "detail": "bulk_in_progress" }
→ 422 (validation: empty / over-limit)
```

Возможные значения `error` в `failed`: `invalid_name`, `nc_error:{status}`.

### POST /api/v1/files/folders/{id}/bulk-move `[editor+]`

Массовое перемещение файлов в другую папку. **Per-file commit** — частичный успех допустим. Естественно идемпотентен (Overwrite=F).

- Требует `editor` на src и target папке.
- Лимиты: `1 ≤ filenames ≤ 100`. Rate-limit: `3/min` per user.
- In-flight guard: тот же Redis-флаг (один параллельный bulk на пользователя).
- `target_folder_id == folder_id` → 422 `same_folder`.
- NC 412 (Overwrite=F конфликт имени) → `error="name_conflict"`.
- NC 404 → `error="not_found"`.
- При сбое БД после успешного MOVE — пишется warning `files.bulk_move_drift` + audit; для пользователя файл считается перемещённым.
- `uploaded_by` не меняется (история факта move хранится в `audit_log.actor_id`); для импортированных файлов создаётся `FileItem` с `uploaded_by = NULL`.
- Один аудит-event `files.bulk_moved` с `metadata = { src_folder_id, target_folder_id, count_total, count_moved, count_failed, count_drift }`.

```json
{ "filenames": ["a.txt"], "target_folder_id": "uuid" }
→ 200 {
  "moved":  [{ "name": "a.txt", "new_name": null, "success": true, "error": null }],
  "failed": [{ "name": "b.txt", "new_name": null, "success": false, "error": "name_conflict" }]
}
→ 409 { "detail": "bulk_in_progress" }
→ 422 (validation / same_folder)
```

Возможные значения `error` в `failed`: `invalid_name`, `name_conflict`, `not_found`, `nc_error:{status}`.

### POST /api/v1/files/open `[viewer+ | file share]`

Открыть файл в Collabora Online. Query: `?folder_id=<uuid>&filename=<имя_файла>`. Доступ резолвится через `require_file_access` = `max(folder ACL, file share)`; `can_write` = true при эффективном уровне `editor+`.

```json
→ 200 { "type": "collabora", "url": "https://collabora.company.local/wopi/...", "display_name": "Иванов Иван", "can_write": true }
```

### GET /api/v1/files/folders/{id}/permissions `[manager]`

Первым элементом всегда возвращается **создатель папки** с `is_creator=true`, `id=null`, `permission="manager"` (по образцу Базы знаний). Если создатель уже есть в `file_folder_permissions` как user — записи дедуплицируются (мердж). Создателя нельзя изменить/удалить (409).

```json
→ 200 { "items": [
  { "id": null, "folder_id": "uuid", "subject_type": "user", "subject_id": "creator-uuid", "subject_name": "Петров", "email": "petrov@company.local", "permission": "manager", "is_creator": true },
  { "id": "uuid", "folder_id": "uuid", "subject_type": "user", "subject_id": "kc-uuid", "subject_name": "Иванов", "email": null, "permission": "editor", "granted_by": "uuid", "created_at": "...", "is_creator": false }
] }
```

### POST /api/v1/files/folders/{id}/permissions `[manager]`

Выдача права создателю папки запрещена → `409 "Cannot modify creator's permission"`.

```json
{ "subject_type": "user", "subject_id": "kc-uuid", "subject_name": "Иванов Иван", "permission": "editor" }
→ 201 { ...PermissionPublic }
→ 409 { "detail": "Cannot modify creator's permission" }
```

### DELETE /api/v1/files/folders/{id}/permissions/{perm_id} `[manager]`

Удаление права создателя папки запрещено → `409 "Cannot revoke creator's permission"`.

```
→ 204
→ 409 { "detail": "Cannot revoke creator's permission" }
```

### PATCH /api/v1/files/folders/{id}/inheritance `[manager]`

Включить/выключить наследование прав от родительской папки. При `inherit_permissions = false` резолв ACL не поднимается выше этой папки.

```json
{ "inherit_permissions": false }
→ 200 { ...FileFolderPublic, "inherit_permissions": false }
```

### GET /api/v1/files/users/search

**Назначение:** Поиск пользователей и групп (Keycloak) + синтетическая группа «Все пользователи» для назначения прав на файловые папки.

**Query:** `q` (строка поиска, 1–100 символов)

**Auth:** роль `editor` или `admin` (иначе 403)

**Response 200:** `[{ "subject_type": "user|group", "subject_id": "string", "subject_name": "string", "email": "string|null" }]`

---

## Пофайловый шеринг (`file_shares`)

> Адресная выдача доступа к **одному файлу** конкретному пользователю/группе/«Всем пользователям» без открытия всей папки. Управлять шарами может только `manager` папки (или admin). На файл выдаётся только `viewer`/`editor`. Шары дублируются в `/data/settings/files-shares.json` и восстанавливаются на старте воркера. `filename` передаётся URL-энкодом (на бэке `sanitize_name`).

### POST /api/v1/files/folders/{folder_id}/files/{filename}/shares `[manager папки]`

Создать/обновить (upsert по `(folder_id, filename, subject_id)`) шару файла. Существование файла в Nextcloud проверяется (404, если нет). Rate-limit: `20/min`. Аудит: `files.file_shared` / `files.file_share_updated`. Уведомления получателю (in-app + email).

```json
{ "subject_type": "user", "subject_id": "kc-uuid", "subject_name": "Иванов Иван", "permission": "editor", "expires_in_days": 7 }
→ 201 { "id": "uuid", "folder_id": "uuid", "filename": "report.pdf", "nc_path": "HR/report.pdf", "subject_type": "user", "subject_id": "kc-uuid", "subject_name": "Иванов Иван", "permission": "editor", "shared_by": "uuid", "created_at": "...", "expires_at": "..." }
→ 404 { "detail": "File not found" }
```

### GET /api/v1/files/folders/{folder_id}/files/{filename}/shares `[manager папки]`

Активные шары файла («С кем поделились»).

```json
→ 200 { "items": [ { ...FileSharePublic } ] }
```

### DELETE /api/v1/files/folders/{folder_id}/files/{filename}/shares/{share_id} `[manager папки]`

Мягкий отзыв (`revoked_at = now`). Аудит: `files.file_share_revoked`.

```
→ 204
→ 404 { "detail": "Share not found" }
```

### GET /api/v1/files/shares/my `[любой авторизованный]`

Активные шары, которые выдал текущий пользователь (`shared_by = me`).

```json
→ 200 { "items": [ { "id": "uuid", "folder_id": "uuid", "filename": "report.pdf", "nc_path": "HR/report.pdf", "folder_name": "HR", "subject_type": "user", "subject_id": "kc-uuid", "subject_name": "Иванов", "permission": "editor", "created_at": "...", "expires_at": "..." } ] }
```

### GET /api/v1/files/shares/shared-with-me `[любой авторизованный]`

Файлы, расшаренные текущему пользователю (по `subject_ids_for_user`, активные, не просроченные). Папка-контейнер в общем дереве не появляется; открытие — через `download`/`preview`/`open`.

```json
→ 200 { "items": [ { "id": "uuid", "folder_id": "uuid", "filename": "report.pdf", "nc_path": "HR/report.pdf", "folder_name": "HR", "permission": "viewer", "shared_by_name": "Петров", "created_at": "...", "expires_at": null } ] }
```

### GET /api/v1/files/admin/shares `[admin]`

Пагинированный реестр всех шеров. Query: `?subject_id=<str>&folder_id=<uuid>&active_only=<bool>&limit=<1..200>&offset=<int>`.

```json
→ 200 { "items": [ { "id": "uuid", "folder_id": "uuid", "filename": "report.pdf", "nc_path": "HR/report.pdf", "folder_name": "HR", "subject_type": "user", "subject_id": "kc-uuid", "subject_name": "Иванов", "permission": "editor", "shared_by": "uuid", "shared_by_name": "Петров", "created_at": "...", "expires_at": null, "revoked_at": null } ], "total": 1, "limit": 50, "offset": 0 }
```

---

### POST /api/v1/files/sync `[admin]`

**Назначение:** Ручной запуск импорта дерева папок из Nextcloud в БД портала. Идемпотентен (существующие по `nc_path` папки пропускаются); soft-deleted папки не восстанавливаются. Права восстанавливаются из `files-acl.json`.

**Auth:** [admin]

**Response 200:** `{ "created": 42, "skipped": 10, "errors": [] }`

---

## Справочники объектов (`/api/v1/directories`)

> Универсальный движок справочников объектов с контактами (подробности — [`./directories.md`](./directories.md), первый кейс — «Флот»). Встраивается вкладками в `/staff`. Код: `app/api/directories.py`, схемы — `app/schemas/object_directory.py`, сервис — `app/services/directories.py`.
>
> **Гейтинг двухуровневый:** мастер-флаг `modules.json` (`directories.enabled`) выключен → весь раздел 404 (`PUT /admin/modules/directories`); отдельный тип с `enabled=false` → его вкладка скрыта для обычных пользователей, но видна editor/admin.
>
> **Доступ:** чтение (`GET`) — любой авторизованный; мутации типов, объектов, контактов и аватаров — `editor`/`admin`. Каждая мутация → `audit_log` (`resource_type=directory`) после commit. Объекты участвуют в глобальном поиске (`type=directory_entry`) — только по `name`.

### GET /directories `[reader+]`

Список типов-справочников (вкладок). Для editor/admin включает типы с `enabled=false` (`include_disabled`), для остальных — только включённые.

```
→ 200 {
  "items": [
    {
      "id": "uuid", "slug": "fleet", "label_ru": "Флот", "label_en": "Fleet",
      "icon": "boat", "description": "…",
      "field_schema": [
        { "key": "imo", "label_ru": "IMO", "label_en": "IMO", "type": "text", "required": false, "sort_order": 0 }
      ],
      "channels": [
        { "key": "inmarsat", "label_ru": "Inmarsat", "label_en": "Inmarsat", "sort_order": 2 }
      ],
      "enabled": true, "sort_order": 0,
      "created_at": "…", "updated_at": "…"
    }
  ],
  "total": 1
}
```

`field.type ∈ {text, number, email, url, multiline}`. `key` — `^[a-z][a-z0-9_]*$`.

### POST /directories `[editor+]`

Создать тип. Body: `slug` (`^[a-z][a-z0-9_-]*$`), `label_ru`, опц. `label_en`/`icon`/`description`/`field_schema`/`channels`/`enabled`/`sort_order`. Дубликаты `key` в `field_schema`/`channels` → 422.

```
→ 201 DirectoryPublic
→ 409 slug уже существует
→ 422 Validation error / duplicate keys
```

### PATCH /directories/{directory_id} `[editor+]`

Частичное обновление типа (включая `field_schema`/`channels`/`enabled`).

```
→ 200 DirectoryPublic
→ 404 not found / module off
```

### DELETE /directories/{directory_id} `[editor+]`

Soft-delete типа (`deleted_at`).

```
→ 204 No Content
```

### GET /directories/{slug}/entries `[reader+]`

Список объектов справочника. Query: `?q=` (поиск только по `name`), `limit` (1..500, default 100), `offset`. Soft-deleted исключены, сортировка по `sort_order`.

```
→ 200 { "items": [EntryPublic…], "total": N, "limit": 100, "offset": 0 }
```

`EntryPublic`: `id`, `directory_id`, `name`, `folder_id`, `folder_name` (имя привязанной папки `/files`), `attributes` (`{key: value}`), `note`, `sort_order`, `created_by`, `created_at`, `updated_at`, `contacts` (`[{id, role, channel, label, value, sort_order}]`).

### GET /directories/{slug}/entries/{entry_id} `[reader+]`

Один объект с контактами.

```
→ 200 EntryPublic
→ 404 not found / type disabled (для не-editor)
```

### POST /directories/{slug}/entries `[editor+]`

Создать объект. Body: `name`, опц. `folder_id`/`attributes`/`note`/`sort_order`/`contacts`. `folder_id` (если задан) обязан ссылаться на существующую неудалённую папку `/files` (иначе `422`). `attributes` валидируются против `field_schema` типа (тип, `required`, отсутствие лишних ключей); `contact.channel` обязан входить в `directory.channels`.

```
→ 201 EntryPublic
→ 422 attributes не соответствуют field_schema / channel вне channels
```

### PATCH /directories/{slug}/entries/reorder `[editor+]`

Массовое переупорядочивание объектов типа. Body: `{ "items": [{ "id": uuid, "sort_order": int }] }`. Все `id` обязаны принадлежать активным (не удалённым) объектам типа, иначе `404` и ничего не меняется. Объявлен раньше `/{entry_id}`, чтобы `reorder` не перехватывался как `entry_id`.

```
→ 204 No Content
→ 404 один или несколько id не найдены
```

### PATCH /directories/{slug}/entries/{entry_id} `[editor+]`

Частичное обновление объекта; передача `contacts` заменяет набор целиком.

```
→ 200 EntryPublic
```

### DELETE /directories/{slug}/entries/{entry_id} `[editor+]`

Soft-delete объекта.

```
→ 204 No Content
```

### GET /directories/{slug}/export `[reader+]`

Экспорт объектов. Query `?format=csv|xlsx|pdf` (default `csv`). CSV/XLSX собираются в сервисе; PDF — через `screenshot-service` (`POST /pdf`). Ответ — `attachment` (`Content-Disposition`), `Cache-Control: no-store`.

```
→ 200  (text/csv | xlsx | application/pdf)
→ 422  format не из csv|xlsx|pdf
```

---

## Техподдержка (Helpdesk)

> **Полное описание API — в [`./helpdesk.md`](./helpdesk.md) §4** (все эндпоинты,
> параметры, статусы, форматы). Здесь — только краткий список. Префикс
> `/api/v1/helpdesk`. Авторизация обязательна; весь роутер обёрнут в
> `require_helpdesk_module` (404, если мастер-флаг `helpdesk.enabled=false`).
> Auth-deps: `CurrentUser` (свой), `HelpdeskAgentDep` (агент/админ), `AdminDep`
> (админ). Все мутации пишут `audit_log` (`helpdesk.*`).

### Инициатор (`CurrentUser`)

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/tickets` | Создать заявку (`multipart/form-data`: `subject`, `description?`, `description_html?`, `files[]`). С 2026-07: rich-редактор TipTap — `description_html` (sanitized nh3), `description` (plain) optional и деривируется из HTML для FTS/email; валидация «plain ИЛИ html непуст». Обратно-совместим: старые клиенты (только `description`) работают. Rate-limit 5/мин. |
| `GET` | `/tickets/my` | Свои заявки (`?status`, `?unassigned`, `?assigned`, пагинация); `unread: bool` в каждой строке |
| `GET` | `/tickets/my/counts` | `{active: N}` — свои тикеты в new/open/pending (для бейджа меню) |
| `GET` | `/tickets/my/{id}` | Своя заявка с публичными сообщениями + `requester_profile` |
| `POST` | `/tickets/my/{id}/read` | Отметить прочитанным (снять подсветку ответов агентов) |
| `POST` | `/tickets/my/{id}/messages` | Ответ (`Form`: `body_text`, `files[]`). Rate-limit 20/мин. |
| `GET` | `/attachments/{id}` | Скачать вложение (`StreamingResponse`); автор/агент/админ |
| `POST` | `/draft-attachments` | Draft inline-картинка для формы **создания** заявки (`multipart`: `file`). Возвращает `{url, filename}` — URL вставляется в `description_html`, бэкенд при `create_ticket` переносит файл в `TKT-{number}/inline/` и переписывает `src` на `/tickets/{id}/inline-media/{name}`. ACL: только владелец. Лимит 20 активных/юзер; TTL 24ч (cron cleanup). Rate-limit 20/мин. |
| `GET` | `/draft-attachments/{id}` | Раздать draft-картинку (через nginx `X-Accel-Redirect`); только владелец, иначе 404. |

### Агент (`HelpdeskAgentDep`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/tickets` | Инбокс: фильтры `status`/`assignee`/`unassigned`/`source`/`active_only`/`q` (FTS — миграция 078), пагинация, `unread: bool` |
| `GET` | `/tickets/counts` | `{active: N}` — тикеты, назначенные агенту, в new/open/pending (для бейджа «Инбокс поддержки») |
| `GET` | `/users/search` | Поиск пользователя по справочнику (Keycloak) для CC-селектора «Ответить всем» (`?q=`, `?limit=`). `[{user_id, full_name, email}]`. `<3 символов` → `[]`. Доступ: любой авторизованный (parent-router gate `require_helpdesk_module`). Симметрично `meetings/participants/search`, но helpdesk-принадлежный. |
| `GET` | `/tickets/{id}` | Карточка (`TicketAgentOut`, все сообщения + служебные поля + `requester_profile`) |
| `POST` | `/tickets/{id}/messages` | Ответ (`Form`: `body_text`, `body_html?`, `files[]`) → `pending` + outbound email через outbox. |
| `POST` | `/tickets/{id}/inline-media` | Загрузка inline-картинки для TipTap-редактора ответа (`multipart`, поле `file`) → `{url, filename}` |
| `GET` | `/tickets/{id}/inline-media/{filename}` | Отдача inline-картинки (nginx `X-Accel-Redirect`, `no-store`+`nosniff`) |
| `POST` | `/tickets/{id}/assign` | Назначить (`assignee_user_id`) |
| `POST` | `/tickets/{id}/take` | Взять на себя (409 если уже назначен) |
| `PATCH` | `/tickets/{id}/status` | Сменить статус (409 на запрещённый переход) |
| `POST` | `/tickets/{id}/reopen` | Reopen закрытой (409 из не-`closed`) |
| `POST` | `/tickets/{id}/read` | Отметить прочитанным для пары `(ticket, agent)` (UPSERT `last_seen_at`) |

### Админ (`AdminDep`)

| Метод | Путь | Назначение |
|---|---|---|
| `GET/POST/PATCH/DELETE` | `/agents[/{user_id}]` | CRUD агентов поддержки (аудит `helpdesk.agent_*`) |
| `GET/PUT` | `/settings/mailbox` | Singleton IMAP-настроек support-ящика; `imap_password_enc` Fernet (write-only) |
| `POST` | `/settings/mailbox/test` | Проверка IMAP-соединения → `{ok, detail}` (маскированная ошибка) |
| `GET/PUT` | `/settings/digest` | Singleton расписания сводки (`enabled`, `digest_hour`/`digest_minute`/`digest_schedule`) |
| `GET/PUT` | `/settings/max-bot` | Singleton MAX-бота (`enabled`, `bot_token_set`, `chat_id`, `configured`). Токен write-only. При `enabled=True` требует токен+chat_id (400 иначе). |
| `POST` | `/settings/max-bot/test` | End-to-end: отправляет реальное сообщение в чат через MAX Bot API. На неудачу — маскированная ошибка с подсказкой по HTTP-коду (404→бот не участник чата, 401→токен, 403→права). |

> **MAX-messenger** (миграция 081): при `enabled=True` и новой заявке
> (web или email-ingress) в общий чат поддержки уходит оповещение
> (№+тема+заявитель+источник+превью тела 500 символов + inline-кнопка
> «Открыть на портале» → абсолютный URL из `SystemSettings.portal_base_url`).
> Доставка — через отдельный transactional outbox `messenger_outbox`
> (retry/backoff/DLQ, mirror `email_outbox`). Подробнее —
> [`./helpdesk.md`](./helpdesk.md) §«MAX-messenger оповещения».

---

## Email-outbox (admin)

> Инфраструктура — в [`./email.md`](./email.md). Admin-endpoint'ы для наблюдения
> за очередью исходящих писем и ручного retry/cancel (всё `[admin]`).

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/admin/email-outbox` | Список писем (`?status`, `?kind`, пагинация) |
| `GET` | `/admin/email-outbox/_/stats` | Сводка: счётчики по статусам |
| `GET` | `/admin/email-outbox/{id}` | Карточка письма (тело, ошибки, попытки) |
| `POST` | `/admin/email-outbox/{id}/retry` | Принудительный retry (сбрасывает `status=PENDING`) |
| `POST` | `/admin/email-outbox/{id}/cancel` | Отмена (`status=CANCELLED`) |

---

## Генератор email-подписей (`/api/v1/signature`)

> Stateless-рендер HTML-подписи сотрудника из формы (матрица «устройство × язык → логотип/вёрстка», внешние mage.ru-логотипы, предзаполнение из профиля). Модуль обвязан мастер-флагом `signature.enabled`. Полная спецификация — [`./signature.md`](./signature.md); точные схемы/параметры — [`./api-contracts.generated.md`](./api-contracts.generated.md) §signature.

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| `GET` | `/signature/config` | Публичная конфигурация генератора (список городов/устройств/языков для формы) | `CurrentUser` |
| `POST` | `/signature/generate` | Сгенерировать HTML-подпись из body формы (возвращает HTML-строку для preview) | `CurrentUser` |
| `POST` | `/signature/download` | Скачать подпись как `.htm`-файл | `CurrentUser` |
| `GET` | `/signature/admin/settings` | Admin-настройки городов/телефонов/домена | `admin` |
| `PUT` | `/signature/admin/settings` | Обновить admin-настройки | `admin` |

---

## Обратная связь (`/api/v1/feedback`)

> Модуль обращений сотрудников (баги/пожелания): статус-машина, вложения, ответы админа. Полная спецификация — [`./feedback.md`](./feedback.md); точные схемы/параметры — [`./api-contracts.generated.md`](./api-contracts.generated.md) §feedback.

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| `POST` | `/feedback` | Создать обращение (текст + опц. вложения) | `CurrentUser` |
| `GET` | `/feedback/my` | Свои обращения | `CurrentUser` |
| `GET` | `/feedback/my/{feedback_id}` | Карточка своего обращения | `CurrentUser` |
| `GET` | `/feedback` | Все обращения (админ-лента с фильтрами) | `admin` |
| `GET` | `/feedback/{feedback_id}` | Карточка обращения | `admin` |
| `POST` | `/feedback/{feedback_id}/reply` | Ответ админа (с опц. вложениями) | `admin` |
| `PATCH` | `/feedback/{feedback_id}/status` | Сменить статус (`new`/`in_progress`/`resolved`/`closed`) | `admin` |
| `POST` | `/feedback/{feedback_id}/attachments` | Загрузить вложение к обращению | `CurrentUser` (автор) / `admin` |
| `GET` | `/feedback/{feedback_id}/attachments/{attachment_id}` | Скачать вложение | `CurrentUser` (автор) / `admin` |
| `DELETE` | `/feedback/{feedback_id}/attachments/{attachment_id}` | Удалить вложение | `admin` |

---

## Переговорные (`/api/v1/meetings`)

> Бронирование переговорных комнат (физических/виртуальных), серии встреч, iCal-уведомления, конфликт-чек через PG EXCLUDE-констрейнт. Полная спецификация — [`./meetings.md`](./meetings.md); точные схемы/параметры — [`./api-contracts.generated.md`](./api-contracts.generated.md) §meetings.

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| `GET` | `/meetings/rooms` | Список активных комнат | `CurrentUser` |
| `POST` | `/meetings/rooms` | Создать комнату | `admin` |
| `GET`/`PUT`/`DELETE` | `/meetings/rooms/{room_id}` | CRUD комнаты | `CurrentUser` / `admin` / `admin` |
| `GET` | `/meetings/bookings` | Список бронирований (с фильтром по комнате/периоду) | `CurrentUser` |
| `POST` | `/meetings/bookings` | Создать бронирование (конфликт-чек, опц. серия) | `CurrentUser` |
| `GET` | `/meetings/bookings/my` | Свои бронирования | `CurrentUser` |
| `GET`/`PUT`/`DELETE` | `/meetings/bookings/{booking_id}` | CRUD бронирования | `CurrentUser` (владелец) |
| `GET` | `/meetings/participants/search` | Поиск участников для приглашения (Keycloak + внешние по email) | `CurrentUser` |
| `PUT`/`DELETE` | `/meetings/series/{series_id}` | Управление серией встреч | `CurrentUser` (владелец) |
| `GET` | `/meetings/series/{series_id}/count` | Кол-во встреч в серии | `CurrentUser` |

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
| 403 | Нет прав (роль или ACL папки) |
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
