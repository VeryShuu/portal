# Корпоративный интранет-портал — Техническое требование и спецификация

> Версия: 1.0 (актуально)
>
> **Команда разработки:** AI-агент (Zencoder) + 1 инженер (владелец проекта). Без внешних сроков, без заказчика, без релизных дат — работаем в своём темпе до готовности.
>
> **Changelog:**
> - v1.0: Phase 2.1 завершена и задокументирована как реализованная: все чекбоксы [x]; bcrypt используется напрямую (`bcrypt` lib, SHA256 pre-hash) вместо passlib; `.env.example` дополнен ADMIN_EMAIL/ADMIN_PASSWORD/LOCAL_AUTH_ENABLED; матрица прав обновлена local auth endpoints; добавлена инструкция входа
> - v0.9: Добавлена таблица статусов фаз разработки (Phase 0-2 ✅, Phase 2.1 ⏳, Phase 3-7 ☐/🔒); добавлена секция **3.1.1 Локальная аутентификация** (bootstrap admin, email+bcrypt, смена/сброс пароля, rate limit, env-переменные, ограничения v1); добавлена строка «Аутентификация» в таблицу зафиксированных решений (auth_source + password_hash + единый Redis-механизм сессий); добавлена строка в оценку трудоёмкости (+2 дня, итого ~81.5); добавлен Phase 2.1 в plan.md с детальными substep'ами
> - v0.8: Исправлена версия в заголовке (0.6→0.7); удалены дублирующиеся SQL-блоки (источник правды — docs/db-schema.md); добавлен `preferences JSONB` в `users`; MAX_UPLOAD_SIZE_MB через .env; шаблоны документов перенесены в v2; зафиксирован статус NC_USER_ID_FIELD (TBD, файлы отложены); исправлен upload\_file\_as на streaming; hunspell и Playwright Docker задокументированы
> - v0.7: WebDAV path mapping — TBD до миграции NC; Loki отложен; a11y не в скопе v1; переводы i18n — AI-агент; уточнены Prerequisites (миграцию делает инженер)
> - v0.6: Обновлена команда разработки (AI + инженер); исправлена нумерация разделов (два "8." → "8." и "9."); rate limit 300/мин; ARQ monitoring через Sentry + Prometheus; AGENT.md в структуре репо; матрица прав вынесена в docs/roles-matrix.md
> - v0.5: Idempotency key — минимальный payload; Docker healthcheck → `/ready`; `avatars_data` volume
> - v0.4: Naive UI; TanStack Query; Markdown+TipTap dual-mode; Playwright PDF; fastapi-limiter; Sentry; Nextcloud impersonation переработан; httpx таймауты; FTS hunspell_ru; оптимистичная блокировка; CSRF упрощён; черновики; DOCX/PDF-viewer; вставка изображений; AD-синхронизация; пагинация; versioning policy; zero-downtime migrations; health checks; soft delete; rate limiting; observability
>
> Аудитория портала: ~300 сотрудников
> Доступ: только внутренняя сеть / корпоративный VPN

---

## 0. Зафиксированные решения

| Параметр | Решение |
|----------|---------|
| Фронтенд | **Vue 3 + TypeScript + Vite** |
| Бэкенд | **Python 3.12 + FastAPI** |
| Keycloak | уже развёрнут, единственный IdP для всей инфраструктуры |
| Аутентификация | **Keycloak OIDC (основной)** + **локальная форма email+bcrypt (аварийный/bootstrap)**. Поля в `users`: `auth_source VARCHAR(20)` (`keycloak`\|`local`), `password_hash VARCHAR(255) NULL` (bcrypt cost≥12, NULL для Keycloak-пользователей). Один сессионный механизм (Redis+HTTPOnly cookie) для обоих источников |
| Nextcloud + Collabora | уже развёрнуты |
| Nextcloud auth | **требует миграции** с прямого AD/LDAP на Keycloak OIDC (`user_oidc` app) |
| Интеграция с Nextcloud | **Вариант B (impersonation)**: все файловые операции от имени пользователя через Bearer JWT; редактирование в новой вкладке Nextcloud/Collabora; service account — только для Templates и webhooks |
| Email | **Postfix** (SMTP) |
| CI/CD | **GitHub Actions** |
| Язык интерфейса | **Русский + Английский** (i18n через vue-i18n) |
| PWA | отложено на будущее |
| Корпоративный календарь | отложено на будущее |

### Статус фаз разработки

| Фаза | Описание | Статус |
|------|----------|--------|
| Phase 0 | Инфраструктура (Docker, Nginx, CI/CD, Alembic, Prometheus) | ✅ Завершено |
| Phase 1 | Новости + Пользователи + i18n + Аутентификация Keycloak | ✅ Завершено |
| Phase 2 | Ярлыки сервисов + Закладки | ✅ Завершено |
| **Phase 2.1** | **Локальная аутентификация (bootstrap admin, аварийный вход)** | **✅ Завершено** |
| Phase 3 | База знаний + Умный поиск | ☐ Запланировано |
| Phase 4 | Email + In-app уведомления (SSE) | ☐ Запланировано |
| Phase 5 | Файлы через Nextcloud + Collabora | 🔒 Заблокировано (ждём миграции NC → Keycloak OIDC) |
| Phase 6 | Аудит-дашборд + Аналитика + Observability | ☐ Запланировано |
| Phase 7 | Финальное тестирование + Поставка | ☐ Запланировано |

---

## ⚠️ Предварительные условия (до начала разработки портала)

> **Ответственный за миграцию:** инженер (владелец проекта) лично.
> **Блокер:** модуль файлов (Вариант B, impersonation) **не разрабатывается** до завершения миграции Nextcloud → Keycloak OIDC и успешного smoke-теста Bearer к WebDAV.

### Миграция Nextcloud: AD/LDAP → Keycloak OIDC

Сейчас Nextcloud авторизует пользователей напрямую через Active Directory (LDAP). Это нужно изменить — иначе портал не сможет делать запросы к Nextcloud WebDAV/OCS от имени пользователей.

**Шаги миграции (~1 рабочий день):**

1. Установить приложение `user_oidc` в Nextcloud (`Apps → Search → OpenID Connect user backend`)
2. Настроить OIDC-провайдер в Nextcloud Admin → Security:
   ```
   Identifier:    keycloak
   Client ID:     nextcloud
   Client Secret: <из Keycloak>
   Discovery URL: https://auth.company.local/realms/corporate/.well-known/openid-configuration
   ```
3. Настроить маппинг атрибутов: `sub` → user ID, `email` → email, `name` → displayName
4. Провести тестовый вход через Keycloak в Nextcloud
5. Убедиться, что группы из AD (через Keycloak → `groups` claim) маппятся в группы Nextcloud
6. Отключить прямую LDAP-интеграцию Nextcloud (она дублирует то, что Keycloak уже делает)

**Результат:** один Keycloak управляет всеми пользователями. Nextcloud принимает Keycloak-сессию через браузер (cookie-based SSO). Портал обращается к Nextcloud **от имени конкретного пользователя** (impersonation через Bearer JWT), service account используется только для системных операций без user-контекста.

### Проверка версии `user_oidc` (критично)

Для impersonation портала в Nextcloud требуется `user_oidc` с поддержкой **Bearer token authentication** (принимает JWT из заголовка `Authorization: Bearer ...`, а не только cookie-сессию). Это появилось в версии ~1.3.

**Проверка (~15 минут):**

1. В Nextcloud Admin → Apps проверить версию `OpenID Connect user backend` (требуется ≥ 1.3)
2. Настроить в Nextcloud Admin → Security → OpenID Connect опцию `Use unique user ID` и включить Bearer auth (если флаг есть)
3. Smoke test:
   ```bash
   # Получить access_token от Keycloak через service account flow или password grant:
   TOKEN=$(curl -s -d "client_id=portal" -d "grant_type=password" \
           -d "username=testuser" -d "password=..." \
           https://auth.company.local/realms/corporate/protocol/openid-connect/token \
           | jq -r .access_token)

   # Запросить WebDAV PROPFIND с Bearer:
   curl -X PROPFIND -H "Authorization: Bearer $TOKEN" -H "Depth: 1" \
        https://nextcloud.company.local/remote.php/dav/files/testuser/
   # Должен вернуть 207 Multi-Status с содержимым папки testuser
   ```
4. **Если тест не проходит** (405/401) — нужно обновить `user_oidc` или использовать fallback-вариант (см. раздел 3.6, «Fallback»)

> ⚠️ **WebDAV path mapping — TBD (определить при миграции), файловый модуль ЗАМОРОЖЕН:**
> В Nextcloud `user_oidc` есть опция `Use unique user ID` (ON/OFF). Она определяет, что станет именем пользователя в WebDAV-пути:
> - `OFF` → используется `preferred_username` (например `ivanov`) → путь: `/remote.php/dav/files/ivanov/`
> - `ON` → используется UUID-sub из Keycloak → путь: `/remote.php/dav/files/{uuid}/`
>
> **Статус:** инженер ещё не провёл миграцию Nextcloud → Keycloak OIDC и не определил `NC_USER_ID_FIELD`. **Разработка модуля файлов (§3.6) не начинается** до получения этого значения.
> **Инженер фиксирует выбор в `.env`** как `NC_USER_ID_FIELD=preferred_username` или `NC_USER_ID_FIELD=sub`. Код в `nextcloud.py` строит WebDAV-путь из этой переменной.

### Настройка audience в Keycloak (критично для impersonation)

JWT пользователя, выданный Keycloak для портала, по умолчанию имеет `aud: portal` — Nextcloud его отклонит. Нужно добавить Nextcloud в audience токена.

**Шаги (~15 минут):**

1. Keycloak Admin Console → Clients → `portal` → Client Scopes → `portal-dedicated` → Add mapper → By configuration → **Audience**:
   ```
   Mapper type:          Audience
   Name:                 nextcloud-audience
   Included Client Audience: nextcloud
   Add to access token:  ON
   ```
2. После этого access_token, выданный порталу, содержит `aud: ["portal", "nextcloud"]` — Nextcloud примет такой токен.
3. **Альтернатива (сложнее, гибче)**: включить Keycloak Token Exchange (feature-preview). Тогда портал явно меняет свой токен на токен для Nextcloud через `POST /token` с `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`. Используется, если нельзя добавить audience в основной токен.

### Настройка Keycloak Protocol Mappers

Поля `department`, `job_title`, `phone` не попадают в JWT автоматически — требуется явная настройка в Keycloak.

**Шаги (~30 минут):**

1. Keycloak Admin Console → Clients → `portal` → Client Scopes → Add mapper:
   ```
   Mapper type:    User Attribute
   Name:           department
   User Attribute: department          ← атрибут из LDAP Federation
   Token Claim:    department
   Claim JSON type: String
   Add to ID token: ON
   Add to access token: ON
   ```
2. Повторить для `job_title` (→ `position`) и `phoneNumber` (→ `phone`)
3. Настроить mapper для `groups` claim:
   ```
   Mapper type: Group Membership
   Token Claim: groups
   Full path:   OFF
   ```
4. Проверить через `GET /realms/corporate/protocol/openid-connect/userinfo`

> ⚠️ **Без настройки Protocol Mappers** портал не получит отдел и должность из JWT — профили будут пустыми.

### ⚠️ Риск: Single Logout (SLO) в Nextcloud

`user_oidc` приложение в Nextcloud поддерживает SLO ограниченно — backchannel logout работает нестабильно в некоторых версиях. **Обязательно протестировать до финализации архитектуры.**

**Fallback (если SLO не работает):** при logout из портала делать redirect на Keycloak logout endpoint (`/realms/.../protocol/openid-connect/logout?post_logout_redirect_uri=...`) — Keycloak инвалидирует сессии у всех подключённых клиентов через front-channel.

### Настройка service account (portal-svc) — только для системных операций

> ⚠️ **Важно**: service account **не используется для файловых операций пользователей**. Все CRUD над файлами (листинг, скачивание, загрузка, шаринг) делаются от имени самого пользователя через Bearer JWT (impersonation). Service account применяется только там, где нет user-контекста.

**Разделение ответственности:**

| Операция | Исполнитель | Обоснование |
|----------|------------|-------------|
| Листинг / скачивание / загрузка / удаление / шаринг файлов | **Bearer user token** | ACL проверяется Nextcloud per-user; audit trail корректный |
| Поиск по файлам | **Bearer user token** | Результаты ограничены ACL пользователя |
| Чтение библиотеки `/Templates/` (отображение шаблонов) | service account | Nет user-контекста, шаблоны публичные для всех сотрудников |
| Копирование шаблона в `/shared/` пользователя | **Bearer user token** | Пишем в user-space, должен проверяться ACL на target |
| Webhook от Nextcloud (события файловых изменений) | service account | Nextcloud → портал, инициатор не user |
| Health check `/status.php` | без auth | Публичный endpoint Nextcloud |
| Массовые миграции / чистки (admin scripts) | service account | Явное admin действие, логируется отдельно |

**Настройка service account:**

1. В Nextcloud создать технический аккаунт `portal-svc` (не основной admin)
2. Создать **App Password**: `Settings → Security → Devices & sessions → Generate app password`
3. Назначить доступ только к системным папкам (`/Templates/`, служебные `/system/`) — **не к корпоративным пользовательским папкам**
4. App password сохранить в secrets (env-переменная `NC_SERVICE_APP_PASSWORD`)
5. **Ротация**: каждые 90 дней — обновить app password и secrets в `.env`

---

## 1. Архитектурная концепция

### Общий принцип

Портал — это **единое окно (hub)**, а не монолит. Он не дублирует данные, а агрегирует и отображает то, что уже хранится в инфраструктуре:

- **Keycloak** — единственный IdP: SSO, OIDC, федерация с Active Directory
- **Nextcloud** — файловое хранилище; портал читает структуру через WebDAV/OCS API
- **Collabora Online** — редактор документов, встроен в Nextcloud; открывается в новой вкладке

> Портал **не обращается к AD напрямую**. Все данные о пользователях (ФИО, отдел, должность, группы) получаются из JWT-токена Keycloak, который сам синхронизируется с AD через LDAP Federation.

```
Active Directory ──(LDAP sync)──► Keycloak
                                      │
                              (OIDC / JWT tokens)
                                      │
              ┌───────────────────────┼────────────────────────┐
              │                       │                        │
         [Портал]              [Nextcloud]               [другие сервисы]
              │                 (user_oidc app)           (Jira, GitLab...)
              │
[Nginx reverse proxy + TLS]
              │
      ┌───────┴────────┐
      │                │
[Frontend SPA]   [Backend API: FastAPI]
 Vue 3 + TS           │
                  ┌────┴─────────────────────────┐
                  │                              │
            [PostgreSQL 16]               [Redis 7]
         статьи, новости, аудит,       кэш, очереди (ARQ),
         закладки, профили, шаблоны    rate limiting

                  │
          [Nextcloud WebDAV/OCS]
         Портал передаёт Bearer {user_access_token} в каждом запросе
         → Nextcloud (user_oidc) резолвит JWT → применяет ACL пользователя
         Service account — только для системных операций (Templates, webhooks)
```

---

## 2. Технологический стек

| Слой | Технология | Обоснование |
|------|-----------|------------|
| Фронтенд | Vue 3 + TypeScript + Vite | Composition API, лёгкий, быстрый |
| UI-библиотека | **Naive UI** | 100% TypeScript-first, dark/light тема через CSS variables нативно, ~120 KB, без Material Design opinionated-стиля |
| Управление состоянием | Pinia | Официальный стейт-менеджер Vue 3 |
| Маршрутизация | Vue Router 4 | — |
| i18n | vue-i18n v9 | Русский + Английский |
| HTTP-клиент фронтенд | **TanStack Query (Vue Query) + ofetch** | Vue Query: кэш, дедупликация, retry, cancel-on-unmount; ofetch — HTTP-транспорт |
| WYSIWYG-редактор | **TipTap v2** + `tiptap-markdown` (community) | Dual-mode: визуальный WYSIWYG ↔ raw Markdown; хранение в MD (CommonMark + GFM) |
| Бэкенд | Python 3.12 + FastAPI | Async, OpenAPI 3.0 автодокументация, Pydantic v2 |
| ORM | SQLAlchemy 2.0 (async) | Типобезопасные запросы, migrations через Alembic |
| Очереди задач | **ARQ** (async Redis Queue) | Отложенные задачи: рассылки, архивация, экспорт |
| БД основная | PostgreSQL 16 | FTS, JSONB, pg_trgm, партиционирование |
| Полнотекстовый поиск | PostgreSQL FTS (`hunspell_ru`) + pg_trgm | Достаточно для 300 пользователей без Elasticsearch |
| Кэш / сессии | Redis 7 | Кэш API-ответов, OIDC state, очереди |
| IdP | Keycloak (существующий) | OIDC, AD LDAP Federation |
| Файловое хранилище | Nextcloud (существующий) | WebDAV + OCS API |
| Редактор документов | Collabora Online (существующий) | WOPI protocol |
| Email | Postfix | SMTP через aiosmtplib |
| Контейнеризация | Docker + Docker Compose v2 | Self-hosted, без облака |
| Reverse proxy | Nginx | TLS termination, security headers, rate limiting |
| CI/CD | GitHub Actions | Lint, test, build Docker images |

### i18n процесс

- **Языки:** русский (основной, fallback) + английский
- **Библиотека:** vue-i18n v9
- **Файлы ключей:** `frontend/src/i18n/ru.json` (мастер), `frontend/src/i18n/en.json`
- **Кто переводит:** AI-агент (Zencoder) — генерирует оба файла одновременно при создании компонентов
- **Fallback:** при отсутствии ключа в `en.json` показывается русский текст из `ru.json`
- **Тестирование:** Playwright snapshot-тест при смене языка; CI-проверка на отсутствующие ключи (сравнение множеств ключей `ru.json` vs `en.json`)

### Accessibility (a11y)

Специализированные требования WCAG **не входят в скоп v1**. Обеспечивается базовая функциональность:
- семантический HTML (nav, main, section, button, label)
- keyboard navigation через Naive UI из коробки
- цветовой контраст тёмной/светлой темы через Naive UI CSS variables

---

## 3. Финальный список функционала

### 3.1. Аутентификация и авторизация

- [ ] **OIDC SSO через Keycloak** — Authorization Code Flow с PKCE
- [ ] **Silent authentication** — попытка тихой авторизации через `prompt=none` при открытии портала
- [ ] **Single Logout (SLO)** — выход завершает сессии в Nextcloud и Keycloak через backchannel logout
- [ ] **Ролевая модель**: `reader`, `editor`, `admin` — маппинг из Keycloak realm roles
- [ ] **Синхронизация групп AD** через Keycloak LDAP User Federation (уже настроен)
- [ ] **Refresh token rotation** — автоматическое обновление сессии без перелогина
- [ ] **Блокировка доступа** из публичной сети — Nginx allow/deny по IP-диапазонам внутренней сети + VPN
- [ ] **Аудит входов/выходов** — запись в `audit_log`
- [ ] **Хранение user access_token для Nextcloud** — серверная сессия в Redis, не в cookie
  - При логине через OIDC портал получает `access_token` (с `aud: [portal, nextcloud]`) и `refresh_token`
  - Оба токена сохраняются в Redis: `session:{session_id}` → `{access_token, refresh_token, expires_at, nc_access_token}`
  - В HTTPOnly cookie клиенту уходит только `session_id` (UUID), не сам JWT
  - Перед запросом к Nextcloud: если `nc_access_token` истёк (за 60 сек до exp) → рефреш через Keycloak `/token` endpoint, обновление в Redis
  - **Почему отдельный `nc_access_token`**: если используется Token Exchange — токен для NC отличается от токена для портала. Если audience mapper — это один и тот же JWT, но логика одна
  - При SLO / logout — очистка ключа Redis + revoke токенов через Keycloak `/revoke`
- [ ] **Ручная синхронизация пользователей из AD (admin)** — кнопка «Синхронизировать всех пользователей» в админ-панели
  - **Проблема**: данные из AD попадают в портал только при следующем логине пользователя (через JWT claims). Если кадровик обновил телефон/должность в AD, изменения не видны до входа сотрудника
  - **Решение**: admin нажимает кнопку → backend вызывает Keycloak Admin API (`GET /admin/realms/{realm}/users`) → для каждого пользователя обновляет запись `users` (full_name, email, department, position, phone) по `keycloak_id`
  - **Реализация**: ARQ-задача (долгая операция, не блокирует запрос), прогресс через SSE или polling; fire-and-forget, результат в `audit_log` (`admin_action: sync_users`)
  - **Rate-limit**: 1 запуск в 5 минут на admin (защита от случайного повтора)
  - **Автоматический запуск**: cron раз в сутки (03:00) через ARQ, на случай если admin забыл

**Технические детали:**
```python
# Конфигурация OIDC (из env)
KEYCLOAK_URL = "https://auth.company.local"
REALM = "corporate"
CLIENT_ID = "portal"
CLIENT_SECRET = "..."  # confidential client
SCOPES = ["openid", "profile", "email", "groups"]

# Маппинг Keycloak claims → модель пользователя
user.keycloak_id = token["sub"]
user.full_name   = token["name"]
user.email       = token["email"]
user.department  = token["department"]   # custom claim, маппинг из AD ou
user.position    = token["job_title"]    # custom claim из AD
user.phone       = token.get("phone_number")
user.roles       = token["realm_access"]["roles"]
```

---

### 3.1.1. Локальная аутентификация (Phase 2.1)

> **Контекст:** Keycloak — основной IdP для всей инфраструктуры. Однако для первоначальной настройки (bootstrap первого admin) и аварийного доступа необходима возможность входа без Keycloak — по email + паролю напрямую в портале.

**Принцип сосуществования двух источников аутентификации:**
- Пользователи с `auth_source = "keycloak"` — входят только через Keycloak OIDC (как сейчас)
- Пользователи с `auth_source = "local"` — входят через форму email + пароль (`POST /auth/local/login`)
- Сессионный механизм (Redis + HTTPOnly cookie) — **единый** для обоих источников, middleware неизменен
- Keycloak-пользователи **не могут** войти по паролю и наоборот

**Функционал:**

- [x] **Локальный вход** — `POST /api/v1/auth/local/login` принимает `{email, password}`, создаёт сессию в Redis, устанавливает `session_id` cookie
- [x] **Форма входа на фронтенде** — страница `/login` с кнопкой «Войти через Keycloak (SSO)» + форма email+password; при 403/401 от Keycloak автоматически показывается форма
- [x] **Bootstrap первого admin** — при старте бэкенда: если в env заданы `ADMIN_EMAIL` + `ADMIN_PASSWORD` и нет ни одного пользователя с `role = "admin"` → создаётся локальный пользователь-admin (idempotent)
- [x] **Создание локальных пользователей** — `POST /api/v1/users/admin/local` (только admin): `{email, full_name, password, role}` → создаётся локальный пользователь
- [x] **Смена пароля** — `PATCH /api/v1/users/me/password`: `{current_password, new_password}` (только для `auth_source = "local"`)
- [x] **Сброс пароля admin'ом** — `PATCH /api/v1/users/admin/{id}/password`: `{new_password}` (только admin, только для локальных пользователей)
- [x] **Аудит** — входы/выходы локальных пользователей пишутся в `audit_log` (`event_type = "local_login"`)

**Схема изменений БД (`users`):**
```sql
ALTER TABLE users
    ADD COLUMN auth_source VARCHAR(20) NOT NULL DEFAULT 'keycloak',
    -- 'keycloak' | 'local'
    ADD COLUMN password_hash VARCHAR(255);
    -- NULL для Keycloak-пользователей, bcrypt hash для локальных

-- keycloak_id становится nullable для локальных пользователей
ALTER TABLE users ALTER COLUMN keycloak_id DROP NOT NULL;
```

**Безопасность:**
- Пароли — bcrypt cost≥12 через `bcrypt` lib напрямую (SHA256 pre-hash перед bcrypt — обход лимита 72 байта)
- `ADMIN_PASSWORD` из env применяется **только при bootstrap** и не логируется
- Rate limit: 5 попыток / 15 минут / IP через `fastapi-limiter` (возвращает 429)
- Локальный вход недоступен если `auth_source = "keycloak"` — явная 403 с сообщением «Use Keycloak SSO»
- Нет `forgot password` / email-ссылок — только admin сбрасывает пароль через API

**Переменные окружения (новые):**

| Переменная | Назначение | Пример |
|-----------|-----------|--------|
| `ADMIN_EMAIL` | Email первого admin (bootstrap) | `admin@company.local` |
| `ADMIN_PASSWORD` | Пароль первого admin (bootstrap) | `change_me_on_first_login` |
| `LOCAL_AUTH_ENABLED` | Включить/выключить локальный вход | `true` |

**Ограничения v1:**
- Нет self-service forgot password (нет email-рассылки паролей — только admin сбрасывает)
- Нет 2FA для локальных пользователей
- Локальные пользователи не синхронизируются с Keycloak

---

### 3.2. Профили пользователей

- [ ] **Карточка пользователя**: ФИО, Email, Должность, Отдел, Телефон — из Keycloak JWT claims
- [ ] **Аватар**: загрузка фото профиля (хранится в local volume `/data/avatars/{user_id}.jpg`, отдаётся через Nginx static location; в БД — только относительный путь)
- [ ] **Статус присутствия**: «В офисе» / «Удалённо» / «В отпуске» — ручной выбор пользователем, хранится в таблице `users`
- [ ] **Страница «Команда»**: справочник всех сотрудников с поиском по имени/отделу/должности
- [ ] **Карточка сотрудника**: кликабельный профиль с контактами

**Технические детали:**
- Данные синхронизируются через Keycloak при каждом входе (JWT claims) — портал не ходит в AD напрямую
- Аватар хранится в **local volume** портала (`/data/avatars/`), отдаётся Nginx как статика (`/static/avatars/`); 300 аватаров × 200 КБ = ~60 МБ — не проблема для volume
- При первом входе создаётся/обновляется запись `users` на основе JWT claims

**Схема БД:**
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keycloak_id VARCHAR(36) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    position VARCHAR(255),
    phone VARCHAR(50),
    avatar_url VARCHAR(512),               -- относительный путь: /static/avatars/{user_id}.jpg
    presence_status VARCHAR(20)            -- 'office', 'remote', 'vacation'
        DEFAULT 'office',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
-- user_profiles как отдельная таблица не нужна: всего 2 поля, один JOIN меньше
```

---

### 3.3. База знаний

- [ ] **Древовидная структура разделов** — adjacency list, неограниченная вложенность
- [ ] **Dual-mode редактор статей** — TipTap v2 + `tiptap-markdown` (community package):
  - Режим **«Визуальный»** (по умолчанию) — WYSIWYG в рамках CommonMark + GFM: H1-H6, таблицы, код, списки, ссылки, изображения
  - Режим **«Markdown»** — raw-редактирование в CodeMirror с подсветкой синтаксиса
  - Кнопка переключения в тулбаре; контент конвертируется без потерь в обе стороны
  - **Хранение в БД**: Markdown (source of truth); рендеринг на фронте через TipTap
  - **Ограничения**: без resize изображений, без custom embeds — только то, что выражается в CommonMark/GFM
  - **Вставка изображений** — кнопка в тулбаре открывает модалку файлового браузера (тот же компонент из раздела 3.6); пользователь выбирает файл в Nextcloud → в MD вставляется `![alt](https://nextcloud.company.local/...)`; Ctrl+V скриншота → автозагрузка в Nextcloud (PUT через бэкенд) → вставка ссылки
  - **Санитизация на бэкенде**: `bleach` (Python) — запрет raw HTML-вставок в MD перед сохранением
  - Преимущества: чистый `diff` в версионировании, читаем без рендера, онлайн-редакторы MD совместимы
- [ ] **Версионность статей** — каждое сохранение создаёт снимок, просмотр diff, откат к версии
- [ ] **Теги и категории** — многие-ко-многим через junction table
- [ ] **Полнотекстовый поиск** — PostgreSQL FTS с `hunspell_ru` (лемматизация лучше Snowball) + `pg_trgm` для нечёткого поиска
- [ ] **Экспорт в PDF** — Playwright/Chromium на бэкенде (`page.pdf()`): рендерит MD → HTML → PDF; Chromium уже есть в образе для E2E-тестов, нет дополнительных зависимостей (Cairo/Pango не нужны)
- [ ] **Экспорт в DOCX** — для редактируемого скачивания (PDF нельзя изменить)
  - **Сценарий**: сотрудник хочет скачать статью, поправить локально, разослать коллегам
  - **Технически**: `markdown` (Python) → HTML → `python-docx` с конвертером (например, `htmldocx` или собственный маппер стилей); сохраняются заголовки, списки, таблицы, жирный/курсив, ссылки
  - **Ограничения**: изображения только по абсолютным URL (внутри сети), код-блоки рендерятся моноширинным шрифтом без подсветки
  - **Endpoint**: `POST /api/v1/kb/articles/{id}/export/docx` → `StreamingResponse` с `Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - **Rate-limit**: 5 req/мин/user (аналогично PDF)
  - **Оценка**: 1 чел.-день
- [ ] **Хлебные крошки** — автогенерация по пути в дереве через рекурсивный CTE
- [ ] **Счётчик просмотров** — дедупликация: 1 просмотр на пользователя в течение 1 часа (Redis)
- [ ] **Комментарии к статьям** — внутренние, только авторизованные сотрудники
- [ ] **«Предложить правку»** — любой сотрудник может создать draft-версию статьи; редактор получает уведомление, утверждает или отклоняет; принятая правка становится новой версией
- [ ] **Обратная связь** — кнопка «Статья полезна?» (helpful/not helpful) для оценки качества контента
- [ ] **Блокировка редактирования** — **оптимистичная блокировка** через поле `version INTEGER`: при UPDATE проверяется `WHERE id=... AND version=:expected`; несовпадение → 409 Conflict с diff конфликтующих версий
- [ ] **Soft delete** — `deleted_at`; статья не удаляется физически, admin может восстановить или полностью очистить

> Полная схема таблиц (`kb_sections`, `kb_articles`, `kb_article_versions`, `kb_tags`, `kb_article_tags`, `kb_article_comments`): [`docs/db-schema.md`](docs/db-schema.md)

---

### 3.4. Новости и объявления

- [ ] **Создание новости** через TipTap WYSIWYG-редактор
- [ ] **Таргетирование** по отделам, ролям, конкретным пользователям (через атрибуты AD из Keycloak)
- [ ] **Отложенная публикация** — поле `publish_at`, ARQ cron-задача публикует по расписанию
- [ ] **Автоматическая архивация** — поле `archive_at`, фоновая задача переводит в `archived`
- [ ] **Email-уведомления** — через Postfix (aiosmtplib), опционально для каждого пользователя
- [ ] **In-app push-уведомления** — SSE через Redis Streams
- [ ] **Закрепление новости** — флаг `is_pinned`, показывается первой
- [ ] **Категории новостей**: Компания, IT, HR, Проекты и т.д.
- [ ] **Прикреплённые файлы** — ссылки на файлы в Nextcloud (не копирование)
- [ ] **Soft delete** — `deleted_at`, новость не удаляется физически; admin может восстановить
- [ ] **Версионность новостей** — каждое сохранение создаёт снимок (аналогично KB-статьям); просмотр истории редактирования
- [ ] **Черновики с автосохранением** — защита от потери данных при закрытии браузера
  - **Сценарий**: редактор пишет длинную новость, отвлекается, случайно закрывает вкладку → весь текст потерян
  - **Решение**: отдельное поле `draft_body TEXT` и `draft_title VARCHAR(500)` в таблице `news` (не в `news_versions`, чтобы не плодить мусорные версии)
  - **Автосохранение**: фронтенд каждые 30 секунд при наличии изменений (debounced watcher в TipTap) шлёт `PUT /api/v1/news/{id}/draft` с текущим телом; если `id` ещё нет — создаётся черновик со `status='draft'`
  - **Индикация в UI**: «Сохранено 14:32» / «Сохранение…» / «Не сохранено» (статус в Pinia store)
  - **Публикация**: при нажатии «Опубликовать» `draft_body` переносится в `body`, создаётся запись в `news_versions`, `draft_body` обнуляется
  - **Черновики редактора**: `GET /api/v1/news?status=draft&author=me` — список «Мои черновики» на странице создания новости
  - **Idempotency**: PUT /draft — идемпотентен по природе (полная замена), `Idempotency-Key` не нужен
  - **Применимо также к KB-статьям** — аналогичная схема: поля `draft_body`, `draft_title` в `kb_articles`

> Полная схема таблиц (`news`, `news_versions`): [`docs/db-schema.md`](docs/db-schema.md)

---

### 3.5. Навигация и ярлыки сервисов

- [ ] **Панель ярлыков**: 1C, Jira, GitLab, CRM, почта, видеоконференция и другие
- [ ] **SSO-проброс** — если сервис поддерживает OIDC/SAML, передаётся Keycloak id_token hint
- [ ] **Управление ярлыками** — только `admin`, интерфейс в панели администратора
- [ ] **Персонализация** — пользователь скрывает ненужные ярлыки (хранится в поле `preferences JSONB` таблицы `users`, ключ `hidden_link_ids: [uuid, ...]`)
- [ ] **Категории ярлыков**: Разработка, Финансы, HR, Общие, Коммуникации

> Полная схема таблицы (`service_links`): [`docs/db-schema.md`](docs/db-schema.md)

---

### 3.6. Интеграция с Nextcloud + Collabora

**Подход (Вариант B — impersonation):** портал — UI + orchestration слой, не WebDAV-прокси с ACL-обходом. Все файловые операции выполняются **от имени пользователя** через Bearer JWT, полученный от Keycloak. Nextcloud (`user_oidc`) валидирует JWT, резолвит пользователя по `sub` и применяет его ACL. Service account используется **только** для системных операций без user-контекста (Templates, webhooks). Портал **не реализует WOPI-сервер**.

**Почему именно так (обоснование):**
- ✅ **Корректные ACL**: если у пользователя нет доступа к папке в Nextcloud — портал тоже её не покажет. Нет обхода прав
- ✅ **Единый audit trail**: в Nextcloud логах имя реального пользователя, совпадает с `audit_log` портала
- ✅ **Compliance**: ISO 27001 / 152-ФЗ требуют индивидуальной идентификации в логах файловых операций
- ✅ **Квоты per-user** из Nextcloud применяются автоматически
- ❌ Требует `user_oidc` ≥ 1.3 с Bearer authentication (проверено в разделе «Предварительные условия»)

**Функционал:**

- [ ] **Файловый браузер** — WebDAV PROPFIND с `Authorization: Bearer {user_token}`; результат ограничен ACL пользователя
- [ ] **Метаданные файлов**: имя, размер, дата изменения, MIME-тип, иконка по типу
- [ ] **Открытие / редактирование файла** — ссылка на файл в Nextcloud в новой вкладке; пользователь авторизован через Keycloak SSO (cookie-based), Collabora получает те же права
- [ ] **Скачивание файла** — бэкенд стримит файл через WebDAV с Bearer user token → `StreamingResponse`; Nextcloud проверяет ACL, возвращает 403/404 если нет доступа
- [ ] **Создание шаринг-ссылки** — через OCS Sharing API с Bearer user token; шара создаётся от имени самого пользователя (он же видит её потом в Nextcloud UI)
- [ ] **Загрузка файлов** — фронтенд → бэкенд → WebDAV PUT с Bearer user token (на путь `/files/{user_sub}/{target}`); ACL проверяется Nextcloud
- [ ] **Удаление файлов** — WebDAV DELETE с Bearer user token; запрещено для шаблонов (их нельзя удалять пользователю)
- [ ] **Права доступа** — полностью делегированы Nextcloud; портал не проверяет ACL сам, а обрабатывает 403/404 от NC
- [ ] **Поиск по файлам** — через Nextcloud OCS Search API с Bearer user token; результаты ограничены ACL
- [ ] **Встроенный просмотр PDF** — если MIME-тип `application/pdf`, файл открывается в браузере без скачивания:
  - Бэкенд стримит содержимое (Bearer user token к Nextcloud) с заголовком `Content-Disposition: inline`
  - Фронтенд открывает PDF в модальном окне через `<iframe src="/api/v1/files/view?path=...">` или нативный `<object>` браузера
  - Fallback: если браузер не поддерживает inline PDF → кнопка «Скачать»
  - Другие MIME-типы (docx, xlsx и т.д.) → стандартное скачивание или открытие в Nextcloud/Collabora
- [ ] **Работа с шаблонами** (`/Templates/`) — чтение через service account (публичная библиотека); копирование в user-space — через Bearer user token (пишем в папку пользователя)

**Как работает: ключевые сценарии (с impersonation)**
```
[Листинг файлов]
Браузер → GET /api/v1/files?path=/shared/docs
         Cookie: session_id=<uuid>
Backend → Redis: получить user_session → nc_access_token
Backend → refresh token если expires < 60s
Backend → WebDAV PROPFIND /remote.php/dav/files/{user_sub}/shared/docs
          Authorization: Bearer {nc_access_token}
          Depth: 1
Nextcloud (user_oidc) → валидирует JWT → резолвит user → применяет ACL
          → 207 Multi-Status (user видит) или 403 (нет доступа)
Backend → парсит XML → JSON → фронтенд

[Скачивание файла]
Браузер → GET /api/v1/files/download?path=/shared/docs/report.pdf
Backend → WebDAV GET с Bearer user token → httpx.stream()
Nextcloud → проверяет ACL → если ok — отдаёт файл → если нет — 403
Backend → StreamingResponse → браузер
(Audit в Nextcloud: "user Иван скачал report.pdf" — корректно)

[Редактирование .docx]
Браузер → клик "Открыть в Nextcloud"
Портал → формирует URL: https://nextcloud.company.local/apps/files/?dir=/path&openfile=123
Браузер → открывает новую вкладку, Nextcloud видит Keycloak cookie → SSO → Collabora
(Collabora работает в контексте того же пользователя)

[Загрузка файла]
Браузер → POST /api/v1/files/upload { path: "/shared/docs/", file: multipart }
Backend → WebDAV PUT /remote.php/dav/files/{user_sub}/shared/docs/file.docx
          Authorization: Bearer {user_access_token}
Nextcloud → проверяет ACL на целевую папку → ok/403
Backend → логирует в audit_log { user_id, file_path, action: upload }

[Шаблон → документ]
Браузер → POST /api/v1/templates/{id}/instantiate { target_path: "/shared/myfolder/" }
Backend → WebDAV COPY /files/portal-svc/Templates/order.docx
          → /files/{user_sub}/shared/myfolder/order.docx
          Authorization: Bearer {user_access_token}  ← от имени пользователя
          Destination header: ...
(Service account владеет источником, пользователь — цель)
```

**Технические детали (impersonation клиент):**
```python
# backend/app/services/nextcloud.py
# Два режима работы:
# - USER context: все CRUD над файлами пользователя — Bearer {user_token}
# - SYSTEM context: только Templates + webhooks — service account (app password)

class NextcloudClient:
    # Разные таймауты для разных операций — единый global timeout (3 сек) убьёт large file transfers:
    TIMEOUT_DEFAULT  = httpx.Timeout(10.0)   # листинг, метаданные, OCS API
    TIMEOUT_DOWNLOAD = httpx.Timeout(None)    # стриминг файлов — без таймаута (зависит от размера файла)
    TIMEOUT_UPLOAD   = httpx.Timeout(600.0)  # upload до 600 сек (≈ 100 МБ при ~1 МБ/с)
    TIMEOUT_HEALTH   = httpx.Timeout(3.0)    # /ready healthcheck — быстрый ответ или fail

    def __init__(self, base_url: str, service_user: str, service_app_password: str):
        self.base_url = base_url
        # Service account — только для системных операций
        self._system_auth = (service_user, service_app_password)
        self._ocs_headers = {"OCS-APIRequest": "true", "Accept": "application/json"}

    # ===== USER CONTEXT (все CRUD пользовательских файлов) =====

    async def list_folder_as(self, user_token: str, user_sub: str, path: str) -> list[FileItem]:
        webdav_url = f"{self.base_url}/remote.php/dav/files/{user_sub}{path}"
        async with httpx.AsyncClient() as client:
            r = await client.request(
                "PROPFIND", webdav_url,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Depth": "1",
                },
            )
            if r.status_code == 403:
                raise PermissionDenied("Нет доступа к папке (ACL Nextcloud)")
            if r.status_code == 404:
                raise NotFound(f"Папка не найдена: {path}")
            r.raise_for_status()
            return parse_propfind_xml(r.text)

    async def stream_file_as(
        self, user_token: str, user_sub: str, path: str
    ) -> AsyncIterator[bytes]:
        """Скачивание от имени пользователя. ACL проверяется Nextcloud."""
        webdav_url = f"{self.base_url}/remote.php/dav/files/{user_sub}{path}"
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", webdav_url,
                headers={"Authorization": f"Bearer {user_token}"},
            ) as r:
                if r.status_code in (403, 404):
                    raise PermissionDenied(f"Нет доступа к файлу: HTTP {r.status_code}")
                r.raise_for_status()
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    yield chunk

    async def upload_file_as(
        self, user_token: str, user_sub: str, target_path: str,
        data: bytes, content_type: str,
    ) -> None:
        webdav_url = f"{self.base_url}/remote.php/dav/files/{user_sub}{target_path}"
        async with httpx.AsyncClient() as client:
            r = await client.put(
                webdav_url,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": content_type,
                },
                content=data,
            )
            if r.status_code == 403:
                raise PermissionDenied(f"Нет прав на запись в {target_path}")
            r.raise_for_status()

    async def create_share_as(
        self, user_token: str, path: str, share_type: int, permissions: int,
        expire_days: int | None = None,
    ) -> str:
        """Создание шары от имени пользователя. В Nextcloud owner = user."""
        url = f"{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
        data = {"path": path, "shareType": share_type, "permissions": permissions}
        if expire_days:
            data["expireDate"] = (date.today() + timedelta(days=expire_days)).isoformat()
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    **self._ocs_headers,
                },
                data=data,
            )
            r.raise_for_status()
            return r.json()["ocs"]["data"]["url"]

    # ===== SYSTEM CONTEXT (Templates + webhooks, без user) =====

    async def list_templates_system(self) -> list[FileItem]:
        """Публичная библиотека шаблонов — читается service account."""
        webdav_url = f"{self.base_url}/remote.php/dav/files/{self._system_auth[0]}/Templates/"
        async with httpx.AsyncClient() as client:
            r = await client.request(
                "PROPFIND", webdav_url,
                auth=self._system_auth,
                headers={"Depth": "1"},
            )
            r.raise_for_status()
            return parse_propfind_xml(r.text)

    async def copy_template_to_user(
        self, user_token: str, user_sub: str,
        template_name: str, target_path: str,
    ) -> None:
        """COPY шаблона → user-space. Source от service, dest — от user."""
        src_url = f"{self.base_url}/remote.php/dav/files/{self._system_auth[0]}/Templates/{template_name}"
        dst_url = f"{self.base_url}/remote.php/dav/files/{user_sub}{target_path}"
        async with httpx.AsyncClient() as client:
            # Копируем от имени пользователя — destination проверяется на его ACL
            r = await client.request(
                "COPY", src_url,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Destination": dst_url,
                    "Overwrite": "F",
                },
            )
            r.raise_for_status()

# FastAPI dependency: кладёт user_token из session в запрос
async def get_user_nc_context(
    user: User = Depends(get_current_user),
    redis=Depends(get_redis),
) -> UserNcContext:
    session = await redis.hgetall(f"session:{user.session_id}")
    nc_token = session.get("nc_access_token")
    expires_at = int(session.get("expires_at", 0))
    # refresh за 60 сек до истечения
    if expires_at - time.time() < 60:
        nc_token = await refresh_nc_token(user.session_id, session["refresh_token"])
    return UserNcContext(user=user, nc_token=nc_token, user_sub=user.keycloak_id)

# Использование в endpoint:
@router.get("/files")
async def list_files(
    path: str,
    ctx: UserNcContext = Depends(get_user_nc_context),
):
    try:
        return await nextcloud.list_folder_as(ctx.nc_token, ctx.user_sub, path)
    except PermissionDenied:
        raise HTTPException(status_code=403, detail="Нет доступа к папке")
```

**Fallback: если `user_oidc` не поддерживает Bearer**

Если версия < 1.3 и апгрейд невозможен, применяется временное решение:

1. **Pre-check прав** через OCS с user-сессией (cookie): портал перед операцией делает `GET /ocs/v2.php/apps/files_sharing/api/v1/shares?path=...` с HTTP-клиентом, которому переданы cookie пользователя (если домены совпадают) или проверяет через Nextcloud API поиск. При успехе — делает операцию через service account
2. **Проблемы подхода**: TOCTOU race, удвоение запросов к NC, audit в Nextcloud по-прежнему на service account
3. **Рассматривается как stopgap** — параллельно инициируется апгрейд `user_oidc`

Решение по fallback принимается **после smoke-теста Bearer в разделе «Предварительные условия»**.

---

### 3.7. Умный поиск

- [ ] **Единый поиск** — статьи KB, новости, файлы Nextcloud, ярлыки, пользователи
- [ ] **Автодополнение (typeahead)** — debounce 300мс, поиск по заголовкам через `pg_trgm`
- [ ] **Нечёткий поиск** — `pg_trgm` similarity ≥ 0.3, поддержка опечаток
- [ ] **Фильтры**: тип контента, дата создания, автор, отдел
- [ ] **Выделение совпадений** — `ts_headline()` в PostgreSQL
- [ ] **История поиска** — последние 10 запросов пользователя (localStorage; в БД не хранится — нет privacy-вопросов, нет лишних записей)
- [ ] **«Ничего не найдено»** — предлагать похожие запросы

**Разделение ответственности между FTS и pg_trgm:**

| | FTS (`tsvector`) | pg_trgm |
|--|--|--|
| Назначение | Поиск по телу статьи/новости | Typeahead по заголовкам, нечёткое совпадение |
| Когда используется | Основной поиск (Enter) | Автодополнение (debounce 300мс) |
| Что ищет | Полный текст с лемматизацией | Только заголовок, допускает опечатки |

```sql
-- Индексы
CREATE INDEX idx_kb_fts  ON kb_articles USING GIN(body_tsvector);          -- основной поиск
CREATE INDEX idx_kb_trgm ON kb_articles USING GIN(title gin_trgm_ops);     -- typeahead
CREATE INDEX idx_news_fts  ON news USING GIN(body_tsvector);
CREATE INDEX idx_news_trgm ON news USING GIN(title gin_trgm_ops);

-- Typeahead (автодополнение по заголовку, только pg_trgm):
SELECT id, title, 'article' AS type
FROM kb_articles
WHERE similarity(title, :raw_q) > 0.3 AND deleted_at IS NULL
ORDER BY similarity(title, :raw_q) DESC
LIMIT 10;

-- Основной поиск (FTS по телу + pg_trgm по заголовку, объединение):
SELECT id, title, 'article' AS type,
       ts_rank(body_tsvector, query) AS rank,
       ts_headline('russian', body, query, 'MaxWords=20') AS snippet
FROM kb_articles, to_tsquery('russian', :q) query
WHERE (body_tsvector @@ query OR similarity(title, :raw_q) > 0.3)
  AND deleted_at IS NULL
ORDER BY rank DESC
LIMIT 20;
```

---

### 3.8. Аналитика

- [ ] **Счётчики просмотров** статей и новостей (защита от накрутки через Redis: 1/час/пользователь)
- [ ] **Топ-10 популярных статей** за неделю/месяц
- [ ] **Топ скачиваемых файлов** — из таблицы `audit_log`
- [ ] **Активность по отделам** — агрегированная (без персональной слежки)
- [ ] **Дашборд администратора**: MAU, DAU, популярные разделы, активность по времени суток
- [ ] **Экспорт отчётов** в CSV

---

### 3.9. Избранное / Закладки

- [ ] **Добавление в избранное**: статья, новость, файл (ссылка Nextcloud), ярлык
- [ ] **Персональная панель быстрого доступа** на главной странице
- [ ] **Drag-and-drop сортировка** закладок
- [ ] **Группы закладок** — пользователь создаёт именованные коллекции

> Полная схема таблицы (`bookmarks`): [`docs/db-schema.md`](docs/db-schema.md)

---

### 3.10. Шаблоны документов (v2 — отложено)

> ⚠️ **Не входит в v1.** Реализуется в следующей версии после запуска портала.

- Библиотека шаблонов (приказ, служебная записка, отчёт, справка, заявление)
- Автоподстановка ФИО / Должности / Отдела / Даты из профиля пользователя
- Хранение в Nextcloud (`/Templates/`), копирование в user-space через WebDAV
- Управление шаблонами — `editor` и `admin`

---

### 3.11. Аудит действий

- [ ] **Полный лог событий** в партиционированной таблице `audit_log` (по месяцам)
- [ ] **Запись — асинхронная** через ARQ (fire-and-forget из request handler, batch insert в worker)
- [ ] **Отслеживаемые события**:
  - `login` / `logout`
  - `view_article` / `view_news`
  - `create_article` / `update_article` / `delete_article`
  - `open_file` / `download_file` / `edit_file`
  - `request_upload_url` / `create_share_link`
  - `search` (запрос + результаты count)
  - `admin_action` (изменение ролей, управление ярлыками)
- [ ] **Интерфейс просмотра** — только `admin`, с фильтрами по пользователю/событию/дате
- [ ] **Экспорт** в CSV
- [ ] **Retention**: 12 месяцев онлайн; старые партиции удаляются ARQ-задачей (раз в месяц `DROP TABLE audit_log_YYYY_MM`)

> Полная схема таблицы `audit_log` (партиционирование, индексы, init.sql): [`docs/db-schema.md`](docs/db-schema.md)

**Async запись через ARQ (не блокирует request):**
```python
# В API endpoint — мгновенно, не ждём записи в БД
async def view_article(article_id: str, request: Request,
                       current_user: User = Depends(get_current_user),
                       background_tasks: BackgroundTasks = BackgroundTasks()):
    article = await kb_service.get_article(article_id)
    background_tasks.add_task(        # fire-and-forget
        audit_service.enqueue,        # кладёт в Redis список
        event_type="view_article",
        user_id=current_user.id,
        resource_id=article_id,
        resource_title=article.title,
        ip=request.client.host,
    )
    return article

# ARQ worker — batch INSERT раз в 1-2 секунды
async def flush_audit_batch(ctx):
    events = await redis.lrange("audit_queue", 0, 999)
    if events:
        await redis.ltrim("audit_queue", len(events), -1)
        await db.execute_many(INSERT_AUDIT_SQL, [json.loads(e) for e in events])
```

---

### 3.12. Уведомления

- [ ] **In-app уведомления** — bell icon в шапке, счётчик непрочитанных
  - Новая новость, таргетированная на отдел пользователя
  - Обновление статьи, добавленной в закладки
  - Файл расшарен с пользователем (через webhook Nextcloud)
- [ ] **Email-уведомления** — опциональные (настройки в профиле), через Postfix/aiosmtplib
- [ ] **SSE (Server-Sent Events)** — realtime через **Redis Streams** (`XADD`/`XREAD`), не pub/sub
  - Поддержка `Last-Event-ID` — при реконнекте клиент получает пропущенные события
  - TTL на записи в Stream: 24 часа (Redis `XADD MAXLEN`)
- [ ] **Очередь email** — ARQ tasks с retry-логикой и exponential backoff

**Технические детали SSE + Redis Streams:**
```python
# Запись события (из ARQ worker или API handler)
await redis.xadd(
    f"notifications:{user_id}",
    {"type": "new_news", "title": "...", "link": "/news/123"},
    maxlen=100,  # хранить не более 100 последних событий на пользователя
)

# SSE endpoint — читает с last_id для event replay
@router.get("/notifications/stream")
async def notification_stream(request: Request, current_user: User = Depends(get_current_user)):
    last_id = request.headers.get("Last-Event-ID", "$")

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            events = await redis.xread(
                {f"notifications:{current_user.id}": last_id},
                block=30000, count=10
            )
            for stream, messages in (events or []):
                for msg_id, data in messages:
                    last_id = msg_id
                    yield f"id: {msg_id}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

> Полная схема таблицы (`notifications`): [`docs/db-schema.md`](docs/db-schema.md)

---

### 3.13. Главная страница (Dashboard)

- [ ] Приветствие с именем пользователя и текущей датой
- [ ] Последние новости (3-5 штук, с таргетингом по отделу)
- [ ] Закреплённые новости
- [ ] Блок «Избранное» (быстрый доступ)
- [ ] Панель ярлыков на корпоративные сервисы
- [ ] Блок «Недавно просмотренные статьи»
- [ ] Счётчик непрочитанных уведомлений

---

## 4. Исключённый функционал

- ❌ BPM-движки, бизнес-процессы
- ❌ Чаты, мессенджеры, видеозвонки
- ❌ Лайки, рейтинги публичные, геймификация
- ❌ Личные блоги пользователей
- ❌ Кастомные конструкторы форм и атрибутных схем
- ❌ Органиграмма (дерево отделов)
- ❌ Страница «О компании»
- ❌ «Кто сегодня в офисе» (агрегированный виджет)
- ❌ Персонализация виджетов главной страницы
- ❌ Корпоративный календарь (отложено)
- ❌ PWA (отложено)

---

## 5. Архитектура безопасности

### 5.1. Сетевой уровень
- Nginx: только HTTPS (TLS 1.2+), HTTP → 301 redirect
- IP-whitelist: разрешены только диапазоны внутренней сети + VPN (`allow 10.0.0.0/8; deny all;`)
- Rate limiting на Nginx: `limit_req_zone` — 100 req/min для API

### 5.2. HTTP Security Headers
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header Content-Security-Policy
  "default-src 'self'; frame-src 'self' https://collabora.company.local;
   img-src 'self' data: blob:; script-src 'self'; style-src 'self' 'unsafe-inline'" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
```

### 5.3. Приложение
- **CSRF**: `SameSite=Strict` на всех cookies + проверка `Origin`/`Referer` заголовка на бэкенде — закрывает 99% CSRF-атак без усложнения кода. Double Submit Cookie не используется (требует non-HttpOnly CSRF-cookie, усложняет SPA)
- **XSS**: контент хранится в Markdown; при рендеринге TipTap парсит MD → DOM безопасно; для HTML-фрагментов (вставка из буфера) — DOMPurify перед сохранением на бэкенде
- **SQL Injection**: только SQLAlchemy ORM, параметризованные запросы
- **Токены**: хранятся в HTTPOnly + Secure cookies (не localStorage)
- **File upload**: валидация MIME-type через python-magic; максимальный размер файла задаётся через `.env` переменную `MAX_UPLOAD_SIZE_MB` (по умолчанию `100`); применяется в Nginx (`client_max_body_size`) и в FastAPI middleware одновременно
- **Pydantic v2**: строгая валидация всех входящих данных на бэкенде

### 5.4. Rate Limiting (backend, per-user, Redis)

Nginx-лимит (100 req/min) — грубая защита по IP. На уровне бэкенда нужен **per-user** лимит через Redis. Библиотека: **`fastapi-limiter`** (async-native, не `slowapi` — у slowapi синхронный Redis client в некоторых версиях, что блокирует event loop).

| Endpoint / действие | Лимит |
|---------------------|-------|
| `POST /auth/login` (brute force) | 5 попыток / 1 мин / IP |
| `GET /search` (search abuse) | 30 req / мин / user |
| `POST /files/upload` | 10 req / мин / user |
| `POST /kb/articles/{id}/export/pdf` | 5 req / мин / user |
| Остальные API endpoints | 300 req / мин / user |

```python
# backend/app/core/rate_limit.py
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as aioredis

# Инициализация при старте приложения:
async def startup():
    redis = await aioredis.from_url(settings.REDIS_URL)
    await FastAPILimiter.init(redis)

# Применяется как Depends:
@router.get("/search")
async def search(
    q: str,
    _: None = Depends(RateLimiter(times=30, seconds=60)),
    current_user: User = Depends(get_current_user),
):
    ...

# Login — по IP (user ещё не авторизован):
@router.post("/auth/login")
async def login(
    _: None = Depends(RateLimiter(times=5, seconds=60)),
):
    ...
```

### 5.5. Сессии
- Access token lifetime: **15 минут**
- Refresh token lifetime: **8 часов** (рабочий день)
- Refresh token rotation: каждый refresh инвалидирует предыдущий

---

## 6. API Design (OpenAPI 3.0)

Базовый URL: `/api/v1/`

```
# Аутентификация
GET  /api/v1/auth/login           → redirect to Keycloak
GET  /api/v1/auth/callback        → OIDC callback, установка HTTPOnly cookies
POST /api/v1/auth/logout          → revoke tokens, clear cookies, SLO
GET  /api/v1/auth/me              → текущий пользователь

# Пользователи
GET  /api/v1/users                → список сотрудников (поиск, фильтр)
GET  /api/v1/users/{id}           → профиль пользователя
PATCH /api/v1/users/me/profile    → обновление статуса/аватара
PATCH /api/v1/users/me/preferences → настройки уведомлений

# База знаний
GET  /api/v1/kb/sections          → дерево разделов
POST /api/v1/kb/sections          → создать раздел [editor+]
GET  /api/v1/kb/articles          → список статей (фильтры: section, tag, status)
POST /api/v1/kb/articles          → создать статью [editor+]
GET  /api/v1/kb/articles/{id}     → статья + инкремент просмотра
PUT  /api/v1/kb/articles/{id}     → обновить [editor+]
DELETE /api/v1/kb/articles/{id}   → удалить [admin]
GET  /api/v1/kb/articles/{id}/versions          → история версий
POST /api/v1/kb/articles/{id}/versions/{n}/restore → откат [editor+]
POST /api/v1/kb/articles/{id}/export/pdf        → экспорт PDF
GET  /api/v1/kb/articles/{id}/comments         → комментарии
POST /api/v1/kb/articles/{id}/comments         → добавить комментарий

# Новости
GET  /api/v1/news                 → список (с таргетингом по профилю)
POST /api/v1/news                 → создать [editor+]
GET  /api/v1/news/{id}            → новость
PUT  /api/v1/news/{id}            → обновить [editor+]
DELETE /api/v1/news/{id}          → удалить [admin]

# Файлы (проксирование Nextcloud)
GET  /api/v1/files                → список файлов (WebDAV PROPFIND)
GET  /api/v1/files/{path:path}    → метаданные
GET  /api/v1/files/{path:path}/open → URL для открытия файла в Nextcloud (новая вкладка)
POST /api/v1/files/{path:path}/share → создать шаринг-ссылку (OCS API)
POST /api/v1/files/{path:path}    → загрузить файл в Nextcloud (WebDAV PUT)

# Поиск
GET  /api/v1/search?q=...&type=...&from=...&to=...&author=...

# Ярлыки
GET  /api/v1/links                → все активные ярлыки
POST /api/v1/links                → создать [admin]
PUT  /api/v1/links/{id}           → обновить [admin]
DELETE /api/v1/links/{id}         → удалить [admin]

# Закладки
GET  /api/v1/bookmarks            → закладки пользователя
POST /api/v1/bookmarks            → добавить
DELETE /api/v1/bookmarks/{id}     → удалить
PATCH /api/v1/bookmarks/reorder   → drag-and-drop порядок

# Уведомления
GET  /api/v1/notifications        → список непрочитанных
POST /api/v1/notifications/{id}/read → отметить прочитанным
GET  /api/v1/notifications/stream → SSE stream

# Аналитика [admin]
GET  /api/v1/analytics/dashboard  → сводная статистика
GET  /api/v1/analytics/top-articles
GET  /api/v1/analytics/top-files
GET  /api/v1/analytics/departments

# Аудит [admin]
GET  /api/v1/audit                → лог событий (фильтры: user, event, from, to)
GET  /api/v1/audit/export.csv
```

### 6.2. Пагинация (обязательно везде)

Все list-эндпоинты обязаны поддерживать пагинацию. Без исключений — сейчас 300 пользователей, потом больше.

**Формат запроса:**
```
GET /api/v1/users?limit=20&offset=40
GET /api/v1/kb/articles?limit=20&offset=0
GET /api/v1/audit?limit=50&offset=0&from=2025-01-01
```

**Формат ответа:**
```json
{
  "items": [...],
  "total": 300,
  "limit": 20,
  "offset": 40
}
```

**Параметры по умолчанию:**
| Параметр | Значение |
|----------|---------|
| `limit` default | 20 |
| `limit` max | 100 (жёсткий cap на бэкенде) |
| `offset` default | 0 |

**Эндпоинты, где пагинация обязательна:**

| Endpoint | Почему критично |
|----------|----------------|
| `GET /users` | 300+ записей |
| `GET /news` | растёт со временем |
| `GET /kb/articles` | растёт со временем |
| `GET /audit` | **потенциально миллионы строк** |
| `GET /search` | может вернуть сотни совпадений |
| `GET /notifications` | накапливается |
| `GET /kb/articles/{id}/versions` | у популярных статей десятки версий |

```python
# backend/app/schemas/pagination.py
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, List

T = TypeVar("T")

class PaginationParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class PageResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int
```

---

### 6.3. Idempotency (защита от дублей)

**Проблема:** пользователь нажал кнопку дважды или сеть дала таймаут и клиент повторил запрос — получаем дублирующиеся новости, статьи, email-отправки.

**Решение:** заголовок `Idempotency-Key` для **критичных** POST-запросов (белый список путей, не все POST).

```
POST /api/v1/news
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

**Схема БД:**
```sql
CREATE TABLE idempotency_keys (
    key         VARCHAR(255) PRIMARY KEY,
    response    JSONB        NOT NULL,
    status_code INTEGER      NOT NULL,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);
-- TTL: автоудаление через pg cron или ARQ task (старше 24 часов)
CREATE INDEX idx_idempotency_created ON idempotency_keys(created_at);
```

**Логика middleware:**
```python
# backend/app/core/idempotency.py
IDEMPOTENCY_PATHS = {
    "/api/v1/news",
    "/api/v1/kb/articles",
    "/api/v1/files/upload",
    "/api/v1/notifications/send",
}

async def idempotency_middleware(request: Request, call_next):
    key = request.headers.get("Idempotency-Key")
    if key and request.method == "POST" and request.url.path in IDEMPOTENCY_PATHS:
        cached = await db.fetchrow(
            "SELECT response, status_code FROM idempotency_keys WHERE key = $1", key
        )
        if cached:
            return JSONResponse(cached["response"], status_code=cached["status_code"])
        response = await call_next(request)
        if 200 <= response.status_code < 300:
            # ⚠️ НЕ сохраняем полный response.json() — это memory leak при больших ответах.
            # Храним только минимальный payload: id созданного ресурса + status_code.
            # Клиент при повторном запросе получит тот же id и не создаст дубль.
            resource_id = response.headers.get("X-Resource-Id")  # endpoint обязан выставить этот заголовок
            minimal_response = {"id": resource_id} if resource_id else {}
            await db.execute(
                "INSERT INTO idempotency_keys(key, response, status_code) VALUES($1, $2, $3)"
                " ON CONFLICT (key) DO NOTHING",
                key, json.dumps(minimal_response), response.status_code
            )
        return response
    return await call_next(request)
```

> **Правило:** каждый POST-endpoint в `IDEMPOTENCY_PATHS` обязан выставлять заголовок `X-Resource-Id: {uuid}` в ответе. Полный body в `idempotency_keys` не хранится.

**Где обязателен `Idempotency-Key`:**
- `POST /news` — создание новости
- `POST /kb/articles` — создание статьи
- `POST /files/upload` — загрузка файла
- `POST /notifications/send` — отправка email

**Где не нужен:**
- GET, DELETE (идемпотентны по природе)
- PATCH/PUT (повтор не создаёт дубль)

**TTL:** ключи хранятся **24 часа**, затем удаляются ARQ-задачей.

---

### 6.4. Политика версионирования API

Текущая версия: `/api/v1/`. Необходима явная политика.

**Правила:**

| Действие | Breaking change? | Требует v2? |
|----------|-----------------|-------------|
| Добавить новое поле в ответ | Нет | Нет |
| Добавить новый endpoint | Нет | Нет |
| Удалить поле из ответа | **Да** | **Да** |
| Изменить тип поля | **Да** | **Да** |
| Изменить бизнес-логику endpoint | **Да** | **Да** |
| Переименовать поле | **Да** | **Да** |

**Deprecation policy:**
- v1 поддерживается **минимум 6 месяцев** после выхода v2
- Устаревшие endpoints возвращают заголовок `Deprecation: date="2026-12-01"`
- За 1 месяц до отключения — уведомления администраторам

**Принцип:** для портала с одной командой-потребителем (фронтенд) v2 маловероятен, но политика фиксируется на случай открытия API для интеграций.

---

### 6.5. Стратегия миграций БД (zero-downtime)

Инструмент: **Alembic**. Все миграции обязаны быть **backward compatible** — деплой возможен без остановки сервиса.

**Правило деплоя:** `migration → code deploy` (сначала миграция, потом код).

**Запрещённые операции (могут залочить таблицу):**
- `ALTER TABLE ... ADD COLUMN ... NOT NULL` без DEFAULT
- `ALTER TABLE ... ALTER COLUMN TYPE` на больших таблицах
- `DROP COLUMN` без предварительного deprecation-периода

**Правильный порядок для частых сценариев:**

*Добавление обязательного поля:*
```sql
-- Шаг 1 (миграция): добавить nullable
ALTER TABLE users ADD COLUMN phone TEXT NULL;

-- Шаг 2: деплой кода, который пишет в поле

-- Шаг 3: бэкфилл существующих строк
UPDATE users SET phone = '' WHERE phone IS NULL;

-- Шаг 4 (следующая миграция): сделать NOT NULL
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;
```

*Переименование поля:*
```sql
-- Шаг 1: добавить новое поле, писать в оба
-- Шаг 2: читать из нового поля
-- Шаг 3: убедиться, что старое не используется
-- Шаг 4: DROP COLUMN старое поле
```

*Создание индекса без блокировки:*
```sql
-- Обычный CREATE INDEX блокирует таблицу!
CREATE INDEX CONCURRENTLY idx_news_published ON news(published_at)
WHERE published_at IS NOT NULL AND deleted_at IS NULL;
```

**Шаблон Alembic-миграции:**
```python
# alembic/versions/xxxx_add_phone_to_users.py
def upgrade():
    # БЕЗОПАСНО: nullable column
    op.add_column('users', sa.Column('phone', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('users', 'phone')
```

---

## 7. Observability

> Prometheus и Grafana устанавливаются отдельно в инфраструктуре. Задача портала — правильно **экспортировать** данные.
> **Log aggregation (Loki/ELK) — отложено.** Логи из stdout Docker-контейнеров собираются `json-file` logging driver с ротацией (`max-size: 50m, max-file: 5`). Loki будет добавлен позже как отдельная инфра, не в compose портала.

### 7.1. Структурированное логирование

Все логи — в формате **JSON** (structlog), вывод в stdout → сбор через Docker logging driver.

```python
# backend/app/core/logging.py
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,      # request_id, user_id из контекста
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

# Каждый лог содержит:
# { "timestamp": "...", "level": "info", "event": "article_viewed",
#   "request_id": "abc-123", "user_id": "uuid", "article_id": "uuid",
#   "duration_ms": 42 }
```

**Middleware добавляет в каждый request:**
- `request_id` (UUID, генерируется или берётся из заголовка `X-Request-ID`)
- `user_id` (из JWT после аутентификации)
- `duration_ms` (время обработки запроса)

### 7.2. Метрики (Prometheus)

Библиотека: `prometheus-fastapi-instrumentator` — автоматически экспортирует HTTP-метрики.

```python
# backend/app/main.py
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

**Стандартные метрики (из instrumentator):**
- `http_requests_total{method, endpoint, status}` — счётчик запросов
- `http_request_duration_seconds{method, endpoint}` — latency histogram

**Кастомные метрики портала:**
```python
from prometheus_client import Counter, Histogram, Gauge

articles_viewed = Counter("portal_articles_viewed_total", "KB article views", ["section"])
search_queries = Counter("portal_search_queries_total", "Search queries", ["has_results"])
active_sse_connections = Gauge("portal_sse_connections_active", "Active SSE connections")
audit_queue_depth = Gauge("portal_audit_queue_depth", "Unprocessed audit events in Redis")
```

**Endpoint:** `GET /metrics` — доступен только из внутренней сети (Nginx location block с IP-restrict).

### 7.3. Error Tracking (Sentry)

Must-have для production. Sentry перехватывает необработанные исключения и отправляет их с контекстом (stack trace, user, request).

```python
# backend/app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,          # из env, self-hosted Sentry или sentry.io
    integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    traces_sample_rate=0.1,            # 10% транзакций для performance monitoring
    environment=settings.ENVIRONMENT,  # "production" / "staging"
    send_default_pii=False,            # не отправлять PII (email, IP пользователей)
)
```

```typescript
// frontend/src/main.ts
import * as Sentry from "@sentry/vue"

Sentry.init({
  app,
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE,
  tracesSampleRate: 0.1,
})
```

> Sentry может быть self-hosted (бесплатно) или cloud. DSN передаётся через переменные окружения — в код не попадает.

### 7.4. Health Checks

Критично для эксплуатации. Позволяет нагрузочному балансировщику, Docker healthcheck и мониторингу понять, жив ли сервис и готов ли принимать трафик.

| Endpoint | Назначение | Когда возвращает не OK |
|----------|-----------|----------------------|
| `GET /health` | Жив ли процесс | Никогда (или при OOM) |
| `GET /ready` | Готов ли принимать трафик | БД недоступна, Redis недоступен, Nextcloud недоступен |

```python
# backend/app/api/health.py
from fastapi import APIRouter
from app.db.session import async_engine
from app.core.redis import redis_client
from app.services.nextcloud import nextcloud_client
import httpx

router = APIRouter(tags=["health"])

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/ready")
async def ready():
    checks = {}
    overall = "ok"

    # PostgreSQL
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {e}"
        overall = "fail"

    # Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"fail: {e}"
        overall = "fail"

    # Nextcloud (HEAD-запрос к /status.php)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.head(f"{settings.NEXTCLOUD_URL}/status.php")
            checks["nextcloud"] = "ok" if r.status_code < 500 else f"fail: HTTP {r.status_code}"
    except Exception as e:
        checks["nextcloud"] = f"fail: {e}"
        # Nextcloud — деградация, не критичный отказ
        if overall == "ok":
            overall = "degraded"

    status_code = 200 if overall == "ok" else (503 if overall == "fail" else 200)
    return JSONResponse({"status": overall, "checks": checks}, status_code=status_code)
```

**Docker Compose healthcheck:**
```yaml
healthcheck:
  # Используем /ready (не /health): проверяет DB + Redis + Nextcloud.
  # /health всегда 200 → контейнер не перезапустится при падении зависимостей.
  test: ["CMD", "curl", "-f", "http://localhost:8000/ready"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 15s
```

**API endpoints добавляются в раздел 6:**
```
GET /health   → жив ли процесс (всегда 200)
GET /ready    → готов ли к трафику (200/503, проверяет DB + Redis + Nextcloud)
```

### 7.5. ARQ Task Monitoring

ARQ не имеет встроенного UI для задач — мониторинг строится на двух уровнях:

**Sentry:** в ARQ worker оборачиваем каждую задачу в try/except — необработанные исключения уходят в Sentry автоматически через `FastApiIntegration`. Дополнительно явная обёртка для критичных задач:

```python
# backend/app/worker.py
async def publish_scheduled_news(ctx, news_id: str):
    try:
        await _publish_scheduled_news(ctx, news_id)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)          # явно, с контекстом задачи
        raise                                        # re-raise для ARQ retry

async def on_job_start(ctx):
    ctx["job_start"] = time.time()

async def on_job_end(ctx):
    duration = time.time() - ctx.get("job_start", time.time())
    arq_jobs_duration.observe(duration, {"job": ctx["job_name"]})

async def on_job_error(ctx, job, error):
    arq_failed_jobs.inc({"job": ctx["job_name"]})
    sentry_sdk.capture_exception(error)
```

**Prometheus метрики ARQ:**
```python
from prometheus_client import Counter, Histogram

arq_failed_jobs = Counter(
    "portal_arq_failed_jobs_total",
    "Failed ARQ jobs",
    ["job"],
)
arq_jobs_duration = Histogram(
    "portal_arq_job_duration_seconds",
    "ARQ job execution time",
    ["job"],
)
```

**Grafana алерт (добавить к существующим в 7.6):**
| Алерт | Условие |
|-------|---------|
| ARQ job failures | `portal_arq_failed_jobs_total` rate > 0 за 10 мин |

**Cron-задачи ARQ** (задачи с расписанием — не разовые):

| Задача | Расписание | При ошибке |
|--------|-----------|-----------|
| `publish_scheduled_news` | каждую минуту | Sentry alert |
| `archive_expired_news` | каждый час | Sentry alert |
| `create_next_audit_partition` | 1-е число месяца | Sentry alert + email admin |
| `drop_old_audit_partition` | 1-е число месяца | Sentry alert + email admin |
| `cleanup_idempotency_keys` | ежедневно | Sentry warning |
| `sync_users_from_keycloak` | вручную (admin API) | HTTP 500 + Sentry |

### 7.6. Tracing (опционально, v2)

OpenTelemetry (OTLP) — в первой версии не реализуется, но код пишется с учётом будущего добавления (`opentelemetry-sdk` подключается без изменения бизнес-логики).

### 7.7. Алерты (настраиваются в Grafana, не в коде портала)

| Алерт | Условие |
|-------|---------|
| Высокий error rate | `http_requests_total{status=~"5.."}` > 1% за 5 мин |
| Медленные запросы | p95 latency > 2 сек за 5 мин |
| Глубокая очередь аудита | `portal_audit_queue_depth` > 1000 |
| Много активных SSE | `portal_sse_connections_active` > 400 (больше пользователей) |

---

## 8. Стратегия тестирования

**Принцип: тесты пишутся вместе с каждым модулем, не в конце.**
Модуль не считается завершённым, пока не написаны unit, integration и E2E тесты для него.

### 8.1. Инструменты

| Тип | Инструмент | Когда пишется |
|-----|-----------|--------------|
| Unit (backend) | Pytest + pytest-asyncio | Вместе с каждым модулем |
| Integration (backend) | Pytest + Testcontainers (PostgreSQL, Redis) + httpx mock | Вместе с каждым модулем |
| Unit/Component (frontend) | Vitest + Vue Test Utils | Вместе с каждым компонентом |
| E2E | Playwright | Вместе с каждым модулем (основной сценарий) |
| Security | OWASP ZAP + ручные проверки | **Финальный этап** |
| Performance | k6 | **Финальный этап** |

### 8.2. Что тестируется в каждом модуле

| Модуль | Unit | Integration | E2E |
|--------|------|-------------|-----|
| Аутентификация | JWT parsing, token refresh, роли | Keycloak OIDC flow (mock) | Логин → главная → выход + SLO |
| Профили / Команда | Маппинг claims → модель | DB upsert при логине | Просмотр профиля, поиск по команде |
| База знаний | Версионность, права доступа, PDF генерация | DB CRUD, FTS запросы | Создать → найти → экспорт PDF → откат версии |
| Новости | Таргетинг по отделу, расписание публикации | ARQ задачи, DB | Создать с таргетом → получить уведомление |
| Nextcloud-браузер | Парсинг WebDAV XML, формирование ссылок | httpx mock Nextcloud API | Открыть папку → скачать файл → создать шаринг |
| Поиск | FTS + pg_trgm ranking, merge результатов | DB запросы с реальным PG | Поиск с опечаткой → релевантные результаты < 1 сек |
| Аудит + аналитика | Запись событий, агрегация | DB партиции, экспорт CSV | Admin видит лог; экспорт содержит корректные данные |
| Ярлыки + закладки | Валидация URL, сортировка | DB CRUD | Добавить закладку → drag-and-drop → сохранилось |
| Уведомления | SSE payload, email рендеринг | Redis pub/sub, aiosmtplib mock | Новость → SSE уведомление появилось в bell icon |

### 8.3. Финальные тесты (после сборки всех модулей)

**Security (OWASP ZAP + ручные проверки):**
- Доступ без VPN полностью заблокирован
- SSO не обходится (прямой запрос к API без токена → 401)
- XSS через WYSIWYG не выполняется (DOMPurify)
- CSRF: SameSite=Strict + Origin/Referer-чек блокирует cross-origin запросы
- Права `reader` не дают доступ к `editor`/`admin` endpoints

**Performance (k6):**
- 300 одновременных сессий
- Время отклика API < 2 сек (p95)
- Стабильность Redis-кэша под нагрузкой
- Поиск: < 1 сек при 300 concurrent запросах

### 8.4. Ключевые E2E сценарии (критерий ≥90% ключевых путей)
1. Логин → просмотр главной → выход (SLO: Nextcloud-сессия тоже завершена)
2. Поиск статьи с опечаткой → открытие → добавление в закладки → экспорт PDF
3. Открытие .docx → переход в Nextcloud → редактирование в Collabora
4. Создание новости с таргетом по отделу → отложенная публикация → SSE уведомление
5. Попытка доступа без авторизации → redirect на Keycloak
6. `reader` пытается создать статью → 403
7. Создание документа из шаблона → автоподстановка ФИО/отдела → открытие в Nextcloud
8. Admin смотрит audit log → фильтрует по пользователю → экспортирует CSV
9. **ACL Nextcloud соблюдается (impersonation)**: пользователь из отдела `Marketing` через файловый браузер портала пытается открыть `/Finance/salaries.xlsx` (нет доступа в Nextcloud) → портал возвращает 403, файл не виден в листинге; та же попытка для `reader` из отдела `Finance` → файл открывается и скачивается
10. **Audit trail синхронизирован**: пользователь Иван скачал файл через портал → в Nextcloud audit.log запись с именем `Ivan`, в портальном `audit_log` то же самое `user_id=Ivan` (не `portal-svc`)
11. **Refresh NC-токена**: после 20 минут неактивности пользователь открывает файловый браузер → портал автоматически рефрешит `nc_access_token` через Keycloak → листинг отдаётся без повторного логина

---

## 9. Docker Compose

```yaml
# docker-compose.yml
services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    # Статика собирается и отдаётся через nginx

  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql+asyncpg://portal:${DB_PASSWORD}@postgres:5432/portal
      - REDIS_URL=redis://redis:6379/0
      - KEYCLOAK_URL=${KEYCLOAK_URL}
      - NEXTCLOUD_URL=${NEXTCLOUD_URL}
    volumes:
      - avatars_data:/data/avatars
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    env_file: .env
    healthcheck:
      # ⚠️ /ready (не /health): проверяет DB + Redis + Nextcloud.
      # /health всегда 200 → контейнер не перезапустится при падении зависимостей.
      test: ["CMD", "curl", "-f", "http://localhost:8000/ready"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s

  worker:
    build: ./backend
    command: python -m arq app.worker.WorkerSettings
    depends_on: [redis, postgres]
    env_file: .env

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: portal
      POSTGRES_USER: portal
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/migrations/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U portal"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
      - frontend_dist:/usr/share/nginx/html:ro
    depends_on: [backend, frontend]

volumes:
  postgres_data:
  redis_data:
  frontend_dist:
  avatars_data:
```

---

## 10. Структура репозитория

```
portal/
├── .github/
│   └── workflows/
│       ├── ci.yml            # lint + test на каждый PR
│       └── build.yml         # сборка Docker образов на merge в main
├── docs/
│   ├── adr.md                # Architecture Decision Records (15 решений)
│   ├── db-schema.md          # финальная схема БД (все таблицы + индексы)
│   ├── api-contracts.md      # контракты API (request/response)
│   └── roles-matrix.md       # матрица прав: роль × ресурс × действие
├── frontend/
│   ├── src/
│   │   ├── components/       # переиспользуемые компоненты
│   │   ├── pages/            # страницы (роуты)
│   │   ├── stores/           # Pinia stores
│   │   ├── composables/      # Vue composables
│   │   ├── api/              # API клиент (ofetch + Vue Query)
│   │   ├── i18n/             # ru.json, en.json
│   │   └── types/            # TypeScript типы
│   ├── tests/
│   │   ├── unit/             # Vitest
│   │   └── e2e/              # Playwright
│   ├── vite.config.ts
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI роутеры
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── kb.py
│   │   │   ├── news.py
│   │   │   ├── files.py      # Nextcloud proxy (impersonation, Вариант B)
│   │   │   ├── search.py
│   │   │   ├── bookmarks.py
│   │   │   ├── links.py
│   │   │   ├── notifications.py
│   │   │   ├── analytics.py
│   │   │   ├── audit.py
│   │   │   └── health.py     # /health + /ready + /metrics
│   │   ├── core/
│   │   │   ├── config.py     # Pydantic Settings из env
│   │   │   ├── security.py   # JWT, CSRF utils
│   │   │   ├── rate_limit.py # fastapi-limiter
│   │   │   ├── idempotency.py # Idempotency-Key middleware
│   │   │   └── dependencies.py # FastAPI deps (get_current_user, require_role, etc.)
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Бизнес-логика
│   │   │   ├── keycloak.py   # OIDC flow, Admin API, token introspection
│   │   │   ├── nextcloud.py  # WebDAV + OCS API клиент (impersonation + service account)
│   │   │   ├── search.py     # FTS + pg_trgm unified search
│   │   │   ├── email.py      # aiosmtplib + Postfix
│   │   │   ├── export.py     # PDF (Playwright) + DOCX (python-docx)
│   │   │   └── notifications.py # SSE + Redis Streams
│   │   ├── worker.py         # ARQ cron + task definitions
│   │   └── main.py           # FastAPI app factory
│   ├── migrations/
│   │   ├── init.sql          # расширения + FTS + первые партиции audit_log
│   │   └── versions/         # Alembic migration files
│   ├── scripts/
│   │   └── create_audit_partitions.py
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── pyproject.toml        # зависимости + ruff + mypy конфиг
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf
│   └── certs/                # TLS сертификаты (gitignore)
├── docker-compose.yml
├── docker-compose.dev.yml    # локальная разработка (Keycloak dev + mock NC)
├── docker-compose.staging.yml
├── .env.example
├── .gitignore
├── AGENT.md                  # системный промт для AI-агента разработчика
└── requirements.md           # техническое требование и спецификация (этот файл)
```

---

## 11. Оценка трудоёмкости

| Модуль | Чел.-дни |
|--------|---------|
| **Prerequisite: миграция Nextcloud на Keycloak OIDC + audience mapper + smoke-тест Bearer** | **1.5** |
| Инфраструктура (Docker, Nginx, CI/CD, Alembic) | 4 |
| Аутентификация: Keycloak OIDC + SLO + Redis session + NC-token refresh | 6 |
| **Локальная аутентификация: bootstrap admin, email+bcrypt, смена/сброс пароля, /login UI** | **2** |
| Профили пользователей + справочник «Команда» | 3 |
| База знаний: CRUD + версионность + PDF + DOCX-экспорт + черновики | 11 |
| Новости + таргетинг + отложенная публикация + автосохранение черновиков | 7 |
| Уведомления: SSE + email (Postfix) | 4 |
| Интеграция Nextcloud: WebDAV + OCS (Вариант B, impersonation через Bearer JWT) | 6 |
| Умный поиск: FTS + pg_trgm + unified | 5 |
| Аудит + аналитика + дашборд | 4 |
| Ярлыки + закладки + шаблоны документов | 4 |
| Главная страница (Dashboard) | 3 |
| i18n (ru + en) | 2 |
| Unit + Integration тесты | 7 |
| E2E тесты (Playwright, включая ACL-сценарии) | 6 |
| Security audit + нагрузочные тесты | 3 |
| Документация (OpenAPI + гайды) | 3 |
| **ИТОГО** | **~81.5 чел.-дня** |

> Отказ от WOPI-сервера (Вариант B impersonation vs WOPI) сэкономил ~6 дней.
> Вариант B (impersonation) вместо Варианта A (service account) добавил ~3 дня на корректную работу с user-токенами и тесты ACL — это оправдано критичностью безопасности и audit trail.
> Keycloak и Nextcloud уже развёрнуты — это экономит ~5-7 дней на инфраструктуру.
