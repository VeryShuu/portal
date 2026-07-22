<!-- AUTO-GENERATED — do not edit manually. Run: cd backend && python -m scripts.generate_api_contracts_doc --output ../docs/api-contracts.generated.md -->
<!-- Generated: 2026-07-22 14:37 UTC -->

# API Contracts (auto-generated)

> Generated from FastAPI OpenAPI spec.  
> Source of truth: `./docs/api-contracts.generated.md` (auto) and `./docs/api-contracts.md` (curated).  
> Base URL: `/api/v1/`

---

## Table of Contents

- [admin](#admin)
- [analytics](#analytics)
- [audit](#audit)
- [auth](#auth)
- [bookmarks](#bookmarks)
- [bootstrap](#bootstrap)
- [branding](#branding)
- [directories](#directories)
- [email-outbox](#email-outbox)
- [feedback](#feedback)
- [files](#files)
- [health](#health)
- [helpdesk](#helpdesk)
- [keycloak-admin](#keycloak-admin)
- [knowledge-base](#knowledge-base)
- [links](#links)
- [mailing-recipients](#mailing-recipients)
- [meetings](#meetings)
- [modules](#modules)
- [nc-federation](#nc-federation)
- [news](#news)
- [news-categories](#news-categories)
- [notifications](#notifications)
- [photos](#photos)
- [search](#search)
- [signature](#signature)
- [system-settings](#system-settings)
- [user-attribute-mappings](#user-attribute-mappings)
- [users](#users)

---

## admin

### `GET /api/v1/admin/email-outbox`

**Список писем в outbox**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `status` | query | `any` |  |  |
| `kind` | query | `any` |  |  |
| `to_email` | query | `any` |  |  |
| `date_from` | query | `any` |  |  |
| `date_to` | query | `any` |  |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/email-outbox/_/stats`

**Сводка по outbox**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/email-outbox/{outbox_id}`

**Карточка письма в outbox**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `outbox_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/email-outbox/{outbox_id}/cancel`

**Отменить отправку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `outbox_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/email-outbox/{outbox_id}/retry`

**Повторить отправку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `outbox_id` | path | `string` | ✓ |  |
| `reset_attempts` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

---

## analytics

### `GET /api/v1/analytics/dashboard`

**Сводный дашборд (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DashboardOut` |
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
| 200 | Successful Response | array of `DepartmentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/export`

**Экспорт таблицы аналитики (CSV/XLSX)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `dataset` | query | `string` | ✓ |  |
| `format` | query | `string` |  |  |
| `days` | query | `integer` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/feedback`

**Статистика обращений (feedback)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FeedbackStatsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/resource-trend`

**Динамика по конкретному ресурсу (ярлык/файл)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `resource_id` | query | `string` | ✓ |  |
| `kind` | query | `string` |  |  |
| `days` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `DailyPoint` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/stale-content`

**Застойный контент (0 просмотров / давно не обновлялся)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `StaleContentItem` |
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
| 200 | Successful Response | array of `TopArticleOut` |
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
| 200 | Successful Response | array of `TopFileOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/analytics/top-links`

**Топ ярлыков по переходам (audit_log)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `days` | query | `integer` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `TopLinkOut` |
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
| 200 | Successful Response | array of `TopNewsOut` |
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
| 200 | Successful Response | object |
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
| `code` | query | `any` |  |  |
| `state` | query | `any` |  |  |
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

## directories

### `GET /api/v1/directories`

**Список типов справочников (вкладок)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DirectoryList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/directories`

**Создать тип справочника (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateDirectoryRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `channels` | array of `DirectoryChannel` |  |  |
| `description` | any |  |  |
| `enabled` | boolean |  |  |
| `field_schema` | array of `DirectoryField` |  |  |
| `icon` | any |  |  |
| `label_en` | any |  |  |
| `label_ru` | string | ✓ |  |
| `slug` | string | ✓ |  |
| `sort_order` | integer |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `DirectoryPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/directories/{directory_id}`

**Обновить тип справочника (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `directory_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateDirectoryRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `channels` | any |  |  |
| `description` | any |  |  |
| `enabled` | any |  |  |
| `field_schema` | any |  |  |
| `icon` | any |  |  |
| `label_en` | any |  |  |
| `label_ru` | any |  |  |
| `sort_order` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DirectoryPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/directories/{directory_id}`

**Удалить тип справочника (editor, soft)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `directory_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/directories/{slug}/entries`

**Список объектов справочника**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `EntryList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/directories/{slug}/entries`

**Создать объект (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateEntryRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `attributes` | object |  |  |
| `contacts` | array of `ContactInput` |  |  |
| `folder_id` | any |  |  |
| `name` | string | ✓ |  |
| `note` | any |  |  |
| `sort_order` | integer |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `EntryPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/directories/{slug}/entries/reorder`

**Изменить порядок объектов (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `ReorderEntriesRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `items` | array of `EntryReorderItem` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/directories/{slug}/entries/{entry_id}`

**Получить объект с контактами**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `entry_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `EntryPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/directories/{slug}/entries/{entry_id}`

**Обновить объект (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `entry_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateEntryRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `attributes` | any |  |  |
| `contacts` | any |  |  |
| `folder_id` | any |  |  |
| `name` | any |  |  |
| `note` | any |  |  |
| `sort_order` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `EntryPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/directories/{slug}/entries/{entry_id}`

**Удалить объект (editor, soft)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `entry_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/directories/{slug}/export`

**Экспорт объектов (csv | xlsx | pdf)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `slug` | path | `string` | ✓ |  |
| `format` | query | `string` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

---

## email-outbox

### `GET /api/v1/admin/email-outbox`

**Список писем в outbox**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `status` | query | `any` |  |  |
| `kind` | query | `any` |  |  |
| `to_email` | query | `any` |  |  |
| `date_from` | query | `any` |  |  |
| `date_to` | query | `any` |  |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/email-outbox/_/stats`

**Сводка по outbox**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/admin/email-outbox/{outbox_id}`

**Карточка письма в outbox**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `outbox_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/email-outbox/{outbox_id}/cancel`

**Отменить отправку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `outbox_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/email-outbox/{outbox_id}/retry`

**Повторить отправку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `outbox_id` | path | `string` | ✓ |  |
| `reset_attempts` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

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

### `POST /api/v1/admin/files/icons/{ext}`

**Загрузить SVG-иконку для расширения**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ext` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_file_icon_api_v1_admin_files_icons__ext__post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/admin/files/icons/{ext}`

**Удалить пользовательскую иконку**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ext` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/admin/shares`

**Admin List Shares**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `subject_id` | query | `any` |  |  |
| `folder_id` | query | `any` |  |  |
| `active_only` | query | `boolean` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `AdminFileShareList` |
| 422 | Validation Error | `HTTPValidationError` |

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

### `GET /api/v1/files/folders/{folder_id}/files/{filename}/shares`

**List File Shares**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `FileShareList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/files/folders/{folder_id}/files/{filename}/shares`

**Create File Share**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateFileShareRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `expires_in_days` | any |  |  |
| `permission` | string | ✓ |  |
| `subject_id` | string | ✓ |  |
| `subject_name` | string | ✓ |  |
| `subject_type` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `FileSharePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/files/folders/{folder_id}/files/{filename}/shares/{share_id}`

**Revoke File Share**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `folder_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `share_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
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

### `GET /api/v1/files/icons`

**Список расширений с пользовательскими иконками**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |

### `GET /api/v1/files/icons/{ext}`

**Получить SVG-иконку для расширения**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ext` | path | `string` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
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

### `GET /api/v1/files/shares/my`

**List My Shares**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MyFileShareList` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/files/shares/shared-with-me`

**List Shared With Me**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SharedFileList` |
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
| 200 | Successful Response | any |

---

## helpdesk

### `GET /api/v1/helpdesk/agents`

**Список агентов поддержки**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `AgentListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/agents`

**Добавить агента поддержки**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `AgentIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `notify_new` | boolean |  |  |
| `user_id` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `AgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/helpdesk/agents/{user_id}`

**Изменить флаг notify_new агента**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `user_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `AgentIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `notify_new` | boolean |  |  |
| `user_id` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `AgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/helpdesk/agents/{user_id}`

**Удалить агента поддержки**

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

### `GET /api/v1/helpdesk/attachments/{attachment_id}`

**Скачать вложение (StreamingResponse из локального файла)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `attachment_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/draft-attachments`

**Загрузить inline-картинку для формы создания заявки (draft)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_draft_attachment_api_v1_helpdesk_draft_attachments_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MediaUploadResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/draft-attachments/{draft_id}`

**Раздать draft-картинку (через nginx X-Accel-Redirect; только владелец)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `draft_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/settings/digest`

**Get Digest Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskDigestSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/helpdesk/settings/digest`

**Put Digest Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `HelpdeskDigestSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `digest_hour` | integer |  |  |
| `digest_minute` | integer |  |  |
| `digest_schedule` | string |  |  |
| `enabled` | boolean |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskDigestSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/settings/mailbox`

**Get Mailbox Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskMailboxSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/helpdesk/settings/mailbox`

**Put Mailbox Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `HelpdeskMailboxSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `delete_after_fetch` | boolean |  |  |
| `imap_folder` | string |  |  |
| `imap_host` | string | ✓ |  |
| `imap_password` | any |  |  |
| `imap_port` | integer |  |  |
| `imap_use_ssl` | boolean |  |  |
| `imap_username` | string | ✓ |  |
| `poll_interval_seconds` | integer |  |  |
| `support_address` | `app__schemas__helpdesk__Email__1` | ✓ |  |
| `support_reply_to` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskMailboxSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/settings/mailbox/test`

**Test Mailbox Connection**

Проверка IMAP-соединения с текущими настройками. Возвращает OK/детали.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | object |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/settings/max-bot`

**Get Max Bot Settings**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskMaxBotSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/helpdesk/settings/max-bot`

**Put Max Bot Settings**

Сохранить конфигурацию MAX-бота (токен write-only, как IMAP-пароль).

Валидация: при ``enabled=True`` обязательно наличие токена (либо в текущем
payload, либо уже сохранённого) и ``chat_id`` — иначе 400 (нельзя включить
канал без валидных кредов).

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `HelpdeskMaxBotSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bot_token` | any |  |  |
| `chat_id` | any |  |  |
| `enabled` | boolean |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskMaxBotSettingsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/settings/max-bot/test`

**Test Max Bot Connection**

Отправить тестовое сообщение в чат поддержки через MAX Bot API.

В отличие от ``POST /mailbox/test`` (который проверяет только IMAP-логин),
здесь мы делаем **полный end-to-end тест**: отправляем реальное сообщение
в настроенный ``chat_id``. Это проверяет:
* токен бота валиден (401 от MAX иначе);
* бот добавлен в чат и имеет права писать (403/400 иначе);
* ``chat_id`` корректный (400 «chat not found» иначе);
* TLS к MAX работает (Russian Trusted CA в trust store).

Пользователь видит сообщение в MAX — это и есть подтверждение «всё работает».

Defense-in-depth: на ошибку маскируем ``str(exc)`` (MAX в JSON-ошибках
иногда отражает часть токена или чувствительные детали). Полный traceback
остаётся в server-log через ``logger.exception``.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskMaxBotTestResult` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets`

**Все заявки (агентский инбокс)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `status` | query | `any` |  |  |
| `assignee` | query | `any` |  |  |
| `unassigned` | query | `boolean` |  |  |
| `source` | query | `any` |  |  |
| `active_only` | query | `boolean` |  |  |
| `assigned` | query | `boolean` |  |  |
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets`

**Создать заявку через веб-форму (multipart/form-data)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_create_ticket_api_v1_helpdesk_tickets_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | string |  |  |
| `description_html` | string |  |  |
| `files` | array of string |  |  |
| `subject` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `TicketOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/assignable-agents`

**Активные агенты для смены ответственного (список)**

Все активные helpdesk-агенты (с живым аккаунтом, ``deleted_at IS NULL``)
для списка смены ответственного в карточке тикета.

Возвращает компактные пункты ``(user_id, full_name, email)`` без флагов
уведомлений (PII-минимизация: агенту для смены ответственного достаточно
знать, кому можно передать заявку). Сортировка — по ФИО. На фронте
рендерится простым списком в popover (без поиска — агентов поддержки
обычно ~5 человек).

Доступ — любой helpdesk-агент/админ (``HelpdeskAgentDep``): смена
ответственного доступна любому агенту, а не только админу. Не заменяет
admin-only ``GET /agents`` (там есть флаги ``notify_new`` и
admin-управление составом), а даёт агентам минимум данных для операции.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `AgentOptionListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/counts`

**Счётчик назначенных агенту тикетов в работе (для бейджа в меню)**

Лёгкий count-endpoint для бейджа в меню пункта «Инбокс поддержки».

``active`` — тикеты, назначенные лично этому агенту (``assignee = agent``),
в статусах new/open/pending. «Моя нагрузка», а не «объём очереди»:
неназначенные тикеты здесь не считаются (для них есть отдельный блок в
инбоксе). ``closed`` исключён. Один ``count(*)`` без join'ов.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketCountsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/my`

**Список своих заявок**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `status` | query | `any` |  |  |
| `unassigned` | query | `boolean` |  |  |
| `assigned` | query | `boolean` |  |  |
| `active_only` | query | `boolean` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketListOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/my/counts`

**Счётчик своих открытых заявок (для бейджа в меню)**

Лёгкий count-endpoint для бейджа в меню пункта «Поддержка».

``active`` — свои тикеты в статусах new/open/pending (closed исключён как
архивная история). Один ``count(*)`` без join'ов и пагинации — дешевле
list-endpoint'а с ``limit=1``, особенно при polling'е раз в 60 c.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketCountsOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/my/{ticket_id}`

**Своя заявка с публичными сообщениями**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/my/{ticket_id}/messages`

**Ответ по своей заявке**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_add_my_message_api_v1_helpdesk_tickets_my__ticket_id__messages_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body_html` | string |  |  |
| `body_text` | string |  |  |
| `files` | array of string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MessageOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/my/{ticket_id}/read`

**Отметить свой тикет прочитанным (снять подсветку ответов агентов)**

Заявительский аналог ``POST /tickets/{id}/read`` (агентского).

Записывает ``last_seen_at = NOW()`` для пары ``(ticket, user)`` — UPSERT по
``uq_helpdesk_ticket_reads_ticket_user``. Снимает подсветку в списке своих
заявок: после открытия карточки заявителем ответы агентов больше не
подсвечиваются как непрочитанные (контракт ``direction='outbound'`` в
``enrich_with_unread``, см. ``GET /tickets/my``).

ACL: только свои тикеты (``fetch_ticket_for_user`` → 404 для чужих, не
раскрываем существование). Не требует audit/rate-limit (read-state —
бизнес-состояние, как ``notifications.read``). Идемпотентно.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MarkTicketReadOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/{ticket_id}`

**Карточка заявки (агентский view, все сообщения)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketAgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/{ticket_id}/assign`

**Назначить ответственного**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `TicketAssignIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `assignee_user_id` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketAgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/{ticket_id}/inline-media`

**Загрузить inline-картинку для rich-редактора ответа**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_upload_ticket_inline_media_api_v1_helpdesk_tickets__ticket_id__inline_media_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MediaUploadResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/tickets/{ticket_id}/inline-media/{filename}`

**Раздать inline-картинку (через nginx X-Accel-Redirect)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `filename` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/{ticket_id}/messages`

**Ответ агента**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `multipart/form-data` — schema: `Body_add_agent_message_api_v1_helpdesk_tickets__ticket_id__messages_post`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body_html` | string |  |  |
| `body_text` | string |  |  |
| `cc` | array of string |  |  |
| `files` | array of string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MessageOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/{ticket_id}/read`

**Отметить тикет прочитанным (снять подсветку в инбоксе агента)**

Записать ``last_seen_at = NOW()`` для пары ``(ticket, agent)`` — UPSERT
по ``uq_helpdesk_ticket_reads_ticket_user``. Вызывается фронтендом при
открытии карточки тикета (точка «прочитано» в инбоксе агента).

Не требует audit (read-state — бизнес-состояние, не мутация, как
``notifications.read``) и rate-limit (доступ только HelpdeskAgentDep).
Идемпотентно: повторное открытие карточки = более свежий ``last_seen_at``.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MarkTicketReadOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/{ticket_id}/reopen`

**Reopen закрытой заявки**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketAgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/helpdesk/tickets/{ticket_id}/status`

**Сменить статус по машине состояний**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `TicketStatusIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketAgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/helpdesk/tickets/{ticket_id}/take`

**Взять нераспределённую заявку на себя**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ticket_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `TicketAgentOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/helpdesk/users/search`

**Поиск пользователя для CC (ответить всем) по справочнику**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `HelpdeskUserOption` |
| 422 | Validation Error | `HTTPValidationError` |

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
| `version` | integer | ✓ | Текущая версия статьи (оптимистичная блокировка) |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbArticlePublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/kb/articles/{article_id}/export/docx`

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

### `GET /api/v1/kb/articles/{article_id}/export/pdf`

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

### `POST /api/v1/kb/articles/{article_id}/purge`

**Окончательно удалить статью вместе с файлами**

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
| 202 | Successful Response | `SuggestionResponse` |
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
| 200 | Successful Response | `SuggestionListResponse` |
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

### `GET /api/v1/kb/articles/{article_id}/versions/{version_number}`

**Детали версии статьи**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `article_id` | path | `string` | ✓ |  |
| `version_number` | path | `integer` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbVersionPublic` |
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
| 200 | Successful Response | `KbSectionList` |
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

### `PATCH /api/v1/kb/sections/{section_id}/inherit`

**Set Section Inherit Permissions**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `section_id` | path | `string` | ✓ |  |
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
| 200 | Successful Response | `ReviewSuggestionResponse` |
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

### `GET /api/v1/kb/trash/articles`

**Список статей в корзине (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbTrashList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/kb/trash/articles/{article_id}/purge`

**Удалить статью из корзины окончательно (admin)**

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

### `POST /api/v1/kb/trash/articles/{article_id}/restore`

**Восстановить статью из корзины (admin)**

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

### `POST /api/v1/kb/trash/purge-all`

**Очистить всю корзину или статьи старше N дней (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `older_than_days` | query | `any` |  | Если задано — удалить только статьи, у которых deleted_at старше N дней. Если null — удалить ВСЕ статьи из корзины. |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `KbTrashPurgeResult` |
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
| `kb_url` | any |  |  |
| `show_on_home` | boolean |  |  |
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
| `kb_url` | any |  |  |
| `show_on_home` | any |  |  |
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

### `POST /api/v1/links/{link_id}/click`

**Зафиксировать переход по ярлыку**

Фиксирует переход пользователя по корпоративному ярлыку для аналитики.

SSO-ярлыки фиксируются серверно в ``/sso-redirect`` (см. ниже), поэтому
фронтенд вызывает этот эндпоинт только для прямых (внешних/внутренних)
ярлыков — двойного учёта нет.

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

Переход фиксируется здесь серверно (``links.visited``): SSO-ярлыки всегда
проходят через этот эндпоинт, поэтому фронтенд для них клик не отправляет.

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

---

## mailing-recipients

### `GET /api/v1/mailing-recipients`

**Список получателей рассылки (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MailingRecipientList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/mailing-recipients`

**Создать получателя рассылки (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateMailingRecipientRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✓ |  |
| `label` | any |  |  |
| `name` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `MailingRecipientPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/mailing-recipients/{recipient_id}`

**Обновить получателя рассылки (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `recipient_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateMailingRecipientRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | any |  |  |
| `label` | any |  |  |
| `name` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MailingRecipientPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/mailing-recipients/{recipient_id}`

**Удалить получателя рассылки (editor, soft)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `recipient_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

---

## meetings

### `GET /api/v1/meetings/bookings`

**List Bookings Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `date` | query | `any` |  |  |
| `start_date` | query | `any` |  |  |
| `end_date` | query | `any` |  |  |
| `room_id` | query | `any` |  |  |
| `creator_id` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `BookingOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/meetings/bookings`

**Create Booking Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `BookingCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `end_time` | string | ✓ |  |
| `invited_users` | array of `InvitedUser` |  |  |
| `recurrence` | any |  |  |
| `room_ids` | array of string | ✓ |  |
| `start_time` | string | ✓ |  |
| `title` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `BookingOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/meetings/bookings/my`

**List My**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `start_date` | query | `any` |  |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `BookingOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/meetings/bookings/{booking_id}`

**Get Booking Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `booking_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BookingOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/meetings/bookings/{booking_id}`

**Update Booking Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `booking_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `BookingUpdate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `apply_to` | string |  |  |
| `description` | any |  |  |
| `end_time` | any |  |  |
| `invited_users` | any |  |  |
| `recurrence` | any |  |  |
| `room_ids` | any |  |  |
| `start_time` | any |  |  |
| `title` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `BookingOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/meetings/bookings/{booking_id}`

**Delete Booking Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `booking_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json`

Schema: any

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/meetings/participants/search`

**Search Participants**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `string` | ✓ |  |
| `limit` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `InvitedUser` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/meetings/rooms`

**List Rooms**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `include_inactive` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `RoomOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/meetings/rooms`

**Create Room Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `RoomCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | any |  |  |
| `kind` | string |  |  |
| `link` | any |  |  |
| `name` | string | ✓ |  |
| `sort_order` | integer |  |  |
| `timezone` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `RoomOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/meetings/rooms/{room_id}`

**Get Room Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `room_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `RoomOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/meetings/rooms/{room_id}`

**Update Room Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `room_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `RoomUpdate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | any |  |  |
| `is_active` | any |  |  |
| `kind` | any |  |  |
| `link` | any |  |  |
| `name` | any |  |  |
| `sort_order` | any |  |  |
| `timezone` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `RoomOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/meetings/rooms/{room_id}`

**Delete Room Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `room_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/meetings/series/{series_id}`

**Update Series Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `series_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SeriesUpdate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `description` | any |  |  |
| `end_time` | any |  |  |
| `invited_users` | any |  |  |
| `room_ids` | any |  |  |
| `start_time` | any |  |  |
| `title` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of `BookingOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/meetings/series/{series_id}`

**Delete Series Endpoint**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `series_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/meetings/series/{series_id}/count`

**Series Count**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `series_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SeriesCountOut` |
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

### `PUT /api/v1/admin/modules/directories`

**Update Directories Module**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `DirectoriesModuleIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DirectoriesModuleOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/modules/helpdesk`

**Update Helpdesk Module**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `HelpdeskModuleIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `HelpdeskModuleOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/modules/meetings`

**Update Meetings Module**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `MeetingsModuleIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `calendar_end_hour` | integer |  |  |
| `calendar_start_hour` | integer |  |  |
| `enabled` | boolean |  |  |
| `max_recurrence_horizon_days` | integer |  |  |
| `min_search_chars` | integer |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `MeetingsModuleOut` |
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
| `max_share_ttl_days` | integer |  |  |
| `max_size_mb` | integer |  |  |
| `strip_gps` | boolean |  |  |
| `widget_limit` | integer |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotosModuleOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/admin/modules/signature`

**Update Signature Module**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SignatureModuleIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SignatureModuleOut` |
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
| `q` | query | `any` |  | FTS по заголовку и тексту |
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
| `cover_focal_x` | any |  |  |
| `cover_focal_y` | any |  |  |
| `cover_focal_zoom` | any |  |  |
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
| `cover_focal_x` | any |  |  |
| `cover_focal_y` | any |  |  |
| `cover_focal_zoom` | any |  |  |
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

### `GET /api/v1/news/{news_id}/comments`

**Комментарии новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `limit` | query | `integer` |  |  |
| `offset` | query | `integer` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsCommentList` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/comments`

**Добавить комментарий**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateNewsCommentRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `NewsCommentPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/news/{news_id}/comments/{comment_id}`

**Редактировать комментарий**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `comment_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateNewsCommentRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `body` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsCommentPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/comments/{comment_id}`

**Удалить комментарий**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `comment_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 204 | Successful Response |  |
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
| `cover_focal_x` | any |  |  |
| `cover_focal_y` | any |  |  |
| `cover_focal_zoom` | any |  |  |
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

### `POST /api/v1/news/{news_id}/like`

**Поставить лайк новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsLikeState` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/like`

**Снять лайк с новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsLikeState` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/poll`

**Получить опрос новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/poll`

**Создать опрос для новости**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `CreateNewsPollRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allow_revote` | boolean |  |  |
| `closes_at` | any |  |  |
| `is_anonymous` | boolean |  |  |
| `questions` | array of `CreateNewsPollQuestion` | ✓ |  |
| `results_visibility` | string |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 201 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `PATCH /api/v1/news/{news_id}/poll`

**Обновить опрос**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `UpdateNewsPollRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allow_revote` | any |  |  |
| `closes_at` | any |  |  |
| `is_anonymous` | any |  |  |
| `questions` | any |  |  |
| `results_visibility` | any |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/poll`

**Удалить опрос**

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

### `POST /api/v1/news/{news_id}/poll/close`

**Принудительно закрыть опрос**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/poll/reopen`

**Переоткрыть опрос**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/news/{news_id}/poll/vote`

**Проголосовать**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `NewsPollVoteRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `answers` | array of `NewsPollAnswer` | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/news/{news_id}/poll/vote`

**Отозвать свой голос**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsPollPublic` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/news/{news_id}/poll/voters`

**Получить список проголосовавших**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | array of object |
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

### `POST /api/v1/news/{news_id}/share-email`

**Отправить новость на email получателям из справочника (editor)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `news_id` | path | `string` | ✓ |  |
| `Idempotency-Key` | header | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `NewsShareEmailRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | any |  |  |
| `recipient_ids` | array of string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `NewsShareEmailResponse` |
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

### `PATCH /api/v1/news-categories/{name}`

**Переименовать категорию (обновляет имя и во всех новостях)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `name` | path | `string` | ✓ |  |
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `RenameIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `CategoriesResponse` |
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
| 200 | Successful Response | object |
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
| 200 | Successful Response | object |
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
| 200 | Successful Response | object |
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
| `subject_type` | query | `any` |  |  |
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
| `tag_id` | query | `any` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `PhotoList` |
| 422 | Validation Error | `HTTPValidationError` |

### `DELETE /api/v1/photos/folders/{folder_id}/purge`

**Purge Folder**

Permanently delete a trashed folder with all descendants and files.

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
| 200 | Successful Response | `PhotoListAnon` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/photos/public-folder/{token}/thumbnail/{photo_id}/{size}`

**Public Folder Thumbnail**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `token` | path | `string` | ✓ |  |
| `photo_id` | path | `string` | ✓ |  |
| `size` | path | `integer` | ✓ |  |
| `format` | query | `string` |  |  |

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
| 200 | Successful Response | `PhotoPublicAnon` |
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

Очищает корзину фотогалереи.

- Для admin: ставит фоновую ARQ-задачу, вычищающую ВСЮ корзину.
  Аудит-событие ``photos.trash_emptied`` публикуется самой задачей по завершении.
- Для остальных пользователей: синхронно вычищает только те фото и папки,
  на которые у пользователя есть право ``manager``. Аудит-событие
  ``photos.trash_emptied`` публикуется немедленно.

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

## signature

### `GET /api/v1/signature/admin/settings`

**Настройки (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SignatureSettings` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/signature/admin/settings`

**Обновить настройки (admin)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SignatureSettingsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `attr_city` | string |  |  |
| `attr_mobile` | string |  |  |
| `attr_office_phone` | string |  |  |
| `cities` | array of `SignatureCity` | ✓ |  |
| `company_url` | string | ✓ |  |
| `logo_base_url` | string | ✓ |  |
| `office_phones` | array of string | ✓ |  |
| `support_email` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SignatureSettings` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/signature/config`

**Данные для формы**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SignatureConfigResponse` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/signature/download`

**Скачать подпись (.htm)**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SignatureGenerateRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `city_id` | integer | ✓ |  |
| `device` | string |  |  |
| `email` | string | ✓ |  |
| `extension` | any |  |  |
| `language` | string |  |  |
| `mobile_phone` | any |  |  |
| `name` | string | ✓ |  |
| `office_phone` | any |  |  |
| `position` | string | ✓ |  |
| `surname` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/signature/generate`

**Сгенерировать подпись**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `SignatureGenerateRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `city_id` | integer | ✓ |  |
| `device` | string |  |  |
| `email` | string | ✓ |  |
| `extension` | any |  |  |
| `language` | string |  |  |
| `mobile_phone` | any |  |  |
| `name` | string | ✓ |  |
| `office_phone` | any |  |  |
| `position` | string | ✓ |  |
| `surname` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `SignatureGenerateResponse` |
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
| `kb_trash_retention_days` | integer |  |  |
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
| `onboarding_enabled` | boolean |  |  |
| `onboarding_reset_trigger` | string |  |  |
| `onboarding_steps` | any |  |  |
| `phone_extract_regex` | string |  |  |
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
| `kb_trash_retention_days` | any |  |  |
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
| `onboarding_enabled` | any |  |  |
| `onboarding_steps` | any |  |  |
| `phone_extract_regex` | any |  |  |
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

### `POST /api/v1/admin/system/settings/onboarding/reset`

**Reset Onboarding**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `OnboardingResetOut` |
| 422 | Validation Error | `HTTPValidationError` |

### `POST /api/v1/admin/system/settings/onboarding/steps/reset-views`

**Reset Onboarding Step Views**

Remove the given step_id from every user's onboarding_seen_step_ids array.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `OnboardingStepResetViewsIn`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `step_id` | string | ✓ |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `OnboardingStepResetViewsOut` |
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

### `GET /api/v1/portal/onboarding`

**Get Onboarding Public**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `OnboardingPublicOut` |

### `GET /api/v1/portal/staff-settings`

**Get Staff Settings**

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `StaffSettingsOut` |

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
| `is_full_name_source` | boolean |  |  |
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
| `is_full_name_source` | any |  |  |
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
| `office` | query | `any` |  |  |
| `sort` | query | `string` |  |  |
| `page` | query | `integer` |  |  |
| `page_size` | query | `integer` |  |  |
| `include_hidden` | query | `boolean` |  |  |
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

### `GET /api/v1/users/admin/staff-order`

**Текущий порядок отделов и список скрытых пользователей в /staff**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `StaffOrderState` |
| 422 | Validation Error | `HTTPValidationError` |

### `PUT /api/v1/users/admin/staff-order`

**Сохранить порядок отделов / пользователей и список скрытых**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Request Body**

Content-Type: `application/json` — schema: `StaffOrderUpdate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `departments` | array of string |  |  |
| `hidden_user_ids` | array of string |  |  |
| `users` | array of `StaffOrderUserItem` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `StaffOrderState` |
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

### `GET /api/v1/users/departments`

**Список отделов**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `ordered` | query | `boolean` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `DepartmentList` |
| 422 | Validation Error | `HTTPValidationError` |

### `GET /api/v1/users/export`

**Экспорт справочника в CSV / XLSX**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `q` | query | `any` |  |  |
| `department` | query | `any` |  |  |
| `office` | query | `any` |  |  |
| `sort` | query | `string` |  |  |
| `format` | query | `string` |  |  |
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | any |
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
| `onboarding_seen_step_ids` | any |  |  |

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

### `GET /api/v1/users/offices`

**Список офисов**

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `portal_session` | cookie | `any` |  |  |

**Responses**

| Status | Description | Schema |
|--------|-------------|--------|
| 200 | Successful Response | `OfficeList` |
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
