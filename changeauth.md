# План реализации: автоматический SSO + локальный вход для админов

## 1. Цели и не-цели

### Цели
- При открытии портала на доменном ПК пользователь попадает на главную **без единого клика** (прозрачный Kerberos через Keycloak).
- Не-доменный пользователь видит **форму Keycloak** (не страницу портала) — там вводит логин/пароль и попадает на главную.
- Локальный вход (для bootstrap-admin / DevOps) доступен только по прямой ссылке `/auth/local`, в публичном UI на него ссылок нет.
- Корректная обработка ошибок SSO без бесконечных редиректов.
- Сохранение `return_to` для глубоких ссылок (`/kb/articles/123` и т.п.).

### Не-цели
- Не убираем локальный вход из бэкенда — endpoint `/api/v1/auth/local/login` остаётся как был.
- Не меняем Keycloak realm / Kerberos настройку — она уже работает.
- Не реализуем `prompt=none` тихую проверку (отдельная история).
- Не настраиваем custom Keycloak login theme — отдельный тикет, выполняется позже.
- Не убиваем Keycloak SSO-сессию при logout портала (см. 3.8).

---

## 2. Итоговый flow (целевой)

| Условие | Поведение |
|---|---|
| Доменный ПК, гость без сессии открывает `/` | Авто-редирект `/api/v1/auth/login` → Kerberos → callback → главная |
| Не-доменный, гость без сессии открывает `/` | Авто-редирект `/api/v1/auth/login` → форма Keycloak → callback → главная |
| Сессия истекла внутри SPA (любой `api()` вернул 401) | `/api/v1/auth/login?redirect=<current_path>` |
| Закладка `/kb/articles/123` без сессии | Авто-редирект с `redirect=/kb/articles/123` → после SSO попадает на статью |
| Keycloak вернул `error=...` или callback упал | Страница `/auth/error?reason=...` без авто-редиректа, кнопки «Повторить» и (мелко) «Вход для администратора» |
| Локальный admin | Открывает `/auth/local` напрямую → форма локального логина → `/admin` (или `redirect`) |
| Уже залогиненный пользователь открыл `/auth/local` | Редирект на главную (`/`) |
| Старая закладка `/login` | 301 редирект на `/api/v1/auth/login` |
| Logout (Keycloak-сессия) | `/api/v1/auth/logout` → удаление портальной сессии в Redis → `/auth/error?reason=logged_out`. **Keycloak SSO-сессию НЕ трогаем** — следующий заход прозрачно перелогинит того же пользователя |
| Logout (локальная сессия) | `/api/v1/auth/logout` → `/auth/local?logged_out=1` |
| `LOCAL_AUTH_ENABLED=false` | `/auth/local` показывает alert «локальный вход выключен»; POST → 403 |
| `keycloak_enabled=false` | Авто-редирект гостя с `/` идёт на `/auth/local` (единственный доступный способ) |

---

## 3. Архитектурные решения

### 3.1. Loop-protection (best-practice подход)
Вдохновлено `keycloak-js` и Auth.js: **counter в `sessionStorage` с временным окном**.

Ключи:
- `sso_attempts` — массив timestamps последних попыток редиректа
- `sso_failed` — последняя причина ошибки (опционально, для UI)

Алгоритм перед каждым авто-редиректом на `/api/v1/auth/login`:
1. Прочитать `sso_attempts`, отфильтровать timestamps старше **30 секунд**.
2. Если осталось **≥ 2** попыток → НЕ редиректим, идём на `/auth/error?reason=loop_detected`.
3. Иначе добавить текущий timestamp, сохранить, выполнить `window.location.href = ...`.

Сброс:
- `loadUser()` при успехе очищает `sso_attempts` и `sso_failed`.
- Явный клик «Войти снова» на `/auth/error` очищает оба ключа.

Почему 2/30s, а не 1/10s: даёт пользователю один автоматический ретрай (например, transient network blip на Keycloak), но защищает от бесконечного loop. Окно 30s покрывает время full Kerberos-handshake + token exchange.

### 3.2. Маршрут `/auth/local`
Отдельный route, `meta: { public: true }` (доступен без сессии). Логика компонента:
- Если `auth.isAuthenticated === true` → `router.replace('/')`.
- Запросить `/auth/config`. Если `local_auth_enabled === false` → показать `n-alert` «Локальный вход выключен», скрыть форму.
- Если `?logged_out=1` → показать `n-alert` `success` «Вы вышли из системы».
- После успешного `localLogin` → `router.push(redirect || '/admin')`.

### 3.3. Страница `/auth/error`
Новый маршрут `/auth/error`, `meta: { public: true }`. Показывает причину (`reason` query param):
- `sso_failed`, `logged_out`, `loop_detected`, `keycloak_unavailable`

Кнопка «Войти снова» сбрасывает `sso_attempts` + `sso_failed` и делает `window.location.href = '/api/v1/auth/login?redirect=...'`. В футере мелкая ссылка `<a href="/auth/local">Вход для администратора</a>`.

При монтировании НЕ очищаем `sso_failed` (иначе тут же случится авто-редирект). Очистка только при явном клике «Войти снова».

### 3.4. Обновление `_handle401` в `api/index.ts`
Сейчас редиректит на `/login?redirect=...`. Меняем на `/api/v1/auth/login?redirect=...`. Whitelist путей (где не редиректим): `/auth/local`, `/auth/error`, `/p/`. Удаляем `/login` из whitelist.

### 3.5. Сохранение `return_to` через PKCE state
Бэкенд `auth.login` уже принимает `?redirect=...` и сохраняет его в Redis рядом с PKCE-стейтом. Изменений не требуется. Фронт обязан передавать `redirect=<current_path>` при каждом редиректе.

### 3.6. Бэкенд: страница ошибки вместо 401
Сейчас `auth.callback` при `error=...` или сбое токен-обмена бросает `HTTPException(401)` — белый экран FastAPI. Меняем на `RedirectResponse('/auth/error?reason=sso_failed', 302)`. Для случая nonce mismatch — отдельный reason `nonce_mismatch` (audit-event сохраняется как сейчас).

### 3.7. Logout — НЕ убиваем Keycloak SSO-сессию
**Изменение относительно текущего поведения:** не вызываем Keycloak end-session endpoint. Просто:
1. Удаляем серверную сессию из Redis (`delete_session`).
2. Удаляем cookie `portal_session`.
3. Редиректим на `/auth/error?reason=logged_out` (Keycloak-юзер) или `/auth/local?logged_out=1` (локальный).

**Последствие:** при возврате на портал доменный пользователь автоматически перелогинится (Kerberos выдаст ticket). Это согласовано с пользователем — для интранета это норма.

Для локальных пользователей этого эффекта нет — они снова попадут в форму на `/auth/local`.

Функция `kc_service.get_logout_url(...)` остаётся, но больше не вызывается из `logout()`. Можно пометить deprecated либо удалить, если нет других вызовов.

### 3.8. Endpoint `/auth/config`
Используется фронтом (`AuthLocalPage`, `AuthErrorPage`). Без изменений.

### 3.9. Брендинг Keycloak
**Вне scope.** Отдельный тикет, выполняется позже.

---

## 4. Изменения по файлам

### 4.1. Frontend

#### `frontend/src/router.ts`
- Удалить route `/login` → новый route `/login` с `redirect: '/api/v1/auth/login'` (для старых закладок). На уровне Vue Router это не сработает для абсолютных URL — реализуем через компонент-стаб с `onMounted(() => window.location.replace('/api/v1/auth/login'))` или `beforeEnter` guard.
- Добавить route `/auth/local` → `AuthLocalPage.vue`, `meta: { public: true }`.
- Добавить route `/auth/error` → `AuthErrorPage.vue`, `meta: { public: true }`.
- Удалить ветку `to.meta.guestOnly` из guard.
- Заменить `auth.redirectToLogin(to.fullPath)` → `auth.redirectToSSO(to.fullPath)`.
- Маршрут `/auth/local` для уже залогиненных → редирект на `/` (логика внутри компонента, через `onMounted`).

#### `frontend/src/stores/auth.ts`
- `redirectToLogin(path)` → переименовать в `redirectToSSO(path)`. Реализация по 3.1: counter `sso_attempts`, проверка лимита, навигация.
- `loadUser()` при успехе → очистить `sso_attempts` и `sso_failed`.
- Новый метод `markSSOFailed(reason)` — `sessionStorage.setItem('sso_failed', reason)`.
- Новый метод `clearSSOState()` — очищает оба ключа (используется кнопкой «Войти снова»).

#### `frontend/src/api/index.ts`
- В `_handle401` заменить `/login?redirect=...` на `/api/v1/auth/login?redirect=...`.
- Whitelist путей (где не редиректим): убрать `/login`, добавить `/auth/local`, `/auth/error`. `/p/` оставить.

#### `frontend/src/pages/LoginPage.vue`
**Действие:** удалить.

#### `frontend/src/pages/AuthLocalPage.vue` (новый)
- Скопировать визуальную часть из `LoginPage.vue` (split layout, branding hero).
- Убрать кнопку «Войти через SSO» — только локальный логин.
- В заголовке: `t('auth.adminLoginTitle')` (например, «Локальный вход»).
- При смонтировании:
  - Если `auth.isAuthenticated` → `router.replace('/')`.
  - Запросить `/auth/config`. Если `local_auth_enabled === false` → показать `n-alert`, скрыть форму.
  - Если `?logged_out=1` → показать `n-alert success` «Вы вышли из системы».
- После `localLogin` → `router.push(redirectTo || '/admin')`.
- **Email pre-fill убран** (по решению).

#### `frontend/src/pages/AuthErrorPage.vue` (новый)
- Минималистичный дизайн с тем же hero-блоком.
- Маппинг `reason → i18n key`:
  - `sso_failed` → `auth.error.ssoFailed`
  - `logged_out` → `auth.error.loggedOut`
  - `loop_detected` → `auth.error.loopDetected`
  - `keycloak_unavailable` → `auth.error.keycloakUnavailable`
  - `nonce_mismatch` → `auth.error.ssoFailed` (общая формулировка для пользователя)
- Кнопка «Войти снова»: вызывает `auth.clearSSOState()` + `window.location.href = '/api/v1/auth/login?redirect=' + redirectTo`.
- В футере мелкая ссылка `<router-link to="/auth/local">{{ t('auth.error.adminLoginLink') }}</router-link>`.
- При монтировании НЕ очищаем `sso_failed` (иначе случится авто-редирект на главной).

#### `frontend/src/i18n/ru.json` и `en.json`
Добавить ключи:
- `auth.adminLoginTitle`
- `auth.error.title`
- `auth.error.ssoFailed`
- `auth.error.loggedOut`
- `auth.error.loopDetected`
- `auth.error.keycloakUnavailable`
- `auth.error.retry`
- `auth.error.adminLoginLink`
- `auth.localDisabled`
- `auth.loggedOutSuccess`

Оба языка обновляются одновременно (`i18n:check` обязан быть зелёным).

### 4.2. Backend

#### `backend/app/api/auth.py`
- В `callback()`:
  - При `error` от Keycloak → `RedirectResponse('/auth/error?reason=sso_failed', 302)`.
  - При `pkce is None` (invalid state) → `RedirectResponse('/auth/error?reason=sso_failed', 302)` + `push_audit_event('auth.sso_failed', metadata={'reason': 'invalid_state'})`.
  - При сбое `exchange_code_for_tokens` → `RedirectResponse('/auth/error?reason=sso_failed', 302)` + audit `auth.sso_failed` (`reason=token_exchange_failed`).
  - При сбое `parse_jwt_claims` → `RedirectResponse('/auth/error?reason=sso_failed', 302)` + audit `auth.sso_failed` (`reason=jwt_invalid`).
  - При nonce mismatch → `RedirectResponse('/auth/error?reason=sso_failed', 302)` + сохранить существующий `auth.nonce_mismatch` audit + новый `auth.sso_failed` (`reason=nonce_mismatch`).
- В `logout()` (POST):
  - **Не вызывать** `kc_service.get_logout_url(...)`.
  - Удалить сессию + cookie.
  - Для `auth_source == "local"` → 302 на `/auth/local?logged_out=1`.
  - Для `keycloak` → 302 на `/auth/error?reason=logged_out`.
- В `logout_get()`:
  - 302 на `/auth/error?reason=logged_out` (вместо `/login`).

#### `backend/app/services/audit.py` (или соответствующий)
- Добавить тип события `auth.sso_failed` в реестр известных типов (если есть валидация).

#### `backend/app/core/redirects.py`
- Проверить, что `safe_redirect` пропускает `/auth/local`, `/auth/error`, `/admin`. Регексп уже должен пропускать (это абсолютные пути) — добавить unit-тест на всякий случай.

#### `backend/app/services/keycloak.py`
- Функция `get_logout_url(...)` остаётся, но не вызывается из `logout()`. Если нет других вызовов — пометить `# noqa: kept for future SLO support` или удалить (решение на момент PR 1).

### 4.3. Nginx

Никаких изменений — все новые пути (`/auth/local`, `/auth/error`) обслуживаются SPA через fallback на `index.html`.

### 4.4. Документация

#### `AGENTS.md`
- В разделе «Аутентификация» обновить: упомянуть авто-SSO, `/auth/local` как backdoor для локальных админов, отсутствие Keycloak end-session при logout.

#### `docs/integration-keycloak-nextcloud.md`
- Описать: «локальный вход доступен по `/auth/local`, не индексируется в UI».

#### `docs/deploy.md`
- В onboarding-чеклисте: bootstrap-admin логинится через `/auth/local` после первого запуска.

#### `docs/adr.md`
- Новый ADR: «Авто-SSO + локальный backdoor через `/auth/local`. Logout не убивает Keycloak SSO-сессию (приемлемо для интранета)».

---

## 5. Тесты

### 5.1. Backend (`backend/tests/`)

#### `tests/integration/test_auth_callback_errors.py` (новый)
- `test_callback_with_oidc_error_redirects_to_auth_error` — `?error=login_required` → 302 на `/auth/error?reason=sso_failed`.
- `test_callback_with_invalid_state_redirects` — невалидный state → 302 на `/auth/error?reason=sso_failed` + audit `auth.sso_failed`.
- `test_callback_token_exchange_failure_redirects` — мок httpx, который бросает → 302 на `/auth/error` + audit.
- `test_callback_nonce_mismatch_redirects` — подменённый nonce → 302 на `/auth/error` + два audit-event (`auth.nonce_mismatch` + `auth.sso_failed`).

#### `tests/integration/test_auth_logout.py` (правка)
- `test_logout_local_redirects_to_auth_local` — после `POST /auth/logout` для локального юзера → 302 на `/auth/local?logged_out=1`.
- `test_logout_keycloak_redirects_to_auth_error` — для Keycloak юзера → 302 на `/auth/error?reason=logged_out`.
- `test_logout_does_not_call_keycloak_end_session` — мок Keycloak service, проверить, что `get_logout_url` не вызывался.

#### `tests/unit/test_redirects.py` (правка)
- Тест что `safe_redirect` принимает `/auth/local`, `/auth/error`, `/admin`, `/`.

### 5.2. Frontend (`frontend/tests/`)

#### `tests/unit/router-guard.spec.ts` (правка)
- `test: guest without session → redirectToSSO called`
- `test: sso_failed flag set → no redirect, navigation to /auth/error`
- `test: deep link preserved in redirect param`
- `test: /auth/local accessible without session`
- `test: /auth/error accessible without session`
- `test: /login → redirect to /api/v1/auth/login`

#### `tests/unit/auth-store.spec.ts` (правка/новый)
- `test: redirectToSSO appends timestamp to sso_attempts and navigates`
- `test: loadUser success clears sso_attempts and sso_failed`
- `test: loop detection — 2 attempts within 30s → /auth/error?reason=loop_detected, no redirect`
- `test: clearSSOState removes both keys`
- `test: attempts older than 30s are filtered out, fresh attempt allowed`

#### `tests/e2e/auth-sso-redirect.spec.ts` (новый)
- Открыть `/` без cookie → ожидается редирект на `/api/v1/auth/login` (мок через Playwright `page.route()`).
- Открыть `/kb/articles/123` без cookie → редирект с `?redirect=/kb/articles/123`.
- Открыть `/auth/error?reason=sso_failed` → видна кнопка «Войти снова» и ссылка «Вход для администратора».
- Открыть `/auth/error?reason=logged_out` → видно сообщение об успешном выходе.
- Loop scenario: дважды редиректнуть на `/api/v1/auth/login` (мок Keycloak, который возвращает на `/` без cookie) → третий заход уходит на `/auth/error?reason=loop_detected`.

#### `tests/e2e/admin-login.spec.ts` (новый, заменяет `local-login.spec.ts`)
- Открыть `/auth/local` → видна форма, нет кнопки SSO.
- Залогиненный пользователь открывает `/auth/local` → редирект на `/`.
- Ввести валидные креды → редирект на `/admin`.
- Ввести невалидные → видна ошибка.
- При `LOCAL_AUTH_ENABLED=false` (env override) → видно сообщение «Локальный вход выключен», форма скрыта.
- `?logged_out=1` → видно сообщение об успешном выходе.

#### `tests/e2e/local-login.spec.ts`
**Действие:** удалить (заменён `admin-login.spec.ts`).

### 5.3. E2E mock-стратегия для Keycloak
На тест-сервере **нет реального Keycloak**. Используем Playwright `page.route()` для моков:
- `/api/v1/auth/login` → 302 на тест-callback с фиксированным state
- `/api/v1/auth/callback` → реальный backend (но с замоканным httpx внутри bullet через fixtures `pytest-httpx` для backend integration tests)

Для E2E auth-flow тестов реальный backend стартует с `KEYCLOAK_URL=http://localhost:9999` (несуществующий) — все Keycloak-вызовы перехватываются на уровне httpx через monkey-patch в `conftest.py`.

---

## 6. Миграции / данные

Нет изменений схемы БД. Нет миграций.

---

## 7. Риски и митигации

| Риск | Митигация |
|---|---|
| Бесконечный редирект если Keycloak возвращает `error=login_required` | Counter `sso_attempts` (2 попытки/30s) → `/auth/error?reason=loop_detected` |
| Cookie не выставилось (прокси режет SetCookie) | Тот же counter ловит этот случай |
| Админ потерял доступ из-за сбоя Keycloak | `/auth/local` работает независимо |
| Logout: пользователь снова прозрачно залогинится | Согласовано с product owner — приемлемо для интранета |
| Старые закладки на `/login` | Стаб-route с `window.location.replace('/api/v1/auth/login')` |
| Тесты E2E без реального Keycloak | Mock через `page.route()` + monkey-patch httpx в backend |
| `LOCAL_AUTH_ENABLED=false` блокирует bootstrap-admin | Backend bootstrap создаёт юзера всегда; admin может включить флаг через env и перезапустить контейнер |
| Утечка `return_to` в логи | `safe_redirect` фильтрует, structlog truncate (если ещё не настроен — добавить) |
| `keycloak_enabled=false` в runtime | Авто-редирект гостя идёт на `/auth/local` (роутер-гард читает config или fallback на try-catch) |

---

## 8. План раскатки (3 PR)

### PR 1: Backend
- Изменения в `api/auth.py` (callback errors → redirect, logout без Keycloak end-session).
- Новый audit-event тип `auth.sso_failed`.
- Новые/обновлённые backend-тесты (`test_auth_callback_errors.py`, `test_auth_logout.py`, `test_redirects.py`).
- `pytest && ruff check && mypy app` — зелёные.
- На этапе merge: фронт ещё на `LoginPage`, `/auth/error` отдаёт SPA-fallback (404 в Vue router) — это терпимо, потому что в нормальном flow callback не падает.

### PR 2: Frontend — новые страницы (без переключения поведения)
- Добавить `AuthLocalPage.vue`, `AuthErrorPage.vue`, новые routes.
- Обновить `i18n/ru.json` и `en.json`.
- Старый `LoginPage.vue` ещё на месте, route `/login` работает как раньше.
- Unit-тесты для новых страниц (smoke).
- `npm run lint && typecheck && test:unit && i18n:check` — зелёные.

### PR 3: Frontend — переключение поведения
- Удалить `LoginPage.vue`.
- Заменить route `/login` на стаб-редирект.
- Обновить router-guard (`redirectToSSO` вместо `redirectToLogin`).
- Обновить `_handle401` в `api/index.ts`.
- Обновить `auth-store` (counter logic, `clearSSOState`).
- Удалить `local-login.spec.ts`, добавить `admin-login.spec.ts` и `auth-sso-redirect.spec.ts`.
- Обновить `AGENTS.md`, `docs/adr.md`, `docs/deploy.md`, `docs/integration-keycloak-nextcloud.md`.
- Smoke-тест на staging: домен / не-домен / локальный admin / logout / закладка.

После PR 3 — production deploy.

---

## 9. Чек-лист готовности

- [ ] Бэкенд: callback редиректит на `/auth/error?reason=sso_failed` при всех видах ошибок
- [ ] Бэкенд: новый audit-event `auth.sso_failed` пишется при каждой ошибке callback
- [ ] Бэкенд: logout редиректит на `/auth/error?reason=logged_out` (Keycloak) или `/auth/local?logged_out=1` (локальный)
- [ ] Бэкенд: `kc_service.get_logout_url` НЕ вызывается из `logout()`
- [ ] Фронт: route `/auth/local` работает, форма видна, локальный вход проходит
- [ ] Фронт: уже залогиненный на `/auth/local` → редирект на `/`
- [ ] Фронт: route `/auth/error` работает, кнопка «Войти снова» сбрасывает state и редиректит на `/api/v1/auth/login`
- [ ] Фронт: router-guard авто-редиректит гостя на `/api/v1/auth/login` с `redirect=...`
- [ ] Фронт: `_handle401` редиректит на `/api/v1/auth/login` (а не на `/login`)
- [ ] Фронт: `LoginPage.vue` удалён, `/login` отдаёт стаб-редирект
- [ ] Loop-detection: 2 попытки за 30 секунд → `/auth/error?reason=loop_detected`
- [ ] `clearSSOState()` сбрасывает counter при ручном клике «Войти снова»
- [ ] `loadUser()` успех → очистка counter и `sso_failed`
- [ ] `return_to` сохраняется при глубоких ссылках
- [ ] i18n ключи добавлены в `ru.json` и `en.json`, `npm run i18n:check` зелёный
- [ ] Все тесты (`pytest`, `npm run test:unit`, `npm run test:e2e`) проходят
- [ ] `npm run lint && npm run typecheck && ruff check && mypy app` — зелёные
- [ ] Smoke-тест на staging пройден: домен / не-домен / локальный admin / logout / закладка
- [ ] AGENTS.md, docs/adr.md, docs/deploy.md, docs/integration-keycloak-nextcloud.md обновлены
