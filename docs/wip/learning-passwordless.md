# Фича: вход внешних обучаемых по коду из письма (passwordless)

## Цель

Убрать пароли у внешних учёток `learning_accounts` (learn-контур): вход — email → 6-значный
код письмом → код → сессия. Причина: задачи приходят редко, пароли забывают; каждый вход
генерирует новый код. Запасной путь — админ выдаёт код вручную в админке.

## Решения по ходу

- 2026-09-04: владелец принял — код 6 цифр, TTL 10 мин, макс 5 попыток, сессия 8 ч (как была),
  запасной путь «админский код» (вариант А), падение SMTP — приемлемый риск (почта
  корпоративная, падение заметят).
- 2026-09-04: migration 113 — CREATE `learning_login_codes` + GRANT learning_app +
  `password_hash DROP NOT NULL`.
- 2026-09-04 (решение владельца при ревью PR: на проде внешних учёток ещё нет):
  **миграция 114 сделана в этом же PR** — дроп `password_hash`/`must_change_password`/
  `failed_attempts`/`locked_until` и таблицы `learning_password_resets`; cleanup-воркер
  чистит только коды. Следствие: откат релиза ниже 113 невозможен (колонок нет) —
  принятый риск, учёток на проде нет.
- 2026-09-04: сессионный payload теряет `restricted_to`; старые живые Redis-сессии с этим
  полем совместимы (поле просто игнорируется резолвером).
- 2026-09-04: nginx не трогаем — зона `learning_auth` матчит префикс
  `^/api/v1/auth/learning/` (learn_server.conf.tmpl:60), `verify` покрыт автоматически.
- 2026-09-04: единый отказ verify = 400 «Invalid or expired code» (анти-enumeration: не
  отличить нет учётки / нет кода / неверный / истёк / исчерпаны попытки). Запрос кода
  отвечает `{"ok": true}` всегда.
- 2026-09-04: старые ссылки `/forgot`, `/reset`, `/reset-password` learn-роутера → redirect
  на `/login` (письма с reset-ссылками имеют TTL 60 мин, жить они перестают сразу).

## Ключевые точки кода

- Сервис: `backend/app/services/learning/accounts_service.py` (request/verify/issue кодов),
  `sessions.py` (payload), `emails.py` (билдер `login_code`).
- Роуты: `backend/app/api/learning/auth_routes.py` (login/verify/logout),
  `admin_routes.py` (`POST /accounts/{id}/login-code`).
- CSRF origin-only: `middleware/csrf.py` — `{/auth/learning/login, /auth/learning/verify}`.
- Фронт learn: `src/learn/pages/LearnLoginPage.vue` (двухшаговый), `router.ts`,
  `authGuard.ts`, `api/learningAuth.ts`.
- Админка: `src/components/learning/AccountsTab.vue` (создание без пароля, «выдать код»).
- E2E learner: код извлекается из `email_outbox.body_text` (regex `\b\d{6}\b`),
  helper вместо `fetchTempPasswordFromOutbox`.

## Грабли / контекст

- GRANT learning_app обязателен в той же миграции, что и CREATE (инцидент 109→112).
- outbox-письмо уходит ~10 с (cron `process_email_outbox`) — в UI честно писать «до минуты».
- Лимиты: IP 5/15 + email-хэш 10/15 на оба публичных эндпоинта (как был логин);
  перебор кода закрыт 5 попытками на код (счётчик attempts в строке кода).
- `secrets.randbelow(1_000_000)` + zero-pad — без modulo bias; сравнение хэшей —
  `hmac.compare_digest`.
- Инвалидация кодов при `admin_set_status(blocked)` — не забыть.
- `EmailStr` не использовать (`.local`-домены) — валидатор `_validate_email` из схем.

## Чеклист (DoD)

- [x] ветка `feat/learning-login-code`, этот план
- [x] миграция 113 (таблица + GRANT + DROP NOT NULL)
- [x] миграция 114 (дроп парольных колонок + learning_password_resets) — в этом же PR
- [x] модель LearningLoginCode + экспорт
- [x] сервис кодов (request/verify/issue) + удаление парольной механики
- [x] письма: login_code; удаление account_created/admin_password_reset/password_reset_link
- [x] роуты auth login/verify + admin login-code + CSRF
- [x] схемы/config/deps/sessions/audit/cleanup
- [x] unit-тесты rewrite + integration + security (unit 5117✓*, integration 695✓, security ✓)
      (*2 фейла test_meetings_rsvp_unit — локальный python без aioimaplib, к фиче не относятся)
- [x] learn-фронт двухшаговый вход, удаление страниц, i18n ru+en
- [x] админка: создание без пароля + «выдать код»
- [x] frontend unit (2745✓) + e2e visual (28✓) + e2e learner (6✓, реальный стек)
- [x] доки learning.md / wip / roles-matrix / db-schema / api-contracts + check-drift
- [ ] ci_lint ✓, diff-cover backend+frontend ≥80% — финальный прогон

## После релиза

- Ничего — миграция 114 вошла в этот же PR (см. решения выше).
