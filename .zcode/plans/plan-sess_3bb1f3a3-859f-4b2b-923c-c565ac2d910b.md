# Фикс локальной авторизации: редирект на Keycloak вместо /auth/local

## Корень проблемы (диагноз)

Это регрессия из июня 2026 (коммит `d5e950d`). Тогда починили **один** из трёх симметричных код-путей, два остальных пропустили:

1. **`redirectToSSO`** (`frontend/src/stores/auth.ts:240-254`) — router guard всегда шлёт на `/api/v1/auth/login` (Keycloak), игнорируя `auth_source`. Нарушение ADR-036 п.7. Самое заметное проявление: любой cold-start защищённого роута у local-юзера → Keycloak.
2. **Холодный старт** — `_sessionAuthSource` это in-memory переменная модуля (`api/index.ts:26`) с дефолтом `'keycloak'`. Новая вкладка/перезапуск → знание о типе сессии потеряно → даже починенный `_handle401` не спасёт.
3. **`logout()`** (`stores/auth.ts:271-284`) — всегда шлёт на `/auth/error?reason=logged_out`, хотя ADR-036 п.5 требует для local → `/auth/local?logged_out=1`. **Бэкенд уже умеет правильно** (`backend/app/api/auth/logout.py:41-48`) — баг только в том, что фронт не дожидается ответа и сразу делает `window.location.href`.

Бэкенд в порядке — `/auth/local/login`, `/auth/refresh` (401 для local), `/bootstrap`, `/auth/logout` работают корректно.

## Подход: бэкенд-управляемая cookie `portal_auth_method`

ADR-036 п.7 требует, чтобы знание «последний вход был локальным» жило у **бэкенда** (а не в localStorage). Реализация: бэкенд ставит/обновляет долгоживущую cookie `portal_auth_method` при каждом login/callback; фронт инициализирует `_sessionAuthSource` из неё на старте. Cookie — только транспорт маркера `'local'|'keycloak'` (не PII); бэкенд — authoritative source.

## Изменения

### Backend (5 правок)

1. **`backend/app/core/security.py`** — добавить константу `LAST_AUTH_METHOD_COOKIE = "portal_auth_method"` и `LAST_AUTH_METHOD_TTL = 30 * 24 * 3600` (30 дней) рядом с существующими `SESSION_COOKIE_NAME`.

2. **`backend/app/api/auth/local.py::local_login`** — после установки `portal_session` дополнительно `resp.set_cookie(LAST_AUTH_METHOD_COOKIE, "local", max_age=LAST_AUTH_METHOD_TTL, httponly=False, samesite="lax", path="/", secure=is_production)`. Не HttpOnly — фронт читает напрямую (как XSRF-TOKEN).

3. **`backend/app/api/auth/oidc.py`** (callback success path) — аналогично поставить `portal_auth_method=keycloak` при успешном OIDC exchange (найти место через `_build_session_cookie_response` или сразу после).

4. **`backend/app/api/auth/logout.py::logout`** — НЕ вызывать `redirect.delete_cookie('portal_auth_method')`. Оставить знание о способе входа (только `portal_session` удаляется). Это и так уже так — но зафиксировать комментарием.

5. **`backend/app/api/auth/local.py::auth_config`** — расширить response: читать cookie `portal_auth_method` (через параметр `request: Request`) и добавлять поле `"last_auth_method": "local" | "keycloak" | null`. Обратная совместимость: старые клиенты игнорируют новое поле.

### Frontend (3 правки)

6. **`frontend/src/api/index.ts`** — инициализировать `_sessionAuthSource` из cookie на загрузке модуля (вместо хардкод-дефолта):
   ```ts
   let _sessionAuthSource: 'keycloak' | 'local' =
     readCookie('portal_auth_method') === 'local' ? 'local' : 'keycloak'
   ```
   `setSessionAuthSource(...)` остаётся без изменений (тесты проверяют null → keycloak).

7. **`frontend/src/stores/auth.ts::redirectToSSO`** — добавить ветку `auth_source === 'local'` (аналогично `_handle401`):
   ```ts
   const loginUrl = _sessionAuthSource === 'local' ? '/auth/local' : '/api/v1/auth/login'
   ```
   Импортировать `getSessionAuthSource()` (новый геттер, экспортируемый из `api/index.ts` — нужен, т.к. `_sessionAuthSource` приватная).

8. **`frontend/src/stores/auth.ts::logout`** — дожидаться ответа бэкенда (он уже даёт 302 на нужный URL), либо явно проверить `auth_source` **до** очистки `user.value` и направить локального юзера на `/auth/local?logged_out=1`. Выбрано второе (predictable, не зависит от ofetch-поведения):
   ```ts
   function logout(): void {
     const wasLocal = user.value?.auth_source === 'local'
     user.value = null
     isHelpdeskAgent.value = false
     stopSilentRefresh()
     api('/auth/logout', { method: 'POST' }).finally(() => {
       window.location.href = wasLocal
         ? '/auth/local?logged_out=1'
         : '/auth/error?reason=logged_out'
     })
   }
   ```

### Документация (1 правка)

9. **`docs/adr.md` ADR-036 п.7** — расширить: явно зафиксировать, что **все три** редирект-пути (`_handle401`, `redirectToSSO`, `logout`) уважают `auth_source`; бэкенд управляет долгоживущей cookie `portal_auth_method`; фронт инициализирует `_sessionAuthSource` из неё. Зафиксировать инвариант: cookie обновляется только на login/callback, переживает logout (знание о способе входа сохраняется для UX корректного re-login).

## Тесты

### Backend (`backend/tests/unit/test_auth_routes.py` — дополнить)
- `local_login` ставит cookie `portal_auth_method=local` с `httponly=False`, `max_age=30d`
- `oidc callback` ставит cookie `portal_auth_method=keycloak`
- `logout` сохраняет cookie `portal_auth_method` (не удаляет)
- `auth_config` возвращает `last_auth_method` из cookie (для всех трёх случаев: local / keycloak / отсутствует → null)

### Frontend
- **`frontend/tests/unit/cov-core-api-index.spec.ts`** — добавить тест: при наличии cookie `portal_auth_method=local` `_sessionAuthSource` инициализируется как `'local'` (даже без явного `setSessionAuthSource`).
- **`frontend/tests/unit/auth-store-sso.spec.ts`** — добавить тест: `redirectToSSO` для local-сессии шлёт на `/auth/local`, а не `/api/v1/auth/login`.
- **`frontend/tests/unit/auth-store-extra.spec.ts`** — добавить тест: `logout()` для local-пользователя шлёт на `/auth/local?logged_out=1`; для keycloak — на `/auth/error?reason=logged_out`.

Существующие тесты `router-guards.spec.ts:43` (проверяет redirectToSSO → Keycloak) обновить: теперь зависит от `auth_source` — split на два кейса (default=Keycloak, local=/auth/local).

## DoD / верификация

- `cd backend && ruff check . && mypy app && pytest tests/unit` — pass
- `cd frontend && npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check` — pass
- Ручной smoke (после `docker compose build backend frontend`):
  1. Войти через `/auth/local` → открыть `/admin` → перезагрузить → остаться в системе (не Keycloak).
  2. Дождаться истечения Redis-сессии (или удалить через `redis-cli DEL session:*`) → перезагрузить `/admin` → должен попасть на `/auth/local?redirect=...`, **не** на Keycloak.
  3. Нажать «Выйти» из local-сессии → должен попасть на `/auth/local?logged_out=1`.
  4. Keycloak-юзер: те же сценарии должны вести на SSO/`/auth/error` (не сломано).

## Рекомендуемый коммит

```
fix(auth): локальный вход редиректил на Keycloak на холодном старте/logout

Регрессия из d5e950d (июнь 2026): починили _handle401, пропустили
redirectToSSO (router guard) и logout(). Добавлен бэкенд-управляемый
маркер portal_auth_method (30d cookie), по которому фронт на холодном
старте знает тип прошлой сессии.

- backend: cookie portal_auth_method в local_login/oidc callback,
  сохраняется через logout, exposed через /auth/config
- frontend: _sessionAuthSource инициализируется из cookie; redirectToSSO
  и logout() теперь уважают auth_source (симметрично с _handle401)
- docs: ADR-036 п.7 расширен — все 3 редирект-пути + cookie-контракт
- tests: +4 backend, +3 frontend кейсов
```

## Открытые вопросы для пользователя
- Нет. Все решения приняты в plan-mode.
