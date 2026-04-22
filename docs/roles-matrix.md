# Матрица прав доступа

> Корпоративный интранет-портал
> Последнее обновление: апрель 2026

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
| `POST /admin/users/sync` | ❌ | ❌ | ✅ | Ручная синхронизация из Keycloak |
| `PATCH /admin/users/{id}/role` | ❌ | ❌ | ✅ | Изменение роли пользователя |

---

## Матрица: База знаний (KB)

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /kb/sections` | ✅ | ✅ | ✅ | Дерево разделов |
| `POST /kb/sections` | ❌ | ✅ | ✅ | Создать раздел |
| `PUT /kb/sections/{id}` | ❌ | ✅ | ✅ | Переименовать раздел |
| `DELETE /kb/sections/{id}` | ❌ | ❌ | ✅ | Удалить раздел (soft) |
| `DELETE /kb/sections/{id}?force=true` | ❌ | ❌ | ✅ | Удалить с содержимым |
| `GET /kb/articles` | ✅ | ✅ | ✅ | Список опубликованных статей |
| `GET /kb/articles?status=draft` | ❌ | ✅ (свои) | ✅ | Черновики — только свои у editor |
| `GET /kb/articles/{id}` | ✅ (опубликованные) | ✅ | ✅ | reader не видит чужие черновики |
| `POST /kb/articles` | ❌ | ✅ | ✅ | Создать статью |
| `PUT /kb/articles/{id}` | ❌ | ✅ (свои) | ✅ | editor редактирует только свои |
| `PUT /kb/articles/{id}/draft` | ❌ | ✅ (свои) | ✅ | Автосохранение черновика |
| `DELETE /kb/articles/{id}` | ❌ | ❌ | ✅ | Soft delete |
| `POST /kb/articles/{id}/restore` | ❌ | ❌ | ✅ | Восстановить удалённую |
| `GET /kb/articles/{id}/versions` | ✅ | ✅ | ✅ | История версий |
| `POST /kb/articles/{id}/versions/{n}/restore` | ❌ | ✅ | ✅ | Откат к версии |
| `POST /kb/articles/{id}/export/pdf` | ✅ | ✅ | ✅ | Экспорт PDF |
| `POST /kb/articles/{id}/export/docx` | ✅ | ✅ | ✅ | Экспорт DOCX |
| `GET /kb/articles/{id}/comments` | ✅ | ✅ | ✅ | Комментарии |
| `POST /kb/articles/{id}/comments` | ✅ | ✅ | ✅ | Добавить комментарий |
| `DELETE /kb/articles/{id}/comments/{cid}` | ❌ | ✅ (свои) | ✅ | Удалить комментарий |
| `POST /kb/articles/{id}/suggest` | ✅ | ✅ | ✅ | Предложить правку |

---

## Матрица: Новости

| Endpoint | reader | editor | admin | Примечание |
|---------|:------:|:------:|:-----:|-----------|
| `GET /news` | ✅ | ✅ | ✅ | С таргетингом по отделу/роли |
| `GET /news/{id}` | ✅ (опубликованные) | ✅ | ✅ | reader не видит черновики |
| `POST /news` | ❌ | ✅ | ✅ | Создать новость |
| `PUT /news/{id}` | ❌ | ✅ (свои) | ✅ | editor редактирует только свои |
| `PUT /news/{id}/draft` | ❌ | ✅ (свои) | ✅ | Автосохранение |
| `DELETE /news/{id}` | ❌ | ❌ | ✅ | Soft delete |
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
