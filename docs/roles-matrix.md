# Матрица прав доступа

> **Когда читать:** меняешь права доступа / «кто что видит» в любом модуле.
> **Ключевой код:** `app/api/deps.py` (`require_role`), `app/services/*_acl*`.
> **Роли:** reader / editor / admin + per-module ACL.

> Корпоративный интранет-портал
> Последнее обновление: апрель 2026 (v1.5) — финальный срез v1.x. Все модули: новости, KB, файлы, фотогалерея, брендинг, система, аудит, аналитика.

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
| `GET /bootstrap` | ✅ | ✅ | ✅ | Агрегация данных для SPA (reader+) |
| `POST /auth/local/login` | ✅ | ✅ | ✅ | Открытый; только `auth_source=local`; rate limit 5/15min/IP |
| `POST /auth/refresh` | ✅ | ✅ | ✅ | Только Keycloak-сессии; rate limit 30/мин/user |

---

## Матрица: Пользователи

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /users` | ✅ | ✅ | ✅ | Список сотрудников — доступен всем |
| `GET /users/{id}` | ✅ | ✅ | ✅ | Профиль любого сотрудника |
| `GET /users/departments` | ✅ | ✅ | ✅ | Список отделов |
| `GET /users/offices` | ✅ | ✅ | ✅ | Список офисов |
| `GET /users/export` | ✅ | ✅ | ✅ | Экспорт справочника в CSV/XLSX |
| `PATCH /users/me/profile` | ✅ | ✅ | ✅ | Только свой профиль (статус, аватар) |
| `PATCH /users/me/preferences` | ✅ | ✅ | ✅ | Только свои настройки уведомлений |
| `POST /users/me/avatar` | ✅ | ✅ | ✅ | Загрузка своего аватара |
| `PATCH /users/me/password` | ✅ | ✅ | ✅ | Только `auth_source=local`; иначе 403 |
| `POST /users/admin/local` | ❌ | ❌ | ✅ | Создать локального пользователя |
| `PATCH /users/admin/{id}/password` | ❌ | ❌ | ✅ | Сброс пароля; только `auth_source=local` |
| `POST /users/admin/sync` | ❌ | ❌ | ✅ | Ручная синхронизация из Keycloak (P2-41) |
| `PATCH /users/admin/{id}/role` | ❌ | ❌ | ✅ | Изменение роли пользователя (P2-41) |
| `DELETE /users/admin/{user_id}` | ❌ | ❌ | ✅ | Soft-delete пользователя |
| `PATCH /users/admin/{user_id}/profile` | ❌ | ❌ | ✅ | Редактирование профиля (только `auth_source=local`) |
| `GET /users/admin/{user_id}/groups` | ❌ | ❌ | ✅ | Список Keycloak-групп пользователя |
| `GET /users/admin/staff-order` | ❌ | ❌ | ✅ | Текущий порядок отделов и скрытые пользователи |
| `PUT /users/admin/staff-order` | ❌ | ❌ | ✅ | Сохранить порядок отделов и список скрытых |

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
| `POST /kb/sections` | ✅ | ✅ | ✅ | Создать раздел может любой; корневой — без ограничений, вложенный — editor+ на родителе; создатель получает manager |
| `PUT /kb/sections/{id}` | ❌ | ⚙ manager | ✅ | Переименовать/описание |
| `DELETE /kb/sections/{id}` | ❌ | ❌ | ✅ | Soft delete |
| `DELETE /kb/sections/{id}?force=true` | ❌ | ❌ | ✅ | Удалить с содержимым |
| `GET /kb/sections/{id}/permissions` | ❌ | ⚙ manager | ✅ | Список прав раздела |
| `POST /kb/sections/{id}/permissions` | ❌ | ⚙ manager | ✅ | Добавить/обновить право |
| `DELETE /kb/sections/{id}/permissions/{sid}` | ❌ | ⚙ manager | ✅ | Отозвать право |
| `PATCH /kb/sections/{id}/inherit` | ❌ | ⚙ manager | ✅ | Переключить наследование прав раздела |
| `GET /kb/sections/{id}/export/zip` | ⚙ viewer+ | ⚙ viewer+ | ✅ | ZIP раздела (Obsidian-совместимый) |
| `GET /kb/users/search` | ❌ | ✅ | ✅ | Поиск пользователей/групп для picker |

### Статьи

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /kb/articles` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Только доступные по ACL |
| `GET /kb/articles?status=draft` | ❌ | ⚙ editor+ (свои) | ✅ | Черновики — только свои у editor |
| `GET /kb/articles/{id}` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Проверка ACL + статус published для reader |
| `POST /kb/articles` | ✅ | ✅ | ✅ | Создать статью может любой; без раздела/в свой раздел — без ограничений, в чужой раздел — editor+ на разделе; создатель → manager |
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
| `GET /kb/articles/{id}/export/pdf` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Экспорт PDF |
| `GET /kb/articles/{id}/export/docx` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Экспорт DOCX |
| `GET /kb/articles/{id}/export/md` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Экспорт Markdown (YAML frontmatter) |
| `GET /kb/articles/{id}/comments` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Комментарии |
| `POST /kb/articles/{id}/comments` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Добавить комментарий |
| `DELETE /kb/articles/{id}/comments/{cid}` | ❌ | ⚙ viewer+ (свои) | ✅ | Удалить свой комментарий |
| `POST /kb/articles/{id}/suggest` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Предложить правку |
| `GET /kb/articles/{id}/suggestions` | ❌ | ⚙ editor+ | ✅ | Список правок |
| `POST /kb/suggestions/{id}/review` | ❌ | ⚙ editor+ | ✅ | Одобрить/отклонить правку |
| `POST /kb/articles/{id}/feedback` | ⚙ viewer+ | ⚙ viewer+ | ✅ | «Статья полезна?» |
| `GET /kb/tags` | ✅ | ✅ | ✅ | Список тегов (viewer+) |

### Медиа и вложения

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `POST /kb/articles/{id}/media` | ❌ | ⚙ editor+ | ✅ | Загрузка изображения в тело статьи |
| `GET /kb/media/{article_id}/{filename}` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Nginx X-Accel-Redirect, ACL-проверка |
| `GET /kb/articles/{id}/files` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Список вложений |
| `POST /kb/articles/{id}/files` | ❌ | ⚙ editor+ | ✅ | Загрузить вложение |
| `GET /kb/files/{article_id}/{filename}` | ⚙ viewer+ | ⚙ viewer+ | ✅ | Скачать вложение |
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
| `GET /news/limits` | ✅ | ✅ | ✅ | Лимиты загрузки (любой авторизованный) |
| `POST /news` | ❌ | ✅ | ✅ | Создать новость |
| `PUT /news/{id}` | ❌ | ✅ (свои) | ✅ | editor редактирует только свои |
| `PUT /news/{id}/draft` | ❌ | ✅ (свои) | ✅ | Автосохранение |
| `DELETE /news/{id}` | ❌ | ✅ | ✅ | Soft delete (editor может удалять) |
| `GET /news/trash` | ❌ | ❌ | ✅ | Список удалённых новостей |
| `POST /news/{id}/restore` | ❌ | ❌ | ✅ | Восстановить |
| `DELETE /news/{id}/purge` | ❌ | ❌ | ✅ | Hard-delete (только из корзины) |
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

## Матрица: Категории новостей

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /news-categories` | ✅ | ✅ | ✅ | Список категорий (все авторизованные) |
| `POST /news-categories` | ❌ | ✅ | ✅ | Создать категорию (editor+) |
| `PATCH /news-categories/{name}/color` | ❌ | ✅ | ✅ | Изменить цвет категории (editor+) |
| `PATCH /news-categories/{name}` | ❌ | ✅ | ✅ | Переименовать категорию (editor+) |
| `DELETE /news-categories/{name}` | ❌ | ✅ | ✅ | Удалить категорию (editor+) |

---

## Матрица: Поиск

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /search` | ✅ | ✅ | ✅ | Результаты с учётом прав (не показывает черновики reader); `type=directory_entry` — поиск объектов справочников по `name` (если мастер-флаг включён) |
| `GET /search/suggest` | ✅ | ✅ | ✅ | Typeahead по заголовкам |

---

## Матрица: Ярлыки

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /links` | ✅ | ✅ | ✅ | Все активные ярлыки (с учётом `hidden_link_ids` пользователя) |
| `GET /links/{id}` | ✅ | ✅ | ✅ | Получить ярлык |
| `GET /links/{id}/sso-url` | ✅ | ✅ | ✅ | URL с `id_token_hint` если `supports_sso=true` |
| `POST /links` | ❌ | ✅ | ✅ | Создать ярлык |
| `PUT /links/{id}` | ❌ | ✅ | ✅ | Изменить ярлык |
| `DELETE /links/{id}` | ❌ | ✅ | ✅ | Удалить ярлык |
| `PATCH /links/reorder` | ❌ | ✅ | ✅ | Изменить порядок ярлыков |
| `POST /links/{link_id}/icon` | ❌ | ✅ | ✅ | Загрузить иконку ярлыка |
| `DELETE /links/{link_id}/icon` | ❌ | ✅ | ✅ | Удалить иконку ярлыка |

---

## Матрица: Закладки

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /bookmarks` | ✅ | ✅ | ✅ | Только свои закладки |
| `POST /bookmarks` | ✅ | ✅ | ✅ | Добавить в избранное |
| `DELETE /bookmarks/{id}` | ✅ (свои) | ✅ (свои) | ✅ | Удалить свою закладку |
| `PATCH /bookmarks/reorder` | ✅ (свои) | ✅ (свои) | ✅ | Сортировка |
| `GET /bookmarks/favicon` | ✅ | ✅ | ✅ | Проксировать favicon сайта (с кэшем 7 дней) |

---

## Матрица: Уведомления

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /notifications` | ✅ | ✅ | ✅ | Только свои уведомления |
| `POST /notifications/{id}/read` | ✅ | ✅ | ✅ | Пометить своё как прочитанное |
| `POST /notifications/read-all` | ✅ | ✅ | ✅ | Все свои |
| `GET /notifications/stream` | ✅ | ✅ | ✅ | SSE — только свои события |
| `GET /notifications/unread-count` | ✅ | ✅ | ✅ | Количество непрочитанных уведомлений |

---

## Матрица: Оформление (Branding)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /branding/settings` | 🌐 | 🌐 | 🌐 | Публичный — нужен до авторизации (portal_name, accent_color) |
| `GET /branding/logo` | 🌐 | 🌐 | 🌐 | Публичный — используется в AppLayout и LoginPage |
| `GET /branding/favicon` | 🌐 | 🌐 | 🌐 | Публичный — используется браузером |
| `GET /branding/login-bg` | 🌐 | 🌐 | 🌐 | Публичный — используется LoginPage |
| `PUT /admin/branding/settings` | ❌ | ✅ | ✅ | Название, слоган, accent color, welcome text, баннер |
| `POST /admin/branding/logo` | ❌ | ✅ | ✅ | PNG/JPEG/WebP, max 2 МБ |
| `DELETE /admin/branding/logo` | ❌ | ✅ | ✅ | Сброс к SVG-дефолту |
| `POST /admin/branding/favicon` | ❌ | ✅ | ✅ | ICO/PNG/JPEG/WebP, max 2 МБ |
| `DELETE /admin/branding/favicon` | ❌ | ✅ | ✅ | Сброс к дефолту браузера |
| `POST /admin/branding/login-bg` | ❌ | ✅ | ✅ | PNG/JPEG/WebP, max 2 МБ |
| `DELETE /admin/branding/login-bg` | ❌ | ✅ | ✅ | Сброс — скрывает BG, показывает SVG-волны |
| `GET /admin/email-settings` | ❌ | ❌ | ✅ | Пароль возвращается только как `password_set: bool` |
| `PUT /admin/email-settings` | ❌ | ❌ | ✅ | SMTP hostname/port/tls/starttls/credentials |
| `POST /admin/email-settings/test` | ❌ | ❌ | ✅ | Тестовое письмо на указанный адрес |

> 🌐 — доступен без JWT (но только из внутренней сети / VPN по Nginx IP-restrict)

---

## Матрица: Системные настройки (Admin UI)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /admin/system/settings` | ❌ | ❌ | ✅ | Nextcloud URL, CIDR, лимиты, log_level |
| `PUT /admin/system/settings` | ❌ | ❌ | ✅ | Автогенерация Nginx limits.conf/allowlist.conf + reload |
| `PATCH /admin/system/settings` | ❌ | ❌ | ✅ | Частичное обновление настроек |
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
| `POST /users/admin/sync` | ❌ | ❌ | ✅ | Ручной запуск ARQ-задачи синхронизации |

---

## Матрица: Фотогалерея (собственный модуль)

> Доступ к ресурсу определяется per-folder ACL (`viewer` / `uploader` / `manager`) с наследованием вверх по дереву. Portal admin = manager везде; создатель папки / автор фото = manager на своём ресурсе.

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /photos/folders/tree` | ✅ | ✅ | ✅ | Возвращает только доступные пользователю узлы |
| `GET /photos/folders/{id}` | viewer | viewer | ✅ | 403 если нет ACL |
| `POST /photos/folders` | manager-of-parent | manager-of-parent | ✅ | Корневые папки — только admin |
| `PATCH /photos/folders/{id}` | manager | manager | ✅ | |
| `DELETE /photos/folders/{id}` | manager | manager | ✅ | Soft-delete |
| `GET /photos/folders/{id}/photos` | viewer | viewer | ✅ | Постраничный список |
| `POST /photos/folders/{id}/upload` | uploader | uploader | ✅ | Multipart; лимиты из настроек модуля |
| `GET /photos/{id}` | viewer | viewer | ✅ | |
| `PATCH /photos/{id}` | uploader | uploader | ✅ | Перенос требует uploader на целевой папке |
| `DELETE /photos/{id}` | uploaded_by | uploaded_by | ✅ | Иначе — manager на папке |
| `GET /photos/recent` | ✅ | ✅ | ✅ | Виджет; ACL-фильтрация после выборки |
| `GET /photos/thumbnail/{id}/{size}` | viewer | viewer | ✅ | X-Accel-Redirect; 200/400/600/1000/1600; `?format=webp\|avif` |
| `GET /photos/original/{id}` | viewer | viewer | ✅ | X-Accel-Redirect; `?download=1` для attachment |
| `POST /photos/{id}/share` | uploader | uploader | ✅ | Создание публичного токена (TTL 1..365 дн или без срока); audit `photos.share_created` |
| `GET /photos/public/{token}/info` | public | public | public | Без auth; 410 если истёк, 404 если отозван |
| `GET /photos/public/{token}/thumbnail/{size}` | public | public | public | X-Accel-Redirect; синхронная генерация при первом обращении |
| `GET /photos/public/{token}/file` | public | public | public | `?download=1` поддерживается |
| `POST /photos/folders/{id}/share` | manager | manager | ✅ | Создать публичный токен для папки |
| `GET /photos/folders/{id}/shares` | manager | manager | ✅ | Список токенов папки |
| `GET /photos/my-shares` | ✅ | ✅ | ✅ | Мои активные photo- и folder-токены |
| `DELETE /photos/my-shares/photo/{token_id}` | ✅ (свои) | ✅ (свои) | ✅ | Отозвать photo-токен |
| `DELETE /photos/my-shares/folder/{token_id}` | ✅ (свои) | ✅ (свои) | ✅ | Отозвать folder-токен |
| `GET /photos/public-folder/{token}/info` | public | public | public | Без auth; метаданные папки |
| `GET /photos/public-folder/{token}/photos` | public | public | public | Постраничный список фото |
| `GET /photos/public-folder/{token}/thumbnail/{size}` | public | public | public | X-Accel-Redirect |
| `GET /photos/folders/{id}/permissions` | manager | manager | ✅ | Список grant'ов на папке |
| `POST /photos/folders/{id}/permissions` | manager | manager | ✅ | Upsert по `(folder_id, subject_type, subject_id)` (миграция 056) |
| `DELETE /photos/folders/{id}/permissions/{subject_id}` | manager | manager | ✅ | Инвалидация Redis-кэша |
| `PUT /admin/modules/photos` | ❌ | ❌ | ✅ | Toggle/widget_limit/max_size/allowed_mime/strip_gps |

---

## Матрица: Модули (Admin UI)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /modules` | ✅ | ✅ | ✅ | Состояние модулей для UI (все авторизованные) |
| `GET /admin/modules` | ❌ | ❌ | ✅ | Все модули с полными настройками |
| `PUT /admin/modules/nextcloud` | ❌ | ❌ | ✅ | Placeholder; только флаг `enabled` |
| `PUT /admin/modules/photos` | ❌ | ❌ | ✅ | Toggle/widget_limit/max_size_mb/allowed_mime/strip_gps; пустой `allowed_mime` не очищает |
| `PUT /admin/modules/meetings` | ❌ | ❌ | ✅ | Toggle/calendar_start_hour/calendar_end_hour/max_recurrence_horizon_days/min_search_chars |
| `PUT /admin/modules/directories` | ❌ | ❌ | ✅ | Мастер-флаг раздела «Справочники объектов»; off → весь `/directories/*` 404 + скрыт из поиска |

---

## Матрица: Атрибуты пользователей (User Attribute Mappings)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /user-attribute-mappings` | ❌ | ❌ | ✅ | Список маппингов атрибутов |
| `POST /user-attribute-mappings` | ❌ | ❌ | ✅ | Создать маппинг |
| `PUT /user-attribute-mappings/{id}` | ❌ | ❌ | ✅ | Обновить маппинг |
| `DELETE /user-attribute-mappings/{id}` | ❌ | ❌ | ✅ | Удалить маппинг |
| `GET /user-attribute-mappings/discover` | ❌ | ❌ | ✅ | Найти атрибуты из `users.attributes` без маппинга |
| `GET /user-attribute-mappings/schema` | ❌ | ❌ | ✅ | Схема атрибутов (системные + все маппинги) |

---

## Матрица: Аналитика и Аудит

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /analytics/dashboard` | ❌ | ❌ | ✅ | Только admin |
| `GET /analytics/top-articles` | ❌ | ❌ | ✅ | |
| `GET /analytics/top-news` | ❌ | ❌ | ✅ | |
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

## Матрица: Файлы (§3.6 Phase 5)

> Доступ к папкам определяется ACL в `file_folder_permissions` (viewer/editor/manager). Роль портала даёт базовый доступ к модулю; `admin` автоматически получает `manager` на все папки.

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /files/tree` | viewer+ | viewer+ | ✅ | Только доступные папки |
| `GET /files/folders/{id}` | viewer+ | viewer+ | ✅ | viewer+ по ACL |
| `POST /files/folders` | ✅ | ✅ | ✅ | Создать папку может любой; корневую — без ограничений, вложенную — editor+ на родителе; создатель → manager |
| `PATCH /files/folders/{id}` | ❌ | manager* | ✅ | manager по ACL |
| `DELETE /files/folders/{id}` | ❌ | manager* | ✅ | manager по ACL |
| `POST /files/folders/{id}/upload` | ❌ | editor+ | ✅ | editor+ по ACL; rate-limit 20/мин |
| `GET /files/download` | viewer+ | viewer+ | ✅ | `require_file_access` = max(folder ACL, file share); `?folder_id=&filename=` |
| `GET /files/preview` | viewer+ | viewer+ | ✅ | `require_file_access` = max(folder ACL, file share); inline PDF/изображения |
| `DELETE /files/file` | ❌ | editor+ | ✅ | editor+ по ACL |
| `POST /files/folders/{id}/bulk-delete` | ❌ | editor+ | ✅ | editor+ по ACL; 3/мин; in-flight-guard |
| `POST /files/folders/{id}/bulk-move` | ❌ | editor+ | ✅ | editor+ на src и target; 3/мин |
| `POST /files/open` | viewer+ | viewer+ | ✅ | `require_file_access`; `can_write` при эффективном editor+ |
| `POST /files/sync` | ❌ | ❌ | ✅ | Синхронизация из Nextcloud (admin) |
| `GET /files/folders/{id}/permissions` | ❌ | manager* | ✅ | manager по ACL; создатель первым (`is_creator`) |
| `POST /files/folders/{id}/permissions` | ❌ | manager* | ✅ | manager по ACL; создателя нельзя — 409 |
| `DELETE /files/folders/{id}/permissions/{id}` | ❌ | manager* | ✅ | manager по ACL; создателя нельзя — 409 |
| `PATCH /files/folders/{id}/inheritance` | ❌ | manager* | ✅ | Переключить наследование прав |
| `POST /files/folders/{fid}/files/{filename}/shares` | ❌ | manager* | ✅ | Поделиться файлом; upsert; 20/мин |
| `GET /files/folders/{fid}/files/{filename}/shares` | ❌ | manager* | ✅ | Список шар файла |
| `DELETE /files/folders/{fid}/files/{filename}/shares/{sid}` | ❌ | manager* | ✅ | Отозвать шару файла (мягко) |
| `GET /files/shares/my` | ✅ | ✅ | ✅ | Мои шеры (что я выдал) |
| `GET /files/shares/shared-with-me` | ✅ | ✅ | ✅ | Доступные мне файлы |
| `GET /files/admin/shares` | ❌ | ❌ | ✅ | Реестр всех шеров (фильтры + пагинация) |
| `GET /files/users/search` | ❌ | editor/admin | ✅ | Поиск users/groups (Keycloak) |

> `viewer+` / `editor+` / `manager*` — уровень определяется `file_folder_permissions`, не глобальной ролью. Управление шарами файла (`.../shares`) требует `manager` на папке-контейнере (или admin); re-sharing получателем невозможен by design.

---

## Матрица: Справочники объектов (`/directories`)

> Вкладки в `/staff`. Чтение — любой авторизованный; все мутации (типы, объекты, контакты, аватары) — `editor`/`admin`. Двухуровневый гейтинг: мастер-флаг `modules.json` (`directories.enabled`) выключен → весь раздел 404; тип с `enabled=false` скрыт для не-editor. Каждая мутация → `audit_log` (`resource_type=directory`).

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /directories` | ✅ | ✅ | ✅ | Список типов-вкладок; editor/admin видят и `enabled=false` |
| `POST /directories` | ❌ | ✅ | ✅ | Создать тип + его `field_schema`/`channels` |
| `PATCH /directories/{id}` | ❌ | ✅ | ✅ | Обновить тип |
| `DELETE /directories/{id}` | ❌ | ✅ | ✅ | Soft-delete типа |
| `GET /directories/{slug}/entries` | ✅ | ✅ | ✅ | Список объектов; поиск `?q=` по `name` |
| `GET /directories/{slug}/entries/{id}` | ✅ | ✅ | ✅ | Объект с контактами |
| `POST /directories/{slug}/entries` | ❌ | ✅ | ✅ | Создать объект; валидация `attributes`/`channel` |
| `PATCH /directories/{slug}/entries/{id}` | ❌ | ✅ | ✅ | Обновить объект |
| `DELETE /directories/{slug}/entries/{id}` | ❌ | ✅ | ✅ | Soft-delete объекта |
| `POST /directories/{slug}/entries/{id}/avatar` | ❌ | ✅ | ✅ | Загрузить фото (streaming + python-magic, `/data`) |
| `DELETE /directories/{slug}/entries/{id}/avatar` | ❌ | ✅ | ✅ | Удалить фото |
| `GET /directories/{slug}/export` | ✅ | ✅ | ✅ | Экспорт `?format=csv\|xlsx\|pdf` |

---

## Правила применения в коде

1. **Всегда использовать `Depends(require_role(...))`** — не проверять роль внутри функции endpoint
2. **«Свои» ресурсы** (`editor` редактирует только свои): дополнительная проверка `resource.created_by == current_user.id` внутри endpoint
3. **Soft-deleted ресурсы** не возвращаются никому без `?include_deleted=true` (только `admin`)
4. **Файловые операции** — авторизация через ACL портала (`file_folder_permissions`). Nextcloud используется как хранилище через service account `portal-svc` (ADR-032)
5. **Audit log пишется для всех операций** — включая неудачные (403, 404) с event_type `access_denied`
