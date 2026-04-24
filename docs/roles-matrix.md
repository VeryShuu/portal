# Матрица прав доступа

> Корпоративный интранет-портал
> Последнее обновление: апрель 2026 (Steps 8.5/8.6/8.7 — Immich, PeerTube, Admin Modules tab)

## Роли

| Роль | Описание | Источник |
|------|---------|---------|
| `reader` | Все авторизованные сотрудники | поле `users.role` (БД) |
| `editor` | Сотрудники, создающие контент | поле `users.role` (БД) |
| `admin` | Администраторы портала | поле `users.role` (БД) |

> Роль хранится в БД (`users.role`). Источники назначения:
> - **Keycloak-пользователи** — роль устанавливается при первом upsert из JWT claim `role` (если присутствует) и затем поддерживается только через admin-API (`PATCH /users/admin/{id}/role`). Изменение роли в Keycloak без явного admin-действия портала на роль в БД **не влияет**.
> - **Local-пользователи (включая bootstrap-admin)** — роль присваивается при создании (`POST /users/admin/local`) или из env (`ADMIN_EMAIL`/`ADMIN_PASSWORD`), затем меняется только через admin-API.
>
> Каждый запрос читает роль из БД через `CurrentUser` (см. `backend/app/api/deps.py`). Это позволяет администратору моментально понизить/повысить роль без ожидания refresh-токена и единообразно работает для обоих `auth_source`.

---

## FastAPI dependency

```python
# backend/app/api/deps.py

def require_role(*roles: str):
    """Dependency: проверяет, что роль пользователя входит в список допустимых."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return current_user
    return _check

# Использование:
# Depends(require_role("editor", "admin"))  ← editor+
# Depends(require_role("admin"))            ← только admin
# AdminDep = Annotated[User, Depends(require_role("admin"))]
```

---

## Матрица: Аутентификация

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /auth/login` | ✅ | ✅ | ✅ | Открытый (redirect на Keycloak) |
| `GET /auth/callback` | ✅ | ✅ | ✅ | Открытый (OIDC callback) |
| `POST /auth/logout` | ✅ | ✅ | ✅ | Авторизованный пользователь |
| `GET /auth/logout` | ✅ | ✅ | ✅ | Открытый (SLO front-channel от Keycloak) |
| `GET /auth/me` | ✅ | ✅ | ✅ | Свой профиль |
| `POST /auth/local/login` | ✅ | ✅ | ✅ | Открытый; только `auth_source=local`; rate limit 5/15min/IP |

---

## Матрица: Пользователи

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /users` | ✅ | ✅ | ✅ | Список сотрудников — доступен всем |
| `GET /users/{id}` | ✅ | ✅ | ✅ | Профиль любого сотрудника |
| `PATCH /users/me/profile` | ✅ | ✅ | ✅ | Только свой профиль (статус, аватар) |
| `PATCH /users/me/preferences` | ✅ | ✅ | ✅ | Только свои настройки уведомлений |
| `POST /users/me/avatar` | ✅ | ✅ | ✅ | Загрузка своего аватара |
| `PATCH /users/me/password` | ✅ | ✅ | ✅ | Только `auth_source=local`; иначе 403 |
| `POST /users/admin/local` | ❌ | ❌ | ✅ | Создать локального пользователя |
| `PATCH /users/admin/{id}/password` | ❌ | ❌ | ✅ | Сброс пароля; только `auth_source=local` |
| `POST /users/admin/sync` | ❌ | ❌ | ✅ | Ручная синхронизация из Keycloak (P2-41) |
| `PATCH /users/admin/{id}/role` | ❌ | ❌ | ✅ | Изменение роли пользователя (P2-41) |

---

## Матрица: База знаний (KB)

> **Двухуровневая система прав KB:**
> 1. **Роль портала** (`users.role`) — контролирует возможность создавать разделы/статьи
> 2. **KB ACL** (`kb_section_permissions`, `kb_article_permissions`) — контролирует доступ к конкретному разделу/статье
>
> Обозначения в столбцах: `✅` — разрешено, `❌` — запрещено, `⚙` — требует KB ACL права.
> `kb_viewer` / `kb_editor` / `kb_manager` — права назначаются на конкретный раздел/статью (независимо от роли портала).

### Разделы

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /kb/sections` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Только доступные по ACL |
| `POST /kb/sections` | ❌ | ✅ | ✅ | Создать раздел; создатель получает manager |
| `PUT /kb/sections/{id}` | ❌ | ⚙ manager | ✅ | Переименовать/описание |
| `DELETE /kb/sections/{id}` | ❌ | ❌ | ✅ | Soft delete |
| `DELETE /kb/sections/{id}?force=true` | ❌ | ❌ | ✅ | Удалить с содержимым |
| `GET /kb/sections/{id}/permissions` | ❌ | ⚙ manager | ✅ | Список прав раздела |
| `POST /kb/sections/{id}/permissions` | ❌ | ⚙ manager | ✅ | Добавить/обновить право |
| `DELETE /kb/sections/{id}/permissions/{sid}` | ❌ | ⚙ manager | ✅ | Отозвать право |
| `GET /kb/sections/{id}/export/zip` | ⚙ viewer+ | ⚙ viewer+ | ✅ | ZIP раздела (Obsidian-совместимый) |
| `GET /kb/users/search` | ❌ | ✅ | ✅ | Поиск пользователей/групп для picker |

### Статьи

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /kb/articles` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Только доступные по ACL |
| `GET /kb/articles?status=draft` | ❌ | ⚙ editor+ (свои) | ✅ | Черновики — только свои у editor |
| `GET /kb/articles/{id}` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Проверка ACL + статус published для reader |
| `POST /kb/articles` | ❌ | ✅ | ✅ | Создать статью в доступном разделе; создатель → manager |
| `PUT /kb/articles/{id}` | ❌ | ⚙ editor+ | ✅ | Требует kb_editor-право |
| `PUT /kb/articles/{id}/draft` | ❌ | ⚙ editor+ | ✅ | Автосохранение черновика |
| `DELETE /kb/articles/{id}` | ❌ | ❌ | ✅ | Soft delete |
| `POST /kb/articles/{id}/restore` | ❌ | ❌ | ✅ | Восстановить удалённую |
| `GET /kb/articles/{id}/versions` | ⚙ viewer+ | ⚙ viewer+ | ✅ | История версий |
| `POST /kb/articles/{id}/versions/{n}/restore` | ❌ | ⚙ editor+ | ✅ | Откат к версии |
| `GET /kb/articles/{id}/versions/{v1}/diff/{v2}` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Diff между версиями |
| `GET /kb/articles/{id}/permissions` | ❌ | ⚙ manager | ✅ | Список прав статьи |
| `POST /kb/articles/{id}/permissions` | ❌ | ⚙ manager | ✅ | Добавить/обновить право |
| `DELETE /kb/articles/{id}/permissions/{sid}` | ❌ | ⚙ manager | ✅ | Отозвать право |
| `PATCH /kb/articles/{id}/inherit` | ❌ | ⚙ manager | ✅ | Переключить наследование прав |
| `POST /kb/articles/{id}/export/pdf` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Экспорт PDF |
| `POST /kb/articles/{id}/export/docx` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Экспорт DOCX |
| `GET /kb/articles/{id}/export/md` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Экспорт Markdown (YAML frontmatter) |
| `GET /kb/articles/{id}/comments` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Комментарии |
| `POST /kb/articles/{id}/comments` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Добавить комментарий |
| `DELETE /kb/articles/{id}/comments/{cid}` | ❌ | ⚙ viewer+ (свои) | ✅ | Удалить свой комментарий |
| `POST /kb/articles/{id}/suggest` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Предложить правку |
| `GET /kb/articles/{id}/suggestions` | ❌ | ⚙ editor+ | ✅ | Список правок |
| `POST /kb/suggestions/{id}/review` | ❌ | ⚙ editor+ | ✅ | Одобрить/отклонить правку |
| `POST /kb/articles/{id}/feedback` | ⚙ viewer+ | ⚙ viewer+ | ✅ | «Статья полезна?» |

### Медиа и вложения

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `POST /kb/articles/{id}/media` | ❌ | ⚙ editor+ | ✅ | Загрузка изображения в тело статьи |
| `GET /kb/media/{article_id}/{filename}` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Nginx X-Accel-Redirect, ACL-проверка |
| `GET /kb/articles/{id}/files` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Список вложений |
| `POST /kb/articles/{id}/files` | ❌ | ⚙ editor+ | ✅ | Загрузить вложение |
| `GET /kb/articles/{id}/files/{fid}/download` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Скачать вложение (RFC 5987) |
| `DELETE /kb/articles/{id}/files/{fid}` | ❌ | ⚙ editor+ (автор) | ✅ | Удалить вложение |

### Импорт / Экспорт KB

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `POST /kb/articles/import` | ❌ | ✅ | ✅ | Импорт `.md` файла |
| `POST /kb/import/vault` | ❌ | ✅ | ✅ | Импорт Obsidian vault `.zip` |
| `GET /kb/export/vault.zip` | ✅ | ✅ | ✅ | Экспорт всей KB (только доступные разделы) |

---

## Матрица: Новости

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /news` | ✅ | ✅ | ✅ | С таргетингом по отделу/роли |
| `GET /news/{id}` | ✅ (опубликованные) | ✅ | ✅ | reader не видит черновики |
| `POST /news` | ❌ | ✅ | ✅ | Создать новость |
| `PUT /news/{id}` | ❌ | ✅ (свои) | ✅ | editor редактирует только свои |
| `PUT /news/{id}/draft` | ❌ | ✅ (свои) | ✅ | Автосохранение |
| `DELETE /news/{id}` | ❌ | ✅ | ✅ | Soft delete (editor может удалять) |
| `POST /news/{id}/restore` | ❌ | ❌ | ✅ | Восстановить |
| `GET /news/{id}/versions` | ❌ | ✅ | ✅ | История версий |
| `POST /news/{id}/cover` | ❌ | ✅ | ✅ | Загрузка обложки (JPEG/PNG/WebP/GIF, ≤10 МБ) |
| `DELETE /news/{id}/cover` | ❌ | ✅ | ✅ | Удаление обложки |
| `GET /news/{id}/gallery` | ✅ (опубл.) | ✅ | ✅ | Черновики — только editor/admin |
| `POST /news/{id}/gallery` | ❌ | ✅ | ✅ | Загрузить изображение в галерею |
| `PATCH /news/{id}/gallery/reorder` | ❌ | ✅ | ✅ | Drag-and-drop сортировка |
| `DELETE /news/{id}/gallery/{img_id}` | ❌ | ✅ | ✅ | Удалить из галереи |
| `GET /news/{id}/attachments` | ✅ (опубл.) | ✅ | ✅ | Черновики — только editor/admin |
| `POST /news/{id}/attachments` | ❌ | ✅ | ✅ | Загрузить вложение |
| `GET /news/{id}/attachments/{att_id}/download` | ✅ (опубл.) | ✅ | ✅ | Скачивание с RFC 5987 именем |
| `DELETE /news/{id}/attachments/{att_id}` | ❌ | ✅ | ✅ | Удалить вложение |
| `GET /news/{id}/export/html` | ✅ (опубл.) | ✅ | ✅ | Standalone HTML (base64 media) |
| `GET /news/{id}/export/markdown` | ✅ (опубл.) | ✅ | ✅ | Standalone Markdown (base64 media) |
| `GET /news/{id}/export/pdf` | ✅ (опубл.) | ✅ | ✅ | PDF через Playwright/Chromium |

---

## Матрица: Файлы (Nextcloud proxy)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /files` | ✅* | ✅* | ✅* | *ACL Nextcloud определяет доступность папки |
| `GET /files/{path}/open` | ✅* | ✅* | ✅* | *ACL Nextcloud |
| `GET /files/{path}/download` | ✅* | ✅* | ✅* | *ACL Nextcloud |
| `POST /files/upload` | ✅* | ✅* | ✅* | *ACL Nextcloud (write permission) |
| `POST /files/{path}/share` | ✅* | ✅* | ✅* | *ACL Nextcloud (share permission) |

> ⚠️ **Файловые операции контролируются двойной проверкой:** портал требует авторизации (JWT), а Nextcloud применяет свои ACL на папки/файлы через impersonation. Даже admin портала не получит файл, на который у его NC-аккаунта нет прав.

---

## Матрица: Поиск

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /search` | ✅ | ✅ | ✅ | Результаты с учётом прав (не показывает черновики reader) |
| `GET /search/suggest` | ✅ | ✅ | ✅ | Typeahead по заголовкам |

---

## Матрица: Ярлыки

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /links` | ✅ | ✅ | ✅ | Все активные ярлыки (с учётом `hidden_link_ids` пользователя) |
| `GET /links/{id}` | ✅ | ✅ | ✅ | Получить ярлык |
| `GET /links/{id}/sso-url` | ✅ | ✅ | ✅ | URL с `id_token_hint` если `supports_sso=true` |
| `POST /links` | ❌ | ❌ | ✅ | Создать ярлык |
| `PUT /links/{id}` | ❌ | ❌ | ✅ | Изменить ярлык |
| `DELETE /links/{id}` | ❌ | ❌ | ✅ | Удалить ярлык |

---

## Матрица: Закладки

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /bookmarks` | ✅ | ✅ | ✅ | Только свои закладки |
| `POST /bookmarks` | ✅ | ✅ | ✅ | Добавить в избранное |
| `DELETE /bookmarks/{id}` | ✅ (свои) | ✅ (свои) | ✅ | Удалить свою закладку |
| `PATCH /bookmarks/reorder` | ✅ (свои) | ✅ (свои) | ✅ | Сортировка |

---

## Матрица: Уведомления

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /notifications` | ✅ | ✅ | ✅ | Только свои уведомления |
| `POST /notifications/{id}/read` | ✅ | ✅ | ✅ | Пометить своё как прочитанное |
| `POST /notifications/read-all` | ✅ | ✅ | ✅ | Все свои |
| `GET /notifications/stream` | ✅ | ✅ | ✅ | SSE — только свои события |

---

## Матрица: Оформление (Branding)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /branding/settings` | 🌐 | 🌐 | 🌐 | Публичный — нужен до авторизации (portal_name, accent_color) |
| `GET /branding/logo` | 🌐 | 🌐 | 🌐 | Публичный — используется в AppLayout и LoginPage |
| `GET /branding/favicon` | 🌐 | 🌐 | 🌐 | Публичный — используется браузером |
| `GET /branding/login-bg` | 🌐 | 🌐 | 🌐 | Публичный — используется LoginPage |
| `PUT /admin/branding/settings` | ❌ | ❌ | ✅ | Название, слоган, accent color, welcome text, баннер |
| `POST /admin/branding/logo` | ❌ | ❌ | ✅ | PNG/JPEG/SVG/WebP, max 2 МБ |
| `DELETE /admin/branding/logo` | ❌ | ❌ | ✅ | Сброс к SVG-дефолту |
| `POST /admin/branding/favicon` | ❌ | ❌ | ✅ | ICO/PNG/JPEG/SVG/WebP, max 2 МБ |
| `DELETE /admin/branding/favicon` | ❌ | ❌ | ✅ | Сброс к дефолту браузера |
| `POST /admin/branding/login-bg` | ❌ | ❌ | ✅ | PNG/JPEG/SVG/WebP, max 2 МБ |
| `DELETE /admin/branding/login-bg` | ❌ | ❌ | ✅ | Сброс — скрывает BG, показывает SVG-волны |
| `GET /admin/branding/email/settings` | ❌ | ❌ | ✅ | Пароль возвращается только как `password_set: bool` |
| `PUT /admin/branding/email/settings` | ❌ | ❌ | ✅ | SMTP hostname/port/tls/starttls/credentials |
| `POST /admin/branding/email/test` | ❌ | ❌ | ✅ | Тестовое письмо на указанный адрес |

> 🌐 — доступен без JWT (но только из внутренней сети / VPN по Nginx IP-restrict)

---

## Матрица: Системные настройки (Admin UI)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /admin/system/settings` | ❌ | ❌ | ✅ | Nextcloud URL, CIDR, лимиты, log_level |
| `PUT /admin/system/settings` | ❌ | ❌ | ✅ | Автогенерация Nginx limits.conf/allowlist.conf + reload |
| `POST /admin/system/nginx/reload` | ❌ | ❌ | ✅ | Принудительный reload Nginx |
| `GET /admin/system/tls/status` | ❌ | ❌ | ✅ | Наличие и срок действия сертификата |
| `POST /admin/system/tls/cert` | ❌ | ❌ | ✅ | Загрузка PEM-сертификата |
| `POST /admin/system/tls/key` | ❌ | ❌ | ✅ | Загрузка PEM приватного ключа |
| `DELETE /admin/system/tls/cert` | ❌ | ❌ | ✅ | Удалить сертификат |
| `DELETE /admin/system/tls/key` | ❌ | ❌ | ✅ | Удалить ключ |

---

## Матрица: Настройки Keycloak (Admin UI)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /admin/keycloak/settings` | ❌ | ❌ | ✅ | Секреты маскируются (`*_secret_set: bool`) |
| `PUT /admin/keycloak/settings` | ❌ | ❌ | ✅ | Сохраняется в `/data/secrets/`, кеш сервиса сбрасывается |
| `POST /admin/keycloak/test/oidc` | ❌ | ❌ | ✅ | Проверка discovery + client_credentials |
| `POST /admin/keycloak/test/sync` | ❌ | ❌ | ✅ | Получение токена sync-клиента + 1 пользователь |
| `GET /admin/keycloak/sync/status` | ❌ | ❌ | ✅ | Дата/количество/статус последней синхронизации |
| `POST /admin/users/sync` | ❌ | ❌ | ✅ | Ручной запуск ARQ-задачи синхронизации |

---

## Матрица: Фотогалерея (Immich)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /photos/recent` | ✅ | ✅ | ✅ | `{"configured": false}` если модуль не включён |
| `GET /photos/thumbnail/{asset_id}` | ✅ | ✅ | ✅ | Disk-кэш; 404 если не настроен |
| `GET /admin/modules` (immich часть) | ❌ | ❌ | ✅ | Только admin |
| `PUT /admin/modules/immich` | ❌ | ❌ | ✅ | Только admin; секреты маскируются |

---

## Матрица: Видеопортал (PeerTube)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /videos/config` | ✅ | ✅ | ✅ | `{"configured": false}` если модуль не включён |
| `GET /videos/recent` | ✅ | ✅ | ✅ | OAuth2 через сервисный аккаунт; кэш токена |
| `GET /videos/thumbnail/{uuid}` | ✅ | ✅ | ✅ | Disk-кэш; 404 если не настроен |
| `PUT /admin/modules/peertube` | ❌ | ❌ | ✅ | Только admin; секреты маскируются |

---

## Матрица: Модули (Admin UI)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /admin/modules` | ❌ | ❌ | ✅ | Все модули; секреты заменены флагами `*_set: bool` |
| `PUT /admin/modules/immich` | ❌ | ❌ | ✅ | Хранение в `/data/settings/modules.json` (atomic write + chmod 0600) |
| `PUT /admin/modules/peertube` | ❌ | ❌ | ✅ | Хранение в `/data/settings/modules.json`; сброс OAuth-кэша при сохранении |
| `PUT /admin/modules/nextcloud` | ❌ | ❌ | ✅ | Placeholder; только флаг `enabled` |
| `POST /admin/modules/immich/test` | ❌ | ❌ | ✅ | Проверка соединения: server/about + альбом |
| `POST /admin/modules/peertube/test` | ❌ | ❌ | ✅ | Проверка OAuth2-токена; дополнительно сбрасывает кэш токена |

---

## Матрица: Аналитика и Аудит

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /analytics/dashboard` | ❌ | ❌ | ✅ | Только admin |
| `GET /analytics/top-articles` | ❌ | ❌ | ✅ | |
| `GET /analytics/top-files` | ❌ | ❌ | ✅ | |
| `GET /analytics/departments` | ❌ | ❌ | ✅ | |
| `GET /audit` | ❌ | ❌ | ✅ | Полный лог всех действий |
| `GET /audit/export.csv` | ❌ | ❌ | ✅ | |

---

## Матрица: Health & Metrics

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /health` | 🌐 | 🌐 | 🌐 | Публичный (только внутренняя сеть) |
| `GET /ready` | 🌐 | 🌐 | 🌐 | Публичный (только внутренняя сеть) |
| `GET /metrics` | ❌ | ❌ | ❌ | Только внутренняя сеть (Nginx IP-restrict), без JWT |

---

## Правила применения в коде

1. **Всегда использовать `Depends(require_role(...))`** — не проверять роль внутри функции endpoint
2. **«Свои» ресурсы** (`editor` редактирует только свои): дополнительная проверка `resource.created_by == current_user.id` внутри endpoint
3. **Soft-deleted ресурсы** не возвращаются никому без `?include_deleted=true` (только `admin`)
4. **Файловые операции** — двойная авторизация: JWT портала + ACL Nextcloud через impersonation
5. **Audit log пишется для всех операций** — включая неудачные (403, 404) с event_type `access_denied`
