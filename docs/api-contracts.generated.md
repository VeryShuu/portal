<!-- AUTO-GENERATED — do not edit manually. Run: cd backend && python -m scripts.generate_api_contracts_doc --output ../docs/api-contracts.generated.md -->
<!-- Generated: 2026-05-14 14:07 UTC -->

# API Contracts (auto-generated)

> Generated from FastAPI OpenAPI spec.  
> Source of truth: `./docs/api-contracts.generated.md` (auto) and `./docs/api-contracts.md` (curated).  
> Base URL: `/api/v1/`

---

## Table of Contents

- [analytics](#analytics)
- [audit](#audit)
- [auth](#auth)
- [bookmarks](#bookmarks)
- [bootstrap](#bootstrap)
- [branding](#branding)
- [feedback](#feedback)
- [files](#files)
- [health](#health)
- [keycloak-admin](#keycloak-admin)
- [knowledge-base](#knowledge-base)
- [links](#links)
- [modules](#modules)
- [nc-federation](#nc-federation)
- [news](#news)
- [news-categories](#news-categories)
- [notifications](#notifications)
- [photos](#photos)
- [search](#search)
- [system-settings](#system-settings)
- [user-attribute-mappings](#user-attribute-mappings)
- [users](#users)

---

## analytics

### `GET /api/v1/analytics/dashboard`

**Сводный дашборд (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/departments`

**Активность по отделам**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/top-articles`

**Топ статей KB по просмотрам**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/top-files`

**Топ файлов по скачиваниям (audit_log)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/top-news`

**Топ новостей по просмотрам**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of object |
| 422 | Validation Error | `HTTPValidationError` |

---

## audit

### `GET /api/v1/audit`

**Журнал аудита (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | query | `any` |  |  |
| `event_type` | query | `any` |  |  |
| `resource_type` | query | `any` |  |  |
| `ip_address` | query | `any` |  |  |
| `date_from` | query | `any` |  |  |
| `date_to` | query | `any` |  |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/audit/event-types`

**Уникальные типы событий (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of string |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/audit/export.csv`

**Экспорт журнала в CSV (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | query | `any` |  |  |
| `event_type` | query | `any` |  |  |
| `resource_type` | query | `any` |  |  |
| `ip_address` | query | `any` |  |  |
| `date_from` | query | `any` |  |  |
| `date_to` | query | `any` |  |  |
| `q` | query | `any` |  |  |
| `max_rows` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/audit/queue/depth`

**Размер очереди audit_queue в Redis**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

---

## auth

### `GET /api/v1/auth/callback`

**OIDC callback — exchange code for session**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `code` | query | `string` | ✓ |  |
| `state` | query | `string` | ✓ |  |
| `error` | query | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/auth/config`

**Конфигурация аутентификации (без авторизации)**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |

### `POST /api/v1/auth/local/login`

**Локальный вход по email + паролю**

**Request Body**

Content-Type: `application/json` — schema: `LocalLoginRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✓ |  |
| `password` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/auth/login`

**Redirect to Keycloak login**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `redirect` | query | `string` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/auth/logout`

**GET logout (SLO front-channel)**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |

### `POST /api/v1/auth/logout`

**Logout — destroy session + SLO**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/auth/me`

**Current user info from session**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/auth/refresh`

**Refresh access token silently**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

---

## bookmarks

### `GET /api/v1/bookmarks`

**Список закладок пользователя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BookmarkList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/bookmarks`

**Создать закладку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateBookmarkRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `group_name` | any |  |  |
| `resource_id` | any |  |  |
| `resource_type` | any |  |  |
| `title` | string | ✓ |  |
| `url` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `BookmarkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/bookmarks/favicon`

**Проксировать favicon сайта (с кэшем 7 дней)**

Возвращает favicon.ico целевого домена, загруженный на сервере.

Кэш в Redis: 7 дней для успешных ответов, 1 день для недоступных доменов.
Endpoint требует аутентификации, но только GET — не требует CSRF-токена.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `url` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/bookmarks/reorder`

**Изменить порядок закладок**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `ReorderBookmarksRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `items` | array of `BookmarkReorderItem` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/bookmarks/{bookmark_id}`

**Удалить закладку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `bookmark_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

---

## bootstrap

### `GET /api/v1/bootstrap`

**Bootstrap данные для SPA**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BootstrapOut` |
| 422 | Validation Error | `HTTPValidationError` |

---

## branding

### `POST /api/v1/admin/branding/favicon`

**Загрузить favicon портала**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_favicon_api_v1_admin_branding_favicon_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/admin/branding/favicon`

**Сбросить favicon к умолчанию**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/branding/login-bg`

**Загрузить фон страницы входа**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_login_bg_api_v1_admin_branding_login_bg_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/admin/branding/login-bg`

**Сбросить фон страницы входа**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/branding/logo`

**Загрузить логотип портала**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_logo_api_v1_admin_branding_logo_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/admin/branding/logo`

**Сбросить логотип к умолчанию**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/branding/settings`

**Сохранить настройки оформления**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `BrandingSettings`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `accent_color` | string |  |  |
| `banner_enabled` | boolean |  |  |
| `banner_expires_at` | any |  |  |
| `banner_text` | string |  |  |
| `banner_type` | string |  |  |
| `logo_hidden` | boolean |  |  |
| `portal_name` | string |  |  |
| `portal_tagline` | string |  |  |
| `welcome_subtitle` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BrandingSettings` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/email-settings`

**Получить настройки email**

Возвращает текущие настройки SMTP. Пароль не возвращается, только флаг password_set.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `EmailSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/email-settings`

**Сохранить настройки email**

Сохраняет настройки SMTP в /data/branding/email-settings.json.
Переопределяет значения из .env — они больше не используются для отправки.
Если password передан как null или '***' — существующий пароль не меняется.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `EmailSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from_address` | string |  |  |
| `host` | string |  |  |
| `password` | any |  | Pass null or '***' to keep existing password; pass '' to clear; pass new value to update |
| `port` | integer |  |  |
| `use_starttls` | boolean |  |  |
| `use_tls` | boolean |  |  |
| `username` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `EmailSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/email-settings/test`

**Отправить тестовое письмо**

Отправляет тестовое письмо используя сохранённые SMTP-настройки.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `EmailTestRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `to` | string | ✓ | Email address to send test message to |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/branding/favicon`

**Получить favicon портала**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |

### `GET /api/v1/branding/login-bg`

**Получить фон страницы входа**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |

### `GET /api/v1/branding/logo`

**Получить логотип портала**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |

### `GET /api/v1/branding/settings`

**Настройки оформления портала**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BrandingSettingsOut` |

---

## feedback

### `GET /api/v1/feedback`

**Все обращения (админ)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `status` | query | `any` |  |  |
| `category` | query | `any` |  |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackAdminListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/feedback`

**Создать обращение**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `FeedbackIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | `FeedbackCategory` | ✓ |  |
| `message` | string |  |  |
| `page_url` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FeedbackOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/feedback/my`

**Мои обращения**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `status` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/feedback/my/{feedback_id}`

**Моё обращение**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/feedback/{feedback_id}`

**Обращение (админ)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackAdminOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/feedback/{feedback_id}/attachments`

**Прикрепить файл к обращению**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_feedback_attachment_api_v1_feedback__feedback_id__attachments_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FeedbackAttachmentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/feedback/{feedback_id}/attachments/{attachment_id}`

**Скачать вложение обращения**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `attachment_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/feedback/{feedback_id}/attachments/{attachment_id}`

**Удалить вложение обращения**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `attachment_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/feedback/{feedback_id}/reply`

**Ответить на обращение**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `FeedbackReplyIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FeedbackReplyOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/feedback/{feedback_id}/status`

**Изменить статус обращения**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `feedback_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `FeedbackStatusIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `FeedbackStatus` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackAdminOut` |
| 422 | Validation Error | `HTTPValidationError` |

---

## files

### `GET /api/v1/files/download`

**Download File**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | query | `string` | ✓ |  |
| `filename` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/files/file`

**Delete File**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | query | `string` | ✓ |  |
| `filename` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/folders`

**Create Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateFolderRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `name` | string | ✓ |  |
| `parent_id` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FileFolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/folders/{folder_id}`

**Get Folder Detail**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FolderDetailResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/files/folders/{folder_id}`

**Update Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `app__schemas__files__UpdateFolderRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `name` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FileFolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/files/folders/{folder_id}`

**Delete Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `hard` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/folders/{folder_id}/bulk-delete`

**Bulk Delete Files**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `BulkDeleteRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filenames` | array of string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BulkDeleteResult` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/folders/{folder_id}/bulk-move`

**Bulk Move Files**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `BulkMoveRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filenames` | array of string | ✓ |  |
| `target_folder_id` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BulkMoveResult` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/files/folders/{folder_id}/inheritance`

**Set Folder Inheritance**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SetInheritanceRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `inherit_permissions` | boolean | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FileFolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/folders/{folder_id}/permissions`

**List Permissions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `app__schemas__files__PermissionList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/folders/{folder_id}/permissions`

**Grant Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `app__schemas__files__GrantPermissionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `permission` | string | ✓ |  |
| `subject_id` | string | ✓ |  |
| `subject_name` | string | ✓ |  |
| `subject_type` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `app__schemas__files__PermissionPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/files/folders/{folder_id}/permissions/{perm_id}`

**Revoke Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `perm_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/folders/{folder_id}/upload`

**Upload Files**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `Idempotency-Key` | header | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_files_api_v1_files_folders__folder_id__upload_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | array of string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `app__schemas__files__UploadResult` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/open`

**Open In Collabora**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | query | `string` | ✓ |  |
| `filename` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FileOpenResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/preview`

**Preview File**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | query | `string` | ✓ |  |
| `filename` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/sync`

**Sync Folders From Nextcloud**

Import folder tree from Nextcloud into the portal DB.

Idempotent: folders already present (by nc_path) are skipped.
Soft-deleted folders are NOT restored — they are counted as skipped.
Permissions are restored from files-acl.json backup if available.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NcSyncReport` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/tree`

**Get Folder Tree**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `parent_id` | query | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FileFolderTree` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/users/search`

**Search Files Subjects**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `SubjectSearchResult` |
| 422 | Validation Error | `HTTPValidationError` |

---

## health

### `GET /health`

**Liveness probe**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |

### `GET /ready`

**Readiness probe — checks DB + Redis**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |

---

## keycloak-admin

### `GET /api/v1/admin/keycloak/settings`

**Get Keycloak Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KeycloakSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/keycloak/settings`

**Update Keycloak Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `KeycloakSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `keycloak_realm` | string |  |  |
| `keycloak_url` | string |  |  |
| `oidc_client_id` | string |  |  |
| `oidc_client_secret` | any |  | Pass null or '***' to keep existing; new value to update |
| `sync_client_id` | string |  |  |
| `sync_client_secret` | any |  | Pass null or '***' to keep existing; '' to clear; new value to update |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KeycloakSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/keycloak/sync/status`

**Get Sync Status**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SyncStatusOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/keycloak/test/oidc`

**Test Oidc Connection**

Проверяет OIDC-клиент: discovery-эндпоинт + client_credentials токен.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/keycloak/test/sync`

**Test Sync Connection**

Проверяет sync-клиент: получает токен и пробует прочитать 1 пользователя из Admin API.

Если в теле запроса переданы sync_client_id / sync_client_secret — они используются для теста
(позволяет проверить новые credentials до сохранения). Иначе читаются из файла настроек.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json`

Schema: any

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

---

## knowledge-base

### `GET /api/v1/kb/articles`

**Список статей KB**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | query | `any` |  |  |
| `tag` | query | `any` |  |  |
| `status` | query | `any` |  |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticleList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles`

**Создать статью**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `Idempotency-Key` | header | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateArticleRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | string |  |  |
| `section_id` | any |  |  |
| `status` | string |  |  |
| `tags` | array of string |  |  |
| `title` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/import`

**Import Article Md**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `strategy` | query | `string` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_import_article_md_api_v1_kb_articles_import_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `ImportReport` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}`

**Получить статью**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/kb/articles/{article_id}`

**Обновить статью**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateArticleRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | any |  |  |
| `change_comment` | any |  |  |
| `section_id` | any |  |  |
| `status` | any |  |  |
| `tags` | any |  |  |
| `title` | any |  |  |
| `version` | integer | ✓ | Текущая версия статьи (оптимистичная блокировка) |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/kb/articles/{article_id}`

**Удалить статью (soft)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/comments`

**Комментарии статьи**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbCommentList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/comments`

**Добавить комментарий**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateCommentRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `KbCommentPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/kb/articles/{article_id}/comments/{comment_id}`

**Удалить комментарий**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `comment_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/kb/articles/{article_id}/draft`

**Автосохранение черновика**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `DraftSaveRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | any |  |  |
| `title` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/export/docx`

**Экспорт статьи в DOCX**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/export/md`

**Export Article Md**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/export/pdf`

**Экспорт статьи в PDF**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/feedback`

**Оценить статью (полезна/нет)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `FeedbackRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `is_helpful` | boolean | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackStats` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/files`

**List Article Files**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbFileList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/files`

**Upload Article File**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_article_file_api_v1_kb_articles__article_id__files_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `KbFilePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/kb/articles/{article_id}/files/{file_id}`

**Delete Article File**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `file_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/kb/articles/{article_id}/inherit`

**Set Inherit Permissions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `InheritRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `inherit_permissions` | boolean | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/media`

**Upload Article Media**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_article_media_api_v1_kb_articles__article_id__media_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MediaUploadResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/permissions`

**Get Article Permissions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `app__schemas__kb_extra__PermissionList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/permissions`

**Set Article Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SetPermissionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `permission` | string | ✓ |  |
| `subject_id` | string | ✓ |  |
| `subject_name` | string | ✓ |  |
| `subject_type` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `PermissionEntry` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/kb/articles/{article_id}/permissions/{subject_id}`

**Delete Article Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `subject_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/restore`

**Восстановить статью**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/suggest`

**Предложить правку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateSuggestionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | string | ✓ |  |
| `comment` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 202 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/suggestions`

**Список правок (editor+)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/versions`

**Версии статьи**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbVersionList` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/versions/{v1}/diff/{v2}`

**Diff Versions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `v1` | path | `integer` | ✓ |  |
| `v2` | path | `integer` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DiffResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/articles/{article_id}/versions/{version_number}/restore`

**Откат к версии N**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `version_number` | path | `integer` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/export/vault.zip`

**Export Vault**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/files/{article_id}/{filename}`

**Download Article File**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/import/vault`

**Import Vault Zip**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `strategy` | query | `string` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_import_vault_zip_api_v1_kb_import_vault_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `ImportReport` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/media/{article_id}/{filename}`

**Serve Article Media**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/sections`

**Дерево разделов**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/sections`

**Создать раздел**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateSectionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `parent_id` | any |  |  |
| `sort_order` | integer |  |  |
| `title` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `KbSectionPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/kb/sections/{section_id}`

**Обновить раздел**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateSectionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `parent_id` | any |  |  |
| `sort_order` | any |  |  |
| `title` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbSectionPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/kb/sections/{section_id}`

**Удалить раздел**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/sections/{section_id}/export/zip`

**Export Section Zip**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/sections/{section_id}/permissions`

**Get Section Permissions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `app__schemas__kb_extra__PermissionList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/sections/{section_id}/permissions`

**Set Section Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SetPermissionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `permission` | string | ✓ |  |
| `subject_id` | string | ✓ |  |
| `subject_name` | string | ✓ |  |
| `subject_type` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `PermissionEntry` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/kb/sections/{section_id}/permissions/{subject_id}`

**Delete Section Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
| `subject_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/suggestions/{suggestion_id}/review`

**Принять/отклонить правку (editor+)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `suggestion_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `ReviewSuggestionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/tags`

**Список тегов KB**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `KbTagPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/users/search`

**Search Kb Users**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `UserSearchResult` |
| 422 | Validation Error | `HTTPValidationError` |

---

## links

### `GET /api/v1/links`

**Список ярлыков**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `category` | query | `any` |  |  |
| `include_inactive` | query | `boolean` |  |  |
| `orphaned` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `ServiceLinkList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/links`

**Создать ярлык (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateLinkRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | any |  |  |
| `description` | any |  |  |
| `icon_url` | any |  |  |
| `is_active` | boolean |  |  |
| `sort_order` | integer |  |  |
| `supports_sso` | boolean |  |  |
| `title` | string | ✓ |  |
| `url` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `ServiceLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/links/reorder`

**Изменить порядок ярлыков (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `ReorderLinksRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `items` | array of `LinkReorderItem` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/links/{link_id}`

**Получить ярлык**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `ServiceLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/links/{link_id}`

**Обновить ярлык (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateLinkRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | any |  |  |
| `description` | any |  |  |
| `icon_url` | any |  |  |
| `is_active` | any |  |  |
| `sort_order` | any |  |  |
| `supports_sso` | any |  |  |
| `title` | any |  |  |
| `url` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `ServiceLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/links/{link_id}`

**Удалить ярлык (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/links/{link_id}/icon`

**Загрузить иконку ярлыка (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_link_icon_api_v1_links__link_id__icon_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `ServiceLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/links/{link_id}/icon`

**Удалить иконку ярлыка (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/links/{link_id}/sso-redirect`

**Серверный SSO-редирект для ярлыка**

302-редирект на целевой сервис с id_token_hint.

id_token_hint НЕ возвращается клиенту в теле ответа — только через Location-заголовок
сервера, что исключает попадание токена в историю браузера портала и JS-память.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/links/{link_id}/sso-url`

**SSO URL для ярлыка (устарел, используйте sso-redirect)**

Оставлен для обратной совместимости. Предпочтительный вариант — sso-redirect.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `link_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

---

## modules

### `GET /api/v1/admin/modules`

**Get Module Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `AllModuleSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/modules/nextcloud`

**Update Nextcloud Module**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `NextcloudModuleIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NextcloudModuleOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/modules/photos`

**Update Photos Module**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `PhotosModuleIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allowed_mime` | array of string |  |  |
| `enabled` | boolean |  |  |
| `max_size_mb` | integer |  |  |
| `strip_gps` | boolean |  |  |
| `widget_limit` | integer |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotosModuleOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/modules`

**Get Modules For Ui**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `AllModuleSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

---

## nc-federation

### `POST /ocs/v2.php/apps/richdocuments/api/v1/federation`

**Federation Remote Wopi Token**

Return initiator wopi-like info for a token previously issued by the portal.

Nextcloud's ``FederationService::getRemoteFileDetails`` calls this as part
of WOPI ``CheckFileInfo`` to obtain ``UserFriendlyName`` (Collabora cursor
name). Response shape mirrors a serialized ``Wopi`` entity so that
``Wopi::fromParams`` can hydrate it on the NC side.

An empty or missing ``token`` field is treated as an unknown token and
returns OCS 404 (not a 422 validation error) to prevent information leakage
and match Nextcloud's expected response envelope.

**Request Body**

Content-Type: `application/x-www-form-urlencoded` — schema: `Body_federation_remote_wopi_token_ocs_v2_php_apps_richdocuments_api_v1_federation_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `token` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

---

## news

### `GET /api/v1/news`

**Список новостей**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `page` | query | `integer` |  |  |
| `page_size` | query | `integer` |  |  |
| `limit` | query | `any` |  | Alias for page_size |
| `offset` | query | `any` |  | Offset alias (overrides page) |
| `status` | query | `any` |  |  |
| `category` | query | `any` |  |  |
| `is_pinned` | query | `any` |  |  |
| `q` | query | `any` |  | Полнотекстовый поиск по заголовку и тексту |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news`

**Создать новость**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `Idempotency-Key` | header | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateNewsRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `archive_at` | any |  |  |
| `body` | string |  |  |
| `categories` | array of string |  |  |
| `cover_focal_point` | any |  |  |
| `is_pinned` | boolean |  |  |
| `publish_at` | any |  |  |
| `status` | string |  |  |
| `target_departments` | any |  |  |
| `target_roles` | any |  |  |
| `title` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/limits`

**Лимиты загрузки файлов новостей**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsUploadLimits` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/trash`

**Корзина: список удалённых новостей**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `page` | query | `integer` |  |  |
| `page_size` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TrashNewsList` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}`

**Получить новость**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/news/{news_id}`

**Обновить новость**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateNewsRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `archive_at` | any |  |  |
| `body` | any |  |  |
| `categories` | any |  |  |
| `cover_focal_point` | any |  |  |
| `is_pinned` | any |  |  |
| `publish_at` | any |  |  |
| `published_at` | any |  |  |
| `status` | any |  |  |
| `target_departments` | any |  |  |
| `target_roles` | any |  |  |
| `title` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}`

**Удалить новость (soft)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/attachments`

**Вложения новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `AttachmentPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/attachments`

**Загрузить вложение**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_attachment_api_v1_news__news_id__attachments_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `AttachmentPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/attachments/{att_id}`

**Удалить вложение**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `att_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/attachments/{att_id}/download`

**Скачать вложение**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `att_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/cover`

**Загрузить обложку новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_news_cover_api_v1_news__news_id__cover_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/cover`

**Удалить обложку новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/news/{news_id}/draft`

**Автосохранение черновика**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateNewsRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `archive_at` | any |  |  |
| `body` | any |  |  |
| `categories` | any |  |  |
| `cover_focal_point` | any |  |  |
| `is_pinned` | any |  |  |
| `publish_at` | any |  |  |
| `published_at` | any |  |  |
| `status` | any |  |  |
| `target_departments` | any |  |  |
| `target_roles` | any |  |  |
| `title` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/export/html`

**Экспорт новости в HTML**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/export/markdown`

**Экспорт новости в Markdown**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/export/pdf`

**Экспорт новости в PDF**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/gallery`

**Галерея новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `GalleryImagePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/gallery`

**Загрузить фото в галерею**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_gallery_image_api_v1_news__news_id__gallery_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `GalleryImagePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/news/{news_id}/gallery/reorder`

**Изменить порядок галереи**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json`

Schema: array of `ReorderItem`

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `GalleryImagePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/gallery/{img_id}`

**Удалить фото из галереи**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `img_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/inline-media`

**Загрузить инлайн-изображение в тело новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_news_inline_media_api_v1_news__news_id__inline_media_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MediaUploadResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/inline-media/{filename}`

**Получить инлайн-изображение новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/purge`

**Hard-delete новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/restore`

**Восстановить удалённую новость**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/versions`

**История версий**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `NewsVersionPublic` |
| 422 | Validation Error | `HTTPValidationError` |

---

## news-categories

### `GET /api/v1/news-categories`

**Список категорий новостей**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `CategoriesResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news-categories`

**Добавить категорию новостей**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CategoryIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `color` | string |  |  |
| `name` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `CategoriesResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news-categories/{name}`

**Удалить категорию из списка и из всех новостей**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `name` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `CategoriesResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/news-categories/{name}/color`

**Обновить цвет категории**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `name` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `ColorIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `color` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `CategoriesResponse` |
| 422 | Validation Error | `HTTPValidationError` |

---

## notifications

### `GET /api/v1/notifications`

**Список уведомлений**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `unread_only` | query | `boolean` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NotificationListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/notifications/read-all`

**Отметить все прочитанными**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/notifications/stream`

**SSE-стрим уведомлений**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/notifications/unread-count`

**Количество непрочитанных**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/notifications/{notification_id}`

**Удалить уведомление**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `notification_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/notifications/{notification_id}/read`

**Отметить уведомление прочитанным**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `notification_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

---

## photos

### `POST /api/v1/photos/bulk`

**Bulk Action**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `BulkActionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | ✓ |  |
| `photo_ids` | array of string | ✓ |  |
| `target_folder_id` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BulkActionResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/deleted`

**List Deleted Photos**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `page` | query | `integer` |  |  |
| `per_page` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/folders`

**Create Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateFolderRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `name` | string | ✓ |  |
| `parent_id` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/folders/deleted`

**List Deleted Folders**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `FolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/folders/tree`

**List Folder Tree**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FolderTree` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/folders/{folder_id}`

**Get Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/photos/folders/{folder_id}`

**Update Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `app__schemas__photos__UpdateFolderRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cover_photo_id` | any |  |  |
| `description` | any |  |  |
| `name` | any |  |  |
| `parent_id` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/folders/{folder_id}`

**Delete Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/folders/{folder_id}/permissions`

**List Folder Permissions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `app__schemas__photos__PermissionList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/folders/{folder_id}/permissions`

**Grant Folder Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `app__schemas__photos__GrantPermissionRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `permission` | string | ✓ |  |
| `subject_id` | string | ✓ |  |
| `subject_name` | string | ✓ |  |
| `subject_type` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `app__schemas__photos__PermissionPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/folders/{folder_id}/permissions/{subject_id}`

**Revoke Folder Permission**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `subject_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/folders/{folder_id}/photos`

**List Folder Photos**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `page` | query | `integer` |  |  |
| `per_page` | query | `integer` |  |  |
| `sort` | query | `string` |  |  |
| `min_date` | query | `any` |  |  |
| `max_date` | query | `any` |  |  |
| `min_size` | query | `any` |  |  |
| `max_size` | query | `any` |  |  |
| `mime_type` | query | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/folders/{folder_id}/restore`

**Restore Folder**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FolderPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/folders/{folder_id}/share`

**Create Folder Share**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `FolderShareLinkRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `expires_in_days` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FolderShareLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/folders/{folder_id}/shares`

**List Folder Shares**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `FolderShareLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/folders/{folder_id}/upload`

**Upload Photos**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_photos_api_v1_photos_folders__folder_id__upload_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | array of string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `app__schemas__photos__UploadResult` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/folders/{folder_id}/zip`

**Create Zip Job**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `ZipJobPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/import/scan`

**Import Scan**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/import/scan/status/{job_id}`

**Import Scan Status**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `job_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/my-shares`

**Get My Shares**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MySharesResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/my-shares/folder/{token_id}`

**Revoke Folder Share**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/my-shares/photo/{token_id}`

**Revoke Photo Share**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/original/{photo_id}`

**Get Original**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `download` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public-folder/{token}/info`

**Public Folder Info**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public-folder/{token}/photos`

**Public Folder Photos**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |
| `page` | query | `integer` |  |  |
| `per_page` | query | `integer` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoList` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public-folder/{token}/thumbnail/{photo_id}/{size}`

**Public Folder Thumbnail**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |
| `photo_id` | path | `string` | ✓ |  |
| `size` | path | `integer` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public/{token}/file`

**Public Original**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |
| `download` | query | `boolean` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public/{token}/info`

**Public Photo Info**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public/{token}/thumbnail/{size}`

**Public Thumbnail**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |
| `size` | path | `integer` | ✓ |  |
| `format` | query | `string` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/recent`

**List Recent Photos**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `PhotoPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/storage-stats`

**Get Storage Stats**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/tags`

**List Tags**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TagList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/tags`

**Create Tag**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateTagRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `TagPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/tags/{tag_id}`

**Delete Tag**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `tag_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/thumbnail/{photo_id}/{size}`

**Get Thumbnail**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `size` | path | `integer` | ✓ |  |
| `format` | query | `string` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/trash/empty`

**Empty Trash**

Ставит в очередь ARQ-задачу очистки корзины (только admin).

Возвращает 202 Accepted немедленно; фактическое удаление происходит в фоне.
Аудит-событие ``photos.trash_emptied`` публикуется самой задачей по завершении.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 202 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/users/search`

**Search Photo Subjects**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `SubjectSearchResult` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/zip-jobs/{job_id}`

**Get Zip Job**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `job_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `ZipJobPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/zip-jobs/{job_id}/download`

**Download Zip Job**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `job_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/{photo_id}`

**Get Photo**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/photos/{photo_id}`

**Update Photo**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdatePhotoRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `folder_id` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/{photo_id}`

**Delete Photo**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/{photo_id}/purge`

**Purge Photo**

Окончательно удаляет фото из корзины (файлы + запись в БД).

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/{photo_id}/restore`

**Restore Photo**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/photos/{photo_id}/share`

**Create Share Link**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `ShareLinkRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `expires_in_days` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `ShareLinkPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/{photo_id}/tags`

**Get Photo Tags**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `TagPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/photos/{photo_id}/tags`

**Set Photo Tags**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `photo_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SetPhotoTagsRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tag_ids` | array of string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `TagPublic` |
| 422 | Validation Error | `HTTPValidationError` |

---

## search

### `GET /api/v1/search`

**Глобальный поиск**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `type` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `from_date` | query | `any` |  |  |
| `to_date` | query | `any` |  |  |
| `author_id` | query | `any` |  |  |
| `department` | query | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SearchResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/search/suggest`

**Typeahead подсказки**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SuggestResponse` |
| 422 | Validation Error | `HTTPValidationError` |

---

## system-settings

### `GET /api/v1/admin/system/nextcloud/status`

**Get Nextcloud Status**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NcStatusOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/system/nginx/reload`

**Nginx Reload**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/system/settings`

**Get System Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SystemSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/system/settings`

**Update System Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SystemSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allowed_cidr` | string |  |  |
| `arq_max_jobs` | integer |  |  |
| `kb_attachment_max_size_mb` | integer |  |  |
| `kb_import_max_size_mb` | integer |  |  |
| `kb_media_max_size_mb` | integer |  |  |
| `log_force_json` | any |  |  |
| `log_level` | string |  |  |
| `log_slow_request_ms` | integer |  |  |
| `max_upload_size_mb` | integer |  |  |
| `metrics_token` | any |  | Pass null or '***' to keep existing; new value to update; '' to clear |
| `nc_files_root` | string |  |  |
| `nc_service_app_password` | any |  | Pass null or '***' to keep existing; new value to update; '' to clear |
| `nc_service_username` | string |  |  |
| `nc_user_id_field` | string |  |  |
| `news_attachment_max_size_mb` | integer |  |  |
| `nextcloud_url` | string |  |  |
| `photo_gallery_mode` | string |  |  |
| `photo_gallery_new_tab` | boolean |  |  |
| `photo_gallery_url` | string |  |  |
| `portal_base_url` | string |  |  |
| `prometheus_metrics_enabled` | boolean |  |  |
| `sentry_dsn` | any |  | Pass null or '***' to keep existing; new value to update; '' to clear |
| `sse_max_connections_global` | integer |  |  |
| `sse_max_connections_per_user` | integer |  |  |
| `timezone` | string |  |  |
| `video_gallery_url` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SystemSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/admin/system/settings`

**Patch System Settings**

Partial update: only fields present in the request body are applied.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SystemSettingsPatch`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allowed_cidr` | any |  |  |
| `arq_max_jobs` | any |  |  |
| `kb_attachment_max_size_mb` | any |  |  |
| `kb_import_max_size_mb` | any |  |  |
| `kb_media_max_size_mb` | any |  |  |
| `log_force_json` | any |  |  |
| `log_level` | any |  |  |
| `log_slow_request_ms` | any |  |  |
| `max_upload_size_mb` | any |  |  |
| `metrics_token` | any |  | Pass null or '***' to keep existing; new value to update; '' to clear |
| `nc_files_root` | any |  |  |
| `nc_service_app_password` | any |  | Pass null or '***' to keep existing; new value to update; '' to clear |
| `nc_service_username` | any |  |  |
| `nc_user_id_field` | any |  |  |
| `news_attachment_max_size_mb` | any |  |  |
| `nextcloud_url` | any |  |  |
| `photo_gallery_mode` | any |  |  |
| `photo_gallery_new_tab` | any |  |  |
| `photo_gallery_url` | any |  |  |
| `portal_base_url` | any |  |  |
| `prometheus_metrics_enabled` | any |  |  |
| `sentry_dsn` | any |  | Pass null or '***' to keep existing; new value to update; '' to clear |
| `sse_max_connections_global` | any |  |  |
| `sse_max_connections_per_user` | any |  |  |
| `timezone` | any |  |  |
| `video_gallery_url` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SystemSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/system/tls/cert`

**Upload Tls Cert**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_tls_cert_api_v1_admin_system_tls_cert_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/admin/system/tls/cert`

**Delete Tls Cert**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/system/tls/key`

**Upload Tls Key**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_tls_key_api_v1_admin_system_tls_key_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/admin/system/tls/key`

**Delete Tls Key**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/system/tls/status`

**Get Tls Status**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TlsStatusOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/portal/gallery-links`

**Get Gallery Links**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `GalleryLinksOut` |

---

## user-attribute-mappings

### `GET /api/v1/user-attribute-mappings`

**Список маппингов атрибутов (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserAttributeMappingList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/user-attribute-mappings`

**Создать маппинг атрибута (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateUserAttributeMappingRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `attr_key` | string | ✓ |  |
| `enabled` | boolean |  |  |
| `label_en` | any |  |  |
| `label_ru` | string | ✓ |  |
| `sort_order` | integer |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `UserAttributeMappingPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/user-attribute-mappings/discover`

**Найти ключи атрибутов в users.attributes (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DiscoverAttributesResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/user-attribute-mappings/schema`

**Публичная схема атрибутов для отображения в карточке пользователя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserAttributeMappingSchemaList` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/user-attribute-mappings/{mapping_id}`

**Обновить маппинг (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `mapping_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateUserAttributeMappingRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | any |  |  |
| `label_en` | any |  |  |
| `label_ru` | any |  |  |
| `sort_order` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserAttributeMappingPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/user-attribute-mappings/{mapping_id}`

**Удалить маппинг (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `mapping_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

---

## users

### `GET /api/v1/users`

**Список сотрудников**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `any` |  |  |
| `department` | query | `any` |  |  |
| `page` | query | `integer` |  |  |
| `page_size` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/users/admin/local`

**Создать локального пользователя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `LocalUserCreateRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✓ |  |
| `full_name` | string | ✓ |  |
| `password` | string | ✓ |  |
| `role` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/users/admin/sync`

**Синхронизировать пользователей из Keycloak**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/users/admin/{user_id}`

**Удалить пользователя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/users/admin/{user_id}/groups`

**Группы Keycloak пользователя (только для админа)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/users/admin/{user_id}/password`

**Сбросить пароль (только admin, только локальные)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `PasswordResetRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_password` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/users/admin/{user_id}/profile`

**Редактировать профиль локального пользователя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `AdminPatchProfileRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `department` | any |  |  |
| `full_name` | any |  |  |
| `phone` | any |  |  |
| `position` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/users/admin/{user_id}/role`

**Сменить роль пользователя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `PatchRoleRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/users/me`

**Текущий пользователь**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserMe` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/users/me/avatar`

**Загрузить аватар**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_avatar_api_v1_users_me_avatar_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserMe` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/users/me/password`

**Сменить пароль (только для локальных пользователей)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `PasswordChangeRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `current_password` | string | ✓ |  |
| `new_password` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/users/me/preferences`

**Обновить персональные настройки**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `PatchPreferencesRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hidden_link_ids` | any |  |  |
| `onboarding_completed` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserMe` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/users/me/profile`

**Обновить профиль**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `PatchProfileRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lang` | any |  |  |
| `notify_email` | any |  |  |
| `notify_inapp` | any |  |  |
| `presence_status` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserMe` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/users/{user_id}`

**Профиль сотрудника**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `UserPublic` |
| 422 | Validation Error | `HTTPValidationError` |

---
