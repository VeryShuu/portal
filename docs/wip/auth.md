# Фича: устойчивое поддержание сессии при фоновой работе вкладки

> **Когда читать:** работаешь над авторизацией / silent refresh / «вылетает на
> логин после фона» / экран «Слишком много попыток входа».
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Удалить после мёржа фичи.

## Цель

Сделать так, чтобы вкладка, провисевшая в фоне (свёрнута / другая вкладка /
сон ноутбука), при возврате **тихо восстанавливала сессию** без полного
редиректа через SSO и без экрана `loop_detected` («Слишком много попыток
входа / обнаружен бесконечный редирект»). Потолок комфортной фоновой работы —
вплоть до Keycloak SSO Session Idle (8 ч), а не 15 минут.

---

## Контекст: как сейчас устроено поддержание сессии

- Логин (Keycloak OIDC + PKCE) → Redis-сессия `session:{uuid}` с
  `{access_token, refresh_token, id_token, user_id, auth_source}`,
  `SESSION_TTL = 8h` (`backend/app/services/session.py`).
- В браузер уходит только opaque `session_id` в cookie `portal_session`
  (HTTPOnly + Secure + SameSite=Lax, 8 ч). JWT в cookie не кладётся.
- На **каждый** запрос `get_current_user` (`backend/app/api/deps.py:84-91`)
  парсит `access_token` JWT с `verify_exp=True`
  (`backend/app/core/security.py:128`) → при истёкшем токене 401.
- **Silent refresh по таймеру** (`frontend/src/stores/auth.ts:29-38`):
  `setInterval(refreshAuth, 4 мин)` после успешного `loadUser/loadBootstrap`.
- **Retry-on-401** (`frontend/src/api/index.ts:119-144`): любой 401 (кроме
  самого `/auth/refresh`) → singleton `refreshAuth()` → один повтор запроса;
  при неудаче — `_handle401()` → редирект на `/api/v1/auth/login`.
- **`POST /auth/refresh`** (`backend/app/api/auth/me.py:51-125`): обновляет
  токены **in-place** под стабильным `session_id` (ADR-042), per-session
  Redis-lock + коалесинг (`REFRESH_COALESCE_WINDOW_S = 10s`).
- **session_sliding_window** (`backend/app/middleware/session.py`): продлевает
  Redis-TTL до 8 ч на каждом запросе (throttle 5 мин). Продлевает только
  Redis-сессию, **не** жизнь Keycloak-токенов.
- **Loop-guard** двойной: клиент (`sessionStorage sso_attempts`, ≥2/30s →
  `/auth/error?reason=loop_detected`) + сервер (HTTPOnly cookie `sso_attempts`,
  ≥5/30s, `backend/app/api/auth/_helpers.py:43-86`, `oidc.py:60-78`).

### Тайминги Keycloak (текущий realm — подтверждено пользователем)

| Параметр | Значение |
|---|---|
| Access Token Lifespan | **15 минут** |
| SSO Session Idle | **8 часов** |
| SSO Session Max | **12 часов** |

Вывод: refresh-токен живёт до 8 ч простоя — Keycloak **не** является узким
местом. Потолок фоновой работы упирается в дефект `/auth/refresh` (ниже).

---

## Корневая причина (критично)

**`POST /auth/refresh` не может обновить просроченный access-токен, потому что
сам зависит от валидного access-токена.**

`refresh_token_endpoint(user: CurrentUser, ...)` (`me.py:56`) → `CurrentUser` →
`get_current_user` → `parse_jwt_claims(access_token, verify_exp=True)`. Если
access-токен истёк (прошло > 15 мин без refresh), эндпоинт отдаёт **401 ещё до
выполнения тела** — то есть отказывается рефрешить ровно тогда, когда refresh и
нужен.

- В **foreground** не проявляется: таймер бьёт на 4-й минуте (< 15 мин), токен
  всегда «живой», refresh проходит.
- В **фоновой/спящей вкладке** браузер замораживает `setInterval` (Chrome
  троттлит фоновые таймеры; при сне ноутбука они вообще не тикают) → токен
  истекает → задекларированный в ADR-035 «safety-net» retry-on-401 →
  `/auth/refresh` → **401** → `_handle401()` → полный редирект на
  `/api/v1/auth/login`.

Это прямо противоречит ADR-035 (`docs/adr.md:958,968`), где retry-on-401 заявлен
как страховка именно для «tab was suspended / laptop went to sleep». Вместо
тихого refresh получается жёсткий full-page bounce через SSO, который при
нескольких триггерах / edge-кейсах добивает счётчик loop-guard → экран
**«Слишком много попыток входа»** (скриншот из задачи).

---

## Сопутствующие слабые места

2. **Нет реакции на возврат фокуса вкладки.** Во всём `frontend/src` нет
   обработчика `visibilitychange`/`focus`/`online` для авторизации (есть только
   в фотослайдшоу `components/photos/LightboxModal.vue`). При возврате к
   замороженной вкладке ничто проактивно не освежает токен — ждём первый 401.
3. **UX просроченной сессии.** Когда re-login реально нужен, пользователь видит
   пугающее «Слишком много попыток входа / бесконечный редирект» вместо
   спокойного «Сессия истекла → Войти». Loop-guard ловит легитимный кейс
   «вернулся после долгого простоя».
4. **Мёртвый код.** `get_silent_auth_url` (`prompt=none`,
   `backend/app/services/keycloak/oidc.py:34`) только реэкспортируется, нигде не
   вызывается (ADR-036 отложил). `/auth/login` всегда интерактивный.
5. **Согласование TTL.** `SESSION_TTL=8h` (Redis) vs SSO Session Idle 8h vs SSO
   Max 12h. После фикса refresh связующий потолок — SSO Session Max (12h, хард-кап)
   и Redis-TTL 8h (sliding). Логично выровнять Redis-TTL с SSO Idle (уже совпали).

---

## План исправления (по приоритету)

### П.1 [Критично] Развязать `/auth/refresh` от валидного access-токена

Эндпоинт должен авторизоваться **только по Redis-сессии (cookie) + наличию
`refresh_token`**, не парся истёкший access-токен.

- Ввести «облегчённую» зависимость (например `get_session_for_refresh`), которая
  читает `session_id` из cookie + `get_session(redis, session_id)`, проверяет
  `auth_source`, грузит пользователя из БД по `user_id`/`keycloak_id`, проверяет
  `deleted_at`, но **не** валидирует `exp` access-токена.
- `refresh_token_endpoint` переключить на неё вместо `CurrentUser`. Вся остальная
  логика (lock, коалесинг, обмен в Keycloak, in-place save, rate-limit 30/мин)
  сохраняется без изменений.
- Сохранить текущие 401-кейсы: нет cookie / нет сессии / нет refresh_token /
  user.deleted_at.
- **Контракт** `/auth/refresh` меняется только по поведению (теперь принимает
  истёкший access), не по сигнатуре/пути → обновить ADR-035, перегенерировать
  `docs/api-contracts.generated.md` при необходимости.

Эффект: возврат к фоновой вкладке (до 8 ч) = тихий in-place refresh без
редиректа и перезагрузки.

### П.2 [Высокий] Refresh по `visibilitychange`

В `frontend/src/stores/auth.ts`:
- Слушатель `document.addEventListener('visibilitychange', ...)`: при переходе в
  `visible` и если прошло достаточно времени с последнего refresh — немедленный
  `refreshAuth()` + переустановка таймера (таймер мог быть заморожен).
- Снимать слушатель в `onScopeDispose` (рядом с существующими `auth:expired` /
  `stopSilentRefresh`).
- Лечит токен в момент возврата, **до** первого 401. Вместе с п.1 убирает bounce
  для типового кейса полностью.

### П.3 [Средний] Грациозный re-login вместо «loop detected»

- Различать «нужен интерактивный вход после простоя» и «реальный цикл
  редиректов». В первом случае — спокойный экран «Сессия истекла → Войти»
  (а не `reason=loop_detected`).
- Вариант: при первом честном 401 после долгого фона — не редиректить молча, а
  показать мягкий промпт; loop-guard оставить только как backstop от настоящих
  циклов.
- Затрагивает `AuthErrorPage.vue` + i18n (`reason=session_expired`?) +
  логику `_handle401`/`redirectToSSO`.

### П.4 [Мелочь] Убрать мёртвый `get_silent_auth_url`

Либо удалить, либо довести историю `prompt=none` до конца (ADR-036). Низкий
приоритет, отдельным коммитом.

---

## Чеклист (DoD)

- [x] П.1: новая зависимость `get_user_for_refresh` в `backend/app/api/deps.py`
      (+ `RefreshUser`; имя отличается от плана — `get_user_for_refresh`)
- [x] П.1: `me.py::refresh_token_endpoint` переведён на неё, 401-кейсы сохранены
- [x] П.1: unit-тесты — refresh с истёкшим access успешен; без сессии/refresh/
      deleted_at → 401 (`backend/tests/unit/test_auth_routes.py::TestGetUserForRefresh`)
- [x] П.2: `visibilitychange`-refresh в `stores/auth.ts` + снятие слушателя
- [x] П.2: unit-тест на стор (`frontend/tests/unit/auth-store-visibility.spec.ts`)
- [x] П.3: грациозный экран «сессия истекла» (`reason=session_expired`,
      `redirectToSessionExpired`) + i18n ru/en + тест в visibility-spec
- [x] lint + typecheck + tests pass (back + front)
- [x] обновлён ADR-035 (поведение `/auth/refresh`) + `docs/adr.md`
- [ ] (опц.) П.4 удаление мёртвого кода `get_silent_auth_url` — не делалось

## Грабли / контекст

- `parse_jwt_claims` использует `verify_exp=True` — это и ломает refresh на
  истёкшем токене. НЕ ослаблять проверку в `get_current_user` (нужна для всех
  обычных эндпоинтов) — именно поэтому нужна отдельная зависимость для refresh.
- ADR-042: токены обновляются **in-place** под стабильным `session_id` — не
  ломать (ротация session_id убьёт параллельные вкладки). Per-session lock +
  коалесинг сохранить.
- Мультитаб: refreshAuth — singleton-promise (`api/index.ts:86-103`); при
  visibilitychange из N вкладок реальный обмен с Keycloak один (коалесинг 10s).
- Loop-guard трогать осторожно: клиент `sso_attempts` (sessionStorage, ≥2/30s) +
  сервер cookie (≥5/30s). Менять только семантику «честный re-login ≠ loop».
- KC realm: Access 15m / SSO Idle 8h / SSO Max 12h. У пользователя есть доступ к
  Keycloak — можно уточнить/поменять при необходимости.
- `refetchOnWindowFocus: false` (`frontend/src/main.ts:35`) — burst рефетчей на
  фокусе НЕ происходит, отдельно гасить не нужно.
